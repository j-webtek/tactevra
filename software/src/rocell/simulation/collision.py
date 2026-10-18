"""Fail-closed, simulation-only collision geometry and query foundation.

The controlled RoArm URDF deliberately contains kinematics but no collision
elements.  The current RC03 artifacts also leave the installed camera holder,
camera connector, moving cable, complete gripper, tool, base, and clamp
geometry unresolved.  This module therefore separates two concerns:

* a typed coverage audit that says exactly which required bodies are missing
  or unknown; and
* bounded primitive collision queries that can be exercised with synthetic or
  subsequently reduced, source-bound geometry.

No default physical dimensions are supplied here.  ``PINNED_DIGITAL`` and
``SYNTHETIC_TEST_ONLY`` geometry can support a diagnostic result, but only
``ACCEPTED_MEASURED`` geometry counts toward physical-geometry completeness.
Even a complete measured model has no motion or physical-release authority.

All lengths are millimetres.  A ``RigidTransform(root, body_frame, ...)`` maps
primitive coordinates from their bound body frame into the collision root.
Sweeps are bounded discrete samples; they are explicitly not a continuous
collision proof.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence, TypeAlias

from rocell.geometry import RigidTransform, Rotation3, UrdfModel, Vec3
from rocell.models.units import finite_real

from .scene import NominalWorkcellScene


COLLISION_CONTRACT_SCHEMA = "rocell.collision_geometry_contract.v1"
COLLISION_AUDIT_SCHEMA = "rocell.collision_geometry_audit.v1"
COLLISION_POSE_REPORT_SCHEMA = "rocell.collision_pose_report.v1"
COLLISION_SWEEP_REPORT_SCHEMA = "rocell.collision_sweep_report.v1"
COLLISION_CLEARANCE_LOWER_BOUND_SCHEMA = "rocell.collision_clearance_lower_bound.v1"

HARD_MAX_REQUIREMENTS = 128
HARD_MAX_BODIES = 128
HARD_MAX_PRIMITIVES_PER_BODY = 64
HARD_MAX_EXCLUDED_PAIRS = 4_096
HARD_MAX_POSE_TRANSFORMS = 256
HARD_MAX_BODY_PAIRS_PER_POSE = 8_192
HARD_MAX_PRIMITIVE_PAIR_TESTS_PER_POSE = 65_536
HARD_MAX_SWEEP_SAMPLES = 512
HARD_MAX_SWEEP_BODY_PAIR_EVALUATIONS = 262_144
HARD_MAX_SWEEP_PRIMITIVE_PAIR_EVALUATIONS = 1_048_576

_RELATIVE_PARALLEL_TOLERANCE = 64.0 * math.ulp(1.0)


class CollisionContractError(ValueError):
    """Collision geometry, pose, or policy violates the typed contract."""


class CollisionResourceLimitError(CollisionContractError):
    """A request exceeds a declared or implementation hard resource cap."""


class CollisionEvidenceState(str, Enum):
    """Evidence state for one complete body envelope."""

    ACCEPTED_MEASURED = "ACCEPTED_MEASURED"
    PINNED_DIGITAL = "PINNED_DIGITAL"
    SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"
    UNKNOWN = "UNKNOWN"
    MISSING = "MISSING"

    @property
    def supports_diagnostic(self) -> bool:
        return self in {
            CollisionEvidenceState.ACCEPTED_MEASURED,
            CollisionEvidenceState.PINNED_DIGITAL,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
        }

    @property
    def is_physically_accepted_geometry(self) -> bool:
        return self is CollisionEvidenceState.ACCEPTED_MEASURED


class CollisionExclusionEvidenceState(str, Enum):
    """Evidence authority behind one globally applied diagnostic exclusion."""

    ACCEPTED_ENGINEERING = "ACCEPTED_ENGINEERING"
    PINNED_KINEMATIC_DIAGNOSTIC = "PINNED_KINEMATIC_DIAGNOSTIC"
    SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"

    @property
    def is_physically_accepted(self) -> bool:
        return self is CollisionExclusionEvidenceState.ACCEPTED_ENGINEERING


class CollisionExclusionScope(str, Enum):
    """Allowed global scopes; phase-specific contact allowances are excluded."""

    ENGINEERING_GLOBAL = "ENGINEERING_GLOBAL"
    URDF_ADJACENT_DIAGNOSTIC = "URDF_ADJACENT_DIAGNOSTIC"
    SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"


class CollisionClearanceEvidenceState(str, Enum):
    """Provenance of clearance and uncertainty values used by a query."""

    ACCEPTED_MEASURED = "ACCEPTED_MEASURED"
    PINNED_DIGITAL = "PINNED_DIGITAL"
    SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"

    @property
    def is_physically_accepted(self) -> bool:
        return self is CollisionClearanceEvidenceState.ACCEPTED_MEASURED


class CollisionBodyRole(str, Enum):
    ROBOT_LINK = "ROBOT_LINK"
    BASE_CLAMP = "BASE_CLAMP"
    ATTACHMENT = "ATTACHMENT"
    CAMERA = "CAMERA"
    CONNECTOR = "CONNECTOR"
    CABLE = "CABLE"
    TOOL = "TOOL"
    STATIC_ENVIRONMENT = "STATIC_ENVIRONMENT"


class CollisionBindingMode(str, Enum):
    """How a body's primitives are supplied at a configuration."""

    RIGID_FRAME = "RIGID_FRAME"
    STATIC_ROOT = "STATIC_ROOT"
    CONFIGURATION_SAMPLED = "CONFIGURATION_SAMPLED"


class CollisionEvaluationStatus(str, Enum):
    BLOCKED_INCOMPLETE_GEOMETRY = "BLOCKED_INCOMPLETE_GEOMETRY"
    BLOCKED_INCOMPLETE_POSE = "BLOCKED_INCOMPLETE_POSE"
    BLOCKED_CLEARANCE_POLICY = "BLOCKED_CLEARANCE_POLICY"
    BLOCKED_DEFORMABLE_SWEEP = "BLOCKED_DEFORMABLE_SWEEP"
    COLLISION_DETECTED = "COLLISION_DETECTED"
    CLEAR_AT_SAMPLED_POSE = "CLEAR_AT_SAMPLED_POSE"
    CLEAR_AT_DISCRETE_SWEEP_SAMPLES = "CLEAR_AT_DISCRETE_SWEEP_SAMPLES"


class CollisionClearanceLowerBoundStatus(str, Enum):
    """Outcome of a conservative residual-clearance calculation."""

    CLEAR = "CLEAR"
    COLLISION = "COLLISION"
    INDETERMINATE = "INDETERMINATE"


class CollisionBlockerCode(str, Enum):
    REQUIRED_BODY_BINDING_MISSING = "REQUIRED_BODY_BINDING_MISSING"
    REQUIRED_BODY_GEOMETRY_MISSING = "REQUIRED_BODY_GEOMETRY_MISSING"
    REQUIRED_BODY_GEOMETRY_UNKNOWN = "REQUIRED_BODY_GEOMETRY_UNKNOWN"
    REQUIRED_BODY_PRIMITIVES_EMPTY = "REQUIRED_BODY_PRIMITIVES_EMPTY"
    REQUIRED_BODY_PARENT_MISMATCH = "REQUIRED_BODY_PARENT_MISMATCH"
    REQUIRED_BODY_ROLE_MISMATCH = "REQUIRED_BODY_ROLE_MISMATCH"
    REQUIRED_BODY_BINDING_MODE_MISMATCH = "REQUIRED_BODY_BINDING_MODE_MISMATCH"
    STATIC_ROOT_PARENT_NOT_CONTRACT_ROOT = "STATIC_ROOT_PARENT_NOT_CONTRACT_ROOT"
    POSE_TRANSFORM_MISSING = "POSE_TRANSFORM_MISSING"
    POSE_TRANSFORM_FRAME_MISMATCH = "POSE_TRANSFORM_FRAME_MISMATCH"
    CONFIGURATION_GEOMETRY_MISSING = "CONFIGURATION_GEOMETRY_MISSING"
    CONFIGURATION_GEOMETRY_EVIDENCE_UNUSABLE = (
        "CONFIGURATION_GEOMETRY_EVIDENCE_UNUSABLE"
    )
    CLEARANCE_POLICY_MISSING = "CLEARANCE_POLICY_MISSING"
    DEFORMABLE_SWEEP_INTERMEDIATE_GEOMETRY_UNAVAILABLE = (
        "DEFORMABLE_SWEEP_INTERMEDIATE_GEOMETRY_UNAVAILABLE"
    )


