"""PC2-PC5 adapter for the canonical PC6 typing trace journal."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from rocell.models import decode_model_motion_batch_v2_json

from .typing_controller_bridge_v1 import parse_typing_controller_preview_v1
from .typing_fault_campaign_v1 import parse_typing_fault_campaign_v1
from .typing_rolling_horizon_v1 import parse_typing_rolling_horizon_v1
from .typing_shadow_pipeline_v1 import parse_typing_shadow_pipeline_v1
from .typing_trace_journal_v1 import (
    TRACE_STAGE_ORDER,
    build_typing_trace_journal_v1,
)


REFERENCE_SCHEMA = "rocell.typing_trace_stage_reference.v1"
PLACEHOLDER_SCHEMA = "rocell.typing_trace_effect_placeholder.v1"


class TypingTraceAdapterV1Error(ValueError):
    """Validated PC2-PC5 artifacts cannot form one consistent trace."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingTraceAdapterV1Error("trace reference is not canonical JSON") from exc


def _reference(stage: str, source: str, **bindings: object) -> bytes:
    return _canonical({
        "schema": REFERENCE_SCHEMA,
        "stage": stage,
        "source": source,
        "bindings": bindings,
        "controller_commands": [],
        "hardware_access": False,
        "physical_authority": False,
    })


def prepare_pc2_pc5_typing_trace_artifacts_v1(
    *,
    request_artifact: bytes,
    batch_payload: bytes,
    shadow_receipt: Mapping[str, Any],
    rolling_horizon: Mapping[str, Any],
    controller_preview: Mapping[str, Any],
    fault_campaign: Mapping[str, Any],
) -> dict[str, bytes]:
    """Validate and adapt existing artifacts without executing their contents."""

    if not isinstance(request_artifact, bytes) or not request_artifact:
        raise TypingTraceAdapterV1Error("request artifact must be non-empty bytes")
    if not isinstance(batch_payload, bytes):
        raise TypingTraceAdapterV1Error("batch payload must be bytes")
    batch = decode_model_motion_batch_v2_json(batch_payload)
    shadow = parse_typing_shadow_pipeline_v1(shadow_receipt)
    horizon = parse_typing_rolling_horizon_v1(rolling_horizon)
    preview = parse_typing_controller_preview_v1(controller_preview)
    campaign = parse_typing_fault_campaign_v1(fault_campaign)

    request_ids = {
        batch.request_id, shadow["request_id"], horizon["request_id"],
        preview["request_id"],
    }
    if len(request_ids) != 1:
        raise TypingTraceAdapterV1Error("PC2-PC4 request identity is crossed")
    targets = tuple(item.target_id for item in batch.proposals)
    if (
        targets != shadow["ordered_target_ids"]
        or horizon["action_count"] != len(targets)
        or horizon["current"] is None
        or horizon["current"]["action_index"] != preview["action_index"]
        or horizon["current"]["target_id"] != preview["target_id"]
        or preview["action_index"] >= len(targets)
        or targets[preview["action_index"]] != preview["target_id"]
    ):
        raise TypingTraceAdapterV1Error("PC2-PC4 action order is crossed")
    if (
        preview["bindings"]["rolling_horizon_sha256"]
        != horizon["rolling_horizon_sha256"]
        or preview["bindings"]["schedule_sha256"]
        != shadow["stage_hashes"]["typing_joint_schedule_sha256"]
    ):
        raise TypingTraceAdapterV1Error("PC2-PC4 planning lineage is crossed")

    shadow_hash = shadow["typing_shadow_pipeline_sha256"]
    campaign_hash = campaign["typing_fault_campaign_sha256"]
    stage_keys = {
        "INGRESS": "ingress_sha256",
        "EXECUTION_PLAN": "typing_execution_plan_sha256",
        "TRAJECTORY_PLAN": "typing_trajectory_plan_sha256",
        "IK_SCREEN": "typing_trajectory_ik_screen_sha256",
        "JOINT_SCHEDULE": "typing_joint_schedule_sha256",
        "COLLISION_SCREEN": "typing_collision_intake_sha256",
    }
    artifacts: dict[str, bytes] = {
        "REQUEST": request_artifact,
        "AI_BATCH": batch_payload,
    }
    for stage, key in stage_keys.items():
        artifacts[stage] = _reference(
            stage, "PC2_SHADOW_RECEIPT",
            source_receipt_sha256=shadow_hash,
            artifact_sha256=shadow["stage_hashes"][key],
        )
    artifacts["CONTROLLER_PREVIEW"] = _canonical(dict(controller_preview))
    artifacts["PERMIT_POLICY"] = _reference(
        "PERMIT_POLICY", "PC4_PREVIEW_AND_PC5_CAMPAIGN",
        execution_permit_sha256=preview["bindings"]["execution_permit_sha256"],
        fault_campaign_sha256=campaign_hash,
        permit_consumed=False,
    )
    artifacts["COMMAND_ENCODING"] = _reference(
        "COMMAND_ENCODING", "PC4_CONTROLLER_PREVIEW",
        preview_sha256=preview["typing_controller_preview_sha256"],
        encoding_profile_sha256=preview["bindings"]["encoding_profile_sha256"],
        ordered_wire_sha256=preview["ordered_wire_sha256"],
    )
    artifacts["DISPATCH_REHEARSAL"] = _reference(
        "DISPATCH_REHEARSAL", "PC3_HORIZON_AND_PC4_PREVIEW",
        rolling_horizon_sha256=horizon["rolling_horizon_sha256"],
        dispatch_intent_sha256=preview["dispatch_intent_sha256"],
        transport_opened=False,
        transport_write_count=0,
    )
    artifacts["FEEDBACK_REHEARSAL"] = _reference(
        "FEEDBACK_REHEARSAL", "PC4_ACKNOWLEDGEMENT_REQUIREMENTS",
        acknowledgement_requirements_sha256=hashlib.sha256(_canonical(
            dict(preview["acknowledgement_requirements"]))).hexdigest(),
        completion_requires_correlated_feedback=True,
    )
    artifacts["EFFECT_VERIFICATION_PLACEHOLDER"] = _canonical({
        "schema": PLACEHOLDER_SCHEMA,
        "status": "NOT_OBSERVED_SYNTHETIC_PLACEHOLDER",
        "request_id": batch.request_id,
        "fault_campaign_sha256": campaign_hash,
        "automatic_retry_allowed": False,
        "controller_commands": [],
        "hardware_access": False,
        "physical_authority": False,
    })
    if tuple(artifacts) != TRACE_STAGE_ORDER:
        raise TypingTraceAdapterV1Error("adapter stage order differs from PC6")
    return artifacts


