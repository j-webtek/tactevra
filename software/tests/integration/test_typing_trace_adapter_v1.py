from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/tests/unit"))

import test_typing_controller_bridge_v1 as bridge  # noqa: E402
import test_typing_fault_campaign_v1 as fault  # noqa: E402
from test_typing_shadow_pipeline_v1 import _inputs as shadow_inputs  # noqa: E402

from rocell.application.typing_shadow_pipeline_v1 import (  # noqa: E402
    run_typing_shadow_pipeline_v1,
)
from rocell.application.typing_trace_adapter_v1 import (  # noqa: E402
    TypingTraceAdapterV1Error,
    build_pc2_pc5_typing_trace_journal_v1,
)
from rocell.application.typing_trace_journal_v1 import (  # noqa: E402
    TRACE_STAGE_ORDER,
    replay_typing_trace_journal_v1,
)
from rocell.models import decode_model_motion_batch_v2_json  # noqa: E402


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _rehash(document: dict, field: str) -> None:
    document.pop(field, None)
    document[field] = hashlib.sha256(_canonical(document)).hexdigest()


def _compatible_inputs():
    inputs = shadow_inputs(("H",), "h")
    shadow = run_typing_shadow_pipeline_v1(**inputs)
    batch = decode_model_motion_batch_v2_json(inputs["payload"])
    _, schedule = bridge._inputs()
    horizon = deepcopy(bridge._horizon(schedule))
    horizon["request_id"] = batch.request_id
    _rehash(horizon, "rolling_horizon_sha256")

    preview = deepcopy(bridge._preview())
    preview["request_id"] = batch.request_id
    preview["bindings"]["rolling_horizon_sha256"] = horizon[
        "rolling_horizon_sha256"]
    preview["bindings"]["schedule_sha256"] = shadow["stage_hashes"][
        "typing_joint_schedule_sha256"]
    preview["dispatch_intent_sha256"] = hashlib.sha256(_canonical({
        "action_index": preview["action_index"],
        "target_id": preview["target_id"],
        "bindings": preview["bindings"],
        "ordered_wire_sha256": preview["ordered_wire_sha256"],
        "action_deadline_monotonic_ns": preview["action_deadline_monotonic_ns"],
    })).hexdigest()
    _rehash(preview, "typing_controller_preview_sha256")
    return inputs["payload"], shadow, horizon, preview, fault._report(), batch


def test_actual_pc2_pc5_contracts_form_one_identical_replay_trace():
    payload, shadow, horizon, preview, campaign, batch = _compatible_inputs()
    journal, artifacts = build_pc2_pc5_typing_trace_journal_v1(
        correlation_id="pc6-h-001",
        request_artifact=_canonical({"request_id": batch.request_id, "text": "h"}),
        batch_payload=payload,
        shadow_receipt=shadow,
        rolling_horizon=horizon,
        controller_preview=preview,
        fault_campaign=campaign,
    )
    assert tuple(artifacts) == TRACE_STAGE_ORDER
    assert journal["ordered_target_ids"] == ["H"]
    replay = replay_typing_trace_journal_v1(
        journal, artifacts, expected_correlation_id="pc6-h-001",
        expected_request_id=batch.request_id)
    assert replay["status"] == "IDENTICAL"
    assert replay["controller_commands"] == []
    assert replay["hardware_access"] is replay["physical_authority"] is False


@pytest.mark.parametrize(("mutation", "message"), [
    ("request", "request identity is crossed"),
    ("schedule", "planning lineage is crossed"),
    ("target", "action order is crossed"),
])
def test_adapter_rejects_crossed_pc2_pc4_lineage(mutation, message):
    payload, shadow, horizon, preview, campaign, batch = _compatible_inputs()
    if mutation == "request":
        preview["request_id"] = "request-crossed"
        _rehash(preview, "typing_controller_preview_sha256")
    elif mutation == "schedule":
        preview["bindings"]["schedule_sha256"] = "f" * 64
        preview["dispatch_intent_sha256"] = hashlib.sha256(_canonical({
            "action_index": preview["action_index"],
            "target_id": preview["target_id"],
            "bindings": preview["bindings"],
            "ordered_wire_sha256": preview["ordered_wire_sha256"],
            "action_deadline_monotonic_ns": preview["action_deadline_monotonic_ns"],
        })).hexdigest()
        _rehash(preview, "typing_controller_preview_sha256")
    else:
        horizon["current"]["target_id"] = "I"
        _rehash(horizon, "rolling_horizon_sha256")
        preview["bindings"]["rolling_horizon_sha256"] = horizon[
            "rolling_horizon_sha256"]
        preview["dispatch_intent_sha256"] = hashlib.sha256(_canonical({
            "action_index": preview["action_index"],
            "target_id": preview["target_id"],
            "bindings": preview["bindings"],
            "ordered_wire_sha256": preview["ordered_wire_sha256"],
            "action_deadline_monotonic_ns": preview["action_deadline_monotonic_ns"],
        })).hexdigest()
        _rehash(preview, "typing_controller_preview_sha256")
    with pytest.raises(TypingTraceAdapterV1Error, match=message):
        build_pc2_pc5_typing_trace_journal_v1(
            correlation_id="pc6-h-001",
            request_artifact=b"request",
            batch_payload=payload,
            shadow_receipt=shadow,
            rolling_horizon=horizon,
            controller_preview=preview,
            fault_campaign=campaign,
        )
