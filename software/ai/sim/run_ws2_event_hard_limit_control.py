"""Run the frozen compression-aware WS2 event hard-limit positive control."""

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

from ai.sim import run_ws2_event_terminated_press as parent  # noqa: E402


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
        raise ValueError("hard-limit control fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture["physical_authority"] is not False or any(fixture["counters"].values()):
        raise ValueError("hard-limit control has nonzero authority")
    for name, binding in fixture["bindings"].items():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = ROOT / source
        if file_sha(source) != binding["sha256"]:
            raise ValueError(f"hard-limit control binding changed: {name}")
    design = fixture["design"]
    actuation = float(design["actuation_key_travel_mm"])
    bottom = float(design["bottom_out_key_travel_mm"])
    key_k = float(design["key_stiffness_n_per_mm"])
    tool_k = float(design["tool_stiffness_n_per_mm"])
    expected_actuation_command = actuation + key_k * actuation / tool_k
    expected_bottom_command = bottom + key_k * bottom / tool_k
    if (
        abs(
            expected_actuation_command
            - float(design["actuation_plus_tool_compression_mm"])
        )
        > 1e-12
    ):
        raise ValueError("actuation-plus-compression derivation changed")
    if (
        abs(
            expected_bottom_command
            - float(design["bottom_out_plus_tool_compression_mm"])
        )
        > 1e-12
    ):
        raise ValueError("bottom-out-plus-compression derivation changed")
    hard = float(design["hard_depth_limit_mm"])
    if not expected_actuation_command < hard < expected_bottom_command:
        raise ValueError("hard limit is not inside the declared compliant window")
    return fixture


def _control(
    fixture: dict[str, Any], parent_fixture: dict[str, Any], physical: dict[str, Any]
) -> dict[str, Any]:
    design = fixture["design"]
    control = parent._control(
        parent_fixture,
        physical=physical,
        target_id=design["target_id"],
        profile_id=design["profile_id"],
        scenario_id=design["scenario_id"],
        latency_ms=float(design["latency_ms"]),
        mode="MATCHING",
        approach_mm_s=float(design["descent_speed_mm_s"]),
    )
    control["fixture_sha256"] = fixture["fixture_sha256"]
    payload = control["control"]
    payload["control_id"] = design["control_id"]
    payload["batch_rows"] = [
        {
            "target_id": design["target_id"],
            "scenario_id": design["scenario_id"],
            "landing_sample_index": index,
            "vertical_origin_offset_mm": float(design["vertical_origin_offset_mm"]),
        }
        for index in design["landing_sample_indices"]
    ]
    payload["landing_sample_indices"] = design["landing_sample_indices"]
    payload["event_termination"]["hard_depth_limit_mm"] = float(
        design["hard_depth_limit_mm"]
    )
    return control


def run_device(fixture: dict[str, Any], device: str) -> dict[str, Any]:
    if device not in fixture["design"]["devices"]:
        raise ValueError("device outside frozen hard-limit control")
    parent_path = ROOT / fixture["bindings"]["parent_fixture"]["path"]
    parent_fixture = parent.load_fixture(parent_path)
    campaign, execution, physical = parent.load_bound(parent_fixture)
    receipt = parent.probe.run_smoke_worker(
        campaign,
        execution,
        workspace=ROOT,
        device_name=device,
        control=_control(fixture, parent_fixture, physical),
    )
    rows = receipt["rows"]
    hard = float(fixture["design"]["hard_depth_limit_mm"])
    events_before_limit = [
        bool(row["event_received"])
        and not row["late_event_ignored"]
        and row["retract_start_displacement_mm"] < hard
        for row in rows
    ]
    result = {
        "schema": "tactevra.ws2_event_hard_limit_control_result.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "device": device,
        "row_count": len(rows),
        "event_before_hard_limit_count": sum(events_before_limit),
        "actuation_count": sum(row["actuation_count"] == 1 for row in rows),
        "admitted_count": sum(row["admitted"] for row in rows),
        "release_complete_count": sum(row["release_complete"] for row in rows),
        "bottom_out_count": sum(row["bottom_out_overflow"] for row in rows),
        "minimum_retract_start_margin_mm": min(
            hard - row["retract_start_displacement_mm"] for row in rows
        ),
        "maximum_closure_ms": max(row["dwell_above_actuation_ms"] for row in rows),
        "primary_failure_counts": {
            failure: sum(parent.probe.primary_failure(row) == failure for row in rows)
            for failure in sorted({parent.probe.primary_failure(row) for row in rows})
        },
        "row_payload_sha256": value_sha(rows),
        "event_path_positive_control_pass": all(events_before_limit)
        and all(row["actuation_count"] == 1 for row in rows)
        and not any(row["bottom_out_overflow"] for row in rows),
        "full_press_admission_pass": all(row["admitted"] for row in rows),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "controller_command_count": 0,
        "physical_authority": False,
    }
    result["status"] = (
        "PASS_EVENT_BEFORE_LIMIT_FULL_ADMISSION"
        if result["event_path_positive_control_pass"]
        and result["full_press_admission_pass"]
        else "PASS_EVENT_BEFORE_LIMIT_RELEASE_OR_OTHER_STOP"
        if result["event_path_positive_control_pass"]
        else "STOP_EVENT_NOT_BEFORE_LIMIT"
    )
    result["receipt_sha256"] = value_sha(result)
    return result


def compare_devices(
    fixture: dict[str, Any], left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    if left["device"] == right["device"]:
        raise ValueError("comparison requires distinct devices")
    if any(row["fixture_sha256"] != fixture["fixture_sha256"] for row in (left, right)):
        raise ValueError("hard-limit control fixture mismatch")
    excluded = {"device", "receipt_sha256"}
    exact = ({k: v for k, v in left.items() if k not in excluded}) == (
        {k: v for k, v in right.items() if k not in excluded}
    )
    result = {
        "schema": "tactevra.ws2_event_hard_limit_control_comparison.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "cross_gpu_exact": exact,
        "device_receipts": {
            left["device"]: left["receipt_sha256"],
            right["device"]: right["receipt_sha256"],
        },
        "status": "PASS_EXACT_CONTROL_COMPARISON" if exact else "STOP_GPU_DISAGREEMENT",
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
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--device", choices=("cuda:0", "cuda:1"))
    parser.add_argument("--left", type=Path)
    parser.add_argument("--right", type=Path)
    parser.add_argument("--output", required=True, type=Path)
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
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
