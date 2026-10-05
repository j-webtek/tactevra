"""Enforce the frozen Stage A long-run policies while executing GPU shards.

This module owns simulation processes and evidence files only.  It has no
controller transport, hardware authority, permit, or physical movement path.
"""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Callable

from ai.sim import run_ws2_stage_a_full_compliance_smoke as full_smoke
from ai.sim import run_ws2_stage_a_vectorized_throughput as throughput
from ai.sim import stage_a_long_run_ops as ops
from integrations.mujoco_warp import key_press_physics_probe as probe


ROOT = Path(__file__).resolve().parents[3]
DETERMINISTIC_FAILURES = {
    "NONFINITE_STATE",
    "OVERFLOW",
    "IDENTITY_MISMATCH",
    "CROSS_GPU_DISAGREEMENT",
    "HASH_MISMATCH",
}
TRANSIENT_FAILURES = {"DRIVER_RESET", "OUT_OF_MEMORY_AT_LAUNCH"}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _result_rows_sha(rows: list[dict[str, Any]]) -> str:
    return ops.value_sha(rows)


def build_control(fixture: dict[str, Any], shard: dict[str, Any]) -> tuple[Any, ...]:
    throughput_fixture = throughput.load_fixture(
        ROOT / fixture["bindings"]["throughput_fixture"]["path"]
    )
    campaign, execution, staged, _, physical = throughput.load_bound(
        throughput_fixture
    )
    compliance = full_smoke.full_compliance(staged)
    base_rows = probe.stage_a_vectorized_ordinary_batch_rows(
        campaign, staged, target_id=shard["target_id"]
    )
    rows = [
        {**row, "compliance_id": option["compliance_id"]}
        for row in base_rows
        if row["compliance_id"] == compliance[0]["compliance_id"]
        for option in compliance
    ]
    if len(rows) != fixture["population"]["worlds_per_shard"]:
        raise ValueError("Stage A shard world population changed")
    neighborhood = next(
        row
        for row in physical["neighborhoods"]
        if row["target_id"] == shard["target_id"]
    )
    target_member = neighborhood["members"][neighborhood["target_joint_index"]]
    control = {
        "fixture_sha256": throughput_fixture["fixture_sha256"],
        "control": {
            "control_id": f"stage-a-{shard['shard_id']}",
            "control_kind": "ACTUATION",
            "target_id": shard["target_id"],
            "profile_id": shard["profile_id"],
            "tip_id": shard["tip_id"],
            "scenario_id": rows[0]["scenario_id"],
            "base_recipe_index": rows[0]["recipe_index"],
            "landing_sample_indices": [
                row["landing_sample_index"] for row in rows
            ],
            "batch_rows": rows,
            "vectorized_world_controls": True,
            "recipe_override": {},
            "tool_compliance_model": "SERIES_QUASISTATIC",
            "tool_compliance_options": compliance,
            "physical_keycap_half_extent_mm": target_member["half_extent_mm"],
            "physical_neighborhood": neighborhood["members"],
            "target_joint_index": neighborhood["target_joint_index"],
            "switch_closure_window_ms": throughput_fixture["smoke"][
                "switch_closure_window_ms"
            ],
        },
    }
    return throughput_fixture, campaign, execution, control


