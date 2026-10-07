"""Run the authorized C02 simulation campaign under fail-closed supervision."""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable

from ai.sim import c02_campaign_supervisor as supervisor
from ai.sim import stage_a_campaign_supervisor as policy
from ai.sim import stage_a_long_run_ops as ops


ROOT = Path(__file__).resolve().parents[3]
SCOPE = supervisor.SCOPE


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _resolve(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def load_authorization(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    claimed = fixture.pop("fixture_sha256")
    if ops.value_sha(fixture) != claimed:
        raise ValueError("C02 authorization fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture.get("scope") != SCOPE or fixture.get("physical_authority") is not False:
        raise ValueError("C02 authorization must remain zero authority")
    if any(int(value) != 0 for value in fixture["counters"].values()):
        raise ValueError("C02 authorization counters must remain zero")
    for name, binding in fixture["bindings"].items():
        source = _resolve(binding["path"])
        if ops.file_sha(source) != binding["sha256"]:
            raise ValueError(f"C02 authorization binding changed: {name}")
    if fixture["full_campaign_authorized"] is not True:
        raise ValueError("C02 full campaign lacks authorization overlay")
    return fixture


def verify_preflight(
    authorization: dict[str, Any], operations_fixture: dict[str, Any]
) -> dict[str, Any]:
    path = _resolve(authorization["bindings"]["preflight_result"]["path"])
    result = json.loads(path.read_text(encoding="utf-8"))
    core = dict(result)
    claimed = core.pop("receipt_sha256")
    if ops.value_sha(core) != claimed:
        raise ValueError("C02 preflight result hash mismatch")
    if result["fixture_sha256"] != operations_fixture["fixture_sha256"]:
        raise ValueError("C02 preflight fixture mismatch")
    if result["manifest_sha256"] != operations_fixture["manifest_sha256"]:
        raise ValueError("C02 preflight manifest mismatch")
    if result["status"] != "PASS_READY_FOR_AUTHORIZATION_AMENDMENT":
        raise ValueError("passing C02 preflight required")
    if result["failed_checks"]:
        raise ValueError("C02 preflight retains failed checks")
    return result


def _worker_command(
    operations_path: Path, shard_id: str, device: str, output: Path
) -> list[str]:
    return [
        sys.executable,
        str(Path(supervisor.__file__).resolve()),
        "worker",
        "--fixture",
        str(operations_path),
        "--shard-id",
        shard_id,
        "--device",
        device,
        "--output",
        str(output),
    ]


def _run_subprocess(command: list[str], timeout: float) -> tuple[int, str]:
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return process.returncode, (process.stdout + process.stderr).strip()
    except subprocess.TimeoutExpired as exc:
        detail = "".join(
            value.decode(errors="replace") if isinstance(value, bytes) else value or ""
            for value in (exc.stdout, exc.stderr)
        )
        return 124, f"STOP_HUNG_WORKER_ALERT {detail}".strip()


def _gpu_snapshot() -> list[dict[str, Any]]:
    ok, rows, detail = ops._gpu_snapshot()
    if not ok:
        raise RuntimeError(f"GPU telemetry unavailable: {detail}")
    return rows


def _disk_free(path: Path) -> int:
    import shutil

    return shutil.disk_usage(path.anchor).free


def _status(
    fixture: dict[str, Any],
    *,
    state: str,
    done: int,
    failures: list[str],
    temperatures: list[float],
    started: float,
) -> dict[str, Any]:
    total = int(fixture["population"]["shard_count"])
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


def _reconcile_for_run(
    results_root: Path,
    backup_root: Path,
    manifest: dict[str, Any],
    fixture: dict[str, Any],
) -> tuple[set[str], list[tuple[dict[str, Any], str, Path]]]:
    """Resume ordinary results while allowing deferred cross-GPU sentinels."""
    by_id = {row["shard_id"]: row for row in manifest["shards"]}
    modulus = int(fixture["integrity"]["cross_gpu_sample_modulus"])
    completed: set[str] = set()
    pending_cross: list[tuple[dict[str, Any], str, Path]] = []
    for source in results_root.glob("*.json"):
        if source.name.endswith(".cross.json") or source.stem not in by_id:
            continue
        shard_id = source.stem
        result = supervisor.load_valid_result(
            source, shard_id=shard_id, fixture=fixture
        )
        destination = backup_root / source.name
        if destination.exists():
            if ops.file_sha(source) != ops.file_sha(destination):
                raise ValueError("existing C02 backup hash mismatch")
        else:
            policy.copy_verified(source, destination)
        if int(shard_id[:8], 16) % modulus == 0:
            cross = source.with_suffix(".cross.json")
            if cross.exists():
                other = supervisor.load_valid_result(
                    cross, shard_id=shard_id, fixture=fixture
                )
                comparison = supervisor.compare_cross_gpu(fixture, result, other)
                if comparison["status"] != "AGREE":
                    raise ValueError(
                        f"C02 cross-GPU disagreement: {comparison['reason']}"
                    )
                cross_destination = backup_root / cross.name
                if cross_destination.exists():
                    if ops.file_sha(cross) != ops.file_sha(cross_destination):
                        raise ValueError("existing C02 cross-GPU backup hash mismatch")
                else:
                    policy.copy_verified(cross, cross_destination)
            else:
                pending_cross.append((by_id[shard_id], result["device"], source))
        completed.add(shard_id)
    return completed, pending_cross


def run_campaign(
    authorization_path: Path,
    *,
    run_subprocess: Callable[[list[str], float], tuple[int, str]] = _run_subprocess,
    gpu_snapshot: Callable[[], list[dict[str, Any]]] = _gpu_snapshot,
    disk_free: Callable[[Path], int] = _disk_free,
) -> dict[str, Any]:
    authorization = load_authorization(authorization_path)
    operations_path = _resolve(authorization["bindings"]["operations_fixture"]["path"])
    fixture = supervisor.load_fixture(operations_path)
    verify_preflight(authorization, fixture)
    _, _, manifest = supervisor.load_bound_campaign(fixture)
    if manifest["manifest_sha256"] != authorization["manifest_sha256"]:
        raise ValueError("authorized C02 manifest changed")

    output_root = Path(fixture["storage"]["output_root"])
    backup_root = Path(fixture["storage"]["backup_root"])
    results_root = output_root / "shards"
    backup_results = backup_root / "shards"
    status_path = Path(fixture["progress"]["status_path"])
    results_root.mkdir(parents=True, exist_ok=True)
    backup_results.mkdir(parents=True, exist_ok=True)
    completed, pending_cross = _reconcile_for_run(
        results_root, backup_results, manifest, fixture
    )
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

    shards = manifest["shards"]
    half_count = int(fixture["schedule"]["half_shard_count"])
    halves = (shards[:half_count], shards[half_count:])
    sample_count = int(fixture["early_abort"]["deterministic_sample_shards"])
    sample_sets = [
        {row["shard_id"] for row in sorted(half, key=lambda row: row["shard_id"])[:sample_count]}
        for half in halves
    ]
    sample_results: list[list[dict[str, Any]]] = [[], []]
    backup_batch: list[Path] = []
    cross_queue: list[tuple[dict[str, Any], str, Path]] = list(pending_cross)
    timeout = float(fixture["watchdog"]["stale_seconds"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        for half_index, half in enumerate(halves):
            pending = [row for row in half if row["shard_id"] not in completed]
            cursor = 0
            active: dict[
                Future[tuple[int, str]], tuple[dict[str, Any], str, Path, int]
            ] = {}
            while cursor < len(pending) or active:
                latest = gpu_snapshot()
                latest_temperatures = [row["temperature_c"] for row in latest]
                boundary = policy.boundary_decision(
                    fixture, latest_temperatures, disk_free(output_root)
                )
                if boundary != "CONTINUE" and not active:
                    failures.append(boundary)
                    _atomic_json(
                        status_path,
                        _status(
                            fixture,
                            state=boundary,
                            done=len(completed),
                            failures=failures,
                            temperatures=latest_temperatures,
                            started=started,
                        ),
                    )
                    return {"status": boundary, "shards_done": len(completed)}
                while boundary == "CONTINUE" and len(active) < 2 and cursor < len(pending):
                    shard = pending[cursor]
                    cursor += 1
                    supervisor.load_fixture(operations_path)
                    occupied = {row[1] for row in active.values()}
                    device = next(
                        value for value in ("cuda:0", "cuda:1") if value not in occupied
                    )
                    output = results_root / f"{shard['shard_id']}.json"
                    future = executor.submit(
                        run_subprocess,
                        _worker_command(operations_path, shard["shard_id"], device, output),
                        timeout,
                    )
                    active[future] = (shard, device, output, 0)
                if not active:
                    continue
                done = [future for future in active if future.done()]
                if not done:
                    time.sleep(0.25)
                    continue
                for future in done:
                    shard, device, output, attempt = active.pop(future)
                    code, detail = future.result()
                    if code == 124:
                        failures.append(f"{shard['shard_id']}:STOP_HUNG_WORKER_ALERT")
                        state = "STOP_HUNG_WORKER_ALERT"
                    elif not output.exists():
                        failures.append(f"{shard['shard_id']}:IDENTITY_MISMATCH:{detail}")
                        state = "STOP_DETERMINISTIC"
                    else:
                        raw = json.loads(output.read_text(encoding="utf-8"))
                        core = dict(raw)
                        claimed = core.pop("receipt_sha256", None)
                        failure_class = raw.get("failure_class")
                        if claimed is None or ops.value_sha(core) != claimed:
                            failure_class = "HASH_MISMATCH"
                        action = policy.worker_decision(failure_class, attempt)
                        if action == "RETRY_ONCE":
                            output.rename(output.with_suffix(".attempt-0.json"))
                            retry = executor.submit(
                                run_subprocess,
                                _worker_command(
                                    operations_path, shard["shard_id"], device, output
                                ),
                                timeout,
                            )
                            active[retry] = (shard, device, output, 1)
                            continue
                        if action == "STOP_PRESERVE" or code != 0:
                            failures.append(
                                f"{shard['shard_id']}:{failure_class or detail}"
                            )
                            state = "STOP_DETERMINISTIC"
                        else:
                            result = supervisor.load_valid_result(
                                output, shard_id=shard["shard_id"], fixture=fixture
                            )
                            completed.add(shard["shard_id"])
                            backup_batch.append(output)
                            if int(shard["shard_id"][:8], 16) % int(
                                fixture["integrity"]["cross_gpu_sample_modulus"]
                            ) == 0:
                                cross_queue.append((shard, device, output))
                            if shard["shard_id"] in sample_sets[half_index]:
                                sample_results[half_index].append(result)
                                if policy.early_abort_decision(
                                    sample_results[half_index], sample_count
                                ) == "STOP_EARLY_ALL_FAIL":
                                    failures.append("STOP_EARLY_ALL_FAIL")
                                    state = "STOP_EARLY_ALL_FAIL"
                                else:
                                    state = "CONTINUE"
                            else:
                                state = "CONTINUE"
                            if len(backup_batch) >= int(
                                fixture["storage"]["backup_every_completed_shards"]
                            ):
                                for source in backup_batch:
                                    policy.copy_verified(source, backup_results / source.name)
                                backup_batch.clear()
                    if state != "CONTINUE":
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
        policy.copy_verified(source, backup_results / source.name)

    # Cross-GPU sentinels run after ordinary shards so they never contend with a
    # campaign worker on the same device.
    for shard, primary_device, primary_path in cross_queue:
        alternate = "cuda:1" if primary_device == "cuda:0" else "cuda:0"
        cross = primary_path.with_suffix(".cross.json")
        code, detail = run_subprocess(
            _worker_command(operations_path, shard["shard_id"], alternate, cross),
            timeout,
        )
        if code != 0 or not cross.exists():
            failures.append(f"{shard['shard_id']}:CROSS_GPU_MISSING:{detail}")
            state = "STOP_DETERMINISTIC"
        else:
            left = supervisor.load_valid_result(
                primary_path, shard_id=shard["shard_id"], fixture=fixture
            )
            right = supervisor.load_valid_result(
                cross, shard_id=shard["shard_id"], fixture=fixture
            )
            comparison = supervisor.compare_cross_gpu(fixture, left, right)
            state = "CONTINUE" if comparison["status"] == "AGREE" else "STOP_DETERMINISTIC"
            if state != "CONTINUE":
                failures.append(
                    f"{shard['shard_id']}:CROSS_GPU_DISAGREEMENT:{comparison['reason']}"
                )
        if state != "CONTINUE":
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
        policy.copy_verified(cross, backup_results / cross.name)

    result = {
        "schema": "tactevra.ws2_c02_campaign_result.v1",
        "scope": SCOPE,
        "authorization_fixture_sha256": authorization["fixture_sha256"],
        "operations_fixture_sha256": fixture["fixture_sha256"],
        "manifest_sha256": manifest["manifest_sha256"],
        "status": "COMPLETE_SIMULATION_ONLY_REQUIRES_FINAL_ADMISSION",
        "shards_done": len(completed),
        "world_count": manifest["population"]["world_count"],
        "cross_gpu_shard_count": len(cross_queue),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = ops.value_sha(result)
    _atomic_json(output_root / "campaign_result.json", result)
    policy.copy_verified(
        output_root / "campaign_result.json", backup_root / "campaign_result.json"
    )
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
    parser.add_argument("--authorization", type=Path, required=True)
    args = parser.parse_args()
    result = run_campaign(args.authorization)
    print(json.dumps({"status": result["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()
