"""Strict, zero-authority v2 AI-to-arm proposal contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from .frames import Point3Mm
from .motion_proposal import Interaction, ProposalDevice, ProposalFrame

BATCH_SCHEMA = "rocell.model_motion_batch.v2"
PROPOSAL_SCHEMA = "rocell.model_motion_proposal.v2"
COORDINATE_PROFILE_V2 = "board_mm_xy_plane_v2"
MAX_BATCH_PROPOSALS_V2 = 64
MAX_BATCH_BYTES_V2 = 1_048_576
MAX_BATCH_JSON_DEPTH_V2 = 32
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PROFILE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class ModelMotionBatchV2Error(ValueError):
    """A v2 proposal is malformed, ambiguous, or unbound."""


class UncertaintyBoundType(str, Enum):
    PLANAR_L2_DISK = "planar_l2_disk"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ModelMotionBatchV2Error("value is not canonical JSON") from exc


def _strict(value: object, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ModelMotionBatchV2Error(f"{label} must contain exactly {sorted(fields)}")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ModelMotionBatchV2Error(f"{label} must be a bounded identifier")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ModelMotionBatchV2Error(f"{label} must be a lowercase SHA-256 digest")
    return value


def _number(value: object, label: str, *, minimum: float | None = None,
            maximum: float | None = None, exclusive_minimum: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelMotionBatchV2Error(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ModelMotionBatchV2Error(f"{label} must be finite")
    if minimum is not None and (result < minimum or
                                (exclusive_minimum and result == minimum)):
        raise ModelMotionBatchV2Error(f"{label} is below its minimum")
    if maximum is not None and result > maximum:
        raise ModelMotionBatchV2Error(f"{label} exceeds its maximum")
    return result


def _epoch_ms(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ModelMotionBatchV2Error(f"{label} must be a positive integer epoch-ms")
    return value


@dataclass(frozen=True, slots=True)
class MotionCapabilityV2:
    profile_id: str
    profile_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or (
            _PROFILE_IDENTIFIER.fullmatch(self.profile_id) is None
        ):
            raise ModelMotionBatchV2Error(
                "capability.profile_id must be a bounded profile identifier")
        _digest(self.profile_sha256, "capability.profile_sha256")

    def to_dict(self) -> dict[str, str]:
        return {"profile_id": self.profile_id, "profile_sha256": self.profile_sha256}

    @classmethod
    def from_mapping(cls, value: object) -> "MotionCapabilityV2":
        item = _strict(value, {"profile_id", "profile_sha256"}, "capability")
        return cls(item["profile_id"], item["profile_sha256"])


@dataclass(frozen=True, slots=True)
class MotionGeometryV2:
    coordinate_profile: str
    coordinate_units: str
    board_frame_definition_sha256: str
    placement_observation_sha256: str
    target_catalog_sha256: str

    def __post_init__(self) -> None:
        if self.coordinate_profile != COORDINATE_PROFILE_V2:
            raise ModelMotionBatchV2Error("unsupported coordinate profile")
        if self.coordinate_units != "mm":
            raise ModelMotionBatchV2Error("v2 coordinate units must be mm")
        for field in ("board_frame_definition_sha256",
                      "placement_observation_sha256", "target_catalog_sha256"):
            _digest(getattr(self, field), f"geometry.{field}")

    def to_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in (
            "coordinate_profile", "coordinate_units", "board_frame_definition_sha256",
            "placement_observation_sha256", "target_catalog_sha256")}

    @classmethod
    def from_mapping(cls, value: object) -> "MotionGeometryV2":
        fields = {"coordinate_profile", "coordinate_units",
                  "board_frame_definition_sha256", "placement_observation_sha256",
                  "target_catalog_sha256"}
        item = _strict(value, fields, "geometry")
        return cls(**{field: item[field] for field in fields})


@dataclass(frozen=True, slots=True)
class MotionEvidenceV2:
    capture_id: str
    frame_id: str
    image_sha256: str
    camera_identity_sha256: str
    capture_clock_domain_id: str
    model_id: str
    model_sha256: str
    scene_observation_sha256: str
    precision_observation_sha256: str
    fusion_decision_sha256: str
    scene_lease_id: str
    scene_lease_issuer_id: str
    scene_lease_sha256: str
    captured_at_epoch_ms: int
    evaluated_at_epoch_ms: int
    expires_at_epoch_ms: int

    def __post_init__(self) -> None:
        for field in ("capture_id", "frame_id", "capture_clock_domain_id", "model_id",
                      "scene_lease_id", "scene_lease_issuer_id"):
            _identifier(getattr(self, field), f"evidence.{field}")
        for field in ("image_sha256", "camera_identity_sha256", "model_sha256",
                      "scene_observation_sha256", "precision_observation_sha256",
                      "fusion_decision_sha256", "scene_lease_sha256"):
            _digest(getattr(self, field), f"evidence.{field}")
        captured = _epoch_ms(self.captured_at_epoch_ms, "captured_at_epoch_ms")
        evaluated = _epoch_ms(self.evaluated_at_epoch_ms, "evaluated_at_epoch_ms")
        expires = _epoch_ms(self.expires_at_epoch_ms, "expires_at_epoch_ms")
        if not captured <= evaluated < expires:
            raise ModelMotionBatchV2Error(
                "observation times must satisfy captured <= evaluated < expires")

    def to_dict(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}

    @classmethod
    def from_mapping(cls, value: object) -> "MotionEvidenceV2":
        fields = set(cls.__dataclass_fields__)
        item = _strict(value, fields, "evidence")
        return cls(**{field: item[field] for field in fields})


@dataclass(frozen=True, slots=True)
class MotionUncertaintyV2:
    bound_type: UncertaintyBoundType
    error_bound_mm: float
    coverage_probability: float
    qualification_sha256: str
    evidence_method_sha256: str
    domain_id: str
    covered_target_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "bound_type", UncertaintyBoundType(self.bound_type))
        except ValueError as exc:
            raise ModelMotionBatchV2Error(str(exc)) from exc
        object.__setattr__(self, "error_bound_mm", _number(
            self.error_bound_mm, "uncertainty.error_bound_mm", minimum=0.0,
            maximum=100.0, exclusive_minimum=True))
        object.__setattr__(self, "coverage_probability", _number(
            self.coverage_probability, "uncertainty.coverage_probability",
            minimum=0.0, maximum=1.0, exclusive_minimum=True))
        _digest(self.qualification_sha256, "uncertainty.qualification_sha256")
        _digest(self.evidence_method_sha256, "uncertainty.evidence_method_sha256")
        _identifier(self.domain_id, "uncertainty.domain_id")
        targets = tuple(_identifier(item, "covered_target_id") for item in self.covered_target_ids)
        if not targets or len(targets) != len(set(targets)):
            raise ModelMotionBatchV2Error("covered target ids must be nonempty and unique")
        object.__setattr__(self, "covered_target_ids", targets)

    def to_dict(self) -> dict[str, object]:
        return {"bound_type": self.bound_type.value, "error_bound_mm": self.error_bound_mm,
                "coverage_probability": self.coverage_probability,
                "qualification_sha256": self.qualification_sha256,
                "evidence_method_sha256": self.evidence_method_sha256,
                "domain_id": self.domain_id,
                "covered_target_ids": list(self.covered_target_ids)}

    @classmethod
    def from_mapping(cls, value: object) -> "MotionUncertaintyV2":
        fields = {"bound_type", "error_bound_mm", "coverage_probability",
                  "qualification_sha256", "evidence_method_sha256", "domain_id",
                  "covered_target_ids"}
        item = _strict(value, fields, "uncertainty")
        if not isinstance(item["covered_target_ids"], list):
            raise ModelMotionBatchV2Error("covered_target_ids must be an array")
        return cls(bound_type=item["bound_type"], error_bound_mm=item["error_bound_mm"],
                   coverage_probability=item["coverage_probability"],
                   qualification_sha256=item["qualification_sha256"],
                   evidence_method_sha256=item["evidence_method_sha256"],
                   domain_id=item["domain_id"],
                   covered_target_ids=tuple(item["covered_target_ids"]))


@dataclass(frozen=True, slots=True)
class ModelMotionProposalV2:
    proposal_id: str
    action_index: int
    device: ProposalDevice
    target_id: str
    target: Point3Mm
    interaction: Interaction
    observation_confidence: float
    schema: str = PROPOSAL_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != PROPOSAL_SCHEMA:
            raise ModelMotionBatchV2Error("unsupported v2 proposal schema")
        _identifier(self.proposal_id, "proposal_id")
        _identifier(self.target_id, "target_id")
        if isinstance(self.action_index, bool) or not isinstance(self.action_index, int) \
                or not 0 <= self.action_index < MAX_BATCH_PROPOSALS_V2:
            raise ModelMotionBatchV2Error("action_index must be an integer in [0, 63]")
        try:
            object.__setattr__(self, "device", ProposalDevice(self.device))
            object.__setattr__(self, "interaction", Interaction(self.interaction))
        except ValueError as exc:
            raise ModelMotionBatchV2Error(str(exc)) from exc
        if not isinstance(self.target, Point3Mm) or self.target.frame != ProposalFrame.BOARD.value:
            raise ModelMotionBatchV2Error("v2 target must use the board frame")
        object.__setattr__(self, "observation_confidence", _number(
            self.observation_confidence, "observation_confidence", minimum=0.0, maximum=1.0))

    def to_dict(self) -> dict[str, object]:
        return {"schema": self.schema, "proposal_id": self.proposal_id,
                "action_index": self.action_index, "device": self.device.value,
                "target_id": self.target_id, "coordinate_frame": self.target.frame,
                "target_mm": {"x": self.target.x, "y": self.target.y, "z": self.target.z},
                "interaction": self.interaction.value,
                "observation_confidence": self.observation_confidence}

    @classmethod
    def from_mapping(cls, value: object) -> "ModelMotionProposalV2":
        fields = {"schema", "proposal_id", "action_index", "device", "target_id",
                  "coordinate_frame", "target_mm", "interaction", "observation_confidence"}
        item = _strict(value, fields, "proposal")
        point = _strict(item["target_mm"], {"x", "y", "z"}, "target_mm")
        return cls(schema=item["schema"], proposal_id=item["proposal_id"],
                   action_index=item["action_index"], device=item["device"],
                   target_id=item["target_id"],
                   target=Point3Mm(_identifier(item["coordinate_frame"], "coordinate_frame"),
                                  point["x"], point["y"], point["z"]),
                   interaction=item["interaction"],
                   observation_confidence=item["observation_confidence"])

    @property
    def proposal_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class ModelMotionBatchV2:
    batch_id: str
    request_id: str
    intent_plan_sha256: str
    device: ProposalDevice
    capability: MotionCapabilityV2
    geometry: MotionGeometryV2
    evidence: MotionEvidenceV2
    uncertainty: MotionUncertaintyV2
    proposals: tuple[ModelMotionProposalV2, ...]
    schema: str = BATCH_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != BATCH_SCHEMA:
            raise ModelMotionBatchV2Error("unsupported v2 batch schema")
        _identifier(self.batch_id, "batch_id")
        _identifier(self.request_id, "request_id")
        _digest(self.intent_plan_sha256, "intent_plan_sha256")
        try:
            object.__setattr__(self, "device", ProposalDevice(self.device))
        except ValueError as exc:
            raise ModelMotionBatchV2Error(str(exc)) from exc
        if not isinstance(self.capability, MotionCapabilityV2) \
                or not isinstance(self.geometry, MotionGeometryV2) \
                or not isinstance(self.evidence, MotionEvidenceV2) \
                or not isinstance(self.uncertainty, MotionUncertaintyV2):
            raise ModelMotionBatchV2Error("invalid v2 semantic group")
        if self.geometry.placement_observation_sha256 == self.evidence.precision_observation_sha256:
            raise ModelMotionBatchV2Error("placement must be independent of precision evidence")
        proposals = tuple(self.proposals)
        if not 1 <= len(proposals) <= MAX_BATCH_PROPOSALS_V2:
            raise ModelMotionBatchV2Error("v2 proposals must contain 1 to 64 items")
        if any(not isinstance(item, ModelMotionProposalV2) for item in proposals):
            raise ModelMotionBatchV2Error("v2 proposals contain an invalid item")
        ids = [item.proposal_id for item in proposals]
        if len(ids) != len(set(ids)):
            raise ModelMotionBatchV2Error("proposal ids must be unique")
        if any(item.device is not self.device for item in proposals):
            raise ModelMotionBatchV2Error("proposal device differs from batch")
        if tuple(item.action_index for item in proposals) != tuple(range(len(proposals))):
            raise ModelMotionBatchV2Error("action indexes must be ordered and contiguous")
        object.__setattr__(self, "proposals", proposals)

    def unsigned_dict(self) -> dict[str, object]:
        return {"schema": self.schema, "batch_id": self.batch_id,
                "request_id": self.request_id, "intent_plan_sha256": self.intent_plan_sha256,
                "device": self.device.value, "capability": self.capability.to_dict(),
                "geometry": self.geometry.to_dict(), "evidence": self.evidence.to_dict(),
                "uncertainty": self.uncertainty.to_dict(),
                "proposals": [item.to_dict() for item in self.proposals],
                "controller_commands": [], "hardware_access": False,
                "physical_authority": False}

    @property
    def batch_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.unsigned_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "batch_sha256": self.batch_sha256}

    @classmethod
    def from_mapping(cls, value: object) -> "ModelMotionBatchV2":
        fields = {"schema", "batch_id", "request_id", "intent_plan_sha256", "device",
                  "capability", "geometry", "evidence", "uncertainty", "proposals",
                  "controller_commands", "hardware_access", "physical_authority",
                  "batch_sha256"}
        item = _strict(value, fields, "v2 batch")
        if item["controller_commands"] != [] or item["hardware_access"] is not False \
                or item["physical_authority"] is not False:
            raise ModelMotionBatchV2Error("v2 batch violates zero authority")
        raw = item["proposals"]
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ModelMotionBatchV2Error("proposals must be an array")
        batch = cls(schema=item["schema"], batch_id=item["batch_id"],
                    request_id=item["request_id"],
                    intent_plan_sha256=item["intent_plan_sha256"], device=item["device"],
                    capability=MotionCapabilityV2.from_mapping(item["capability"]),
                    geometry=MotionGeometryV2.from_mapping(item["geometry"]),
                    evidence=MotionEvidenceV2.from_mapping(item["evidence"]),
                    uncertainty=MotionUncertaintyV2.from_mapping(item["uncertainty"]),
                    proposals=tuple(ModelMotionProposalV2.from_mapping(x) for x in raw))
        if _digest(item["batch_sha256"], "batch_sha256") != batch.batch_sha256:
            raise ModelMotionBatchV2Error("batch_sha256 does not match v2 content")
        return batch


def decode_model_motion_batch_v2_json(payload: bytes) -> ModelMotionBatchV2:
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if not payload or len(payload) > MAX_BATCH_BYTES_V2:
        raise ModelMotionBatchV2Error("v2 payload is empty or oversized")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ModelMotionBatchV2Error(f"duplicate JSON field {key!r}")
            result[key] = item
        return result
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=unique,
                           parse_constant=lambda item: (_ for _ in ()).throw(
                               ModelMotionBatchV2Error(f"non-finite JSON constant {item!r}")))
    except RecursionError as exc:
        raise ModelMotionBatchV2Error("v2 payload exceeds JSON depth limit") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelMotionBatchV2Error("v2 payload is not strict UTF-8 JSON") from exc
    stack: list[tuple[object, int]] = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if depth > MAX_BATCH_JSON_DEPTH_V2:
            raise ModelMotionBatchV2Error("v2 payload exceeds JSON depth limit")
        if isinstance(item, Mapping):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
    return ModelMotionBatchV2.from_mapping(value)


__all__ = ["BATCH_SCHEMA", "PROPOSAL_SCHEMA", "COORDINATE_PROFILE_V2",
           "MAX_BATCH_BYTES_V2", "MAX_BATCH_JSON_DEPTH_V2",
           "MAX_BATCH_PROPOSALS_V2", "ModelMotionBatchV2",
           "ModelMotionBatchV2Error", "ModelMotionProposalV2", "MotionCapabilityV2",
           "MotionEvidenceV2", "MotionGeometryV2", "MotionUncertaintyV2",
           "UncertaintyBoundType", "decode_model_motion_batch_v2_json"]
