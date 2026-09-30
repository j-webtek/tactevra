from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

import rocell.application.typing_supervised_command_gateway_campaign_v1 as campaign
import rocell.application.typing_supervised_command_gateway_v1 as gateway

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = Draft202012Validator(json.loads((ROOT / "software/ai/schemas/typing_supervised_command_gateway_campaign_v1.schema.json").read_text()))


def _environment():
    core = {"schema": "rocell.operational_benchmark_environment.v1", "captured_at_utc": "2026-09-30T09:00:00Z", "repository_commit": "a" * 40, "repository_dirty": False, "python_version": "3.10.10", "python_implementation": "CPython", "platform_system": "Windows", "platform_release": "10", "platform_machine": "AMD64", "logical_cpu_count": 24, "perf_counter_resolution_ns": 100, "benchmark_entrypoint": "software/scripts/run_typing_supervised_command_gateway_campaign_v1.py"}
    core["environment_sha256"] = campaign._sha(core); return core


def _snapshot(state, admitted, rejected, *, backpressure=0, state_rejected=0, inputs=0):
    core = {"schema": gateway.SNAPSHOT_SCHEMA, "supervisor_state": state,
            "supervisor_snapshot_sha256": "b" * 64, "admitted": admitted,
            "rejected": rejected, "backpressure_rejections": backpressure,
            "state_rejections": state_rejected, "input_rejections": inputs,
            "automatic_retry_allowed": False, "executor_attached": False,
            "controller_opened": False, "transport_opened": False,
            "controller_commands": [], "hardware_commands_generated": 0,
            "hardware_access": False, "physical_authority": False}
    return {**core, "gateway_snapshot_sha256": gateway._sha(core)}


def _cases(reference="a" * 64):
    expected = [(gateway.ADMITTED, "WARM", None, "SHADOW_COMPLETED", True),
                (gateway.ADMITTED, "FULL_SOLVE_ONLY", None, "SHADOW_COMPLETED", True),
                (gateway.REJECTED, "WARM", "BACKPRESSURE_QUEUE_FULL", None, False),
                (gateway.REJECTED, "WARM", "INPUT_REJECTED", None, False),
                (gateway.REJECTED, "WARM", "BACKPRESSURE_REQUEST_BOUND", None, False),
                (gateway.REJECTED, "REQUALIFICATION_REQUIRED", "REQUALIFICATION_REQUIRED", None, False),
                (gateway.ADMITTED, "FULL_SOLVE_ONLY", None, "SHADOW_COMPLETED", False),
                (gateway.ADMITTED, "WARM", None, "SHADOW_COMPLETED", True)]
    result = []
    for name, (status, state, blocker, shadow_status, equivalent) in zip(campaign.CASES, expected):
        receipt = gateway._receipt(status=status, request_id=name.lower(), disposition=state,
                                   request_sha256="c" * 64 if status == gateway.ADMITTED else None,
                                   blocker=blocker, supervisor_snapshot_sha256="b" * 64)
        rejected = int(status == gateway.REJECTED)
        result.append({"case": name, "admission_receipt": receipt,
                       "gateway_snapshot": _snapshot(state, int(not rejected), rejected,
                                                       backpressure=int(blocker in {"BACKPRESSURE_QUEUE_FULL", "BACKPRESSURE_REQUEST_BOUND"}),
                                                       state_rejected=int(blocker == "REQUALIFICATION_REQUIRED"),
                                                       inputs=int(blocker == "INPUT_REJECTED")),
                       "shadow_status": shadow_status,
                       "shadow_receipt_sha256": reference if equivalent else ("d" * 64 if shadow_status else None),
                       "reference_equivalent": equivalent})
    return result


def test_gateway_campaign_round_trip_and_zero_authority():
    reference = "a" * 64
    value = campaign.build_typing_supervised_command_gateway_campaign_v1(
        _cases(reference), campaign_id="campaign", environment=_environment(),
        reference_shadow_receipt_sha256=reference)
    VALIDATOR.validate(value)
    assert campaign.parse_typing_supervised_command_gateway_campaign_v1(value) == value
    assert value["backpressure_is_nonretrying"] is True
    assert value["hardware_writes"] == value["physical_movements"] == 0


def test_gateway_campaign_rejects_disposition_equivalence_and_hash_drift():
    cases = _cases(); cases[2]["admission_receipt"]["disposition"] = "FULL_SOLVE_ONLY"
    with pytest.raises(campaign.TypingSupervisedCommandGatewayCampaignV1Error):
        campaign.build_typing_supervised_command_gateway_campaign_v1(
            cases, campaign_id="campaign", environment=_environment(),
            reference_shadow_receipt_sha256="a" * 64)
    cases = _cases(); cases[-1]["shadow_receipt_sha256"] = "e" * 64
    with pytest.raises(campaign.TypingSupervisedCommandGatewayCampaignV1Error, match="reference"):
        campaign.build_typing_supervised_command_gateway_campaign_v1(
            cases, campaign_id="campaign", environment=_environment(),
            reference_shadow_receipt_sha256="a" * 64)
    value = campaign.build_typing_supervised_command_gateway_campaign_v1(
        _cases(), campaign_id="campaign", environment=_environment(),
        reference_shadow_receipt_sha256="a" * 64)
    changed = copy.deepcopy(value); changed["campaign_sha256"] = "f" * 64
    with pytest.raises(campaign.TypingSupervisedCommandGatewayCampaignV1Error, match="hash"):
        campaign.parse_typing_supervised_command_gateway_campaign_v1(changed)
