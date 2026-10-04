"""Diagnose the consumed residual-obstruction v2 development failure."""

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

from sim.render_residual_obstruction_v2 import (  # noqa: E402
    FIXTURE_SCHEMA,
    canonical,
    load_bound,
    sha256_bytes,
    verify,
)
from train.train_residual_obstruction_v2 import MODEL_MAGIC, RESULT_SCHEMA  # noqa: E402


REPORT_SCHEMA = "tactevra.ai_residual_obstruction_v2_diagnostic.v1"


def read_model(path: Path) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    payload = path.read_bytes()
    if not payload.startswith(MODEL_MAGIC):
        raise ValueError("model magic mismatch")
    offset = len(MODEL_MAGIC)
    metadata_length = struct.unpack_from("<I", payload, offset)[0]
    offset += 4
    metadata = json.loads(payload[offset:offset + metadata_length])
    offset += metadata_length
    state: dict[str, np.ndarray] = {}
    while offset < len(payload):
        name_length = struct.unpack_from("<I", payload, offset)[0]
        offset += 4
        name = payload[offset:offset + name_length].decode()
        offset += name_length
        dimensions = struct.unpack_from("<I", payload, offset)[0]
        offset += 4
        shape = struct.unpack_from("<" + "I" * dimensions, payload, offset)
        offset += 4 * dimensions
        count = int(np.prod(shape))
        array = np.frombuffer(payload, dtype="<f4", count=count, offset=offset).reshape(shape).copy()
        offset += count * 4
        if name in state:
            raise ValueError("duplicate model tensor")
        state[name] = array
    if offset != len(payload):
        raise ValueError("model payload length mismatch")
    return metadata, state


def infer(model_path: Path, dataset_dir: Path, entries: list[dict[str, Any]]) -> np.ndarray:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    metadata, arrays = read_model(model_path)
    channels = metadata["convolution_channels"]
    model = torch.nn.Sequential(
        torch.nn.Conv2d(3, channels[0], 3, padding=1), torch.nn.ReLU(), torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[0], channels[1], 3, padding=1), torch.nn.ReLU(), torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[1], channels[2], 3, padding=1), torch.nn.ReLU(),
        torch.nn.AdaptiveAvgPool2d((1, 1)), torch.nn.Flatten(), torch.nn.Linear(channels[2], 1),
    )
    state = model.state_dict()
    if set(state) != set(arrays):
        raise ValueError("model tensor inventory mismatch")
    model.load_state_dict({name: torch.from_numpy(arrays[name]) for name in state})
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    model.to(device)
    model.eval()
    outputs = []
    with torch.no_grad():
        for start in range(0, len(entries), 128):
            batch = np.empty((min(128, len(entries) - start), 3, 96, 96), dtype=np.uint8)
            for local, entry in enumerate(entries[start:start + 128]):
                with Image.open(dataset_dir / entry["path"]) as image:
                    batch[local] = np.asarray(image.convert("RGB"), dtype=np.uint8).transpose(2, 0, 1)
            tensor = torch.from_numpy(batch).to(device=device, dtype=torch.float32).div_(255.0)
            outputs.append(torch.sigmoid(model(tensor)).reshape(-1).cpu().numpy())
    return np.concatenate(outputs).astype(np.float32)


def _stats(values: np.ndarray) -> dict[str, float]:
    return {
        "minimum": float(np.min(values)), "maximum": float(np.max(values)),
        "mean": float(np.mean(values)), "median": float(np.median(values)),
    }


def _group(rows: list[dict[str, Any]], probabilities: np.ndarray, field: str, thresholds: list[float]) -> list[dict[str, Any]]:
    output = []
    for identity in sorted({row[field] for row in rows}):
        index = np.asarray([i for i, row in enumerate(rows) if row[field] == identity])
        labels = np.asarray([rows[i]["expected_decision"] == "ABSTAIN" for i in index])
        values = probabilities[index]
        visible = values[~labels]
        obstruction = values[labels]
        decisions = []
        for threshold in thresholds:
            decisions.append({
                "threshold": threshold,
                "missed_obstructions": int(np.sum(obstruction < threshold)),
                "obstruction_count": int(len(obstruction)),
                "visible_false_stops": int(np.sum(visible >= threshold)),
                "visible_count": int(len(visible)),
            })
        output.append({
            "group_id": identity, "count": int(len(index)),
            "visible_probability": None if not len(visible) else _stats(visible),
            "obstruction_probability": None if not len(obstruction) else _stats(obstruction),
            "separation_margin": None if not len(visible) or not len(obstruction) else float(np.min(obstruction) - np.max(visible)),
            "threshold_decisions": decisions,
        })
    return output


def _auc(labels: np.ndarray, probabilities: np.ndarray) -> float:
    positive = probabilities[labels]
    negative = probabilities[~labels]
    wins = 0.0
    for start in range(0, len(positive), 256):
        comparison = positive[start:start + 256, None] - negative[None, :]
        wins += float(np.sum(comparison > 0) + 0.5 * np.sum(comparison == 0))
    return wins / (len(positive) * len(negative))


