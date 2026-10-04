"""Independently admit residual-obstruction v4.2 Isaac campaign shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


FIXTURE_SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v4_2"
MANIFEST_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_shard_manifest.v1"
REPORT_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_admission.v1"


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


def _validate_overlap(fixture: dict[str, Any], row: dict[str, Any]) -> None:
    variant = row["variant_id"]
    overlap = row["safe_overlap_fraction"]
    adjacent = row["adjacent_overlap_fraction"]
    admission = fixture["render_admission"]
    bounds = admission["semantic_safe_overlap_bounds"].get(variant)
    if bounds is not None and not (bounds[0] <= overlap <= bounds[1]):
        raise ValueError(f"{variant} overlap outside frozen bounds")
    if variant in admission["zero_semantic_obstruction_overlap_variants"] and overlap != 0.0:
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
    shard_paths: list[Path],
    *,
    allow_partial: bool,
) -> dict[str, Any]:
    fixture, fixture_bytes = load_bound(fixture_path, FIXTURE_SCHEMA, "bundle_sha256")
    if fixture["evaluation_opened"] or fixture["split_policy"]["evaluation_pairs_rendered"] != 0:
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
    for shard_path in shard_paths:
        manifest_path = shard_path.resolve(strict=True) / "manifest.json"
        manifest, manifest_bytes = load_bound(manifest_path, MANIFEST_SCHEMA, "dataset_sha256")
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
            expected_reference = f"{row['scene_id']}:{row['device']}:{row['target_id']}"
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
        if len(local_ids) != manifest["observation_count"]:
            raise ValueError("shard observation count mismatch")
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

    expected_by_split = {
        "training": fixture["render_admission"]["exact_training_observation_count"],
        "development": fixture["render_admission"]["exact_development_observation_count"],
    }
    missing_by_split = {
        split: expected_by_split[split] - verified_by_split[split] for split in expected_by_split
    }
    if any(value < 0 for value in missing_by_split.values()):
        raise ValueError("verified rows exceed the frozen campaign")
    complete = all(value == 0 for value in missing_by_split.values())
    if not complete and not allow_partial:
        raise ValueError("campaign is incomplete")
    expected_reference_count = (fixture["split_policy"]["training_scene_count"] + fixture["split_policy"]["development_scene_count"]) * len(targets)
    core = {
        "schema": REPORT_SCHEMA,
        "status": "PASS" if complete else "PARTIAL",
        "campaign_admitted": complete,
        "fixture_file_sha256": digest(fixture_bytes),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
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
    parser.add_argument("--shard", type=Path, action="append", required=True)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = admit(args.workspace, args.fixture, args.shard, allow_partial=args.allow_partial)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
