"""Qualify the physical B0477 electronic controls from external receipts."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "rocell.b0477_locked_controls_qualification.v1"
STATUS = "LOCKED_ELECTRONIC_CONTROLS_REOPEN_QUALIFIED_PHYSICAL_INTRINSICS_BLOCKED"
CAMERA_NAME = "Arducam B0477 (USB3 20MP)"
CAMERA_PNP = "USB\\VID_04B4&PID_0477&MI_00\\8&257B140A&0&0000"
EXPECTED_CONTROLS = {
    "brightness": 0,
    "contrast": 10,
    "saturation": 10,
    "white_balance": 4500,
    "gain": 500,
    "exposure": -3,
}


class B0477LockedControlsQualificationError(ValueError):
    """The source receipts are absent, malformed, or inconsistent."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise B0477LockedControlsQualificationError("source cannot be canonicalized") from exc


def _pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise B0477LockedControlsQualificationError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _read(path: Path) -> Mapping[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda item: (_ for _ in ()).throw(B0477LockedControlsQualificationError(f"nonfinite JSON constant {item!r}")))
    except OSError as exc:
        raise B0477LockedControlsQualificationError(f"source unavailable: {path}") from exc
    if not isinstance(value, Mapping):
        raise B0477LockedControlsQualificationError(f"{path} must contain an object")
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise B0477LockedControlsQualificationError(f"{label} must be an object")
    return value


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise B0477LockedControlsQualificationError(f"{label} must be an array")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise B0477LockedControlsQualificationError(f"{label} must be finite numeric")
    return float(value)


