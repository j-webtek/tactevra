"""Replay a current camera target through the frozen layout sensitivity model."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .model_motion_simulation import run as run_model_motion
from .scene_observation import canonical_hash


SCHEMA = "rocell.current_target_layout_sensitivity.v1"
INTAKE_SCHEMA = "rocell.current_bare_jaw_route_screening_intake.v1"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _verify_intake(intake: Mapping[str, Any]) -> None:
    if intake.get("schema") != INTAKE_SCHEMA:
        raise ValueError("unsupported current route intake schema")
    claimed = intake.get("intake_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise ValueError("current route intake digest is missing")
    core = dict(intake)
    del core["intake_sha256"]
    if hashlib.sha256(_canonical(core)).hexdigest() != claimed:
        raise ValueError("current route intake digest mismatch")
    bindings = _object(intake.get("bindings"), "intake bindings")
    if bindings.get("attachment_profile") != "BARE_JAW":
        raise ValueError("current target sensitivity requires BARE_JAW")
    for field in (
        "physical_authority",
        "hardware_access",
        "descent_authorized",
        "contact_authorized",
    ):
        if intake.get(field) is not False:
            raise ValueError(f"current route intake cannot assert {field}")
    if intake.get("controller_commands") != [] or intake.get("transport_writes") != 0:
        raise ValueError("current route intake must remain zero-write")


def run(
    intake: Mapping[str, Any], *, workspace: Path, profile_path: Path
) -> dict[str, Any]:
    """Screen the intake target under a frozen, explicitly unmeasured hypothesis."""

    _verify_intake(intake)
    workspace = workspace.resolve(strict=True)
    profile_path = profile_path.resolve(strict=True)
    target = _object(intake.get("selected_target"), "selected target")
    surface = _object(target.get("surface_board_mm"), "surface target")
    hover = _object(target.get("hover_board_mm"), "hover target")
    if target.get("device") != "keyboard" or target.get("target_id") != "H":
        raise ValueError("current target sensitivity v1 requires keyboard H")
    if target.get("interaction") != "HOVER" or hover.get("frame") != "board":
        raise ValueError("current target sensitivity requires the blocked board hover")
    x = _number(surface.get("x"), "surface x")
    y = _number(surface.get("y"), "surface y")
    z = _number(surface.get("z"), "surface z")
    clearance = _number(hover.get("z"), "hover z") - z
    if clearance <= 0.0:
        raise ValueError("current hover clearance must be positive")
    if (
        max(
            abs(_number(hover.get(axis), f"hover {axis}") - value)
            for axis, value in (("x", x), ("y", y))
        )
        > 0.001
    ):
        raise ValueError(
            "current hover must remain vertically above the surface target"
        )

    bindings = _object(intake.get("bindings"), "intake bindings")
    selected_frame_sha256 = bindings.get("selected_frame_sha256")
    if not isinstance(selected_frame_sha256, str) or len(selected_frame_sha256) != 64:
        raise ValueError("selected frame digest is missing")
    proposal = {
        "schema": "rocell.model_motion_proposal.v1",
        "proposal_id": "current-camera-h-contact-sensitivity-001",
        "device": "keyboard",
        "target_id": "H",
        "coordinate_frame": "board",
        "target_mm": {"x": x, "y": y, "z": z},
        "interaction": "CONTACT",
        "approach_clearance_mm": clearance,
        "speed_class": "SLOW",
        "confidence": 1.0,
        "source": {
            "model_id": "current-planar-camera-observation-v1",
            "frame_id": str(bindings.get("workcell_epoch_id")),
            "image_sha256": selected_frame_sha256,
        },
    }
    simulation = run_model_motion(
        proposal,
        workspace=workspace,
        park_xy_board_mm=(290.0, 10.0),
        robot_layout_profile=profile_path,
    )
    passed = simulation["dense_route_all_waypoints_accepted"] is True
    report = {
        "schema": SCHEMA,
        "status": (
            "CURRENT_H_PASSES_UNMEASURED_LAYOUT_SENSITIVITY"
            if passed
            else "CURRENT_H_FAILS_UNMEASURED_LAYOUT_SENSITIVITY"
        ),
        "current_intake_sha256": intake["intake_sha256"],
        "selected_frame_sha256": selected_frame_sha256,
        "workcell_epoch_id": bindings.get("workcell_epoch_id"),
        "attachment_profile": "BARE_JAW",
        "surface_board_mm": [x, y, z],
        "hover_board_mm": [x, y, z + clearance],
        "derived_contact_proposal": proposal,
        "frozen_hypothesis": {
            "profile_path": profile_path.relative_to(workspace).as_posix(),
            "profile_file_sha256": hashlib.sha256(
                profile_path.read_bytes()
            ).hexdigest(),
            "park_xy_board_mm": [290.0, 10.0],
            "installed_position_verified": False,
            "installed_tool_verified": False,
        },
        "simulation": simulation,
        "interpretation": (
            "The current H coordinate is numerically reachable under the retained "
            "unmeasured layout and park hypothesis. This narrows the prior unreachable "
            "result to setup/registration assumptions; it does not prove installed reachability."
            if passed
            else "The current H coordinate does not pass the retained unmeasured layout hypothesis."
        ),
        "remaining_physical_blockers": list(intake.get("blockers", [])),
        "physical_execution_authorized": False,
        "controller_commands": [],
        "transport_writes": 0,
        "hardware_access": False,
    }
    return {**report, "report_sha256": canonical_hash(report)}


__all__ = ["SCHEMA", "run"]