def _name(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CollisionContractError(f"{label} must be a non-empty string")
    return value.strip()


def _nonnegative(value: object, label: str) -> float:
    result = finite_real(value, name=label)
    if result < 0.0:
        raise CollisionContractError(f"{label} must be non-negative")
    return result


def _positive(value: object, label: str) -> float:
    result = finite_real(value, name=label)
    if result <= 0.0:
        raise CollisionContractError(f"{label} must be positive")
    return result


def _positive_int(value: object, label: str, hard_maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CollisionContractError(f"{label} must be a positive integer")
    if value > hard_maximum:
        raise CollisionResourceLimitError(
            f"{label} {value} exceeds hard maximum {hard_maximum}"
        )
    return value


def _bounded_tuple(values: Iterable[Any], maximum: int, label: str) -> tuple[Any, ...]:
    """Materialize at most ``maximum + 1`` items before rejecting an input."""

    result: list[Any] = []
    try:
        iterator = iter(values)
    except TypeError as exc:
        raise TypeError(f"{label} must be iterable") from exc
    for _ in range(maximum + 1):
        try:
            result.append(next(iterator))
        except StopIteration:
            return tuple(result)
    raise CollisionResourceLimitError(f"{label} exceeds hard maximum {maximum}")


def _bounded_mapping_items(
    values: Mapping[Any, Any],
    maximum: int,
    label: str,
) -> tuple[tuple[Any, Any], ...]:
    """Materialize a mapping through a MAX+1 sentinel without trusting len()."""

    if not isinstance(values, MappingABC):
        raise TypeError(f"{label} must be a mapping")
    raw_keys = _bounded_tuple(values, maximum, f"{label} items")
    result: list[tuple[Any, Any]] = []
    seen_keys: set[Any] = set()
    for key in raw_keys:
        try:
            duplicate = key in seen_keys
            seen_keys.add(key)
        except TypeError as exc:
            raise CollisionContractError(f"{label} keys must be hashable") from exc
        if duplicate:
            raise CollisionContractError(f"{label} contains duplicate key {key!r}")
        try:
            value = values[key]
        except (KeyError, IndexError) as exc:
            raise CollisionContractError(
                f"{label} changed while it was materialized"
            ) from exc
        result.append((key, value))
    if len(result) > maximum:
        # Defensive recheck independent of the source mapping's reported size.
        raise CollisionResourceLimitError(f"{label} exceeds hard maximum {maximum}")
    return tuple(result)


def _stable_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _vec_to_list(value: Vec3) -> list[float]:
    return [value.x, value.y, value.z]


def _transform_to_dict(value: RigidTransform) -> dict[str, Any]:
    return {
        "parent_frame": value.parent_frame,
        "child_frame": value.child_frame,
        "rotation_row_major": list(value.rotation.matrix),
        "translation_mm": _vec_to_list(value.translation_mm),
    }


@dataclass(frozen=True, slots=True)
class SphereMm:
    center_mm: Vec3
    radius_mm: float

    def __post_init__(self) -> None:
        if not isinstance(self.center_mm, Vec3):
            raise TypeError("center_mm must be Vec3")
        object.__setattr__(self, "radius_mm", _positive(self.radius_mm, "sphere radius_mm"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "sphere",
            "center_mm": _vec_to_list(self.center_mm),
            "radius_mm": self.radius_mm,
        }


@dataclass(frozen=True, slots=True)
class CapsuleMm:
    start_mm: Vec3
    end_mm: Vec3
    radius_mm: float

    def __post_init__(self) -> None:
        if not isinstance(self.start_mm, Vec3) or not isinstance(self.end_mm, Vec3):
            raise TypeError("capsule endpoints must be Vec3")
        object.__setattr__(self, "radius_mm", _positive(self.radius_mm, "capsule radius_mm"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "capsule",
            "start_mm": _vec_to_list(self.start_mm),
            "end_mm": _vec_to_list(self.end_mm),
            "radius_mm": self.radius_mm,
        }


@dataclass(frozen=True, slots=True)
class OrientedBoxMm:
    center_mm: Vec3
    half_extents_mm: Vec3
    rotation: Rotation3 = field(default_factory=Rotation3.identity)

    def __post_init__(self) -> None:
        if not isinstance(self.center_mm, Vec3):
            raise TypeError("center_mm must be Vec3")
        if not isinstance(self.half_extents_mm, Vec3):
            raise TypeError("half_extents_mm must be Vec3")
        if min(
            self.half_extents_mm.x,
            self.half_extents_mm.y,
            self.half_extents_mm.z,
        ) <= 0.0:
            raise CollisionContractError("box half extents must all be positive")
        if not isinstance(self.rotation, Rotation3):
            raise TypeError("rotation must be Rotation3")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "oriented_box",
            "center_mm": _vec_to_list(self.center_mm),
            "half_extents_mm": _vec_to_list(self.half_extents_mm),
            "rotation_row_major": list(self.rotation.matrix),
        }


CollisionPrimitive: TypeAlias = SphereMm | CapsuleMm | OrientedBoxMm


def _validate_primitives(
    primitives: Iterable[CollisionPrimitive],
    *,
    label: str,
) -> tuple[CollisionPrimitive, ...]:
    values = _bounded_tuple(primitives, HARD_MAX_PRIMITIVES_PER_BODY, label)
    if any(not isinstance(item, (SphereMm, CapsuleMm, OrientedBoxMm)) for item in values):
        raise TypeError(f"{label} contains an unsupported primitive")
    return values


@dataclass(frozen=True, slots=True)
class SampledCollisionGeometry:
    """Per-pose geometry for a deformable/configuration-sampled body."""

    primitives: tuple[CollisionPrimitive, ...]
    evidence_state: CollisionEvidenceState
    source_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "primitives",
            _validate_primitives(self.primitives, label="sampled collision geometry"),
        )
        if not self.primitives:
            raise CollisionContractError(
                "sampled collision geometry must contain at least one primitive"
            )
        if not isinstance(self.evidence_state, CollisionEvidenceState):
            raise TypeError("evidence_state must be CollisionEvidenceState")
        object.__setattr__(
            self,
            "source_reference",
            _name(self.source_reference, "sampled geometry source_reference"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_state": self.evidence_state.value,
            "source_reference": self.source_reference,
            "primitives": [item.to_dict() for item in self.primitives],
        }


@dataclass(frozen=True, slots=True)
class CollisionBodyRequirement:
    body_id: str
    parent_frame: str
    role: CollisionBodyRole
    binding_mode: CollisionBindingMode = CollisionBindingMode.RIGID_FRAME
    reason: str = "required collision coverage"

    def __post_init__(self) -> None:
        object.__setattr__(self, "body_id", _name(self.body_id, "body_id"))
        object.__setattr__(self, "parent_frame", _name(self.parent_frame, "parent_frame"))
        if not isinstance(self.role, CollisionBodyRole):
            raise TypeError("role must be CollisionBodyRole")
        if not isinstance(self.binding_mode, CollisionBindingMode):
            raise TypeError("binding_mode must be CollisionBindingMode")
        object.__setattr__(self, "reason", _name(self.reason, "requirement reason"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "body_id": self.body_id,
            "parent_frame": self.parent_frame,
            "role": self.role.value,
            "binding_mode": self.binding_mode.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CollisionBody:
    body_id: str
    parent_frame: str
    role: CollisionBodyRole
    evidence_state: CollisionEvidenceState
    primitives: tuple[CollisionPrimitive, ...] = ()
    binding_mode: CollisionBindingMode = CollisionBindingMode.RIGID_FRAME
    source_reference: str = "unavailable"

    def __post_init__(self) -> None:
        object.__setattr__(self, "body_id", _name(self.body_id, "body_id"))
        object.__setattr__(self, "parent_frame", _name(self.parent_frame, "parent_frame"))
        if not isinstance(self.role, CollisionBodyRole):
            raise TypeError("role must be CollisionBodyRole")
        if not isinstance(self.evidence_state, CollisionEvidenceState):
            raise TypeError("evidence_state must be CollisionEvidenceState")
        if not isinstance(self.binding_mode, CollisionBindingMode):
            raise TypeError("binding_mode must be CollisionBindingMode")
        object.__setattr__(
            self,
            "primitives",
            _validate_primitives(self.primitives, label=f"body {self.body_id!r}"),
        )
        object.__setattr__(
            self,
            "source_reference",
            _name(self.source_reference, "source_reference"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "body_id": self.body_id,
            "parent_frame": self.parent_frame,
            "role": self.role.value,
            "binding_mode": self.binding_mode.value,
            "evidence_state": self.evidence_state.value,
            "source_reference": self.source_reference,
            "primitives": [item.to_dict() for item in self.primitives],
        }


@dataclass(frozen=True, slots=True)
class CollisionPairExclusion:
    """One evidence-bearing, globally applied diagnostic pair exclusion.

    Tool contact or any other phase-specific allowance must not be encoded as
    this type.  Such allowances require a separate phase-local query contract.
    """

    first_body_id: str
    second_body_id: str
    scope: CollisionExclusionScope
    evidence_state: CollisionExclusionEvidenceState
    rationale: str
    source_reference: str

    def __post_init__(self) -> None:
        first = _name(self.first_body_id, "exclusion first_body_id")
        second = _name(self.second_body_id, "exclusion second_body_id")
        if first == second:
            raise CollisionContractError("an exclusion cannot name one body twice")
        first, second = sorted((first, second))
        object.__setattr__(self, "first_body_id", first)
        object.__setattr__(self, "second_body_id", second)
        if not isinstance(self.scope, CollisionExclusionScope):
            raise TypeError("scope must be CollisionExclusionScope")
        if not isinstance(self.evidence_state, CollisionExclusionEvidenceState):
            raise TypeError("evidence_state must be CollisionExclusionEvidenceState")
        expected = {
            CollisionExclusionScope.ENGINEERING_GLOBAL: (
                CollisionExclusionEvidenceState.ACCEPTED_ENGINEERING
            ),
            CollisionExclusionScope.URDF_ADJACENT_DIAGNOSTIC: (
                CollisionExclusionEvidenceState.PINNED_KINEMATIC_DIAGNOSTIC
            ),
            CollisionExclusionScope.SYNTHETIC_TEST_ONLY: (
                CollisionExclusionEvidenceState.SYNTHETIC_TEST_ONLY
            ),
        }[self.scope]
        if self.evidence_state is not expected:
            raise CollisionContractError(
                f"exclusion scope {self.scope.value} requires evidence {expected.value}"
            )
        object.__setattr__(self, "rationale", _name(self.rationale, "exclusion rationale"))
        object.__setattr__(
            self,
            "source_reference",
            _name(self.source_reference, "exclusion source_reference"),
        )

    @property
    def pair(self) -> tuple[str, str]:
        return self.first_body_id, self.second_body_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "body_pair": [self.first_body_id, self.second_body_id],
            "scope": self.scope.value,
            "evidence_state": self.evidence_state.value,
            "rationale": self.rationale,
            "source_reference": self.source_reference,
            "physically_accepted_exclusion": self.evidence_state.is_physically_accepted,
            "can_authorize_contact": False,
        }


@dataclass(frozen=True, slots=True)
class CollisionClearancePolicy:
    """Explicit pair-separation and per-body uncertainty inflation policy."""

    minimum_separation_mm: float
    geometry_uncertainty_mm_per_body: float
    pose_uncertainty_mm_per_body: float
    evidence_state: CollisionClearanceEvidenceState
    source_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "minimum_separation_mm",
            _nonnegative(self.minimum_separation_mm, "minimum_separation_mm"),
        )
        object.__setattr__(
            self,
            "geometry_uncertainty_mm_per_body",
            _nonnegative(
                self.geometry_uncertainty_mm_per_body,
                "geometry_uncertainty_mm_per_body",
            ),
        )
        object.__setattr__(
            self,
            "pose_uncertainty_mm_per_body",
            _nonnegative(
                self.pose_uncertainty_mm_per_body,
                "pose_uncertainty_mm_per_body",
            ),
        )
        if not isinstance(self.evidence_state, CollisionClearanceEvidenceState):
            raise TypeError("evidence_state must be CollisionClearanceEvidenceState")
        object.__setattr__(
            self,
            "source_reference",
            _name(self.source_reference, "clearance source_reference"),
        )
        if self.per_body_inflation_mm <= 0.0:
            raise CollisionContractError(
                "clearance policy must require positive separation or uncertainty inflation"
            )

    @property
    def per_body_inflation_mm(self) -> float:
        return (
            self.minimum_separation_mm / 2.0
            + self.geometry_uncertainty_mm_per_body
            + self.pose_uncertainty_mm_per_body
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_separation_mm": self.minimum_separation_mm,
            "geometry_uncertainty_mm_per_body": self.geometry_uncertainty_mm_per_body,
            "pose_uncertainty_mm_per_body": self.pose_uncertainty_mm_per_body,
            "per_body_inflation_mm": self.per_body_inflation_mm,
            "pair_inflation_mm": 2.0 * self.per_body_inflation_mm,
            "evidence_state": self.evidence_state.value,
            "source_reference": self.source_reference,
            "inflation_method": (
                "conservative primitive expansion; OBB expansion is axis-aligned in its local frame"
            ),
            "physically_accepted_policy": self.evidence_state.is_physically_accepted,
        }


@dataclass(frozen=True, slots=True)
class CollisionGeometryContract:
    contract_id: str
    root_frame: str
    requirements: tuple[CollisionBodyRequirement, ...]
    bodies: tuple[CollisionBody, ...]
    pair_exclusions: tuple[CollisionPairExclusion, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_id", _name(self.contract_id, "contract_id"))
        object.__setattr__(self, "root_frame", _name(self.root_frame, "root_frame"))
        if self.schema_version != 1:
            raise CollisionContractError("only collision geometry schema_version 1 is supported")
        requirements = _bounded_tuple(
            self.requirements, HARD_MAX_REQUIREMENTS, "collision requirements"
        )
        bodies = _bounded_tuple(self.bodies, HARD_MAX_BODIES, "collision bodies")
        if not requirements:
            raise CollisionContractError(
                "collision contract must declare at least one required body"
            )
        if any(not isinstance(item, CollisionBodyRequirement) for item in requirements):
            raise TypeError("requirements must contain CollisionBodyRequirement values")
        if any(not isinstance(item, CollisionBody) for item in bodies):
            raise TypeError("bodies must contain CollisionBody values")
        requirement_ids = [item.body_id for item in requirements]
        body_ids = [item.body_id for item in bodies]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise CollisionContractError("required collision body ids must be unique")
        if len(body_ids) != len(set(body_ids)):
            raise CollisionContractError("collision body ids must be unique")
        exclusions = _bounded_tuple(
            self.pair_exclusions,
            HARD_MAX_EXCLUDED_PAIRS,
            "excluded body pairs",
        )
        if any(not isinstance(item, CollisionPairExclusion) for item in exclusions):
            raise TypeError("pair_exclusions must contain CollisionPairExclusion values")
        exclusion_pairs = [item.pair for item in exclusions]
        if len(exclusion_pairs) != len(set(exclusion_pairs)):
            raise CollisionContractError("excluded body pairs must be unique")
        unknown_exclusion_ids = (
            set().union(*map(set, exclusion_pairs)) - set(body_ids)
            if exclusion_pairs
            else set()
        )
        if unknown_exclusion_ids:
            raise CollisionContractError(
                f"excluded pairs reference unknown bodies: {sorted(unknown_exclusion_ids)}"
            )
        object.__setattr__(self, "requirements", requirements)
        object.__setattr__(self, "bodies", bodies)
        object.__setattr__(
            self,
            "pair_exclusions",
            tuple(sorted(exclusions, key=lambda item: item.pair)),
        )

    @property
    def bodies_by_id(self) -> Mapping[str, CollisionBody]:
        return MappingProxyType({item.body_id: item for item in self.bodies})

    @property
    def content_hash(self) -> str:
        return _stable_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COLLISION_CONTRACT_SCHEMA,
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "root_frame": self.root_frame,
            "requirements": [item.to_dict() for item in self.requirements],
            "bodies": [item.to_dict() for item in self.bodies],
            "pair_exclusions": [item.to_dict() for item in self.pair_exclusions],
            "exclusion_policy": {
                "global_only": True,
                "phase_specific_tool_or_contact_allowances_are_global_exclusions": False,
                "rule": (
                    "Any phase-specific allowed contact requires a separate phase-local "
                    "query and is never added to this global pair-exclusion list."
                ),
            },
            "authority": {
                "simulation_only": True,
                "hardware_commands_generated": 0,
                "can_release_physical_gates": False,
                "contact_enabled": False,
            },
        }


@dataclass(frozen=True, slots=True)
class CollisionBlocker:
    code: CollisionBlockerCode
    body_id: str
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, CollisionBlockerCode):
            raise TypeError("code must be CollisionBlockerCode")
        object.__setattr__(self, "body_id", _name(self.body_id, "blocker body_id"))
        object.__setattr__(self, "detail", _name(self.detail, "blocker detail"))

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "body_id": self.body_id, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class CollisionGeometryAudit:
    contract_id: str
    required_body_count: int
    bound_body_count: int
    diagnostic_ready: bool
    physical_geometry_complete: bool
    diagnostic_blockers: tuple[CollisionBlocker, ...]
    diagnostic_only_body_ids: tuple[str, ...]
    configuration_sampled_body_ids: tuple[str, ...]
    diagnostic_only_exclusion_pairs: tuple[tuple[str, str], ...]

    @property
    def can_release_physical_gates(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COLLISION_AUDIT_SCHEMA,
            "contract_id": self.contract_id,
            "required_body_count": self.required_body_count,
            "bound_body_count": self.bound_body_count,
            "diagnostic_ready": self.diagnostic_ready,
            "physical_geometry_complete": self.physical_geometry_complete,
            "diagnostic_blockers": [item.to_dict() for item in self.diagnostic_blockers],
            "diagnostic_only_body_ids": list(self.diagnostic_only_body_ids),
            "configuration_sampled_body_ids": list(self.configuration_sampled_body_ids),
            "diagnostic_only_exclusion_pairs": [
                list(item) for item in self.diagnostic_only_exclusion_pairs
            ],
            "authority": {
                "simulation_only": True,
                "hardware_commands_generated": 0,
                "can_release_physical_gates": False,
                "contact_enabled": False,
            },
        }


def audit_collision_geometry(contract: CollisionGeometryContract) -> CollisionGeometryAudit:
    """Audit complete required-body coverage without running any geometry query."""

    if not isinstance(contract, CollisionGeometryContract):
        raise TypeError("contract must be CollisionGeometryContract")
    bodies = contract.bodies_by_id
    blockers: list[CollisionBlocker] = []
    diagnostic_only: list[str] = []
    configuration_sampled: list[str] = []
    physically_complete = True
    for requirement in contract.requirements:
        if (
            requirement.binding_mode is CollisionBindingMode.STATIC_ROOT
            and requirement.parent_frame != contract.root_frame
        ):
            blockers.append(
                CollisionBlocker(
                    CollisionBlockerCode.STATIC_ROOT_PARENT_NOT_CONTRACT_ROOT,
                    requirement.body_id,
                    f"required STATIC_ROOT parent {requirement.parent_frame} is not {contract.root_frame}",
                )
            )
            physically_complete = False
        body = bodies.get(requirement.body_id)
        if body is None:
            blockers.append(
                CollisionBlocker(
                    CollisionBlockerCode.REQUIRED_BODY_BINDING_MISSING,
                    requirement.body_id,
                    "required body has no collision binding",
                )
            )
            physically_complete = False
            continue
        if body.parent_frame != requirement.parent_frame:
            blockers.append(
                CollisionBlocker(
                    CollisionBlockerCode.REQUIRED_BODY_PARENT_MISMATCH,
                    requirement.body_id,
                    f"expected parent {requirement.parent_frame}, got {body.parent_frame}",
                )
            )
        if body.role is not requirement.role:
            blockers.append(
                CollisionBlocker(
                    CollisionBlockerCode.REQUIRED_BODY_ROLE_MISMATCH,
                    requirement.body_id,
                    f"expected role {requirement.role.value}, got {body.role.value}",
                )
            )
        if body.binding_mode is not requirement.binding_mode:
            blockers.append(
                CollisionBlocker(
                    CollisionBlockerCode.REQUIRED_BODY_BINDING_MODE_MISMATCH,
                    requirement.body_id,
                    f"expected mode {requirement.binding_mode.value}, got {body.binding_mode.value}",
                )
            )
        if (
            body.binding_mode is CollisionBindingMode.STATIC_ROOT
            and body.parent_frame != contract.root_frame
            and not (
                requirement.binding_mode is CollisionBindingMode.STATIC_ROOT
                and requirement.parent_frame == body.parent_frame
            )
        ):
            blockers.append(
                CollisionBlocker(
                    CollisionBlockerCode.STATIC_ROOT_PARENT_NOT_CONTRACT_ROOT,
                    requirement.body_id,
                    f"bound STATIC_ROOT parent {body.parent_frame} is not {contract.root_frame}",
                )
            )
        if body.evidence_state is CollisionEvidenceState.MISSING:
            blockers.append(
                CollisionBlocker(
                    CollisionBlockerCode.REQUIRED_BODY_GEOMETRY_MISSING,
                    requirement.body_id,
                    "complete body geometry is absent",
                )
            )
        elif body.evidence_state is CollisionEvidenceState.UNKNOWN:
            blockers.append(
                CollisionBlocker(
                    CollisionBlockerCode.REQUIRED_BODY_GEOMETRY_UNKNOWN,
                    requirement.body_id,
                    "installed body geometry or transform remains unknown",
                )
            )
        elif (
            requirement.binding_mode is not CollisionBindingMode.CONFIGURATION_SAMPLED
            and not body.primitives
        ):
            blockers.append(
                CollisionBlocker(
                    CollisionBlockerCode.REQUIRED_BODY_PRIMITIVES_EMPTY,
                    requirement.body_id,
                    "usable evidence state has no collision primitives",
                )
            )
        if not body.evidence_state.is_physically_accepted_geometry:
            physically_complete = False
            if body.evidence_state.supports_diagnostic:
                diagnostic_only.append(body.body_id)
        if requirement.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED:
            # A contract cannot prove that every future configuration supplies
            # complete accepted deformable geometry.  That evidence is bound at
            # each pose, so contract-level physical completeness remains false.
            physically_complete = False
            configuration_sampled.append(body.body_id)
    diagnostic_only_exclusions = tuple(
        item.pair
        for item in contract.pair_exclusions
        if not item.evidence_state.is_physically_accepted
    )
    if diagnostic_only_exclusions:
        physically_complete = False
    blockers.sort(key=lambda item: (item.body_id, item.code.value, item.detail))
    return CollisionGeometryAudit(
        contract_id=contract.contract_id,
        required_body_count=len(contract.requirements),
        bound_body_count=sum(item.body_id in bodies for item in contract.requirements),
        diagnostic_ready=not blockers,
        physical_geometry_complete=physically_complete and not blockers,
        diagnostic_blockers=tuple(blockers),
        diagnostic_only_body_ids=tuple(sorted(diagnostic_only)),
        configuration_sampled_body_ids=tuple(sorted(configuration_sampled)),
        diagnostic_only_exclusion_pairs=tuple(sorted(diagnostic_only_exclusions)),
    )


@dataclass(frozen=True, slots=True)
class CollisionPose:
    """One fully supplied configuration in the contract's collision root."""

    pose_id: str
    root_frame: str
    root_t_parent: Mapping[str, RigidTransform]
    configuration_primitives: Mapping[str, SampledCollisionGeometry] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "pose_id", _name(self.pose_id, "pose_id"))
        object.__setattr__(self, "root_frame", _name(self.root_frame, "root_frame"))
        transform_items = _bounded_mapping_items(
            self.root_t_parent,
            HARD_MAX_POSE_TRANSFORMS,
            "pose transforms",
        )
        transforms: dict[str, RigidTransform] = {}
        for raw_frame, transform in transform_items:
            frame = _name(raw_frame, "pose transform key")
            if raw_frame != frame:
                raise CollisionContractError("pose transform keys may not contain padding")
            if not isinstance(transform, RigidTransform):
                raise TypeError("pose transforms must be RigidTransform values")
            if frame in transforms:
                raise CollisionContractError(f"pose transforms duplicate normalized key {frame!r}")
            transforms[frame] = transform
        configuration_items = _bounded_mapping_items(
            self.configuration_primitives,
            HARD_MAX_BODIES,
            "configuration geometry",
        )
        configurations: dict[str, SampledCollisionGeometry] = {}
        for raw_body_id, sampled_geometry in configuration_items:
            body_id = _name(raw_body_id, "configuration body id")
            if raw_body_id != body_id:
                raise CollisionContractError(
                    "configuration body ids may not contain padding"
                )
            if not isinstance(sampled_geometry, SampledCollisionGeometry):
                raise TypeError(
                    "configuration geometry values must be SampledCollisionGeometry"
                )
            if body_id in configurations:
                raise CollisionContractError(
                    f"configuration geometry duplicates normalized key {body_id!r}"
                )
            configurations[body_id] = sampled_geometry
        object.__setattr__(self, "root_t_parent", MappingProxyType(transforms))
        object.__setattr__(
            self, "configuration_primitives", MappingProxyType(configurations)
        )

    @property
    def content_hash(self) -> str:
        return _stable_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "pose_id": self.pose_id,
            "root_frame": self.root_frame,
            "root_t_parent": {
                frame: _transform_to_dict(transform)
                for frame, transform in sorted(self.root_t_parent.items())
            },
            "configuration_geometry": {
                body_id: geometry.to_dict()
                for body_id, geometry in sorted(self.configuration_primitives.items())
            },
        }


@dataclass(frozen=True, slots=True)
class CollisionEvaluationPolicy:
    maximum_bodies: int = 64
    maximum_body_pairs_per_pose: int = 2_048
    maximum_primitive_pair_tests_per_pose: int = 32_768
    maximum_sweep_samples: int = 128
    maximum_sweep_body_pair_evaluations: int = 65_536
    maximum_sweep_primitive_pair_evaluations: int = 262_144
    maximum_surface_step_mm: float = 5.0
    maximum_rotation_step_rad: float = math.radians(5.0)
    clearance_policy: CollisionClearancePolicy | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "maximum_bodies",
            _positive_int(self.maximum_bodies, "maximum_bodies", HARD_MAX_BODIES),
        )
        object.__setattr__(
            self,
            "maximum_body_pairs_per_pose",
            _positive_int(
                self.maximum_body_pairs_per_pose,
                "maximum_body_pairs_per_pose",
                HARD_MAX_BODY_PAIRS_PER_POSE,
            ),
        )
        object.__setattr__(
            self,
            "maximum_primitive_pair_tests_per_pose",
            _positive_int(
                self.maximum_primitive_pair_tests_per_pose,
                "maximum_primitive_pair_tests_per_pose",
                HARD_MAX_PRIMITIVE_PAIR_TESTS_PER_POSE,
            ),
        )
        object.__setattr__(
            self,
            "maximum_sweep_samples",
            _positive_int(
                self.maximum_sweep_samples,
                "maximum_sweep_samples",
                HARD_MAX_SWEEP_SAMPLES,
            ),
        )
        object.__setattr__(
            self,
            "maximum_sweep_body_pair_evaluations",
            _positive_int(
                self.maximum_sweep_body_pair_evaluations,
                "maximum_sweep_body_pair_evaluations",
                HARD_MAX_SWEEP_BODY_PAIR_EVALUATIONS,
            ),
        )
        object.__setattr__(
            self,
            "maximum_sweep_primitive_pair_evaluations",
            _positive_int(
                self.maximum_sweep_primitive_pair_evaluations,
                "maximum_sweep_primitive_pair_evaluations",
                HARD_MAX_SWEEP_PRIMITIVE_PAIR_EVALUATIONS,
            ),
        )
        object.__setattr__(
            self,
            "maximum_surface_step_mm",
            _positive(self.maximum_surface_step_mm, "maximum_surface_step_mm"),
        )
        object.__setattr__(
            self,
            "maximum_rotation_step_rad",
            _positive(self.maximum_rotation_step_rad, "maximum_rotation_step_rad"),
        )
        if self.clearance_policy is not None and not isinstance(
            self.clearance_policy, CollisionClearancePolicy
        ):
            raise TypeError("clearance_policy must be CollisionClearancePolicy or None")

    @property
    def content_hash(self) -> str:
        return _stable_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "maximum_bodies": self.maximum_bodies,
            "maximum_body_pairs_per_pose": self.maximum_body_pairs_per_pose,
            "maximum_primitive_pair_tests_per_pose": (
                self.maximum_primitive_pair_tests_per_pose
            ),
            "maximum_sweep_samples": self.maximum_sweep_samples,
            "maximum_sweep_body_pair_evaluations": (
                self.maximum_sweep_body_pair_evaluations
            ),
            "maximum_sweep_primitive_pair_evaluations": (
                self.maximum_sweep_primitive_pair_evaluations
            ),
            "maximum_surface_step_mm": self.maximum_surface_step_mm,
            "maximum_rotation_step_rad": self.maximum_rotation_step_rad,
            "clearance_policy": (
                None if self.clearance_policy is None else self.clearance_policy.to_dict()
            ),
        }


