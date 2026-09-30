"""Strict retained campaign for immutable shadow-artifact retention."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence

from .operational_latency_reference_v1 import (
    validate_operational_benchmark_environment_v1,
)
from .typing_shadow_artifact_store_v1 import (
    parse_typing_shadow_artifact_store_snapshot_v1,
)
from .typing_shadow_pipeline_v1 import parse_typing_shadow_pipeline_v1

SCHEMA = "rocell.typing_shadow_artifact_store_campaign.v1"
CASES = (
    "RUNTIME_RETENTION",
    "REPEAT_RETRIEVAL",
    "WRONG_HASH_REJECTED",
    "UNKNOWN_REQUEST_REJECTED",
    "REPLACEMENT_REJECTED",
    "CAPACITY_EXHAUSTION",
    "CANCELED_HAS_NO_ARTIFACT",
    "STALE_HAS_NO_ARTIFACT",
)
EXPECTED = {
    "RUNTIME_RETENTION": "ARTIFACT_RETAINED",
    "REPEAT_RETRIEVAL": "IDENTICAL_ARTIFACT_RETRIEVED",
    "WRONG_HASH_REJECTED": "CONTENT_ADDRESS_REJECTED",
    "UNKNOWN_REQUEST_REJECTED": "UNKNOWN_REQUEST_REJECTED",
    "REPLACEMENT_REJECTED": "REPLACEMENT_REJECTED",
    "CAPACITY_EXHAUSTION": "CAPACITY_REJECTED",
    "CANCELED_HAS_NO_ARTIFACT": "NO_ARTIFACT_RETAINED",
    "STALE_HAS_NO_ARTIFACT": "NO_ARTIFACT_RETAINED",
}


class TypingShadowArtifactStoreCampaignV1Error(ValueError):
    """Artifact-retention campaign evidence differs from the frozen matrix."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_typing_shadow_artifact_store_campaign_v1(
    cases: Sequence[Mapping[str, object]], *, campaign_id: str,
    environment: Mapping[str, object], reference_artifact_sha256: str,
) -> dict[str, object]:
    if not isinstance(campaign_id, str) or not campaign_id:
        raise TypingShadowArtifactStoreCampaignV1Error("campaign id differs")
    if (not isinstance(reference_artifact_sha256, str)
            or len(reference_artifact_sha256) != 64):
        raise TypingShadowArtifactStoreCampaignV1Error("reference differs")
    if len(cases) != len(CASES):
        raise TypingShadowArtifactStoreCampaignV1Error("case count differs")
    retained_cases = {"RUNTIME_RETENTION", "REPEAT_RETRIEVAL"}
    normalized = []
    for index, item in enumerate(cases):
        fields = {
            "case", "observed", "artifact", "error", "store_snapshot",
            "zero_authority_validated",
        }
        if (not isinstance(item, Mapping) or set(item) != fields
                or item["case"] != CASES[index]
                or item["observed"] != EXPECTED[item["case"]]
                or item["zero_authority_validated"] is not True):
            raise TypingShadowArtifactStoreCampaignV1Error(
                "case fields or outcome differ"
            )
        try:
            snapshot = dict(parse_typing_shadow_artifact_store_snapshot_v1(
                item["store_snapshot"]
            ))
        except ValueError as exc:
            raise TypingShadowArtifactStoreCampaignV1Error(
                f"{item['case']} snapshot differs: {exc}"
            ) from exc
        if item["case"] in retained_cases:
            try:
                parsed_artifact = parse_typing_shadow_pipeline_v1(
                    item["artifact"]
                )
            except ValueError as exc:
                raise TypingShadowArtifactStoreCampaignV1Error(
                    f"{item['case']} artifact differs: {exc}"
                ) from exc
            if (parsed_artifact["typing_shadow_pipeline_sha256"]
                    != reference_artifact_sha256 or item["error"] is not None):
                raise TypingShadowArtifactStoreCampaignV1Error(
                    f"{item['case']} reference differs"
                )
            artifact = json.loads(_canonical(item["artifact"]))
        else:
            if (item["artifact"] is not None
                    or not isinstance(item["error"], str)
                    or not item["error"]):
                raise TypingShadowArtifactStoreCampaignV1Error(
                    f"{item['case']} rejection differs"
                )
            artifact = None
        normalized.append({
            "case": item["case"], "observed": item["observed"],
            "artifact": artifact, "error": item["error"],
            "store_snapshot": snapshot, "zero_authority_validated": True,
        })
    core = {
        "schema": SCHEMA,
        "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_SYNTHETIC_INTEGRATION",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "actual_shared_emitter_used": True,
        "reference_artifact_sha256": reference_artifact_sha256,
        "case_count": len(normalized),
        "cases": normalized,
        "all_expected_outcomes": True,
        "content_addressed_retrieval": True,
        "mutable_replacement_allowed": False,
        "automatic_retry_allowed": False,
        "executor_attached": False,
        "controller_opened": False,
        "transport_opened": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_shadow_artifact_store_campaign_v1(
    value: Mapping[str, object],
):
    fields = {
        "schema", "campaign_id", "evidence_class", "environment",
        "actual_shared_emitter_used", "reference_artifact_sha256",
        "case_count", "cases", "all_expected_outcomes",
        "content_addressed_retrieval", "mutable_replacement_allowed",
        "automatic_retry_allowed", "executor_attached", "controller_opened",
        "transport_opened", "controller_commands", "hardware_writes",
        "physical_movements", "physical_authority", "campaign_sha256",
    }
    if (not isinstance(value, Mapping) or set(value) != fields
            or value.get("schema") != SCHEMA):
        raise TypingShadowArtifactStoreCampaignV1Error(
            "campaign fields differ"
        )
    unsigned = dict(value)
    supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingShadowArtifactStoreCampaignV1Error("campaign hash differs")
    rebuilt = build_typing_shadow_artifact_store_campaign_v1(
        value["cases"], campaign_id=value["campaign_id"],
        environment=value["environment"],
        reference_artifact_sha256=value["reference_artifact_sha256"],
    )
    if rebuilt != dict(value):
        raise TypingShadowArtifactStoreCampaignV1Error(
            "campaign derivation differs"
        )
    return value


__all__ = [
    "CASES", "EXPECTED", "SCHEMA",
    "TypingShadowArtifactStoreCampaignV1Error",
    "build_typing_shadow_artifact_store_campaign_v1",
    "parse_typing_shadow_artifact_store_campaign_v1",
]