def execute_shard(
    fixture_path: Path, shard_id: str, device: str, output: Path
) -> dict[str, Any]:
    fixture = ops.load_fixture(fixture_path)
    shard = next(row for row in ops.build_shards(fixture) if row["shard_id"] == shard_id)
    throughput_fixture, campaign, execution, control = build_control(fixture, shard)
    started = time.time()
    try:
        receipt = probe.run_smoke_worker(
            campaign,
            execution,
            workspace=ROOT,
            device_name=device,
            control=control,
        )
        failure_class = None
        if not receipt["finite"]:
            failure_class = "NONFINITE_STATE"
        elif not receipt["overflow_zero"]:
            failure_class = "OVERFLOW"
        elif len(receipt["rows"]) != shard["world_count"]:
            failure_class = "IDENTITY_MISMATCH"
        result = {
            "schema": "tactevra.ws2_stage_a_shard.v1",
            "scope": fixture["scope"],
            "fixture_sha256": fixture["fixture_sha256"],
            "throughput_fixture_sha256": throughput_fixture["fixture_sha256"],
            "shard": shard,
            "device": device,
            "status": "PASS" if failure_class is None else "STOP_DETERMINISTIC",
            "failure_class": failure_class,
            "world_count": len(receipt["rows"]),
            "rows": receipt["rows"],
            "rows_sha256": _result_rows_sha(receipt["rows"]),
            "primary_failure_counts": _failure_counts(receipt["rows"]),
            "settle_pass": receipt["settle_pass"],
            "finite": receipt["finite"],
            "overflow_zero": receipt["overflow_zero"],
            "wall_elapsed_seconds": receipt["wall_elapsed_seconds"],
            "started_unix": started,
            "finished_unix": time.time(),
            "hardware_write_count": 0,
            "physical_movement_count": 0,
            "physical_authority": False,
        }
    except Exception as exc:  # Worker must preserve a classified terminal record.
        text = f"{type(exc).__name__}: {exc}"
        lowered = text.lower()
        transient = (
            "out of memory" in lowered
            or "cuda_error_out_of_memory" in lowered
            or "driver reset" in lowered
        )
        result = {
            "schema": "tactevra.ws2_stage_a_shard.v1",
            "scope": fixture["scope"],
            "fixture_sha256": fixture["fixture_sha256"],
            "shard": shard,
            "device": device,
            "status": "STOP_TRANSIENT" if transient else "STOP_DETERMINISTIC",
            "failure_class": (
                "OUT_OF_MEMORY_AT_LAUNCH" if transient else "IDENTITY_MISMATCH"
            ),
            "error": text,
            "world_count": 0,
            "rows": [],
            "rows_sha256": _result_rows_sha([]),
            "primary_failure_counts": {},
            "started_unix": started,
            "finished_unix": time.time(),
            "hardware_write_count": 0,
            "physical_movement_count": 0,
            "physical_authority": False,
        }
    result["receipt_sha256"] = ops.value_sha(result)
    _atomic_json(output, result)
    return result


def _failure_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        failure = probe.primary_failure(row)
        counts[failure] = counts.get(failure, 0) + 1
    return dict(sorted(counts.items()))


def load_valid_shard_result(path: Path, expected_shard_id: str) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    core = dict(result)
    claimed = core.pop("receipt_sha256")
    if ops.value_sha(core) != claimed:
        raise ValueError("shard receipt hash mismatch")
    if result["shard"]["shard_id"] != expected_shard_id:
        raise ValueError("shard identity mismatch")
    if result["rows_sha256"] != _result_rows_sha(result["rows"]):
        raise ValueError("shard row hash mismatch")
    if result["status"] != "PASS" or result.get("failure_class") is not None:
        raise ValueError("only passing shard results may resume")
    return result


def _gpu_snapshot() -> list[dict[str, Any]]:
    ok, rows, detail = ops._gpu_snapshot()
    if not ok:
        raise RuntimeError(f"GPU telemetry unavailable: {detail}")
    return rows


def _disk_free(path: Path) -> int:
    return shutil.disk_usage(path.anchor).free


