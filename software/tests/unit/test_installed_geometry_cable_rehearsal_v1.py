from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from rocell.application.installed_geometry_cable_rehearsal_v1 import (
    InstalledGeometryCableRehearsalV1Error,
    build_synthetic_installed_collision_profile_v1,
    parse_installed_geometry_cable_rehearsal_v1,
    run_installed_geometry_cable_rehearsal_v1,
)


ROOT = Path(__file__).resolve().parents[3]
RETAINED = ROOT / "software/ai/eval/installed_geometry_cable_rehearsal_v1.json"
VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/installed_geometry_cable_rehearsal_v1.schema.json"
).read_text(encoding="utf-8")))


def _hash(core: dict) -> str:
    return hashlib.sha256(json.dumps(
        core, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()


def test_campaign_matches_retained_report_and_exact_diagnostics():
    actual = run_installed_geometry_cable_rehearsal_v1(ROOT)
    retained = json.loads(RETAINED.read_text(encoding="utf-8"))
    assert actual == retained
    assert list(VALIDATOR.iter_errors(actual)) == []
    assert dict(parse_installed_geometry_cable_rehearsal_v1(actual)) == actual
    assert actual["case_count"] == actual["matched_count"] == 8
    assert actual["all_declared_cases_matched"] is True
    assert actual["qualification_installed"] is False
    assert actual["camera_opened"] is actual["transport_opened"] is False
    assert actual["controller_commands"] == []
    assert actual["hardware_writes"] == actual["physical_movements"] == 0
    assert actual["physical_authority"] is False


def test_complete_fixture_is_diagnostic_only_until_sampled_cable_is_bound():
    profile = build_synthetic_installed_collision_profile_v1(ROOT)
    audit = profile.to_dict()["geometry_audit"]
    assert audit["diagnostic_ready"] is True
    assert audit["physical_geometry_complete"] is False
    assert audit["configuration_sampled_body_ids"] == [
        "attachment:moving_camera_cable"
    ]


@pytest.mark.parametrize("mutation", ("order", "detail", "authority", "hash"))
def test_campaign_report_mutations_reject(mutation: str):
    value = json.loads(RETAINED.read_text(encoding="utf-8"))
    if mutation == "order":
        value["cases"][0], value["cases"][1] = value["cases"][1], value["cases"][0]
    elif mutation == "detail":
        value["cases"][1]["detail"] = ["WEAKENED"]
    elif mutation == "authority":
        value["physical_authority"] = True
    else:
        value["report_sha256"] = "0" * 64
    if mutation != "hash":
        core = {key: item for key, item in value.items() if key != "report_sha256"}
        value["report_sha256"] = _hash(core)
    with pytest.raises(InstalledGeometryCableRehearsalV1Error):
        parse_installed_geometry_cable_rehearsal_v1(value)
