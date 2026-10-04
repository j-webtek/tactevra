"""Attribute the frozen v5.4 codec failure without changing its decision."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


SCHEMA = "tactevra.residual_v5_4_codec_failure_diagnostic.v1"
THIS_DIR = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "v5_4_codec_fidelity", THIS_DIR / "evaluate_residual_v5_4_codec_fidelity.py"
)
assert _SPEC and _SPEC.loader
_FIDELITY = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_FIDELITY)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def values(name: str) -> np.ndarray:
        return np.asarray([row[name] for row in rows], dtype=np.float64)

    result: dict[str, Any] = {"row_count": len(rows)}
    for name in ("raw_rgb_signal", "yuy2_rgb_signal", "raw_edge_signal", "yuy2_edge_signal", "distortion_to_signal"):
        data = values(name)
        result[name] = {
            "minimum": float(np.min(data)),
            "q05": float(np.quantile(data, 0.05)),
            "median": float(np.median(data)),
            "q95": float(np.quantile(data, 0.95)),
            "maximum": float(np.max(data)),
        }
    result["raw_rgb_below_2_levels"] = sum(row["raw_rgb_signal"] < 2.0 for row in rows)
    result["raw_rgb_below_3_levels"] = sum(row["raw_rgb_signal"] < 3.0 for row in rows)
    result["yuy2_rgb_below_2_levels"] = sum(row["yuy2_rgb_signal"] < 2.0 for row in rows)
    result["yuy2_rgb_below_3_levels"] = sum(row["yuy2_rgb_signal"] < 3.0 for row in rows)
    return result


def diagnose(probe_dir: Path, frozen_result_path: Path) -> dict[str, Any]:
    frozen = json.loads(frozen_result_path.read_text(encoding="utf-8"))
    if frozen["status"] != "FAIL" or frozen["training_authorized_by_jpeg_gate"]:
        raise ValueError("diagnostic requires the unchanged rejected codec result")
    manifest_path = probe_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for source in manifest["observations"]:
        raw_reference = np.asarray(Image.open(probe_dir / source["reference_raw_rgb_path"]).convert("RGB"))
        raw_observation = np.asarray(Image.open(probe_dir / source["raw_rgb_path"]).convert("RGB"))
        mask = np.asarray(Image.open(probe_dir / source["safe_region_mask_path"]).convert("L")) > 0
        yuy2_reference = _FIDELITY.yuy2_round_trip(raw_reference)
        yuy2_observation = _FIDELITY.yuy2_round_trip(raw_observation)
        raw_rgb, raw_edge = _FIDELITY._signal(raw_reference, raw_observation, mask)
        encoded_rgb, encoded_edge = _FIDELITY._signal(yuy2_reference, yuy2_observation, mask)
        distortion = (
            _FIDELITY._distortion(raw_reference, yuy2_reference, mask)
            + _FIDELITY._distortion(raw_observation, yuy2_observation, mask)
        ) / 2.0
        rows.append({
            "observation_id": source["observation_id"],
            "expected_decision": source["expected_decision"],
            "variant_id": source["variant_id"],
            "safe_overlap_fraction": source["safe_overlap_fraction"],
            "raw_rgb_signal": raw_rgb,
            "yuy2_rgb_signal": encoded_rgb,
            "raw_edge_signal": raw_edge,
            "yuy2_edge_signal": encoded_edge,
            "rgb_retention": encoded_rgb / raw_rgb,
            "edge_retention": encoded_edge / raw_edge,
            "distortion_to_signal": distortion / raw_rgb,
        })
    visible = [row for row in rows if row["expected_decision"] == "VISIBLE"]
    abstain = [row for row in rows if row["expected_decision"] == "ABSTAIN"]
    if len(visible) != 48 or len(abstain) != 96:
        raise ValueError("unexpected decision inventory")
    worst_ratio = sorted(rows, key=lambda row: row["distortion_to_signal"], reverse=True)[:12]
    weakest_abstain = sorted(abstain, key=lambda row: row["yuy2_rgb_signal"])[:12]
    core = {
        "schema": SCHEMA,
        "status": "DIAGNOSTIC_ONLY_FROZEN_FAILURE_UNCHANGED",
        "frozen_result_file_sha256": sha256(frozen_result_path),
        "frozen_result_report_sha256": frozen["report_sha256"],
        "probe_manifest_file_sha256": sha256(manifest_path),
        "probe_dataset_sha256": manifest["dataset_sha256"],
        "population": {"rows": len(rows), "visible_rows": len(visible), "abstain_rows": len(abstain)},
        "visible_summary": summarize(visible),
        "abstain_summary": summarize(abstain),
        "worst_distortion_to_signal_rows": worst_ratio,
        "weakest_yuy2_abstain_rows": weakest_abstain,
        "findings": [
            "The worst YUY2 distortion ratio is a 10-percent visible boundary row with only 0.5307 raw RGB levels of signal; YUY2 retains 1.1035 of its RGB signal and 1.0169 of its edge signal.",
            "The overall YUY2 ratio failure is dominated by near-zero denominators among visible boundary probes rather than erased encoded contrast.",
            "Safety-relevant abstention rows still include three delivered RGB signals below two levels and seven below three levels, so camera-domain detectability remains unresolved.",
            "The frozen codec failure remains valid; this diagnostic cannot authorize training or alter a threshold.",
        ],
        "replacement_rule_constraints": [
            "Train on lossless renders converted to the simulated delivered YUY2 domain.",
            "Measure detectability in delivered YUY2 inputs rather than treating raw-to-YUY2 distortion ratio as the safety endpoint.",
            "Report near-zero delivered signals separately by expected decision, target, coverage, lighting, and scene.",
            "Do not invent an absolute physical detectability floor before the real-camera cable pilot.",
        ],
        "training_authorized": False,
        "evaluation_images_opened": 0,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "This is a synthetic training-only failure attribution, not a new gate or a physical detectability measurement.",
            "YUY2 simulation omits the real camera optics, ISP, exposure, noise, white balance, and materials.",
        ],
    }
    return {**core, "report_sha256": hashlib.sha256(canonical(core)).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-dir", type=Path, required=True)
    parser.add_argument("--frozen-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = diagnose(args.probe_dir, args.frozen_result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(report) + b"\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
