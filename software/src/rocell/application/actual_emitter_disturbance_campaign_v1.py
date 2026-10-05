"""Strict evidence for bounded disturbances against a warm profiled service."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Mapping, Sequence

from .operational_latency_reference_v1 import validate_operational_benchmark_environment_v1

SCHEMA = "rocell.actual_emitter_disturbance_campaign.v1"
CASES = ("WARM_BASELINE", "QUEUE_SATURATION", "CANCEL_PRESSURE",
         "MALFORMED_REJECTION", "RELOAD_STALE_AND_FALLBACK",
         "RESTART_STALE_AND_FALLBACK", "QUALIFIED_REPLACEMENT_RECOVERY")
COUNTERS = frozenset({"lookups", "hits", "misses", "stores", "capacity_skips"})
_HASH = re.compile(r"^[0-9a-f]{64}$")


class ActualEmitterDisturbanceCampaignV1Error(ValueError):
    """Operational-disturbance evidence differs from the frozen matrix."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _counters(value: object) -> dict[str, int]:
    if (not isinstance(value, Mapping) or set(value) != COUNTERS
            or any(isinstance(v, bool) or not isinstance(v, int) or v < 0
                   for v in value.values())):
        raise ActualEmitterDisturbanceCampaignV1Error("cache counters differ")
    result = dict(value)
    if result["lookups"] != result["hits"] + result["misses"]:
        raise ActualEmitterDisturbanceCampaignV1Error("cache derivation differs")
    return result


