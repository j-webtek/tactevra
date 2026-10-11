from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]
INTAKE = ROOT / "config" / "tripod_camera_installation_intake_v1.json"
sys.path.insert(0, str(ROOT / "scripts"))

from validate_tripod_camera_intake import (  # noqa: E402
    TripodIntakeError,
    validate_tripod_camera_intake,
)


def test_tripod_intake_is_hash_bound_and_zero_authority() -> None:
    document = validate_tripod_camera_intake()

    assert document["schema"] == "rocell.rc03.tripod_camera_installation_intake.v1"
    assert document["status"] == "AWAITING_RECEIVED_HARDWARE_MEASUREMENTS"
    for binding in document["source_bindings"].values():
        source = REPOSITORY_ROOT / binding["path"]
        assert source.is_file()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == binding["sha256"]
    assert document["authority"] == {
        "fabrication": False,
        "physical_installation": False,
        "robot_power": False,
        "motion": False,
        "contact": False,
        "physical_release_effect": "NONE",
    }


def test_tripod_intake_has_no_prequalified_measurement() -> None:
    document = json.loads(INTAKE.read_text(encoding="utf-8"))

    for section in (
        "measured_mount_interface",
        "measured_support_geometry",
        "installed_pose",
        "stability_results",
        "qualification_results",
    ):
        for value in document[section].values():
            assert value is None or value == []


def test_tripod_intake_rejects_source_hash_drift(tmp_path: Path) -> None:
    document = json.loads(INTAKE.read_text(encoding="utf-8"))
    document["source_bindings"]["workcell_layout"]["sha256"] = "0" * 64
    changed = tmp_path / "tripod_camera_installation_intake_v1.json"
    changed.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(TripodIntakeError, match="source hash changed"):
        validate_tripod_camera_intake(changed)
