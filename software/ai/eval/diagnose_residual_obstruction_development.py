"""Diagnose a rejected residual-obstruction candidate without changing it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
from typing import Any

import numpy as np


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from train.build_residual_obstruction_pretraining import (  # noqa: E402
    FIXTURE_SCHEMA,
    MODEL_MAGIC,
    RESULT_SCHEMA as SCORECARD_SCHEMA,
    _load_arrays,
    canonical,
    load_bound,
    sha256_bytes,
    verify_dataset,
)


OUTPUT_SCHEMA = "tactevra.ai_residual_obstruction_development_diagnostic.v1"
DIAGNOSTIC_THRESHOLDS = (0.75, 0.80)


def _model(channels: list[int]):
    import torch

    return torch.nn.Sequential(
        torch.nn.Conv2d(4, channels[0], 3, padding=1), torch.nn.ReLU(), torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[0], channels[1], 3, padding=1), torch.nn.ReLU(), torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[1], channels[2], 3, padding=1), torch.nn.ReLU(),
        torch.nn.AdaptiveAvgPool2d((1, 1)), torch.nn.Flatten(), torch.nn.Linear(channels[2], 1),
    )


def load_model(path: Path):
    import torch

    payload = path.read_bytes()
    if not payload.startswith(MODEL_MAGIC):
        raise ValueError("residual model magic mismatch")
    cursor = len(MODEL_MAGIC)
    if len(payload) < cursor + 4:
        raise ValueError("residual model is truncated")
    metadata_size = struct.unpack_from("<I", payload, cursor)[0]
    cursor += 4
    end = cursor + metadata_size
    if end > len(payload):
        raise ValueError("residual model metadata is truncated")
    metadata = json.loads(payload[cursor:end])
    cursor = end
    state: dict[str, Any] = {}
    while cursor < len(payload):
        if cursor + 4 > len(payload):
            raise ValueError("residual model tensor header is truncated")
        name_size = struct.unpack_from("<I", payload, cursor)[0]
        cursor += 4
        name_end = cursor + name_size
        if name_end > len(payload):
            raise ValueError("residual model tensor name is truncated")
        name = payload[cursor:name_end].decode()
        cursor = name_end
        if cursor + 4 > len(payload):
            raise ValueError("residual model dimension header is truncated")
        dimensions = struct.unpack_from("<I", payload, cursor)[0]
        cursor += 4
        shape_end = cursor + dimensions * 4
        if shape_end > len(payload):
            raise ValueError("residual model shape is truncated")
        shape = struct.unpack_from("<" + "I" * dimensions, payload, cursor)
        cursor = shape_end
        count = int(np.prod(shape))
        tensor_end = cursor + count * 4
        if tensor_end > len(payload):
            raise ValueError("residual model tensor is truncated")
        array = np.frombuffer(payload[cursor:tensor_end], dtype="<f4").reshape(shape).copy()
        cursor = tensor_end
        if name in state:
            raise ValueError("residual model contains duplicate tensors")
        state[name] = torch.from_numpy(array)
    model = _model([int(value) for value in metadata["convolution_channels"]])
    model.load_state_dict(state, strict=True)
    model.eval()
    return model, metadata


def _summary(values: np.ndarray) -> dict[str, float]:
    return {
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
    }


def analyze(rows: list[dict[str, Any]], probabilities: np.ndarray) -> dict[str, Any]:
    if len(rows) != len(probabilities) or not rows:
        raise ValueError("diagnostic rows and probabilities must be nonempty and aligned")
    variants: list[dict[str, Any]] = []
    for variant in sorted({row["variant_id"] for row in rows}):
        indices = [index for index, row in enumerate(rows) if row["variant_id"] == variant]
        values = probabilities[indices]
        expected = {rows[index]["expected_decision"] for index in indices}
        if len(expected) != 1:
            raise ValueError("variant has mixed expected decisions")
        variants.append({
            "variant_id": variant,
            "expected_decision": expected.pop(),
            "count": len(indices),
            "probability": _summary(values),
            "threshold_decisions": [
                {
                    "threshold": threshold,
                    "abstain_count": int(np.sum(values >= threshold)),
                    "visible_count": int(np.sum(values < threshold)),
                }
                for threshold in DIAGNOSTIC_THRESHOLDS
            ],
        })

    targets: list[dict[str, Any]] = []
    for target in sorted({row["target_id"] for row in rows}):
        indices = [index for index, row in enumerate(rows) if row["target_id"] == target]
        visible = np.asarray([probabilities[index] for index in indices if rows[index]["expected_decision"] == "VISIBLE"])
        obstruction = np.asarray([probabilities[index] for index in indices if rows[index]["expected_decision"] == "ABSTAIN"])
        margin = float(np.min(obstruction) - np.max(visible))
        targets.append({
            "target_id": target,
            "visible_count": len(visible),
            "obstruction_count": len(obstruction),
            "visible_probability": _summary(visible),
            "obstruction_probability": _summary(obstruction),
            "separation_margin": margin,
            "locally_separable": margin > 0,
        })

    positive = probabilities[[row["expected_decision"] == "ABSTAIN" for row in rows]]
    negative = probabilities[[row["expected_decision"] == "VISIBLE" for row in rows]]
    comparisons = positive[:, None] - negative[None, :]
    auc = float(np.mean(comparisons > 0) + 0.5 * np.mean(comparisons == 0))
    separable = sum(1 for target in targets if target["locally_separable"])
    visible_variants = [item for item in variants if item["expected_decision"] == "VISIBLE"]
    obstruction_variants = [item for item in variants if item["expected_decision"] == "ABSTAIN"]
    return {
        "variant_diagnostics": variants,
        "target_diagnostics": targets,
        "global_probability": {
            "visible": _summary(negative),
            "obstruction": _summary(positive),
            "pairwise_auc": auc,
        },
        "target_separation": {
            "target_count": len(targets),
            "locally_separable_count": separable,
            "nonseparable_count": len(targets) - separable,
            "worst_margin": min(item["separation_margin"] for item in targets),
            "best_margin": max(item["separation_margin"] for item in targets),
        },
        "highest_visible_variant": max(visible_variants, key=lambda item: item["probability"]["mean"])["variant_id"],
        "lowest_obstruction_variant": min(obstruction_variants, key=lambda item: item["probability"]["mean"])["variant_id"],
    }


def diagnose(fixture_path: Path, dataset_dir: Path, model_path: Path, scorecard_path: Path) -> dict[str, Any]:
    import torch

    fixture = load_bound(fixture_path.resolve(strict=True), FIXTURE_SCHEMA, "bundle_sha256")
    dataset = verify_dataset(fixture_path, dataset_dir)
    scorecard = load_bound(scorecard_path.resolve(strict=True), SCORECARD_SCHEMA, "result_sha256")
    if scorecard.get("status") != "FAILED_DEVELOPMENT_GATE" or scorecard.get("selected_threshold") is not None:
        raise ValueError("diagnostic requires the exact rejected unselected candidate")
    if scorecard.get("evaluation_opened") is not False or scorecard.get("evaluation_count") != 0:
        raise ValueError("diagnostic refuses opened evaluation evidence")
    if scorecard["fixture_bundle_sha256"] != fixture["bundle_sha256"] or scorecard["dataset_sha256"] != dataset["dataset_sha256"]:
        raise ValueError("scorecard source binding mismatch")
    if sha256_bytes(model_path.read_bytes()) != scorecard["model_sha256"]:
        raise ValueError("model hash mismatch")
    model, metadata = load_model(model_path)
    if metadata["fixture_bundle_sha256"] != fixture["bundle_sha256"] or metadata["dataset_sha256"] != dataset["dataset_sha256"]:
        raise ValueError("model metadata binding mismatch")

    x, _, splits, _, identities = _load_arrays(dataset_dir, dataset)
    development_indices = [index for index, split in enumerate(splits) if split == "development"]
    with torch.no_grad():
        probabilities = torch.sigmoid(model(torch.from_numpy(x[development_indices]))).reshape(-1).numpy()
    if sha256_bytes(np.asarray(probabilities, dtype="<f4").tobytes()) != scorecard["development_probability_sha256"]:
        raise ValueError("reconstructed probabilities do not match the retained candidate")
    development_identities = [identities[index] for index in development_indices]
    if sha256_bytes(canonical(development_identities)) != scorecard["development_identity_sha256"]:
        raise ValueError("development identity order mismatch")
    fixture_rows = {row["observation_id"]: row for row in fixture["observations"]}
    rows = [fixture_rows[identity] for identity in development_identities]
    diagnostic = analyze(rows, probabilities)
    development_files = [entry for entry in dataset["files"] if entry["split"] == "development"]
    file_hashes = {(entry["target_id"], entry["variant_id"]): entry["sha256"] for entry in development_files}
    target_ids = sorted({entry["target_id"] for entry in development_files})
    identical_clear_distractor = sum(
        file_hashes[(target_id, "none_clear")] == file_hashes[(target_id, "none_adjacent_distractor")]
        for target_id in target_ids
    )
    core = {
        "schema": OUTPUT_SCHEMA,
        "scope": "CONSUMED_SYNTHETIC_DEVELOPMENT_DIAGNOSTIC_NO_QUALIFICATION",
        "fixture_file_sha256": sha256_bytes(fixture_path.read_bytes()),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "dataset_manifest_file_sha256": sha256_bytes((dataset_dir / "manifest.json").read_bytes()),
        "dataset_sha256": dataset["dataset_sha256"],
        "dataset_inventory_sha256": dataset["inventory_sha256"],
        "model_file_sha256": sha256_bytes(model_path.read_bytes()),
        "scorecard_file_sha256": sha256_bytes(scorecard_path.read_bytes()),
        "scorecard_result_sha256": scorecard["result_sha256"],
        "development_probability_sha256": scorecard["development_probability_sha256"],
        "development_count": len(rows),
        "dataset_identity_diagnostics": {
            "clear_adjacent_pair_count": len(target_ids),
            "byte_identical_clear_adjacent_pair_count": identical_clear_distractor,
        },
        **diagnostic,
        "checkpoint_changed": False,
        "threshold_changed": False,
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "This diagnostic reuses a consumed synthetic development split and cannot evaluate a successor",
            "The two source poses are correlated and do not represent physical camera or obstruction diversity",
            "Per-variant and per-target identities are design evidence, not qualification",
        ],
    }
    return {**core, "report_sha256": sha256_bytes(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--scorecard", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(args.fixture, args.dataset_dir, args.model.resolve(strict=True), args.scorecard)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({
        "schema": result["schema"], "report_sha256": result["report_sha256"],
        "pairwise_auc": result["global_probability"]["pairwise_auc"],
        "nonseparable_targets": result["target_separation"]["nonseparable_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
