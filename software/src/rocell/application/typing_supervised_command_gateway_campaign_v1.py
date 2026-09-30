"""Strict retained campaign for supervised model-command admission."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Mapping, Sequence

from .operational_latency_reference_v1 import validate_operational_benchmark_environment_v1
from .typing_supervised_command_gateway_v1 import (
    ADMITTED, REJECTED,
    parse_typing_supervised_command_admission_v1,
    parse_typing_supervised_command_gateway_snapshot_v1,
)

SCHEMA = "rocell.typing_supervised_command_gateway_campaign.v1"
CASES = ("WARM_ADMISSION", "FULL_SOLVE_ADMISSION", "QUEUE_BACKPRESSURE",
         "INPUT_REJECTION", "REQUEST_BOUND_BACKPRESSURE",
         "REQUALIFICATION_REJECTION", "FULL_SOLVE_CONTINUATION_ADMISSION",
         "QUALIFIED_REPLACEMENT_ADMISSION")
_HASH = re.compile(r"^[0-9a-f]{64}$")


class TypingSupervisedCommandGatewayCampaignV1Error(ValueError):
    """Gateway campaign evidence differs from the frozen matrix."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_typing_supervised_command_gateway_campaign_v1(
    cases: Sequence[Mapping[str, object]], *, campaign_id: str,
    environment: Mapping[str, object], reference_shadow_receipt_sha256: str,
) -> dict[str, object]:
    if not isinstance(campaign_id, str) or not campaign_id:
        raise TypingSupervisedCommandGatewayCampaignV1Error("campaign id differs")
    if _HASH.fullmatch(reference_shadow_receipt_sha256 or "") is None:
        raise TypingSupervisedCommandGatewayCampaignV1Error("reference receipt differs")
    if len(cases) != len(CASES):
        raise TypingSupervisedCommandGatewayCampaignV1Error("case count differs")
    expected = {
        "WARM_ADMISSION": (ADMITTED, "WARM", None, "SHADOW_COMPLETED", True),
        "FULL_SOLVE_ADMISSION": (ADMITTED, "FULL_SOLVE_ONLY", None, "SHADOW_COMPLETED", True),
        "QUEUE_BACKPRESSURE": (REJECTED, "WARM", "BACKPRESSURE_QUEUE_FULL", None, False),
        "INPUT_REJECTION": (REJECTED, "WARM", "INPUT_REJECTED", None, False),
        "REQUEST_BOUND_BACKPRESSURE": (REJECTED, "WARM", "BACKPRESSURE_REQUEST_BOUND", None, False),
        "REQUALIFICATION_REJECTION": (REJECTED, "REQUALIFICATION_REQUIRED", "REQUALIFICATION_REQUIRED", None, False),
        "FULL_SOLVE_CONTINUATION_ADMISSION": (ADMITTED, "FULL_SOLVE_ONLY", None, "SHADOW_COMPLETED", False),
        "QUALIFIED_REPLACEMENT_ADMISSION": (ADMITTED, "WARM", None, "SHADOW_COMPLETED", True),
    }
    normalized = []
    for index, item in enumerate(cases):
        fields = {"case", "admission_receipt", "gateway_snapshot",
                  "shadow_status", "shadow_receipt_sha256",
                  "reference_equivalent"}
        if not isinstance(item, Mapping) or set(item) != fields or item["case"] != CASES[index]:
            raise TypingSupervisedCommandGatewayCampaignV1Error("case fields differ")
        try:
            admission = dict(parse_typing_supervised_command_admission_v1(
                item["admission_receipt"]))
            snapshot = dict(parse_typing_supervised_command_gateway_snapshot_v1(
                item["gateway_snapshot"]))
        except ValueError as exc:
            raise TypingSupervisedCommandGatewayCampaignV1Error(
                f"{item['case']} receipt or snapshot differs: {exc}"
            ) from exc
        status, disposition, blocker, shadow_status, equivalent = expected[item["case"]]
        if (admission["status"], admission["disposition"], admission["blocker"],
                item["shadow_status"], item["reference_equivalent"]) != (
                status, disposition, blocker, shadow_status, equivalent):
            raise TypingSupervisedCommandGatewayCampaignV1Error(f"{item['case']} outcome differs")
        shadow = item["shadow_receipt_sha256"]
        if equivalent:
            if shadow != reference_shadow_receipt_sha256:
                raise TypingSupervisedCommandGatewayCampaignV1Error(f"{item['case']} reference differs")
        elif shadow_status is None:
            if shadow is not None:
                raise TypingSupervisedCommandGatewayCampaignV1Error(f"{item['case']} shadow differs")
        elif _HASH.fullmatch(shadow or "") is None:
            raise TypingSupervisedCommandGatewayCampaignV1Error(f"{item['case']} shadow differs")
        if admission["status"] == ADMITTED and snapshot["admitted"] < 1:
            raise TypingSupervisedCommandGatewayCampaignV1Error(f"{item['case']} counters differ")
        if admission["status"] == REJECTED and snapshot["rejected"] < 1:
            raise TypingSupervisedCommandGatewayCampaignV1Error(f"{item['case']} counters differ")
        normalized.append({"case": item["case"], "admission_receipt": admission,
                           "gateway_snapshot": snapshot,
                           "shadow_status": shadow_status,
                           "shadow_receipt_sha256": shadow,
                           "reference_equivalent": equivalent})
    core = {
        "schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_SYNTHETIC_INTEGRATION",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "actual_shared_emitter_used": True,
        "reference_shadow_receipt_sha256": reference_shadow_receipt_sha256,
        "case_count": len(normalized), "cases": normalized,
        "all_expected_outcomes": True, "decision_equivalence_preserved": True,
        "backpressure_is_nonretrying": True,
        "state_disposition_is_explicit": True,
        "automatic_retry_allowed": False,
        "executor_attached": False, "controller_opened": False,
        "transport_opened": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_supervised_command_gateway_campaign_v1(value: Mapping[str, object]):
    fields = {"schema", "campaign_id", "evidence_class", "environment",
              "actual_shared_emitter_used", "reference_shadow_receipt_sha256",
              "case_count", "cases", "all_expected_outcomes",
              "decision_equivalence_preserved", "backpressure_is_nonretrying",
              "state_disposition_is_explicit", "automatic_retry_allowed",
              "executor_attached", "controller_opened", "transport_opened",
              "controller_commands", "hardware_writes", "physical_movements",
              "physical_authority", "campaign_sha256"}
    if not isinstance(value, Mapping) or set(value) != fields or value.get("schema") != SCHEMA:
        raise TypingSupervisedCommandGatewayCampaignV1Error("campaign fields differ")
    unsigned = dict(value); supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingSupervisedCommandGatewayCampaignV1Error("campaign hash differs")
    rebuilt = build_typing_supervised_command_gateway_campaign_v1(
        value["cases"], campaign_id=value["campaign_id"],
        environment=value["environment"],
        reference_shadow_receipt_sha256=value["reference_shadow_receipt_sha256"])
    if rebuilt != dict(value):
        raise TypingSupervisedCommandGatewayCampaignV1Error("campaign derivation differs")
    return value


__all__ = ["CASES", "SCHEMA", "TypingSupervisedCommandGatewayCampaignV1Error",
           "build_typing_supervised_command_gateway_campaign_v1",
           "parse_typing_supervised_command_gateway_campaign_v1"]
