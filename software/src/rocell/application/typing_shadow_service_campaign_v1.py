"""Strict retained fault campaign for the bounded typing shadow service."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .operational_latency_reference_v1 import (
    validate_operational_benchmark_environment_v1,
)
from .typing_shadow_service_v1 import (
    TypingShadowServiceV1Error,
    parse_typing_shadow_service_receipt_v1,
    parse_typing_shadow_service_snapshot_v1,
)


SCHEMA = "rocell.typing_shadow_service_campaign.v1"
CASES = (
    "FIFO_COMPLETION",
    "CANCEL_BEFORE_ADMISSION",
    "RELOAD_STALE_REJECTION",
    "RESTART_STALE_REJECTION",
    "QUEUE_BOUND_REJECTION",
    "EXPLICIT_INVALIDATION",
    "UNEXPECTED_SHADOW_FAILURE",
    "ADMISSION_RELOAD_SERIALIZATION",
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
    "case", "status", "observed_outcome", "service_receipt",
    "shadow_receipt_sha256", "owner_runs", "transition_waited",
    "after_service_snapshot",
}
_EXPECTED = {
    "FIFO_COMPLETION": {
        "outcome": "SHADOW_COMPLETED", "receipt": True, "shadow": True,
        "runs": 1, "waited": False, "counter": "completed",
    },
    "CANCEL_BEFORE_ADMISSION": {
        "outcome": "CANCELED_BEFORE_ADMISSION", "receipt": True,
        "shadow": False, "runs": 0, "waited": False, "counter": "canceled",
    },
    "RELOAD_STALE_REJECTION": {
        "outcome": "STALE_GENERATION_REJECTED", "receipt": True,
        "shadow": False, "runs": 0, "waited": False,
        "counter": "stale_rejected", "reloads": 1,
    },
    "RESTART_STALE_REJECTION": {
        "outcome": "STALE_GENERATION_REJECTED", "receipt": True,
        "shadow": False, "runs": 0, "waited": False,
        "counter": "stale_rejected", "restarts": 1,
    },
    "QUEUE_BOUND_REJECTION": {
        "outcome": "SUBMISSION_REJECTED_QUEUE_FULL", "receipt": False,
        "shadow": False, "runs": 0, "waited": False, "counter": "canceled",
    },
    "EXPLICIT_INVALIDATION": {
        "outcome": "SERVICE_INVALIDATED", "receipt": False,
        "shadow": False, "runs": 0, "waited": False,
        "counter": "invalidated_queued", "invalidations": 1,
    },
    "UNEXPECTED_SHADOW_FAILURE": {
        "outcome": "SHADOW_REJECTED", "receipt": True, "shadow": False,
        "runs": 0, "waited": False, "counter": "shadow_rejected",
    },
    "ADMISSION_RELOAD_SERIALIZATION": {
        "outcome": "SHADOW_COMPLETED", "receipt": True, "shadow": True,
        "runs": 1, "waited": True, "counter": "completed", "reloads": 1,
    },
}


class TypingShadowServiceCampaignV1Error(ValueError):
    """Retained service evidence is incomplete or claims authority."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingShadowServiceCampaignV1Error(
            f"{label} is not a SHA-256 digest"
        )
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 192
        or value != value.strip() or ":\\" in value or "://" in value
        or value.startswith(("/", "\\"))
    ):
        raise TypingShadowServiceCampaignV1Error(
            f"{label} is invalid or path-like"
        )
    return value


def build_typing_shadow_service_campaign_v1(
    cases: Sequence[Mapping[str, Any]], *, campaign_id: str,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
        raise TypingShadowServiceCampaignV1Error("cases are not a sequence")
    if len(cases) != len(CASES):
        raise TypingShadowServiceCampaignV1Error("case count differs")
    normalized = []
    completed_shadow_hashes = set()
    for index, item in enumerate(cases):
        if not isinstance(item, Mapping) or set(item) != _CASE_FIELDS:
            raise TypingShadowServiceCampaignV1Error("case fields differ")
        case = item.get("case")
        if case != CASES[index]:
            raise TypingShadowServiceCampaignV1Error("case order differs")
        expected = _EXPECTED[case]
        if (
            item.get("status") != "PASS"
            or item.get("observed_outcome") != expected["outcome"]
            or item.get("owner_runs") != expected["runs"]
            or item.get("transition_waited") is not expected["waited"]
        ):
            raise TypingShadowServiceCampaignV1Error(
                f"{case} outcome differs"
            )
        receipt_value = item.get("service_receipt")
        if expected["receipt"]:
            try:
                receipt = dict(parse_typing_shadow_service_receipt_v1(
                    receipt_value
                ))
            except TypingShadowServiceV1Error as exc:
                raise TypingShadowServiceCampaignV1Error(
                    f"{case} service receipt is invalid: {exc}"
                ) from exc
            if receipt["status"] != expected["outcome"]:
                raise TypingShadowServiceCampaignV1Error(
                    f"{case} receipt outcome differs"
                )
        elif receipt_value is not None:
            raise TypingShadowServiceCampaignV1Error(
                f"{case} service receipt must be null"
            )
        else:
            receipt = None
        shadow_hash = item.get("shadow_receipt_sha256")
        if expected["shadow"]:
            shadow_hash = _digest(shadow_hash, "shadow receipt")
            if receipt is None or receipt["shadow_receipt_sha256"] != shadow_hash:
                raise TypingShadowServiceCampaignV1Error(
                    f"{case} shadow receipt differs"
                )
            completed_shadow_hashes.add(shadow_hash)
        elif shadow_hash is not None:
            raise TypingShadowServiceCampaignV1Error(
                f"{case} shadow receipt must be null"
            )
        try:
            snapshot = dict(parse_typing_shadow_service_snapshot_v1(
                item.get("after_service_snapshot")
            ))
        except TypingShadowServiceV1Error as exc:
            raise TypingShadowServiceCampaignV1Error(
                f"{case} service snapshot is invalid: {exc}"
            ) from exc
        if (
            snapshot[expected["counter"]] != 1
            or snapshot["reloads"] != expected.get("reloads", 0)
            or snapshot["restarts"] != expected.get("restarts", 0)
            or snapshot["invalidations"] != expected.get("invalidations", 0)
            or snapshot["queued"] != 0
        ):
            raise TypingShadowServiceCampaignV1Error(
                f"{case} snapshot outcome differs"
            )
        normalized.append({
            "case": case,
            "status": "PASS",
            "observed_outcome": expected["outcome"],
            "service_receipt": receipt,
            "shadow_receipt_sha256": shadow_hash,
            "owner_runs": expected["runs"],
            "transition_waited": expected["waited"],
            "after_service_snapshot": snapshot,
        })
    if len(completed_shadow_hashes) != 1:
        raise TypingShadowServiceCampaignV1Error(
            "completed shadow decision hashes differ"
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


def parse_typing_shadow_service_campaign_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise TypingShadowServiceCampaignV1Error("campaign fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingShadowServiceCampaignV1Error("campaign hash differs")
    rebuilt = build_typing_shadow_service_campaign_v1(
        value.get("cases"), campaign_id=value.get("campaign_id"),
        environment=value.get("environment"),
    )
    if rebuilt != dict(value):
        raise TypingShadowServiceCampaignV1Error(
            "campaign derivation or authority fields differ"
        )
    return value


__all__ = [
    "CASES", "SCHEMA", "TypingShadowServiceCampaignV1Error",
    "build_typing_shadow_service_campaign_v1",
    "parse_typing_shadow_service_campaign_v1",
]
