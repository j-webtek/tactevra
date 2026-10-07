"""CPU-only full typing-route reconstruction under the promoted virtual profile."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any

from rocell.application.context import load_simulation_context
from rocell.application.model_motion_registry_v2 import (
    ingest_with_trusted_registry_v2,
    revalidate_with_trusted_registry_v2,
)
from rocell.application.trajectory_simulation import TrajectorySimulationPolicy
from rocell.application.typing_collision_intake_v1 import (
    PROFILE_REQUIRED_STATUS,
    prepare_typing_collision_intake_v1,
)
from rocell.application.typing_execution_plan_v1 import (
    TypingExecutionConfigV1,
    compile_typing_execution_plan_v1,
)
from rocell.application.typing_trajectory_ik_screen_v1 import (
    READY_STATUS,
    TypingTrajectoryIkSeedV1,
    screen_typing_trajectory_ik_v1,
)
from rocell.application.typing_trajectory_plan_v1 import (
    TypingTrajectoryPolicyV1,
    compile_typing_trajectory_plan_v1,
)
from rocell.geometry import RigidTransform, Rotation3, Vec3
from rocell.kinematics import ARM_JOINT_NAMES
from rocell.models import Point3Mm, SpeedClass, decode_model_motion_batch_v2_json
from rocell.simulation.virtual_profile import load_virtual_commissioning_profile

from .actual_output_compatibility_v1 import (
    _plan,
    _registry_for_batch,
    build_actual_emitter_payload,
)
from .typing_twin_ik_collision_v1 import (
    SCOPE,
    _candidate_diagnostic,
    _load_fixture as _load_collision_fixture,
    _synthetic_ready_tip,
    _synthetic_snapshot,
)


SCHEMA = "tactevra.typing_twin_promoted_full_route_receipt.v1"
FIXTURE_SCHEMA = "tactevra.typing_twin_promoted_full_route_fixture.v1"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_fixture(path: Path, workspace: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    claimed = document.pop("fixture_sha256", None)
    if claimed != _sha(document):
        raise ValueError("promoted full-route fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("schema") != FIXTURE_SCHEMA or document.get("scope") != SCOPE:
        raise ValueError("unexpected promoted full-route fixture identity")
    if any(document["counters"].values()):
        raise ValueError("fixture violates the zero-authority scope")
    for binding in document["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file():
            raise ValueError(f"bound source is absent: {binding['path']}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {binding['path']}")
    return document


def run_promoted_full_route(
    fixture_path: Path, *, workspace: Path
) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path, workspace)
    parent = _load_collision_fixture(
        workspace / fixture["parent_fixture"]["path"], workspace
    )
    if parent["fixture_sha256"] != fixture["parent_fixture"]["fixture_sha256"]:
        raise ValueError("parent collision fixture identity changed")
    prior = json.loads(
        (workspace / fixture["admission_result"]["path"]).read_text(encoding="utf-8")
    )
    if (
        prior["receipt_sha256"] != fixture["admission_result"]["receipt_sha256"]
        or prior["decision"]
        != "PROMOTED_TRANSFORM_EXPLORATORY_PROFILE_ADMISSIBLE"
    ):
        raise ValueError("promoted exact-contact admission result changed")

    context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json"
    )
    profile = load_virtual_commissioning_profile(context)
    frozen = fixture["reconstruction"]
    if (
        profile.profile_id != fixture["promoted_profile"]["profile_id"]
        or profile.study_input.study_input_id
        != fixture["promoted_profile"]["study_input_id"]
        or profile.source_sha256 != fixture["promoted_profile"]["source_sha256"]
        or profile.study_input.keyboard_tool_length_mm != frozen["tool_length_mm"]
    ):
        raise ValueError("promoted virtual profile binding changed")

    case = parent["case"]
    targets = tuple(case["expected_targets"])
    payload = build_actual_emitter_payload(
        workspace,
        text=case["text"],
        targets=targets,
        batch_id=case["batch_id"],
        request_id=case["request_id"],
    )
    batch = decode_model_motion_batch_v2_json(payload)
    plan = _plan(case["text"], targets)
    registry = _registry_for_batch(context, batch)
    ingress = ingest_with_trusted_registry_v2(
        batch,
        plan,
        context,
        registry=registry,
        current_time_epoch_ms=batch.evidence.evaluated_at_epoch_ms,
        current_monotonic_ns=9_000_000_000,
    )
    fresh = revalidate_with_trusted_registry_v2(
        ingress, registry=registry, current_monotonic_ns=10_000_000_000
    )
    snapshot = replace(
        _synthetic_snapshot(context),
        board_T_vendor_world=profile.study_input.board_T_vendor_world,
        hand_T_tool=RigidTransform(
            "G",
            "T",
            Rotation3.identity(),
            Vec3(0.0, 0.0, -float(frozen["tool_length_mm"])),
        ),
    )
    ready_tip = _synthetic_ready_tip(context, snapshot)
    route = parent["route"]
    execution = compile_typing_execution_plan_v1(
        batch,
        ingress,
        config=TypingExecutionConfigV1(
            config_id=fixture["route"]["config_id"],
            calibration_snapshot_sha256=snapshot.snapshot_sha256,
            tool_profile_sha256=fixture["route"]["tool_profile_sha256"],
            dynamics_profile_sha256=route["dynamics_profile_sha256"],
            route_reference_point=Point3Mm(
                "board", ready_tip.x, ready_tip.y, ready_tip.z
            ),
            hover_clearance_mm=float(frozen["hover_clearance_mm"]),
            settle_position_tolerance_mm=route["settle_position_tolerance_mm"],
            settle_velocity_tolerance_mm_s=route[
                "settle_velocity_tolerance_mm_s"
            ],
            settle_hold_ms=route["settle_hold_ms"],
            preview_horizon=1,
            speed_class=SpeedClass.SLOW,
        ),
    )
    trajectory = compile_typing_trajectory_plan_v1(
        execution,
        policy=TypingTrajectoryPolicyV1(
            policy_id=fixture["route"]["trajectory_policy_id"],
            maximum_cartesian_step_mm=route["maximum_cartesian_step_mm"],
            maximum_velocity_mm_s=route["maximum_velocity_mm_s"],
            maximum_acceleration_mm_s2=route["maximum_acceleration_mm_s2"],
            maximum_jerk_mm_s3=route["maximum_jerk_mm_s3"],
            hover_settle_ms=route["hover_settle_ms"],
            contact_dwell_ms=route["contact_dwell_ms"],
        ),
    )
    if [action.target_id for action in execution.actions] != list(targets):
        raise ValueError("reconstructed route changed semantic target order")

    seed = TypingTrajectoryIkSeedV1(
        seed_id="typing-twin-promoted-profile-synthetic-ready-v1",
        calibration_snapshot_sha256=snapshot.snapshot_sha256,
        build_snapshot_sha256=context.snapshot.snapshot_hash,
        joint_positions_rad={
            name: context.scenario.ready_arm_joint_positions_rad[name].value
            for name in ARM_JOINT_NAMES
        },
    )
    maximum_samples = fixture["resource_limits"]["maximum_ik_samples"]
    ik = screen_typing_trajectory_ik_v1(
        execution,
        trajectory,
        context,
        snapshot,
        seed,
        policy=TrajectorySimulationPolicy(
            maximum_cartesian_step_mm=route["maximum_cartesian_step_mm"],
            maximum_refinement_rounds=0,
            maximum_waypoints_per_round=maximum_samples,
            maximum_total_ik_solves=maximum_samples,
            maximum_route_targets=len(targets),
        ),
    )
    route_accepted = ik["status"] == READY_STATUS
    if route_accepted:
        intake = prepare_typing_collision_intake_v1(
            execution, trajectory, ik, context, snapshot, installed_profile=None
        )
        if intake["status"] != PROFILE_REQUIRED_STATUS:
            raise ValueError("installed collision intake did not remain fail closed")
        diagnostic_input = ik
        decision = "PASS_IK_CONTINUITY_RETAIN_INSTALLED_COLLISION_BLOCKER"
    else:
        accepted_prefix = []
        for result in ik["joint_results"]:
            if result["accepted"] is not True:
                break
            accepted_prefix.append(result)
        intake = {
            "status": "NOT_REACHED_CANONICAL_IK_BLOCKED",
            "blockers": list(ik["blockers"]),
            "installed_geometry_collision_screening_executed": False,
            "continuous_collision_proven": False,
            "physical_authority": False,
        }
        diagnostic_input = {**ik, "joint_results": accepted_prefix}
        decision = "BLOCKED_CANONICAL_IK_OR_CONTINUITY"

    diagnostic_fixture = {
        **parent,
        "candidate_collision_ranges": fixture["candidate_collision_ranges"],
    }
    diagnostic = _candidate_diagnostic(
        diagnostic_fixture, context, snapshot, diagnostic_input
    )
    expected_profiles = fixture["resource_limits"][
        "expected_candidate_profile_count"
    ]
    if diagnostic["profile_count"] != expected_profiles:
        raise ValueError("candidate diagnostic profile count differs from fixture")
    accepted_results = [item for item in ik["joint_results"] if item["accepted"]]
    core = {
        "schema": SCHEMA,
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "parent_fixture_sha256": parent["fixture_sha256"],
        "admission_receipt_sha256": prior["receipt_sha256"],
        "promoted_profile": {
            "profile_id": profile.profile_id,
            "study_input_id": profile.study_input.study_input_id,
            "source_sha256": profile.source_sha256,
            "status": profile.status,
            "simulation_only": profile.simulation_only,
            "physical_release_effect": profile.physical_release_effect,
        },
        "reconstruction": frozen,
        "ordered_targets": list(targets),
        "batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress["ingress_sha256"],
        "freshness_sha256": fresh["preplanner_gate_sha256"],
        "calibration_snapshot_sha256": snapshot.snapshot_sha256,
        "execution_plan_sha256": execution.plan_sha256,
        "trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "trajectory_sample_count": len(trajectory.screening_samples),
        "ik_screen": ik,
        "ik_accepted_sample_count": len(accepted_results),
        "minimum_normalized_arm_joint_margin": (
            min(
                item["minimum_normalized_arm_joint_margin"]
                for item in accepted_results
            )
            if accepted_results
            else None
        ),
        "maximum_adjacent_joint_delta_rad": (
            max(item["maximum_joint_delta_rad"] for item in accepted_results)
            if accepted_results
            else None
        ),
        "canonical_ik_route_accepted": route_accepted,
        "canonical_joint_continuity_accepted": route_accepted,
        "installed_collision_intake": intake,
        "candidate_collision_diagnostic": diagnostic,
        "candidate_collision_sample_scope": (
            "FULL_ROUTE" if route_accepted else "ACCEPTED_PREFIX_ONLY"
        ),
        "candidate_continuous_collision_proven": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "decision": decision,
        "limitations": fixture["limitations"],
    }
    return {**core, "receipt_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_promoted_full_route(args.fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "trajectory_sample_count": result["trajectory_sample_count"],
                "ik_accepted_sample_count": result["ik_accepted_sample_count"],
                "receipt_sha256": result["receipt_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
