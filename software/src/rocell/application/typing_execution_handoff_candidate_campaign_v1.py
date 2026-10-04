"""Strict retained campaign for the zero-authority execution handoff candidate."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence

from .operational_latency_reference_v1 import validate_operational_benchmark_environment_v1
from .typing_execution_handoff_candidate_v1 import (
    parse_typing_execution_handoff_candidate_v1,
)

SCHEMA = "rocell.typing_execution_handoff_candidate_campaign.v1"
CASES = (
    "VALID_COMPLETED_CHAIN", "DETERMINISTIC_REBUILD",
    "NONCOMPLETED_SESSION_REJECTED", "ADMISSION_LINEAGE_REJECTED",
    "SERVICE_LINEAGE_REJECTED", "SHADOW_LINEAGE_REJECTED",
    "BLOCKERS_PRESERVED", "AUTHORITY_TAMPER_REJECTED",
)
EXPECTED = {
    "VALID_COMPLETED_CHAIN": "CANDIDATE_RETAINED",
    "DETERMINISTIC_REBUILD": "IDENTICAL_CANDIDATE_REBUILT",
    "NONCOMPLETED_SESSION_REJECTED": "SESSION_REJECTED",
    "ADMISSION_LINEAGE_REJECTED": "ADMISSION_REJECTED",
    "SERVICE_LINEAGE_REJECTED": "SERVICE_REJECTED",
    "SHADOW_LINEAGE_REJECTED": "SHADOW_REJECTED",
    "BLOCKERS_PRESERVED": "BLOCKERS_EXPLICIT",
    "AUTHORITY_TAMPER_REJECTED": "AUTHORITY_REJECTED",
}


class TypingExecutionHandoffCandidateCampaignV1Error(ValueError):
    """Handoff-candidate campaign evidence differs from the frozen matrix."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_typing_execution_handoff_candidate_campaign_v1(
    cases: Sequence[Mapping[str, object]], *, campaign_id: str,
    environment: Mapping[str, object], reference_candidate_sha256: str,
) -> dict[str, object]:
    if not isinstance(campaign_id, str) or not campaign_id:
        raise TypingExecutionHandoffCandidateCampaignV1Error("campaign id differs")
    if not isinstance(reference_candidate_sha256, str) or len(reference_candidate_sha256) != 64:
        raise TypingExecutionHandoffCandidateCampaignV1Error("reference differs")
    if len(cases) != len(CASES):
        raise TypingExecutionHandoffCandidateCampaignV1Error("case count differs")
    normalized = []
    retained_cases = {"VALID_COMPLETED_CHAIN", "DETERMINISTIC_REBUILD",
                      "BLOCKERS_PRESERVED"}
    for index, item in enumerate(cases):
        fields = {"case", "observed", "candidate", "error",
                  "zero_authority_validated"}
        if (not isinstance(item, Mapping) or set(item) != fields
                or item["case"] != CASES[index]
                or item["observed"] != EXPECTED[item["case"]]
                or item["zero_authority_validated"] is not True):
            raise TypingExecutionHandoffCandidateCampaignV1Error(
                "case fields or outcome differ"
            )
        if item["case"] in retained_cases:
            try:
                candidate = dict(parse_typing_execution_handoff_candidate_v1(
                    item["candidate"]))
            except ValueError as exc:
                raise TypingExecutionHandoffCandidateCampaignV1Error(
                    f"{item['case']} candidate differs: {exc}"
                ) from exc
            if (candidate["handoff_candidate_sha256"]
                    != reference_candidate_sha256 or item["error"] is not None):
                raise TypingExecutionHandoffCandidateCampaignV1Error(
                    f"{item['case']} reference differs"
                )
        else:
            if item["candidate"] is not None or not isinstance(
                item["error"], str
            ) or not item["error"]:
                raise TypingExecutionHandoffCandidateCampaignV1Error(
                    f"{item['case']} rejection differs"
                )
            candidate = None
        normalized.append({"case": item["case"], "observed": item["observed"],
                           "candidate": candidate, "error": item["error"],
                           "zero_authority_validated": True})
    core = {
        "schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_SYNTHETIC_INTEGRATION",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "actual_shared_emitter_used": True,
        "reference_candidate_sha256": reference_candidate_sha256,
        "case_count": len(normalized), "cases": normalized,
        "all_expected_outcomes": True, "lineage_is_fail_closed": True,
        "qualification_blockers_preserved": True,
        "automatic_retry_allowed": False,
        "eligible_for_executor": False, "permit_issued": False,
        "executor_attached": False, "controller_opened": False,
        "transport_opened": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_execution_handoff_candidate_campaign_v1(
    value: Mapping[str, object],
):
    fields = {"schema", "campaign_id", "evidence_class", "environment",
              "actual_shared_emitter_used", "reference_candidate_sha256",
              "case_count", "cases", "all_expected_outcomes",
              "lineage_is_fail_closed", "qualification_blockers_preserved",
              "automatic_retry_allowed", "eligible_for_executor",
              "permit_issued", "executor_attached", "controller_opened",
              "transport_opened", "controller_commands", "hardware_writes",
              "physical_movements", "physical_authority", "campaign_sha256"}
    if (not isinstance(value, Mapping) or set(value) != fields
            or value.get("schema") != SCHEMA):
        raise TypingExecutionHandoffCandidateCampaignV1Error(
            "campaign fields differ"
        )
    unsigned = dict(value); supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingExecutionHandoffCandidateCampaignV1Error(
            "campaign hash differs"
        )
    rebuilt = build_typing_execution_handoff_candidate_campaign_v1(
        value["cases"], campaign_id=value["campaign_id"],
        environment=value["environment"],
        reference_candidate_sha256=value["reference_candidate_sha256"])
    if rebuilt != dict(value):
        raise TypingExecutionHandoffCandidateCampaignV1Error(
            "campaign derivation differs"
        )
    return value


__all__ = ["CASES", "EXPECTED", "SCHEMA",
           "TypingExecutionHandoffCandidateCampaignV1Error",
           "build_typing_execution_handoff_candidate_campaign_v1",
           "parse_typing_execution_handoff_candidate_campaign_v1"]
