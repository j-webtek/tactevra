import json

import pytest

from ai.sim import run_ws2_c02_supervised_campaign as runner
from ai.sim import stage_a_long_run_ops as ops


def test_authorization_rejects_authority_and_disabled_campaign(tmp_path):
    payload = {
        "schema": "test",
        "scope": runner.SCOPE,
        "bindings": {},
        "full_campaign_authorized": False,
        "counters": {"hardware_writes": 0},
        "physical_authority": False,
    }
    payload["fixture_sha256"] = ops.value_sha(payload)
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="lacks authorization"):
        runner.load_authorization(path)


def test_preflight_verification_rejects_failed_checks(tmp_path):
    operations = {"fixture_sha256": "ops", "manifest_sha256": "manifest"}
    result = {
        "fixture_sha256": "ops",
        "manifest_sha256": "manifest",
        "status": "PASS_READY_FOR_AUTHORIZATION_AMENDMENT",
        "failed_checks": ["disk"],
    }
    result["receipt_sha256"] = ops.value_sha(result)
    path = tmp_path / "preflight.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    authorization = {"bindings": {"preflight_result": {"path": str(path)}}}
    with pytest.raises(ValueError, match="retains failed checks"):
        runner.verify_preflight(authorization, operations)


def test_resume_defers_missing_cross_gpu_result(tmp_path):
    fixture = {
        "fixture_sha256": "fixture",
        "manifest_sha256": "manifest",
        "campaign_fixture_sha256": "campaign",
        "integrity": {"cross_gpu_sample_modulus": 1},
    }
    shard_id = "a" * 64
    rows = [{"row": 1}]
    result = {
        "schema": "tactevra.ws2_c02_shard.v1",
        "fixture_sha256": "fixture",
        "campaign_fixture_sha256": "campaign",
        "manifest_sha256": "manifest",
        "shard": {"shard_id": shard_id, "world_count": 1},
        "device": "cuda:0",
        "status": "PASS",
        "failure_class": None,
        "world_count": 1,
        "rows": rows,
        "rows_sha256": ops.value_sha(rows),
    }
    result["receipt_sha256"] = ops.value_sha(result)
    results = tmp_path / "results"
    backups = tmp_path / "backups"
    results.mkdir()
    (results / f"{shard_id}.json").write_text(json.dumps(result), encoding="utf-8")
    manifest = {"shards": [{"shard_id": shard_id}]}
    completed, pending = runner._reconcile_for_run(
        results, backups, manifest, fixture
    )
    assert completed == {shard_id}
    assert [(row[0]["shard_id"], row[1]) for row in pending] == [
        (shard_id, "cuda:0")
    ]
    assert (backups / f"{shard_id}.json").exists()
