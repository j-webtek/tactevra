"""Deterministic zero-dispatch readiness audit for the retained bare-jaw route.

The audit deliberately distinguishes observed register values from calibrated
model joints.  It records which parts of the camera/board/keyboard chain are
already reusable and stops before IK whenever the physical transform chain is
incomplete.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.calibration import STATIC_OVERHEAD_PHASE1_GRAPH

from .collision_readiness import assess_current_collision_readiness
from .context import load_simulation_context
from .static_phase1_calibration import run_static_phase1_calibration_rehearsal
from .static_phase1_retained_evidence import (
    assess_static_phase1_retained_evidence,
)
from .static_phase1_intrinsics_intake import (
    plan_static_phase1_intrinsics_intake,
)


SCHEMA = "rocell.bare_jaw_route_readiness.v1"
STATUS = "BLOCKED_CALIBRATION_COMPONENTS_REQUIRED"
_SESSION = Path("software/config/live_camera_feedback_session_20261015.json")
_REGISTRATION = Path("software/ai/eval/b0477_fixed_board_registration_20261016.json")
_OVERLAY = Path("software/ai/eval/b0477_keyboard_overlay_20261016.json")
_RETAINED_COVERAGE = Path(
    "software/ai/eval/static_phase1_retained_evidence_coverage_20261016.json"
)
_INTRINSICS_INTAKE = Path(
    "software/ai/eval/static_phase1_intrinsics_intake_plan_20261016.json"
)
_TOOL_PROFILES = Path("software/config/tool_attachment_profiles.json")
_SYSTEM_MANIFEST = Path("software/config/system_manifest.json")


class BareJawRouteReadinessError(ValueError):
    """Retained evidence does not form the expected route-screening intake."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BareJawRouteReadinessError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _read(path: Path) -> Mapping[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_without_duplicates,
        parse_constant=lambda item: (_ for _ in ()).throw(
            BareJawRouteReadinessError(f"nonfinite JSON constant {item!r}")
        ),
    )
    if not isinstance(value, Mapping):
        raise BareJawRouteReadinessError(f"{path} must contain an object")
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BareJawRouteReadinessError(f"{label} must be an object")
    return value


def _array(value: object, label: str, length: int | None = None) -> list[Any]:
    if not isinstance(value, list) or (length is not None and len(value) != length):
        suffix = " an array" if length is None else f" a {length}-item array"
        raise BareJawRouteReadinessError(f"{label} must be{suffix}")
    return value


