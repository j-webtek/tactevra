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
import struct
from typing import Any, Mapping, Sequence

from rocell.simulation.collision import (
    HARD_MAX_BODIES,
    HARD_MAX_PRIMITIVES_PER_BODY,
    CollisionBindingMode,
    CollisionGeometryContract,
)

from .collision_readiness import (
    assess_current_collision_readiness,
    assess_static_b0477_collision_readiness,
)
from .context import SimulationContext, load_simulation_context


SCHEMA = "rocell.installed_collision_measurement_manifest.v1"
REPORT_SCHEMA = "rocell.installed_collision_measurement_validation.v1"
NOMINAL_SOURCE_INVENTORY_SCHEMA = (
    "rocell.installed_collision_nominal_source_inventory.v1"
)
STATIC_B0477_NOMINAL_SOURCE_INVENTORY_SCHEMA = (
    "rocell.static_b0477_collision_nominal_source_inventory.v2"
)
NOMINAL_ENVELOPE_AUDIT_SCHEMA = "rocell.installed_collision_nominal_envelope_audit.v1"
NOMINAL_PROXY_AUDIT_SCHEMA = "rocell.installed_collision_nominal_proxy_audit.v1"
_BINARY_STL_COMPARISON_TOLERANCE_MM = 0.001
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

