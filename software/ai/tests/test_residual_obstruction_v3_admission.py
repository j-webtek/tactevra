from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
AI_ROOT = ROOT / "software" / "ai"
sys.path.insert(0, str(AI_ROOT / "eval"))
sys.path.insert(0, str(ROOT / "software" / "src"))

from admit_residual_obstruction_v3_shards import (  # noqa: E402
    canonical,
    sha256_bytes,
    verify_shards,
)
from rocell.application.bootstrap import bootstrap_virtual_workcell  # noqa: E402


FIXTURE = AI_ROOT / "sim" / "evidence" / "residual_obstruction_successor_v3.json"
SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_v3_admission_v1.schema.json"
RECEIPT = AI_ROOT / "eval" / "residual_obstruction_v3_partial_admission_v1.json"
FULL_SHARD_RECEIPT = AI_ROOT / "eval" / "residual_obstruction_v3_first_full_shard_admission_v1.json"
COMPLETE_RECEIPT = AI_ROOT / "eval" / "residual_obstruction_v3_complete_admission_v1.json"
LINEAGE = AI_ROOT / "eval" / "residual_obstruction_v3_renderer_lineage_v1.json"
LINEAGE_SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_v3_renderer_lineage_v1.schema.json"


def _write_shard(tmp_path: Path, rows: list[dict], **updates) -> Path:
    shard = tmp_path / "shard"
    shard.mkdir()
    for index, row in enumerate(rows):
        payload = f"synthetic-jpeg-{index}".encode()
        path = shard / row["rgb_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        row["rgb_bytes"] = len(payload)
        row["rgb_sha256"] = sha256_bytes(payload)
    fixture_bytes = FIXTURE.read_bytes()
    fixture = json.loads(fixture_bytes)
    core = {
        "schema": "tactevra.ai_residual_obstruction_v3_isaac_manifest.v1",
        "scope": "SYNTHETIC_ISAAC_RENDER_NO_QUALIFICATION",
        "fixture_file_sha256": sha256_bytes(fixture_bytes),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "complete_campaign": False,
        "scene_count": 1,
        "observation_count": len(rows),
        "target_shard": {"start": 0, "count": 1},
        "split_counts": {
            "training": sum(row["split"] == "training" for row in rows),
            "development": sum(row["split"] == "development" for row in rows),
        },
        "observations": rows,
        "evaluation_observation_count": 0,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": ["synthetic"],
    }
    core.update(updates)
    manifest = {**core, "dataset_sha256": sha256_bytes(canonical(core))}
    (shard / "manifest.json").write_bytes(canonical(manifest) + b"\n")
    return shard


def _row(variant_id: str = "clear") -> dict:
    context = bootstrap_virtual_workcell(ROOT).context
    target = sorted(
        [
            *context.targets.keyboard_targets.values(),
            *context.targets.phone_targets.values(),
        ],
        key=lambda item: (item.device, item.target_id),
    )[0]
    decisions = {"clear": "VISIBLE", "adjacent_left": "VISIBLE", "cable_rubber": "ABSTAIN"}
    overlaps = {"clear": 0.0, "adjacent_left": 0.0, "cable_rubber": 0.6}
    return {
        "observation_id": f"residual_training_scene_01:neutral:{variant_id}:{target.device}:{target.target_id}",
        "split": "training",
        "scene_id": "residual_training_scene_01",
        "appearance_id": "neutral",
        "variant_id": variant_id,
        "target_id": target.target_id,
        "device": target.device,
        "expected_decision": decisions[variant_id],
        "rgb_path": f"training/residual_training_scene_01/neutral/{variant_id}/000.jpg",
        "rgb_sha256": "0" * 64,
        "rgb_bytes": 0,
        "safe_overlap_fraction": overlaps[variant_id],
        "adjacent_overlap_fraction": 0.0,
        "depth_min_mm": 75.0,
        "depth_max_mm": 125.0,
    }


def test_partial_shard_is_verified_but_not_admitted(tmp_path):
    receipt = verify_shards(ROOT, FIXTURE, [_write_shard(tmp_path, [_row()])], require_complete=False)
    Draft202012Validator(json.loads(SCHEMA.read_text())).validate(receipt)
    core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    assert receipt["receipt_sha256"] == sha256_bytes(canonical(core))
    assert receipt["status"] == "PARTIAL"
    assert receipt["campaign_admitted"] is False
    assert receipt["verified_observation_count"] == 1
    assert receipt["missing_observation_count"] == 43199
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_retained_partial_receipt_is_bound_and_not_admitted():
    receipt = json.loads(RECEIPT.read_text())
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(receipt)
    core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    assert receipt["receipt_sha256"] == sha256_bytes(canonical(core))
    assert receipt["status"] == "PARTIAL"
    assert receipt["campaign_admitted"] is False
    assert receipt["verified_observation_count"] == 192
    assert receipt["missing_observation_count"] == 43008


def test_retained_first_full_shard_is_bound_and_not_admitted():
    receipt = json.loads(FULL_SHARD_RECEIPT.read_text())
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator(schema).validate(receipt)
    core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    assert receipt["receipt_sha256"] == sha256_bytes(canonical(core))
    assert receipt["status"] == "PARTIAL"
    assert receipt["campaign_admitted"] is False
    assert receipt["verified_observation_count"] == 2304
    assert receipt["missing_observation_count"] == 40896


def test_retained_complete_receipt_is_bound_and_admitted():
    receipt = json.loads(COMPLETE_RECEIPT.read_text())
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator(schema).validate(receipt)
    core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    assert receipt["receipt_sha256"] == sha256_bytes(canonical(core))
    assert receipt["status"] == "PASS"
    assert receipt["campaign_admitted"] is True
    assert receipt["manifest_count"] == 19
    assert receipt["verified_observation_count"] == 43200
    assert receipt["missing_observation_count"] == 0
    assert receipt["unique_rgb_sha256_count"] == 43200
    assert receipt["split_counts"] == {"training": 28800, "development": 14400}
    assert receipt["evaluation_observation_count"] == 0
    assert receipt["training_started"] is False
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0
    assert receipt["physical_authority"] is False


def test_retained_renderer_lineage_covers_complete_receipt():
    receipt = json.loads(COMPLETE_RECEIPT.read_text())
    lineage = json.loads(LINEAGE.read_text())
    schema = json.loads(LINEAGE_SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(lineage)
    core = {key: value for key, value in lineage.items() if key != "lineage_sha256"}
    assert lineage["lineage_sha256"] == sha256_bytes(canonical(core))
    assert lineage["admission_receipt_sha256"] == receipt["receipt_sha256"]
    assert lineage["admission_file_sha256"] == sha256_bytes(COMPLETE_RECEIPT.read_bytes())
    assert [
        {
            key: shard[key]
            for key in (
                "manifest_file_sha256",
                "dataset_sha256",
                "target_start",
                "target_count",
                "observation_count",
            )
        }
        for shard in lineage["shards"]
    ] == receipt["manifests"]
    covered_targets = [
        target
        for shard in lineage["shards"]
        for target in range(shard["target_start"], shard["target_start"] + shard["target_count"])
    ]
    assert covered_targets == list(range(75))
    assert lineage["hardware_writes"] == lineage["physical_movements"] == 0
    assert lineage["physical_authority"] is False


def test_complete_gate_rejects_partial_shard(tmp_path):
    shard = _write_shard(tmp_path, [_row()])
    with pytest.raises(ValueError, match="campaign incomplete"):
        verify_shards(ROOT, FIXTURE, [shard])


def test_altered_image_is_rejected(tmp_path):
    shard = _write_shard(tmp_path, [_row()])
    next(shard.rglob("*.jpg")).write_bytes(b"altered")
    with pytest.raises(ValueError, match="image size or hash mismatch"):
        verify_shards(ROOT, FIXTURE, [shard], require_complete=False)


def test_wrong_fixture_binding_is_rejected(tmp_path):
    shard = _write_shard(tmp_path, [_row()], fixture_bundle_sha256="0" * 64)
    with pytest.raises(ValueError, match="fixture bundle hash mismatch"):
        verify_shards(ROOT, FIXTURE, [shard], require_complete=False)


def test_overlap_outside_frozen_contract_is_rejected(tmp_path):
    row = _row("cable_rubber")
    row["safe_overlap_fraction"] = 0.9
    shard = _write_shard(tmp_path, [row])
    with pytest.raises(ValueError, match="overlap outside contract"):
        verify_shards(ROOT, FIXTURE, [shard], require_complete=False)


def test_duplicate_rgb_bytes_across_rows_are_rejected(tmp_path):
    rows = [_row(), _row("adjacent_left")]
    shard = _write_shard(tmp_path, rows)
    manifest_path = shard / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    first = shard / manifest["observations"][0]["rgb_path"]
    second = shard / manifest["observations"][1]["rgb_path"]
    payload = first.read_bytes()
    second.write_bytes(payload)
    manifest["observations"][1]["rgb_bytes"] = len(payload)
    manifest["observations"][1]["rgb_sha256"] = sha256_bytes(payload)
    core = {key: value for key, value in manifest.items() if key != "dataset_sha256"}
    manifest["dataset_sha256"] = sha256_bytes(canonical(core))
    manifest_path.write_bytes(canonical(manifest) + b"\n")
    with pytest.raises(ValueError, match="duplicate RGB bytes"):
        verify_shards(ROOT, FIXTURE, [shard], require_complete=False)


def test_extra_file_is_rejected(tmp_path):
    shard = _write_shard(tmp_path, [_row()])
    (shard / "unexpected.txt").write_text("extra")
    with pytest.raises(ValueError, match="missing or extra regular files"):
        verify_shards(ROOT, FIXTURE, [shard], require_complete=False)
