"""Selected local intent model to ModelMotionBatchV2 zero-authority shadow bridge."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Mapping

from rocell.application import SimulationContext, run_model_motion_shadow_v2
from rocell.models import ActionPlan, Device, PressKey

from .batch_emitter_v2 import assemble
from .end_to_end_typing_twin import compile_virtual_us_sticky_keys
from .offline_intent_shadow_runtime_v1 import (
    parse_intent_shadow_receipt_v1,
    run_intent_shadow_runtime_v1,
)
from .shared_shadow_runner_v2 import SharedShadowInputsV2


SCHEMA = "tactevra.selected_intent_shadow_bridge.v1"
SCOPE = "SYNTHETIC_INTEGRATION_ZERO_AUTHORITY"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _terminal(
    *, intent_receipt: Mapping[str, Any], status: str, reason: str,
    plan: ActionPlan | None = None, payload: bytes | None = None,
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
        "intent_plan_sha256": None if plan is None else plan.plan_hash,
        "ordered_target_ids": (
            [] if plan is None else [action.key_id for action in plan.actions]
        ),
        "model_motion_batch_sha256": (
            None if payload is None else hashlib.sha256(payload).hexdigest()
        ),
        "arm_shadow_trace_sha256": (
            None if arm_trace is None else arm_trace["shadow_trace_sha256"]
        ),
        "model_motion_batch_count": 0 if payload is None else 1,
        "motion_adapter_call_count": 0,
        "controller_command_count": 0,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    return {
        **core,
        "receipt_sha256": hashlib.sha256(_canonical(core)).hexdigest(),
    }


def _keyboard_plan(
    intent: Mapping[str, str], inputs: SharedShadowInputsV2,
) -> ActionPlan:
    targets = compile_virtual_us_sticky_keys(intent["text"])
    return ActionPlan.from_text(
        device=Device.KEYBOARD,
        profile_id=inputs.capability.profile_id,
        text=intent["text"],
        actions=tuple(PressKey(target_id) for target_id in targets),
        required_calibrations=("keyboard_pose", "keyboard_tcp"),
    )


def run_selected_intent_shadow_bridge_v1(
    *, request_id: str, request_text: str, observation: Mapping[str, Any],
    model: str, expected_model_digest: str, decoder_schema_sha256: str,
    generate: Callable[[dict[str, Any]], str],
    resolve_model_digest: Callable[[str], str],
    context: SimulationContext, inputs: SharedShadowInputsV2 | None,
) -> dict[str, Any]:
    """Run the selected classifier to the existing arm shadow boundary."""

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
            reason="qualified_v2_perception_not_supplied",
        )

    plan = _keyboard_plan(intent, inputs)
    payload = assemble(
        plan,
        batch_id=inputs.batch_id,
        request_id=request_id,
        capability=inputs.capability,
        geometry=inputs.geometry,
        evidence=inputs.evidence,
        observations=inputs.observations,
        uncertainty=inputs.uncertainty,
    )
    if payload is None:
        return _terminal(
            intent_receipt=intent_receipt,
            status="PERCEPTION_ABSTAINED",
            reason="model_motion_batch_not_emitted",
            plan=plan,
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
        plan=plan,
        payload=payload,
        arm_trace=arm_trace,
    )


__all__ = ["run_selected_intent_shadow_bridge_v1"]
