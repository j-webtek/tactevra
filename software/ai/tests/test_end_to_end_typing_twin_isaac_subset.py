from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "software/integrations/isaac_sim/end_to_end_typing_twin_subset_probe.py"
FIXTURE = ROOT / "software/ai/sim/evidence/end_to_end_typing_twin_isaac_subset_v1.json"
SPEC = importlib.util.spec_from_file_location("ws1_isaac_subset", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_fixture_is_hash_bound_zero_authority_and_exact_population():
    fixture = MODULE.load_fixture(FIXTURE, workspace=ROOT)
    samples = MODULE.frozen_samples(fixture)
    assert len(fixture["scenarios"]) == 6
    assert len(samples) == 162
    assert len({row["sample_id"] for row in samples}) == 162
    assert fixture["physical_authority"] is False
    assert not any(fixture["counters"].values())
    hello = fixture["scenarios"][0]
    assert hello["target_ids"] == [
        "SHIFT", "H", "E", "L", "L", "O", "SPACE", "2", "0", "2", "6",
        "SHIFT", "1",
    ]


def test_fixture_rejects_tampering(tmp_path: Path):
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["physical_authority"] = True
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        MODULE.load_fixture(path, workspace=ROOT)


def _write_manifest(root: Path, fixture: dict, gpu_id: int, delta: int = 0) -> Path:
    root.mkdir()
    samples = []
    for index, frozen in enumerate(MODULE.frozen_samples(fixture)):
        rgb = np.full((4, 6, 3), 20 + delta, dtype=np.uint8)
        mask = np.zeros((4, 6), dtype=np.uint16)
        mask[1:3, 2:4] = 1
        rgb_path = root / f"r{index}.png"
        mask_path = root / f"m{index}.png"
        Image.fromarray(rgb, mode="RGB").save(rgb_path)
        Image.fromarray(mask, mode="I;16").save(mask_path)
        scenario = next(
            row for row in fixture["scenarios"]
            if row["scenario_id"] == frozen["scenario_id"]
        )
        unique_targets = list(dict.fromkeys(scenario["target_ids"]))
        samples.append({
            **frozen, "target_ids": scenario["target_ids"],
            "render_mode": scenario["render_mode"],
            "expected_outcome": scenario["expected_outcome"],
            "actual_outcome": scenario["expected_outcome"], "outcome_matches": True,
            "passes_local_gates": True, "rgb_path": rgb_path.name,
            "rgb_sha256": MODULE.file_sha256(rgb_path), "mask_path": mask_path.name,
            "mask_sha256": MODULE.file_sha256(mask_path), "render_seconds": 0.1,
            "target_metrics": [
                {"target_id": target, "semantic_pixels": 4,
                 "semantic_centroid_px": [2.5, 1.5],
                 "projected_center_px": [2.5, 1.5],
                 "target_center_max_abs_error_px": 0.0,
                 "safe_region_visible_fraction": 1.0}
                for target in unique_targets
            ],
        })
    core = {
        "schema": MODULE.MANIFEST_SCHEMA, "scope": MODULE.SCOPE,
        "fixture_sha256": fixture["fixture_sha256"], "gpu_id": gpu_id,
        "gpu_name": f"GPU {gpu_id}", "gpu_uuid": f"UUID-{gpu_id}",
        "driver_version": "TEST", "isaac_version": "6.1.0",
        "warp_version": "TEST", "git_commit": "0" * 40,
        "sample_count": len(samples), "samples": samples, "local_pass": True,
        "hardware_writes": 0, "physical_movements": 0, "real_commands": 0,
        "permits": 0, "transport_operations": 0, "physical_authority": False,
        "limitations": fixture["limitations"],
    }
    value = {**core, "report_sha256": MODULE.digest(core)}
    path = root / "manifest.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_cross_gpu_comparator_passes_identical_and_stops_rgb_drift(tmp_path: Path):
    fixture = MODULE.load_fixture(FIXTURE, workspace=ROOT)
    left = _write_manifest(tmp_path / "left", fixture, 0)
    right = _write_manifest(tmp_path / "right", fixture, 1)
    result = MODULE.compare_manifests(fixture=fixture, left_path=left, right_path=right)
    assert result["decision"] == "PASS_EXPLORATORY_CROSS_GPU"
    drifted = _write_manifest(tmp_path / "drifted", fixture, 1, delta=3)
    result = MODULE.compare_manifests(fixture=fixture, left_path=left, right_path=drifted)
    assert result["decision"] == "STOP"
    assert all(row["rgb_max_abs_uint8"] == 3 for row in result["samples"])


def test_source_has_no_real_transport_import_or_authority_surface():
    source = SOURCE.read_text(encoding="utf-8")
    assert "import serial" not in source
    assert "import socket" not in source
    assert "ProductionController" not in source
    assert "physical_authority\": True" not in source
    assert hashlib.sha256(source.encode()).hexdigest()