def qualify_b0477_locked_controls(lock_path: Path, capture_path: Path, observation_path: Path) -> dict[str, Any]:
    """Return a deterministic qualification without opening any device."""

    paths = {"control_lock": Path(lock_path), "capture_receipt": Path(capture_path), "post_reopen_observation": Path(observation_path)}
    docs = {key: _read(path) for key, path in paths.items()}
    expected_schemas = {
        "control_lock": "rocell.camera_bench_control_lock.v1",
        "capture_receipt": "rocell.live_camera_read_only_intake.v1",
        "post_reopen_observation": "rocell.camera_bench_control_observation.v1",
    }
    for key, schema in expected_schemas.items():
        if docs[key].get("schema") != schema:
            raise B0477LockedControlsQualificationError(f"unexpected {key} schema")

    lock = docs["control_lock"]
    observation = docs["post_reopen_observation"]
    for document in (lock, observation):
        if document.get("device_name") != CAMERA_NAME:
            raise B0477LockedControlsQualificationError("camera friendly name differs")
    if lock.get("device_path") != observation.get("device_path"):
        raise B0477LockedControlsQualificationError("DirectShow device path differs")
    changes = _array(lock.get("changes"), "control changes")
    changed = {row.get("name"): row for row in changes if isinstance(row, Mapping)}
    for name in ("white_balance", "gain", "exposure"):
        row = _mapping(changed.get(name), f"{name} change")
        if row.get("requested_value") != EXPECTED_CONTROLS[name] or row.get("after_value") != EXPECTED_CONTROLS[name] or row.get("after_mode") != "manual" or row.get("readback_matches") is not True:
            raise B0477LockedControlsQualificationError(f"{name} lock/readback differs")
    if lock.get("control_set_calls") != 3 or lock.get("camera_only") is not True or lock.get("arm_access") is not False:
        raise B0477LockedControlsQualificationError("control-lock authority differs")

    observed_rows = _array(observation.get("controls"), "observed controls")
    observed = {row.get("name"): row for row in observed_rows if isinstance(row, Mapping)}
    for name, value in EXPECTED_CONTROLS.items():
        row = _mapping(observed.get(name), f"{name} observation")
        if row.get("current_value") != value or row.get("reported_mode") != "manual":
            raise B0477LockedControlsQualificationError(f"{name} persistence differs")
    for name in ("iris", "focus"):
        row = _mapping(observed.get(name), f"{name} observation")
        if row.get("value_observed") is not False:
            raise B0477LockedControlsQualificationError(f"{name} must remain mechanically witnessed")

    capture = docs["capture_receipt"]
    if capture.get("friendly_name") != CAMERA_NAME or capture.get("persistent_device_identity") != CAMERA_PNP or capture.get("camera_closed") is not True:
        raise B0477LockedControlsQualificationError("capture identity or close receipt differs")
    requested = _mapping(capture.get("requested_mode"), "requested mode")
    if requested != {"backend": "CAP_DSHOW", "fourcc": "YUY2", "fps": 60.0, "height_px": 1080, "width_px": 1920}:
        raise B0477LockedControlsQualificationError("requested mode differs")
    cycles = _array(capture.get("reopen_cycles"), "reopen cycles")
    if len(cycles) != 2:
        raise B0477LockedControlsQualificationError("exactly two reopen cycles are required")
    frames: list[Mapping[str, Any]] = []
    mode_hashes: set[str] = set()
    for ordinal, item in enumerate(cycles):
        cycle = _mapping(item, "reopen cycle")
        if cycle.get("reopen_ordinal") != ordinal or cycle.get("camera_closed") is not True:
            raise B0477LockedControlsQualificationError("reopen close sequence differs")
        mode = _mapping(cycle.get("negotiated_mode"), "negotiated mode")
        details = _mapping(mode.get("details"), "mode details")
        if mode.get("width_px") != 1920 or mode.get("height_px") != 1080 or abs(_finite(mode.get("fps"), "fps") - 60.000240000960005) > 1e-9 or details.get("observed_pixel_format") != "YUY2" or mode.get("identity") != CAMERA_PNP:
            raise B0477LockedControlsQualificationError("negotiated mode differs")
        mode_hashes.add(str(mode.get("settings_sha256")))
        frames.extend(_mapping(row, "frame") for row in _array(cycle.get("frames"), "frames"))
    if len(frames) != 6 or len({row.get("sha256") for row in frames}) != 6 or len(mode_hashes) != 1:
        raise B0477LockedControlsQualificationError("frame uniqueness or settings stability differs")

    scenes = [_mapping(row.get("scene_assessment"), "scene assessment") for row in frames]
    luma = [_finite(row.get("mean_luma_8bit"), "mean luma") for row in scenes]
    sharpness = [_finite(row.get("laplacian_variance"), "laplacian variance") for row in scenes]
    high_clip = [_finite(row.get("fraction_luma_ge_247"), "high clipping") for row in scenes]
    tag_union = sorted({int(tag) for row in scenes for tag in _array(row.get("detected_tag36h11_ids"), "detected tags")})
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "camera_binding": {"friendly_name": CAMERA_NAME, "persistent_device_identity": CAMERA_PNP, "directshow_device_path": lock.get("device_path"), "selector": 0, "mode": {"width_px": 1920, "height_px": 1080, "fps": 60.000240000960005, "pixel_format": "YUY2", "settings_sha256": next(iter(mode_hashes))}},
        "locked_electronic_controls": dict(EXPECTED_CONTROLS),
        "reopen_qualification": {"reopen_cycle_count": 2, "frame_count": 6, "unique_frame_count": 6, "all_six_tags_frame_count": sum(row.get("all_required_tags_visible") is True for row in scenes), "detected_tag_union": tag_union, "mean_luma_8bit_range": [min(luma), max(luma)], "mean_luma_8bit_spread": max(luma) - min(luma), "laplacian_variance_range": [min(sharpness), max(sharpness)], "maximum_fraction_luma_ge_247": max(high_clip), "frame_sha256": [row.get("sha256") for row in frames], "camera_closed_after_each_cycle": True},
        "source_bindings": {key: {"path": path.as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for key, path in paths.items()},
        "remaining_acceptance_evidence": ["mechanical focus and aperture identity with witness marks", "manual-control and selected-mode persistence across physical reconnect and host reboot", "scale-verified existing target with precommitted multi-view fit and held-out capture manifest"],
        "non_substitutions": ["fixed-pose tag visibility does not solve camera intrinsics", "reopen persistence does not prove reconnect or reboot persistence"],
        "authority": {"camera_frames_observed": 6, "camera_control_writes_observed": 3, "robot_transport_opened": False, "robot_commands_sent": 0, "physical_authority": False},
    }
    return {**report, "qualification_sha256": hashlib.sha256(_canonical(report)).hexdigest()}


__all__ = ["B0477LockedControlsQualificationError", "SCHEMA", "STATUS", "qualify_b0477_locked_controls"]
