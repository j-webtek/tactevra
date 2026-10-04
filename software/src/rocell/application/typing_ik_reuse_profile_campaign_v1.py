"""Strict retained qualification record for the frozen IK reuse-profile gate."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence

from .operational_latency_reference_v1 import validate_operational_benchmark_environment_v1

SCHEMA = "rocell.typing_ik_reuse_profile_campaign.v1"
CASES = (
    "EXACT_PROFILE_ELIGIBLE", "EVIDENCE_MISMATCH_FALLBACK",
    "CALIBRATION_MISMATCH_FALLBACK", "UNSAFE_SETTINGS_REJECTED",
    "RELOAD_STALE_REJECTED", "RESTART_STALE_REJECTED",
)
EXPECTED = (
    "EXACT_INPUT_REUSE_SHADOW_ELIGIBLE", "FULL_SOLVE_ONLY",
    "FULL_SOLVE_ONLY", "REJECTED", "REJECTED", "REJECTED",
)


class TypingIkReuseProfileCampaignV1Error(ValueError):
    """The profile-gate qualification record differs from its frozen matrix."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_typing_ik_reuse_profile_campaign_v1(
    cases: Sequence[Mapping[str, object]], *, campaign_id: str,
    environment: Mapping[str, object], qualified_profile_sha256: str,
) -> dict[str, object]:
    if not isinstance(campaign_id, str) or not campaign_id:
        raise TypingIkReuseProfileCampaignV1Error("campaign id differs")
    if not isinstance(qualified_profile_sha256, str) or len(qualified_profile_sha256) != 64:
        raise TypingIkReuseProfileCampaignV1Error("profile hash differs")
    if len(cases) != len(CASES):
        raise TypingIkReuseProfileCampaignV1Error("case count differs")
    normalized = []
    for index, item in enumerate(cases):
        if not isinstance(item, Mapping) or set(item) != {"case", "status", "disposition", "detail"}:
            raise TypingIkReuseProfileCampaignV1Error("case fields differ")
        detail = item["detail"]
        if (item["case"] != CASES[index] or item["status"] != "PASS"
                or item["disposition"] != EXPECTED[index]
                or not isinstance(detail, str) or not detail):
            raise TypingIkReuseProfileCampaignV1Error("case result differs")
        normalized.append(dict(item))
    core = {
        "schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_OFFLINE",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "qualified_profile_sha256": qualified_profile_sha256,
        "case_count": len(normalized), "cases": normalized,
        "exact_solver_input_only": True,
        "endpoint_only_substitution_authorized": False,
        "complete_solve_fallback_required": True,
        "automatic_retry_allowed": False,
        "candidate_used_for_admission": False,
        "controller_opened": False, "transport_opened": False,
        "controller_commands": [], "hardware_writes": 0,
        "physical_movements": 0, "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_ik_reuse_profile_campaign_v1(value: Mapping[str, object]):
    expected_fields = {
        "schema", "campaign_id", "evidence_class", "environment",
        "qualified_profile_sha256", "case_count", "cases",
        "exact_solver_input_only", "endpoint_only_substitution_authorized",
        "complete_solve_fallback_required", "automatic_retry_allowed",
        "candidate_used_for_admission", "controller_opened", "transport_opened",
        "controller_commands", "hardware_writes", "physical_movements",
        "physical_authority", "campaign_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise TypingIkReuseProfileCampaignV1Error("campaign fields differ")
    supplied = value["campaign_sha256"]
    unsigned = dict(value); unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingIkReuseProfileCampaignV1Error("campaign hash differs")
    rebuilt = build_typing_ik_reuse_profile_campaign_v1(
        value["cases"], campaign_id=value["campaign_id"],
        environment=value["environment"],
        qualified_profile_sha256=value["qualified_profile_sha256"],
    )
    if rebuilt != dict(value):
        raise TypingIkReuseProfileCampaignV1Error("campaign derivation differs")
    return value


__all__ = ["CASES", "EXPECTED", "SCHEMA", "TypingIkReuseProfileCampaignV1Error",
           "build_typing_ik_reuse_profile_campaign_v1",
           "parse_typing_ik_reuse_profile_campaign_v1"]
