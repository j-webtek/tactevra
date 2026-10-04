"""MW2Q atomic, resumable MuJoCo Warp research queues."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


BASE_PATH = Path(__file__).with_name("persistent_campaign_probe.py")
BASE_SPEC = importlib.util.spec_from_file_location("mw2s_persistent_campaign", BASE_PATH)
if BASE_SPEC is None or BASE_SPEC.loader is None:
    raise RuntimeError("cannot load frozen MW2S campaign module")
BASE = importlib.util.module_from_spec(BASE_SPEC)
BASE_SPEC.loader.exec_module(BASE)
PROFILE_PATH = Path(__file__).with_name("scenario_profile_probe.py")
PROFILE_SPEC = importlib.util.spec_from_file_location("mw2p_scenario_profile", PROFILE_PATH)
if PROFILE_SPEC is None or PROFILE_SPEC.loader is None:
    raise RuntimeError("cannot load MW2P scenario profile module")
PROFILE = importlib.util.module_from_spec(PROFILE_SPEC)
PROFILE_SPEC.loader.exec_module(PROFILE)

SHARD_SCHEMA = "rocell.mujoco_warp_atomic_shard_receipt.v1"
QUEUE_SCHEMA = "rocell.mujoco_warp_resumable_queue.v1"
ASSEMBLY_SCHEMA = "rocell.mujoco_warp_resumable_assembly.v1"
HEX_DIGITS = frozenset("0123456789abcdef")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and set(value).issubset(HEX_DIGITS)
    )


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate_campaign_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema") == "rocell.mujoco_warp_campaign_manifest.v1":
        BASE.validate_manifest(manifest)
        return
    if manifest.get("schema") == PROFILE.MANIFEST_SCHEMA:
        errors = PROFILE.validate_compiled_manifest(manifest)
        if errors:
            raise ValueError("; ".join(errors))
        return
    raise ValueError("unsupported campaign manifest schema")


def _initial_states(manifest: dict[str, Any], seed: int, nworld: int):
    if manifest["schema"] == PROFILE.MANIFEST_SCHEMA:
        return PROFILE.initial_states(manifest, seed, nworld)
    if nworld != BASE.WORLD_COUNT:
        raise ValueError("world count outside frozen MW2S campaign")
    return BASE._initial_states(seed, nworld)


def _canonical_sha256(value: object) -> str:
    return BASE.canonical_sha256(value)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _manifest_shard(
    manifest: dict[str, Any], shard_id: str
) -> dict[str, Any] | None:
    matches = [item for item in manifest["shards"] if item["shard_id"] == shard_id]
    return matches[0] if len(matches) == 1 else None


def build_shard_receipt(
    manifest: dict[str, Any], shard: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    receipt = {
        "schema": SHARD_SCHEMA,
        "scope": "KINEMATIC_RESEARCH_ONLY",
        "manifest_sha256": manifest["manifest_sha256"],
        "mjcf_sha256": BASE.EXPECTED_MJCF_SHA256,
        "device": shard["device"],
        "shard": dict(shard),
        "result": result,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


def validate_shard_receipt(
    receipt: dict[str, Any], manifest: dict[str, Any], expected: dict[str, Any]
) -> list[str]:
    errors = []
    expected_keys = {
        "schema",
        "scope",
        "manifest_sha256",
        "mjcf_sha256",
        "device",
        "shard",
        "result",
        "hardware_write_count",
        "physical_movement_count",
        "physical_authority",
        "receipt_sha256",
    }
    if set(receipt) != expected_keys:
        errors.append("receipt fields mismatch")
    if receipt.get("schema") != SHARD_SCHEMA:
        errors.append("schema mismatch")
    if receipt.get("scope") != "KINEMATIC_RESEARCH_ONLY":
        errors.append("scope mismatch")
    if receipt.get("manifest_sha256") != manifest.get("manifest_sha256"):
        errors.append("manifest mismatch")
    if receipt.get("mjcf_sha256") != BASE.EXPECTED_MJCF_SHA256:
        errors.append("MJCF mismatch")
    if receipt.get("device") != expected["device"] or receipt.get("shard") != expected:
        errors.append("shard identity mismatch")
    if (
        receipt.get("hardware_write_count") != 0
        or receipt.get("physical_movement_count") != 0
        or receipt.get("physical_authority") is not False
    ):
        errors.append("authority fields mismatch")
    claimed_hash = receipt.get("receipt_sha256")
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if claimed_hash != _canonical_sha256(unsigned):
        errors.append("canonical receipt hash mismatch")

    result = receipt.get("result")
    if not isinstance(result, dict):
        return errors + ["result missing"]
    if result.get("shard_id") != expected["shard_id"]:
        errors.append("result shard identity mismatch")
    if result.get("seed") != expected["seed"]:
        errors.append("result seed mismatch")
    if result.get("world_count") != expected["world_count"]:
        errors.append("result world count mismatch")
    if result.get("unique_initial_poses") != expected["world_count"]:
        errors.append("initial pose uniqueness failed")
    if not _is_sha256(result.get("initial_qpos_sha256")) or not _is_sha256(
        result.get("initial_qvel_sha256")
    ):
        errors.append("initial state hash invalid")
    qpos_delta = result.get("maximum_qpos_delta")
    qvel_delta = result.get("maximum_qvel_delta")
    if not _finite_number(qpos_delta) or qpos_delta > BASE.NUMERICAL_REPEATABILITY_LIMIT:
        errors.append("qpos repeatability failed")
    if not _finite_number(qvel_delta) or qvel_delta > BASE.NUMERICAL_REPEATABILITY_LIMIT:
        errors.append("qvel repeatability failed")
    if result.get("pass") is not True:
        errors.append("shard safety gate failed")
    replays = result.get("replays")
    expected_replays = manifest["worker_contract"]["replays"]
    if not isinstance(replays, list) or len(replays) != expected_replays:
        errors.append("replay count mismatch")
    else:
        for index, replay in enumerate(replays):
            if replay.get("replay") != index:
                errors.append(f"replay {index}: identity mismatch")
            if not (
                replay.get("finite") is True
                and replay.get("world_count_preserved") is True
                and replay.get("overflow_zero") is True
            ):
                errors.append(f"replay {index}: safety gate failed")
            if not _finite_number(replay.get("elapsed_seconds")) or not _finite_number(
                replay.get("world_steps_per_second")
            ):
                errors.append(f"replay {index}: timing evidence invalid")
            if not _is_sha256(replay.get("final_qpos_sha256")) or not _is_sha256(
                replay.get("final_qvel_sha256")
            ):
                errors.append(f"replay {index}: final state hash invalid")
    return errors


def _load_receipt(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("receipt root must be an object")
    return value


def inspect_queue(
    manifest: dict[str, Any], receipt_dir: Path, device: str, *, quarantine: bool
) -> dict[str, Any]:
    expected = [item for item in manifest["shards"] if item["device"] == device]
    valid = []
    pending = []
    quarantined = []
    for shard in expected:
        path = receipt_dir / f"{shard['shard_id']}.json"
        if not path.exists():
            pending.append(shard)
            continue
        try:
            receipt = _load_receipt(path)
            errors = validate_shard_receipt(receipt, manifest, shard)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            errors = [f"unreadable receipt: {exc}"]
        if not errors:
            valid.append({"shard": shard, "path": path, "receipt": receipt})
            continue
        if quarantine:
            digest = _file_sha256(path)
            quarantine_dir = receipt_dir / "_quarantine"
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            destination = quarantine_dir / f"{path.stem}.{digest}.invalid.json"
            os.replace(path, destination)
            quarantined.append(
                {
                    "shard_id": shard["shard_id"],
                    "source_sha256": digest,
                    "quarantine_path": destination.as_posix(),
                    "errors": errors,
                }
            )
        pending.append(shard)
    return {"valid": valid, "pending": pending, "quarantined": quarantined}


def _run_shard(
    data,
    warp_model,
    device,
    manifest: dict[str, Any],
    shard: dict[str, Any],
) -> dict[str, Any]:
    import mujoco_warp as mjw
    import numpy as np
    import warp as wp

    world_count = shard["world_count"]
    contract = manifest["worker_contract"]
    initial_qpos, initial_qvel = _initial_states(manifest, shard["seed"], world_count)
    replay_states = []
    replay_checks = []
    for replay in range(contract["replays"]):
        data.qpos.assign(initial_qpos)
        data.qvel.assign(initial_qvel)
        mjw.forward(warp_model, data)
        for _ in range(contract["warmup_steps"]):
            mjw.step(warp_model, data)
        wp.synchronize_device(device)
        started = time.perf_counter()
        for _ in range(contract["timed_steps"]):
            mjw.step(warp_model, data)
        wp.synchronize_device(device)
        elapsed = time.perf_counter() - started
        qpos = np.asarray(data.qpos.numpy(), dtype=np.float64)
        qvel = np.asarray(data.qvel.numpy(), dtype=np.float64)
        overflow = np.asarray(data.overflow.numpy(), dtype=np.int64)
        replay_states.append((qpos, qvel))
        replay_checks.append(
            {
                "replay": replay,
                "finite": bool(np.isfinite(qpos).all() and np.isfinite(qvel).all()),
                "world_count_preserved": qpos.shape[0] == world_count,
                "overflow_zero": bool((overflow == 0).all()),
                "elapsed_seconds": elapsed,
                "world_steps_per_second": world_count * contract["timed_steps"] / elapsed,
                "final_qpos_sha256": BASE._array_hash(qpos),
                "final_qvel_sha256": BASE._array_hash(qvel),
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
        "world_count": world_count,
        "unique_initial_poses": int(np.unique(initial_qpos, axis=0).shape[0]),
        "initial_qpos_sha256": hashlib.sha256(initial_qpos.tobytes()).hexdigest(),
        "initial_qvel_sha256": hashlib.sha256(initial_qvel.tobytes()).hexdigest(),
        "replays": replay_checks,
        "maximum_qpos_delta": qpos_delta,
        "maximum_qvel_delta": qvel_delta,
    }
    result["pass"] = (
        result["unique_initial_poses"] == world_count
        and all(
            item["finite"]
            and item["world_count_preserved"]
            and item["overflow_zero"]
            for item in replay_checks
        )
        and qpos_delta <= BASE.NUMERICAL_REPEATABILITY_LIMIT
        and qvel_delta <= BASE.NUMERICAL_REPEATABILITY_LIMIT
    )
    return result


def run_queue(
    manifest: dict[str, Any], mjcf: Path, device_name: str, receipt_dir: Path
) -> dict[str, Any]:
    validate_campaign_manifest(manifest)
    if device_name not in BASE.DEVICES:
        raise ValueError("device outside frozen MW2S manifest")
    if BASE.sha256(mjcf) != BASE.EXPECTED_MJCF_SHA256:
        raise ValueError("MJCF hash mismatch")
    initial = inspect_queue(manifest, receipt_dir, device_name, quarantine=True)
    executed = []
    model_load_count = 0
    allocation_count = 0
    started = time.perf_counter()
    if initial["pending"]:
        import mujoco
        import mujoco_warp as mjw
        import warp as wp

        wp.init()
        wp.set_device(device_name)
        device = wp.get_device()
        model = mujoco.MjModel.from_xml_path(str(mjcf))
        seed_data = mujoco.MjData(model)
        warp_model = mjw.put_model(model)
        world_counts = {item["world_count"] for item in initial["pending"]}
        if len(world_counts) != 1:
            raise ValueError("pending queue mixes world counts")
        data = mjw.put_data(model, seed_data, nworld=world_counts.pop())
        model_load_count = 1
        allocation_count = 1
        for shard in initial["pending"]:
            result = _run_shard(data, warp_model, device, manifest, shard)
            receipt = build_shard_receipt(manifest, shard, result)
            errors = validate_shard_receipt(receipt, manifest, shard)
            if errors:
                raise RuntimeError(f"new shard receipt failed validation: {errors}")
            path = receipt_dir / f"{shard['shard_id']}.json"
            atomic_write(path, receipt)
            executed.append(shard["shard_id"])
    final = inspect_queue(manifest, receipt_dir, device_name, quarantine=False)
    if final["pending"]:
        raise RuntimeError("queue remains incomplete after execution")
    valid_files = [
        {
            "shard_id": item["shard"]["shard_id"],
            "file_sha256": _file_sha256(item["path"]),
            "receipt_sha256": item["receipt"]["receipt_sha256"],
        }
        for item in final["valid"]
    ]
    summary = {
        "schema": QUEUE_SCHEMA,
        "scope": "KINEMATIC_RESEARCH_ONLY",
        "device": device_name,
        "manifest_sha256": manifest["manifest_sha256"],
        "model_load_count": model_load_count,
        "world_allocation_count": allocation_count,
        "skipped_shard_ids": [item["shard"]["shard_id"] for item in initial["valid"]],
        "executed_shard_ids": executed,
        "quarantined": initial["quarantined"],
        "valid_receipts": valid_files,
        "elapsed_seconds": time.perf_counter() - started,
        "complete": len(valid_files)
        == len([item for item in manifest["shards"] if item["device"] == device_name]),
        "temporary_file_count": len(list(receipt_dir.glob("*.tmp"))),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    summary["receipt_sha256"] = _canonical_sha256(summary)
    return summary


def assemble(
    manifest: dict[str, Any], cuda0_dir: Path, cuda1_dir: Path
) -> dict[str, Any]:
    validate_campaign_manifest(manifest)
    directories = {"cuda:0": cuda0_dir, "cuda:1": cuda1_dir}
    receipts = []
    errors = []
    for device, directory in directories.items():
        expected = [item for item in manifest["shards"] if item["device"] == device]
        allowed_names = {f"{item['shard_id']}.json" for item in expected}
        observed_names = {path.name for path in directory.glob("*.json")}
        if observed_names != allowed_names:
            errors.append(f"{device}: root receipt allowlist mismatch")
        inspected = inspect_queue(manifest, directory, device, quarantine=False)
        if inspected["pending"]:
            errors.append(f"{device}: incomplete or invalid receipts")
        for item in inspected["valid"]:
            receipts.append(
                {
                    "device": device,
                    "shard_id": item["shard"]["shard_id"],
                    "file_sha256": _file_sha256(item["path"]),
                    "receipt_sha256": item["receipt"]["receipt_sha256"],
                    "initial_qpos_sha256": item["receipt"]["result"][
                        "initial_qpos_sha256"
                    ],
                    "initial_qvel_sha256": item["receipt"]["result"][
                        "initial_qvel_sha256"
                    ],
                }
            )
    identities = {
        (item["initial_qpos_sha256"], item["initial_qvel_sha256"])
        for item in receipts
    }
    if len(receipts) != len(manifest["shards"]):
        errors.append("campaign receipt count mismatch")
    if len(identities) != len(receipts):
        errors.append("campaign initial states are not disjoint")
    result = {
        "schema": ASSEMBLY_SCHEMA,
        "status": "ADMIT_RESUMABLE_RESEARCH_QUEUE" if not errors else "REJECTED",
        "errors": errors,
        "manifest_sha256": manifest["manifest_sha256"],
        "receipts": receipts,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
        "limitations": [
            "resumable kinematic research only",
            "no rendering, contact, collision, policy, training, or hardware qualification",
            "MW2, MW2R, and MW2S decisions remain unchanged",
        ],
    }
    result["receipt_sha256"] = _canonical_sha256(result)
    return result


def run_both(
    manifest_path: Path, mjcf: Path, receipt_root: Path, output_root: Path
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    processes = []
    commands = []
    started = time.perf_counter()
    for index, device in enumerate(BASE.DEVICES):
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "queue",
            "--manifest",
            str(manifest_path),
            "--mjcf",
            str(mjcf),
            "--device",
            device,
            "--receipt-dir",
            str(receipt_root / f"cuda{index}"),
            "--output",
            str(output_root / f"cuda{index}.json"),
        ]
        commands.append(command)
        processes.append(subprocess.Popen(command))
    return_codes = [process.wait() for process in processes]
    if return_codes != [0, 0]:
        raise RuntimeError(f"queue child failure: {return_codes}")
    children = [
        _load_receipt(output_root / f"cuda{index}.json") for index in range(2)
    ]
    result = {
        "schema": "rocell.mujoco_warp_resumable_dual_queue.v1",
        "scope": "KINEMATIC_RESEARCH_ONLY",
        "manifest_sha256": _load_receipt(manifest_path)["manifest_sha256"],
        "wall_seconds": time.perf_counter() - started,
        "child_receipt_sha256": [item["receipt_sha256"] for item in children],
        "children": children,
        "complete": all(item["complete"] for item in children),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = _canonical_sha256(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    queue = subparsers.add_parser("queue")
    queue.add_argument("--manifest", type=Path, required=True)
    queue.add_argument("--mjcf", type=Path, required=True)
    queue.add_argument("--device", choices=BASE.DEVICES, required=True)
    queue.add_argument("--receipt-dir", type=Path, required=True)
    queue.add_argument("--output", type=Path, required=True)
    both = subparsers.add_parser("run-both")
    both.add_argument("--manifest", type=Path, required=True)
    both.add_argument("--mjcf", type=Path, required=True)
    both.add_argument("--receipt-root", type=Path, required=True)
    both.add_argument("--output-root", type=Path, required=True)
    both.add_argument("--output", type=Path, required=True)
    assembly = subparsers.add_parser("assemble")
    assembly.add_argument("--manifest", type=Path, required=True)
    assembly.add_argument("--cuda0-dir", type=Path, required=True)
    assembly.add_argument("--cuda1-dir", type=Path, required=True)
    assembly.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = _load_receipt(args.manifest)
    if args.command == "queue":
        result = run_queue(manifest, args.mjcf, args.device, args.receipt_dir)
    elif args.command == "run-both":
        result = run_both(args.manifest, args.mjcf, args.receipt_root, args.output_root)
    else:
        result = assemble(manifest, args.cuda0_dir, args.cuda1_dir)
    atomic_write(args.output, result)
    print(
        json.dumps(
            {
                "status": result.get("status", result.get("complete")),
                "receipt_sha256": result["receipt_sha256"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
