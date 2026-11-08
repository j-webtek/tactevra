"""Reconcile maintained base/board priors against the ARM-244 work order.

The report deliberately separates accepted installed metrology from nominal
simulation geometry, calibration-plane evidence, and semantic frame contracts.
It never completes a capture submission or grants physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


WORKORDER_SCHEMA = "tactevra.isaac_lm4_base_board_capture_workorder.v1"
REPORT_SCHEMA = "tactevra.isaac_lm4_base_board_prior_reconciliation.v1"
FRAME_DEFINITION = (
    "RC03 board frame, origin at front-left finished top surface; "
    "+x right, +y rear, +z up"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BaseBoardPriorReconciliationError(ValueError):
    """An input changed or crossed the installed-measurement boundary."""


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
        raise BaseBoardPriorReconciliationError("document is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BaseBoardPriorReconciliationError(f"{label} must be a SHA-256 digest")
    return value


def _validate_workorder(workorder: Mapping[str, Any]) -> tuple[str, dict[str, list[str]]]:
    unsigned = dict(workorder)
    claimed = unsigned.pop("workorder_sha256", None)
    fields = workorder.get("required_acceptance_fields_by_body")
    expected = {
        "installation:base_and_factory_clamp": {
            "accepted_source_hash",
            "board_to_base_transform",
            "geometry_uncertainty_mm",
            "installed_clamp_footprint",
            "local_frame_envelope_primitives",
        },
        "workcell:board_solid": {
            "accepted_source_hash",
            "flatness_or_bow_bound",
            "geometry_uncertainty_mm",
            "installed_board_pose",
            "local_frame_envelope_primitives",
        },
    }
    if (
        workorder.get("schema") != WORKORDER_SCHEMA
        or workorder.get("status") != "BLOCKED_OPERATOR_MEASUREMENTS_AND_REVIEW_REQUIRED"
        or claimed != _sha(unsigned)
        or workorder.get("submission_completed") is not False
        or workorder.get("physical_authority") is not False
        or workorder.get("unfilled_acceptance_field_count") != 10
        or not isinstance(fields, Mapping)
        or {body: set(value) for body, value in fields.items()} != expected
    ):
        raise BaseBoardPriorReconciliationError("ARM-244 work order changed")
    return claimed, {body: list(value) for body, value in fields.items()}


def _validate_sources(
    frame_contract: Mapping[str, Any],
    board_plane: Mapping[str, Any],
    hardware_profile: Mapping[str, Any],
    nominal_scene: Mapping[str, Any],
) -> None:
    if frame_contract.get("frames", {}).get("B") != FRAME_DEFINITION:
        raise BaseBoardPriorReconciliationError("board frame contract changed")
    board = board_plane.get("board", {})
    if (
        board_plane.get("status") != "accepted-provisional-fixed-plane"
        or board_plane.get("safe_for_open_loop_contact") is not False
        or [board.get("width_mm"), board.get("depth_mm")] != [610.0, 457.0]
        or board.get("origin") != "front-left finished board corner"
    ):
        raise BaseBoardPriorReconciliationError("fixed board-plane prior changed")
    placement = hardware_profile.get("robot", {}).get("nominal_board_T_robot_world", {})
    if (
        hardware_profile.get("simulation_only") is not True
        or hardware_profile.get("physical_release_effect") != "NONE"
        or placement.get("state") != "NOMINAL_ONLY_FROM_RC03_REACH_SCREENING"
        or placement.get("translation_mm") != [305.0, 457.0, 0.0]
    ):
        raise BaseBoardPriorReconciliationError("simulation placement prior changed")
    source_scene = nominal_scene.get("source_scene", {})
    if (
        nominal_scene.get("evidence_class") != "RIGID_SCENE_COMPOSITION_ONLY"
        or nominal_scene.get("physical_authority") is not False
        or source_scene.get("status") != "ASSUMED_GOOD_FOR_SIMULATION_ONLY"
        or source_scene.get("arm_clamp_rear_edge_x_range_mm") != [225.0, 385.0]
        or source_scene.get("board", {}).get("minimum_mm") != [0.0, 0.0, -18.0]
        or source_scene.get("board", {}).get("maximum_mm") != [610.0, 457.0, 0.0]
    ):
        raise BaseBoardPriorReconciliationError("nominal scene prior changed")


def build_reconciliation(
    workorder: Mapping[str, Any],
    frame_contract: Mapping[str, Any],
    board_plane: Mapping[str, Any],
    hardware_profile: Mapping[str, Any],
    nominal_scene: Mapping[str, Any],
    *,
    source_file_sha256: Mapping[str, str],
) -> dict[str, Any]:
    """Build a zero-authority assessment of reusable but non-acceptable priors."""

    workorder_hash, required = _validate_workorder(workorder)
    _validate_sources(frame_contract, board_plane, hardware_profile, nominal_scene)
    expected_names = {
        "workorder",
        "frame_contract",
        "board_plane",
        "hardware_profile",
        "nominal_scene",
    }
    if set(source_file_sha256) != expected_names:
        raise BaseBoardPriorReconciliationError("source hash inventory changed")
    hashes = {
        name: _digest(value, f"{name} file hash")
        for name, value in sorted(source_file_sha256.items())
    }
    placement = hardware_profile["robot"]["nominal_board_T_robot_world"]
    rows = {
        "installation:base_and_factory_clamp": {
            "accepted_source_hash": "MISSING_ACCEPTED_EVIDENCE",
            "board_to_base_transform": "PROVISIONAL_VALUE_NOT_ACCEPTABLE",
            "geometry_uncertainty_mm": "MISSING_ACCEPTED_EVIDENCE",
            "installed_clamp_footprint": "PARTIAL_PRIOR_NOT_ACCEPTABLE",
            "local_frame_envelope_primitives": "MISSING_ACCEPTED_EVIDENCE",
        },
        "workcell:board_solid": {
            "accepted_source_hash": "MISSING_ACCEPTED_EVIDENCE",
            "flatness_or_bow_bound": "MISSING_ACCEPTED_EVIDENCE",
            "geometry_uncertainty_mm": "MISSING_ACCEPTED_EVIDENCE",
            "installed_board_pose": "SEMANTIC_FRAME_ONLY_NOT_ACCEPTABLE",
            "local_frame_envelope_primitives": "PROVISIONAL_VALUE_NOT_ACCEPTABLE",
        },
    }
    if {body: set(values) for body, values in rows.items()} != {
        body: set(values) for body, values in required.items()
    }:
        raise BaseBoardPriorReconciliationError("field reconciliation is incomplete")
    core: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": "BLOCKED_INSTALLED_METROLOGY_STILL_REQUIRED",
        "source_arm244_workorder_sha256": workorder_hash,
        "source_files_sha256": hashes,
        "accepted_field_count": 0,
        "required_field_count": 10,
        "reusable_priors": [
            {
                "prior_id": "board_nominal_solid",
                "value": {"minimum_B_mm": [0.0, 0.0, -18.0], "maximum_B_mm": [610.0, 457.0, 0.0]},
                "disposition": "COMPARISON_TARGET_ONLY_NOT_INSTALLED_MEASUREMENT",
                "supports_field": "workcell:board_solid/local_frame_envelope_primitives",
            },
            {
                "prior_id": "base_nominal_pose",
                "value": {
                    "translation_B_mm": list(placement["translation_mm"]),
                    "rotation_row_major": list(placement["rotation_row_major"]),
                },
                "disposition": "REACH_SCREENING_SEED_ONLY_NOT_INSTALLED_MEASUREMENT",
                "supports_field": "installation:base_and_factory_clamp/board_to_base_transform",
            },
            {
                "prior_id": "clamp_rear_edge_x_span",
                "value": {"x_range_B_mm": [225.0, 385.0]},
                "disposition": "PARTIAL_NOMINAL_SPAN_NOT_FULL_FOOTPRINT",
                "supports_field": "installation:base_and_factory_clamp/installed_clamp_footprint",
            },
        ],
        "semantic_support": {
            "frame_B": FRAME_DEFINITION,
            "fixed_camera_board_plane_fit_rms_mm": board_plane["fit"]["rms_error_mm"],
            "disposition": (
                "FRAME_AND_IMAGE_PLANE_CONTEXT_ONLY; the fit residual is not board "
                "geometry uncertainty, flatness, or a base transform"
            ),
        },
        "field_dispositions": rows,
        "capture_reduction": {
            "fields_completed": 0,
            "remeasurement_avoided": False,
            "comparison_targets_available": 3,
            "remaining_measurement_focus": [
                "installed board extents, thickness, and conservative 3D envelope in B",
                "board top-surface flatness or bow bound and measurement uncertainty",
                "installed base transform and uncertainty in B",
                "full factory-clamp footprint and conservative 3D envelope in B",
                "retained evidence hashes and independent measured review",
            ],
        },
        "submission_completed": False,
        "measurement_manifest_modified": False,
        "installed_collision_profile_generated": False,
        "isaac_started": False,
        "gpu_started": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "next_required_stage": "CAPTURE_INSTALLED_BASE_BOARD_METROLOGY_AGAINST_PRIOR_TARGETS",
    }
    return {**core, "reconciliation_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise BaseBoardPriorReconciliationError(f"{path} is not a JSON object")
    return value


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workorder", type=Path, required=True)
    parser.add_argument("--frame-contract", type=Path, required=True)
    parser.add_argument("--board-plane", type=Path, required=True)
    parser.add_argument("--hardware-profile", type=Path, required=True)
    parser.add_argument("--nominal-scene", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        "workorder": args.workorder.resolve(strict=True),
        "frame_contract": args.frame_contract.resolve(strict=True),
        "board_plane": args.board_plane.resolve(strict=True),
        "hardware_profile": args.hardware_profile.resolve(strict=True),
        "nominal_scene": args.nominal_scene.resolve(strict=True),
    }
    result = build_reconciliation(
        _load(paths["workorder"]),
        _load(paths["frame_contract"]),
        _load(paths["board_plane"]),
        _load(paths["hardware_profile"]),
        _load(paths["nominal_scene"]),
        source_file_sha256={name: _file_sha(path) for name, path in paths.items()},
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
