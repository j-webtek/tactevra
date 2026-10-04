"""MW2R large-batch specialization probe with deterministic diverse worlds."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


EXPECTED_MJCF_SHA256 = "448b711ae30ed3df8a5f5eff66ecb53034f6540eade7264388d86e3911a7a8a0"
WORLD_COUNTS = [4096, 8192, 16384]
REPEATS = 3
WARMUP_STEPS = 16
TIMED_STEPS = 128
POSE_SEED = 190201
NUMERICAL_REPEATABILITY_LIMIT = 1e-6
TIMING_CV_LIMIT = 0.25
FROZEN_STANDARD_4096_WORLD_STEPS_PER_SECOND = 325123.39
MINIMUM_CPU_SPEEDUP = 3.0
MINIMUM_WORLD_STEPS_PER_SECOND = (
    FROZEN_STANDARD_4096_WORLD_STEPS_PER_SECOND * MINIMUM_CPU_SPEEDUP
)
MINIMUM_SCALING_EFFICIENCY = 0.85
MINIMUM_CONCURRENT_SCALING = 1.70
JOINT_LIMITS = [
    (-3.1416, 3.1416),
    (-1.5708, 1.5708),
    (-1.0, 2.95),
    (-1.5708, 1.5708),
    (-3.1416, 3.1416),
    (0.0, 1.5),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _initial_states(nworld: int):
    import numpy as np

    rng = np.random.default_rng(POSE_SEED + nworld)
    qpos = np.empty((nworld, 6), dtype=np.float32)
    for index, (lower, upper) in enumerate(JOINT_LIMITS):
        margin = 0.1 * (upper - lower)
        qpos[:, index] = rng.uniform(lower + margin, upper - margin, size=nworld)
    qvel = rng.uniform(-0.025, 0.025, size=(nworld, 6)).astype(np.float32)
    return qpos, qvel


def _free_memory(device) -> int | None:
    value = getattr(device, "free_memory", None)
    return int(value) if value is not None else None


def _summary(array) -> dict[str, Any]:
    import numpy as np

    value = np.asarray(array, dtype=np.float64)
    return {
        "shape": list(value.shape),
        "minimum": float(value.min()),
        "maximum": float(value.max()),
        "mean": float(value.mean()),
        "sha256": hashlib.sha256(value.tobytes(order="C")).hexdigest(),
    }


def run_device(mjcf: Path, device_name: str, counts: list[int]) -> dict[str, Any]:
    import mujoco
    import mujoco_warp as mjw
    import numpy as np
    import warp as wp

    if sha256(mjcf) != EXPECTED_MJCF_SHA256:
        raise ValueError("MJCF hash mismatch")
    if any(count not in WORLD_COUNTS for count in counts):
        raise ValueError("world count outside frozen MW2R matrix")
    wp.init()
    wp.set_device(device_name)
    device = wp.get_device()
    model = mujoco.MjModel.from_xml_path(str(mjcf))
    seed = mujoco.MjData(model)
    warp_model = mjw.put_model(model)
    results = []
    for nworld in counts:
        initial_qpos, initial_qvel = _initial_states(nworld)
        repeats = []
        final_states = []
        for repeat in range(REPEATS):
            free_before = _free_memory(device)
            data = mjw.put_data(model, seed, nworld=nworld)
            data.qpos.assign(initial_qpos)
            data.qvel.assign(initial_qvel)
            mjw.forward(warp_model, data)
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
            final_states.append((qpos, qvel))
            repeats.append(
                {
                    "repeat": repeat,
                    "elapsed_seconds": elapsed,
                    "world_steps_per_second": nworld * TIMED_STEPS / elapsed,
                    "finite": bool(np.isfinite(qpos).all() and np.isfinite(qvel).all()),
                    "overflow": overflow.tolist(),
                    "overflow_zero": bool((overflow == 0).all()),
                    "world_count_preserved": qpos.shape[0] == nworld,
                    "resident_memory_delta": (
                        None if free_before is None or free_after is None else free_before - free_after
                    ),
                    "qpos": _summary(qpos),
                    "qvel": _summary(qvel),
                }
            )
        rates = [item["world_steps_per_second"] for item in repeats]
        median_rate = statistics.median(rates)
        mean_rate = statistics.mean(rates)
        qpos_reference, qvel_reference = final_states[0]
        qpos_delta = max(
            float(np.max(np.abs(qpos - qpos_reference))) for qpos, _ in final_states[1:]
        )
        qvel_delta = max(
            float(np.max(np.abs(qvel - qvel_reference))) for _, qvel in final_states[1:]
        )
        timing_cv = statistics.pstdev(rates) / mean_rate
        results.append(
            {
                "nworld": nworld,
                "initial_qpos_sha256": hashlib.sha256(initial_qpos.tobytes()).hexdigest(),
                "initial_qvel_sha256": hashlib.sha256(initial_qvel.tobytes()).hexdigest(),
                "unique_initial_poses": int(np.unique(initial_qpos, axis=0).shape[0]),
                "repeats": repeats,
                "median_world_steps_per_second": median_rate,
                "median_observations_per_hour": median_rate * 3600,
                "timing_cv": timing_cv,
                "maximum_qpos_delta": qpos_delta,
                "maximum_qvel_delta": qvel_delta,
                "pass": all(
                    item["finite"] and item["overflow_zero"] and item["world_count_preserved"]
                    for item in repeats
                )
                and qpos_delta <= NUMERICAL_REPEATABILITY_LIMIT
                and qvel_delta <= NUMERICAL_REPEATABILITY_LIMIT
                and timing_cv <= TIMING_CV_LIMIT,
            }
        )
    receipt = {
        "schema": "rocell.mujoco_warp_large_batch_probe.v1",
        "scope": "LARGE_BATCH_KINEMATIC_RESEARCH_ONLY",
        "device_requested": device_name,
        "device_name": device.name,
        "mjcf_sha256": EXPECTED_MJCF_SHA256,
        "world_counts": counts,
        "repeats": REPEATS,
        "warmup_steps": WARMUP_STEPS,
        "timed_steps": TIMED_STEPS,
        "pose_seed": POSE_SEED,
        "results": results,
        "safety_pass": all(item["pass"] for item in results),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def run_concurrent(mjcf: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    commands = []
    processes = []
    started = time.perf_counter()
    for index in (0, 1):
        output = output_dir / f"concurrent_cuda{index}.json"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "run",
            "--device",
            f"cuda:{index}",
            "--mjcf",
            str(mjcf),
            "--counts",
            "4096",
            "--output",
            str(output),
        ]
        commands.append(command)
        processes.append(subprocess.Popen(command))
    return_codes = [process.wait() for process in processes]
    wall_seconds = time.perf_counter() - started
    if return_codes != [0, 0]:
        raise RuntimeError(f"concurrent child failure: {return_codes}")
    children = [json.loads((output_dir / f"concurrent_cuda{i}.json").read_text()) for i in (0, 1)]
    rates = [child["results"][0]["median_world_steps_per_second"] for child in children]
    result = {
        "schema": "rocell.mujoco_warp_concurrent_shards.v1",
        "scope": "TWO_INDEPENDENT_4096_WORLD_SHARDS",
        "wall_seconds_including_process_startup": wall_seconds,
        "child_receipt_sha256": [child["receipt_sha256"] for child in children],
        "child_file_sha256": [
            sha256(output_dir / f"concurrent_cuda{i}.json") for i in (0, 1)
        ],
        "child_median_world_steps_per_second": rates,
        "aggregate_median_world_steps_per_second": sum(rates),
        "safety_pass": all(child["safety_pass"] for child in children),
        "peer_access_used": False,
        "shared_state_used": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = canonical_sha256(result)
    return result


def admit(gpu0: dict, gpu1: dict, concurrent: dict) -> dict[str, Any]:
    errors = []
    for shard in (gpu0, gpu1):
        if shard.get("mjcf_sha256") != EXPECTED_MJCF_SHA256:
            errors.append(f'{shard.get("device_requested")}: MJCF hash mismatch')
        if shard.get("world_counts") != WORLD_COUNTS:
            errors.append(f'{shard.get("device_requested")}: world matrix mismatch')
        if not shard.get("safety_pass"):
            errors.append(f'{shard.get("device_requested")}: safety gate failed')
        rates = [item["median_world_steps_per_second"] for item in shard["results"]]
        if any(rate < MINIMUM_WORLD_STEPS_PER_SECOND for rate in rates):
            errors.append(f'{shard.get("device_requested")}: throughput floor failed')
        if min(rates[1:]) / rates[0] < MINIMUM_SCALING_EFFICIENCY:
            errors.append(f'{shard.get("device_requested")}: scaling efficiency failed')
    independent_4096 = max(
        gpu0["results"][0]["median_world_steps_per_second"],
        gpu1["results"][0]["median_world_steps_per_second"],
    )
    concurrent_scaling = concurrent["aggregate_median_world_steps_per_second"] / independent_4096
    if not concurrent.get("safety_pass"):
        errors.append("concurrent shard safety gate failed")
    if concurrent_scaling < MINIMUM_CONCURRENT_SCALING:
        errors.append("concurrent scaling gate failed")
    result = {
        "schema": "rocell.mujoco_warp_large_batch_admission.v1",
        "status": "ADOPT_LARGE_BATCH_RESEARCH" if not errors else "RESEARCH_ONLY",
        "errors": errors,
        "minimum_world_steps_per_second": MINIMUM_WORLD_STEPS_PER_SECOND,
        "minimum_scaling_efficiency": MINIMUM_SCALING_EFFICIENCY,
        "minimum_concurrent_scaling": MINIMUM_CONCURRENT_SCALING,
        "concurrent_scaling": concurrent_scaling,
        "dual_gpu_state_aggregation": False,
        "source_receipt_sha256": {
            "cuda:0": gpu0["receipt_sha256"],
            "cuda:1": gpu1["receipt_sha256"],
            "concurrent": concurrent["receipt_sha256"],
        },
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
        "limitations": [
            "large-batch kinematic research only",
            "no contact, collision, rendering, actuator, or training qualification",
            "MW2 general-purpose rejection remains unchanged",
        ],
    }
    result["receipt_sha256"] = canonical_sha256(result)
    return result


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--device", choices=("cuda:0", "cuda:1"), required=True)
    run.add_argument("--mjcf", type=Path, required=True)
    run.add_argument("--counts", nargs="+", type=int, default=WORLD_COUNTS)
    run.add_argument("--output", type=Path, required=True)
    concurrent = subparsers.add_parser("concurrent")
    concurrent.add_argument("--mjcf", type=Path, required=True)
    concurrent.add_argument("--output-dir", type=Path, required=True)
    concurrent.add_argument("--output", type=Path, required=True)
    admission = subparsers.add_parser("admit")
    admission.add_argument("--gpu0", type=Path, required=True)
    admission.add_argument("--gpu1", type=Path, required=True)
    admission.add_argument("--concurrent", type=Path, required=True)
    admission.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run":
        result = run_device(args.mjcf, args.device, args.counts)
    elif args.command == "concurrent":
        result = run_concurrent(args.mjcf, args.output_dir)
    else:
        result = admit(_load(args.gpu0), _load(args.gpu1), _load(args.concurrent))
    _write(args.output, result)
    print(json.dumps({"status": result.get("status", result.get("safety_pass")), "receipt_sha256": result["receipt_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
