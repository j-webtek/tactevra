from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from rocell.application.camera_arrival_fault_campaign_v1 import (
    CameraArrivalFaultCampaignV1Error,
    parse_camera_arrival_fault_campaign_v1,
    run_camera_arrival_fault_campaign_v1,
)


ROOT = Path(__file__).resolve().parents[3]
RETAINED = ROOT / "software/ai/eval/camera_arrival_fault_campaign_v1.json"
VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/camera_arrival_fault_campaign_v1.schema.json"
).read_text(encoding="utf-8")))


def _hash(core: dict) -> str:
    return hashlib.sha256(json.dumps(
        core, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()


def test_actual_campaign_matches_retained_report_exactly():
    actual = run_camera_arrival_fault_campaign_v1(ROOT)
    retained = json.loads(RETAINED.read_text(encoding="utf-8"))
    assert actual == retained
    assert list(VALIDATOR.iter_errors(actual)) == []
    assert dict(parse_camera_arrival_fault_campaign_v1(actual)) == actual
    assert actual["case_count"] == actual["pass_count"] == 18
    assert actual["failure_count"] == 0
    assert actual["all_cases_passed"] is True
    assert actual["camera_opened"] is actual["transport_opened"] is False
    assert actual["controller_commands"] == []
    assert actual["hardware_writes"] == actual["physical_movements"] == 0
    assert actual["physical_authority"] is False


@pytest.mark.parametrize("mutation", ("order", "expected", "authority", "hash"))
def test_campaign_report_mutations_reject(mutation: str):
    value = json.loads(RETAINED.read_text(encoding="utf-8"))
    if mutation == "order":
        value["observations"][0], value["observations"][1] = (
            value["observations"][1], value["observations"][0]
        )
    elif mutation == "expected":
        value["observations"][0]["expected_detail"] = "WEAKENED"
    elif mutation == "authority":
        value["physical_authority"] = True
    else:
        value["campaign_sha256"] = "0" * 64
    if mutation != "hash":
        core = {key: item for key, item in value.items() if key != "campaign_sha256"}
        value["campaign_sha256"] = _hash(core)
    with pytest.raises(CameraArrivalFaultCampaignV1Error):
        parse_camera_arrival_fault_campaign_v1(value)
