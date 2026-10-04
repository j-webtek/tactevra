"""Independently verify residual-v3 Isaac shards before any model training."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


FIXTURE_SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v3"
MANIFEST_SCHEMA = "tactevra.ai_residual_obstruction_v3_isaac_manifest.v1"
RECEIPT_SCHEMA = "tactevra.ai_residual_obstruction_v3_admission.v1"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    value = json.loads(payload, object_pairs_hook=_pairs)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value, payload


def load_bound(path: Path, schema: str, hash_field: str) -> tuple[dict[str, Any], bytes]:
    value, payload = load_json(path)
    if value.get("schema") != schema:
        raise ValueError(f"unexpected schema in {path}")
    claimed = value.get(hash_field)
    core = {key: item for key, item in value.items() if key != hash_field}
    if claimed != sha256_bytes(canonical(core)):
        raise ValueError(f"canonical hash mismatch in {path}")
    return value, payload


def _contained_regular(root: Path, relative: str) -> Path:
    if "\\" in relative:
        raise ValueError(f"non-portable path: {relative}")
    candidate = root / relative
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"missing regular image: {relative}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError(f"image escapes shard: {relative}") from exc
    return resolved


def _overlap_in_contract(row: dict[str, Any], variant: dict[str, Any]) -> None:
    geometry = variant["geometry"]
    declared = geometry.get("safe_overlap")
    if variant["family"] in {"NONE", "IMAGE_QUALITY"}:
        return
    measured = (
        row["adjacent_overlap_fraction"]
        if variant["family"] == "DISTRACTOR"
        else row["safe_overlap_fraction"]
    )
    if isinstance(declared, list):
        valid = declared[0] <= measured <= declared[1]
    else:
        valid = measured == declared
    if not valid:
        raise ValueError(
            f"overlap outside contract for {row['observation_id']}: {measured}"
        )


def verify_shards(
    workspace: Path,
    fixture_path: Path,
    shard_dirs: list[Path],
    *,
    require_complete: bool = True,
) -> dict[str, Any]:
    workspace = workspace.resolve(strict=True)
    fixture_path = fixture_path.resolve(strict=True)
    fixture, fixture_bytes = load_bound(fixture_path, FIXTURE_SCHEMA, "bundle_sha256")
    if not shard_dirs:
        raise ValueError("at least one shard is required")
    if fixture["training_started"] or fixture["physical_authority"]:
        raise ValueError("fixture authority state is invalid")

    sys.path.insert(0, str(workspace / "software" / "src"))
    from rocell.application.bootstrap import bootstrap_virtual_workcell

    context = bootstrap_virtual_workcell(workspace).context
    targets = sorted(
        [*context.targets.keyboard_targets.values(), *context.targets.phone_targets.values()],
        key=lambda item: (item.device, item.target_id),
    )
    if len(targets) != 75 or context.targets.content_sha256 != fixture["source"]["target_catalog_sha256"]:
        raise ValueError("target catalog mismatch")
    target_keys = [(item.device, item.target_id) for item in targets]
    scenes = {item["scene_id"]: item for item in fixture["base_scenes"]}
    appearances = {item["appearance_id"] for item in fixture["appearances"]}
    variants = {item["variant_id"]: item for item in fixture["variants"]}

    seen_observations: set[str] = set()
    seen_hashes: set[str] = set()
    seen_combinations: set[tuple[str, str, str, str, str]] = set()
    manifests: list[dict[str, Any]] = []
    split_counts = {"training": 0, "development": 0}
    total_bytes = 0

    for raw_dir in shard_dirs:
        if raw_dir.is_symlink():
            raise ValueError(f"shard directory cannot be a symlink: {raw_dir}")
        shard = raw_dir.resolve(strict=True)
        manifest_path = shard / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError(f"missing regular manifest: {shard}")
        manifest, manifest_bytes = load_bound(
            manifest_path, MANIFEST_SCHEMA, "dataset_sha256"
        )
        if manifest["fixture_file_sha256"] != sha256_bytes(fixture_bytes):
            raise ValueError("fixture file hash mismatch")
        if manifest["fixture_bundle_sha256"] != fixture["bundle_sha256"]:
            raise ValueError("fixture bundle hash mismatch")
        if (
            manifest["hardware_writes"] != 0
            or manifest["physical_movements"] != 0
            or manifest["physical_authority"] is not False
            or manifest["evaluation_observation_count"] != 0
        ):
            raise ValueError("manifest claims forbidden authority or evaluation access")
        start = manifest["target_shard"]["start"]
        count = manifest["target_shard"]["count"]
        if not isinstance(start, int) or not isinstance(count, int) or start < 0 or count < 1 or start + count > len(targets):
            raise ValueError("invalid target shard")
        allowed_targets = set(target_keys[start:start + count])
        rows = manifest["observations"]
        if manifest["observation_count"] != len(rows):
            raise ValueError("manifest observation count mismatch")
        if manifest["scene_count"] != len({row["scene_id"] for row in rows}):
            raise ValueError("manifest scene count mismatch")
        local_splits = {name: 0 for name in split_counts}
        referenced = {"manifest.json"}
        for row in rows:
            observation_id = row["observation_id"]
            expected_id = ":".join((
                row["scene_id"], row["appearance_id"], row["variant_id"],
                row["device"], row["target_id"],
            ))
            if observation_id != expected_id:
                raise ValueError(f"observation id mismatch: {observation_id}")
            if observation_id in seen_observations:
                raise ValueError(f"duplicate observation id: {observation_id}")
            key = (row["scene_id"], row["appearance_id"], row["variant_id"], row["device"], row["target_id"])
            if key in seen_combinations:
                raise ValueError(f"duplicate observation combination: {observation_id}")
            scene = scenes.get(row["scene_id"])
            variant = variants.get(row["variant_id"])
            if scene is None or row["appearance_id"] not in appearances or variant is None:
                raise ValueError(f"unknown scene, appearance, or variant: {observation_id}")
            if (row["device"], row["target_id"]) not in allowed_targets:
                raise ValueError(f"target outside declared shard: {observation_id}")
            if row["split"] != scene["split"] or row["expected_decision"] != variant["decision"]:
                raise ValueError(f"split or decision mismatch: {observation_id}")
            global_index = target_keys.index((row["device"], row["target_id"]))
            expected_path = f"{row['split']}/{row['scene_id']}/{row['appearance_id']}/{row['variant_id']}/{global_index:03d}.jpg"
            if row["rgb_path"] != expected_path:
                raise ValueError(f"unexpected image path: {row['rgb_path']}")
            image = _contained_regular(shard, row["rgb_path"])
            payload = image.read_bytes()
            digest = sha256_bytes(payload)
            if len(payload) != row["rgb_bytes"] or digest != row["rgb_sha256"]:
                raise ValueError(f"image size or hash mismatch: {row['rgb_path']}")
            if digest in seen_hashes:
                raise ValueError(f"duplicate RGB bytes: {row['rgb_path']}")
            if row["depth_min_mm"] is None or row["depth_max_mm"] is None or row["depth_min_mm"] >= row["depth_max_mm"]:
                raise ValueError(f"invalid retained depth bounds: {observation_id}")
            _overlap_in_contract(row, variant)
            seen_observations.add(observation_id)
            seen_combinations.add(key)
            seen_hashes.add(digest)
            referenced.add(row["rgb_path"])
            local_splits[row["split"]] += 1
            split_counts[row["split"]] += 1
            total_bytes += len(payload)
        if manifest["split_counts"] != local_splits:
            raise ValueError("manifest split counts mismatch")
        expected_local = {
            (scene_id, appearance_id, variant_id, device, target_id)
            for scene_id in scenes
            for appearance_id in appearances
            for variant_id in variants
            for device, target_id in allowed_targets
        }
        local_combinations = {
            (row["scene_id"], row["appearance_id"], row["variant_id"], row["device"], row["target_id"])
            for row in rows
        }
        if manifest["complete_campaign"] is not (local_combinations == expected_local and start == 0 and count == len(targets)):
            raise ValueError("manifest complete-campaign claim mismatch")
        actual_files = {
            item.relative_to(shard).as_posix()
            for item in shard.rglob("*")
            if item.is_file()
        }
        if actual_files != referenced:
            raise ValueError("shard has missing or extra regular files")
        manifests.append({
            "manifest_file_sha256": sha256_bytes(manifest_bytes),
            "dataset_sha256": manifest["dataset_sha256"],
            "target_start": start,
            "target_count": count,
            "observation_count": len(rows),
        })

    expected = {
        (scene_id, appearance_id, variant_id, device, target_id)
        for scene_id in scenes
        for appearance_id in appearances
        for variant_id in variants
        for device, target_id in target_keys
    }
    complete = seen_combinations == expected
    missing_count = len(expected - seen_combinations)
    if require_complete and not complete:
        raise ValueError(f"campaign incomplete: {missing_count} observation combinations missing")
    core = {
        "schema": RECEIPT_SCHEMA,
        "scope": "SYNTHETIC_ISAAC_ADMISSION_NO_QUALIFICATION",
        "status": "PASS" if complete else "PARTIAL",
        "campaign_admitted": complete,
        "fixture_file_sha256": sha256_bytes(fixture_bytes),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "target_catalog_sha256": fixture["source"]["target_catalog_sha256"],
        "manifest_count": len(manifests),
        "manifests": sorted(manifests, key=lambda item: (item["target_start"], item["dataset_sha256"])),
        "expected_observation_count": len(expected),
        "verified_observation_count": len(seen_combinations),
        "missing_observation_count": missing_count,
        "unique_rgb_sha256_count": len(seen_hashes),
        "rgb_bytes": total_bytes,
        "split_counts": split_counts,
        "evaluation_observation_count": 0,
        "training_started": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "Synthetic Isaac admission does not establish physical or deployment qualification",
            "Only a complete receipt may be consumed by later training",
            "Evaluation remains absent",
        ],
    }
    return {**core, "receipt_sha256": sha256_bytes(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--shard", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    receipt = verify_shards(
        args.workspace, args.fixture, args.shard,
        require_complete=not args.allow_partial,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(receipt) + b"\n")
    print(json.dumps({
        "status": receipt["status"],
        "campaign_admitted": receipt["campaign_admitted"],
        "verified_observation_count": receipt["verified_observation_count"],
        "missing_observation_count": receipt["missing_observation_count"],
        "receipt_sha256": receipt["receipt_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
