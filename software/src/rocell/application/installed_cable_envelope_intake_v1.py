"""Typed synthetic rehearsal contract for configuration-sampled cable evidence.

This contract removes ambiguity from the future measured cable intake without
claiming that fixture dimensions were observed.  It binds pose-local samples
and adjacent swept envelopes to one installed collision profile and remains
incapable of physical qualification or execution.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from rocell.simulation.collision import CollisionBindingMode

from .installed_collision_geometry import InstalledCollisionGeometryProfile


SCHEMA = "rocell.installed_cable_envelope_intake.v1"
EVIDENCE_CLASS = "SYNTHETIC_OFFLINE_ONLY"
MAX_POSTURES = 64
_HASH = re.compile(r"^[0-9a-f]{64}$")
_BODY_ID = "attachment:moving_camera_cable"


class InstalledCableEnvelopeIntakeV1Error(ValueError):
    """Cable samples, lineage, or resource bounds are inconsistent."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise InstalledCableEnvelopeIntakeV1Error(f"{label} is not a SHA-256 digest")
    return value


def _capsule(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "kind", "start_mm", "end_mm", "radius_mm"
    } or value.get("kind") != "capsule":
        raise InstalledCableEnvelopeIntakeV1Error(f"{label} must be one capsule")
    for key in ("start_mm", "end_mm"):
        vector = value[key]
        if (
            not isinstance(vector, Sequence) or isinstance(vector, (str, bytes))
            or len(vector) != 3
            or any(isinstance(item, bool) or not isinstance(item, (int, float))
                   or not math.isfinite(float(item)) for item in vector)
        ):
            raise InstalledCableEnvelopeIntakeV1Error(f"{label}.{key} is invalid")
    radius = value["radius_mm"]
    if (
        isinstance(radius, bool) or not isinstance(radius, (int, float))
        or not math.isfinite(float(radius)) or float(radius) <= 0.0
    ):
        raise InstalledCableEnvelopeIntakeV1Error(f"{label}.radius_mm is invalid")
    return {
        "kind": "capsule", "start_mm": list(value["start_mm"]),
        "end_mm": list(value["end_mm"]), "radius_mm": float(radius),
    }


