"""Compile controlled RC03 design priors into a simulation-only fixture profile.

This boundary exists so nominal physics and route experiments do not wait on
installed metrology.  The result is deliberately incompatible with an
installed collision profile and cannot satisfy any measured-evidence gate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PROFILE_SCHEMA = "tactevra.isaac_lm4_base_board_nominal_profile.v1"
PROFILE_STATUS = "READY_FOR_SIMULATION_ONLY_EXPERIMENTS"
LAYOUT_SCHEMA_VERSION = 3
DESIGN_REVISION = "RC03-INT-R1"
BOARD_FRAME = {
    "origin": "front-left corner of board top surface",
    "axes": {"+x": "right", "+y": "rear/toward arm", "+z": "up"},
    "units": "mm",
}
BOARD_MM = [610.0, 457.0, 18.0]
BASE_TRANSLATION_MM = [305.0, 457.0, 0.0]
BASE_ROTATION = [0.0, 1.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
CLAMP_X_RANGE_MM = [225.0, 385.0]


class BaseBoardNominalProfileError(ValueError):
    """A controlled nominal source changed or crossed an authority boundary."""


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
        raise BaseBoardNominalProfileError("profile is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise BaseBoardNominalProfileError(f"{path} is not a JSON object")
    return value


def _validate_layout(layout: Mapping[str, Any]) -> None:
    board = layout.get("board", {})
    frame = {
        "origin": layout.get("origin"),
        "axes": layout.get("axes"),
        "units": layout.get("units"),
    }
    if (
        layout.get("schema_version") != LAYOUT_SCHEMA_VERSION
        or layout.get("release_revision") != DESIGN_REVISION
        or frame != BOARD_FRAME
        or [board.get("width"), board.get("depth"), board.get("thickness")]
        != BOARD_MM
        or board.get("top_surface_z") != 0.0
        or board.get("bottom_surface_z") != -18.0
        or layout.get("arm_clamp_zone", {}).get("rear_edge_x_range")
        != [225, 385]
    ):
        raise BaseBoardNominalProfileError("controlled RC03 layout changed")


def _validate_bom(rows: list[Mapping[str, str]]) -> None:
    matches = [row for row in rows if row.get("item") == "Structural board"]
    if (
        len(matches) != 1
        or matches[0].get("required") != "Yes"
        or "610 x 457 x 18 mm" not in matches[0].get("specification", "")
    ):
        raise BaseBoardNominalProfileError("controlled RC03 BOM board row changed")


def _validate_hardware(profile: Mapping[str, Any]) -> None:
    placement = profile.get("robot", {}).get("nominal_board_T_robot_world", {})
    if (
        profile.get("status") != "ASSUMED_GOOD_FOR_SIMULATION_ONLY"
        or profile.get("simulation_only") is not True
        or profile.get("physical_release_effect") != "NONE"
        or profile.get("live_hardware_access_allowed") is not False
        or placement.get("state") != "NOMINAL_ONLY_FROM_RC03_REACH_SCREENING"
        or placement.get("translation_mm") != BASE_TRANSLATION_MM
        or placement.get("rotation_row_major") != BASE_ROTATION
    ):
        raise BaseBoardNominalProfileError("simulation hardware prior changed")


def _validate_scene(scene: Mapping[str, Any]) -> None:
    source = scene.get("source_scene", {})
    board = source.get("board", {})
    if (
        scene.get("evidence_class") != "RIGID_SCENE_COMPOSITION_ONLY"
        or scene.get("physical_authority") is not False
        or scene.get("hardware_access") is not False
        or source.get("status") != "ASSUMED_GOOD_FOR_SIMULATION_ONLY"
        or source.get("can_release_physical_gates") is not False
        or board.get("minimum_mm") != [0.0, 0.0, -18.0]
        or board.get("maximum_mm") != [610.0, 457.0, 0.0]
        or source.get("arm_clamp_rear_edge_x_range_mm") != CLAMP_X_RANGE_MM
    ):
        raise BaseBoardNominalProfileError("nominal rigid scene changed")


def build_nominal_profile(
    layout: Mapping[str, Any],
    bom_rows: list[Mapping[str, str]],
    hardware_profile: Mapping[str, Any],
    nominal_scene: Mapping[str, Any],
    *,
    source_files_sha256: Mapping[str, str],
) -> dict[str, Any]:
    """Build one byte-stable, zero-authority nominal fixture profile."""

    _validate_layout(layout)
    _validate_bom(bom_rows)
    _validate_hardware(hardware_profile)
    _validate_scene(nominal_scene)
    expected_sources = {"workcell_layout", "bom", "hardware_profile", "nominal_scene"}
    if set(source_files_sha256) != expected_sources or any(
        not isinstance(value, str) or len(value) != 64
        for value in source_files_sha256.values()
    ):
        raise BaseBoardNominalProfileError("source hash inventory changed")

    placement = hardware_profile["robot"]["nominal_board_T_robot_world"]
    core: dict[str, Any] = {
        "schema": PROFILE_SCHEMA,
        "profile_id": "rc03-base-board-design-prior-001",
        "status": PROFILE_STATUS,
        "profile_class": "NOMINAL_DESIGN_PRIOR",
        "design_revision": DESIGN_REVISION,
        "source_files_sha256": dict(sorted(source_files_sha256.items())),
        "frame_B": {
            "origin": BOARD_FRAME["origin"],
            "axes": dict(BOARD_FRAME["axes"]),
            "units": "mm",
        },
        "board": {
            "evidence_state": "CONTROLLED_DESIGN_PRIOR_NOT_INSTALLED_MEASUREMENT",
            "minimum_B_mm": [0.0, 0.0, -18.0],
            "maximum_B_mm": [610.0, 457.0, 0.0],
            "width_mm": 610.0,
            "depth_mm": 457.0,
            "thickness_mm": 18.0,
            "flatness_or_bow_bound_mm": None,
        },
        "robot_base": {
            "evidence_state": "REACH_SCREENING_SEED_NOT_INSTALLED_MEASUREMENT",
            "translation_B_mm": list(placement["translation_mm"]),
            "rotation_row_major": list(placement["rotation_row_major"]),
        },
        "factory_clamp": {
            "evidence_state": "PARTIAL_NOMINAL_SPAN_NOT_FULL_3D_ENVELOPE",
            "rear_edge_x_range_B_mm": CLAMP_X_RANGE_MM,
            "minimum_B_mm": None,
            "maximum_B_mm": None,
        },
        "allowed_uses": [
            "nominal_scene_composition",
            "simulation_only_route_candidate_generation",
            "simulation_only_physics_and_sensitivity_experiments",
            "comparison_against_later_installed_metrology",
        ],
        "forbidden_uses": [
            "installed_collision_profile",
            "physical_clearance_acceptance",
            "controller_command_generation",
            "physical_gate_promotion",
        ],
        "installed_metrology_status": "SEPARATE_AND_STILL_PENDING",
        "installed_profile_compatible": False,
        "simulation_only": True,
        "physical_release_effect": "NONE",
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "controller_commands": [],
        "wire_commands": [],
        "next_stage": "CONSUME_IN_NOMINAL_ROUTE_AND_PHYSICS_EXPERIMENTS",
    }
    return {**core, "profile_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workcell-layout", type=Path, required=True)
    parser.add_argument("--bom", type=Path, required=True)
    parser.add_argument("--hardware-profile", type=Path, required=True)
    parser.add_argument("--nominal-scene", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        "workcell_layout": args.workcell_layout.resolve(strict=True),
        "bom": args.bom.resolve(strict=True),
        "hardware_profile": args.hardware_profile.resolve(strict=True),
        "nominal_scene": args.nominal_scene.resolve(strict=True),
    }
    with paths["bom"].open(encoding="utf-8", newline="") as stream:
        bom_rows = list(csv.DictReader(stream))
    result = build_nominal_profile(
        _load_object(paths["workcell_layout"]),
        bom_rows,
        _load_object(paths["hardware_profile"]),
        _load_object(paths["nominal_scene"]),
        source_files_sha256={name: _file_sha(path) for name, path in paths.items()},
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
