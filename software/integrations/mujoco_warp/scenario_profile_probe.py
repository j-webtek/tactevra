"""Compile provenanced kinematic uncertainty profiles into deterministic shards."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from typing import Any


BASE_PATH = Path(__file__).with_name("persistent_campaign_probe.py")
BASE_SPEC = importlib.util.spec_from_file_location("mw2p_persistent_campaign", BASE_PATH)
if BASE_SPEC is None or BASE_SPEC.loader is None:
    raise RuntimeError("cannot load frozen MW2S campaign module")
BASE = importlib.util.module_from_spec(BASE_SPEC)
BASE_SPEC.loader.exec_module(BASE)

PROFILE_SCHEMA = "rocell.mujoco_warp_scenario_profile.v1"
MANIFEST_SCHEMA = "rocell.mujoco_warp_profiled_campaign_manifest.v1"
JOINT_ORDER = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
    "link5_to_gripper_link",
)
PROFILE_KEYS = {
    "schema",
    "profile_id",
    "admission_mode",
    "mjcf_sha256",
    "provenance",
    "assumptions",
    "joint_ranges",
    "campaign",
    "hardware_write_count",
    "physical_movement_count",
    "physical_authority",
}
PROVENANCE_KEYS = {"source_type", "artifact_sha256", "domain_id", "collected_at"}
RANGE_KEYS = {
    "joint_id",
    "qpos_min",
    "qpos_max",
    "qvel_min",
    "qvel_max",
    "units",
    "source_field",
}
CAMPAIGN = {
    "devices": list(BASE.DEVICES),
    "shards_per_device": BASE.SHARDS_PER_DEVICE,
    "world_count": BASE.WORLD_COUNT,
    "replays": BASE.REPLAYS,
    "warmup_steps": BASE.WARMUP_STEPS,
    "timed_steps": BASE.TIMED_STEPS,
}
SOURCE_SCHEMA = "rocell.mujoco_warp_joint_uncertainty_source.v1"
SOURCE_KEYS = {
    "schema",
    "source_type",
    "domain_id",
    "collected_at",
    "method",
    "sample_count",
    "joint_ranges",
    "assumptions",
}


def canonical_sha256(value: object) -> str:
    return BASE.canonical_sha256(value)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_content_errors(profile: dict[str, Any], source_artifact: Path) -> list[str]:
    try:
        source = json.loads(source_artifact.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"source artifact unreadable: {exc}"]
    if not isinstance(source, dict) or set(source) != SOURCE_KEYS:
        return ["source artifact fields mismatch"]
    errors = []
    provenance = profile.get("provenance", {})
    if source.get("schema") != SOURCE_SCHEMA:
        errors.append("source artifact schema mismatch")
    for field in ("source_type", "domain_id", "collected_at"):
        if source.get(field) != provenance.get(field):
            errors.append(f"source artifact {field} mismatch")
    if source.get("joint_ranges") != profile.get("joint_ranges"):
        errors.append("source artifact joint ranges mismatch")
    if source.get("assumptions") != profile.get("assumptions"):
        errors.append("source artifact assumptions mismatch")
    if not isinstance(source.get("method"), str) or not source.get("method"):
        errors.append("source artifact method invalid")
    sample_count = source.get("sample_count")
    if not isinstance(sample_count, int) or isinstance(sample_count, bool) or sample_count < 0:
        errors.append("source artifact sample_count invalid")
    elif source.get("source_type") == "physical_measurement" and sample_count < 1:
        errors.append("physical source requires positive sample_count")
    return errors


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate_profile(
    profile: dict[str, Any], source_artifact: Path | None = None
) -> list[str]:
    errors = []
    if set(profile) != PROFILE_KEYS:
        errors.append("profile fields mismatch")
    if profile.get("schema") != PROFILE_SCHEMA:
        errors.append("profile schema mismatch")
    if not isinstance(profile.get("profile_id"), str) or not profile.get("profile_id"):
        errors.append("profile_id invalid")
    mode = profile.get("admission_mode")
    if mode not in {"exploratory", "qualifying"}:
        errors.append("admission_mode invalid")
    if profile.get("mjcf_sha256") != BASE.EXPECTED_MJCF_SHA256:
        errors.append("MJCF identity mismatch")
    provenance = profile.get("provenance")
    if not isinstance(provenance, dict) or set(provenance) != PROVENANCE_KEYS:
        errors.append("provenance fields mismatch")
        provenance = {}
    source_type = provenance.get("source_type")
    if source_type not in {"synthetic_rehearsal", "physical_measurement"}:
        errors.append("source_type invalid")
    for field in ("domain_id", "collected_at"):
        if not isinstance(provenance.get(field), str) or not provenance.get(field):
            errors.append(f"provenance {field} invalid")
    assumptions = profile.get("assumptions")
    if not isinstance(assumptions, list) or any(
        not isinstance(item, str) or not item for item in assumptions
    ):
        errors.append("assumptions invalid")
        assumptions = []
    if mode == "qualifying" and source_type != "physical_measurement":
        errors.append("qualifying mode requires physical measurement provenance")
    if mode == "qualifying" and assumptions:
        errors.append("qualifying mode forbids assumed ranges")
    if source_type == "physical_measurement" and assumptions:
        errors.append("physical measurement profile forbids assumptions")
    if source_artifact is None or not source_artifact.is_file():
        errors.append("source artifact missing")
    elif file_sha256(source_artifact) != provenance.get("artifact_sha256"):
        errors.append("source artifact hash mismatch")
    else:
        errors.extend(_source_content_errors(profile, source_artifact))

    ranges = profile.get("joint_ranges")
    if not isinstance(ranges, list) or len(ranges) != len(JOINT_ORDER):
        errors.append("joint range count mismatch")
        ranges = []
    if ranges and (
        not all(isinstance(item, dict) for item in ranges)
        or [item.get("joint_id") for item in ranges] != list(JOINT_ORDER)
    ):
        errors.append("joint order mismatch")
    for index, item in enumerate(ranges):
        if not isinstance(item, dict) or set(item) != RANGE_KEYS:
            errors.append(f"joint {index}: fields mismatch")
            continue
        values = [item.get(name) for name in ("qpos_min", "qpos_max", "qvel_min", "qvel_max")]
        if not all(_finite_number(value) for value in values):
            errors.append(f"joint {index}: bounds must be finite numbers")
            continue
        qpos_min, qpos_max, qvel_min, qvel_max = values
        governed_min, governed_max = BASE.JOINT_LIMITS[index]
        if not governed_min <= qpos_min < qpos_max <= governed_max:
            errors.append(f"joint {index}: position bounds outside governed limits")
        if not qvel_min < qvel_max:
            errors.append(f"joint {index}: velocity bounds unordered")
        if item.get("units") != "radians":
            errors.append(f"joint {index}: units mismatch")
        if not isinstance(item.get("source_field"), str) or not item.get("source_field"):
            errors.append(f"joint {index}: source_field invalid")
    if profile.get("campaign") != CAMPAIGN:
        errors.append("campaign contract mismatch")
    if (
        profile.get("hardware_write_count") != 0
        or profile.get("physical_movement_count") != 0
        or profile.get("physical_authority") is not False
    ):
        errors.append("authority fields mismatch")
    return errors


def _derived_seed(profile_hash: str, device: str, shard_index: int) -> int:
    identity = f"{profile_hash}:{device}:{shard_index}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(identity).digest()[:4], "big") & 0x7FFFFFFF


def compile_manifest(profile: dict[str, Any], source_artifact: Path) -> dict[str, Any]:
    errors = validate_profile(profile, source_artifact)
    if errors:
        raise ValueError("; ".join(errors))
    profile_hash = canonical_sha256(profile)
    shards = []
    for device_index, device in enumerate(BASE.DEVICES):
        for shard_index in range(BASE.SHARDS_PER_DEVICE):
            shards.append(
                {
                    "shard_id": f"mw2p-{profile_hash[:12]}-d{device_index}-s{shard_index:02d}",
                    "device": device,
                    "seed": _derived_seed(profile_hash, device, shard_index),
                    "world_count": BASE.WORLD_COUNT,
                    "scenario_family": "provenanced_joint_state_uncertainty",
                }
            )
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "scope": "KINEMATIC_RESEARCH_ONLY",
        "admission_scope": (
            "QUALIFYING_CANDIDATE"
            if profile["admission_mode"] == "qualifying"
            else "EXPLORATORY_ONLY"
        ),
        "mjcf_sha256": BASE.EXPECTED_MJCF_SHA256,
        "profile": profile,
        "profile_sha256": profile_hash,
        "source_artifact_sha256": profile["provenance"]["artifact_sha256"],
        "generator": {
            "algorithm": "numpy-pcg64-independent-uniform-profile-v1",
            "joint_ranges": profile["joint_ranges"],
        },
        "worker_contract": {
            "allocation_reused": True,
            "replays": BASE.REPLAYS,
            "warmup_steps": BASE.WARMUP_STEPS,
            "timed_steps": BASE.TIMED_STEPS,
        },
        "shards": shards,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def validate_compiled_manifest(
    manifest: dict[str, Any], source_artifact: Path | None = None
) -> list[str]:
    errors = []
    expected_keys = {
        "schema",
        "scope",
        "admission_scope",
        "mjcf_sha256",
        "profile",
        "profile_sha256",
        "source_artifact_sha256",
        "generator",
        "worker_contract",
        "shards",
        "hardware_write_count",
        "physical_movement_count",
        "physical_authority",
        "manifest_sha256",
    }
    if set(manifest) != expected_keys:
        errors.append("manifest fields mismatch")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        errors.append("manifest schema mismatch")
    profile = manifest.get("profile")
    if not isinstance(profile, dict):
        return errors + ["embedded profile missing"]
    if source_artifact is not None:
        errors.extend(validate_profile(profile, source_artifact))
    else:
        # Structural validation still runs with the immutable source hash temporarily
        # satisfied by a sentinel path-independent branch below.
        structural = validate_profile(profile, None)
        errors.extend(error for error in structural if error != "source artifact missing")
    profile_hash = canonical_sha256(profile)
    if manifest.get("profile_sha256") != profile_hash:
        errors.append("profile hash mismatch")
    if manifest.get("source_artifact_sha256") != profile.get("provenance", {}).get(
        "artifact_sha256"
    ):
        errors.append("source identity mismatch")
    expected_scope = (
        "QUALIFYING_CANDIDATE"
        if profile.get("admission_mode") == "qualifying"
        else "EXPLORATORY_ONLY"
    )
    if manifest.get("admission_scope") != expected_scope:
        errors.append("admission scope mismatch")
    if manifest.get("mjcf_sha256") != BASE.EXPECTED_MJCF_SHA256:
        errors.append("MJCF mismatch")
    if manifest.get("generator") != {
        "algorithm": "numpy-pcg64-independent-uniform-profile-v1",
        "joint_ranges": profile.get("joint_ranges"),
    }:
        errors.append("generator mismatch")
    expected_worker = {
        "allocation_reused": True,
        "replays": BASE.REPLAYS,
        "warmup_steps": BASE.WARMUP_STEPS,
        "timed_steps": BASE.TIMED_STEPS,
    }
    if manifest.get("worker_contract") != expected_worker:
        errors.append("worker contract mismatch")
    expected_shards = []
    for device_index, device in enumerate(BASE.DEVICES):
        for shard_index in range(BASE.SHARDS_PER_DEVICE):
            expected_shards.append(
                {
                    "shard_id": f"mw2p-{profile_hash[:12]}-d{device_index}-s{shard_index:02d}",
                    "device": device,
                    "seed": _derived_seed(profile_hash, device, shard_index),
                    "world_count": BASE.WORLD_COUNT,
                    "scenario_family": "provenanced_joint_state_uncertainty",
                }
            )
    if manifest.get("shards") != expected_shards:
        errors.append("shard derivation mismatch")
    seeds = [item["seed"] for item in expected_shards]
    if len(set(seeds)) != len(seeds):
        errors.append("derived seed collision")
    if (
        manifest.get("hardware_write_count") != 0
        or manifest.get("physical_movement_count") != 0
        or manifest.get("physical_authority") is not False
    ):
        errors.append("authority fields mismatch")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("manifest_sha256") != canonical_sha256(unsigned):
        errors.append("manifest hash mismatch")
    return errors


def initial_states(manifest: dict[str, Any], seed: int, nworld: int):
    import numpy as np

    errors = validate_compiled_manifest(manifest)
    if errors:
        raise ValueError("; ".join(errors))
    if nworld != BASE.WORLD_COUNT:
        raise ValueError("world count outside profiled campaign")
    rng = np.random.default_rng(seed)
    qpos = np.empty((nworld, len(JOINT_ORDER)), dtype=np.float32)
    qvel = np.empty_like(qpos)
    for index, item in enumerate(manifest["profile"]["joint_ranges"]):
        qpos[:, index] = rng.uniform(item["qpos_min"], item["qpos_max"], size=nworld)
        qvel[:, index] = rng.uniform(item["qvel_min"], item["qvel_max"], size=nworld)
    return qpos, qvel


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--profile", type=Path, required=True)
    compile_parser.add_argument("--source-artifact", type=Path, required=True)
    compile_parser.add_argument("--output", type=Path, required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--manifest", type=Path, required=True)
    validate_parser.add_argument("--source-artifact", type=Path, required=True)
    validate_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "compile":
        result = compile_manifest(_load(args.profile), args.source_artifact)
    else:
        result = _load(args.manifest)
        errors = validate_compiled_manifest(result, args.source_artifact)
        if errors:
            raise ValueError("; ".join(errors))
    _write(args.output, result)
    print(
        json.dumps(
            {
                "status": result["admission_scope"],
                "manifest_sha256": result["manifest_sha256"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
