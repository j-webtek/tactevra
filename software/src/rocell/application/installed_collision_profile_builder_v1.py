"""Deterministically build an installed collision profile from ICQ-1 evidence.

This ICQ-2 boundary consumes only a complete, hash-bound measurement manifest.
It inflates static measured primitives by their per-body geometry uncertainty,
retains configuration-sampled bodies without inventing static cable geometry,
and emits a byte-stable profile plus a measured-to-envelope difference report.
It never screens a trajectory, opens transport, generates a controller command,
or grants physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from rocell.simulation.collision import CollisionBindingMode

from .collision_readiness import assess_current_collision_readiness
from .context import SimulationContext
from .installed_collision_geometry import load_installed_collision_geometry_profile
from .installed_collision_measurement_manifest_v1 import (
    READY_STATUS,
    load_installed_collision_measurement_manifest_v1,
)


RESULT_SCHEMA = "rocell.installed_collision_profile_build_result.v1"
DIFFERENCE_SCHEMA = "rocell.installed_collision_profile_difference.v1"
BUILT_STATUS = "BUILT_ZERO_AUTHORITY"
BLOCKED_MEASUREMENTS_STATUS = "BLOCKED_REQUIRED_BODY_MEASUREMENT_MISSING"
BLOCKED_CLEARANCE_STATUS = "BLOCKED_CLEARANCE_POLICY_UNSUPPORTED"
PROFILE_SCHEMA = "rocell.installed_collision_geometry_profile.v1"


class InstalledCollisionProfileBuilderV1Error(ValueError):
    """A validated manifest cannot be mapped to a conservative profile."""


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
        raise InstalledCollisionProfileBuilderV1Error(
            "profile build result is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _inflate_primitive(
    primitive: Mapping[str, Any], uncertainty_mm: float
) -> tuple[dict[str, Any], dict[str, Any]]:
    kind = primitive["kind"]
    measured = dict(primitive)
    if kind == "sphere":
        derived = {
            "kind": kind,
            "center_mm": list(primitive["center_mm"]),
            "radius_mm": float(primitive["radius_mm"]) + uncertainty_mm,
        }
    elif kind == "capsule":
        derived = {
            "kind": kind,
            "start_mm": list(primitive["start_mm"]),
            "end_mm": list(primitive["end_mm"]),
            "radius_mm": float(primitive["radius_mm"]) + uncertainty_mm,
        }
    elif kind == "oriented_box":
        derived = {
            "kind": kind,
            "center_mm": list(primitive["center_mm"]),
            "half_extents_mm": [
                float(value) + uncertainty_mm
                for value in primitive["half_extents_mm"]
            ],
            "rotation_row_major": list(primitive["rotation_row_major"]),
        }
    else:  # The ICQ-1 validator should make this unreachable.
        raise InstalledCollisionProfileBuilderV1Error(
            f"unsupported validated primitive kind {kind!r}"
        )
    difference = {
        "kind": kind,
        "measured_primitive": measured,
        "geometry_uncertainty_mm": uncertainty_mm,
        "derived_conservative_primitive": derived,
        "fit_rule": "INFLATE_RADIAL_OR_EACH_HALF_EXTENT_BY_BODY_UNCERTAINTY",
    }
    return derived, difference


def _source_reference(source_ids: Sequence[str]) -> str:
    return "measurement_sources:" + ",".join(sorted(source_ids))


@dataclass(frozen=True, slots=True)
class InstalledCollisionProfileBuildResultV1:
    status: str
    measurement_manifest_file_sha256: str
    measurement_manifest_content_sha256: str
    blockers: tuple[str, ...]
    profile_document: Mapping[str, Any] | None
    profile_bytes: bytes | None
    profile_file_sha256: str | None
    difference_report: Mapping[str, Any] | None

    def __post_init__(self) -> None:
        if self.profile_document is not None:
            object.__setattr__(
                self,
                "profile_document",
                MappingProxyType(dict(self.profile_document)),
            )
        if self.difference_report is not None:
            object.__setattr__(
                self,
                "difference_report",
                MappingProxyType(dict(self.difference_report)),
            )

    def to_dict(self) -> dict[str, Any]:
        core: dict[str, Any] = {
            "schema": RESULT_SCHEMA,
            "status": self.status,
            "measurement_manifest_file_sha256": (
                self.measurement_manifest_file_sha256
            ),
            "measurement_manifest_content_sha256": (
                self.measurement_manifest_content_sha256
            ),
            "blockers": list(self.blockers),
            "profile_generated": self.profile_document is not None,
            "profile_file_sha256": self.profile_file_sha256,
            "difference_report_sha256": (
                None
                if self.difference_report is None
                else self.difference_report["difference_report_sha256"]
            ),
            "collision_screening_executed": False,
            "controller_commands": [],
            "wire_commands": [],
            "hardware_commands_generated": 0,
            "hardware_access": False,
            "physical_movements": 0,
            "physical_authority": False,
        }
        return {**core, "build_result_sha256": _sha(core)}


def build_installed_collision_profile_v1(
    measurement_manifest_path: str | Path,
    expected_measurement_manifest_file_sha256: str,
    *,
    context: SimulationContext,
) -> InstalledCollisionProfileBuildResultV1:
    """Build one byte-stable, zero-authority profile or retain a blocker."""

    document, validation = load_installed_collision_measurement_manifest_v1(
        measurement_manifest_path,
        expected_measurement_manifest_file_sha256,
        context=context,
    )
    manifest_file_hash = validation["measurement_manifest_file_sha256"]
    manifest_content_hash = validation["measurement_manifest_sha256"]
    if validation["status"] != READY_STATUS:
        blockers = tuple(validation["blockers"])
        status = (
            BLOCKED_CLEARANCE_STATUS
            if blockers == ("PENDING:CLEARANCE_POLICY",)
            else BLOCKED_MEASUREMENTS_STATUS
        )
        return InstalledCollisionProfileBuildResultV1(
            status,
            manifest_file_hash,
            manifest_content_hash,
            blockers,
            None,
            None,
            None,
            None,
        )

    readiness = assess_current_collision_readiness(context)
    requirements = {item.body_id: item for item in readiness.contract.requirements}
    sources = {
        f"measurement_source:{row['source_id']}": row["sha256"]
        for row in document["sources"]
    }
    sources.update({
        "measurement_manifest:content": manifest_content_hash,
        "measurement_manifest:file": manifest_file_hash,
    })
    bodies: list[dict[str, Any]] = []
    differences: list[dict[str, Any]] = []
    for row in sorted(document["body_measurements"], key=lambda item: item["body_id"]):
        body_id = row["body_id"]
        requirement = requirements[body_id]
        uncertainty = float(row["geometry_uncertainty_mm"])
        derived_primitives: list[dict[str, Any]] = []
        primitive_differences: list[dict[str, Any]] = []
        if requirement.binding_mode is not CollisionBindingMode.CONFIGURATION_SAMPLED:
            for primitive in row["envelope_primitives"]:
                derived, difference = _inflate_primitive(primitive, uncertainty)
                derived_primitives.append(derived)
                primitive_differences.append(difference)
        bodies.append({
            "body_id": body_id,
            "parent_frame": requirement.parent_frame,
            "role": requirement.role.value,
            "binding_mode": requirement.binding_mode.value,
            "evidence_state": "ACCEPTED_MEASURED",
            "source_reference": _source_reference(row["source_ids"]),
            "primitives": derived_primitives,
        })
        differences.append({
            "body_id": body_id,
            "binding_mode": requirement.binding_mode.value,
            "measurement_source_ids": sorted(row["source_ids"]),
            "geometry_uncertainty_mm": uncertainty,
            "static_primitive_count": len(derived_primitives),
            "configuration_sampled_geometry_deferred": (
                requirement.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
            ),
            "primitive_differences": primitive_differences,
        })

    clearance = document["clearance_measurement"]
    profile: dict[str, Any] = {
        "schema": PROFILE_SCHEMA,
        "profile_id": (
            "installed-profile-from-" + document["measurement_manifest_id"]
        ),
        "manifest_id": document["manifest_id"],
        "manifest_sha256": document["manifest_sha256"],
        "active_build_id": document["active_build_id"],
        "build_snapshot_sha256": document["build_snapshot_sha256"],
        "robot_model_sha256": document["robot_model_sha256"],
        "base_contract_sha256": document["base_contract_sha256"],
        "source_bindings": dict(sorted(sources.items())),
        "bodies": bodies,
        "pair_exclusions": [],
        "clearance_policy": {
            "minimum_separation_mm": float(clearance["minimum_separation_mm"]),
            "geometry_uncertainty_mm_per_body": float(
                clearance["geometry_uncertainty_mm_per_body"]
            ),
            "pose_uncertainty_mm_per_body": float(
                clearance["pose_uncertainty_mm_per_body"]
            ),
            "evidence_state": "ACCEPTED_MEASURED",
            "source_reference": _source_reference(clearance["source_ids"]),
        },
    }
    profile["content_sha256"] = _sha(profile)
    profile_bytes = _canonical(profile)
    profile_file_hash = hashlib.sha256(profile_bytes).hexdigest()

    # Audit through the existing strict consumer before exposing the bytes.
    load_installed_collision_geometry_profile_from_bytes_v1(
        profile_bytes,
        profile_file_hash,
        context=context,
        expected_source_bindings=sources,
    )

    difference_core: dict[str, Any] = {
        "schema": DIFFERENCE_SCHEMA,
        "measurement_manifest_file_sha256": manifest_file_hash,
        "measurement_manifest_content_sha256": manifest_content_hash,
        "profile_content_sha256": profile["content_sha256"],
        "profile_file_sha256": profile_file_hash,
        "fit_rule": "PER_BODY_UNCERTAINTY_INFLATION_V1",
        "body_differences": differences,
        "pair_exclusions": [],
        "configuration_sampled_body_ids": sorted(
            row["body_id"]
            for row in differences
            if row["configuration_sampled_geometry_deferred"]
        ),
        "controller_commands": [],
        "hardware_access": False,
        "physical_authority": False,
    }
    difference_report = {
        **difference_core,
        "difference_report_sha256": _sha(difference_core),
    }
    return InstalledCollisionProfileBuildResultV1(
        BUILT_STATUS,
        manifest_file_hash,
        manifest_content_hash,
        (),
        profile,
        profile_bytes,
        profile_file_hash,
        difference_report,
    )


def load_installed_collision_geometry_profile_from_bytes_v1(
    profile_bytes: bytes,
    profile_file_sha256: str,
    *,
    context: SimulationContext,
    expected_source_bindings: Mapping[str, str],
):
    """Audit generated bytes through the existing file-based strict loader."""

    # The existing consumer intentionally accepts an exact path and digest.
    # Use a private temporary file without retaining or installing the profile.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="rocell-icq2-") as directory:
        path = Path(directory) / "profile.json"
        path.write_bytes(profile_bytes)
        readiness = assess_current_collision_readiness(context)
        if readiness.active_build_id is None:
            raise InstalledCollisionProfileBuilderV1Error(
                "active build id is unavailable"
            )
        return load_installed_collision_geometry_profile(
            path,
            profile_file_sha256,
            base_contract=readiness.contract,
            expected_manifest_id=readiness.manifest_id,
            expected_manifest_sha256=readiness.manifest_sha256,
            expected_active_build_id=readiness.active_build_id,
            expected_build_snapshot_sha256=readiness.build_snapshot_hash,
            expected_robot_model_sha256=readiness.urdf_sha256,
            expected_source_bindings=expected_source_bindings,
        )


__all__ = [
    "BLOCKED_CLEARANCE_STATUS",
    "BLOCKED_MEASUREMENTS_STATUS",
    "BUILT_STATUS",
    "DIFFERENCE_SCHEMA",
    "RESULT_SCHEMA",
    "InstalledCollisionProfileBuildResultV1",
    "InstalledCollisionProfileBuilderV1Error",
    "build_installed_collision_profile_v1",
]
