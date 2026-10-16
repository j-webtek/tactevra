"""Prepare physical static-intrinsics intake from retained evidence.

The planner binds the exact installed runtime mode and identifies missing
physical evidence.  It never opens a camera, accepts synthetic rehearsal
values as physical calibration, writes the registry, or grants motion.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .static_phase1_retained_evidence import (
    assess_static_phase1_retained_evidence,
)


SCHEMA = "rocell.static_phase1_intrinsics_intake_plan.v1"
STATUS = "BLOCKED_PHYSICAL_INTRINSICS_INPUTS_REQUIRED"

_SESSION = Path("software/config/live_camera_feedback_session_20261015.json")
_COVERAGE = Path(
    "software/ai/eval/static_phase1_retained_evidence_coverage_20261016.json"
)
_PROFILE = Path("software/config/camera_profiles/arducam_b0477_imx283_16mm.json")
_REHEARSAL = Path(
    "software/tests/fixtures/camera/b0477_synthetic_intrinsics_rehearsal.json"
)
_LOCKED_CONTROLS = Path(
    "software/ai/eval/b0477_locked_controls_qualification_20261016.json"
)


class StaticPhase1IntrinsicsIntakeError(ValueError):
    """Retained inputs are missing, stale, malformed, or inconsistent."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StaticPhase1IntrinsicsIntakeError(
            "intrinsics intake input cannot be canonicalized"
        ) from exc


def _without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StaticPhase1IntrinsicsIntakeError(
                f"duplicate JSON field {key!r}"
            )
        result[key] = value
    return result


def _read(path: Path) -> Mapping[str, Any]:
    try:
        payload = path.read_bytes()
        value = json.loads(
            payload,
            object_pairs_hook=_without_duplicates,
            parse_constant=lambda item: (_ for _ in ()).throw(
                StaticPhase1IntrinsicsIntakeError(
                    f"nonfinite JSON constant {item!r}"
                )
            ),
        )
    except OSError as exc:
        raise StaticPhase1IntrinsicsIntakeError(
            f"intrinsics intake source is unavailable: {path}"
        ) from exc
    if not isinstance(value, Mapping):
        raise StaticPhase1IntrinsicsIntakeError(f"{path} must contain an object")
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StaticPhase1IntrinsicsIntakeError(f"{label} must be an object")
    return value


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise StaticPhase1IntrinsicsIntakeError(f"{label} must be an array")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StaticPhase1IntrinsicsIntakeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise StaticPhase1IntrinsicsIntakeError(f"{label} must be finite")
    return result