_NOMINAL_SOURCE_PATHS = {
    "robot": ("software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf",),
    "layout": ("active-project/RoCell_v0_3/config/workcell_layout.json",),
    "board": (
        "active-project/RoCell_v0_3/config/workcell_layout.json",
        "active-project/RoCell_v0_3/cad/step/board_610x457x18_RC03.step",
    ),
    "keyboard_station_left": (
        "active-project/RoCell_v0_3/config/workcell_layout.json",
        "active-project/RoCell_v0_3/stl/keyboard_station_left.stl",
    ),
    "keyboard_station_right": (
        "active-project/RoCell_v0_3/config/workcell_layout.json",
        "active-project/RoCell_v0_3/stl/keyboard_station_right.stl",
    ),
    "phone_tcp_station": (
        "active-project/RoCell_v0_3/config/workcell_layout.json",
        "active-project/RoCell_v0_3/stl/phone_tcp_station.stl",
    ),
    "contact_tool": (
        "active-project/RoCell_v0_3/stl/compliant_tool_body.stl",
        "active-project/RoCell_v0_3/stl/compliant_tool_top_cap.stl",
    ),
    "camera_support": (
        "hardware/static_overhead_camera/config/support_design.json",
        "active-project/RoCell_v0_3/stl/camera_plate_universal.stl",
    ),
    "camera_module": (
        "software/config/camera_profiles/arducam_b0477_imx283_16mm.json",
        "hardware/static_overhead_camera/config/support_design.json",
    ),
    "arm_harness": ("software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf",),
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
    nonnegative: bool = False,
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
    if (
        not math.isfinite(result)
        or (nonnegative and result < 0.0)
        or (positive and result <= 0.0)
    ):
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
            nonnegative=True,
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
        nonnegative=True,
        nullable=True,
    )
    geometry_uncertainty = _number(
        clearance["geometry_uncertainty_mm_per_body"],
        "clearance_measurement.geometry_uncertainty_mm_per_body",
        nonnegative=True,
        nullable=True,
    )
    pose_uncertainty = _number(
        clearance["pose_uncertainty_mm_per_body"],
        "clearance_measurement.pose_uncertainty_mm_per_body",
        nonnegative=True,
        nullable=True,
    )
    clearance_numbers = (separation, geometry_uncertainty, pose_uncertainty)
    if clearance_status == "ACCEPTED_MEASURED":
        if (
            not clearance_sources
            or any(value is None for value in clearance_numbers)
            or separation is None
            or separation <= 0.0
        ):
            raise InstalledCollisionMeasurementManifestV1Error(
                "accepted clearance measurement is incomplete or nonpositive"
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

    _, report = load_installed_collision_measurement_manifest_v1(
        path,
        expected_file_sha256,
        context=context,
    )
    return report


def load_installed_collision_measurement_manifest_v1(
    path: str | Path,
    expected_file_sha256: str,
    *,
    context: SimulationContext,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load, strictly validate, and return one exact manifest plus its report.

    The returned document is the same strictly parsed, content-addressed input
    that produced the report.  This lets downstream zero-authority builders
    consume one interpretation of the manifest instead of reparsing it.
    """

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    readiness = assess_current_collision_readiness(context)
    if readiness.active_build_id is None:
        raise InstalledCollisionMeasurementManifestV1Error(
            "active build id is unavailable"
        )
    document, file_hash = _load_json(Path(path), expected_file_sha256)
    report = validate_installed_collision_measurement_manifest_v1(
        document,
        contract=readiness.contract,
        expected_manifest_id=readiness.manifest_id,
        expected_manifest_sha256=readiness.manifest_sha256,
        expected_active_build_id=readiness.active_build_id,
        expected_build_snapshot_sha256=readiness.build_snapshot_hash,
        expected_robot_model_sha256=readiness.urdf_sha256,
        file_sha256=file_hash,
    )
    return document, report


def build_installed_collision_nominal_source_inventory_v1(
    context: SimulationContext,
) -> dict[str, Any]:
    """Inventory nominal geometry without promoting it to measured evidence."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    readiness = assess_current_collision_readiness(context)
    layout_path = context.scenario.workcell_layout_path
    try:
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstalledCollisionMeasurementManifestV1Error(
            "cannot read nominal workcell layout"
        ) from exc
    board = layout["board"]
    devices = layout["devices"]
    stations = layout["stations"]

    body_plan = {
        **{
            f"robot:{name}": (
                "NOMINAL_GEOMETRY_AVAILABLE", "robot",
                "Verify received arm identity, installed base transform, and link envelopes.",
                None,
            )
            for name in ("base_link", "link1", "link2", "link3", "link4", "link5", "gripper")
        },
        "installation:base_and_factory_clamp": (
            "PARTIAL_NOMINAL_GEOMETRY", "layout",
            "Capture installed clamp/base extents and board-relative transform.", None,
        ),
        "attachment:camera_holder": (
            "PARTIAL_NOMINAL_GEOMETRY", "camera_support",
            "After the tower is built, capture holder extents and its rigid transform.", None,
        ),
        "attachment:camera_module": (
            "PUBLISHED_AND_CONCEPT_GEOMETRY_ONLY", "camera_module",
            "After installation, verify the received case, lens, pose, and conservative envelope.", None,
        ),
        "attachment:camera_connector": (
            "PARTIAL_NOMINAL_GEOMETRY", "camera_module",
            "After installation, capture connector, strain relief, and rigid transform.", None,
        ),
        "attachment:moving_camera_cable": (
            "CONFIGURATION_MODEL_PENDING", "camera_module",
            "Capture cable diameter, routing, slack, anchors, and configuration samples for ICQ-4.", None,
        ),
        "attachment:contact_tool": (
            "NOMINAL_GEOMETRY_AVAILABLE", "contact_tool",
            "Measure the assembled printed tool envelope, tip, compression range, and hand-TCP transform.", None,
        ),
        "workcell:board_solid": (
            "NOMINAL_GEOMETRY_AVAILABLE", "board",
            "Measure the installed board size, thickness, flatness, and root-frame realization.", {
                "size_mm": [board["width"], board["depth"], board["thickness"]],
                "top_surface_z_mm": board["top_surface_z"],
            },
        ),
        "workcell:keyboard": (
            "NOMINAL_ENVELOPE_AVAILABLE", "layout",
            "Top-down datum image can verify XY and yaw; measure support/top Z and conservative exterior envelope.", {
                "origin_xy_mm": devices["keyboard"]["nominal_origin_xy"],
                "size_mm": devices["keyboard"]["nominal_size"],
                "support_plane_z_mm": devices["keyboard"]["support_plane_z"],
            },
        ),
        "workcell:phone": (
            "NOMINAL_ENVELOPE_AVAILABLE", "layout",
            "Top-down datum image can verify XY and yaw; measure case/camera-bump envelope and screen Z.", {
                "origin_xy_mm": devices["phone"]["nominal_origin_xy"],
                "size_mm": devices["phone"]["configured_size"],
                "support_plane_z_mm": devices["phone"]["support_plane_z"],
                "screen_plane_z_mm": devices["phone"]["nominal_screen_plane_z"],
            },
        ),
        "workcell:station:keyboard_left": (
            "NOMINAL_GEOMETRY_AVAILABLE", "keyboard_station_left",
            "Top-down datum image can verify XY and yaw; measure printed first-article and installed Z deviations.", stations["keyboard_left"],
        ),
        "workcell:station:keyboard_right": (
            "NOMINAL_GEOMETRY_AVAILABLE", "keyboard_station_right",
            "Top-down datum image can verify XY and yaw; measure seam, printed first-article, and installed Z deviations.", stations["keyboard_right"],
        ),
        "workcell:station:phone_tcp": (
            "NOMINAL_GEOMETRY_AVAILABLE", "phone_tcp_station",
            "Top-down datum image can verify XY and yaw; measure printed first-article and installed Z deviations.", stations["phone_tcp"],
        ),
    }
    source_paths = sorted({path for paths in _NOMINAL_SOURCE_PATHS.values() for path in paths})
    sources = []
    for relative in source_paths:
        path = context.workspace / relative
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise InstalledCollisionMeasurementManifestV1Error(
                f"cannot read nominal source {relative}"
            ) from exc
        sources.append({
            "path": relative,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "physical_measurement": False,
        })
    source_hashes = {row["path"]: row["sha256"] for row in sources}
    bodies = []
    for requirement in readiness.contract.requirements:
        state, source_key, residual, placement = body_plan[requirement.body_id]
        bodies.append({
            "body_id": requirement.body_id,
            "parent_frame": requirement.parent_frame,
            "binding_mode": requirement.binding_mode.value,
            "nominal_state": state,
            "nominal_sources": [
                {"path": path, "sha256": source_hashes[path]}
                for path in _NOMINAL_SOURCE_PATHS[source_key]
            ],
            "nominal_placement": placement,
            "remaining_physical_check": residual,
            "top_down_image_useful": requirement.body_id in {
                "installation:base_and_factory_clamp", "workcell:keyboard",
                "workcell:phone", "workcell:station:keyboard_left",
                "workcell:station:keyboard_right", "workcell:station:phone_tcp",
            },
            "measured": False,
        })
    core: dict[str, Any] = {
        "schema": NOMINAL_SOURCE_INVENTORY_SCHEMA,
        "status": "NOMINAL_SIMULATION_INPUTS_AVAILABLE_PHYSICAL_VERIFICATION_PENDING",
        "base_contract_sha256": readiness.contract.content_hash,
        "robot_model_sha256": readiness.urdf_sha256,
        "source_count": len(sources),
        "sources": sources,
        "body_count": len(bodies),
        "bodies": bodies,
        "top_down_capture_requirements": [
            "Keep the camera approximately perpendicular to the board.",
            "Include all four board edges and the installed keyboard, phone, and stations.",
            "Include at least two board datum or scale references in both X and Y.",
            "Do not use the image to infer height, hidden geometry, or uncertainty.",
        ],
        "simulation_use_allowed": True,
        "installed_measurement_status": "PENDING",
        "collision_qualification": False,
        "hardware_access": False,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "content_sha256": _sha(core)}


def build_static_b0477_collision_nominal_source_inventory_v2(
    context: SimulationContext,
) -> dict[str, Any]:
    """Map v2 static-camera bodies to existing nominal, unmeasured sources."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    readiness = assess_static_b0477_collision_readiness(context)
    legacy = build_installed_collision_nominal_source_inventory_v1(context)
    legacy_rows = {row["body_id"]: row for row in legacy["bodies"]}
    source_hashes = {row["path"]: row["sha256"] for row in legacy["sources"]}

    def plan(
        state: str,
        source_key: str,
        residual: str,
        placement: object = None,
        *,
        image_useful: bool = False,
    ) -> tuple[str, str, str, object, bool]:
        return state, source_key, residual, placement, image_useful

    body_plan: dict[str, tuple[str, str, str, object, bool]] = {
        **{
            f"robot:{name}": plan(
                "NOMINAL_GEOMETRY_AVAILABLE",
                "robot",
                "Verify received arm identity, installed base transform, and link envelopes.",
            )
            for name in (
                "base_link", "link1", "link2", "link3", "link4", "link5", "gripper"
            )
        },
        "robot:contact_tool": plan(
            "NOMINAL_GEOMETRY_AVAILABLE", "contact_tool",
            "Measure the assembled tool envelope, compliance range, and rigid transform.",
        ),
        "robot:tool_tip": plan(
            "PLANNING_POINT_ONLY", "contact_tool",
            "Measure the mounted jaw-reference-to-tip transform and tip envelope.",
        ),
        "attachment:arm_harness": plan(
            "CONFIGURATION_MODEL_PENDING", "arm_harness",
            "Capture harness diameter, anchors, slack, and configuration samples.",
        ),
        "installation:base_clamp": plan(
            "PARTIAL_NOMINAL_GEOMETRY", "layout",
            "Capture installed clamp/base extents and board-relative transform.",
            image_useful=True,
        ),
        "workcell:board": plan(
            "NOMINAL_GEOMETRY_AVAILABLE", "board",
            "Measure installed size, thickness, flatness, and root-frame realization.",
            legacy_rows["workcell:board_solid"]["nominal_placement"],
            image_useful=True,
        ),
        "workcell:keyboard": plan(
            "NOMINAL_ENVELOPE_AVAILABLE", "layout",
            "Verify XY/yaw and measure support/top Z and exterior envelope.",
            legacy_rows["workcell:keyboard"]["nominal_placement"],
            image_useful=True,
        ),
        "workcell:phone": plan(
            "NOMINAL_ENVELOPE_AVAILABLE", "layout",
            "Verify XY/yaw and measure case, camera bump, and screen Z.",
            legacy_rows["workcell:phone"]["nominal_placement"],
            image_useful=True,
        ),
        "cable:fixed_usb_route": plan(
            "FIXED_ROUTE_DESIGN_PENDING", "camera_module",
            "Capture fixed USB route, diameter, anchors, strain relief, and sag envelope.",
        ),
        "camera:b0477_enclosure": plan(
            "PUBLISHED_AND_CONCEPT_GEOMETRY_ONLY", "camera_module",
            "Verify the received enclosure and installed board-relative envelope.",
        ),
        "camera:b0477_lens": plan(
            "PUBLISHED_AND_CONCEPT_GEOMETRY_ONLY", "camera_module",
            "Measure the installed lens barrel and entrance-pupil transform.",
        ),
        "camera:b0477_connector": plan(
            "PARTIAL_NOMINAL_GEOMETRY", "camera_module",
            "Capture connector and strain-relief envelope and transform.",
        ),
    }
    for body_id in (
        "support:portal_left_post", "support:portal_right_post",
        "support:portal_crossbar", "support:camera_boom",
        "support:lighting_boom_left", "support:lighting_boom_right",
        "lighting:key_light_left", "lighting:key_light_right",
    ):
        body_plan[body_id] = plan(
            "PARTIAL_NOMINAL_GEOMETRY", "camera_support",
            "Capture installed envelope and board-relative transform.",
            image_useful=True,
        )
    diagnostic_legacy = {
        "diagnostic_proxy:board_solid": "workcell:board_solid",
        "diagnostic_proxy:keyboard": "workcell:keyboard",
        "diagnostic_proxy:phone": "workcell:phone",
        "diagnostic_proxy:station:keyboard_left": "workcell:station:keyboard_left",
        "diagnostic_proxy:station:keyboard_right": "workcell:station:keyboard_right",
        "diagnostic_proxy:station:phone_tcp": "workcell:station:phone_tcp",
    }
    for body_id, legacy_id in diagnostic_legacy.items():
        row = legacy_rows[legacy_id]
        source_key = {
            "workcell:board_solid": "board",
            "workcell:keyboard": "layout",
            "workcell:phone": "layout",
            "workcell:station:keyboard_left": "keyboard_station_left",
            "workcell:station:keyboard_right": "keyboard_station_right",
            "workcell:station:phone_tcp": "phone_tcp_station",
        }[legacy_id]
        body_plan[body_id] = plan(
            row["nominal_state"], source_key,
            "Diagnostic proxy only; does not satisfy its installed-body counterpart.",
            row["nominal_placement"], image_useful=row["top_down_image_useful"],
        )

    bodies = []
    for requirement in readiness.contract.requirements:
        state, source_key, residual, placement, image_useful = body_plan[
            requirement.body_id
        ]
        bodies.append({
            "body_id": requirement.body_id,
            "parent_frame": requirement.parent_frame,
            "binding_mode": requirement.binding_mode.value,
            "nominal_state": state,
            "nominal_sources": [
                {"path": path, "sha256": source_hashes[path]}
                for path in _NOMINAL_SOURCE_PATHS[source_key]
            ],
            "nominal_placement": placement,
            "remaining_physical_check": residual,
            "top_down_image_useful": image_useful,
            "measured": False,
        })
    core: dict[str, Any] = {
        "schema": STATIC_B0477_NOMINAL_SOURCE_INVENTORY_SCHEMA,
        "status": "NOMINAL_SIMULATION_INPUTS_AVAILABLE_PHYSICAL_VERIFICATION_PENDING",
        "base_contract_sha256": readiness.contract.content_hash,
        "robot_model_sha256": readiness.urdf_sha256,
        "source_count": len(legacy["sources"]),
        "sources": legacy["sources"],
        "body_count": len(bodies),
        "bodies": bodies,
        "legacy_v1_inventory_sha256": legacy["content_sha256"],
        "simulation_use_allowed": True,
        "installed_measurement_status": "PENDING",
        "collision_qualification": False,
        "hardware_access": False,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "content_sha256": _sha(core)}


def _binary_stl_bounds_mm(path: Path) -> dict[str, list[float]]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise InstalledCollisionMeasurementManifestV1Error(
            f"cannot read nominal mesh {path}"
        ) from exc
    if len(payload) < 84:
        raise InstalledCollisionMeasurementManifestV1Error(
            f"nominal mesh {path} is not a binary STL"
        )
    triangle_count = struct.unpack_from("<I", payload, 80)[0]
    if len(payload) != 84 + triangle_count * 50 or triangle_count == 0:
        raise InstalledCollisionMeasurementManifestV1Error(
            f"nominal mesh {path} has an invalid binary STL length"
        )
    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    for triangle in range(triangle_count):
        vertices = struct.unpack_from("<9f", payload, 84 + triangle * 50 + 12)
        for index, value in enumerate(vertices):
            axis = index % 3
            minimum[axis] = min(minimum[axis], value)
            maximum[axis] = max(maximum[axis], value)
    return {
        "minimum_mm": [round(value, 6) for value in minimum],
        "maximum_mm": [round(value, 6) for value in maximum],
        "extents_mm": [
            round(maximum[index] - minimum[index], 6) for index in range(3)
        ],
    }


def build_installed_collision_nominal_envelope_audit_v1(
    context: SimulationContext,
) -> dict[str, Any]:
    """Compare nominal STL bounds with the declared station envelopes."""

    inventory = build_installed_collision_nominal_source_inventory_v1(context)
    layout = json.loads(context.scenario.workcell_layout_path.read_text(encoding="utf-8"))
    meshes = {
        name: _binary_stl_bounds_mm(
            context.rc03_root / "stl" / f"{name}.stl"
        )
        for name in (
            "keyboard_station_left", "keyboard_station_right",
            "phone_tcp_station", "compliant_tool_body",
            "compliant_tool_top_cap", "camera_plate_universal",
        )
    }
    station_pairs = {
        "keyboard_left": "keyboard_station_left",
        "keyboard_right": "keyboard_station_right",
        "phone_tcp": "phone_tcp_station",
    }
    comparisons = []
    for station_id, mesh_id in station_pairs.items():
        declared = [float(value) for value in layout["stations"][station_id]["outer_envelope"]]
        observed = meshes[mesh_id]["extents_mm"][:2]
        difference = [
            round(abs(declared[index] - observed[index]), 6)
            for index in range(2)
        ]
        comparisons.append({
            "station_id": station_id,
            "mesh_id": mesh_id,
            "declared_outer_envelope_xy_mm": declared,
            "mesh_extents_xy_mm": observed,
            "absolute_difference_xy_mm": difference,
            "binary_stl_comparison_tolerance_mm": (
                _BINARY_STL_COMPARISON_TOLERANCE_MM
            ),
            "matches_within_binary_stl_tolerance": all(
                value <= _BINARY_STL_COMPARISON_TOLERANCE_MM
                for value in difference
            ),
        })
    core: dict[str, Any] = {
        "schema": NOMINAL_ENVELOPE_AUDIT_SCHEMA,
        "source_inventory_sha256": inventory["content_sha256"],
        "mesh_bounds": meshes,
        "station_comparisons": comparisons,
        "all_station_envelopes_match_within_binary_stl_tolerance": all(
            row["matches_within_binary_stl_tolerance"] for row in comparisons
        ),
        "evidence_class": "NOMINAL_DIGITAL_ONLY",
        "installed_measurement_status": "PENDING",
        "collision_qualification": False,
        "hardware_access": False,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "content_sha256": _sha(core)}


def build_installed_collision_nominal_proxy_audit_v1(
    context: SimulationContext,
) -> dict[str, Any]:
    """Compare active workcell proxies with their nominal digital sources."""

    envelope_audit = build_installed_collision_nominal_envelope_audit_v1(context)
    layout = json.loads(context.scenario.workcell_layout_path.read_text(encoding="utf-8"))
    active = {item.obstacle_id: item for item in context.scene.obstacles}
    devices = layout["devices"]
    stations = layout["stations"]

    expected = {
        "board_solid": (
            [0.0, 0.0, float(layout["board"]["bottom_surface_z"])],
            [float(layout["board"]["width"]), float(layout["board"]["depth"]), 0.0],
            "MATCHES_LAYOUT_NOMINAL",
        ),
        "keyboard": (
            [*map(float, devices["keyboard"]["nominal_origin_xy"]),
             float(devices["keyboard"]["support_plane_z"])],
            [
                float(devices["keyboard"]["nominal_origin_xy"][0]
                      + devices["keyboard"]["nominal_size"][0]),
                float(devices["keyboard"]["nominal_origin_xy"][1]
                      + devices["keyboard"]["nominal_size"][1]),
                float(devices["keyboard"]["support_plane_z"]
                      + devices["keyboard"]["nominal_size"][2]),
            ],
            "MATCHES_LAYOUT_NOMINAL",
        ),
        "phone": (
            [*map(float, devices["phone"]["nominal_origin_xy"]),
             float(devices["phone"]["support_plane_z"])],
            [
                float(devices["phone"]["nominal_origin_xy"][0]
                      + devices["phone"]["configured_size"][0]),
                float(devices["phone"]["nominal_origin_xy"][1]
                      + devices["phone"]["configured_size"][1]),
                float(devices["phone"]["support_plane_z"]
                      + devices["phone"]["configured_size"][2]),
            ],
            "MATCHES_LAYOUT_NOMINAL",
        ),
    }
    mesh_for_station = {
        "keyboard_left": "keyboard_station_left",
        "keyboard_right": "keyboard_station_right",
        "phone_tcp": "phone_tcp_station",
    }
    for station_id, mesh_id in mesh_for_station.items():
        origin = stations[station_id]["origin_xy"]
        installed_z = float(stations[station_id]["installed_z"])
        extents = envelope_audit["mesh_bounds"][mesh_id]["extents_mm"]
        expected[f"station:{station_id}"] = (
            [float(origin[0]), float(origin[1]), installed_z],
            [
                float(origin[0] + extents[0]),
                float(origin[1] + extents[1]),
                float(installed_z + extents[2]),
            ],
            "CONSERVATIVE_HEIGHT_PROXY_CONTAINS_CAD_SOLID",
        )

    comparisons = []
    for obstacle_id, (nominal_min, nominal_max, classification) in expected.items():
        obstacle = active[obstacle_id]
        proxy_min = [obstacle.minimum.x, obstacle.minimum.y, obstacle.minimum.z]
        proxy_max = [obstacle.maximum.x, obstacle.maximum.y, obstacle.maximum.z]
        underbound = [
            max(0.0, proxy_min[index] - nominal_min[index])
            + max(0.0, nominal_max[index] - proxy_max[index])
            for index in range(3)
        ]
        overbound_low = [
            max(0.0, nominal_min[index] - proxy_min[index]) for index in range(3)
        ]
        overbound_high = [
            max(0.0, proxy_max[index] - nominal_max[index]) for index in range(3)
        ]
        comparisons.append({
            "obstacle_id": obstacle_id,
            "active_proxy_minimum_mm": proxy_min,
            "active_proxy_maximum_mm": proxy_max,
            "nominal_minimum_mm": nominal_min,
            "nominal_maximum_mm": nominal_max,
            "underbound_mm_by_axis": underbound,
            "overbound_low_mm_by_axis": overbound_low,
            "overbound_high_mm_by_axis": overbound_high,
            "has_nominal_underbound": any(value > 0.001 for value in underbound),
            "classification": classification,
        })
    core: dict[str, Any] = {
        "schema": NOMINAL_PROXY_AUDIT_SCHEMA,
        "source_envelope_audit_sha256": envelope_audit["content_sha256"],
        "comparison_count": len(comparisons),
        "comparisons": comparisons,
        "underbounded_obstacle_ids": [
            row["obstacle_id"] for row in comparisons
            if row["has_nominal_underbound"]
        ],
        "conservative_height_proxy_ids": [
            row["obstacle_id"] for row in comparisons
            if row["classification"]
            == "CONSERVATIVE_HEIGHT_PROXY_CONTAINS_CAD_SOLID"
        ],
        "all_nominal_solids_contained": not any(
            row["has_nominal_underbound"] for row in comparisons
        ),
        "station_proxy_height_mm": context.scenario.station_proxy_height_mm,
        "proxy_change_authorized": False,
        "evidence_class": "NOMINAL_DIGITAL_ONLY",
        "installed_measurement_status": "PENDING",
        "collision_qualification": False,
        "hardware_access": False,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "content_sha256": _sha(core)}


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


def build_pending_installed_collision_measurement_manifest_v1(
    context: SimulationContext,
    *,
    measurement_manifest_id: str,
    captured_at_utc: str,
) -> dict[str, Any]:
    """Build a complete, context-bound draft with no claimed measurements."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    manifest_id = _text(measurement_manifest_id, "measurement_manifest_id")
    _utc(captured_at_utc, "captured_at_utc")
    readiness = assess_current_collision_readiness(context)
    if readiness.active_build_id is None:
        raise InstalledCollisionMeasurementManifestV1Error(
            "active build id is unavailable"
        )
    draft: dict[str, Any] = {
        "schema": SCHEMA,
        "measurement_manifest_id": manifest_id,
        "captured_at_utc": captured_at_utc,
        "manifest_id": readiness.manifest_id,
        "manifest_sha256": readiness.manifest_sha256,
        "active_build_id": readiness.active_build_id,
        "build_snapshot_sha256": readiness.build_snapshot_hash,
        "robot_model_sha256": readiness.urdf_sha256,
        "base_contract_sha256": readiness.contract.content_hash,
        "root_frame": readiness.contract.root_frame,
        "sources": [],
        "body_measurements": [
            {
                "body_id": requirement.body_id,
                "parent_frame": requirement.parent_frame,
                "role": requirement.role.value,
                "binding_mode": requirement.binding_mode.value,
                "status": "PENDING",
                "source_ids": [],
                "coordinate_frame": requirement.parent_frame,
                "units": "mm",
                "geometry_uncertainty_mm": None,
                "envelope_primitives": [],
                "notes": "Pending physical measurement; no value claimed.",
            }
            for requirement in readiness.contract.requirements
        ],
        "clearance_measurement": {
            "status": "PENDING",
            "source_ids": [],
            "minimum_separation_mm": None,
            "geometry_uncertainty_mm_per_body": None,
            "pose_uncertainty_mm_per_body": None,
            "notes": "Pending reviewed physical clearance policy.",
        },
    }
    draft["content_sha256"] = _sha(draft)
    payload = _canonical(draft)
    report = validate_installed_collision_measurement_manifest_v1(
        draft,
        contract=readiness.contract,
        expected_manifest_id=readiness.manifest_id,
        expected_manifest_sha256=readiness.manifest_sha256,
        expected_active_build_id=readiness.active_build_id,
        expected_build_snapshot_sha256=readiness.build_snapshot_hash,
        expected_robot_model_sha256=readiness.urdf_sha256,
        file_sha256=hashlib.sha256(payload).hexdigest(),
    )
    if (
        report["status"] != BLOCKED_STATUS
        or report["measured_body_count"] != 0
        or len(report["pending_body_ids"]) != len(readiness.contract.requirements)
        or report["clearance_status"] != "PENDING"
    ):
        raise InstalledCollisionMeasurementManifestV1Error(
            "pending measurement draft did not remain fail closed"
        )
    return draft


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--system-manifest", type=Path)
    parser.add_argument("--measurement-manifest", type=Path)
    parser.add_argument("--measurement-manifest-sha256")
    parser.add_argument("--write-pending-draft", type=Path)
    parser.add_argument("--draft-manifest-id")
    parser.add_argument("--draft-captured-at-utc")
    parser.add_argument("--nominal-source-inventory", action="store_true")
    parser.add_argument("--nominal-envelope-audit", action="store_true")
    parser.add_argument("--nominal-proxy-audit", action="store_true")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    system_manifest = args.system_manifest or (
        args.workspace / "software/config/system_manifest.json"
    )
    try:
        context = load_simulation_context(args.workspace, system_manifest)
        readiness = assess_current_collision_readiness(context)
        if args.nominal_proxy_audit:
            if any((
                args.measurement_manifest, args.write_pending_draft,
                args.nominal_source_inventory, args.nominal_envelope_audit,
            )):
                raise InstalledCollisionMeasurementManifestV1Error(
                    "nominal proxy audit cannot be combined with other modes"
                )
            print(json.dumps(
                build_installed_collision_nominal_proxy_audit_v1(context),
                indent=2,
                sort_keys=True,
            ))
            return 0
        if args.nominal_envelope_audit:
            if any((
                args.measurement_manifest, args.write_pending_draft,
                args.nominal_source_inventory,
            )):
                raise InstalledCollisionMeasurementManifestV1Error(
                    "nominal envelope audit cannot be combined with manifest modes"
                )
            print(json.dumps(
                build_installed_collision_nominal_envelope_audit_v1(context),
                indent=2,
                sort_keys=True,
            ))
            return 0
        if args.nominal_source_inventory:
            if any((args.measurement_manifest, args.write_pending_draft)):
                raise InstalledCollisionMeasurementManifestV1Error(
                    "nominal source inventory cannot be combined with manifest modes"
                )
            print(json.dumps(
                build_installed_collision_nominal_source_inventory_v1(context),
                indent=2,
                sort_keys=True,
            ))
            return 0
        draft_values = (
            args.write_pending_draft,
            args.draft_manifest_id,
            args.draft_captured_at_utc,
        )
        if any(value is not None for value in draft_values):
            if not all(value is not None for value in draft_values):
                raise InstalledCollisionMeasurementManifestV1Error(
                    "pending draft path, manifest id, and capture time are required together"
                )
            if args.measurement_manifest is not None:
                raise InstalledCollisionMeasurementManifestV1Error(
                    "pending draft creation cannot also validate a measurement manifest"
                )
            draft = build_pending_installed_collision_measurement_manifest_v1(
                context,
                measurement_manifest_id=args.draft_manifest_id,
                captured_at_utc=args.draft_captured_at_utc,
            )
            payload = json.dumps(
                draft,
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8") + b"\n"
            try:
                with args.write_pending_draft.open("xb") as handle:
                    handle.write(payload)
            except FileExistsError as exc:
                raise InstalledCollisionMeasurementManifestV1Error(
                    "pending draft output already exists"
                ) from exc
            print(json.dumps({
                "status": BLOCKED_STATUS,
                "output_path": str(args.write_pending_draft),
                "file_sha256": hashlib.sha256(payload).hexdigest(),
                "content_sha256": draft["content_sha256"],
                "pending_body_count": len(draft["body_measurements"]),
                "physical_authority": False,
            }, indent=2, sort_keys=True))
            return 2
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
    "NOMINAL_SOURCE_INVENTORY_SCHEMA",
    "STATIC_B0477_NOMINAL_SOURCE_INVENTORY_SCHEMA",
    "NOMINAL_ENVELOPE_AUDIT_SCHEMA",
    "NOMINAL_PROXY_AUDIT_SCHEMA",
    "build_installed_collision_nominal_envelope_audit_v1",
    "build_installed_collision_nominal_proxy_audit_v1",
    "build_installed_collision_nominal_source_inventory_v1",
    "build_static_b0477_collision_nominal_source_inventory_v2",
    "load_and_validate_installed_collision_measurement_manifest_v1",
    "build_pending_installed_collision_measurement_manifest_v1",
    "load_installed_collision_measurement_manifest_v1",
    "main",
    "render_installed_collision_measurement_worksheet_v1",
    "validate_installed_collision_measurement_manifest_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())
