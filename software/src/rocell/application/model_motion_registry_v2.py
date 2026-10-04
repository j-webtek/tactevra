"""Consumer-owned trusted registry snapshot for model-motion v2 admission.

The model never constructs this object. Commissioning/capture services resolve
their signed or content-addressed records first, then the arm runtime freezes the
identities into this immutable snapshot for one admission/revalidation window.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from rocell.models import ActionPlan, ModelMotionBatchV2
from .context import SimulationContext, SimulationContextValidationLeaseV1
from .context_lifecycle_v1 import SimulationContextLifecycleV1
from .model_motion_ingress_v2 import (
    MeasuredTargetRegionV2, ModelMotionIngressV2Error,
    TrustedLocalizationQualificationV2, ingest_model_motion_batch_v2,
    revalidate_model_motion_ingress_v2)


@dataclass(frozen=True, slots=True)
class TrustedMotionRegistryV2:
    """Exact active arm-side identities; never populated from model output."""

    capability_profile_id: str
    capability_profile_sha256: str
    capture_id: str
    frame_id: str
    image_sha256: str
    capture_clock_domain_id: str
    camera_identity_sha256: str
    scene_lease_id: str
    scene_lease_issuer_id: str
    scene_lease_sha256: str
    scene_lease_expires_at_epoch_ms: int
    scene_observation_sha256: str
    precision_observation_sha256: str
    fusion_decision_sha256: str
    placement_observation_sha256: str
    board_frame_definition_sha256: str
    target_catalog_sha256: str
    maximum_scene_age_ms: int
    minimum_observation_confidence: float
    maximum_surface_normal_error_mm: float
    qualification: TrustedLocalizationQualificationV2
    target_regions: tuple[MeasuredTargetRegionV2, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.qualification, TrustedLocalizationQualificationV2):
            raise ModelMotionIngressV2Error("registry qualification has the wrong type")
        if isinstance(self.scene_lease_expires_at_epoch_ms, bool) or not isinstance(
                self.scene_lease_expires_at_epoch_ms, int) \
                or self.scene_lease_expires_at_epoch_ms <= 0:
            raise ModelMotionIngressV2Error("registry lease expiry must be positive epoch-ms")
        if isinstance(self.maximum_scene_age_ms, bool) or not isinstance(
                self.maximum_scene_age_ms, int) or self.maximum_scene_age_ms <= 0:
            raise ModelMotionIngressV2Error("registry maximum scene age must be positive")
        if isinstance(self.minimum_observation_confidence, bool) or not isinstance(
                self.minimum_observation_confidence, (int, float)) \
                or not 0.0 <= float(self.minimum_observation_confidence) <= 1.0:
            raise ModelMotionIngressV2Error("registry minimum confidence must be in [0, 1]")
        if isinstance(self.maximum_surface_normal_error_mm, bool) or not isinstance(
                self.maximum_surface_normal_error_mm, (int, float)) \
                or float(self.maximum_surface_normal_error_mm) < 0.0:
            raise ModelMotionIngressV2Error("registry surface error must be nonnegative")
        regions = tuple(self.target_regions)
        if not regions or any(not isinstance(item, MeasuredTargetRegionV2)
                              for item in regions):
            raise ModelMotionIngressV2Error("registry needs measured target regions")
        ids = tuple(item.target_id for item in regions)
        if len(ids) != len(set(ids)):
            raise ModelMotionIngressV2Error("registry target region ids must be unique")
        if set(ids) != set(self.qualification.target_ids):
            raise ModelMotionIngressV2Error(
                "registry regions must exactly cover qualification targets")
        for region in regions:
            if region.placement_observation_sha256 != self.placement_observation_sha256 \
                    or region.board_frame_definition_sha256 \
                    != self.board_frame_definition_sha256 \
                    or region.target_catalog_sha256 != self.target_catalog_sha256:
                raise ModelMotionIngressV2Error(
                    "registry target region differs from active geometry")
        if self.qualification.target_catalog_sha256 != self.target_catalog_sha256:
            raise ModelMotionIngressV2Error(
                "registry qualification differs from active target map")
        object.__setattr__(self, "target_regions", regions)

    @property
    def target_region_map(self) -> Mapping[str, MeasuredTargetRegionV2]:
        return MappingProxyType({item.target_id: item for item in self.target_regions})


def ingest_with_trusted_registry_v2(
    batch: ModelMotionBatchV2, plan: ActionPlan, context: SimulationContext, *,
    registry: TrustedMotionRegistryV2, current_time_epoch_ms: int,
    current_monotonic_ns: int,
    context_validation_lease: SimulationContextValidationLeaseV1 | None = None,
    active_context_epoch_sha256: str | None = None,
    active_service_instance_id: str | None = None,
    active_context_generation: int | None = None,
    context_lifecycle: SimulationContextLifecycleV1 | None = None,
) -> dict[str, Any]:
    """Admit using one coherent consumer-owned registry snapshot."""
    manual_lifecycle = (
        context_validation_lease,
        active_context_epoch_sha256,
        active_service_instance_id,
        active_context_generation,
    )
    if context_lifecycle is not None:
        if not isinstance(context_lifecycle, SimulationContextLifecycleV1):
            raise TypeError("context_lifecycle must be SimulationContextLifecycleV1")
        if any(value is not None for value in manual_lifecycle):
            raise ModelMotionIngressV2Error(
                "lifecycle-managed admission cannot accept manual lease identity"
            )
        with context_lifecycle.validation_scope(context) as binding:
            return ingest_with_trusted_registry_v2(
                batch, plan, context,
                registry=registry,
                current_time_epoch_ms=current_time_epoch_ms,
                current_monotonic_ns=current_monotonic_ns,
                context_validation_lease=binding.lease,
                active_context_epoch_sha256=binding.context_epoch_sha256,
                active_service_instance_id=binding.service_instance_id,
                active_context_generation=binding.generation,
            )
    if not isinstance(registry, TrustedMotionRegistryV2):
        raise TypeError("registry must be TrustedMotionRegistryV2")
    if registry.target_catalog_sha256 != context.targets.content_sha256:
        raise ModelMotionIngressV2Error("registry target map is not active in context")
    return ingest_model_motion_batch_v2(
        batch, plan, context, current_time_epoch_ms=current_time_epoch_ms,
        current_monotonic_ns=current_monotonic_ns,
        maximum_scene_age_ms=registry.maximum_scene_age_ms,
        trusted_scene_lease_expires_at_epoch_ms=(
            registry.scene_lease_expires_at_epoch_ms),
        expected_capability_profile_id=registry.capability_profile_id,
        expected_capability_profile_sha256=registry.capability_profile_sha256,
        expected_capture_id=registry.capture_id,
        expected_frame_id=registry.frame_id,
        expected_image_sha256=registry.image_sha256,
        expected_capture_clock_domain_id=registry.capture_clock_domain_id,
        expected_camera_identity_sha256=registry.camera_identity_sha256,
        expected_scene_lease_id=registry.scene_lease_id,
        expected_scene_lease_issuer_id=registry.scene_lease_issuer_id,
        expected_scene_lease_sha256=registry.scene_lease_sha256,
        expected_scene_observation_sha256=registry.scene_observation_sha256,
        expected_precision_observation_sha256=(
            registry.precision_observation_sha256),
        expected_fusion_decision_sha256=registry.fusion_decision_sha256,
        expected_placement_observation_sha256=(
            registry.placement_observation_sha256),
        expected_board_frame_definition_sha256=(
            registry.board_frame_definition_sha256),
        trusted_qualification=registry.qualification,
        measured_target_regions=registry.target_region_map,
        minimum_observation_confidence=registry.minimum_observation_confidence,
        maximum_surface_normal_error_mm=(
            registry.maximum_surface_normal_error_mm),
        context_validation_lease=context_validation_lease,
        active_context_epoch_sha256=active_context_epoch_sha256,
        active_service_instance_id=active_service_instance_id,
        active_context_generation=active_context_generation)


def revalidate_with_trusted_registry_v2(
    ingress: Mapping[str, Any], *, registry: TrustedMotionRegistryV2,
    current_monotonic_ns: int,
) -> dict[str, Any]:
    """Recheck the same active snapshot immediately before planning."""
    if not isinstance(registry, TrustedMotionRegistryV2):
        raise TypeError("registry must be TrustedMotionRegistryV2")
    return revalidate_model_motion_ingress_v2(
        ingress, current_monotonic_ns=current_monotonic_ns,
        expected_capability_profile_sha256=registry.capability_profile_sha256,
        active_scene_lease_sha256=registry.scene_lease_sha256,
        active_placement_observation_sha256=(
            registry.placement_observation_sha256),
        active_target_catalog_sha256=registry.target_catalog_sha256)


__all__ = ["TrustedMotionRegistryV2", "ingest_with_trusted_registry_v2",
           "revalidate_with_trusted_registry_v2"]
