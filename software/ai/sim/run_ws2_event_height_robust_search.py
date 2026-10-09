"""Bounded height-robust hard-limit search for event-terminated WS2 presses."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

SOFTWARE_ROOT = Path(__file__).resolve().parents[2]
if str(SOFTWARE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_ROOT))

from ai.sim import run_ws2_event_terminated_press as event_runner  # noqa: E402
from integrations.mujoco_warp import key_press_physics_probe as probe  # noqa: E402

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
        raise ValueError("height-robust fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture["physical_authority"] is not False or any(fixture["counters"].values()):
        raise ValueError("height-robust fixture has nonzero authority")
    for name, binding in fixture["bindings"].items():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = ROOT / source
        if file_sha(source) != binding["sha256"]:
            raise ValueError(f"height-robust binding changed: {name}")
    parent = event_runner.load_fixture(
        ROOT / fixture["bindings"]["parent_fixture"]["path"]
    )
    if (
        parent["fixture_sha256"]
        != fixture["bindings"]["parent_fixture"]["fixture_sha256"]
    ):
        raise ValueError("height-robust parent identity changed")
    design = fixture["design"]
    if design["height_offset_mm_samples"] != [
        -1.0,
        -0.75,
        -0.5,
        -0.25,
        0.0,
        0.25,
        0.5,
        0.75,
        1.0,
    ]:
        raise ValueError("height robustness population changed")
    if (
        sorted(design["hard_depth_limit_mm_candidates"])
        != design["hard_depth_limit_mm_candidates"]
    ):
        raise ValueError("hard limits must be ordered shallow to deep")
    if design["selection_rule"] != (
        "SELECT_DEEPEST_CANDIDATE_ONLY_IF_EVERY_MATCHING_EVENT_ROW_ADMITS_AND_"
        "EVERY_NO_EVENT_ROW_RELEASES_WITH_ZERO_REPEAT_ZERO_BOTTOM_OUT_AND_ZERO_RETRY"
    ):
        raise ValueError("height-robust selection rule changed")
    return fixture


def control_for(
    fixture: dict[str, Any],
    parent: dict[str, Any],
    physical: dict[str, Any],
    *,
    target_id: str,
    scenario_id: str,
    latency_ms: float,
    hard_limit_mm: float,
    mode: str,
) -> dict[str, Any]:
    design = fixture["design"]
    control = event_runner._control(
        parent,
        physical=physical,
        target_id=target_id,
        profile_id=design["profile_id"],
        scenario_id=scenario_id,
        latency_ms=latency_ms,
        mode=mode,
        approach_mm_s=design["approach_mm_s"],
    )
    body = control["control"]
    body["control_id"] = (
        f"{target_id}-{scenario_id}-{mode}-latency-{latency_ms:g}"
        f"-limit-{hard_limit_mm:g}"
    )
    body["recipe_override"].update(
        {
            "press_depth_mm": hard_limit_mm,
            "approach_mm_s": design["approach_mm_s"],
        }
    )
    body["event_termination"]["hard_depth_limit_mm"] = hard_limit_mm
    body["batch_rows"] = [
        {
            "target_id": target_id,
            "scenario_id": scenario_id,
            "landing_sample_index": landing_index,
            "vertical_origin_offset_mm": height_offset,
        }
        for height_offset in design["height_offset_mm_samples"]
        for landing_index in design["landing_sample_indices"]
    ]
    return control


def _band(rows: list[dict[str, Any]], maximum_absolute_offset: float) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if abs(float(row["vertical_origin_offset_mm"])) <= maximum_absolute_offset
    ]
    return {
        "maximum_absolute_height_offset_mm": maximum_absolute_offset,
        "row_count": len(selected),
        "admitted_count": sum(row["admitted"] for row in selected),
        "bottom_out_count": sum(row["bottom_out_overflow"] for row in selected),
        "auto_repeat_count": sum(row["auto_repeat_count"] for row in selected),
        "partial_press_count": sum(row["partial_press"] for row in selected),
        "minimum_depth_margin_mm": min(
            row["minimum_depth_margin_mm"] for row in selected
        ),
    }


def run_device(fixture: dict[str, Any], device: str) -> dict[str, Any]:
    design = fixture["design"]
    if device not in design["devices"]:
        raise ValueError("device outside height-robust fixture")
    parent = event_runner.load_fixture(
        ROOT / fixture["bindings"]["parent_fixture"]["path"]
    )
    campaign, execution, physical = event_runner.load_bound(parent)
    matching_by_limit: dict[float, list[dict[str, Any]]] = {
        float(limit): [] for limit in design["hard_depth_limit_mm_candidates"]
    }
    no_event_by_limit: dict[float, list[dict[str, Any]]] = {
        float(limit): [] for limit in design["hard_depth_limit_mm_candidates"]
    }
    for hard_limit in design["hard_depth_limit_mm_candidates"]:
        hard_limit = float(hard_limit)
        for target_id in design["target_ids"]:
            for scenario_id in design["scenario_ids"]:
                for latency_ms in design["latency_ms_samples"]:
                    receipt = probe.run_smoke_worker(
                        campaign,
                        execution,
                        workspace=ROOT,
                        device_name=device,
                        control=control_for(
                            fixture,
                            parent,
                            physical,
                            target_id=target_id,
                            scenario_id=scenario_id,
                            latency_ms=float(latency_ms),
                            hard_limit_mm=hard_limit,
                            mode="MATCHING",
                        ),
                    )
                    matching_by_limit[hard_limit].extend(receipt["rows"])
                no_event = probe.run_smoke_worker(
                    campaign,
                    execution,
                    workspace=ROOT,
                    device_name=device,
                    control=control_for(
                        fixture,
                        parent,
                        physical,
                        target_id=target_id,
                        scenario_id=scenario_id,
                        latency_ms=max(design["latency_ms_samples"]),
                        hard_limit_mm=hard_limit,
                        mode="NO_EVENT",
                    ),
                )
                no_event_by_limit[hard_limit].extend(no_event["rows"])

    limit_rows = []
    eligible = []
    payload = {}
    for hard_limit in map(float, design["hard_depth_limit_mm_candidates"]):
        matching = matching_by_limit[hard_limit]
        no_event = no_event_by_limit[hard_limit]
        matching_pass = all(row["admitted"] for row in matching)
        no_event_pass = all(
            row["no_event_before_hard_limit"]
            and row["release_complete"]
            and not row["bottom_out_overflow"]
            and row["auto_repeat_count"] == 0
            and row["retry_count"] == 0
            for row in no_event
        )
        admitted = matching_pass and no_event_pass
        if admitted:
            eligible.append(hard_limit)
        limit_rows.append(
            {
                "hard_depth_limit_mm": hard_limit,
                "eligible": admitted,
                "matching_row_count": len(matching),
                "matching_admitted_count": sum(row["admitted"] for row in matching),
                "matching_bottom_out_count": sum(
                    row["bottom_out_overflow"] for row in matching
                ),
                "matching_auto_repeat_count": sum(
                    row["auto_repeat_count"] for row in matching
                ),
                "matching_partial_press_count": sum(
                    row["partial_press"] for row in matching
                ),
                "matching_bands": [
                    _band(matching, width)
                    for width in design["reported_height_bands_mm"]
                ],
                "no_event_row_count": len(no_event),
                "no_event_bottom_out_count": sum(
                    row["bottom_out_overflow"] for row in no_event
                ),
                "no_event_auto_repeat_count": sum(
                    row["auto_repeat_count"] for row in no_event
                ),
                "no_event_release_count": sum(
                    row["release_complete"] for row in no_event
                ),
                "no_event_failure_count": sum(
                    row["no_event_before_hard_limit"] for row in no_event
                ),
            }
        )
        payload[str(hard_limit)] = {"matching": matching, "no_event": no_event}
    selected = max(eligible) if eligible else None
    result = {
        "schema": "tactevra.ws2_event_height_robust_search_device.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "device": device,
        "limit_results": limit_rows,
        "selected_hard_depth_limit_mm": selected,
        "status": (
            "PASS_HEIGHT_ROBUST_EVENT_HARD_LIMIT"
            if selected is not None
            else "STOP_NO_HEIGHT_ROBUST_EVENT_HARD_LIMIT"
        ),
        "row_payload_sha256": value_sha(payload),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "controller_command_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = value_sha(result)
    return result


def compare_devices(
    fixture: dict[str, Any], left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    if left["fixture_sha256"] != fixture["fixture_sha256"]:
        raise ValueError("left result is not bound to the requested fixture")
    if right["fixture_sha256"] != fixture["fixture_sha256"]:
        raise ValueError("right result is not bound to the requested fixture")
    if left["device"] == right["device"]:
        raise ValueError("comparison requires distinct devices")

    def comparable(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in row.items()
            if key not in {"device", "receipt_sha256"}
        }

    exact = comparable(left) == comparable(right)
    selected = left["selected_hard_depth_limit_mm"] if exact else None
    result = {
        "schema": "tactevra.ws2_event_height_robust_search_comparison.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "cross_gpu_exact": exact,
        "selected_hard_depth_limit_mm": selected,
        "status": (
            "PASS_HEIGHT_ROBUST_EVENT_HARD_LIMIT_COMPARISON"
            if exact and selected is not None
            else "STOP_HEIGHT_ROBUST_EVENT_HARD_LIMIT_COMPARISON"
        ),
        "expansion_authorized": exact and selected is not None,
        "device_receipts": {
            left["device"]: left["receipt_sha256"],
            right["device"]: right["receipt_sha256"],
        },
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "controller_command_count": 0,
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
        result = compare_devices(
            fixture,
            json.loads(args.left.read_text(encoding="utf-8")),
            json.loads(args.right.read_text(encoding="utf-8")),
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
