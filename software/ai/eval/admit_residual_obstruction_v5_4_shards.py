"""Independently admit residual-obstruction v5.4 Isaac campaign shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


FIXTURE_SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v5_4"
V5_SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v5"
MANIFEST_SCHEMA = "tactevra.ai_residual_obstruction_v5_4_shard_manifest.v1"
REPORT_SCHEMA = "tactevra.ai_residual_obstruction_v5_4_admission.v1"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_bound(path: Path, schema: str, hash_field: str) -> tuple[dict[str, Any], bytes]:
    payload = path.resolve(strict=True).read_bytes()
    value = json.loads(payload)
    if value.get("schema") != schema:
        raise ValueError(f"schema mismatch: {path}")
    core = {key: item for key, item in value.items() if key != hash_field}
    if value.get(hash_field) != digest(canonical(core)):
        raise ValueError(f"canonical hash mismatch: {path}")
    return value, payload


def _verify_file(root: Path, relative: str, expected_hash: str, expected_bytes: int) -> None:
    path = (root / relative).resolve(strict=True)
    if root not in path.parents:
        raise ValueError("image path escapes shard root")
    payload = path.read_bytes()
    if len(payload) != expected_bytes or digest(payload) != expected_hash:
        raise ValueError(f"image binding mismatch: {relative}")


def _verify_hash(root: Path, relative: str, expected_hash: str) -> None:
    path = (root / relative).resolve(strict=True)
    if root not in path.parents or digest(path.read_bytes()) != expected_hash:
        raise ValueError(f"file binding mismatch: {relative}")


def load_fixture(path: Path) -> tuple[dict[str, Any], bytes]:
    payload, payload_bytes = load_bound(path, FIXTURE_SCHEMA, "bundle_sha256")
    v5_path = path.with_name("residual_obstruction_successor_v5.json")
    v5, v5_bytes = load_bound(v5_path, V5_SCHEMA, "bundle_sha256")
    if digest(v5_bytes) != payload["source"]["v5_file_sha256"]:
        raise ValueError("v5 source file hash mismatch")
    if v5["bundle_sha256"] != payload["source"]["v5_bundle_sha256"]:
        raise ValueError("v5 source bundle mismatch")
    merged = dict(payload)
    merged["variants"] = v5["variants"]
    merged["render_contract"] = v5["render_contract"]
    merged["base_scenes"] = []
    for split, lower in (("training", 51000), ("development", 52000)):
        for index, scene_id in enumerate(v5["split_identities"]["scenes"][split]):
            merged["base_scenes"].append({
                "split": split,
                "scene_id": scene_id,
                "isaac_seed": lower + index,
                "camera_pose_jitter_mm": v5["render_contract"]["camera_translation_jitter_mm"],
                "camera_rotation_jitter_deg": v5["render_contract"]["camera_rotation_jitter_deg"],
            })
    families = ("NEUTRAL", "WARM_SIDE", "DIM_AMBIENT")
    merged["appearances"] = [
        {"split": split, "appearance_id": value, "family": families[index]}
        for split in ("training", "development")
        for index, value in enumerate(v5["split_identities"]["lighting"][split])
    ]
    merged["obstruction_assets"] = v5["split_identities"]["obstruction_assets"]
    return merged, payload_bytes


def load_allowlist(path: Path) -> tuple[dict[str, Any], bytes]:
    value, payload = load_bound(
        path, "tactevra.ai_residual_obstruction_v5_4_shard_allowlist.v1", "allowlist_sha256"
    )
    if len(value["shards"]) != 38:
        raise ValueError("allowlist must contain exactly 38 shards")
    identities = {
        (row["split"], row["target_start"], row["target_count"]) for row in value["shards"]
    }
    expected = {
        (split, start, min(4, 75 - start))
        for split in ("training", "development")
        for start in range(0, 75, 4)
    }
    if identities != expected:
        raise ValueError("allowlist shard identities are not exact")
    return value, payload


def _validate_overlap(fixture: dict[str, Any], row: dict[str, Any]) -> None:
    variant = row["variant_id"]
    overlap = row["safe_overlap_fraction"]
    adjacent = row["adjacent_overlap_fraction"]
    contract = next(item for item in fixture["variants"] if item["variant_id"] == variant)
    coverage = contract.get("coverage")
    bounds = None if coverage is None else (
        max(0.0, coverage - 0.12), min(1.0, coverage + 0.12)
    )
    if bounds is not None and not (bounds[0] <= overlap <= bounds[1]):
        raise ValueError(f"{variant} overlap outside frozen bounds")
    if variant in {"clear", "adjacent_left", "adjacent_right"} and overlap != 0.0:
        raise ValueError(f"{variant} has unexpected obstruction overlap")
    if variant in {"adjacent_left", "adjacent_right"} and adjacent != 0.0:
        raise ValueError(f"{variant} overlaps the safe region")


def _validate_camera_contract(scene: dict[str, Any], row: dict[str, Any]) -> None:
    for field in (
        "camera_position_mm",
        "camera_look_at_mm",
        "camera_up_axis",
        "camera_position_jitter_mm",
        "camera_rotation_jitter_deg",
    ):
        values = row.get(field)
        if not isinstance(values, list) or len(values) != 3 or not all(
            isinstance(value, (int, float)) and math.isfinite(value) for value in values
        ):
            raise ValueError(f"invalid camera contract field: {field}")
    for actual, limit in zip(
        row["camera_position_jitter_mm"], scene["camera_pose_jitter_mm"], strict=True
    ):
        if abs(actual) > limit:
            raise ValueError("camera position jitter exceeds frozen bound")
    for actual, limit in zip(
        row["camera_rotation_jitter_deg"], scene["camera_rotation_jitter_deg"], strict=True
    ):
        if abs(actual) > limit:
            raise ValueError("camera rotation jitter exceeds frozen bound")
    up_norm = math.sqrt(sum(value * value for value in row["camera_up_axis"]))
    if not math.isclose(up_norm, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("camera up axis is not normalized")


def admit(
    workspace: Path,
    fixture_path: Path,
    allowlist_path: Path,
    shard_paths: list[Path],
    *,
    allow_partial: bool,
) -> dict[str, Any]:
    fixture, fixture_bytes = load_fixture(fixture_path)
    allowlist, allowlist_bytes = load_allowlist(allowlist_path)
    if fixture["evaluation_opened"] or fixture["evaluation_rotation"]["images_generated"] != 0:
        raise ValueError("evaluation must remain absent")
    sys.path.insert(0, str(workspace.resolve(strict=True) / "software/src"))
    from rocell.application.bootstrap import bootstrap_virtual_workcell

    context = bootstrap_virtual_workcell(workspace).context
    if context.targets.content_sha256 != fixture["source"]["target_catalog_sha256"]:
        raise ValueError("target catalog mismatch")
    targets = sorted(
        [*context.targets.keyboard_targets.values(), *context.targets.phone_targets.values()],
        key=lambda item: (item.device, item.target_id),
    )
    target_keys = {(target.device, target.target_id) for target in targets}
    variants = {row["variant_id"]: row for row in fixture["variants"]}
    scenes = {row["scene_id"]: row for row in fixture["base_scenes"] if row["split"] != "evaluation"}
    appearances = {row["appearance_id"]: row for row in fixture["appearances"] if row["split"] != "evaluation"}

    observation_ids: set[str] = set()
    observation_hashes: set[str] = set()
    reference_bindings: dict[str, tuple[Any, ...]] = {}
    verified_by_split = {"training": 0, "development": 0}
    manifests: list[dict[str, Any]] = []
    allowed_by_path = {
        str(Path(row["path"]).resolve()): row for row in allowlist["shards"]
    }
    actual_paths = [str(path.resolve()) for path in shard_paths]
    if len(actual_paths) != len(set(actual_paths)) or set(actual_paths) != set(allowed_by_path):
        raise ValueError("shard paths differ from exact allowlist")
    for shard_path in shard_paths:
        manifest_path = shard_path.resolve(strict=True) / "manifest.json"
        manifest, manifest_bytes = load_bound(manifest_path, MANIFEST_SCHEMA, "dataset_sha256")
        allowed = allowed_by_path[str(shard_path.resolve())]
        if digest(manifest_bytes) != allowed["manifest_file_sha256"]:
            raise ValueError("manifest file hash differs from allowlist")
        if manifest["dataset_sha256"] != allowed["dataset_sha256"]:
            raise ValueError("dataset hash differs from allowlist")
        if manifest["fixture_bundle_sha256"] != fixture["bundle_sha256"]:
            raise ValueError("shard fixture binding mismatch")
        if manifest["split"] not in {"training", "development"}:
            raise ValueError("evaluation shard is prohibited")
        if manifest["evaluation_observation_count"] != 0:
            raise ValueError("evaluation rows are prohibited")
        if manifest["hardware_writes"] != 0 or manifest["physical_movements"] != 0:
            raise ValueError("shard claims physical effects")
        root = manifest_path.parent
        local_ids: set[str] = set()
        for row in manifest["observations"]:
            if row["split"] != manifest["split"]:
                raise ValueError("row split differs from shard split")
            scene = scenes.get(row["scene_id"])
            appearance = appearances.get(row["appearance_id"])
            variant = variants.get(row["variant_id"])
            if scene is None or scene["split"] != row["split"]:
                raise ValueError("undeclared scene")
            if appearance is None or appearance["split"] != row["split"]:
                raise ValueError("undeclared appearance")
            if variant is None or variant["family"] != row["variant_family"] or variant["decision"] != row["expected_decision"]:
                raise ValueError("variant contract mismatch")
            if (row["device"], row["target_id"]) not in target_keys:
                raise ValueError("undeclared target")
            expected_id = ":".join(
                [row["scene_id"], row["appearance_id"], row["variant_id"], row["device"], row["target_id"]]
            )
            if row["observation_id"] != expected_id:
                raise ValueError("observation identity mismatch")
            if expected_id in observation_ids or expected_id in local_ids:
                raise ValueError("duplicate observation identity")
            local_ids.add(expected_id)
            if row["rgb_sha256"] in observation_hashes:
                raise ValueError("duplicate observation RGB bytes")
            observation_hashes.add(row["rgb_sha256"])
            _verify_file(root, row["rgb_path"], row["rgb_sha256"], row["rgb_bytes"])
            _verify_file(root, row["reference_rgb_path"], row["reference_rgb_sha256"], row["reference_rgb_bytes"])
            _verify_hash(root, row["context_rgb_path"], row["context_rgb_sha256"])
            _verify_hash(root, row["safe_region_mask_path"], row["safe_region_mask_sha256"])
            _verify_file(
                root, row["arm_projection_mask_path"],
                row["arm_projection_mask_sha256"], row["arm_projection_mask_bytes"],
            )
            if row.get("raw_rgb_path") is not None or row.get("reference_raw_rgb_path") is not None:
                raise ValueError("campaign shard unexpectedly contains codec-probe raw inputs")
            expected_reference = ":".join([
                row["scene_id"], row["appearance_id"], row["device"], row["target_id"]
            ])
            if row["reference_id"] != expected_reference:
                raise ValueError("reference identity mismatch")
            camera_binding = tuple(
                tuple(row[field])
                for field in (
                    "camera_position_mm",
                    "camera_look_at_mm",
                    "camera_up_axis",
                    "camera_position_jitter_mm",
                    "camera_rotation_jitter_deg",
                )
            )
            binding = (row["reference_rgb_sha256"], row["reference_rgb_bytes"], camera_binding)
            previous = reference_bindings.setdefault(expected_reference, binding)
            if previous != binding:
                raise ValueError("reference identity maps to inconsistent bytes")
            _validate_overlap(fixture, row)
            _validate_camera_contract(scene, row)
            descriptor = row["obstruction_render_descriptor"]
            if descriptor is None:
                if row["obstruction_asset_id"] is not None or row["obstruction_asset_signature_sha256"] is not None:
                    raise ValueError("clear/distractor row has obstruction descriptor")
            else:
                if row["obstruction_asset_id"] not in fixture["obstruction_assets"][manifest["split"]]:
                    raise ValueError("obstruction asset crosses split")
                if digest(canonical(descriptor)) != row["obstruction_asset_signature_sha256"]:
                    raise ValueError("obstruction descriptor hash mismatch")
        if len(local_ids) != manifest["observation_count"]:
            raise ValueError("shard observation count mismatch")
        if manifest["scene_shard"] != allowed["scene_shard"] or manifest["target_shard"] != {
            "start": allowed["target_start"], "count": allowed["target_count"]
        }:
            raise ValueError("manifest shard identity differs from allowlist")
        observation_ids.update(local_ids)
        verified_by_split[manifest["split"]] += len(local_ids)
        manifests.append(
            {
                "path": str(manifest_path),
                "manifest_file_sha256": digest(manifest_bytes),
                "dataset_sha256": manifest["dataset_sha256"],
                "split": manifest["split"],
                "scene_shard": manifest["scene_shard"],
                "target_shard": manifest["target_shard"],
                "observation_count": manifest["observation_count"],
                "reference_count": manifest["reference_count"],
            }
        )

    expected_by_split = {"training": 43200, "development": 21600}
    missing_by_split = {
        split: expected_by_split[split] - verified_by_split[split] for split in expected_by_split
    }
    if any(value < 0 for value in missing_by_split.values()):
        raise ValueError("verified rows exceed the frozen campaign")
    complete = all(value == 0 for value in missing_by_split.values())
    if not complete and not allow_partial:
        raise ValueError("campaign is incomplete")
    expected_reference_count = 24 * len(targets) * 3
    if complete and (
        len(manifests) != 38 or len(reference_bindings) != expected_reference_count
    ):
        raise ValueError("complete campaign reference or manifest inventory mismatch")
    core = {
        "schema": REPORT_SCHEMA,
        "status": "PASS" if complete else "PARTIAL",
        "campaign_admitted": complete,
        "fixture_file_sha256": digest(fixture_bytes),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "allowlist_file_sha256": digest(allowlist_bytes),
        "allowlist_sha256": allowlist["allowlist_sha256"],
        "manifest_count": len(manifests),
        "manifests": manifests,
        "verified_observation_count": len(observation_ids),
        "unique_observation_rgb_count": len(observation_hashes),
        "verified_reference_count": len(reference_bindings),
        "expected_reference_count": expected_reference_count,
        "verified_by_split": verified_by_split,
        "expected_by_split": expected_by_split,
        "missing_by_split": missing_by_split,
        "evaluation_observation_count": 0,
        "training_started": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "Synthetic campaign admission does not establish physical or deployment qualification",
            "PARTIAL status cannot unlock training or development scoring",
            "Evaluation images remain absent and unopened",
        ],
    }
    return {**core, "report_sha256": digest(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--shard", type=Path, action="append", required=True)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = admit(
        args.workspace, args.fixture, args.allowlist, args.shard,
        allow_partial=args.allow_partial,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
