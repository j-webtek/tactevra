import json
from pathlib import Path

import pytest

from ai.sim import c02_campaign_supervisor as supervisor
from ai.sim import stage_a_long_run_ops as ops


def _fixture(tmp_path: Path) -> dict:
    return {
        "fixture_sha256": "fixture",
        "manifest_sha256": "manifest",
        "campaign_fixture_sha256": "campaign",
        "integrity": {
            "cross_gpu_sample_modulus": 31,
            "cross_gpu_comparison": {
                "continuous_absolute_tolerance": 1e-5,
                "continuous_fields": ["peak_penetration_mm"],
            },
        },
        "storage": {"clean_stop_floor_bytes": 100},
        "thermals": {"pause_ceiling_c": 83},
        "watchdog": {"stale_seconds": 300},
        "early_abort": {"deterministic_sample_shards": 4},
    }


def _result(fixture: dict, shard_id: str) -> dict:
    rows = [{"peak_penetration_mm": 1.0, "admitted": False}]
    result = {
        "schema": "tactevra.ws2_c02_shard.v1",
        "scope": supervisor.SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "campaign_fixture_sha256": fixture["campaign_fixture_sha256"],
        "manifest_sha256": fixture["manifest_sha256"],
        "shard": {"shard_id": shard_id, "world_count": 1},
        "status": "PASS",
        "failure_class": None,
        "world_count": 1,
        "rows": rows,
        "rows_sha256": ops.value_sha(rows),
    }
    result["receipt_sha256"] = ops.value_sha(result)
    return result


def test_fault_matrix_exercises_every_required_policy(tmp_path):
    fixture = _fixture(tmp_path)
    result = supervisor.fault_injection_matrix(tmp_path, fixture)
    assert result["status"] == "PASS"
    assert all(result["cases"].values())
    assert result["physical_authority"] is False


def test_valid_result_rejects_tampering(tmp_path):
    fixture = _fixture(tmp_path)
    shard_id = "a" * 64
    path = tmp_path / "result.json"
    result = _result(fixture, shard_id)
    path.write_text(json.dumps(result), encoding="utf-8")
    assert supervisor.load_valid_result(path, shard_id=shard_id, fixture=fixture)[
        "status"
    ] == "PASS"
    result["rows"][0]["peak_penetration_mm"] = 2.0
    path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError, match="receipt hash mismatch"):
        supervisor.load_valid_result(path, shard_id=shard_id, fixture=fixture)


def test_cross_gpu_allows_bounded_continuous_row_hash_difference(tmp_path):
    fixture = _fixture(tmp_path)
    shard_id = "c" * 64
    left = _result(fixture, shard_id)
    right = _result(fixture, shard_id)
    right["rows"][0]["peak_penetration_mm"] += 5e-6
    right["rows_sha256"] = ops.value_sha(right["rows"])
    comparison = supervisor.compare_cross_gpu(fixture, left, right)
    assert comparison["status"] == "AGREE"


def test_resume_copies_and_rejects_conflicting_backup(tmp_path):
    fixture = _fixture(tmp_path)
    fixture["integrity"]["cross_gpu_sample_modulus"] = 10**20
    shard_id = "f" * 64
    results = tmp_path / "results"
    backups = tmp_path / "backups"
    results.mkdir()
    path = results / f"{shard_id}.json"
    path.write_text(json.dumps(_result(fixture, shard_id)), encoding="utf-8")
    manifest = {"shards": [{"shard_id": shard_id}]}
    assert supervisor.reconcile_resume(results, backups, manifest, fixture) == {
        shard_id
    }
    (backups / path.name).write_text("altered", encoding="utf-8")
    with pytest.raises(ValueError, match="backup hash mismatch"):
        supervisor.reconcile_resume(results, backups, manifest, fixture)
