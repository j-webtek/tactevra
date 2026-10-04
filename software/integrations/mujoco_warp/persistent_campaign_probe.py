"""MW2S deterministic persistent-worker campaign probe.

This module is an offline, zero-authority research tool. It never imports or
invokes robot transport, controller, permit, or hardware APIs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


EXPECTED_MJCF_SHA256 = "448b711ae30ed3df8a5f5eff66ecb53034f6540eade7264388d86e3911a7a8a0"
DEVICES = ("cuda:0", "cuda:1")
WORLD_COUNT = 16_384
SHARDS_PER_DEVICE = 8
REPLAYS = 2
WARMUP_STEPS = 16
TIMED_STEPS = 128
SEED_BASE = 190_300
NUMERICAL_REPEATABILITY_LIMIT = 1e-6
MINIMUM_CONCURRENT_SCALING = 1.70
JOINT_LIMITS = (
    (-3.1416, 3.1416),
    (-1.5708, 1.5708),
    (-1.0, 2.95),
    (-1.5708, 1.5708),
    (-3.1416, 3.1416),
    (0.0, 1.5),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_manifest() -> dict[str, Any]:
    shards = []
    for device_index, device in enumerate(DEVICES):
        for shard_index in range(SHARDS_PER_DEVICE):
            shards.append(
                {
                    "shard_id": f"mw2s-d{device_index}-s{shard_index:02d}",
                    "device": device,
                    "seed": SEED_BASE + device_index * 100 + shard_index,
                    "world_count": WORLD_COUNT,
                    "scenario_family": "joint_state_uncertainty",
                }
            )
    manifest = {
        "schema": "rocell.mujoco_warp_campaign_manifest.v1",
        "scope": "KINEMATIC_RESEARCH_ONLY",
        "mjcf_sha256": EXPECTED_MJCF_SHA256,
        "generator": {
            "algorithm": "numpy-pcg64-uniform-v1",
            "joint_limits": [list(limit) for limit in JOINT_LIMITS],
            "position_limit_margin_fraction": 0.1,
            "velocity_range_radians_per_second": [-0.025, 0.025],
        },
        "worker_contract": {
            "allocation_reused": True,
            "replays": REPLAYS,
            "warmup_steps": WARMUP_STEPS,
            "timed_steps": TIMED_STEPS,
        },
        "shards": shards,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    expected = build_manifest()
    if manifest != expected:
        raise ValueError("manifest differs from frozen MW2S campaign")
    if manifest["manifest_sha256"] != canonical_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    ):
        raise ValueError("manifest self-hash mismatch")
    identities = [item["shard_id"] for item in manifest["shards"]]
    seeds = [item["seed"] for item in manifest["shards"]]
    if len(identities) != len(set(identities)) or len(seeds) != len(set(seeds)):
        raise ValueError("manifest shard identities and seeds must be disjoint")


def _initial_states(seed: int, nworld: int):
    import numpy as np

    rng = np.random.default_rng(seed)
    qpos = np.empty((nworld, len(JOINT_LIMITS)), dtype=np.float32)
    for index, (lower, upper) in enumerate(JOINT_LIMITS):
        margin = 0.1 * (upper - lower)
        qpos[:, index] = rng.uniform(lower + margin, upper - margin, size=nworld)
    qvel = rng.uniform(-0.025, 0.025, size=qpos.shape).astype(np.float32)
    return qpos, qvel


def _array_hash(value) -> str:
    import numpy as np

    return hashlib.sha256(np.asarray(value, dtype=np.float64).tobytes(order="C")).hexdigest()


def run_worker(manifest: dict[str, Any], mjcf: Path, device_name: str) -> dict[str, Any]:
    import mujoco
    import mujoco_warp as mjw
    import numpy as np
    import warp as wp

    validate_manifest(manifest)
    if device_name not in DEVICES:
        raise ValueError("device outside frozen MW2S campaign")
    if sha256(mjcf) != EXPECTED_MJCF_SHA256:
        raise ValueError("MJCF hash mismatch")

    wp.init()
    wp.set_device(device_name)
    device = wp.get_device()
    model = mujoco.MjModel.from_xml_path(str(mjcf))
    seed_data = mujoco.MjData(model)
    warp_model = mjw.put_model(model)
    data = mjw.put_data(model, seed_data, nworld=WORLD_COUNT)
    selected = [item for item in manifest["shards"] if item["device"] == device_name]
    results = []
    started = time.perf_counter()
    for shard in selected:
        initial_qpos, initial_qvel = _initial_states(shard["seed"], WORLD_COUNT)
        replay_states = []
        replay_rates = []
        replay_checks = []
        for replay in range(REPLAYS):
            data.qpos.assign(initial_qpos)
            data.qvel.assign(initial_qvel)
            mjw.forward(warp_model, data)
            for _ in range(WARMUP_STEPS):
                mjw.step(warp_model, data)
            wp.synchronize_device(device)
            timed_start = time.perf_counter()
            for _ in range(TIMED_STEPS):
                mjw.step(warp_model, data)
            wp.synchronize_device(device)
            elapsed = time.perf_counter() - timed_start
            qpos = np.asarray(data.qpos.numpy(), dtype=np.float64)
            qvel = np.asarray(data.qvel.numpy(), dtype=np.float64)
            overflow = np.asarray(data.overflow.numpy(), dtype=np.int64)
            replay_states.append((qpos, qvel))
            replay_rates.append(WORLD_COUNT * TIMED_STEPS / elapsed)
            replay_checks.append(
                {
                    "replay": replay,
                    "finite": bool(np.isfinite(qpos).all() and np.isfinite(qvel).all()),
                    "world_count_preserved": qpos.shape[0] == WORLD_COUNT,
                    "overflow_zero": bool((overflow == 0).all()),
                    "elapsed_seconds": elapsed,
                    "world_steps_per_second": replay_rates[-1],
                    "final_qpos_sha256": _array_hash(qpos),
                    "final_qvel_sha256": _array_hash(qvel),
                }
            )
        reference_qpos, reference_qvel = replay_states[0]
        qpos_delta = max(
            float(np.max(np.abs(qpos - reference_qpos)))
            for qpos, _ in replay_states[1:]
        )
        qvel_delta = max(
            float(np.max(np.abs(qvel - reference_qvel)))
            for _, qvel in replay_states[1:]
        )
        result = {
            "shard_id": shard["shard_id"],
            "seed": shard["seed"],
            "world_count": WORLD_COUNT,
            "unique_initial_poses": int(np.unique(initial_qpos, axis=0).shape[0]),
            "initial_qpos_sha256": hashlib.sha256(initial_qpos.tobytes()).hexdigest(),
            "initial_qvel_sha256": hashlib.sha256(initial_qvel.tobytes()).hexdigest(),
            "replays": replay_checks,
            "maximum_qpos_delta": qpos_delta,
            "maximum_qvel_delta": qvel_delta,
        }
        result["pass"] = (
            result["unique_initial_poses"] == WORLD_COUNT
            and all(
                item["finite"]
                and item["world_count_preserved"]
                and item["overflow_zero"]
                for item in replay_checks
            )
            and qpos_delta <= NUMERICAL_REPEATABILITY_LIMIT
            and qvel_delta <= NUMERICAL_REPEATABILITY_LIMIT
        )
        results.append(result)
    worker_elapsed = time.perf_counter() - started
    receipt = {
        "schema": "rocell.mujoco_warp_persistent_worker.v1",
        "scope": "KINEMATIC_RESEARCH_ONLY",
        "device_requested": device_name,
        "device_name": device.name,
        "manifest_sha256": manifest["manifest_sha256"],
        "mjcf_sha256": EXPECTED_MJCF_SHA256,
        "model_load_count": 1,
        "world_allocation_count": 1,
        "worker_elapsed_seconds": worker_elapsed,
        "shards": results,
        "safety_pass": len(results) == SHARDS_PER_DEVICE
        and all(item["pass"] for item in results),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _worker_command(manifest_path: Path, mjcf: Path, device: str, output: Path) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "worker",
        "--manifest",
        str(manifest_path),
        "--mjcf",
        str(mjcf),
        "--device",
        device,
        "--output",
        str(output),
    ]


def orchestrate(
    manifest_path: Path, mjcf: Path, output_dir: Path, mode: str
) -> dict[str, Any]:
    manifest = _load(manifest_path)
    validate_manifest(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    commands = [
        _worker_command(manifest_path, mjcf, device, output_dir / f"{device[-1]}.json")
        for device in DEVICES
    ]
    started = time.perf_counter()
    if mode == "sequential":
        return_codes = [subprocess.run(command, check=False).returncode for command in commands]
    elif mode == "concurrent":
        processes = [subprocess.Popen(command) for command in commands]
        return_codes = [process.wait() for process in processes]
    else:
        raise ValueError("mode must be sequential or concurrent")
    wall_seconds = time.perf_counter() - started
    if return_codes != [0, 0]:
        raise RuntimeError(f"worker failure: {return_codes}")
    children = [_load(output_dir / f"{device[-1]}.json") for device in DEVICES]
    result = {
        "schema": "rocell.mujoco_warp_persistent_orchestration.v1",
        "scope": "KINEMATIC_RESEARCH_ONLY",
        "mode": mode,
        "manifest_sha256": manifest["manifest_sha256"],
        "wall_seconds_including_launch_and_receipt_writes": wall_seconds,
        "child_receipt_sha256": [child["receipt_sha256"] for child in children],
        "child_file_sha256": [
            sha256(output_dir / f"{device[-1]}.json") for device in DEVICES
        ],
        "children": children,
        "safety_pass": all(child["safety_pass"] for child in children),
        "peer_access_used": False,
        "shared_state_used": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = canonical_sha256(result)
    return result


def _state_identity(receipt: dict[str, Any]) -> dict[str, tuple[str, str, str, str]]:
    identities = {}
    for child in receipt["children"]:
        for shard in child["shards"]:
            if shard["shard_id"] in identities:
                raise ValueError("duplicate shard receipt identity")
            first = shard["replays"][0]
            identities[shard["shard_id"]] = (
                shard["initial_qpos_sha256"],
                shard["initial_qvel_sha256"],
                first["final_qpos_sha256"],
                first["final_qvel_sha256"],
            )
    return identities


def _valid_receipt_hash(receipt: dict[str, Any]) -> bool:
    claimed = receipt.get("receipt_sha256")
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    return isinstance(claimed, str) and claimed == canonical_sha256(unsigned)


def _validate_orchestration(
    receipt: dict[str, Any], expected_mode: str, manifest_hash: str
) -> list[str]:
    errors = []
    if receipt.get("schema") != "rocell.mujoco_warp_persistent_orchestration.v1":
        errors.append(f"{expected_mode}: schema mismatch")
    if receipt.get("mode") != expected_mode:
        errors.append(f"{expected_mode}: orchestration mode mismatch")
    if receipt.get("manifest_sha256") != manifest_hash:
        errors.append(f"{expected_mode}: orchestration manifest mismatch")
    if not _valid_receipt_hash(receipt):
        errors.append(f"{expected_mode}: receipt hash mismatch")
    children = receipt.get("children")
    if not isinstance(children, list) or len(children) != len(DEVICES):
        errors.append(f"{expected_mode}: child count mismatch")
        return errors
    if [child.get("device_requested") for child in children] != list(DEVICES):
        errors.append(f"{expected_mode}: child device order mismatch")
    for child in children:
        device = child.get("device_requested", "unknown")
        if child.get("schema") != "rocell.mujoco_warp_persistent_worker.v1":
            errors.append(f"{expected_mode}/{device}: worker schema mismatch")
        if child.get("manifest_sha256") != manifest_hash:
            errors.append(f"{expected_mode}/{device}: worker manifest mismatch")
        if child.get("mjcf_sha256") != EXPECTED_MJCF_SHA256:
            errors.append(f"{expected_mode}/{device}: MJCF mismatch")
        if child.get("model_load_count") != 1 or child.get("world_allocation_count") != 1:
            errors.append(f"{expected_mode}/{device}: persistence contract failed")
        if not child.get("safety_pass"):
            errors.append(f"{expected_mode}/{device}: worker safety gate failed")
        if not _valid_receipt_hash(child):
            errors.append(f"{expected_mode}/{device}: worker receipt hash mismatch")
        if len(child.get("shards", [])) != SHARDS_PER_DEVICE:
            errors.append(f"{expected_mode}/{device}: shard count mismatch")
    return errors


def admit(
    manifest: dict[str, Any], sequential: dict[str, Any], concurrent: dict[str, Any]
) -> dict[str, Any]:
    errors = []
    try:
        validate_manifest(manifest)
    except ValueError as exc:
        errors.append(str(exc))
    manifest_hash = manifest.get("manifest_sha256")
    errors.extend(_validate_orchestration(sequential, "sequential", manifest_hash))
    errors.extend(_validate_orchestration(concurrent, "concurrent", manifest_hash))

    expected_ids = {item["shard_id"] for item in manifest.get("shards", [])}
    try:
        sequential_states = _state_identity(sequential)
        concurrent_states = _state_identity(concurrent)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        errors.append(f"malformed state evidence: {exc}")
        sequential_states = {}
        concurrent_states = {}
    if set(sequential_states) != expected_ids or set(concurrent_states) != expected_ids:
        errors.append("incomplete or unexpected shard coverage")
    if sequential_states != concurrent_states:
        errors.append("sequential/concurrent state identity mismatch")
    initial_pairs = {(item[0], item[1]) for item in sequential_states.values()}
    if len(initial_pairs) != len(expected_ids):
        errors.append("initial state hashes are not disjoint")

    sequential_wall = sequential.get("wall_seconds_including_launch_and_receipt_writes", 0)
    concurrent_wall = concurrent.get("wall_seconds_including_launch_and_receipt_writes", 0)
    scaling = sequential_wall / concurrent_wall if concurrent_wall > 0 else 0.0
    if scaling < MINIMUM_CONCURRENT_SCALING:
        errors.append("persistent concurrent scaling gate failed")
    result = {
        "schema": "rocell.mujoco_warp_persistent_campaign_admission.v1",
        "status": "ADOPT_PERSISTENT_LARGE_BATCH_RESEARCH" if not errors else "RESEARCH_ONLY",
        "errors": errors,
        "manifest_sha256": manifest_hash,
        "minimum_concurrent_scaling": MINIMUM_CONCURRENT_SCALING,
        "concurrent_scaling": scaling,
        "sequential_wall_seconds": sequential_wall,
        "concurrent_wall_seconds": concurrent_wall,
        "shard_count": len(expected_ids),
        "world_count_per_shard": WORLD_COUNT,
        "source_receipt_sha256": {
            "sequential": sequential.get("receipt_sha256"),
            "concurrent": concurrent.get("receipt_sha256"),
        },
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
        "limitations": [
            "persistent large-batch kinematic research only",
            "no contact, collision, rendering, actuator, policy, or training qualification",
            "MW2 and MW2R decisions remain unchanged",
        ],
    }
    result["receipt_sha256"] = canonical_sha256(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    manifest_parser = subparsers.add_parser("manifest")
    manifest_parser.add_argument("--output", type=Path, required=True)
    worker = subparsers.add_parser("worker")
    worker.add_argument("--manifest", type=Path, required=True)
    worker.add_argument("--mjcf", type=Path, required=True)
    worker.add_argument("--device", choices=DEVICES, required=True)
    worker.add_argument("--output", type=Path, required=True)
    orchestration = subparsers.add_parser("orchestrate")
    orchestration.add_argument("--manifest", type=Path, required=True)
    orchestration.add_argument("--mjcf", type=Path, required=True)
    orchestration.add_argument("--mode", choices=("sequential", "concurrent"), required=True)
    orchestration.add_argument("--output-dir", type=Path, required=True)
    orchestration.add_argument("--output", type=Path, required=True)
    admission = subparsers.add_parser("admit")
    admission.add_argument("--manifest", type=Path, required=True)
    admission.add_argument("--sequential", type=Path, required=True)
    admission.add_argument("--concurrent", type=Path, required=True)
    admission.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "manifest":
        result = build_manifest()
    elif args.command == "worker":
        result = run_worker(_load(args.manifest), args.mjcf, args.device)
    elif args.command == "orchestrate":
        result = orchestrate(args.manifest, args.mjcf, args.output_dir, args.mode)
    else:
        result = admit(
            _load(args.manifest), _load(args.sequential), _load(args.concurrent)
        )
    _write(args.output, result)
    print(
        json.dumps(
            {
                "status": result.get("status", result.get("safety_pass", "MANIFESTED")),
                "receipt_sha256": result.get(
                    "receipt_sha256", result.get("manifest_sha256")
                ),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
