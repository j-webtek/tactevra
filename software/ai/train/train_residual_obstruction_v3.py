"""Train and development-score the frozen residual-obstruction v3 campaign."""

from __future__ import annotations

import argparse
from collections import defaultdict
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
ROOT = AI_ROOT.parents[1]
sys.path.insert(0, str(AI_ROOT / "eval"))

from admit_residual_obstruction_v3_shards import (  # noqa: E402
    FIXTURE_SCHEMA,
    MANIFEST_SCHEMA,
    canonical,
    load_bound,
    sha256_bytes,
    verify_shards,
)


ADMISSION_SCHEMA = "tactevra.ai_residual_obstruction_v3_admission.v1"
LINEAGE_SCHEMA = "tactevra.ai_residual_obstruction_v3_renderer_lineage.v1"
RESULT_SCHEMA = "tactevra.ai_residual_obstruction_development.v3"
MODEL_MAGIC = b"TACTEVRA_RESIDUAL_CNN_V3\0"


def _load_campaign(
    workspace: Path,
    fixture_path: Path,
    admission_path: Path,
    lineage_path: Path,
    shard_dirs: list[Path],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    fixture, _ = load_bound(fixture_path.resolve(strict=True), FIXTURE_SCHEMA, "bundle_sha256")
    admission, admission_bytes = load_bound(
        admission_path.resolve(strict=True), ADMISSION_SCHEMA, "receipt_sha256"
    )
    lineage, _ = load_bound(
        lineage_path.resolve(strict=True), LINEAGE_SCHEMA, "lineage_sha256"
    )
    if admission["status"] != "PASS" or admission["campaign_admitted"] is not True:
        raise ValueError("training requires a complete admitted campaign")
    if admission["training_started"] is not False or admission["evaluation_observation_count"] != 0:
        raise ValueError("admission claims training or evaluation access")
    if lineage["admission_receipt_sha256"] != admission["receipt_sha256"]:
        raise ValueError("lineage admission receipt mismatch")
    if lineage["admission_file_sha256"] != sha256_bytes(admission_bytes):
        raise ValueError("lineage admission file mismatch")
    verified = verify_shards(workspace, fixture_path, shard_dirs)
    if canonical(verified) != canonical(admission):
        raise ValueError("external shards do not reproduce retained admission")

    expected_lineage = {
        (item["manifest_file_sha256"], item["dataset_sha256"]): item
        for item in lineage["shards"]
    }
    if len(expected_lineage) != lineage["shard_count"]:
        raise ValueError("duplicate lineage shard binding")
    entries: list[dict[str, Any]] = []
    consumed: set[tuple[str, str]] = set()
    for raw_dir in shard_dirs:
        shard = raw_dir.resolve(strict=True)
        manifest, payload = load_bound(shard / "manifest.json", MANIFEST_SCHEMA, "dataset_sha256")
        binding = (sha256_bytes(payload), manifest["dataset_sha256"])
        if binding not in expected_lineage or binding in consumed:
            raise ValueError("shard is absent or duplicated in renderer lineage")
        consumed.add(binding)
        for row in manifest["observations"]:
            entries.append({**row, "image_path": shard / row["rgb_path"]})
    if consumed != set(expected_lineage):
        raise ValueError("renderer lineage was not fully consumed")
    entries.sort(key=lambda row: row["observation_id"])
    if len(entries) != 43200:
        raise ValueError("campaign entry count mismatch")
    return fixture, admission, entries


def paired_groups(
    entries: list[dict[str, Any]],
    split: str,
    appearance_ids: list[str],
) -> list[list[int]]:
    groups: dict[tuple[str, str, str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(entries):
        if row["split"] == split:
            key = (row["scene_id"], row["device"], row["target_id"], row["variant_id"])
            groups[key].append(index)
    ordered: list[list[int]] = []
    for key in sorted(groups):
        indices = sorted(groups[key], key=lambda index: appearance_ids.index(entries[index]["appearance_id"]))
        if [entries[index]["appearance_id"] for index in indices] != appearance_ids:
            raise ValueError(f"appearance pairing mismatch: {key}")
        ordered.append(indices)
    return ordered


def group_epoch_order(groups: list[list[int]], seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(groups))
    return np.asarray([index for group_index in order for index in groups[group_index]], dtype=np.int64)


def _rates(
    labels: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
) -> tuple[int, int, int, int]:
    predicted = probabilities >= threshold
    obstruction = labels == 1
    visible = ~obstruction
    return (
        int(np.sum(obstruction & ~predicted)),
        int(np.sum(obstruction)),
        int(np.sum(visible & predicted)),
        int(np.sum(visible)),
    )


def _rate_rows(
    labels: np.ndarray,
    probabilities: np.ndarray,
    identities: list[str],
    threshold: float,
    identity_name: str,
) -> list[dict[str, Any]]:
    output = []
    for identity in sorted(set(identities)):
        selected = np.asarray([i for i, value in enumerate(identities) if value == identity])
        misses, obstruction_count, false_stops, visible_count = _rates(
            labels[selected], probabilities[selected], threshold
        )
        output.append({
            identity_name: identity,
            "missed_obstructions": misses,
            "obstruction_count": obstruction_count,
            "missed_obstruction_rate": 0.0 if obstruction_count == 0 else misses / obstruction_count,
            "visible_false_stops": false_stops,
            "visible_count": visible_count,
            "visible_false_stop_rate": 0.0 if visible_count == 0 else false_stops / visible_count,
        })
    return output


def target_separation(
    labels: np.ndarray,
    probabilities: np.ndarray,
    target_ids: list[str],
) -> list[dict[str, Any]]:
    output = []
    for target_id in sorted(set(target_ids)):
        selected = np.asarray([i for i, value in enumerate(target_ids) if value == target_id])
        target_labels = labels[selected]
        target_probabilities = probabilities[selected]
        visible = target_probabilities[target_labels == 0]
        obstruction = target_probabilities[target_labels == 1]
        margin = float(np.min(obstruction) - np.max(visible))
        output.append({
            "target_id": target_id,
            "visible_count": int(len(visible)),
            "obstruction_count": int(len(obstruction)),
            "maximum_visible_probability": float(np.max(visible)),
            "minimum_obstruction_probability": float(np.min(obstruction)),
            "separation_margin": margin,
            "locally_separable": margin > 0.0,
        })
    return output


def score_thresholds(
    labels: np.ndarray,
    probabilities: np.ndarray,
    scenes: list[str],
    appearances: list[str],
    families: list[str],
    target_ids: list[str],
    candidates: list[float],
    gate: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    unique_scenes = sorted(set(scenes))
    scene_groups = [
        np.asarray([i for i, value in enumerate(scenes) if value == identity])
        for identity in unique_scenes
    ]
    rng = np.random.default_rng(int(gate["base_scene_cluster_bootstrap_seed"]))
    samples = rng.integers(
        0,
        len(scene_groups),
        size=(int(gate["base_scene_cluster_bootstrap_resamples"]), len(scene_groups)),
    )
    confidence = float(gate["confidence_level"])
    separations = target_separation(labels, probabilities, target_ids)
    minimum_margin = min(row["separation_margin"] for row in separations)
    target_gate = all(row["locally_separable"] for row in separations) and minimum_margin > float(
        gate["minimum_target_local_separation_margin"]
    )
    results = []
    for threshold in candidates:
        misses, obstruction_count, false_stops, visible_count = _rates(labels, probabilities, threshold)
        grouped = np.asarray(
            [_rates(labels[index], probabilities[index], threshold) for index in scene_groups],
            dtype=np.int64,
        )
        selected = grouped[samples].sum(axis=1)
        miss_upper = float(np.quantile(selected[:, 0] / selected[:, 1], confidence, method="higher"))
        false_upper = float(np.quantile(selected[:, 2] / selected[:, 3], confidence, method="higher"))
        appearance_metrics = _rate_rows(
            labels, probabilities, appearances, threshold, "appearance_id"
        )
        family_metrics = _rate_rows(labels, probabilities, families, threshold, "family")
        maximum_appearance_miss = max(row["missed_obstruction_rate"] for row in appearance_metrics)
        maximum_appearance_false = max(row["visible_false_stop_rate"] for row in appearance_metrics)
        maximum_family_miss = max(
            row["missed_obstruction_rate"] for row in family_metrics if row["obstruction_count"]
        )
        maximum_family_false = max(
            row["visible_false_stop_rate"] for row in family_metrics if row["visible_count"]
        )
        miss_rate = misses / obstruction_count
        false_rate = false_stops / visible_count
        miss_limit = float(gate["missed_obstruction_rate_upper"])
        false_limit = float(gate["visible_false_stop_rate_upper"])
        point_cluster_gate = all((
            miss_rate <= miss_limit,
            miss_upper <= miss_limit,
            false_rate <= false_limit,
            false_upper <= false_limit,
        ))
        appearance_gate = all((
            maximum_appearance_miss <= miss_limit,
            maximum_appearance_false <= false_limit,
        ))
        family_gate = all((
            maximum_family_miss <= miss_limit,
            maximum_family_false <= false_limit,
        ))
        results.append({
            "threshold": float(threshold),
            "missed_obstructions": misses,
            "obstruction_count": obstruction_count,
            "missed_obstruction_rate": miss_rate,
            "missed_obstruction_scene_cluster_upper": miss_upper,
            "visible_false_stops": false_stops,
            "visible_count": visible_count,
            "visible_false_stop_rate": false_rate,
            "visible_false_stop_scene_cluster_upper": false_upper,
            "maximum_appearance_missed_obstruction_rate": maximum_appearance_miss,
            "maximum_appearance_visible_false_stop_rate": maximum_appearance_false,
            "maximum_family_missed_obstruction_rate": maximum_family_miss,
            "maximum_family_visible_false_stop_rate": maximum_family_false,
            "minimum_target_separation_margin": minimum_margin,
            "point_and_cluster_gate_met": point_cluster_gate,
            "worst_appearance_gate_met": appearance_gate,
            "worst_family_gate_met": family_gate,
            "target_separation_gate_met": target_gate,
            "appearance_metrics": appearance_metrics,
            "family_metrics": family_metrics,
            "gate_met": point_cluster_gate and appearance_gate and family_gate and target_gate,
        })
    return results, separations


def _load_arrays(entries: list[dict[str, Any]]) -> np.ndarray:
    arrays = np.empty((len(entries), 3, 96, 96), dtype=np.uint8)
    for index, entry in enumerate(entries):
        with Image.open(entry["image_path"]) as image:
            value = np.asarray(image.convert("RGB"), dtype=np.uint8)
        if value.shape != (96, 96, 3):
            raise ValueError(f"unexpected crop shape: {entry['observation_id']}")
        arrays[index] = value.transpose(2, 0, 1)
    return arrays


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


def train(
    workspace: Path,
    fixture_path: Path,
    admission_path: Path,
    lineage_path: Path,
    shard_dirs: list[Path],
    output_dir: Path,
) -> dict[str, Any]:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    fixture, admission, entries = _load_campaign(
        workspace, fixture_path, admission_path, lineage_path, shard_dirs
    )
    if output_dir.exists():
        raise FileExistsError(f"refusing existing output directory: {output_dir}")
    appearance_ids = [item["appearance_id"] for item in fixture["appearances"]]
    train_groups = paired_groups(entries, "training", appearance_ids)
    development_indices = np.asarray(
        [index for index, row in enumerate(entries) if row["split"] == "development"],
        dtype=np.int64,
    )
    if len(train_groups) != 7200 or len(development_indices) != 14400:
        raise ValueError("split or appearance-group count mismatch")
    arrays = _load_arrays(entries)

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
        torch.nn.Conv2d(3, channels[0], 3, padding=1),
        torch.nn.GroupNorm(6, channels[0]),
        torch.nn.ReLU(),
        torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[0], channels[1], 3, padding=1),
        torch.nn.GroupNorm(8, channels[1]),
        torch.nn.ReLU(),
        torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[1], channels[2], 3, padding=1),
        torch.nn.GroupNorm(8, channels[2]),
        torch.nn.ReLU(),
        torch.nn.AdaptiveAvgPool2d((1, 1)),
        torch.nn.Flatten(),
        torch.nn.Linear(channels[2], 1),
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(plan["learning_rate"]),
        weight_decay=float(plan["weight_decay"]),
    )
    classification_loss = torch.nn.BCEWithLogitsLoss()
    consistency_loss = torch.nn.SmoothL1Loss()
    consistency_weight = float(plan["losses"]["appearance_consistency_weight"])
    batch_size = int(plan["batch_size"])
    appearance_count = len(appearance_ids)
    if batch_size % appearance_count:
        raise ValueError("batch size must preserve complete appearance groups")
    epoch_losses = []
    for epoch in range(int(plan["epochs"])):
        order = group_epoch_order(train_groups, seed + epoch)
        model.train()
        classification_total = 0.0
        consistency_total = 0.0
        combined_total = 0.0
        for start in range(0, len(order), batch_size):
            selected = order[start:start + batch_size]
            x = torch.from_numpy(arrays[selected]).to(device=device, dtype=torch.float32).div_(255.0)
            y = torch.tensor(
                [1.0 if entries[index]["expected_decision"] == "ABSTAIN" else 0.0 for index in selected],
                device=device,
            ).reshape(-1, 1)
            optimizer.zero_grad(set_to_none=True)
            logits = model(x)
            classification = classification_loss(logits, y)
            grouped_logits = logits.reshape(-1, appearance_count)
            consistency = consistency_loss(
                grouped_logits,
                grouped_logits.mean(dim=1, keepdim=True).expand_as(grouped_logits),
            )
            loss = classification + consistency_weight * consistency
            loss.backward()
            optimizer.step()
            count = len(selected)
            classification_total += float(classification.detach().cpu()) * count
            consistency_total += float(consistency.detach().cpu()) * count
            combined_total += float(loss.detach().cpu()) * count
        epoch_losses.append({
            "epoch": epoch + 1,
            "classification": classification_total / len(order),
            "appearance_consistency": consistency_total / len(order),
            "combined": combined_total / len(order),
        })

    model.eval()
    probability_chunks = []
    with torch.no_grad():
        for start in range(0, len(development_indices), batch_size):
            selected = development_indices[start:start + batch_size]
            x = torch.from_numpy(arrays[selected]).to(device=device, dtype=torch.float32).div_(255.0)
            probability_chunks.append(torch.sigmoid(model(x)).reshape(-1).cpu().numpy())
    probabilities = np.concatenate(probability_chunks).astype(np.float32)
    development = [entries[index] for index in development_indices]
    labels = np.asarray(
        [1 if row["expected_decision"] == "ABSTAIN" else 0 for row in development],
        dtype=np.int8,
    )
    family_by_variant = {item["variant_id"]: item["family"] for item in fixture["variants"]}
    measurements, separations = score_thresholds(
        labels,
        probabilities,
        [row["scene_id"] for row in development],
        [row["appearance_id"] for row in development],
        [family_by_variant[row["variant_id"]] for row in development],
        [f"{row['device']}:{row['target_id']}" for row in development],
        [float(value) for value in plan["threshold_candidates"]],
        fixture["development_gate"],
    )
    passing = [row for row in measurements if row["gate_met"]]
    selected_measurement = passing[0] if passing else None
    output_dir.mkdir(parents=True)
    model_path = output_dir / "model.bin"
    metadata = {
        "algorithm": plan["algorithm"],
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "admission_receipt_sha256": admission["receipt_sha256"],
        "input_channels": ["RGB"],
        "input_size_px": [96, 96],
        "convolution_channels": channels,
        "normalization": plan["normalization"],
    }
    _write_model(model_path, model.state_dict(), metadata)
    core = {
        "schema": RESULT_SCHEMA,
        "scope": "SYNTHETIC_ISAAC_DEVELOPMENT_ONLY_NO_QUALIFICATION",
        "status": "PASSED_DEVELOPMENT_GATE" if selected_measurement else "FAILED_DEVELOPMENT_GATE",
        "fixture_file_sha256": sha256_bytes(fixture_path.read_bytes()),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "admission_file_sha256": sha256_bytes(admission_path.read_bytes()),
        "admission_receipt_sha256": admission["receipt_sha256"],
        "lineage_file_sha256": sha256_bytes(lineage_path.read_bytes()),
        "model_sha256": sha256_bytes(model_path.read_bytes()),
        "model_bytes": model_path.stat().st_size,
        "training_plan": plan,
        "training_device": str(device),
        "training_count": 28800,
        "development_count": 14400,
        "evaluation_count": 0,
        "epoch_losses": epoch_losses,
        "selected_threshold": None if selected_measurement is None else selected_measurement["threshold"],
        "selected_measurement": selected_measurement,
        "threshold_measurements": measurements,
        "target_separation": separations,
        "development_probability_sha256": sha256_bytes(probabilities.astype("<f4").tobytes()),
        "development_identity_sha256": sha256_bytes(
            canonical([row["observation_id"] for row in development])
        ),
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "Training and development use synthetic Isaac observations with unmeasured camera and materials",
            "A development pass cannot qualify the physical camera, deployment, or execution",
            "The admitted external image corpus must remain retained with its exact manifests",
            "No evaluation source was present or opened",
        ],
    }
    result = {**core, "result_sha256": sha256_bytes(canonical(core))}
    (output_dir / "scorecard.json").write_bytes(canonical(result) + b"\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--lineage", type=Path, required=True)
    parser.add_argument("--shard", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = train(
        args.workspace,
        args.fixture,
        args.admission,
        args.lineage,
        args.shard,
        args.output_dir,
    )
    print(json.dumps({
        "schema": result["schema"],
        "status": result["status"],
        "result_sha256": result["result_sha256"],
        "selected_threshold": result["selected_threshold"],
        "model_sha256": result["model_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
