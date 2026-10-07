"""Validate installed-collision measurements and render a capture worksheet.

This is the ICQ-1 boundary.  It inventories the exact required bodies from the
active collision contract, validates hash-bound measurement records, and
reports whether the records are complete enough for a separately reviewed
profile builder.  It never creates that profile, evaluates collision, opens a
device, or grants physical authority.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from rocell.simulation.collision import (
    HARD_MAX_BODIES,
    HARD_MAX_PRIMITIVES_PER_BODY,
    CollisionBindingMode,
    CollisionGeometryContract,
)

from .collision_readiness import assess_current_collision_readiness
from .context import SimulationContext, load_simulation_context


SCHEMA = "rocell.installed_collision_measurement_manifest.v1"
REPORT_SCHEMA = "rocell.installed_collision_measurement_validation.v1"
READY_STATUS = "READY_FOR_INSTALLED_PROFILE_BUILD"
BLOCKED_STATUS = "BLOCKED_INCOMPLETE_INSTALLED_MEASUREMENTS"
MAX_MANIFEST_BYTES = 1_048_576
MEASUREMENT_METHODS = frozenset({
    "CALIPER",
    "TAPE_MEASURE",
    "FIXTURE_GAUGE",
    "PHOTOGRAMMETRY",
    "CAD_DERIVED_AND_PHYSICALLY_VERIFIED",
    "OTHER_REVIEWED",
})
BODY_STATUSES = frozenset({"MEASURED", "PENDING", "DECLARED_ABSENT"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ROOT_FIELDS = {
    "schema", "measurement_manifest_id", "captured_at_utc",
    "manifest_id", "manifest_sha256", "active_build_id",
    "build_snapshot_sha256", "robot_model_sha256",
    "base_contract_sha256", "root_frame", "sources",
    "body_measurements", "clearance_measurement", "content_sha256",
}
_SOURCE_FIELDS = {
    "source_id", "sha256", "measurement_method", "captured_at_utc",
    "instrument_id", "instrument_resolution_mm", "notes",
}
_BODY_FIELDS = {
    "body_id", "parent_frame", "role", "binding_mode", "status",
    "source_ids", "coordinate_frame", "units", "geometry_uncertainty_mm",
    "envelope_primitives", "notes",
}
_CLEARANCE_FIELDS = {
    "status", "source_ids", "minimum_separation_mm",
    "geometry_uncertainty_mm_per_body", "pose_uncertainty_mm_per_body",
    "notes",
}


class InstalledCollisionMeasurementManifestV1Error(ValueError):
    """The measurement manifest is malformed, crossed, or unbounded."""


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
        raise InstalledCollisionMeasurementManifestV1Error(
            "measurement manifest is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _exact(value: object, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InstalledCollisionMeasurementManifestV1Error(
            f"{label} must be an object"
        )
    actual = set(value)
    if actual != fields:
        raise InstalledCollisionMeasurementManifestV1Error(
            f"{label} fields differ: missing={sorted(fields - actual)}, "
            f"unexpected={sorted(actual - fields)}"
        )
    return value


def _text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise InstalledCollisionMeasurementManifestV1Error(
            f"{label} must be text"
        )
    return value.strip()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise InstalledCollisionMeasurementManifestV1Error(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _utc(value: object, label: str) -> str:
    text = _text(value, label)
    if not text.endswith("Z"):
        raise InstalledCollisionMeasurementManifestV1Error(
            f"{label} must be UTC with a Z suffix"
        )
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise InstalledCollisionMeasurementManifestV1Error(
            f"{label} is not an ISO-8601 timestamp"
        ) from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise InstalledCollisionMeasurementManifestV1Error(
            f"{label} is not UTC"
        )
    return text


def _number(
    value: object,
    label: str,
    *,
    positive: bool = False,
    nullable: bool = False,
) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InstalledCollisionMeasurementManifestV1Error(
            f"{label} must be numeric"
        )
    result = float(value)
    if not math.isfinite(result) or result < 0.0 or (positive and result <= 0.0):
        raise InstalledCollisionMeasurementManifestV1Error(
            f"{label} is outside its finite range"
        )
    return result


def _vec(value: object, label: str, *, positive: bool = False) -> list[float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 3
    ):
        raise InstalledCollisionMeasurementManifestV1Error(
            f"{label} must contain three numbers"
        )
    return [float(_number(item, label, positive=positive)) for item in value]


def _primitive(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise InstalledCollisionMeasurementManifestV1Error(
            f"{label} must be an object"
        )
    kind = value.get("kind")
    if kind == "sphere":
        row = _exact(value, {"kind", "center_mm", "radius_mm"}, label)
        return {
            "kind": kind,
            "center_mm": _vec(row["center_mm"], f"{label}.center_mm"),
            "radius_mm": _number(row["radius_mm"], f"{label}.radius_mm", positive=True),
        }
    if kind == "capsule":
        row = _exact(
            value, {"kind", "start_mm", "end_mm", "radius_mm"}, label
        )
        return {
            "kind": kind,
            "start_mm": _vec(row["start_mm"], f"{label}.start_mm"),
            "end_mm": _vec(row["end_mm"], f"{label}.end_mm"),
            "radius_mm": _number(row["radius_mm"], f"{label}.radius_mm", positive=True),
        }
    if kind == "oriented_box":
        row = _exact(
            value,
            {"kind", "center_mm", "half_extents_mm", "rotation_row_major"},
            label,
        )
        rotation = row["rotation_row_major"]
        if (
            not isinstance(rotation, Sequence)
            or isinstance(rotation, (str, bytes))
            or len(rotation) != 9
        ):
            raise InstalledCollisionMeasurementManifestV1Error(
                f"{label}.rotation_row_major must contain nine numbers"
            )
        return {
            "kind": kind,
            "center_mm": _vec(row["center_mm"], f"{label}.center_mm"),
            "half_extents_mm": _vec(
                row["half_extents_mm"], f"{label}.half_extents_mm", positive=True
            ),
            "rotation_row_major": [
                float(_number(item, f"{label}.rotation_row_major"))
                for item in rotation
            ],
        }
    raise InstalledCollisionMeasurementManifestV1Error(
        f"{label} has unsupported primitive kind {kind!r}"
    )


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise InstalledCollisionMeasurementManifestV1Error(
            f"{label} must be an array"
        )
    rows = [_text(item, label) for item in value]
    if len(set(rows)) != len(rows):
        raise InstalledCollisionMeasurementManifestV1Error(
            f"{label} contains duplicates"
        )
    return rows


def _load_json(path: Path, expected_file_sha256: str) -> tuple[dict[str, Any], str]:
    expected = _digest(expected_file_sha256, "expected_file_sha256")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise InstalledCollisionMeasurementManifestV1Error(
            f"cannot read measurement manifest {path}"
        ) from exc
    if len(payload) > MAX_MANIFEST_BYTES:
        raise InstalledCollisionMeasurementManifestV1Error(
            "measurement manifest exceeds byte limit"
        )
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise InstalledCollisionMeasurementManifestV1Error(
            "measurement manifest file hash mismatch"
        )

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise InstalledCollisionMeasurementManifestV1Error(
                    f"duplicate JSON key {key!r}"
                )
            result[key] = value
        return result

    try:
        document = json.loads(payload, object_pairs_hook=unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstalledCollisionMeasurementManifestV1Error(
            "measurement manifest is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(document, dict):
        raise InstalledCollisionMeasurementManifestV1Error(
            "measurement manifest root must be an object"
        )
    return document, actual


def validate_installed_collision_measurement_manifest_v1(
    document: Mapping[str, Any],
    *,
    contract: CollisionGeometryContract,
    expected_manifest_id: str,
    expected_manifest_sha256: str,
    expected_active_build_id: str,
    expected_build_snapshot_sha256: str,
    expected_robot_model_sha256: str,
    file_sha256: str,
) -> dict[str, Any]:
    """Validate one measurement manifest and return a zero-authority report."""

    root = _exact(document, _ROOT_FIELDS, "measurement manifest")
    if root["schema"] != SCHEMA:
        raise InstalledCollisionMeasurementManifestV1Error(
            "measurement manifest schema mismatch"
        )
    unsigned = dict(root)
    supplied_content_hash = _digest(unsigned.pop("content_sha256"), "content_sha256")
    if _sha(unsigned) != supplied_content_hash:
        raise InstalledCollisionMeasurementManifestV1Error(
            "measurement manifest content hash mismatch"
        )
    manifest_id = _text(root["measurement_manifest_id"], "measurement_manifest_id")
    captured_at = _utc(root["captured_at_utc"], "captured_at_utc")
    bindings = {
        "manifest_id": (_text(root["manifest_id"], "manifest_id"), expected_manifest_id),
        "manifest_sha256": (
            _digest(root["manifest_sha256"], "manifest_sha256"),
            _digest(expected_manifest_sha256, "expected_manifest_sha256"),
        ),
        "active_build_id": (
            _text(root["active_build_id"], "active_build_id"),
            _text(expected_active_build_id, "expected_active_build_id"),
        ),
        "build_snapshot_sha256": (
            _digest(root["build_snapshot_sha256"], "build_snapshot_sha256"),
            _digest(expected_build_snapshot_sha256, "expected_build_snapshot_sha256"),
        ),
        "robot_model_sha256": (
            _digest(root["robot_model_sha256"], "robot_model_sha256"),
            _digest(expected_robot_model_sha256, "expected_robot_model_sha256"),
        ),
        "base_contract_sha256": (
            _digest(root["base_contract_sha256"], "base_contract_sha256"),
            contract.content_hash,
        ),
        "root_frame": (
            _text(root["root_frame"], "root_frame"),
            contract.root_frame,
        ),
    }
    mismatched = [name for name, (actual, expected) in bindings.items() if actual != expected]
    if mismatched:
        raise InstalledCollisionMeasurementManifestV1Error(
            "measurement manifest context binding mismatch: " + ", ".join(mismatched)
        )

    sources_value = root["sources"]
    if not isinstance(sources_value, list) or len(sources_value) > 256:
        raise InstalledCollisionMeasurementManifestV1Error(
            "sources must be an array of at most 256 records"
        )
    sources: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(sources_value):
        row = _exact(value, _SOURCE_FIELDS, f"source {index}")
        source_id = _text(row["source_id"], f"source {index}.source_id")
        if source_id in sources:
            raise InstalledCollisionMeasurementManifestV1Error(
                f"duplicate source id {source_id!r}"
            )
        method = _text(row["measurement_method"], f"source {index}.measurement_method")
        if method not in MEASUREMENT_METHODS:
            raise InstalledCollisionMeasurementManifestV1Error(
                f"source {source_id} measurement method is unsupported"
            )
        source_captured = _utc(row["captured_at_utc"], f"source {source_id}.captured_at_utc")
        if source_captured > captured_at:
            raise InstalledCollisionMeasurementManifestV1Error(
                f"source {source_id} is newer than the manifest"
            )
        sources[source_id] = {
            "source_id": source_id,
            "sha256": _digest(row["sha256"], f"source {source_id}.sha256"),
            "measurement_method": method,
            "captured_at_utc": source_captured,
            "instrument_id": _text(row["instrument_id"], f"source {source_id}.instrument_id"),
            "instrument_resolution_mm": _number(
                row["instrument_resolution_mm"],
                f"source {source_id}.instrument_resolution_mm",
                positive=True,
            ),
            "notes": _text(row["notes"], f"source {source_id}.notes", allow_empty=True),
        }

    bodies_value = root["body_measurements"]
    if not isinstance(bodies_value, list) or len(bodies_value) > HARD_MAX_BODIES:
        raise InstalledCollisionMeasurementManifestV1Error(
            "body_measurements exceeds the collision body limit"
        )
    requirements = {item.body_id: item for item in contract.requirements}
    bodies: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    for index, value in enumerate(bodies_value):
        row = _exact(value, _BODY_FIELDS, f"body measurement {index}")
        body_id = _text(row["body_id"], f"body measurement {index}.body_id")
        if body_id in bodies:
            raise InstalledCollisionMeasurementManifestV1Error(
                f"duplicate body measurement {body_id!r}"
            )
        requirement = requirements.get(body_id)
        if requirement is None:
            raise InstalledCollisionMeasurementManifestV1Error(
                f"unexpected body measurement {body_id!r}"
            )
        if (
            row["parent_frame"] != requirement.parent_frame
            or row["role"] != requirement.role.value
            or row["binding_mode"] != requirement.binding_mode.value
            or row["coordinate_frame"] != requirement.parent_frame
            or row["units"] != "mm"
        ):
            raise InstalledCollisionMeasurementManifestV1Error(
                f"body {body_id} frame, role, binding mode, or units differ"
            )
        status = _text(row["status"], f"body {body_id}.status")
        if status not in BODY_STATUSES:
            raise InstalledCollisionMeasurementManifestV1Error(
                f"body {body_id} status is unsupported"
            )
        source_ids = _string_list(row["source_ids"], f"body {body_id}.source_ids")
        unknown_sources = sorted(set(source_ids) - set(sources))
        if unknown_sources:
            raise InstalledCollisionMeasurementManifestV1Error(
                f"body {body_id} references unknown sources {unknown_sources}"
            )
        primitives_value = row["envelope_primitives"]
        if (
            not isinstance(primitives_value, list)
            or len(primitives_value) > HARD_MAX_PRIMITIVES_PER_BODY
        ):
            raise InstalledCollisionMeasurementManifestV1Error(
                f"body {body_id} primitive count exceeds its limit"
            )
        primitives = [
            _primitive(item, f"body {body_id} primitive {primitive_index}")
            for primitive_index, item in enumerate(primitives_value)
        ]
        uncertainty = _number(
            row["geometry_uncertainty_mm"],
            f"body {body_id}.geometry_uncertainty_mm",
            nullable=True,
        )
        if status == "MEASURED":
            if not source_ids or uncertainty is None:
                raise InstalledCollisionMeasurementManifestV1Error(
                    f"measured body {body_id} lacks sources or uncertainty"
                )
            if requirement.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED:
                if primitives:
                    raise InstalledCollisionMeasurementManifestV1Error(
                        f"configuration-sampled body {body_id} must not store static primitives"
                    )
            elif not primitives:
                raise InstalledCollisionMeasurementManifestV1Error(
                    f"measured body {body_id} lacks envelope primitives"
                )
        else:
            if primitives or uncertainty is not None:
                raise InstalledCollisionMeasurementManifestV1Error(
                    f"incomplete body {body_id} cannot claim geometry or uncertainty"
                )
            if status == "PENDING" and source_ids:
                raise InstalledCollisionMeasurementManifestV1Error(
                    f"pending body {body_id} cannot claim measurement sources"
                )
            if status == "DECLARED_ABSENT" and not source_ids:
                raise InstalledCollisionMeasurementManifestV1Error(
                    f"absent body {body_id} requires a reviewed source"
                )
            blockers.append(f"{status}:{body_id}")
        bodies[body_id] = {
            "body_id": body_id,
            "status": status,
            "source_ids": source_ids,
            "geometry_uncertainty_mm": uncertainty,
            "envelope_primitives": primitives,
        }

    missing = sorted(set(requirements) - set(bodies))
    blockers.extend(f"MISSING:{body_id}" for body_id in missing)

    clearance = _exact(
        root["clearance_measurement"], _CLEARANCE_FIELDS, "clearance_measurement"
    )
    clearance_status = _text(clearance["status"], "clearance_measurement.status")
    if clearance_status not in {"PENDING", "ACCEPTED_MEASURED"}:
        raise InstalledCollisionMeasurementManifestV1Error(
            "clearance measurement status is unsupported"
        )
    clearance_sources = _string_list(
        clearance["source_ids"], "clearance_measurement.source_ids"
    )
    unknown_clearance_sources = sorted(set(clearance_sources) - set(sources))
    if unknown_clearance_sources:
        raise InstalledCollisionMeasurementManifestV1Error(
            f"clearance measurement references unknown sources {unknown_clearance_sources}"
        )
    separation = _number(
        clearance["minimum_separation_mm"],
        "clearance_measurement.minimum_separation_mm",
        nullable=True,
    )
    geometry_uncertainty = _number(
        clearance["geometry_uncertainty_mm_per_body"],
        "clearance_measurement.geometry_uncertainty_mm_per_body",
        nullable=True,
    )
    pose_uncertainty = _number(
        clearance["pose_uncertainty_mm_per_body"],
        "clearance_measurement.pose_uncertainty_mm_per_body",
        nullable=True,
    )
    clearance_numbers = (separation, geometry_uncertainty, pose_uncertainty)
    if clearance_status == "ACCEPTED_MEASURED":
        if (
            not clearance_sources
            or any(value is None for value in clearance_numbers)
            or sum(float(value) for value in clearance_numbers if value is not None) <= 0.0
        ):
            raise InstalledCollisionMeasurementManifestV1Error(
                "accepted clearance measurement is incomplete or all-zero"
            )
    else:
        if clearance_sources or any(value is not None for value in clearance_numbers):
            raise InstalledCollisionMeasurementManifestV1Error(
                "pending clearance measurement cannot claim sources or values"
            )
        blockers.append("PENDING:CLEARANCE_POLICY")

    measured_ids = sorted(
        body_id for body_id, row in bodies.items() if row["status"] == "MEASURED"
    )
    pending_ids = sorted(
        body_id for body_id, row in bodies.items() if row["status"] == "PENDING"
    )
    absent_ids = sorted(
        body_id
        for body_id, row in bodies.items()
        if row["status"] == "DECLARED_ABSENT"
    )
    status = READY_STATUS if not blockers else BLOCKED_STATUS
    core: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": status,
        "measurement_manifest_id": manifest_id,
        "measurement_manifest_sha256": supplied_content_hash,
        "measurement_manifest_file_sha256": _digest(file_sha256, "file_sha256"),
        "base_contract_sha256": contract.content_hash,
        "required_body_count": len(requirements),
        "measured_body_count": len(measured_ids),
        "measured_body_ids": measured_ids,
        "pending_body_ids": pending_ids,
        "declared_absent_body_ids": absent_ids,
        "missing_body_ids": missing,
        "source_count": len(sources),
        "clearance_status": clearance_status,
        "blockers": sorted(blockers),
        "profile_generated": False,
        "collision_screening_executed": False,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "validation_report_sha256": _sha(core)}


def load_and_validate_installed_collision_measurement_manifest_v1(
    path: str | Path,
    expected_file_sha256: str,
    *,
    context: SimulationContext,
) -> dict[str, Any]:
    """Load one exact file and validate it against the active context."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    readiness = assess_current_collision_readiness(context)
    if readiness.active_build_id is None:
        raise InstalledCollisionMeasurementManifestV1Error(
            "active build id is unavailable"
        )
    document, file_hash = _load_json(Path(path), expected_file_sha256)
    return validate_installed_collision_measurement_manifest_v1(
        document,
        contract=readiness.contract,
        expected_manifest_id=readiness.manifest_id,
        expected_manifest_sha256=readiness.manifest_sha256,
        expected_active_build_id=readiness.active_build_id,
        expected_build_snapshot_sha256=readiness.build_snapshot_hash,
        expected_robot_model_sha256=readiness.urdf_sha256,
        file_sha256=file_hash,
    )


