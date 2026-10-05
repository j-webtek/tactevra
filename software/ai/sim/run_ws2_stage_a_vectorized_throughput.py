"""Measure the exact recipe/compliance-vectorized ordinary-key Stage A batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from integrations.mujoco_warp import key_press_physics_probe as probe
from ai.sim import keyboard_physical_neighborhoods as neighborhoods


ROOT = Path(__file__).resolve().parents[3]


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def value_sha(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fixture(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    claimed = fixture.pop("fixture_sha256")
    if value_sha(fixture) != claimed:
        raise ValueError("fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture["physical_authority"] is not False or any(fixture["counters"].values()):
        raise ValueError("authority violation")
    for binding in fixture["bindings"].values():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = ROOT / source
        if file_sha(source) != binding["sha256"]:
            raise ValueError(f"binding changed: {binding['path']}")
    return fixture


def load_bound(fixture: dict[str, Any]):
    campaign = probe.load_fixture(
        ROOT / fixture["bindings"]["campaign"]["path"], workspace=ROOT
    )
    execution = probe.load_execution_fixture(
        ROOT / fixture["bindings"]["execution"]["path"],
        workspace=ROOT,
        parent=campaign,
    )
    staged = probe.load_staged_fixture(
        ROOT / fixture["bindings"]["staged"]["path"],
        workspace=ROOT,
        parent=campaign,
        execution=execution,
    )
    mechanism = json.loads(
        (ROOT / fixture["bindings"]["mechanisms"]["path"]).read_text(encoding="utf-8")
    )
    claimed = mechanism.pop("fixture_sha256")
    if probe._sha_value(mechanism) != claimed:
        raise ValueError("mechanism fixture self-hash mismatch")
    mechanism["fixture_sha256"] = claimed
    neighborhood_fixture = neighborhoods.load_fixture(
        ROOT / fixture["bindings"]["physical_neighborhoods"]["path"]
    )
    physical = neighborhoods.deduplicated_neighborhoods(neighborhood_fixture)
    return campaign, execution, staged, mechanism, physical


def compliance_options(staged: dict[str, Any]) -> list[dict[str, Any]]:
    options = []
    for identity in staged["stage_a_coarse"]["throughput_selected_compliance"][
        "over_budget"
    ]:
        match = re.fullmatch(r"k([0-9.]+)_t([0-9.]+)", identity)
        if match is None:
            raise ValueError(f"invalid compliance identity: {identity}")
        options.append(
            {
                "compliance_id": identity,
                "stiffness_n_per_mm": float(match.group(1)),
                "travel_mm": float(match.group(2)),
            }
        )
    return options


def run_device(fixture: dict[str, Any], device: str) -> dict[str, Any]:
    campaign, execution, staged, mechanism, physical = load_bound(fixture)
    smoke = fixture["smoke"]
    stabilized = set(
        mechanism["mechanism_classes"]["STABILIZED_UNMEASURED"]["target_ids"]
    )
    wide_unknown = set(
        mechanism["mechanism_classes"]["WIDE_UNSTABILIZED_GEOMETRY_UNMEASURED"][
            "target_ids"
        ]
    )
    if smoke["target_id"] in stabilized | wide_unknown:
        raise ValueError("throughput representative is not an admitted ordinary key")
    rows = probe.stage_a_vectorized_ordinary_batch_rows(
        campaign, staged, target_id=smoke["target_id"]
    )
    physical_neighborhood = next(
        row
        for row in physical["neighborhoods"]
        if row["target_id"] == smoke["target_id"]
    )
    control = {
        "fixture_sha256": fixture["fixture_sha256"],
        "control": {
            "control_id": "ordinary-vectorized-throughput",
            "control_kind": "ACTUATION",
            "target_id": smoke["target_id"],
            "profile_id": smoke["profile_id"],
            "tip_id": smoke["tip_id"],
            "scenario_id": rows[0]["scenario_id"],
            "base_recipe_index": rows[0]["recipe_index"],
            "landing_sample_indices": [row["landing_sample_index"] for row in rows],
            "batch_rows": rows,
            "vectorized_world_controls": True,
            "recipe_override": {},
            "tool_compliance_model": "SERIES_QUASISTATIC",
            "tool_compliance_options": compliance_options(staged),
            "physical_keycap_half_extent_mm": smoke["physical_keycap_half_extent_mm"],
            "physical_neighborhood": physical_neighborhood["members"],
            "target_joint_index": physical_neighborhood["target_joint_index"],
            "switch_closure_window_ms": smoke["switch_closure_window_ms"],
        },
    }
    receipt = probe.run_smoke_worker(
        campaign,
        execution,
        workspace=ROOT,
        device_name=device,
        control=control,
    )
    expected = fixture["population"]["worlds_per_compiled_batch"]
    result = {
        "schema": "tactevra.ws2_stage_a_vectorized_throughput_device.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "device": device,
        "world_count": len(receipt["rows"]),
        "wall_elapsed_seconds": receipt["wall_elapsed_seconds"],
        "motion_steps": receipt["motion_steps"],
        "settle_pass": receipt["settle_pass"],
        "finite": receipt["finite"],
        "overflow_zero": receipt["overflow_zero"],
        "row_payload_sha256": value_sha(receipt["rows"]),
        "status": (
            "PASS_VECTORIZED_ORDINARY_DEVICE_SMOKE"
            if receipt["settle_pass"]
            and receipt["finite"]
            and receipt["overflow_zero"]
            and len(receipt["rows"]) == expected
            else "STOP_VECTORIZED_ORDINARY_DEVICE_SMOKE"
        ),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = value_sha(result)
    return result


def compare(
    fixture: dict[str, Any], left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    if left["device"] == right["device"]:
        raise ValueError("distinct devices required")
    if any(row["fixture_sha256"] != fixture["fixture_sha256"] for row in (left, right)):
        raise ValueError("fixture identity mismatch")
    batch_count = fixture["population"]["ordinary_compiled_batch_count"]
    device_batch_counts = {
        left["device"]: math.ceil(batch_count / 2),
        right["device"]: math.floor(batch_count / 2),
    }
    projected = {
        row["device"]: (
            float(row["wall_elapsed_seconds"])
            * device_batch_counts[row["device"]]
            / 3600.0
        )
        for row in (left, right)
    }
    projected_hours = max(projected.values())
    admitted = (
        all(
            row["status"] == "PASS_VECTORIZED_ORDINARY_DEVICE_SMOKE"
            for row in (left, right)
        )
        and projected_hours <= fixture["decision"]["maximum_two_gpu_hours"]
    )
    result = {
        "schema": "tactevra.ws2_stage_a_vectorized_throughput_comparison.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "device_compiled_batch_counts": device_batch_counts,
        "device_projected_hours": projected,
        "projected_two_gpu_wall_hours": projected_hours,
        "status": (
            "PASS_ORDINARY_VECTORIZED_THROUGHPUT"
            if admitted
            else "STOP_ORDINARY_VECTORIZED_THROUGHPUT"
        ),
        "stage_a_launch_authorized": False,
        "blocked_special_targets": fixture["population"]["blocked_special_targets"],
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = value_sha(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("device", "compare"))
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--device", choices=("cuda:0", "cuda:1"))
    parser.add_argument("--left", type=Path)
    parser.add_argument("--right", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = load_fixture(args.fixture)
    if args.mode == "device":
        if args.device is None:
            parser.error("device mode requires --device")
        result = run_device(fixture, args.device)
    else:
        if args.left is None or args.right is None:
            parser.error("compare mode requires --left and --right")
        result = compare(
            fixture,
            json.loads(args.left.read_text(encoding="utf-8")),
            json.loads(args.right.read_text(encoding="utf-8")),
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
