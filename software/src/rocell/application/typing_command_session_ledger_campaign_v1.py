"""Strict retained campaign for command-session lifecycle correlation."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence

from .operational_latency_reference_v1 import validate_operational_benchmark_environment_v1
from .typing_command_session_ledger_v1 import (
    parse_typing_command_session_ledger_snapshot_v1,
    parse_typing_command_session_receipt_v1,
)

SCHEMA = "rocell.typing_command_session_ledger_campaign.v1"
CASES = (
    "COMPLETED_CHAIN", "IDEMPOTENT_REPLAY", "CANCELED_CHAIN",
    "STALE_CHAIN", "ADMISSION_REJECTION", "CAPACITY_REJECTION",
    "CONFLICTING_DUPLICATE_REJECTION", "TERMINAL_LOOKUP_REPLAY",
)


class TypingCommandSessionLedgerCampaignV1Error(ValueError):
    """Session-ledger campaign evidence differs from the frozen matrix."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_typing_command_session_ledger_campaign_v1(
    cases: Sequence[Mapping[str, object]], *, campaign_id: str,
    environment: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(campaign_id, str) or not campaign_id:
        raise TypingCommandSessionLedgerCampaignV1Error("campaign id differs")
    if len(cases) != len(CASES):
        raise TypingCommandSessionLedgerCampaignV1Error("case count differs")
    expected = {
        "COMPLETED_CHAIN": ("QUEUED", "SHADOW_COMPLETED", "TERMINAL_RECORDED"),
        "IDEMPOTENT_REPLAY": ("QUEUED", "QUEUED", "IDENTICAL_RECEIPT_REPLAYED"),
        "CANCELED_CHAIN": ("QUEUED", "CANCELED_BEFORE_ADMISSION", "TERMINAL_RECORDED"),
        "STALE_CHAIN": ("QUEUED", "STALE_GENERATION_REJECTED", "TERMINAL_RECORDED"),
        "ADMISSION_REJECTION": ("ADMISSION_REJECTED", "ADMISSION_REJECTED", "TERMINAL_RECORDED"),
        "CAPACITY_REJECTION": ("LEDGER_CAPACITY_REJECTED", "LEDGER_CAPACITY_REJECTED", "TERMINAL_NOT_RETAINED"),
        "CONFLICTING_DUPLICATE_REJECTION": ("QUEUED", None, "CONFLICT_REJECTED"),
        "TERMINAL_LOOKUP_REPLAY": ("QUEUED", "SHADOW_COMPLETED", "IDENTICAL_RECEIPT_REPLAYED"),
    }
    normalized = []
    for index, item in enumerate(cases):
        fields = {"case", "initial_receipt", "outcome_receipt", "observed",
                  "ledger_snapshot", "chain_validated"}
        if (not isinstance(item, Mapping) or set(item) != fields
                or item["case"] != CASES[index]):
            raise TypingCommandSessionLedgerCampaignV1Error("case fields differ")
        try:
            initial = dict(parse_typing_command_session_receipt_v1(
                item["initial_receipt"]))
            outcome = (None if item["outcome_receipt"] is None else
                       dict(parse_typing_command_session_receipt_v1(
                           item["outcome_receipt"])))
            snapshot = dict(parse_typing_command_session_ledger_snapshot_v1(
                item["ledger_snapshot"]))
        except ValueError as exc:
            raise TypingCommandSessionLedgerCampaignV1Error(
                f"{item['case']} evidence differs: {exc}"
            ) from exc
        first_status, outcome_status, observed = expected[item["case"]]
        if (initial["status"] != first_status
                or (outcome["status"] if outcome else None) != outcome_status
                or item["observed"] != observed
                or item["chain_validated"] is not True):
            raise TypingCommandSessionLedgerCampaignV1Error(
                f"{item['case']} outcome differs"
            )
        if outcome is not None and outcome_status not in {
            "QUEUED", "ADMISSION_REJECTED", "LEDGER_CAPACITY_REJECTED"
        }:
            if outcome["previous_session_receipt_sha256"] != initial[
                "session_receipt_sha256"
            ]:
                raise TypingCommandSessionLedgerCampaignV1Error(
                    f"{item['case']} chain differs"
                )
        if item["case"] in {"IDEMPOTENT_REPLAY", "ADMISSION_REJECTION",
                             "CAPACITY_REJECTION"} and outcome != initial:
            raise TypingCommandSessionLedgerCampaignV1Error(
                f"{item['case']} replay differs"
            )
        normalized.append({"case": item["case"], "initial_receipt": initial,
                           "outcome_receipt": outcome, "observed": observed,
                           "ledger_snapshot": snapshot,
                           "chain_validated": True})
    core = {
        "schema": SCHEMA, "campaign_id": campaign_id,
        "evidence_class": "HOST_MEASURED_SYNTHETIC_INTEGRATION",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "actual_shared_emitter_used": True,
        "case_count": len(normalized), "cases": normalized,
        "all_expected_outcomes": True,
        "admission_to_terminal_chain_preserved": True,
        "identical_replay_is_idempotent": True,
        "conflicting_replay_fails_closed": True,
        "automatic_retry_allowed": False,
        "executor_attached": False, "controller_opened": False,
        "transport_opened": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_command_session_ledger_campaign_v1(value: Mapping[str, object]):
    fields = {"schema", "campaign_id", "evidence_class", "environment",
              "actual_shared_emitter_used", "case_count", "cases",
              "all_expected_outcomes", "admission_to_terminal_chain_preserved",
              "identical_replay_is_idempotent",
              "conflicting_replay_fails_closed", "automatic_retry_allowed",
              "executor_attached", "controller_opened", "transport_opened",
              "controller_commands", "hardware_writes", "physical_movements",
              "physical_authority", "campaign_sha256"}
    if (not isinstance(value, Mapping) or set(value) != fields
            or value.get("schema") != SCHEMA):
        raise TypingCommandSessionLedgerCampaignV1Error("campaign fields differ")
    unsigned = dict(value); supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingCommandSessionLedgerCampaignV1Error("campaign hash differs")
    rebuilt = build_typing_command_session_ledger_campaign_v1(
        value["cases"], campaign_id=value["campaign_id"],
        environment=value["environment"])
    if rebuilt != dict(value):
        raise TypingCommandSessionLedgerCampaignV1Error(
            "campaign derivation differs"
        )
    return value


__all__ = ["CASES", "SCHEMA", "TypingCommandSessionLedgerCampaignV1Error",
           "build_typing_command_session_ledger_campaign_v1",
           "parse_typing_command_session_ledger_campaign_v1"]