@dataclass(frozen=True, slots=True)
class BoundsMm:
    minimum_mm: Vec3
    maximum_mm: Vec3

    def __post_init__(self) -> None:
        if not isinstance(self.minimum_mm, Vec3) or not isinstance(self.maximum_mm, Vec3):
            raise TypeError("bounds endpoints must be Vec3")
        if any(
            low > high
            for low, high in zip(
                _coordinates(self.minimum_mm), _coordinates(self.maximum_mm)
            )
        ):
            raise CollisionContractError("bounds minimum cannot exceed maximum")

    def intersects(self, other: "BoundsMm") -> bool:
        if not isinstance(other, BoundsMm):
            raise TypeError("other must be BoundsMm")
        return all(
            left_low <= right_high and right_low <= left_high
            for left_low, left_high, right_low, right_high in zip(
                _coordinates(self.minimum_mm),
                _coordinates(self.maximum_mm),
                _coordinates(other.minimum_mm),
                _coordinates(other.maximum_mm),
            )
        )

    @classmethod
    def union(cls, values: Sequence["BoundsMm"]) -> "BoundsMm":
        if not values:
            raise CollisionContractError("cannot union an empty bounds sequence")
        return cls(
            Vec3(*(min(_coordinates(item.minimum_mm)[axis] for item in values) for axis in range(3))),
            Vec3(*(max(_coordinates(item.maximum_mm)[axis] for item in values) for axis in range(3))),
        )


