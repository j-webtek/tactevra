"""Epoch-bound immutable preparation for typing IK and collision intake."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from ._pinned_model import LoadedPinnedUrdf, load_pinned_urdf
from .context import SimulationContext, SimulationContextError
from .context_lifecycle_v1 import (
    SimulationContextLifecycleBindingV1,
    SimulationContextLifecycleV1,
)


SCHEMA = "rocell.prepared_typing_planner.v1"


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PreparedTypingPlannerV1:
    """Parsed immutable model bound to one context lifecycle generation."""

    context: SimulationContext
    context_epoch_sha256: str
    service_instance_id: str
    generation: int
    loaded_model: LoadedPinnedUrdf
    preparation_sha256: str
    hardware_access: bool
    physical_authority: bool


def _core(
    binding: SimulationContextLifecycleBindingV1,
    loaded: LoadedPinnedUrdf,
) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "context_epoch_sha256": binding.context_epoch_sha256,
        "service_instance_id": binding.service_instance_id,
        "generation": binding.generation,
        "model_sha256": loaded.sha256,
        "model_byte_count": loaded.byte_count,
        "hardware_access": False,
        "physical_authority": False,
    }


def prepare_typing_planner_v1(
    context: SimulationContext,
    lifecycle: SimulationContextLifecycleV1,
) -> PreparedTypingPlannerV1:
    """Parse the exact pinned model once under the active lifecycle lock."""

    if not isinstance(lifecycle, SimulationContextLifecycleV1):
        raise TypeError("lifecycle must be SimulationContextLifecycleV1")
    with lifecycle.validation_scope(context) as binding:
        loaded = load_pinned_urdf(
            context.scenario.model_path,
            context.scenario.model_sha256,
        )
        fixed = loaded.model.joint("world_to_base_link")
        if (
            fixed.joint_type != "fixed"
            or fixed.parent_link != "world"
            or fixed.child_link != "base_link"
        ):
            raise SimulationContextError("pinned URDF lost Wv_T_Ru contract")
        core = _core(binding, loaded)
        return PreparedTypingPlannerV1(
            context=context,
            context_epoch_sha256=binding.context_epoch_sha256,
            service_instance_id=binding.service_instance_id,
            generation=binding.generation,
            loaded_model=loaded,
            preparation_sha256=_sha(core),
            hardware_access=False,
            physical_authority=False,
        )


def validate_prepared_typing_planner_v1(
    prepared: PreparedTypingPlannerV1,
    binding: SimulationContextLifecycleBindingV1,
) -> None:
    """Reject preparation from another context, generation, or model."""

    if not isinstance(prepared, PreparedTypingPlannerV1):
        raise SimulationContextError("prepared planner has the wrong type")
    if not isinstance(binding, SimulationContextLifecycleBindingV1):
        raise SimulationContextError("context lifecycle binding has the wrong type")
    if prepared.context is not binding.context:
        raise SimulationContextError("prepared planner belongs to a different context")
    if (
        prepared.context_epoch_sha256 != binding.context_epoch_sha256
        or prepared.service_instance_id != binding.service_instance_id
        or prepared.generation != binding.generation
    ):
        raise SimulationContextError("prepared planner lifecycle binding is stale")
    if (
        prepared.loaded_model.sha256 != binding.context.scenario.model_sha256
        or prepared.hardware_access is not False
        or prepared.physical_authority is not False
    ):
        raise SimulationContextError("prepared planner violates model or authority binding")
    if prepared.preparation_sha256 != _sha(_core(binding, prepared.loaded_model)):
        raise SimulationContextError("prepared planner hash differs")


__all__ = [
    "PreparedTypingPlannerV1",
    "prepare_typing_planner_v1",
    "validate_prepared_typing_planner_v1",
]
