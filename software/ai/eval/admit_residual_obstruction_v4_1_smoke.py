"""Independently verify and summarize a bounded v4.1 reference-pair smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


MANIFEST_SCHEMA = "tactevra.ai_residual_obstruction_v4_1_smoke_manifest.v1"
REPORT_SCHEMA = "tactevra.ai_residual_obstruction_v4_1_smoke_admission.v1"
METRICS = (
    "raw_mean_absolute_difference",
    "self_crop_normalized_mean_absolute_difference",
    "context_normalized_mean_absolute_difference",
)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def rank_auc(labels: list[bool], scores: list[float]) -> float:
    """Return tie-aware binary ROC AUC without an external statistics package."""
    if len(labels) != len(scores) or not labels:
        raise ValueError("labels and scores must be nonempty and equal length")
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("both classes are required")
    ordered = sorted(zip(scores, labels, strict=True), key=lambda item: item[0])
    rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2.0
        rank_sum += average_rank * sum(label for _, label in ordered[index:end])
        index = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def _read_bound_file(root: Path, relative: str, expected_hash: str, expected_bytes: int) -> bytes:
    path = (root / relative).resolve(strict=True)
    if root not in path.parents:
        raise ValueError("bound image escapes the smoke root")
    payload = path.read_bytes()
    if len(payload) != expected_bytes or sha256_bytes(payload) != expected_hash:
        raise ValueError(f"bound image mismatch: {relative}")
    return payload


def admit(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve(strict=True)
    root = manifest_path.parent
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("unsupported smoke manifest")
    if manifest.get("scope") != "SYNTHETIC_ISAAC_REFERENCE_PAIR_SMOKE_NO_QUALIFICATION":
        raise ValueError("smoke scope changed")
    if manifest.get("complete_campaign") is not False:
        raise ValueError("bounded smoke cannot claim a complete campaign")
    if manifest.get("evaluation_observation_count") != 0 or manifest["split_counts"].get("evaluation", 0) != 0:
        raise ValueError("evaluation rows are prohibited")
    if manifest.get("hardware_writes") != 0 or manifest.get("physical_movements") != 0:
        raise ValueError("smoke claims physical effects")
    observations = manifest.get("observations")
    if not isinstance(observations, list) or len(observations) != manifest.get("observation_count"):
        raise ValueError("observation inventory mismatch")

    observation_ids: set[str] = set()
    observation_hashes: set[str] = set()
    reference_bindings: dict[str, tuple[str, str, int]] = {}
    targets: set[str] = set()
    labels: list[bool] = []
    scores = {metric: [] for metric in METRICS}
    target_rows: dict[str, list[dict[str, Any]]] = {}
    for row in observations:
        if row["split"] != "training":
            raise ValueError("smoke may contain training rows only")
        if row["observation_id"] in observation_ids or row["rgb_sha256"] in observation_hashes:
            raise ValueError("duplicate observation identity or RGB bytes")
        observation_ids.add(row["observation_id"])
        observation_hashes.add(row["rgb_sha256"])
        _read_bound_file(root, row["rgb_path"], row["rgb_sha256"], row["rgb_bytes"])
        _read_bound_file(
            root,
            row["reference_rgb_path"],
            row["reference_rgb_sha256"],
            row["reference_rgb_bytes"],
        )
        binding = (row["reference_rgb_path"], row["reference_rgb_sha256"], row["reference_rgb_bytes"])
        previous = reference_bindings.setdefault(row["reference_id"], binding)
        if previous != binding:
            raise ValueError("reference identity maps to inconsistent bytes")
        metrics = row.get("difference_metrics", {})
        for metric in METRICS:
            value = metrics.get(metric)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0.0:
                raise ValueError(f"invalid difference metric: {metric}")
            scores[metric].append(float(value))
        label = row["expected_decision"] == "ABSTAIN"
        if row["expected_decision"] not in {"ABSTAIN", "VISIBLE"}:
            raise ValueError("unsupported decision label")
        labels.append(label)
        targets.add(row["target_id"])
        target_rows.setdefault(row["target_id"], []).append(row)

    canonical_core = {key: value for key, value in manifest.items() if key != "dataset_sha256"}
    if sha256_bytes(canonical(canonical_core)) != manifest.get("dataset_sha256"):
        raise ValueError("canonical dataset hash mismatch")

    pooled_auc = {metric: rank_auc(labels, values) for metric, values in scores.items()}
    per_target_auc = {
        target: {
            metric: rank_auc(
                [row["expected_decision"] == "ABSTAIN" for row in rows],
                [float(row["difference_metrics"][metric]) for row in rows],
            )
            for metric in METRICS
        }
        for target, rows in sorted(target_rows.items())
    }
    report_core = {
        "schema": REPORT_SCHEMA,
        "status": "PASS_WITH_LIMITATIONS",
        "scope": manifest["scope"],
        "manifest_file_sha256": sha256_bytes(manifest_bytes),
        "dataset_sha256": manifest["dataset_sha256"],
        "fixture_bundle_sha256": manifest["fixture_bundle_sha256"],
        "observation_count": len(observations),
        "reference_count": len(reference_bindings),
        "unique_observation_rgb_count": len(observation_hashes),
        "target_ids": sorted(targets),
        "evaluation_observation_count": 0,
        "pooled_auc": pooled_auc,
        "per_target_auc": per_target_auc,
        "normalization_decision": "RETAIN_SELF_AND_REFERENCE_CONTEXT_FOR_DEVELOPMENT_COMPARISON",
        "normalization_finding": (
            "On this bounded shard, independent self-crop normalization ranks labels better than "
            "the current reference-context transform; neither method is selected from smoke evidence."
        ),
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "This is a four-target, one-scene synthetic training smoke, not a model or qualification result.",
            "The smoke is too small to select normalization, thresholds, architecture, or deployment policy.",
            "Evaluation pixels remain absent and unopened.",
        ],
    }
    return {**report_core, "report_sha256": sha256_bytes(canonical(report_core))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = admit(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
