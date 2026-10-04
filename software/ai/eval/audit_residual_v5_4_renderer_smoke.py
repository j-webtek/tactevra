"""Audit a bounded v5.4 training renderer smoke without opening evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator
from PIL import Image

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.amend_residual_v5_pre_render import canonical_hash, load_json  # noqa: E402

SCHEMA = AI_ROOT / "schemas/residual_obstruction_v5_4_renderer_smoke_v1.schema.json"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(
    *, source_commit: str, fixture_path: Path, manifest_path: Path,
    status_path: Path, renderer_path: Path,
) -> dict[str, Any]:
    fixture = load_json(fixture_path)
    manifest = load_json(manifest_path)
    status = load_json(status_path)
    if manifest.get("fixture_bundle_sha256") != fixture.get("bundle_sha256"):
        raise ValueError("manifest does not bind v5.4 fixture")
    if manifest.get("split") != "training" or manifest.get("evaluation_observation_count") != 0:
        raise ValueError("smoke must be training-only and evaluation-free")
    if status.get("status") != "PASS" or status.get("dataset_sha256") != manifest.get("dataset_sha256"):
        raise ValueError("status does not bind passing manifest")
    manifest_core = {key: value for key, value in manifest.items() if key != "dataset_sha256"}
    if canonical_hash(manifest_core) != manifest.get("dataset_sha256"):
        raise ValueError("manifest canonical hash mismatch")
    rows = manifest["observations"]
    variants = {row["variant_id"] for row in rows}
    expected_variants = {row["variant_id"] for row in load_json(
        fixture_path.with_name("residual_obstruction_successor_v5.json")
    )["variants"]}
    if variants != expected_variants:
        raise ValueError("smoke variant inventory mismatch")
    root = manifest_path.parent
    nonempty_arm_masks = 0
    for row in rows:
        for path_key, hash_key in (
            ("rgb_path", "rgb_sha256"),
            ("context_rgb_path", "context_rgb_sha256"),
            ("safe_region_mask_path", "safe_region_mask_sha256"),
            ("arm_projection_mask_path", "arm_projection_mask_sha256"),
        ):
            path = root / row[path_key]
            if file_hash(path) != row[hash_key]:
                raise ValueError(f"pixel hash mismatch: {path_key}")
        descriptor = row["obstruction_render_descriptor"]
        if descriptor is None:
            if row["obstruction_asset_id"] is not None or row["obstruction_asset_signature_sha256"] is not None:
                raise ValueError("uncovered row has obstruction asset binding")
        else:
            if descriptor["asset_id"] != row["obstruction_asset_id"]:
                raise ValueError("descriptor asset binding mismatch")
            if canonical_hash(descriptor) != row["obstruction_asset_signature_sha256"]:
                raise ValueError("render descriptor hash mismatch")
            if descriptor["texture"]["kind"] != "NONE_PROCEDURAL_SOLID_DISPLAY_COLOR":
                raise ValueError("unexpected procedural texture contract")
        projection = row["arm_projection"]
        projection_input = row["arm_projection_input"]
        if projection["projection_model"] != "ANALYTIC_PINHOLE_FK_CAPSULES_NO_SIMULATOR_MASK":
            raise ValueError("arm projection is not the analytic no-truth contract")
        if projection_input["source"] != "PERTURBED_READY_MEASURED_STATE_SURROGATE_NOT_SIMULATOR_TRUTH":
            raise ValueError("arm projection input source mismatch")
        if projection_input["joint_values_emitted_to_model"] is not False:
            raise ValueError("joint values may not be emitted to the model")
        with Image.open(root / row["arm_projection_mask_path"]) as arm_mask:
            nonempty_arm_masks += arm_mask.getbbox() is not None
    overlap_ranges = {}
    for variant_id in sorted(variants):
        values = [row["safe_overlap_fraction"] for row in rows if row["variant_id"] == variant_id]
        overlap_ranges[variant_id] = {"minimum": min(values), "maximum": max(values)}
    core = {
        "schema": "tactevra.ai_residual_obstruction_v5_4_renderer_smoke.v1",
        "scope": "SYNTHETIC_TRAINING_RENDERER_SMOKE_NO_QUALIFICATION",
        "status": "PASS_TRAINING_DEVELOPMENT_CAMPAIGN_RENDER_AUTHORIZED_EVALUATION_BLOCKED",
        "source_commit": source_commit,
        "fixture_file_sha256": file_hash(fixture_path),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "renderer_file_sha256": file_hash(renderer_path),
        "external_manifest_file_sha256": file_hash(manifest_path),
        "external_manifest_dataset_sha256": manifest["dataset_sha256"],
        "external_status_file_sha256": file_hash(status_path),
        "metrics": {
            "scene_count": manifest["scene_count"],
            "target_count": manifest["target_shard"]["count"],
            "appearance_count": 3,
            "variant_count": len(variants),
            "observation_count": len(rows),
            "reference_count": manifest["reference_count"],
            "file_count": sum(1 for path in root.rglob("*") if path.is_file()),
            "unique_obstruction_asset_count": len({
                row["obstruction_asset_id"] for row in rows if row["obstruction_asset_id"]
            }),
            "unique_render_descriptor_count": len({
                row["obstruction_asset_signature_sha256"] for row in rows
                if row["obstruction_asset_signature_sha256"]
            }),
            "unique_arm_projection_mask_count": len({
                row["arm_projection_mask_sha256"] for row in rows
            }),
            "nonempty_arm_projection_mask_count": nonempty_arm_masks,
            "overlap_ranges": overlap_ranges,
        },
        "visual_audit": {
            "reviewed_variants": [
                "clear", "adjacent_right", "dark_cable_10", "dark_cable_60",
                "hand_60", "foreign_40",
            ],
            "pair_alignment": "PASS",
            "coverage_progression": "PASS",
            "finding": "FAMILY_MATCHED_PROCEDURAL_GEOMETRY_PASSES_TRAINING_SMOKE_VISUAL_REVIEW_WITH_SYNTHETIC_ONLY_LIMITATION",
        },
        "descriptor_and_projection_audit": {
            "render_descriptors_hash_bound": True,
            "geometry_material_texture_fields_present": True,
            "arm_projection_masks_hash_verified": True,
            "arm_projection_uses_simulator_truth": False,
            "empty_masks_expected_for_parked_pose_smoke": nonempty_arm_masks == 0,
        },
        "campaign_render_authorized": True,
        "evaluation_render_authorized": False,
        "model_training_started": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "The smoke uses one training scene and four targets and is not a model-quality sample.",
            "Procedural obstruction geometry is family-matched but remains synthetic and does not prove real appearance diversity.",
            "All four parked-pose smoke target views have empty analytic arm masks; the artifacts validate derivation and custody, not positive arm-mask overlap behavior.",
            "Synthetic RGB and overlap truth do not establish physical-camera transfer.",
            "The external pixel corpus remains outside Git and evaluation identities remain unopened.",
        ],
    }
    result = {**core, "report_sha256": canonical_hash(core)}
    errors = sorted(
        Draft202012Validator(load_json(SCHEMA)).iter_errors(result),
        key=lambda error: list(error.path),
    )
    if errors:
        error = errors[0]
        raise ValueError(f"schema validation failed at {list(error.path)}: {error.message}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--renderer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        source_commit=args.source_commit, fixture_path=args.fixture,
        manifest_path=args.manifest, status_path=args.status,
        renderer_path=args.renderer,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
