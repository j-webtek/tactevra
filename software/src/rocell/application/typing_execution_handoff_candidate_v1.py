"""Seal completed typing evidence for future permit review, without authority."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .typing_command_session_ledger_v1 import (
    parse_typing_command_session_receipt_v1,
)
from .typing_shadow_pipeline_v1 import parse_typing_shadow_pipeline_v1
from .typing_shadow_service_v1 import parse_typing_shadow_service_receipt_v1
from .typing_supervised_command_gateway_v1 import (
    ADMITTED,
    parse_typing_supervised_command_admission_v1,
)

SCHEMA = "rocell.typing_execution_handoff_candidate.v1"
STATUS = "BLOCKED_PENDING_EXECUTION_QUALIFICATION"
REQUIRED_BLOCKERS = (
    "INSTALLED_COLLISION_PROFILE_REQUIRED",
    "FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION",
    "EXECUTION_PERMIT_REQUIRED",
    "FRESH_CONTROLLER_STATE_REQUIRED",
    "INDEPENDENT_EFFECT_VERIFIER_REQUIRED",
)
_HASH = re.compile(r"^[0-9a-f]{64}$")


class TypingExecutionHandoffCandidateV1Error(ValueError):
    """Handoff evidence or zero-authority disposition is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_typing_execution_handoff_candidate_v1(
    session_receipt: Mapping[str, Any],
    admission_receipt: Mapping[str, Any],
    service_receipt: Mapping[str, Any],
    shadow_pipeline_receipt: Mapping[str, Any],
) -> dict[str, object]:
    try:
        session = dict(parse_typing_command_session_receipt_v1(session_receipt))
        admission = dict(parse_typing_supervised_command_admission_v1(
            admission_receipt))
        service = dict(parse_typing_shadow_service_receipt_v1(service_receipt))
        shadow = dict(parse_typing_shadow_pipeline_v1(shadow_pipeline_receipt))
    except ValueError as exc:
        raise TypingExecutionHandoffCandidateV1Error(
            f"handoff source evidence differs: {exc}"
        ) from exc
    if (session["status"] != "SHADOW_COMPLETED" or not session["terminal"]
            or session["revision"] != 1):
        raise TypingExecutionHandoffCandidateV1Error(
            "session is not a completed terminal shadow result"
        )
    if admission["status"] != ADMITTED:
        raise TypingExecutionHandoffCandidateV1Error(
            "admission was not accepted"
        )
    if service["status"] != "SHADOW_COMPLETED":
        raise TypingExecutionHandoffCandidateV1Error(
            "service did not complete shadow planning"
        )
    if not (
        session["request_id"] == admission["request_id"]
        == service["request_id"] == shadow["request_id"]
        and session["request_sha256"] == admission["request_sha256"]
        == service["request_sha256"]
        and session["admission_receipt_sha256"]
        == admission["admission_receipt_sha256"]
        and session["service_receipt_sha256"]
        == service["service_receipt_sha256"]
        and session["shadow_receipt_sha256"]
        == service["shadow_receipt_sha256"]
        == shadow["typing_shadow_pipeline_sha256"]
    ):
        raise TypingExecutionHandoffCandidateV1Error(
            "handoff lineage differs"
        )
    blockers = tuple(shadow["terminal_blockers"])
    if blockers != REQUIRED_BLOCKERS[:2]:
        raise TypingExecutionHandoffCandidateV1Error(
            "shadow terminal blockers differ"
        )
    stage_hashes = dict(shadow["stage_hashes"])
    core = {
        "schema": SCHEMA,
        "status": STATUS,
        "mission_id": session["mission_id"],
        "request_id": session["request_id"],
        "session_receipt_sha256": session["session_receipt_sha256"],
        "admission_receipt_sha256": admission["admission_receipt_sha256"],
        "service_receipt_sha256": service["service_receipt_sha256"],
        "shadow_pipeline_receipt_sha256": shadow[
            "typing_shadow_pipeline_sha256"
        ],
        "typing_execution_plan_sha256": stage_hashes[
            "typing_execution_plan_sha256"
        ],
        "typing_trajectory_plan_sha256": stage_hashes[
            "typing_trajectory_plan_sha256"
        ],
        "typing_trajectory_ik_screen_sha256": stage_hashes[
            "typing_trajectory_ik_screen_sha256"
        ],
        "typing_joint_schedule_sha256": stage_hashes[
            "typing_joint_schedule_sha256"
        ],
        "typing_collision_intake_sha256": stage_hashes[
            "typing_collision_intake_sha256"
        ],
        "ordered_target_ids": list(shadow["ordered_target_ids"]),
        "action_count": shadow["action_count"],
        "commit_horizon": 1,
        "required_blockers": list(REQUIRED_BLOCKERS),
        "eligible_for_permit_review": False,
        "eligible_for_executor": False,
        "permit_issued": False,
        "automatic_retry_allowed": False,
        "executor_attached": False,
        "controller_opened": False,
        "transport_opened": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "handoff_candidate_sha256": _sha(core)}


