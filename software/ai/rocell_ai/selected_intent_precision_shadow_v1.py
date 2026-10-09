"""Selected local intent and precision adapters through the arm shadow boundary."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable, Mapping

from rocell.application import (
    ArmMotionPolicyV2,
    ObservedPlannerStartState,
    SimulationContext,
    TrustedMotionRegistryV2,
    run_model_motion_shadow_v2,
)
from rocell.models import (
    ActionPlan,
    Device,
    MotionCapabilityV2,
    MotionEvidenceV2,
    MotionGeometryV2,
    PressKey,
)

from .end_to_end_typing_twin import compile_virtual_us_sticky_keys
from .offline_intent_shadow_runtime_v1 import (
    parse_intent_shadow_receipt_v1,
    run_intent_shadow_runtime_v1,
)
from .precision_adapter_v2 import PrecisionAdapterResultV2
from .precision_batch_producer_v2 import (
    PlacedTargetRegionMapV2,
    produce_model_motion_batch_v2,
)


SCHEMA = "tactevra.selected_intent_precision_shadow.v1"
SCOPE = "SYNTHETIC_PRECISION_INTEGRATION_ZERO_AUTHORITY"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class SelectedPrecisionShadowInputsV1:
    batch_id: str
    capability: MotionCapabilityV2
    geometry: MotionGeometryV2
    evidence: MotionEvidenceV2
    adapter_result: PrecisionAdapterResultV2
    placed_targets: PlacedTargetRegionMapV2
    registry: TrustedMotionRegistryV2
    policy: ArmMotionPolicyV2
    observed_start_state: ObservedPlannerStartState
    current_time_epoch_ms: int
    ingress_monotonic_ns: int
    preplanner_monotonic_ns: int
    planner_monotonic_ns: int
    fixture_scope: str = "SYNTHETIC_INTEGRATION_ONLY"

    def __post_init__(self) -> None:
        if self.fixture_scope != "SYNTHETIC_INTEGRATION_ONLY":
            raise ValueError("selected precision shadow accepts synthetic fixtures only")


def _terminal(
    *,
    intent_receipt: Mapping[str, Any],
    status: str,
    reason: str,
    plan_hash: str | None = None,
    ordered_targets: tuple[str, ...] = (),
    precision_sha256: str | None = None,
    qualification_sha256: str | None = None,
    payload: bytes | None = None,
    arm_trace: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    core = {
        "schema": SCHEMA,
        "scope": SCOPE,
        "status": status,
        "reason": reason,
        "request_id": intent_receipt["request_id"],
        "intent_shadow_receipt_sha256": intent_receipt["receipt_sha256"],
        "classification_source": intent_receipt["classification_source"],
        "model_digest": intent_receipt["model_digest"],
        "intent_plan_sha256": plan_hash,
        "ordered_target_ids": list(ordered_targets),
        "precision_observation_sha256": precision_sha256,
        "qualification_sha256": qualification_sha256,
        "model_motion_batch_sha256": (
            None if payload is None else hashlib.sha256(payload).hexdigest()
        ),
        "arm_shadow_trace_sha256": (
            None if arm_trace is None else arm_trace["shadow_trace_sha256"]
        ),
        "model_motion_batch_count": 0 if payload is None else 1,
        "controller_command_count": 0,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    return {**core, "receipt_sha256": hashlib.sha256(_canonical(core)).hexdigest()}


def run_selected_intent_precision_shadow_v1(
    *,
    request_id: str,
    request_text: str,
    observation: Mapping[str, Any],
    model: str,
    expected_model_digest: str,
    decoder_schema_sha256: str,
    generate: Callable[[dict[str, Any]], str],
    resolve_model_digest: Callable[[str], str],
    context: SimulationContext,
    inputs: SelectedPrecisionShadowInputsV1 | None,
) -> dict[str, Any]:
    """Compose selected intent and precision evidence without execution authority."""

    intent_receipt = run_intent_shadow_runtime_v1(
        request_id=request_id,
        request_text=request_text,
        observation=observation,
        model=model,
        expected_model_digest=expected_model_digest,
        decoder_schema_sha256=decoder_schema_sha256,
        generate=generate,
        resolve_model_digest=resolve_model_digest,
    )
    parse_intent_shadow_receipt_v1(intent_receipt)
    intent = intent_receipt["composed_intent"]
    if intent["intent_type"] != "TYPE_TEXT":
        return _terminal(
            intent_receipt=intent_receipt,
            status="SHADOW_NON_ACTIONABLE",
            reason=intent["intent_type"].lower(),
        )
    if intent["device"] != "KEYBOARD":
        return _terminal(
            intent_receipt=intent_receipt,
            status="PHONE_MOTION_BOUNDARY_UNAVAILABLE",
            reason="phone_motion_not_integrated",
        )
    if inputs is None:
        return _terminal(
            intent_receipt=intent_receipt,
            status="QUALIFIED_PERCEPTION_REQUIRED",
            reason="precision_adapter_result_not_supplied",
        )

    target_ids = compile_virtual_us_sticky_keys(intent["text"])
    plan = ActionPlan.from_text(
        device=Device.KEYBOARD,
        profile_id=inputs.capability.profile_id,
        text=intent["text"],
        actions=tuple(PressKey(target_id) for target_id in target_ids),
        required_calibrations=("keyboard_pose", "keyboard_tcp"),
    )
    targets = tuple(action.key_id for action in plan.actions)
    precision = inputs.adapter_result.precision_observation
    precision_sha256 = precision["observation_sha256"]
    qualification = inputs.adapter_result.qualification
    qualification_sha256 = (
        None if qualification is None else qualification["qualification_sha256"]
    )
    payload = produce_model_motion_batch_v2(
        plan,
        adapter_result=inputs.adapter_result,
        batch_id=inputs.batch_id,
        request_id=request_id,
        capability=inputs.capability,
        geometry=inputs.geometry,
        evidence=inputs.evidence,
        placed_targets=inputs.placed_targets,
        now_epoch_ms=inputs.current_time_epoch_ms,
    )
    if payload is None:
        return _terminal(
            intent_receipt=intent_receipt,
            status="PERCEPTION_ABSTAINED",
            reason="precision_or_safe_region_not_admitted",
            plan_hash=plan.plan_hash,
            ordered_targets=targets,
            precision_sha256=precision_sha256,
            qualification_sha256=qualification_sha256,
        )
    arm_trace = run_model_motion_shadow_v2(
        payload,
        plan,
        context,
        registry=inputs.registry,
        policy=inputs.policy,
        observed_start_state=inputs.observed_start_state,
        current_time_epoch_ms=inputs.current_time_epoch_ms,
        ingress_monotonic_ns=inputs.ingress_monotonic_ns,
        preplanner_monotonic_ns=inputs.preplanner_monotonic_ns,
        planner_monotonic_ns=inputs.planner_monotonic_ns,
    )
    return _terminal(
        intent_receipt=intent_receipt,
        status=arm_trace["status"],
        reason="arm_shadow_terminal",
        plan_hash=plan.plan_hash,
        ordered_targets=targets,
        precision_sha256=precision_sha256,
        qualification_sha256=qualification_sha256,
        payload=payload,
        arm_trace=arm_trace,
    )


__all__ = ["SelectedPrecisionShadowInputsV1", "run_selected_intent_precision_shadow_v1"]
