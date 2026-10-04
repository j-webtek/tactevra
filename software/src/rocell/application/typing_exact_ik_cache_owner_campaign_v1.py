"""Strict retained lifecycle and fault campaign for the exact IK cache owner."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .operational_latency_reference_v1 import (
    validate_operational_benchmark_environment_v1,
)
from .typing_exact_ik_cache_owner_v1 import (
    TypingExactIkCacheOwnerV1Error,
    parse_typing_exact_ik_cache_owner_snapshot_v1,
)


SCHEMA = "rocell.typing_exact_ik_cache_owner_campaign.v1"
CASES = (
    "NORMAL_COLD_WARM",
    "RELOAD_RETIREMENT",
    "RESTART_RETIREMENT",
    "EXPLICIT_INVALIDATION",
    "RELOAD_REFRESH_FAILURE",
    "RESTART_REFRESH_FAILURE",
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_REPORT_FIELDS = {
    "schema", "campaign_id", "evidence_class", "environment", "case_count",
    "cases", "all_expected_outcomes", "decision_hashes_unchanged",
    "diagnostics_used_for_admission", "performance_authority",
    "controller_opened", "transport_opened", "controller_commands",
    "hardware_writes", "physical_movements", "physical_authority",
    "campaign_sha256",
}
_CASE_FIELDS = {
    "case", "status", "transition", "old_cache_retired",
    "execution_status", "receipt_sha256", "receipt_matches_reference",
    "after_owner_snapshot",
}
_EXPECTED = {
    "NORMAL_COLD_WARM": {
        "transition": "NONE", "retired": False, "execution": "PASSED",
        "receipt": True, "active": True, "ready": True, "cache": True,
        "reloads": 0, "restarts": 0, "invalidations": 0,
        "refresh_failures": 0,
    },
    "RELOAD_RETIREMENT": {
        "transition": "RELOAD", "retired": True, "execution": "PASSED",
        "receipt": True, "active": True, "ready": True, "cache": True,
        "reloads": 1, "restarts": 0, "invalidations": 0,
        "refresh_failures": 0,
    },
    "RESTART_RETIREMENT": {
        "transition": "RESTART", "retired": True, "execution": "PASSED",
        "receipt": True, "active": True, "ready": True, "cache": True,
        "reloads": 0, "restarts": 1, "invalidations": 0,
        "refresh_failures": 0,
    },
    "EXPLICIT_INVALIDATION": {
        "transition": "INVALIDATE", "retired": True, "execution": "BLOCKED",
        "receipt": None, "active": False, "ready": False, "cache": False,
        "reloads": 0, "restarts": 0, "invalidations": 1,
        "refresh_failures": 0,
    },
    "RELOAD_REFRESH_FAILURE": {
        "transition": "RELOAD", "retired": True, "execution": "BLOCKED",
        "receipt": None, "active": True, "ready": False, "cache": False,
        "reloads": 0, "restarts": 0, "invalidations": 0,
        "refresh_failures": 1,
    },
    "RESTART_REFRESH_FAILURE": {
        "transition": "RESTART", "retired": True, "execution": "BLOCKED",
        "receipt": None, "active": True, "ready": False, "cache": False,
        "reloads": 0, "restarts": 0, "invalidations": 0,
        "refresh_failures": 1,
    },
}


class TypingExactIkCacheOwnerCampaignV1Error(ValueError):
    """Owner campaign evidence is incomplete, inconsistent, or authoritative."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingExactIkCacheOwnerCampaignV1Error(
            f"{label} is not a SHA-256 digest"
        )
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 192
        or value != value.strip() or ":\\" in value or "://" in value
        or value.startswith(("/", "\\"))
    ):
        raise TypingExactIkCacheOwnerCampaignV1Error(
            f"{label} is invalid or path-like"
        )
    return value


