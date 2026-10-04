from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "software/ai"), str(ROOT / "software/src"),
                str(ROOT / "software/tests/integration")]
import test_typing_shadow_pipeline_v1 as fixture  # noqa: E402

from rocell.models import decode_model_motion_batch_v2_json  # noqa: E402
from rocell_ai.profiled_service_ingress_v2 import (  # noqa: E402
    ProfiledServiceIngressV2Error, emit_profiled_service_inputs_v2)


def test_actual_shared_emitter_preserves_order_and_zero_authority():
    source = fixture._inputs(("H", "H", "1", "PERIOD"), "hh1.")
    emitted = emit_profiled_service_inputs_v2(
        source, batch_id="profiled-ingress-test", request_id="profiled-request")
    batch = decode_model_motion_batch_v2_json(emitted["payload"])
    assert [item.target_id for item in batch.proposals] == ["H", "H", "1", "PERIOD"]
    assert batch.request_id == json.loads(emitted["payload"])["request_id"] == "profiled-request"
    assert batch.intent_plan_sha256 == source["intent_plan"].plan_hash
    authority = batch.unsigned_dict()
    assert authority["controller_commands"] == []
    assert authority["hardware_access"] is authority["physical_authority"] is False
    assert {key for key in emitted if key != "payload"} == {key for key in source if key != "payload"}


@pytest.mark.parametrize("changes, match", [
    ({"payload": b""}, "missing"),
    ({"intent_plan": None}, "missing"),
])
def test_missing_fixture_inputs_fail_closed(changes, match):
    source = fixture._inputs()
    source.update(changes)
    with pytest.raises(ProfiledServiceIngressV2Error, match=match):
        emit_profiled_service_inputs_v2(source, batch_id="batch", request_id="request")
