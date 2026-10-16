"""Map retained workcell evidence onto the static Phase-1 calibration graph.

This audit is deliberately non-promotional.  It identifies measurements and
observations that can be reused during commissioning, but it never creates a
``CalibrationArtifact`` or writes the physical registry.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.calibration import STATIC_OVERHEAD_PHASE1_GRAPH


SCHEMA = "rocell.static_phase1_retained_evidence_coverage.v1"
STATUS = "RETAINED_EVIDENCE_MAPPED_PHYSICAL_CALIBRATION_BLOCKED"

_SESSION = Path("software/config/live_camera_feedback_session_20261015.json")
_TAG_XY = Path("software/ai/eval/physical_installed_apriltag_xy_working_v1.json")
_REGISTRATION = Path("software/ai/eval/b0477_fixed_board_registration_20261016.json")
_OVERLAY = Path("software/ai/eval/b0477_keyboard_overlay_20261016.json")
_TOOL_PROFILES = Path("software/config/tool_attachment_profiles.json")


class StaticPhase1RetainedEvidenceError(ValueError):
    """Retained evidence is missing, stale, or internally inconsistent."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StaticPhase1RetainedEvidenceError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _read(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_without_duplicates,
            parse_constant=lambda item: (_ for _ in ()).throw(
                StaticPhase1RetainedEvidenceError(
                    f"nonfinite JSON constant {item!r}"
                )
            ),
        )
    except OSError as exc:
        raise StaticPhase1RetainedEvidenceError(
            f"retained evidence is unavailable: {path}"
        ) from exc
    if not isinstance(value, Mapping):
        raise StaticPhase1RetainedEvidenceError(f"{path} must contain an object")
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StaticPhase1RetainedEvidenceError(f"{label} must be an object")
    return value


def _array(value: object, label: str, length: int | None = None) -> list[Any]:
    if not isinstance(value, list) or (length is not None and len(value) != length):
        suffix = "an array" if length is None else f"a {length}-item array"
        raise StaticPhase1RetainedEvidenceError(f"{label} must be {suffix}")
    return value


def _coverage_row(
    artifact_id: str,
    *,
    status: str,
    source_ids: tuple[str, ...],
    retained_facts: Mapping[str, Any],
    remaining_evidence: tuple[str, ...],
    non_substitutions: tuple[str, ...] = (),
) -> dict[str, Any]:
    if status not in {"RETAINED_CANDIDATE_PARTIAL", "NO_RETAINED_CANDIDATE"}:
        raise StaticPhase1RetainedEvidenceError(
            f"unsupported retained coverage status {status!r}"
        )
    requirement = STATIC_OVERHEAD_PHASE1_GRAPH.requirements[artifact_id]
    if not remaining_evidence:
        raise StaticPhase1RetainedEvidenceError(
            f"{artifact_id} cannot be presented as physically complete"
        )
    return {
        "artifact_id": artifact_id,
        "artifact_schema": requirement.artifact_schema,
        "prerequisites": list(requirement.prerequisites),
        "coverage_status": status,
        "retained_source_ids": list(source_ids),
        "retained_facts": dict(retained_facts),
        "remaining_acceptance_evidence": list(remaining_evidence),
        "non_substitutions": list(non_substitutions),
        "physical_artifact_created": False,
        "physical_registry_written": False,
    }


