"""Attribute failures in a consumed pose-diverse development scorecard.

This tool is deliberately read only. It never loads evaluation rows, images, a
controller, or hardware. Its output is a development diagnostic, not a model
qualification or a permission to execute motion.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "rocell.ai_pose_cluster_development_diagnostic.v1"
SCOPE = "SYNTHETIC_DEVELOPMENT_ONLY_NO_QUALIFICATION"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _verified_claim(document: dict[str, Any], field: str, label: str) -> str:
    claimed = document.get(field)
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise ValueError(f"{label} has no valid {field}")
    core = {key: value for key, value in document.items() if key != field}
    if _sha256(_canonical(core)) != claimed:
        raise ValueError(f"{label} canonical hash mismatch")
    return claimed


def _load_development_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"development row {line_number} is not an object")
        if value.get("id") in {row.get("id") for row in rows}:
            raise ValueError("development row ids are not unique")
        if value.get("synthetic_only") is not True:
            raise ValueError("diagnostic accepts synthetic development rows only")
        if value.get("decision") not in {"abstain", "target_visible"}:
            raise ValueError("development row has unsupported decision")
        rows.append(value)
    if not rows:
        raise ValueError("development rows are empty")
    return rows


def diagnose(
    *,
    dataset_manifest_path: Path,
    development_rows_path: Path,
    scorecard_path: Path,
    pose_fixture_path: Path,
) -> dict[str, Any]:
    """Return deterministic pose-level attribution for one failed dev scorecard."""
    manifest = _read_json(dataset_manifest_path)
    dataset_sha = _verified_claim(manifest, "dataset_sha256", "dataset manifest")
    scorecard = _read_json(scorecard_path)
    scorecard_sha = _verified_claim(scorecard, "scorecard_sha256", "scorecard")
    fixture = _read_json(pose_fixture_path)
    fixture_sha = _verified_claim(fixture, "bundle_sha256", "pose fixture")

    if scorecard.get("schema") != "rocell.ai_pose_diverse_candidate.v1":
        raise ValueError("scorecard is not the frozen pose-diverse candidate")
    if scorecard.get("development_gate_met") is not False \
            or scorecard.get("promotion_status") != "FAILED_DEVELOPMENT_GATE":
        raise ValueError("diagnostic requires a failed development candidate")
    if scorecard.get("evaluation_group_present") is not False:
        raise ValueError("diagnostic refuses a scorecard with evaluation access")
    if scorecard.get("hardware_writes") != 0 \
            or scorecard.get("physical_movements") != 0 \
            or scorecard.get("physical_authority") is not False:
        raise ValueError("scorecard has prohibited physical effects or authority")
    if scorecard.get("dataset_sha256") != dataset_sha:
        raise ValueError("scorecard and dataset manifest hashes differ")
    if manifest.get("splits", {}).get("evaluation", {}).get("count") != 0:
        raise ValueError("diagnostic refuses a dataset containing evaluation rows")

    rows = _load_development_rows(development_rows_path)
    expected_count = manifest.get("splits", {}).get("development", {}).get("count")
    if expected_count != len(rows):
        raise ValueError("development row count differs from manifest")
    rows_by_id = {str(row["id"]): row for row in rows}
    if len(rows_by_id) != len(rows):
        raise ValueError("development row ids are not unique")

    samples = fixture.get("samples")
    if not isinstance(samples, list):
        raise ValueError("pose fixture samples are missing")
    development_samples = {
        str(sample["pose_id"]): sample
        for sample in samples
        if isinstance(sample, dict) and sample.get("split") == "development"
    }
    row_pose_ids = {str(row["pose_id"]) for row in rows}
    if row_pose_ids != set(development_samples):
        raise ValueError("fixture and development pose identities differ")

    bound_mm = float(scorecard["maximum_supported_planar_error_mm"])
    measurements = [
        item for item in scorecard.get("development_measurements", [])
        if max(abs(float(item["offset"]["x_mm"])), abs(float(item["offset"]["y_mm"])))
        <= bound_mm
    ]
    if not measurements:
        raise ValueError("scorecard has no measurements inside its selected bound")

    per_pose: dict[str, dict[str, Any]] = {}
    for pose_id in sorted(row_pose_ids):
        pose_rows = [row for row in rows if str(row["pose_id"]) == pose_id]
        sample = development_samples[pose_id]
        per_pose[pose_id] = {
            "pose_id": pose_id,
            "source_interval": sample["source_interval"],
            "source_path_fraction": sample["source_path_fraction"],
            "expected_tool_tip_board_mm": sample["expected_tool_tip_board_mm"],
            "abstain_row_count": sum(row["decision"] == "abstain" for row in pose_rows),
            "visible_row_count": sum(row["decision"] == "target_visible" for row in pose_rows),
            "missed_abstain_across_offsets": 0,
            "false_abstain_across_offsets": 0,
            "maximum_missed_abstain_at_one_offset": 0,
            "maximum_false_abstain_at_one_offset": 0,
            "missed_target_counts": Counter(),
            "missed_lighting_counts": Counter(),
        }

    unique_failures: set[tuple[str, float, float]] = set()
    for measurement in measurements:
        pose_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        offset = measurement["offset"]
        for failure in measurement["metrics"].get("failures", []):
            failure_id = str(failure.get("id"))
            row = rows_by_id.get(failure_id)
            if row is None:
                raise ValueError("scorecard failure does not bind a development row")
            key = (failure_id, float(offset["x_mm"]), float(offset["y_mm"]))
            if key in unique_failures:
                raise ValueError("duplicate failure at one offset")
            unique_failures.add(key)
            pose_id = str(row["pose_id"])
            if failure.get("expected") == "abstain" and failure.get("predicted") == "target_visible":
                pose_counts[pose_id][0] += 1
                per_pose[pose_id]["missed_target_counts"][str(row["target_id"])] += 1
                per_pose[pose_id]["missed_lighting_counts"][str(row["lighting_variant"])] += 1
            elif failure.get("expected") == "target_visible" and failure.get("predicted") == "abstain":
                pose_counts[pose_id][1] += 1
            else:
                raise ValueError("scorecard failure has inconsistent decisions")
        for pose_id, (missed, false) in pose_counts.items():
            item = per_pose[pose_id]
            item["missed_abstain_across_offsets"] += missed
            item["false_abstain_across_offsets"] += false
            item["maximum_missed_abstain_at_one_offset"] = max(
                item["maximum_missed_abstain_at_one_offset"], missed,
            )
            item["maximum_false_abstain_at_one_offset"] = max(
                item["maximum_false_abstain_at_one_offset"], false,
            )

    pose_records = []
    for item in per_pose.values():
        item["missed_target_counts"] = dict(sorted(item["missed_target_counts"].items()))
        item["missed_lighting_counts"] = dict(sorted(item["missed_lighting_counts"].items()))
        pose_records.append(item)
    pose_records.sort(key=lambda item: item["pose_id"])
    total_misses = sum(item["missed_abstain_across_offsets"] for item in pose_records)
    total_false = sum(item["false_abstain_across_offsets"] for item in pose_records)
    if total_misses == 0:
        raise ValueError("failed candidate has no missed abstentions to diagnose")

    pair_counts: Counter[tuple[str, str]] = Counter()
    for item in pose_records:
        for target_id, count in item["missed_target_counts"].items():
            pair_counts[(item["pose_id"], target_id)] += count
    ranked_pairs = sorted(pair_counts.items(), key=lambda pair: (-pair[1], pair[0]))
    dominant_pair, dominant_count = ranked_pairs[0]
    ranked_poses = sorted(
        pose_records,
        key=lambda item: (-item["missed_abstain_across_offsets"], item["pose_id"]),
    )
    top_two_count = sum(item["missed_abstain_across_offsets"] for item in ranked_poses[:2])
    bootstrap = scorecard["pose_cluster_bootstrap"]
    worst_miss_offset = max(
        bootstrap["offsets"], key=lambda item: item["missed_abstain_upper_95"],
    )

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "scope": SCOPE,
        "source": {
            "dataset_manifest_file_sha256": _sha256(dataset_manifest_path.read_bytes()),
            "dataset_sha256": dataset_sha,
            "development_rows_file_sha256": _sha256(development_rows_path.read_bytes()),
            "scorecard_file_sha256": _sha256(scorecard_path.read_bytes()),
            "scorecard_sha256": scorecard_sha,
            "model_sha256": scorecard["model_sha256"],
            "target_catalog_sha256": scorecard["target_catalog_sha256"],
            "pose_fixture_file_sha256": _sha256(pose_fixture_path.read_bytes()),
            "pose_fixture_sha256": fixture_sha,
            "selected_threshold": scorecard["selected_threshold"],
            "selected_bound_mm": bound_mm,
        },
        "analysis": {
            "development_pose_count": len(pose_records),
            "development_row_count": len(rows),
            "in_bound_offset_count": len(measurements),
            "missed_abstain_across_offsets": total_misses,
            "false_abstain_across_offsets": total_false,
            "poses_with_any_missed_abstain": sum(
                item["missed_abstain_across_offsets"] > 0 for item in pose_records
            ),
            "pose_target_pairs_with_any_missed_abstain": len(pair_counts),
            "dominant_missed_pose_target": {
                "pose_id": dominant_pair[0],
                "target_id": dominant_pair[1],
                "count": dominant_count,
                "fraction_of_all_misses": dominant_count / total_misses,
            },
            "top_two_pose_fraction_of_all_misses": top_two_count / total_misses,
            "worst_clustered_miss_offset": worst_miss_offset,
            "failed_pose_clusters": [
                item for item in ranked_poses if item["missed_abstain_across_offsets"] > 0
            ],
        },
        "v16_design_requirements": [
            "keep the v15 checkpoint rejected and do not change its threshold",
            "treat v15 development identities and outcomes as consumed design evidence and exclude them from v16 selection and evaluation",
            "create fresh train and development poses with source-interval groups disjoint across splits",
            "cover neighborhoods of failed source intervals and balance the observed failed target identities without copying consumed images",
            "predeclare architecture, training, split, cluster-bootstrap seed, and asymmetric gates before rendering",
            "open no untouched evaluation source unless the fresh v16 clustered development gate passes",
            "develop synchronized deterministic geometry projection in parallel as the primary known-self-occlusion path",
        ],
        "evaluation_accessed": False,
        "render_started": False,
        "candidate_promoted": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "the report analyzes one consumed synthetic development split only",
            "failure concentration is diagnostic and is not an unbiased generalization estimate",
            "source-path neighborhoods are correlated static visual states rather than independent robot trials",
            "no camera calibration, measured feedback, physical image, or deployment qualification is present",
            "the report grants no localization, collision, controller, transport, permit, or execution authority",
        ],
    }
    report["report_sha256"] = _sha256(_canonical(report))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--development-rows", type=Path, required=True)
    parser.add_argument("--scorecard", type=Path, required=True)
    parser.add_argument("--pose-fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = diagnose(
        dataset_manifest_path=args.dataset_manifest,
        development_rows_path=args.development_rows,
        scorecard_path=args.scorecard,
        pose_fixture_path=args.pose_fixture,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical(report) + b"\n")
    print(json.dumps({
        "output": str(args.output),
        "report_sha256": report["report_sha256"],
        "dominant_missed_pose_target": report["analysis"]["dominant_missed_pose_target"],
        "hardware_writes": 0,
        "physical_movements": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
