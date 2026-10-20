"""Publish separate partitioned collision-evidence intakes for both tool states.

The boundary consumes the hash-pinned profile route screen produced by
``fixed_camera_keyboard_profiled_route_screen_v1`` and partitions each accepted
IK route with the existing bounded collision planner.  It enumerates evidence;
it does not supply measured geometry, execute collision checks, or authorize
hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from rocell.calibration import PlannerCalibrationSnapshot
from rocell.simulation.collision import CollisionAttachmentProfile

from .bounded_segment_collision_qualification import BoundedSegmentSamplingPolicy
from .context import SimulationContext
from .fixed_camera_keyboard_clearance_intake_v1 import SUPPORTED_PROFILES
from .fixed_camera_keyboard_profiled_route_screen_v1 import (
    IK_NAMES as SCREEN_IK_NAMES,
    MANIFEST_NAME as SCREEN_MANIFEST_NAME,
    RECEIPT_NAME as SCREEN_RECEIPT_NAME,
    RECEIPT_STATUS as SCREEN_RECEIPT_STATUS,
    SCHEMA as SCREEN_SCHEMA,
    STATUS as SCREEN_STATUS,
    ZERO_AUTHORITY as SCREEN_ZERO_AUTHORITY,
)
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .partitioned_typing_collision_intake_v1 import (
    READY_STATUS as PARTITION_READY_STATUS,
    prepare_partitioned_typing_collision_intake_v1,
)


SCHEMA = "rocell.fixed_camera_keyboard_profiled_collision_partitions_manifest.v1"
STATUS = "READY_FOR_PARTITIONED_PROFILE_BOUND_COLLISION_EVIDENCE"
RECEIPT_SCHEMA = "rocell.fixed_camera_keyboard_profiled_collision_partitions_receipt.v1"
RECEIPT_STATUS = "PROFILED_COLLISION_PARTITIONS_ADMITTED"
MANIFEST_NAME = "profiled-collision-partitions-manifest.json"
RECEIPT_NAME = "profiled-collision-partitions-receipt.json"
PARTITION_NAMES = {
    "no_attachment": "no-attachment-partitioned-collision-intake.json",
    "stylus_attachment": "stylus-attachment-partitioned-collision-intake.json",
}
MAX_JSON_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
ZERO_AUTHORITY: Mapping[str, object] = {
    "partition_planning_executed_offline": True,
    "measured_collision_evidence_supplied": False,
    "installed_geometry_collision_screening_executed": False,
    "continuous_collision_proven": False,
    "fresh_observed_start_state_present": False,
    "controller_commands": [],
    "hardware_commands_generated": 0,
    "hardware_access": False,
    "physical_authority": False,
    "physical_release_effect": "NONE",
}


class FixedCameraKeyboardProfiledCollisionPartitionsV1Error(ValueError):
    """A profile route bundle cannot form exact collision partitions."""


def _canonical(value: object, *, newline: bool = False) -> bytes:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return payload + (b"\n" if newline else b"")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(value: object) -> str:
    return _sha_bytes(_canonical(value))


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _reject_constant(value: str) -> None:
    raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
        f"profiled collision input contains nonfinite constant {value!r}"
    )


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
                f"profiled collision input contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _read_json(
    path: str | Path, *, expected_sha256: str, label: str
) -> tuple[Path, bytes, Mapping[str, Any]]:
    source = Path(path).expanduser()
    expected = _digest(expected_sha256, f"expected_{label}_file_sha256")
    if source.is_symlink():
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            f"{label} path must not be a symlink"
        )
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            f"cannot inspect {label} file: {exc}"
        ) from exc
    if not source.is_file() or size <= 0 or size > MAX_JSON_BYTES:
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            f"{label} file size is invalid"
        )
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            f"cannot read {label} file: {exc}"
        ) from exc
    if len(payload) != size or _sha_bytes(payload) != expected:
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            f"{label} bytes differ from expected file SHA-256"
        )
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            f"{label} must be a JSON object"
        )
    return source.resolve(), payload, value


def _profile_map(value: Mapping[str, Any], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != set(SUPPORTED_PROFILES):
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            f"{label} must contain the exact supported profile set"
        )


def _validate_source(
    receipt_path: Path,
    receipt: Mapping[str, Any],
    manifest_path: Path,
    manifest_bytes: bytes,
    manifest: Mapping[str, Any],
    ik_sources: Mapping[str, tuple[Path, bytes, Mapping[str, Any]]],
) -> None:
    if (
        receipt_path.name != SCREEN_RECEIPT_NAME
        or manifest_path.name != SCREEN_MANIFEST_NAME
        or receipt_path.parent != manifest_path.parent
        or any(path.parent != receipt_path.parent for path, _, _ in ik_sources.values())
    ):
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            "route receipt, manifest, and IK screens must be the named co-located bundle"
        )
    if (
        receipt.get("schema")
        != "rocell.fixed_camera_keyboard_profiled_route_screen_admission_receipt.v1"
        or receipt.get("status") != SCREEN_RECEIPT_STATUS
        or receipt.get("profile_separation_preserved") is not True
        or receipt.get("authority") != SCREEN_ZERO_AUTHORITY
    ):
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            "route screen receipt is invalid or authority-bearing"
        )
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            "route screen receipt artifacts must be an object"
        )
    bound_manifest = artifacts.get("profiled_route_screen_manifest")
    if (
        not isinstance(bound_manifest, Mapping)
        or bound_manifest.get("name") != SCREEN_MANIFEST_NAME
        or bound_manifest.get("size_bytes") != len(manifest_bytes)
        or bound_manifest.get("file_sha256") != _sha_bytes(manifest_bytes)
        or bound_manifest.get("meaning_sha256") != _sha(manifest)
    ):
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            "route screen manifest differs from its receipt"
        )
    unsigned = dict(manifest)
    claimed = unsigned.pop("profiled_route_screen_manifest_sha256", None)
    profiles = manifest.get("profiles")
    if (
        manifest.get("schema") != SCREEN_SCHEMA
        or manifest.get("status") != SCREEN_STATUS
        or claimed != _sha(unsigned)
        or manifest.get("profile_separation_preserved") is not True
        or manifest.get("authority") != SCREEN_ZERO_AUTHORITY
        or not isinstance(profiles, Mapping)
        or set(profiles) != set(SUPPORTED_PROFILES)
    ):
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            "route screen manifest is invalid or authority-bearing"
        )
    for name in SUPPORTED_PROFILES:
        path, payload, ik = ik_sources[name]
        row = profiles[name]
        bound = artifacts.get(f"{name}_ik")
        if (
            path.name != SCREEN_IK_NAMES[name]
            or not isinstance(row, Mapping)
            or not isinstance(bound, Mapping)
            or bound.get("name") != path.name
            or bound.get("size_bytes") != len(payload)
            or bound.get("file_sha256") != _sha_bytes(payload)
            or row.get("typing_trajectory_ik_screen_file_sha256") != _sha_bytes(payload)
            or row.get("typing_trajectory_ik_screen_sha256")
            != ik.get("typing_trajectory_ik_screen_sha256")
        ):
            raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
                f"route screen IK binding differs: {name}"
            )


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            f"cannot publish new collision partition file {path.name}: {exc}"
        ) from exc


@dataclass(frozen=True, slots=True)
class FixedCameraKeyboardProfiledCollisionPartitionsResultV1:
    output_directory: Path
    partition_paths: Mapping[str, Path]
    manifest_path: Path
    receipt_path: Path
    manifest: Mapping[str, Any]
    receipt: Mapping[str, Any]


def partition_fixed_camera_keyboard_profiled_collision_routes_v1(
    route_screen_receipt_path: str | Path,
    *,
    expected_route_screen_receipt_file_sha256: str,
    route_screen_manifest_path: str | Path,
    expected_route_screen_manifest_file_sha256: str,
    ik_screen_paths: Mapping[str, str | Path],
    expected_ik_screen_file_sha256: Mapping[str, str],
    context: SimulationContext,
    calibration_snapshot: PlannerCalibrationSnapshot,
    installed_collision_profiles: Mapping[str, InstalledCollisionGeometryProfile],
    output_directory: str | Path,
    sampling_policies: Mapping[str, BoundedSegmentSamplingPolicy | None] | None = None,
    maximum_partitions: Mapping[str, int] | None = None,
) -> FixedCameraKeyboardProfiledCollisionPartitionsResultV1:
    """Partition both profile routes and publish their exact evidence slots."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(calibration_snapshot, PlannerCalibrationSnapshot):
        raise TypeError("calibration_snapshot must be a PlannerCalibrationSnapshot")
    for value, label in (
        (ik_screen_paths, "ik_screen_paths"),
        (expected_ik_screen_file_sha256, "expected_ik_screen_file_sha256"),
        (installed_collision_profiles, "installed_collision_profiles"),
    ):
        _profile_map(value, label)
    if sampling_policies is not None:
        _profile_map(sampling_policies, "sampling_policies")
    if maximum_partitions is not None:
        _profile_map(maximum_partitions, "maximum_partitions")

    receipt_source, receipt_bytes, receipt = _read_json(
        route_screen_receipt_path,
        expected_sha256=expected_route_screen_receipt_file_sha256,
        label="route screen receipt",
    )
    manifest_source, manifest_bytes, source_manifest = _read_json(
        route_screen_manifest_path,
        expected_sha256=expected_route_screen_manifest_file_sha256,
        label="route screen manifest",
    )
    ik_sources: dict[str, tuple[Path, bytes, Mapping[str, Any]]] = {}
    for name in SUPPORTED_PROFILES:
        ik_sources[name] = _read_json(
            ik_screen_paths[name],
            expected_sha256=expected_ik_screen_file_sha256[name],
            label=f"{name} IK screen",
        )
    _validate_source(
        receipt_source,
        receipt,
        manifest_source,
        manifest_bytes,
        source_manifest,
        ik_sources,
    )

    if (
        source_manifest.get("calibration_snapshot_sha256")
        != calibration_snapshot.snapshot_sha256
        or source_manifest.get("build_snapshot_sha256")
        != context.snapshot.snapshot_hash
        or source_manifest.get("kinematic_model_sha256")
        != context.scenario.model_sha256
        or calibration_snapshot.manifest_id != context.snapshot.manifest_id
        or calibration_snapshot.active_build_id != context.snapshot.active_build_id
    ):
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            "route screen, calibration, build, or model context differs"
        )
    if any(
        not isinstance(
            installed_collision_profiles[name], InstalledCollisionGeometryProfile
        )
        for name in SUPPORTED_PROFILES
    ):
        raise TypeError("installed collision profiles have an unsupported type")
    if (
        len(
            {
                installed_collision_profiles[name].content_sha256
                for name in SUPPORTED_PROFILES
            }
        )
        != 2
    ):
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            "attachment profiles require distinct installed collision profiles"
        )

    reports: dict[str, Mapping[str, Any]] = {}
    payloads: dict[str, bytes] = {}
    profile_rows: dict[str, Any] = {}
    source_profiles = source_manifest["profiles"]
    for name in SUPPORTED_PROFILES:
        source_row = source_profiles[name]
        profile = installed_collision_profiles[name]
        if (
            source_row.get("installed_collision_profile_id") != profile.profile_id
            or source_row.get("installed_collision_profile_content_sha256")
            != profile.content_sha256
            or source_row.get("collision_contract_sha256")
            != profile.contract.content_hash
        ):
            raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
                f"installed collision profile differs from route screen: {name}"
            )
        report = prepare_partitioned_typing_collision_intake_v1(
            ik_sources[name][2],
            context,
            expected_execution_plan_sha256=source_row["typing_execution_plan_sha256"],
            expected_trajectory_plan_sha256=source_row["typing_trajectory_plan_sha256"],
            expected_calibration_snapshot_sha256=(calibration_snapshot.snapshot_sha256),
            installed_profile=profile,
            attachment_profile=CollisionAttachmentProfile(name),
            sampling_policy=(
                None if sampling_policies is None else sampling_policies[name]
            ),
            maximum_partitions=(
                64 if maximum_partitions is None else maximum_partitions[name]
            ),
        )
        if report.get("status") != PARTITION_READY_STATUS:
            raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
                f"profile did not reach partitioned collision intake: {name}"
            )
        payload = _canonical(report, newline=True)
        reports[name] = report
        payloads[name] = payload
        profile_rows[name] = {
            "profile": name,
            "attachment_state": source_row["attachment_state"],
            "typing_execution_plan_sha256": source_row["typing_execution_plan_sha256"],
            "typing_trajectory_plan_sha256": source_row[
                "typing_trajectory_plan_sha256"
            ],
            "typing_trajectory_ik_screen_sha256": source_row[
                "typing_trajectory_ik_screen_sha256"
            ],
            "installed_collision_profile_id": profile.profile_id,
            "installed_collision_profile_content_sha256": profile.content_sha256,
            "collision_contract_sha256": profile.contract.content_hash,
            "partitioned_typing_collision_intake_sha256": report[
                "partitioned_typing_collision_intake_sha256"
            ],
            "partitioned_typing_collision_intake_file_sha256": _sha_bytes(payload),
            "partition_count": len(report["partitions"]),
            "boundary_lineage": report["boundary_lineage"],
            "required_evidence_slots": report["required_evidence_slots"],
            "blockers": report["blockers"],
            "next_required_stage": report["next_required_stage"],
        }

    manifest_core: Mapping[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "source_profiled_route_screen_manifest_sha256": source_manifest[
            "profiled_route_screen_manifest_sha256"
        ],
        "calibration_snapshot_sha256": calibration_snapshot.snapshot_sha256,
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "kinematic_model_sha256": context.scenario.model_sha256,
        "profiles": profile_rows,
        "profile_separation_preserved": True,
        "next_required_stage": "SUPPLY_PARTITIONED_PROFILE_BOUND_COLLISION_EVIDENCE",
        "authority": dict(ZERO_AUTHORITY),
    }
    manifest = {
        **manifest_core,
        "profiled_collision_partitions_manifest_sha256": _sha(manifest_core),
    }
    manifest_out = _canonical(manifest, newline=True)
    source_rows = {
        "route_screen_receipt": (receipt_source, receipt_bytes),
        "route_screen_manifest": (manifest_source, manifest_bytes),
        **{
            f"{name}_ik_screen": (ik_sources[name][0], ik_sources[name][1])
            for name in SUPPORTED_PROFILES
        },
    }
    receipt_out: Mapping[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "status": RECEIPT_STATUS,
        "sources": {
            key: {
                "name": path.name,
                "size_bytes": len(payload),
                "file_sha256": _sha_bytes(payload),
            }
            for key, (path, payload) in source_rows.items()
        },
        "artifacts": {
            **{
                f"{name}_partitioned_collision_intake": {
                    "name": PARTITION_NAMES[name],
                    "size_bytes": len(payloads[name]),
                    "file_sha256": _sha_bytes(payloads[name]),
                    "meaning_sha256": reports[name][
                        "partitioned_typing_collision_intake_sha256"
                    ],
                }
                for name in SUPPORTED_PROFILES
            },
            "profiled_collision_partitions_manifest": {
                "name": MANIFEST_NAME,
                "size_bytes": len(manifest_out),
                "file_sha256": _sha_bytes(manifest_out),
                "meaning_sha256": _sha(manifest),
            },
            "completion_receipt": {"name": RECEIPT_NAME, "written_last": True},
        },
        "profile_separation_preserved": True,
        "next_required_stage": "SUPPLY_PARTITIONED_PROFILE_BOUND_COLLISION_EVIDENCE",
        "authority": dict(ZERO_AUTHORITY),
    }
    receipt_out_bytes = _canonical(receipt_out, newline=True)

    requested = Path(output_directory).expanduser()
    if not requested.name or requested.name in (".", ".."):
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            "output_directory must name a new directory"
        )
    parent = requested.parent.resolve()
    if not parent.is_dir():
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            "output_directory parent must already exist"
        )
    destination = parent / requested.name
    if destination.exists() or destination.is_symlink():
        raise FixedCameraKeyboardProfiledCollisionPartitionsV1Error(
            "output_directory already exists; refusing to overwrite"
        )
    try:
        destination.mkdir(mode=0o700, exist_ok=False)
        partition_paths = {
            name: destination / PARTITION_NAMES[name] for name in SUPPORTED_PROFILES
        }
        for name in SUPPORTED_PROFILES:
            _write_new(partition_paths[name], payloads[name])
        manifest_path = destination / MANIFEST_NAME
        receipt_path = destination / RECEIPT_NAME
        _write_new(manifest_path, manifest_out)
        _write_new(receipt_path, receipt_out_bytes)
    except Exception:
        if destination.exists():
            for child in destination.iterdir():
                child.unlink(missing_ok=True)
            destination.rmdir()
        raise
    return FixedCameraKeyboardProfiledCollisionPartitionsResultV1(
        destination,
        partition_paths,
        manifest_path,
        receipt_path,
        manifest,
        receipt_out,
    )


__all__ = [
    "MANIFEST_NAME",
    "PARTITION_NAMES",
    "RECEIPT_NAME",
    "RECEIPT_STATUS",
    "STATUS",
    "ZERO_AUTHORITY",
    "FixedCameraKeyboardProfiledCollisionPartitionsResultV1",
    "FixedCameraKeyboardProfiledCollisionPartitionsV1Error",
    "partition_fixed_camera_keyboard_profiled_collision_routes_v1",
]
