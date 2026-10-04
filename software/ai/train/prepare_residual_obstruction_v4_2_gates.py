"""Prepare frozen v4.2 pretraining gates from a completely admitted campaign."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT / "eval"))

from admit_residual_obstruction_v4_2_shards import (  # noqa: E402
    MANIFEST_SCHEMA,
    canonical,
    digest,
    load_bound,
)


ADMISSION_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_admission.v1"
FIXTURE_SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v4_2"
PREPARATION_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_gate_preparation.v1"
NORMALIZATION_METRICS = {
    "SELF_CROP_P05_P95": "self_crop_normalized_mean_absolute_difference",
    "REFERENCE_CONTEXT_WHITEPOINT": "context_normalized_mean_absolute_difference",
}


def _load_report(path: Path, schema: str) -> tuple[dict[str, Any], bytes]:
    payload = path.resolve(strict=True).read_bytes()
    report = json.loads(payload)
    if report.get("schema") != schema:
        raise ValueError(f"schema mismatch: {path}")
    core = {key: value for key, value in report.items() if key != "report_sha256"}
    if report.get("report_sha256") != digest(canonical(core)):
        raise ValueError(f"report hash mismatch: {path}")
    return report, payload


def load_complete_campaign(
    fixture_path: Path, admission_path: Path, shard_dirs: list[Path]
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    fixture, fixture_bytes = load_bound(
        fixture_path.resolve(strict=True), FIXTURE_SCHEMA, "bundle_sha256"
    )
    admission, admission_bytes = _load_report(admission_path, ADMISSION_SCHEMA)
    if admission["status"] != "PASS" or admission["campaign_admitted"] is not True:
        raise ValueError("gate preparation requires complete campaign admission")
    if admission["training_started"] is not False:
        raise ValueError("admission already claims training")
    if admission["evaluation_observation_count"] != 0:
        raise ValueError("evaluation observations are prohibited")
    if admission["fixture_file_sha256"] != digest(fixture_bytes):
        raise ValueError("admission fixture file mismatch")
    if admission["fixture_bundle_sha256"] != fixture["bundle_sha256"]:
        raise ValueError("admission fixture bundle mismatch")
    expected = {str(Path(row["path"]).resolve()): row for row in admission["manifests"]}
    actual = {str(path.resolve(strict=True) / "manifest.json") for path in shard_dirs}
    if actual != set(expected):
        raise ValueError("shard paths differ from exact admitted manifest inventory")
    entries: list[dict[str, Any]] = []
    for manifest_path_text in sorted(actual):
        manifest_path = Path(manifest_path_text)
        manifest, manifest_bytes = load_bound(manifest_path, MANIFEST_SCHEMA, "dataset_sha256")
        bound = expected[manifest_path_text]
        if digest(manifest_bytes) != bound["manifest_file_sha256"]:
            raise ValueError("manifest file hash differs from admission")
        if manifest["dataset_sha256"] != bound["dataset_sha256"]:
            raise ValueError("manifest dataset hash differs from admission")
        if manifest["split"] != bound["split"]:
            raise ValueError("manifest split differs from admission")
        root = manifest_path.parent
        for row in manifest["observations"]:
            entries.append({**row, "shard_root": str(root)})
    entries.sort(key=lambda row: row["observation_id"])
    if len(entries) != admission["verified_observation_count"]:
        raise ValueError("loaded observation count differs from admission")
    if sum(row["split"] == "training" for row in entries) != 43_200:
        raise ValueError("training observation count differs from frozen campaign")
    if sum(row["split"] == "development" for row in entries) != 28_800:
        raise ValueError("development observation count differs from frozen campaign")
    return fixture, admission, entries


def load_manifest_rows(manifest_path: Path) -> list[dict[str, Any]]:
    """Load one bound manifest for smoke-testing pure training preparation logic."""
    manifest_path = manifest_path.resolve(strict=True)
    manifest, _ = load_bound(manifest_path, MANIFEST_SCHEMA, "dataset_sha256")
    if manifest["split"] != "training" or manifest["evaluation_observation_count"] != 0:
        raise ValueError("smoke preparation accepts training manifests only")
    return [
        {**row, "shard_root": str(manifest_path.parent)} for row in manifest["observations"]
    ]


def _rank(seed: int, observation_id: str) -> str:
    return hashlib.sha256(f"{seed}:{observation_id}".encode()).hexdigest()


def select_memorization_subset(
    entries: list[dict[str, Any]], count: int, seed: int
) -> list[dict[str, Any]]:
    if count <= 0 or count % 2:
        raise ValueError("memorization subset count must be a positive even number")
    training = [row for row in entries if row["split"] == "training"]
    by_label_target: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in training:
        decision = row["expected_decision"]
        if decision not in {"VISIBLE", "ABSTAIN"}:
            raise ValueError("unsupported decision label")
        target = f"{row['device']}:{row['target_id']}"
        by_label_target[(decision, target)].append(row)
    quota = count // 2
    selected: list[dict[str, Any]] = []
    for decision in ("VISIBLE", "ABSTAIN"):
        groups = {
            target: sorted(rows, key=lambda row: (_rank(seed, row["observation_id"]), row["observation_id"]))
            for (label, target), rows in by_label_target.items()
            if label == decision
        }
        if not groups:
            raise ValueError(f"no rows for label: {decision}")
        cursors = {target: 0 for target in groups}
        targets = sorted(groups)
        chosen: list[dict[str, Any]] = []
        while len(chosen) < quota:
            progressed = False
            for target in targets:
                cursor = cursors[target]
                if cursor < len(groups[target]) and len(chosen) < quota:
                    chosen.append(groups[target][cursor])
                    cursors[target] += 1
                    progressed = True
            if not progressed:
                raise ValueError(f"insufficient rows for label: {decision}")
        selected.extend(chosen)
    selected.sort(key=lambda row: row["observation_id"])
    if len({row["observation_id"] for row in selected}) != count:
        raise ValueError("memorization subset contains duplicate identities")
    return selected


def build_preparation(
    fixture: dict[str, Any], admission: dict[str, Any], entries: list[dict[str, Any]]
) -> dict[str, Any]:
    gates = fixture["pretraining_gates"]
    seed = int(fixture["training_plan"]["seed"]) + 1
    subset = select_memorization_subset(entries, int(gates["memorization_subset_count"]), seed)
    rows = [
        {
            "observation_id": row["observation_id"],
            "expected_decision": row["expected_decision"],
            "device": row["device"],
            "target_id": row["target_id"],
            "variant_id": row["variant_id"],
            "rgb_path": row["rgb_path"],
            "rgb_sha256": row["rgb_sha256"],
            "rgb_bytes": row["rgb_bytes"],
            "reference_rgb_path": row["reference_rgb_path"],
            "reference_rgb_sha256": row["reference_rgb_sha256"],
            "reference_rgb_bytes": row["reference_rgb_bytes"],
            "shard_root": row["shard_root"],
        }
        for row in subset
    ]
    core = {
        "schema": PREPARATION_SCHEMA,
        "scope": "SYNTHETIC_TRAINING_ONLY_PRETRAINING_GATE_INPUT_NO_QUALIFICATION",
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "admission_report_sha256": admission["report_sha256"],
        "subset_seed": seed,
        "subset_selector": "LABEL_BALANCED_TARGET_ROUND_ROBIN_SHA256_RANK_V1",
        "subset_count": len(rows),
        "visible_count": sum(row["expected_decision"] == "VISIBLE" for row in rows),
        "abstain_count": sum(row["expected_decision"] == "ABSTAIN" for row in rows),
        "covered_target_ids": sorted({f"{row['device']}:{row['target_id']}" for row in rows}),
        "subset_identity_sha256": digest(canonical([row["observation_id"] for row in rows])),
        "subset_rows": rows,
        "normalization_metrics": NORMALIZATION_METRICS,
        "memorization_training": {
            "architecture": "SPATIAL_REFERENCE_DIFFERENCE_CNN_6X6",
            "one_run_per_normalization": True,
            "epochs_maximum": 300,
            "batch_size": 100,
            "optimizer": "ADAMW",
            "learning_rate": 0.003,
            "weight_decay": 0.0,
            "augmentation_enabled": False,
            "dropout_enabled": False,
            "accuracy_minimum": gates["memorization_accuracy_minimum"],
            "loss_maximum": gates["memorization_loss_maximum"],
        },
        "gate_order": [
            "COMPLETE_ADMISSION",
            "BOTH_NORMALIZATION_MEMORIZATION_RUNS",
            "DEVELOPMENT_TRAINING_FREE_BASELINE_SELECTION",
            "FULL_TRAINING_AND_CNN_UPLIFT",
        ],
        "development_pixels_opened": False,
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "report_sha256": digest(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--shard", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture, admission, entries = load_complete_campaign(args.fixture, args.admission, args.shard)
    result = build_preparation(fixture, admission, entries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: result[key] for key in (
        "report_sha256", "subset_identity_sha256", "subset_count", "visible_count", "abstain_count"
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
