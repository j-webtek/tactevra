"""Build a bounded Isaac replay input from an arm-lane schedule report.

The retained bundle contains joint positions and Cartesian reference points only.
It cannot encode controller traffic or grant physical execution authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "tactevra.arm_joint_schedule_replay_bundle.v1"
ACTUAL_EMITTER_SCHEMA = "tactevra.arm_joint_schedule_replay_bundle.v2"
EXPECTED_ARM_JOINTS = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_replay_bundle(
    report: dict[str, Any], report_bytes: bytes, expected_arm_commit: str,
    *, require_actual_emitter: bool = False,
) -> dict[str, Any]:
    if report.get("arm_source_commit") != expected_arm_commit:
        raise ValueError("arm source commit differs from the requested source")
    if report.get("geometry_variant") != "UNMEASURED_SENSITIVITY_OVERLAY":
        raise ValueError("schedule did not use the declared simulation-only geometry")
    if report.get("ik", {}).get("status") \
            != "READY_FOR_INSTALLED_GEOMETRY_COLLISION_SCREENING":
        raise ValueError("arm IK did not reach the installed-geometry gate")
    schedule = report.get("schedule")
    if not isinstance(schedule, dict):
        raise ValueError("arm report contains no joint schedule")
    if schedule.get("schema") != "rocell.typing_joint_schedule.v1":
        raise ValueError("unsupported arm schedule schema")
    if schedule.get("hardware_access") is not False \
            or schedule.get("physical_authority") is not False \
            or schedule.get("hardware_commands_generated") != 0 \
            or schedule.get("controller_commands") != []:
        raise ValueError("schedule crossed the zero-authority replay boundary")

    ordered_targets = report.get("ordered_target_ids")
    proposal_targets = [
        item.get("target_id") for item in report.get("batch", {}).get("proposals", [])
    ]
    if not ordered_targets or proposal_targets != ordered_targets:
        raise ValueError("batch proposal order or repetitions differ from the request")

    samples = schedule.get("samples")
    trajectory_samples = report.get("trajectory", {}).get("screening_samples")
    ik_results = report.get("ik", {}).get("joint_results")
    if not isinstance(samples, list) or not samples:
        raise ValueError("schedule samples are missing")
    if not isinstance(trajectory_samples, list) or len(trajectory_samples) != len(samples):
        raise ValueError("trajectory and joint schedule sample counts differ")
    if not isinstance(ik_results, list) or len(ik_results) != len(samples):
        raise ValueError("IK and joint schedule sample counts differ")
    compact_samples: list[dict[str, Any]] = []
    for index, (sample, trajectory, ik_result) in enumerate(
        zip(samples, trajectory_samples, ik_results)
    ):
        if sample.get("sequence") != index or trajectory.get("sequence") != index:
            raise ValueError("schedule or trajectory sequence is not contiguous")
        if sample.get("action_index") != trajectory.get("action_index") \
                or sample.get("target_id") != trajectory.get("target_id") \
                or sample.get("phase") != trajectory.get("phase"):
            raise ValueError("schedule semantics differ from the Cartesian trajectory")
        joints = sample.get("joint_positions_rad")
        if not isinstance(joints, dict) or tuple(joints) != EXPECTED_ARM_JOINTS:
            raise ValueError("schedule uses a noncanonical arm joint order")
        if ik_result.get("accepted") is not True \
                or ik_result.get("hardware_commands_generated") != 0:
            raise ValueError("schedule contains an unaccepted or authoritative IK sample")
        point = trajectory.get("point")
        if not isinstance(point, dict) or point.get("frame") != "board":
            raise ValueError("trajectory point is not expressed in the board frame")
        compact_samples.append({
            "sequence": index,
            "time_from_start_ns": sample["time_from_start_ns"],
            "phase": sample["phase"],
            "phase_endpoint": sample["phase_endpoint"],
            "action_index": sample["action_index"],
            "target_id": sample["target_id"],
            "joint_positions_rad": joints,
            "expected_tool_tip_board_mm": [point["x"], point["y"], point["z"]],
        })

    contact_order = [
        sample["target_id"] for sample in compact_samples
        if sample["phase"] == "CONTACT" and sample["phase_endpoint"]
    ]
    if contact_order != ordered_targets:
        raise ValueError("contact endpoint order or repetitions differ from the request")
    ik_position_errors = [float(item["position_error_mm"]) for item in ik_results]
    ik_margins = [float(item["minimum_normalized_arm_joint_margin"]) for item in ik_results]
    batch_sha256 = _digest(_canonical(report["batch"]))
    producer: dict[str, Any] | None = None
    if require_actual_emitter:
        input_sha256 = report.get("actual_emitter_input_sha256")
        payload_sha256 = report.get("actual_emitter_payload_sha256")
        if report.get("actual_shared_emitter_used") is not True:
            raise ValueError("arm report does not attest to the actual shared emitter")
        if not isinstance(input_sha256, str) or len(input_sha256) != 64:
            raise ValueError("actual-emitter input digest is invalid")
        if payload_sha256 != batch_sha256:
            raise ValueError("actual-emitter payload does not bind the retained batch")
        producer = {
            "kind": "ACTUAL_SHARED_EMITTER",
            "input_sha256": input_sha256,
            "payload_sha256": payload_sha256,
            "synthetic_observations": True,
            "deployment_qualification_claimed": False,
        }

    bundle: dict[str, Any] = {
        "schema": ACTUAL_EMITTER_SCHEMA if producer else SCHEMA,
        "source": {
            "arm_commit": expected_arm_commit,
            "arm_report_sha256": _digest(report_bytes),
            "geometry_variant": report["geometry_variant"],
            "virtual_profile_sha256": report["virtual_profile_sha256"],
            "batch_sha256": batch_sha256,
            "trajectory_plan_sha256": schedule["source_trajectory_plan_sha256"],
            "ik_screen_sha256": schedule["source_ik_screen_sha256"],
            "schedule_profile_sha256": schedule["profile_sha256"],
        },
        "ordered_target_ids": ordered_targets,
        "sample_count": len(compact_samples),
        "total_time_ns": schedule["total_motion_and_dwell_time_ns"],
        "samples": compact_samples,
        "arm_screening_metrics": {
            "maximum_position_error_mm": max(ik_position_errors),
            "minimum_normalized_arm_joint_margin": min(ik_margins),
            "joint_dynamics_all_samples_accepted": schedule[
                "joint_dynamics_all_samples_accepted"
            ],
        },
        "remaining_arm_blockers": schedule["blockers"],
        "scope": "SYNTHETIC_OFFLINE_ISAAC_REPLAY_ONLY",
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
    }
    if producer is not None:
        bundle["producer"] = producer
    bundle["bundle_sha256"] = _digest(_canonical(bundle))
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm-report", type=Path, required=True)
    parser.add_argument("--arm-commit", required=True)
    parser.add_argument("--require-actual-emitter", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.arm_report.resolve(strict=True).read_bytes()
    report = json.loads(raw)
    bundle = build_replay_bundle(
        report, raw, args.arm_commit,
        require_actual_emitter=args.require_actual_emitter,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "bundle_sha256": bundle["bundle_sha256"],
        "sample_count": bundle["sample_count"],
        "ordered_target_ids": bundle["ordered_target_ids"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
