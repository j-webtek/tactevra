"""Build and compile the ARM-248 installed base/board metrology protocol.

The protocol converts repeated instrument readings into the exact ARM-246 raw
observation. It uses conservative repeatability plus instrument-resolution
uncertainty, reconstructs the base rotation from three measured datums, and
requires independent acceptance. It never reads a device or commands motion.
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


PACK_SCHEMA = "tactevra.isaac_lm4_base_board_context_evidence_pack.v1"
PROTOCOL_SCHEMA = "tactevra.isaac_lm4_base_board_installed_metrology_protocol.v1"
SESSION_SCHEMA = "tactevra.isaac_lm4_base_board_installed_metrology_session.v1"
OBSERVATION_SCHEMA = "tactevra.isaac_lm4_base_board_raw_observation.v1"
AUDIT_SCHEMA = "tactevra.isaac_lm4_base_board_metrology_session_audit.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BaseBoardInstalledMetrologyError(ValueError):
    """The evidence lineage or measurement session is invalid."""


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
        raise BaseBoardInstalledMetrologyError("document is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BaseBoardInstalledMetrologyError(f"{label} must be a SHA-256 digest")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BaseBoardInstalledMetrologyError(f"{label} must be nonempty text")
    return value.strip()


def _number(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BaseBoardInstalledMetrologyError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        raise BaseBoardInstalledMetrologyError(f"{label} is outside its valid range")
    return result


def _validate_pack(pack: Mapping[str, Any]) -> str:
    unsigned = dict(pack)
    claimed = unsigned.pop("evidence_pack_sha256", None)
    if (
        pack.get("schema") != PACK_SCHEMA
        or pack.get("status")
        != "BLOCKED_PRECISION_METROLOGY_AND_INDEPENDENT_REVIEW_REQUIRED"
        or claimed != _sha(unsigned)
        or pack.get("context_evidence_may_fill_measurements") is not False
        or pack.get("accepted_measurement_source_count") != 0
        or pack.get("physical_authority") is not False
        or not isinstance(pack.get("observation_draft"), Mapping)
    ):
        raise BaseBoardInstalledMetrologyError("ARM-247 evidence pack changed")
    return _digest(claimed, "evidence pack hash")


def build_protocol(pack: Mapping[str, Any]) -> dict[str, Any]:
    """Create a blank, lineage-bound repeated-reading session."""

    pack_hash = _validate_pack(pack)
    template = {
        "schema": SESSION_SCHEMA,
        "source_evidence_pack_sha256": pack_hash,
        "instrument_identity": None,
        "instrument_resolution_mm": None,
        "observer": None,
        "reviewer": None,
        "reviewer_decision": "PENDING",
        "frame_B_registration_verified": None,
        "readings_mm": {
            "board_width": [None, None, None],
            "board_depth": [None, None, None],
            "board_thickness": [None, None, None],
            "board_top_surface_deviation": [None] * 9,
            "base_origin_B": [[None, None, None] for _ in range(3)],
            "base_x_datum_B": [[None, None, None] for _ in range(3)],
            "base_y_datum_B": [[None, None, None] for _ in range(3)],
            "clamp_min_B": [[None, None, None] for _ in range(3)],
            "clamp_max_B": [[None, None, None] for _ in range(3)],
        },
    }
    core: dict[str, Any] = {
        "schema": PROTOCOL_SCHEMA,
        "status": "BLOCKED_READINGS_AND_INDEPENDENT_REVIEW_REQUIRED",
        "source_evidence_pack_sha256": pack_hash,
        "coordinate_frame": "B",
        "units": "mm",
        "capture_rules": {
            "dimensional_repeat_count": 3,
            "vector_repeat_count": 3,
            "board_bow_grid": "3x3 installed top-surface deviations from z=0 in B",
            "base_rotation_method": (
                "orthonormal basis from mean origin, +x datum, and +y datum; "
                "matrix columns are base axes expressed in B"
            ),
            "uncertainty_method": (
                "maximum absolute repeat residual plus instrument resolution"
            ),
            "configuration_change_forbidden": True,
        },
        "session_template": template,
        "context_evidence_may_fill_readings": False,
        "submission_completed": False,
        "isaac_started": False,
        "gpu_started": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "next_required_stage": "FILL_REPEATED_READINGS_AND_OBTAIN_INDEPENDENT_REVIEW",
    }
    return {**core, "protocol_sha256": _sha(core)}


def _validate_protocol(protocol: Mapping[str, Any]) -> str:
    unsigned = dict(protocol)
    claimed = unsigned.pop("protocol_sha256", None)
    template = protocol.get("session_template")
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status") != "BLOCKED_READINGS_AND_INDEPENDENT_REVIEW_REQUIRED"
        or claimed != _sha(unsigned)
        or protocol.get("context_evidence_may_fill_readings") is not False
        or protocol.get("physical_authority") is not False
        or not isinstance(template, Mapping)
        or template.get("schema") != SESSION_SCHEMA
        or template.get("source_evidence_pack_sha256")
        != protocol.get("source_evidence_pack_sha256")
    ):
        raise BaseBoardInstalledMetrologyError("ARM-248 protocol changed")
    return _digest(claimed, "protocol hash")


def create_session(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact editable ARM-248 session without inventing values."""

    _validate_protocol(protocol)
    return copy.deepcopy(protocol["session_template"])


