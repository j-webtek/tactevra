"""Static-overhead B0477 route collision diagnostics.

This module adds a route-level contract on top of :mod:`rocell.simulation.collision`
without changing that historical primitive evaluator.  It inventories the complete
RoArm/static-camera workcell, binds geometry to named source hashes, evaluates every
required route phase, and evaluates caller-supplied intermediate poses for every
segment.  The moving arm harness is configuration-sampled at every evaluated pose;
endpoint interpolation is deliberately not used for deformable cable geometry.

The service is zero-authority by construction.  A PASS means only that the supplied
model was clear at the supplied discrete samples.  It is never an authorization_v2
physical evidence source and cannot release power, motion, or contact gates.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping as MappingABC
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from rocell.geometry import UrdfModel, Vec3
from rocell.targets import NominalTargetCatalog, TargetRegion

from .collision import (
    CapsuleMm,
    CollisionBindingMode,
    CollisionBody,
    CollisionBodyRequirement,
    CollisionBodyRole,
    CollisionContractError,
    CollisionEvaluationPolicy,
    CollisionEvidenceState,
    CollisionGeometryAudit,
    CollisionGeometryContract,
    CollisionPair,
    CollisionPairExclusion,
    CollisionPose,
    CollisionPoseEvaluation,
    CollisionPrimitive,
    OrientedBoxMm,
    SphereMm,
    audit_collision_geometry,
    evaluate_collision_pose,
)
from .scene import NominalWorkcellScene


STATIC_B0477_ROUTE_CONTRACT_SCHEMA = "rocell.static_b0477_route_contract.v1"
STATIC_B0477_TARGET_BINDING_SCHEMA = "rocell.static_b0477_target_binding.v1"
STATIC_B0477_ROUTE_SCHEMA = "rocell.static_b0477_route.v1"
STATIC_B0477_ROUTE_REPORT_SCHEMA = "rocell.static_b0477_route_report.v1"

MAX_STATIC_ROUTE_BODIES = 64
MAX_STATIC_ROUTE_SOURCE_HASHES = 32
MAX_STATIC_ROUTE_PHASE_POSES = 16
MAX_STATIC_ROUTE_SEGMENTS = 15
MAX_STATIC_ROUTE_SAMPLES_PER_SEGMENT = 32
MAX_STATIC_ROUTE_TOTAL_INTERMEDIATE_SAMPLES = 256

REQUIRED_STATIC_ROUTE_SOURCE_KEYS = frozenset(
    {
        "robot_model",
        "workcell_layout",
        "target_profile",
        "static_support_design",
        "b0477_mechanical_design",
        "fixed_usb_route_design",
        "lighting_design",
        "arm_harness_design",
        "contact_tool_design",
    }
)


class StaticRouteCollisionError(ValueError):
    """A static-camera route or its collision evidence is malformed."""


class StaticRouteGeometryProvenance(str, Enum):
    """Authority of one complete conservative body envelope."""

    MEASURED = "MEASURED"
    CONSERVATIVE_SYNTHETIC = "CONSERVATIVE_SYNTHETIC"
    MISSING = "MISSING"

    @property
    def supports_diagnostic(self) -> bool:
        return self is not StaticRouteGeometryProvenance.MISSING

    @property
    def collision_evidence_state(self) -> CollisionEvidenceState:
        return {
            StaticRouteGeometryProvenance.MEASURED: (
                CollisionEvidenceState.ACCEPTED_MEASURED
            ),
            StaticRouteGeometryProvenance.CONSERVATIVE_SYNTHETIC: (
                CollisionEvidenceState.SYNTHETIC_TEST_ONLY
            ),
            StaticRouteGeometryProvenance.MISSING: CollisionEvidenceState.MISSING,
        }[self]


class StaticRouteBodyRole(str, Enum):
    ROARM_BASE = "ROARM_BASE"
    ROARM_LINK = "ROARM_LINK"
    ROARM_GRIPPER = "ROARM_GRIPPER"
    CONTACT_TOOL_BODY = "CONTACT_TOOL_BODY"
    TOOL_TIP = "TOOL_TIP"
    ARM_HARNESS = "ARM_HARNESS"
    BOARD = "BOARD"
    BASE_CLAMP = "BASE_CLAMP"
    KEYBOARD = "KEYBOARD"
    PHONE = "PHONE"
    PORTAL_POST = "PORTAL_POST"
    PORTAL_CROSSBAR = "PORTAL_CROSSBAR"
    CAMERA_BOOM = "CAMERA_BOOM"
    LIGHTING_BOOM = "LIGHTING_BOOM"
    B0477_ENCLOSURE = "B0477_ENCLOSURE"
    B0477_LENS = "B0477_LENS"
    B0477_CONNECTOR = "B0477_CONNECTOR"
    FIXED_USB_ROUTE = "FIXED_USB_ROUTE"
    LIGHTING = "LIGHTING"

    @property
    def collision_role(self) -> CollisionBodyRole:
        if self in {
            StaticRouteBodyRole.ROARM_BASE,
            StaticRouteBodyRole.ROARM_LINK,
            StaticRouteBodyRole.ROARM_GRIPPER,
        }:
            return CollisionBodyRole.ROBOT_LINK
        if self is StaticRouteBodyRole.BASE_CLAMP:
            return CollisionBodyRole.BASE_CLAMP
        if self in {
            StaticRouteBodyRole.CONTACT_TOOL_BODY,
            StaticRouteBodyRole.TOOL_TIP,
        }:
            return CollisionBodyRole.TOOL
        if self in {
            StaticRouteBodyRole.ARM_HARNESS,
            StaticRouteBodyRole.FIXED_USB_ROUTE,
        }:
            return CollisionBodyRole.CABLE
        if self in {
            StaticRouteBodyRole.B0477_ENCLOSURE,
            StaticRouteBodyRole.B0477_LENS,
        }:
            return CollisionBodyRole.CAMERA
        if self is StaticRouteBodyRole.B0477_CONNECTOR:
            return CollisionBodyRole.CONNECTOR
        return CollisionBodyRole.STATIC_ENVIRONMENT


class StaticRoutePhase(str, Enum):
    PARK = "park"
    TRANSIT = "transit"
    HOVER = "hover"
    APPROACH = "approach"
    CONTACT = "contact"
    RETRACT = "retract"


REQUIRED_STATIC_ROUTE_PHASES = (
    StaticRoutePhase.PARK,
    StaticRoutePhase.TRANSIT,
    StaticRoutePhase.HOVER,
    StaticRoutePhase.APPROACH,
    StaticRoutePhase.CONTACT,
    StaticRoutePhase.RETRACT,
    StaticRoutePhase.PARK,
)


class StaticRouteCollisionStatus(str, Enum):
    BLOCKED_CONTRACT = "BLOCKED_CONTRACT"
    BLOCKED_POLICY = "BLOCKED_POLICY"
    BLOCKED_TARGET_BINDING = "BLOCKED_TARGET_BINDING"
    BLOCKED_PHASE_SEQUENCE = "BLOCKED_PHASE_SEQUENCE"
    BLOCKED_SEGMENT_COVERAGE = "BLOCKED_SEGMENT_COVERAGE"
    BLOCKED_POSE_INPUT = "BLOCKED_POSE_INPUT"
    COLLISION_DETECTED = "COLLISION_DETECTED"
    CONTACT_OVERLAP_MISSING = "CONTACT_OVERLAP_MISSING"
    PASS_DIAGNOSTIC_ONLY = "PASS_DIAGNOSTIC_ONLY"


class StaticRouteSampleDisposition(str, Enum):
    CLEAR = "CLEAR"
    ALLOWED_DESIGNATED_CONTACT = "ALLOWED_DESIGNATED_CONTACT"
    BLOCKED = "BLOCKED"
    COLLISION = "COLLISION"
    REQUIRED_CONTACT_MISSING = "REQUIRED_CONTACT_MISSING"


def _bounded_tuple(values: Iterable[Any], maximum: int, label: str) -> tuple[Any, ...]:
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
    raise StaticRouteCollisionError(f"{label} exceeds hard maximum {maximum}")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StaticRouteCollisionError(f"{label} must be a non-empty string")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    digest = _text(value, label).lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise StaticRouteCollisionError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _finite_fraction(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StaticRouteCollisionError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or not 0.0 < result < 1.0:
        raise StaticRouteCollisionError(f"{label} must be strictly between zero and one")
    return result


@dataclass(frozen=True, slots=True)
class StaticRouteBodyRequirement:
    body_id: str
    parent_frame: str
    role: StaticRouteBodyRole
    binding_mode: CollisionBindingMode
    source_key: str

    def to_dict(self) -> dict[str, str]:
        return {
            "body_id": self.body_id,
            "parent_frame": self.parent_frame,
            "role": self.role.value,
            "binding_mode": self.binding_mode.value,
            "source_key": self.source_key,
        }


def _requirement(
    body_id: str,
    parent_frame: str,
    role: StaticRouteBodyRole,
    binding_mode: CollisionBindingMode,
    source_key: str,
) -> StaticRouteBodyRequirement:
    return StaticRouteBodyRequirement(
        body_id, parent_frame, role, binding_mode, source_key
    )


_RIGID = CollisionBindingMode.RIGID_FRAME
_STATIC = CollisionBindingMode.STATIC_ROOT
_SAMPLED = CollisionBindingMode.CONFIGURATION_SAMPLED

STATIC_ROUTE_BODY_REQUIREMENTS = (
    _requirement("robot:base_link", "base_link", StaticRouteBodyRole.ROARM_BASE, _RIGID, "robot_model"),
    _requirement("robot:link1", "link1", StaticRouteBodyRole.ROARM_LINK, _RIGID, "robot_model"),
    _requirement("robot:link2", "link2", StaticRouteBodyRole.ROARM_LINK, _RIGID, "robot_model"),
    _requirement("robot:link3", "link3", StaticRouteBodyRole.ROARM_LINK, _RIGID, "robot_model"),
    _requirement("robot:link4", "link4", StaticRouteBodyRole.ROARM_LINK, _RIGID, "robot_model"),
    _requirement("robot:link5", "link5", StaticRouteBodyRole.ROARM_LINK, _RIGID, "robot_model"),
    _requirement("robot:gripper", "gripper_link", StaticRouteBodyRole.ROARM_GRIPPER, _RIGID, "robot_model"),
    _requirement("robot:contact_tool", "contact_tool", StaticRouteBodyRole.CONTACT_TOOL_BODY, _RIGID, "contact_tool_design"),
    _requirement("robot:tool_tip", "tool_tip", StaticRouteBodyRole.TOOL_TIP, _RIGID, "contact_tool_design"),
    _requirement("attachment:arm_harness", "arm_harness", StaticRouteBodyRole.ARM_HARNESS, _SAMPLED, "arm_harness_design"),
    _requirement("workcell:board", "board", StaticRouteBodyRole.BOARD, _STATIC, "workcell_layout"),
    _requirement("installation:base_clamp", "board", StaticRouteBodyRole.BASE_CLAMP, _STATIC, "workcell_layout"),
    _requirement("workcell:keyboard", "board", StaticRouteBodyRole.KEYBOARD, _STATIC, "workcell_layout"),
    _requirement("workcell:phone", "board", StaticRouteBodyRole.PHONE, _STATIC, "workcell_layout"),
    _requirement("support:portal_left_post", "board", StaticRouteBodyRole.PORTAL_POST, _STATIC, "static_support_design"),
    _requirement("support:portal_right_post", "board", StaticRouteBodyRole.PORTAL_POST, _STATIC, "static_support_design"),
    _requirement("support:portal_crossbar", "board", StaticRouteBodyRole.PORTAL_CROSSBAR, _STATIC, "static_support_design"),
    _requirement("support:camera_boom", "board", StaticRouteBodyRole.CAMERA_BOOM, _STATIC, "static_support_design"),
    _requirement("support:lighting_boom_left", "board", StaticRouteBodyRole.LIGHTING_BOOM, _STATIC, "static_support_design"),
    _requirement("support:lighting_boom_right", "board", StaticRouteBodyRole.LIGHTING_BOOM, _STATIC, "static_support_design"),
    _requirement("camera:b0477_enclosure", "board", StaticRouteBodyRole.B0477_ENCLOSURE, _STATIC, "b0477_mechanical_design"),
    _requirement("camera:b0477_lens", "board", StaticRouteBodyRole.B0477_LENS, _STATIC, "b0477_mechanical_design"),
    _requirement("camera:b0477_connector", "board", StaticRouteBodyRole.B0477_CONNECTOR, _STATIC, "b0477_mechanical_design"),
    _requirement("cable:fixed_usb_route", "board", StaticRouteBodyRole.FIXED_USB_ROUTE, _STATIC, "fixed_usb_route_design"),
    _requirement("lighting:key_light_left", "board", StaticRouteBodyRole.LIGHTING, _STATIC, "lighting_design"),
    _requirement("lighting:key_light_right", "board", StaticRouteBodyRole.LIGHTING, _STATIC, "lighting_design"),
)

# Retained v2 evidence assumed two dedicated key lights and two lighting booms.
# The selected workcell instead uses variable ambient illumination, so these
# four identifiers are explicitly absent physical hardware rather than missing
# collision geometry. Keep the v2 catalog unchanged and expose an additive
# ambient-light catalog for new consumers.
AMBIENT_LIGHT_ABSENT_BODY_IDS = (
    "support:lighting_boom_left",
    "support:lighting_boom_right",
    "lighting:key_light_left",
    "lighting:key_light_right",
)
AMBIENT_LIGHT_STATIC_ROUTE_BODY_REQUIREMENTS = tuple(
    item
    for item in STATIC_ROUTE_BODY_REQUIREMENTS
    if item.body_id not in AMBIENT_LIGHT_ABSENT_BODY_IDS
)

# Historical v1 readiness evidence used the left-hand identifiers.  This map is
# deliberately explicit and non-bijective: the static architecture splits broad
# attachment placeholders into the independently measurable installed bodies
# already required by the route contract.
STATIC_B0477_LEGACY_BODY_MIGRATION = (
    ("installation:base_and_factory_clamp", ("installation:base_clamp",)),
    (
        "attachment:camera_holder",
        (
            "support:portal_left_post",
            "support:portal_right_post",
            "support:portal_crossbar",
            "support:camera_boom",
        ),
    ),
    (
        "attachment:camera_module",
        ("camera:b0477_enclosure", "camera:b0477_lens"),
    ),
    ("attachment:camera_connector", ("camera:b0477_connector",)),
    ("attachment:moving_camera_cable", ("cable:fixed_usb_route",)),
    (
        "attachment:contact_tool",
        ("robot:contact_tool", "robot:tool_tip"),
    ),
)

_REQUIREMENTS_BY_ID = MappingProxyType(
    {item.body_id: item for item in STATIC_ROUTE_BODY_REQUIREMENTS}
)


def build_static_b0477_prehardware_collision_contract(
    model: UrdfModel,
    scene: NominalWorkcellScene | None = None,
) -> CollisionGeometryContract:
    """Build the opt-in fail-closed v2 contract for the selected static camera.

    The route catalog is the sole body-requirement source.  Existing nominal
    scene AABBs remain separately named diagnostic proxies; they do not satisfy
    an installed-body requirement and cannot clear a physical gate.
    """

    return _build_static_b0477_prehardware_collision_contract(
        model,
        scene,
        requirements=STATIC_ROUTE_BODY_REQUIREMENTS,
        contract_id="ROCELL-ROARM-M3-RC03-STATIC-B0477-PREHARDWARE-COLLISION-V2",
    )


def build_ambient_light_b0477_prehardware_collision_contract(
    model: UrdfModel,
    scene: NominalWorkcellScene | None = None,
) -> CollisionGeometryContract:
    """Build the additive v3 contract for variable ambient illumination.

    Illumination remains a perception-domain condition. It is not represented
    as collision geometry because this architecture has no dedicated light or
    light-support hardware.
    """

    return _build_static_b0477_prehardware_collision_contract(
        model,
        scene,
        requirements=AMBIENT_LIGHT_STATIC_ROUTE_BODY_REQUIREMENTS,
        contract_id=(
            "ROCELL-ROARM-M3-RC03-AMBIENT-LIGHT-B0477-"
            "PREHARDWARE-COLLISION-V3"
        ),
    )


def _build_static_b0477_prehardware_collision_contract(
    model: UrdfModel,
    scene: NominalWorkcellScene | None,
    *,
    requirements: tuple[StaticRouteBodyRequirement, ...],
    contract_id: str,
) -> CollisionGeometryContract:
    if not isinstance(model, UrdfModel):
        raise TypeError("model must be UrdfModel")
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
            f"static B0477 requirements reference absent URDF links: {missing_links}"
        )
    route_requirements = requirements
    requirements = [
        CollisionBodyRequirement(
            item.body_id,
            item.parent_frame,
            item.role.collision_role,
            item.binding_mode,
            (
                "required static B0477 installed body; "
                f"role={item.role.value}; source_key={item.source_key}"
            ),
        )
        for item in route_requirements
    ]
    bodies = [
        CollisionBody(
            item.body_id,
            item.parent_frame,
            item.role.collision_role,
            (
                CollisionEvidenceState.MISSING
                if item.role
                in {
                    StaticRouteBodyRole.ROARM_BASE,
                    StaticRouteBodyRole.ROARM_LINK,
                    StaticRouteBodyRole.ROARM_GRIPPER,
                }
                else CollisionEvidenceState.UNKNOWN
            ),
            (),
            item.binding_mode,
            (
                "installed dimensions, transform, configuration, or accepted "
                f"source remain open; source_key={item.source_key}"
            ),
        )
        for item in route_requirements
    ]
    if scene is not None:
        if not isinstance(scene, NominalWorkcellScene):
            raise TypeError("scene must be NominalWorkcellScene or None")
        if scene.board_frame != "board":
            raise CollisionContractError(
                "static B0477 prehardware contract expects board frame"
            )
        for obstacle in scene.obstacles:
            body_id = f"diagnostic_proxy:{obstacle.obstacle_id}"
            requirements.append(
                CollisionBodyRequirement(
                    body_id,
                    scene.board_frame,
                    CollisionBodyRole.STATIC_ENVIRONMENT,
                    CollisionBindingMode.STATIC_ROOT,
                    "nominal RC03 AABB retained for prehardware diagnostics only",
                )
            )
            minimum = Vec3(
                obstacle.minimum.x, obstacle.minimum.y, obstacle.minimum.z
            )
            maximum = Vec3(
                obstacle.maximum.x, obstacle.maximum.y, obstacle.maximum.z
            )
            bodies.append(
                CollisionBody(
                    body_id,
                    scene.board_frame,
                    CollisionBodyRole.STATIC_ENVIRONMENT,
                    CollisionEvidenceState.PINNED_DIGITAL,
                    (OrientedBoxMm((minimum + maximum).scaled(0.5), (maximum - minimum).scaled(0.5)),),
                    CollisionBindingMode.STATIC_ROOT,
                    f"nominal scene AABB:{obstacle.source}",
                )
            )
    return CollisionGeometryContract(
        contract_id=contract_id,
        root_frame="board",
        requirements=tuple(requirements),
        bodies=tuple(bodies),
        pair_exclusions=(),
    )


@dataclass(frozen=True, slots=True)
class StaticRouteSourceBinding:
    """Hash closure for the mechanical and layout inputs used by the model."""

    support_design_id: str
    support_design_sha256: str
    source_hashes: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "support_design_id",
            _text(self.support_design_id, "support_design_id"),
        )
        support_hash = _sha256(
            self.support_design_sha256, "support_design_sha256"
        )
        if not isinstance(self.source_hashes, MappingABC):
            raise TypeError("source_hashes must be a mapping")
        items = _bounded_tuple(
            self.source_hashes.items(),
            MAX_STATIC_ROUTE_SOURCE_HASHES,
            "source_hashes",
        )
        hashes: dict[str, str] = {}
        for raw_key, raw_digest in items:
            key = _text(raw_key, "source hash key")
            if key in hashes:
                raise StaticRouteCollisionError(f"duplicate source hash key {key!r}")
            hashes[key] = _sha256(raw_digest, f"source_hashes[{key!r}]")
        missing = sorted(REQUIRED_STATIC_ROUTE_SOURCE_KEYS - set(hashes))
        if missing:
            raise StaticRouteCollisionError(
                f"source hash closure is missing required keys: {missing}"
            )
        if hashes["static_support_design"] != support_hash:
            raise StaticRouteCollisionError(
                "support_design_sha256 must equal source_hashes['static_support_design']"
            )
        object.__setattr__(self, "support_design_sha256", support_hash)
        object.__setattr__(self, "source_hashes", MappingProxyType(hashes))

    @property
    def content_hash(self) -> str:
        return _canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "support_design_id": self.support_design_id,
            "support_design_sha256": self.support_design_sha256,
            "source_hashes": dict(sorted(self.source_hashes.items())),
        }


@dataclass(frozen=True, slots=True)
class StaticRouteBody:
    """One body envelope tied to its required role and one source hash key."""

    body_id: str
    parent_frame: str
    role: StaticRouteBodyRole
    binding_mode: CollisionBindingMode
    provenance: StaticRouteGeometryProvenance
    source_key: str
    source_reference: str
    primitives: tuple[CollisionPrimitive, ...] = ()

    def __post_init__(self) -> None:
        body_id = _text(self.body_id, "body_id")
        parent_frame = _text(self.parent_frame, "parent_frame")
        source_key = _text(self.source_key, "source_key")
        source_reference = _text(self.source_reference, "source_reference")
        if not isinstance(self.role, StaticRouteBodyRole):
            raise TypeError("role must be StaticRouteBodyRole")
        if not isinstance(self.binding_mode, CollisionBindingMode):
            raise TypeError("binding_mode must be CollisionBindingMode")
        if not isinstance(self.provenance, StaticRouteGeometryProvenance):
            raise TypeError("provenance must be StaticRouteGeometryProvenance")
        primitives = _bounded_tuple(
            self.primitives, 64, f"body {body_id!r} primitives"
        )
        if any(
            not isinstance(item, (SphereMm, CapsuleMm, OrientedBoxMm))
            for item in primitives
        ):
            raise TypeError("primitives contain an unsupported collision primitive")
        if self.provenance is StaticRouteGeometryProvenance.MISSING and primitives:
            raise StaticRouteCollisionError("MISSING body geometry must have no primitives")
        if (
            self.provenance.supports_diagnostic
            and self.binding_mode is not CollisionBindingMode.CONFIGURATION_SAMPLED
            and not primitives
        ):
            raise StaticRouteCollisionError(
                "diagnostic rigid/static body geometry must contain a primitive"
            )
        object.__setattr__(self, "body_id", body_id)
        object.__setattr__(self, "parent_frame", parent_frame)
        object.__setattr__(self, "source_key", source_key)
        object.__setattr__(self, "source_reference", source_reference)
        object.__setattr__(self, "primitives", primitives)

    def to_dict(self) -> dict[str, Any]:
        return {
            "body_id": self.body_id,
            "parent_frame": self.parent_frame,
            "role": self.role.value,
            "binding_mode": self.binding_mode.value,
            "provenance": self.provenance.value,
            "source_key": self.source_key,
            "source_reference": self.source_reference,
            "primitives": [item.to_dict() for item in self.primitives],
        }


@dataclass(frozen=True, slots=True)
class StaticB0477RouteCollisionContract:
    """Complete body/source contract for the static-overhead camera architecture."""

    contract_id: str
    root_frame: str
    sources: StaticRouteSourceBinding
    bodies: tuple[StaticRouteBody, ...]
    global_pair_exclusions: tuple[CollisionPairExclusion, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_id", _text(self.contract_id, "contract_id"))
        root = _text(self.root_frame, "root_frame")
        if root != "board":
            raise StaticRouteCollisionError("static route collision root must be 'board'")
        if not isinstance(self.sources, StaticRouteSourceBinding):
            raise TypeError("sources must be StaticRouteSourceBinding")
        bodies = _bounded_tuple(self.bodies, MAX_STATIC_ROUTE_BODIES, "bodies")
        if any(not isinstance(item, StaticRouteBody) for item in bodies):
            raise TypeError("bodies must contain StaticRouteBody values")
        if len({item.body_id for item in bodies}) != len(bodies):
            raise StaticRouteCollisionError("body ids must be unique")
        unknown = sorted(set(item.body_id for item in bodies) - set(_REQUIREMENTS_BY_ID))
        if unknown:
            raise StaticRouteCollisionError(f"unknown body ids: {unknown}")
        for body in bodies:
            requirement = _REQUIREMENTS_BY_ID[body.body_id]
            if (
                body.parent_frame != requirement.parent_frame
                or body.role is not requirement.role
                or body.binding_mode is not requirement.binding_mode
                or body.source_key != requirement.source_key
            ):
                raise StaticRouteCollisionError(
                    f"body {body.body_id!r} differs from its required role/frame/mode/source"
                )
            if body.source_key not in self.sources.source_hashes:
                raise StaticRouteCollisionError(
                    f"body {body.body_id!r} source key is not hash-bound"
                )
        exclusions = _bounded_tuple(
            self.global_pair_exclusions, 256, "global_pair_exclusions"
        )
        if any(not isinstance(item, CollisionPairExclusion) for item in exclusions):
            raise TypeError("global_pair_exclusions must contain CollisionPairExclusion")
        # Global exclusions make an overlap invisible to the primitive
        # evaluator.  This route contract promises that the sole tolerated
        # overlap is applied locally at CONTACT, so no global exclusion can be
        # admitted here (including otherwise common adjacent-link exclusions).
        if exclusions:
            raise StaticRouteCollisionError(
                "static target routes do not permit global collision exclusions"
            )
        tool_tip = next(
            (item for item in bodies if item.body_id == "robot:tool_tip"), None
        )
        if tool_tip is not None and tool_tip.provenance.supports_diagnostic:
            if (
                len(tool_tip.primitives) != 1
                or not isinstance(tool_tip.primitives[0], SphereMm)
                or not tool_tip.primitives[0].center_mm.almost_equal(Vec3.zero())
            ):
                raise StaticRouteCollisionError(
                    "robot:tool_tip must be one origin-centered sphere"
                )
        object.__setattr__(self, "root_frame", root)
        object.__setattr__(self, "bodies", bodies)
        object.__setattr__(self, "global_pair_exclusions", exclusions)

    @property
    def collision_contract(self) -> CollisionGeometryContract:
        supplied = {item.body_id: item for item in self.bodies}
        requirements = tuple(
            CollisionBodyRequirement(
                item.body_id,
                item.parent_frame,
                item.role.collision_role,
                item.binding_mode,
                f"required static B0477 route body ({item.role.value})",
            )
            for item in STATIC_ROUTE_BODY_REQUIREMENTS
        )
        bodies = tuple(
            CollisionBody(
                item.body_id,
                item.parent_frame,
                item.role.collision_role,
                item.provenance.collision_evidence_state,
                item.primitives,
                item.binding_mode,
                (
                    f"{item.source_reference}; source_key={item.source_key}; "
                    f"sha256={self.sources.source_hashes[item.source_key]}"
                ),
            )
            for item in supplied.values()
        )
        return CollisionGeometryContract(
            contract_id=self.contract_id,
            root_frame=self.root_frame,
            requirements=requirements,
            bodies=bodies,
            pair_exclusions=self.global_pair_exclusions,
        )

    @property
    def content_hash(self) -> str:
        return _canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        collision_contract = self.collision_contract
        return {
            "schema": STATIC_B0477_ROUTE_CONTRACT_SCHEMA,
            "contract_id": self.contract_id,
            "root_frame": self.root_frame,
            "sources": self.sources.to_dict(),
            "requirements": [item.to_dict() for item in STATIC_ROUTE_BODY_REQUIREMENTS],
            "bodies": [item.to_dict() for item in self.bodies],
            "global_pair_exclusions": [
                item.to_dict() for item in self.global_pair_exclusions
            ],
            "primitive_collision_contract_sha256": collision_contract.content_hash,
            "authority": _zero_authority(),
        }


@dataclass(frozen=True, slots=True)
class StaticRouteTargetBinding:
    device: str
    target_id: str
    target_body_id: str
    target_profile_sha256: str
    target_region_sha256: str
    center_board_mm: Vec3

    def __post_init__(self) -> None:
        if self.device not in {"keyboard", "phone"}:
            raise StaticRouteCollisionError("target device must be keyboard or phone")
        object.__setattr__(self, "target_id", _text(self.target_id, "target_id"))
        expected_body = f"workcell:{self.device}"
        if self.target_body_id != expected_body:
            raise StaticRouteCollisionError(
                f"{self.device} target must designate body {expected_body!r}"
            )
        object.__setattr__(
            self,
            "target_profile_sha256",
            _sha256(self.target_profile_sha256, "target_profile_sha256"),
        )
        object.__setattr__(
            self,
            "target_region_sha256",
            _sha256(self.target_region_sha256, "target_region_sha256"),
        )
        if not isinstance(self.center_board_mm, Vec3):
            raise TypeError("center_board_mm must be Vec3")

    @property
    def content_hash(self) -> str:
        return _canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": STATIC_B0477_TARGET_BINDING_SCHEMA,
            "device": self.device,
            "target_id": self.target_id,
            "target_body_id": self.target_body_id,
            "target_profile_sha256": self.target_profile_sha256,
            "target_region_sha256": self.target_region_sha256,
            "center_board_mm": [
                self.center_board_mm.x,
                self.center_board_mm.y,
                self.center_board_mm.z,
            ],
            "authority": _zero_authority(),
        }


def bind_static_route_target(
    catalog: NominalTargetCatalog,
    device: str,
    target_id: str,
) -> StaticRouteTargetBinding:
    """Create a deterministic target binding from the simulation-only catalog."""

    if not isinstance(catalog, NominalTargetCatalog):
        raise TypeError("catalog must be NominalTargetCatalog")
    target = catalog.resolve(device, target_id)
    if not isinstance(target, TargetRegion):
        raise TypeError("catalog target must be TargetRegion")
    return StaticRouteTargetBinding(
        device=device,
        target_id=target.target_id,
        target_body_id=f"workcell:{device}",
        target_profile_sha256=catalog.content_sha256,
        target_region_sha256=_canonical_hash(target.to_dict()),
        center_board_mm=Vec3(target.center.x, target.center.y, target.center.z),
    )


@dataclass(frozen=True, slots=True)
class StaticRoutePhasePose:
    phase: StaticRoutePhase
    pose: CollisionPose

    def __post_init__(self) -> None:
        if not isinstance(self.phase, StaticRoutePhase):
            raise TypeError("phase must be StaticRoutePhase")
        if not isinstance(self.pose, CollisionPose):
            raise TypeError("pose must be CollisionPose")

    def to_dict(self) -> dict[str, Any]:
        return {"phase": self.phase.value, "pose": self.pose.to_dict()}


@dataclass(frozen=True, slots=True)
class StaticRouteIntermediateSample:
    interpolation_fraction: float
    pose: CollisionPose

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "interpolation_fraction",
            _finite_fraction(self.interpolation_fraction, "interpolation_fraction"),
        )
        if not isinstance(self.pose, CollisionPose):
            raise TypeError("pose must be CollisionPose")

    def to_dict(self) -> dict[str, Any]:
        return {
            "interpolation_fraction": self.interpolation_fraction,
            "pose": self.pose.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class StaticRouteSegment:
    start_phase_index: int
    end_phase_index: int
    intermediate_samples: tuple[StaticRouteIntermediateSample, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("start_phase_index", self.start_phase_index),
            ("end_phase_index", self.end_phase_index),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise StaticRouteCollisionError(f"{label} must be a non-negative integer")
        samples = _bounded_tuple(
            self.intermediate_samples,
            MAX_STATIC_ROUTE_SAMPLES_PER_SEGMENT,
            "intermediate_samples",
        )
        if any(not isinstance(item, StaticRouteIntermediateSample) for item in samples):
            raise TypeError("intermediate_samples contain an unsupported value")
        fractions = tuple(item.interpolation_fraction for item in samples)
        if fractions != tuple(sorted(fractions)) or len(set(fractions)) != len(fractions):
            raise StaticRouteCollisionError(
                "intermediate sample fractions must be unique and increasing"
            )
        object.__setattr__(self, "intermediate_samples", samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_phase_index": self.start_phase_index,
            "end_phase_index": self.end_phase_index,
            "intermediate_samples": [item.to_dict() for item in self.intermediate_samples],
        }


@dataclass(frozen=True, slots=True)
class StaticTargetRoute:
    route_id: str
    target: StaticRouteTargetBinding
    phase_poses: tuple[StaticRoutePhasePose, ...]
    segments: tuple[StaticRouteSegment, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_id", _text(self.route_id, "route_id"))
        if not isinstance(self.target, StaticRouteTargetBinding):
            raise TypeError("target must be StaticRouteTargetBinding")
        phase_poses = _bounded_tuple(
            self.phase_poses, MAX_STATIC_ROUTE_PHASE_POSES, "phase_poses"
        )
        segments = _bounded_tuple(
            self.segments, MAX_STATIC_ROUTE_SEGMENTS, "segments"
        )
        if any(not isinstance(item, StaticRoutePhasePose) for item in phase_poses):
            raise TypeError("phase_poses contain an unsupported value")
        if any(not isinstance(item, StaticRouteSegment) for item in segments):
            raise TypeError("segments contain an unsupported value")
        pose_ids = [item.pose.pose_id for item in phase_poses]
        pose_ids.extend(
            sample.pose.pose_id for segment in segments for sample in segment.intermediate_samples
        )
        if len(pose_ids) != len(set(pose_ids)):
            raise StaticRouteCollisionError("every route and sample pose_id must be unique")
        object.__setattr__(self, "phase_poses", phase_poses)
        object.__setattr__(self, "segments", segments)

    @property
    def content_hash(self) -> str:
        return _canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": STATIC_B0477_ROUTE_SCHEMA,
            "route_id": self.route_id,
            "target": self.target.to_dict(),
            "phase_poses": [item.to_dict() for item in self.phase_poses],
            "segments": [item.to_dict() for item in self.segments],
            "authority": _zero_authority(),
        }


@dataclass(frozen=True, slots=True)
class StaticRouteCollisionPolicy:
    collision_policy: CollisionEvaluationPolicy
    minimum_intermediate_samples_per_segment: int = 1
    maximum_intermediate_samples_per_segment: int = 16
    require_midpoint_sample: bool = True
    require_designated_contact_overlap: bool = True
    maximum_contact_target_offset_mm: float = 0.001
    source_reference: str = "explicit simulation-only route collision policy"

    def __post_init__(self) -> None:
        if not isinstance(self.collision_policy, CollisionEvaluationPolicy):
            raise TypeError("collision_policy must be CollisionEvaluationPolicy")
        for label, value in (
            ("minimum_intermediate_samples_per_segment", self.minimum_intermediate_samples_per_segment),
            ("maximum_intermediate_samples_per_segment", self.maximum_intermediate_samples_per_segment),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise StaticRouteCollisionError(f"{label} must be a positive integer")
        if (
            self.minimum_intermediate_samples_per_segment
            > self.maximum_intermediate_samples_per_segment
            or self.maximum_intermediate_samples_per_segment
            > MAX_STATIC_ROUTE_SAMPLES_PER_SEGMENT
        ):
            raise StaticRouteCollisionError("intermediate sample policy is inconsistent")
        if not isinstance(self.require_midpoint_sample, bool):
            raise TypeError("require_midpoint_sample must be bool")
        if not isinstance(self.require_designated_contact_overlap, bool):
            raise TypeError("require_designated_contact_overlap must be bool")
        offset_value = self.maximum_contact_target_offset_mm
        if isinstance(offset_value, bool) or not isinstance(offset_value, (int, float)):
            raise StaticRouteCollisionError(
                "maximum_contact_target_offset_mm must be a finite non-negative number"
            )
        offset = float(offset_value)
        if not math.isfinite(offset) or offset < 0.0:
            raise StaticRouteCollisionError(
                "maximum_contact_target_offset_mm must be a finite non-negative number"
            )
        object.__setattr__(self, "maximum_contact_target_offset_mm", offset)
        object.__setattr__(
            self, "source_reference", _text(self.source_reference, "source_reference")
        )

    @property
    def content_hash(self) -> str:
        return _canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "collision_policy": self.collision_policy.to_dict(),
            "minimum_intermediate_samples_per_segment": self.minimum_intermediate_samples_per_segment,
            "maximum_intermediate_samples_per_segment": self.maximum_intermediate_samples_per_segment,
            "require_midpoint_sample": self.require_midpoint_sample,
            "require_designated_contact_overlap": self.require_designated_contact_overlap,
            "maximum_contact_target_offset_mm": self.maximum_contact_target_offset_mm,
            "source_reference": self.source_reference,
            "authority": _zero_authority(),
        }


@dataclass(frozen=True, slots=True)
class StaticRoutePoseResult:
    pose_id: str
    disposition: StaticRouteSampleDisposition
    evaluation: CollisionPoseEvaluation | None
    blocker: str | None = None

    @property
    def accepted(self) -> bool:
        return self.disposition in {
            StaticRouteSampleDisposition.CLEAR,
            StaticRouteSampleDisposition.ALLOWED_DESIGNATED_CONTACT,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "pose_id": self.pose_id,
            "disposition": self.disposition.value,
            "accepted": self.accepted,
            "blocker": self.blocker,
            "primitive_evaluation_sha256": (
                self.evaluation.report_hash if self.evaluation is not None else None
            ),
            "primitive_status": (
                self.evaluation.status.value if self.evaluation is not None else None
            ),
            "collisions": (
                [item.to_dict() for item in self.evaluation.collisions]
                if self.evaluation is not None
                else []
            ),
        }


@dataclass(frozen=True, slots=True)
class StaticRoutePhaseResult:
    phase_index: int
    phase: StaticRoutePhase
    pose_result: StaticRoutePoseResult

    @property
    def accepted(self) -> bool:
        return self.pose_result.accepted

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_index": self.phase_index,
            "phase": self.phase.value,
            "pose_result": self.pose_result.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class StaticRouteSegmentSampleResult:
    interpolation_fraction: float
    pose_result: StaticRoutePoseResult

    @property
    def accepted(self) -> bool:
        return self.pose_result.accepted

    def to_dict(self) -> dict[str, Any]:
        return {
            "interpolation_fraction": self.interpolation_fraction,
            "pose_result": self.pose_result.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class StaticRouteSegmentResult:
    segment_index: int
    start_phase_index: int
    end_phase_index: int
    sample_results: tuple[StaticRouteSegmentSampleResult, ...]

    @property
    def accepted(self) -> bool:
        return bool(self.sample_results) and all(item.accepted for item in self.sample_results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_index": self.segment_index,
            "start_phase_index": self.start_phase_index,
            "end_phase_index": self.end_phase_index,
            "accepted": self.accepted,
            "sample_results": [item.to_dict() for item in self.sample_results],
        }


@dataclass(frozen=True, slots=True)
class StaticRouteCollisionReport:
    status: StaticRouteCollisionStatus
    contract: StaticB0477RouteCollisionContract
    route: StaticTargetRoute
    policy: StaticRouteCollisionPolicy | None
    geometry_audit: CollisionGeometryAudit
    blockers: tuple[str, ...]
    phase_results: tuple[StaticRoutePhaseResult, ...]
    segment_results: tuple[StaticRouteSegmentResult, ...]

    @property
    def passed_diagnostic(self) -> bool:
        return self.status is StaticRouteCollisionStatus.PASS_DIAGNOSTIC_ONLY

    @property
    def can_produce_authorization_v2_physical_evidence(self) -> bool:
        return False

    def as_authorization_v2_physical_evidence(self) -> None:
        """Reject attempts to promote this discrete simulation into authority."""

        raise StaticRouteCollisionError(
            "static route collision reports are diagnostic-only and cannot produce "
            "authorization_v2 physical evidence"
        )

    @property
    def report_hash(self) -> str:
        return _canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": STATIC_B0477_ROUTE_REPORT_SCHEMA,
            "status": self.status.value,
            "passed_diagnostic": self.passed_diagnostic,
            "contract": {
                "sha256": self.contract.content_hash,
                "content": self.contract.to_dict(),
            },
            "route": {"sha256": self.route.content_hash, "content": self.route.to_dict()},
            "policy": (
                None
                if self.policy is None
                else {"sha256": self.policy.content_hash, "content": self.policy.to_dict()}
            ),
            "geometry_audit": self.geometry_audit.to_dict(),
            "blockers": list(self.blockers),
            "phase_results": [item.to_dict() for item in self.phase_results],
            "segment_results": [item.to_dict() for item in self.segment_results],
            "limitations": [
                "Discrete samples are not a continuous collision proof.",
                "Synthetic or measured labels are caller-supplied and are not authenticity proofs.",
                "Dynamics, deflection, force, payload, and unmodelled cable motion are excluded.",
            ],
            "authorization_v2": {
                "eligible_as_physical_evidence": False,
                "reason": "zero-authority discrete simulation diagnostic",
            },
            "authority": _zero_authority(),
        }


def _zero_authority() -> dict[str, Any]:
    return {
        "simulation_only": True,
        "hardware_commands_generated": 0,
        "can_release_physical_gates": False,
        "can_authorize_motion": False,
        "can_authorize_contact": False,
    }


def _empty_report(
    status: StaticRouteCollisionStatus,
    contract: StaticB0477RouteCollisionContract,
    route: StaticTargetRoute,
    policy: StaticRouteCollisionPolicy | None,
    audit: CollisionGeometryAudit,
    blockers: Iterable[str],
) -> StaticRouteCollisionReport:
    return StaticRouteCollisionReport(
        status,
        contract,
        route,
        policy,
        audit,
        tuple(blockers),
        (),
        (),
    )


def _normalized_pair(pair: CollisionPair) -> tuple[str, str]:
    first, second = sorted((pair.first_body_id, pair.second_body_id))
    return first, second


def _evaluate_route_pose(
    collision_contract: CollisionGeometryContract,
    pose: CollisionPose,
    policy: CollisionEvaluationPolicy,
    *,
    allowed_contact_pair: tuple[str, str] | None,
    require_contact: bool,
) -> StaticRoutePoseResult:
    try:
        evaluation = evaluate_collision_pose(collision_contract, pose, policy)
    except (CollisionContractError, TypeError, ValueError) as exc:
        return StaticRoutePoseResult(
            pose.pose_id,
            StaticRouteSampleDisposition.BLOCKED,
            None,
            str(exc),
        )
    if not evaluation.evaluation_complete:
        blockers = evaluation.pose_blockers or evaluation.geometry_audit.diagnostic_blockers
        detail = "; ".join(
            f"{item.code.value}:{item.body_id}" for item in blockers
        ) or evaluation.status.value
        return StaticRoutePoseResult(
            pose.pose_id,
            StaticRouteSampleDisposition.BLOCKED,
            evaluation,
            detail,
        )
    collision_pairs = tuple(_normalized_pair(item) for item in evaluation.collisions)
    if allowed_contact_pair is None:
        if collision_pairs:
            return StaticRoutePoseResult(
                pose.pose_id,
                StaticRouteSampleDisposition.COLLISION,
                evaluation,
                "collision is not allowed outside the CONTACT phase",
            )
        return StaticRoutePoseResult(
            pose.pose_id, StaticRouteSampleDisposition.CLEAR, evaluation
        )
    disallowed = tuple(pair for pair in collision_pairs if pair != allowed_contact_pair)
    if disallowed:
        return StaticRoutePoseResult(
            pose.pose_id,
            StaticRouteSampleDisposition.COLLISION,
            evaluation,
            f"CONTACT contains collisions other than {allowed_contact_pair!r}",
        )
    if allowed_contact_pair in collision_pairs:
        return StaticRoutePoseResult(
            pose.pose_id,
            StaticRouteSampleDisposition.ALLOWED_DESIGNATED_CONTACT,
            evaluation,
        )
    if require_contact:
        return StaticRoutePoseResult(
            pose.pose_id,
            StaticRouteSampleDisposition.REQUIRED_CONTACT_MISSING,
            evaluation,
            "designated tool-tip/target overlap is absent at CONTACT",
        )
    return StaticRoutePoseResult(
        pose.pose_id, StaticRouteSampleDisposition.CLEAR, evaluation
    )


def _route_shape_blockers(
    route: StaticTargetRoute,
    policy: StaticRouteCollisionPolicy,
) -> tuple[StaticRouteCollisionStatus | None, tuple[str, ...]]:
    phases = tuple(item.phase for item in route.phase_poses)
    if phases != REQUIRED_STATIC_ROUTE_PHASES:
        return (
            StaticRouteCollisionStatus.BLOCKED_PHASE_SEQUENCE,
            (
                "phase sequence must be exactly "
                "park/transit/hover/approach/contact/retract/park",
            ),
        )
    expected_segments = tuple((index, index + 1) for index in range(6))
    actual_segments = tuple(
        (item.start_phase_index, item.end_phase_index) for item in route.segments
    )
    blockers: list[str] = []
    if actual_segments != expected_segments:
        blockers.append("segments must cover each adjacent phase pair exactly once")
    total_samples = 0
    for index, segment in enumerate(route.segments):
        count = len(segment.intermediate_samples)
        total_samples += count
        if not (
            policy.minimum_intermediate_samples_per_segment
            <= count
            <= policy.maximum_intermediate_samples_per_segment
        ):
            blockers.append(
                f"segment {index} intermediate sample count {count} violates policy"
            )
        if policy.require_midpoint_sample and not any(
            math.isclose(item.interpolation_fraction, 0.5, abs_tol=1e-12)
            for item in segment.intermediate_samples
        ):
            blockers.append(f"segment {index} has no exact midpoint sample")
    if total_samples > MAX_STATIC_ROUTE_TOTAL_INTERMEDIATE_SAMPLES:
        blockers.append("route intermediate samples exceed the hard total cap")
    return (
        (StaticRouteCollisionStatus.BLOCKED_SEGMENT_COVERAGE if blockers else None),
        tuple(blockers),
    )


def evaluate_static_b0477_target_route(
    contract: StaticB0477RouteCollisionContract,
    route: StaticTargetRoute,
    policy: StaticRouteCollisionPolicy | None,
) -> StaticRouteCollisionReport:
    """Evaluate all seven phases and all six discretely sampled segments.

    Only ``robot:tool_tip`` and the route's designated keyboard/phone body may
    intersect, and only at the CONTACT phase pose.  Intermediate segment samples,
    APPROACH, and RETRACT never inherit that allowance.
    """

    if not isinstance(contract, StaticB0477RouteCollisionContract):
        raise TypeError("contract must be StaticB0477RouteCollisionContract")
    if not isinstance(route, StaticTargetRoute):
        raise TypeError("route must be StaticTargetRoute")
    collision_contract = contract.collision_contract
    audit = audit_collision_geometry(collision_contract)
    if policy is None:
        return _empty_report(
            StaticRouteCollisionStatus.BLOCKED_POLICY,
            contract,
            route,
            policy,
            audit,
            ("an explicit StaticRouteCollisionPolicy is required",),
        )
    if not isinstance(policy, StaticRouteCollisionPolicy):
        raise TypeError("policy must be StaticRouteCollisionPolicy or None")
    if policy.collision_policy.clearance_policy is None:
        return _empty_report(
            StaticRouteCollisionStatus.BLOCKED_POLICY,
            contract,
            route,
            policy,
            audit,
            ("collision_policy must contain an explicit clearance policy",),
        )
    if route.target.target_profile_sha256 != contract.sources.source_hashes["target_profile"]:
        return _empty_report(
            StaticRouteCollisionStatus.BLOCKED_TARGET_BINDING,
            contract,
            route,
            policy,
            audit,
            ("route target profile hash differs from the contract source closure",),
        )
    shape_status, shape_blockers = _route_shape_blockers(route, policy)
    if shape_status is not None:
        return _empty_report(
            shape_status, contract, route, policy, audit, shape_blockers
        )
    if not audit.diagnostic_ready:
        return _empty_report(
            StaticRouteCollisionStatus.BLOCKED_CONTRACT,
            contract,
            route,
            policy,
            audit,
            tuple(
                f"{item.code.value}:{item.body_id}"
                for item in audit.diagnostic_blockers
            ),
        )

    contact_index = REQUIRED_STATIC_ROUTE_PHASES.index(StaticRoutePhase.CONTACT)
    contact_pose = route.phase_poses[contact_index].pose
    tool_transform = contact_pose.root_t_parent.get("tool_tip")
    target_offset_blocker: str | None
    if tool_transform is None:
        target_offset_blocker = "CONTACT pose lacks board_T_tool_tip"
    else:
        offset = (
            tool_transform.translation_mm - route.target.center_board_mm
        ).norm
        target_offset_blocker = (
            f"CONTACT tool-tip origin is {offset:.9g} mm from bound target center"
            if offset > policy.maximum_contact_target_offset_mm
            else None
        )

    allowed_first, allowed_second = sorted(
        ("robot:tool_tip", route.target.target_body_id)
    )
    allowed_pair = (allowed_first, allowed_second)
    phase_results: list[StaticRoutePhaseResult] = []
    for index, item in enumerate(route.phase_poses):
        result = _evaluate_route_pose(
            collision_contract,
            item.pose,
            policy.collision_policy,
            allowed_contact_pair=(allowed_pair if item.phase is StaticRoutePhase.CONTACT else None),
            require_contact=(
                item.phase is StaticRoutePhase.CONTACT
                and policy.require_designated_contact_overlap
            ),
        )
        if item.phase is StaticRoutePhase.CONTACT and target_offset_blocker is not None:
            result = StaticRoutePoseResult(
                item.pose.pose_id,
                StaticRouteSampleDisposition.BLOCKED,
                result.evaluation,
                target_offset_blocker,
            )
        phase_results.append(StaticRoutePhaseResult(index, item.phase, result))

    segment_results: list[StaticRouteSegmentResult] = []
    for index, segment in enumerate(route.segments):
        samples = tuple(
            StaticRouteSegmentSampleResult(
                item.interpolation_fraction,
                _evaluate_route_pose(
                    collision_contract,
                    item.pose,
                    policy.collision_policy,
                    allowed_contact_pair=None,
                    require_contact=False,
                ),
            )
            for item in segment.intermediate_samples
        )
        segment_results.append(
            StaticRouteSegmentResult(
                index,
                segment.start_phase_index,
                segment.end_phase_index,
                samples,
            )
        )

    all_pose_results = [item.pose_result for item in phase_results]
    all_pose_results.extend(
        sample.pose_result
        for segment in segment_results
        for sample in segment.sample_results
    )
    blockers = tuple(
        item.blocker for item in all_pose_results if item.blocker is not None
    )
    if any(item.disposition is StaticRouteSampleDisposition.BLOCKED for item in all_pose_results):
        status = StaticRouteCollisionStatus.BLOCKED_POSE_INPUT
    elif any(item.disposition is StaticRouteSampleDisposition.COLLISION for item in all_pose_results):
        status = StaticRouteCollisionStatus.COLLISION_DETECTED
    elif any(
        item.disposition is StaticRouteSampleDisposition.REQUIRED_CONTACT_MISSING
        for item in all_pose_results
    ):
        status = StaticRouteCollisionStatus.CONTACT_OVERLAP_MISSING
    else:
        status = StaticRouteCollisionStatus.PASS_DIAGNOSTIC_ONLY
    return StaticRouteCollisionReport(
        status=status,
        contract=contract,
        route=route,
        policy=policy,
        geometry_audit=audit,
        blockers=blockers,
        phase_results=tuple(phase_results),
        segment_results=tuple(segment_results),
    )


__all__ = [
    "AMBIENT_LIGHT_ABSENT_BODY_IDS",
    "AMBIENT_LIGHT_STATIC_ROUTE_BODY_REQUIREMENTS",
    "MAX_STATIC_ROUTE_BODIES",
    "MAX_STATIC_ROUTE_PHASE_POSES",
    "MAX_STATIC_ROUTE_SAMPLES_PER_SEGMENT",
    "MAX_STATIC_ROUTE_SEGMENTS",
    "MAX_STATIC_ROUTE_SOURCE_HASHES",
    "MAX_STATIC_ROUTE_TOTAL_INTERMEDIATE_SAMPLES",
    "REQUIRED_STATIC_ROUTE_PHASES",
    "REQUIRED_STATIC_ROUTE_SOURCE_KEYS",
    "STATIC_B0477_ROUTE_CONTRACT_SCHEMA",
    "STATIC_B0477_ROUTE_REPORT_SCHEMA",
    "STATIC_B0477_ROUTE_SCHEMA",
    "STATIC_B0477_TARGET_BINDING_SCHEMA",
    "STATIC_B0477_LEGACY_BODY_MIGRATION",
    "STATIC_ROUTE_BODY_REQUIREMENTS",
    "StaticB0477RouteCollisionContract",
    "StaticRouteBody",
    "StaticRouteBodyRequirement",
    "StaticRouteBodyRole",
    "StaticRouteCollisionError",
    "StaticRouteCollisionPolicy",
    "StaticRouteCollisionReport",
    "StaticRouteCollisionStatus",
    "StaticRouteGeometryProvenance",
    "StaticRouteIntermediateSample",
    "StaticRoutePhase",
    "StaticRoutePhasePose",
    "StaticRoutePhaseResult",
    "StaticRoutePoseResult",
    "StaticRouteSampleDisposition",
    "StaticRouteSegment",
    "StaticRouteSegmentResult",
    "StaticRouteSegmentSampleResult",
    "StaticRouteSourceBinding",
    "StaticRouteTargetBinding",
    "StaticTargetRoute",
    "bind_static_route_target",
    "build_static_b0477_prehardware_collision_contract",
    "build_ambient_light_b0477_prehardware_collision_contract",
    "evaluate_static_b0477_target_route",
]
