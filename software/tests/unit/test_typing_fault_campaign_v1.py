from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.typing_controller_bridge_v1 import (
    MAX_COMMAND_PAYLOAD_BYTES,
    TypingControllerBridgeV1Error,
    parse_typing_controller_preview_v1,
)
from rocell.application.typing_fault_campaign_v1 import (
    REQUIRED_CASES,
    TypingFaultCampaignV1Error,
    TypingFaultObservationV1,
    build_typing_fault_campaign_v1,
    build_typing_fault_observation_cache_v1,
    parse_typing_fault_campaign_v1,
    parse_typing_fault_observation_cache_v1,
)
from rocell.application.typing_rolling_horizon_v1 import (
    TypingRollingHorizonV1Error,
    parse_typing_rolling_horizon_v1,
)
from rocell.models.model_motion_batch_v2 import (
    MAX_BATCH_BYTES_V2,
    ModelMotionBatchV2Error,
    decode_model_motion_batch_v2_json,
)

import test_typing_controller_bridge_v1 as bridge


WORKSPACE = Path(__file__).resolve().parents[3]
BASIS = "a" * 64


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _observations(**case_changes):
    observations = []
    for case_id, (family, reason, outcome) in REQUIRED_CASES.items():
        values = dict(
            case_id=case_id, family=family, reason_code=reason,
            terminal_outcome=outcome,
            boundary_sha256=hashlib.sha256(case_id.encode()).hexdigest(),
        )
        if case_id in case_changes:
            values.update(case_changes[case_id])
        observations.append(TypingFaultObservationV1(**values))
    return observations


def _report():
    return build_typing_fault_campaign_v1(
        _observations(), qualification_basis_sha256=BASIS)


def test_complete_campaign_is_deterministic_schema_valid_and_zero_authority():
    first, second = _report(), _report()
    assert first == second
    assert first["family_count"] == 6
    assert first["case_count"] == 35
    assert [item["case_id"] for item in first["cases"]] == sorted(REQUIRED_CASES)
    assert all(value == 0 for value in first["invariants"].values())
    assert first["controller_commands"] == []
    assert first["transport_write_count"] == 0
    assert first["hardware_access"] is first["physical_authority"] is False
    parse_typing_fault_campaign_v1(first)
    schema = json.loads((
        WORKSPACE / "software/ai/schemas/typing_fault_campaign_v1.schema.json"
    ).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(first)


def test_observation_cache_is_schema_valid_hash_bound_and_zero_authority():
    cache = build_typing_fault_observation_cache_v1(
        _observations()[:3], qualification_basis_sha256=BASIS)
    parsed = parse_typing_fault_observation_cache_v1(
        cache, expected_qualification_basis_sha256=BASIS)
    assert parsed["entry_count"] == 3
    assert parsed["controller_commands"] == ()
    assert parsed["hardware_access"] is parsed["physical_authority"] is False
    schema = json.loads((
        WORKSPACE
        / "software/ai/schemas/typing_fault_observation_cache_v1.schema.json"
    ).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(cache)


@pytest.mark.parametrize("change", [
    {"exception_escaped": True},
    {"automatic_retry_allowed": True},
    {"order_preserved": False},
    {"silent_fallback_used": True},
    {"bounded_resources": False},
    {"controller_commands": ({"T": 102},)},
    {"hardware_access": True},
    {"physical_authority": True},
])
def test_each_safety_invariant_fails_closed(change):
    with pytest.raises(TypingFaultCampaignV1Error, match="PC5 invariants"):
        _observations(INPUT_MALFORMED=change)


def test_missing_duplicate_and_crossed_dispositions_reject():
    observations = _observations()
    with pytest.raises(TypingFaultCampaignV1Error, match="exact PC5 basis"):
        build_typing_fault_campaign_v1(
            observations[:-1], qualification_basis_sha256=BASIS)
    with pytest.raises(TypingFaultCampaignV1Error, match="duplicate"):
        build_typing_fault_campaign_v1(
            [*observations, observations[0]], qualification_basis_sha256=BASIS)
    with pytest.raises(TypingFaultCampaignV1Error, match="differs"):
        TypingFaultObservationV1(
            case_id="ACK_LATE", family="TRANSPORT_FEEDBACK",
            reason_code="ACK_LATE", terminal_outcome="REJECTED_BEFORE_DISPATCH",
            boundary_sha256="b" * 64,
        )


@pytest.mark.parametrize(("payload", "message"), [
    (b"{", "strict UTF-8 JSON"),
    (b'{"schema":1,"schema":2}', "duplicate JSON field"),
    (b"{}", "must contain exactly"),
    (b'{"x":NaN}', "non-finite JSON constant"),
    (b'{"x":Infinity}', "non-finite JSON constant"),
    ((b"[" * 40) + b"0" + (b"]" * 40), "JSON depth limit"),
])
def test_model_faults_are_normalized_without_uncaught_exceptions(payload, message):
    with pytest.raises(ModelMotionBatchV2Error, match=message):
        decode_model_motion_batch_v2_json(payload)


def test_oversized_model_input_rejects_before_decode():
    with pytest.raises(ModelMotionBatchV2Error, match="oversized"):
        decode_model_motion_batch_v2_json(b" " * (MAX_BATCH_BYTES_V2 + 1))


def test_rolling_horizon_resource_bound_rejects_even_with_valid_hash():
    _, schedule = bridge._inputs()
    horizon = bridge._horizon(schedule)
    horizon.pop("rolling_horizon_sha256")
    horizon["action_count"] = 65
    horizon["rolling_horizon_sha256"] = hashlib.sha256(_canonical(horizon)).hexdigest()
    with pytest.raises(TypingRollingHorizonV1Error, match="action accounting"):
        parse_typing_rolling_horizon_v1(horizon)


def test_controller_preview_payload_bound_is_stable_and_zero_io():
    document = deepcopy(bridge._preview())
    document.pop("typing_controller_preview_sha256")
    document["commands"][0]["payload_utf8"] = "x" * (MAX_COMMAND_PAYLOAD_BYTES + 1)
    document["typing_controller_preview_sha256"] = hashlib.sha256(
        _canonical(document)).hexdigest()
    with pytest.raises(TypingControllerBridgeV1Error, match="payload size"):
        parse_typing_controller_preview_v1(document)


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(physical_authority=True),
    lambda value: value["invariants"].update(automatic_retries=1),
    lambda value: value["cases"].reverse(),
    lambda value: value["cases"][0].update(reason_code="WRONG"),
])
def test_independently_rehashed_report_mutations_reject(mutation):
    document = deepcopy(_report())
    document.pop("typing_fault_campaign_sha256")
    mutation(document)
    document["typing_fault_campaign_sha256"] = hashlib.sha256(
        _canonical(document)).hexdigest()
    with pytest.raises(TypingFaultCampaignV1Error):
        parse_typing_fault_campaign_v1(document)
