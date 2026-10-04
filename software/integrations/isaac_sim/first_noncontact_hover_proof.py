"""Derive a bounded first-hover proof from retained Isaac replay evidence.

This verifier does not run Isaac, plan motion, step physics, encode controller
commands, or access hardware.  It proves that the already-retained, hash-bound
Isaac replay included a contiguous schedule prefix ending at the first H hover
and that the prefix contains no contact sample.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "tactevra.isaac_first_noncontact_hover_proof.v1"
BUNDLE_SCHEMAS = {
    "tactevra.arm_joint_schedule_replay_bundle.v1",
    "tactevra.arm_joint_schedule_replay_bundle.v2",
}
REPLAY_SCHEMA = "tactevra.isaac_joint_schedule_replay.v1"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _verify_content_digest(document: dict[str, Any], field: str) -> None:
    claimed = document.get(field)
    unsigned = dict(document)
    unsigned.pop(field, None)
    if claimed != _digest(_canonical(unsigned)):
        raise ValueError(f"{field} mismatch")


def _require_zero_authority(document: dict[str, Any], label: str) -> None:
    if (
        document.get("hardware_access") is not False
        or document.get("physical_authority") is not False
        or document.get("controller_commands") != []
        or document.get("hardware_writes") != 0
        or document.get("physical_movements") != 0
    ):
        raise ValueError(f"{label} crosses the zero-authority boundary")


def build_first_hover_proof(
    bundle: dict[str, Any],
    bundle_bytes: bytes,
    replay: dict[str, Any],
    replay_bytes: bytes,
) -> dict[str, Any]:
    if json.loads(bundle_bytes) != bundle:
        raise ValueError("bundle bytes differ from the decoded bundle")
    if json.loads(replay_bytes) != replay:
        raise ValueError("replay bytes differ from the decoded replay receipt")
    if bundle.get("schema") not in BUNDLE_SCHEMAS:
        raise ValueError("unsupported replay bundle schema")
    _verify_content_digest(bundle, "bundle_sha256")
    _require_zero_authority(bundle, "bundle")
    samples = bundle.get("samples")
    if not isinstance(samples, list) or len(samples) != bundle.get("sample_count"):
        raise ValueError("bundle sample count mismatch")
    if [sample.get("sequence") for sample in samples] != list(range(len(samples))):
        raise ValueError("bundle sample sequence is not contiguous")
    producer = bundle.get("producer")
    if not isinstance(producer, dict):
        raise ValueError("actual-emitter producer lineage is absent")
    if (
        producer.get("kind") != "ACTUAL_SHARED_EMITTER"
        or producer.get("synthetic_observations") is not True
        or producer.get("deployment_qualification_claimed") is not False
        or producer.get("payload_sha256") != bundle.get("source", {}).get("batch_sha256")
    ):
        raise ValueError("actual-emitter producer lineage is invalid")

    if replay.get("schema") != REPLAY_SCHEMA:
        raise ValueError("unsupported Isaac replay receipt schema")
    _verify_content_digest(replay, "receipt_sha256")
    _require_zero_authority(replay, "replay receipt")
    bindings = replay.get("source_bindings")
    if not isinstance(bindings, dict):
        raise ValueError("Isaac replay source bindings are absent")
    if bindings.get("bundle_file_sha256") != _digest(bundle_bytes):
        raise ValueError("Isaac replay does not bind the retained bundle file")
    if bindings.get("bundle_sha256") != bundle.get("bundle_sha256"):
        raise ValueError("Isaac replay does not bind the retained bundle content")
    if bindings.get("arm_commit") != bundle.get("source", {}).get("arm_commit"):
        raise ValueError("Isaac replay and bundle arm commits differ")
    if replay.get("sample_count") != len(samples) or replay.get("all_samples_pass") is not True:
        raise ValueError("Isaac replay did not pass every retained schedule sample")
    if replay.get("physics_steps") != 0:
        raise ValueError("retained replay stepped physics")

    hover_index = next(
        (
            index
            for index, sample in enumerate(samples)
            if sample.get("action_index") == 0
            and sample.get("target_id") == "H"
            and sample.get("phase") == "HOVER"
            and sample.get("phase_endpoint") is True
        ),
        None,
    )
    if hover_index is None:
        raise ValueError("first H hover endpoint is absent")
    prefix = samples[: hover_index + 1]
    if any(sample.get("phase") == "CONTACT" for sample in prefix):
        raise ValueError("contact occurs before the first H hover endpoint")
    endpoint = prefix[-1]
    expected_tip = endpoint.get("expected_tool_tip_board_mm")
    if not isinstance(expected_tip, list) or len(expected_tip) != 3:
        raise ValueError("first H hover endpoint is missing its expected tool-tip pose")

    maximum_tip_error = replay.get("maximum_tool_tip_error_mm")
    maximum_joint_error = replay.get("maximum_joint_tracking_error_rad")
    thresholds = replay.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("Isaac replay thresholds are absent")
    if not isinstance(maximum_tip_error, (int, float)) or maximum_tip_error > thresholds.get(
        "maximum_tool_tip_error_mm", -1
    ):
        raise ValueError("Isaac replay tool-tip bound did not pass")
    if not isinstance(maximum_joint_error, (int, float)) or maximum_joint_error > thresholds.get(
        "maximum_joint_tracking_error_rad", -1
    ):
        raise ValueError("Isaac replay joint bound did not pass")

    proof: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "PASS_KINEMATIC_HOVER_WITH_BLOCKERS",
        "evidence_class": "DERIVED_FROM_HASH_BOUND_FULL_ROUTE_ISAAC_REPLAY",
        "source_bindings": {
            "bundle_file_sha256": _digest(bundle_bytes),
            "bundle_sha256": bundle["bundle_sha256"],
            "replay_file_sha256": _digest(replay_bytes),
            "replay_receipt_sha256": replay["receipt_sha256"],
            "arm_commit": bindings["arm_commit"],
            "robot_usd_sha256": bindings["robot_usd_sha256"],
        },
        "prefix": {
            "sample_count": len(prefix),
            "first_sequence": prefix[0]["sequence"],
            "last_sequence": endpoint["sequence"],
            "contact_sample_count": 0,
            "endpoint": {
                "action_index": endpoint["action_index"],
                "target_id": endpoint["target_id"],
                "phase": endpoint["phase"],
                "phase_endpoint": endpoint["phase_endpoint"],
                "time_from_start_ns": endpoint["time_from_start_ns"],
                "expected_tool_tip_board_mm": expected_tip,
            },
        },
        "conservative_replay_bounds": {
            "maximum_prefix_tool_tip_error_mm": maximum_tip_error,
            "maximum_prefix_joint_tracking_error_rad": maximum_joint_error,
            "derivation": "bounded_by_passing_full_route_maximum",
        },
        "producer_scope": {
            "synthetic_observations": True,
            "deployment_qualification_claimed": False,
        },
        "physics_steps": 0,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "remaining_blockers": sorted(
            set(replay.get("remaining_blockers", []))
            | {
                "SAFE_REGION_FITTING_LOCALIZATION_REQUIRED",
                "SIMULATION_ONLY_LAYOUT_AND_TOOL_GEOMETRY",
                "NO_DYNAMIC_OR_CONTACT_QUALIFICATION",
            }
        ),
        "limitations": [
            "The proof is derived from a retained full-route Isaac receipt; the per-hover error is conservatively bounded by the passing full-route maximum.",
            "The schedule source uses synthetic observations and explicitly denies deployment qualification.",
            "The replay teleports joints with zero physics steps and does not test dynamics, clearance, contact, or controller tracking.",
            "This proof cannot promote any camera, collision, controller, hardware, or physical gate.",
        ],
    }
    proof["proof_sha256"] = _digest(_canonical(proof))
    return proof


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bundle_bytes = args.bundle.resolve(strict=True).read_bytes()
    replay_bytes = args.replay.resolve(strict=True).read_bytes()
    proof = build_first_hover_proof(
        json.loads(bundle_bytes), bundle_bytes, json.loads(replay_bytes), replay_bytes
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": proof["status"],
        "proof_sha256": proof["proof_sha256"],
        "prefix_sample_count": proof["prefix"]["sample_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
