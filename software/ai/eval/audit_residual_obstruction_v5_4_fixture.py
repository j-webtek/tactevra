"""Independently audit the frozen v5.4 rotation and development support."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

AI_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = AI_ROOT / "schemas/residual_obstruction_v5_4_fixture_audit_v1.schema.json"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def audit(*, source_commit: str, fixture_path: Path, v5_path: Path, v5_3_path: Path, pretraining_path: Path) -> dict[str, Any]:
    fixture = load_json(fixture_path)
    v5 = load_json(v5_path)
    v5_3 = load_json(v5_3_path)
    pretraining = load_json(pretraining_path)
    fixture_core = {key: value for key, value in fixture.items() if key != "bundle_sha256"}
    if canonical_hash(fixture_core) != fixture["bundle_sha256"]:
        raise ValueError("fixture bundle hash mismatch")
    source = fixture["source"]
    expected_files = {
        "v5_file_sha256": file_hash(v5_path),
        "v5_3_file_sha256": file_hash(v5_3_path),
        "pretraining_file_sha256": file_hash(pretraining_path),
    }
    for field, expected in expected_files.items():
        if source[field] != expected:
            raise ValueError(f"source hash mismatch: {field}")
    if source["v5_bundle_sha256"] != v5["bundle_sha256"] or source["v5_3_report_sha256"] != v5_3["report_sha256"]:
        raise ValueError("source report binding mismatch")
    if source["target_catalog_sha256"] != pretraining["source"]["target_catalog_sha256"]:
        raise ValueError("target catalog mismatch")

    source_targets = {(row["device"], row["target_id"]) for row in pretraining["observations"]}
    rotation = fixture["evaluation_rotation"]
    order = [(row["device"], row["target_id"]) for row in rotation["target_order"]]
    if len(order) != 75 or len(set(order)) != 75 or set(order) != source_targets:
        raise ValueError("rotation target inventory mismatch")
    salt = rotation["salt"]
    expected_order = sorted(
        source_targets,
        key=lambda value: hashlib.sha256(f"{salt}|{value[0]}|{value[1]}".encode()).hexdigest(),
    )
    if order != expected_order:
        raise ValueError("target order does not match declared SHA-256 algorithm")

    occurrences: Counter[tuple[str, str]] = Counter()
    scene_ids: set[str] = set()
    seeds: set[int] = set()
    mixed_device_scenes = 0
    for index, scene in enumerate(rotation["scenes"]):
        if scene["scene_id"] != f"v5_4_evaluation_scene_{index + 1:04d}":
            raise ValueError("scene identity sequence mismatch")
        if scene["procedural_seed"] != 53000 + index:
            raise ValueError("scene seed sequence mismatch")
        targets = [(row["device"], row["target_id"]) for row in scene["targets"]]
        expected = [order[(index * 12 + offset) % 75] for offset in range(12)]
        if targets != expected or len(set(targets)) != 12:
            raise ValueError("scene target rotation mismatch")
        scene_ids.add(scene["scene_id"])
        seeds.add(scene["procedural_seed"])
        occurrences.update(targets)
        mixed_device_scenes += len({device for device, _ in targets}) == 2
    if len(scene_ids) != 224 or len(seeds) != 224:
        raise ValueError("scene or seed identities are not unique")
    distribution = Counter(occurrences.values())
    if distribution != Counter({36: 63, 35: 12}):
        raise ValueError("target exposure distribution mismatch")

    train_dev_scene_ids = set(fixture["preserved_splits"]["training_scene_ids"] + fixture["preserved_splits"]["development_scene_ids"])
    if scene_ids & train_dev_scene_ids:
        raise ValueError("evaluation scene leakage")
    if any(seed < 53000 or seed > 53223 for seed in seeds):
        raise ValueError("evaluation seed outside frozen range")

    variants = v5["variants"]
    dev_scenes = len(v5["split_identities"]["scenes"]["development"])
    appearances = v5["render_contract"]["appearances_per_scene"]
    expected_per_target = {
        "scene_identities": 8,
        "appearance_identities": 3,
        "visible_rows": dev_scenes * appearances * sum(row["decision"] == "VISIBLE" for row in variants),
        "all_obstruction_rows": dev_scenes * appearances * sum(row["decision"] == "ABSTAIN" for row in variants),
        "cable_abstain_rows": dev_scenes * appearances * sum(row["family"] == "CABLE" and row["decision"] == "ABSTAIN" for row in variants),
        "dark_cable_30_60_abstain_rows": dev_scenes * appearances * sum(row["variant_id"] in {"dark_cable_30", "dark_cable_60"} for row in variants),
        "dark_cable_10_boundary_visible_rows": dev_scenes * appearances * sum(row["variant_id"] == "dark_cable_10" for row in variants),
    }
    if fixture["development_selection"]["per_target_support"] != expected_per_target:
        raise ValueError("development support mismatch")
    if fixture["evaluation_safety_gates"] != v5_3["gate_roles"]["single_use_evaluation_safety_gates"]:
        raise ValueError("evaluation safety gates mismatch")
    if rotation["observation_identities"] != 224 * 12 * 3 * 12:
        raise ValueError("evaluation identity count mismatch")

    core = {
        "schema": "tactevra.ai_residual_obstruction_v5_4_fixture_audit.v1",
        "scope": "INDEPENDENT_FIXTURE_IDENTITY_AND_COUNT_AUDIT_NO_RENDER",
        "status": "PASS_FIXTURE_READY_FOR_TRAINING_DEVELOPMENT_RENDERER_IMPLEMENTATION",
        "source_commit": source_commit,
        "fixture_file_sha256": file_hash(fixture_path),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "source_file_sha256": expected_files,
        "rotation_metrics": {
            "scene_count": len(scene_ids),
            "unique_seed_count": len(seeds),
            "targets_per_scene": 12,
            "target_count": len(occurrences),
            "targets_at_35_scenes": distribution[35],
            "targets_at_36_scenes": distribution[36],
            "mixed_device_scene_count": mixed_device_scenes,
            "evaluation_observation_identities": rotation["observation_identities"],
        },
        "development_support": {
            "per_target": expected_per_target,
            "aggregate_cable_abstain_rows": expected_per_target["cable_abstain_rows"] * 75,
            "aggregate_dark_cable_abstain_rows": expected_per_target["dark_cable_30_60_abstain_rows"] * 75,
            "aggregate_dark_boundary_visible_rows": expected_per_target["dark_cable_10_boundary_visible_rows"] * 75,
            "candidate_count": fixture["development_selection"]["candidate_count"],
            "same_rows_for_every_candidate": fixture["development_selection"]["same_rows_for_every_candidate"],
            "adequacy": fixture["development_selection"]["adequacy"],
        },
        "power_interpretation_present": fixture["power_binding"]["interpretation"],
        "training_development_renderer_implementation_may_begin": True,
        "evaluation_render_authorized": False,
        "images_generated": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "Audit validates identities, balance, counts, hashes, and gate roles only.",
            "No renderer, image, model, threshold, or evaluation result exists.",
            "Development counts support diagnostics and paired selection, not powered safety claims.",
            "Physical pilot remains required for lighting, obstruction contrast, and sim-to-real transfer.",
        ],
    }
    result = {**core, "report_sha256": canonical_hash(core)}
    errors = sorted(Draft202012Validator(load_json(SCHEMA)).iter_errors(result), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        raise ValueError(f"schema validation failed at {list(first.path)}: {first.message}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--v5", type=Path, required=True)
    parser.add_argument("--v5-3", type=Path, required=True)
    parser.add_argument("--pretraining", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(source_commit=args.source_commit, fixture_path=args.fixture, v5_path=args.v5, v5_3_path=args.v5_3, pretraining_path=args.pretraining)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
