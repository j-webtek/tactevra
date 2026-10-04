"""Tests for the frozen residual-obstruction pretraining campaign."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import jsonschema
import pytest
from PIL import Image


AI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI / "sim"))

from build_residual_obstruction_campaign_fixture import build  # noqa: E402


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _write_source(tmp_path: Path) -> Path:
    samples = []
    targets = [
        {"device": "keyboard", "target_id": "A", "center_px": [20.0, 20.0], "safe_polygon_px": [[15.0, 15.0], [25.0, 15.0], [25.0, 25.0], [15.0, 25.0]]},
        {"device": "phone", "target_id": "key_a", "center_px": [40.0, 40.0], "safe_polygon_px": [[37.0, 35.0], [43.0, 35.0], [43.0, 45.0], [37.0, 45.0]]},
    ]
    for pose in ("hover_t", "hover_e"):
        image_path = tmp_path / f"{pose}.jpg"
        Image.new("RGB", (64, 64), (40, 45, 50)).save(image_path, "JPEG")
        samples.append({
            "sample_id": f"{pose}__nominal", "pose_id": pose,
            "image_path": image_path.name, "image_sha256": _sha(image_path.read_bytes()),
            "targets": targets,
        })
    core = {
        "schema": "rocell.fixed_fixture_practice_corpus.v1",
        "scope": "SYNTHETIC_FIXED_FIXTURE_PRACTICE_ONLY",
        "generator_sha256": "a" * 64, "target_catalog_sha256": "b" * 64,
        "camera_state": "SYNTHETIC_UNMEASURED_ARM_CAMERA", "samples": samples,
        "authority": {"hardware_accessed": False, "hardware_write_count": 0, "physical_movement_count": 0, "can_release_physical_gates": False},
    }
    source = {**core, "corpus_sha256": _sha(_canonical(core))}
    path = tmp_path / "manifest.json"
    path.write_bytes(_canonical(source) + b"\n")
    return path


def test_fixture_is_deterministic_balanced_and_zero_authority(tmp_path):
    source = _write_source(tmp_path)
    first = build(source)
    assert first == build(source)
    assert first["split_policy"]["split_counts"] == {
        "training": {"total": 16, "visible": 4, "abstain": 12},
        "development": {"total": 16, "visible": 4, "abstain": 12},
    }
    assert first["split_policy"]["training_pose_ids"] == ["hover_t"]
    assert first["split_policy"]["development_pose_ids"] == ["hover_e"]
    assert all(row["truth_mask_used_as_model_input"] is False for row in first["observations"])
    assert all(row["runtime_geometry_mask_used_as_model_input"] is False for row in first["observations"])
    assert first["hardware_writes"] == first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_retained_fixture_validates_and_freezes_expected_counts():
    fixture = json.loads((AI / "sim" / "evidence" / "residual_obstruction_pretraining_v1.json").read_text())
    schema = json.loads((AI / "schemas" / "residual_obstruction_campaign_fixture_v1.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(fixture)
    assert fixture["split_policy"]["target_count_per_split"] == 75
    assert fixture["split_policy"]["split_counts"]["training"] == {"total": 600, "visible": 150, "abstain": 450}
    assert fixture["split_policy"]["split_counts"]["development"] == {"total": 600, "visible": 150, "abstain": 450}
    assert fixture["evaluation_group_present"] is False
    assert fixture["images_generated"] is fixture["training_started"] is False


def test_changed_base_image_fails_closed(tmp_path):
    source = _write_source(tmp_path)
    (tmp_path / "hover_e.jpg").write_bytes(b"changed")
    with pytest.raises(ValueError, match="base image hash mismatch"):
        build(source)


def test_source_authority_claim_fails_closed(tmp_path):
    source = _write_source(tmp_path)
    document = json.loads(source.read_text())
    document["authority"]["hardware_write_count"] = 1
    core = {key: value for key, value in document.items() if key != "corpus_sha256"}
    document["corpus_sha256"] = _sha(_canonical(core))
    source.write_bytes(_canonical(document) + b"\n")
    with pytest.raises(ValueError, match="authority or physical effects"):
        build(source)


def test_cross_pose_target_catalog_mismatch_fails_closed(tmp_path):
    source = _write_source(tmp_path)
    document = json.loads(source.read_text())
    document["samples"][1]["targets"].reverse()
    core = {key: value for key, value in document.items() if key != "corpus_sha256"}
    document["corpus_sha256"] = _sha(_canonical(core))
    source.write_bytes(_canonical(document) + b"\n")
    with pytest.raises(ValueError, match="different ordered target catalogs"):
        build(source)
