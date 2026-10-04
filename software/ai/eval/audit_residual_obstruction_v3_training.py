"""Run training-only causal audits for the rejected residual-v3 model."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


AI_ROOT = Path(__file__).resolve().parents[1]
ROOT = AI_ROOT.parents[1]
sys.path.insert(0, str(AI_ROOT))
sys.path.insert(0, str(AI_ROOT / "eval"))

from eval.admit_residual_obstruction_v3_shards import (  # noqa: E402
    FIXTURE_SCHEMA,
    MANIFEST_SCHEMA,
    canonical,
    load_bound,
    sha256_bytes,
)
from eval.diagnose_residual_obstruction_v3 import (  # noqa: E402
    _build_model,
    load_model,
    pairwise_auc,
)
from train.train_residual_obstruction_v3 import (  # noqa: E402
    ADMISSION_SCHEMA,
    LINEAGE_SCHEMA,
    RESULT_SCHEMA,
)


AUDIT_SCHEMA = "tactevra.ai_residual_obstruction_v3_training_audit.v1"


def load_training_entries(
    workspace: Path,
    fixture_path: Path,
    admission_path: Path,
    lineage_path: Path,
    shard_dirs: list[Path],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    fixture, _ = load_bound(fixture_path.resolve(strict=True), FIXTURE_SCHEMA, "bundle_sha256")
    admission, admission_bytes = load_bound(
        admission_path.resolve(strict=True), ADMISSION_SCHEMA, "receipt_sha256"
    )
    lineage, _ = load_bound(
        lineage_path.resolve(strict=True), LINEAGE_SCHEMA, "lineage_sha256"
    )
    if admission["campaign_admitted"] is not True or admission["status"] != "PASS":
        raise ValueError("training audit requires complete retained admission")
    if lineage["admission_receipt_sha256"] != admission["receipt_sha256"]:
        raise ValueError("lineage admission receipt mismatch")
    if lineage["admission_file_sha256"] != sha256_bytes(admission_bytes):
        raise ValueError("lineage admission file mismatch")
    expected = {
        (item["manifest_file_sha256"], item["dataset_sha256"]): item
        for item in lineage["shards"]
    }
    entries = []
    consumed = set()
    training_hashes = set()
    split_scenes: dict[str, set[str]] = {"training": set(), "development": set()}
    split_appearances: dict[str, set[str]] = {"training": set(), "development": set()}
    split_observations: dict[str, set[str]] = {"training": set(), "development": set()}
    for raw_dir in shard_dirs:
        shard = raw_dir.resolve(strict=True)
        manifest, payload = load_bound(shard / "manifest.json", MANIFEST_SCHEMA, "dataset_sha256")
        binding = (sha256_bytes(payload), manifest["dataset_sha256"])
        if binding not in expected or binding in consumed:
            raise ValueError("shard is absent or duplicated in renderer lineage")
        consumed.add(binding)
        for row in manifest["observations"]:
            split = row["split"]
            split_scenes[split].add(row["scene_id"])
            split_appearances[split].add(row["appearance_id"])
            split_observations[split].add(row["observation_id"])
            if split != "training":
                continue
            path = (shard / row["rgb_path"]).resolve(strict=True)
            payload_bytes = path.read_bytes()
            if len(payload_bytes) != row["rgb_bytes"] or sha256_bytes(payload_bytes) != row["rgb_sha256"]:
                raise ValueError(f"training image mismatch: {row['observation_id']}")
            if row["rgb_sha256"] in training_hashes:
                raise ValueError("duplicate training RGB bytes")
            training_hashes.add(row["rgb_sha256"])
            entries.append({**row, "image_path": path})
    if consumed != set(expected) or len(entries) != 28800 or len(training_hashes) != 28800:
        raise ValueError("training corpus or lineage coverage mismatch")
    entries.sort(key=lambda row: row["observation_id"])
    split_audit = {
        "training_scene_ids": sorted(split_scenes["training"]),
        "development_scene_ids": sorted(split_scenes["development"]),
        "scene_identity_overlap": sorted(split_scenes["training"] & split_scenes["development"]),
        "training_appearance_ids": sorted(split_appearances["training"]),
        "development_appearance_ids": sorted(split_appearances["development"]),
        "appearance_identity_overlap": sorted(
            split_appearances["training"] & split_appearances["development"]
        ),
        "observation_identity_overlap_count": len(
            split_observations["training"] & split_observations["development"]
        ),
        "split_unit": "BASE_SCENE",
        "development_pixels_opened": False,
        "evaluation_present": False,
        "evaluation_opened": False,
    }
    return fixture, admission, entries, split_audit


def geometry_catalog(workspace: Path) -> dict[str, list[float]]:
    sys.path.insert(0, str(workspace.resolve(strict=True) / "software" / "src"))
    from rocell.application.bootstrap import bootstrap_virtual_workcell

    context = bootstrap_virtual_workcell(workspace).context
    targets = [*context.targets.keyboard_targets.values(), *context.targets.phone_targets.values()]
    return {
        f"{target.device}:{target.target_id}": [
            target.center.x,
            target.center.y,
            target.center.z,
            target.half_extent_x_mm,
            target.half_extent_y_mm,
            1.0 if target.device == "phone" else 0.0,
        ]
        for target in targets
    }


def fit_identity_geometry_baseline(
    entries: list[dict[str, Any]],
    geometry: dict[str, list[float]],
) -> dict[str, Any]:
    target_ids = sorted(geometry)
    target_index = {target_id: index for index, target_id in enumerate(target_ids)}
    group_counts = Counter()
    positive_counts = Counter()
    for row in entries:
        target_id = f"{row['device']}:{row['target_id']}"
        group_counts[target_id] += 1
        positive_counts[target_id] += row["expected_decision"] == "ABSTAIN"
    geometry_array = np.asarray([geometry[target_id] for target_id in target_ids], dtype=np.float64)
    geometry_array = (geometry_array - geometry_array.mean(axis=0)) / np.where(
        geometry_array.std(axis=0) == 0.0, 1.0, geometry_array.std(axis=0)
    )
    x = np.concatenate(
        [
            np.ones((len(target_ids), 1), dtype=np.float64),
            np.eye(len(target_ids), dtype=np.float64),
            geometry_array,
        ],
        axis=1,
    )
    counts = np.asarray([group_counts[target_id] for target_id in target_ids], dtype=np.float64)
    positives = np.asarray([positive_counts[target_id] for target_id in target_ids], dtype=np.float64)
    coefficients = np.zeros(x.shape[1], dtype=np.float64)
    ridge = 1e-6
    iterations = 0
    for iterations in range(1, 51):
        logits = np.clip(x @ coefficients, -30.0, 30.0)
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        gradient = x.T @ (counts * probabilities - positives)
        regularizer = np.eye(x.shape[1]) * ridge
        regularizer[0, 0] = 0.0
        gradient += regularizer @ coefficients
        weights = counts * probabilities * (1.0 - probabilities)
        hessian = x.T @ (weights[:, None] * x) + regularizer
        step = np.linalg.solve(hessian, gradient)
        coefficients -= step
        if float(np.max(np.abs(step))) < 1e-12:
            break
    target_probabilities = 1.0 / (1.0 + np.exp(-np.clip(x @ coefficients, -30.0, 30.0)))
    labels = np.asarray(
        [1 if row["expected_decision"] == "ABSTAIN" else 0 for row in entries], dtype=np.int8
    )
    expanded = np.asarray(
        [target_probabilities[target_index[f"{row['device']}:{row['target_id']}"]] for row in entries],
        dtype=np.float64,
    )
    return {
        "model": "RIDGE_LOGISTIC_TARGET_ONE_HOT_PLUS_NORMALIZED_GEOMETRY",
        "feature_count": int(x.shape[1]),
        "ridge": ridge,
        "iterations": iterations,
        "training_count": len(entries),
        "positive_rate": float(np.mean(labels)),
        "minimum_target_positive_rate": float(np.min(positives / counts)),
        "maximum_target_positive_rate": float(np.max(positives / counts)),
        "minimum_probability": float(np.min(expanded)),
        "maximum_probability": float(np.max(expanded)),
        "pooled_training_auc": pairwise_auc(labels, expanded),
        "coefficient_sha256": sha256_bytes(coefficients.astype("<f8").tobytes()),
    }


def _load_arrays(entries: list[dict[str, Any]]) -> np.ndarray:
    arrays = np.empty((len(entries), 3, 96, 96), dtype=np.uint8)
    for index, row in enumerate(entries):
        with Image.open(row["image_path"]) as image:
            value = np.asarray(image.convert("RGB"), dtype=np.uint8)
        if value.shape != (96, 96, 3):
            raise ValueError(f"unexpected crop shape: {row['observation_id']}")
        arrays[index] = value.transpose(2, 0, 1)
    return arrays


def model_training_diagnostics(
    model: Any,
    entries: list[dict[str, Any]],
    batch_size: int,
) -> tuple[dict[str, Any], np.ndarray]:
    import torch

    arrays = _load_arrays(entries)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    chunks = []
    with torch.no_grad():
        for start in range(0, len(entries), batch_size):
            x = torch.from_numpy(arrays[start:start + batch_size]).to(
                device=device, dtype=torch.float32
            ).div_(255.0)
            chunks.append(torch.sigmoid(model(x)).reshape(-1).cpu().numpy())
    probabilities = np.concatenate(chunks).astype(np.float32)
    labels = np.asarray(
        [1 if row["expected_decision"] == "ABSTAIN" else 0 for row in entries], dtype=np.int8
    )
    target_ids = [f"{row['device']}:{row['target_id']}" for row in entries]
    diagnostics = []
    for target_id in sorted(set(target_ids)):
        selected = np.asarray([i for i, value in enumerate(target_ids) if value == target_id])
        local_labels = labels[selected]
        local_probabilities = probabilities[selected]
        visible = local_probabilities[local_labels == 0]
        obstruction = local_probabilities[local_labels == 1]
        diagnostics.append({
            "target_id": target_id,
            "training_count": int(len(selected)),
            "visible_count": int(len(visible)),
            "obstruction_count": int(len(obstruction)),
            "auc": pairwise_auc(local_labels, local_probabilities),
            "maximum_visible_probability": float(np.max(visible)),
            "minimum_obstruction_probability": float(np.min(obstruction)),
            "separation_margin": float(np.min(obstruction) - np.max(visible)),
            "maximum_visible_observation_id": entries[
                int(selected[np.flatnonzero(local_labels == 0)[int(np.argmax(visible))]])
            ]["observation_id"],
            "minimum_obstruction_observation_id": entries[
                int(selected[np.flatnonzero(local_labels == 1)[int(np.argmin(obstruction))]])
            ]["observation_id"],
        })
    family_diagnostics = []
    families = [row["variant_id"] for row in entries]
    for family in sorted(set(families)):
        selected = np.asarray([i for i, value in enumerate(families) if value == family])
        local_labels = labels[selected]
        local_probabilities = probabilities[selected]
        family_diagnostics.append({
            "variant_id": family,
            "training_count": int(len(selected)),
            "visible_count": int(np.sum(local_labels == 0)),
            "obstruction_count": int(np.sum(local_labels == 1)),
            "mean_probability": float(np.mean(local_probabilities)),
            "minimum_probability": float(np.min(local_probabilities)),
            "maximum_probability": float(np.max(local_probabilities)),
        })
    return {
        "pooled_training_auc": pairwise_auc(labels, probabilities),
        "locally_separable_target_count": sum(row["separation_margin"] > 0.0 for row in diagnostics),
        "target_count": len(diagnostics),
        "minimum_target_auc": min(row["auc"] for row in diagnostics),
        "median_target_auc": float(np.median([row["auc"] for row in diagnostics])),
        "maximum_target_auc": max(row["auc"] for row in diagnostics),
        "worst_target_margin": min(row["separation_margin"] for row in diagnostics),
        "best_target_margin": max(row["separation_margin"] for row in diagnostics),
        "target_diagnostics": diagnostics,
        "variant_diagnostics": family_diagnostics,
        "training_probability_sha256": sha256_bytes(probabilities.astype("<f4").tobytes()),
    }, arrays


def select_memorization_subset(entries: list[dict[str, Any]], count: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    selected = []
    per_label = count // 2
    for decision in ("VISIBLE", "ABSTAIN"):
        candidates = np.asarray(
            [i for i, row in enumerate(entries) if row["expected_decision"] == decision],
            dtype=np.int64,
        )
        selected.extend(rng.choice(candidates, size=per_label, replace=False).tolist())
    output = np.asarray(selected, dtype=np.int64)
    rng.shuffle(output)
    return output


def memorization_test(
    entries: list[dict[str, Any]],
    arrays: np.ndarray,
    channels: list[int],
    seed: int,
) -> dict[str, Any]:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    selected = select_memorization_subset(entries, 500, seed)
    subset = arrays[selected]
    labels = np.asarray(
        [1.0 if entries[index]["expected_decision"] == "ABSTAIN" else 0.0 for index in selected],
        dtype=np.float32,
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = _build_model(torch, channels).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.003, weight_decay=0.0)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    rng = np.random.default_rng(seed)
    epoch_losses = []
    final_accuracy = 0.0
    for epoch in range(1, 301):
        order = rng.permutation(len(selected))
        total = 0.0
        model.train()
        for start in range(0, len(order), 100):
            batch = order[start:start + 100]
            x = torch.from_numpy(subset[batch]).to(device=device, dtype=torch.float32).div_(255.0)
            y = torch.from_numpy(labels[batch]).to(device=device).reshape(-1, 1)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(x), y)
            loss.backward()
            optimizer.step()
            total += float(loss.detach().cpu()) * len(batch)
        mean_loss = total / len(selected)
        model.eval()
        with torch.no_grad():
            x = torch.from_numpy(subset).to(device=device, dtype=torch.float32).div_(255.0)
            probabilities = torch.sigmoid(model(x)).reshape(-1).cpu().numpy()
        final_accuracy = float(np.mean((probabilities >= 0.5) == labels))
        epoch_losses.append(mean_loss)
        if mean_loss <= 0.01 and final_accuracy >= 0.995:
            break
    target_counts = Counter(f"{entries[index]['device']}:{entries[index]['target_id']}" for index in selected)
    return {
        "subset_count": len(selected),
        "visible_count": int(np.sum(labels == 0)),
        "obstruction_count": int(np.sum(labels == 1)),
        "covered_target_count": len(target_counts),
        "minimum_examples_per_target": min(target_counts.values()),
        "maximum_examples_per_target": max(target_counts.values()),
        "seed": seed,
        "optimizer": "ADAMW",
        "learning_rate": 0.003,
        "weight_decay": 0.0,
        "maximum_epochs": 300,
        "epochs_run": len(epoch_losses),
        "first_loss": epoch_losses[0],
        "final_loss": epoch_losses[-1],
        "final_accuracy": final_accuracy,
        "near_zero_loss_met": epoch_losses[-1] <= 0.01,
        "memorization_accuracy_met": final_accuracy >= 0.995,
        "subset_identity_sha256": sha256_bytes(
            canonical([entries[index]["observation_id"] for index in selected])
        ),
    }


def build_visual_audit(
    entries: list[dict[str, Any]],
    output_path: Path,
) -> tuple[list[dict[str, Any]], str]:
    selected = [
        row
        for row in entries
        if row["device"] == "keyboard"
        and row["target_id"] == "G"
        and row["scene_id"] in {"residual_training_scene_01", "residual_training_scene_08"}
        and row["appearance_id"] == "neutral"
    ]
    selected.sort(key=lambda row: (row["scene_id"], row["variant_id"]))
    if len(selected) != 24:
        raise ValueError("unexpected target-G visual audit selection")
    tile_width, tile_height = 160, 126
    sheet = Image.new("RGB", (6 * tile_width, 4 * tile_height), "white")
    draw = ImageDraw.Draw(sheet)
    audit_rows = []
    for index, row in enumerate(selected):
        with Image.open(row["image_path"]) as image:
            crop = image.convert("RGB").resize((96, 96))
        x = (index % 6) * tile_width
        y = (index // 6) * tile_height
        sheet.paste(crop, (x, y))
        label = f"{row['scene_id'][-2:]} {row['variant_id'][:18]}"
        draw.text((x, y + 98), label, fill="black")
        draw.text((x, y + 111), f"{row['expected_decision']} ov={row['safe_overlap_fraction']:.2f}", fill="black")
        audit_rows.append({
            "observation_id": row["observation_id"],
            "scene_id": row["scene_id"],
            "variant_id": row["variant_id"],
            "expected_decision": row["expected_decision"],
            "safe_overlap_fraction": row["safe_overlap_fraction"],
            "rgb_sha256": row["rgb_sha256"],
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="JPEG", quality=95, subsampling=0)
    return audit_rows, sha256_bytes(output_path.read_bytes())


def audit(
    workspace: Path,
    fixture_path: Path,
    admission_path: Path,
    lineage_path: Path,
    shard_dirs: list[Path],
    scorecard_path: Path,
    model_path: Path,
    visual_audit_path: Path,
) -> dict[str, Any]:
    fixture, admission, entries, split_audit = load_training_entries(
        workspace, fixture_path, admission_path, lineage_path, shard_dirs
    )
    scorecard, scorecard_bytes = load_bound(scorecard_path, RESULT_SCHEMA, "result_sha256")
    if scorecard["status"] != "FAILED_DEVELOPMENT_GATE":
        raise ValueError("training audit requires rejected v3 scorecard")
    model, metadata = load_model(model_path, scorecard["model_sha256"])
    if metadata["admission_receipt_sha256"] != admission["receipt_sha256"]:
        raise ValueError("model admission mismatch")
    baseline = fit_identity_geometry_baseline(entries, geometry_catalog(workspace))
    model_diagnostics, arrays = model_training_diagnostics(
        model, entries, int(fixture["training_plan"]["batch_size"])
    )
    memorization = memorization_test(
        entries,
        arrays,
        [int(value) for value in fixture["training_plan"]["convolution_channels"]],
        int(fixture["training_plan"]["seed"]) + 1,
    )
    audit_rows, sheet_hash = build_visual_audit(entries, visual_audit_path)
    core = {
        "schema": AUDIT_SCHEMA,
        "scope": "TRAINING_ONLY_CAUSAL_AUDIT_NO_QUALIFICATION",
        "fixture_file_sha256": sha256_bytes(fixture_path.read_bytes()),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "admission_file_sha256": sha256_bytes(admission_path.read_bytes()),
        "admission_receipt_sha256": admission["receipt_sha256"],
        "lineage_file_sha256": sha256_bytes(lineage_path.read_bytes()),
        "scorecard_file_sha256": sha256_bytes(scorecard_bytes),
        "scorecard_result_sha256": scorecard["result_sha256"],
        "model_file_sha256": sha256_bytes(model_path.read_bytes()),
        "training_count": len(entries),
        "identity_geometry_baseline": baseline,
        "model_training_diagnostics": model_diagnostics,
        "memorization_test": memorization,
        "visual_audit": {
            "target_id": "keyboard:G",
            "row_count": len(audit_rows),
            "rows": audit_rows,
            "sheet_sha256": sheet_hash,
            "human_review_status": "PENDING",
        },
        "split_audit": split_audit,
        "checkpoint_changed": False,
        "threshold_changed": False,
        "development_pixels_opened": False,
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "This audit uses admitted synthetic training pixels and cannot evaluate a successor",
            "The visual contact sheet is a human-readable derivative and is not model input",
            "Identity and geometry features are nominal synthetic target metadata, not measured physical geometry",
            "Development metadata is used only to audit split identities; development pixels remain unopened",
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
    parser.add_argument("--scorecard", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--visual-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(
        args.workspace,
        args.fixture,
        args.admission,
        args.lineage,
        args.shard,
        args.scorecard,
        args.model,
        args.visual_audit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(report) + b"\n")
    print(json.dumps({
        "schema": report["schema"],
        "report_sha256": report["report_sha256"],
        "identity_geometry_auc": report["identity_geometry_baseline"]["pooled_training_auc"],
        "model_training_auc": report["model_training_diagnostics"]["pooled_training_auc"],
        "locally_separable_training_targets": report["model_training_diagnostics"][
            "locally_separable_target_count"
        ],
        "memorization_final_loss": report["memorization_test"]["final_loss"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
