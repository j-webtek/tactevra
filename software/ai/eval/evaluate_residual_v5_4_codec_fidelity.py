"""Evaluate the frozen v5.4 raw/JPEG/YUY2 input-fidelity gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


SCHEMA = "tactevra.residual_v5_4_codec_fidelity_result.v1"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _luma(rgb: np.ndarray) -> np.ndarray:
    value = rgb.astype(np.float64)
    return 0.299 * value[..., 0] + 0.587 * value[..., 1] + 0.114 * value[..., 2]


def _sobel_magnitude(rgb: np.ndarray) -> np.ndarray:
    value = _luma(rgb)
    padded = np.pad(value, 1, mode="edge")
    gx = (
        -padded[:-2, :-2] + padded[:-2, 2:]
        - 2 * padded[1:-1, :-2] + 2 * padded[1:-1, 2:]
        - padded[2:, :-2] + padded[2:, 2:]
    )
    gy = (
        -padded[:-2, :-2] - 2 * padded[:-2, 1:-1] - padded[:-2, 2:]
        + padded[2:, :-2] + 2 * padded[2:, 1:-1] + padded[2:, 2:]
    )
    return np.hypot(gx, gy)


def yuy2_round_trip(rgb: np.ndarray) -> np.ndarray:
    """Round-trip RGB8 through packed full-range BT.601 YUY2 with left chroma."""
    if rgb.shape[-1] != 3 or rgb.shape[1] % 2:
        raise ValueError("YUY2 input must be even-width RGB")
    value = rgb.astype(np.float64)
    red, green, blue = value[..., 0], value[..., 1], value[..., 2]
    y = np.clip(np.rint(0.299 * red + 0.587 * green + 0.114 * blue), 0, 255)
    u = np.clip(np.rint(-0.168736 * red + -0.331264 * green + 0.5 * blue + 128), 0, 255)
    v = np.clip(np.rint(0.5 * red + -0.418688 * green + -0.081312 * blue + 128), 0, 255)
    u_pair = u[:, 0::2]
    v_pair = v[:, 0::2]
    u_full = np.repeat(u_pair, 2, axis=1)
    v_full = np.repeat(v_pair, 2, axis=1)
    red_out = y + 1.402 * (v_full - 128)
    green_out = y - 0.344136 * (u_full - 128) - 0.714136 * (v_full - 128)
    blue_out = y + 1.772 * (u_full - 128)
    return np.clip(np.rint(np.stack((red_out, green_out, blue_out), axis=-1)), 0, 255).astype(np.uint8)


def _signal(reference: np.ndarray, observation: np.ndarray, mask: np.ndarray) -> tuple[float, float]:
    rgb = float(np.mean(np.abs(observation.astype(np.int16) - reference.astype(np.int16))[mask]))
    edge = float(np.mean(np.abs(_sobel_magnitude(observation) - _sobel_magnitude(reference))[mask]))
    return rgb, edge


def _distortion(raw: np.ndarray, encoded: np.ndarray, mask: np.ndarray) -> float:
    return float(np.mean(np.abs(raw.astype(np.int16) - encoded.astype(np.int16))[mask]))


def _summary(rows: list[dict[str, float]]) -> dict[str, float]:
    def values(name: str) -> np.ndarray:
        return np.asarray([row[name] for row in rows], dtype=np.float64)

    return {
        "row_count": len(rows),
        "median_rgb_contrast_retention": float(np.median(values("rgb_retention"))),
        "q05_rgb_contrast_retention": float(np.quantile(values("rgb_retention"), 0.05)),
        "minimum_rgb_contrast_retention": float(np.min(values("rgb_retention"))),
        "median_codec_distortion_to_signal": float(np.median(values("distortion_to_signal"))),
        "q95_codec_distortion_to_signal": float(np.quantile(values("distortion_to_signal"), 0.95)),
        "maximum_codec_distortion_to_signal": float(np.max(values("distortion_to_signal"))),
        "q05_edge_contrast_retention": float(np.quantile(values("edge_retention"), 0.05)),
        "minimum_edge_contrast_retention": float(np.min(values("edge_retention"))),
        "minimum_encoded_rgb_signal_when_raw_meets_floor": float(np.min([
            row["encoded_rgb_signal"] for row in rows if row["raw_rgb_signal"] >= 2.0
        ])),
    }


def _gate(summary: dict[str, float], limits: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "median_rgb": summary["median_rgb_contrast_retention"] >= limits["minimum_median_rgb_contrast_retention"],
        "q05_rgb": summary["q05_rgb_contrast_retention"] >= limits["minimum_q05_rgb_contrast_retention"],
        "every_rgb": summary["minimum_rgb_contrast_retention"] >= limits["minimum_every_row_rgb_contrast_retention"],
        "median_distortion": summary["median_codec_distortion_to_signal"] <= limits["maximum_median_codec_distortion_to_signal"],
        "q95_distortion": summary["q95_codec_distortion_to_signal"] <= limits["maximum_q95_codec_distortion_to_signal"],
        "every_distortion": summary["maximum_codec_distortion_to_signal"] <= limits["maximum_every_row_codec_distortion_to_signal"],
        "q05_edge": summary["q05_edge_contrast_retention"] >= limits["minimum_q05_edge_contrast_retention"],
        "every_edge": summary["minimum_edge_contrast_retention"] >= limits["minimum_every_row_edge_contrast_retention"],
        "encoded_floor": summary["minimum_encoded_rgb_signal_when_raw_meets_floor"] >= limits["minimum_encoded_rgb_signal_when_raw_meets_floor_levels"],
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def evaluate(predeclaration_path: Path, probe_dir: Path) -> dict[str, Any]:
    predeclaration = json.loads(predeclaration_path.read_text(encoding="utf-8"))
    core = {key: value for key, value in predeclaration.items() if key != "bundle_sha256"}
    if predeclaration["bundle_sha256"] != hashlib.sha256(canonical(core)).hexdigest():
        raise ValueError("predeclaration hash mismatch")
    manifest_path = probe_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    population = predeclaration["population"]
    expected_targets = {(row["device"], row["target_id"]) for row in population["target_indices_and_ids"]}
    rows = manifest["observations"]
    actual_ids = {
        (row["scene_id"], row["appearance_id"], row["variant_id"], row["device"], row["target_id"])
        for row in rows
    }
    expected_ids = {
        (scene, appearance, variant, device, target)
        for scene in population["scene_ids"]
        for appearance in population["appearance_ids"]
        for variant in population["variant_ids"]
        for device, target in expected_targets
    }
    if actual_ids != expected_ids or len(rows) != population["obstructed_pair_count"]:
        raise ValueError("codec probe population differs from frozen predeclaration")
    by_codec: dict[str, list[dict[str, float]]] = {"jpeg": [], "yuy2": []}
    for row in rows:
        raw_reference = np.asarray(Image.open(probe_dir / row["reference_raw_rgb_path"]).convert("RGB"))
        raw_observation = np.asarray(Image.open(probe_dir / row["raw_rgb_path"]).convert("RGB"))
        jpeg_reference = np.asarray(Image.open(probe_dir / row["reference_rgb_path"]).convert("RGB"))
        jpeg_observation = np.asarray(Image.open(probe_dir / row["rgb_path"]).convert("RGB"))
        mask = np.asarray(Image.open(probe_dir / row["safe_region_mask_path"]).convert("L")) > 0
        raw_rgb, raw_edge = _signal(raw_reference, raw_observation, mask)
        if raw_rgb == 0 or raw_edge == 0:
            raise ValueError("zero raw signal")
        for codec, reference, observation in (
            ("jpeg", jpeg_reference, jpeg_observation),
            ("yuy2", yuy2_round_trip(raw_reference), yuy2_round_trip(raw_observation)),
        ):
            encoded_rgb, encoded_edge = _signal(reference, observation, mask)
            distortion = (_distortion(raw_reference, reference, mask) + _distortion(raw_observation, observation, mask)) / 2
            by_codec[codec].append({
                "raw_rgb_signal": raw_rgb,
                "encoded_rgb_signal": encoded_rgb,
                "rgb_retention": encoded_rgb / raw_rgb,
                "edge_retention": encoded_edge / raw_edge,
                "distortion_to_signal": distortion / raw_rgb,
            })
    summaries = {codec: _summary(codec_rows) for codec, codec_rows in by_codec.items()}
    gates = {
        codec: _gate(summary, predeclaration["frozen_gate_applied_separately_to_jpeg_and_yuy2"])
        for codec, summary in summaries.items()
    }
    result = {
        "schema": SCHEMA,
        "status": "PASS" if all(gate["status"] == "PASS" for gate in gates.values()) else "FAIL",
        "predeclaration_file_sha256": sha256(predeclaration_path),
        "predeclaration_bundle_sha256": predeclaration["bundle_sha256"],
        "probe_manifest_file_sha256": sha256(manifest_path),
        "probe_dataset_sha256": manifest["dataset_sha256"],
        "population": {"rows": len(rows), "evaluation_images_opened": 0},
        "summaries": summaries,
        "gates": gates,
        "training_authorized_by_jpeg_gate": gates["jpeg"]["status"] == "PASS",
        "synthetic_yuy2_transfer_plausible": gates["yuy2"]["status"] == "PASS",
        "physical_qualification": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": predeclaration["limitations"],
    }
    result["report_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predeclaration", type=Path, required=True)
    parser.add_argument("--probe-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.predeclaration, args.probe_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(report) + b"\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
