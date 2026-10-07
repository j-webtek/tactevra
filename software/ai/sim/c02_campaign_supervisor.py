"""Fail-closed supervision and operational preflight for the bounded C02 run.

This module executes simulation workers and manages evidence custody only.  It
contains no controller transport, hardware command, permit, or physical-motion
path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

from ai.sim import run_ws2_c02_boundary_campaign as campaign
from ai.sim import stage_a_campaign_supervisor as policy
from ai.sim import stage_a_long_run_ops as ops
from integrations.mujoco_warp import key_press_physics_probe as probe


ROOT = Path(__file__).resolve().parents[3]
SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"


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


def _resolve(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def load_fixture(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    claimed = fixture.pop("fixture_sha256")
    if ops.value_sha(fixture) != claimed:
        raise ValueError("C02 supervisor fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture.get("scope") != SCOPE or fixture.get("physical_authority") is not False:
        raise ValueError("C02 supervisor fixture must remain zero authority")
    if any(int(value) != 0 for value in fixture["counters"].values()):
        raise ValueError("C02 supervisor counters must remain zero")
    for name, binding in fixture["bindings"].items():
        source = _resolve(binding["path"])
        if _file_sha(source) != binding["sha256"]:
            raise ValueError(f"C02 supervisor binding changed: {name}")
    return fixture


def load_bound_campaign(
    fixture: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    campaign_path = _resolve(fixture["bindings"]["campaign_fixture"]["path"])
    campaign_fixture = campaign.load_fixture(campaign_path)
    if campaign_fixture["fixture_sha256"] != fixture["campaign_fixture_sha256"]:
        raise ValueError("C02 campaign fixture identity changed")
    plan = campaign.load_candidate_plan(campaign_fixture)
    manifest = campaign.build_manifest(campaign_fixture, plan)
    if manifest["manifest_sha256"] != fixture["manifest_sha256"]:
        raise ValueError("C02 manifest identity changed")
    return campaign_fixture, plan, manifest


def _failure_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        failure = probe.primary_failure(row)
        counts[failure] = counts.get(failure, 0) + 1
    return dict(sorted(counts.items()))


def execute_shard(
    fixture_path: Path, shard_id: str, device: str, output: Path
) -> dict[str, Any]:
    fixture = load_fixture(fixture_path)
    campaign_fixture, plan, manifest = load_bound_campaign(fixture)
    shard = next(
        (row for row in manifest["shards"] if row["shard_id"] == shard_id), None
    )
    if shard is None:
        raise ValueError("unknown C02 shard identity")
    started = time.time()
    try:
        _, physics_campaign, execution, control = campaign.build_control(
            campaign_fixture, plan, shard_id
        )
        receipt = probe.run_smoke_worker(
            physics_campaign,
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
        elif len(receipt["rows"]) != int(shard["world_count"]):
            failure_class = "IDENTITY_MISMATCH"
        result = {
            "schema": "tactevra.ws2_c02_shard.v1",
            "scope": SCOPE,
            "fixture_sha256": fixture["fixture_sha256"],
            "campaign_fixture_sha256": campaign_fixture["fixture_sha256"],
            "manifest_sha256": manifest["manifest_sha256"],
            "throughput_fixture_sha256": campaign_fixture["bindings"][
                "throughput_fixture"
            ]["fixture_sha256"],
            "shard": shard,
            "device": device,
            "status": "PASS" if failure_class is None else "STOP_DETERMINISTIC",
            "failure_class": failure_class,
            "world_count": len(receipt["rows"]),
            "rows": receipt["rows"],
            "rows_sha256": ops.value_sha(receipt["rows"]),
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
    except Exception as exc:  # Preserve a classified terminal worker record.
        detail = f"{type(exc).__name__}: {exc}"
        lowered = detail.lower()
        transient = (
            "out of memory" in lowered
            or "cuda_error_out_of_memory" in lowered
            or "driver reset" in lowered
        )
        result = {
            "schema": "tactevra.ws2_c02_shard.v1",
            "scope": SCOPE,
            "fixture_sha256": fixture["fixture_sha256"],
            "campaign_fixture_sha256": fixture["campaign_fixture_sha256"],
            "manifest_sha256": fixture["manifest_sha256"],
            "shard": shard,
            "device": device,
            "status": "STOP_TRANSIENT" if transient else "STOP_DETERMINISTIC",
            "failure_class": (
                "OUT_OF_MEMORY_AT_LAUNCH" if transient else "IDENTITY_MISMATCH"
            ),
            "error": detail,
            "world_count": 0,
            "rows": [],
            "rows_sha256": ops.value_sha([]),
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


def load_valid_result(
    path: Path,
    *,
    shard_id: str,
    fixture: dict[str, Any],
) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    core = dict(result)
    claimed = core.pop("receipt_sha256")
    if ops.value_sha(core) != claimed:
        raise ValueError("C02 shard receipt hash mismatch")
    if result["shard"]["shard_id"] != shard_id:
        raise ValueError("C02 shard identity mismatch")
    if result["fixture_sha256"] != fixture["fixture_sha256"]:
        raise ValueError("C02 supervisor fixture mismatch")
    if result["manifest_sha256"] != fixture["manifest_sha256"]:
        raise ValueError("C02 manifest mismatch")
    if result["rows_sha256"] != ops.value_sha(result["rows"]):
        raise ValueError("C02 row hash mismatch")
    if result["world_count"] != result["shard"]["world_count"]:
        raise ValueError("C02 world count mismatch")
    if result["status"] != "PASS" or result.get("failure_class") is not None:
        raise ValueError("only passing C02 results may resume")
    return result


def compare_cross_gpu(
    fixture: dict[str, Any], left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    for field in (
        "campaign_fixture_sha256",
        "manifest_sha256",
        "rows_sha256",
    ):
        if left.get(field) != right.get(field):
            return {"status": "DISAGREE", "reason": f"binding:{field}"}
    return policy.compare_cross_gpu_results(fixture, left, right)


def reconcile_resume(
    results_root: Path,
    backup_root: Path,
    manifest: dict[str, Any],
    fixture: dict[str, Any],
) -> set[str]:
    expected = {row["shard_id"] for row in manifest["shards"]}
    completed: set[str] = set()
    modulus = int(fixture["integrity"]["cross_gpu_sample_modulus"])
    for source in results_root.glob("*.json"):
        shard_id = source.stem
        if shard_id not in expected:
            continue
        result = load_valid_result(source, shard_id=shard_id, fixture=fixture)
        if int(shard_id[:8], 16) % modulus == 0:
            cross = source.with_suffix(".cross.json")
            if not cross.exists():
                raise ValueError("required C02 cross-GPU result missing")
            other = load_valid_result(cross, shard_id=shard_id, fixture=fixture)
            comparison = compare_cross_gpu(fixture, result, other)
            if comparison["status"] != "AGREE":
                raise ValueError(f"C02 cross-GPU disagreement: {comparison['reason']}")
            cross_destination = backup_root / cross.name
            if cross_destination.exists():
                if _file_sha(cross) != _file_sha(cross_destination):
                    raise ValueError("existing C02 cross-GPU backup hash mismatch")
            else:
                policy.copy_verified(cross, cross_destination)
        destination = backup_root / source.name
        if destination.exists():
            if _file_sha(source) != _file_sha(destination):
                raise ValueError("existing C02 backup hash mismatch")
        else:
            policy.copy_verified(source, destination)
        completed.add(shard_id)
    return completed


def fault_injection_matrix(root: Path, fixture: dict[str, Any]) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    source = root / "backup-source.json"
    source.write_text('{"fault":"backup"}\n', encoding="utf-8")
    backup = root / "backup" / source.name
    copy = policy.copy_verified(source, backup)
    sample_count = int(fixture["early_abort"]["deterministic_sample_shards"])
    all_fail = [
        {
            "world_count": 64,
            "primary_failure_counts": {"PARTIAL_PRESS": 64},
        }
        for _ in range(sample_count)
    ]
    ceiling = float(fixture["thermals"]["pause_ceiling_c"])
    floor = int(fixture["storage"]["clean_stop_floor_bytes"])
    cases = {
        "temperature_over_ceiling": policy.boundary_decision(
            fixture, [ceiling, 40.0], 10**12
        )
        == "PAUSE_THERMAL_AT_BOUNDARY",
        "disk_below_floor": policy.boundary_decision(
            fixture, [40.0, 40.0], floor - 1
        )
        == "STOP_DISK_FLOOR",
        "hung_worker": policy.watchdog_decision(
            now=601.0,
            last_progress=300.0,
            stale_seconds=float(fixture["watchdog"]["stale_seconds"]),
        )
        == "STOP_HUNG_WORKER_ALERT",
        "transient_retry_once_then_success": (
            policy.worker_decision("DRIVER_RESET", 0) == "RETRY_ONCE"
            and policy.worker_decision(None, 1) == "ACCEPT"
        ),
        "deterministic_no_retry": (
            policy.worker_decision("NONFINITE_STATE", 0) == "STOP_PRESERVE"
            and policy.worker_decision("HASH_MISMATCH", 0) == "STOP_PRESERVE"
        ),
        "backup_hash_matches": (
            backup.exists() and copy["sha256"] == _file_sha(source) == _file_sha(backup)
        ),
        "early_abort_all_fail": policy.early_abort_decision(
            all_fail, sample_count
        )
        == "STOP_EARLY_ALL_FAIL",
    }
    result = {
        "schema": "tactevra.ws2_c02_supervisor_fault_matrix.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "cases": cases,
        "status": "PASS" if all(cases.values()) else "STOP",
        "backup_receipt": copy,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = ops.value_sha(result)
    return result


def _command(command: list[str]) -> tuple[int, str]:
    process = subprocess.run(command, capture_output=True, text=True, check=False)
    return process.returncode, (process.stdout + process.stderr).strip()


def _power_value(alias: str) -> tuple[bool, str]:
    code, output = _command(["powercfg", "/query", "SCHEME_CURRENT", "SUB_SLEEP", alias])
    return code == 0 and "Current AC Power Setting Index: 0x00000000" in output, output


def _restart_policy() -> tuple[bool, str]:
    code, output = _command(
        [
            "reg",
            "query",
            r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU",
            "/v",
            "NoAutoRebootWithLoggedOnUsers",
        ]
    )
    return code == 0 and "0x1" in output.lower(), output


def _gpu_snapshot() -> list[dict[str, Any]]:
    ok, rows, detail = ops._gpu_snapshot()
    if not ok:
        raise RuntimeError(f"GPU telemetry unavailable: {detail}")
    return rows


def _load_fault_receipt(path: Path, fixture: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    core = dict(result)
    claimed = core.pop("receipt_sha256")
    if ops.value_sha(core) != claimed or result["fixture_sha256"] != fixture["fixture_sha256"]:
        raise ValueError("C02 fault-matrix receipt mismatch")
    return result


def run_preflight(fixture: dict[str, Any]) -> dict[str, Any]:
    _, _, manifest = load_bound_campaign(fixture)
    resume = ops.resume_proof()
    sleep_ok, sleep_detail = _power_value("STANDBYIDLE")
    hibernate_ok, hibernate_detail = _power_value("HIBERNATEIDLE")
    restart_ok, restart_detail = _restart_policy()
    gpu_rows = _gpu_snapshot()
    temperature_ok = all(
        row["temperature_c"] < fixture["thermals"]["pause_ceiling_c"]
        for row in gpu_rows
    )
    output_root = Path(fixture["storage"]["output_root"])
    backup_root = Path(fixture["storage"]["backup_root"])
    output_root.mkdir(parents=True, exist_ok=True)
    backup_root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(output_root.anchor)
    projected = int(fixture["storage"]["projected_output_bytes"])
    disk_ok = usage.free >= 3 * projected and usage.free >= int(
        fixture["storage"]["clean_stop_floor_bytes"]
    )
    backup_ok = (
        backup_root.drive != ""
        and Path(backup_root.anchor).exists()
        and os.access(backup_root.anchor, os.W_OK)
        and output_root.drive.casefold() != backup_root.drive.casefold()
    )
    probe_results = [
        load_valid_result(
            Path(fixture["preflight_probes"][device]),
            shard_id=fixture["preflight_probes"]["shard_id"],
            fixture=fixture,
        )
        for device in ("cuda0", "cuda1")
    ]
    comparison = compare_cross_gpu(fixture, probe_results[0], probe_results[1])
    probe_ok = (
        comparison["status"] == "AGREE"
        and all(
            row["world_count"] == fixture["preflight_probes"]["world_count"]
            for row in probe_results
        )
    )
    combined_rate = sum(
        row["world_count"] / row["wall_elapsed_seconds"] for row in probe_results
    )
    projected_wall = manifest["population"]["world_count"] / combined_rate
    throughput_ok = projected_wall <= fixture["schedule"]["maximum_projected_wall_seconds"]
    half = int(fixture["schedule"]["half_shard_count"])
    shards = manifest["shards"]
    halves_ok = len(shards[:half]) == half and len(shards[half:]) == half
    fault = _load_fault_receipt(
        Path(fixture["preflight_probes"]["fault_matrix"]), fixture
    )
    checks = {
        "bindings_manifest_and_population": True,
        "deterministic_halves": halves_ok,
        "resume_hash_equivalence": resume["match"],
        "sleep_disabled_ac": sleep_ok,
        "hibernation_disabled_ac": hibernate_ok,
        "automatic_update_restart_disabled": restart_ok,
        "maximum_shard_survives_both_gpus": probe_ok,
        "projected_runtime_within_budget": throughput_ok,
        "disk_three_x_headroom_and_floor": disk_ok,
        "independent_writable_backup_volume": backup_ok,
        "gpu_telemetry_available_and_below_ceiling": temperature_ok,
        "fault_injection_matrix": fault["status"] == "PASS",
        "watchdog_policy_declared": fixture["watchdog"]["stale_seconds"] > 0,
        "cross_gpu_sampling_declared": fixture["integrity"][
            "cross_gpu_sample_modulus"
        ]
        > 0,
        "base_campaign_still_requires_preflight": fixture[
            "base_campaign_full_execution_authorized"
        ]
        is False,
    }
    result = {
        "schema": "tactevra.ws2_c02_preflight_result.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "manifest_sha256": manifest["manifest_sha256"],
        "checks": checks,
        "status": (
            "PASS_READY_FOR_AUTHORIZATION_AMENDMENT"
            if all(checks.values())
            else "STOP_PREFLIGHT"
        ),
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "resume_proof": resume,
        "fault_matrix_receipt_sha256": fault["receipt_sha256"],
        "cross_gpu_probe": comparison,
        "population": manifest["population"],
        "throughput": {
            "combined_worlds_per_second": combined_rate,
            "projected_wall_seconds": projected_wall,
            "maximum_projected_wall_seconds": fixture["schedule"][
                "maximum_projected_wall_seconds"
            ],
        },
        "storage": {
            "free_bytes": usage.free,
            "projected_output_bytes": projected,
            "required_three_x_bytes": 3 * projected,
            "floor_bytes": fixture["storage"]["clean_stop_floor_bytes"],
            "output_root": str(output_root),
            "backup_root": str(backup_root),
        },
        "gpu_snapshot": gpu_rows,
        "windows_details": {
            "sleep": sleep_detail,
            "hibernate": hibernate_detail,
            "automatic_restart": restart_detail,
        },
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = ops.value_sha(result)
    return result


def _worker_command(
    fixture_path: Path, shard_id: str, device: str, output: Path
) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "worker",
        "--fixture",
        str(fixture_path),
        "--shard-id",
        shard_id,
        "--device",
        device,
        "--output",
        str(output),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    worker = subparsers.add_parser("worker")
    worker.add_argument("--fixture", type=Path, required=True)
    worker.add_argument("--shard-id", required=True)
    worker.add_argument("--device", choices=("cuda:0", "cuda:1"), required=True)
    worker.add_argument("--output", type=Path, required=True)
    faults = subparsers.add_parser("fault-matrix")
    faults.add_argument("--fixture", type=Path, required=True)
    faults.add_argument("--root", type=Path, required=True)
    faults.add_argument("--output", type=Path, required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--fixture", type=Path, required=True)
    preflight.add_argument("--output", type=Path, required=True)
    manifest_mode = subparsers.add_parser("manifest")
    manifest_mode.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "worker":
        result = execute_shard(args.fixture, args.shard_id, args.device, args.output)
    elif args.mode == "fault-matrix":
        result = fault_injection_matrix(args.root, load_fixture(args.fixture))
        _atomic_json(args.output, result)
    elif args.mode == "preflight":
        result = run_preflight(load_fixture(args.fixture))
        _atomic_json(args.output, result)
    else:
        _, _, result = load_bound_campaign(load_fixture(args.fixture))
    print(json.dumps({"status": result.get("status", "PASS")}, sort_keys=True))


if __name__ == "__main__":
    main()
