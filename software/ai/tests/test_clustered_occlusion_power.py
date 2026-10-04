from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import jsonschema
import pytest


AI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI))

from eval import plan_clustered_occlusion_power as planner  # noqa: E402


H = hashlib.sha256(b"catalog").hexdigest()


def _canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_source(root: Path, name: str, *, evaluation: bool = False):
    root.mkdir()
    rows = []
    for pose in ("pose-a", "pose-b"):
        for index, decision in enumerate(("abstain", "abstain", "target_visible", "target_visible")):
            rows.append({"id": f"{pose}-{index}", "pose_id": pose, "decision": decision, "synthetic_only": True})
    dataset = root / "rows.jsonl"
    dataset.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    manifest_core = {
        "schema": "fixture", "scope": "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION",
        "authority": {"can_release_physical_gates": False, "hardware_accessed": False, "hardware_write_count": 0, "physical_movement_count": 0},
        "target_catalog_sha256": H,
    }
    manifest = {**manifest_core, "dataset_sha256": _canonical(manifest_core)}
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    failures = [
        {"id": "pose-a-0", "expected": "abstain", "predicted": "target_visible"},
        {"id": "pose-b-2", "expected": "target_visible", "predicted": "abstain"},
    ]
    measurement = {"offset": {"x_mm": 0.0, "y_mm": 0.0}, "metrics": {"count": 8, "failures": failures, "confusion": {"missed_abstain": 1, "true_abstain": 3, "false_abstain": 1, "true_visible": 3}}}
    key = "measurements" if evaluation else "development_measurements"
    report_core = {
        "schema": "fixture", "dataset_sha256": manifest["dataset_sha256"],
        "dataset_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "target_catalog_sha256": H, key: [measurement], "hardware_writes": 0,
        "physical_movements": 0, "physical_authority": False,
    }
    hash_field = "report_sha256" if evaluation else "scorecard_sha256"
    report = {**report_core, hash_field: _canonical(report_core)}
    report_path = root / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return {"name": name, "dataset_path": dataset, "manifest_path": manifest_path, "report_path": report_path, "measurements_key": key}


def test_plan_is_deterministic_aggregate_only_and_schema_valid(tmp_path, monkeypatch):
    sources = [_write_source(tmp_path / "v13", "V13_DEVELOPMENT"), _write_source(tmp_path / "v14", "V14_FROZEN_EVALUATION", evaluation=True)]
    monkeypatch.setattr(planner, "POSE_CANDIDATES", (64,))
    first = planner.build_plan(sources=sources, bootstrap_samples=1000, simulation_trials=1000, seed=7)
    second = planner.build_plan(sources=sources, bootstrap_samples=1000, simulation_trials=1000, seed=7)
    assert first == second
    schema = json.loads((AI / "schemas" / "clustered_occlusion_power_plan_v1.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(first)
    assert first["identity_disclosure"] == {"pose_ids": 0, "target_ids": 0, "row_ids": 0, "image_paths": 0, "failure_identities": 0}
    assert first["controller_authority"] is False
    assert first["hardware_writes"] == first["physical_movements"] == 0
    rendered = json.dumps(first)
    assert "pose-a" not in rendered and "pose-b" not in rendered


def test_tampered_manifest_hash_is_rejected(tmp_path):
    source = _write_source(tmp_path / "v13", "V13_DEVELOPMENT")
    source2 = _write_source(tmp_path / "v14", "V14_FROZEN_EVALUATION", evaluation=True)
    manifest = json.loads(source["manifest_path"].read_text())
    manifest["target_catalog_sha256"] = hashlib.sha256(b"altered").hexdigest()
    source["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(planner.PowerPlanError, match="content hash mismatch"):
        planner.build_plan(sources=[source, source2], bootstrap_samples=1000, simulation_trials=1000)


def test_failure_label_mismatch_and_physical_authority_are_rejected(tmp_path):
    source = _write_source(tmp_path / "v13", "V13_DEVELOPMENT")
    source2 = _write_source(tmp_path / "v14", "V14_FROZEN_EVALUATION", evaluation=True)
    report = json.loads(source["report_path"].read_text())
    report["development_measurements"][0]["metrics"]["failures"][0]["expected"] = "target_visible"
    core = {key: value for key, value in report.items() if key != "scorecard_sha256"}
    report["scorecard_sha256"] = _canonical(core)
    source["report_path"].write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(planner.PowerPlanError, match="failure label mismatch"):
        planner.build_plan(sources=[source, source2], bootstrap_samples=1000, simulation_trials=1000)

    source = _write_source(tmp_path / "v13b", "V13_DEVELOPMENT")
    manifest = json.loads(source["manifest_path"].read_text())
    manifest["authority"]["hardware_accessed"] = True
    core = {key: value for key, value in manifest.items() if key != "dataset_sha256"}
    manifest["dataset_sha256"] = _canonical(core)
    source["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(planner.PowerPlanError, match="authority is not zero"):
        planner.build_plan(sources=[source, source2], bootstrap_samples=1000, simulation_trials=1000)
