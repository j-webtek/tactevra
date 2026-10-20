"""Strict content-addressed installed collision-geometry profile loader.

The primitive collision kernel already exists.  This boundary supplies its
missing evidence contract without inventing dimensions: every required body
must be present, source hashes and build/model identity must match exactly, and
only measured geometry/clearance evidence is accepted.  Loading remains
offline and confers no motion or contact authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from rocell.geometry import Rotation3, Vec3
from rocell.simulation.collision import (
    CollisionAttachmentProfile,
    HARD_MAX_BODIES,
    HARD_MAX_EXCLUDED_PAIRS,
    HARD_MAX_PRIMITIVES_PER_BODY,
    CapsuleMm,
    CollisionBindingMode,
    CollisionBody,
    CollisionClearanceEvidenceState,
    CollisionClearancePolicy,
    CollisionEvidenceState,
    CollisionExclusionEvidenceState,
    CollisionExclusionScope,
    CollisionGeometryContract,
    CollisionPairExclusion,
    OrientedBoxMm,
    SphereMm,
    audit_collision_geometry,
)

from .collision_readiness import assess_current_collision_readiness
from .context import SimulationContext


SCHEMA = "rocell.installed_collision_geometry_profile.v1"
MAX_PROFILE_BYTES = 1_048_576
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class InstalledCollisionGeometryError(ValueError):
    """Installed geometry does not satisfy the exact measured profile contract."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _exact(value: object, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InstalledCollisionGeometryError(f"{label} must be an object")
    actual = set(value)
    if actual != fields:
        raise InstalledCollisionGeometryError(
            f"{label} fields differ: missing={sorted(fields - actual)}, "
            f"unexpected={sorted(actual - fields)}"
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InstalledCollisionGeometryError(f"{label} must be nonempty text")
    return value.strip()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise InstalledCollisionGeometryError(f"{label} must be a SHA-256 digest")
    return value


def _number(
    value: object,
    label: str,
    *,
    nonnegative: bool = False,
    positive: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InstalledCollisionGeometryError(f"{label} must be numeric")
    result = float(value)
    if (
        not math.isfinite(result)
        or (positive and result <= 0.0)
        or (nonnegative and result < 0.0)
    ):
        raise InstalledCollisionGeometryError(f"{label} is outside its finite range")
    return result


def _vec(value: object, label: str, *, positive: bool = False) -> Vec3:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise InstalledCollisionGeometryError(f"{label} must contain three numbers")
    result = Vec3(*(_number(item, label, positive=positive) for item in value))
    return result


def _rotation(value: object, label: str) -> Rotation3:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 9:
        raise InstalledCollisionGeometryError(f"{label} must contain nine numbers")
    try:
        return Rotation3(tuple(_number(item, label) for item in value))
    except (TypeError, ValueError) as exc:
        raise InstalledCollisionGeometryError(f"{label} is not a rotation") from exc


def _primitive(value: object, body_id: str, index: int):
    label = f"body {body_id} primitive {index}"
    if not isinstance(value, Mapping):
        raise InstalledCollisionGeometryError(f"{label} must be an object")
    kind = value.get("kind")
    if kind == "sphere":
        item = _exact(value, {"kind", "center_mm", "radius_mm"}, label)
        return SphereMm(
            _vec(item["center_mm"], f"{label}.center_mm"),
            _number(item["radius_mm"], f"{label}.radius_mm", positive=True),
        )
    if kind == "capsule":
        item = _exact(value, {"kind", "start_mm", "end_mm", "radius_mm"}, label)
        return CapsuleMm(
            _vec(item["start_mm"], f"{label}.start_mm"),
            _vec(item["end_mm"], f"{label}.end_mm"),
            _number(item["radius_mm"], f"{label}.radius_mm", positive=True),
        )
    if kind == "oriented_box":
        item = _exact(
            value,
            {"kind", "center_mm", "half_extents_mm", "rotation_row_major"},
            label,
        )
        return OrientedBoxMm(
            _vec(item["center_mm"], f"{label}.center_mm"),
            _vec(item["half_extents_mm"], f"{label}.half_extents_mm", positive=True),
            _rotation(item["rotation_row_major"], f"{label}.rotation_row_major"),
        )
    raise InstalledCollisionGeometryError(f"{label} has unsupported kind {kind!r}")


@dataclass(frozen=True, slots=True)
class InstalledCollisionGeometryProfile:
    profile_id: str
    manifest_id: str
    manifest_sha256: str
    active_build_id: str
    build_snapshot_sha256: str
    robot_model_sha256: str
    base_contract_sha256: str
    source_bindings: Mapping[str, str]
    contract: CollisionGeometryContract
    clearance_policy: CollisionClearancePolicy
    content_sha256: str
    file_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_bindings", MappingProxyType(dict(sorted(self.source_bindings.items())))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "profile_id": self.profile_id,
            "manifest_id": self.manifest_id,
            "manifest_sha256": self.manifest_sha256,
            "active_build_id": self.active_build_id,
            "build_snapshot_sha256": self.build_snapshot_sha256,
            "robot_model_sha256": self.robot_model_sha256,
            "base_contract_sha256": self.base_contract_sha256,
            "source_bindings": dict(self.source_bindings),
            "contract_sha256": self.contract.content_hash,
            "clearance_policy_sha256": hashlib.sha256(
                _canonical(self.clearance_policy.to_dict())
            ).hexdigest(),
            "content_sha256": self.content_sha256,
            "file_sha256": self.file_sha256,
            "geometry_audit": audit_collision_geometry(self.contract).to_dict(),
            "hardware_commands_generated": 0,
            "hardware_access": False,
            "physical_authority": False,
        }


def _decode_profile(
    document: Mapping[str, Any],
    *,
    file_sha256: str,
    base_contract: CollisionGeometryContract,
    expected_manifest_id: str,
    expected_manifest_sha256: str,
    expected_active_build_id: str,
    expected_build_snapshot_sha256: str,
    expected_robot_model_sha256: str,
    expected_source_bindings: Mapping[str, str],
) -> InstalledCollisionGeometryProfile:
    root = _exact(
        document,
        {
            "schema", "profile_id", "manifest_id", "manifest_sha256",
            "active_build_id", "build_snapshot_sha256",
            "robot_model_sha256", "base_contract_sha256", "source_bindings",
            "bodies", "pair_exclusions", "clearance_policy", "content_sha256",
        },
        "installed collision profile",
    )
    if root["schema"] != SCHEMA:
        raise InstalledCollisionGeometryError("installed collision profile schema mismatch")
    profile_id = _text(root["profile_id"], "profile_id")
    manifest_id = _text(root["manifest_id"], "manifest_id")
    manifest_hash = _digest(root["manifest_sha256"], "manifest_sha256")
    active_build_id = _text(root["active_build_id"], "active_build_id")
    build_snapshot_hash = _digest(
        root["build_snapshot_sha256"], "build_snapshot_sha256"
    )
    model_hash = _digest(root["robot_model_sha256"], "robot_model_sha256")
    base_hash = _digest(root["base_contract_sha256"], "base_contract_sha256")
    if (
        manifest_id != expected_manifest_id
        or manifest_hash != _digest(expected_manifest_sha256, "expected_manifest_sha256")
        or active_build_id != expected_active_build_id
        or build_snapshot_hash
        != _digest(expected_build_snapshot_sha256, "expected_build_snapshot_sha256")
        or model_hash != expected_robot_model_sha256
        or base_hash != base_contract.content_hash
    ):
        raise InstalledCollisionGeometryError(
            "installed collision profile build/model/base-contract binding mismatch"
        )
    sources = root["source_bindings"]
    if not isinstance(sources, Mapping) or not sources:
        raise InstalledCollisionGeometryError("source_bindings must be a nonempty object")
    normalized_sources = {
        _text(key, "source binding id"): _digest(value, f"source binding {key}")
        for key, value in sources.items()
    }
    if len(normalized_sources) != len(sources):
        raise InstalledCollisionGeometryError("source binding ids must be unique after normalization")
    normalized_expected_sources = {
        _text(key, "expected source binding id"): _digest(
            value, f"expected source binding {key}"
        )
        for key, value in expected_source_bindings.items()
    }
    if len(normalized_expected_sources) != len(expected_source_bindings):
        raise InstalledCollisionGeometryError(
            "expected source binding ids must be unique after normalization"
        )
    if normalized_sources != normalized_expected_sources:
        raise InstalledCollisionGeometryError("source binding hashes do not match expected inputs")

    requirements = {item.body_id: item for item in base_contract.requirements}
    raw_bodies = root["bodies"]
    if not isinstance(raw_bodies, Sequence) or isinstance(raw_bodies, (str, bytes)):
        raise InstalledCollisionGeometryError("bodies must be an array")
    if len(raw_bodies) > HARD_MAX_BODIES:
        raise InstalledCollisionGeometryError("body count exceeds collision hard limit")
    bodies: list[CollisionBody] = []
    for index, raw in enumerate(raw_bodies):
        body = _exact(
            raw,
            {"body_id", "parent_frame", "role", "binding_mode", "evidence_state", "source_reference", "primitives"},
            f"body {index}",
        )
        body_id = _text(body["body_id"], f"body {index}.body_id")
        requirement = requirements.get(body_id)
        if requirement is None:
            raise InstalledCollisionGeometryError(f"profile contains unknown body {body_id}")
        try:
            role = type(requirement.role)(body["role"])
            binding = CollisionBindingMode(body["binding_mode"])
            evidence = CollisionEvidenceState(body["evidence_state"])
        except (TypeError, ValueError) as exc:
            raise InstalledCollisionGeometryError(f"body {body_id} enum value is invalid") from exc
        if (
            body["parent_frame"] != requirement.parent_frame
            or role is not requirement.role
            or binding is not requirement.binding_mode
        ):
            raise InstalledCollisionGeometryError(
                f"body {body_id} differs from required parent/role/binding"
            )
        if evidence is not CollisionEvidenceState.ACCEPTED_MEASURED:
            raise InstalledCollisionGeometryError(
                f"body {body_id} must use ACCEPTED_MEASURED evidence"
            )
        raw_primitives = body["primitives"]
        if not isinstance(raw_primitives, Sequence) or isinstance(raw_primitives, (str, bytes)):
            raise InstalledCollisionGeometryError(f"body {body_id} primitives must be an array")
        if len(raw_primitives) > HARD_MAX_PRIMITIVES_PER_BODY:
            raise InstalledCollisionGeometryError(f"body {body_id} exceeds primitive limit")
        primitives = tuple(
            _primitive(item, body_id, primitive_index)
            for primitive_index, item in enumerate(raw_primitives)
        )
        if binding is CollisionBindingMode.CONFIGURATION_SAMPLED:
            if primitives:
                raise InstalledCollisionGeometryError(
                    f"configuration-sampled body {body_id} must provide geometry per pose"
                )
        elif not primitives:
            raise InstalledCollisionGeometryError(f"body {body_id} has no measured primitives")
        bodies.append(
            CollisionBody(
                body_id,
                requirement.parent_frame,
                requirement.role,
                evidence,
                primitives,
                binding,
                _text(body["source_reference"], f"body {body_id}.source_reference"),
            )
        )
    if {item.body_id for item in bodies} != set(requirements):
        missing = sorted(set(requirements) - {item.body_id for item in bodies})
        raise InstalledCollisionGeometryError(f"profile body coverage is incomplete: {missing}")

    raw_exclusions = root["pair_exclusions"]
    if not isinstance(raw_exclusions, Sequence) or isinstance(raw_exclusions, (str, bytes)):
        raise InstalledCollisionGeometryError("pair_exclusions must be an array")
    if len(raw_exclusions) > HARD_MAX_EXCLUDED_PAIRS:
        raise InstalledCollisionGeometryError("pair exclusion count exceeds hard limit")
    exclusions: list[CollisionPairExclusion] = []
    for index, raw in enumerate(raw_exclusions):
        item = _exact(
            raw,
            {"body_pair", "scope", "evidence_state", "rationale", "source_reference"},
            f"pair exclusion {index}",
        )
        pair = item["body_pair"]
        if not isinstance(pair, Sequence) or isinstance(pair, (str, bytes)) or len(pair) != 2:
            raise InstalledCollisionGeometryError("exclusion body_pair must have two ids")
        if (
            item["scope"] != CollisionExclusionScope.ENGINEERING_GLOBAL.value
            or item["evidence_state"]
            != CollisionExclusionEvidenceState.ACCEPTED_ENGINEERING.value
        ):
            raise InstalledCollisionGeometryError(
                "installed profile exclusions require accepted global engineering evidence"
            )
        exclusions.append(
            CollisionPairExclusion(
                _text(pair[0], "exclusion first body"),
                _text(pair[1], "exclusion second body"),
                CollisionExclusionScope.ENGINEERING_GLOBAL,
                CollisionExclusionEvidenceState.ACCEPTED_ENGINEERING,
                _text(item["rationale"], "exclusion rationale"),
                _text(item["source_reference"], "exclusion source_reference"),
            )
        )

    clearance = _exact(
        root["clearance_policy"],
        {"minimum_separation_mm", "geometry_uncertainty_mm_per_body", "pose_uncertainty_mm_per_body", "evidence_state", "source_reference"},
        "clearance_policy",
    )
    if clearance["evidence_state"] != CollisionClearanceEvidenceState.ACCEPTED_MEASURED.value:
        raise InstalledCollisionGeometryError("clearance policy must use ACCEPTED_MEASURED evidence")
    clearance_policy = CollisionClearancePolicy(
        _number(
            clearance["minimum_separation_mm"],
            "minimum_separation_mm",
            nonnegative=True,
        ),
        _number(
            clearance["geometry_uncertainty_mm_per_body"],
            "geometry uncertainty",
            nonnegative=True,
        ),
        _number(
            clearance["pose_uncertainty_mm_per_body"],
            "pose uncertainty",
            nonnegative=True,
        ),
        CollisionClearanceEvidenceState.ACCEPTED_MEASURED,
        _text(clearance["source_reference"], "clearance source_reference"),
    )
    claimed_hash = _digest(root["content_sha256"], "content_sha256")
    hash_payload = dict(root)
    del hash_payload["content_sha256"]
    if hashlib.sha256(_canonical(hash_payload)).hexdigest() != claimed_hash:
        raise InstalledCollisionGeometryError("installed collision content hash mismatch")
    contract = CollisionGeometryContract(
        f"{profile_id}:contract",
        base_contract.root_frame,
        base_contract.requirements,
        tuple(bodies),
        tuple(exclusions),
    )
    audit = audit_collision_geometry(contract)
    if not audit.diagnostic_ready:
        raise InstalledCollisionGeometryError("decoded measured collision contract is incomplete")
    return InstalledCollisionGeometryProfile(
        profile_id,
        manifest_id,
        manifest_hash,
        active_build_id,
        build_snapshot_hash,
        model_hash,
        base_hash,
        normalized_sources,
        contract,
        clearance_policy,
        claimed_hash,
        file_sha256,
    )


def load_installed_collision_geometry_profile(
    path: str | Path,
    expected_file_sha256: str,
    *,
    base_contract: CollisionGeometryContract,
    expected_manifest_id: str,
    expected_manifest_sha256: str,
    expected_active_build_id: str,
    expected_build_snapshot_sha256: str,
    expected_robot_model_sha256: str,
    expected_source_bindings: Mapping[str, str],
) -> InstalledCollisionGeometryProfile:
    """Read, hash, strictly decode, and bind one measured collision profile."""

    expected_file = _digest(expected_file_sha256, "expected_file_sha256")
    source = Path(path)
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise InstalledCollisionGeometryError(f"cannot read collision profile {source}") from exc
    if len(payload) > MAX_PROFILE_BYTES:
        raise InstalledCollisionGeometryError("installed collision profile exceeds byte limit")
    actual_file = hashlib.sha256(payload).hexdigest()
    if actual_file != expected_file:
        raise InstalledCollisionGeometryError("installed collision profile file hash mismatch")

    def reject_constant(value: str) -> None:
        raise InstalledCollisionGeometryError(f"non-finite JSON constant {value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise InstalledCollisionGeometryError(f"duplicate JSON field {key!r}")
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstalledCollisionGeometryError("installed collision profile is not strict JSON") from exc
    return _decode_profile(
        document,
        file_sha256=actual_file,
        base_contract=base_contract,
        expected_manifest_id=expected_manifest_id,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_active_build_id=expected_active_build_id,
        expected_build_snapshot_sha256=expected_build_snapshot_sha256,
        expected_robot_model_sha256=expected_robot_model_sha256,
        expected_source_bindings=expected_source_bindings,
    )


def load_installed_collision_geometry_for_context(
    path: str | Path,
    expected_file_sha256: str,
    *,
    context: SimulationContext,
    expected_source_bindings: Mapping[str, str],
    attachment_profile: CollisionAttachmentProfile = (
        CollisionAttachmentProfile.STYLUS_ATTACHMENT
    ),
) -> InstalledCollisionGeometryProfile:
    """Revalidate the locked context, then load its exact measured profile."""

    readiness = assess_current_collision_readiness(
        context,
        attachment_profile=attachment_profile,
    )
    if readiness.active_build_id is None:
        raise InstalledCollisionGeometryError(
            "verified context has no active build id for installed geometry"
        )
    return load_installed_collision_geometry_profile(
        path,
        expected_file_sha256,
        base_contract=readiness.contract,
        expected_manifest_id=readiness.manifest_id,
        expected_manifest_sha256=readiness.manifest_sha256,
        expected_active_build_id=readiness.active_build_id,
        expected_build_snapshot_sha256=readiness.build_snapshot_hash,
        expected_robot_model_sha256=readiness.urdf_sha256,
        expected_source_bindings=expected_source_bindings,
    )


__all__ = [
    "SCHEMA",
    "InstalledCollisionGeometryError",
    "InstalledCollisionGeometryProfile",
    "load_installed_collision_geometry_for_context",
    "load_installed_collision_geometry_profile",
]
