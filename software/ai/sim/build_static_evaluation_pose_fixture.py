"""Build fresh static render poses from a zero-authority governed schedule.

The output is an AI perception fixture. Interpolation is used only to place a
visual mesh at deterministic poses. It is not a trajectory, command, collision
screen, controller input, or physical qualification.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "tactevra.ai_static_interpolated_pose_fixture.v1"
EXPECTED_SOURCE_FILE_SHA256 = (
    "6a59ce143f5527c7a9ced09b08d5515644ea4fb859dd69691e08483eb020ee42"
)
INTERPOLATION_FRACTIONS = (
    Fraction(2, 19), Fraction(5, 19), Fraction(8, 19),
    Fraction(11, 19), Fraction(14, 19), Fraction(17, 19),
)
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
    output_samples = []
    for output_index, fraction in enumerate(INTERPOLATION_FRACTIONS, start=1):
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
        output_samples.append({
            "sequence": 1000 + output_index,
            "phase": "STATIC_INTERPOLATED_POSE",
            "phase_endpoint": False,
            "action_index": None,
            "target_id": None,
            "source_interval": [lower_index, upper_index],
            "source_path_fraction": [fraction.numerator, fraction.denominator],
            "interpolation_alpha": alpha,
            "joint_positions_rad": {
                name: (1.0 - alpha) * float(lower_joints[name])
                + alpha * float(upper_joints[name])
                for name in JOINTS
            },
            "expected_tool_tip_board_mm": [
                (1.0 - alpha) * float(left) + alpha * float(right)
                for left, right in zip(lower_tip, upper_tip, strict=True)
            ],
        })

    original_joint_states = {
        tuple(float(row["joint_positions_rad"][name]) for name in JOINTS)
        for row in samples
    }
    generated_joint_states = [
        tuple(row["joint_positions_rad"][name] for name in JOINTS)
        for row in output_samples
    ]
    if len(set(generated_joint_states)) != len(generated_joint_states) \
            or any(state in original_joint_states for state in generated_joint_states):
        raise RuntimeError("generated render poses are not fresh and distinct")

    fixture: dict[str, Any] = {
        "schema": SCHEMA,
        "source": {
            "schedule_file_sha256": EXPECTED_SOURCE_FILE_SHA256,
            "schedule_bundle_sha256": source["bundle_sha256"],
            "sample_count": len(samples),
        },
        "method": "linear_joint_interpolation_at_predeclared_rational_path_fractions",
        "samples": output_samples,
        "sample_count": len(output_samples),
        "scope": "SYNTHETIC_STATIC_PERCEPTION_RENDER_ONLY",
        "controller_commands": [],
        "hardware_access": False,
        "physical_authority": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "interpolated states are static perception fixtures, not a motion trajectory",
            "no dynamics, collision, clearance, or reachability claim is made",
            "source and generated coordinates are synthetic and unmeasured",
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
    args.output.write_text(
        json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps({
        "bundle_sha256": fixture["bundle_sha256"],
        "sample_count": fixture["sample_count"],
        "hardware_writes": 0,
        "physical_movements": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