def render_installed_collision_measurement_worksheet_v1(
    contract: CollisionGeometryContract,
) -> str:
    """Render the exact required-body inventory without inventing values."""

    lines = [
        "# Installed collision measurement worksheet",
        "",
        f"- Base contract SHA-256: `{contract.content_hash}`",
        f"- Root frame: `{contract.root_frame}`",
        f"- Required bodies: {len(contract.requirements)}",
        "- Status: `UNMEASURED_TEMPLATE`",
        "- Authority: no profile, collision result, command, or physical authority",
        "",
        "Record source hashes, methods, instruments, timestamps, millimetre-valued "
        "conservative envelopes, and uncertainty in the manifest. Do not fill "
        "unknown values with nominal dimensions.",
        "",
        "| Body ID | Parent frame | Role | Binding mode | Required capture |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in contract.requirements:
        capture = (
            "baseline cable properties now; per-configuration geometry in ICQ-4"
            if item.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
            else "measured conservative envelope and uncertainty"
        )
        lines.append(
            f"| `{item.body_id}` | `{item.parent_frame}` | `{item.role.value}` | "
            f"`{item.binding_mode.value}` | {capture} |"
        )
    lines.extend([
        "",
        "## Clearance evidence",
        "",
        "Record the reviewed minimum separation, geometry uncertainty per body, "
        "pose uncertainty per body, and their source hashes. An all-zero or "
        "unsourced policy is rejected.",
        "",
        "This worksheet is read-only planning output. It does not qualify geometry.",
    ])
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--system-manifest", type=Path)
    parser.add_argument("--measurement-manifest", type=Path)
    parser.add_argument("--measurement-manifest-sha256")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    system_manifest = args.system_manifest or (
        args.workspace / "software/config/system_manifest.json"
    )
    try:
        context = load_simulation_context(args.workspace, system_manifest)
        readiness = assess_current_collision_readiness(context)
        if args.measurement_manifest is None:
            if args.measurement_manifest_sha256 is not None:
                raise InstalledCollisionMeasurementManifestV1Error(
                    "manifest SHA-256 requires a measurement manifest path"
                )
            print(render_installed_collision_measurement_worksheet_v1(readiness.contract))
            return 0
        if args.measurement_manifest_sha256 is None:
            raise InstalledCollisionMeasurementManifestV1Error(
                "measurement manifest SHA-256 is required"
            )
        report = load_and_validate_installed_collision_measurement_manifest_v1(
            args.measurement_manifest,
            args.measurement_manifest_sha256,
            context=context,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.format == "markdown":
        print(render_installed_collision_measurement_worksheet_v1(readiness.contract))
        print(f"Validation status: `{report['status']}`")
        for blocker in report["blockers"]:
            print(f"- `{blocker}`")
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == READY_STATUS else 2


__all__ = [
    "BLOCKED_STATUS",
    "BODY_STATUSES",
    "MAX_MANIFEST_BYTES",
    "MEASUREMENT_METHODS",
    "READY_STATUS",
    "REPORT_SCHEMA",
    "SCHEMA",
    "InstalledCollisionMeasurementManifestV1Error",
    "load_and_validate_installed_collision_measurement_manifest_v1",
    "main",
    "render_installed_collision_measurement_worksheet_v1",
    "validate_installed_collision_measurement_manifest_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())