def build_actual_emitter_disturbance_campaign_v1(
    cases: Sequence[Mapping[str, object]], *, campaign_id: str,
    environment: Mapping[str, object], reference_shadow_receipt_sha256: str,
) -> dict[str, object]:
    if not isinstance(campaign_id, str) or not campaign_id:
        raise ActualEmitterDisturbanceCampaignV1Error("campaign id differs")
    if _HASH.fullmatch(reference_shadow_receipt_sha256 or "") is None:
        raise ActualEmitterDisturbanceCampaignV1Error("reference receipt differs")
    if len(cases) != len(CASES):
        raise ActualEmitterDisturbanceCampaignV1Error("case count differs")
    normalized = []
    expected_statuses = {
        "WARM_BASELINE": ["SHADOW_COMPLETED"],
        "QUEUE_SATURATION": ["SHADOW_COMPLETED"] * 8,
        "CANCEL_PRESSURE": ["CANCELED_BEFORE_ADMISSION"] * 3 + ["SHADOW_COMPLETED"] * 5,
        "MALFORMED_REJECTION": [],
        "RELOAD_STALE_AND_FALLBACK": ["STALE_GENERATION_REJECTED"] * 3 + ["SHADOW_COMPLETED"],
        "RESTART_STALE_AND_FALLBACK": ["STALE_GENERATION_REJECTED"] * 2 + ["SHADOW_COMPLETED"],
        "QUALIFIED_REPLACEMENT_RECOVERY": ["SHADOW_COMPLETED"],
    }
    for index, item in enumerate(cases):
        fields = {"case", "statuses", "request_order_preserved",
                  "rejection_messages", "cache_activity", "exact_reuse_enabled_after",
                  "automatic_retries", "reference_equivalent",
                  "shadow_receipt_sha256"}
        if not isinstance(item, Mapping) or set(item) != fields or item["case"] != CASES[index]:
            raise ActualEmitterDisturbanceCampaignV1Error("case fields differ")
        name = CASES[index]; statuses = item["statuses"]
        if statuses != expected_statuses[name] or item["request_order_preserved"] is not True:
            raise ActualEmitterDisturbanceCampaignV1Error(f"{name} outcome differs")
        messages = item["rejection_messages"]
        if not isinstance(messages, list) or any(not isinstance(v, str) or not v for v in messages):
            raise ActualEmitterDisturbanceCampaignV1Error(f"{name} rejection evidence differs")
        expected_message_counts = {"QUEUE_SATURATION": 1, "MALFORMED_REJECTION": 3}
        if len(messages) != expected_message_counts.get(name, 0):
            raise ActualEmitterDisturbanceCampaignV1Error(f"{name} rejection evidence differs")
        counters = _counters(item["cache_activity"])
        warm_case = name in {"WARM_BASELINE", "QUEUE_SATURATION", "CANCEL_PRESSURE",
                             "QUALIFIED_REPLACEMENT_RECOVERY"}
        if warm_case and (counters["lookups"] < 1 or counters["hits"] != counters["lookups"]
                          or counters["misses"] or counters["stores"]
                          or counters["capacity_skips"]):
            raise ActualEmitterDisturbanceCampaignV1Error(f"{name} warm cache differs")
        if not warm_case and any(counters.values()):
            raise ActualEmitterDisturbanceCampaignV1Error(f"{name} cache activity differs")
        enabled = item["exact_reuse_enabled_after"]
        expected_enabled = name not in {"RELOAD_STALE_AND_FALLBACK",
                                        "RESTART_STALE_AND_FALLBACK"}
        if enabled is not expected_enabled or item["automatic_retries"] != 0:
            raise ActualEmitterDisturbanceCampaignV1Error(f"{name} lifecycle result differs")
        equivalent = item["reference_equivalent"]
        shadow = item["shadow_receipt_sha256"]
        should_match = name in {"WARM_BASELINE", "QUALIFIED_REPLACEMENT_RECOVERY"}
        if should_match:
            if equivalent is not True or shadow != reference_shadow_receipt_sha256:
                raise ActualEmitterDisturbanceCampaignV1Error(f"{name} reference differs")
        elif equivalent is not False or shadow is not None:
            raise ActualEmitterDisturbanceCampaignV1Error(f"{name} reference differs")
        normalized.append({**dict(item), "cache_activity": counters})
    core = {
        "schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_SYNTHETIC_INTEGRATION",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "actual_shared_emitter_used": True,
        "fixture_scope": "SYNTHETIC_INTEGRATION_ONLY",
        "reference_shadow_receipt_sha256": reference_shadow_receipt_sha256,
        "case_count": len(normalized), "cases": normalized,
        "all_expected_outcomes": True, "decision_equivalence_preserved": True,
        "queue_bound": 8, "request_bound": 64, "cache_entry_bound": 256,
        "complete_solve_fallback_required": True,
        "automatic_retry_allowed": False,
        "executor_attached": False, "controller_opened": False,
        "transport_opened": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_actual_emitter_disturbance_campaign_v1(value: Mapping[str, object]):
    fields = {"schema", "campaign_id", "evidence_class", "environment",
              "actual_shared_emitter_used", "fixture_scope",
              "reference_shadow_receipt_sha256", "case_count", "cases",
              "all_expected_outcomes", "decision_equivalence_preserved",
              "queue_bound", "request_bound", "cache_entry_bound",
              "complete_solve_fallback_required", "automatic_retry_allowed",
              "executor_attached", "controller_opened", "transport_opened",
              "controller_commands", "hardware_writes", "physical_movements",
              "physical_authority", "campaign_sha256"}
    if not isinstance(value, Mapping) or set(value) != fields or value.get("schema") != SCHEMA:
        raise ActualEmitterDisturbanceCampaignV1Error("campaign fields differ")
    unsigned = dict(value); supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise ActualEmitterDisturbanceCampaignV1Error("campaign hash differs")
    rebuilt = build_actual_emitter_disturbance_campaign_v1(
        value["cases"], campaign_id=value["campaign_id"],
        environment=value["environment"],
        reference_shadow_receipt_sha256=value["reference_shadow_receipt_sha256"])
    if rebuilt != dict(value):
        raise ActualEmitterDisturbanceCampaignV1Error("campaign derivation differs")
    return value


__all__ = ["CASES", "SCHEMA", "ActualEmitterDisturbanceCampaignV1Error",
           "build_actual_emitter_disturbance_campaign_v1",
           "parse_actual_emitter_disturbance_campaign_v1"]
