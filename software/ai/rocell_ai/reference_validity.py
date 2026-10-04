"""Fail-closed freshness checks for commissioned visual references."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def evaluate_reference_validity(reference: dict[str, Any], capture: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    age_ms = capture["captured_at_ms"] - reference["captured_at_ms"]
    if age_ms < 0:
        reasons.append("reference_created_after_frame")
    if age_ms > reference["maximum_age_ms"]:
        reasons.append("reference_age_exceeded")
    for field, reason in (
        ("camera_calibration_sha256", "camera_calibration_changed"),
        ("fixture_pose_sha256", "fixture_pose_changed"),
        ("target_map_sha256", "target_map_changed"),
    ):
        if reference[field] != capture[field]:
            reasons.append(reason)
    lighting_delta = max(
        abs(capture["lighting_descriptor"][name] - reference["lighting_descriptor"][name])
        / max(abs(reference["lighting_descriptor"][name]), 1e-6)
        for name in ("luminance", "red_green_ratio", "blue_green_ratio")
    )
    if lighting_delta > reference["maximum_relative_lighting_drift"]:
        reasons.append("lighting_drift_exceeded")
    core = {
        "schema": "tactevra.ai_reference_validity.v1",
        "status": "VALID" if not reasons else "ABSTAIN",
        "reference_id": reference["reference_id"],
        "frame_id": capture["frame_id"],
        "reference_age_ms": age_ms,
        "maximum_age_ms": reference["maximum_age_ms"],
        "relative_lighting_drift": lighting_delta,
        "maximum_relative_lighting_drift": reference["maximum_relative_lighting_drift"],
        "reasons": reasons,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "result_sha256": _hash(core)}
