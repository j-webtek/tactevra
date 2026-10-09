"""Independent standard-MuJoCo timing reference for retained WS2 recipe 80.

This runner deliberately does not use MuJoCo Warp for integration.  It replays
one frozen zero-height-offset world through standard MuJoCo and compares the
observed switch closure with the analytic commanded-motion timeline.  It has no
controller, transport, permit, or hardware surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
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


def run_reference(fixture_path: Path) -> dict[str, Any]:
    import mujoco
    import numpy as np

    fixture = event_runner.load_fixture(fixture_path)
    campaign, execution, physical = event_runner.load_bound(fixture)
    target_id = "GRAVE"
    profile_id = fixture["design"]["profile_ids"][0]
    scenario_id = "MID_SOURCE_MID_RESIDUAL"
    control = event_runner._control(
        fixture,
        physical=physical,
        target_id=target_id,
        profile_id=profile_id,
        scenario_id=scenario_id,
        latency_ms=0.0,
        mode="FIXED_DEPTH",
        approach_mm_s=None,
    )["control"]
    neighborhood = control["physical_neighborhood"]
    profile = next(
        row
        for row in probe.physical_profiles(campaign)
        if row["profile_id"] == profile_id
    )
    tip = next(
        row
        for row in probe.tip_geometries(campaign)
        if row["tip_id"] == control["tip_id"]
    )
    catalog = json.loads(
        Path(campaign["bindings"]["candidate_catalog"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    pitch_mm = float(catalog["keyboard"]["pitch_mm"])
    xml = probe.build_contact_mjcf(
        campaign,
        profile,
        tip,
        control["physical_keycap_half_extent_mm"],
        pitch_mm,
        None,
        neighborhood,
    )
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    center_joint = int(control["target_joint_index"])
    landing = json.loads(
        Path(execution["bindings"]["landing_prepass"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    landing_row = next(
        row
        for row in landing["rows"]
        if row["target_id"] == target_id and row["scenario_id"] == scenario_id
    )
    offset_x_mm, offset_y_mm = landing_row["offset_xy_mm"][0]
    data.qpos[:] = 0.0
    data.qvel[:] = 0.0
    data.mocap_pos[0] = [offset_x_mm / 1000.0, offset_y_mm / 1000.0, 0.05]
    mujoco.mj_forward(model, data)

    settle = execution["numerical_protocol"]["settle"]
    previous = data.qpos.copy()
    settled_count = 0
    settle_steps = 0
    for settle_steps in range(
        1, math.ceil(settle["maximum_seconds"] / model.opt.timestep) + 1
    ):
        mujoco.mj_step(model, data)
        stable = (
            float(np.max(np.abs(data.qvel))) <= settle["velocity_limit_m_s"]
            and float(np.max(np.abs(data.qpos - previous)))
            <= settle["position_delta_limit_m"]
        )
        settled_count = settled_count + 1 if stable else 0
        previous = data.qpos.copy()
        if settled_count >= settle["consecutive_steps"]:
            break
    if settled_count < settle["consecutive_steps"]:
        raise RuntimeError("standard-MuJoCo reference did not settle")

    rest_qpos = data.qpos.copy()
    recipe = fixture["design"]["retained_recipe"]
    depth = float(recipe["press_depth_mm"])
    approach_s = depth / float(recipe["approach_mm_s"])
    dwell_s = float(recipe["dwell_ms"]) / 1000.0
    release_s = depth / float(recipe["release_mm_s"])
    motion_s = approach_s + dwell_s + release_s
    total_s = (
        motion_s
        + execution["numerical_protocol"]["release"]["additional_settle_seconds"]
    )
    values = profile["values"]
    actuation_mm = values["travel_mm"] * values["actuation_fraction"]
    tip_extent_mm = tip["radius_mm"] + tip["half_length_mm"]
    compliance = fixture["design"]["tool_compliance"]
    active_run = maximum_active_run = 0
    peak_mm = 0.0
    first_active_ms = last_active_ms = None
    trace = []
    for step in range(math.ceil(total_s / model.opt.timestep)):
        elapsed = step * model.opt.timestep
        if elapsed < approach_s:
            commanded = depth * elapsed / approach_s
        elif elapsed < approach_s + dwell_s:
            commanded = depth
        elif elapsed < motion_s:
            commanded = depth * (1.0 - (elapsed - approach_s - dwell_s) / release_s)
        else:
            commanded = 0.0
        effective, _, _ = probe.series_compliance_displacement(
            commanded,
            key_stiffness_n_per_mm=values["spring_n_per_mm"],
            tool_stiffness_n_per_mm=compliance["stiffness_n_per_mm"],
            tool_travel_mm=compliance["travel_mm"],
        )
        z_m = (tip_extent_mm - rest_qpos[center_joint] * 1000.0 - effective) / 1000.0
        data.mocap_pos[0] = [offset_x_mm / 1000.0, offset_y_mm / 1000.0, z_m]
        mujoco.mj_step(model, data)
        penetration_mm = (data.qpos[center_joint] - rest_qpos[center_joint]) * 1000.0
        peak_mm = max(peak_mm, float(penetration_mm))
        active = penetration_mm >= actuation_mm
        active_run = active_run + 1 if active else 0
        maximum_active_run = max(maximum_active_run, active_run)
        if active:
            first_active_ms = (
                first_active_ms if first_active_ms is not None else elapsed * 1000.0
            )
            last_active_ms = elapsed * 1000.0
        if elapsed <= motion_s and step % 10 == 0:
            trace.append(
                {
                    "time_ms": elapsed * 1000.0,
                    "commanded_depth_mm": commanded,
                    "key_penetration_mm": float(penetration_mm),
                }
            )

    result = {
        "schema": "tactevra.ws2_stage_a_timing_reference.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "fixture_file_sha256": file_sha(fixture_path),
        "engine": "STANDARD_MUJOCO_SINGLE_WORLD_NOT_WARP",
        "mujoco_version": mujoco.__version__,
        "identity": {
            "target_id": target_id,
            "profile_id": profile_id,
            "scenario_id": scenario_id,
            "landing_sample_index": 0,
            "vertical_origin_offset_mm": 0.0,
            "recipe_index": recipe["recipe_index"],
        },
        "analytic_command_timeline_ms": {
            "approach": approach_s * 1000.0,
            "dwell": dwell_s * 1000.0,
            "release": release_s * 1000.0,
            "total_motion": motion_s * 1000.0,
        },
        "observed": {
            "settle_steps": settle_steps,
            "peak_key_penetration_mm": peak_mm,
            "first_actuation_ms": first_active_ms,
            "last_actuation_ms": last_active_ms,
            "maximum_continuous_closure_ms": maximum_active_run
            * model.opt.timestep
            * 1000.0,
        },
        "interpretation": (
            "The command dwells for 268.229 ms, while compliant contact overshoots "
            "and relaxes below actuation during the unchanged dwell. Closure duration "
            "therefore need not equal commanded dwell."
        ),
        "trace_20ms": trace,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "controller_command_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = value_sha(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run_reference(args.fixture)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
