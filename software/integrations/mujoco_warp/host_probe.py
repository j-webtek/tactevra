"""Validate the pinned MuJoCo Warp host before importing simulator modules."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path
from typing import Any


def collect_observed(package_names: list[str]) -> dict[str, Any]:
    """Collect package metadata and GPU identity without importing the simulator."""
    command = [
        "nvidia-smi",
        "--query-gpu=uuid,name,driver_version,compute_cap",
        "--format=csv,noheader,nounits",
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    gpus = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        uuid, name, driver, capability = (part.strip() for part in line.split(",", 3))
        gpus.append(
            {
                "uuid": uuid,
                "name": name,
                "driver_version": driver,
                "compute_capability": capability,
            }
        )
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name) for name in package_names},
        "gpus": gpus,
    }


def validate_lock(lock: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    """Return a fail-closed result; this function never imports MuJoCo or Warp."""
    errors: list[str] = []
    if lock.get("schema") != "rocell.mujoco_warp_toolchain_lock.v1":
        errors.append("unsupported lock schema")
    if observed.get("python_version") != lock.get("python_version"):
        errors.append("python version mismatch")
    expected_packages = lock.get("packages", {})
    for name in expected_packages:
        if observed.get("packages", {}).get(name) != expected_packages.get(name):
            errors.append(f"package mismatch: {name}")

    expected_host = lock.get("host", {})
    if not str(observed.get("platform", "")).startswith(expected_host.get("platform_prefix", "")):
        errors.append("platform mismatch")
    gpus = observed.get("gpus", [])
    if len(gpus) < expected_host.get("minimum_gpu_count", 0):
        errors.append("insufficient GPU count")
    if [gpu.get("uuid") for gpu in gpus] != expected_host.get("gpu_uuids"):
        errors.append("GPU identity or order mismatch")
    for gpu in gpus:
        if gpu.get("name") != expected_host.get("gpu_name"):
            errors.append("GPU name mismatch")
        if gpu.get("driver_version") != expected_host.get("driver_version"):
            errors.append("driver version mismatch")
        if gpu.get("compute_capability") != expected_host.get("compute_capability"):
            errors.append("compute capability mismatch")

    return {
        "schema": "rocell.mujoco_warp_host_probe.v1",
        "status": "PASS" if not errors else "REJECTED_LOCK_MISMATCH",
        "errors": errors,
        "observed": observed,
        "simulator_modules_imported": False,
        "model_load_attempted": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--observed-fixture", type=Path)
    args = parser.parse_args()
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    observed = (
        json.loads(args.observed_fixture.read_text(encoding="utf-8"))["observed"]
        if args.observed_fixture
        else collect_observed(list(lock.get("packages", {})))
    )
    result = validate_lock(lock, observed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