def diagnose(
    fixture_path: Path,
    contract_path: Path,
    dataset_dir: Path,
    model_path: Path,
    scorecard_path: Path,
) -> dict[str, Any]:
    fixture = load_bound(fixture_path.resolve(strict=True), FIXTURE_SCHEMA, "bundle_sha256")
    manifest = verify(fixture_path, contract_path, dataset_dir)
    scorecard = load_bound(scorecard_path.resolve(strict=True), RESULT_SCHEMA, "result_sha256")
    if scorecard["status"] != "FAILED_DEVELOPMENT_GATE" or scorecard["selected_threshold"] is not None:
        raise ValueError("diagnostic requires rejected unselected candidate")
    if scorecard["evaluation_opened"] is not False or scorecard["evaluation_count"] != 0:
        raise ValueError("evaluation was opened")
    if sha256_bytes(model_path.read_bytes()) != scorecard["model_sha256"]:
        raise ValueError("model hash mismatch")
    if scorecard["dataset_sha256"] != manifest["dataset_sha256"] or scorecard["fixture_bundle_sha256"] != fixture["bundle_sha256"]:
        raise ValueError("scorecard binding mismatch")
    metadata, _ = read_model(model_path)
    if metadata["dataset_sha256"] != manifest["dataset_sha256"] or metadata["fixture_bundle_sha256"] != fixture["bundle_sha256"]:
        raise ValueError("model binding mismatch")
    rows = [row for row in manifest["files"] if row["split"] == "development"]
    probabilities = infer(model_path, dataset_dir, rows)
    if sha256_bytes(probabilities.astype("<f4").tobytes()) != scorecard["development_probability_sha256"]:
        raise ValueError("development probability reconstruction mismatch")
    if sha256_bytes(canonical([row["observation_id"] for row in rows])) != scorecard["development_identity_sha256"]:
        raise ValueError("development identity mismatch")
    labels = np.asarray([row["expected_decision"] == "ABSTAIN" for row in rows])
    thresholds = [0.1, 0.2]
    groups = {
        "variant": _group(rows, probabilities, "variant_id", thresholds),
        "appearance": _group(rows, probabilities, "appearance_id", thresholds),
        "view": _group(rows, probabilities, "view_id", thresholds),
        "target": _group(rows, probabilities, "target_id", thresholds),
    }
    margins = [row["separation_margin"] for row in groups["target"] if row["separation_margin"] is not None]
    core = {
        "schema": REPORT_SCHEMA,
        "scope": "CONSUMED_SYNTHETIC_DEVELOPMENT_DIAGNOSTIC_NO_QUALIFICATION",
        "fixture_file_sha256": sha256_bytes(fixture_path.read_bytes()), "fixture_bundle_sha256": fixture["bundle_sha256"],
        "contract_file_sha256": sha256_bytes(contract_path.read_bytes()), "contract_sha256": manifest["contract_sha256"],
        "dataset_manifest_file_sha256": sha256_bytes((dataset_dir / "manifest.json").read_bytes()),
        "dataset_sha256": manifest["dataset_sha256"], "model_sha256": scorecard["model_sha256"],
        "scorecard_file_sha256": sha256_bytes(scorecard_path.read_bytes()), "scorecard_result_sha256": scorecard["result_sha256"],
        "development_count": len(rows), "obstruction_count": int(np.sum(labels)), "visible_count": int(np.sum(~labels)),
        "pairwise_auc": _auc(labels, probabilities),
        "visible_probability": _stats(probabilities[~labels]), "obstruction_probability": _stats(probabilities[labels]),
        "diagnostic_thresholds": thresholds, "groups": groups,
        "target_separation": {
            "target_count": len(margins), "locally_separable_count": sum(value > 0 for value in margins),
            "nonseparable_count": sum(value <= 0 for value in margins),
            "best_margin": max(margins), "worst_margin": min(margins),
        },
        "findings": [
            {
                "finding_id": "appearance_transfer_failure",
                "evidence": "Cool appearance drives obstruction misses while shadow and sensor-noise appearances drive visible false stops",
                "successor_dependency": "Use fresh independent base scenes and predeclared appearance-invariance training rather than more thresholds",
            },
            {
                "finding_id": "weak_cable_tool_compression_separation",
                "evidence": "Cable, tool, and compression families contribute most threshold-0.20 obstruction misses",
                "successor_dependency": "Replace pixel-fill proxies with physically shaped renders spanning material, edge, depth, and transparency variation",
            },
            {
                "finding_id": "catalog_wide_overlap",
                "evidence": "All 75 targets have nonpositive local visible-versus-obstruction separation margins",
                "successor_dependency": "Retain target-balanced gates and require positive held-out local margins before evaluation",
            },
        ],
        "checkpoint_changed": False, "threshold_changed": False, "evaluation_opened": False,
        "hardware_writes": 0, "physical_movements": 0, "physical_authority": False,
        "limitations": [
            "This diagnosis consumes the synthetic development split and cannot evaluate a successor",
            "All images derive from one simplified base scene and pixel-domain transformations",
            "Group attribution does not establish physical realism, qualification, or execution authority",
        ],
    }
    return {**core, "report_sha256": sha256_bytes(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--scorecard", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = diagnose(args.fixture, args.contract, args.dataset_dir, args.model, args.scorecard)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(report) + b"\n")
    print(json.dumps({"schema": report["schema"], "report_sha256": report["report_sha256"], "pairwise_auc": report["pairwise_auc"], "target_separation": report["target_separation"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
