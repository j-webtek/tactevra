"""Fail-closed, side-effect-free arm admission for v2 model batches."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping

from rocell.models import (ActionPlan, Interaction, ModelMotionBatchV2, PressKey,
                           TapPhoneTarget, UncertaintyBoundType, VerifyPhoneState)
from .context import (
    SimulationContext,
    SimulationContextValidationLeaseV1,
    revalidate_simulation_context,
)

SCHEMA = "rocell.model_motion_ingress.v2"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PROFILE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class ModelMotionIngressV2Error(ValueError):
    """A v2 model batch cannot enter deterministic arm planning."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ModelMotionIngressV2Error(f"{label} must be a SHA-256 digest")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ModelMotionIngressV2Error(f"{label} must be a bounded identifier")
    return value


def _profile_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _PROFILE_IDENTIFIER.fullmatch(value) is None:
        raise ModelMotionIngressV2Error(
            f"{label} must be a bounded profile identifier")
    return value


def _finite(value: object, label: str, *, nonnegative: bool = False,
            positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelMotionIngressV2Error(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0.0) \
            or (positive and result <= 0.0):
        raise ModelMotionIngressV2Error(f"{label} must be finite and valid")
    return result


@dataclass(frozen=True, slots=True)
class TrustedLocalizationQualificationV2:
    qualification_sha256: str
    model_id: str
    model_sha256: str
    evidence_method_sha256: str
    domain_id: str
    target_catalog_sha256: str
    bound_type: UncertaintyBoundType
    error_bound_mm: float
    coverage_probability: float
    target_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("qualification_sha256", "model_sha256", "evidence_method_sha256",
                      "target_catalog_sha256"):
            _digest(getattr(self, field), field)
        _identifier(self.model_id, "model_id")
        _identifier(self.domain_id, "domain_id")
        try:
            object.__setattr__(self, "bound_type", UncertaintyBoundType(self.bound_type))
        except ValueError as exc:
            raise ModelMotionIngressV2Error(str(exc)) from exc
        object.__setattr__(self, "error_bound_mm",
                           _finite(self.error_bound_mm, "error_bound_mm", positive=True))
        coverage = _finite(self.coverage_probability, "coverage_probability", positive=True)
        if coverage > 1.0:
            raise ModelMotionIngressV2Error("coverage_probability must not exceed 1")
        object.__setattr__(self, "coverage_probability", coverage)
        targets = tuple(_identifier(item, "target_id") for item in self.target_ids)
        if not targets or len(targets) != len(set(targets)):
            raise ModelMotionIngressV2Error("qualification target ids must be unique")
        object.__setattr__(self, "target_ids", targets)


@dataclass(frozen=True, slots=True)
class MeasuredTargetRegionV2:
    target_id: str
    coordinate_frame: str
    coordinate_profile: str
    board_frame_definition_sha256: str
    vertices_xy_mm: tuple[tuple[float, float], ...]
    surface_z_mm: float
    surface_normal_error_bound_mm: float
    placement_error_bound_mm: float
    placement_observation_sha256: str
    target_catalog_sha256: str

    def __post_init__(self) -> None:
        _identifier(self.target_id, "target_id")
        _identifier(self.coordinate_frame, "coordinate_frame")
        _identifier(self.coordinate_profile, "coordinate_profile")
        for field in ("board_frame_definition_sha256", "placement_observation_sha256",
                      "target_catalog_sha256"):
            _digest(getattr(self, field), field)
        object.__setattr__(self, "surface_z_mm", _finite(self.surface_z_mm, "surface_z_mm"))
        for field in ("surface_normal_error_bound_mm", "placement_error_bound_mm"):
            object.__setattr__(self, field, _finite(getattr(self, field), field,
                                                   nonnegative=True))
        vertices = tuple((_finite(v[0], "vertex.x"), _finite(v[1], "vertex.y"))
                         for v in self.vertices_xy_mm)
        if len(vertices) < 3 or len(set(vertices)) != len(vertices):
            raise ModelMotionIngressV2Error("target region needs unique polygon vertices")
        signs = []
        for index in range(len(vertices)):
            a, b, c = vertices[index], vertices[(index + 1) % len(vertices)], \
                      vertices[(index + 2) % len(vertices)]
            cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if abs(cross) <= 1e-12:
                raise ModelMotionIngressV2Error("target region has a degenerate edge")
            signs.append(cross > 0.0)
        if len(set(signs)) != 1:
            raise ModelMotionIngressV2Error("target region must be strictly convex")
        object.__setattr__(self, "vertices_xy_mm", vertices)

    def to_dict(self) -> dict[str, object]:
        return {field: ([list(v) for v in self.vertices_xy_mm]
                        if field == "vertices_xy_mm" else getattr(self, field))
                for field in self.__dataclass_fields__}

    @property
    def region_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()

    def contains_disk(self, x: float, y: float, radius: float) -> bool:
        a, b, c = self.vertices_xy_mm[:3]
        orientation = 1.0 if ((b[0] - a[0]) * (c[1] - b[1]) -
                              (b[1] - a[1]) * (c[0] - b[0])) > 0 else -1.0
        for index, left in enumerate(self.vertices_xy_mm):
            right = self.vertices_xy_mm[(index + 1) % len(self.vertices_xy_mm)]
            dx, dy = right[0] - left[0], right[1] - left[1]
            distance = orientation * (dx * (y - left[1]) - dy * (x - left[0]))
            if distance / math.hypot(dx, dy) + 1e-12 < radius:
                return False
        return True


def _movement_targets(plan: ActionPlan) -> tuple[str, ...]:
    result = []
    for action in plan.actions:
        if isinstance(action, PressKey):
            result.append(action.key_id)
        elif isinstance(action, TapPhoneTarget):
            result.append(action.target_id)
        elif not isinstance(action, VerifyPhoneState):
            raise ModelMotionIngressV2Error("unsupported semantic action")
    return tuple(result)


def ingest_model_motion_batch_v2(
    batch: ModelMotionBatchV2, plan: ActionPlan, context: SimulationContext, *,
    current_time_epoch_ms: int, current_monotonic_ns: int,
    maximum_scene_age_ms: int, trusted_scene_lease_expires_at_epoch_ms: int,
    expected_capability_profile_id: str, expected_capability_profile_sha256: str,
    expected_capture_id: str, expected_frame_id: str, expected_image_sha256: str,
    expected_capture_clock_domain_id: str, expected_camera_identity_sha256: str,
    expected_scene_lease_id: str, expected_scene_lease_issuer_id: str,
    expected_scene_lease_sha256: str, expected_scene_observation_sha256: str,
    expected_precision_observation_sha256: str,
    expected_fusion_decision_sha256: str,
    expected_placement_observation_sha256: str,
    expected_board_frame_definition_sha256: str,
    trusted_qualification: TrustedLocalizationQualificationV2,
    measured_target_regions: Mapping[str, MeasuredTargetRegionV2],
    minimum_observation_confidence: float = 0.9,
    maximum_surface_normal_error_mm: float = 0.5,
    context_validation_lease: SimulationContextValidationLeaseV1 | None = None,
    active_context_epoch_sha256: str | None = None,
    active_service_instance_id: str | None = None,
    active_context_generation: int | None = None,
) -> dict[str, Any]:
    """Admit a v2 batch without generating commands or touching hardware."""
    if not isinstance(batch, ModelMotionBatchV2) or not isinstance(plan, ActionPlan) \
            or not isinstance(context, SimulationContext):
        raise TypeError("batch, plan, or context has the wrong type")
    revalidate_simulation_context(
        context, lease=context_validation_lease,
        active_context_epoch_sha256=active_context_epoch_sha256,
        active_service_instance_id=active_service_instance_id,
        active_generation=active_context_generation,
    )
    if batch.capability.profile_id != _profile_identifier(
            expected_capability_profile_id, "profile") \
            or batch.capability.profile_sha256 != _digest(
                expected_capability_profile_sha256, "profile hash") \
            or plan.profile_id != expected_capability_profile_id:
        raise ModelMotionIngressV2Error("capability profile binding differs")
    if batch.intent_plan_sha256 != plan.plan_hash or batch.device.value != plan.device.value:
        raise ModelMotionIngressV2Error("batch differs from the semantic plan")
    expected_targets = _movement_targets(plan)
    actual_targets = tuple(item.target_id for item in batch.proposals)
    if actual_targets != expected_targets:
        raise ModelMotionIngressV2Error("proposal target order differs from plan")
    if any(item.action_index != index for index, item in enumerate(batch.proposals)):
        raise ModelMotionIngressV2Error("proposal action index differs from plan")
    if any(item.interaction is not Interaction.CONTACT for item in batch.proposals):
        raise ModelMotionIngressV2Error("typing proposals must request CONTACT")

    evidence_expected = {
        "capture_id": _identifier(expected_capture_id, "capture id"),
        "frame_id": _identifier(expected_frame_id, "frame id"),
        "image_sha256": _digest(expected_image_sha256, "image"),
        "capture_clock_domain_id": _identifier(expected_capture_clock_domain_id, "clock"),
        "camera_identity_sha256": _digest(expected_camera_identity_sha256, "camera"),
        "scene_lease_id": _identifier(expected_scene_lease_id, "lease"),
        "scene_lease_issuer_id": _identifier(expected_scene_lease_issuer_id, "issuer"),
        "scene_lease_sha256": _digest(expected_scene_lease_sha256, "lease hash"),
        "scene_observation_sha256": _digest(expected_scene_observation_sha256, "scene"),
        "precision_observation_sha256": _digest(expected_precision_observation_sha256,
                                                 "precision"),
        "fusion_decision_sha256": _digest(expected_fusion_decision_sha256, "fusion"),
    }
    for field, expected in evidence_expected.items():
        if getattr(batch.evidence, field) != expected:
            raise ModelMotionIngressV2Error(f"batch {field} differs from trusted evidence")
    geometry = batch.geometry
    if geometry.placement_observation_sha256 != _digest(
            expected_placement_observation_sha256, "placement") \
            or geometry.board_frame_definition_sha256 != _digest(
                expected_board_frame_definition_sha256, "board frame") \
            or geometry.target_catalog_sha256 != context.targets.content_sha256:
        raise ModelMotionIngressV2Error("batch geometry binding differs")

    for value, label in ((current_time_epoch_ms, "current_time_epoch_ms"),
                         (current_monotonic_ns, "current_monotonic_ns"),
                         (maximum_scene_age_ms, "maximum_scene_age_ms"),
                         (trusted_scene_lease_expires_at_epoch_ms, "trusted lease expiry")):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ModelMotionIngressV2Error(f"{label} must be a positive integer")
    evidence = batch.evidence
    if not evidence.captured_at_epoch_ms <= evidence.evaluated_at_epoch_ms \
            <= current_time_epoch_ms < evidence.expires_at_epoch_ms:
        raise ModelMotionIngressV2Error("batch evidence is future-dated or expired")
    if current_time_epoch_ms - evidence.captured_at_epoch_ms > maximum_scene_age_ms:
        raise ModelMotionIngressV2Error("batch evidence exceeds maximum scene age")
    if evidence.expires_at_epoch_ms > trusted_scene_lease_expires_at_epoch_ms \
            or current_time_epoch_ms >= trusted_scene_lease_expires_at_epoch_ms:
        raise ModelMotionIngressV2Error("batch exceeds trusted scene lease")
    deadline_ms = min(evidence.expires_at_epoch_ms,
                      trusted_scene_lease_expires_at_epoch_ms) - current_time_epoch_ms
    valid_until_monotonic_ns = current_monotonic_ns + deadline_ms * 1_000_000

    uncertainty, qualification = batch.uncertainty, trusted_qualification
    if (uncertainty.qualification_sha256 != qualification.qualification_sha256
            or uncertainty.evidence_method_sha256 != qualification.evidence_method_sha256
            or evidence.model_id != qualification.model_id
            or evidence.model_sha256 != qualification.model_sha256
            or uncertainty.domain_id != qualification.domain_id
            or geometry.target_catalog_sha256 != qualification.target_catalog_sha256
            or uncertainty.bound_type is not qualification.bound_type
            or uncertainty.error_bound_mm != qualification.error_bound_mm
            or uncertainty.coverage_probability != qualification.coverage_probability
            or uncertainty.covered_target_ids != qualification.target_ids):
        raise ModelMotionIngressV2Error("batch uncertainty differs from qualification")

    minimum = _finite(minimum_observation_confidence, "minimum confidence")
    normal_limit = _finite(maximum_surface_normal_error_mm, "normal error",
                           nonnegative=True)
    if not 0 <= minimum <= 1:
        raise ModelMotionIngressV2Error("minimum confidence must be in [0, 1]")
    admitted = []
    for index, proposal in enumerate(batch.proposals):
        if proposal.target_id not in qualification.target_ids:
            raise ModelMotionIngressV2Error(f"proposal {index} target is unqualified")
        if proposal.observation_confidence < minimum:
            raise ModelMotionIngressV2Error(f"proposal {index} confidence is below policy")
        region = measured_target_regions.get(proposal.target_id)
        if not isinstance(region, MeasuredTargetRegionV2):
            raise ModelMotionIngressV2Error(f"proposal {index} lacks measured region")
        if (region.target_id != proposal.target_id or region.coordinate_frame != "board"
                or region.coordinate_profile != geometry.coordinate_profile
                or region.board_frame_definition_sha256
                != geometry.board_frame_definition_sha256
                or region.placement_observation_sha256
                != geometry.placement_observation_sha256
                or region.target_catalog_sha256 != geometry.target_catalog_sha256):
            raise ModelMotionIngressV2Error(f"proposal {index} region binding differs")
        if region.surface_normal_error_bound_mm > normal_limit \
                or abs(proposal.target.z - region.surface_z_mm) \
                + region.surface_normal_error_bound_mm > normal_limit:
            raise ModelMotionIngressV2Error(f"proposal {index} surface plane is unqualified")
        composed = uncertainty.error_bound_mm + region.placement_error_bound_mm
        if not region.contains_disk(proposal.target.x, proposal.target.y, composed):
            raise ModelMotionIngressV2Error(
                f"proposal {index} composed uncertainty leaves measured region")
        admitted.append({"action_index": index, "proposal_id": proposal.proposal_id,
                         "proposal_sha256": proposal.proposal_sha256,
                         "target_id": proposal.target_id,
                         "observation_confidence": proposal.observation_confidence,
                         "model_error_bound_mm": uncertainty.error_bound_mm,
                         "placement_error_bound_mm": region.placement_error_bound_mm,
                         "composed_planar_error_bound_mm": composed,
                         "measured_target_region_sha256": region.region_sha256})

    report = {"schema": SCHEMA,
              "status": "ACCEPTED_V2_FOR_FRESH_SEQUENTIAL_PLANNER_GATES",
              "batch_sha256": batch.batch_sha256,
              "intent_plan_sha256": plan.plan_hash, "request_id": batch.request_id,
              "capability": batch.capability.to_dict(),
              "coordinate_profile": geometry.coordinate_profile,
              "scene_lease_id": evidence.scene_lease_id,
              "scene_lease_sha256": evidence.scene_lease_sha256,
              "expires_at_epoch_ms": evidence.expires_at_epoch_ms,
              "valid_until_monotonic_ns": valid_until_monotonic_ns,
              "qualification_sha256": qualification.qualification_sha256,
              "placement_observation_sha256": geometry.placement_observation_sha256,
              "target_catalog_sha256": geometry.target_catalog_sha256,
              "ordered_target_ids": list(actual_targets), "admitted_actions": admitted,
              "next_required_stage": "FRESH_STATE_AND_MEASURED_SEQUENTIAL_PLANNER_GATE",
              "controller_commands": [], "hardware_commands_generated": 0,
              "hardware_access": False, "physical_authority": False}
    return {**report, "ingress_sha256": hashlib.sha256(_canonical(report)).hexdigest()}


def revalidate_model_motion_ingress_v2(
    ingress: Mapping[str, Any], *, current_monotonic_ns: int,
    expected_capability_profile_sha256: str,
    active_scene_lease_sha256: str,
    active_placement_observation_sha256: str,
    active_target_catalog_sha256: str,
) -> dict[str, Any]:
    """Recheck one admitted batch immediately before deterministic planning.

    This check deliberately uses the monotonic deadline derived at ingress. It
    cannot extend a lease after a wall-clock rollback and still emits no route,
    controller command, or physical authority.
    """
    if not isinstance(ingress, Mapping):
        raise TypeError("ingress must be a mapping")
    if ingress.get("schema") != SCHEMA or ingress.get("status") != \
            "ACCEPTED_V2_FOR_FRESH_SEQUENTIAL_PLANNER_GATES":
        raise ModelMotionIngressV2Error("ingress is not an accepted v2 record")
    if ingress.get("hardware_access") is not False \
            or ingress.get("physical_authority") is not False \
            or ingress.get("controller_commands") != []:
        raise ModelMotionIngressV2Error("ingress violates zero authority")
    claimed = ingress.get("ingress_sha256")
    unsigned = {key: value for key, value in ingress.items() if key != "ingress_sha256"}
    if not isinstance(claimed, str) or hashlib.sha256(_canonical(unsigned)).hexdigest() != claimed:
        raise ModelMotionIngressV2Error("ingress_sha256 does not match content")
    deadline = ingress.get("valid_until_monotonic_ns")
    if isinstance(current_monotonic_ns, bool) or not isinstance(current_monotonic_ns, int) \
            or current_monotonic_ns <= 0 or isinstance(deadline, bool) \
            or not isinstance(deadline, int):
        raise ModelMotionIngressV2Error("monotonic time is invalid")
    if current_monotonic_ns >= deadline:
        raise ModelMotionIngressV2Error("ingress lease expired before planning")
    capability = ingress.get("capability")
    if not isinstance(capability, Mapping) or capability.get("profile_sha256") != _digest(
            expected_capability_profile_sha256, "capability hash"):
        raise ModelMotionIngressV2Error("capability was changed or revoked")
    active = {
        "scene_lease_sha256": _digest(active_scene_lease_sha256, "scene lease hash"),
        "placement_observation_sha256": _digest(
            active_placement_observation_sha256, "placement hash"),
        "target_catalog_sha256": _digest(active_target_catalog_sha256, "target map hash"),
    }
    for field, expected in active.items():
        if ingress.get(field) != expected:
            raise ModelMotionIngressV2Error(f"{field} was changed or revoked")
    report = {
        "schema": "rocell.model_motion_preplanner_gate.v2",
        "status": "FRESH_FOR_DETERMINISTIC_PLANNING",
        "ingress_sha256": claimed,
        "batch_sha256": ingress.get("batch_sha256"),
        "checked_at_monotonic_ns": current_monotonic_ns,
        "valid_until_monotonic_ns": deadline,
        "controller_commands": [], "hardware_access": False,
        "physical_authority": False,
    }
    return {**report, "preplanner_gate_sha256": hashlib.sha256(
        _canonical(report)).hexdigest()}


__all__ = ["SCHEMA", "MeasuredTargetRegionV2", "ModelMotionIngressV2Error",
           "TrustedLocalizationQualificationV2", "ingest_model_motion_batch_v2",
           "revalidate_model_motion_ingress_v2"]
