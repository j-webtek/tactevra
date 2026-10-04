"""Train and development-score the frozen residual-obstruction v2 campaign."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import struct
import sys
from typing import Any

import numpy as np
from PIL import Image


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from sim.render_residual_obstruction_v2 import (  # noqa: E402
    FIXTURE_SCHEMA,
    canonical,
    load_bound,
    sha256_bytes,
    verify,
)


RESULT_SCHEMA = "tactevra.ai_residual_obstruction_development.v2"
MODEL_MAGIC = b"TACTEVRA_RESIDUAL_CNN_V2\0"


def _load_arrays(dataset_dir: Path, entries: list[dict[str, Any]]) -> np.ndarray:
    arrays = np.empty((len(entries), 3, 96, 96), dtype=np.uint8)
    for index, entry in enumerate(entries):
        with Image.open(dataset_dir / entry["path"]) as image:
            value = np.asarray(image.convert("RGB"), dtype=np.uint8)
        if value.shape != (96, 96, 3):
            raise ValueError(f"unexpected crop shape: {entry['observation_id']}")
        arrays[index] = value.transpose(2, 0, 1)
    return arrays


def balanced_epoch_indices(entries: list[dict[str, Any]], count: int, seed: int) -> np.ndarray:
    groups: dict[tuple[str, str], np.ndarray] = {}
    for label in ("VISIBLE", "ABSTAIN"):
        variants = sorted({row["variant_id"] for row in entries if row["expected_decision"] == label})
        for variant in variants:
            groups[(label, variant)] = np.asarray([
                index for index, row in enumerate(entries)
                if row["expected_decision"] == label and row["variant_id"] == variant
            ], dtype=np.int64)
    rng = np.random.default_rng(seed)
    selected: list[np.ndarray] = []
    per_label = count // 2
    for label in ("VISIBLE", "ABSTAIN"):
        keys = [key for key in groups if key[0] == label]
        base, remainder = divmod(per_label, len(keys))
        for position, key in enumerate(keys):
            size = base + (position < remainder)
            source = groups[key]
            selected.append(rng.choice(source, size=size, replace=size > len(source)))
    output = np.concatenate(selected)
    rng.shuffle(output)
    if len(output) != count:
        raise ValueError("balanced sampling count mismatch")
    return output


def _rates(labels: np.ndarray, probabilities: np.ndarray, threshold: float) -> tuple[int, int, int, int]:
    predicted = probabilities >= threshold
    obstruction = labels == 1
    visible = ~obstruction
    return (
        int(np.sum(obstruction & ~predicted)), int(np.sum(obstruction)),
        int(np.sum(visible & predicted)), int(np.sum(visible)),
    )


def score_thresholds(
    labels: np.ndarray,
    probabilities: np.ndarray,
    views: list[str],
    appearances: list[str],
    candidates: list[float],
    gate: dict[str, Any],
) -> list[dict[str, Any]]:
    unique_views = sorted(set(views))
    view_groups = [np.asarray([i for i, value in enumerate(views) if value == identity]) for identity in unique_views]
    rng = np.random.default_rng(int(gate["view_cluster_bootstrap_seed"]))
    samples = rng.integers(0, len(view_groups), size=(int(gate["view_cluster_bootstrap_resamples"]), len(view_groups)))
    results = []
    for threshold in candidates:
        misses, obstruction_count, false_stops, visible_count = _rates(labels, probabilities, threshold)
        grouped = np.asarray([_rates(labels[index], probabilities[index], threshold) for index in view_groups], dtype=np.int64)
        selected = grouped[samples].sum(axis=1)
        miss_upper = float(np.quantile(selected[:, 0] / selected[:, 1], 0.95, method="higher"))
        false_upper = float(np.quantile(selected[:, 2] / selected[:, 3], 0.95, method="higher"))
        appearance_metrics = []
        for identity in sorted(set(appearances)):
            index = np.asarray([i for i, value in enumerate(appearances) if value == identity])
            am, ac, af, av = _rates(labels[index], probabilities[index], threshold)
            appearance_metrics.append({
                "appearance_id": identity,
                "missed_obstruction_rate": am / ac,
                "visible_false_stop_rate": af / av,
            })
        maximum_miss = max(row["missed_obstruction_rate"] for row in appearance_metrics)
        maximum_false = max(row["visible_false_stop_rate"] for row in appearance_metrics)
        miss_rate, false_rate = misses / obstruction_count, false_stops / visible_count
        miss_limit = float(gate["missed_obstruction_rate_upper"])
        false_limit = float(gate["visible_false_stop_rate_upper"])
        results.append({
            "threshold": float(threshold),
            "missed_obstructions": misses,
            "obstruction_count": obstruction_count,
            "missed_obstruction_rate": miss_rate,
            "missed_obstruction_view_cluster_upper": miss_upper,
            "visible_false_stops": false_stops,
            "visible_count": visible_count,
            "visible_false_stop_rate": false_rate,
            "visible_false_stop_view_cluster_upper": false_upper,
            "maximum_appearance_missed_obstruction_rate": maximum_miss,
            "maximum_appearance_visible_false_stop_rate": maximum_false,
            "appearance_metrics": appearance_metrics,
            "gate_met": all((miss_rate <= miss_limit, miss_upper <= miss_limit, maximum_miss <= miss_limit,
                             false_rate <= false_limit, false_upper <= false_limit, maximum_false <= false_limit)),
        })
    return results


def _write_model(path: Path, state: dict[str, Any], metadata: dict[str, Any]) -> None:
    with path.open("wb") as handle:
        handle.write(MODEL_MAGIC)
        rendered = canonical(metadata)
        handle.write(struct.pack("<I", len(rendered)))
        handle.write(rendered)
        for name in sorted(state):
            array = state[name].detach().cpu().numpy().astype("<f4", copy=False)
            encoded = name.encode()
            handle.write(struct.pack("<I", len(encoded)))
            handle.write(encoded)
            handle.write(struct.pack("<I", array.ndim))
            handle.write(struct.pack("<" + "I" * array.ndim, *array.shape))
            handle.write(array.tobytes(order="C"))


def train(fixture_path: Path, contract_path: Path, dataset_dir: Path, output_dir: Path) -> dict[str, Any]:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    fixture = load_bound(fixture_path.resolve(strict=True), FIXTURE_SCHEMA, "bundle_sha256")
    manifest = verify(fixture_path, contract_path, dataset_dir)
    if manifest["evaluation_count"] != 0 or fixture["evaluation_group_present"] is not False:
        raise ValueError("evaluation data is present")
    if output_dir.exists():
        raise FileExistsError(f"refusing existing output directory: {output_dir}")
    entries = manifest["files"]
    arrays = _load_arrays(dataset_dir, entries)
    train_entries = [row for row in entries if row["split"] == "training"]
    train_indices = np.asarray([i for i, row in enumerate(entries) if row["split"] == "training"])
    development_indices = np.asarray([i for i, row in enumerate(entries) if row["split"] == "development"])
    if len(train_indices) != 27000 or len(development_indices) != 10125:
        raise ValueError("split count mismatch")

    plan = fixture["training_plan"]
    seed = int(plan["seed"])
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    channels = [int(value) for value in plan["convolution_channels"]]
    model = torch.nn.Sequential(
        torch.nn.Conv2d(3, channels[0], 3, padding=1), torch.nn.ReLU(), torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[0], channels[1], 3, padding=1), torch.nn.ReLU(), torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[1], channels[2], 3, padding=1), torch.nn.ReLU(),
        torch.nn.AdaptiveAvgPool2d((1, 1)), torch.nn.Flatten(), torch.nn.Linear(channels[2], 1),
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=float(plan["learning_rate"]), weight_decay=float(plan["weight_decay"]))
    loss_fn = torch.nn.BCEWithLogitsLoss()
    batch_size = int(plan["batch_size"])
    losses = []
    for epoch in range(int(plan["epochs"])):
        local_order = balanced_epoch_indices(train_entries, len(train_entries), seed + epoch)
        order = train_indices[local_order]
        total = 0.0
        model.train()
        for start in range(0, len(order), batch_size):
            selected = order[start:start + batch_size]
            x = torch.from_numpy(arrays[selected]).to(device=device, dtype=torch.float32).div_(255.0)
            y = torch.tensor([
                1.0 if entries[index]["expected_decision"] == "ABSTAIN" else 0.0 for index in selected
            ], device=device).reshape(-1, 1)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(x), y)
            loss.backward()
            optimizer.step()
            total += float(loss.detach().cpu()) * len(selected)
        losses.append(total / len(order))

    model.eval()
    probability_chunks = []
    with torch.no_grad():
        for start in range(0, len(development_indices), batch_size):
            selected = development_indices[start:start + batch_size]
            x = torch.from_numpy(arrays[selected]).to(device=device, dtype=torch.float32).div_(255.0)
            probability_chunks.append(torch.sigmoid(model(x)).reshape(-1).cpu().numpy())
    probabilities = np.concatenate(probability_chunks).astype(np.float32)
    development = [entries[index] for index in development_indices]
    labels = np.asarray([1 if row["expected_decision"] == "ABSTAIN" else 0 for row in development], dtype=np.int8)
    measurements = score_thresholds(
        labels, probabilities, [row["view_id"] for row in development],
        [row["appearance_id"] for row in development],
        [float(value) for value in plan["threshold_candidates"]], fixture["development_gate"],
    )
    passing = [row for row in measurements if row["gate_met"]]
    selected = passing[0] if passing else None
    output_dir.mkdir(parents=True)
    model_path = output_dir / "model.bin"
    metadata = {
        "algorithm": plan["algorithm"], "fixture_bundle_sha256": fixture["bundle_sha256"],
        "dataset_sha256": manifest["dataset_sha256"], "input_channels": ["RGB"],
        "input_size_px": [96, 96], "convolution_channels": channels,
    }
    _write_model(model_path, model.state_dict(), metadata)
    core = {
        "schema": RESULT_SCHEMA,
        "scope": "SYNTHETIC_DEVELOPMENT_ONLY_NO_QUALIFICATION",
        "status": "PASSED_DEVELOPMENT_GATE" if selected else "FAILED_DEVELOPMENT_GATE",
        "fixture_file_sha256": sha256_bytes(fixture_path.read_bytes()),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "contract_file_sha256": sha256_bytes(contract_path.read_bytes()),
        "contract_sha256": manifest["contract_sha256"],
        "dataset_manifest_file_sha256": sha256_bytes((dataset_dir / "manifest.json").read_bytes()),
        "dataset_sha256": manifest["dataset_sha256"], "dataset_inventory_sha256": manifest["inventory_sha256"],
        "model_sha256": sha256_bytes(model_path.read_bytes()), "model_bytes": model_path.stat().st_size,
        "training_plan": plan, "training_device": str(device),
        "training_count": len(train_indices), "development_count": len(development_indices), "evaluation_count": 0,
        "epoch_losses": losses, "selected_threshold": None if selected is None else selected["threshold"],
        "selected_measurement": selected, "threshold_measurements": measurements,
        "development_probability_sha256": sha256_bytes(probabilities.astype("<f4").tobytes()),
        "development_identity_sha256": sha256_bytes(canonical([row["observation_id"] for row in development])),
        "evaluation_opened": False, "hardware_writes": 0, "physical_movements": 0, "physical_authority": False,
        "limitations": [
            "Training and development derive from one simplified synthetic base scene",
            "Pixel-domain transformations and procedural obstructions are not physical evidence",
            "A development pass cannot qualify the camera, deployment, or physical execution",
            "No evaluation source was present or opened",
        ],
    }
    result = {**core, "result_sha256": sha256_bytes(canonical(core))}
    (output_dir / "scorecard.json").write_bytes(canonical(result) + b"\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = train(args.fixture, args.contract, args.dataset_dir, args.output_dir)
    print(json.dumps({
        "schema": result["schema"], "status": result["status"],
        "result_sha256": result["result_sha256"], "selected_threshold": result["selected_threshold"],
        "model_sha256": result["model_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
