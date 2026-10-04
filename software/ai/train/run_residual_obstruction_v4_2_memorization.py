"""Run both frozen v4.2 500-row memorization gates on training pairs only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from prepare_residual_obstruction_v4_2_gates import (
    ADMISSION_SCHEMA,
    NORMALIZATION_METRICS,
    PREPARATION_SCHEMA,
    _load_report,
)


SCHEMA = "tactevra.ai_residual_obstruction_v4_2_memorization.v1"


def _read_image(root: Path, relative: str, expected_hash: str, expected_bytes: int) -> np.ndarray:
    path = (root / relative).resolve(strict=True)
    if root not in path.parents:
        raise ValueError("image path escapes shard root")
    payload = path.read_bytes()
    if len(payload) != expected_bytes or hashlib.sha256(payload).hexdigest() != expected_hash:
        raise ValueError("memorization image binding mismatch")
    with Image.open(path) as image:
        value = np.asarray(image.convert("RGB"), dtype=np.uint8)
    if value.shape != (96, 96, 3):
        raise ValueError("memorization crop shape mismatch")
    return value


def normalize_pair(
    reference: np.ndarray, observation: np.ndarray, normalization_id: str
) -> np.ndarray:
    reference = reference.astype(np.float32) / 255.0
    observation = observation.astype(np.float32) / 255.0
    if normalization_id == "SELF_CROP_P05_P95":
        def normalize(value: np.ndarray) -> np.ndarray:
            low = np.quantile(value, 0.05, axis=(0, 1))
            high = np.quantile(value, 0.95, axis=(0, 1))
            return np.clip((value - low) / np.maximum(high - low, 0.05), 0.0, 1.0)

        reference = normalize(reference)
        observation = normalize(observation)
    elif normalization_id == "REFERENCE_CONTEXT_WHITEPOINT":
        context = np.ones(reference.shape[:2], dtype=bool)
        height, width = reference.shape[:2]
        context[height // 4 : height - height // 4, width // 4 : width - width // 4] = False
        white = np.quantile(reference[context], 0.95, axis=0)
        reference = np.clip(reference / np.maximum(white, 0.05), 0.0, 1.0)
        observation = np.clip(observation / np.maximum(white, 0.05), 0.0, 1.0)
    else:
        raise ValueError(f"unsupported normalization: {normalization_id}")
    difference = np.abs(reference - observation)
    return np.concatenate((reference, observation, difference), axis=2).transpose(2, 0, 1)


def load_subset(preparation: dict[str, Any], normalization_id: str) -> tuple[np.ndarray, np.ndarray]:
    arrays = np.empty((preparation["subset_count"], 9, 96, 96), dtype=np.float32)
    labels = np.empty(preparation["subset_count"], dtype=np.float32)
    for index, row in enumerate(preparation["subset_rows"]):
        root = Path(row["shard_root"]).resolve(strict=True)
        reference = _read_image(
            root, row["reference_rgb_path"], row["reference_rgb_sha256"], row["reference_rgb_bytes"]
        )
        observation = _read_image(root, row["rgb_path"], row["rgb_sha256"], row["rgb_bytes"])
        arrays[index] = normalize_pair(reference, observation, normalization_id)
        labels[index] = 1.0 if row["expected_decision"] == "ABSTAIN" else 0.0
    return arrays, labels


def spatial_model(torch: Any) -> Any:
    return torch.nn.Sequential(
        torch.nn.Conv2d(9, 24, 3, padding=1),
        torch.nn.GroupNorm(6, 24),
        torch.nn.ReLU(),
        torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(24, 48, 3, padding=1),
        torch.nn.GroupNorm(8, 48),
        torch.nn.ReLU(),
        torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(48, 64, 3, padding=1),
        torch.nn.GroupNorm(8, 64),
        torch.nn.ReLU(),
        torch.nn.AvgPool2d(4),
        torch.nn.Flatten(),
        torch.nn.Linear(64 * 36, 1),
    )


def paired_resolution_spatial_model(torch: Any, input_size_px: int) -> Any:
    """Build the parameter-matched 96/192 comparison model.

    The released v4.2 function above stays byte-for-byte architectural evidence.
    This successor preserves its 6 by 6 spatial head while allowing only the two
    predeclared square input sizes.  Adaptive pooling keeps parameter count
    identical, so the comparison changes input sampling rather than capacity.
    """

    if isinstance(input_size_px, bool) or input_size_px not in {96, 192}:
        raise ValueError("paired input_size_px must be 96 or 192")
    return torch.nn.Sequential(
        torch.nn.Conv2d(9, 24, 3, padding=1),
        torch.nn.GroupNorm(6, 24),
        torch.nn.ReLU(),
        torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(24, 48, 3, padding=1),
        torch.nn.GroupNorm(8, 48),
        torch.nn.ReLU(),
        torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(48, 64, 3, padding=1),
        torch.nn.GroupNorm(8, 64),
        torch.nn.ReLU(),
        torch.nn.AdaptiveAvgPool2d((6, 6)),
        torch.nn.Flatten(),
        torch.nn.Linear(64 * 36, 1),
    )


def paired_height_resolution_spatial_model(torch: Any, input_size_px: int) -> Any:
    """Build the frozen twelve-channel paired-height comparison model.

    Both resolutions retain the same two early 2x pooling operations.  The
    192-pixel candidate therefore carries a 48x48 map into the final adaptive
    pool while the 96-pixel candidate carries 24x24.  The final 6x6 cells cover
    the same physical region because both inputs represent the same 48 mm crop.
    """

    if isinstance(input_size_px, bool) or input_size_px not in {96, 192}:
        raise ValueError("paired-height input_size_px must be 96 or 192")
    return torch.nn.Sequential(
        torch.nn.Conv2d(12, 24, 3, padding=1),
        torch.nn.GroupNorm(6, 24),
        torch.nn.ReLU(),
        torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(24, 48, 3, padding=1),
        torch.nn.GroupNorm(8, 48),
        torch.nn.ReLU(),
        torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(48, 64, 3, padding=1),
        torch.nn.GroupNorm(8, 64),
        torch.nn.ReLU(),
        torch.nn.AdaptiveAvgPool2d((6, 6)),
        torch.nn.Flatten(),
        torch.nn.Linear(64 * 36, 1),
    )


def train_one(
    arrays: np.ndarray, labels: np.ndarray, settings: dict[str, Any], seed: int
) -> dict[str, Any]:
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
        lr=float(settings["learning_rate"]),
        weight_decay=float(settings["weight_decay"]),
    )
    loss_fn = torch.nn.BCEWithLogitsLoss()
    rng = np.random.default_rng(seed)
    first_loss = None
    final_loss = float("inf")
    final_accuracy = 0.0
    batch_size = int(settings["batch_size"])
    for epoch in range(1, int(settings["epochs_maximum"]) + 1):
        model.train()
        order = rng.permutation(len(labels))
        for start in range(0, len(labels), batch_size):
            batch = order[start:start + batch_size]
            x = torch.from_numpy(arrays[batch]).to(device)
            y = torch.from_numpy(labels[batch]).to(device).reshape(-1, 1)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(x), y)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            logits = model(torch.from_numpy(arrays).to(device))
            expected = torch.from_numpy(labels).to(device).reshape(-1, 1)
            final_loss = float(loss_fn(logits, expected).cpu())
            probability = torch.sigmoid(logits).reshape(-1).cpu().numpy()
        final_accuracy = float(np.mean((probability >= 0.5) == labels))
        if first_loss is None:
            first_loss = final_loss
        if (
            final_loss <= float(settings["loss_maximum"])
            and final_accuracy >= float(settings["accuracy_minimum"])
        ):
            break
    return {
        "architecture": settings["architecture"],
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "device": str(device),
        "epochs_run": epoch,
        "first_loss": first_loss,
        "final_loss": final_loss,
        "final_accuracy": final_accuracy,
        "gate_met": (
            final_loss <= float(settings["loss_maximum"])
            and final_accuracy >= float(settings["accuracy_minimum"])
        ),
        "augmentation_enabled": False,
        "dropout_enabled": False,
    }


def run(preparation_path: Path, admission_path: Path) -> dict[str, Any]:
    preparation, _ = _load_report(preparation_path, PREPARATION_SCHEMA)
    admission, _ = _load_report(admission_path, ADMISSION_SCHEMA)
    if admission["status"] != "PASS" or admission["campaign_admitted"] is not True:
        raise ValueError("memorization requires complete campaign admission")
    if admission["report_sha256"] != preparation["admission_report_sha256"]:
        raise ValueError("memorization preparation/admission mismatch")
    if preparation["development_pixels_opened"] is not False:
        raise ValueError("preparation claims development access")
    settings = preparation["memorization_training"]
    runs = {}
    for normalization_id in NORMALIZATION_METRICS:
        arrays, labels = load_subset(preparation, normalization_id)
        runs[normalization_id] = train_one(
            arrays, labels, settings, int(preparation["subset_seed"])
        )
    core = {
        "schema": SCHEMA,
        "scope": "SYNTHETIC_TRAINING_ONLY_MEMORIZATION_GATE_NO_QUALIFICATION",
        "fixture_bundle_sha256": preparation["fixture_bundle_sha256"],
        "admission_report_sha256": admission["report_sha256"],
        "preparation_report_sha256": preparation["report_sha256"],
        "subset_identity_sha256": preparation["subset_identity_sha256"],
        "subset_count": preparation["subset_count"],
        "runs": runs,
        "both_gates_met": all(row["gate_met"] for row in runs.values()),
        "development_pixels_opened": False,
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    from admit_residual_obstruction_v4_2_shards import canonical, digest

    return {**core, "report_sha256": digest(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.preparation, args.admission)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "report_sha256": result["report_sha256"],
        "both_gates_met": result["both_gates_met"],
        "runs": result["runs"],
    }, indent=2))
    return 0 if result["both_gates_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
