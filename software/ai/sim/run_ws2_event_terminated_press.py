"""Bounded WS2 fixed-depth versus event-terminated key-press comparison."""

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

from ai.sim import keyboard_physical_neighborhoods as neighborhoods  # noqa: E402
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
        raise ValueError("event-terminated fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture["physical_authority"] is not False or any(fixture["counters"].values()):
        raise ValueError("event-terminated fixture has nonzero authority")
    if fixture["event_authority"] != {
        "may_start_motion": False,
        "may_deepen_motion": False,
        "may_extend_motion": False,
        "may_retry_motion": False,
        "may_redirect_motion": False,
        "may_start_early_retraction": True,
    }:
        raise ValueError("event authority boundary changed")
    for name, binding in fixture["bindings"].items():
        if name == "retained_recipe_envelope":
            source = Path(binding["path"])
            if source.exists() and file_sha(source) != binding["sha256"]:
                raise ValueError("retained recipe envelope changed")
            continue
        source = Path(binding["path"])
        if not source.is_absolute():
            source = ROOT / source
        if file_sha(source) != binding["sha256"]:
            raise ValueError(f"event fixture binding changed: {name}")
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
    neighborhood_fixture = neighborhoods.load_fixture(
        ROOT / fixture["bindings"]["physical_neighborhoods"]["path"]
    )
    physical = neighborhoods.deduplicated_neighborhoods(neighborhood_fixture)
    return campaign, execution, physical


def _control(
    fixture: dict[str, Any],
    *,
    physical: dict[str, Any],
    target_id: str,
    profile_id: str,
    scenario_id: str,
    latency_ms: float,
    mode: str,
    approach_mm_s: float | None,
) -> dict[str, Any]:
    design = fixture["design"]
    if target_id not in design["initial_target_ids"]:
        raise ValueError("target outside frozen initial event comparison")
    if profile_id not in design["profile_ids"]:
        raise ValueError("profile outside frozen event comparison")
    if scenario_id not in design["scenario_ids"]:
        raise ValueError("scenario outside frozen event comparison")
    if mode == "FIXED_DEPTH":
        if approach_mm_s is not None or latency_ms != 0.0:
            raise ValueError("fixed-depth comparator cannot carry event inputs")
    else:
        allowed_modes = {"MATCHING", *design["failure_injection"]["modes"]}
        if mode not in allowed_modes or approach_mm_s is None:
            raise ValueError("event mode outside frozen event comparison")
        allowed_latencies = set(design["latency_ms_samples"])
        allowed_latencies.add(design["failure_injection"]["latency_ms"])
        if latency_ms not in allowed_latencies:
            raise ValueError("latency outside frozen event comparison")
    physical_neighborhood = next(
        row for row in physical["neighborhoods"] if row["target_id"] == target_id
    )
    target_member = next(
        member
        for member in physical_neighborhood["members"]
        if member["is_target"] is True
    )
    recipe = design["retained_recipe"]
    event = None
    recipe_override: dict[str, float] = {}
    if approach_mm_s is not None:
        recipe_override["approach_mm_s"] = approach_mm_s
        event = {
            "source": "MODELED_HOST_KEYSTROKE_EVENT",
            "mode": mode,
            "latency_ms": latency_ms,
            "expected_target_id": target_id,
            "reported_target_id": (
                None
                if mode == "NO_EVENT"
                else design["wrong_key_target_id"]
                if mode == "WRONG_KEY"
                else target_id
            ),
            "hard_depth_limit_mm": recipe["press_depth_mm"],
            "reserved_bottom_out_margin_mm": design["reserved_bottom_out_margin_mm"],
            "no_retry": True,
            "may_only_shorten_motion": True,
        }
    rows = [
        {
            "target_id": target_id,
            "scenario_id": scenario_id,
            "landing_sample_index": index,
            "vertical_origin_offset_mm": vertical_offset,
        }
        for vertical_offset in design["vertical_origin_offset_mm_samples"]
        for index in design["landing_sample_indices"]
    ]
    control = {
        "fixture_sha256": fixture["fixture_sha256"],
        "control": {
            "control_id": (
                f"{target_id}-{profile_id}-{scenario_id}-{mode}-latency-{latency_ms:g}"
            ),
            "control_kind": "ACTUATION",
            "target_id": target_id,
            "profile_id": profile_id,
            "tip_id": design["tip_id"],
            "scenario_id": scenario_id,
            "base_recipe_index": recipe["recipe_index"],
            "landing_sample_indices": design["landing_sample_indices"],
            "batch_rows": rows,
            "vectorized_world_controls": False,
            "recipe_override": recipe_override,
            "tool_compliance_model": "SERIES_QUASISTATIC",
            "tool_compliance": design["tool_compliance"],
            "physical_keycap_half_extent_mm": [
                float(target_member["size_xy_mm"][0]) / 2.0,
                float(target_member["size_xy_mm"][1]) / 2.0,
            ],
            "physical_neighborhood": physical_neighborhood["members"],
            "target_joint_index": physical_neighborhood["target_joint_index"],
        },
    }
    if event is not None:
        control["control"]["event_termination"] = event
    return control


def _event_speed(
    fixture: dict[str, Any], profile: dict[str, Any], latency_ms: float
) -> tuple[float, float]:
    values = profile["values"]
    actuation = values["travel_mm"] * values["actuation_fraction"]
    bottom = values["travel_mm"] * values["bottom_out_fraction"]
    limit = probe.event_terminated_speed_limit_mm_s(
        actuation_mm=actuation,
        bottom_out_mm=bottom,
        latency_ms=latency_ms,
        reserved_margin_mm=fixture["design"]["reserved_bottom_out_margin_mm"],
    )
    selected = min(
        fixture["design"]["retained_recipe"]["approach_mm_s"],
        fixture["design"]["speed_fraction_of_limit"] * limit,
    )
    return limit, selected


def _run_receipt(
    fixture: dict[str, Any],
    campaign: dict[str, Any],
    execution: dict[str, Any],
    physical: dict[str, Any],
    *,
    device: str,
    target_id: str,
    profile_id: str,
    scenario_id: str,
    latency_ms: float,
    mode: str,
    approach_mm_s: float | None,
) -> dict[str, Any]:
    return probe.run_smoke_worker(
        campaign,
        execution,
        workspace=ROOT,
        device_name=device,
        control=_control(
            fixture,
            physical=physical,
            target_id=target_id,
            profile_id=profile_id,
            scenario_id=scenario_id,
            latency_ms=latency_ms,
            mode=mode,
            approach_mm_s=approach_mm_s,
        ),
    )


def run_device(fixture: dict[str, Any], device: str) -> dict[str, Any]:
    if device not in fixture["design"]["devices"]:
        raise ValueError("device outside frozen event comparison")
    campaign, execution, physical = load_bound(fixture)
    profiles = {row["profile_id"]: row for row in probe.physical_profiles(campaign)}
    event_receipts = []
    fixed_receipts = []
    speed_rows = []
    for target_id in fixture["design"]["initial_target_ids"]:
        for profile_id in fixture["design"]["profile_ids"]:
            profile = profiles[profile_id]
            for scenario_id in fixture["design"]["scenario_ids"]:
                fixed_receipts.append(
                    _run_receipt(
                        fixture,
                        campaign,
                        execution,
                        physical,
                        device=device,
                        target_id=target_id,
                        profile_id=profile_id,
                        scenario_id=scenario_id,
                        latency_ms=0.0,
                        mode="FIXED_DEPTH",
                        approach_mm_s=None,
                    )
                )
                for latency_ms in fixture["design"]["latency_ms_samples"]:
                    limit, selected = _event_speed(fixture, profile, latency_ms)
                    speed_rows.append(
                        {
                            "profile_id": profile_id,
                            "latency_ms": latency_ms,
                            "maximum_speed_mm_s": limit,
                            "selected_speed_mm_s": selected,
                        }
                    )
                    event_receipts.append(
                        _run_receipt(
                            fixture,
                            campaign,
                            execution,
                            physical,
                            device=device,
                            target_id=target_id,
                            profile_id=profile_id,
                            scenario_id=scenario_id,
                            latency_ms=latency_ms,
                            mode="MATCHING",
                            approach_mm_s=selected,
                        )
                    )
    failure_receipts = []
    failure = fixture["design"]["failure_injection"]
    profile = profiles[failure["profile_id"]]
    _, failure_speed = _event_speed(fixture, profile, failure["latency_ms"])
    for target_id in fixture["design"]["initial_target_ids"]:
        for mode in ("NO_EVENT", "WRONG_KEY", "LATE_AFTER_RETRACTION"):
            failure_receipts.append(
                _run_receipt(
                    fixture,
                    campaign,
                    execution,
                    physical,
                    device=device,
                    target_id=target_id,
                    profile_id=failure["profile_id"],
                    scenario_id=failure["scenario_id"],
                    latency_ms=failure["latency_ms"],
                    mode=mode,
                    approach_mm_s=failure_speed,
                )
            )
    event_rows = [row for receipt in event_receipts for row in receipt["rows"]]
    fixed_rows = [row for receipt in fixed_receipts for row in receipt["rows"]]
    failure_rows = [row for receipt in failure_receipts for row in receipt["rows"]]
    event_times = [
        row["retract_start_time_ms"]
        + row["retract_start_displacement_mm"]
        / fixture["design"]["retained_recipe"]["release_mm_s"]
        * 1000.0
        for row in event_rows
    ]
    fixed_time = fixture["design"]["retained_fixed_motion_time_ms"]
    expected_failure_counts = {
        "NO_EVENT_BEFORE_HARD_LIMIT": sum(
            probe.primary_failure(row) == "NO_EVENT_BEFORE_HARD_LIMIT"
            for row in failure_rows
        ),
        "WRONG_KEY_EVENT": sum(
            probe.primary_failure(row) == "WRONG_KEY_EVENT" for row in failure_rows
        ),
        "LATE_EVENT_IGNORED": sum(
            probe.primary_failure(row) == "LATE_EVENT_IGNORED" for row in failure_rows
        ),
    }

    def by_vertical_offset(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for offset in fixture["design"]["vertical_origin_offset_mm_samples"]:
            selected = [
                row for row in rows if row["vertical_origin_offset_mm"] == offset
            ]
            result.append(
                {
                    "vertical_origin_offset_mm": offset,
                    "row_count": len(selected),
                    "admitted_count": sum(row["admitted"] for row in selected),
                    "bottom_out_count": sum(
                        row["bottom_out_overflow"] for row in selected
                    ),
                    "minimum_depth_margin_mm": min(
                        row["minimum_depth_margin_mm"] for row in selected
                    ),
                }
            )
        return result

    result = {
        "schema": "tactevra.ws2_event_terminated_device_result.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "device": device,
        "speed_by_latency_and_profile": sorted(
            {value_sha(row): row for row in speed_rows}.values(),
            key=lambda row: (row["profile_id"], row["latency_ms"]),
        ),
        "fixed": {
            "row_count": len(fixed_rows),
            "admitted_count": sum(row["admitted"] for row in fixed_rows),
            "minimum_depth_margin_mm": min(
                row["minimum_depth_margin_mm"] for row in fixed_rows
            ),
            "bottom_out_count": sum(row["bottom_out_overflow"] for row in fixed_rows),
            "time_per_key_ms": fixed_time,
            "keystrokes_per_minute": 60000.0 / fixed_time,
            "primary_failure_counts": {
                failure: sum(
                    probe.primary_failure(row) == failure for row in fixed_rows
                )
                for failure in sorted(
                    {probe.primary_failure(row) for row in fixed_rows}
                )
            },
            "by_vertical_origin_offset": by_vertical_offset(fixed_rows),
        },
        "event_terminated": {
            "row_count": len(event_rows),
            "admitted_count": sum(row["admitted"] for row in event_rows),
            "minimum_depth_margin_mm": min(
                row["minimum_depth_margin_mm"] for row in event_rows
            ),
            "bottom_out_count": sum(row["bottom_out_overflow"] for row in event_rows),
            "worst_time_per_key_ms": max(event_times),
            "worst_keystrokes_per_minute": 60000.0 / max(event_times),
            "maximum_closure_ms": max(
                row["dwell_above_actuation_ms"] for row in event_rows
            ),
            "primary_failure_counts": {
                failure: sum(
                    probe.primary_failure(row) == failure for row in event_rows
                )
                for failure in sorted(
                    {probe.primary_failure(row) for row in event_rows}
                )
            },
            "by_vertical_origin_offset": by_vertical_offset(event_rows),
        },
        "failure_injection": {
            "row_count": len(failure_rows),
            "primary_failure_counts": expected_failure_counts,
            "all_retries_zero": all(row["retry_count"] == 0 for row in failure_rows),
            "wrong_key_requires_batch_stop": all(
                receipt["batch_stop_required"]
                for receipt in failure_receipts
                if receipt["event_termination"]["mode"] == "WRONG_KEY"
            ),
        },
        "row_payload_sha256": value_sha(
            {"fixed": fixed_rows, "event": event_rows, "failure": failure_rows}
        ),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "controller_command_count": 0,
        "physical_authority": False,
    }
    failures_ok = (
        expected_failure_counts["NO_EVENT_BEFORE_HARD_LIMIT"] > 0
        and expected_failure_counts["WRONG_KEY_EVENT"] > 0
        and expected_failure_counts["LATE_EVENT_IGNORED"] > 0
        and result["failure_injection"]["all_retries_zero"]
        and result["failure_injection"]["wrong_key_requires_batch_stop"]
    )
    result["status"] = (
        "PASS_EVENT_TERMINATED_INITIAL_SMOKE"
        if failures_ok
        and result["event_terminated"]["admitted_count"]
        == result["event_terminated"]["row_count"]
        else "STOP_EVENT_TERMINATED_INITIAL_SMOKE"
    )
    result["receipt_sha256"] = value_sha(result)
    return result


def compare_devices(
    fixture: dict[str, Any], left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    if left["device"] == right["device"]:
        raise ValueError("comparison requires distinct devices")
    if any(row["fixture_sha256"] != fixture["fixture_sha256"] for row in (left, right)):
        raise ValueError("device result fixture mismatch")
    comparable_left = {
        key: value
        for key, value in left.items()
        if key not in {"device", "receipt_sha256"}
    }
    comparable_right = {
        key: value
        for key, value in right.items()
        if key not in {"device", "receipt_sha256"}
    }
    exact = comparable_left == comparable_right
    result = {
        "schema": "tactevra.ws2_event_terminated_comparison.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "device_receipts": {
            left["device"]: left["receipt_sha256"],
            right["device"]: right["receipt_sha256"],
        },
        "cross_gpu_exact": exact,
        "status": (
            "PASS_EVENT_TERMINATED_INITIAL_COMPARISON"
            if exact
            and all(
                row["status"] == "PASS_EVENT_TERMINATED_INITIAL_SMOKE"
                for row in (left, right)
            )
            else "STOP_EVENT_TERMINATED_INITIAL_COMPARISON"
        ),
        "expansion_authorized": exact
        and all(
            row["status"] == "PASS_EVENT_TERMINATED_INITIAL_SMOKE"
            for row in (left, right)
        ),
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