def plan_static_phase1_intrinsics_intake(workspace: Path) -> dict[str, Any]:
    """Return the next physical-intrinsics intake plan without device access."""

    root = Path(workspace)
    session_path = root / _SESSION
    coverage_path = root / _COVERAGE
    profile_path = root / _PROFILE
    rehearsal_path = root / _REHEARSAL
    locked_controls_path = root / _LOCKED_CONTROLS
    session = _read(session_path)
    coverage = _read(coverage_path)
    profile = _read(profile_path)
    rehearsal = _read(rehearsal_path)
    locked_controls = _read(locked_controls_path)
    if (
        locked_controls.get("schema")
        != "rocell.b0477_locked_controls_qualification.v1"
        or locked_controls.get("status")
        != "LOCKED_ELECTRONIC_CONTROLS_REOPEN_QUALIFIED_PHYSICAL_INTRINSICS_BLOCKED"
    ):
        raise StaticPhase1IntrinsicsIntakeError(
            "locked electronic controls are not qualified"
        )

    recomputed = assess_static_phase1_retained_evidence(root)
    if coverage != recomputed:
        raise StaticPhase1IntrinsicsIntakeError(
            "retained Phase-1 evidence coverage is stale"
        )

    rows = _array(coverage.get("coverage"), "coverage rows")
    by_id = {
        row.get("artifact_id"): row
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("artifact_id"), str)
    }
    intrinsics = _mapping(
        by_id.get("phase1_static_intrinsics"), "intrinsics coverage"
    )
    if intrinsics.get("coverage_status") != "NO_RETAINED_CANDIDATE":
        raise StaticPhase1IntrinsicsIntakeError(
            "physical intrinsics must remain without a retained candidate"
        )
    prerequisite_ids = (
        "phase1_b0477_identity",
        "phase1_b0477_mode",
        "phase1_b0477_settings",
    )
    prerequisite_status = {
        item: _mapping(by_id.get(item), f"{item} coverage").get("coverage_status")
        for item in prerequisite_ids
    }

    camera = _mapping(session.get("camera_baseline"), "camera baseline")
    identity = _mapping(camera.get("physical_identity"), "camera identity")
    selector = _mapping(camera.get("capture_selector"), "capture selector")
    mode = _mapping(camera.get("negotiated_mode"), "negotiated mode")
    width = mode.get("width_px")
    height = mode.get("height_px")
    fps = _finite(mode.get("fps"), "negotiated fps")
    fourcc = mode.get("fourcc")
    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
        or width <= 0
        or height <= 0
        or fps <= 0
        or not isinstance(fourcc, str)
        or not fourcc
    ):
        raise StaticPhase1IntrinsicsIntakeError(
            "retained negotiated mode is incomplete"
        )

    published_modes = _array(
        profile.get("published_native_modes"), "published native modes"
    )
    mode_supported = any(
        isinstance(row, Mapping)
        and row.get("width_px") == width
        and row.get("height_px") == height
        and row.get("pixel_format") == fourcc
        and _finite(row.get("maximum_fps"), "published maximum fps") + 0.01 >= fps
        for row in published_modes
    )
    if not mode_supported:
        raise StaticPhase1IntrinsicsIntakeError(
            "retained negotiated mode is absent from the purchased profile"
        )

    rehearsal_camera = _mapping(rehearsal.get("camera_binding"), "rehearsal camera")
    rehearsal_mode = _mapping(rehearsal_camera.get("mode"), "rehearsal mode")
    runtime_mode = {
        "width_px": width,
        "height_px": height,
        "fps": fps,
        "pixel_format": fourcc,
    }
    synthetic_mode = {
        "width_px": rehearsal_mode.get("width_px"),
        "height_px": rehearsal_mode.get("height_px"),
        "fps": rehearsal_mode.get("fps"),
        "pixel_format": rehearsal_mode.get("pixel_format"),
    }
    if runtime_mode == synthetic_mode:
        raise StaticPhase1IntrinsicsIntakeError(
            "expected retained runtime to remain distinct from synthetic rehearsal"
        )

    session_evidence = dict(session)
    session_evidence.pop("route_readiness_audit_20261016", None)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "target_artifact_id": "phase1_static_intrinsics",
        "workcell_epoch_id": _mapping(
            session.get("workcell_epoch"), "workcell epoch"
        ).get("epoch_id"),
        "source_bindings": {
            "live_session": {
                "path": _SESSION.as_posix(),
                "sha256": hashlib.sha256(_canonical(session_evidence)).hexdigest(),
                "hash_scope": (
                    "canonical document excluding derived "
                    "route_readiness_audit_20261016"
                ),
            },
            "retained_coverage": {
                "path": _COVERAGE.as_posix(),
                "artifact_sha256": _sha256(coverage_path),
                "coverage_sha256": coverage.get("coverage_sha256"),
            },
            "purchased_profile": {
                "path": _PROFILE.as_posix(),
                "sha256": _sha256(profile_path),
            },
            "synthetic_rehearsal": {
                "path": _REHEARSAL.as_posix(),
                "sha256": _sha256(rehearsal_path),
            },
            "locked_electronic_controls": {
                "path": _LOCKED_CONTROLS.as_posix(),
                "artifact_sha256": _sha256(locked_controls_path),
                "qualification_sha256": locked_controls.get(
                    "qualification_sha256"
                ),
            },
        },
        "retained_runtime_binding": {
            "friendly_name": identity.get("friendly_name"),
            "vid": identity.get("vid"),
            "pid": identity.get("pid"),
            "backend": selector.get("backend"),
            "selector": selector.get("selector"),
            "mode": runtime_mode,
            "settings_sha256": mode.get("settings_sha256"),
            "stable_after_two_open_cycles": mode.get(
                "stable_after_two_open_cycles"
            ),
        },
        "prerequisites": prerequisite_status,
        "locked_electronic_controls": {
            "status": "REOPEN_QUALIFIED",
            "values": locked_controls.get("locked_electronic_controls"),
            "reopen_qualification": locked_controls.get("reopen_qualification"),
        },
        "legacy_rehearsal_comparison": {
            "synthetic_mode": synthetic_mode,
            "matches_retained_runtime": False,
            "rehearsal_artifact_class": rehearsal.get("artifact_class"),
            "eligible_as_physical_intrinsics": False,
        },
        "required_new_evidence": [
            "mechanical focus and aperture identity with physical lock witness marks",
            "manual-control and selected-mode persistence across physical reconnect and host reboot",
            "scale-verified existing calibration-target identity and metric definition",
            "precommitted fit/held-out image manifest at the retained runtime mode",
            "immutable source-image hashes with regional pose and coverage observations",
            "selected distortion model, camera matrix, and per-view residuals",
            "held-out regional residuals, valid ROI/crop, and undistortion-map hash",
            "warm-up, illumination, disturbance, and drift evidence for the retained stack",
        ],
        "collection_policy": {
            "repeat_board_or_tag_center_measurements": False,
            "new_target_print_requested": False,
            "accept_existing_scale_verified_target": True,
            "capture_mode_must_equal_retained_runtime": True,
            "split_must_be_committed_before_solution_review": True,
            "synthetic_rehearsal_may_fill_physical_fields": False,
        },
        "next_action": (
            "COMPLETE_EXISTING_TARGET_IDENTITY_AND_PRECOMMIT_"
            "MULTIVIEW_INTRINSICS_DATASET"
        ),
        "capture_ready": False,
        "authority": {
            "camera_opened": False,
            "camera_frames_requested": 0,
            "physical_artifacts_created": 0,
            "physical_registry_written": False,
            "robot_transport_opened": False,
            "robot_commands_sent": 0,
            "physical_authority": False,
        },
    }
    return {
        **report,
        "plan_sha256": hashlib.sha256(_canonical(report)).hexdigest(),
    }


__all__ = [
    "SCHEMA",
    "STATUS",
    "StaticPhase1IntrinsicsIntakeError",
    "plan_static_phase1_intrinsics_intake",
]