def _postures(values: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    if not 2 <= len(values) <= MAX_POSTURES:
        raise InstalledCableEnvelopeIntakeV1Error("posture count is outside its bound")
    rows: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        if not isinstance(value, Mapping) or set(value) != {
            "sequence", "posture_id", "joint_state_sha256", "capsules"
        } or value.get("sequence") != index:
            raise InstalledCableEnvelopeIntakeV1Error(
                f"posture {index} fields or sequence differ"
            )
        posture_id = value["posture_id"]
        capsules = value["capsules"]
        if not isinstance(posture_id, str) or not posture_id.strip():
            raise InstalledCableEnvelopeIntakeV1Error("posture_id is empty")
        if not isinstance(capsules, Sequence) or not 1 <= len(capsules) <= 16:
            raise InstalledCableEnvelopeIntakeV1Error("posture capsules are incomplete")
        rows.append({
            "sequence": index, "posture_id": posture_id,
            "joint_state_sha256": _digest(
                value["joint_state_sha256"], "joint_state_sha256"
            ),
            "capsules": [
                _capsule(item, f"posture {index} capsule {item_index}")
                for item_index, item in enumerate(capsules)
            ],
        })
    if len({row["posture_id"] for row in rows}) != len(rows):
        raise InstalledCableEnvelopeIntakeV1Error("posture ids are not unique")
    return tuple(rows)


def _sweeps(
    values: Sequence[Mapping[str, Any]], postures: tuple[dict[str, Any], ...]
) -> tuple[dict[str, Any], ...]:
    if len(values) != len(postures) - 1:
        raise InstalledCableEnvelopeIntakeV1Error(
            "swept envelopes do not cover every adjacent posture pair"
        )
    rows: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        if not isinstance(value, Mapping) or set(value) != {
            "sequence", "start_posture_id", "end_posture_id", "capsules"
        } or value.get("sequence") != index:
            raise InstalledCableEnvelopeIntakeV1Error(
                f"sweep {index} fields or sequence differ"
            )
        if (
            value.get("start_posture_id") != postures[index]["posture_id"]
            or value.get("end_posture_id") != postures[index + 1]["posture_id"]
        ):
            raise InstalledCableEnvelopeIntakeV1Error(
                f"sweep {index} lineage differs from adjacent postures"
            )
        capsules = value["capsules"]
        if not isinstance(capsules, Sequence) or not 1 <= len(capsules) <= 16:
            raise InstalledCableEnvelopeIntakeV1Error("sweep capsules are incomplete")
        rows.append({
            "sequence": index,
            "start_posture_id": value["start_posture_id"],
            "end_posture_id": value["end_posture_id"],
            "capsules": [
                _capsule(item, f"sweep {index} capsule {item_index}")
                for item_index, item in enumerate(capsules)
            ],
        })
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class InstalledCableEnvelopeIntakeV1:
    profile: InstalledCollisionGeometryProfile
    sampled_body_id: str
    source_sha256: str
    maximum_uncertainty_mm: float
    postures: tuple[Mapping[str, Any], ...]
    swept_envelopes: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.profile, InstalledCollisionGeometryProfile):
            raise TypeError("profile must be InstalledCollisionGeometryProfile")
        if self.sampled_body_id != _BODY_ID:
            raise InstalledCableEnvelopeIntakeV1Error("sampled cable body differs")
        body = self.profile.contract.bodies_by_id.get(self.sampled_body_id)
        if body is None or body.binding_mode is not CollisionBindingMode.CONFIGURATION_SAMPLED:
            raise InstalledCableEnvelopeIntakeV1Error(
                "profile does not declare the required sampled cable body"
            )
        source = _digest(self.source_sha256, "source_sha256")
        if source not in self.profile.source_bindings.values():
            raise InstalledCableEnvelopeIntakeV1Error(
                "cable source is absent from installed profile bindings"
            )
        uncertainty = self.maximum_uncertainty_mm
        if (
            isinstance(uncertainty, bool) or not isinstance(uncertainty, (int, float))
            or not math.isfinite(float(uncertainty)) or float(uncertainty) < 0.0
        ):
            raise InstalledCableEnvelopeIntakeV1Error(
                "maximum_uncertainty_mm is invalid"
            )
        postures = _postures(self.postures)
        sweeps = _sweeps(self.swept_envelopes, postures)
        object.__setattr__(self, "maximum_uncertainty_mm", float(uncertainty))
        object.__setattr__(self, "postures", postures)
        object.__setattr__(self, "swept_envelopes", sweeps)

    @property
    def content_sha256(self) -> str:
        return _sha(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "evidence_class": EVIDENCE_CLASS,
            "installed_collision_profile_sha256": self.profile.content_sha256,
            "sampled_body_id": self.sampled_body_id,
            "source_sha256": self.source_sha256,
            "maximum_uncertainty_mm": self.maximum_uncertainty_mm,
            "postures": [dict(row) for row in self.postures],
            "swept_envelopes": [dict(row) for row in self.swept_envelopes],
            "template_complete": True,
            "qualification_installed": False,
            "hardware_access": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "physical_authority": False,
        }


def build_synthetic_cable_envelope_intake_v1(
    profile: InstalledCollisionGeometryProfile,
) -> InstalledCableEnvelopeIntakeV1:
    """Build a deterministic far-field fixture for contract rehearsal only."""

    source = profile.source_bindings.get(
        "synthetic_cable_envelope", sorted(profile.source_bindings.values())[0]
    )
    names = ("synthetic-park", "synthetic-left", "synthetic-right")
    postures = tuple({
        "sequence": index, "posture_id": name,
        "joint_state_sha256": hashlib.sha256(name.encode("ascii")).hexdigest(),
        "capsules": [{
            "kind": "capsule", "start_mm": [50000.0 + index, 0.0, 0.0],
            "end_mm": [50010.0 + index, 0.0, 0.0], "radius_mm": 0.1,
        }],
    } for index, name in enumerate(names))
    sweeps = tuple({
        "sequence": index, "start_posture_id": names[index],
        "end_posture_id": names[index + 1],
        "capsules": [{
            "kind": "capsule", "start_mm": [50000.0 + index, 0.0, 0.0],
            "end_mm": [50011.0 + index, 0.0, 0.0], "radius_mm": 0.2,
        }],
    } for index in range(len(names) - 1))
    return InstalledCableEnvelopeIntakeV1(
        profile, _BODY_ID, source, 0.5, postures, sweeps
    )


__all__ = [
    "EVIDENCE_CLASS", "MAX_POSTURES", "SCHEMA",
    "InstalledCableEnvelopeIntakeV1", "InstalledCableEnvelopeIntakeV1Error",
    "build_synthetic_cable_envelope_intake_v1",
]
