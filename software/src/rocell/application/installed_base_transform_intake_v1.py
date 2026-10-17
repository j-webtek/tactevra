"""Prepare and validate the installed board-to-robot-base transform intake.

The intake preserves retained board and neutral-pose evidence, but deliberately
does not infer a transform from photographs, a named pose, or simulation
coordinates.  It performs no hardware I/O and grants no physical authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from rocell.calibration.static_phase1_requirements import (
    STATIC_OVERHEAD_PHASE1_GRAPH,
)


SCHEMA = "rocell.installed_base_transform_intake.v1"
STATUS = "BLOCKED_INSTALLED_BASE_TRANSFORM_EVIDENCE_REQUIRED"

_SOURCE_PATHS = (
    "software/config/live_camera_feedback_session_20261015.json",
    "software/ai/eval/physical_installed_apriltag_xy_working_v1.json",
    "software/ai/eval/bare_jaw_route_readiness_20261016.json",
    "software/ai/eval/static_overhead_collision_candidate_envelopes_20261017.json",
    "software/src/rocell/calibration/static_phase1_requirements.py",
    "active-project/RoCell_v0_3/config/robot_reach_screening.json",
    "software/config/virtual_commissioning_profile.json",
    "software/config/simulation_hardware_profile.json",
)


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


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _source_binding(workspace: Path, relative: str) -> dict[str, Any]:
    path = workspace / relative
    payload = path.read_bytes()
    return {
        "path": relative,
        "byte_length": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def build_installed_base_transform_intake_v1(
    workspace: Path,
    *,
    intake_id: str,
    captured_at_utc: str,
) -> dict[str, Any]:
    """Build a deterministic pending physical-evidence intake."""

    if not isinstance(intake_id, str) or not intake_id.strip():
        raise ValueError("intake_id must be non-empty text")
    if not isinstance(captured_at_utc, str) or not captured_at_utc.endswith("Z"):
        raise ValueError("captured_at_utc must be an ISO-8601 UTC timestamp")

    session = _load_json(workspace / _SOURCE_PATHS[0])
    tag_map = _load_json(workspace / _SOURCE_PATHS[1])
    readiness = _load_json(workspace / _SOURCE_PATHS[2])
    candidates = _load_json(workspace / _SOURCE_PATHS[3])
    reach = _load_json(workspace / _SOURCE_PATHS[5])
    virtual = _load_json(workspace / _SOURCE_PATHS[6])
    simulation = _load_json(workspace / _SOURCE_PATHS[7])

    arm = session["arm_baseline"]
    camera = session["camera_baseline"]
    requirement = STATIC_OVERHEAD_PHASE1_GRAPH.requirements["phase1_arm_board"]
    robot_rows = [
        row
        for row in candidates["body_candidates"]
        if row["body_id"].startswith("robot:")
    ]
    virtual_transform = virtual["study_input"]["physical_placement_input"]
    nominal_transform = simulation["robot"]["nominal_board_T_robot_world"]

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "intake_id": intake_id.strip(),
        "captured_at_utc": captured_at_utc,
        "status": STATUS,
        "target_artifact": {
            "artifact_id": requirement.artifact_id,
            "artifact_schema": requirement.artifact_schema,
            "purpose": requirement.purpose,
            "acceptance_evidence": requirement.acceptance_evidence,
            "prerequisites": list(requirement.prerequisites),
            "prerequisite_status": {
                item: "REQUIRED_ACCEPTED_PHYSICAL_ARTIFACT"
                for item in requirement.prerequisites
            },
        },
        "source_bindings": [
            _source_binding(workspace, relative) for relative in _SOURCE_PATHS
        ],
        "retained_context": {
            "workcell_epoch_id": session["workcell_epoch"]["epoch_id"],
            "fixed_items": session["workcell_epoch"]["fixed_items"],
            "board_frame": "B",
            "board_size_xy_mm": tag_map["board"]["size_xy_mm"],
            "board_origin": tag_map["board"]["origin"],
            "board_axes": tag_map["board"]["axes"],
            "installed_tag_geometry": tag_map["installed_tag_geometry"],
            "installed_tag_centers_xy_mm": {
                name: row["working_detection_center_xy_mm"]
                for name, row in tag_map["tags"].items()
            },
            "neutral_observation_pose": camera["neutral_observation_pose"],
            "neutral_observation_servo_positions": camera[
                "neutral_observation_servo_positions"
            ],
            "attachment_profile": arm["attachment_profile"],
            "attachment_profile_id": arm["profile_id"],
            "all_six_fiducials_visible": camera["all_six_fiducials_visible"],
            "detected_tag_ids": camera["detected_tag_ids_across_frames"],
            "board_to_arm_transform_status": readiness["calibration_component_status"][
                "board_to_arm_transform"
            ],
            "robot_local_envelopes": [
                {
                    "body_id": row["body_id"],
                    "frame": row["frame"],
                    "envelope": row["envelope"],
                }
                for row in robot_rows
            ],
        },
        "assumptions_excluded_from_physical_solution": [
            {
                "source": _SOURCE_PATHS[5],
                "classification": reach["status"],
                "value": {
                    "board_frame_base_axis_xy_mm": reach["screening_assumption"][
                        "board_frame_base_axis_xy_mm"
                    ]
                },
            },
            {
                "source": _SOURCE_PATHS[5],
                "classification": "SENSITIVITY_CASE_ONLY",
                "value": {
                    "assumed_base_axis_xy_mm": reach["sensitivity_case"][
                        "assumed_base_axis_xy_mm"
                    ]
                },
            },
            {
                "source": _SOURCE_PATHS[6],
                "classification": virtual["status"],
                "value": {
                    "base_axis_x_board_mm": virtual_transform["base_axis_x_board_mm"],
                    "base_axis_y_board_mm": virtual_transform[
                        "rear_edge_to_base_axis_y_mm"
                    ]
                    + 457.0,
                    "base_link_z_board_mm": virtual_transform["base_link_z_board_mm"],
                    "base_yaw_board_rad": virtual_transform["base_yaw_board_rad"],
                },
            },
            {
                "source": _SOURCE_PATHS[7],
                "classification": nominal_transform["state"],
                "value": {
                    "translation_mm": nominal_transform["translation_mm"],
                    "rotation_row_major": nominal_transform["rotation_row_major"],
                },
            },
        ],
        "measurement_intake": {
            "installed_base_and_clamp": {
                "status": "PENDING",
                "arm_serial_or_unique_id": None,
                "controller_id": None,
                "factory_clamp_revision": None,
                "installation_witness_ids": [],
                "clamp_edge_to_base_axis_offset_xyz_mm": None,
                "conservative_board_frame_envelope": None,
                "geometry_uncertainty_mm": None,
            },
            "board_T_robot_base": {
                "status": "PENDING",
                "to_frame": "B",
                "from_frame": "base_link",
                "translation_mm": None,
                "rotation_matrix_row_major": None,
                "quaternion_xyzw": None,
                "translation_uncertainty_mm": None,
                "rotation_uncertainty_deg": None,
            },
            "correspondences": [],
            "observability": {
                "status": "PENDING",
                "correspondence_count": 0,
                "position_diversity_count": 0,
                "orientation_diversity_count": 0,
                "design_matrix_rank": None,
                "condition_number": None,
            },
            "held_out_validation": {
                "status": "PENDING",
                "sample_count": 0,
                "maximum_position_residual_mm": None,
                "rms_position_residual_mm": None,
                "maximum_orientation_residual_deg": None,
                "rms_orientation_residual_deg": None,
            },
            "reseat_repeatability": {
                "status": "PENDING",
                "trial_count": 0,
                "maximum_translation_delta_mm": None,
                "maximum_rotation_delta_deg": None,
            },
            "source_ids": [],
        },
        "completion_rules": {
            "minimum_correspondence_count": 6,
            "minimum_position_diversity_count": 3,
            "minimum_orientation_diversity_count": 2,
            "required_design_matrix_rank": 6,
            "minimum_held_out_sample_count": 2,
            "minimum_reseat_trial_count": 2,
            "all_prerequisites_must_be_accepted": True,
            "accepted_thresholds_must_be_declared_by_reviewed_policy": True,
            "attachment_change_invalidates_trajectory": True,
            "stylus_requires_separate_profile": True,
        },
        "next_action": (
            "ACCEPT_PREREQUISITES_THEN_CAPTURE_DIVERSE_ROBOT_TO_BOARD_"
            "CORRESPONDENCES_AND_SOLVE_HELD_OUT_TRANSFORM"
        ),
        "profile_generated": False,
        "collision_screening_executed": False,
        "controller_commands": [],
        "hardware_access": False,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "content_sha256": _sha(core)}


def validate_completed_installed_base_transform_intake_v1(
    document: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed unless the intake contains a finite, observable solution."""

    errors: list[str] = []
    if document.get("schema") != SCHEMA:
        errors.append("unsupported schema")
    expected_hash = document.get("content_sha256")
    unsigned = {
        key: value for key, value in document.items() if key != "content_sha256"
    }
    if expected_hash != _sha(unsigned):
        errors.append("content hash mismatch")

    target = document.get("target_artifact", {})
    prerequisite_status = target.get("prerequisite_status", {})
    for prerequisite in target.get("prerequisites", []):
        if prerequisite_status.get(prerequisite) != "ACCEPTED_PHYSICAL_ARTIFACT":
            errors.append(f"prerequisite {prerequisite} is not accepted")

    intake = document.get("measurement_intake", {})
    transform = intake.get("board_T_robot_base", {})
    rules = document.get("completion_rules", {})
    base = intake.get("installed_base_and_clamp", {})
    for name in (
        "arm_serial_or_unique_id",
        "controller_id",
        "factory_clamp_revision",
        "clamp_edge_to_base_axis_offset_xyz_mm",
        "conservative_board_frame_envelope",
        "geometry_uncertainty_mm",
    ):
        if base.get(name) in (None, "", []):
            errors.append(f"installed_base_and_clamp.{name} is required")

    for name, length in (
        ("translation_mm", 3),
        ("rotation_matrix_row_major", 9),
        ("quaternion_xyzw", 4),
    ):
        values = transform.get(name)
        if (
            not isinstance(values, list)
            or len(values) != length
            or not all(
                isinstance(value, (int, float)) and math.isfinite(value)
                for value in values
            )
        ):
            errors.append(
                f"board_T_robot_base.{name} must contain {length} finite values"
            )
    rotation = transform.get("rotation_matrix_row_major")
    if (
        isinstance(rotation, list)
        and len(rotation) == 9
        and all(
            isinstance(value, (int, float)) and math.isfinite(value)
            for value in rotation
        )
    ):
        rows = (rotation[0:3], rotation[3:6], rotation[6:9])
        products = [
            sum(rows[i][k] * rows[j][k] for k in range(3))
            for i in range(3)
            for j in range(i, 3)
        ]
        expected = [1.0, 0.0, 0.0, 1.0, 0.0, 1.0]
        if any(
            abs(actual - wanted) > 1e-6 for actual, wanted in zip(products, expected)
        ):
            errors.append(
                "board_T_robot_base.rotation_matrix_row_major is not orthonormal"
            )
    for name in ("translation_uncertainty_mm", "rotation_uncertainty_deg"):
        value = transform.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            errors.append(f"board_T_robot_base.{name} must be finite and nonnegative")

    correspondences = intake.get("correspondences", [])
    if len(correspondences) < rules.get("minimum_correspondence_count", 6):
        errors.append("insufficient correspondences")
    observability = intake.get("observability", {})
    for name, rule_name in (
        ("position_diversity_count", "minimum_position_diversity_count"),
        ("orientation_diversity_count", "minimum_orientation_diversity_count"),
        ("design_matrix_rank", "required_design_matrix_rank"),
    ):
        value = observability.get(name)
        if not isinstance(value, int) or value < rules.get(rule_name, 0):
            errors.append(f"observability.{name} is below the completion rule")
    condition = observability.get("condition_number")
    if (
        not isinstance(condition, (int, float))
        or not math.isfinite(condition)
        or condition <= 0
    ):
        errors.append("observability.condition_number must be finite and positive")

    held_out = intake.get("held_out_validation", {})
    if held_out.get("sample_count", 0) < rules.get("minimum_held_out_sample_count", 2):
        errors.append("insufficient held-out samples")
    for name in (
        "maximum_position_residual_mm",
        "rms_position_residual_mm",
        "maximum_orientation_residual_deg",
        "rms_orientation_residual_deg",
    ):
        value = held_out.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            errors.append(f"held_out_validation.{name} must be finite and nonnegative")
    reseat = intake.get("reseat_repeatability", {})
    if reseat.get("trial_count", 0) < rules.get("minimum_reseat_trial_count", 2):
        errors.append("insufficient reseat trials")
    for name in ("maximum_translation_delta_mm", "maximum_rotation_delta_deg"):
        value = reseat.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            errors.append(f"reseat_repeatability.{name} must be finite and nonnegative")
    if not intake.get("source_ids"):
        errors.append("measurement source_ids are required")

    complete = not errors
    return {
        "schema": "rocell.installed_base_transform_validation.v1",
        "status": "COMPLETE_ZERO_AUTHORITY" if complete else STATUS,
        "complete": complete,
        "errors": errors,
        "controller_commands": [],
        "hardware_access": False,
        "physical_movements": 0,
        "physical_authority": False,
    }


__all__ = [
    "SCHEMA",
    "STATUS",
    "build_installed_base_transform_intake_v1",
    "validate_completed_installed_base_transform_intake_v1",
]
