"""Strict zero-authority composition of the semantic typing twin and arm boundary."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .end_to_end_typing_twin import _canonical, _sha, compile_virtual_us_sticky_keys


def _compile_installed(text: str, installed: tuple[str, ...]) -> tuple[str, ...]:
    targets = compile_virtual_us_sticky_keys(text)
    missing = tuple(dict.fromkeys(target for target in targets if target not in installed))
    if missing:
        raise ValueError(f"uncommissioned keyboard targets: {list(missing)}")
    return targets

def _load_boundary_fixture(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    claimed = document.pop("fixture_sha256")
    if _sha(document) != claimed:
        raise ValueError("boundary fixture hash changed")
    document["fixture_sha256"] = claimed
    if document["scope"] != "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY":
        raise ValueError("boundary fixture scope is invalid")
    if any(document["counters"].values()):
        raise ValueError("boundary fixture violates zero authority")
    return document


def run_boundary_sweep(boundary_fixture_path: Path, *, workspace: Path) -> dict[str, Any]:
    """Traverse actual V2 decode/registry/trajectory contracts over frozen ranges."""

    from rocell.application.context import load_simulation_context
    from rocell.application.model_motion_ingress_v2 import (
        MeasuredTargetRegionV2,
        TrustedLocalizationQualificationV2,
    )
    from rocell.application.model_motion_registry_v2 import (
        TrustedMotionRegistryV2,
        ingest_with_trusted_registry_v2,
        revalidate_with_trusted_registry_v2,
    )
    from rocell.application.typing_execution_plan_v1 import (
        TypingExecutionConfigV1,
        compile_typing_execution_plan_v1,
    )
    from rocell.application.typing_trajectory_plan_v1 import (
        TypingTrajectoryPolicyV1,
        compile_typing_trajectory_plan_v1,
    )
    from rocell.models import (
        ActionPlan,
        Device,
        Interaction,
        ModelMotionBatchV2,
        ModelMotionProposalV2,
        MotionCapabilityV2,
        MotionEvidenceV2,
        MotionGeometryV2,
        MotionUncertaintyV2,
        Point3Mm,
        PressKey,
        ProposalDevice,
        SpeedClass,
        UncertaintyBoundType,
        decode_model_motion_batch_v2_json,
    )

    fixture = _load_boundary_fixture(boundary_fixture_path)
    for binding in fixture["input_bindings"].values():
        source = workspace / binding["path"]
        if not source.is_file():
            raise ValueError(f"bound source is absent: {binding['path']}")
        observed = hashlib.sha256(source.read_bytes()).hexdigest()
        if observed != binding["sha256"]:
            raise ValueError(f"bound source hash changed: {binding['path']}")
    context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json")
    if context.targets.content_sha256 != fixture["installed_target_catalog_sha256"]:
        raise ValueError("active target catalog differs from boundary fixture")
    active_ids = tuple(context.targets.keyboard_targets)
    blocked = fixture["cases"]["blocked_missing_target"]
    try:
        _compile_installed(blocked["text"], active_ids)
    except ValueError as exc:
        blocked_result = {
            "status": "BLOCK_BEFORE_BATCH",
            "expected_missing_target": blocked["expected_missing_target"],
            "message_sha256": hashlib.sha256(str(exc).encode()).hexdigest(),
        }
    else:
        raise ValueError("missing Shift case was falsely accepted")

    case = fixture["cases"]["admitted_installed_subset"]
    target_ids = _compile_installed(case["text"], active_ids)
    if list(target_ids) != case["expected_targets"]:
        raise ValueError("compiler target order differs from frozen boundary fixture")
    plan = ActionPlan.from_text(
        device=Device.KEYBOARD,
        profile_id="keyboard-development-v1",
        text=case["text"],
        actions=tuple(PressKey(target_id) for target_id in target_ids),
        required_calibrations=("keyboard_pose", "keyboard_tcp"),
    )
    unique_ids = tuple(dict.fromkeys(target_ids))
    h = {letter: letter * 64 for letter in "abcdef"}
    t0 = fixture["evidence"]["captured_at_epoch_ms"]
    capability = MotionCapabilityV2(plan.profile_id, h["e"])
    geometry = MotionGeometryV2(
        "board_mm_xy_plane_v2", "mm", h["d"], h["e"],
        context.targets.content_sha256)
    evidence = MotionEvidenceV2(
        capture_id="typing-twin-capture", frame_id="typing-twin-frame",
        image_sha256=h["a"], camera_identity_sha256=h["b"],
        capture_clock_domain_id="typing-twin-clock", model_id="analytic-geometry-v1",
        model_sha256=h["c"], scene_observation_sha256=h["b"],
        precision_observation_sha256=h["c"], fusion_decision_sha256=h["d"],
        scene_lease_id="typing-twin-lease", scene_lease_issuer_id="simulation-only",
        scene_lease_sha256=h["f"], captured_at_epoch_ms=t0,
        evaluated_at_epoch_ms=t0 + fixture["evidence"]["evaluated_offset_ms_range"][1],
        expires_at_epoch_ms=t0 + fixture["evidence"]["expires_offset_ms_range"][1],
    )
    regions = []
    for target_id in unique_ids:
        target = context.targets.resolve("keyboard", target_id)
        left, front, right, rear = target.safe_rectangle_board_mm
        regions.append(MeasuredTargetRegionV2(
            target_id=target_id, coordinate_frame="board",
            coordinate_profile="board_mm_xy_plane_v2",
            board_frame_definition_sha256=h["d"],
            vertices_xy_mm=((left, front), (right, front), (right, rear), (left, rear)),
            surface_z_mm=target.center.z, surface_normal_error_bound_mm=0.1,
            placement_error_bound_mm=0.25, placement_observation_sha256=h["e"],
            target_catalog_sha256=context.targets.content_sha256,
        ))
    combinations = []
    paired = zip(
        fixture["sweeps"]["maximum_velocity_mm_s"]["values"],
        fixture["sweeps"]["maximum_acceleration_mm_s2"]["values"],
        fixture["sweeps"]["maximum_jerk_mm_s3"]["values"],
        fixture["sweeps"]["hover_settle_ms"]["values"],
        fixture["sweeps"]["contact_dwell_ms"]["values"],
    )
    paired_values = tuple(paired)
    for uncertainty_mm in fixture["sweeps"]["planar_uncertainty_bound_mm"]["values"]:
        qualification = TrustedLocalizationQualificationV2(
            qualification_sha256=h["f"], model_id=evidence.model_id,
            model_sha256=evidence.model_sha256, evidence_method_sha256=h["a"],
            domain_id="typing-twin-analytic-v1",
            target_catalog_sha256=context.targets.content_sha256,
            bound_type=UncertaintyBoundType.PLANAR_L2_DISK,
            error_bound_mm=uncertainty_mm, coverage_probability=0.99,
            target_ids=unique_ids,
        )
        uncertainty = MotionUncertaintyV2(
            UncertaintyBoundType.PLANAR_L2_DISK, uncertainty_mm, 0.99,
            h["f"], h["a"], "typing-twin-analytic-v1", unique_ids)
        proposals = tuple(
            ModelMotionProposalV2(
                proposal_id=f"typing-twin-{index}", action_index=index,
                device=ProposalDevice.KEYBOARD, target_id=target_id,
                target=Point3Mm(
                    "board",
                    context.targets.resolve("keyboard", target_id).center.x,
                    context.targets.resolve("keyboard", target_id).center.y,
                    context.targets.resolve("keyboard", target_id).center.z,
                ),
                interaction=Interaction.CONTACT, observation_confidence=0.99,
            )
            for index, target_id in enumerate(target_ids)
        )
        batch = ModelMotionBatchV2(
            batch_id=f"typing-twin-u-{str(uncertainty_mm).replace('.', '-')}",
            request_id="typing-twin-request", intent_plan_sha256=plan.plan_hash,
            device=ProposalDevice.KEYBOARD, capability=capability, geometry=geometry,
            evidence=evidence, uncertainty=uncertainty, proposals=proposals)
        payload = _canonical(batch.to_dict())
        decoded = decode_model_motion_batch_v2_json(payload)
        registry = TrustedMotionRegistryV2(
            capability_profile_id=capability.profile_id,
            capability_profile_sha256=capability.profile_sha256,
            capture_id=evidence.capture_id, frame_id=evidence.frame_id,
            image_sha256=evidence.image_sha256,
            capture_clock_domain_id=evidence.capture_clock_domain_id,
            camera_identity_sha256=evidence.camera_identity_sha256,
            scene_lease_id=evidence.scene_lease_id,
            scene_lease_issuer_id=evidence.scene_lease_issuer_id,
            scene_lease_sha256=evidence.scene_lease_sha256,
            scene_lease_expires_at_epoch_ms=evidence.expires_at_epoch_ms,
            scene_observation_sha256=evidence.scene_observation_sha256,
            precision_observation_sha256=evidence.precision_observation_sha256,
            fusion_decision_sha256=evidence.fusion_decision_sha256,
            placement_observation_sha256=h["e"],
            board_frame_definition_sha256=h["d"],
            target_catalog_sha256=context.targets.content_sha256,
            maximum_scene_age_ms=fixture["evidence"]["scene_age_ms_range"][1],
            minimum_observation_confidence=fixture["evidence"]["observation_confidence_range"][0],
            maximum_surface_normal_error_mm=0.5,
            qualification=qualification, target_regions=tuple(regions),
        )
        ingress = ingest_with_trusted_registry_v2(
            decoded, plan, context, registry=registry,
            current_time_epoch_ms=t0 + 3000, current_monotonic_ns=9_000_000_000)
        fresh = revalidate_with_trusted_registry_v2(
            ingress, registry=registry, current_monotonic_ns=10_000_000_000)
        for hover in fixture["sweeps"]["hover_clearance_mm"]["values"]:
            first = proposals[0].target
            for cartesian_step in fixture["sweeps"]["maximum_cartesian_step_mm"]["values"]:
                for velocity, acceleration, jerk, settle, dwell in paired_values:
                    execution = compile_typing_execution_plan_v1(
                        decoded, ingress,
                        config=TypingExecutionConfigV1(
                            config_id="typing-twin-boundary-v1",
                            calibration_snapshot_sha256=h["a"],
                            tool_profile_sha256=h["b"], dynamics_profile_sha256=h["c"],
                            route_reference_point=Point3Mm(
                                "board", first.x, first.y, first.z + hover),
                            hover_clearance_mm=hover,
                            settle_position_tolerance_mm=0.5,
                            settle_velocity_tolerance_mm_s=1.0,
                            settle_hold_ms=settle, preview_horizon=1,
                            speed_class=SpeedClass.SLOW,
                        ),
                    )
                    trajectory = compile_typing_trajectory_plan_v1(
                        execution,
                        policy=TypingTrajectoryPolicyV1(
                            policy_id="typing-twin-boundary-v1",
                            maximum_cartesian_step_mm=cartesian_step,
                            maximum_velocity_mm_s=velocity,
                            maximum_acceleration_mm_s2=acceleration,
                            maximum_jerk_mm_s3=jerk,
                            hover_settle_ms=settle, contact_dwell_ms=dwell,
                        ),
                    )
                    combinations.append({
                        "uncertainty_mm": uncertainty_mm,
                        "hover_mm": hover,
                        "cartesian_step_mm": cartesian_step,
                        "profile_index": paired_values.index(
                            (velocity, acceleration, jerk, settle, dwell)),
                        "batch_sha256": decoded.batch_sha256,
                        "ingress_sha256": ingress["ingress_sha256"],
                        "freshness_sha256": fresh["preplanner_gate_sha256"],
                        "execution_sha256": execution.plan_sha256,
                        "trajectory_sha256": trajectory.trajectory_plan_sha256,
                        "ordered_targets": list(target_ids),
                        "screening_sample_count": len(trajectory.screening_samples),
                    })
    if len(combinations) != fixture["expected_combination_count"]:
        raise ValueError("boundary combination count differs from frozen fixture")
    core = {
        "schema": "tactevra.end_to_end_typing_twin_boundary_receipt.v1",
        "scope": fixture["scope"], "fixture_sha256": fixture["fixture_sha256"],
        "combination_count": len(combinations), "combinations": combinations,
        "ordered_targets": list(target_ids), "blocked_missing_target": blocked_result,
        "strict_decode_pass_count": len(combinations),
        "trusted_registry_ingress_pass_count": len(combinations),
        "trajectory_build_pass_count": len(combinations),
        "target_order_difference_count": 0,
        "authority_bearing_output_count": 0,
        "ik_screening_executed": False, "collision_screening_executed": False,
        "mujoco_replay_executed": False, "controller_commands": [],
        "hardware_commands_generated": 0, "hardware_access": False,
        "hardware_writes": 0, "physical_movements": 0, "physical_authority": False,
        "decision": "PASS_STRICT_BOUNDARY_AND_TRAJECTORY_PARTIAL_WORKSTREAM",
    }
    return {**core, "receipt_sha256": _sha(core)}



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_boundary_sweep(args.fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"decision": result["decision"], "receipt_sha256": result["receipt_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
