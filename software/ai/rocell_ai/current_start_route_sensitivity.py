"""Compare the retained controller-register pose with the passing H route."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

from rocell.arm.joint_mapping import JOINT_MAP, REFERENCE_SHA256, STEP_RAD
from rocell.kinematics import ARM_JOINT_NAMES

from .current_target_sensitivity import run_with_route_evidence
from .model_motion_simulation import run_with_route_evidence as run_seeded_model_motion
from .scene_observation import canonical_hash


SCHEMA = "rocell.current_start_route_sensitivity.v1"
_SERVO_IDS = (11, 12, 13, 14, 15, 16, 17)
_MODEL_TO_REFERENCE_KEY = dict(zip(ARM_JOINT_NAMES, ("b", "s", "e", "t", "r")))


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _retained_registers(intake: Mapping[str, Any]) -> tuple[int, ...]:
    arm = _object(intake.get("arm_start_evidence"), "arm start evidence")
    if (
        arm.get("classification")
        != "OBSERVED_CONTROLLER_REGISTERS_NOT_MODEL_JOINT_RADIANS"
    ):
        raise ValueError("arm start evidence must remain controller-register evidence")
    if arm.get("named_pose") != "KEYBOARD_FORWARD_CAL_1":
        raise ValueError("current start sensitivity requires KEYBOARD_FORWARD_CAL_1")
    if (
        arm.get("motion_active") is not False
        or arm.get("trajectory_progress_permille") != 1000
    ):
        raise ValueError("retained start must be a completed idle pose")
    if arm.get("freshness") != "RETAINED_NOT_SYNCHRONIZED_TO_CURRENT_CAMERA_FRAME":
        raise ValueError("retained start freshness must remain explicit")
    if arm.get("current_camera_synchronized") is not False:
        raise ValueError("retained start cannot claim camera synchronization")
    raw = arm.get("servo_register_positions")
    if (
        not isinstance(raw, list)
        or len(raw) != len(_SERVO_IDS)
        or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= 4095
            for value in raw
        )
    ):
        raise ValueError("seven bounded servo registers are required")
    return tuple(raw)


def _reference_projection(registers: tuple[int, ...]) -> dict[str, Any]:
    by_servo = dict(zip(_SERVO_IDS, registers))
    reference_angles: dict[str, float] = {}
    for mapping in JOINT_MAP:
        driving_register = by_servo[mapping.servo_ids[0]]
        reference_angles[mapping.key] = (
            mapping.register_sign
            * (driving_register - mapping.feedback_offset)
            * STEP_RAD
        )
    model_angles = {
        model_name: reference_angles[reference_key]
        for model_name, reference_key in _MODEL_TO_REFERENCE_KEY.items()
    }
    return {
        "classification": "REFERENCE_ONLY_NOT_INSTALLED_CALIBRATION",
        "reference_source_sha256": REFERENCE_SHA256,
        "servo_ids": list(_SERVO_IDS),
        "servo_register_positions": list(registers),
        "arm_joint_positions_rad": model_angles,
        "gripper_reference_rad": reference_angles["g"],
        "shoulder_follower_register": by_servo[13],
        "shoulder_pair_sum_registers": by_servo[12] + by_servo[13],
        "installed_firmware_verified": False,
        "installed_controller_to_model_correlation_verified": False,
    }


def _transition(
    reference: Mapping[str, float], solution: Mapping[str, Any]
) -> dict[str, Any]:
    if set(solution) != set(ARM_JOINT_NAMES):
        raise ValueError("route solution has an unexpected joint set")
    deltas = {
        name: float(solution[name]) - float(reference[name]) for name in ARM_JOINT_NAMES
    }
    return {
        "joint_deltas_rad": deltas,
        "maximum_absolute_joint_delta_rad": max(
            abs(value) for value in deltas.values()
        ),
        "euclidean_joint_delta_rad": math.sqrt(
            sum(value * value for value in deltas.values())
        ),
    }


def run(
    intake: Mapping[str, Any], *, workspace: Path, profile_path: Path
) -> dict[str, Any]:
    """Produce a no-dispatch start-to-route sensitivity comparison."""

    registers = _retained_registers(intake)
    projection = _reference_projection(registers)
    target_report, route = run_with_route_evidence(
        intake, workspace=workspace, profile_path=profile_path
    )
    route_round = _object(route.get("round"), "dense route round")
    results = route_round.get("joint_results")
    if (
        route.get("all_waypoints_accepted") is not True
        or not isinstance(results, list)
        or not results
    ):
        raise ValueError("current H dense route must pass before start comparison")
    accepted = [
        _object(row, "dense route result")
        for row in results
        if _object(row, "dense route result").get("accepted") is True
    ]
    if len(accepted) != len(results):
        raise ValueError("current H dense route contains an unaccepted waypoint")
    reference = _object(projection["arm_joint_positions_rad"], "reference joints")
    comparisons = [
        _transition(
            reference,
            _object(row.get("solution_arm_joint_positions_rad"), "route solution"),
        )
        for row in accepted
    ]
    first = accepted[0]
    first_transition = comparisons[0]
    minimum_index = min(
        range(len(comparisons)),
        key=lambda index: comparisons[index]["maximum_absolute_joint_delta_rad"],
    )
    minimum_row = accepted[minimum_index]
    maximum_joint_step = float(
        _object(route.get("policy"), "route policy")["maximum_joint_step_rad"]
    )
    direct_transition_passed = (
        first_transition["maximum_absolute_joint_delta_rad"] <= maximum_joint_step
    )
    _, seeded_route = run_seeded_model_motion(
        target_report["derived_contact_proposal"],
        workspace=workspace,
        park_xy_board_mm=(290.0, 10.0),
        robot_layout_profile=profile_path,
        initial_arm_joint_positions_rad=dict(reference),
    )
    seeded_round = _object(seeded_route.get("round"), "seeded dense route round")
    seeded_results = seeded_round.get("joint_results")
    if not isinstance(seeded_results, list) or not seeded_results:
        raise ValueError("seeded route did not evaluate its entry waypoint")
    seeded_first = _object(seeded_results[0], "seeded first route result")
    core = {
        "schema": SCHEMA,
        "status": (
            "REFERENCE_START_WITHIN_FIRST_ROUTE_JOINT_STEP"
            if direct_transition_passed
            else "REFERENCE_START_OUTSIDE_FIRST_ROUTE_JOINT_STEP"
        ),
        "scope": "OFFLINE_REFERENCE_REGISTER_TO_PASSING_ROUTE_COMPARISON_ONLY",
        "current_intake_sha256": intake.get("intake_sha256"),
        "current_target_sensitivity_sha256": target_report["report_sha256"],
        "route_status": route["status"],
        "evaluated_waypoint_count": len(results),
        "reference_projection": projection,
        "first_route_waypoint": {
            "sequence": first["waypoint_sequence"],
            "phase": first["phase"],
            "semantic_target": first["semantic_target"],
            "solution_arm_joint_positions_rad": first[
                "solution_arm_joint_positions_rad"
            ],
        },
        "first_route_transition": {
            **first_transition,
            "maximum_joint_step_rad": maximum_joint_step,
            "within_route_joint_step": direct_transition_passed,
        },
        "nearest_route_waypoint_by_maximum_joint_delta": {
            "sequence": minimum_row["waypoint_sequence"],
            "phase": minimum_row["phase"],
            "semantic_target": minimum_row["semantic_target"],
            **comparisons[minimum_index],
        },
        "seeded_entry_route": {
            "status": seeded_route["status"],
            "all_waypoints_accepted": seeded_route["all_waypoints_accepted"],
            "evaluated_waypoint_count": seeded_round["evaluated_waypoint_count"],
            "first_waypoint": {
                "sequence": seeded_first["waypoint_sequence"],
                "phase": seeded_first["phase"],
                "accepted": seeded_first["accepted"],
                "previous_solution_seed_supplied": seeded_first[
                    "previous_solution_seed_supplied"
                ],
                "maximum_joint_delta_rad": seeded_first["maximum_joint_delta_rad"],
                "failure_reason": seeded_first["failure_reason"],
                "solution_arm_joint_positions_rad": seeded_first[
                    "solution_arm_joint_positions_rad"
                ],
            },
        },
        "interpretation": (
            "The retained register pose projects within the route policy's single-step bound of the first accepted route state under the pinned reference conversion."
            if direct_transition_passed
            else "The retained register pose does not project within the route policy's single-step bound of the first accepted route state under the pinned reference conversion. A commissioned controller-to-model calibration and a newly screened entry segment are still required."
        ),
        "limitations": [
            "The register conversion is the pinned vendor reference, not installed calibration",
            "The retained register sample is not synchronized to the current camera frame",
            "The route uses an unmeasured board-to-arm layout and tool hypothesis",
            "The seeded screen checks discrete IK continuity; it does not prove a continuous or collision-free entry segment",
        ],
        "physical_execution_authorized": False,
        "controller_commands": [],
        "transport_writes": 0,
        "hardware_access": False,
    }
    return {**core, "report_sha256": canonical_hash(core)}


__all__ = ["SCHEMA", "run"]
