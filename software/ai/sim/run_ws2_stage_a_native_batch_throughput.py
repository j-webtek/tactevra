"""Measure WS2 Stage A throughput using its exact homogeneous batch shapes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from integrations.mujoco_warp import key_press_physics_probe as probe


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
    if fixture["physical_authority"] is not False or any(
        fixture["counters"].values()
    ):
        raise ValueError("authority violation")
    for binding in fixture["bindings"].values():
        if file_sha(ROOT / binding["path"]) != binding["sha256"]:
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
    batches = probe.stage_a_homogeneous_batches(campaign, staged, workspace=ROOT)
    return campaign, execution, batches


def run_device(fixture: dict[str, Any], device: str) -> dict[str, Any]:
    campaign, execution, batches = load_bound(fixture)
    smoke = fixture["smoke"]
    selected = [
        row
        for row in batches
        if row["profile_id"] == smoke["profile_id"]
        and row["tip_id"] == smoke["tip_id"]
        and row["recipe_index"] == smoke["recipe_index"]
        and row["tool_compliance"]["compliance_id"] == smoke["compliance_id"]
    ]
    if len(selected) != fixture["population"]["geometry_class_count"]:
        raise ValueError("representative geometry population changed")
    receipts = []
    for batch in selected:
        tool = {
            key: batch["tool_compliance"][key]
            for key in ("stiffness_n_per_mm", "travel_mm")
        }
        control = {
            "fixture_sha256": fixture["fixture_sha256"],
            "control": {
                "control_id": f"native-batch-{batch['batch_id']}",
                "control_kind": "ACTUATION",
                "target_id": batch["rows"][0]["target_id"],
                "profile_id": batch["profile_id"],
                "tip_id": batch["tip_id"],
                "scenario_id": batch["rows"][0]["scenario_id"],
                "base_recipe_index": batch["recipe_index"],
                "landing_sample_indices": [
                    row["landing_sample_index"] for row in batch["rows"]
                ],
                "batch_rows": batch["rows"],
                "recipe_override": {},
                "tool_compliance_model": "SERIES_QUASISTATIC",
                "tool_compliance": tool,
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
        receipts.append(
            {
                "half_extent_mm": batch["half_extent_mm"],
                "world_count": batch["world_count"],
                "wall_elapsed_seconds": receipt["wall_elapsed_seconds"],
                "motion_steps": receipt["motion_steps"],
                "settle_pass": receipt["settle_pass"],
                "finite": receipt["finite"],
                "overflow_zero": receipt["overflow_zero"],
                "row_count": len(receipt["rows"]),
                "depth_margin_summary": receipt["depth_margin_summary"],
                "failure_counts": dict(
                    sorted(
                        {
                            failure: sum(
                                probe.primary_failure(row) == failure
                                for row in receipt["rows"]
                            )
                            for failure in {
                                probe.primary_failure(row) for row in receipt["rows"]
                            }
                        }.items()
                    )
                ),
                "row_payload_sha256": value_sha(receipt["rows"]),
            }
        )
    result = {
        "schema": "tactevra.ws2_stage_a_native_batch_throughput_device.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "device": device,
        "receipts": receipts,
        "status": (
            "PASS_NATIVE_BATCH_DEVICE_SMOKE"
            if all(
                row["settle_pass"]
                and row["finite"]
                and row["overflow_zero"]
                and row["row_count"] == row["world_count"]
                for row in receipts
            )
            else "STOP_NATIVE_BATCH_DEVICE_SMOKE"
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
    if any(
        row["fixture_sha256"] != fixture["fixture_sha256"]
        for row in (left, right)
    ):
        raise ValueError("fixture identity mismatch")
    _, _, batches = load_bound(fixture)
    projected = {}
    for device_result in (left, right):
        timing = {
            tuple(row["half_extent_mm"]): row["wall_elapsed_seconds"]
            for row in device_result["receipts"]
        }
        projected[device_result["device"]] = sum(
            timing[tuple(batch["half_extent_mm"])]
            for batch in batches
            if batch["device"] == device_result["device"]
        ) / 3600.0
    projected_hours = max(projected.values())
    pass_smoke = all(
        row["status"] == "PASS_NATIVE_BATCH_DEVICE_SMOKE"
        for row in (left, right)
    )
    admitted = (
        pass_smoke
        and projected_hours <= fixture["decision"]["maximum_two_gpu_hours"]
    )
    result = {
        "schema": "tactevra.ws2_stage_a_native_batch_throughput_comparison.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "device_projected_hours": projected,
        "projected_two_gpu_wall_hours": projected_hours,
        "status": (
            "PASS_STAGE_A_NATIVE_BATCH_LAUNCH"
            if admitted
            else "STOP_STAGE_A_NATIVE_BATCH_LAUNCH"
        ),
        "prior_uniform_projection_used_for_launch": False,
        "device_receipt_sha256": [left["receipt_sha256"], right["receipt_sha256"]],
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
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
