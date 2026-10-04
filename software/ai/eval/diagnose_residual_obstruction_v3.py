"""Diagnose the consumed residual-v3 development split without model selection."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import sys
from typing import Any

import numpy as np
from PIL import Image


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from train.train_residual_obstruction_v3 import (  # noqa: E402
    MODEL_MAGIC,
    RESULT_SCHEMA,
    _load_campaign,
    canonical,
    load_bound,
    sha256_bytes,
)


DIAGNOSTIC_SCHEMA = "tactevra.ai_residual_obstruction_v3_diagnostic.v1"


def _build_model(torch: Any, channels: list[int]) -> Any:
    return torch.nn.Sequential(
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
    )


def load_model(path: Path, expected_sha256: str) -> tuple[Any, dict[str, Any]]:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False

    payload = path.resolve(strict=True).read_bytes()
    if sha256_bytes(payload) != expected_sha256:
        raise ValueError("model hash mismatch")
    if not payload.startswith(MODEL_MAGIC):
        raise ValueError("model magic mismatch")
    offset = len(MODEL_MAGIC)

    def take_u32() -> int:
        nonlocal offset
        if offset + 4 > len(payload):
            raise ValueError("truncated model")
        value = struct.unpack_from("<I", payload, offset)[0]
        offset += 4
        return value

    metadata_size = take_u32()
    if offset + metadata_size > len(payload):
        raise ValueError("truncated model metadata")
    metadata = json.loads(payload[offset:offset + metadata_size])
    offset += metadata_size
    state = {}
    while offset < len(payload):
        name_size = take_u32()
        if offset + name_size > len(payload):
            raise ValueError("truncated parameter name")
        name = payload[offset:offset + name_size].decode()
        offset += name_size
        dimensions = take_u32()
        shape = tuple(take_u32() for _ in range(dimensions))
        count = int(np.prod(shape, dtype=np.int64))
        byte_count = count * 4
        if offset + byte_count > len(payload):
            raise ValueError("truncated parameter values")
        values = np.frombuffer(payload, dtype="<f4", count=count, offset=offset).copy().reshape(shape)
        offset += byte_count
        if name in state:
            raise ValueError(f"duplicate model parameter: {name}")
        state[name] = torch.from_numpy(values)
    channels = [int(value) for value in metadata["convolution_channels"]]
    model = _build_model(torch, channels)
    model.load_state_dict(state, strict=True)
    model.eval()
    return model, metadata


def probability_summary(values: np.ndarray) -> dict[str, float]:
    return {
        "minimum": float(np.min(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "maximum": float(np.max(values)),
    }


def pairwise_auc(labels: np.ndarray, probabilities: np.ndarray) -> float:
    visible = np.sort(probabilities[labels == 0])
    obstruction = probabilities[labels == 1]
    lower = np.searchsorted(visible, obstruction, side="left")
    upper = np.searchsorted(visible, obstruction, side="right")
    return float(np.sum(lower + 0.5 * (upper - lower)) / (len(visible) * len(obstruction)))


def _mixed_group_diagnostics(
    labels: np.ndarray,
    probabilities: np.ndarray,
    identities: list[str],
    identity_name: str,
) -> list[dict[str, Any]]:
    output = []
    for identity in sorted(set(identities)):
        selected = np.asarray([i for i, value in enumerate(identities) if value == identity])
        local_labels = labels[selected]
        local_probabilities = probabilities[selected]
        visible = local_probabilities[local_labels == 0]
        obstruction = local_probabilities[local_labels == 1]
        margin = float(np.min(obstruction) - np.max(visible))
        output.append({
            identity_name: identity,
            "visible_count": int(len(visible)),
            "obstruction_count": int(len(obstruction)),
            "visible_probability": probability_summary(visible),
            "obstruction_probability": probability_summary(obstruction),
            "separation_margin": margin,
            "locally_separable": margin > 0.0,
        })
    return output


def _single_label_diagnostics(
    labels: np.ndarray,
    probabilities: np.ndarray,
    identities: list[str],
    identity_name: str,
) -> list[dict[str, Any]]:
    output = []
    for identity in sorted(set(identities)):
        selected = np.asarray([i for i, value in enumerate(identities) if value == identity])
        local_labels = labels[selected]
        if len(set(local_labels.tolist())) != 1:
            raise ValueError(f"mixed labels in {identity_name}: {identity}")
        output.append({
            identity_name: identity,
            "expected_decision": "ABSTAIN" if local_labels[0] else "VISIBLE",
            "count": int(len(selected)),
            "probability": probability_summary(probabilities[selected]),
        })
    return output


def _development_probabilities(model: Any, entries: list[dict[str, Any]], batch_size: int) -> tuple[list[dict[str, Any]], np.ndarray]:
    import torch

    development = [row for row in entries if row["split"] == "development"]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    chunks = []
    with torch.no_grad():
        for start in range(0, len(development), batch_size):
            rows = development[start:start + batch_size]
            arrays = np.empty((len(rows), 3, 96, 96), dtype=np.uint8)
            for index, row in enumerate(rows):
                with Image.open(row["image_path"]) as image:
                    value = np.asarray(image.convert("RGB"), dtype=np.uint8)
                if value.shape != (96, 96, 3):
                    raise ValueError(f"unexpected crop shape: {row['observation_id']}")
                arrays[index] = value.transpose(2, 0, 1)
            x = torch.from_numpy(arrays).to(device=device, dtype=torch.float32).div_(255.0)
            chunks.append(torch.sigmoid(model(x)).reshape(-1).cpu().numpy())
    return development, np.concatenate(chunks).astype(np.float32)


def diagnose(
    workspace: Path,
    fixture_path: Path,
    admission_path: Path,
    lineage_path: Path,
    shard_dirs: list[Path],
    scorecard_path: Path,
    model_path: Path,
) -> dict[str, Any]:
    fixture, admission, entries = _load_campaign(
        workspace, fixture_path, admission_path, lineage_path, shard_dirs
    )
    scorecard, scorecard_bytes = load_bound(scorecard_path, RESULT_SCHEMA, "result_sha256")
    if scorecard["status"] != "FAILED_DEVELOPMENT_GATE" or scorecard["selected_threshold"] is not None:
        raise ValueError("diagnostic requires the unchanged rejected scorecard")
    if scorecard["admission_receipt_sha256"] != admission["receipt_sha256"]:
        raise ValueError("scorecard admission mismatch")
    model, metadata = load_model(model_path, scorecard["model_sha256"])
    if metadata["fixture_bundle_sha256"] != fixture["bundle_sha256"]:
        raise ValueError("model fixture mismatch")
    development, probabilities = _development_probabilities(
        model, entries, int(fixture["training_plan"]["batch_size"])
    )
    if sha256_bytes(probabilities.astype("<f4").tobytes()) != scorecard["development_probability_sha256"]:
        raise ValueError("development probabilities do not reproduce")
    labels = np.asarray(
        [1 if row["expected_decision"] == "ABSTAIN" else 0 for row in development],
        dtype=np.int8,
    )
    family_by_variant = {item["variant_id"]: item["family"] for item in fixture["variants"]}
    families = [family_by_variant[row["variant_id"]] for row in development]
    variants = [row["variant_id"] for row in development]
    core = {
        "schema": DIAGNOSTIC_SCHEMA,
        "scope": "CONSUMED_SYNTHETIC_ISAAC_DEVELOPMENT_DIAGNOSTIC_NO_QUALIFICATION",
        "fixture_file_sha256": sha256_bytes(fixture_path.read_bytes()),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "admission_file_sha256": sha256_bytes(admission_path.read_bytes()),
        "admission_receipt_sha256": admission["receipt_sha256"],
        "lineage_file_sha256": sha256_bytes(lineage_path.read_bytes()),
        "scorecard_file_sha256": sha256_bytes(scorecard_bytes),
        "scorecard_result_sha256": scorecard["result_sha256"],
        "model_file_sha256": sha256_bytes(model_path.read_bytes()),
        "development_count": len(development),
        "development_probability_sha256": scorecard["development_probability_sha256"],
        "pairwise_auc": pairwise_auc(labels, probabilities),
        "global_probability": {
            "visible": probability_summary(probabilities[labels == 0]),
            "obstruction": probability_summary(probabilities[labels == 1]),
        },
        "scene_diagnostics": _mixed_group_diagnostics(
            labels, probabilities, [row["scene_id"] for row in development], "scene_id"
        ),
        "appearance_diagnostics": _mixed_group_diagnostics(
            labels, probabilities, [row["appearance_id"] for row in development], "appearance_id"
        ),
        "target_diagnostics": _mixed_group_diagnostics(
            labels,
            probabilities,
            [f"{row['device']}:{row['target_id']}" for row in development],
            "target_id",
        ),
        "variant_diagnostics": _single_label_diagnostics(
            labels, probabilities, variants, "variant_id"
        ),
        "family_diagnostics": _single_label_diagnostics(
            labels, probabilities, families, "family"
        ),
        "checkpoint_changed": False,
        "threshold_changed": False,
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "This diagnostic reuses consumed synthetic development evidence and cannot evaluate a successor",
            "The camera, materials, and obstruction geometry remain synthetic and unmeasured",
            "Probability attribution may guide a fresh predeclaration but cannot qualify deployment",
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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = diagnose(
        args.workspace,
        args.fixture,
        args.admission,
        args.lineage,
        args.shard,
        args.scorecard,
        args.model,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(report) + b"\n")
    print(json.dumps({
        "schema": report["schema"],
        "report_sha256": report["report_sha256"],
        "pairwise_auc": report["pairwise_auc"],
        "locally_separable_targets": sum(
            row["locally_separable"] for row in report["target_diagnostics"]
        ),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
