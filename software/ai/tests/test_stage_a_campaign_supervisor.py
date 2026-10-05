import json
import math
from pathlib import Path

import pytest

from ai.sim import stage_a_campaign_supervisor as supervisor
from ai.sim import stage_a_long_run_ops as ops


ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = (
    ROOT / "software/ai/sim/evidence/workstream_2_stage_a_long_run_preflight_v1.json"
)


def test_fault_injection_matrix_exercises_all_required_stops(tmp_path):
    result = supervisor.fault_injection_matrix(tmp_path)
    assert result["status"] == "PASS"
    assert result["cases"] == {
        "backup_hash_matches": True,
        "deterministic_no_retry": True,
        "disk_below_floor": True,
        "early_abort_all_fail": True,
        "hung_worker": True,
        "temperature_over_ceiling": True,
        "transient_retry_once_then_success": True,
    }
    assert result["hardware_write_count"] == 0
    assert result["physical_movement_count"] == 0
    assert result["physical_authority"] is False


def test_boundary_stops_are_conservative():
    fixture = ops.load_fixture(FIXTURE_PATH)
    ceiling = fixture["thermals"]["pause_ceiling_c"]
    floor = fixture["storage"]["clean_stop_floor_bytes"]
    assert (
        supervisor.boundary_decision(fixture, [ceiling - 0.1], floor)
        == "CONTINUE"
    )
    assert (
        supervisor.boundary_decision(fixture, [ceiling], floor)
        == "PAUSE_THERMAL_AT_BOUNDARY"
    )
    assert (
        supervisor.boundary_decision(fixture, [ceiling - 0.1], floor - 1)
        == "STOP_DISK_FLOOR"
    )


def test_retry_and_deterministic_failure_policy():
    assert supervisor.worker_decision("DRIVER_RESET", 0) == "RETRY_ONCE"
    assert supervisor.worker_decision("DRIVER_RESET", 1) == "STOP_PRESERVE"
    assert supervisor.worker_decision("NONFINITE_STATE", 0) == "STOP_PRESERVE"
    assert supervisor.worker_decision("HASH_MISMATCH", 0) == "STOP_PRESERVE"
    assert supervisor.worker_decision(None, 0) == "ACCEPT"


def test_early_abort_requires_one_identical_failure_for_every_world():
    all_fail = [
        {
            "world_count": 2_304,
            "primary_failure_counts": {"PARTIAL_PRESS": 2_304},
        }
        for _ in range(32)
    ]
    assert supervisor.early_abort_decision(all_fail, 32) == "STOP_EARLY_ALL_FAIL"
    all_fail[-1]["primary_failure_counts"] = {"ADMITTED": 1, "PARTIAL_PRESS": 2_303}
    assert supervisor.early_abort_decision(all_fail, 32) == "CONTINUE"


def test_resume_rejects_altered_result(tmp_path):
    shard_id = "a" * 64
    rows = [{"row": 1}]
    result = {
        "schema": "tactevra.ws2_stage_a_shard.v1",
        "status": "PASS",
        "failure_class": None,
        "shard": {"shard_id": shard_id},
        "rows": rows,
        "rows_sha256": supervisor._result_rows_sha(rows),
    }
    result["receipt_sha256"] = ops.value_sha(result)
    path = tmp_path / f"{shard_id}.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    assert supervisor.load_valid_shard_result(path, shard_id)["status"] == "PASS"
    result["rows"][0]["row"] = 2
    path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError, match="receipt hash mismatch"):
        supervisor.load_valid_shard_result(path, shard_id)


def test_watchdog_boundary_is_strictly_past_timeout():
    assert (
        supervisor.watchdog_decision(now=600, last_progress=300, stale_seconds=300)
        == "CONTINUE"
    )
    assert (
        supervisor.watchdog_decision(
            now=600.001, last_progress=300, stale_seconds=300
        )
        == "STOP_HUNG_WORKER_ALERT"
    )


