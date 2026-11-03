"""Plan and compare zero-authority native/offline collision geometry captures."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


PLAN_SCHEMA = "tactevra.isaac_lm1_collision_geometry_parity_plan.v1"
CAPTURE_SCHEMA = "tactevra.isaac_lm1_collision_geometry_capture.v1"
REPORT_SCHEMA = "tactevra.isaac_lm1_collision_geometry_parity_report.v1"
SELECTION_SCHEMA = "tactevra.isaac_lm1_route_shape_v4_native_selection.v1"
FIXED_BASE_PLAN_SCHEMA = (
    "tactevra.isaac_lm1_fixed_base_collision_replay_plan.v1"
)
FIXED_BASE_RESULT_SCHEMA = (
    "tactevra.isaac_lm1_fixed_base_collision_replay_result.v1"
)
FIXED_BASE_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v5"
)
LEARNING_BASELINE_SELECTION_SCHEMA = (
    "tactevra.isaac_lm1_key_mechanics_learning_baseline_selection.v1"
)
KEY_MECHANICS_PROFILE_SCHEMA = (
    "tactevra.isaac_lm1_representative_key_mechanics.v1"
)
IK_RECEIPT_SCHEMA = "tactevra.isaac_lm1_robot_tcp_cartesian_ik_screen.v1"
CARTESIAN_REQUEST_SCHEMA = (
    "tactevra.isaac_lm1_robot_tcp_cartesian_schedule_request.v1"
)
ARM_JOINT_ORDER = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
)


class ParityContractError(ValueError):
    """Raised when parity evidence crosses its fixed zero-authority boundary."""


def _canonical_sha256(document: dict[str, Any]) -> str:
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _verify_digest(document: dict[str, Any], field: str, label: str) -> str:
    claimed = document.get(field)
    unsigned = dict(document)
    unsigned.pop(field, None)
    if not isinstance(claimed, str) or claimed != _canonical_sha256(unsigned):
        raise ParityContractError(f"{label} hash mismatch")
    return claimed


def _require_zero_authority(document: dict[str, Any], label: str) -> None:
    physical_authority = document.get("physical_authority")
    if physical_authority is None:
        authority = document.get("authority")
        physical_authority = not (
            isinstance(authority, dict)
            and authority
            and all(value is False for value in authority.values())
        )
    commands = document.get("controller_commands", document.get("commands"))
    hardware_writes = document.get(
        "hardware_writes", document.get("hardware_write_count")
    )
    physical_movements = document.get(
        "physical_movements", document.get("physical_movement_count")
    )
    hardware_access = document.get("hardware_access")
    if hardware_access is None and physical_authority is False:
        hardware_access = False
    if (
        hardware_access is not False
        or physical_authority is not False
        or commands != []
        or hardware_writes != 0
        or physical_movements != 0
    ):
        raise ParityContractError(f"{label} authority boundary changed")


def _pair_key(pair: list[str]) -> tuple[str, str]:
    if (
        not isinstance(pair, list)
        or len(pair) != 2
        or not all(isinstance(item, str) and item for item in pair)
    ):
        raise ParityContractError("collision pair is invalid")
    return tuple(sorted(pair))


def _select_capture_samples(result: dict[str, Any]) -> list[dict[str, Any]]:
    samples = result.get("raw_native_samples")
    if not isinstance(samples, list) or not samples:
        raise ParityContractError("retained native samples are absent")
    ordered = sorted(samples, key=lambda item: item.get("sample_sequence", -1))
    if [item.get("sample_sequence") for item in ordered] != list(
        range(len(ordered))
    ):
        raise ParityContractError("retained native sample sequence changed")

    blocked = [
        item for item in ordered if item.get("physical_solid_blocker_pairs")
    ]
    if not blocked:
        raise ParityContractError("candidate has no physical blocker onset")
    first_onset = blocked[0]
    peak = min(
        blocked,
        key=lambda item: (
            -len(item["physical_solid_blocker_pairs"]),
            item["sample_sequence"],
        ),
    )
    later_clear = next(
        (
            item
            for item in ordered
            if item["sample_sequence"] > first_onset["sample_sequence"]
            and not item.get("physical_solid_blocker_pairs")
        ),
        None,
    )
    if later_clear is None:
        raise ParityContractError("candidate lacks a post-onset physical-clear sample")

    selected: dict[int, dict[str, Any]] = {}
    for role, sample in (
        ("FIRST_PHYSICAL_ONSET", first_onset),
        ("PEAK_PHYSICAL_PAIR_COUNT", peak),
        ("FIRST_PHYSICAL_CLEAR_AFTER_ONSET", later_clear),
    ):
        sequence = sample["sample_sequence"]
        entry = selected.setdefault(
            sequence,
            {
                "sample_sequence": sequence,
                "sample_id": sample["sample_id"],
                "source_segment_index": sample["source_segment_index"],
                "selection_roles": [],
                "physical_solid_blocker_pairs": sample.get(
                    "physical_solid_blocker_pairs", []
                ),
                "physical_primitive_pairs": [],
            },
        )
        entry["selection_roles"].append(role)
        physical_pairs = {
            _pair_key(pair) for pair in entry["physical_solid_blocker_pairs"]
        }
        primitive_pairs = []
        for primitive_pair in sample.get("raw_collision_primitive_pairs", []):
            body_pair = primitive_pair.get("body_pair")
            if _pair_key(body_pair) in physical_pairs:
                primitive_pairs.append(
                    {
                        "body_pair": body_pair,
                        "primitive_indices": primitive_pair["primitive_indices"],
                    }
                )
        entry["physical_primitive_pairs"] = sorted(
            primitive_pairs,
            key=lambda item: (item["body_pair"], item["primitive_indices"]),
        )
    return [selected[key] for key in sorted(selected)]


def build_capture_plan(
    selection: dict[str, Any],
    collision_candidate: dict[str, Any],
    requests: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Fix the samples and canonical primitive representation before capture."""

    selection_hash = _verify_digest(selection, "selection_sha256", "selection")
    candidate_hash = _verify_digest(
        collision_candidate, "candidate_sha256", "collision candidate"
    )
    if (
        selection.get("schema") != SELECTION_SCHEMA
        or selection.get("status")
        != "INCOMPLETE_V4_NATIVE_REPLAY_NO_IMPROVEMENT_RETAINED"
        or selection.get("native_improvement_over_control") is not False
        or selection.get("selected_candidate_id") is not None
    ):
        raise ParityContractError("ARM-203 selection boundary changed")
    _require_zero_authority(selection, "selection")
    _require_zero_authority(collision_candidate, "collision candidate")

    results = selection.get("retained_results")
    if not isinstance(results, list) or len(results) != 2:
        raise ParityContractError("completed ARM-203 candidate coverage changed")
    captures = []
    for result in results:
        candidate_id = result.get("candidate_id")
        request = requests.get(candidate_id)
        if request is None:
            raise ParityContractError(f"request is absent for {candidate_id}")
        request_hash = _verify_digest(request, "request_sha256", "route request")
        if (
            request.get("route_shape_candidate_id") != candidate_id
            or result.get("native_receipt_schema")
            != "tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v4"
            or result.get("station_route_predicate_applied") is not True
        ):
            raise ParityContractError(f"candidate binding changed for {candidate_id}")
        _require_zero_authority(request, "route request")
        capture_samples = _select_capture_samples(result)
        for sample in capture_samples:
            segment = sample["source_segment_index"]
            if not isinstance(segment, int) or not 0 <= segment < len(request["samples"]):
                raise ParityContractError("source segment is outside the route request")
            source = request["samples"][segment]
            destination = request["samples"][min(segment + 1, len(request["samples"]) - 1)]
            sample["source_phase"] = source["phase"]
            sample["destination_phase"] = destination["phase"]
            sample["target_id"] = destination.get("target_id") or source.get("target_id")
        captures.append(
            {
                "candidate_id": candidate_id,
                "request_sha256": request_hash,
                "native_receipt_sha256": result["native_receipt_sha256"],
                "capture_samples": capture_samples,
            }
        )

    plan: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_NATIVE_AND_OFFLINE_GEOMETRY_CAPTURE",
        "source_selection_sha256": selection_hash,
        "source_collision_candidate_sha256": candidate_hash,
        "candidate_captures": captures,
        "canonical_primitive_representation": {
            "length_unit": "mm",
            "matrix_layout": "ROW_MAJOR_4X4",
            "matrix_semantics": "CANONICAL_PRIMITIVE_LOCAL_TO_BOARD_WORLD",
            "rotation_semantics": "RIGHT_HANDED_ACTIVE",
            "primitive_key": ["body_id", "primitive_index"],
            "required_fields": [
                "body_id",
                "primitive_index",
                "kind",
                "half_extents_mm",
                "local_center_mm",
                "local_rotation_row_major",
                "world_matrix_row_major",
            ],
        },
        "comparison_tolerances": {
            "translation_mm": 0.001,
            "half_extent_mm": 0.000001,
            "rotation_matrix_element": 0.000001,
        },
        "geometry_mutated": False,
        "route_mutated": False,
        "placement_mutated": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
    }
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def build_fixed_base_replay_plan(
    selection: dict[str, Any],
    parity_report: dict[str, Any],
    parity_plan: dict[str, Any],
) -> dict[str, Any]:
    """Bind the immutable v4 outcomes to a fail-closed fixed-base rerun."""

    selection_hash = _verify_digest(selection, "selection_sha256", "selection")
    report_hash = _verify_digest(parity_report, "report_sha256", "parity report")
    parity_plan_hash = _verify_digest(parity_plan, "plan_sha256", "parity plan")
    _require_zero_authority(selection, "selection")
    _require_zero_authority(parity_report, "parity report")
    _require_zero_authority(parity_plan, "parity plan")
    conclusion = parity_report.get("diagnostic_conclusion")
    if (
        selection.get("schema") != SELECTION_SCHEMA
        or selection.get("status")
        != "INCOMPLETE_V4_NATIVE_REPLAY_NO_IMPROVEMENT_RETAINED"
        or parity_report.get("schema") != REPORT_SCHEMA
        or parity_report.get("status") != "PARITY_DISCREPANCY_CLASSIFIED"
        or parity_plan.get("schema") != PLAN_SCHEMA
        or parity_report.get("source_plan_sha256") != parity_plan_hash
        or parity_plan.get("source_selection_sha256") != selection_hash
        or not isinstance(conclusion, dict)
        or conclusion.get("primary_classification")
        != "NATIVE_ROBOT_ROOT_Z_DRIFT"
        or conclusion.get("required_next_action")
        != "REPLAY_WITH_FIXED_BASE_AND_ROOT_POSE_INVARIANT"
        or conclusion.get(
            "retained_native_collision_conclusion_usable_for_fixed_base_route_comparison"
        )
        is not False
    ):
        raise ParityContractError("ARM-204 fixed-base handoff changed")

    results = selection.get("retained_results")
    if not isinstance(results, list) or len(results) != 2:
        raise ParityContractError("completed ARM-203 candidate coverage changed")
    captures = {
        item.get("candidate_id"): item
        for item in parity_plan.get("candidate_captures", [])
    }
    candidates = []
    for result in results:
        candidate_id = result.get("candidate_id")
        capture = captures.get(candidate_id)
        if (
            not isinstance(candidate_id, str)
            or not candidate_id
            or result.get("native_receipt_schema")
            != "tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v4"
            or result.get("station_route_predicate_applied") is not True
            or not isinstance(result.get("native_receipt_sha256"), str)
            or not isinstance(capture, dict)
            or capture.get("native_receipt_sha256")
            != result.get("native_receipt_sha256")
        ):
            raise ParityContractError("fixed-base candidate binding changed")
        candidates.append(
            {
                "candidate_id": candidate_id,
                "source_request_sha256": capture.get("request_sha256"),
                "source_v4_native_receipt_sha256": result["native_receipt_sha256"],
                "source_v4_bounded_sample_count": result["bounded_sample_count"],
            }
        )
    if any(
        not isinstance(item["source_request_sha256"], str)
        for item in candidates
    ):
        raise ParityContractError("fixed-base source request binding is absent")

    plan: dict[str, Any] = {
        "schema": FIXED_BASE_PLAN_SCHEMA,
        "status": "READY_FOR_FIXED_BASE_ZERO_AUTHORITY_NATIVE_REPLAY",
        "source_selection_sha256": selection_hash,
        "source_parity_report_sha256": report_hash,
        "source_parity_plan_sha256": parity_plan_hash,
        "candidates": sorted(candidates, key=lambda item: item["candidate_id"]),
        "fixed_base_contract": {
            "mechanism": "USD_FIXED_JOINT_TO_WORLD",
            "articulation_path": "/roarm_m3",
            "base_body_name": "base_link",
            "author_before_physics_initialization": True,
            "requested_placement_is_world_anchor": True,
        },
        "root_pose_invariant": {
            "translation_tolerance_mm": 0.05,
            "orientation_tolerance_deg": 0.1,
            "required_at_admission": True,
            "required_after_every_sample": True,
            "failure_behavior": "ERROR_NO_ACCEPTED_COLLISION_RECEIPT",
        },
        "rotation_serialization": {
            "matrix_layout": "ROW_MAJOR_3X3",
            "semantics": "RIGHT_HANDED_ACTIVE_COLUMN_VECTOR",
            "gf_row_vector_storage_transposed": True,
        },
        "source_v4_receipts_mutated": False,
        "geometry_mutated": False,
        "route_mutated": False,
        "placement_mutated": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
    }
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def retain_fixed_base_replay_results(
    plan: dict[str, Any], receipts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Retain complete v5 fixed-base evidence without promoting authority."""

    plan_hash = _verify_digest(plan, "plan_sha256", "fixed-base plan")
    _require_zero_authority(plan, "fixed-base plan")
    if (
        plan.get("schema") != FIXED_BASE_PLAN_SCHEMA
        or plan.get("status")
        != "READY_FOR_FIXED_BASE_ZERO_AUTHORITY_NATIVE_REPLAY"
    ):
        raise ParityContractError("fixed-base plan boundary changed")
    candidates = {
        item.get("source_v4_native_receipt_sha256"): item
        for item in plan.get("candidates", [])
        if isinstance(item, dict)
    }
    if len(candidates) != 2 or len(receipts) != len(candidates):
        raise ParityContractError("fixed-base receipt coverage changed")

    retained = []
    seen: set[str] = set()
    for receipt in receipts:
        receipt_hash = _verify_digest(receipt, "receipt_sha256", "v5 receipt")
        _require_zero_authority(receipt, "v5 receipt")
        source_v4_hash = receipt.get("source_v4_native_receipt_sha256")
        candidate = candidates.get(source_v4_hash)
        root = receipt.get("root_pose_invariant")
        bindings = receipt.get("source_bindings")
        if (
            receipt.get("schema") != FIXED_BASE_RECEIPT_SCHEMA
            or receipt.get("fixed_base_replay_applied") is not True
            or receipt.get("source_v4_receipt_mutated") is not False
            or not isinstance(candidate, dict)
            or source_v4_hash in seen
            or receipt.get("bounded_sample_count")
            != candidate.get("source_v4_bounded_sample_count")
            or not isinstance(bindings, dict)
            or bindings.get("fixed_base_replay_plan_sha256") != plan_hash
            or not isinstance(root, dict)
            or root.get("status") != "PASS"
            or root.get("observation_count")
            != receipt.get("bounded_sample_count") + 1
            or root.get("expected_observation_count")
            != root.get("observation_count")
            or not isinstance(
                root.get("maximum_translation_delta_mm"), (int, float)
            )
            or root.get("maximum_translation_delta_mm")
            > plan["root_pose_invariant"]["translation_tolerance_mm"]
            or not isinstance(
                root.get("maximum_orientation_delta_deg"), (int, float)
            )
            or root.get("maximum_orientation_delta_deg")
            > plan["root_pose_invariant"]["orientation_tolerance_deg"]
            or any(
                not isinstance(receipt.get(field), int)
                or isinstance(receipt.get(field), bool)
                or receipt.get(field) < 0
                for field in (
                    "physical_solid_blocker_pair_count",
                    "planning_envelope_blocker_pair_count",
                    "unreviewed_blocker_pair_count",
                    "policy_excluded_pair_count",
                )
            )
        ):
            raise ParityContractError("fixed-base v5 receipt binding changed")
        seen.add(source_v4_hash)
        retained.append(
            {
                "candidate_id": candidate["candidate_id"],
                "v5_receipt_sha256": receipt_hash,
                "bounded_sample_count": receipt["bounded_sample_count"],
                "root_pose_observation_count": root["observation_count"],
                "maximum_root_translation_delta_mm": root[
                    "maximum_translation_delta_mm"
                ],
                "maximum_root_orientation_delta_deg": root[
                    "maximum_orientation_delta_deg"
                ],
                "physical_solid_blocker_pair_count": receipt.get(
                    "physical_solid_blocker_pair_count"
                ),
                "planning_envelope_blocker_pair_count": receipt.get(
                    "planning_envelope_blocker_pair_count"
                ),
                "unreviewed_blocker_pair_count": receipt.get(
                    "unreviewed_blocker_pair_count"
                ),
                "policy_excluded_pair_count": receipt.get(
                    "policy_excluded_pair_count"
                ),
                "diagnostic_status": receipt.get("status"),
            }
        )
    retained.sort(key=lambda item: item["candidate_id"])
    zero_physical = all(
        item["physical_solid_blocker_pair_count"] == 0
        and item["planning_envelope_blocker_pair_count"] == 0
        and item["unreviewed_blocker_pair_count"] == 0
        for item in retained
    )
    result: dict[str, Any] = {
        "schema": FIXED_BASE_RESULT_SCHEMA,
        "status": (
            "FIXED_BASE_REPLAY_COMPLETE_NO_PHYSICAL_SOLID_BLOCKERS"
            if zero_physical
            else "FIXED_BASE_REPLAY_COMPLETE_BLOCKERS_RETAINED"
        ),
        "source_plan_sha256": plan_hash,
        "retained_results": retained,
        "fixed_base_root_invariant_passed_for_all_candidates": True,
        "zero_physical_solid_blockers_for_all_candidates": zero_physical,
        "next_action": (
            "COMPARE_KEY_MECHANICS_AND_SELECT_LEARNING_BASELINE"
            if zero_physical
            else "REVIEW_RETAINED_PHYSICAL_BLOCKERS"
        ),
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
    }
    result["result_sha256"] = _canonical_sha256(result)
    return result


def _finite(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ParityContractError(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ParityContractError(f"{label} is not finite")
    return result


def _project_h_key_actions(
    request: dict[str, Any], profile: dict[str, Any]
) -> list[dict[str, Any]]:
    """Project governed H endpoints through the existing mechanics thresholds."""

    prior = profile.get("mechanics_prior")
    region = profile.get("regions", {}).get("H")
    if not isinstance(prior, dict) or not isinstance(region, dict):
        raise ParityContractError("representative H mechanics are absent")
    center = region.get("center_board_xy_mm")
    half = region.get("half_extent_mm")
    if (
        not isinstance(center, list)
        or len(center) != 2
        or not isinstance(half, list)
        or len(half) != 2
    ):
        raise ParityContractError("representative H geometry is invalid")
    rest_z = _finite(profile.get("target_plane_z_board_mm"), "H rest plane")
    activation = _finite(prior["activation_mm"]["nominal"], "activation")
    release = _finite(prior["release_mm"]["nominal"], "release")
    travel = _finite(prior["travel_mm"]["nominal"], "travel")
    stiffness = _finite(
        prior["stiffness_n_per_mm"]["nominal"], "key stiffness"
    )
    damping = _finite(
        prior["damping_n_s_per_mm"]["nominal"], "key damping"
    )
    margin = _finite(prior["center_margin_mm"], "center margin")

    grouped: dict[int, list[dict[str, Any]]] = {}
    for sample in request.get("samples", []):
        if sample.get("target_id") == "H" and sample.get("phase") in {
            "HOVER",
            "CONTACT",
            "RETRACT",
        }:
            action = sample.get("action_index")
            if not isinstance(action, int):
                raise ParityContractError("H action index is invalid")
            grouped.setdefault(action, []).append(sample)
    if not grouped:
        raise ParityContractError("candidate contains no H key action")

    results = []
    for action, samples in sorted(grouped.items()):
        ordered = sorted(samples, key=lambda item: item.get("sequence", -1))
        if [item.get("phase") for item in ordered] != [
            "HOVER",
            "CONTACT",
            "RETRACT",
        ] or not all(item.get("phase_endpoint") is True for item in ordered):
            raise ParityContractError("H action endpoint schedule changed")
        trace = []
        for sample in ordered:
            point = sample.get("expected_tool_tip_board_mm")
            if not isinstance(point, list) or len(point) != 3:
                raise ParityContractError("H endpoint position is invalid")
            x, y, z = (_finite(value, "H endpoint") for value in point)
            trace.append(
                {
                    "sequence": sample["sequence"],
                    "phase": sample["phase"],
                    "time_s": _finite(
                        sample.get("time_from_start_ns"), "H endpoint time"
                    )
                    / 1_000_000_000.0,
                    "tip_x_board_mm": x,
                    "tip_y_board_mm": y,
                    "compression_mm": max(0.0, rest_z - z),
                }
            )
        if any(
            trace[index]["time_s"] <= trace[index - 1]["time_s"]
            for index in range(1, len(trace))
        ):
            raise ParityContractError("H endpoint time is not increasing")
        contact = trace[1]
        safe_center = all(
            abs(contact[key] - center[index]) <= half[index] - margin
            for index, key in enumerate(("tip_x_board_mm", "tip_y_board_mm"))
        )
        compression = contact["compression_mm"]
        released = trace[0]["compression_mm"] <= release and trace[2][
            "compression_mm"
        ] <= release
        activated = compression >= activation
        within_travel = compression <= travel
        velocity = compression / (contact["time_s"] - trace[0]["time_s"])
        estimated_force = stiffness * compression + damping * max(velocity, 0.0)
        accepted = safe_center and released and activated and within_travel
        results.append(
            {
                "action_index": action,
                "status": "ACCEPTED" if accepted else "BLOCKED_KEY_MECHANICS",
                "accepted": accepted,
                "resolved_key": "H" if safe_center and compression > 0.0 else None,
                "activation_count": 1 if activated else 0,
                "maximum_compression_mm": compression,
                "final_compression_mm": trace[2]["compression_mm"],
                "maximum_estimated_force_n": estimated_force,
                "safe_center": safe_center,
                "within_travel": within_travel,
                "complete_release": released,
                "trace": trace,
            }
        )
    return results


def _candidate_motion_metrics(
    request: dict[str, Any], ik_receipt: dict[str, Any]
) -> dict[str, float | int]:
    samples = request.get("samples")
    joints = ik_receipt.get("joint_results")
    if (
        not isinstance(samples, list)
        or not isinstance(joints, list)
        or len(samples) != len(joints)
        or len(samples) < 3
    ):
        raise ParityContractError("candidate motion sample coverage changed")
    times = [
        _finite(sample.get("time_from_start_ns"), "candidate sample time")
        / 1_000_000_000.0
        for sample in samples
    ]
    if any(times[index] <= times[index - 1] for index in range(1, len(times))):
        raise ParityContractError("candidate sample time is not increasing")
    vectors = []
    cartesian = []
    for sample, joint in zip(samples, joints, strict=True):
        if joint.get("waypoint_sequence") != sample.get("sequence"):
            raise ParityContractError("candidate waypoint sequence changed")
        positions = joint.get("solution_arm_joint_positions_rad")
        point = sample.get("expected_tool_tip_board_mm")
        if not isinstance(positions, dict) or not isinstance(point, list) or len(point) != 3:
            raise ParityContractError("candidate motion vector is invalid")
        vectors.append([_finite(positions[name], name) for name in ARM_JOINT_ORDER])
        cartesian.append([_finite(value, "Cartesian point") for value in point])

    velocities: list[list[float]] = []
    total_joint_travel = 0.0
    sum_squared_joint_delta = 0.0
    cartesian_path = 0.0
    for index in range(1, len(samples)):
        dt = times[index] - times[index - 1]
        delta = [
            vectors[index][axis] - vectors[index - 1][axis]
            for axis in range(len(ARM_JOINT_ORDER))
        ]
        velocities.append([value / dt for value in delta])
        total_joint_travel += sum(abs(value) for value in delta)
        sum_squared_joint_delta += sum(value * value for value in delta)
        cartesian_path += math.dist(cartesian[index - 1], cartesian[index])
    accelerations = []
    for index in range(1, len(velocities)):
        dt = (times[index + 1] - times[index - 1]) / 2.0
        accelerations.extend(
            abs((velocities[index][axis] - velocities[index - 1][axis]) / dt)
            for axis in range(len(ARM_JOINT_ORDER))
        )
    metrics = ik_receipt.get("metrics")
    if not isinstance(metrics, dict):
        raise ParityContractError("candidate IK metrics are absent")
    return {
        "sample_count": len(samples),
        "duration_s": times[-1] - times[0],
        "cartesian_path_length_mm": cartesian_path,
        "total_absolute_joint_travel_rad": total_joint_travel,
        "sum_squared_joint_delta_rad2": sum_squared_joint_delta,
        "maximum_commanded_joint_velocity_rad_s": max(
            abs(value) for row in velocities for value in row
        ),
        "maximum_commanded_joint_acceleration_rad_s2": max(accelerations),
        "maximum_adjacent_joint_delta_rad": _finite(
            metrics.get("maximum_adjacent_joint_delta_rad"), "maximum joint delta"
        ),
        "maximum_position_error_mm": _finite(
            metrics.get("maximum_position_error_mm"), "maximum position error"
        ),
        "minimum_normalized_arm_joint_margin": _finite(
            metrics.get("minimum_normalized_arm_joint_margin"), "minimum joint margin"
        ),
    }


def select_key_mechanics_learning_baseline(
    fixed_result: dict[str, Any],
    fixed_receipts: list[dict[str, Any]],
    cartesian_requests: list[dict[str, Any]],
    ik_receipts: list[dict[str, Any]],
    mechanics_profile: dict[str, Any],
) -> dict[str, Any]:
    """Select one zero-authority baseline from complete ARM-205 evidence."""

    fixed_hash = _verify_digest(fixed_result, "result_sha256", "fixed-base result")
    _require_zero_authority(fixed_result, "fixed-base result")
    if (
        fixed_result.get("schema") != FIXED_BASE_RESULT_SCHEMA
        or fixed_result.get("status")
        != "FIXED_BASE_REPLAY_COMPLETE_NO_PHYSICAL_SOLID_BLOCKERS"
        or fixed_result.get("fixed_base_root_invariant_passed_for_all_candidates")
        is not True
        or fixed_result.get("zero_physical_solid_blockers_for_all_candidates")
        is not True
        or fixed_result.get("next_action")
        != "COMPARE_KEY_MECHANICS_AND_SELECT_LEARNING_BASELINE"
    ):
        raise ParityContractError("fixed-base result is not eligible for selection")
    profile_hash = _verify_digest(
        mechanics_profile, "profile_sha256", "key mechanics profile"
    )
    if mechanics_profile.get("schema") != KEY_MECHANICS_PROFILE_SCHEMA:
        raise ParityContractError("key mechanics profile schema changed")
    authority = mechanics_profile.get("authority")
    if not isinstance(authority, dict) or not authority or not all(
        value is False for value in authority.values()
    ):
        raise ParityContractError("key mechanics profile authority changed")

    retained = fixed_result.get("retained_results")
    if not isinstance(retained, list) or len(retained) != 2:
        raise ParityContractError("fixed-base candidate coverage changed")
    expected = {item.get("candidate_id"): item for item in retained}
    if None in expected or len(expected) != len(retained):
        raise ParityContractError("fixed-base candidate ids changed")

    receipt_by_hash = {}
    for receipt in fixed_receipts:
        receipt_hash = _verify_digest(receipt, "receipt_sha256", "v5 receipt")
        _require_zero_authority(receipt, "v5 receipt")
        if receipt.get("schema") != FIXED_BASE_RECEIPT_SCHEMA:
            raise ParityContractError("v5 receipt schema changed")
        receipt_by_hash[receipt_hash] = receipt
    request_by_candidate = {}
    for request in cartesian_requests:
        request_hash = _verify_digest(request, "request_sha256", "Cartesian request")
        _require_zero_authority(request, "Cartesian request")
        candidate_id = request.get("route_shape_candidate_id")
        if (
            request.get("schema") != CARTESIAN_REQUEST_SCHEMA
            or request.get("status") != "READY_FOR_IK_QUALIFICATION"
            or request.get("route_shape_materialized") is not True
            or request.get("joint_positions_included") is not False
            or candidate_id in request_by_candidate
        ):
            raise ParityContractError("Cartesian candidate boundary changed")
        request_by_candidate[candidate_id] = (request_hash, request)
    ik_by_candidate = {}
    for receipt in ik_receipts:
        receipt_hash = _verify_digest(receipt, "receipt_sha256", "IK receipt")
        _require_zero_authority(receipt, "IK receipt")
        candidate_id = receipt.get("route_shape_candidate_id")
        if (
            receipt.get("schema") != IK_RECEIPT_SCHEMA
            or receipt.get("status") != "READY_FOR_COLLISION_QUALIFICATION"
            or receipt.get("ik_all_samples_accepted") is not True
            or candidate_id in ik_by_candidate
        ):
            raise ParityContractError("IK candidate boundary changed")
        ik_by_candidate[candidate_id] = (receipt_hash, receipt)
    if set(expected) != set(request_by_candidate) or set(expected) != set(ik_by_candidate):
        raise ParityContractError("learning-baseline candidate coverage changed")

    candidates = []
    mechanics_signatures = []
    for candidate_id in sorted(expected):
        retained_row = expected[candidate_id]
        v5_hash = retained_row.get("v5_receipt_sha256")
        v5 = receipt_by_hash.get(v5_hash)
        request_hash, request = request_by_candidate[candidate_id]
        ik_hash, ik = ik_by_candidate[candidate_id]
        if (
            v5 is None
            or v5.get("source_bindings", {}).get("ik_receipt_sha256") != ik_hash
            or ik.get("source_request_sha256") != request_hash
            or request.get("route_shape_candidate") != ik.get("route_shape_candidate")
            or retained_row.get("physical_solid_blocker_pair_count") != 0
            or retained_row.get("planning_envelope_blocker_pair_count") != 0
            or retained_row.get("unreviewed_blocker_pair_count") != 0
            or v5.get("root_pose_invariant", {}).get("status") != "PASS"
        ):
            raise ParityContractError("candidate evidence lineage changed")
        actions = _project_h_key_actions(request, mechanics_profile)
        mechanics_passed = all(item["accepted"] for item in actions)
        signature = [
            {
                "action_index": item["action_index"],
                "status": item["status"],
                "resolved_key": item["resolved_key"],
                "activation_count": item["activation_count"],
                "maximum_compression_mm": item["maximum_compression_mm"],
                "final_compression_mm": item["final_compression_mm"],
            }
            for item in actions
        ]
        mechanics_signatures.append(signature)
        motion = _candidate_motion_metrics(request, ik)
        candidates.append(
            {
                "candidate_id": candidate_id,
                "route_shape_candidate": request["route_shape_candidate"],
                "source_cartesian_request_sha256": request_hash,
                "source_ik_receipt_sha256": ik_hash,
                "source_fixed_base_v5_receipt_sha256": v5_hash,
                "fixed_base_collision_passed": True,
                "key_mechanics_passed": mechanics_passed,
                "key_mechanics_actions": actions,
                "motion_metrics": motion,
                "fixed_base_metrics": {
                    "bounded_sample_count": retained_row["bounded_sample_count"],
                    "maximum_root_translation_delta_mm": retained_row[
                        "maximum_root_translation_delta_mm"
                    ],
                    "maximum_root_orientation_delta_deg": retained_row[
                        "maximum_root_orientation_delta_deg"
                    ],
                },
            }
        )
    mechanics_equivalent = all(
        signature == mechanics_signatures[0] for signature in mechanics_signatures[1:]
    )
    eligible = [
        item
        for item in candidates
        if item["fixed_base_collision_passed"] and item["key_mechanics_passed"]
    ]
    if len(eligible) != len(candidates) or not mechanics_equivalent:
        raise ParityContractError("candidate key mechanics are not selection-equivalent")

    ranking_rule = [
        "maximum_commanded_joint_acceleration_rad_s2 ASC",
        "maximum_adjacent_joint_delta_rad ASC",
        "total_absolute_joint_travel_rad ASC",
        "maximum_commanded_joint_velocity_rad_s ASC",
        "cartesian_path_length_mm ASC",
        "maximum_position_error_mm ASC",
        "candidate_id ASC",
    ]
    ranked = sorted(
        eligible,
        key=lambda item: (
            item["motion_metrics"]["maximum_commanded_joint_acceleration_rad_s2"],
            item["motion_metrics"]["maximum_adjacent_joint_delta_rad"],
            item["motion_metrics"]["total_absolute_joint_travel_rad"],
            item["motion_metrics"]["maximum_commanded_joint_velocity_rad_s"],
            item["motion_metrics"]["cartesian_path_length_mm"],
            item["motion_metrics"]["maximum_position_error_mm"],
            item["candidate_id"],
        ),
    )
    for rank, item in enumerate(ranked, start=1):
        item["learning_baseline_rank"] = rank
    result: dict[str, Any] = {
        "schema": LEARNING_BASELINE_SELECTION_SCHEMA,
        "status": "SELECTED_ZERO_AUTHORITY_SIMULATION_LEARNING_BASELINE",
        "source_fixed_base_result_sha256": fixed_hash,
        "source_key_mechanics_profile_sha256": profile_hash,
        "candidate_count": len(candidates),
        "key_mechanics_equivalent_across_candidates": mechanics_equivalent,
        "ranking_rule": ranking_rule,
        "ranked_candidates": ranked,
        "selected_candidate_id": ranked[0]["candidate_id"],
        "selected_candidate_rank": 1,
        "selection_scope": "SIMULATION_LEARNING_BASELINE_ONLY",
        "next_action": "RUN_DRIVE_CONTROLLED_ROBOT_H_KEY_REPLAY_FOR_SELECTED_BASELINE",
        "continuous_collision_proven": False,
        "native_robot_key_contact_proven": False,
        "installed_collision_qualified": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "key_mechanics_projection_uses_synthetic_bounded_priors",
            "ranking_uses_commanded_kinematics_not_drive_or_contact_dynamics",
            "fixed_base_replay_is_discrete_not_continuous_clearance",
            "selection_grants_no_hardware_motion_contact_or_release_authority",
        ],
    }
    result["selection_sha256"] = _canonical_sha256(result)
    return result


def _capture_records(capture: dict[str, Any], source: str) -> dict[tuple[Any, ...], dict[str, Any]]:
    _verify_digest(capture, "capture_sha256", f"{source} capture")
    if capture.get("schema") != CAPTURE_SCHEMA or capture.get("source") != source:
        raise ParityContractError(f"{source} capture boundary changed")
    _require_zero_authority(capture, f"{source} capture")
    records: dict[tuple[Any, ...], dict[str, Any]] = {}
    for sample in capture.get("samples", []):
        candidate_id = sample.get("candidate_id")
        sequence = sample.get("sample_sequence")
        for primitive in sample.get("primitives", []):
            key = (
                candidate_id,
                sequence,
                primitive.get("body_id"),
                primitive.get("primitive_index"),
            )
            if key in records:
                raise ParityContractError(f"duplicate {source} primitive record")
            records[key] = primitive
    if not records:
        raise ParityContractError(f"{source} capture is empty")
    return records


def _maximum_delta(first: list[float], second: list[float]) -> float:
    if len(first) != len(second) or not first:
        return math.inf
    return max(abs(float(left) - float(right)) for left, right in zip(first, second))


def _systematic_findings(comparisons: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Separate a moving robot root from per-primitive geometry disagreement."""

    findings: list[dict[str, Any]] = []
    workcell = [item for item in comparisons if item["body_id"].startswith("workcell:")]
    if workcell and all(item["classification"] == "MATCH" for item in workcell):
        findings.append(
            {
                "classification": "STATIC_WORKCELL_PARITY_CONFIRMED",
                "primitive_comparison_count": len(workcell),
            }
        )

    robot = [item for item in comparisons if item["body_id"].startswith("robot:")]
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for item in robot:
        grouped.setdefault(
            (item["candidate_id"], item["sample_sequence"]), []
        ).append(item)
    coherent_offsets: list[dict[str, Any]] = []
    for (candidate_id, sample_sequence), items in sorted(grouped.items()):
        offsets = [
            item.get("translation_offset_native_minus_offline_mm") for item in items
        ]
        if not offsets or any(not isinstance(offset, list) for offset in offsets):
            continue
        component_spread = [
            max(float(offset[index]) for offset in offsets)
            - min(float(offset[index]) for offset in offsets)
            for index in range(3)
        ]
        # The native USD/PhysX bridge is single precision.  A 0.05 mm spread
        # is tight enough to distinguish a shared root displacement from local
        # collision-primitive placement error without pretending micrometre
        # precision at the installed-workcell scale.
        if max(component_spread) <= 0.05:
            mean = [
                sum(float(offset[index]) for offset in offsets) / len(offsets)
                for index in range(3)
            ]
            coherent_offsets.append(
                {
                    "candidate_id": candidate_id,
                    "sample_sequence": sample_sequence,
                    "robot_primitive_count": len(items),
                    "mean_translation_offset_native_minus_offline_mm": mean,
                    "maximum_component_spread_mm": max(component_spread),
                }
            )
    if coherent_offsets:
        findings.append(
            {
                "classification": "ROBOT_RIGID_TRANSLATION_OFFSET_BY_SAMPLE",
                "samples": coherent_offsets,
            }
        )

    root_z_drift = bool(
        workcell
        and all(item["classification"] == "MATCH" for item in workcell)
        and len(coherent_offsets) == len(grouped)
        and coherent_offsets
        and all(
            abs(item["mean_translation_offset_native_minus_offline_mm"][0]) <= 0.05
            and abs(item["mean_translation_offset_native_minus_offline_mm"][1]) <= 0.05
            and item["mean_translation_offset_native_minus_offline_mm"][2] < -0.05
            for item in coherent_offsets
        )
    )
    conclusion = {
        "primary_classification": (
            "NATIVE_ROBOT_ROOT_Z_DRIFT"
            if root_z_drift
            else "PRIMITIVE_GEOMETRY_PARITY_DISCREPANCY"
        ),
        "retained_native_collision_conclusion_usable_for_fixed_base_route_comparison": (
            not root_z_drift
        ),
        "required_next_action": (
            "REPLAY_WITH_FIXED_BASE_AND_ROOT_POSE_INVARIANT"
            if root_z_drift
            else "RESOLVE_REPORTED_PRIMITIVE_DISCREPANCIES"
        ),
    }
    return findings, conclusion


def compare_captures(
    plan: dict[str, Any],
    native_capture: dict[str, Any],
    offline_capture: dict[str, Any],
) -> dict[str, Any]:
    """Compare two captures without allowing missing primitives to disappear."""

    plan_hash = _verify_digest(plan, "plan_sha256", "parity plan")
    if plan.get("schema") != PLAN_SCHEMA:
        raise ParityContractError("parity plan schema changed")
    native = _capture_records(native_capture, "NATIVE_PHYSX")
    offline = _capture_records(offline_capture, "OFFLINE_OBB")
    native_hash = native_capture["capture_sha256"]
    offline_hash = offline_capture["capture_sha256"]
    if (
        native_capture.get("source_plan_sha256") != plan_hash
        or offline_capture.get("source_plan_sha256") != plan_hash
    ):
        raise ParityContractError("capture plan binding changed")

    translation_limit = plan["comparison_tolerances"]["translation_mm"]
    extent_limit = plan["comparison_tolerances"]["half_extent_mm"]
    rotation_limit = plan["comparison_tolerances"]["rotation_matrix_element"]
    comparisons = []
    classifications: set[str] = set()
    for key in sorted(set(native) | set(offline)):
        native_item = native.get(key)
        offline_item = offline.get(key)
        if native_item is None or offline_item is None:
            classification = "COVERAGE_MISMATCH"
            details = {"native_present": native_item is not None, "offline_present": offline_item is not None}
        else:
            required = plan["canonical_primitive_representation"]["required_fields"]
            if any(field not in native_item or field not in offline_item for field in required):
                raise ParityContractError("capture primitive representation is incomplete")
            if native_item["kind"] != offline_item["kind"]:
                classification = "GEOMETRY_KIND_MISMATCH"
                details = {}
            else:
                extent_delta = _maximum_delta(
                    native_item["half_extents_mm"], offline_item["half_extents_mm"]
                )
                native_matrix = native_item["world_matrix_row_major"]
                offline_matrix = offline_item["world_matrix_row_major"]
                if len(native_matrix) != 16 or len(offline_matrix) != 16:
                    raise ParityContractError("world matrix shape changed")
                translation_delta = max(
                    abs(float(native_matrix[index]) - float(offline_matrix[index]))
                    for index in (3, 7, 11)
                )
                rotation_indices = (0, 1, 2, 4, 5, 6, 8, 9, 10)
                rotation_delta = max(
                    abs(float(native_matrix[index]) - float(offline_matrix[index]))
                    for index in rotation_indices
                )
                details = {
                    "maximum_half_extent_delta_mm": extent_delta,
                    "maximum_translation_delta_mm": translation_delta,
                    "maximum_rotation_element_delta": rotation_delta,
                    "translation_offset_native_minus_offline_mm": [
                        float(native_matrix[index]) - float(offline_matrix[index])
                        for index in (3, 7, 11)
                    ],
                }
                if extent_delta > extent_limit:
                    classification = "GEOMETRY_DIMENSION_MISMATCH"
                elif translation_delta > translation_limit:
                    classification = "WORLD_TRANSLATION_MISMATCH"
                elif rotation_delta > rotation_limit:
                    classification = "WORLD_ORIENTATION_MISMATCH"
                else:
                    classification = "MATCH"
        classifications.add(classification)
        comparisons.append(
            {
                "candidate_id": key[0],
                "sample_sequence": key[1],
                "body_id": key[2],
                "primitive_index": key[3],
                "classification": classification,
                **details,
            }
        )

    mismatch_count = sum(item["classification"] != "MATCH" for item in comparisons)
    systematic_findings, diagnostic_conclusion = _systematic_findings(comparisons)
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": "PARITY_MATCH" if mismatch_count == 0 else "PARITY_DISCREPANCY_CLASSIFIED",
        "source_plan_sha256": plan_hash,
        "native_capture_sha256": native_hash,
        "offline_capture_sha256": offline_hash,
        "primitive_comparison_count": len(comparisons),
        "mismatch_count": mismatch_count,
        "classifications": sorted(classifications),
        "comparisons": comparisons,
        "systematic_findings": systematic_findings,
        "diagnostic_conclusion": diagnostic_conclusion,
        "geometry_mutated": False,
        "route_mutated": False,
        "placement_mutated": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def merge_captures(
    plan: dict[str, Any], captures: list[dict[str, Any]]
) -> dict[str, Any]:
    """Merge candidate-local native sidecars without changing their records."""

    plan_hash = _verify_digest(plan, "plan_sha256", "parity plan")
    if not captures:
        raise ParityContractError("no captures were supplied")
    samples = []
    source_receipts = []
    seen_candidates: set[str] = set()
    for capture in captures:
        records = _capture_records(capture, "NATIVE_PHYSX")
        if capture.get("source_plan_sha256") != plan_hash:
            raise ParityContractError("native capture plan binding changed")
        candidate_ids = {key[0] for key in records}
        if len(candidate_ids) != 1 or seen_candidates & candidate_ids:
            raise ParityContractError("native capture candidate coverage is invalid")
        seen_candidates.update(candidate_ids)
        samples.extend(capture["samples"])
        source_receipts.append(capture["source_native_receipt_sha256"])
    expected_candidates = {
        item["candidate_id"] for item in plan["candidate_captures"]
    }
    if seen_candidates != expected_candidates:
        raise ParityContractError("native capture candidate set is incomplete")
    merged: dict[str, Any] = {
        "schema": CAPTURE_SCHEMA,
        "source": "NATIVE_PHYSX",
        "source_plan_sha256": plan_hash,
        "source_native_receipt_sha256s": sorted(source_receipts),
        "samples": sorted(
            samples, key=lambda item: (item["candidate_id"], item["sample_sequence"])
        ),
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
    }
    merged["capture_sha256"] = _canonical_sha256(merged)
    return merged


def build_offline_capture(
    plan: dict[str, Any],
    collision_candidate: dict[str, Any],
    collision_requests: list[dict[str, Any]],
    workspace: Path,
) -> dict[str, Any]:
    """Reconstruct the primitive poses consumed by the portable OBB evaluator."""

    try:
        from rocell.application._pinned_model import load_pinned_urdf
        from rocell.application.context import load_simulation_context
        from rocell.geometry import JointPosition, RigidTransform, Rotation3, Vec3
        from rocell.kinematics import ARM_JOINT_NAMES
    except ImportError as exc:
        raise ParityContractError(
            "offline geometry runtime is unavailable; include software/src on PYTHONPATH"
        ) from exc

    plan_hash = _verify_digest(plan, "plan_sha256", "parity plan")
    candidate_hash = _verify_digest(
        collision_candidate, "candidate_sha256", "collision candidate"
    )
    if plan.get("source_collision_candidate_sha256") != candidate_hash:
        raise ParityContractError("offline collision candidate binding changed")
    request_by_source: dict[str, dict[str, Any]] = {}
    for request in collision_requests:
        _verify_digest(request, "request_sha256", "collision request")
        _require_zero_authority(request, "collision request")
        source_hash = request.get("source_request_sha256")
        if not isinstance(source_hash, str) or source_hash in request_by_source:
            raise ParityContractError("collision request source binding is invalid")
        request_by_source[source_hash] = request

    root = workspace.resolve(strict=True)
    context = load_simulation_context(
        root, root / "software/config/system_manifest.json"
    )
    model = load_pinned_urdf(
        context.scenario.model_path, context.scenario.model_sha256
    ).model
    remaining = set(model.movable_joint_names) - set(ARM_JOINT_NAMES)
    if len(remaining) != 1:
        raise ParityContractError("pinned robot gripper topology changed")
    gripper_joint = next(iter(remaining))
    fixed = model.joint("world_to_base_link")
    robot_bodies = collision_candidate.get("robot_bodies", [])
    physical_workcell_bodies = [
        body
        for body in collision_candidate.get("workcell_bodies", [])
        if not body.get("body_id", "").startswith("workcell:station:")
    ]

    samples = []
    for capture in plan["candidate_captures"]:
        request = request_by_source.get(capture["request_sha256"])
        if request is None:
            raise ParityContractError(
                f"collision request is absent for {capture['candidate_id']}"
            )
        matrix = request.get("robot_placement_matrix_row_major")
        if not isinstance(matrix, list) or len(matrix) != 16:
            raise ParityContractError("collision request placement matrix is invalid")
        board_t_base = RigidTransform(
            "board",
            "base_link",
            Rotation3(
                tuple(matrix[index] for index in (0, 1, 2, 4, 5, 6, 8, 9, 10))
            ),
            Vec3(matrix[3], matrix[7], matrix[11]),
        )
        board_t_world = board_t_base.compose(fixed.transform_at(None).inverse())
        bounded_by_sequence = {
            item["sample_sequence"]: item for item in request["bounded_samples"]
        }
        for selected_sample in capture["capture_samples"]:
            sequence = selected_sample["sample_sequence"]
            bounded = bounded_by_sequence.get(sequence)
            if bounded is None:
                raise ParityContractError("selected bounded sample is absent")
            positions = {
                name: JointPosition.radians(bounded["joint_positions_rad"][name])
                for name in ARM_JOINT_NAMES
            }
            positions[gripper_joint] = context.scenario.fixed_gripper_position
            base_transforms = model.forward_kinematics(positions)
            board_transforms = {
                frame: board_t_world.compose(transform)
                for frame, transform in base_transforms.items()
            }
            primitive_records = []
            for body in [*robot_bodies, *physical_workcell_bodies]:
                parent_transform = (
                    board_transforms[body["parent_frame"]]
                    if body in robot_bodies
                    else RigidTransform.identity("board")
                )
                for primitive_index, primitive in enumerate(body["primitives"]):
                    local = RigidTransform(
                        body["parent_frame"],
                        f"{body['body_id']}:primitive:{primitive_index}",
                        Rotation3(tuple(primitive["rotation_row_major"])),
                        Vec3.from_iterable(primitive["center_mm"]),
                    )
                    world = parent_transform.compose(local)
                    rotation = world.rotation.matrix
                    translation = world.translation_mm
                    primitive_records.append(
                        {
                            "body_id": body["body_id"],
                            "primitive_index": primitive_index,
                            "kind": primitive["kind"],
                            "half_extents_mm": primitive["half_extents_mm"],
                            "local_center_mm": primitive["center_mm"],
                            "local_rotation_row_major": primitive[
                                "rotation_row_major"
                            ],
                            "world_matrix_row_major": [
                                rotation[0],
                                rotation[1],
                                rotation[2],
                                translation.x,
                                rotation[3],
                                rotation[4],
                                rotation[5],
                                translation.y,
                                rotation[6],
                                rotation[7],
                                rotation[8],
                                translation.z,
                                0.0,
                                0.0,
                                0.0,
                                1.0,
                            ],
                        }
                    )
            samples.append(
                {
                    "candidate_id": capture["candidate_id"],
                    "sample_sequence": sequence,
                    "sample_id": bounded["sample_id"],
                    "primitives": sorted(
                        primitive_records,
                        key=lambda item: (item["body_id"], item["primitive_index"]),
                    ),
                }
            )
    result: dict[str, Any] = {
        "schema": CAPTURE_SCHEMA,
        "source": "OFFLINE_OBB",
        "source_plan_sha256": plan_hash,
        "source_collision_candidate_sha256": candidate_hash,
        "samples": sorted(
            samples, key=lambda item: (item["candidate_id"], item["sample_sequence"])
        ),
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
    }
    result["capture_sha256"] = _canonical_sha256(result)
    return result


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.resolve(strict=True).read_bytes())


