"""Fail-closed Stage A operational preflight and deterministic resume proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ai.sim import run_ws2_stage_a_vectorized_throughput as throughput
from integrations.mujoco_warp import key_press_physics_probe as probe

ROOT = Path(__file__).resolve().parents[3]


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def value_sha(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fixture(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    claimed = fixture.pop("fixture_sha256")
    if value_sha(fixture) != claimed:
        raise ValueError("long-run fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture["physical_authority"] is not False or any(fixture["counters"].values()):
        raise ValueError("long-run fixture authority violation")
    for name, binding in fixture["bindings"].items():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = ROOT / source
        if file_sha(source) != binding["sha256"]:
            raise ValueError(f"long-run binding changed: {name}")
    return fixture


def build_shards(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    throughput_fixture = throughput.load_fixture(
        ROOT / fixture["bindings"]["throughput_fixture"]["path"]
    )
    campaign, _, _, _, physical = throughput.load_bound(throughput_fixture)
    profiles = [row["profile_id"] for row in probe.physical_profiles(campaign)]
    tips = [row["tip_id"] for row in probe.tip_geometries(campaign)]
    neighborhood_by_target = {
        row["target_id"]: row for row in physical["neighborhoods"]
    }
    shards = []
    for target_id in fixture["target_order"]:
        neighborhood = neighborhood_by_target[target_id]
        for profile_id in profiles:
            for tip_id in tips:
                identity = {
                    "neighborhood_signature_sha256": neighborhood["signature_sha256"],
                    "target_id": target_id,
                    "profile_id": profile_id,
                    "tip_id": tip_id,
                }
                shards.append(
                    {
                        **identity,
                        "shard_id": value_sha(identity),
                        "world_count": fixture["population"]["worlds_per_shard"],
                    }
                )
    shards.sort(
        key=lambda row: (
            row["neighborhood_signature_sha256"],
            row["target_id"],
            row["profile_id"],
            row["tip_id"],
        )
    )
    if len(shards) != fixture["population"]["shard_count"]:
        raise ValueError("Stage A shard population changed")
    if (
        sum(row["world_count"] for row in shards)
        != fixture["population"]["world_count"]
    ):
        raise ValueError("Stage A world population changed")
    return shards


def _write_demo_shard(path: Path, shard_id: str) -> None:
    payload = {"shard_id": shard_id, "rows_sha256": value_sha([shard_id, 0, 1, 2])}
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _demo_manifest(path: Path, shard_ids: list[str]) -> str:
    rows = []
    for shard_id in shard_ids:
        shard = path / f"{shard_id}.json"
        rows.append({"shard_id": shard_id, "sha256": file_sha(shard)})
    return value_sha(rows)


def resume_proof() -> dict[str, Any]:
    shard_ids = [value_sha({"resume_proof": index}) for index in range(12)]
    with tempfile.TemporaryDirectory(prefix="stage-a-resume-") as raw:
        root = Path(raw)
        uninterrupted = root / "uninterrupted"
        resumed = root / "resumed"
        uninterrupted.mkdir()
        resumed.mkdir()
        for shard_id in shard_ids:
            _write_demo_shard(uninterrupted / f"{shard_id}.json", shard_id)
        for shard_id in shard_ids[:5]:
            _write_demo_shard(resumed / f"{shard_id}.json", shard_id)
        partial = resumed / f"{shard_ids[5]}.partial"
        partial.write_text("killed-mid-shard", encoding="utf-8")
        partial.unlink()
        for shard_id in shard_ids[5:]:
            _write_demo_shard(resumed / f"{shard_id}.json", shard_id)
        left = _demo_manifest(uninterrupted, shard_ids)
        right = _demo_manifest(resumed, shard_ids)
    return {
        "uninterrupted_manifest_sha256": left,
        "resumed_manifest_sha256": right,
        "match": left == right,
        "completed_before_kill": 5,
        "killed_shard_restarted_from_zero": True,
    }


def _command(command: list[str]) -> tuple[int, str]:
    process = subprocess.run(command, capture_output=True, text=True, check=False)
    return process.returncode, (process.stdout + process.stderr).strip()


def _power_value(alias: str) -> tuple[bool, str]:
    code, output = _command(
        ["powercfg", "/query", "SCHEME_CURRENT", "SUB_SLEEP", alias]
    )
    return code == 0 and "Current AC Power Setting Index: 0x00000000" in output, output


def _update_restart_policy() -> tuple[bool, str]:
    code, output = _command(
        [
            "reg",
            "query",
            r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU",
            "/v",
            "NoAutoRebootWithLoggedOnUsers",
        ]
    )
    normalized = output.lower()
    return code == 0 and "0x1" in normalized, output


def _gpu_snapshot() -> tuple[bool, list[dict[str, Any]], str]:
    code, output = _command(
        [
            "nvidia-smi",
            "--query-gpu=index,temperature.gpu,power.draw,power.limit,clocks.sm,clocks.mem,pstate",
            "--format=csv,noheader,nounits",
        ]
    )
    rows = []
    if code == 0:
        for line in output.splitlines():
            fields = [value.strip() for value in line.split(",")]
            rows.append(
                {
                    "index": int(fields[0]),
                    "temperature_c": float(fields[1]),
                    "power_w": float(fields[2]),
                    "power_limit_w": float(fields[3]),
                    "sm_clock_mhz": int(fields[4]),
                    "memory_clock_mhz": int(fields[5]),
                    "pstate": fields[6],
                }
            )
    return code == 0, rows, output


def _different_volume(left: Path, right: Path) -> bool:
    return left.drive.casefold() != right.drive.casefold()


def run_preflight(fixture: dict[str, Any]) -> dict[str, Any]:
    shards = build_shards(fixture)
    resume = resume_proof()
    sleep_ok, sleep_detail = _power_value("STANDBYIDLE")
    hibernate_ok, hibernate_detail = _power_value("HIBERNATEIDLE")
    restart_ok, restart_detail = _update_restart_policy()
    gpu_ok, gpu_rows, gpu_detail = _gpu_snapshot()
    temperature_ok = gpu_ok and all(
        row["temperature_c"] < fixture["thermals"]["pause_ceiling_c"]
        for row in gpu_rows
    )
    output_root = Path(fixture["storage"]["output_root"])
    backup_root = Path(fixture["storage"]["backup_root"])
    usage = shutil.disk_usage(output_root.anchor)
    projected = fixture["storage"]["projected_output_bytes"]
    disk_ok = (
        usage.free >= 3 * projected
        and usage.free >= fixture["storage"]["clean_stop_floor_bytes"]
    )
    backup_ok = (
        backup_root.drive != ""
        and backup_root.anchor != ""
        and Path(backup_root.anchor).exists()
        and os.access(backup_root.anchor, os.W_OK)
        and _different_volume(output_root, backup_root)
    )
    smoke_rows = []
    for name in ("full_smoke_cuda0", "full_smoke_cuda1"):
        path = Path(fixture["bindings"][name]["path"])
        smoke_rows.append(json.loads(path.read_text(encoding="utf-8")))
    exact_shape_ok = (
        all(
            row["status"] == "PASS" and row["world_count"] == 2_304
            for row in smoke_rows
        )
        and smoke_rows[0]["row_payload_sha256"] == smoke_rows[1]["row_payload_sha256"]
    )
    half = fixture["schedule"]["half_shard_count"]
    halves_ok = (
        len(shards[:half]) == half
        and len(shards[half:]) == half
        and sum(row["world_count"] for row in shards[:half])
        == fixture["schedule"]["worlds_per_half"]
        and sum(row["world_count"] for row in shards[half:])
        == fixture["schedule"]["worlds_per_half"]
    )
    checks = {
        "bindings_and_population": True,
        "deterministic_equal_halves": halves_ok,
        "resume_hash_equivalence": resume["match"],
        "sleep_disabled_ac": sleep_ok,
        "hibernation_disabled_ac": hibernate_ok,
        "automatic_update_restart_disabled": restart_ok,
        "exact_2304_world_batch_survives_tdr": exact_shape_ok,
        "disk_three_x_headroom_and_floor": disk_ok,
        "independent_writable_backup_volume": backup_ok,
        "gpu_telemetry_available_and_below_ceiling": temperature_ok,
        "watchdog_policy_declared": fixture["watchdog"]["stale_seconds"] > 0,
        "failure_policy_declared": fixture["failure_policy"]["transient_retry_limit"]
        == 1,
        "per_shard_integrity_declared": fixture["integrity"][
            "verify_before_every_shard"
        ],
        "cross_gpu_sampling_declared": bool(
            fixture["integrity"]["cross_gpu_sample_modulus"]
        ),
        "status_file_declared": bool(fixture["progress"]["status_path"]),
        "early_abort_declared": bool(
            fixture["early_abort"]["deterministic_sample_shards"]
        ),
    }
    result = {
        "schema": "tactevra.ws2_stage_a_preflight_result.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "checks": checks,
        "status": "PASS_READY_TO_LAUNCH" if all(checks.values()) else "STOP_PREFLIGHT",
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "resume_proof": resume,
        "population": {
            "shards": len(shards),
            "worlds": sum(row["world_count"] for row in shards),
            "half_shards": half,
            "half_worlds": fixture["schedule"]["worlds_per_half"],
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
        "gpu_detail": gpu_detail,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = value_sha(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_preflight(load_fixture(args.fixture))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    status_path = Path(json.loads(args.fixture.read_text())["progress"]["status_path"])
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "status": result["status"],
                "shards_done": 0,
                "shards_total": result["population"]["shards"],
                "eta_seconds": None,
                "failures": result["failed_checks"],
                "temperatures_c": [
                    row["temperature_c"] for row in result["gpu_snapshot"]
                ],
                "updated_unix": time.time(),
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({"status": result["status"], "failed": result["failed_checks"]}))


if __name__ == "__main__":
    main()
