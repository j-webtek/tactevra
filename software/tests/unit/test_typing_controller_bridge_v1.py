from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest
import jsonschema

from rocell.application.typing_controller_bridge_v1 import (
    TypingControllerActionQualificationV1,
    TypingControllerBridgeV1Error,
    TypingControllerEncodingProfileV1,
    parse_typing_controller_preview_v1,
    preview_typing_controller_action_v1,
)
from rocell.application.typing_joint_schedule_v1 import compile_typing_joint_schedule_v1

import test_typing_joint_schedule_v1 as support


WORKSPACE = Path(__file__).resolve().parents[3]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _inputs():
    trajectory = support._plan()
    schedule = compile_typing_joint_schedule_v1(
        trajectory, support._ik_report(trajectory), support._profile())
    return trajectory, schedule


def _horizon(schedule, **changes):
    binding = {
        "schema": "rocell.typing_observed_execution_binding.v1",
        "observed_start_state_sha256": "2" * 64,
        "feedback_receipt_sha256": "3" * 64,
        "configuration_epoch_sha256": "4" * 64,
        "calibration_snapshot_sha256": "5" * 64,
        "tool_profile_sha256": "6" * 64,
        "dynamics_profile_sha256": schedule.profile.profile_sha256,
        "controller_session_id": "session-1",
        "valid_until_monotonic_ns": 9_000_000_000_000,
    }
    binding_sha = hashlib.sha256(_canonical(binding)).hexdigest()
    current = {
        "action_index": 0, "target_id": "H", "action_sha256": "7" * 64,
        "proposal_sha256": "8" * 64, "role": "CURRENT", "permit_id": None,
        "permit_issued": False, "controller_commands": [],
        "hardware_commands_generated": 0, "hardware_access": False,
        "physical_authority": False,
    }
    value = {
        "schema": "rocell.typing_rolling_horizon.v1", "phase": "PRE_DISPATCH",
        "request_id": "request-1", "plan_sha256": "a" * 64,
        "configuration_epoch_sha256": "4" * 64, "binding": binding,
        "binding_sha256": binding_sha, "action_count": 1, "action_index": 0,
        "current": current, "preview": None,
        "deadline_monotonic_ns": 8_000_000_000_000,
        "dispatch_intent_sha256": None, "completion_receipt_sha256": None,
        "invalidation_reason": None, "restart_reconciliation": None,
        "commit_horizon": 1, "preview_horizon": 1,
        "automatic_retry_allowed": False, "controller_commands": [],
        "hardware_commands_generated": 0, "hardware_access": False,
        "physical_authority": False,
    }
    value.update(changes)
    value["rolling_horizon_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
    return value


def _profile(**changes):
    values = dict(
        profile_id="typing-waveshare-t102-v1", vendor_source_sha256="9" * 64,
        controller_joint_mapping_sha256="b" * 64,
        controller_session_id="session-1", configuration_epoch_sha256="4" * 64,
        fixed_gripper_rad=0.25, speed=20, acceleration=1,
        feedback_timeout_ns=1_000_000_000,
    )
    values.update(changes)
    return TypingControllerEncodingProfileV1(**values)


def _qualification(horizon, **changes):
    values = dict(
        rolling_horizon_sha256=horizon["rolling_horizon_sha256"],
        collision_qualification_sha256="c" * 64,
        execution_envelope_sha256="d" * 64,
        execution_permit_sha256="e" * 64,
        action_deadline_monotonic_ns=horizon["deadline_monotonic_ns"],
    )
    values.update(changes)
    return TypingControllerActionQualificationV1(**values)


def _preview():
    trajectory, schedule = _inputs()
    horizon = _horizon(schedule)
    return preview_typing_controller_action_v1(
        schedule, trajectory, horizon, _qualification(horizon), _profile(),
        now_monotonic_ns=1_000,
    )


def test_current_action_becomes_exact_ordered_t102_bytes_with_zero_authority():
    preview = _preview()
    assert preview["status"] == "ZERO_WRITE_T102_ACTION_PREVIEW"
    assert preview["action_index"] == 0 and preview["target_id"] == "H"
    assert preview["command_count"] == 3
    assert [item["sample_sequence"] for item in preview["commands"]] == [1, 2, 3]
    assert preview["commands"][0]["payload_utf8"] == (
        '{"T":102,"base":0.2,"shoulder":0.1,"elbow":0.06666666666666667,'
        '"wrist":0.05,"roll":0.04,"hand":0.25,"spd":20,"acc":1}\n'
    )
    assert preview["transport_opened"] is False
    assert preview["transport_write_count"] == 0
    assert preview["submitted_bytes"] == []
    assert preview["permit_consumed"] is False
    assert preview["automatic_retry_allowed"] is False
    assert preview["physical_authority"] is False
    parse_typing_controller_preview_v1(preview)
    schema = json.loads((
        WORKSPACE / "software/ai/schemas/typing_controller_preview_v1.schema.json"
    ).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(preview)


def test_all_arm_owned_lineages_and_feedback_deadline_are_sealed():
    preview = _preview()
    assert preview["bindings"]["schedule_sha256"] == _inputs()[1].schedule_sha256
    assert preview["bindings"]["collision_qualification_sha256"] == "c" * 64
    assert preview["bindings"]["execution_envelope_sha256"] == "d" * 64
    assert preview["bindings"]["execution_permit_sha256"] == "e" * 64
    ack = preview["acknowledgement_requirements"]
    assert ack["t102_acknowledgement"] == "OPTIONAL_NOT_ASSUMED"
    assert ack["required_feedback_request_type"] == 105
    assert ack["required_feedback_response_type"] == 1051
    assert ack["completion_requires_correlated_feedback"] is True
    assert ack["feedback_deadline_monotonic_ns"] <= preview["action_deadline_monotonic_ns"]


def test_preview_is_deterministic_and_each_wire_hash_is_reconstructible():
    first = _preview()
    second = _preview()
    assert first == second
    for command in first["commands"]:
        raw = command["payload_utf8"].encode()
        assert hashlib.sha256(raw).hexdigest() == command["payload_sha256"]
        assert len(raw) == command["payload_bytes"]


def test_golden_bytes_are_frozen_and_repeated_target_action_stays_distinct():
    first = _preview()
    golden = json.loads((
        WORKSPACE / "software/tests/fixtures/typing_controller_golden_bytes_v1.json"
    ).read_text(encoding="utf-8"))
    assert [item["payload_utf8"] for item in first["commands"]] == golden["payload_utf8"]
    assert [item["payload_sha256"] for item in first["commands"]] == golden["payload_sha256"]
    assert first["ordered_wire_sha256"] == golden["ordered_wire_sha256"]

    original_trajectory = support._plan()
    repeated_trajectory = replace(
        original_trajectory,
        phase_waypoints=tuple(
            replace(item, action_index=1) if item.action_index is not None else item
            for item in original_trajectory.phase_waypoints
        ),
        screening_samples=tuple(
            replace(item, action_index=1) if item.action_index is not None else item
            for item in original_trajectory.screening_samples
        ),
    )
    repeated_schedule = compile_typing_joint_schedule_v1(
        repeated_trajectory, support._ik_report(repeated_trajectory), support._profile())
    repeated_horizon = _horizon(repeated_schedule)
    repeated_horizon.pop("rolling_horizon_sha256")
    repeated_horizon["action_count"] = 2
    repeated_horizon["action_index"] = 1
    repeated_horizon["current"]["action_index"] = 1
    repeated_horizon["current"]["action_sha256"] = "f" * 64
    repeated_horizon["rolling_horizon_sha256"] = hashlib.sha256(
        _canonical(repeated_horizon)).hexdigest()
    repeated = preview_typing_controller_action_v1(
        repeated_schedule, repeated_trajectory, repeated_horizon,
        _qualification(repeated_horizon), _profile(), now_monotonic_ns=1_000)
    assert repeated["target_id"] == first["target_id"] == "H"
    assert repeated["action_index"] == 1
    assert repeated["dispatch_intent_sha256"] != first["dispatch_intent_sha256"]


@pytest.mark.parametrize(("profile_change", "message"), [
    ({"controller_session_id": "other"}, "session or epoch"),
    ({"configuration_epoch_sha256": "f" * 64}, "session or epoch"),
])
def test_controller_session_and_epoch_crossing_reject(profile_change, message):
    trajectory, schedule = _inputs()
    horizon = _horizon(schedule)
    with pytest.raises(TypingControllerBridgeV1Error, match=message):
        preview_typing_controller_action_v1(
            schedule, trajectory, horizon, _qualification(horizon),
            _profile(**profile_change), now_monotonic_ns=1_000)


def test_crossed_horizon_trajectory_schedule_and_dynamics_reject():
    trajectory, schedule = _inputs()
    horizon = _horizon(schedule)
    with pytest.raises(TypingControllerBridgeV1Error, match="horizon"):
        preview_typing_controller_action_v1(
            schedule, trajectory, horizon,
            _qualification(horizon, rolling_horizon_sha256="f" * 64),
            _profile(), now_monotonic_ns=1_000)
    with pytest.raises(TypingControllerBridgeV1Error, match="typing plan"):
        preview_typing_controller_action_v1(
            schedule, replace(trajectory, source_plan_sha256="f" * 64), horizon,
            _qualification(horizon), _profile(), now_monotonic_ns=1_000)
    bad_schedule = replace(schedule, source_trajectory_plan_sha256="f" * 64)
    with pytest.raises(TypingControllerBridgeV1Error, match="trajectory"):
        preview_typing_controller_action_v1(
            bad_schedule, trajectory, horizon, _qualification(horizon),
            _profile(), now_monotonic_ns=1_000)
    crossed_samples = list(schedule.samples)
    crossed_samples[1] = replace(crossed_samples[1], target_id="X")
    crossed_schedule = replace(schedule, samples=tuple(crossed_samples))
    with pytest.raises(TypingControllerBridgeV1Error, match="semantics"):
        preview_typing_controller_action_v1(
            crossed_schedule, trajectory, horizon, _qualification(horizon),
            _profile(), now_monotonic_ns=1_000)


def test_non_predispatch_expired_and_too_short_feedback_window_reject():
    trajectory, schedule = _inputs()
    dispatched = _horizon(schedule, phase="DISPATCH_INTENT_RETAINED",
                          dispatch_intent_sha256="f" * 64)
    with pytest.raises(TypingControllerBridgeV1Error, match="pre-dispatch"):
        preview_typing_controller_action_v1(
            schedule, trajectory, dispatched, _qualification(dispatched),
            _profile(), now_monotonic_ns=1_000)
    horizon = _horizon(schedule, deadline_monotonic_ns=999)
    with pytest.raises(TypingControllerBridgeV1Error, match="expired"):
        preview_typing_controller_action_v1(
            schedule, trajectory, horizon, _qualification(horizon), _profile(),
            now_monotonic_ns=1_000)
    horizon = _horizon(schedule, deadline_monotonic_ns=2_000)
    with pytest.raises(TypingControllerBridgeV1Error, match="feedback window"):
        preview_typing_controller_action_v1(
            schedule, trajectory, horizon, _qualification(horizon), _profile(),
            now_monotonic_ns=1_000)


@pytest.mark.parametrize("change", [
    {"speed": 0}, {"acceleration": 0}, {"fixed_gripper_rad": float("nan")},
])
def test_invalid_arm_owned_firmware_settings_reject(change):
    with pytest.raises(ValueError):
        _profile(**change)


@pytest.mark.parametrize("mutation", ["payload", "authority", "binding", "order"])
def test_parser_rejects_independently_rehashed_mutations(mutation):
    document = deepcopy(_preview())
    document.pop("typing_controller_preview_sha256")
    if mutation == "payload":
        document["commands"][0]["payload_utf8"] = '{"T":999}\n'
    elif mutation == "authority":
        document["physical_authority"] = True
    elif mutation == "binding":
        document["bindings"]["execution_permit_sha256"] = "f" * 64
    else:
        document["commands"][0]["ordinal"] = 1
    document["typing_controller_preview_sha256"] = hashlib.sha256(
        _canonical(document)).hexdigest()
    with pytest.raises(TypingControllerBridgeV1Error):
        parse_typing_controller_preview_v1(document)