@dataclass(frozen=True, slots=True)
class _WorldSphere:
    center_mm: Vec3
    radius_mm: float


@dataclass(frozen=True, slots=True)
class _WorldCapsule:
    start_mm: Vec3
    end_mm: Vec3
    radius_mm: float


@dataclass(frozen=True, slots=True)
class _WorldObb:
    center_mm: Vec3
    half_extents_mm: Vec3
    rotation: Rotation3


_WorldPrimitive: TypeAlias = _WorldSphere | _WorldCapsule | _WorldObb


def _coordinates(value: Vec3) -> tuple[float, float, float]:
    return value.x, value.y, value.z


def _world_primitive(
    primitive: CollisionPrimitive,
    root_t_parent: RigidTransform,
) -> _WorldPrimitive:
    if isinstance(primitive, SphereMm):
        return _WorldSphere(
            root_t_parent.transform_position_mm(primitive.center_mm), primitive.radius_mm
        )
    if isinstance(primitive, CapsuleMm):
        return _WorldCapsule(
            root_t_parent.transform_position_mm(primitive.start_mm),
            root_t_parent.transform_position_mm(primitive.end_mm),
            primitive.radius_mm,
        )
    return _WorldObb(
        root_t_parent.transform_position_mm(primitive.center_mm),
        primitive.half_extents_mm,
        root_t_parent.rotation.compose(primitive.rotation),
    )


def _inflate_world_primitive(
    primitive: _WorldPrimitive,
    inflation_mm: float,
) -> _WorldPrimitive:
    """Conservatively expand one primitive by an explicit per-body margin."""

    inflation = _positive(inflation_mm, "primitive inflation_mm")
    if isinstance(primitive, _WorldSphere):
        return _WorldSphere(primitive.center_mm, primitive.radius_mm + inflation)
    if isinstance(primitive, _WorldCapsule):
        return _WorldCapsule(
            primitive.start_mm,
            primitive.end_mm,
            primitive.radius_mm + inflation,
        )
    return _WorldObb(
        primitive.center_mm,
        primitive.half_extents_mm + Vec3(inflation, inflation, inflation),
        primitive.rotation,
    )


def _primitive_bounds(primitive: _WorldPrimitive) -> BoundsMm:
    if isinstance(primitive, _WorldSphere):
        radius = primitive.radius_mm
        return BoundsMm(
            primitive.center_mm - Vec3(radius, radius, radius),
            primitive.center_mm + Vec3(radius, radius, radius),
        )
    if isinstance(primitive, _WorldCapsule):
        radius = primitive.radius_mm
        starts = _coordinates(primitive.start_mm)
        ends = _coordinates(primitive.end_mm)
        return BoundsMm(
            Vec3(*(min(starts[i], ends[i]) - radius for i in range(3))),
            Vec3(*(max(starts[i], ends[i]) + radius for i in range(3))),
        )
    rotation = primitive.rotation.matrix
    half = _coordinates(primitive.half_extents_mm)
    projected = tuple(
        sum(abs(rotation[row * 3 + column]) * half[column] for column in range(3))
        for row in range(3)
    )
    extent = Vec3(*projected)
    return BoundsMm(primitive.center_mm - extent, primitive.center_mm + extent)


def _squared_distance(left: Vec3, right: Vec3) -> float:
    difference = left - right
    return difference.dot(difference)


def _point_segment_distance_squared(point: Vec3, start: Vec3, end: Vec3) -> float:
    segment = end - start
    length_squared = segment.dot(segment)
    if length_squared == 0.0:
        return _squared_distance(point, start)
    parameter = max(0.0, min(1.0, (point - start).dot(segment) / length_squared))
    return _squared_distance(point, start + segment.scaled(parameter))


def _segment_segment_distance_squared(
    first_start: Vec3,
    first_end: Vec3,
    second_start: Vec3,
    second_end: Vec3,
) -> float:
    """Scale-relative squared distance between two closed 3-D segments.

    Boundary candidates cover every clamped optimum.  The unconstrained
    interior candidate is used only when the Gram determinant is significant
    relative to ``|u|^2 |v|^2``.  This avoids treating millimetre-scale or
    smaller valid segments as points merely because of an absolute epsilon.
    """

    first = first_end - first_start
    second = second_end - second_start
    first_length = first.dot(first)
    second_length = second.dot(second)
    if first_length == 0.0 and second_length == 0.0:
        return _squared_distance(first_start, second_start)
    candidates = (
        _point_segment_distance_squared(first_start, second_start, second_end),
        _point_segment_distance_squared(first_end, second_start, second_end),
        _point_segment_distance_squared(second_start, first_start, first_end),
        _point_segment_distance_squared(second_end, first_start, first_end),
    )
    best = min(candidates)
    if first_length == 0.0 or second_length == 0.0:
        return best

    offset = first_start - second_start
    cross = first.dot(second)
    first_offset = first.dot(offset)
    second_offset = second.dot(offset)
    scale = first_length * second_length
    denominator = scale - cross * cross
    if denominator > _RELATIVE_PARALLEL_TOLERANCE * scale:
        first_parameter = (
            cross * second_offset - second_length * first_offset
        ) / denominator
        second_parameter = (
            first_length * second_offset - cross * first_offset
        ) / denominator
        if 0.0 <= first_parameter <= 1.0 and 0.0 <= second_parameter <= 1.0:
            closest_first = first_start + first.scaled(first_parameter)
            closest_second = second_start + second.scaled(second_parameter)
            best = min(best, _squared_distance(closest_first, closest_second))
    return best


def _to_obb_local(point: Vec3, box: _WorldObb) -> Vec3:
    return box.rotation.inverse().apply(point - box.center_mm)


def _point_aabb_distance_squared(point: Vec3, half: Vec3) -> float:
    return sum(
        max(abs(coordinate) - extent, 0.0) ** 2
        for coordinate, extent in zip(_coordinates(point), _coordinates(half))
    )


def _segment_aabb_distance_squared(start: Vec3, end: Vec3, half: Vec3) -> float:
    """Exact segment/AABB distance via piecewise-quadratic intervals."""

    origin = _coordinates(start)
    direction = _coordinates(end - start)
    extents = _coordinates(half)
    breakpoints = {0.0, 1.0}
    for axis in range(3):
        if direction[axis] == 0.0:
            continue
        for plane in (-extents[axis], extents[axis]):
            parameter = (plane - origin[axis]) / direction[axis]
            if 0.0 < parameter < 1.0:
                breakpoints.add(parameter)
    ordered = sorted(breakpoints)

    def distance_at(parameter: float) -> float:
        return _point_aabb_distance_squared(
            Vec3(*(origin[i] + direction[i] * parameter for i in range(3))), half
        )

    best = min(distance_at(item) for item in ordered)
    for low, high in zip(ordered, ordered[1:]):
        middle = (low + high) / 2.0
        quadratic = 0.0
        linear = 0.0
        for axis in range(3):
            coordinate = origin[axis] + direction[axis] * middle
            if coordinate < -extents[axis]:
                offset = origin[axis] + extents[axis]
            elif coordinate > extents[axis]:
                offset = origin[axis] - extents[axis]
            else:
                continue
            quadratic += direction[axis] * direction[axis]
            linear += direction[axis] * offset
        if quadratic > 0.0:
            stationary = max(low, min(high, -linear / quadratic))
            best = min(best, distance_at(stationary))
    return best


def _obb_axes(box: _WorldObb) -> tuple[Vec3, Vec3, Vec3]:
    matrix = box.rotation.matrix
    return (
        Vec3(matrix[0], matrix[3], matrix[6]),
        Vec3(matrix[1], matrix[4], matrix[7]),
        Vec3(matrix[2], matrix[5], matrix[8]),
    )


def _obb_intersects_obb(left: _WorldObb, right: _WorldObb) -> bool:
    """Exact OBB intersection using the 15 separating axes."""

    left_axes = _obb_axes(left)
    right_axes = _obb_axes(right)
    left_half = _coordinates(left.half_extents_mm)
    right_half = _coordinates(right.half_extents_mm)
    rotation = tuple(
        tuple(left_axes[row].dot(right_axes[column]) for column in range(3))
        for row in range(3)
    )
    absolute = tuple(
        tuple(abs(rotation[row][column]) + 1e-12 for column in range(3))
        for row in range(3)
    )
    offset_world = right.center_mm - left.center_mm
    offset = tuple(offset_world.dot(axis) for axis in left_axes)
    for axis in range(3):
        left_radius = left_half[axis]
        right_radius = sum(right_half[j] * absolute[axis][j] for j in range(3))
        if abs(offset[axis]) > left_radius + right_radius:
            return False
    for axis in range(3):
        left_radius = sum(left_half[i] * absolute[i][axis] for i in range(3))
        right_radius = right_half[axis]
        projection = abs(sum(offset[i] * rotation[i][axis] for i in range(3)))
        if projection > left_radius + right_radius:
            return False
    for left_axis in range(3):
        left_next = (left_axis + 1) % 3
        left_last = (left_axis + 2) % 3
        for right_axis in range(3):
            right_next = (right_axis + 1) % 3
            right_last = (right_axis + 2) % 3
            left_radius = (
                left_half[left_next] * absolute[left_last][right_axis]
                + left_half[left_last] * absolute[left_next][right_axis]
            )
            right_radius = (
                right_half[right_next] * absolute[left_axis][right_last]
                + right_half[right_last] * absolute[left_axis][right_next]
            )
            projection = abs(
                offset[left_last] * rotation[left_next][right_axis]
                - offset[left_next] * rotation[left_last][right_axis]
            )
            if projection > left_radius + right_radius:
                return False
    return True


