"""Emit canonical shared V2 bytes for the profiled arm shadow service."""

from __future__ import annotations

from typing import Any, Mapping

from rocell.models import decode_model_motion_batch_v2_json

from .batch_emitter_v2 import TargetObservationV2, assemble


class ProfiledServiceIngressV2Error(ValueError):
    """The supplied integration fixture cannot be emitted safely."""


def emit_profiled_service_inputs_v2(
    pipeline_inputs: Mapping[str, Any], *, batch_id: str, request_id: str,
) -> dict[str, Any]:
    """Replace fixture payload bytes using the actual shared AI assembler.

    All consumer-owned registry, calibration, policy, and planning inputs remain
    untouched. This adapter creates no execution or hardware authority.
    """

    if not isinstance(pipeline_inputs, Mapping):
        raise TypeError("pipeline_inputs must be a mapping")
    if not isinstance(batch_id, str) or not batch_id:
        raise ProfiledServiceIngressV2Error("batch id is invalid")
    if not isinstance(request_id, str) or not request_id:
        raise ProfiledServiceIngressV2Error("request id is invalid")
    payload = pipeline_inputs.get("payload")
    plan = pipeline_inputs.get("intent_plan")
    if not isinstance(payload, bytes) or not payload or plan is None:
        raise ProfiledServiceIngressV2Error("fixture payload or plan is missing")
    source = decode_model_motion_batch_v2_json(payload)
    observations = {
        proposal.target_id: TargetObservationV2(
            proposal.target, proposal.observation_confidence
        )
        for proposal in source.proposals
    }
    emitted = assemble(
        plan, batch_id=batch_id, request_id=request_id,
        capability=source.capability, geometry=source.geometry,
        evidence=source.evidence, uncertainty=source.uncertainty,
        observations=observations,
    )
    if emitted is None:
        raise ProfiledServiceIngressV2Error("shared emitter abstained")
    decoded = decode_model_motion_batch_v2_json(emitted)
    expected_order = [getattr(action, "key_id", None) for action in plan.actions]
    actual_order = [proposal.target_id for proposal in decoded.proposals]
    if actual_order != expected_order:
        raise ProfiledServiceIngressV2Error("shared emitter changed action order")
    authority = decoded.unsigned_dict()
    if (decoded.intent_plan_sha256 != plan.plan_hash
            or authority["controller_commands"] != []
            or authority["hardware_access"] is not False
            or authority["physical_authority"] is not False):
        raise ProfiledServiceIngressV2Error("shared emitter changed authority or plan")
    result = dict(pipeline_inputs)
    result["payload"] = emitted
    return result


__all__ = ["ProfiledServiceIngressV2Error", "emit_profiled_service_inputs_v2"]
