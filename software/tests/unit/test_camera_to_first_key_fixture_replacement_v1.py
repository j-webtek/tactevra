from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "software/config/camera_to_first_key_fixture_replacement_v1.json"
STAGE_IDS = (
    "camera_arrival_offline_review",
    "measured_configuration_epoch",
    "physical_localization_qualification",
    "installed_collision_qualification",
    "observed_pose_entry",
    "entry_conservative_sweep",
    "measured_entry_dynamics",
    "sampled_tracking_and_settling",
    "bounded_telemetry_coverage",
    "independent_key_effect",
)


def _load():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_fixture_replacement_registry_is_complete_ordered_and_source_bound():
    document = _load()
    assert document["schema"] == "rocell.camera_to_first_key_fixture_replacement.v1"
    assert document["status"] == "AWAITING_PHYSICAL_ORIGINALS"
    assert document["evidence_class"] == "PRE_COMMISSIONING_REQUIREMENTS_ONLY"
    stages = document["stages"]
    assert tuple(item["stage_id"] for item in stages) == STAGE_IDS
    assert tuple(item["order"] for item in stages) == tuple(range(1, 11))
    seen = set()
    for item in stages:
        assert (ROOT / item["source_path"]).is_file()
        assert item["required_schema"].startswith("rocell.")
        assert item["required_status"]
        assert item["fixture_replaced"]
        assert item["physical_replacement"]
        assert set(item["prerequisite_stage_ids"]) <= seen
        assert item["motion_authority"] is False
        seen.add(item["stage_id"])


def test_registry_cannot_claim_camera_controller_movement_or_authority():
    document = _load()
    assert document["camera_open_authorized"] is False
    assert document["controller_start_authorized"] is False
    assert document["movement_authorized"] is False
    assert document["hardware_commands_generated"] == 0
    assert document["physical_authority"] is False
    serialized = REGISTRY.read_text(encoding="utf-8").lower()
    assert '"motion_authority": true' not in serialized
    assert '"physical_authority": true' not in serialized


def test_fixture_replacement_registry_keeps_all_physical_gaps_explicit():
    stages = _load()["stages"]
    assert len({item["required_schema"] for item in stages}) == len(stages)
    assert all("fixture" in item["fixture_replaced"].lower() or item["stage_id"] in {
        "camera_arrival_offline_review",
        "physical_localization_qualification",
        "measured_configuration_epoch",
    } for item in stages)
    assert all(
        any(word in item["physical_replacement"].lower() for word in (
            "physical", "installed", "retained", "independent", "camera",
            "epoch", "geometry",
        ))
        for item in stages
    )
