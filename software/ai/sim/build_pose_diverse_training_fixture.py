"""Build a dense static train/development pose fixture for Isaac rendering.

The fixture interpolates a governed zero-authority schedule only to place visual
meshes for synthetic perception renders. It is not a trajectory or controller
input and makes no reachability, dynamics, clearance, or execution claim.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "tactevra.ai_pose_diverse_training_fixture.v1"
EXPECTED_SOURCE_FILE_SHA256 = (
    "6a59ce143f5527c7a9ced09b08d5515644ea4fb859dd69691e08483eb020ee42"
)
CONSUMED_V14_FIXTURE_FILE_SHA256 = (
    "638e17a18feb79aa15864078ff80df37e69ebe6889710de08d98ed709013fb69"
)
CONSUMED_V14_FRACTIONS = {
    Fraction(2, 19), Fraction(5, 19), Fraction(8, 19),
    Fraction(11, 19), Fraction(14, 19), Fraction(17, 19),
}
POSE_DENOMINATOR = 389
POSE_PERMUTATION_STEP = 149
TARGET_POSE_COUNT = 96
DEVELOPMENT_INTERVAL = 4
JOINTS = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build(source: dict[str, Any], source_bytes: bytes) -> dict[str, Any]:
    if _sha256(source_bytes) != EXPECTED_SOURCE_FILE_SHA256:
        raise ValueError("source schedule file identity mismatch")
    if source.get("hardware_access") is not False \
            or source.get("physical_authority") is not False \
            or source.get("hardware_writes") != 0 \
            or source.get("physical_movements") != 0 \
            or source.get("controller_commands") != []:
        raise ValueError("source schedule crosses the zero-authority boundary")
    samples = source.get("samples")
    if not isinstance(samples, list) or len(samples) < 2:
        raise ValueError("source schedule has insufficient samples")
    if [row.get("sequence") for row in samples] != list(range(len(samples))):
        raise ValueError("source schedule sequence is not contiguous")

    denominator = len(samples) - 1
    original_joint_states = {
        tuple(float(row["joint_positions_rad"][name]) for name in JOINTS)
        for row in samples
    }
    generated_joint_states: set[tuple[float, ...]] = set()
    output_samples = []
    for candidate_rank in range(1, POSE_DENOMINATOR):
        numerator = (candidate_rank * POSE_PERMUTATION_STEP) % POSE_DENOMINATOR
        fraction = Fraction(numerator, POSE_DENOMINATOR)
        if fraction in CONSUMED_V14_FRACTIONS:
            raise RuntimeError("pose fixture reuses a consumed v14 fraction")
        position = fraction * denominator
        lower_index = position.numerator // position.denominator
        upper_index = lower_index + 1
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
        joint_positions = {
            name: (1.0 - alpha) * float(lower_joints[name])
            + alpha * float(upper_joints[name])
            for name in JOINTS
        }
        joint_state = tuple(joint_positions[name] for name in JOINTS)
        if joint_state in original_joint_states or joint_state in generated_joint_states:
            continue
        generated_joint_states.add(joint_state)
        output_index = len(output_samples) + 1
        split = (
            "development"
            if output_index % DEVELOPMENT_INTERVAL == 0
            else "training"
        )
        output_samples.append({
            "sequence": 2000 + output_index,
            "pose_id": f"pose_diverse_{split}_{output_index:03d}",
            "split": split,
            "phase": "STATIC_INTERPOLATED_POSE",
            "phase_endpoint": False,
            "action_index": None,
            "target_id": None,
            "source_interval": [lower_index, upper_index],
            "source_path_fraction": [fraction.numerator, fraction.denominator],
            "interpolation_alpha": alpha,
            "candidate_rank": candidate_rank,
            "joint_positions_rad": joint_positions,
            "expected_tool_tip_board_mm": [
                (1.0 - alpha) * float(left) + alpha * float(right)
                for left, right in zip(lower_tip, upper_tip, strict=True)
            ],
        })
        if len(output_samples) == TARGET_POSE_COUNT:
            break
    if len(output_samples) != TARGET_POSE_COUNT:
        raise RuntimeError("source schedule cannot supply enough fresh distinct render poses")

    split_counts = {
        split: sum(row["split"] == split for row in output_samples)
        for split in ("training", "development")
    }
    fixture: dict[str, Any] = {
        "schema": SCHEMA,
        "source": {
            "schedule_file_sha256": EXPECTED_SOURCE_FILE_SHA256,
            "schedule_bundle_sha256": source["bundle_sha256"],
            "sample_count": len(samples),
        },
        "method": "prime_modulus_permuted_path_interpolation_with_distinct_state_filter",
        "pose_denominator": POSE_DENOMINATOR,
        "pose_permutation_step": POSE_PERMUTATION_STEP,
        "target_pose_count": TARGET_POSE_COUNT,
        "development_interval": DEVELOPMENT_INTERVAL,
        "samples": output_samples,
        "sample_count": len(output_samples),
        "split_counts": split_counts,
        "consumed_evaluation_sources_excluded": [{
            "campaign": "rebalance-evaluation-v14",
            "fixture_file_sha256": CONSUMED_V14_FIXTURE_FILE_SHA256,
            "excluded_fraction_count": len(CONSUMED_V14_FRACTIONS),
        }],
        "scope": "SYNTHETIC_STATIC_PERCEPTION_TRAIN_DEVELOPMENT_ONLY",
        "controller_commands": [],
        "hardware_access": False,
        "physical_authority": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "interpolated states are static perception fixtures, not a motion trajectory",
            "dense samples cover one governed path and do not span arbitrary robot configurations",
            "no dynamics, collision, clearance, or reachability claim is made",
            "all coordinates are synthetic and unmeasured",
            "consumed v14 bytes and pose fractions are excluded from training and selection",
            "the fixture cannot qualify deployment or physical execution",
        ],
    }
    fixture["bundle_sha256"] = _sha256(_canonical(fixture))
    return fixture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_bytes = args.source.resolve(strict=True).read_bytes()
    fixture = build(json.loads(source_bytes), source_bytes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(
        (json.dumps(fixture, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
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