def assess_bare_jaw_route_readiness(workspace: Path) -> dict[str, Any]:
    """Audit the retained physical evidence without opening any device."""

    root = Path(workspace)
    session_path = root / _SESSION
    registration_path = root / _REGISTRATION
    overlay_path = root / _OVERLAY
    coverage_path = root / _RETAINED_COVERAGE
    intrinsics_intake_path = root / _INTRINSICS_INTAKE
    profiles_path = root / _TOOL_PROFILES
    session = _read(session_path)
    registration = _read(registration_path)
    overlay = _read(overlay_path)
    retained_coverage = _read(coverage_path)
    intrinsics_intake = _read(intrinsics_intake_path)
    profiles = _read(profiles_path)

    if session.get("schema") != "rocell.live_camera_feedback_session.v1":
        raise BareJawRouteReadinessError("unexpected retained session schema")
    camera = _mapping(session.get("camera_baseline"), "camera_baseline")
    fixed = _mapping(camera.get("fixed_board_planar_registration"), "fixed registration")
    keyboard = _mapping(camera.get("keyboard_overlay"), "keyboard overlay")
    if fixed.get("artifact_sha256") != _sha256(registration_path):
        raise BareJawRouteReadinessError("fixed board registration hash mismatch")
    if keyboard.get("artifact_sha256") != _sha256(overlay_path):
        raise BareJawRouteReadinessError("keyboard overlay hash mismatch")
    if camera.get("missing_required_tag_ids") != [] or camera.get(
        "all_six_fiducials_visible"
    ) is not True:
        raise BareJawRouteReadinessError("all six retained fiducials are required")

    arm = _mapping(session.get("arm_baseline"), "arm_baseline")
    stationary = _mapping(
        session.get("stationary_observation_20261016"), "stationary observation"
    )
    feedback = _mapping(stationary.get("active_feedback"), "active feedback")
    decoded = _mapping(feedback.get("feedback"), "decoded feedback")
    registers = _array(decoded.get("p"), "feedback positions", 7)
    if decoded.get("pose") != arm.get("last_verified_pose"):
        raise BareJawRouteReadinessError("feedback pose differs from retained arm pose")
    if registers != arm.get("last_measured_servo_positions"):
        raise BareJawRouteReadinessError("feedback registers differ from retained arm pose")
    if decoded.get("motion_active") is not False or decoded.get(
        "trajectory_progress_permille"
    ) != 1000:
        raise BareJawRouteReadinessError("retained arm observation is not settled")
    if feedback.get("second_request_sent") is not False or feedback.get("retry_count") != 0:
        raise BareJawRouteReadinessError("feedback evidence must be the retained one-shot read")

    draft = _mapping(session.get("retained_hover_draft"), "retained hover draft")
    proposal = _mapping(draft.get("proposal"), "retained hover proposal")
    target = _mapping(proposal.get("target_mm"), "retained target")
    waypoints = _array(draft.get("requested_waypoints"), "requested waypoints", 1)
    hover = _mapping(_mapping(waypoints[0], "hover waypoint").get("point_mm"), "hover point")
    if proposal.get("target_id") != "H" or proposal.get("coordinate_frame") != "board":
        raise BareJawRouteReadinessError("audit expects the retained board-frame H target")
    if arm.get("attachment_profile") != "BARE_JAW":
        raise BareJawRouteReadinessError("audit requires the BARE_JAW attachment")

    profile_rows = _array(profiles.get("profiles"), "tool profiles")
    selected = next(
        (
            row for row in profile_rows
            if isinstance(row, Mapping) and row.get("profile_id") == arm.get("profile_id")
        ),
        None,
    )
    if selected is None or selected.get("attachment_profile") != "BARE_JAW":
        raise BareJawRouteReadinessError("active bare-jaw profile is missing")
    switching = _mapping(profiles.get("switching_policy"), "switching policy")
    if switching.get("invalidate_precomputed_trajectory_on_change") is not True \
            or switching.get("allow_pose_inheritance_between_profiles") is not False:
        raise BareJawRouteReadinessError("attachment profile separation is not enforced")

    recomputed_coverage = assess_static_phase1_retained_evidence(root)
    if retained_coverage != recomputed_coverage:
        raise BareJawRouteReadinessError(
            "retained Phase-1 evidence coverage is stale"
        )
    recomputed_intrinsics_intake = plan_static_phase1_intrinsics_intake(root)
    if intrinsics_intake != recomputed_intrinsics_intake:
        raise BareJawRouteReadinessError(
            "static Phase-1 intrinsics intake plan is stale"
        )

    context = load_simulation_context(root, root / _SYSTEM_MANIFEST)
    calibration = run_static_phase1_calibration_rehearsal(context)
    calibration_document = calibration.to_dict()
    collision = assess_current_collision_readiness(context)
    registration_inputs = _mapping(registration.get("inputs"), "registration inputs")
    overlay_geometry = _mapping(overlay.get("keyboard_geometry"), "keyboard geometry")
    validation = _mapping(registration.get("validation"), "registration validation")
    closure_rows = _array(
        calibration_document.get("device_closures"),
        "static Phase-1 device closures",
    )
    keyboard_closure = next(
        (
            _mapping(row, "static Phase-1 device closure")
            for row in closure_rows
            if isinstance(row, Mapping) and row.get("device") == "keyboard"
        ),
        None,
    )
    if keyboard_closure is None:
        raise BareJawRouteReadinessError(
            "static Phase-1 report omits the keyboard closure"
        )
    requirement_rows = _array(
        keyboard_closure.get("ordered_requirements"),
        "static Phase-1 keyboard requirements",
    )
    requirement_by_id: dict[str, Mapping[str, Any]] = {}
    for row in requirement_rows:
        requirement = _mapping(row, "static Phase-1 calibration requirement")
        artifact_id = requirement.get("artifact_id")
        if not isinstance(artifact_id, str) or artifact_id in requirement_by_id:
            raise BareJawRouteReadinessError(
                "static Phase-1 requirement identity is invalid"
            )
        requirement_by_id[artifact_id] = requirement
    required_route_artifacts = STATIC_OVERHEAD_PHASE1_GRAPH.ordered_closure(
        ("phase1_keyboard_tcp",)
    )
    if not set(required_route_artifacts).issubset(requirement_by_id):
        raise BareJawRouteReadinessError(
            "static Phase-1 report omits a route artifact"
        )

    session_camera_architecture = camera.get("architecture_candidate")
    graph = _mapping(calibration_document.get("graph"), "static Phase-1 graph")
    camera_architecture_aligned = (
        session_camera_architecture == "STATIC_EXTERNAL_CAMERA"
        and graph.get("architecture") == "RIGID_STATIC_OVERHEAD_EYE_TO_HAND"
        and graph.get("historical_eye_on_arm_graph_reinterpreted") is False
    )
    blockers = [
        "MEASURED_STATIC_CAMERA_CHAIN_REQUIRED",
        "MEASURED_ROBOT_JOINT_REFERENCE_REQUIRED",
        "MEASURED_CONTROLLER_TO_MODEL_CORRELATION_REQUIRED",
        "MEASURED_BOARD_TO_ARM_TRANSFORM_REQUIRED",
        "QUALIFIED_KEYBOARD_TARGET_MAP_Z_NORMAL_AND_TRAVEL_REQUIRED",
        "MEASURED_BARE_JAW_TCP_REQUIRED",
        "MEASURED_BARE_JAW_COLLISION_GEOMETRY_REQUIRED",
    ]
    if not camera_architecture_aligned:
        raise BareJawRouteReadinessError(
            "retained fixed camera does not match the selected static Phase-1 graph"
        )
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "scope": "OFFLINE_BOARD_TO_ARM_AND_BARE_JAW_ROUTE_READINESS_WITHOUT_DISPATCH",
        "bindings": {
            "workcell_epoch_id": _mapping(
                session.get("workcell_epoch"), "workcell epoch"
            ).get("epoch_id"),
            "session_record_id": session.get("record_id"),
            "fixed_board_registration_sha256": _sha256(registration_path),
            "keyboard_overlay_sha256": _sha256(overlay_path),
            "retained_evidence_coverage_artifact_sha256": _sha256(coverage_path),
            "retained_evidence_coverage_sha256": retained_coverage.get(
                "coverage_sha256"
            ),
            "static_intrinsics_intake_artifact_sha256": _sha256(
                intrinsics_intake_path
            ),
            "static_intrinsics_intake_plan_sha256": intrinsics_intake.get(
                "plan_sha256"
            ),
            "tool_profiles_sha256": _sha256(profiles_path),
            "retained_hover_draft_sha256": draft.get("draft_sha256"),
            "active_feedback_response_sha256": feedback.get("response_sha256"),
            "system_manifest_sha256": context.snapshot.manifest_sha256,
            "build_snapshot_sha256": context.snapshot.snapshot_hash,
            "simulation_bundle_sha256": context.bundle_lock.source_lock_sha256,
        },
        "reusable_measured_geometry": {
            "board_size_xy_mm": registration_inputs.get("board_size_xy_mm"),
            "tag_detection_edge_mm": registration_inputs.get("tag_detection_edge_mm"),
            "tag_centers_xy_mm": registration_inputs.get("tag_centers_xy_mm"),
            "detected_tag_ids": camera.get("detected_tag_ids_across_frames"),
            "held_out_station_center_max_error_mm": validation.get(
                "held_out_station_center_max_error_mm"
            ),
            "keyboard_housing_dimensions_mm": overlay_geometry.get(
                "housing_dimensions_mm"
            ),
            "keyboard_front_left_board_xy_mm": keyboard.get(
                "dimension_constrained_front_left_board_xy_mm"
            ),
            "keyboard_yaw_deg": keyboard.get("dimension_constrained_yaw_deg"),
            "reviewed_target_count": keyboard.get(
                "individually_reviewed_target_center_count"
            ),
            "selected_target": {"id": "H", "surface_board_mm": dict(target)},
            "selected_hover_board_mm": dict(hover),
        },
        "observed_start": {
            "named_pose": decoded.get("pose"),
            "servo_register_positions": registers,
            "motion_active": False,
            "trajectory_progress_permille": 1000,
            "classification": "OBSERVED_CONTROLLER_REGISTERS_NOT_MODEL_JOINT_RADIANS",
        },
        "attachment_profiles": {
            "active": "BARE_JAW",
            "active_profile_id": arm.get("profile_id"),
            "stylus_profile_id": next(
                (
                    row.get("profile_id") for row in profile_rows
                    if isinstance(row, Mapping)
                    and row.get("attachment_profile") == "STYLUS"
                ),
                None,
            ),
            "trajectory_invalidated_on_attachment_change": True,
            "pose_inheritance_allowed": False,
        },
        "calibration_component_status": {
            "camera_to_board_xy": "MEASURED_FIXED_EPOCH_PLANAR_MAPPING",
            "keyboard_targets_in_board_xy": "REVIEWED_IMAGE_DERIVED_WITH_STUDY_BOUND",
            "keyboard_z": "UNQUALIFIED_OFF_PLANE_HEIGHT_ASSUMPTION",
            "robot_joint_reference": "MISSING",
            "controller_to_model_correlation": "MISSING",
            "board_to_arm_transform": "MISSING",
            "keyboard_pose_z_and_normal": "MISSING_QUALIFIED_ARTIFACT",
            "bare_jaw_tcp": "MISSING",
            "bare_jaw_installed_collision_geometry": "MISSING",
        },
        "static_phase1_calibration_intake": {
            "status": calibration_document.get("status"),
            "report_sha256": calibration.report_hash,
            "manifest_id": calibration_document.get("manifest_id"),
            "active_build_id": calibration_document.get("active_build_id"),
            "graph_id": graph.get("graph_id"),
            "graph_sha256": graph.get("graph_hash"),
            "physical_registry": calibration_document.get("physical_registry"),
            "route_terminal_artifact_id": "phase1_keyboard_tcp",
            "route_artifact_ids": list(required_route_artifacts),
            "route_artifacts": {
                artifact_id: requirement_by_id[artifact_id]
                for artifact_id in required_route_artifacts
            },
            "complete_keyboard_requirement_order": [
                requirement.get("artifact_id") for requirement in requirement_rows
            ],
            "contact_completion_artifact_ids": [
                "phase1_keyboard_outcome_observer"
            ],
            "camera_architecture": {
                "retained_live_session": session_camera_architecture,
                "selected_graph": graph.get("architecture"),
                "historical_eye_on_arm_graph_reinterpreted": graph.get(
                    "historical_eye_on_arm_graph_reinterpreted"
                ),
                "aligned": camera_architecture_aligned,
            },
            "physical_release_effect": "NONE",
        },
        "installed_collision_intake": {
            "status": collision.status,
            "report_sha256": collision.report_hash,
            "missing_required_body_ids": list(collision.missing_required_body_ids),
            "unknown_required_body_ids": list(collision.unknown_required_body_ids),
            "diagnostic_ready": collision.geometry_audit.diagnostic_ready,
            "continuous_collision_proven": False,
            "physical_release_effect": "NONE",
        },
        "retained_evidence_coverage": {
            "status": retained_coverage.get("status"),
            "summary": retained_coverage.get("summary"),
            "route_reusable_candidate_ids": [
                row.get("artifact_id")
                for row in _array(retained_coverage.get("coverage"), "coverage rows")
                if isinstance(row, Mapping)
                and row.get("artifact_id") in required_route_artifacts
                and row.get("coverage_status") == "RETAINED_CANDIDATE_PARTIAL"
            ],
            "route_no_candidate_ids": [
                row.get("artifact_id")
                for row in _array(retained_coverage.get("coverage"), "coverage rows")
                if isinstance(row, Mapping)
                and row.get("artifact_id") in required_route_artifacts
                and row.get("coverage_status") == "NO_RETAINED_CANDIDATE"
            ],
            "repeated_measurement_requested": False,
            "physical_release_effect": "NONE",
        },
        "physical_intrinsics_intake": {
            "status": intrinsics_intake.get("status"),
            "target_artifact_id": intrinsics_intake.get("target_artifact_id"),
            "target_reconciliation": intrinsics_intake.get(
                "target_reconciliation"
            ),
            "retained_runtime_binding": intrinsics_intake.get(
                "retained_runtime_binding"
            ),
            "legacy_rehearsal_comparison": intrinsics_intake.get(
                "legacy_rehearsal_comparison"
            ),
            "required_new_evidence": intrinsics_intake.get(
                "required_new_evidence"
            ),
            "collection_policy": intrinsics_intake.get("collection_policy"),
            "next_action": intrinsics_intake.get("next_action"),
            "capture_ready": intrinsics_intake.get("capture_ready"),
            "physical_release_effect": "NONE",
        },
        "prior_sensitivity_evidence": [
            {
                "commit": "c5920d1e7",
                "decision": "BLOCKED_EXACT_HOVER_HAS_NO_MARGIN_ADMISSIBLE_IK",
                "use": "historical nominal endpoint bound only",
            },
            {
                "commit": "05d67cb41",
                "decision": "BLOCKED_NO_BOUNDED_DESCENT_CORRIDOR",
                "use": "historical 110 mm descent bound only",
            },
            {
                "commit": "85f9b5ba4",
                "decision": "BLOCKED_120MM_EXACT_CONTACT",
                "use": "historical 120 mm exact-contact bound only",
            },
            {
                "commit": "6bda616f3",
                "decision": "PASS_IK_CONTINUITY_RETAIN_INSTALLED_COLLISION_BLOCKER",
                "use": "unmeasured 120 mm transform sensitivity overlay only",
            },
        ],
        "screening": {
            "board_target_reused": True,
            "observed_registers_reused": True,
            "register_to_joint_projection_executed": False,
            "ik_executed": False,
            "route_densification_executed": False,
            "collision_screening_executed": False,
            "continuous_collision_proven": False,
            "unreachable_claim_supported_for_installed_workcell": False,
        },
        "blockers": blockers,
        "next_required_stage": "POPULATE_CALIBRATION_SLOTS_THEN_RERUN_OFFLINE_IK_ROUTE_COLLISION_SCREEN",
        "controller_commands": [],
        "transport_writes": 0,
        "hardware_access": False,
        "physical_authority": False,
        "descent_authorized": False,
        "contact_authorized": False,
    }
    return {
        **report,
        "readiness_sha256": hashlib.sha256(_canonical(report)).hexdigest(),
    }


__all__ = [
    "SCHEMA",
    "STATUS",
    "BareJawRouteReadinessError",
    "assess_bare_jaw_route_readiness",
]
