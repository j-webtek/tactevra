"""Exploratory WS2 key-press physics runner with zero physical authority.

The retained fixture defines every sampled physical range and decision rule.
This module may create only in-memory MuJoCo models and external JSON evidence;
it has no controller, transport, permit, serial, socket, or hardware surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
from typing import Any


SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
DEVICES = ("cuda:0", "cuda:1")
COUNT_METRICS = (
    "actuation_count",
    "auto_repeat_count",
    "neighbor_contact",
    "bottom_out_overflow",
    "release_complete",
)
CONTINUOUS_METRICS = (
    "peak_penetration_mm",
    "peak_required_force_n",
    "dwell_above_actuation_ms",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha_value(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(workspace: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else workspace / path


def load_fixture(path: Path, *, workspace: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    claimed = fixture.pop("fixture_sha256")
    if _sha_value(fixture) != claimed:
        raise ValueError("WS2 fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture.get("scope") != SCOPE or fixture.get("physical_authority") is not False:
        raise ValueError("WS2 fixture is not zero-authority simulation")
    if fixture.get("gpu_execution_authorized") is not False:
        raise ValueError("WS2 fixture unexpectedly authorizes GPU execution")
    if any(fixture.get("counters", {}).values()):
        raise ValueError("WS2 fixture contains nonzero authority counters")
    for name, binding in fixture["bindings"].items():
        source = _resolve(workspace, binding["path"])
        if _sha_file(source) != binding["sha256"]:
            raise ValueError(f"bound source changed: {name}")
        if "content_sha256" in binding:
            content = json.loads(source.read_text(encoding="utf-8"))
            normalized = {
                key: value
                for key, value in content.items()
                if key not in {"device", "stack", "receipt_sha256"}
            }
            if _sha_value(normalized) != binding["content_sha256"]:
                raise ValueError(f"bound content identity changed: {name}")
    program = json.loads(
        _resolve(workspace, fixture["bindings"]["program_fixture"]["path"])
        .read_text(encoding="utf-8")
    )
    section = program["sections"]["workstream_2"]
    if section["section_sha256"] != fixture["bindings"]["program_fixture"][
        "section_sha256"
    ]:
        raise ValueError("governing WS2 section changed")
    return fixture


def _target_records(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    keyboard = catalog["keyboard"]
    default_extent = keyboard["key_half_extent_mm"]
    explicit = keyboard.get("explicit_targets", {})
    records: list[dict[str, Any]] = []
    for row in keyboard["rows"]:
        start = row["first_center_xy_mm"]
        step = row["step_xy_mm"]
        for index, target_id in enumerate(row["key_ids"]):
            override = explicit.get(target_id, {})
            records.append(
                {
                    "target_id": target_id,
                    "center_xy_mm": override.get(
                        "center_xy_mm",
                        [start[0] + step[0] * index, start[1] + step[1] * index],
                    ),
                    "half_extent_mm": override.get("half_extent_mm", default_extent),
                }
            )
    known = {row["target_id"] for row in records}
    for target_id, target in explicit.items():
        if target_id not in known:
            records.append(
                {
                    "target_id": target_id,
                    "center_xy_mm": target["center_xy_mm"],
                    "half_extent_mm": target["half_extent_mm"],
                }
            )
    return records


def _midpoint(bounds: list[float]) -> float:
    return (float(bounds[0]) + float(bounds[1])) / 2.0


def physical_profiles(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    ranges = fixture["contact_model"]["unmeasured_ranges"]
    design = fixture["contact_model"]["physical_profile_design"]
    axes = design["axes"]
    baseline = {name: _midpoint(ranges[name]) for name in axes}
    profiles = [{"profile_id": "BASELINE", "values": baseline}]
    for name in axes:
        for label, value in (("LOW", ranges[name][0]), ("HIGH", ranges[name][1])):
            values = dict(baseline)
            values[name] = float(value)
            profiles.append({"profile_id": f"{name}__{label}", "values": values})
    expected = design["profile_count"]
    if len(profiles) != expected:
        raise ValueError(f"physical profile count changed: {len(profiles)} != {expected}")
    return profiles


def tip_geometries(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    families = fixture["contact_model"]["tip_families"]
    tips = [
        {"tip_id": f"sphere-r{radius:g}", "shape": "sphere", "radius_mm": radius,
         "half_length_mm": 0.0}
        for radius in families["sphere"]["radius_samples_mm"]
    ]
    for radius in families["capsule"]["radius_samples_mm"]:
        for multiple in families["capsule"]["half_length_radius_multiple_samples"]:
            tips.append(
                {
                    "tip_id": f"capsule-r{radius:g}-m{multiple:g}",
                    "shape": "capsule",
                    "radius_mm": radius,
                    "half_length_mm": radius * multiple,
                }
            )
    return tips


def recipe_rows(fixture: dict[str, Any]) -> list[dict[str, float | int]]:
    import numpy as np

    design = fixture["recipe_design"]
    count = design["recipe_count"]
    rng = np.random.Generator(np.random.PCG64(design["seed"]))
    dimensions: dict[str, list[float]] = design["ranges"]
    permutations = {name: rng.permutation(count) for name in dimensions}
    rows = []
    for index in range(count):
        row: dict[str, float | int] = {"recipe_index": index}
        for name, bounds in dimensions.items():
            fraction = (float(permutations[name][index]) + 0.5) / count
            row[name] = float(bounds[0]) + fraction * (float(bounds[1]) - float(bounds[0]))
        rows.append(row)
    return rows


def build_manifest(fixture: dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    catalog = json.loads(
        _resolve(workspace, fixture["bindings"]["candidate_catalog"]["path"])
        .read_text(encoding="utf-8")
    )
    pose_bundle = json.loads(
        _resolve(workspace, fixture["bindings"]["pose_bundle"]["path"])
        .read_text(encoding="utf-8")
    )
    targets = _target_records(catalog)
    pose_ids = [row["target_id"] for row in pose_bundle["poses"]]
    if [row["target_id"] for row in targets] != pose_ids:
        raise ValueError("candidate catalog order differs from bound pose bundle")
    classes: dict[tuple[float, float], list[str]] = {}
    for target in targets:
        key = tuple(float(value) for value in target["half_extent_mm"])
        classes.setdefault(key, []).append(target["target_id"])
    profiles = physical_profiles(fixture)
    tips = tip_geometries(fixture)
    units = []
    for half_extent, target_ids in sorted(classes.items()):
        class_id = f"hx{half_extent[0]:g}-hy{half_extent[1]:g}"
        for profile in profiles:
            for tip in tips:
                identity = f"{class_id}__{profile['profile_id']}__{tip['tip_id']}"
                parity = int(hashlib.sha256(identity.encode()).hexdigest(), 16) % 2
                units.append(
                    {
                        "unit_id": identity,
                        "device": f"cuda:{parity}",
                        "half_extent_mm": list(half_extent),
                        "target_ids": target_ids,
                        "profile_id": profile["profile_id"],
                        "tip_id": tip["tip_id"],
                    }
                )
    logical_rows = (
        len(targets)
        * len(profiles)
        * len(tips)
        * len(recipe_rows(fixture))
        * len(fixture["landing_model"]["scenarios"])
    )
    manifest = {
        "schema": "tactevra.ws2_key_press_campaign_manifest.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "target_count": len(targets),
        "geometry_class_count": len(classes),
        "physical_profile_count": len(profiles),
        "tip_geometry_count": len(tips),
        "recipe_count": len(recipe_rows(fixture)),
        "landing_scenario_count": len(fixture["landing_model"]["scenarios"]),
        "landing_samples_per_row": fixture["landing_model"]["samples_per_target_scenario"],
        "logical_scored_row_count": logical_rows,
        "physics_world_count": logical_rows
        * fixture["landing_model"]["samples_per_target_scenario"],
        "units": units,
        "phone_cell_count": math.prod(
            len(fixture["phone_design"][name])
            for name in (
                "contact_radius_mm_samples",
                "duration_ms_samples",
                "long_press_threshold_ms_samples",
            )
        ),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_commands": [],
        "permits": [],
        "transport_operations": [],
        "physical_authority": False,
    }
    manifest["manifest_sha256"] = _sha_value(manifest)
    return manifest


def build_contact_mjcf(
    fixture: dict[str, Any],
    profile: dict[str, Any],
    tip: dict[str, Any],
    half_extent_mm: list[float],
    pitch_mm: float,
) -> str:
    values = profile["values"]
    width = values["keycap_width_height_mm"] * half_extent_mm[0] / half_extent_mm[1]
    height = values["keycap_width_height_mm"]
    thickness = values["keycap_thickness_mm"]
    travel = values["travel_mm"]
    bottom = travel * values["bottom_out_fraction"]
    spring = values["spring_n_per_mm"] * 1000.0
    damping = values["damping_n_s_per_mm"] * 1000.0
    mass = values["keycap_mass_kg"]
    friction = values["friction_coefficient"]
    bodies = []
    for index, (x_index, y_index) in enumerate(
        (x, y) for y in (-1, 0, 1) for x in (-1, 0, 1)
    ):
        bodies.append(
            f'<body name="key_{index}" '
            f'pos="{x_index * pitch_mm / 1000:.9f} '
            f'{y_index * pitch_mm / 1000:.9f} 0">'
            f'<joint name="key_joint_{index}" type="slide" axis="0 0 -1" '
            f'range="0 {bottom / 1000:.9f}" stiffness="{spring:.9f}" '
            f'damping="{damping:.9f}"/>'
            f'<geom name="key_geom_{index}" type="box" '
            f'pos="0 0 {-thickness / 2000:.9f}" '
            f'size="{width / 2000:.9f} {height / 2000:.9f} '
            f'{thickness / 2000:.9f}" mass="{mass:.9f}" '
            f'friction="{friction:.9f} 0.005 0.0001"/></body>'
        )
    if tip["shape"] == "sphere":
        tip_geom = f'<geom name="tip" type="sphere" size="{tip["radius_mm"] / 1000:.9f}"/>'
    else:
        tip_geom = (
            f'<geom name="tip" type="capsule" size="{tip["radius_mm"] / 1000:.9f} '
            f'{tip["half_length_mm"] / 1000:.9f}"/>'
        )
    return (
        '<mujoco model="tactevra_ws2"><compiler angle="radian"/>'
        f'<option timestep="{fixture["contact_model"]["timestep_seconds"]}" '
        f'integrator="{fixture["contact_model"]["integrator"]}" gravity="0 0 -9.81"/>'
        '<size nconmax="128" njmax="512"/><worldbody>'
        '<geom name="bottom_stop" type="plane" pos="0 0 -0.020" size="0 0 0.1"/>'
        + "".join(bodies)
        + f'<body name="tip_mocap" mocap="true" pos="0 0 0.02">{tip_geom}</body>'
        '</worldbody></mujoco>'
    )


def cpu_contact_smoke(fixture: dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    import mujoco

    catalog = json.loads(
        _resolve(workspace, fixture["bindings"]["candidate_catalog"]["path"])
        .read_text(encoding="utf-8")
    )
    profiles = physical_profiles(fixture)
    tips = tip_geometries(fixture)
    target = next(row for row in _target_records(catalog) if row["target_id"] == "EQUAL")
    selected_profiles = [profiles[0], profiles[1], profiles[2]]
    selected_tips = [tips[0], tips[-1]]
    compiled = []
    for profile in selected_profiles:
        for tip in selected_tips:
            xml = build_contact_mjcf(
                fixture,
                profile,
                tip,
                target["half_extent_mm"],
                float(catalog["keyboard"]["pitch_mm"]),
            )
            model = mujoco.MjModel.from_xml_string(xml)
            data = mujoco.MjData(model)
            mujoco.mj_forward(model, data)
            compiled.append(
                {
                    "profile_id": profile["profile_id"],
                    "tip_id": tip["tip_id"],
                    "nq": model.nq,
                    "nmocap": model.nmocap,
                    "finite": bool(math.isfinite(float(data.energy[0]))),
                }
            )
    if not all(row["nq"] == 9 and row["nmocap"] == 1 for row in compiled):
        raise AssertionError("WS2 contact-model topology changed")
    return {
        "schema": "tactevra.ws2_cpu_contact_smoke.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "compiled_models": compiled,
        "gpu_launches": 0,
        "physics_steps": 0,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }


def phone_cells(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    design = fixture["phone_design"]
    rows = []
    for radius in design["contact_radius_mm_samples"]:
        for duration in design["duration_ms_samples"]:
            for threshold in design["long_press_threshold_ms_samples"]:
                tap = duration >= 20
                long_press = duration >= threshold
                rows.append(
                    {
                        "contact_radius_mm": radius,
                        "duration_ms": duration,
                        "long_press_threshold_ms": threshold,
                        "tap_count": int(tap and not long_press),
                        "long_press": long_press,
                        "admitted": bool(tap and not long_press),
                    }
                )
    return rows


def compare_receipts(
    fixture: dict[str, Any], left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    if left.get("device") == right.get("device"):
        raise ValueError("cross-GPU comparison requires distinct devices")
    if left.get("fixture_sha256") != fixture["fixture_sha256"] or right.get(
        "fixture_sha256"
    ) != fixture["fixture_sha256"]:
        raise ValueError("receipt fixture identity mismatch")
    left_rows = {row["row_id"]: row for row in left.get("rows", [])}
    right_rows = {row["row_id"]: row for row in right.get("rows", [])}
    if not left_rows or left_rows.keys() != right_rows.keys():
        raise ValueError("cross-GPU row identities differ or are empty")
    limit = fixture["decision"]["cross_gpu_limits"]["continuous_metric_max_abs"]
    maximum = 0.0
    for row_id in left_rows:
        a, b = left_rows[row_id], right_rows[row_id]
        for metric in COUNT_METRICS:
            if a[metric] != b[metric]:
                raise ValueError(f"count disagreement at {row_id}: {metric}")
        for metric in CONTINUOUS_METRICS:
            delta = abs(float(a[metric]) - float(b[metric]))
            maximum = max(maximum, delta)
            if not math.isfinite(delta) or delta > limit:
                raise ValueError(f"continuous disagreement at {row_id}: {metric}")
    return {
        "schema": "tactevra.ws2_cross_gpu_comparison.v1",
        "status": "PASS_EXPLORATORY_CROSS_GPU_AGREEMENT",
        "fixture_sha256": fixture["fixture_sha256"],
        "row_count": len(left_rows),
        "maximum_continuous_delta": maximum,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }


def _stack() -> dict[str, Any]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,driver_version",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        "platform": platform.platform(),
        "gpus": [line.strip() for line in completed.stdout.splitlines() if line.strip()],
    }


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    value["receipt_sha256"] = _sha_value(value)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("manifest", "cpu-smoke", "phone", "compare"))
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--left", type=Path)
    parser.add_argument("--right", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    fixture = load_fixture(args.fixture.resolve(strict=True), workspace=workspace)
    if args.mode == "manifest":
        result = build_manifest(fixture, workspace=workspace)
    elif args.mode == "cpu-smoke":
        result = cpu_contact_smoke(fixture, workspace=workspace)
    elif args.mode == "phone":
        rows = phone_cells(fixture)
        result = {
            "schema": "tactevra.ws2_phone_event_sweep.v1",
            "scope": SCOPE,
            "fixture_sha256": fixture["fixture_sha256"],
            "rows": rows,
            "admitted_cells": sum(row["admitted"] for row in rows),
            "hardware_write_count": 0,
            "physical_movement_count": 0,
            "physical_authority": False,
        }
    else:
        if args.left is None or args.right is None:
            parser.error("compare requires --left and --right")
        result = compare_receipts(
            fixture,
            json.loads(args.left.read_text(encoding="utf-8")),
            json.loads(args.right.read_text(encoding="utf-8")),
        )
    _write(args.output, result)
    print(json.dumps({"status": result.get("status", "COMPLETE"), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