def test_real_shard_control_derives_half_extent_from_physical_size():
    fixture = ops.load_fixture(FIXTURE_PATH)
    shard = ops.build_shards(fixture)[0]
    _, _, _, control = supervisor.build_control(fixture, shard)
    assert control["control"]["physical_keycap_half_extent_mm"] == [7.0, 7.0]
    assert len(control["control"]["batch_rows"]) == 2_304


def test_resume_reconciles_missing_backup_and_rejects_conflict(tmp_path):
    results = tmp_path / "results"
    backups = tmp_path / "backups"
    results.mkdir()
    shard_id = "b" * 64
    rows = [{"row": 1}]
    result = {
        "schema": "tactevra.ws2_stage_a_shard.v1",
        "status": "PASS",
        "failure_class": None,
        "shard": {"shard_id": shard_id},
        "rows": rows,
        "rows_sha256": supervisor._result_rows_sha(rows),
    }
    result["receipt_sha256"] = ops.value_sha(result)
    source = results / f"{shard_id}.json"
    source.write_text(json.dumps(result), encoding="utf-8")
    assert supervisor.reconcile_resume_backups(results, backups, {shard_id}) == {
        shard_id
    }
    destination = backups / source.name
    assert destination.read_bytes() == source.read_bytes()
    destination.write_text("altered", encoding="utf-8")
    with pytest.raises(ValueError, match="existing backup hash mismatch"):
        supervisor.reconcile_resume_backups(results, backups, {shard_id})


def _cross_row(value=1.0, *, admitted=False):
    fixture = ops.load_fixture(FIXTURE_PATH)
    row = {
        field: value
        for field in fixture["integrity"]["cross_gpu_comparison"][
            "continuous_fields"
        ]
    }
    row.update({"row_id": "row-1", "admitted": admitted, "actuation_count": 0})
    return row


def _cross_result(row):
    return {
        "schema": "tactevra.ws2_stage_a_shard.v1",
        "scope": "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY",
        "throughput_fixture_sha256": "bound",
        "shard": {"shard_id": "a" * 64},
        "status": "PASS",
        "failure_class": None,
        "world_count": 1,
        "rows": [row],
        "primary_failure_counts": {"PARTIAL_PRESS": 1},
        "settle_pass": True,
        "finite": True,
        "overflow_zero": True,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }


def test_cross_gpu_comparison_bounds_only_continuous_measurements():
    fixture = ops.load_fixture(FIXTURE_PATH)
    tolerance = fixture["integrity"]["cross_gpu_comparison"][
        "continuous_absolute_tolerance"
    ]
    left = _cross_result(_cross_row())
    right = _cross_result(_cross_row(1.0 + tolerance * 0.99))
    assert supervisor.compare_cross_gpu_results(fixture, left, right)["status"] == "AGREE"
    right["rows"][0]["peak_penetration_mm"] += tolerance / 100
    mismatch = supervisor.compare_cross_gpu_results(fixture, left, right)
    assert mismatch["status"] == "DISAGREE"
    assert mismatch["reason"].endswith("peak_penetration_mm")


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda result: result["rows"][0].update(admitted=True), "row_exact"),
        (lambda result: result["rows"][0].pop("peak_tool_force_n"), "row_fields"),
        (
            lambda result: result["rows"][0].update(peak_tool_force_n=math.inf),
            "row_nonfinite",
        ),
        (
            lambda result: result.update(primary_failure_counts={"ADMITTED": 1}),
            "top:primary_failure_counts",
        ),
    ],
)
def test_cross_gpu_comparison_rejects_safety_or_integrity_drift(mutation, reason):
    fixture = ops.load_fixture(FIXTURE_PATH)
    left = _cross_result(_cross_row())
    right = _cross_result(_cross_row())
    mutation(right)
    result = supervisor.compare_cross_gpu_results(fixture, left, right)
    assert result["status"] == "DISAGREE"
    assert result["reason"].startswith(reason)