def _audit_number(
    value: object,
    path: str,
    missing: list[str],
    invalid: list[str],
    *,
    positive: bool = False,
) -> bool:
    if value is None:
        missing.append(path)
        return False
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or (positive and float(value) <= 0.0)
    ):
        invalid.append(path)
        return False
    return True


def audit_session(
    protocol: Mapping[str, Any], session: Mapping[str, Any]
) -> dict[str, Any]:
    """Audit one editable session without compiling or accessing hardware."""

    protocol_hash = _validate_protocol(protocol)
    expected_top = {
        "schema",
        "source_evidence_pack_sha256",
        "instrument_identity",
        "instrument_resolution_mm",
        "observer",
        "reviewer",
        "reviewer_decision",
        "frame_B_registration_verified",
        "readings_mm",
    }
    missing_capture: list[str] = []
    invalid: list[str] = []
    review_blockers: list[str] = []
    completed_readings = 0
    if set(session) != expected_top:
        invalid.append("/")
    if session.get("schema") != SESSION_SCHEMA:
        invalid.append("/schema")
    if (
        session.get("source_evidence_pack_sha256")
        != protocol.get("source_evidence_pack_sha256")
    ):
        invalid.append("/source_evidence_pack_sha256")

    instrument = session.get("instrument_identity")
    if instrument is None:
        missing_capture.append("/instrument_identity")
    elif not isinstance(instrument, str) or not instrument.strip():
        invalid.append("/instrument_identity")
    resolution_valid = _audit_number(
        session.get("instrument_resolution_mm"),
        "/instrument_resolution_mm",
        missing_capture,
        invalid,
        positive=True,
    )
    observer = session.get("observer")
    if observer is None:
        missing_capture.append("/observer")
    elif not isinstance(observer, str) or not observer.strip():
        invalid.append("/observer")
    frame_verified = session.get("frame_B_registration_verified")
    if frame_verified is None:
        missing_capture.append("/frame_B_registration_verified")
    elif frame_verified is not True:
        invalid.append("/frame_B_registration_verified")

    reviewer = session.get("reviewer")
    if reviewer is None:
        review_blockers.append("/reviewer")
    elif not isinstance(reviewer, str) or not reviewer.strip():
        invalid.append("/reviewer")
    elif (
        isinstance(observer, str)
        and observer.strip()
        and reviewer.casefold() == observer.casefold()
    ):
        invalid.append("/reviewer")
    decision = session.get("reviewer_decision")
    if decision != "ACCEPTED_MEASURED":
        if decision == "PENDING":
            review_blockers.append("/reviewer_decision")
        else:
            invalid.append("/reviewer_decision")

    readings = session.get("readings_mm")
    scalar_shapes = {
        "board_width": (3, True),
        "board_depth": (3, True),
        "board_thickness": (3, True),
        "board_top_surface_deviation": (9, False),
    }
    vector_fields = (
        "base_origin_B",
        "base_x_datum_B",
        "base_y_datum_B",
        "clamp_min_B",
        "clamp_max_B",
    )
    expected_readings = set(scalar_shapes) | set(vector_fields)
    if not isinstance(readings, Mapping) or set(readings) != expected_readings:
        invalid.append("/readings_mm")
        readings = {}
    for field, (count, positive) in scalar_shapes.items():
        values = readings.get(field)
        if not isinstance(values, list) or len(values) != count:
            invalid.append(f"/readings_mm/{field}")
            continue
        for index, value in enumerate(values):
            if _audit_number(
                value,
                f"/readings_mm/{field}/{index}",
                missing_capture,
                invalid,
                positive=positive,
            ):
                completed_readings += 1
    for field in vector_fields:
        rows = readings.get(field)
        if not isinstance(rows, list) or len(rows) != 3:
            invalid.append(f"/readings_mm/{field}")
            continue
        for row_index, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != 3:
                invalid.append(f"/readings_mm/{field}/{row_index}")
                continue
            for column_index, value in enumerate(row):
                if _audit_number(
                    value,
                    f"/readings_mm/{field}/{row_index}/{column_index}",
                    missing_capture,
                    invalid,
                ):
                    completed_readings += 1

    if not missing_capture and not invalid and resolution_valid:
        resolution = float(session["instrument_resolution_mm"])
        try:
            origin, _ = _vector_repeats(
                readings["base_origin_B"], "base origin", resolution
            )
            x_datum, _ = _vector_repeats(
                readings["base_x_datum_B"], "base +x datum", resolution
            )
            y_datum, _ = _vector_repeats(
                readings["base_y_datum_B"], "base +y datum", resolution
            )
            clamp_min, _ = _vector_repeats(
                readings["clamp_min_B"], "clamp minimum", resolution
            )
            clamp_max, _ = _vector_repeats(
                readings["clamp_max_B"], "clamp maximum", resolution
            )
            _rotation_from_datums(origin, x_datum, y_datum)
            if any(high <= low for low, high in zip(clamp_min, clamp_max)):
                invalid.extend(
                    ["/readings_mm/clamp_min_B", "/readings_mm/clamp_max_B"]
                )
        except BaseBoardInstalledMetrologyError as exc:
            invalid.append(f"/readings_mm: {exc}")

    missing_capture = sorted(set(missing_capture))
    invalid = sorted(set(invalid))
    review_blockers = sorted(set(review_blockers))
    if invalid:
        status = "BLOCKED_INVALID_SESSION"
    elif missing_capture:
        status = "BLOCKED_CAPTURE_FIELDS_REQUIRED"
    elif review_blockers:
        status = "BLOCKED_INDEPENDENT_REVIEW_REQUIRED"
    else:
        status = "READY_FOR_ARM248_COMPILATION"
    core: dict[str, Any] = {
        "schema": AUDIT_SCHEMA,
        "status": status,
        "source_protocol_sha256": protocol_hash,
        "completed_reading_count": completed_readings,
        "required_reading_count": 63,
        "missing_capture_fields": missing_capture,
        "invalid_fields": invalid,
        "independent_review_blockers": review_blockers,
        "compiler_ready": status == "READY_FOR_ARM248_COMPILATION",
        "values_inferred": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "next_required_stage": (
            "RUN_ARM248_COMPILER"
            if status == "READY_FOR_ARM248_COMPILATION"
            else "RESOLVE_REPORTED_FIELDS"
        ),
    }
    return {**core, "audit_sha256": _sha(core)}


