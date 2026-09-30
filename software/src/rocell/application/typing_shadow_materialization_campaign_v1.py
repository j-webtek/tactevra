"""Strict retained campaign for five-stage shadow materialization."""

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
from .typing_shadow_materialization_v1 import (
    STAGES,
    parse_typing_shadow_materialization_v1,
)

SCHEMA = "rocell.typing_shadow_materialization_campaign.v1"
CASES = (
    "COMPLETED_MATERIALIZATION",
    "REPEAT_RETRIEVAL",
    "POST_INVALIDATION_AUDIT_RETRIEVAL",
    "TAMPER_REJECTED",
    "QUEUED_HAS_NO_MATERIALIZATION",
    "CANCELED_HAS_NO_MATERIALIZATION",
    "STALE_HAS_NO_MATERIALIZATION",
    "UNKNOWN_HAS_NO_MATERIALIZATION",
)
EXPECTED = {
    "COMPLETED_MATERIALIZATION": "FIVE_STAGES_RETAINED",
    "REPEAT_RETRIEVAL": "IDENTICAL_MATERIALIZATION_RETRIEVED",
    "POST_INVALIDATION_AUDIT_RETRIEVAL": (
        "IDENTICAL_MATERIALIZATION_RETRIEVED"
    ),
    "TAMPER_REJECTED": "CONTENT_TAMPER_REJECTED",
    "QUEUED_HAS_NO_MATERIALIZATION": "NO_MATERIALIZATION_RETAINED",
    "CANCELED_HAS_NO_MATERIALIZATION": "NO_MATERIALIZATION_RETAINED",
    "STALE_HAS_NO_MATERIALIZATION": "NO_MATERIALIZATION_RETAINED",
    "UNKNOWN_HAS_NO_MATERIALIZATION": "NO_MATERIALIZATION_RETAINED",
}


class TypingShadowMaterializationCampaignV1Error(ValueError):
    """Materialization campaign evidence differs from its frozen matrix."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_typing_shadow_materialization_campaign_v1(
    cases: Sequence[Mapping[str, object]], *, campaign_id: str,
    environment: Mapping[str, object], reference_materialization_sha256: str,
) -> dict[str, object]:
    if not isinstance(campaign_id, str) or not campaign_id:
        raise TypingShadowMaterializationCampaignV1Error(
            "campaign id differs"
        )
    if (not isinstance(reference_materialization_sha256, str)
            or len(reference_materialization_sha256) != 64
            or len(cases) != len(CASES)):
        raise TypingShadowMaterializationCampaignV1Error(
            "campaign reference or case count differs"
        )
    accepted = {
        "COMPLETED_MATERIALIZATION", "REPEAT_RETRIEVAL",
        "POST_INVALIDATION_AUDIT_RETRIEVAL",
    }
    normalized = []
    for index, item in enumerate(cases):
        fields = {
            "case", "observed", "materialization", "error",
            "ledger_snapshot", "zero_authority_validated",
        }
        if (not isinstance(item, Mapping) or set(item) != fields
                or item["case"] != CASES[index]
                or item["observed"] != EXPECTED[item["case"]]
                or item["zero_authority_validated"] is not True):
            raise TypingShadowMaterializationCampaignV1Error(
                "case fields or outcome differ"
            )
        try:
            snapshot = dict(parse_typing_command_session_ledger_snapshot_v1(
                item["ledger_snapshot"]
            ))
        except ValueError as exc:
            raise TypingShadowMaterializationCampaignV1Error(
                f"{item['case']} ledger snapshot differs: {exc}"
            ) from exc
        if item["case"] in accepted:
            try:
                parsed = parse_typing_shadow_materialization_v1(
                    item["materialization"]
                )
            except ValueError as exc:
                raise TypingShadowMaterializationCampaignV1Error(
                    f"{item['case']} materialization differs: {exc}"
                ) from exc
            if (parsed["materialization_sha256"]
                    != reference_materialization_sha256
                    or set(parsed["stage_artifacts"]) != set(STAGES)
                    or item["error"] is not None):
                raise TypingShadowMaterializationCampaignV1Error(
                    f"{item['case']} reference differs"
                )
            materialization = json.loads(_canonical(item["materialization"]))
        else:
            if (item["materialization"] is not None
                    or not isinstance(item["error"], str)
                    or not item["error"]):
                raise TypingShadowMaterializationCampaignV1Error(
                    f"{item['case']} rejection differs"
                )
            materialization = None
        normalized.append({
            "case": item["case"], "observed": item["observed"],
            "materialization": materialization, "error": item["error"],
            "ledger_snapshot": snapshot, "zero_authority_validated": True,
        })
    core = {
        "schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_SYNTHETIC_INTEGRATION",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "actual_shared_emitter_used": True,
        "reference_materialization_sha256": reference_materialization_sha256,
        "stage_count": len(STAGES), "case_count": len(normalized),
        "cases": normalized, "all_expected_outcomes": True,
        "permit_review_ready": False, "automatic_retry_allowed": False,
        "eligible_for_executor": False, "permit_issued": False,
        "executor_attached": False, "controller_opened": False,
        "transport_opened": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_shadow_materialization_campaign_v1(
    value: Mapping[str, object],
):
    fields = {
        "schema", "campaign_id", "evidence_class", "environment",
        "actual_shared_emitter_used", "reference_materialization_sha256",
        "stage_count", "case_count", "cases", "all_expected_outcomes",
        "permit_review_ready", "automatic_retry_allowed",
        "eligible_for_executor", "permit_issued", "executor_attached",
        "controller_opened", "transport_opened", "controller_commands",
        "hardware_writes", "physical_movements", "physical_authority",
        "campaign_sha256",
    }
    if (not isinstance(value, Mapping) or set(value) != fields
            or value.get("schema") != SCHEMA):
        raise TypingShadowMaterializationCampaignV1Error(
            "campaign fields differ"
        )
    unsigned = dict(value)
    supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingShadowMaterializationCampaignV1Error(
            "campaign hash differs"
        )
    rebuilt = build_typing_shadow_materialization_campaign_v1(
        value["cases"], campaign_id=value["campaign_id"],
        environment=value["environment"],
        reference_materialization_sha256=value[
            "reference_materialization_sha256"
        ],
    )
    if rebuilt != dict(value):
        raise TypingShadowMaterializationCampaignV1Error(
            "campaign derivation differs"
        )
    return value


__all__ = [
    "CASES", "EXPECTED", "SCHEMA",
    "TypingShadowMaterializationCampaignV1Error",
    "build_typing_shadow_materialization_campaign_v1",
    "parse_typing_shadow_materialization_campaign_v1",
]
