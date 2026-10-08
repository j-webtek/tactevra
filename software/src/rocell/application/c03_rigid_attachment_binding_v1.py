"""Strict zero-authority rigid attachment binding for the exact C03 route."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from rocell.geometry.transforms import RigidTransform, Rotation3, Vec3

from .c03_installed_collision_qualification_v1 import READY_FOR_EVIDENCE_STATUS
from .collision_readiness import assess_current_collision_readiness
from .context import SimulationContext, revalidate_simulation_context


SCHEMA = "tactevra.c03_rigid_attachment_binding_manifest.v1"
REPORT_SCHEMA = "tactevra.c03_rigid_attachment_binding_report.v1"
READY_STATUS = "READY_FOR_PROFILE_BOUND_RIGID_COLLISION_EVIDENCE"
MAX_BYTES = 256 * 1024

_ROOT_FIELDS = {
    "schema",
    "binding_manifest_id",
    "captured_at_utc",
    "valid_until_utc",
    "c03_installed_collision_qualification_sha256",
    "collision_contract_sha256",
    "installed_collision_profile_content_sha256",
    "installed_collision_profile_file_sha256",
    "measurement_manifest_file_sha256",
    "measurement_manifest_content_sha256",
    "root_frame",
    "sources",
    "transforms",
    "content_sha256",
}
_SOURCE_FIELDS = {"source_id", "sha256", "captured_at_utc", "method", "notes"}
_TRANSFORM_FIELDS = {
    "frame",
    "to_frame",
    "from_frame",
    "rotation_row_major",
    "translation_mm",
    "translation_uncertainty_mm",
    "rotation_uncertainty_deg",
    "source_ids",
    "captured_at_utc",
}


class C03RigidAttachmentBindingV1Error(ValueError):
    """A rigid binding manifest is malformed, crossed, stale, or incomplete."""


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
        raise C03RigidAttachmentBindingV1Error("document is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise C03RigidAttachmentBindingV1Error(f"{label} must be lowercase SHA-256")
    return value


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise C03RigidAttachmentBindingV1Error(f"{label} must be a UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise C03RigidAttachmentBindingV1Error(f"{label} is invalid") from exc
    if parsed.tzinfo != timezone.utc:
        raise C03RigidAttachmentBindingV1Error(f"{label} must be UTC")
    return parsed


def _exact(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise C03RigidAttachmentBindingV1Error(f"{label} fields differ")
    return dict(value)


def _list(value: object, label: str, *, maximum: int) -> list[Any]:
    if not isinstance(value, list) or not value or len(value) > maximum:
        raise C03RigidAttachmentBindingV1Error(f"{label} must be a bounded nonempty list")
    return value


def _finite(value: object, label: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise C03RigidAttachmentBindingV1Error(f"{label} must be finite")
    number = float(value)
    if not math.isfinite(number) or (nonnegative and number < 0.0):
        raise C03RigidAttachmentBindingV1Error(f"{label} must be finite and nonnegative")
    return number


def _qualification(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise C03RigidAttachmentBindingV1Error("qualification must be an object")
    report = dict(value)
    claimed = report.pop("c03_installed_collision_qualification_sha256", None)
    if not isinstance(claimed, str) or claimed != _sha(report):
        raise C03RigidAttachmentBindingV1Error("qualification hash is invalid")
    full = dict(value)
    handoff = full.get("c03_collision_handoff")
    if (
        full.get("status") != READY_FOR_EVIDENCE_STATUS
        or not isinstance(handoff, Mapping)
        or full.get("profile_file_sha256") is None
        or full.get("installed_collision_gate_cleared") is not False
        or full.get("continuous_collision_proven") is not False
        or full.get("controller_commands") != []
        or full.get("hardware_access") is not False
        or full.get("hardware_writes") != 0
        or full.get("physical_movements") != 0
        or full.get("physical_authority") is not False
    ):
        raise C03RigidAttachmentBindingV1Error(
            "qualification is not a ready zero-authority profile boundary"
        )
    return full


def _load(path: Path, expected_file_sha256: str) -> tuple[dict[str, Any], str]:
    expected = _digest(expected_file_sha256, "expected file hash")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise C03RigidAttachmentBindingV1Error("cannot read binding manifest") from exc
    if len(payload) > MAX_BYTES:
        raise C03RigidAttachmentBindingV1Error("binding manifest exceeds byte limit")
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise C03RigidAttachmentBindingV1Error("binding manifest file hash mismatch")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise C03RigidAttachmentBindingV1Error(
                    f"duplicate JSON field {key!r}"
                )
            result[key] = item
        return result

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise C03RigidAttachmentBindingV1Error("binding manifest is invalid JSON") from exc
    if not isinstance(value, dict):
        raise C03RigidAttachmentBindingV1Error("binding manifest root must be an object")
    return value, actual


def validate_c03_rigid_attachment_binding_v1(
    document: Mapping[str, Any],
    qualification: Mapping[str, Any],
    *,
    context: SimulationContext,
    file_sha256: str,
    evaluated_at_utc: str,
) -> dict[str, Any]:
    """Validate exact measured rigid bindings and return a zero-authority report."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    revalidate_simulation_context(context)
    readiness = assess_current_collision_readiness(context)
    root = _exact(document, _ROOT_FIELDS, "binding manifest")
    if root["schema"] != SCHEMA:
        raise C03RigidAttachmentBindingV1Error("binding manifest schema mismatch")
    claimed_content = _digest(root["content_sha256"], "content_sha256")
    unsigned = {key: value for key, value in root.items() if key != "content_sha256"}
    if claimed_content != _sha(unsigned):
        raise C03RigidAttachmentBindingV1Error("binding manifest content hash mismatch")
    if not isinstance(root["binding_manifest_id"], str) or not root["binding_manifest_id"]:
        raise C03RigidAttachmentBindingV1Error("binding_manifest_id is invalid")

    qualified = _qualification(qualification)
    intake = qualified["c03_collision_handoff"]["collision_intake"]
    required_frames = intake["required_rigid_attachment_frames"]
    if (
        not isinstance(required_frames, list)
        or not required_frames
        or any(not isinstance(frame, str) or not frame for frame in required_frames)
        or len(set(required_frames)) != len(required_frames)
    ):
        raise C03RigidAttachmentBindingV1Error("required rigid frame inventory is invalid")

    expected = {
        "c03_installed_collision_qualification_sha256": qualified[
            "c03_installed_collision_qualification_sha256"
        ],
        "collision_contract_sha256": intake["collision_contract_sha256"],
        "installed_collision_profile_content_sha256": intake[
            "installed_collision_profile_sha256"
        ],
        "installed_collision_profile_file_sha256": qualified["profile_file_sha256"],
        "measurement_manifest_file_sha256": qualified[
            "measurement_manifest_file_sha256"
        ],
        "measurement_manifest_content_sha256": qualified[
            "measurement_manifest_content_sha256"
        ],
        "root_frame": readiness.contract.root_frame,
    }
    mismatched = [key for key, value in expected.items() if root[key] != value]
    if mismatched:
        raise C03RigidAttachmentBindingV1Error(
            "binding lineage differs: " + ", ".join(sorted(mismatched))
        )

    captured = _timestamp(root["captured_at_utc"], "captured_at_utc")
    valid_until = _timestamp(root["valid_until_utc"], "valid_until_utc")
    evaluated = _timestamp(evaluated_at_utc, "evaluated_at_utc")
    if not captured <= evaluated <= valid_until:
        raise C03RigidAttachmentBindingV1Error("binding manifest is stale or future dated")

    source_hashes: dict[str, str] = {}
    source_times: dict[str, datetime] = {}
    for index, value in enumerate(_list(root["sources"], "sources", maximum=128)):
        row = _exact(value, _SOURCE_FIELDS, f"sources[{index}]")
        source_id = row["source_id"]
        if not isinstance(source_id, str) or not source_id or source_id in source_hashes:
            raise C03RigidAttachmentBindingV1Error("source IDs must be unique and nonempty")
        source_hashes[source_id] = _digest(row["sha256"], f"source {source_id} hash")
        source_times[source_id] = _timestamp(
            row["captured_at_utc"], f"source {source_id} captured_at_utc"
        )
        if source_times[source_id] > captured:
            raise C03RigidAttachmentBindingV1Error("source is newer than manifest capture")
        if not isinstance(row["method"], str) or not row["method"]:
            raise C03RigidAttachmentBindingV1Error("source method is invalid")
        if not isinstance(row["notes"], str):
            raise C03RigidAttachmentBindingV1Error("source notes must be a string")

    transforms: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(
        _list(root["transforms"], "transforms", maximum=128)
    ):
        row = _exact(value, _TRANSFORM_FIELDS, f"transforms[{index}]")
        frame = row["frame"]
        if not isinstance(frame, str) or not frame or frame in transforms:
            raise C03RigidAttachmentBindingV1Error("transform frames must be unique")
        if row["to_frame"] != readiness.contract.root_frame or row["from_frame"] != frame:
            raise C03RigidAttachmentBindingV1Error(
                "transform direction must be root_T_required_frame"
            )
        rotation_values = _list(
            row["rotation_row_major"], f"transform {frame} rotation", maximum=9
        )
        translation_values = _list(
            row["translation_mm"], f"transform {frame} translation", maximum=3
        )
        if len(rotation_values) != 9 or len(translation_values) != 3:
            raise C03RigidAttachmentBindingV1Error("transform dimensions are invalid")
        transform = RigidTransform(
            readiness.contract.root_frame,
            frame,
            Rotation3(tuple(_finite(item, "rotation") for item in rotation_values)),
            Vec3(*(_finite(item, "translation") for item in translation_values)),
        )
        identity = transform.compose(transform.inverse())
        if not identity.almost_equal(
            RigidTransform.identity(readiness.contract.root_frame),
            absolute_tolerance=1e-9,
        ):
            raise C03RigidAttachmentBindingV1Error("transform round trip failed")
        translation_uncertainty = _finite(
            row["translation_uncertainty_mm"],
            "translation_uncertainty_mm",
            nonnegative=True,
        )
        rotation_uncertainty = _finite(
            row["rotation_uncertainty_deg"],
            "rotation_uncertainty_deg",
            nonnegative=True,
        )
        source_ids = _list(row["source_ids"], "source_ids", maximum=32)
        if (
            any(not isinstance(item, str) or item not in source_hashes for item in source_ids)
            or len(set(source_ids)) != len(source_ids)
        ):
            raise C03RigidAttachmentBindingV1Error("transform source IDs are invalid")
        transform_time = _timestamp(
            row["captured_at_utc"], f"transform {frame} captured_at_utc"
        )
        if transform_time > captured or any(
            source_times[source_id] > transform_time for source_id in source_ids
        ):
            raise C03RigidAttachmentBindingV1Error("transform/source chronology is invalid")
        core = {
            "frame": frame,
            "root_T_frame": {
                "to_frame": transform.parent_frame,
                "from_frame": transform.child_frame,
                "rotation_row_major": list(transform.rotation.matrix),
                "translation_mm": [
                    transform.translation_mm.x,
                    transform.translation_mm.y,
                    transform.translation_mm.z,
                ],
            },
            "translation_uncertainty_mm": translation_uncertainty,
            "rotation_uncertainty_deg": rotation_uncertainty,
            "source_ids": sorted(source_ids),
        }
        transforms[frame] = {**core, "transform_binding_sha256": _sha(core)}

    if set(transforms) != set(required_frames):
        raise C03RigidAttachmentBindingV1Error(
            "transform coverage differs from required rigid attachment frames"
        )

    report_core: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": READY_STATUS,
        "binding_manifest_id": root["binding_manifest_id"],
        "binding_manifest_file_sha256": _digest(file_sha256, "file_sha256"),
        "binding_manifest_content_sha256": claimed_content,
        "c03_installed_collision_qualification_sha256": expected[
            "c03_installed_collision_qualification_sha256"
        ],
        "collision_contract_sha256": expected["collision_contract_sha256"],
        "installed_collision_profile_content_sha256": expected[
            "installed_collision_profile_content_sha256"
        ],
        "installed_collision_profile_file_sha256": expected[
            "installed_collision_profile_file_sha256"
        ],
        "measurement_manifest_file_sha256": expected[
            "measurement_manifest_file_sha256"
        ],
        "measurement_manifest_content_sha256": expected[
            "measurement_manifest_content_sha256"
        ],
        "root_frame": readiness.contract.root_frame,
        "required_frames": sorted(required_frames),
        "transform_bindings": [transforms[key] for key in sorted(transforms)],
        "source_bindings": dict(sorted(source_hashes.items())),
        "installed_geometry_collision_screening_executed": False,
        "continuous_collision_proven": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**report_core, "c03_rigid_attachment_binding_report_sha256": _sha(report_core)}


def load_c03_rigid_attachment_binding_v1(
    path: str | Path,
    expected_file_sha256: str,
    qualification: Mapping[str, Any],
    *,
    context: SimulationContext,
    evaluated_at_utc: str,
) -> dict[str, Any]:
    """Load exact manifest bytes and validate them against the C03 profile intake."""

    document, file_hash = _load(Path(path), expected_file_sha256)
    return validate_c03_rigid_attachment_binding_v1(
        document,
        qualification,
        context=context,
        file_sha256=file_hash,
        evaluated_at_utc=evaluated_at_utc,
    )


__all__ = [
    "MAX_BYTES",
    "READY_STATUS",
    "REPORT_SCHEMA",
    "SCHEMA",
    "C03RigidAttachmentBindingV1Error",
    "load_c03_rigid_attachment_binding_v1",
    "validate_c03_rigid_attachment_binding_v1",
]