def copy_verified(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    shutil.copy2(source, temporary)
    source_sha = _file_sha(source)
    copied_sha = _file_sha(temporary)
    if source_sha != copied_sha:
        raise ValueError("backup hash mismatch")
    os.replace(temporary, destination)
    return {
        "source": str(source),
        "destination": str(destination),
        "sha256": source_sha,
        "bytes": source.stat().st_size,
    }


def boundary_decision(
    fixture: dict[str, Any], temperatures: list[float], free_bytes: int
) -> str:
    if any(value >= fixture["thermals"]["pause_ceiling_c"] for value in temperatures):
        return "PAUSE_THERMAL_AT_BOUNDARY"
    if free_bytes < fixture["storage"]["clean_stop_floor_bytes"]:
        return "STOP_DISK_FLOOR"
    return "CONTINUE"


def worker_decision(failure_class: str | None, attempt: int) -> str:
    if failure_class is None:
        return "ACCEPT"
    if failure_class in TRANSIENT_FAILURES and attempt == 0:
        return "RETRY_ONCE"
    return "STOP_PRESERVE"


def early_abort_decision(sample: list[dict[str, Any]], expected: int) -> str:
    if len(sample) < expected:
        return "CONTINUE"
    primary = []
    for row in sample:
        counts = row.get("primary_failure_counts", {})
        admitted = int(counts.get("ADMITTED", 0))
        failures = [(name, count) for name, count in counts.items() if name != "ADMITTED"]
        if admitted or len(failures) != 1 or failures[0][1] != row["world_count"]:
            return "CONTINUE"
        primary.append(failures[0][0])
    return "STOP_EARLY_ALL_FAIL" if len(set(primary)) == 1 else "CONTINUE"


def _status(
    fixture: dict[str, Any], *, state: str, done: int, failures: list[str],
    temperatures: list[float], started: float
) -> dict[str, Any]:
    total = fixture["population"]["shard_count"]
    elapsed = max(time.time() - started, 0.0)
    eta = None if done == 0 else elapsed / done * (total - done)
    return {
        "status": state,
        "shards_done": done,
        "shards_total": total,
        "eta_seconds": eta,
        "failures": failures,
        "temperatures_c": temperatures,
        "updated_unix": time.time(),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }


def fault_injection_matrix(root: Path) -> dict[str, Any]:
    """Exercise the real policy helpers with deterministic injected values."""
    fixture = ops.load_fixture(
        ROOT / "software/ai/sim/evidence/workstream_2_stage_a_long_run_preflight_v1.json"
    )
    root.mkdir(parents=True, exist_ok=True)
    source = root / "backup-source.json"
    source.write_text('{"fault":"backup"}\n', encoding="utf-8")
    backup = root / "backup" / source.name
    backup_receipt = copy_verified(source, backup)
    all_fail = [
        {
            "world_count": 2_304,
            "primary_failure_counts": {"PARTIAL_PRESS": 2_304},
        }
        for _ in range(32)
    ]
    cases = {
        "temperature_over_ceiling": boundary_decision(
            fixture, [fixture["thermals"]["pause_ceiling_c"], 40.0], 10**12
        )
        == "PAUSE_THERMAL_AT_BOUNDARY",
        "disk_below_floor": boundary_decision(
            fixture,
            [40.0, 40.0],
            fixture["storage"]["clean_stop_floor_bytes"] - 1,
        )
        == "STOP_DISK_FLOOR",
        "hung_worker": watchdog_decision(
            now=601.0, last_progress=300.0, stale_seconds=300
        )
        == "STOP_HUNG_WORKER_ALERT",
        "transient_retry_once_then_success": (
            worker_decision("DRIVER_RESET", 0) == "RETRY_ONCE"
            and worker_decision(None, 1) == "ACCEPT"
        ),
        "deterministic_no_retry": (
            worker_decision("NONFINITE_STATE", 0) == "STOP_PRESERVE"
            and worker_decision("HASH_MISMATCH", 0) == "STOP_PRESERVE"
        ),
        "backup_hash_matches": (
            backup.exists()
            and backup_receipt["sha256"] == _file_sha(source) == _file_sha(backup)
        ),
        "early_abort_all_fail": early_abort_decision(all_fail, 32)
        == "STOP_EARLY_ALL_FAIL",
    }
    result = {
        "schema": "tactevra.ws2_stage_a_supervisor_fault_matrix.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "cases": cases,
        "status": "PASS" if all(cases.values()) else "STOP",
        "backup_receipt": backup_receipt,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = ops.value_sha(result)
    return result


def watchdog_decision(*, now: float, last_progress: float, stale_seconds: float) -> str:
    return (
        "STOP_HUNG_WORKER_ALERT"
        if now - last_progress > stale_seconds
        else "CONTINUE"
    )


def _verify_preflight(path: Path, fixture: dict[str, Any]) -> None:
    result = json.loads(path.read_text(encoding="utf-8"))
    core = dict(result)
    claimed = core.pop("receipt_sha256")
    if ops.value_sha(core) != claimed:
        raise ValueError("preflight receipt hash mismatch")
    if result["fixture_sha256"] != fixture["fixture_sha256"]:
        raise ValueError("preflight fixture mismatch")
    if result["status"] != "PASS_READY_TO_LAUNCH" or result["failed_checks"]:
        raise ValueError("passing preflight required")


def _worker_command(
    fixture_path: Path, shard: dict[str, Any], device: str, output: Path
) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "worker",
        "--fixture",
        str(fixture_path),
        "--shard-id",
        shard["shard_id"],
        "--device",
        device,
        "--output",
        str(output),
    ]


def _run_subprocess(command: list[str], timeout: float) -> tuple[int, str]:
    process = subprocess.run(
        command, capture_output=True, text=True, check=False, timeout=timeout
    )
    return process.returncode, (process.stdout + process.stderr).strip()


def run_campaign(
    fixture_path: Path,
    preflight_path: Path,
    *,
    run_subprocess: Callable[[list[str], float], tuple[int, str]] = _run_subprocess,
    gpu_snapshot: Callable[[], list[dict[str, Any]]] = _gpu_snapshot,
    disk_free: Callable[[Path], int] = _disk_free,
) -> dict[str, Any]:
    fixture = ops.load_fixture(fixture_path)
    _verify_preflight(preflight_path, fixture)
    shards = ops.build_shards(fixture)
    output_root = Path(fixture["storage"]["output_root"])
    backup_root = Path(fixture["storage"]["backup_root"])
    results_root = output_root / "shards"
    backup_results = backup_root / "shards"
    status_path = Path(fixture["progress"]["status_path"])
    results_root.mkdir(parents=True, exist_ok=True)
    backup_results.mkdir(parents=True, exist_ok=True)
    shard_ids = {row["shard_id"] for row in shards}
    completed: set[str] = set()
    for path in results_root.glob("*.json"):
        if path.stem not in shard_ids:
            continue
        load_valid_shard_result(path, path.stem)
        completed.add(path.stem)
    started = time.time()
    failures: list[str] = []
    latest_temperatures = [row["temperature_c"] for row in gpu_snapshot()]
    _atomic_json(
        status_path,
        _status(
            fixture,
            state="RUNNING",
            done=len(completed),
            failures=failures,
            temperatures=latest_temperatures,
            started=started,
        ),
    )
    half_count = fixture["schedule"]["half_shard_count"]
    backup_batch: list[Path] = []
    sample_sets = [
        {
            row["shard_id"]
            for row in sorted(part, key=lambda value: value["shard_id"])[
                : fixture["early_abort"]["deterministic_sample_shards"]
            ]
        }
        for part in (shards[:half_count], shards[half_count:])
    ]
    sample_results: list[list[dict[str, Any]]] = [[], []]
    shard_timeout = float(fixture["watchdog"]["stale_seconds"])
    with ThreadPoolExecutor(max_workers=2) as executor:
        for half_index, half in enumerate((shards[:half_count], shards[half_count:])):
            pending = [row for row in half if row["shard_id"] not in completed]
            cursor = 0
            active: dict[Future[tuple[int, str]], tuple[dict[str, Any], str, Path, int, float]] = {}
            while cursor < len(pending) or active:
                latest = gpu_snapshot()
                latest_temperatures = [row["temperature_c"] for row in latest]
                decision = boundary_decision(
                    fixture, latest_temperatures, disk_free(output_root)
                )
                if decision != "CONTINUE" and not active:
                    _atomic_json(
                        status_path,
                        _status(
                            fixture,
                            state=decision,
                            done=len(completed),
                            failures=[decision],
                            temperatures=latest_temperatures,
                            started=started,
                        ),
                    )
                    return {"status": decision, "shards_done": len(completed)}
                while decision == "CONTINUE" and len(active) < 2 and cursor < len(pending):
                    shard = pending[cursor]
                    cursor += 1
                    # Revalidate every frozen binding before every shard.
                    ops.load_fixture(fixture_path)
                    occupied = {row[1] for row in active.values()}
                    device = next(
                        candidate
                        for candidate in ("cuda:0", "cuda:1")
                        if candidate not in occupied
                    )
                    output = results_root / f"{shard['shard_id']}.json"
                    command = _worker_command(fixture_path, shard, device, output)
                    future = executor.submit(run_subprocess, command, shard_timeout)
                    active[future] = (shard, device, output, 0, time.time())
                if not active:
                    continue
                done = [future for future in active if future.done()]
                if not done:
                    oldest = min(row[4] for row in active.values())
                    if watchdog_decision(
                        now=time.time(),
                        last_progress=oldest,
                        stale_seconds=shard_timeout,
                    ) == "STOP_HUNG_WORKER_ALERT":
                        failures.append("STOP_HUNG_WORKER_ALERT")
                        for future in active:
                            future.cancel()
                        _atomic_json(
                            status_path,
                            _status(
                                fixture,
                                state="STOP_HUNG_WORKER_ALERT",
                                done=len(completed),
                                failures=failures,
                                temperatures=latest_temperatures,
                                started=started,
                            ),
                        )
                        return {
                            "status": "STOP_HUNG_WORKER_ALERT",
                            "shards_done": len(completed),
                        }
                    time.sleep(1.0)
                    continue
                for future in done:
                    shard, device, output, attempt, _ = active.pop(future)
                    try:
                        code, detail = future.result()
                    except subprocess.TimeoutExpired:
                        code, detail = 124, "worker timeout"
                    if not output.exists():
                        failures.append(f"{shard['shard_id']}:IDENTITY_MISMATCH:{detail}")
                        state = "STOP_DETERMINISTIC"
                        _atomic_json(
                            status_path,
                            _status(
                                fixture,
                                state=state,
                                done=len(completed),
                                failures=failures,
                                temperatures=latest_temperatures,
                                started=started,
                            ),
                        )
                        return {"status": state, "shards_done": len(completed)}
                    result = json.loads(output.read_text(encoding="utf-8"))
                    core = dict(result)
                    claimed = core.pop("receipt_sha256")
                    failure_class = result.get("failure_class")
                    if ops.value_sha(core) != claimed:
                        failure_class = "HASH_MISMATCH"
                    action = worker_decision(failure_class, attempt)
                    if action == "RETRY_ONCE":
                        output.rename(output.with_suffix(".attempt-0.json"))
                        command = _worker_command(fixture_path, shard, device, output)
                        retry = executor.submit(run_subprocess, command, shard_timeout)
                        active[retry] = (shard, device, output, 1, time.time())
                        continue
                    if action == "STOP_PRESERVE" or code != 0:
                        failures.append(f"{shard['shard_id']}:{failure_class or detail}")
                        state = "STOP_DETERMINISTIC"
                        _atomic_json(
                            status_path,
                            _status(
                                fixture,
                                state=state,
                                done=len(completed),
                                failures=failures,
                                temperatures=latest_temperatures,
                                started=started,
                            ),
                        )
                        return {"status": state, "shards_done": len(completed)}
                    if int(shard["shard_id"][:8], 16) % fixture["integrity"][
                        "cross_gpu_sample_modulus"
                    ] == 0:
                        cross = output.with_suffix(".cross.json")
                        alternate = "cuda:1" if device == "cuda:0" else "cuda:0"
                        cross_code, _ = run_subprocess(
                            _worker_command(fixture_path, shard, alternate, cross),
                            shard_timeout,
                        )
                        other = json.loads(cross.read_text(encoding="utf-8"))
                        if cross_code != 0 or other["rows_sha256"] != result["rows_sha256"]:
                            failures.append(f"{shard['shard_id']}:CROSS_GPU_DISAGREEMENT")
                            _atomic_json(
                                status_path,
                                _status(
                                    fixture,
                                    state="STOP_DETERMINISTIC",
                                    done=len(completed),
                                    failures=failures,
                                    temperatures=latest_temperatures,
                                    started=started,
                                ),
                            )
                            return {
                                "status": "STOP_DETERMINISTIC",
                                "shards_done": len(completed),
                            }
                    completed.add(shard["shard_id"])
                    backup_batch.append(output)
                    if shard["shard_id"] in sample_sets[half_index]:
                        sample_results[half_index].append(result)
                        if early_abort_decision(
                            sample_results[half_index],
                            fixture["early_abort"]["deterministic_sample_shards"],
                        ) == "STOP_EARLY_ALL_FAIL":
                            failures.append("STOP_EARLY_ALL_FAIL")
                            _atomic_json(
                                status_path,
                                _status(
                                    fixture,
                                    state="STOP_EARLY_ALL_FAIL",
                                    done=len(completed),
                                    failures=failures,
                                    temperatures=latest_temperatures,
                                    started=started,
                                ),
                            )
                            return {
                                "status": "STOP_EARLY_ALL_FAIL",
                                "shards_done": len(completed),
                            }
                    if len(backup_batch) >= fixture["storage"][
                        "backup_every_completed_shards"
                    ]:
                        for source in backup_batch:
                            copy_verified(source, backup_results / source.name)
                        backup_batch.clear()
                    _atomic_json(
                        status_path,
                        _status(
                            fixture,
                            state="RUNNING",
                            done=len(completed),
                            failures=failures,
                            temperatures=latest_temperatures,
                            started=started,
                        ),
                    )
    for source in backup_batch:
        copy_verified(source, backup_results / source.name)
    result = {
        "schema": "tactevra.ws2_stage_a_campaign_result.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "status": "COMPLETE_SIMULATION_ONLY",
        "shards_done": len(completed),
        "worlds": fixture["population"]["world_count"],
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = ops.value_sha(result)
    _atomic_json(output_root / "campaign_result.json", result)
    _atomic_json(
        status_path,
        _status(
            fixture,
            state=result["status"],
            done=len(completed),
            failures=[],
            temperatures=latest_temperatures,
            started=started,
        ),
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    worker = subparsers.add_parser("worker")
    worker.add_argument("--fixture", type=Path, required=True)
    worker.add_argument("--shard-id", required=True)
    worker.add_argument("--device", choices=("cuda:0", "cuda:1"), required=True)
    worker.add_argument("--output", type=Path, required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--fixture", type=Path, required=True)
    run.add_argument("--preflight", type=Path, required=True)
    faults = subparsers.add_parser("fault-matrix")
    faults.add_argument("--root", type=Path, required=True)
    faults.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "worker":
        result = execute_shard(args.fixture, args.shard_id, args.device, args.output)
    elif args.mode == "run":
        result = run_campaign(args.fixture, args.preflight)
    else:
        result = fault_injection_matrix(args.root)
        _atomic_json(args.output, result)
    print(json.dumps({"status": result["status"]}))


if __name__ == "__main__":
    main()
