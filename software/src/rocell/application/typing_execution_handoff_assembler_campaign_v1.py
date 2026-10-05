"""Strict retained campaign for ledger-owned handoff assembly."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence

from .operational_latency_reference_v1 import (
    validate_operational_benchmark_environment_v1,
)
from .typing_command_session_ledger_v1 import (
    parse_typing_command_session_ledger_snapshot_v1,
)
from .typing_execution_handoff_candidate_v1 import (
    parse_typing_execution_handoff_candidate_v1,
)
from .typing_shadow_artifact_store_v1 import (
    parse_typing_shadow_artifact_store_snapshot_v1,
)

SCHEMA = "rocell.typing_execution_handoff_assembler_campaign.v1"
CASES = (
    "COMPLETED_ASSEMBLY",
    "REPEAT_ASSEMBLY",
    "POST_INVALIDATION_AUDIT_ASSEMBLY",
    "QUEUED_REJECTED",
    "CANCELED_REJECTED",
    "STALE_REJECTED",
    "ADMISSION_REJECTED",
    "UNKNOWN_REJECTED",
)
EXPECTED = {
    "COMPLETED_ASSEMBLY": "CANDIDATE_ASSEMBLED",
    "REPEAT_ASSEMBLY": "IDENTICAL_CANDIDATE_ASSEMBLED",
    "POST_INVALIDATION_AUDIT_ASSEMBLY": "IDENTICAL_CANDIDATE_ASSEMBLED",
    "QUEUED_REJECTED": "INCOMPLETE_CHAIN_REJECTED",
    "CANCELED_REJECTED": "INCOMPLETE_CHAIN_REJECTED",
    "STALE_REJECTED": "INCOMPLETE_CHAIN_REJECTED",
    "ADMISSION_REJECTED": "INCOMPLETE_CHAIN_REJECTED",
    "UNKNOWN_REJECTED": "UNKNOWN_REQUEST_REJECTED",
}


class TypingExecutionHandoffAssemblerCampaignV1Error(ValueError):
    """Assembler campaign evidence differs from the frozen matrix."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_typing_execution_handoff_assembler_campaign_v1(
    cases: Sequence[Mapping[str, object]], *, campaign_id: str,
    environment: Mapping[str, object], reference_candidate_sha256: str,
) -> dict[str, object]:
    if not isinstance(campaign_id, str) or not campaign_id:
        raise TypingExecutionHandoffAssemblerCampaignV1Error(
            "campaign id differs"
        )
    if (not isinstance(reference_candidate_sha256, str)
            or len(reference_candidate_sha256) != 64
            or len(cases) != len(CASES)):
        raise TypingExecutionHandoffAssemblerCampaignV1Error(
            "campaign reference or case count differs"
        )
    accepted = {
        "COMPLETED_ASSEMBLY", "REPEAT_ASSEMBLY",
        "POST_INVALIDATION_AUDIT_ASSEMBLY",
    }
    normalized = []
    for index, item in enumerate(cases):
        fields = {
            "case", "observed", "candidate", "error", "ledger_snapshot",
            "artifact_store_snapshot", "zero_authority_validated",
        }
        if (not isinstance(item, Mapping) or set(item) != fields
                or item["case"] != CASES[index]
                or item["observed"] != EXPECTED[item["case"]]
                or item["zero_authority_validated"] is not True):
            raise TypingExecutionHandoffAssemblerCampaignV1Error(
                "case fields or outcome differ"
            )
        try:
            ledger_snapshot = dict(
                parse_typing_command_session_ledger_snapshot_v1(
                    item["ledger_snapshot"]
                )
            )
            artifact_snapshot = dict(
                parse_typing_shadow_artifact_store_snapshot_v1(
                    item["artifact_store_snapshot"]
                )
            )
        except ValueError as exc:
            raise TypingExecutionHandoffAssemblerCampaignV1Error(
                f"{item['case']} snapshot differs: {exc}"
            ) from exc
        if item["case"] in accepted:
            try:
                parsed = parse_typing_execution_handoff_candidate_v1(
                    item["candidate"]
                )
            except ValueError as exc:
                raise TypingExecutionHandoffAssemblerCampaignV1Error(
                    f"{item['case']} candidate differs: {exc}"
                ) from exc
            if (parsed["handoff_candidate_sha256"]
                    != reference_candidate_sha256 or item["error"] is not None):
                raise TypingExecutionHandoffAssemblerCampaignV1Error(
                    f"{item['case']} reference differs"
                )
            candidate = json.loads(_canonical(item["candidate"]))
        else:
            if (item["candidate"] is not None
                    or not isinstance(item["error"], str)
                    or not item["error"]):
                raise TypingExecutionHandoffAssemblerCampaignV1Error(
                    f"{item['case']} rejection differs"
                )
            candidate = None
        normalized.append({
            "case": item["case"], "observed": item["observed"],
            "candidate": candidate, "error": item["error"],
            "ledger_snapshot": ledger_snapshot,
            "artifact_store_snapshot": artifact_snapshot,
            "zero_authority_validated": True,
        })
    core = {
        "schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_SYNTHETIC_INTEGRATION",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "actual_shared_emitter_used": True,
        "reference_candidate_sha256": reference_candidate_sha256,
        "case_count": len(normalized), "cases": normalized,
        "all_expected_outcomes": True,
        "planner_rerun_required_for_assembly": False,
        "post_invalidation_audit_available": True,
        "automatic_retry_allowed": False,
        "eligible_for_executor": False, "permit_issued": False,
        "executor_attached": False, "controller_opened": False,
        "transport_opened": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_execution_handoff_assembler_campaign_v1(
    value: Mapping[str, object],
):
    fields = {
        "schema", "campaign_id", "evidence_class", "environment",
        "actual_shared_emitter_used", "reference_candidate_sha256",
        "case_count", "cases", "all_expected_outcomes",
        "planner_rerun_required_for_assembly",
        "post_invalidation_audit_available", "automatic_retry_allowed",
        "eligible_for_executor", "permit_issued", "executor_attached",
        "controller_opened", "transport_opened", "controller_commands",
        "hardware_writes", "physical_movements", "physical_authority",
        "campaign_sha256",
    }
    if (not isinstance(value, Mapping) or set(value) != fields
            or value.get("schema") != SCHEMA):
        raise TypingExecutionHandoffAssemblerCampaignV1Error(
            "campaign fields differ"
        )
    unsigned = dict(value)
    supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingExecutionHandoffAssemblerCampaignV1Error(
            "campaign hash differs"
        )
    rebuilt = build_typing_execution_handoff_assembler_campaign_v1(
        value["cases"], campaign_id=value["campaign_id"],
        environment=value["environment"],
        reference_candidate_sha256=value["reference_candidate_sha256"],
    )
    if rebuilt != dict(value):
        raise TypingExecutionHandoffAssemblerCampaignV1Error(
            "campaign derivation differs"
        )
    return value


__all__ = [
    "CASES", "EXPECTED", "SCHEMA",
    "TypingExecutionHandoffAssemblerCampaignV1Error",
    "build_typing_execution_handoff_assembler_campaign_v1",
    "parse_typing_execution_handoff_assembler_campaign_v1",
]