def _obb_clearance_lower_bound_mm(left: _WorldObb, right: _WorldObb) -> float:
    """Return a conservative Euclidean separation lower bound for two OBBs."""

    left_axes = _obb_axes(left)
    right_axes = _obb_axes(right)
    left_half = _coordinates(left.half_extents_mm)
    right_half = _coordinates(right.half_extents_mm)
    rotation = tuple(
        tuple(left_axes[row].dot(right_axes[column]) for column in range(3))
        for row in range(3)
    )
    absolute = tuple(
        tuple(abs(rotation[row][column]) for column in range(3))
        for row in range(3)
    )
    offset_world = right.center_mm - left.center_mm
    offset = tuple(offset_world.dot(axis) for axis in left_axes)
    gaps: list[float] = []
    for axis in range(3):
        left_radius = left_half[axis]
        right_radius = sum(right_half[j] * absolute[axis][j] for j in range(3))
        gaps.append(abs(offset[axis]) - left_radius - right_radius)
    for axis in range(3):
        left_radius = sum(left_half[i] * absolute[i][axis] for i in range(3))
        right_radius = right_half[axis]
        projection = abs(sum(offset[i] * rotation[i][axis] for i in range(3)))
        gaps.append(projection - left_radius - right_radius)
    for left_axis in range(3):
        left_next = (left_axis + 1) % 3
        left_last = (left_axis + 2) % 3
        for right_axis in range(3):
            axis_norm = math.sqrt(
                max(0.0, 1.0 - rotation[left_axis][right_axis] ** 2)
            )
            if axis_norm <= _RELATIVE_PARALLEL_TOLERANCE:
                continue
            right_next = (right_axis + 1) % 3
            right_last = (right_axis + 2) % 3
            left_radius = (
                left_half[left_next] * absolute[left_last][right_axis]
                + left_half[left_last] * absolute[left_next][right_axis]
            )
            right_radius = (
                right_half[right_next] * absolute[left_axis][right_last]
                + right_half[right_last] * absolute[left_axis][right_next]
            )
            projection = abs(
                offset[left_last] * rotation[left_next][right_axis]
                - offset[left_next] * rotation[left_last][right_axis]
            )
            gaps.append((projection - left_radius - right_radius) / axis_norm)
    return max(0.0, max(gaps, default=0.0))


def _primitive_clearance_lower_bound_mm(
    left: _WorldPrimitive,
    right: _WorldPrimitive,
) -> float:
    """Residual clearance after primitive inflation, in millimetres."""

    if isinstance(left, _WorldSphere) and isinstance(right, _WorldSphere):
        center_distance = math.sqrt(_squared_distance(left.center_mm, right.center_mm))
        return max(0.0, center_distance - left.radius_mm - right.radius_mm)
    if isinstance(left, _WorldSphere) and isinstance(right, _WorldCapsule):
        axis_distance = math.sqrt(
            _point_segment_distance_squared(
                left.center_mm, right.start_mm, right.end_mm
            )
        )
        return max(0.0, axis_distance - left.radius_mm - right.radius_mm)
    if isinstance(left, _WorldCapsule) and isinstance(right, _WorldSphere):
        return _primitive_clearance_lower_bound_mm(right, left)
    if isinstance(left, _WorldCapsule) and isinstance(right, _WorldCapsule):
        axis_distance = math.sqrt(
            _segment_segment_distance_squared(
                left.start_mm, left.end_mm, right.start_mm, right.end_mm
            )
        )
        return max(0.0, axis_distance - left.radius_mm - right.radius_mm)
    if isinstance(left, _WorldSphere) and isinstance(right, _WorldObb):
        local = _to_obb_local(left.center_mm, right)
        return max(
            0.0,
            math.sqrt(_point_aabb_distance_squared(local, right.half_extents_mm))
            - left.radius_mm,
        )
    if isinstance(left, _WorldObb) and isinstance(right, _WorldSphere):
        return _primitive_clearance_lower_bound_mm(right, left)
    if isinstance(left, _WorldCapsule) and isinstance(right, _WorldObb):
        local_start = _to_obb_local(left.start_mm, right)
        local_end = _to_obb_local(left.end_mm, right)
        return max(
            0.0,
            math.sqrt(
                _segment_aabb_distance_squared(
                    local_start, local_end, right.half_extents_mm
                )
            )
            - left.radius_mm,
        )
    if isinstance(left, _WorldObb) and isinstance(right, _WorldCapsule):
        return _primitive_clearance_lower_bound_mm(right, left)
    assert isinstance(left, _WorldObb) and isinstance(right, _WorldObb)
    return _obb_clearance_lower_bound_mm(left, right)


def _primitive_intersects(left: _WorldPrimitive, right: _WorldPrimitive) -> bool:
    if isinstance(left, _WorldSphere) and isinstance(right, _WorldSphere):
        return _squared_distance(left.center_mm, right.center_mm) <= (
            left.radius_mm + right.radius_mm
        ) ** 2
    if isinstance(left, _WorldSphere) and isinstance(right, _WorldCapsule):
        return _point_segment_distance_squared(
            left.center_mm, right.start_mm, right.end_mm
        ) <= (left.radius_mm + right.radius_mm) ** 2
    if isinstance(left, _WorldCapsule) and isinstance(right, _WorldSphere):
        return _primitive_intersects(right, left)
    if isinstance(left, _WorldCapsule) and isinstance(right, _WorldCapsule):
        return _segment_segment_distance_squared(
            left.start_mm, left.end_mm, right.start_mm, right.end_mm
        ) <= (left.radius_mm + right.radius_mm) ** 2
    if isinstance(left, _WorldSphere) and isinstance(right, _WorldObb):
        local = _to_obb_local(left.center_mm, right)
        return _point_aabb_distance_squared(local, right.half_extents_mm) <= left.radius_mm**2
    if isinstance(left, _WorldObb) and isinstance(right, _WorldSphere):
        return _primitive_intersects(right, left)
    if isinstance(left, _WorldCapsule) and isinstance(right, _WorldObb):
        local_start = _to_obb_local(left.start_mm, right)
        local_end = _to_obb_local(left.end_mm, right)
        return _segment_aabb_distance_squared(
            local_start, local_end, right.half_extents_mm
        ) <= left.radius_mm**2
    if isinstance(left, _WorldObb) and isinstance(right, _WorldCapsule):
        return _primitive_intersects(right, left)
    assert isinstance(left, _WorldObb) and isinstance(right, _WorldObb)
    return _obb_intersects_obb(left, right)


@dataclass(frozen=True, slots=True)
class CollisionPair:
    first_body_id: str
    second_body_id: str
    first_primitive_index: int
    second_primitive_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "first_body_id": self.first_body_id,
            "second_body_id": self.second_body_id,
            "first_primitive_index": self.first_primitive_index,
            "second_primitive_index": self.second_primitive_index,
        }


@dataclass(frozen=True, slots=True)
class CollisionClearanceLowerBoundEvaluation:
    """Conservative residual clearance across all evaluated body pairs."""

    status: CollisionClearanceLowerBoundStatus
    minimum_clearance_lower_bound_mm: float | None
    limiting_body_pair: tuple[str, str] | None
    checked_body_pair_count: int
    checked_primitive_pair_count: int
    collision_pose_report_sha256: str

    @property
    def report_hash(self) -> str:
        return _stable_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COLLISION_CLEARANCE_LOWER_BOUND_SCHEMA,
            "status": self.status.value,
            "minimum_clearance_lower_bound_mm": self.minimum_clearance_lower_bound_mm,
            "limiting_body_pair": (
                list(self.limiting_body_pair)
                if self.limiting_body_pair is not None
                else None
            ),
            "checked_body_pair_count": self.checked_body_pair_count,
            "checked_primitive_pair_count": self.checked_primitive_pair_count,
            "collision_pose_report_sha256": self.collision_pose_report_sha256,
            "method": (
                "minimum inflated-primitive separation; exact for sphere/capsule/OBB "
                "mixed pairs and conservative normalized separating-axis lower bound "
                "for OBB/OBB pairs"
            ),
            "semantics": (
                "residual millimetres after minimum-separation, geometry-uncertainty, "
                "and pose-uncertainty inflation"
            ),
            "physical_authority": False,
        }


@dataclass(frozen=True, slots=True)
class CollisionPoseInputBindings:
    contract: CollisionGeometryContract
    pose: CollisionPose
    policy: CollisionEvaluationPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.contract, CollisionGeometryContract):
            raise TypeError("contract must be CollisionGeometryContract")
        if not isinstance(self.pose, CollisionPose):
            raise TypeError("pose must be CollisionPose")
        if not isinstance(self.policy, CollisionEvaluationPolicy):
            raise TypeError("policy must be CollisionEvaluationPolicy")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": {
                "sha256": self.contract.content_hash,
                "content": self.contract.to_dict(),
            },
            "pose": {
                "sha256": self.pose.content_hash,
                "content": self.pose.to_dict(),
            },
            "policy": {
                "sha256": self.policy.content_hash,
                "content": self.policy.to_dict(),
            },
        }


@dataclass(frozen=True, slots=True)
class CollisionSweepInputBindings:
    contract: CollisionGeometryContract
    start_pose: CollisionPose
    end_pose: CollisionPose
    policy: CollisionEvaluationPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.contract, CollisionGeometryContract):
            raise TypeError("contract must be CollisionGeometryContract")
        if not isinstance(self.start_pose, CollisionPose) or not isinstance(
            self.end_pose, CollisionPose
        ):
            raise TypeError("sweep poses must be CollisionPose values")
        if not isinstance(self.policy, CollisionEvaluationPolicy):
            raise TypeError("policy must be CollisionEvaluationPolicy")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": {
                "sha256": self.contract.content_hash,
                "content": self.contract.to_dict(),
            },
            "start_pose": {
                "sha256": self.start_pose.content_hash,
                "content": self.start_pose.to_dict(),
            },
            "end_pose": {
                "sha256": self.end_pose.content_hash,
                "content": self.end_pose.to_dict(),
            },
            "policy": {
                "sha256": self.policy.content_hash,
                "content": self.policy.to_dict(),
            },
        }


@dataclass(frozen=True, slots=True)
class CollisionPoseEvaluation:
    contract_id: str
    pose_id: str
    status: CollisionEvaluationStatus
    geometry_audit: CollisionGeometryAudit
    pose_blockers: tuple[CollisionBlocker, ...]
    checked_body_pair_count: int
    broad_phase_candidate_count: int
    narrow_phase_primitive_pair_test_count: int
    collisions: tuple[CollisionPair, ...]
    input_bindings: CollisionPoseInputBindings

    def __post_init__(self) -> None:
        if not isinstance(self.input_bindings, CollisionPoseInputBindings):
            raise TypeError("input_bindings must be CollisionPoseInputBindings")
        if self.input_bindings.contract.contract_id != self.contract_id:
            raise CollisionContractError("pose report contract id differs from bound content")
        if self.input_bindings.pose.pose_id != self.pose_id:
            raise CollisionContractError("pose report pose id differs from bound content")

    @property
    def evaluation_complete(self) -> bool:
        return self.status in {
            CollisionEvaluationStatus.COLLISION_DETECTED,
            CollisionEvaluationStatus.CLEAR_AT_SAMPLED_POSE,
        }

    @property
    def collision_free_diagnostic(self) -> bool:
        return (
            self.evaluation_complete
            and self.geometry_audit.diagnostic_ready
            and not self.collisions
        )

    @property
    def report_hash(self) -> str:
        return _stable_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COLLISION_POSE_REPORT_SCHEMA,
            "contract_id": self.contract_id,
            "pose_id": self.pose_id,
            "status": self.status.value,
            "evaluation_complete": self.evaluation_complete,
            "collision_free_diagnostic": self.collision_free_diagnostic,
            "input_bindings": self.input_bindings.to_dict(),
            "geometry_audit": self.geometry_audit.to_dict(),
            "pose_blockers": [item.to_dict() for item in self.pose_blockers],
            "checked_body_pair_count": self.checked_body_pair_count,
            "broad_phase_candidate_count": self.broad_phase_candidate_count,
            "narrow_phase_primitive_pair_test_count": (
                self.narrow_phase_primitive_pair_test_count
            ),
            "collisions": [item.to_dict() for item in self.collisions],
            "limitations": {
                "single_sampled_pose_only": True,
                "continuous_collision_proof": False,
                "collision_semantics": (
                    "intersection after explicit per-body clearance and uncertainty inflation"
                ),
            },
            "authority": {
                "simulation_only": True,
                "hardware_commands_generated": 0,
                "can_release_physical_gates": False,
                "contact_enabled": False,
            },
        }


