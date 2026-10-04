"""Freeze the v5.4 exact balanced evaluation rotation and split roles."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.amend_residual_v5_pre_render import canonical_hash, load_json  # noqa: E402

SCHEMA = AI_ROOT / "schemas/residual_obstruction_successor_fixture_v5_4.schema.json"
ROTATION_SALT = "TACTEVRA_RESIDUAL_V5_4_EVALUATION_ROTATION_V1"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _targets(pretraining: dict[str, Any], expected_catalog_sha256: str) -> list[dict[str, str]]:
    if pretraining["source"]["target_catalog_sha256"] != expected_catalog_sha256:
        raise ValueError("target catalog binding mismatch")
    unique = {(row["device"], row["target_id"]) for row in pretraining["observations"]}
    if len(unique) != 75:
        raise ValueError("exactly 75 targets required")
    ordered = sorted(
        unique,
        key=lambda value: hashlib.sha256(
            f"{ROTATION_SALT}|{value[0]}|{value[1]}".encode("utf-8"),
        ).hexdigest(),
    )
    return [{"device": device, "target_id": target_id} for device, target_id in ordered]


def build(*, source_commit: str, v5_path: Path, v5_3_path: Path, pretraining_path: Path) -> dict[str, Any]:
    v5 = load_json(v5_path)
    v5_3 = load_json(v5_3_path)
    pretraining = load_json(pretraining_path)
    if v5["bundle_sha256"] != v5_3["v5_bundle_sha256"]:
        raise ValueError("v5.3 does not bind v5")
    if v5_3["status"] != "READY_FOR_FIXTURE_REVISION_RENDER_STILL_BLOCKED":
        raise ValueError("v5.3 planning result is required")
    target_order = _targets(pretraining, v5["source"]["target_catalog_sha256"])
    scene_count = v5_3["evaluation_rotation"]["recommended_scene_count"]
    targets_per_scene = v5_3["evaluation_rotation"]["targets_per_scene"]
    rotation = []
    occurrence: Counter[tuple[str, str]] = Counter()
    for scene_index in range(scene_count):
        targets = [
            target_order[(scene_index * targets_per_scene + offset) % len(target_order)]
            for offset in range(targets_per_scene)
        ]
        occurrence.update((row["device"], row["target_id"]) for row in targets)
        rotation.append({
            "scene_id": f"v5_4_evaluation_scene_{scene_index + 1:04d}",
            "procedural_seed": 53000 + scene_index,
            "targets": targets,
        })
    counts = sorted(occurrence.values())
    if counts[0] != 35 or counts[-1] != 36:
        raise ValueError("rotation is not balanced to 35/36 scenes per target")

    development_scenes = len(v5["split_identities"]["scenes"]["development"])
    appearances = v5["render_contract"]["appearances_per_scene"]
    variants = {row["variant_id"]: row for row in v5["variants"]}
    visible = sum(row["decision"] == "VISIBLE" for row in variants.values())
    abstain = sum(row["decision"] == "ABSTAIN" for row in variants.values())
    cable_abstain = sum(row["family"] == "CABLE" and row["decision"] == "ABSTAIN" for row in variants.values())
    dark_abstain = sum(row["variant_id"] in {"dark_cable_30", "dark_cable_60"} for row in variants.values())
    dark_boundary = int("dark_cable_10" in variants)
    per_target = {
        "scene_identities": development_scenes,
        "appearance_identities": appearances,
        "visible_rows": development_scenes * appearances * visible,
        "all_obstruction_rows": development_scenes * appearances * abstain,
        "cable_abstain_rows": development_scenes * appearances * cable_abstain,
        "dark_cable_30_60_abstain_rows": development_scenes * appearances * dark_abstain,
        "dark_cable_10_boundary_visible_rows": development_scenes * appearances * dark_boundary,
    }
    aggregate = {key: value * len(target_order) for key, value in per_target.items() if key.endswith("rows")}

    core = {
        "schema": "tactevra.ai_residual_obstruction_successor_fixture.v5_4",
        "scope": "SYNTHETIC_V5_4_EXACT_ROTATION_AND_GATE_ROLE_REVISION_NO_QUALIFICATION",
        "status": "FROZEN_BEFORE_RENDER_INDEPENDENT_AUDIT_REQUIRED",
        "source_commit": source_commit,
        "source": {
            "v5_file_sha256": file_hash(v5_path),
            "v5_bundle_sha256": v5["bundle_sha256"],
            "v5_3_file_sha256": file_hash(v5_3_path),
            "v5_3_report_sha256": v5_3["report_sha256"],
            "pretraining_file_sha256": file_hash(pretraining_path),
            "target_catalog_sha256": v5["source"]["target_catalog_sha256"],
        },
        "preserved_splits": {
            "training_scene_ids": v5["split_identities"]["scenes"]["training"],
            "development_scene_ids": v5["split_identities"]["scenes"]["development"],
            "lighting_ids": v5["split_identities"]["lighting"],
            "obstruction_asset_ids": v5["split_identities"]["obstruction_assets"],
            "pairwise_disjoint_required": True,
        },
        "development_selection": {
            "candidate_count": len(v5["candidate_models"]),
            "same_rows_for_every_candidate": True,
            "observation_count": v5["render_contract"]["development_observations"],
            "per_target_support": per_target,
            "aggregate_support": aggregate,
            "adequacy": "ADEQUATE_FOR_PAIRED_CANDIDATE_SELECTION_AND_HARD_CASE_DIAGNOSTICS_NOT_POWERED_SAFETY",
            "point_safety_checks": v5_3["gate_roles"]["development_candidate_selection"]["point_estimate_safety_checks"],
            "diagnostic_floors": v5_3["gate_roles"]["development_candidate_selection"]["diagnostic_floors"],
            "reported_not_powered": v5_3["gate_roles"]["development_candidate_selection"]["reported_not_powered"],
            "selection_rule": v5_3["gate_roles"]["development_candidate_selection"]["selection_rule"],
            "powered_confidence_claim": False,
        },
        "evaluation_rotation": {
            "algorithm": "SHA256_SALTED_TARGET_ORDER_CYCLIC_CONTIGUOUS_BLOCKS_V1",
            "salt": ROTATION_SALT,
            "scene_count": scene_count,
            "targets_per_scene": targets_per_scene,
            "target_count": len(target_order),
            "appearances_per_scene": appearances,
            "variants_per_target": len(variants),
            "observation_identities": scene_count * targets_per_scene * appearances * len(variants),
            "target_order": target_order,
            "scenes": rotation,
            "minimum_target_scene_exposures": counts[0],
            "maximum_target_scene_exposures": counts[-1],
            "targets_with_minimum_exposure": sum(value == counts[0] for value in occurrence.values()),
            "targets_with_maximum_exposure": sum(value == counts[-1] for value in occurrence.values()),
            "every_scene_contains_keyboard_and_phone": all(
                {target["device"] for target in scene["targets"]} == {"keyboard", "phone"}
                for scene in rotation
            ),
            "procedural_seed_range": [53000, 53000 + scene_count - 1],
            "images_generated": 0,
        },
        "evaluation_safety_gates": v5_3["gate_roles"]["single_use_evaluation_safety_gates"],
        "power_binding": {
            "assumed_true_rates": {
                "pooled_all_obstruction_miss": v5_3["power_assumptions"]["pooled_all_obstruction_miss_design_rate"],
                "cable_family_miss": v5_3["power_assumptions"]["cable_family_miss_design_rate"],
                "dark_cable_30_60_miss": v5_3["power_assumptions"]["dark_cable_30_60_miss_design_rate"],
                "visible_false_stop": v5_3["power_assumptions"]["visible_false_stop_design_rate"],
            },
            "interpretation": "POWER_IS_PROBABILITY_OF_PROVING_THE_SAFETY_BOUNDS_IF_TRUE_RATES_EQUAL_THE_ASSUMED_RATES_NOT_A_PREDICTION_THE_MODEL_WILL_PASS",
            "pessimistic_bonferroni_joint_lower_bound": 0.93055,
            "planning_only": True,
        },
        "render_sequence": {
            "training_and_development_may_render_after_independent_fixture_audit": True,
            "evaluation_must_remain_identity_only_until_candidate_and_threshold_frozen": True,
            "evaluation_render_before_development_pass_prohibited": True,
            "evaluation_retuning_prohibited": True,
        },
        "images_generated": False,
        "training_started": False,
        "development_opened": False,
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "The 0.5% miss and 3% false-stop rates are power alternatives, not predicted model performance.",
            "Development supports paired selection and diagnostics but no powered safety claim.",
            "Evaluation scene identities are synthetic and cannot replace physical transfer evidence.",
            "Lighting and obstruction properties remain provisional until the physical pilot.",
            "Independent fixture audit is required before any training or development render.",
        ],
    }
    result = {**core, "bundle_sha256": canonical_hash(core)}
    errors = sorted(Draft202012Validator(load_json(SCHEMA)).iter_errors(result), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        raise ValueError(f"schema validation failed at {list(first.path)}: {first.message}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--v5", type=Path, required=True)
    parser.add_argument("--v5-3", type=Path, required=True)
    parser.add_argument("--pretraining", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(source_commit=args.source_commit, v5_path=args.v5, v5_3_path=args.v5_3, pretraining_path=args.pretraining)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
