"""Strict retained qualification for runtime-supervisor state transitions."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Mapping, Sequence

from .operational_latency_reference_v1 import validate_operational_benchmark_environment_v1
from .typing_runtime_supervisor_v1 import FULL_SOLVE_ONLY, REQUALIFICATION_REQUIRED, WARM

SCHEMA = "rocell.typing_runtime_supervisor_campaign.v1"
CASES = ("QUALIFIED_WARM_START", "STARTUP_MISMATCH_FULL_SOLVE",
         "RELOAD_REQUIRES_REQUALIFICATION", "RESTART_REQUIRES_REQUALIFICATION",
         "EXPLICIT_FULL_SOLVE_CONTINUATION", "QUALIFIED_REPLACEMENT_WARM",
         "INVALIDATION_TERMINAL")
_HASH = re.compile(r"^[0-9a-f]{64}$")


class TypingRuntimeSupervisorCampaignV1Error(ValueError):
    """Supervisor transition evidence differs from the frozen matrix."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_typing_runtime_supervisor_campaign_v1(
    cases: Sequence[Mapping[str, object]], *, campaign_id: str,
    environment: Mapping[str, object], reference_shadow_receipt_sha256: str,
) -> dict[str, object]:
    if not isinstance(campaign_id, str) or not campaign_id:
        raise TypingRuntimeSupervisorCampaignV1Error("campaign id differs")
    if _HASH.fullmatch(reference_shadow_receipt_sha256 or "") is None:
        raise TypingRuntimeSupervisorCampaignV1Error("reference receipt differs")
    if len(cases) != len(CASES):
        raise TypingRuntimeSupervisorCampaignV1Error("case count differs")
    expected = {
        "QUALIFIED_WARM_START": (WARM, "QUALIFIED_PROFILE", True, True, None),
        "STARTUP_MISMATCH_FULL_SOLVE": (FULL_SOLVE_ONLY, "STARTUP_PROFILE_MISMATCH", True, False, "SHADOW_COMPLETED"),
        "RELOAD_REQUIRES_REQUALIFICATION": (REQUALIFICATION_REQUIRED, "SOURCES_RELOADED", True, False, "STALE_GENERATION_REJECTED"),
        "RESTART_REQUIRES_REQUALIFICATION": (REQUALIFICATION_REQUIRED, "SERVICE_RESTARTED", True, False, "STALE_GENERATION_REJECTED"),
        "EXPLICIT_FULL_SOLVE_CONTINUATION": (FULL_SOLVE_ONLY, "EXPLICIT_FULL_SOLVE_CONTINUATION", True, False, "SHADOW_COMPLETED"),
        "QUALIFIED_REPLACEMENT_WARM": (WARM, "QUALIFIED_PROFILE", True, True, "SHADOW_COMPLETED"),
        "INVALIDATION_TERMINAL": (REQUALIFICATION_REQUIRED, "INVALIDATED", False, False, None),
    }
    normalized = []
    for index, item in enumerate(cases):
        fields = {"case", "state", "state_reason", "active", "exact_reuse_enabled",
                  "status", "submission_rejection", "cache_counters",
                  "reference_equivalent", "shadow_receipt_sha256",
                  "automatic_retries", "snapshot_sha256"}
        if not isinstance(item, Mapping) or set(item) != fields or item["case"] != CASES[index]:
            raise TypingRuntimeSupervisorCampaignV1Error("case fields differ")
        state, reason, active, reuse, status = expected[item["case"]]
        if (item["state"], item["state_reason"], item["active"],
                item["exact_reuse_enabled"], item["status"]) != (
                state, reason, active, reuse, status):
            raise TypingRuntimeSupervisorCampaignV1Error(f"{item['case']} outcome differs")
        rejection_expected = item["case"] in {
            "RELOAD_REQUIRES_REQUALIFICATION", "RESTART_REQUIRES_REQUALIFICATION",
            "INVALIDATION_TERMINAL"}
        rejection = item["submission_rejection"]
        if rejection_expected is not (isinstance(rejection, str) and bool(rejection)):
            raise TypingRuntimeSupervisorCampaignV1Error(f"{item['case']} rejection differs")
        counters = item["cache_counters"]
        if (not isinstance(counters, Mapping)
                or set(counters) != {"lookups", "hits", "misses", "stores", "capacity_skips"}
                or any(isinstance(v, bool) or not isinstance(v, int) or v < 0
                       for v in counters.values())):
            raise TypingRuntimeSupervisorCampaignV1Error("cache counters differ")
        match_expected = item["case"] in {
            "STARTUP_MISMATCH_FULL_SOLVE", "QUALIFIED_REPLACEMENT_WARM"}
        if match_expected:
            if (item["reference_equivalent"] is not True
                    or item["shadow_receipt_sha256"] != reference_shadow_receipt_sha256):
                raise TypingRuntimeSupervisorCampaignV1Error(f"{item['case']} reference differs")
        elif item["reference_equivalent"] is not False or item["shadow_receipt_sha256"] is not None:
            raise TypingRuntimeSupervisorCampaignV1Error(f"{item['case']} reference differs")
        if (item["automatic_retries"] != 0
                or _HASH.fullmatch(item["snapshot_sha256"] or "") is None):
            raise TypingRuntimeSupervisorCampaignV1Error(f"{item['case']} evidence differs")
        normalized.append({**dict(item), "cache_counters": dict(counters)})
    core = {
        "schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_SYNTHETIC_INTEGRATION",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "reference_shadow_receipt_sha256": reference_shadow_receipt_sha256,
        "case_count": len(normalized), "cases": normalized,
        "all_expected_outcomes": True, "decision_equivalence_preserved": True,
        "new_work_blocked_while_requalification_required": True,
        "complete_solve_continuation_explicit": True,
        "automatic_retry_allowed": False,
        "executor_attached": False, "controller_opened": False,
        "transport_opened": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_runtime_supervisor_campaign_v1(value: Mapping[str, object]):
    fields = {"schema", "campaign_id", "evidence_class", "environment",
              "reference_shadow_receipt_sha256", "case_count", "cases",
              "all_expected_outcomes", "decision_equivalence_preserved",
              "new_work_blocked_while_requalification_required",
              "complete_solve_continuation_explicit", "automatic_retry_allowed",
              "executor_attached", "controller_opened", "transport_opened",
              "controller_commands", "hardware_writes", "physical_movements",
              "physical_authority", "campaign_sha256"}
    if not isinstance(value, Mapping) or set(value) != fields or value.get("schema") != SCHEMA:
        raise TypingRuntimeSupervisorCampaignV1Error("campaign fields differ")
    unsigned = dict(value); supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingRuntimeSupervisorCampaignV1Error("campaign hash differs")
    rebuilt = build_typing_runtime_supervisor_campaign_v1(
        value["cases"], campaign_id=value["campaign_id"],
        environment=value["environment"],
        reference_shadow_receipt_sha256=value["reference_shadow_receipt_sha256"])
    if rebuilt != dict(value):
        raise TypingRuntimeSupervisorCampaignV1Error("campaign derivation differs")
    return value


__all__ = ["CASES", "SCHEMA", "TypingRuntimeSupervisorCampaignV1Error",
           "build_typing_runtime_supervisor_campaign_v1",
           "parse_typing_runtime_supervisor_campaign_v1"]
