"""Freeze fresh grouped train/development poses for the v16 Isaac campaign.

The generator uses consumed v15 development failures only to identify source
interval neighborhoods for new training coverage. V15 rows cannot appear in
the new fixture, and source blocks adjacent to development blocks are excluded
from training to reduce path-neighborhood leakage.
"""

from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "tactevra.ai_grouped_neighborhood_training_fixture.v1"
EXPECTED_SOURCE_FILE_SHA256 = "6a59ce143f5527c7a9ced09b08d5515644ea4fb859dd69691e08483eb020ee42"
EXPECTED_V15_FIXTURE_FILE_SHA256 = "38e169e1b8b59d77785470b44e5feca8dad78fce18bc6dab8459ffa3f867ae0e"
EXPECTED_V15_DIAGNOSTIC_FILE_SHA256 = "a13a999c8c8ca279e72bdd11bca79d6803b291600f0e1bdce152542e250a482a"
POSE_DENOMINATOR = 1543
POSE_PERMUTATION_STEP = 613
SOURCE_BLOCK_WIDTH = 3
SOURCE_SAMPLE_COUNT = 133
SOURCE_BLOCK_COUNT = 44
TRAINING_POSE_COUNT = 256
DEVELOPMENT_POSE_COUNT = 64
DEVELOPMENT_BLOCKS = frozenset({1, 3, 7, 15, 17, 25, 27, 32, 37, 39})
DIAGNOSED_TRAINING_BLOCKS = frozenset({5, 10, 13, 20, 23, 30, 35})
TRAINING_BLOCKS = frozenset(
    block for block in range(SOURCE_BLOCK_COUNT)
    if block not in DEVELOPMENT_BLOCKS
    and all(abs(block - development) >= 2 for development in DEVELOPMENT_BLOCKS)
)
JOINTS = (
    "base_link_to_link1", "link1_to_link2", "link2_to_link3",
    "link3_to_link4", "link4_to_link5",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _verify_zero_authority(source: dict[str, Any]) -> None:
    if source.get("hardware_access") is not False \
            or source.get("physical_authority") is not False \
            or source.get("hardware_writes") != 0 \
            or source.get("physical_movements") != 0 \
            or source.get("controller_commands") != []:
        raise ValueError("source schedule crosses the zero-authority boundary")


def build(
    source: dict[str, Any], source_bytes: bytes,
    v15_fixture: dict[str, Any], v15_fixture_bytes: bytes,
    diagnostic: dict[str, Any], diagnostic_bytes: bytes,
) -> dict[str, Any]:
    if _sha256(source_bytes) != EXPECTED_SOURCE_FILE_SHA256:
        raise ValueError("source schedule file identity mismatch")
    if _sha256(v15_fixture_bytes) != EXPECTED_V15_FIXTURE_FILE_SHA256:
        raise ValueError("v15 fixture file identity mismatch")
    if _sha256(diagnostic_bytes) != EXPECTED_V15_DIAGNOSTIC_FILE_SHA256:
        raise ValueError("v15 diagnostic file identity mismatch")
    _verify_zero_authority(source)
    if v15_fixture.get("schema") != "tactevra.ai_pose_diverse_training_fixture.v1" \
            or v15_fixture.get("sample_count") != 96:
        raise ValueError("v15 consumed fixture contract mismatch")
    if diagnostic.get("schema") != "rocell.ai_pose_cluster_development_diagnostic.v1" \
            or diagnostic.get("evaluation_accessed") is not False \
            or diagnostic.get("candidate_promoted") is not False:
        raise ValueError("v15 diagnostic contract mismatch")
    failures = diagnostic.get("analysis", {}).get("failed_pose_clusters")
    if not isinstance(failures, list) or not failures:
        raise ValueError("v15 diagnostic has no failed pose clusters")
    diagnosed_blocks = {
        int(item["source_interval"][0]) // SOURCE_BLOCK_WIDTH for item in failures
    }
    if diagnosed_blocks != DIAGNOSED_TRAINING_BLOCKS:
        raise ValueError("diagnosed source blocks changed")
    if not DIAGNOSED_TRAINING_BLOCKS.issubset(TRAINING_BLOCKS):
        raise RuntimeError("diagnosed neighborhoods are not assigned to training")

    samples = source.get("samples")
    if not isinstance(samples, list) or len(samples) != SOURCE_SAMPLE_COUNT:
        raise ValueError("source schedule shape changed")
    if [row.get("sequence") for row in samples] != list(range(len(samples))):
        raise ValueError("source schedule sequence is not contiguous")
    consumed_fractions = {
        Fraction(*row["source_path_fraction"]) for row in v15_fixture["samples"]
    }
    denominator = len(samples) - 1
    original_states = {
        tuple(float(row["joint_positions_rad"][name]) for name in JOINTS)
        for row in samples
    }
    generated_states: set[tuple[float, ...]] = set()
    output: dict[str, list[dict[str, Any]]] = {"training": [], "development": []}
    block_counts: dict[str, Counter[int]] = {
        "training": Counter(), "development": Counter(),
    }
    targets = {"training": TRAINING_POSE_COUNT, "development": DEVELOPMENT_POSE_COUNT}
    split_blocks = {
        "training": sorted(TRAINING_BLOCKS),
        "development": sorted(DEVELOPMENT_BLOCKS),
    }
    block_quotas: dict[str, dict[int, int]] = {}
    for split, blocks in split_blocks.items():
        base, remainder = divmod(targets[split], len(blocks))
        block_quotas[split] = {
            block: base + (index < remainder)
            for index, block in enumerate(blocks)
        }

    for candidate_rank in range(1, POSE_DENOMINATOR):
        numerator = (candidate_rank * POSE_PERMUTATION_STEP) % POSE_DENOMINATOR
        fraction = Fraction(numerator, POSE_DENOMINATOR)
        if fraction in consumed_fractions:
            raise RuntimeError("candidate reuses a consumed v15 fraction")
        position = fraction * denominator
        lower_index = position.numerator // position.denominator
        upper_index = lower_index + 1
        block = lower_index // SOURCE_BLOCK_WIDTH
        split = (
            "development" if block in DEVELOPMENT_BLOCKS
            else "training" if block in TRAINING_BLOCKS else None
        )
        if split is None or block_counts[split][block] >= block_quotas[split][block]:
            continue
        alpha = float(position - lower_index)
        lower = samples[lower_index]
        upper = samples[upper_index]
        lower_joints = lower.get("joint_positions_rad")
        upper_joints = upper.get("joint_positions_rad")
        if tuple(lower_joints or {}) != JOINTS or tuple(upper_joints or {}) != JOINTS:
            raise ValueError("source schedule uses a noncanonical joint order")
        lower_tip = lower.get("expected_tool_tip_board_mm")
        upper_tip = upper.get("expected_tool_tip_board_mm")
        if not isinstance(lower_tip, list) or not isinstance(upper_tip, list) \
                or len(lower_tip) != 3 or len(upper_tip) != 3:
            raise ValueError("source schedule omits board-frame reference points")
        joints = {
            name: (1.0 - alpha) * float(lower_joints[name])
            + alpha * float(upper_joints[name])
            for name in JOINTS
        }
        state = tuple(joints[name] for name in JOINTS)
        if state in original_states or state in generated_states:
            continue
        generated_states.add(state)
        index = len(output[split]) + 1
        output[split].append({
            "pose_id": f"grouped_{split}_{index:03d}",
            "split": split,
            "source_block": block,
            "source_interval": [lower_index, upper_index],
            "source_path_fraction": [fraction.numerator, fraction.denominator],
            "interpolation_alpha": alpha,
            "candidate_rank": candidate_rank,
            "phase": "STATIC_INTERPOLATED_POSE",
            "phase_endpoint": False,
            "action_index": None,
            "target_id": None,
            "joint_positions_rad": joints,
            "expected_tool_tip_board_mm": [
                (1.0 - alpha) * float(left) + alpha * float(right)
                for left, right in zip(lower_tip, upper_tip, strict=True)
            ],
        })
        block_counts[split][block] += 1
        if all(len(output[name]) == targets[name] for name in targets):
            break
    if any(len(output[name]) != targets[name] for name in targets):
        raise RuntimeError("source schedule cannot supply the frozen grouped pose counts")
    if min(block_counts["training"][block] for block in TRAINING_BLOCKS) < 8:
        raise RuntimeError("training source-block coverage is below the frozen floor")
    if min(block_counts["development"][block] for block in DEVELOPMENT_BLOCKS) < 4:
        raise RuntimeError("development source-block coverage is below the frozen floor")

    ordered_samples = output["training"] + output["development"]
    for index, sample in enumerate(ordered_samples, start=1):
        sample["sequence"] = 3000 + index
    fixture: dict[str, Any] = {
        "schema": SCHEMA,
        "source": {
            "schedule_file_sha256": EXPECTED_SOURCE_FILE_SHA256,
            "schedule_bundle_sha256": source["bundle_sha256"],
            "sample_count": len(samples),
        },
        "consumed_design_evidence": {
            "v15_fixture_file_sha256": EXPECTED_V15_FIXTURE_FILE_SHA256,
            "v15_fixture_bundle_sha256": v15_fixture["bundle_sha256"],
            "v15_diagnostic_file_sha256": EXPECTED_V15_DIAGNOSTIC_FILE_SHA256,
            "v15_diagnostic_report_sha256": diagnostic["report_sha256"],
            "consumed_fraction_count": len(consumed_fractions),
            "diagnosed_training_blocks": sorted(DIAGNOSED_TRAINING_BLOCKS),
        },
        "method": "prime_permutation_with_balanced_three_interval_group_isolation_v1",
        "pose_denominator": POSE_DENOMINATOR,
        "pose_permutation_step": POSE_PERMUTATION_STEP,
        "source_block_width_intervals": SOURCE_BLOCK_WIDTH,
        "training_blocks": sorted(TRAINING_BLOCKS),
        "development_blocks": sorted(DEVELOPMENT_BLOCKS),
        "excluded_buffer_blocks": sorted(
            set(range(SOURCE_BLOCK_COUNT)) - TRAINING_BLOCKS - DEVELOPMENT_BLOCKS
        ),
        "minimum_training_poses_per_block": 8,
        "minimum_development_poses_per_block": 4,
        "samples": ordered_samples,
        "sample_count": len(ordered_samples),
        "split_counts": {name: len(output[name]) for name in output},
        "split_block_counts": {
            name: {str(block): count for block, count in sorted(block_counts[name].items())}
            for name in block_counts
        },
        "scope": "SYNTHETIC_STATIC_PERCEPTION_TRAIN_DEVELOPMENT_ONLY",
        "controller_commands": [],
        "hardware_access": False,
        "physical_authority": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "v15 development failures informed training neighborhoods, so v15 is consumed and cannot evaluate v16",
            "source-block isolation reduces adjacent path leakage but does not make poses physically independent",
            "interpolated states are static perception fixtures, not trajectories",
            "all coordinates and labels remain synthetic and unmeasured",
            "the fixture grants no localization, collision, controller, transport, permit, or physical authority",
        ],
    }
    fixture["bundle_sha256"] = _sha256(_canonical(fixture))
    return fixture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--v15-fixture", type=Path, required=True)
    parser.add_argument("--v15-diagnostic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_bytes = args.source.resolve(strict=True).read_bytes()
    fixture_bytes = args.v15_fixture.resolve(strict=True).read_bytes()
    diagnostic_bytes = args.v15_diagnostic.resolve(strict=True).read_bytes()
    fixture = build(
        json.loads(source_bytes), source_bytes,
        json.loads(fixture_bytes), fixture_bytes,
        json.loads(diagnostic_bytes), diagnostic_bytes,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes((json.dumps(fixture, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({
        "bundle_sha256": fixture["bundle_sha256"],
        "sample_count": fixture["sample_count"],
        "split_counts": fixture["split_counts"],
        "hardware_writes": 0,
        "physical_movements": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
