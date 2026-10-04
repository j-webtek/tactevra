"""Train and score the selected v4.2 CNN after the frozen baseline selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT / "eval"))

from admit_residual_obstruction_v4_1_smoke import rank_auc  # noqa: E402
from admit_residual_obstruction_v4_2_shards import canonical, digest  # noqa: E402
from prepare_residual_obstruction_v4_2_gates import (  # noqa: E402
    PREPARATION_SCHEMA,
    _load_report,
    load_complete_campaign,
)
from run_residual_obstruction_v4_2_memorization import (  # noqa: E402
    SCHEMA as MEMORIZATION_SCHEMA,
    _read_image,
    normalize_pair,
    spatial_model,
)


BASELINE_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_training_free_baseline.v1"
REPORT_SCHEMA = "tactevra.ai_residual_obstruction_v4_2_cnn_development.v1"


def linear_q05(values: list[float]) -> float:
    if not values:
        raise ValueError("q05 requires values")
    return float(np.quantile(np.asarray(values, dtype=np.float64), 0.05, method="linear"))


def score_probabilities(
    rows: list[dict[str, Any]], probabilities: np.ndarray
) -> dict[str, Any]:
    if len(rows) != len(probabilities):
        raise ValueError("probability count differs from row count")
    labels = [row["expected_decision"] == "ABSTAIN" for row in rows]
    targets = sorted({f"{row['device']}:{row['target_id']}" for row in rows})
    per_target: dict[str, float] = {}
    for target in targets:
        indices = [
            index
            for index, row in enumerate(rows)
            if f"{row['device']}:{row['target_id']}" == target
        ]
        per_target[target] = rank_auc(
            [labels[index] for index in indices],
            [float(probabilities[index]) for index in indices],
        )
    return {
        "pooled_auc": rank_auc(labels, [float(value) for value in probabilities]),
        "per_target_auc": per_target,
        "q05_per_target_auc": linear_q05(list(per_target.values())),
        "minimum_per_target_auc": min(per_target.values()),
    }


def uplift_result(
    baseline: dict[str, Any], cnn: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    pooled = float(cnn["pooled_auc"]) - float(baseline["pooled_auc"])
    q05 = float(cnn["q05_per_target_auc"]) - float(baseline["q05_per_target_auc"])
    pooled_pass = pooled >= float(gate["minimum_pooled_auc_improvement"])
    q05_pass = q05 >= float(gate["minimum_q05_per_target_auc_improvement"])
    return {
        "pooled_auc_improvement": pooled,
        "q05_per_target_auc_improvement": q05,
        "minimum_pooled_auc_improvement": float(
            gate["minimum_pooled_auc_improvement"]
        ),
        "minimum_q05_per_target_auc_improvement": float(
            gate["minimum_q05_per_target_auc_improvement"]
        ),
        "pooled_gate_met": pooled_pass,
        "q05_gate_met": q05_pass,
        "gate_met": pooled_pass and q05_pass,
    }


def load_arrays(
    rows: list[dict[str, Any]], normalization_id: str, label: str
) -> tuple[np.ndarray, np.ndarray]:
    arrays = np.empty((len(rows), 9, 96, 96), dtype=np.float32)
    labels = np.empty(len(rows), dtype=np.float32)
    reference_cache: dict[tuple[str, str], np.ndarray] = {}
    for index, row in enumerate(rows):
        root = Path(row["shard_root"]).resolve(strict=True)
        key = (str(root), row["reference_rgb_path"])
        reference = reference_cache.get(key)
        if reference is None:
            reference = _read_image(
                root,
                row["reference_rgb_path"],
                row["reference_rgb_sha256"],
                row["reference_rgb_bytes"],
            )
            reference_cache[key] = reference
        observation = _read_image(
            root, row["rgb_path"], row["rgb_sha256"], row["rgb_bytes"]
        )
        arrays[index] = normalize_pair(reference, observation, normalization_id)
        labels[index] = 1.0 if row["expected_decision"] == "ABSTAIN" else 0.0
        if (index + 1) % 5000 == 0 or index + 1 == len(rows):
            print(f"loaded {label}: {index + 1}/{len(rows)}", flush=True)
    return arrays, labels


def train_model(
    training_arrays: np.ndarray,
    training_labels: np.ndarray,
    plan: dict[str, Any],
    seed: int,
) -> tuple[Any, dict[str, Any]]:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = spatial_model(torch).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(plan["learning_rate"]),
        weight_decay=float(plan["weight_decay"]),
    )
    loss_fn = torch.nn.BCEWithLogitsLoss()
    rng = np.random.default_rng(seed)
    batch_size = int(plan["batch_size"])
    losses: list[float] = []
    model.train()
    for epoch in range(1, int(plan["epochs"]) + 1):
        order = rng.permutation(len(training_labels))
        total_loss = 0.0
        total_count = 0
        for start in range(0, len(order), batch_size):
            batch = order[start : start + batch_size]
            x = torch.from_numpy(training_arrays[batch]).to(device)
            y = torch.from_numpy(training_labels[batch]).to(device).reshape(-1, 1)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(x), y)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach().cpu()) * len(batch)
            total_count += len(batch)
        epoch_loss = total_loss / total_count
        losses.append(epoch_loss)
        print(f"epoch {epoch}/{plan['epochs']}: loss={epoch_loss:.9f}", flush=True)
    return model, {
        "architecture": "SPATIAL_REFERENCE_DIFFERENCE_CNN_6X6",
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "device": str(device),
        "epochs_run": int(plan["epochs"]),
        "batch_size": batch_size,
        "learning_rate": float(plan["learning_rate"]),
        "weight_decay": float(plan["weight_decay"]),
        "epoch_losses": losses,
        "final_training_loss": losses[-1],
        "augmentation_enabled": False,
        "dropout_enabled": False,
    }


def predict(model: Any, arrays: np.ndarray, batch_size: int) -> np.ndarray:
    import torch

    device = next(model.parameters()).device
    model.eval()
    output = np.empty(len(arrays), dtype=np.float32)
    with torch.no_grad():
        for start in range(0, len(arrays), batch_size):
            end = min(start + batch_size, len(arrays))
            logits = model(torch.from_numpy(arrays[start:end]).to(device))
            output[start:end] = torch.sigmoid(logits).reshape(-1).cpu().numpy()
    return output


def run(
    fixture_path: Path,
    admission_path: Path,
    preparation_path: Path,
    memorization_path: Path,
    baseline_path: Path,
    shard_dirs: list[Path],
    checkpoint_path: Path,
) -> dict[str, Any]:
    fixture, admission, entries = load_complete_campaign(
        fixture_path, admission_path, shard_dirs
    )
    preparation, _ = _load_report(preparation_path, PREPARATION_SCHEMA)
    memorization, _ = _load_report(memorization_path, MEMORIZATION_SCHEMA)
    baseline, _ = _load_report(baseline_path, BASELINE_SCHEMA)
    if preparation["admission_report_sha256"] != admission["report_sha256"]:
        raise ValueError("preparation admission binding mismatch")
    if memorization["preparation_report_sha256"] != preparation["report_sha256"]:
        raise ValueError("memorization preparation binding mismatch")
    if memorization.get("both_gates_met") is not True:
        raise ValueError("both memorization gates must pass before full training")
    if baseline["memorization_report_sha256"] != memorization["report_sha256"]:
        raise ValueError("baseline memorization binding mismatch")
    if baseline.get("selection_made_once") is not True:
        raise ValueError("baseline did not freeze normalization selection")
    if baseline.get("evaluation_opened") is not False:
        raise ValueError("baseline claims evaluation access")
    normalization_id = str(baseline["selected_normalization"])
    if normalization_id not in memorization["runs"]:
        raise ValueError("selected normalization was not memorization tested")
    training = [row for row in entries if row["split"] == "training"]
    development = [row for row in entries if row["split"] == "development"]
    if len(training) != 43_200 or len(development) != 28_800:
        raise ValueError("frozen train/development counts differ")
    training_arrays, training_labels = load_arrays(training, normalization_id, "training")
    development_arrays, _ = load_arrays(development, normalization_id, "development")
    model, training_metrics = train_model(
        training_arrays,
        training_labels,
        fixture["training_plan"],
        int(fixture["training_plan"]["seed"]),
    )
    probabilities = predict(
        model, development_arrays, int(fixture["training_plan"]["batch_size"])
    )
    cnn_metrics = score_probabilities(development, probabilities)
    baseline_metrics = baseline["results"][normalization_id]
    gate = uplift_result(
        baseline_metrics,
        cnn_metrics,
        fixture["training_plan"]["cnn_baseline_uplift_gate"],
    )
    import torch

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.cpu().state_dict(),
            "architecture": training_metrics["architecture"],
            "input_channels": 9,
            "input_size_px": [96, 96],
            "normalization_id": normalization_id,
            "fixture_bundle_sha256": fixture["bundle_sha256"],
            "admission_report_sha256": admission["report_sha256"],
            "baseline_report_sha256": baseline["report_sha256"],
        },
        checkpoint_path,
    )
    checkpoint_bytes = checkpoint_path.read_bytes()
    core = {
        "schema": REPORT_SCHEMA,
        "scope": "SYNTHETIC_DEVELOPMENT_CNN_NO_PHYSICAL_QUALIFICATION",
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "admission_report_sha256": admission["report_sha256"],
        "preparation_report_sha256": preparation["report_sha256"],
        "memorization_report_sha256": memorization["report_sha256"],
        "baseline_report_sha256": baseline["report_sha256"],
        "selected_normalization": normalization_id,
        "unselected_normalization_status": "UNTESTED_FULL_CNN_NOT_REJECTED",
        "training_observation_count": len(training),
        "development_observation_count": len(development),
        "training": training_metrics,
        "baseline_metrics": baseline_metrics,
        "cnn_metrics": cnn_metrics,
        "uplift_gate": gate,
        "checkpoint_path": str(checkpoint_path.resolve()),
        "checkpoint_bytes": len(checkpoint_bytes),
        "checkpoint_sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
        "development_pass_in_simulation": gate["gate_met"],
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "A passing result establishes only synthetic development uplift",
            "Real-camera clear references and cable/hand captures remain required",
            "The unselected normalization was not full-trained and is not ruled out",
            "Evaluation remains absent and unopened",
        ],
    }
    return {**core, "report_sha256": digest(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--memorization", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--shard", type=Path, action="append", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        args.fixture,
        args.admission,
        args.preparation,
        args.memorization,
        args.baseline,
        args.shard,
        args.checkpoint,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "report_sha256": result["report_sha256"],
                "selected_normalization": result["selected_normalization"],
                "cnn_metrics": result["cnn_metrics"],
                "uplift_gate": result["uplift_gate"],
                "checkpoint_sha256": result["checkpoint_sha256"],
            },
            indent=2,
        )
    )
    return 0 if result["development_pass_in_simulation"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