def _scalar_repeats(
    value: object, label: str, resolution: float, *, positive: bool = False
) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise BaseBoardInstalledMetrologyError(f"{label} must contain three readings")
    readings = [_number(item, f"{label}[{index}]", positive=positive) for index, item in enumerate(value)]
    mean = sum(readings) / 3.0
    uncertainty = max(abs(item - mean) for item in readings) + resolution
    return mean, uncertainty


def _vector_repeats(
    value: object, label: str, resolution: float
) -> tuple[list[float], float]:
    if not isinstance(value, list) or len(value) != 3:
        raise BaseBoardInstalledMetrologyError(f"{label} must contain three vectors")
    rows: list[list[float]] = []
    for row_index, row in enumerate(value):
        if not isinstance(row, list) or len(row) != 3:
            raise BaseBoardInstalledMetrologyError(f"{label}[{row_index}] must be xyz")
        rows.append(
            [_number(item, f"{label}[{row_index}][{index}]") for index, item in enumerate(row)]
        )
    mean = [sum(row[index] for row in rows) / 3.0 for index in range(3)]
    uncertainty = max(
        abs(row[index] - mean[index]) for row in rows for index in range(3)
    ) + resolution
    return mean, uncertainty


def _subtract(left: Sequence[float], right: Sequence[float]) -> list[float]:
    return [left[index] - right[index] for index in range(3)]


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(left[index] * right[index] for index in range(3))