def _empty_pose_evaluation(
    contract: CollisionGeometryContract,
    pose: CollisionPose,
    audit: CollisionGeometryAudit,
    status: CollisionEvaluationStatus,
    blockers: Iterable[CollisionBlocker],
    policy: CollisionEvaluationPolicy,
) -> CollisionPoseEvaluation:
    return CollisionPoseEvaluation(
        contract.contract_id,
        pose.pose_id,
        status,
        audit,
        tuple(blockers),
        0,
        0,
        0,
        (),
        CollisionPoseInputBindings(contract, pose, policy),
    )


def _pose_body_primitives(
    contract: CollisionGeometryContract,
    pose: CollisionPose,
) -> tuple[dict[str, tuple[_WorldPrimitive, ...]], tuple[CollisionBlocker, ...]]:
    blockers: list[CollisionBlocker] = []
    world: dict[str, tuple[_WorldPrimitive, ...]] = {}
    for body in contract.bodies:
        if not body.evidence_state.supports_diagnostic:
            continue
        if body.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED:
            sampled_geometry = pose.configuration_primitives.get(body.body_id)
            if sampled_geometry is None:
                blockers.append(
                    CollisionBlocker(
                        CollisionBlockerCode.CONFIGURATION_GEOMETRY_MISSING,
                        body.body_id,
                        "pose lacks required configuration-sampled primitives",
                    )
                )
                continue
            if not sampled_geometry.evidence_state.supports_diagnostic:
                blockers.append(
                    CollisionBlocker(
                        CollisionBlockerCode.CONFIGURATION_GEOMETRY_EVIDENCE_UNUSABLE,
                        body.body_id,
                        f"sample evidence state {sampled_geometry.evidence_state.value} is unusable",
                    )
                )
                continue
            primitives = sampled_geometry.primitives
        else:
            primitives = body.primitives
        if body.binding_mode is CollisionBindingMode.STATIC_ROOT:
            if body.parent_frame != contract.root_frame:
                blockers.append(
                    CollisionBlocker(
                        CollisionBlockerCode.POSE_TRANSFORM_FRAME_MISMATCH,
                        body.body_id,
                        "STATIC_ROOT body parent is not the collision root",
                    )
                )
                continue
            transform = RigidTransform.identity(contract.root_frame)
        else:
            candidate_transform = pose.root_t_parent.get(body.parent_frame)
            if candidate_transform is None:
                blockers.append(
                    CollisionBlocker(
                        CollisionBlockerCode.POSE_TRANSFORM_MISSING,
                        body.body_id,
                        f"pose lacks {contract.root_frame}_T_{body.parent_frame}",
                    )
                )
                continue
            transform = candidate_transform
            if (
                transform.parent_frame != contract.root_frame
                or transform.child_frame != body.parent_frame
            ):
                blockers.append(
                    CollisionBlocker(
                        CollisionBlockerCode.POSE_TRANSFORM_FRAME_MISMATCH,
                        body.body_id,
                        f"transform is {transform.parent_frame}_T_{transform.child_frame}",
                    )
                )
                continue
        world[body.body_id] = tuple(_world_primitive(item, transform) for item in primitives)
    blockers.sort(key=lambda item: (item.body_id, item.code.value))
    return world, tuple(blockers)


def _candidate_body_pairs(
    contract: CollisionGeometryContract,
    body_ids: Iterable[str],
) -> tuple[tuple[str, str], ...]:
    bodies = contract.bodies_by_id
    exclusions = {item.pair for item in contract.pair_exclusions}
    ordered = sorted(body_ids)
    pairs: list[tuple[str, str]] = []
    for left_index, left_id in enumerate(ordered):
        for right_id in ordered[left_index + 1 :]:
            pair = (left_id, right_id)
            if pair in exclusions:
                continue
            if (
                bodies[left_id].role is CollisionBodyRole.STATIC_ENVIRONMENT
                and bodies[right_id].role is CollisionBodyRole.STATIC_ENVIRONMENT
            ):
                continue
            pairs.append(pair)
    return tuple(pairs)


def evaluate_collision_pose(
    contract: CollisionGeometryContract,
    pose: CollisionPose,
    policy: CollisionEvaluationPolicy | None = None,
) -> CollisionPoseEvaluation:
    """Evaluate one complete sampled pose with broad and narrow phases."""

    if not isinstance(contract, CollisionGeometryContract):
        raise TypeError("contract must be CollisionGeometryContract")
    if not isinstance(pose, CollisionPose):
        raise TypeError("pose must be CollisionPose")
    selected_policy = policy or CollisionEvaluationPolicy()
    if not isinstance(selected_policy, CollisionEvaluationPolicy):
        raise TypeError("policy must be CollisionEvaluationPolicy")
    if pose.root_frame != contract.root_frame:
        raise CollisionContractError(
            f"pose root {pose.root_frame!r} differs from contract root {contract.root_frame!r}"
        )
    if len(contract.bodies) > selected_policy.maximum_bodies:
        raise CollisionResourceLimitError("body count exceeds policy maximum_bodies")
    audit = audit_collision_geometry(contract)
    if not audit.diagnostic_ready:
        return _empty_pose_evaluation(
            contract,
            pose,
            audit,
            CollisionEvaluationStatus.BLOCKED_INCOMPLETE_GEOMETRY,
            audit.diagnostic_blockers,
            selected_policy,
        )
    if selected_policy.clearance_policy is None:
        return _empty_pose_evaluation(
            contract,
            pose,
            audit,
            CollisionEvaluationStatus.BLOCKED_CLEARANCE_POLICY,
            (
                CollisionBlocker(
                    CollisionBlockerCode.CLEARANCE_POLICY_MISSING,
                    "__policy__",
                    "an explicit positive clearance and uncertainty policy is required",
                ),
            ),
            selected_policy,
        )
    world, pose_blockers = _pose_body_primitives(contract, pose)
    if pose_blockers:
        return _empty_pose_evaluation(
            contract,
            pose,
            audit,
            CollisionEvaluationStatus.BLOCKED_INCOMPLETE_POSE,
            pose_blockers,
            selected_policy,
        )
    inflation = selected_policy.clearance_policy.per_body_inflation_mm
    world = {
        body_id: tuple(_inflate_world_primitive(item, inflation) for item in primitives)
        for body_id, primitives in world.items()
    }
    body_pairs = _candidate_body_pairs(contract, world)
    if len(body_pairs) > selected_policy.maximum_body_pairs_per_pose:
        raise CollisionResourceLimitError("body-pair count exceeds per-pose policy cap")
    body_bounds = {
        body_id: BoundsMm.union(tuple(_primitive_bounds(item) for item in primitives))
        for body_id, primitives in world.items()
    }
    broad_candidates: list[tuple[str, str]] = []
    collisions: list[CollisionPair] = []
    narrow_tests = 0
    for left_id, right_id in body_pairs:
        if not body_bounds[left_id].intersects(body_bounds[right_id]):
            continue
        broad_candidates.append((left_id, right_id))
        for left_index, left in enumerate(world[left_id]):
            for right_index, right in enumerate(world[right_id]):
                narrow_tests += 1
                if narrow_tests > selected_policy.maximum_primitive_pair_tests_per_pose:
                    raise CollisionResourceLimitError(
                        "primitive-pair tests exceed per-pose policy cap"
                    )
                if _primitive_intersects(left, right):
                    collisions.append(
                        CollisionPair(left_id, right_id, left_index, right_index)
                    )
    return CollisionPoseEvaluation(
        contract_id=contract.contract_id,
        pose_id=pose.pose_id,
        status=(
            CollisionEvaluationStatus.COLLISION_DETECTED
            if collisions
            else CollisionEvaluationStatus.CLEAR_AT_SAMPLED_POSE
        ),
        geometry_audit=audit,
        pose_blockers=(),
        checked_body_pair_count=len(body_pairs),
        broad_phase_candidate_count=len(broad_candidates),
        narrow_phase_primitive_pair_test_count=narrow_tests,
        collisions=tuple(collisions),
        input_bindings=CollisionPoseInputBindings(contract, pose, selected_policy),
    )


def evaluate_collision_pose_clearance_lower_bound(
    contract: CollisionGeometryContract,
    pose: CollisionPose,
    policy: CollisionEvaluationPolicy | None = None,
) -> CollisionClearanceLowerBoundEvaluation:
    """Measure conservative residual clearance for one collision pose.

    The same audited, transformed, and policy-inflated primitives used by the
    collision query are evaluated. Incomplete evidence remains explicitly
    indeterminate, and this companion result never adds physical authority.
    """

    selected_policy = policy or CollisionEvaluationPolicy()
    evaluation = evaluate_collision_pose(contract, pose, selected_policy)
    if not evaluation.evaluation_complete:
        return CollisionClearanceLowerBoundEvaluation(
            CollisionClearanceLowerBoundStatus.INDETERMINATE,
            None,
            None,
            0,
            0,
            evaluation.report_hash,
        )
    world, pose_blockers = _pose_body_primitives(contract, pose)
    if pose_blockers:
        return CollisionClearanceLowerBoundEvaluation(
            CollisionClearanceLowerBoundStatus.INDETERMINATE,
            None,
            None,
            0,
            0,
            evaluation.report_hash,
        )
    assert selected_policy.clearance_policy is not None
    inflation = selected_policy.clearance_policy.per_body_inflation_mm
    world = {
        body_id: tuple(_inflate_world_primitive(item, inflation) for item in primitives)
        for body_id, primitives in world.items()
    }
    body_pairs = _candidate_body_pairs(contract, world)
    if not body_pairs:
        return CollisionClearanceLowerBoundEvaluation(
            CollisionClearanceLowerBoundStatus.INDETERMINATE,
            None,
            None,
            0,
            0,
            evaluation.report_hash,
        )
    minimum: float | None = None
    limiting_pair: tuple[str, str] | None = None
    primitive_pair_count = 0
    for left_id, right_id in body_pairs:
        for left in world[left_id]:
            for right in world[right_id]:
                primitive_pair_count += 1
                if (
                    primitive_pair_count
                    > selected_policy.maximum_primitive_pair_tests_per_pose
                ):
                    raise CollisionResourceLimitError(
                        "clearance primitive-pair tests exceed per-pose policy cap"
                    )
                candidate = _primitive_clearance_lower_bound_mm(left, right)
                if minimum is None or candidate < minimum:
                    minimum = candidate
                    limiting_pair = (left_id, right_id)
    collision_detected = (
        evaluation.status is CollisionEvaluationStatus.COLLISION_DETECTED
    )
    if collision_detected:
        first_collision = evaluation.collisions[0]
        minimum = 0.0
        limiting_pair = (
            first_collision.first_body_id,
            first_collision.second_body_id,
        )
    return CollisionClearanceLowerBoundEvaluation(
        (
            CollisionClearanceLowerBoundStatus.COLLISION
            if collision_detected
            else CollisionClearanceLowerBoundStatus.CLEAR
        ),
        minimum,
        limiting_pair,
        len(body_pairs),
        primitive_pair_count,
        evaluation.report_hash,
    )