def build_pc2_pc5_typing_trace_journal_v1(
    *,
    correlation_id: str,
    request_artifact: bytes,
    batch_payload: bytes,
    shadow_receipt: Mapping[str, Any],
    rolling_horizon: Mapping[str, Any],
    controller_preview: Mapping[str, Any],
    fault_campaign: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Return the sealed journal and exact replay inputs for retained storage."""

    artifacts = prepare_pc2_pc5_typing_trace_artifacts_v1(
        request_artifact=request_artifact,
        batch_payload=batch_payload,
        shadow_receipt=shadow_receipt,
        rolling_horizon=rolling_horizon,
        controller_preview=controller_preview,
        fault_campaign=fault_campaign,
    )
    batch = decode_model_motion_batch_v2_json(batch_payload)
    journal = build_typing_trace_journal_v1(
        artifacts,
        correlation_id=correlation_id,
        request_id=batch.request_id,
        ordered_target_ids=tuple(item.target_id for item in batch.proposals),
    )
    return journal, artifacts


__all__ = [
    "PLACEHOLDER_SCHEMA", "REFERENCE_SCHEMA", "TypingTraceAdapterV1Error",
    "build_pc2_pc5_typing_trace_journal_v1",
    "prepare_pc2_pc5_typing_trace_artifacts_v1",
]