def _normalize(vector: Sequence[float], label: str) -> list[float]:
    norm = math.sqrt(_dot(vector, vector))
    if norm <= 1e-9:
        raise BaseBoardInstalledMetrologyError(f"{label} datum is coincident")
    return [item / norm for item in vector]


def _cross(left: Sequence[float], right: Sequence[float]) -> list[float]:
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _rotation_from_datums(
    origin: Sequence[float], x_datum: Sequence[float], y_datum: Sequence[float]
) -> list[float]:
    x_axis = _normalize(_subtract(x_datum, origin), "base +x")
    y_seed = _subtract(y_datum, origin)
    y_orthogonal = [y_seed[index] - _dot(y_seed, x_axis) * x_axis[index] for index in range(3)]
    y_axis = _normalize(y_orthogonal, "base +y")
    z_axis = _normalize(_cross(x_axis, y_axis), "base +z")
    return [
        x_axis[0], y_axis[0], z_axis[0],
        x_axis[1], y_axis[1], z_axis[1],
        x_axis[2], y_axis[2], z_axis[2],
    ]


def compile_session(
    pack: Mapping[str, Any],
    session: Mapping[str, Any],
    *,
    session_file_sha256: str,
    session_reference: str,
) -> dict[str, Any]:
    """Compile independently reviewed repeated readings into ARM-246 input."""

    pack_hash = _validate_pack(pack)
    expected = {
        "schema", "source_evidence_pack_sha256", "instrument_identity",
        "instrument_resolution_mm", "observer", "reviewer", "reviewer_decision",
        "frame_B_registration_verified", "readings_mm",
    }
    if set(session) != expected or session.get("schema") != SESSION_SCHEMA:
        raise BaseBoardInstalledMetrologyError("measurement session fields differ")
    if session.get("source_evidence_pack_sha256") != pack_hash:
        raise BaseBoardInstalledMetrologyError("measurement session lineage changed")
    observer = _text(session.get("observer"), "observer")
    reviewer = _text(session.get("reviewer"), "reviewer")
    if observer.casefold() == reviewer.casefold():
        raise BaseBoardInstalledMetrologyError("reviewer must differ from observer")
    if session.get("reviewer_decision") != "ACCEPTED_MEASURED":
        raise BaseBoardInstalledMetrologyError("measurement session is not accepted")
    if session.get("frame_B_registration_verified") is not True:
        raise BaseBoardInstalledMetrologyError("frame B registration is not verified")
    instrument = _text(session.get("instrument_identity"), "instrument identity")
    resolution = _number(session.get("instrument_resolution_mm"), "instrument resolution", positive=True)
    readings = session.get("readings_mm")
    required_readings = {
        "board_width", "board_depth", "board_thickness",
        "board_top_surface_deviation", "base_origin_B", "base_x_datum_B",
        "base_y_datum_B", "clamp_min_B", "clamp_max_B",
    }
    if not isinstance(readings, Mapping) or set(readings) != required_readings:
        raise BaseBoardInstalledMetrologyError("measurement reading fields differ")

    width, width_u = _scalar_repeats(readings["board_width"], "board width", resolution, positive=True)
    depth, depth_u = _scalar_repeats(readings["board_depth"], "board depth", resolution, positive=True)
    thickness, thickness_u = _scalar_repeats(readings["board_thickness"], "board thickness", resolution, positive=True)
    deviations = readings["board_top_surface_deviation"]
    if not isinstance(deviations, list) or len(deviations) != 9:
        raise BaseBoardInstalledMetrologyError("board bow grid must contain nine readings")
    deviation_values = [_number(item, f"board bow grid[{index}]") for index, item in enumerate(deviations)]
    bow_bound = max(abs(item) for item in deviation_values) + resolution

    origin, origin_u = _vector_repeats(readings["base_origin_B"], "base origin", resolution)
    x_datum, x_u = _vector_repeats(readings["base_x_datum_B"], "base +x datum", resolution)
    y_datum, y_u = _vector_repeats(readings["base_y_datum_B"], "base +y datum", resolution)
    clamp_min, min_u = _vector_repeats(readings["clamp_min_B"], "clamp minimum", resolution)
    clamp_max, max_u = _vector_repeats(readings["clamp_max_B"], "clamp maximum", resolution)
    if any(high <= low for low, high in zip(clamp_min, clamp_max)):
        raise BaseBoardInstalledMetrologyError("clamp maximum must exceed minimum")
    rotation = _rotation_from_datums(origin, x_datum, y_datum)

    session_hash = _digest(session_file_sha256, "measurement session file hash")
    draft = copy.deepcopy(pack["observation_draft"])
    context_sources = draft.get("evidence_sources")
    if not isinstance(context_sources, list):
        raise BaseBoardInstalledMetrologyError("ARM-247 evidence sources changed")
    draft.update(
        {
            "schema": OBSERVATION_SCHEMA,
            "instrument_identity": instrument,
            "instrument_resolution_mm": resolution,
            "observer": observer,
            "reviewer": reviewer,
            "reviewer_decision": "ACCEPTED_MEASURED",
        }
    )
    draft["evidence_sources"] = context_sources + [
        {"source_file_sha256": session_hash, "source_reference": _text(session_reference, "session reference")}
    ]
    draft["board"] = {
        "accepted_source_hash": session_hash,
        "frame_B_registration_verified": True,
        "width_mm": width,
        "depth_mm": depth,
        "thickness_mm": thickness,
        "flatness_or_bow_bound_mm": bow_bound,
        "geometry_uncertainty_mm": max(width_u, depth_u, thickness_u),
    }
    draft["base_and_factory_clamp"] = {
        "accepted_source_hash": session_hash,
        "base_origin_B_mm": origin,
        "base_rotation_row_major": rotation,
        "clamp_min_B_mm": clamp_min,
        "clamp_max_B_mm": clamp_max,
        "geometry_uncertainty_mm": max(origin_u, x_u, y_u, min_u, max_u),
    }
    return draft


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise BaseBoardInstalledMetrologyError(f"{path} is not a JSON object")
    return value


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--evidence-pack", type=Path)
    source.add_argument("--protocol", type=Path)
    parser.add_argument("--session", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.protocol is not None:
        protocol = _load(args.protocol.resolve(strict=True))
        if args.session is None:
            result = create_session(protocol)
        else:
            result = audit_session(protocol, _load(args.session.resolve(strict=True)))
    else:
        pack = _load(args.evidence_pack.resolve(strict=True))
        if args.session is None:
            result = build_protocol(pack)
        else:
            session_path = args.session.resolve(strict=True)
            result = compile_session(
                pack,
                _load(session_path),
                session_file_sha256=hashlib.sha256(session_path.read_bytes()).hexdigest(),
                session_reference=session_path.name,
            )
    _write_new(args.output.resolve(), result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
