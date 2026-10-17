"""Bind current camera evidence to the bare-jaw route-screening boundary.

This module consumes saved JSON artifacts only.  It proves that one current
planar observation, one unsent hover draft, and the retained bare-jaw readiness
audit describe the same epoch, attachment, and board target.  It deliberately
stops before arm-frame projection, IK, collision screening, or dispatch.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "rocell.current_bare_jaw_route_screening_intake.v1"
STATUS = "BLOCKED_ARM_SPACE_CALIBRATION_REQUIRED"


class CurrentBareJawRouteIntakeError(ValueError):
    """Saved camera and route artifacts do not form one coherent intake."""


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


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CurrentBareJawRouteIntakeError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _read(path: Path) -> Mapping[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_strict_object,
        parse_constant=lambda item: (_ for _ in ()).throw(
            CurrentBareJawRouteIntakeError(f"nonfinite JSON constant {item!r}")
        ),
    )
    if not isinstance(value, Mapping):
        raise CurrentBareJawRouteIntakeError(f"{path} must contain an object")
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CurrentBareJawRouteIntakeError(f"{label} must be an object")
    return value


def _array(value: object, label: str, length: int | None = None) -> list[Any]:
    if not isinstance(value, list) or (length is not None and len(value) != length):
        expected = "an array" if length is None else f"a {length}-item array"
        raise CurrentBareJawRouteIntakeError(f"{label} must be {expected}")
    return value


def _verify_embedded_digest(
    document: Mapping[str, Any], field: str, label: str
) -> str:
    claimed = document.get(field)
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise CurrentBareJawRouteIntakeError(f"{label} digest is missing")
    payload = dict(document)
    del payload[field]
    actual = hashlib.sha256(_canonical(payload)).hexdigest()
    if claimed != actual:
        raise CurrentBareJawRouteIntakeError(f"{label} embedded digest mismatch")
    return claimed


def _finite_pair(value: object, label: str) -> tuple[float, float]:
    row = _array(value, label, 2)
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in row):
        raise CurrentBareJawRouteIntakeError(f"{label} must be numeric")
    result = (float(row[0]), float(row[1]))
    if not all(math.isfinite(item) for item in result):
        raise CurrentBareJawRouteIntakeError(f"{label} must be finite")
    return result


def build_current_bare_jaw_route_intake(
    observation_path: Path,
    hover_draft_path: Path,
    readiness_path: Path,
) -> dict[str, Any]:
    """Produce a hash-bound, zero-dispatch current route-screening intake."""

    observation_path = observation_path.resolve(strict=True)
    hover_draft_path = hover_draft_path.resolve(strict=True)
    readiness_path = readiness_path.resolve(strict=True)
    observation = _read(observation_path)
    draft = _read(hover_draft_path)
    readiness = _read(readiness_path)

    if observation.get("schema") != "rocell.current_planar_keyboard_observation.v1":
        raise CurrentBareJawRouteIntakeError("unsupported current observation schema")
    if observation.get("status") != "CURRENT_PLANAR_KEYBOARD_OBSERVATION_READ_ONLY":
        raise CurrentBareJawRouteIntakeError("current observation is not read-only")
    observation_digest = _verify_embedded_digest(
        observation, "observation_sha256", "current observation"
    )
    if draft.get("schema") != "rocell.current_keyboard_hover_draft.v1":
        raise CurrentBareJawRouteIntakeError("unsupported current hover draft schema")
    if draft.get("status") != "UNSENT_CURRENT_SCENE_HOVER_DRAFT_BLOCKED_FROM_INGRESS":
        raise CurrentBareJawRouteIntakeError("current hover draft is not blocked")
    draft_digest = _verify_embedded_digest(draft, "draft_sha256", "current hover draft")
    if readiness.get("schema") != "rocell.bare_jaw_route_readiness.v1":
        raise CurrentBareJawRouteIntakeError("unsupported route readiness schema")
    readiness_digest = _verify_embedded_digest(
        readiness, "readiness_sha256", "route readiness"
    )

    observation_inputs = _mapping(observation.get("inputs"), "observation inputs")
    draft_bindings = _mapping(draft.get("bindings"), "draft bindings")
    readiness_bindings = _mapping(readiness.get("bindings"), "readiness bindings")
    if draft_bindings.get("current_observation_sha256") != _sha256(observation_path):
        raise CurrentBareJawRouteIntakeError("hover draft observation file binding mismatch")
    epochs = {
        observation.get("workcell_epoch_id"),
        draft_bindings.get("workcell_epoch_id"),
        readiness_bindings.get("workcell_epoch_id"),
    }
    if len(epochs) != 1 or None in epochs:
        raise CurrentBareJawRouteIntakeError("workcell epoch binding mismatch")
    if draft_bindings.get("attachment_profile") != "BARE_JAW":
        raise CurrentBareJawRouteIntakeError("route intake requires BARE_JAW")
    attachment = _mapping(readiness.get("attachment_profiles"), "attachment profiles")
    if attachment.get("active") != "BARE_JAW" or attachment.get(
        "trajectory_invalidated_on_attachment_change"
    ) is not True or attachment.get("pose_inheritance_allowed") is not False:
        raise CurrentBareJawRouteIntakeError("bare-jaw profile separation is not enforced")

    current_frame = _mapping(observation.get("current_frame"), "current frame")
    tag_ids = _array(current_frame.get("detected_tag_ids"), "detected tag ids")
    if sorted(tag_ids) != [0, 1, 2, 3, 4, 5]:
        raise CurrentBareJawRouteIntakeError("current frame must contain all six tags")
    scene = _mapping(observation.get("scene_binding"), "scene binding")
    if scene.get("camera_scene_agrees_with_retained_epoch") is not True:
        raise CurrentBareJawRouteIntakeError("current camera scene does not agree")
    if observation.get("target_count") != 46:
        raise CurrentBareJawRouteIntakeError("current observation must contain 46 targets")

    proposal = _mapping(draft.get("proposal"), "hover proposal")
    target_id = proposal.get("target_id")
    if not isinstance(target_id, str):
        raise CurrentBareJawRouteIntakeError("hover target identity is missing")
    targets = _mapping(observation.get("targets"), "current targets")
    current_target = _mapping(targets.get(target_id), "current selected target")
    image_target = _mapping(draft.get("current_image_target"), "draft image target")
    if image_target.get("target_id") != target_id:
        raise CurrentBareJawRouteIntakeError("draft image target identity mismatch")
    if observation_inputs.get("selected_frame_sha256") != draft_bindings.get(
        "selected_frame_sha256"
    ):
        raise CurrentBareJawRouteIntakeError("selected camera frame binding mismatch")
    if _finite_pair(current_target.get("current_center_px"), "observed center") != _finite_pair(
        image_target.get("center_px"), "draft center"
    ):
        raise CurrentBareJawRouteIntakeError("current target pixel center mismatch")

    proposal_target = _mapping(proposal.get("target_mm"), "proposal target")
    current_board_xy = _finite_pair(
        current_target.get("board_center_xy_mm"), "current board target"
    )
    proposal_board_xy = (float(proposal_target.get("x")), float(proposal_target.get("y")))
    if max(abs(a - b) for a, b in zip(current_board_xy, proposal_board_xy, strict=True)) > 0.001:
        raise CurrentBareJawRouteIntakeError("current and proposed board targets differ")
    waypoints = _array(draft.get("requested_waypoints"), "requested waypoints", 1)
    waypoint = _mapping(waypoints[0], "hover waypoint")
    hover = _mapping(waypoint.get("point_mm"), "hover point")
    if waypoint.get("phase") != "HOVER_DESTINATION" or hover.get("frame") != "board":
        raise CurrentBareJawRouteIntakeError("draft must contain one board-frame hover")

    route_blockers = _array(readiness.get("blockers"), "route blockers")
    blockers = ["CURRENT_ARM_TELEMETRY_BOUND_TO_CAMERA_OBSERVATION_REQUIRED"]
    blockers.extend(str(item) for item in route_blockers)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "scope": "CURRENT_CAMERA_TO_OFFLINE_BARE_JAW_ROUTE_SCREENING_WITHOUT_DISPATCH",
        "bindings": {
            "workcell_epoch_id": next(iter(epochs)),
            "current_observation_artifact_sha256": _sha256(observation_path),
            "current_observation_sha256": observation_digest,
            "current_hover_draft_artifact_sha256": _sha256(hover_draft_path),
            "current_hover_draft_sha256": draft_digest,
            "bare_jaw_readiness_artifact_sha256": _sha256(readiness_path),
            "bare_jaw_readiness_sha256": readiness_digest,
            "selected_frame_sha256": observation_inputs.get("selected_frame_sha256"),
            "attachment_profile": "BARE_JAW",
            "profile_id": draft_bindings.get("profile_id"),
        },
        "current_camera_evidence": {
            "scene_agrees_with_epoch": True,
            "selected_frame_path": observation_inputs.get("selected_frame_path"),
            "image_size_px": current_frame.get("image_size_px"),
            "detected_tag_ids": tag_ids,
            "world_corner_fit_rmse_px": current_frame.get("world_corner_fit_rmse_px"),
            "world_corner_fit_max_px": current_frame.get("world_corner_fit_max_px"),
            "held_out_station_checks": current_frame.get("held_out_station_checks"),
            "maximum_reference_center_shift_mm": scene.get(
                "maximum_reference_center_shift_mm"
            ),
            "reviewed_target_count": observation.get("target_count"),
        },
        "selected_target": {
            "device": proposal.get("device"),
            "target_id": target_id,
            "interaction": proposal.get("interaction"),
            "current_center_px": current_target.get("current_center_px"),
            "current_region_corners_px": current_target.get(
                "current_region_corners_px"
            ),
            "surface_board_mm": dict(proposal_target),
            "hover_board_mm": dict(hover),
        },
        "arm_start_evidence": {
            **dict(_mapping(readiness.get("observed_start"), "observed start")),
            "freshness": "RETAINED_NOT_SYNCHRONIZED_TO_CURRENT_CAMERA_FRAME",
            "current_camera_synchronized": False,
        },
        "screening_progress": {
            "current_scene_bound": True,
            "all_six_tags_observed": True,
            "all_reviewed_keyboard_targets_projected": True,
            "selected_pixel_target_bound_to_board_hover": True,
            "attachment_profile_separated": True,
            "current_arm_telemetry_bound": False,
            "board_target_projected_to_arm_frame": False,
            "ik_executed": False,
            "route_screening_executed": False,
            "collision_screening_executed": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_required_stage": "COMMISSION_ARM_SPACE_CHAIN_THEN_RERUN_OFFLINE_ROUTE_SCREEN",
        "controller_commands": [],
        "transport_writes": 0,
        "hardware_access": False,
        "physical_authority": False,
        "descent_authorized": False,
        "contact_authorized": False,
        "autonomous_retry_authorized": False,
    }
    return {
        **report,
        "intake_sha256": hashlib.sha256(_canonical(report)).hexdigest(),
    }


__all__ = [
    "SCHEMA",
    "STATUS",
    "CurrentBareJawRouteIntakeError",
    "build_current_bare_jaw_route_intake",
]
