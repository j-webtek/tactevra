"""Tests for the synthetic geometry-first fusion development replay."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import jsonschema
import pytest
from PIL import Image


AI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI / "eval"))

from replay_geometry_first_fusion_development import replay  # noqa: E402


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _claim(value, field):
    value[field] = _sha(_canonical(value))
    return value


def _write_json(path, value):
    path.write_bytes(_canonical(value) + b"\n")


def _fixtures(tmp_path: Path):
    mask = Image.new("L", (10, 10), 0)
    for x in range(4):
        mask.putpixel((x, 5), 255)
    mask.putpixel((8, 8), 255)
    mask_path = tmp_path / "mask.png"
    mask.save(mask_path)
    mask_sha = _sha(mask_path.read_bytes())
    targets = [
        {
            "device": "keyboard", "target_id": "A", "center_px": [1, 1],
            "safe_polygon_px": [[0, 0], [2, 0], [2, 2], [0, 2]],
            "center_occluded_by_official_mesh": False,
            "safe_region_official_mesh_overlap_fraction": 0.0,
        },
        {
            "device": "keyboard", "target_id": "B", "center_px": [8, 8],
            "safe_polygon_px": [[7, 7], [9, 7], [9, 9], [7, 9]],
            "center_occluded_by_official_mesh": True,
            "safe_region_official_mesh_overlap_fraction": 1 / 9,
        },
        {
            "device": "keyboard", "target_id": "C", "center_px": [4.5, 5.5],
            "safe_polygon_px": [[0, 5], [9, 5], [9, 6], [0, 6]],
            "center_occluded_by_official_mesh": False,
            "safe_region_official_mesh_overlap_fraction": 0.2,
        },
    ]
    source = _claim({
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v16",
        "campaign": "grouped-neighborhood-training-v16",
        "artifact_atlases": {"robot_mask_000": {"path": "mask.png", "sha256": mask_sha}},
        "pose_results": [{
            "pose_id": "p1", "pose_group": "development", "rgb_atlas_key": "rgb_000",
            "atlas_crop_px": [0, 0, 10, 10], "targets": targets,
        }],
        "hardware_writes": 0, "physical_movements": 0, "physical_authority": False,
    }, "receipt_sha256")
    source_path = tmp_path / "source.json"
    _write_json(source_path, source)

    rows = [
        {"id": "p1-a", "pose_id": "p1", "target_id": "A", "center_occluded": False, "safe_region_overlap_fraction": 0.0, "decision": "target_visible", "synthetic_only": True},
        {"id": "p1-b", "pose_id": "p1", "target_id": "B", "center_occluded": True, "safe_region_overlap_fraction": 1 / 9, "decision": "abstain", "synthetic_only": True},
        {"id": "p1-c", "pose_id": "p1", "target_id": "C", "center_occluded": False, "safe_region_overlap_fraction": 0.2, "decision": "target_visible", "synthetic_only": True},
    ]
    rows_path = tmp_path / "development.jsonl"
    rows_payload = b"".join(_canonical(row) + b"\n" for row in rows)
    rows_path.write_bytes(rows_payload)
    dataset = _claim({
        "schema": "rocell.ai_official_mesh_occlusion_data.v16",
        "source_manifest_sha256": _sha(source_path.read_bytes()),
        "source_receipt_sha256": source["receipt_sha256"],
        "target_catalog_sha256": "a" * 64,
        "splits": {"development": {"path": "development.jsonl", "sha256": _sha(rows_payload), "count": 3}, "evaluation": {"count": 0}},
        "authority": {"hardware_write_count": 0, "physical_movement_count": 0},
    }, "dataset_sha256")
    dataset_path = tmp_path / "dataset.json"
    _write_json(dataset_path, dataset)
    scorecard = _claim({
        "schema": "rocell.ai_grouped_neighborhood_candidate.v1",
        "dataset_manifest_sha256": _sha(dataset_path.read_bytes()),
        "dataset_sha256": dataset["dataset_sha256"], "target_catalog_sha256": "a" * 64,
        "model_sha256": "b" * 64, "maximum_supported_planar_error_mm": 1.0,
        "development_gate_met": False, "evaluation_group_present": False,
        "promotion_status": "FAILED_DEVELOPMENT_GATE",
        "development_measurements": [{
            "offset": {"x_mm": 0.0, "x_px": 0.0, "y_mm": 0.0, "y_px": 0.0},
            "metrics": {
                "confusion": {"true_abstain": 0, "missed_abstain": 1, "true_visible": 2, "false_abstain": 0},
                "failures": [{"id": "p1-b", "expected": "abstain", "predicted": "target_visible"}],
            },
        }],
        "hardware_writes": 0, "physical_movements": 0, "physical_authority": False,
    }, "scorecard_sha256")
    scorecard_path = tmp_path / "scorecard.json"
    _write_json(scorecard_path, scorecard)
    return source_path, dataset_path, rows_path, scorecard_path


def _run(paths):
    return replay(source_manifest_path=paths[0], dataset_manifest_path=paths[1], development_rows_path=paths[2], scorecard_path=paths[3])


def test_replay_recomputes_masks_and_fuses_conservatively(tmp_path):
    paths = _fixtures(tmp_path)
    report = _run(paths)
    assert report == _run(paths)
    measurement = report["analysis"]["measurements"][0]
    assert measurement["learned_confusion"]["missed_abstain"] == 1
    assert measurement["fused_confusion"]["missed_abstain"] == 0
    assert measurement["fused_confusion"]["false_abstain"] == 1
    assert measurement["ambiguity_accepted_false_abstain"] == 0
    assert report["analysis"]["ambiguous_row_ids"] == ["p1-c"]
    assert report["hardware_writes"] == report["physical_movements"] == 0
    assert report["physical_authority"] is False


def test_retained_report_schema_and_measured_result():
    report = json.loads((AI / "eval" / "geometry_first_fusion_replay_v1.json").read_text())
    schema = json.loads((AI / "schemas" / "geometry_first_fusion_replay_v1.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(report)
    assert report["analysis"]["development_pose_count"] == 64
    assert report["analysis"]["recomputed_pose_target_count"] == 4800
    assert report["analysis"]["replayed_offset_count"] == 17
    assert report["analysis"]["ambiguous_row_count"] == 54
    assert report["analysis"]["worst_strict_fused_missed_abstain"] == 0
    assert report["analysis"]["worst_strict_fused_false_abstain"] == 881
    assert report["analysis"]["worst_ambiguity_accepted_fused_false_abstain"] == 866
    assert report["policy"]["qualification_installed"] is False


def test_altered_mask_atlas_fails_closed(tmp_path):
    paths = _fixtures(tmp_path)
    (tmp_path / "mask.png").write_bytes(b"altered")
    with pytest.raises(ValueError, match="mask atlas hash mismatch"):
        _run(paths)


def test_evaluation_access_is_rejected(tmp_path):
    paths = _fixtures(tmp_path)
    scorecard = json.loads(paths[3].read_text())
    scorecard.pop("scorecard_sha256")
    scorecard["evaluation_group_present"] = True
    _claim(scorecard, "scorecard_sha256")
    _write_json(paths[3], scorecard)
    with pytest.raises(ValueError, match="evaluation access"):
        _run(paths)


def test_recorded_confusion_mismatch_is_rejected(tmp_path):
    paths = _fixtures(tmp_path)
    scorecard = json.loads(paths[3].read_text())
    scorecard.pop("scorecard_sha256")
    altered = deepcopy(scorecard)
    altered["development_measurements"][0]["metrics"]["confusion"]["missed_abstain"] = 0
    _claim(altered, "scorecard_sha256")
    _write_json(paths[3], altered)
    with pytest.raises(ValueError, match="reconstructed learned confusion"):
        _run(paths)