def _rotation_angle(left: Rotation3, right: Rotation3) -> float:
    relative = left.inverse().compose(right).matrix
    cosine = max(-1.0, min(1.0, (relative[0] + relative[4] + relative[8] - 1.0) / 2.0))
    return math.acos(cosine)


def _rotation_to_quaternion(rotation: Rotation3) -> tuple[float, float, float, float]:
    matrix = rotation.matrix
    trace = matrix[0] + matrix[4] + matrix[8]
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        quaternion = (
            0.25 * scale,
            (matrix[7] - matrix[5]) / scale,
            (matrix[2] - matrix[6]) / scale,
            (matrix[3] - matrix[1]) / scale,
        )
    elif matrix[0] > matrix[4] and matrix[0] > matrix[8]:
        scale = math.sqrt(1.0 + matrix[0] - matrix[4] - matrix[8]) * 2.0
        quaternion = (
            (matrix[7] - matrix[5]) / scale,
            0.25 * scale,
            (matrix[1] + matrix[3]) / scale,
            (matrix[2] + matrix[6]) / scale,
        )
    elif matrix[4] > matrix[8]:
        scale = math.sqrt(1.0 + matrix[4] - matrix[0] - matrix[8]) * 2.0
        quaternion = (
            (matrix[2] - matrix[6]) / scale,
            (matrix[1] + matrix[3]) / scale,
            0.25 * scale,
            (matrix[5] + matrix[7]) / scale,
        )
    else:
        scale = math.sqrt(1.0 + matrix[8] - matrix[0] - matrix[4]) * 2.0
        quaternion = (
            (matrix[3] - matrix[1]) / scale,
            (matrix[2] + matrix[6]) / scale,
            (matrix[5] + matrix[7]) / scale,
            0.25 * scale,
        )
    magnitude = math.sqrt(sum(item * item for item in quaternion))
    return tuple(item / magnitude for item in quaternion)  # type: ignore[return-value]


def _quaternion_to_rotation(quaternion: tuple[float, float, float, float]) -> Rotation3:
    w, x, y, z = quaternion
    return Rotation3(
        (
            1.0 - 2.0 * (y * y + z * z),
            2.0 * (x * y - z * w),
            2.0 * (x * z + y * w),
            2.0 * (x * y + z * w),
            1.0 - 2.0 * (x * x + z * z),
            2.0 * (y * z - x * w),
            2.0 * (x * z - y * w),
            2.0 * (y * z + x * w),
            1.0 - 2.0 * (x * x + y * y),
        )
    )


def _interpolate_rotation(left: Rotation3, right: Rotation3, parameter: float) -> Rotation3:
    first = _rotation_to_quaternion(left)
    second = _rotation_to_quaternion(right)
    dot = sum(a * b for a, b in zip(first, second))
    if dot < 0.0:
        second = tuple(-item for item in second)  # type: ignore[assignment]
        dot = -dot
    if dot > 0.9995:
        mixed = tuple(a + parameter * (b - a) for a, b in zip(first, second))
        magnitude = math.sqrt(sum(item * item for item in mixed))
        return _quaternion_to_rotation(
            tuple(item / magnitude for item in mixed)  # type: ignore[arg-type]
        )
    angle = math.acos(max(-1.0, min(1.0, dot)))
    sine = math.sin(angle)
    left_weight = math.sin((1.0 - parameter) * angle) / sine
    right_weight = math.sin(parameter * angle) / sine
    return _quaternion_to_rotation(
        tuple(left_weight * a + right_weight * b for a, b in zip(first, second))  # type: ignore[arg-type]
    )


def _interpolate_transform(
    start: RigidTransform,
    end: RigidTransform,
    parameter: float,
) -> RigidTransform:
    if (
        start.parent_frame != end.parent_frame
        or start.child_frame != end.child_frame
    ):
        raise CollisionContractError("sweep endpoint transform frames differ")
    translation = start.translation_mm + (end.translation_mm - start.translation_mm).scaled(
        parameter
    )
    return RigidTransform(
        start.parent_frame,
        start.child_frame,
        _interpolate_rotation(start.rotation, end.rotation, parameter),
        translation,
    )


def _primitive_origin_radius(primitive: CollisionPrimitive) -> float:
    if isinstance(primitive, SphereMm):
        return primitive.center_mm.norm + primitive.radius_mm
    if isinstance(primitive, CapsuleMm):
        return max(primitive.start_mm.norm, primitive.end_mm.norm) + primitive.radius_mm
    return primitive.center_mm.norm + primitive.half_extents_mm.norm


@dataclass(frozen=True, slots=True)
class CollisionSweepSample:
    sample_index: int
    interpolation_fraction: float
    status: CollisionEvaluationStatus
    collision_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_index": self.sample_index,
            "interpolation_fraction": self.interpolation_fraction,
            "status": self.status.value,
            "collision_count": self.collision_count,
        }


@dataclass(frozen=True, slots=True)
class CollisionSweepEvaluation:
    contract_id: str
    start_pose_id: str
    end_pose_id: str
    status: CollisionEvaluationStatus
    geometry_audit: CollisionGeometryAudit
    blockers: tuple[CollisionBlocker, ...]
    planned_sample_count: int
    samples: tuple[CollisionSweepSample, ...]
    checked_body_pair_count: int
    narrow_phase_primitive_pair_test_count: int
    collisions: tuple[tuple[int, CollisionPair], ...]
    input_bindings: CollisionSweepInputBindings

    def __post_init__(self) -> None:
        if not isinstance(self.input_bindings, CollisionSweepInputBindings):
            raise TypeError("input_bindings must be CollisionSweepInputBindings")
        if self.input_bindings.contract.contract_id != self.contract_id:
            raise CollisionContractError("sweep report contract id differs from bound content")
        if self.input_bindings.start_pose.pose_id != self.start_pose_id:
            raise CollisionContractError("sweep report start pose id differs from bound content")
        if self.input_bindings.end_pose.pose_id != self.end_pose_id:
            raise CollisionContractError("sweep report end pose id differs from bound content")

    @property
    def evaluation_complete(self) -> bool:
        return self.status in {
            CollisionEvaluationStatus.COLLISION_DETECTED,
            CollisionEvaluationStatus.CLEAR_AT_DISCRETE_SWEEP_SAMPLES,
        }

    @property
    def collision_free_at_discrete_samples(self) -> bool:
        return (
            self.status
            is CollisionEvaluationStatus.CLEAR_AT_DISCRETE_SWEEP_SAMPLES
            and self.geometry_audit.diagnostic_ready
            and len(self.samples) == self.planned_sample_count
            and not self.collisions
        )

    @property
    def continuous_collision_proof(self) -> bool:
        return False

    @property
    def report_hash(self) -> str:
        return _stable_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COLLISION_SWEEP_REPORT_SCHEMA,
            "contract_id": self.contract_id,
            "start_pose_id": self.start_pose_id,
            "end_pose_id": self.end_pose_id,
            "status": self.status.value,
            "evaluation_complete": self.evaluation_complete,
            "collision_free_at_discrete_samples": self.collision_free_at_discrete_samples,
            "continuous_collision_proof": False,
            "input_bindings": self.input_bindings.to_dict(),
            "sweep_method": (
                "bounded_rigid_transform_interpolation_with_translation_rotation_"
                "and_body_radius_driven_discrete_sampling"
            ),
            "geometry_audit": self.geometry_audit.to_dict(),
            "blockers": [item.to_dict() for item in self.blockers],
            "planned_sample_count": self.planned_sample_count,
            "evaluated_sample_count": len(self.samples),
            "samples": [item.to_dict() for item in self.samples],
            "checked_body_pair_count": self.checked_body_pair_count,
            "narrow_phase_primitive_pair_test_count": (
                self.narrow_phase_primitive_pair_test_count
            ),
            "collisions": [
                {"sample_index": index, "pair": pair.to_dict()}
                for index, pair in self.collisions
            ],
            "limitations": [
                "Discrete samples do not prove continuous collision freedom between samples.",
                "Only uncertainty explicitly encoded by the bound clearance policy is inflated.",
                "Dynamics, deformation, payload, force, and cable behavior are not inferred.",
            ],
            "authority": {
                "simulation_only": True,
                "hardware_commands_generated": 0,
                "can_release_physical_gates": False,
                "contact_enabled": False,
            },
        }


def _blocked_sweep(
    contract: CollisionGeometryContract,
    start_pose: CollisionPose,
    end_pose: CollisionPose,
    audit: CollisionGeometryAudit,
    status: CollisionEvaluationStatus,
    blockers: Iterable[CollisionBlocker],
    policy: CollisionEvaluationPolicy,
) -> CollisionSweepEvaluation:
    return CollisionSweepEvaluation(
        contract.contract_id,
        start_pose.pose_id,
        end_pose.pose_id,
        status,
        audit,
        tuple(blockers),
        0,
        (),
        0,
        0,
        (),
        CollisionSweepInputBindings(contract, start_pose, end_pose, policy),
    )


