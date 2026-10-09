"""Force-bounded WS2 event termination and immediate-limit retraction search."""

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

from ai.sim import run_ws2_event_height_robust_search as height_runner  # noqa: E402
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
        raise ValueError("force-guard fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture["physical_authority"] is not False or any(fixture["counters"].values()):
        raise ValueError("force-guard fixture has nonzero authority")
    for name, binding in fixture["bindings"].items():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = ROOT / source
        if file_sha(source) != binding["sha256"]:
            raise ValueError(f"force-guard binding changed: {name}")
    predecessor = height_runner.load_fixture(
        ROOT / fixture["bindings"]["predecessor_fixture"]["path"]
    )
    if (
        predecessor["fixture_sha256"]
        != fixture["bindings"]["predecessor_fixture"]["fixture_sha256"]
    ):
        raise ValueError("force-guard predecessor identity changed")
    design = fixture["design"]
    if design["selection_rule"] != (
        "REQUIRE_ALL_MATCHING_AND_NO_EVENT_ROWS_PASS_FORCE_BOUNDED_RULES_THEN_"
        "MINIMIZE_WORST_FORCE_THEN_SPEED_THEN_HARD_LIMIT"
    ):
        raise ValueError("force-guard selection rule changed")
    if design["no_event_response"] != (
        "IMMEDIATE_RETRACT_AT_HARD_LIMIT_NO_DWELL_REPORT_FAILED_PRESS_NO_RETRY"
    ):
        raise ValueError("force-guard no-event response changed")
    if design["bottom_out_treatment"] != "DIAGNOSTIC_ONLY_FORCE_IS_GATE":
        raise ValueError("force-guard bottom-out treatment changed")
    if design["hard_depth_limit_mm_candidates"] != [5.8, 6.1, 6.4]:
        raise ValueError("force-guard hard-limit grid changed")
    if design["approach_mm_s_candidates"] != [12.0, 16.0, 20.0, 24.0, 32.0]:
        raise ValueError("force-guard speed grid changed")
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
        raise ValueError("force-guard height population changed")
    if design["maximum_contact_force_n"] != 1.4104166666666667:
        raise ValueError("force-guard force ceiling changed")
    return fixture


def control_for(
    fixture: dict[str, Any],
    predecessor: dict[str, Any],
    physical: dict[str, Any],
    *,
    target_id: str,
    scenario_id: str,
    latency_ms: float,
    hard_limit_mm: float,
    approach_mm_s: float,
    mode: str,
) -> dict[str, Any]:
    control = height_runner.control_for(
        predecessor,
        event_runner.load_fixture(
            ROOT / predecessor["bindings"]["parent_fixture"]["path"]
        ),
        physical,
        target_id=target_id,
        scenario_id=scenario_id,
        latency_ms=latency_ms,
        hard_limit_mm=hard_limit_mm,
        mode=mode,
    )
    body = control["control"]
    body["control_id"] += f"-speed-{approach_mm_s:g}"
    body["recipe_override"]["approach_mm_s"] = approach_mm_s
    return control


def _force_pass(row: dict[str, Any], ceiling_n: float) -> bool:
    return (
        float(row["peak_required_force_n"]) <= ceiling_n
        and float(row["peak_tool_force_n"]) <= ceiling_n
    )


def _matching_pass(row: dict[str, Any], ceiling_n: float) -> bool:
    return bool(
        row["actuation_count"] == 1
        and row["auto_repeat_count"] == 0
        and not row["neighbor_contact"]
        and row["release_complete"]
        and _force_pass(row, ceiling_n)
        and row.get("debounce_hold_complete", True)
        and row["event_received"]
        and not row["no_event_before_hard_limit"]
        and not row["wrong_key_event"]
        and not row["late_event_ignored"]
        and row["retry_count"] == 0
    )


def _no_event_pass(row: dict[str, Any], ceiling_n: float, hard_limit_mm: float) -> bool:
    return bool(
        row["no_event_before_hard_limit"]
        and not row["event_received"]
        and row["retract_started"]
        and abs(float(row["retract_start_displacement_mm"]) - hard_limit_mm) <= 1e-12
        and row["release_complete"]
        and row["auto_repeat_count"] == 0
        and not row["neighbor_contact"]
        and _force_pass(row, ceiling_n)
        and row["retry_count"] == 0
    )


def _summary(
    rows: list[dict[str, Any]],
    *,
    ceiling_n: float,
    hard_limit_mm: float,
    matching: bool,
    maximum_absolute_offset_mm: float,
) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if abs(float(row["vertical_origin_offset_mm"])) <= maximum_absolute_offset_mm
    ]
    gate = (
        (lambda row: _matching_pass(row, ceiling_n))
        if matching
        else (lambda row: _no_event_pass(row, ceiling_n, hard_limit_mm))
    )
    return {
        "maximum_absolute_height_offset_mm": maximum_absolute_offset_mm,
        "row_count": len(selected),
        "pass_count": sum(gate(row) for row in selected),
        "actuation_count": sum(row["actuation_count"] > 0 for row in selected),
        "partial_press_count": sum(row["partial_press"] for row in selected),
        "auto_repeat_row_count": sum(row["auto_repeat_count"] > 0 for row in selected),
        "bottom_out_row_count": sum(row["bottom_out_overflow"] for row in selected),
        "force_failure_count": sum(not _force_pass(row, ceiling_n) for row in selected),
        "release_failure_count": sum(not row["release_complete"] for row in selected),
        "maximum_required_force_n": max(
            float(row["peak_required_force_n"]) for row in selected
        ),
        "maximum_tool_force_n": max(
            float(row["peak_tool_force_n"]) for row in selected
        ),
        "maximum_closure_ms": max(
            float(row["dwell_above_actuation_ms"]) for row in selected
        ),
    }