def _write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build-plan", action="store_true")
    mode.add_argument("--compare", action="store_true")
    mode.add_argument("--merge-captures", action="store_true")
    mode.add_argument("--build-offline-capture", action="store_true")
    mode.add_argument("--build-fixed-base-plan", action="store_true")
    mode.add_argument("--retain-fixed-base-results", action="store_true")
    mode.add_argument("--select-learning-baseline", action="store_true")
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--collision-candidate", type=Path)
    parser.add_argument("--request", action="append", type=Path, default=[])
    parser.add_argument("--collision-request", action="append", type=Path, default=[])
    parser.add_argument("--capture", action="append", type=Path, default=[])
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--native-capture", type=Path)
    parser.add_argument("--offline-capture", type=Path)
    parser.add_argument("--parity-report", type=Path)
    parser.add_argument("--fixed-base-receipt", action="append", type=Path, default=[])
    parser.add_argument("--fixed-base-result", type=Path)
    parser.add_argument("--cartesian-request", action="append", type=Path, default=[])
    parser.add_argument("--ik-receipt", action="append", type=Path, default=[])
    parser.add_argument("--layout", type=Path)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.select_learning_baseline:
        if (
            args.fixed_base_result is None
            or not args.fixed_base_receipt
            or not args.cartesian_request
            or not args.ik_receipt
            or args.layout is None
        ):
            parser.error(
                "--select-learning-baseline requires fixed-base result/receipts, "
                "Cartesian requests, IK receipts, and layout"
            )
        from representative_key_mechanics import build_profile

        result = select_key_mechanics_learning_baseline(
            _load(args.fixed_base_result),
            [_load(path) for path in args.fixed_base_receipt],
            [_load(path) for path in args.cartesian_request],
            [_load(path) for path in args.ik_receipt],
            build_profile(args.layout.resolve(strict=True)),
        )
    elif args.retain_fixed_base_results:
        if args.plan is None or not args.fixed_base_receipt:
            parser.error(
                "--retain-fixed-base-results requires a plan and fixed-base receipts"
            )
        result = retain_fixed_base_replay_results(
            _load(args.plan), [_load(path) for path in args.fixed_base_receipt]
        )
    elif args.build_fixed_base_plan:
        if args.selection is None or args.parity_report is None or args.plan is None:
            parser.error(
                "--build-fixed-base-plan requires selection, parity plan, and parity report"
            )
        result = build_fixed_base_replay_plan(
            _load(args.selection), _load(args.parity_report), _load(args.plan)
        )
    elif args.build_plan:
        if args.selection is None or args.collision_candidate is None or not args.request:
            parser.error("--build-plan requires selection, collision candidate, and requests")
        loaded_requests = [_load(path) for path in args.request]
        requests = {
            request["route_shape_candidate_id"]: request
            for request in loaded_requests
        }
        result = build_capture_plan(_load(args.selection), _load(args.collision_candidate), requests)
    elif args.merge_captures:
        if args.plan is None or not args.capture:
            parser.error("--merge-captures requires a plan and captures")
        result = merge_captures(
            _load(args.plan), [_load(path) for path in args.capture]
        )
    elif args.build_offline_capture:
        if (
            args.plan is None
            or args.collision_candidate is None
            or not args.collision_request
        ):
            parser.error(
                "--build-offline-capture requires a plan, collision candidate, "
                "and collision requests"
            )
        result = build_offline_capture(
            _load(args.plan),
            _load(args.collision_candidate),
            [_load(path) for path in args.collision_request],
            args.workspace,
        )
    else:
        if args.plan is None or args.native_capture is None or args.offline_capture is None:
            parser.error("--compare requires plan, native capture, and offline capture")
        result = compare_captures(_load(args.plan), _load(args.native_capture), _load(args.offline_capture))
    _write(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
