"""Frozen MW2 MuJoCo/MuJoCo-Warp batch, overflow, and repeatability probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any


EXPECTED_MJCF_SHA256 = "448b711ae30ed3df8a5f5eff66ecb53034f6540eade7264388d86e3911a7a8a0"
WORLD_COUNTS = [1, 32, 256, 1024, 4096]
REPEATS = 3
WARMUP_STEPS = 16
TIMED_STEPS = 128
NUMERICAL_REPEATABILITY_LIMIT = 1e-6
TIMING_CV_LIMIT = 0.25
TARGET_WORLD_COUNTS = [1024, 4096]
MINIMUM_SPEEDUP = 3.0
INITIAL_QPOS = [0.0, 0.0, 2.618, -1.0472, 0.0, 0.0]
INITIAL_QVEL = [0.0, 0.0, -0.05, 0.0, 0.0, 0.0]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _summary(values) -> dict[str, Any]:
    import numpy as np

    array = np.asarray(values, dtype=np.float64)
    return {
        "shape": list(array.shape),
        "minimum": float(array.min()),
        "maximum": float(array.max()),
        "mean": float(array.mean()),
        "sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest(),
    }


def _repeatability(finals: list[tuple[Any, Any]]) -> dict[str, float]:
    import numpy as np

    qpos_ref, qvel_ref = finals[0]
    return {
        "maximum_qpos_delta": max(
            float(np.max(np.abs(qpos - qpos_ref))) for qpos, _ in finals[1:]
        ),
        "maximum_qvel_delta": max(
            float(np.max(np.abs(qvel - qvel_ref))) for _, qvel in finals[1:]
        ),
    }


def _timing_summary(throughputs: list[float]) -> dict[str, float]:
    mean = statistics.mean(throughputs)
    return {
        "median_world_steps_per_second": statistics.median(throughputs),
        "mean_world_steps_per_second": mean,
        "timing_cv": statistics.pstdev(throughputs) / mean if mean else math.inf,
        "median_observations_per_hour": statistics.median(throughputs) * 3600,
    }


def run_standard(mjcf: Path) -> dict[str, Any]:
    import mujoco
    import numpy as np

    model = mujoco.MjModel.from_xml_path(str(mjcf))
    results = []
    for nworld in WORLD_COUNTS:
        repeats = []
        finals = []
        for repeat in range(REPEATS):
            worlds = [mujoco.MjData(model) for _ in range(nworld)]
            for data in worlds:
                data.qpos[:] = INITIAL_QPOS
                data.qvel[:] = INITIAL_QVEL
            for _ in range(WARMUP_STEPS):
                for data in worlds:
                    mujoco.mj_step(model, data)
            started = time.perf_counter()
            for _ in range(TIMED_STEPS):
                for data in worlds:
                    mujoco.mj_step(model, data)
            elapsed = time.perf_counter() - started
            qpos = np.stack([data.qpos.copy() for data in worlds])
            qvel = np.stack([data.qvel.copy() for data in worlds])
            finals.append((qpos, qvel))
            repeats.append(
                {
                    "repeat": repeat,
                    "elapsed_seconds": elapsed,
                    "world_steps_per_second": nworld * TIMED_STEPS / elapsed,
                    "finite": bool(np.isfinite(qpos).all() and np.isfinite(qvel).all()),
                    "qpos": _summary(qpos),
                    "qvel": _summary(qvel),
                }
            )
        repeatability = _repeatability(finals)
        timing = _timing_summary([item["world_steps_per_second"] for item in repeats])
        results.append(
            {
                "nworld": nworld,
                "repeats": repeats,
                "repeatability": repeatability,
                "timing": timing,
                "pass": all(item["finite"] for item in repeats)
                and repeatability["maximum_qpos_delta"] <= NUMERICAL_REPEATABILITY_LIMIT
                and repeatability["maximum_qvel_delta"] <= NUMERICAL_REPEATABILITY_LIMIT,
            }
        )
    return _receipt("standard-mujoco", "cpu", mjcf, results)


def _free_memory(device) -> int | None:
    value = getattr(device, "free_memory", None)
    return int(value) if value is not None else None


def run_warp(mjcf: Path, device_name: str) -> dict[str, Any]:
    import mujoco
    import mujoco_warp as mjw
    import numpy as np
    import warp as wp

    wp.init()
    wp.set_device(device_name)
    device = wp.get_device()
    model = mujoco.MjModel.from_xml_path(str(mjcf))
    seed = mujoco.MjData(model)
    seed.qpos[:] = INITIAL_QPOS
    seed.qvel[:] = INITIAL_QVEL
    transfer_started = time.perf_counter()
    warp_model = mjw.put_model(model)
    model_transfer_seconds = time.perf_counter() - transfer_started
    results = []
    for nworld in WORLD_COUNTS:
        repeats = []
        finals = []
        for repeat in range(REPEATS):
            free_before = _free_memory(device)
            data_started = time.perf_counter()
            data = mjw.put_data(model, seed, nworld=nworld)
            data_transfer_seconds = time.perf_counter() - data_started
            for _ in range(WARMUP_STEPS):
                mjw.step(warp_model, data)
            wp.synchronize_device(device)
            started = time.perf_counter()
            for _ in range(TIMED_STEPS):
                mjw.step(warp_model, data)
            wp.synchronize_device(device)
            elapsed = time.perf_counter() - started
            qpos = np.asarray(data.qpos.numpy(), dtype=np.float64)
            qvel = np.asarray(data.qvel.numpy(), dtype=np.float64)
            overflow = np.asarray(data.overflow.numpy()).astype(np.int64)
            free_after = _free_memory(device)
            finals.append((qpos, qvel))
            repeats.append(
                {
                    "repeat": repeat,
                    "data_transfer_seconds": data_transfer_seconds,
                    "elapsed_seconds": elapsed,
                    "world_steps_per_second": nworld * TIMED_STEPS / elapsed,
                    "finite": bool(np.isfinite(qpos).all() and np.isfinite(qvel).all()),
                    "overflow": overflow.tolist(),
                    "overflow_zero": bool((overflow == 0).all()),
                    "world_count_preserved": qpos.shape[0] == nworld,
                    "free_memory_before": free_before,
                    "free_memory_after": free_after,
                    "resident_memory_delta": (
                        None if free_before is None or free_after is None else free_before - free_after
                    ),
                    "qpos": _summary(qpos),
                    "qvel": _summary(qvel),
                }
            )
        repeatability = _repeatability(finals)
        timing = _timing_summary([item["world_steps_per_second"] for item in repeats])
        results.append(
            {
                "nworld": nworld,
                "repeats": repeats,
                "repeatability": repeatability,
                "timing": timing,
                "pass": all(
                    item["finite"] and item["overflow_zero"] and item["world_count_preserved"]
                    for item in repeats
                )
                and repeatability["maximum_qpos_delta"] <= NUMERICAL_REPEATABILITY_LIMIT
                and repeatability["maximum_qvel_delta"] <= NUMERICAL_REPEATABILITY_LIMIT
                and timing["timing_cv"] <= TIMING_CV_LIMIT,
            }
        )
    receipt = _receipt("mujoco-warp", device_name, mjcf, results)
    receipt["model_transfer_seconds"] = model_transfer_seconds
    receipt["device"] = {
        "alias": str(device),
        "name": device.name,
        "total_memory": int(device.total_memory),
        "free_memory_at_end": _free_memory(device),
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def _receipt(backend: str, device: str, mjcf: Path, results: list[dict]) -> dict[str, Any]:
    receipt = {
        "schema": "rocell.mujoco_warp_batch_probe.v1",
        "backend": backend,
        "device_requested": device,
        "mjcf_sha256": sha256(mjcf),
        "fixture": {
            "world_counts": WORLD_COUNTS,
            "repeats": REPEATS,
            "warmup_steps": WARMUP_STEPS,
            "timed_steps": TIMED_STEPS,
            "initial_qpos": INITIAL_QPOS,
            "initial_qvel": INITIAL_QVEL,
        },
        "gates": {
            "numerical_repeatability_limit": NUMERICAL_REPEATABILITY_LIMIT,
            "timing_cv_limit": TIMING_CV_LIMIT,
            "target_world_counts": TARGET_WORLD_COUNTS,
            "minimum_speedup": MINIMUM_SPEEDUP,
        },
        "results": results,
        "safety_pass": all(item["pass"] for item in results),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def admit(standard: dict, gpu0: dict, gpu1: dict) -> dict[str, Any]:
    shards = [gpu0, gpu1]
    errors = []
    for item in [standard, *shards]:
        if item.get("mjcf_sha256") != EXPECTED_MJCF_SHA256:
            errors.append(f'{item.get("device_requested")}: MJCF hash mismatch')
        if not item.get("safety_pass"):
            errors.append(f'{item.get("device_requested")}: safety/repeatability gate failed')
    standard_by_size = {item["nworld"]: item for item in standard["results"]}
    speedups = {}
    for shard in shards:
        values = {}
        for result in shard["results"]:
            baseline = standard_by_size[result["nworld"]]["timing"]["median_world_steps_per_second"]
            values[str(result["nworld"])] = (
                result["timing"]["median_world_steps_per_second"] / baseline
            )
        speedups[shard["device_requested"]] = values
        for nworld in TARGET_WORLD_COUNTS:
            if values[str(nworld)] < MINIMUM_SPEEDUP:
                errors.append(f'{shard["device_requested"]}: speedup below gate at {nworld}')
    result = {
        "schema": "rocell.mujoco_warp_batch_admission.v1",
        "status": "ADOPT_FOR_DECLARED_SCOPE" if not errors else "RESEARCH_ONLY",
        "errors": errors,
        "speedups_vs_standard_mujoco": speedups,
        "source_receipt_sha256": {
            "standard": standard["receipt_sha256"],
            "cuda:0": gpu0["receipt_sha256"],
            "cuda:1": gpu1["receipt_sha256"],
        },
        "world_counts": WORLD_COUNTS,
        "target_world_counts": TARGET_WORLD_COUNTS,
        "minimum_speedup": MINIMUM_SPEEDUP,
        "dual_gpu_aggregation_performed": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
        "limitations": [
            "kinematic-only placeholder inertia",
            "no rendering, contacts, collision geometry, or actuator workload",
            "device shards remain separate",
        ],
    }
    result["receipt_sha256"] = canonical_sha256(result)
    return result


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--backend", choices=("standard-mujoco", "mujoco-warp"), required=True)
    run.add_argument("--device", default="cuda:0")
    run.add_argument("--mjcf", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    admission = subparsers.add_parser("admit")
    admission.add_argument("--standard", type=Path, required=True)
    admission.add_argument("--gpu0", type=Path, required=True)
    admission.add_argument("--gpu1", type=Path, required=True)
    admission.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run":
        if sha256(args.mjcf) != EXPECTED_MJCF_SHA256:
            raise ValueError("MJCF hash mismatch")
        result = (
            run_standard(args.mjcf)
            if args.backend == "standard-mujoco"
            else run_warp(args.mjcf, args.device)
        )
    else:
        result = admit(_load(args.standard), _load(args.gpu0), _load(args.gpu1))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result.get("status", result.get("safety_pass")), "receipt_sha256": result["receipt_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
