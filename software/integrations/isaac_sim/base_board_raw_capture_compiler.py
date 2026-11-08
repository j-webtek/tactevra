"""Build and compile the ARM-246 base/board raw capture kit.

The kit reduces the ARM-243 ``base_board_installation`` submission to one
reviewed observation record.  Nominal ARM-245 priors are shown only as
comparison targets.  They are never copied into measured fields.

No simulator, GPU, device, controller, or physical motion is used.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


TEMPLATES_SCHEMA = "tactevra.isaac_lm4_capture_submission_templates.v1"
RECONCILIATION_SCHEMA = "tactevra.isaac_lm4_base_board_prior_reconciliation.v1"
KIT_SCHEMA = "tactevra.isaac_lm4_base_board_raw_capture_kit.v1"
OBSERVATION_SCHEMA = "tactevra.isaac_lm4_base_board_raw_observation.v1"
SUBMISSION_SCHEMA = "tactevra.isaac_lm4_capture_packet_submission.v1"
PACKET_ID = "base_board_installation"
FRAME_B = (
    "RC03 board frame, origin at front-left finished top surface; "
    "+x right, +y rear, +z up"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]


class BaseBoardRawCaptureError(ValueError):
    """A lineage document or measured observation is incomplete or invalid."""


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
        raise BaseBoardRawCaptureError("document is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BaseBoardRawCaptureError(f"{label} must be a SHA-256 digest")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BaseBoardRawCaptureError(f"{label} must be nonempty text")
    return value.strip()


def _number(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BaseBoardRawCaptureError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise BaseBoardRawCaptureError(f"{label} must be {qualifier}")
    return result


def _vector(value: object, label: str, length: int = 3) -> list[float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != length
    ):
        raise BaseBoardRawCaptureError(f"{label} must contain {length} numbers")
    return [_number(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _rotation(value: object, label: str) -> list[float]:
    rotation = _vector(value, label, 9)
    rows = [rotation[index : index + 3] for index in range(0, 9, 3)]
    for index, row in enumerate(rows):
        norm = sum(item * item for item in row)
        if not math.isclose(norm, 1.0, abs_tol=1e-6):
            raise BaseBoardRawCaptureError(f"{label} row {index} is not unit length")
    for left in range(3):
        for right in range(left + 1, 3):
            dot = sum(rows[left][i] * rows[right][i] for i in range(3))
            if not math.isclose(dot, 0.0, abs_tol=1e-6):
                raise BaseBoardRawCaptureError(f"{label} rows are not orthogonal")
    determinant = (
        rotation[0] * (rotation[4] * rotation[8] - rotation[5] * rotation[7])
        - rotation[1] * (rotation[3] * rotation[8] - rotation[5] * rotation[6])
        + rotation[2] * (rotation[3] * rotation[7] - rotation[4] * rotation[6])
    )
    if not math.isclose(determinant, 1.0, abs_tol=1e-6):
        raise BaseBoardRawCaptureError(f"{label} must be a proper rotation")
    return rotation


def _validate_templates(templates: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    unsigned = dict(templates)
    claimed = unsigned.pop("templates_sha256", None)
    rows = templates.get("submission_templates")
    if (
        templates.get("schema") != TEMPLATES_SCHEMA
        or templates.get("status") != "BLOCKED_CAPTURE_SUBMISSIONS_REQUIRED"
        or claimed != _sha(unsigned)
        or not isinstance(rows, list)
        or templates.get("template_count") != len(rows)
    ):
        raise BaseBoardRawCaptureError("ARM-243 templates changed")
    selected = [row for row in rows if row.get("packet_id") == PACKET_ID]
    if len(selected) != 1:
        raise BaseBoardRawCaptureError("ARM-243 base/board template coverage changed")
    template = selected[0]
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
    actual = {
        row.get("body_id"): set(row.get("acceptance_values", {}))
        for row in template.get("body_submissions", [])
    }
    if (
        template.get("schema") != SUBMISSION_SCHEMA
        or template.get("reviewer_decision") != "PENDING"
        or template.get("submission_sha256") is not None
        or actual != expected
    ):
        raise BaseBoardRawCaptureError("ARM-243 base/board template changed")
    return _digest(claimed, "ARM-243 templates hash"), copy.deepcopy(template)


def _validate_reconciliation(reconciliation: Mapping[str, Any]) -> str:
    unsigned = dict(reconciliation)
    claimed = unsigned.pop("reconciliation_sha256", None)
    priors = reconciliation.get("reusable_priors")
    if (
        reconciliation.get("schema") != RECONCILIATION_SCHEMA
        or reconciliation.get("status") != "BLOCKED_INSTALLED_METROLOGY_STILL_REQUIRED"
        or claimed != _sha(unsigned)
        or reconciliation.get("accepted_field_count") != 0
        or reconciliation.get("required_field_count") != 10
        or reconciliation.get("submission_completed") is not False
        or reconciliation.get("physical_authority") is not False
        or not isinstance(priors, list)
        or len(priors) != 3
        or any("NOT_" not in prior.get("disposition", "") for prior in priors)
    ):
        raise BaseBoardRawCaptureError("ARM-245 reconciliation changed")
    return _digest(claimed, "ARM-245 reconciliation hash")


def build_capture_kit(
    templates: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    *,
    templates_file_sha256: str,
    reconciliation_file_sha256: str,
) -> dict[str, Any]:
    """Create a blank, lineage-bound raw observation form."""

    templates_hash, _ = _validate_templates(templates)
    reconciliation_hash = _validate_reconciliation(reconciliation)
    raw_template = {
        "schema": OBSERVATION_SCHEMA,
        "source_capture_kit_sha256": None,
        "evidence_sources": [],
        "instrument_identity": None,
        "instrument_resolution_mm": None,
        "coordinate_frame": "B",
        "observer": None,
        "reviewer": None,
        "reviewer_decision": "PENDING",
        "board": {
            "accepted_source_hash": None,
            "frame_B_registration_verified": None,
            "width_mm": None,
            "depth_mm": None,
            "thickness_mm": None,
            "flatness_or_bow_bound_mm": None,
            "geometry_uncertainty_mm": None,
        },
        "base_and_factory_clamp": {
            "accepted_source_hash": None,
            "base_origin_B_mm": None,
            "base_rotation_row_major": None,
            "clamp_min_B_mm": None,
            "clamp_max_B_mm": None,
            "geometry_uncertainty_mm": None,
        },
    }
    core: dict[str, Any] = {
        "schema": KIT_SCHEMA,
        "status": "BLOCKED_RAW_OBSERVATIONS_AND_REVIEW_REQUIRED",
        "source_arm243_templates_sha256": templates_hash,
        "source_arm243_templates_file_sha256": _digest(
            templates_file_sha256, "ARM-243 templates file hash"
        ),
        "source_arm245_reconciliation_sha256": reconciliation_hash,
        "source_arm245_reconciliation_file_sha256": _digest(
            reconciliation_file_sha256, "ARM-245 reconciliation file hash"
        ),
        "packet_id": PACKET_ID,
        "coordinate_frame_definition": FRAME_B,
        "nominal_comparison_targets": copy.deepcopy(reconciliation["reusable_priors"]),
        "nominal_values_may_fill_observations": False,
        "raw_observation_template": raw_template,
        "compiler_derivations": {
            "board_envelope": "oriented box from measured width, depth, and thickness",
            "board_pose": "identity in B because B is defined on the installed board",
            "clamp_footprint": "x/y projection of measured clamp bounds in B",
            "clamp_envelope": "oriented box from measured minimum and maximum bounds in B",
            "base_transform": "measured base origin and proper rotation in B",
        },
        "required_review": "reviewer must differ from observer and accept measured evidence",
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
        "next_required_stage": "FILL_RAW_OBSERVATION_AND_OBTAIN_INDEPENDENT_REVIEW",
    }
    return {**core, "capture_kit_sha256": _sha(core)}


def _validate_kit(kit: Mapping[str, Any]) -> str:
    unsigned = dict(kit)
    claimed = unsigned.pop("capture_kit_sha256", None)
    if (
        kit.get("schema") != KIT_SCHEMA
        or kit.get("status") != "BLOCKED_RAW_OBSERVATIONS_AND_REVIEW_REQUIRED"
        or claimed != _sha(unsigned)
        or kit.get("packet_id") != PACKET_ID
        or kit.get("nominal_values_may_fill_observations") is not False
        or kit.get("submission_completed") is not False
        or kit.get("physical_authority") is not False
    ):
        raise BaseBoardRawCaptureError("ARM-246 capture kit changed")
    return _digest(claimed, "capture kit hash")


def _validate_observation(
    observation: Mapping[str, Any], capture_kit_sha256: str
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    expected_top = {
        "schema",
        "source_capture_kit_sha256",
        "evidence_sources",
        "instrument_identity",
        "instrument_resolution_mm",
        "coordinate_frame",
        "observer",
        "reviewer",
        "reviewer_decision",
        "board",
        "base_and_factory_clamp",
    }
    if set(observation) != expected_top:
        raise BaseBoardRawCaptureError("raw observation fields differ")
    if (
        observation.get("schema") != OBSERVATION_SCHEMA
        or observation.get("source_capture_kit_sha256") != capture_kit_sha256
        or observation.get("coordinate_frame") != "B"
        or observation.get("reviewer_decision") != "ACCEPTED_MEASURED"
    ):
        raise BaseBoardRawCaptureError("raw observation is not accepted for this kit")
    observer = _text(observation.get("observer"), "observer")
    reviewer = _text(observation.get("reviewer"), "reviewer")
    if observer.casefold() == reviewer.casefold():
        raise BaseBoardRawCaptureError("reviewer must differ from observer")
    _text(observation.get("instrument_identity"), "instrument identity")
    _number(observation.get("instrument_resolution_mm"), "instrument resolution", positive=True)
    sources = observation.get("evidence_sources")
    if not isinstance(sources, list) or not sources:
        raise BaseBoardRawCaptureError("evidence_sources must be nonempty")
    clean_sources: list[dict[str, str]] = []
    source_hashes = set()
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping) or set(source) != {
            "source_file_sha256",
            "source_reference",
        }:
            raise BaseBoardRawCaptureError(f"evidence source {index} fields differ")
        digest = _digest(source["source_file_sha256"], f"evidence source {index} hash")
        source_hashes.add(digest)
        clean_sources.append(
            {
                "source_file_sha256": digest,
                "source_reference": _text(
                    source["source_reference"], f"evidence source {index} reference"
                ),
            }
        )
    board = observation.get("board")
    base = observation.get("base_and_factory_clamp")
    board_keys = {
        "accepted_source_hash",
        "frame_B_registration_verified",
        "width_mm",
        "depth_mm",
        "thickness_mm",
        "flatness_or_bow_bound_mm",
        "geometry_uncertainty_mm",
    }
    base_keys = {
        "accepted_source_hash",
        "base_origin_B_mm",
        "base_rotation_row_major",
        "clamp_min_B_mm",
        "clamp_max_B_mm",
        "geometry_uncertainty_mm",
    }
    if not isinstance(board, Mapping) or set(board) != board_keys:
        raise BaseBoardRawCaptureError("board observation fields differ")
    if not isinstance(base, Mapping) or set(base) != base_keys:
        raise BaseBoardRawCaptureError("base/clamp observation fields differ")
    for label, body in (("board", board), ("base/clamp", base)):
        if _digest(body["accepted_source_hash"], f"{label} accepted source") not in source_hashes:
            raise BaseBoardRawCaptureError(f"{label} source is not retained evidence")
    if board["frame_B_registration_verified"] is not True:
        raise BaseBoardRawCaptureError("installed frame B registration is not verified")
    clean_board = {
        "accepted_source_hash": board["accepted_source_hash"],
        "frame_B_registration_verified": True,
        "width_mm": _number(board["width_mm"], "board width", positive=True),
        "depth_mm": _number(board["depth_mm"], "board depth", positive=True),
        "thickness_mm": _number(board["thickness_mm"], "board thickness", positive=True),
        "flatness_or_bow_bound_mm": _number(
            board["flatness_or_bow_bound_mm"], "board flatness/bow bound", positive=True
        ),
        "geometry_uncertainty_mm": _number(
            board["geometry_uncertainty_mm"], "board geometry uncertainty", positive=True
        ),
    }
    minimum = _vector(base["clamp_min_B_mm"], "clamp minimum")
    maximum = _vector(base["clamp_max_B_mm"], "clamp maximum")
    if any(high <= low for low, high in zip(minimum, maximum)):
        raise BaseBoardRawCaptureError("clamp maximum must exceed minimum on every axis")
    clean_base = {
        "accepted_source_hash": base["accepted_source_hash"],
        "base_origin_B_mm": _vector(base["base_origin_B_mm"], "base origin"),
        "base_rotation_row_major": _rotation(
            base["base_rotation_row_major"], "base rotation"
        ),
        "clamp_min_B_mm": minimum,
        "clamp_max_B_mm": maximum,
        "geometry_uncertainty_mm": _number(
            base["geometry_uncertainty_mm"], "base geometry uncertainty", positive=True
        ),
    }
    return clean_board, clean_base, clean_sources


def compile_observation(
    templates: Mapping[str, Any],
    capture_kit: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile one independently reviewed observation into an ARM-243 submission."""

    templates_hash, submission = _validate_templates(templates)
    kit_hash = _validate_kit(capture_kit)
    if capture_kit.get("source_arm243_templates_sha256") != templates_hash:
        raise BaseBoardRawCaptureError("capture kit and ARM-243 templates do not match")
    board, base, evidence_sources = _validate_observation(observation, kit_hash)
    body_map = {row["body_id"]: row for row in submission["body_submissions"]}
    clamp_center = [
        (low + high) / 2.0
        for low, high in zip(base["clamp_min_B_mm"], base["clamp_max_B_mm"])
    ]
    clamp_half_extents = [
        (high - low) / 2.0
        for low, high in zip(base["clamp_min_B_mm"], base["clamp_max_B_mm"])
    ]
    body_map["installation:base_and_factory_clamp"]["acceptance_values"] = {
        "accepted_source_hash": base["accepted_source_hash"],
        "board_to_base_transform": {
            "translation_B_mm": base["base_origin_B_mm"],
            "rotation_row_major": base["base_rotation_row_major"],
        },
        "geometry_uncertainty_mm": base["geometry_uncertainty_mm"],
        "installed_clamp_footprint": {
            "minimum_B_xy_mm": base["clamp_min_B_mm"][:2],
            "maximum_B_xy_mm": base["clamp_max_B_mm"][:2],
        },
        "local_frame_envelope_primitives": [
            {
                "kind": "oriented_box",
                "center_mm": clamp_center,
                "half_extents_mm": clamp_half_extents,
                "rotation_row_major": _IDENTITY,
            }
        ],
    }
    body_map["workcell:board_solid"]["acceptance_values"] = {
        "accepted_source_hash": board["accepted_source_hash"],
        "flatness_or_bow_bound": {
            "maximum_absolute_deviation_mm": board["flatness_or_bow_bound_mm"],
            "reference": "installed board top surface z=0 in B",
        },
        "geometry_uncertainty_mm": board["geometry_uncertainty_mm"],
        "installed_board_pose": {
            "translation_B_mm": [0.0, 0.0, 0.0],
            "rotation_row_major": _IDENTITY,
            "basis": FRAME_B,
            "registration_verified": board["frame_B_registration_verified"],
        },
        "local_frame_envelope_primitives": [
            {
                "kind": "oriented_box",
                "center_mm": [
                    board["width_mm"] / 2.0,
                    board["depth_mm"] / 2.0,
                    -board["thickness_mm"] / 2.0,
                ],
                "half_extents_mm": [
                    board["width_mm"] / 2.0,
                    board["depth_mm"] / 2.0,
                    board["thickness_mm"] / 2.0,
                ],
                "rotation_row_major": _IDENTITY,
            }
        ],
    }
    submission["evidence_sources"] = evidence_sources
    submission["instrument_identity"] = observation["instrument_identity"].strip()
    submission["instrument_resolution_mm"] = float(observation["instrument_resolution_mm"])
    submission["coordinate_frame"] = "B"
    submission["reviewer"] = observation["reviewer"].strip()
    submission["reviewer_decision"] = "ACCEPTED_MEASURED"
    unsigned = dict(submission)
    unsigned.pop("submission_sha256")
    submission["submission_sha256"] = _sha(unsigned)
    return submission


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise BaseBoardRawCaptureError(f"{path} is not a JSON object")
    return value


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--templates", type=Path, required=True)
    parser.add_argument("--reconciliation", type=Path)
    parser.add_argument("--capture-kit", type=Path)
    parser.add_argument("--observation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    templates_path = args.templates.resolve(strict=True)
    if args.observation is None:
        if args.reconciliation is None or args.capture_kit is not None:
            parser.error("kit mode requires --reconciliation and no --capture-kit")
        reconciliation_path = args.reconciliation.resolve(strict=True)
        result = build_capture_kit(
            _load(templates_path),
            _load(reconciliation_path),
            templates_file_sha256=_file_sha(templates_path),
            reconciliation_file_sha256=_file_sha(reconciliation_path),
        )
    else:
        if args.capture_kit is None or args.reconciliation is not None:
            parser.error("compile mode requires --capture-kit and --observation")
        result = compile_observation(
            _load(templates_path),
            _load(args.capture_kit.resolve(strict=True)),
            _load(args.observation.resolve(strict=True)),
        )
    output = args.output.resolve()
    _write_new(output, result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
