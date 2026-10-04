from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.admit_residual_obstruction_v4_2_shards import (  # noqa: E402
    _validate_camera_contract,
    _validate_overlap,
    canonical,
    load_bound,
)


FIXTURE_PATH = AI_ROOT / "sim/evidence/residual_obstruction_successor_v4_2.json"
REPORT_PATH = AI_ROOT / "eval/residual_obstruction_v4_2_renderer_smoke_v1.json"
CORRECTED_REPORT_PATH = AI_ROOT / "eval/residual_obstruction_v4_2_camera_contract_smoke_v1.json"
SCHEMA_PATH = AI_ROOT / "schemas/residual_obstruction_v4_2_admission_v1.schema.json"


def test_retained_partial_admission_is_hash_bound_and_cannot_unlock_training() -> None:
    report = json.loads(REPORT_PATH.read_text())
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)
    core = {key: value for key, value in report.items() if key != "report_sha256"}
    assert report["report_sha256"] == hashlib.sha256(canonical(core)).hexdigest()
    assert report["status"] == "PARTIAL"
    assert report["campaign_admitted"] is False
    assert report["verified_observation_count"] == 192
    assert report["missing_by_split"] == {"training": 43008, "development": 28800}
    assert report["evaluation_observation_count"] == 0


def test_corrected_camera_contract_smoke_is_hash_bound_and_partial() -> None:
    report = json.loads(CORRECTED_REPORT_PATH.read_text())
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator(schema).validate(report)
    core = {key: value for key, value in report.items() if key != "report_sha256"}
    assert report["report_sha256"] == hashlib.sha256(canonical(core)).hexdigest()
    assert report["status"] == "PARTIAL"
    assert report["campaign_admitted"] is False
    assert report["manifests"][0]["dataset_sha256"] == (
        "368b5e4016ffd5d38563d108931b80b06618d256ab0dbd38596e6e6f46f13d79"
    )


def test_overlap_reconciliation_rejects_drift() -> None:
    fixture, _ = load_bound(
        FIXTURE_PATH,
        "tactevra.ai_residual_obstruction_successor_fixture.v4_2",
        "bundle_sha256",
    )
    row = {
        "variant_id": "tool_matte_edge",
        "safe_overlap_fraction": 0.4,
        "adjacent_overlap_fraction": 0.0,
    }
    _validate_overlap(fixture, row)
    row["safe_overlap_fraction"] = 0.8
    with pytest.raises(ValueError, match="outside frozen bounds"):
        _validate_overlap(fixture, row)


def test_camera_contract_rejects_out_of_bound_jitter() -> None:
    fixture, _ = load_bound(
        FIXTURE_PATH,
        "tactevra.ai_residual_obstruction_successor_fixture.v4_2",
        "bundle_sha256",
    )
    scene = next(row for row in fixture["base_scenes"] if row["split"] == "training")
    row = {
        "camera_position_mm": [0.0, 0.0, 82.0],
        "camera_look_at_mm": [0.0, 0.0, 0.0],
        "camera_up_axis": [0.0, 1.0, 0.0],
        "camera_position_jitter_mm": [0.0, 0.0, 0.0],
        "camera_rotation_jitter_deg": [0.0, 0.0, 0.0],
    }
    _validate_camera_contract(scene, row)
    row["camera_position_jitter_mm"][0] = 3.01
    with pytest.raises(ValueError, match="position jitter exceeds"):
        _validate_camera_contract(scene, row)
