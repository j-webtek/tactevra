"""Explain the rejected residual-v3 500-row memorization failure on training data."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.audit_residual_obstruction_v3_training import (  # noqa: E402
    _load_arrays,
    load_training_entries,
    select_memorization_subset,
)
from eval.admit_residual_obstruction_v3_shards import canonical, sha256_bytes  # noqa: E402


SCHEMA = "tactevra.ai_residual_v3_memorization_diagnostic.v1"


def _legacy_model(torch: Any, channels: list[int]) -> Any:
    return torch.nn.Sequential(
        torch.nn.Conv2d(3, channels[0], 3, padding=1), torch.nn.GroupNorm(6, channels[0]),
        torch.nn.ReLU(), torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[0], channels[1], 3, padding=1), torch.nn.GroupNorm(8, channels[1]),
        torch.nn.ReLU(), torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[1], channels[2], 3, padding=1), torch.nn.GroupNorm(8, channels[2]),
        torch.nn.ReLU(), torch.nn.AdaptiveAvgPool2d((1, 1)), torch.nn.Flatten(),
        torch.nn.Linear(channels[2], 1),
    )


def _spatial_control(torch: Any, channels: list[int]) -> Any:
    return torch.nn.Sequential(
        torch.nn.Conv2d(3, channels[0], 3, padding=1), torch.nn.GroupNorm(6, channels[0]),
        torch.nn.ReLU(), torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[0], channels[1], 3, padding=1), torch.nn.GroupNorm(8, channels[1]),
        torch.nn.ReLU(), torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[1], channels[2], 3, padding=1), torch.nn.GroupNorm(8, channels[2]),
        torch.nn.ReLU(), torch.nn.AvgPool2d(4), torch.nn.Flatten(),
        torch.nn.Linear(channels[2] * 36, 1),
    )


def _train_control(
    arrays: np.ndarray, labels: np.ndarray, channels: list[int], seed: int, spatial: bool
) -> tuple[dict[str, Any], np.ndarray]:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = (_spatial_control if spatial else _legacy_model)(torch, channels).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.003, weight_decay=0.0)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    rng = np.random.default_rng(seed)
    first_loss = None
    final_loss = 0.0
    probabilities = np.zeros(len(labels), dtype=np.float32)
    for epoch in range(1, 301):
        order = rng.permutation(len(labels))
        model.train()
        total = 0.0
        for start in range(0, len(order), 100):
            batch = order[start:start + 100]
            x = torch.from_numpy(arrays[batch]).to(device=device, dtype=torch.float32).div_(255.0)
            y = torch.from_numpy(labels[batch]).to(device=device).reshape(-1, 1)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(x), y)
            loss.backward()
            optimizer.step()
            total += float(loss.detach().cpu()) * len(batch)
        final_loss = total / len(labels)
        if first_loss is None:
            first_loss = final_loss
        model.eval()
        with torch.no_grad():
            x = torch.from_numpy(arrays).to(device=device, dtype=torch.float32).div_(255.0)
            probabilities = torch.sigmoid(model(x)).reshape(-1).cpu().numpy()
        accuracy = float(np.mean((probabilities >= 0.5) == labels))
        if final_loss <= 0.01 and accuracy >= 0.995:
            break
    return {
        "architecture": "SPATIAL_6X6_CONTROL" if spatial else "LEGACY_GLOBAL_AVERAGE_POOL",
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "epochs_run": epoch,
        "first_loss": first_loss,
        "final_loss": final_loss,
        "final_accuracy": accuracy,
        "gate_met": final_loss <= 0.01 and accuracy >= 0.995,
        "augmentation_enabled": False,
        "dropout_module_count": sum(isinstance(module, torch.nn.Dropout) for module in model.modules()),
        "optimizer": "ADAMW",
        "learning_rate": 0.003,
        "weight_decay": 0.0,
    }, probabilities


def _normalize_pixels(arrays: np.ndarray) -> np.ndarray:
    values = arrays.astype(np.float32) / 255.0
    low = np.quantile(values, 0.05, axis=(2, 3), keepdims=True)
    high = np.quantile(values, 0.95, axis=(2, 3), keepdims=True)
    values = np.clip((values - low) / np.maximum(high - low, 0.05), 0.0, 1.0)
    means = values.mean(axis=(2, 3), keepdims=True)
    return np.clip(values / np.maximum(means.mean(axis=1, keepdims=True), 0.1), 0.0, 2.0)


def _opposite_label_similarity(arrays: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    raw = arrays[:, :, ::8, ::8].astype(np.float32) / 255.0
    normalized = _normalize_pixels(arrays)[:, :, ::8, ::8]
    visible = np.flatnonzero(labels == 0)
    obstruction = np.flatnonzero(labels == 1)
    raw_distances = np.mean(
        np.abs(raw[visible, None] - raw[obstruction][None, :]), axis=(2, 3, 4)
    )
    normalized_distances = np.mean(
        np.abs(normalized[visible, None] - normalized[obstruction][None, :]), axis=(2, 3, 4)
    )
    flat = int(np.argmin(normalized_distances))
    row, column = np.unravel_index(flat, normalized_distances.shape)
    return {
        "exact_opposite_label_rgb_duplicate_count": 0,
        "minimum_raw_downsampled_mae": float(np.min(raw_distances)),
        "minimum_photometric_normalized_downsampled_mae": float(np.min(normalized_distances)),
        "normalized_mae_quantiles": {
            "q01": float(np.quantile(normalized_distances, 0.01)),
            "q05": float(np.quantile(normalized_distances, 0.05)),
            "q50": float(np.quantile(normalized_distances, 0.5)),
        },
        "closest_visible_subset_index": int(visible[row]),
        "closest_obstruction_subset_index": int(obstruction[column]),
    }


def _errors(entries: list[dict[str, Any]], probabilities: np.ndarray) -> dict[str, Any]:
    labels = np.asarray([row["expected_decision"] == "ABSTAIN" for row in entries])
    wrong = np.flatnonzero((probabilities >= 0.5) != labels)
    by_variant = Counter(entries[index]["variant_id"] for index in wrong)
    by_appearance = Counter(entries[index]["appearance_id"] for index in wrong)
    by_scene = Counter(entries[index]["scene_id"] for index in wrong)
    rows = sorted(
        ({
            "observation_id": entries[index]["observation_id"],
            "expected_decision": entries[index]["expected_decision"],
            "probability": float(probabilities[index]),
            "variant_id": entries[index]["variant_id"],
            "safe_overlap_fraction": entries[index]["safe_overlap_fraction"],
        } for index in wrong),
        key=lambda row: abs(row["probability"] - (1.0 if row["expected_decision"] == "ABSTAIN" else 0.0)),
        reverse=True,
    )
    return {
        "error_count": len(wrong),
        "by_variant": dict(sorted(by_variant.items())),
        "by_appearance": dict(sorted(by_appearance.items())),
        "by_scene": dict(sorted(by_scene.items())),
        "most_confident_errors": rows[:25],
    }


def diagnose(
    workspace: Path, fixture: Path, admission: Path, lineage: Path, shards: list[Path]
) -> dict[str, Any]:
    fixture_data, admission_data, entries, _ = load_training_entries(
        workspace, fixture, admission, lineage, shards
    )
    arrays = _load_arrays(entries)
    seed = int(fixture_data["training_plan"]["seed"]) + 1
    selected = select_memorization_subset(entries, 500, seed)
    subset_entries = [entries[index] for index in selected]
    subset_arrays = arrays[selected]
    labels = np.asarray(
        [1.0 if row["expected_decision"] == "ABSTAIN" else 0.0 for row in subset_entries],
        dtype=np.float32,
    )
    hashes: dict[str, set[int]] = defaultdict(set)
    for index, row in enumerate(subset_entries):
        hashes[row["rgb_sha256"]].add(int(labels[index]))
    similarity = _opposite_label_similarity(subset_arrays, labels)
    similarity["exact_opposite_label_rgb_duplicate_count"] = sum(len(value) > 1 for value in hashes.values())
    channels = [int(value) for value in fixture_data["training_plan"]["convolution_channels"]]
    legacy, legacy_probabilities = _train_control(subset_arrays, labels, channels, seed, False)
    spatial, spatial_probabilities = _train_control(subset_arrays, labels, channels, seed, True)
    closest_visible = similarity.pop("closest_visible_subset_index")
    closest_obstruction = similarity.pop("closest_obstruction_subset_index")
    similarity["closest_opposite_label_pair"] = [
        subset_entries[closest_visible]["observation_id"],
        subset_entries[closest_obstruction]["observation_id"],
    ]
    core = {
        "schema": SCHEMA,
        "scope": "TRAINING_ONLY_MEMORIZATION_DIAGNOSTIC_NO_QUALIFICATION",
        "fixture_bundle_sha256": fixture_data["bundle_sha256"],
        "admission_receipt_sha256": admission_data["receipt_sha256"],
        "subset_identity_sha256": sha256_bytes(canonical([row["observation_id"] for row in subset_entries])),
        "subset_count": 500,
        "visible_count": 250,
        "obstruction_count": 250,
        "opposite_label_similarity": similarity,
        "legacy_control": legacy,
        "legacy_errors": _errors(subset_entries, legacy_probabilities),
        "spatial_control": spatial,
        "spatial_errors": _errors(subset_entries, spatial_probabilities),
        "development_pixels_opened": False,
        "evaluation_opened": False,
        "checkpoint_changed": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "This diagnostic uses synthetic training crops and cannot evaluate v4 or v4.1",
            "Downsampled MAE is a collision diagnostic, not a perceptual-equivalence proof",
            "The spatial control diagnoses representational capacity and is not a deployable candidate",
        ],
    }
    return {**core, "report_sha256": sha256_bytes(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--lineage", type=Path, required=True)
    parser.add_argument("--shard", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(args.workspace, args.fixture, args.admission, args.lineage, args.shard)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({
        "report_sha256": result["report_sha256"],
        "legacy": result["legacy_control"],
        "spatial": result["spatial_control"],
        "similarity": result["opposite_label_similarity"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