def evaluate_collision_sweep(
    contract: CollisionGeometryContract,
    start_pose: CollisionPose,
    end_pose: CollisionPose,
    policy: CollisionEvaluationPolicy | None = None,
) -> CollisionSweepEvaluation:
    """Evaluate a bounded discrete rigid-body sweep between two poses.

    A required ``CONFIGURATION_SAMPLED`` body (for example a moving cable)
    cannot be interpolated from endpoint shapes.  Such a sweep fails closed
    until intermediate, configuration-specific geometry is supplied through a
    future explicit waypoint-sequence boundary.
    """

    if not isinstance(contract, CollisionGeometryContract):
        raise TypeError("contract must be CollisionGeometryContract")
    if not isinstance(start_pose, CollisionPose) or not isinstance(end_pose, CollisionPose):
        raise TypeError("sweep endpoints must be CollisionPose values")
    selected_policy = policy or CollisionEvaluationPolicy()
    if not isinstance(selected_policy, CollisionEvaluationPolicy):
        raise TypeError("policy must be CollisionEvaluationPolicy")
    if start_pose.root_frame != contract.root_frame or end_pose.root_frame != contract.root_frame:
        raise CollisionContractError("sweep endpoint root frames must match the contract root")
    if len(contract.bodies) > selected_policy.maximum_bodies:
        raise CollisionResourceLimitError("body count exceeds policy maximum_bodies")
    audit = audit_collision_geometry(contract)
    if not audit.diagnostic_ready:
        return _blocked_sweep(
            contract,
            start_pose,
            end_pose,
            audit,
            CollisionEvaluationStatus.BLOCKED_INCOMPLETE_GEOMETRY,
            audit.diagnostic_blockers,
            selected_policy,
        )
    if selected_policy.clearance_policy is None:
        return _blocked_sweep(
            contract,
            start_pose,
            end_pose,
            audit,
            CollisionEvaluationStatus.BLOCKED_CLEARANCE_POLICY,
            (
                CollisionBlocker(
                    CollisionBlockerCode.CLEARANCE_POLICY_MISSING,
                    "__policy__",
                    "an explicit positive clearance and uncertainty policy is required",
                ),
            ),
            selected_policy,
        )
    configuration_bodies = tuple(
        item.body_id
        for item in contract.bodies
        if item.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
    )
    if configuration_bodies:
        blockers = tuple(
            CollisionBlocker(
                CollisionBlockerCode.DEFORMABLE_SWEEP_INTERMEDIATE_GEOMETRY_UNAVAILABLE,
                body_id,
                "endpoint shapes cannot define intermediate deformable cable geometry",
            )
            for body_id in sorted(configuration_bodies)
        )
        return _blocked_sweep(
            contract,
            start_pose,
            end_pose,
            audit,
            CollisionEvaluationStatus.BLOCKED_DEFORMABLE_SWEEP,
            blockers,
            selected_policy,
        )
    start_world, start_blockers = _pose_body_primitives(contract, start_pose)
    end_world, end_blockers = _pose_body_primitives(contract, end_pose)
    blockers = tuple(sorted(start_blockers + end_blockers, key=lambda item: (item.body_id, item.code.value)))
    if blockers:
        return _blocked_sweep(
            contract,
            start_pose,
            end_pose,
            audit,
            CollisionEvaluationStatus.BLOCKED_INCOMPLETE_POSE,
            blockers,
            selected_policy,
        )
    del start_world, end_world  # endpoint validation only; samples rebuild deterministically
    maximum_ratio = 0.0
    bodies = contract.bodies_by_id
    for frame in sorted(
        {
            body.parent_frame
            for body in contract.bodies
            if body.binding_mode is CollisionBindingMode.RIGID_FRAME
        }
    ):
        start_transform = start_pose.root_t_parent[frame]
        end_transform = end_pose.root_t_parent[frame]
        translation_distance = (
            end_transform.translation_mm - start_transform.translation_mm
        ).norm
        angle = _rotation_angle(start_transform.rotation, end_transform.rotation)
        body_radius = max(
            (
                _primitive_origin_radius(primitive)
                for body in contract.bodies
                if body.parent_frame == frame
                for primitive in body.primitives
            ),
            default=0.0,
        ) + math.sqrt(3.0) * selected_policy.clearance_policy.per_body_inflation_mm
        surface_travel_bound = translation_distance + angle * body_radius
        maximum_ratio = max(
            maximum_ratio,
            surface_travel_bound / selected_policy.maximum_surface_step_mm,
            angle / selected_policy.maximum_rotation_step_rad,
        )
    interval_count = max(1, math.ceil(maximum_ratio))
    sample_count = interval_count + 1
    if sample_count > selected_policy.maximum_sweep_samples:
        raise CollisionResourceLimitError(
            f"sweep requires {sample_count} samples; policy cap is "
            f"{selected_policy.maximum_sweep_samples}"
        )
    body_pairs = _candidate_body_pairs(contract, (item.body_id for item in contract.bodies))
    primitive_pair_upper_bound = sum(
        len(bodies[left].primitives) * len(bodies[right].primitives)
        for left, right in body_pairs
    )
    if len(body_pairs) * sample_count > selected_policy.maximum_sweep_body_pair_evaluations:
        raise CollisionResourceLimitError("sweep body-pair evaluation upper bound exceeds policy cap")
    if (
        primitive_pair_upper_bound * sample_count
        > selected_policy.maximum_sweep_primitive_pair_evaluations
    ):
        raise CollisionResourceLimitError(
            "sweep primitive-pair evaluation upper bound exceeds policy cap"
        )
    samples: list[CollisionSweepSample] = []
    collisions: list[tuple[int, CollisionPair]] = []
    checked_pairs = 0
    narrow_tests = 0
    for index in range(sample_count):
        parameter = index / interval_count
        transforms = {
            frame: _interpolate_transform(
                start_pose.root_t_parent[frame],
                end_pose.root_t_parent[frame],
                parameter,
            )
            for frame in sorted(start_pose.root_t_parent)
            if frame in end_pose.root_t_parent
        }
        sample_pose = CollisionPose(
            pose_id=f"{start_pose.pose_id}--{end_pose.pose_id}--sample-{index:04d}",
            root_frame=contract.root_frame,
            root_t_parent=transforms,
        )
        evaluation = evaluate_collision_pose(contract, sample_pose, selected_policy)
        checked_pairs += evaluation.checked_body_pair_count
        narrow_tests += evaluation.narrow_phase_primitive_pair_test_count
        samples.append(
            CollisionSweepSample(
                index, parameter, evaluation.status, len(evaluation.collisions)
            )
        )
        collisions.extend((index, item) for item in evaluation.collisions)
        if evaluation.collisions:
            break
        if not evaluation.evaluation_complete:
            return _blocked_sweep(
                contract,
                start_pose,
                end_pose,
                audit,
                evaluation.status,
                evaluation.pose_blockers,
                selected_policy,
            )
    return CollisionSweepEvaluation(
        contract_id=contract.contract_id,
        start_pose_id=start_pose.pose_id,
        end_pose_id=end_pose.pose_id,
        status=(
            CollisionEvaluationStatus.COLLISION_DETECTED
            if collisions
            else CollisionEvaluationStatus.CLEAR_AT_DISCRETE_SWEEP_SAMPLES
        ),
        geometry_audit=audit,
        blockers=(),
        planned_sample_count=sample_count,
        samples=tuple(samples),
        checked_body_pair_count=checked_pairs,
        narrow_phase_primitive_pair_test_count=narrow_tests,
        collisions=tuple(collisions),
        input_bindings=CollisionSweepInputBindings(
            contract, start_pose, end_pose, selected_policy
        ),
    )


_ROARM_BODY_REQUIREMENTS = (
    ("robot:base_link", "base_link", CollisionBodyRole.ROBOT_LINK),
    ("robot:link1", "link1", CollisionBodyRole.ROBOT_LINK),
    ("robot:link2", "link2", CollisionBodyRole.ROBOT_LINK),
    ("robot:link3", "link3", CollisionBodyRole.ROBOT_LINK),
    ("robot:link4", "link4", CollisionBodyRole.ROBOT_LINK),
    ("robot:link5", "link5", CollisionBodyRole.ROBOT_LINK),
    ("robot:gripper", "gripper_link", CollisionBodyRole.ROBOT_LINK),
    ("installation:base_and_factory_clamp", "board", CollisionBodyRole.BASE_CLAMP),
    ("attachment:camera_holder", "holder", CollisionBodyRole.ATTACHMENT),
    ("attachment:camera_module", "camera_module", CollisionBodyRole.CAMERA),
    ("attachment:camera_connector", "camera_module", CollisionBodyRole.CONNECTOR),
    ("attachment:moving_camera_cable", "board", CollisionBodyRole.CABLE),
    ("attachment:contact_tool", "hand_tcp", CollisionBodyRole.TOOL),
)


def build_roarm_m3_prehardware_collision_contract(
    model: UrdfModel,
    scene: NominalWorkcellScene | None = None,
) -> CollisionGeometryContract:
    """Describe current collision coverage without inventing any dimensions.

    Robot and attachment entries deliberately contain no primitives.  The
    optional RC03 nominal scene is converted exactly from its existing AABB
    proxies and remains ``PINNED_DIGITAL`` diagnostic-only geometry.
    """

    if not isinstance(model, UrdfModel):
        raise TypeError("model must be UrdfModel")
    if len(model.links) > HARD_MAX_REQUIREMENTS or len(model.joints) > HARD_MAX_REQUIREMENTS:
        raise CollisionResourceLimitError("URDF topology exceeds collision projection hard cap")
    required_links = {
        "base_link",
        "link1",
        "link2",
        "link3",
        "link4",
        "link5",
        "gripper_link",
        "hand_tcp",
    }
    missing_links = sorted(required_links - set(model.link_names))
    if missing_links:
        raise CollisionContractError(
            f"RoArm collision requirements reference absent URDF links: {missing_links}"
        )
    requirements: list[CollisionBodyRequirement] = []
    bodies: list[CollisionBody] = []
    for body_id, parent, role in _ROARM_BODY_REQUIREMENTS:
        mode = (
            CollisionBindingMode.CONFIGURATION_SAMPLED
            if role is CollisionBodyRole.CABLE
            else (
                CollisionBindingMode.STATIC_ROOT
                if role is CollisionBodyRole.BASE_CLAMP
                else CollisionBindingMode.RIGID_FRAME
            )
        )
        requirements.append(
            CollisionBodyRequirement(
                body_id,
                parent,
                role,
                mode,
                "complete installed body envelope is required for collision diagnostics",
            )
        )
        if role is CollisionBodyRole.ROBOT_LINK:
            state = CollisionEvidenceState.MISSING
            source = "no accepted reduced link collision geometry supplied to this contract"
        else:
            state = CollisionEvidenceState.UNKNOWN
            source = "installed dimensions, transform, or configuration remain open"
        bodies.append(
            CollisionBody(body_id, parent, role, state, (), mode, source)
        )
    if scene is not None:
        if not isinstance(scene, NominalWorkcellScene):
            raise TypeError("scene must be NominalWorkcellScene or None")
        if scene.board_frame != "board":
            raise CollisionContractError("canonical prehardware contract expects board frame")
        for obstacle in scene.obstacles:
            body_id = f"workcell:{obstacle.obstacle_id}"
            requirements.append(
                CollisionBodyRequirement(
                    body_id,
                    scene.board_frame,
                    CollisionBodyRole.STATIC_ENVIRONMENT,
                    CollisionBindingMode.STATIC_ROOT,
                    "nominal RC03 obstacle proxy required for prehardware diagnostics",
                )
            )
            minimum = Vec3(
                obstacle.minimum.x, obstacle.minimum.y, obstacle.minimum.z
            )
            maximum = Vec3(
                obstacle.maximum.x, obstacle.maximum.y, obstacle.maximum.z
            )
            center = (minimum + maximum).scaled(0.5)
            half = (maximum - minimum).scaled(0.5)
            bodies.append(
                CollisionBody(
                    body_id,
                    scene.board_frame,
                    CollisionBodyRole.STATIC_ENVIRONMENT,
                    CollisionEvidenceState.PINNED_DIGITAL,
                    (OrientedBoxMm(center, half),),
                    CollisionBindingMode.STATIC_ROOT,
                    f"nominal scene AABB:{obstacle.source}",
                )
            )
    adjacent_exclusions: list[CollisionPairExclusion] = []
    robot_body_for_link = {
        body.parent_frame: body.body_id
        for body in bodies
        if body.role is CollisionBodyRole.ROBOT_LINK
    }
    for joint in model.joints:
        parent_body = robot_body_for_link.get(joint.parent_link)
        child_body = robot_body_for_link.get(joint.child_link)
        if parent_body is not None and child_body is not None:
            adjacent_exclusions.append(
                CollisionPairExclusion(
                    parent_body,
                    child_body,
                    CollisionExclusionScope.URDF_ADJACENT_DIAGNOSTIC,
                    CollisionExclusionEvidenceState.PINNED_KINEMATIC_DIAGNOSTIC,
                    (
                        f"URDF-adjacent bodies joined by {joint.name}; diagnostic "
                        "exclusion only, pending accepted overlap geometry"
                    ),
                    "exact hash-pinned kinematic URDF topology",
                )
            )
    return CollisionGeometryContract(
        contract_id="ROCELL-ROARM-M3-RC03-PREHARDWARE-COLLISION-V1",
        root_frame="board",
        requirements=tuple(requirements),
        bodies=tuple(bodies),
        pair_exclusions=tuple(adjacent_exclusions),
    )


__all__ = [
    "COLLISION_AUDIT_SCHEMA",
    "COLLISION_CLEARANCE_LOWER_BOUND_SCHEMA",
    "COLLISION_CONTRACT_SCHEMA",
    "COLLISION_POSE_REPORT_SCHEMA",
    "COLLISION_SWEEP_REPORT_SCHEMA",
    "CapsuleMm",
    "CollisionBindingMode",
    "CollisionBlocker",
    "CollisionBlockerCode",
    "CollisionBody",
    "CollisionBodyRequirement",
    "CollisionBodyRole",
    "CollisionClearanceEvidenceState",
    "CollisionClearanceLowerBoundEvaluation",
    "CollisionClearanceLowerBoundStatus",
    "CollisionClearancePolicy",
    "CollisionContractError",
    "CollisionEvaluationPolicy",
    "CollisionEvaluationStatus",
    "CollisionEvidenceState",
    "CollisionExclusionEvidenceState",
    "CollisionExclusionScope",
    "CollisionGeometryAudit",
    "CollisionGeometryContract",
    "CollisionPair",
    "CollisionPairExclusion",
    "CollisionPose",
    "CollisionPoseEvaluation",
    "CollisionPoseInputBindings",
    "CollisionResourceLimitError",
    "CollisionSweepEvaluation",
    "CollisionSweepInputBindings",
    "CollisionSweepSample",
    "OrientedBoxMm",
    "SphereMm",
    "SampledCollisionGeometry",
    "audit_collision_geometry",
    "build_roarm_m3_prehardware_collision_contract",
    "evaluate_collision_pose",
    "evaluate_collision_pose_clearance_lower_bound",
    "evaluate_collision_sweep",
]