def parse_typing_execution_handoff_candidate_v1(value: Mapping[str, object]):
    fields = {
        "schema", "status", "mission_id", "request_id",
        "session_receipt_sha256", "admission_receipt_sha256",
        "service_receipt_sha256", "shadow_pipeline_receipt_sha256",
        "typing_execution_plan_sha256", "typing_trajectory_plan_sha256",
        "typing_trajectory_ik_screen_sha256", "typing_joint_schedule_sha256",
        "typing_collision_intake_sha256", "ordered_target_ids", "action_count",
        "commit_horizon", "required_blockers", "eligible_for_permit_review",
        "eligible_for_executor", "permit_issued", "automatic_retry_allowed",
        "executor_attached", "controller_opened", "transport_opened",
        "controller_commands", "hardware_commands_generated",
        "hardware_access", "physical_authority", "handoff_candidate_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingExecutionHandoffCandidateV1Error(
            "handoff candidate fields differ"
        )
    unsigned = dict(value); supplied = unsigned.pop("handoff_candidate_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingExecutionHandoffCandidateV1Error(
            "handoff candidate hash differs"
        )
    if (value["schema"] != SCHEMA or value["status"] != STATUS
            or not isinstance(value["mission_id"], str)
            or not value["mission_id"] or not isinstance(value["request_id"], str)
            or not value["request_id"]):
        raise TypingExecutionHandoffCandidateV1Error(
            "handoff candidate identity differs"
        )
    for field in (
        "session_receipt_sha256", "admission_receipt_sha256",
        "service_receipt_sha256", "shadow_pipeline_receipt_sha256",
        "typing_execution_plan_sha256", "typing_trajectory_plan_sha256",
        "typing_trajectory_ik_screen_sha256", "typing_joint_schedule_sha256",
        "typing_collision_intake_sha256",
    ):
        if _HASH.fullmatch(value[field] or "") is None:
            raise TypingExecutionHandoffCandidateV1Error(
                "handoff candidate digest differs"
            )
    targets = value["ordered_target_ids"]
    if (not isinstance(targets, list) or not targets
            or any(not isinstance(item, str) or not item for item in targets)
            or value["action_count"] != len(targets)
            or value["commit_horizon"] != 1
            or value["required_blockers"] != list(REQUIRED_BLOCKERS)):
        raise TypingExecutionHandoffCandidateV1Error(
            "handoff candidate plan summary differs"
        )
    if (value["eligible_for_permit_review"] is not False
            or value["eligible_for_executor"] is not False
            or value["permit_issued"] is not False
            or value["automatic_retry_allowed"] is not False
            or value["executor_attached"] is not False
            or value["controller_opened"] is not False
            or value["transport_opened"] is not False
            or value["controller_commands"] != []
            or value["hardware_commands_generated"] != 0
            or value["hardware_access"] is not False
            or value["physical_authority"] is not False):
        raise TypingExecutionHandoffCandidateV1Error(
            "handoff candidate authority differs"
        )
    return value


__all__ = [
    "REQUIRED_BLOCKERS", "SCHEMA", "STATUS",
    "TypingExecutionHandoffCandidateV1Error",
    "build_typing_execution_handoff_candidate_v1",
    "parse_typing_execution_handoff_candidate_v1",
]