def run_device(fixture: dict[str, Any], device: str) -> dict[str, Any]:
    design = fixture["design"]
    if device not in design["devices"]:
        raise ValueError("device outside force-guard fixture")
    predecessor = height_runner.load_fixture(
        ROOT / fixture["bindings"]["predecessor_fixture"]["path"]
    )
    parent = event_runner.load_fixture(
        ROOT / predecessor["bindings"]["parent_fixture"]["path"]
    )
    campaign, execution, physical = event_runner.load_bound(parent)
    ceiling_n = float(design["maximum_contact_force_n"])
    results = []
    payload: dict[str, Any] = {}
    eligible = []
    for approach_speed in design["approach_mm_s_candidates"]:
        for hard_limit in design["hard_depth_limit_mm_candidates"]:
            approach_speed = float(approach_speed)
            hard_limit = float(hard_limit)
            matching_rows: list[dict[str, Any]] = []
            no_event_rows: list[dict[str, Any]] = []
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
                                predecessor,
                                physical,
                                target_id=target_id,
                                scenario_id=scenario_id,
                                latency_ms=float(latency_ms),
                                hard_limit_mm=hard_limit,
                                approach_mm_s=approach_speed,
                                mode="MATCHING",
                            ),
                        )
                        matching_rows.extend(receipt["rows"])
                    no_event = probe.run_smoke_worker(
                        campaign,
                        execution,
                        workspace=ROOT,
                        device_name=device,
                        control=control_for(
                            fixture,
                            predecessor,
                            physical,
                            target_id=target_id,
                            scenario_id=scenario_id,
                            latency_ms=max(design["latency_ms_samples"]),
                            hard_limit_mm=hard_limit,
                            approach_mm_s=approach_speed,
                            mode="NO_EVENT",
                        ),
                    )
                    no_event_rows.extend(no_event["rows"])
            matching_pass = all(_matching_pass(row, ceiling_n) for row in matching_rows)
            no_event_pass = all(
                _no_event_pass(row, ceiling_n, hard_limit) for row in no_event_rows
            )
            candidate_pass = matching_pass and no_event_pass
            summaries = {
                "matching": [
                    _summary(
                        matching_rows,
                        ceiling_n=ceiling_n,
                        hard_limit_mm=hard_limit,
                        matching=True,
                        maximum_absolute_offset_mm=band,
                    )
                    for band in design["reported_height_bands_mm"]
                ],
                "no_event": [
                    _summary(
                        no_event_rows,
                        ceiling_n=ceiling_n,
                        hard_limit_mm=hard_limit,
                        matching=False,
                        maximum_absolute_offset_mm=band,
                    )
                    for band in design["reported_height_bands_mm"]
                ],
            }
            worst_force = max(
                max(float(row["peak_required_force_n"]) for row in matching_rows),
                max(float(row["peak_tool_force_n"]) for row in matching_rows),
                max(float(row["peak_required_force_n"]) for row in no_event_rows),
                max(float(row["peak_tool_force_n"]) for row in no_event_rows),
            )
            result = {
                "approach_mm_s": approach_speed,
                "hard_depth_limit_mm": hard_limit,
                "eligible": candidate_pass,
                "matching_all_pass": matching_pass,
                "no_event_all_pass": no_event_pass,
                "worst_contact_force_n": worst_force,
                "summaries": summaries,
            }
            results.append(result)
            if candidate_pass:
                eligible.append(result)
            key = f"speed-{approach_speed:g}__limit-{hard_limit:g}"
            payload[key] = {
                "matching": matching_rows,
                "no_event": no_event_rows,
            }
    selected = (
        min(
            eligible,
            key=lambda row: (
                row["worst_contact_force_n"],
                row["approach_mm_s"],
                row["hard_depth_limit_mm"],
            ),
        )
        if eligible
        else None
    )
    result = {
        "schema": "tactevra.ws2_event_force_guard_search_device.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "device": device,
        "candidate_results": results,
        "selected_candidate": selected,
        "status": (
            "PASS_FORCE_BOUNDED_EVENT_AND_IMMEDIATE_LIMIT_RETRACTION"
            if selected is not None
            else "STOP_NO_FORCE_BOUNDED_EVENT_CANDIDATE"
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
    selected = left["selected_candidate"] if exact else None
    result = {
        "schema": "tactevra.ws2_event_force_guard_search_comparison.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "cross_gpu_exact": exact,
        "selected_candidate": selected,
        "status": (
            "PASS_FORCE_BOUNDED_EVENT_COMPARISON"
            if exact and selected is not None
            else "STOP_FORCE_BOUNDED_EVENT_COMPARISON"
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
