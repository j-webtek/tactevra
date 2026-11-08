"""Package base/board setup photos without promoting them to metrology.

ARM-247 preserves supplied ruler, board, and calibration images as immutable
context evidence and creates a lineage-bound draft of the ARM-246 observation.
Context photos are deliberately not selected as accepted measurement sources.
No simulator, device, controller, or physical motion is used.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Any, Mapping, Sequence


KIT_SCHEMA = "tactevra.isaac_lm4_base_board_raw_capture_kit.v1"
OBSERVATION_SCHEMA = "tactevra.isaac_lm4_base_board_raw_observation.v1"
PACK_SCHEMA = "tactevra.isaac_lm4_base_board_context_evidence_pack.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CATEGORIES = {"ruler_context", "board_context", "calibration_context", "setup_context"}


class BaseBoardContextEvidenceError(ValueError):
    """The capture kit or context-evidence request is invalid."""


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
        raise BaseBoardContextEvidenceError("document is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_kit(kit: Mapping[str, Any]) -> str:
    unsigned = dict(kit)
    claimed = unsigned.pop("capture_kit_sha256", None)
    template = kit.get("raw_observation_template")
    if (
        kit.get("schema") != KIT_SCHEMA
        or kit.get("status") != "BLOCKED_RAW_OBSERVATIONS_AND_REVIEW_REQUIRED"
        or not isinstance(claimed, str)
        or _SHA256.fullmatch(claimed) is None
        or claimed != _sha(unsigned)
        or kit.get("nominal_values_may_fill_observations") is not False
        or kit.get("physical_authority") is not False
        or not isinstance(template, Mapping)
        or template.get("schema") != OBSERVATION_SCHEMA
    ):
        raise BaseBoardContextEvidenceError("ARM-246 capture kit changed")
    return claimed


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    return None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    offset = 2
    start_of_frame = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            break
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            break
        if marker in start_of_frame and length >= 7:
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            return width, height
        offset += length
    return None


def _image_dimensions(data: bytes) -> tuple[int, int]:
    result = _png_dimensions(data) or _jpeg_dimensions(data)
    if result is None or any(value <= 0 for value in result):
        raise BaseBoardContextEvidenceError("evidence must be a readable PNG or JPEG image")
    return result


def _normal_reference(path: Path, reference_root: Path | None) -> str:
    resolved = path.resolve(strict=True)
    if reference_root is None:
        return resolved.name
    root = reference_root.resolve(strict=True)
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise BaseBoardContextEvidenceError(
            f"evidence is outside reference root: {resolved}"
        ) from exc


def build_context_evidence_pack(
    capture_kit: Mapping[str, Any],
    evidence: Sequence[tuple[str, Path]],
    *,
    reference_root: Path | None = None,
) -> dict[str, Any]:
    """Hash context photos and build an explicitly incomplete observation draft."""

    kit_hash = _validate_kit(capture_kit)
    if not evidence:
        raise BaseBoardContextEvidenceError("at least one context image is required")
    retained: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for category, source in evidence:
        if category not in _CATEGORIES:
            raise BaseBoardContextEvidenceError(f"unsupported evidence category: {category}")
        path = source.resolve(strict=True)
        data = path.read_bytes()
        width, height = _image_dimensions(data)
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen_hashes:
            raise BaseBoardContextEvidenceError("duplicate evidence content")
        seen_hashes.add(digest)
        retained.append(
            {
                "category": category,
                "source_reference": _normal_reference(path, reference_root),
                "source_file_sha256": digest,
                "byte_count": len(data),
                "pixel_width": width,
                "pixel_height": height,
                "disposition": "CONTEXT_ONLY_NOT_ACCEPTED_METROLOGY",
            }
        )
    retained.sort(key=lambda row: (row["source_reference"], row["source_file_sha256"]))

    draft = copy.deepcopy(capture_kit["raw_observation_template"])
    draft["source_capture_kit_sha256"] = kit_hash
    draft["evidence_sources"] = [
        {
            "source_file_sha256": row["source_file_sha256"],
            "source_reference": row["source_reference"],
        }
        for row in retained
    ]

    remaining = [
        "instrument_identity",
        "instrument_resolution_mm",
        "observer",
        "reviewer",
        "reviewer_decision=ACCEPTED_MEASURED",
        "board.accepted_source_hash",
        "board.frame_B_registration_verified",
        "board.width_mm",
        "board.depth_mm",
        "board.thickness_mm",
        "board.flatness_or_bow_bound_mm",
        "board.geometry_uncertainty_mm",
        "base_and_factory_clamp.accepted_source_hash",
        "base_and_factory_clamp.base_origin_B_mm",
        "base_and_factory_clamp.base_rotation_row_major",
        "base_and_factory_clamp.clamp_min_B_mm",
        "base_and_factory_clamp.clamp_max_B_mm",
        "base_and_factory_clamp.geometry_uncertainty_mm",
    ]
    core: dict[str, Any] = {
        "schema": PACK_SCHEMA,
        "status": "BLOCKED_PRECISION_METROLOGY_AND_INDEPENDENT_REVIEW_REQUIRED",
        "source_capture_kit_sha256": kit_hash,
        "retained_context_evidence": retained,
        "retained_context_evidence_count": len(retained),
        "context_evidence_may_fill_measurements": False,
        "accepted_measurement_source_count": 0,
        "completed_measurement_field_count": 0,
        "remaining_observation_requirements": remaining,
        "remaining_observation_requirement_count": len(remaining),
        "observation_draft": draft,
        "next_required_stage": (
            "CAPTURE_INSTALLED_METROLOGY_WITH_DECLARED_INSTRUMENT_AND_INDEPENDENT_REVIEW"
        ),
        "submission_completed": False,
        "installed_collision_profile_generated": False,
        "isaac_started": False,
        "gpu_started": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
    }
    return {**core, "evidence_pack_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise BaseBoardContextEvidenceError(f"{path} is not a JSON object")
    return value


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def _evidence_argument(value: str) -> tuple[str, Path]:
    category, separator, raw_path = value.partition("=")
    if not separator or not raw_path:
        raise argparse.ArgumentTypeError("evidence must use CATEGORY=PATH")
    return category, Path(raw_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-kit", type=Path, required=True)
    parser.add_argument(
        "--evidence",
        action="append",
        type=_evidence_argument,
        required=True,
        metavar="CATEGORY=PATH",
    )
    parser.add_argument("--reference-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_context_evidence_pack(
        _load(args.capture_kit.resolve(strict=True)),
        args.evidence,
        reference_root=args.reference_root,
    )
    _write_new(args.output.resolve(), result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