def build_typing_exact_ik_cache_owner_campaign_v1(
    cases: Sequence[Mapping[str, Any]], *, campaign_id: str,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
        raise TypingExactIkCacheOwnerCampaignV1Error("cases are not a sequence")
    if len(cases) != len(CASES):
        raise TypingExactIkCacheOwnerCampaignV1Error("case count differs")
    normalized = []
    for index, item in enumerate(cases):
        if not isinstance(item, Mapping) or set(item) != _CASE_FIELDS:
            raise TypingExactIkCacheOwnerCampaignV1Error("case fields differ")
        case = item.get("case")
        if case != CASES[index]:
            raise TypingExactIkCacheOwnerCampaignV1Error("case order differs")
        expected = _EXPECTED[case]
        if item.get("status") != "PASS":
            raise TypingExactIkCacheOwnerCampaignV1Error("case status differs")
        if (
            item.get("transition") != expected["transition"]
            or item.get("old_cache_retired") is not expected["retired"]
            or item.get("execution_status") != expected["execution"]
            or item.get("receipt_matches_reference") is not expected["receipt"]
        ):
            raise TypingExactIkCacheOwnerCampaignV1Error(
                f"{case} outcome differs"
            )
        receipt = item.get("receipt_sha256")
        if expected["receipt"] is True:
            receipt = _digest(receipt, "receipt")
        elif receipt is not None:
            raise TypingExactIkCacheOwnerCampaignV1Error(
                f"{case} blocked receipt must be null"
            )
        try:
            snapshot = dict(parse_typing_exact_ik_cache_owner_snapshot_v1(
                item.get("after_owner_snapshot")
            ))
        except TypingExactIkCacheOwnerV1Error as exc:
            raise TypingExactIkCacheOwnerCampaignV1Error(
                f"{case} owner snapshot is invalid: {exc}"
            ) from exc
        if (
            snapshot["active"] is not expected["active"]
            or snapshot["ready"] is not expected["ready"]
            or snapshot["cache"]["active"] is not expected["cache"]
            or snapshot["reloads"] != expected["reloads"]
            or snapshot["restarts"] != expected["restarts"]
            or snapshot["invalidations"] != expected["invalidations"]
            or snapshot["refresh_failures"] != expected["refresh_failures"]
            or snapshot["retired_caches"] != int(expected["retired"])
        ):
            raise TypingExactIkCacheOwnerCampaignV1Error(
                f"{case} snapshot outcome differs"
            )
        normalized.append({
            "case": case,
            "status": "PASS",
            "transition": expected["transition"],
            "old_cache_retired": expected["retired"],
            "execution_status": expected["execution"],
            "receipt_sha256": receipt,
            "receipt_matches_reference": expected["receipt"],
            "after_owner_snapshot": snapshot,
        })
    successful_receipts = {
        item["receipt_sha256"] for item in normalized
        if item["receipt_sha256"] is not None
    }
    if len(successful_receipts) != 1:
        raise TypingExactIkCacheOwnerCampaignV1Error(
            "successful case receipts differ"
        )
    core = {
        "schema": SCHEMA,
        "campaign_id": _identifier(campaign_id, "campaign_id"),
        "evidence_class": "HOST_MEASURED_OFFLINE",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "case_count": len(normalized),
        "cases": normalized,
        "all_expected_outcomes": True,
        "decision_hashes_unchanged": True,
        "diagnostics_used_for_admission": False,
        "performance_authority": False,
        "controller_opened": False,
        "transport_opened": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_exact_ik_cache_owner_campaign_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise TypingExactIkCacheOwnerCampaignV1Error("campaign fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingExactIkCacheOwnerCampaignV1Error("campaign hash differs")
    rebuilt = build_typing_exact_ik_cache_owner_campaign_v1(
        value.get("cases"),
        campaign_id=value.get("campaign_id"),
        environment=value.get("environment"),
    )
    if rebuilt != dict(value):
        raise TypingExactIkCacheOwnerCampaignV1Error(
            "campaign derivation or authority fields differ"
        )
    return value


__all__ = [
    "CASES", "SCHEMA", "TypingExactIkCacheOwnerCampaignV1Error",
    "build_typing_exact_ik_cache_owner_campaign_v1",
    "parse_typing_exact_ik_cache_owner_campaign_v1",
]