def assess_static_phase1_retained_evidence(workspace: Path) -> dict[str, Any]:
    """Bind retained records to the keyboard closure without hardware access."""

    root = Path(workspace)
    paths = {
        "live_session": root / _SESSION,
        "installed_tag_xy": root / _TAG_XY,
        "fixed_board_registration": root / _REGISTRATION,
        "keyboard_overlay": root / _OVERLAY,
        "tool_profiles": root / _TOOL_PROFILES,
    }
    documents = {key: _read(path) for key, path in paths.items()}
    source_bindings = {
        key: {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256(path),
        }
        for key, path in paths.items()
    }

    session = documents["live_session"]
    session_evidence = dict(session)
    session_evidence.pop("route_readiness_audit_20261016", None)
    source_bindings["live_session"] = {
        "path": _SESSION.as_posix(),
        "sha256": hashlib.sha256(_canonical(session_evidence)).hexdigest(),
        "hash_scope": "canonical document excluding derived route_readiness_audit_20261016",
    }
    tags = documents["installed_tag_xy"]
    registration = documents["fixed_board_registration"]
    overlay = documents["keyboard_overlay"]
    profiles = documents["tool_profiles"]
    camera = _mapping(session.get("camera_baseline"), "camera baseline")
    arm = _mapping(session.get("arm_baseline"), "arm baseline")
    stationary = _mapping(
        session.get("stationary_observation_20261016"), "stationary observation"
    )
    feedback = _mapping(stationary.get("active_feedback"), "active feedback")
    decoded = _mapping(feedback.get("feedback"), "decoded feedback")
    tag_measurement = _mapping(tags.get("measurement"), "tag measurement")
    tag_qualification = _mapping(tags.get("qualification"), "tag qualification")
    registration_inputs = _mapping(registration.get("inputs"), "registration inputs")
    registration_validation = _mapping(
        registration.get("validation"), "registration validation"
    )
    overlay_geometry = _mapping(overlay.get("keyboard_geometry"), "overlay geometry")
    overlay_uncertainty = _mapping(
        overlay.get("uncertainty_review"), "overlay uncertainty review"
    )

    fixed = _mapping(camera.get("fixed_board_planar_registration"), "fixed mapping")
    keyboard = _mapping(camera.get("keyboard_overlay"), "keyboard overlay")
    if fixed.get("artifact_sha256") != source_bindings["fixed_board_registration"][
        "sha256"
    ]:
        raise StaticPhase1RetainedEvidenceError(
            "session fixed-board registration binding is stale"
        )
    if keyboard.get("artifact_sha256") != source_bindings["keyboard_overlay"][
        "sha256"
    ]:
        raise StaticPhase1RetainedEvidenceError(
            "session keyboard-overlay binding is stale"
        )
    if registration_inputs.get("xy_observations_sha256") != source_bindings[
        "installed_tag_xy"
    ]["sha256"]:
        raise StaticPhase1RetainedEvidenceError(
            "registration installed-tag binding is stale"
        )
    if camera.get("architecture_candidate") != "STATIC_EXTERNAL_CAMERA":
        raise StaticPhase1RetainedEvidenceError(
            "retained session is not the fixed external-camera architecture"
        )

    tag_rows = _mapping(tags.get("tags"), "installed tags")
    if len(tag_rows) != 6 or camera.get("missing_required_tag_ids") != []:
        raise StaticPhase1RetainedEvidenceError(
            "retained coverage requires all six installed tags"
        )
    tag_centers = {
        name: _array(
            _mapping(row, f"tag {name}").get("working_detection_center_xy_mm"),
            f"tag {name} center",
            2,
        )
        for name, row in tag_rows.items()
    }
    if tag_centers != registration_inputs.get("tag_centers_xy_mm"):
        raise StaticPhase1RetainedEvidenceError(
            "installed tag centers differ from the retained registration"
        )

    mode = _mapping(camera.get("negotiated_mode"), "camera negotiated mode")
    identity = _mapping(camera.get("physical_identity"), "camera physical identity")
    profile_rows = _array(profiles.get("profiles"), "tool profiles")
    active_profile = next(
        (
            row
            for row in profile_rows
            if isinstance(row, Mapping)
            and row.get("profile_id") == arm.get("profile_id")
        ),
        None,
    )
    if active_profile is None or active_profile.get("attachment_profile") != "BARE_JAW":
        raise StaticPhase1RetainedEvidenceError(
            "retained bare-jaw attachment profile is unavailable"
        )

    common_camera_sources = ("live_session", "fixed_board_registration")
    rows = [
        _coverage_row(
            "phase1_b0477_identity",
            status="RETAINED_CANDIDATE_PARTIAL",
            source_ids=common_camera_sources,
            retained_facts={
                "friendly_name": identity.get("friendly_name"),
                "vid": identity.get("vid"),
                "pid": identity.get("pid"),
                "pnp_status": identity.get("windows_pnp_status"),
                "persistent_device_identity": camera.get(
                    "persistent_device_identity"
                ),
            },
            remaining_evidence=(
                "received camera, sensor, lens, enclosure, and cable label/serial originals",
                "persistent identity trials across reconnect and reboot",
            ),
        ),
        _coverage_row(
            "phase1_b0477_mode",
            status="RETAINED_CANDIDATE_PARTIAL",
            source_ids=common_camera_sources,
            retained_facts={
                "backend": _mapping(camera.get("capture_selector"), "capture selector").get(
                    "backend"
                ),
                "width_px": mode.get("width_px"),
                "height_px": mode.get("height_px"),
                "fps": mode.get("fps"),
                "fourcc": mode.get("fourcc"),
                "stable_after_two_open_cycles": mode.get(
                    "stable_after_two_open_cycles"
                ),
            },
            remaining_evidence=(
                "bounded native-mode inventory for the retained unit",
                "selected-mode persistence across reconnect and reboot",
            ),
        ),
        _coverage_row(
            "phase1_b0477_settings",
            status="RETAINED_CANDIDATE_PARTIAL",
            source_ids=common_camera_sources,
            retained_facts={
                "settings_sha256": mode.get("settings_sha256"),
                "settings_stable_after_reopen": _mapping(
                    camera.get("repeat_capture_receipt"), "repeat capture receipt"
                ).get("settings_stable_after_reopen"),
                "locked_controls": camera.get("locked_controls"),
            },
            remaining_evidence=(
                "explicit locked focus, aperture, exposure, gain, white-balance, and auto-control values",
                "installed optical-stack identity and physical lock witness marks",
                "warm-up, illumination, disturbance, and drift checks",
            ),
            non_substitutions=(
                "the retained settings hash does not reveal or prove locked control values",
            ),
        ),
        _coverage_row(
            "phase1_static_intrinsics",
            status="NO_RETAINED_CANDIDATE",
            source_ids=("live_session", "fixed_board_registration"),
            retained_facts={
                "intrinsics_artifact_sha256": camera.get(
                    "intrinsics_artifact_sha256"
                ),
                "planar_fit_rmse_px": registration_validation.get(
                    "world_corner_fit_rmse_px"
                ),
            },
            remaining_evidence=(
                "scale-verified calibration images from the retained optical stack",
                "camera matrix, distortion model, fit/held-out residuals, ROI, and map hash",
            ),
            non_substitutions=(
                "the fixed-plane homography is not a camera-intrinsics calibration",
            ),
        ),
        _coverage_row(
            "phase1_measured_tag_map",
            status="RETAINED_CANDIDATE_PARTIAL",
            source_ids=("installed_tag_xy", "fixed_board_registration"),
            retained_facts={
                "board_size_xy_mm": registration_inputs.get("board_size_xy_mm"),
                "tag_detection_edge_mm": registration_inputs.get(
                    "tag_detection_edge_mm"
                ),
                "tag_centers_xy_mm": tag_centers,
                "measurement_method": tag_measurement.get("method"),
                "eligible_for_fixed_epoch_planar_mapping": tag_qualification.get(
                    "eligible_for_fixed_epoch_planar_mapping"
                ),
            },
            remaining_evidence=(
                "measured tag corners, optical-plane Z, and installed yaw",
                "measurement uncertainty and bound measurement-tool identity",
                "held-out survey residuals",
            ),
        ),
        _coverage_row(
            "phase1_static_extrinsic",
            status="RETAINED_CANDIDATE_PARTIAL",
            source_ids=("fixed_board_registration", "installed_tag_xy"),
            retained_facts={
                "mapping_status": registration.get("status"),
                "held_out_station_center_max_error_mm": registration_validation.get(
                    "held_out_station_center_max_error_mm"
                ),
                "maximum_repeatability_deviation_mm": registration_validation.get(
                    "maximum_mapped_center_repeatability_deviation_mm"
                ),
            },
            remaining_evidence=(
                "qualified intrinsics and measured three-dimensional tag map",
                "rigid camera-to-board transform with covariance",
                "reseating, warm-up, load, and time-drift trials",
            ),
            non_substitutions=(
                "the retained planar mapping does not determine a rigid 3D extrinsic",
            ),
        ),
        _coverage_row(
            "phase1_robot_reference",
            status="RETAINED_CANDIDATE_PARTIAL",
            source_ids=("live_session",),
            retained_facts={
                "named_pose": decoded.get("pose"),
                "servo_register_positions": decoded.get("p"),
                "motion_active": decoded.get("motion_active"),
                "trajectory_progress_permille": decoded.get(
                    "trajectory_progress_permille"
                ),
                "firmware_candidate": _mapping(
                    arm.get("installed_firmware"), "installed firmware"
                ).get("candidate"),
            },
            remaining_evidence=(
                "installed arm, servo, controller, and firmware identity records",
                "joint order, sign, zero, range, and repeatable reference procedure",
                "repeated bounded references with uncertainty",
            ),
            non_substitutions=(
                "one settled controller-register sample is not calibrated joint radians",
            ),
        ),
        _coverage_row(
            "phase1_controller_correlation",
            status="RETAINED_CANDIDATE_PARTIAL",
            source_ids=("live_session",),
            retained_facts={
                "retained_path": _mapping(
                    arm.get("latest_motion_observation"), "latest motion observation"
                ).get("path"),
                "retained_command_ids": _mapping(
                    arm.get("latest_motion_observation"), "latest motion observation"
                ).get("commands"),
                "feedback_response_sha256": feedback.get("response_sha256"),
                "one_shot_feedback": feedback.get("second_request_sent") is False,
            },
            remaining_evidence=(
                "configuration-diverse command and achieved-feedback trials",
                "controller/model frame, unit, settling, overshoot, and latency correlation",
                "residual model plus reset and reconnect behavior",
            ),
        ),
        _coverage_row(
            "phase1_arm_board",
            status="NO_RETAINED_CANDIDATE",
            source_ids=("live_session", "installed_tag_xy"),
            retained_facts={
                "fixed_epoch_id": _mapping(
                    session.get("workcell_epoch"), "workcell epoch"
                ).get("epoch_id"),
                "board_size_xy_mm": registration_inputs.get("board_size_xy_mm"),
                "settled_named_pose": decoded.get("pose"),
            },
            remaining_evidence=(
                "diverse measured robot-to-board correspondences",
                "observable robot-base-to-board transform with held-out residuals",
                "installed base/clamp identity and reseat checks",
            ),
            non_substitutions=(
                "coexisting board measurements and a named arm pose do not solve board-to-arm",
            ),
        ),
        _coverage_row(
            "phase1_keyboard_target_map",
            status="RETAINED_CANDIDATE_PARTIAL",
            source_ids=("keyboard_overlay", "fixed_board_registration"),
            retained_facts={
                "device_model_candidate": overlay_geometry.get("device_model"),
                "housing_dimensions_mm": overlay_geometry.get(
                    "housing_dimensions_mm"
                ),
                "reviewed_target_count": _mapping(
                    overlay_geometry.get("target_fit_summary"), "target fit summary"
                ).get("reviewed_center_count"),
                "maximum_center_to_row_fit_residual_mm": _mapping(
                    overlay_geometry.get("target_fit_summary"), "target fit summary"
                ).get(
                    "maximum_individual_center_to_row_fit_residual_mm"
                ),
                "additive_review_bound_mm": overlay_uncertainty.get(
                    "additive_review_bound_mm"
                ),
            },
            remaining_evidence=(
                "bound keyboard identity and measured board transform",
                "per-key polygons, safe insets, surface Z, normals, and press travel",
                "tool-footprint uncertainty budget and held-out targeting residuals",
            ),
            non_substitutions=(
                "reviewed image centers are not product metrology or a contact map",
            ),
        ),
        _coverage_row(
            "phase1_keyboard_tcp",
            status="RETAINED_CANDIDATE_PARTIAL",
            source_ids=("live_session", "tool_profiles"),
            retained_facts={
                "attachment_profile": active_profile.get("attachment_profile"),
                "profile_id": active_profile.get("profile_id"),
                "rigid_jaw_clearance_mm": arm.get("rigid_jaw_clearance_mm"),
                "rigid_jaw_clearance_uncertainty_mm": arm.get(
                    "rigid_jaw_clearance_uncertainty_mm"
                ),
                "clearance_state": arm.get("clearance_state"),
                "external_ruler_photo_receipts": session.get(
                    "external_ruler_photo_receipts"
                ),
            },
            remaining_evidence=(
                "bare-jaw TCP pivot and contact-point trials",
                "compliance, hover/contact/retract travel, and load limits",
                "repeatability, recovery, telemetry, and collision-cleared route evidence",
            ),
            non_substitutions=(
                "the provisional ruler-photo clearance is not a calibrated TCP",
            ),
        ),
        _coverage_row(
            "phase1_keyboard_outcome_observer",
            status="NO_RETAINED_CANDIDATE",
            source_ids=("keyboard_overlay",),
            retained_facts={
                "mapped_target_count": _mapping(
                    overlay_geometry.get("target_fit_summary"), "target fit summary"
                ).get("reviewed_center_count")
            },
            remaining_evidence=(
                "qualified host application, OS, and keyboard-layout identity",
                "baseline, expected, and observed transitions for every supported key",
                "repeated-key trials, negative controls, and held-out text trials",
            ),
            non_substitutions=(
                "a geometric target map does not observe or verify a host key effect",
            ),
        ),
    ]

    expected = STATIC_OVERHEAD_PHASE1_GRAPH.device_closure("keyboard")
    if tuple(row["artifact_id"] for row in rows) != expected:
        raise StaticPhase1RetainedEvidenceError(
            "retained coverage rows do not match the static keyboard closure"
        )
    route_ids = STATIC_OVERHEAD_PHASE1_GRAPH.ordered_closure(
        ("phase1_keyboard_tcp",)
    )
    by_id = {row["artifact_id"]: row for row in rows}
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "graph_id": STATIC_OVERHEAD_PHASE1_GRAPH.graph_id,
        "graph_sha256": STATIC_OVERHEAD_PHASE1_GRAPH.graph_hash,
        "camera_architecture": "RIGID_STATIC_OVERHEAD_EYE_TO_HAND",
        "workcell_epoch_id": _mapping(
            session.get("workcell_epoch"), "workcell epoch"
        ).get("epoch_id"),
        "source_bindings": source_bindings,
        "route_terminal_artifact_id": "phase1_keyboard_tcp",
        "route_artifact_ids": list(route_ids),
        "full_keyboard_closure_ids": list(expected),
        "coverage": rows,
        "summary": {
            "route_artifact_count": len(route_ids),
            "route_partial_candidate_count": sum(
                by_id[item]["coverage_status"] == "RETAINED_CANDIDATE_PARTIAL"
                for item in route_ids
            ),
            "route_missing_candidate_count": sum(
                by_id[item]["coverage_status"] == "NO_RETAINED_CANDIDATE"
                for item in route_ids
            ),
            "physically_complete_artifact_count": 0,
            "repeated_measurement_requested": False,
        },
        "next_collection_order": [
            "phase1_b0477_identity",
            "phase1_b0477_mode",
            "phase1_b0477_settings",
            "phase1_static_intrinsics",
            "phase1_measured_tag_map",
            "phase1_static_extrinsic",
            "phase1_robot_reference",
            "phase1_controller_correlation",
            "phase1_arm_board",
            "phase1_keyboard_target_map",
            "phase1_keyboard_tcp",
            "phase1_keyboard_outcome_observer",
        ],
        "authority": {
            "physical_artifacts_created": 0,
            "physical_registry_written": False,
            "camera_opened": False,
            "robot_transport_opened": False,
            "robot_commands_sent": 0,
            "physical_authority": False,
        },
    }
    return {
        **report,
        "coverage_sha256": hashlib.sha256(_canonical(report)).hexdigest(),
    }


__all__ = [
    "SCHEMA",
    "STATUS",
    "StaticPhase1RetainedEvidenceError",
    "assess_static_phase1_retained_evidence",
]
