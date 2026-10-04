"""Tests for the read-only v15 pose-cluster development diagnostic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import jsonschema
import pytest


AI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI / "eval"))

from diagnose_pose_cluster_development import diagnose  # noqa: E402


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _claim(value, field):
    value[field] = hashlib.sha256(_canonical(value)).hexdigest()
    return value


def _write_fixture(tmp_path: Path):
    rows = [
        {"id": "p1-a", "pose_id": "p1", "target_id": "MINUS", "lighting_variant": "l1", "decision": "abstain", "synthetic_only": True},
        {"id": "p1-v", "pose_id": "p1", "target_id": "A", "lighting_variant": "l1", "decision": "target_visible", "synthetic_only": True},
        {"id": "p2-a", "pose_id": "p2", "target_id": "U", "lighting_variant": "l2", "decision": "abstain", "synthetic_only": True},
        {"id": "p2-v", "pose_id": "p2", "target_id": "B", "lighting_variant": "l2", "decision": "target_visible", "synthetic_only": True},
    ]
    rows_path = tmp_path / "development.jsonl"
    rows_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    manifest = _claim({"splits": {"development": {"count": 4}, "evaluation": {"count": 0}}}, "dataset_sha256")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest) + b"\n")
    scorecard = _claim({
        "schema": "rocell.ai_pose_diverse_candidate.v1", "dataset_sha256": manifest["dataset_sha256"],
        "model_sha256": "a" * 64, "target_catalog_sha256": "b" * 64, "selected_threshold": 0.2,
        "maximum_supported_planar_error_mm": 1.0, "development_gate_met": False,
        "evaluation_group_present": False, "promotion_status": "FAILED_DEVELOPMENT_GATE",
        "hardware_writes": 0, "physical_movements": 0, "physical_authority": False,
        "development_measurements": [{"offset": {"x_mm": 0.0, "x_px": 0.0, "y_mm": 0.0, "y_px": 0.0}, "metrics": {"failures": [{"id": "p1-a", "expected": "abstain", "predicted": "target_visible"}]}}],
        "pose_cluster_bootstrap": {"offsets": [{"offset": {"x_mm": 0.0, "x_px": 0.0, "y_mm": 0.0, "y_px": 0.0}, "missed_abstain_upper_95": 0.6, "visible_false_abstain_upper_95": 0.1}]},
    }, "scorecard_sha256")
    scorecard_path = tmp_path / "scorecard.json"
    scorecard_path.write_bytes(_canonical(scorecard) + b"\n")
    fixture = _claim({"samples": [
        {"pose_id": "p1", "split": "development", "source_interval": [1, 2], "source_path_fraction": [1, 10], "expected_tool_tip_board_mm": [1.0, 2.0, 3.0]},
        {"pose_id": "p2", "split": "development", "source_interval": [3, 4], "source_path_fraction": [3, 10], "expected_tool_tip_board_mm": [4.0, 5.0, 6.0]},
    ]}, "bundle_sha256")
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_bytes(_canonical(fixture) + b"\n")
    return manifest_path, rows_path, scorecard_path, fixture_path


def _run(paths):
    return diagnose(dataset_manifest_path=paths[0], development_rows_path=paths[1], scorecard_path=paths[2], pose_fixture_path=paths[3])


def test_diagnostic_is_deterministic_and_zero_authority(tmp_path):
    paths = _write_fixture(tmp_path)
    first = _run(paths)
    assert first == _run(paths)
    assert first["analysis"]["dominant_missed_pose_target"] == {"pose_id": "p1", "target_id": "MINUS", "count": 1, "fraction_of_all_misses": 1.0}
    assert first["evaluation_accessed"] is False
    assert first["hardware_writes"] == first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_retained_report_validates_and_records_measured_concentration():
    report = json.loads((AI / "eval" / "pose_cluster_development_diagnostic_v1.json").read_text())
    schema = json.loads((AI / "schemas" / "pose_cluster_development_diagnostic_v1.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(report)
    dominant = report["analysis"]["dominant_missed_pose_target"]
    assert dominant["pose_id"] == "pose_diverse_development_016"
    assert dominant["target_id"] == "MINUS"
    assert dominant["count"] == 27
    assert report["analysis"]["poses_with_any_missed_abstain"] == 7


def test_altered_scorecard_hash_is_rejected(tmp_path):
    paths = _write_fixture(tmp_path)
    scorecard = json.loads(paths[2].read_text())
    scorecard["selected_threshold"] = 0.3
    paths[2].write_bytes(_canonical(scorecard) + b"\n")
    with pytest.raises(ValueError, match="scorecard canonical hash mismatch"):
        _run(paths)


def test_evaluation_access_is_rejected_even_with_valid_hash(tmp_path):
    paths = _write_fixture(tmp_path)
    scorecard = json.loads(paths[2].read_text())
    scorecard.pop("scorecard_sha256")
    scorecard["evaluation_group_present"] = True
    _claim(scorecard, "scorecard_sha256")
    paths[2].write_bytes(_canonical(scorecard) + b"\n")
    with pytest.raises(ValueError, match="evaluation access"):
        _run(paths)
