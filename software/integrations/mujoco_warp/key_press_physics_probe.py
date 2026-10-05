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
import time
from typing import Any


SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
DEVICES = ("cuda:0", "cuda:1")
COUNT_METRICS = (
    "actuation_count",
    "auto_repeat_count",
    "neighbor_contact",
    "bottom_out_overflow",
    "release_complete",
    "force_within_available",
)
CONTINUOUS_METRICS = (
    "peak_penetration_mm",
    "peak_required_force_n",
    "dwell_above_actuation_ms",
    "actuation_margin_mm",
    "bottom_out_margin_mm",
    "minimum_depth_margin_mm",
    "midpoint_error_mm",
    "final_position_error_mm",
    "final_velocity_mm_s",
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


def load_execution_fixture(
    path: Path, *, workspace: Path, parent: dict[str, Any]
) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    claimed = fixture.pop("fixture_sha256")
    if _sha_value(fixture) != claimed:
        raise ValueError("WS2 execution fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture.get("scope") != SCOPE or fixture.get("physical_authority") is not False:
        raise ValueError("WS2 execution fixture is not zero-authority simulation")
    if fixture.get("gpu_execution_authorized") is not False:
        raise ValueError("WS2 execution fixture unexpectedly authorizes execution")
    if any(fixture.get("counters", {}).values()):
        raise ValueError("WS2 execution fixture contains nonzero authority counters")
    for name, binding in fixture["bindings"].items():
        source = _resolve(workspace, binding["path"])
        if _sha_file(source) != binding["sha256"]:
            raise ValueError(f"execution binding changed: {name}")
    parent_binding = fixture["bindings"]["parent_fixture"]
    if parent_binding["fixture_sha256"] != parent["fixture_sha256"]:
        raise ValueError("execution fixture parent identity mismatch")
    landing = json.loads(
        _resolve(workspace, fixture["bindings"]["landing_prepass"]["path"])
        .read_text(encoding="utf-8")
    )
    if landing.get("receipt_sha256") != fixture["bindings"]["landing_prepass"][
        "receipt_sha256"
    ]:
        raise ValueError("execution landing receipt identity mismatch")
    return fixture


def load_positive_control_fixture(
    path: Path,
    *,
    workspace: Path,
    parent: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    claimed = fixture.pop("fixture_sha256")
    if _sha_value(fixture) != claimed:
        raise ValueError("WS2 positive-control fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture.get("scope") != SCOPE or fixture.get("physical_authority") is not False:
        raise ValueError("WS2 positive control is not zero-authority simulation")
    if any(fixture.get("counters", {}).values()):
        raise ValueError("WS2 positive control contains nonzero authority counters")
    for name in ("campaign_fixture", "execution_fixture"):
        binding = fixture["bindings"][name]
        source = _resolve(workspace, binding["path"])
        if _sha_file(source) != binding["sha256"]:
            raise ValueError(f"positive-control binding changed: {name}")
    if fixture["bindings"]["campaign_fixture"]["fixture_sha256"] != parent[
        "fixture_sha256"
    ]:
        raise ValueError("positive-control campaign identity mismatch")
    if fixture["bindings"]["execution_fixture"]["fixture_sha256"] != execution[
        "fixture_sha256"
    ]:
        raise ValueError("positive-control execution identity mismatch")
    control = fixture["control"]
    profile = next(
        row
        for row in physical_profiles(parent)
        if row["profile_id"] == control["profile_id"]
    )
    values = profile["values"]
    actuation_mm = values["travel_mm"] * values["actuation_fraction"]
    bottom_mm = values["travel_mm"] * values["bottom_out_fraction"]
    depth_mm = float(control["recipe_override"]["press_depth_mm"])
    if not actuation_mm < depth_mm < bottom_mm:
        raise ValueError("positive-control depth must lie between actuation and bottom-out")
    if control["landing_sample_indices"] != list(range(64)):
        raise ValueError("positive-control landing population changed")
    kind = control.get("control_kind", "ACTUATION")
    if kind not in {"ACTUATION", "RELEASE"}:
        raise ValueError("unknown positive-control kind")
    if kind == "RELEASE":
        release = control.get("release_protocol_override")
        if set(release or {}) != {
            "additional_settle_seconds",
            "position_error_limit_mm",
            "velocity_limit_mm_s",
        }:
            raise ValueError("release control requires the exact release protocol override")
        if float(release["additional_settle_seconds"]) < 1.0:
            raise ValueError("release control requires at least one second of extra settle")
        if float(release["position_error_limit_mm"]) <= 0.0 or float(
            release["velocity_limit_mm_s"]
        ) <= 0.0:
            raise ValueError("release-control reset tolerances must be positive")
    return fixture


def depth_margin_metrics(
    peak_penetration_mm: float, actuation_mm: float, bottom_out_mm: float
) -> dict[str, float]:
    """Score both sides of the modeled press window without changing admission."""
    values = (peak_penetration_mm, actuation_mm, bottom_out_mm)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("depth-margin inputs must be finite")
    if not 0.0 < actuation_mm < bottom_out_mm:
        raise ValueError("depth-margin window is invalid")
    actuation_margin = peak_penetration_mm - actuation_mm
    bottom_margin = bottom_out_mm - peak_penetration_mm
    midpoint = (actuation_mm + bottom_out_mm) / 2.0
    return {
        "actuation_margin_mm": actuation_margin,
        "bottom_out_margin_mm": bottom_margin,
        "minimum_depth_margin_mm": min(actuation_margin, bottom_margin),
        "midpoint_error_mm": abs(peak_penetration_mm - midpoint),
    }


def load_staged_fixture(
    path: Path,
    *,
    workspace: Path,
    parent: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    claimed = fixture.pop("fixture_sha256")
    if _sha_value(fixture) != claimed:
        raise ValueError("WS2 staged-search fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture.get("scope") != SCOPE or fixture.get("physical_authority") is not False:
        raise ValueError("WS2 staged-search fixture is not zero-authority simulation")
    if fixture.get("gpu_execution_authorized") is not False:
        raise ValueError("WS2 staged-search fixture unexpectedly authorizes execution")
    if any(fixture.get("counters", {}).values()):
        raise ValueError("WS2 staged-search fixture contains nonzero authority counters")
    for name, binding in fixture["bindings"].items():
        source = _resolve(workspace, binding["path"])
        if _sha_file(source) != binding["sha256"]:
            raise ValueError(f"staged-search binding changed: {name}")
    if fixture["bindings"]["campaign_fixture"]["fixture_sha256"] != parent[
        "fixture_sha256"
    ]:
        raise ValueError("staged-search campaign identity mismatch")
    if fixture["bindings"]["execution_fixture"]["fixture_sha256"] != execution[
        "fixture_sha256"
    ]:
        raise ValueError("staged-search execution identity mismatch")
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


def _normalized_recipe_vectors(fixture: dict[str, Any]) -> dict[int, tuple[float, ...]]:
    dimensions = fixture["recipe_design"]["ranges"]
    vectors = {}
    for row in recipe_rows(fixture):
        vectors[int(row["recipe_index"])] = tuple(
            (float(row[name]) - float(bounds[0]))
            / (float(bounds[1]) - float(bounds[0]))
            for name, bounds in dimensions.items()
        )
    return vectors


def _distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def coarse_recipe_indices(
    fixture: dict[str, Any], staged: dict[str, Any]
) -> list[int]:
    vectors = _normalized_recipe_vectors(fixture)
    count = staged["stage_a_coarse"]["recipe_selection"]["count"]
    selected = [min(vectors)]
    while len(selected) < count:
        remaining = [index for index in vectors if index not in selected]
        selected.append(
            min(
                remaining,
                key=lambda index: (
                    -min(_distance(vectors[index], vectors[used]) for used in selected),
                    index,
                ),
            )
        )
    return selected


def primary_failure(row: dict[str, Any]) -> str:
    if not row.get("finite", True) or not row.get("overflow_zero", True):
        return "NONFINITE_OR_OVERFLOW"
    if row.get("neighbor_contact"):
        return "NEIGHBOR_CONTACT"
    if row.get("bottom_out_overflow"):
        return "BOTTOM_OUT"
    if row.get("auto_repeat_count", 0):
        return "AUTO_REPEAT"
    if row.get("double_actuation") or row.get("actuation_count", 0) > 1:
        return "DOUBLE_ACTUATION"
    if row.get("partial_press") or row.get("actuation_count", 0) == 0:
        return "PARTIAL_PRESS"
    if not row.get("release_complete"):
        return "RELEASE_INCOMPLETE"
    if not row.get("force_within_available"):
        return "FORCE_EXCEEDED"
    return "ADMITTED"


def refinement_plan(
    fixture: dict[str, Any], staged: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Apply the frozen coarse-boundary rule without changing any gate."""
    coarse = coarse_recipe_indices(fixture, staged)
    vectors = _normalized_recipe_vectors(fixture)
    grouped: dict[tuple[str, ...], dict[int, list[dict[str, Any]]]] = {}
    identity_fields = ("target_id", "profile_id", "tip_id", "scenario_id")
    for row in rows:
        key = tuple(str(row[field]) for field in identity_fields)
        grouped.setdefault(key, {}).setdefault(int(row["recipe_index"]), []).append(row)
    boundaries = []
    refine = []
    for key, recipes in sorted(grouped.items()):
        if set(recipes) != set(coarse):
            raise ValueError(f"coarse recipe population incomplete for {key}")
        admission = {
            index: {bool(row["admitted"]) for row in sample_rows}
            for index, sample_rows in recipes.items()
        }
        failures = {
            index: {primary_failure(row) for row in sample_rows}
            for index, sample_rows in recipes.items()
        }
        for index in coarse:
            nearest = sorted(
                (other for other in coarse if other != index),
                key=lambda other: (_distance(vectors[index], vectors[other]), other),
            )[:3]
            boundary = (
                len(admission[index]) > 1
                or any(admission[index] != admission[other] for other in nearest)
                or any(failures[index] != failures[other] for other in nearest)
            )
            if not boundary:
                continue
            boundary_id = {
                **dict(zip(identity_fields, key, strict=True)),
                "recipe_index": index,
            }
            boundaries.append(boundary_id)
            unrun = sorted(
                (candidate for candidate in vectors if candidate not in coarse),
                key=lambda candidate: (
                    _distance(vectors[index], vectors[candidate]),
                    candidate,
                ),
            )[: staged["stage_b_refinement"]["maximum_new_recipe_indices_per_boundary"]]
            refine.extend({**boundary_id, "recipe_index": candidate} for candidate in unrun)
    unique = {
        tuple(row[field] for field in (*identity_fields, "recipe_index")): row
        for row in refine
    }
    result = {
        "schema": "tactevra.ws2_refinement_plan.v1",
        "scope": SCOPE,
        "campaign_fixture_sha256": fixture["fixture_sha256"],
        "staged_fixture_sha256": staged["fixture_sha256"],
        "coarse_recipe_indices": coarse,
        "group_count": len(grouped),
        "boundary_count": len(boundaries),
        "boundaries": boundaries,
        "refinement_identity_count": len(unique),
        "refinement_identities": [unique[key] for key in sorted(unique)],
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["plan_sha256"] = _sha_value(result)
    return result


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
    tool_compliance: dict[str, float] | None = None,
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
    if tool_compliance is None:
        tip_body = f'<body name="tip_mocap" mocap="true" pos="0 0 0.02">{tip_geom}</body>'
    else:
        required = {"stiffness_n_per_mm", "damping_n_s_per_mm", "travel_mm"}
        if set(tool_compliance) != required:
            raise ValueError("tool compliance requires exact stiffness, damping, and travel")
        stiffness = float(tool_compliance["stiffness_n_per_mm"])
        tool_damping = float(tool_compliance["damping_n_s_per_mm"])
        tool_travel = float(tool_compliance["travel_mm"])
        if not (stiffness > 0.0 and tool_damping >= 0.0 and tool_travel > 0.0):
            raise ValueError("tool compliance values are outside the physical domain")
        tip_body = (
            '<body name="tip_mocap" mocap="true" pos="0 0 0.02">'
            '<body name="tip_compliant">'
            '<joint name="tool_compliance" type="slide" axis="0 0 1" '
            f'range="0 {tool_travel / 1000:.9f}" '
            f'stiffness="{stiffness * 1000.0:.9f}" '
            f'damping="{tool_damping * 1000.0:.9f}"/>'
            f'{tip_geom}</body></body>'
        )
    return (
        '<mujoco model="tactevra_ws2"><compiler angle="radian"/>'
        f'<option timestep="{fixture["contact_model"]["timestep_seconds"]}" '
        f'integrator="{fixture["contact_model"]["integrator"]}" gravity="0 0 -9.81"/>'
        '<size nconmax="128" njmax="512"/><worldbody>'
        '<geom name="bottom_stop" type="plane" pos="0 0 -0.020" size="0 0 0.1"/>'
        + "".join(bodies)
        + tip_body
        + '</worldbody></mujoco>'
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


def _board_tip_from_mujoco(
    data: Any,
    hand_id: int,
    board_t_world: Any,
    tool_length_mm: float,
    np: Any,
) -> Any:
    position = np.asarray(data.xpos[hand_id], dtype=np.float64) * 1000.0
    rotation = np.asarray(data.xmat[hand_id], dtype=np.float64).reshape(3, 3)
    world = position + rotation @ np.asarray([0.0, 0.0, -tool_length_mm])
    return (board_t_world @ np.concatenate((world, [1.0])))[:3]


def landing_prepass(fixture: dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    """Reproduce the frozen MW2UC joint draws with standard MuJoCo FK only."""
    import mujoco
    import numpy as np

    binding = fixture["bindings"]
    bundle = json.loads(
        _resolve(workspace, binding["pose_bundle"]["path"]).read_text(encoding="utf-8")
    )
    profile = json.loads(
        _resolve(workspace, binding["virtual_profile"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    model = mujoco.MjModel.from_xml_path(
        str(_resolve(workspace, binding["arm_mjcf"]["path"]))
    )
    data = mujoco.MjData(model)
    hand_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "hand_tcp")
    poses = bundle["poses"]
    target_count = len(poses)
    if target_count != 51 or model.nq != 6 or hand_id < 0:
        raise ValueError("MW2UC pose or arm model topology changed")
    nominal = np.asarray(
        [pose["joint_positions_rad"] + [0.0] for pose in poses], dtype=np.float64
    )
    centers = np.asarray([pose["center_board_mm"] for pose in poses], dtype=np.float64)
    board_t_world = np.asarray(
        profile["study_input"]["derived_solver_transform"]["matrix_row_major"],
        dtype=np.float64,
    ).reshape(4, 4)
    tool_length = float(
        profile["study_input"]["route_tool_lengths_mm"]["keyboard"]
    )
    design = fixture["landing_model"]
    retained_worlds = json.loads(
        _resolve(workspace, binding["mw2uc_cuda0"]["path"]).read_text(
            encoding="utf-8"
        )
    )["worlds_per_target_per_fk_scenario"]
    rng = np.random.Generator(np.random.PCG64(design["seed"]))
    fixed_signs = (
        rng.integers(0, 2, size=(target_count, 5), dtype=np.int8).astype(np.float64)
        * 2.0
        - 1.0
    )
    systematic_unit = rng.uniform(-1.0, 1.0, size=5)
    random_unit = rng.normal(0.0, 1.0, size=(target_count, retained_worlds, 5))
    sample_count = design["samples_per_target_scenario"]
    rows = []
    for target_index, pose in enumerate(poses):
        for scenario in design["scenarios"]:
            fixed = scenario["fixed_rad"]
            fixed_q = nominal[target_index].copy()
            fixed_q[:5] += fixed_signs[target_index] * fixed + systematic_unit * fixed
            data.qpos[:] = fixed_q
            mujoco.mj_forward(model, data)
            fixed_tip = _board_tip_from_mujoco(
                data, hand_id, board_t_world, tool_length, np
            )
            fixed_delta = fixed_tip - centers[target_index]
            offsets = []
            for sample_index in range(sample_count):
                qpos = fixed_q.copy()
                qpos[:5] += (
                    random_unit[target_index, sample_index]
                    * scenario["random_sigma_rad"]
                )
                data.qpos[:] = qpos
                mujoco.mj_forward(model, data)
                raw_tip = _board_tip_from_mujoco(
                    data, hand_id, board_t_world, tool_length, np
                )
                corrected = raw_tip - (
                    1.0 - scenario["residual_fraction"]
                ) * fixed_delta
                delta = corrected - centers[target_index]
                offsets.append([float(delta[0]), float(delta[1])])
            rows.append(
                {
                    "target_id": pose["target_id"],
                    "scenario_id": scenario["id"],
                    "offset_xy_mm": offsets,
                }
            )
    return {
        "schema": "tactevra.ws2_landing_prepass.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "algorithm": design["algorithm"],
        "target_count": target_count,
        "scenario_count": len(design["scenarios"]),
        "samples_per_target_scenario": sample_count,
        "source_worlds_per_target": retained_worlds,
        "rows": rows,
        "mujoco_forward_calls": target_count
        * len(design["scenarios"])
        * (sample_count + 1),
        "physics_steps": 0,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_commands": [],
        "physical_authority": False,
    }


def _mocap_positions(np: Any, x_m: Any, y_m: Any, z_m: Any) -> Any:
    return np.stack((x_m, y_m, z_m), axis=1).reshape(len(x_m), 1, 3).astype(
        np.float32
    )


def run_smoke_worker(
    fixture: dict[str, Any],
    execution: dict[str, Any],
    *,
    workspace: Path,
    device_name: str,
    control: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run only the exact bounded smoke frozen by the execution fixture."""
    if device_name not in execution["smoke"]["devices"]:
        raise ValueError("device outside frozen WS2 smoke")
    import mujoco
    import mujoco_warp as mjw
    import numpy as np
    import warp as wp

    smoke = (
        execution["smoke"]
        if control is None
        else {
            "target_id": control["control"]["target_id"],
            "profile_id": control["control"]["profile_id"],
            "tip_id": control["control"]["tip_id"],
            "scenario_ids": [control["control"]["scenario_id"]],
            "recipe_indices": [control["control"]["base_recipe_index"]],
            "landing_sample_indices": control["control"]["landing_sample_indices"],
            "expected_world_count": len(control["control"]["landing_sample_indices"]),
        }
    )
    catalog = json.loads(
        _resolve(workspace, fixture["bindings"]["candidate_catalog"]["path"])
        .read_text(encoding="utf-8")
    )
    targets = _target_records(catalog)
    target = next(row for row in targets if row["target_id"] == smoke["target_id"])
    profile = next(
        row for row in physical_profiles(fixture) if row["profile_id"] == smoke["profile_id"]
    )
    tip = next(row for row in tip_geometries(fixture) if row["tip_id"] == smoke["tip_id"])
    recipes = {row["recipe_index"]: row for row in recipe_rows(fixture)}
    if len(smoke["recipe_indices"]) != 1 or len(smoke["scenario_ids"]) != 1:
        raise ValueError("bounded smoke must contain one recipe and scenario")
    recipe = recipes[smoke["recipe_indices"][0]]
    if control is not None:
        recipe = {**recipe, **control["control"]["recipe_override"]}
    scenario_id = smoke["scenario_ids"][0]
    landing = json.loads(
        _resolve(workspace, execution["bindings"]["landing_prepass"]["path"])
        .read_text(encoding="utf-8")
    )
    landing_row = next(
        row
        for row in landing["rows"]
        if row["target_id"] == target["target_id"]
        and row["scenario_id"] == scenario_id
    )
    offsets = np.asarray(
        [landing_row["offset_xy_mm"][index] for index in smoke["landing_sample_indices"]],
        dtype=np.float64,
    )
    nworld = len(offsets)
    if nworld != smoke["expected_world_count"]:
        raise ValueError("bounded smoke world count changed")

    tool_compliance = (
        None if control is None else control["control"].get("tool_compliance")
    )
    xml = build_contact_mjcf(
        fixture,
        profile,
        tip,
        target["half_extent_mm"],
        float(catalog["keyboard"]["pitch_mm"]),
        tool_compliance,
    )
    overall_started = time.perf_counter()
    model = mujoco.MjModel.from_xml_string(xml)
    seed_data = mujoco.MjData(model)
    wp.init()
    wp.set_device(device_name)
    device = wp.get_device()
    free_before = int(device.free_memory)
    warp_model = mjw.put_model(model)
    data = mjw.put_data(model, seed_data, nworld=nworld)
    free_after_allocation = int(device.free_memory)
    zeros = np.zeros((nworld, model.nq), dtype=np.float32)
    data.qpos.assign(zeros)
    data.qvel.assign(zeros)
    far_z = np.full(nworld, 0.05, dtype=np.float32)
    data.mocap_pos.assign(
        _mocap_positions(np, offsets[:, 0] / 1000.0, offsets[:, 1] / 1000.0, far_z)
    )
    mjw.forward(warp_model, data)

    dt = fixture["contact_model"]["timestep_seconds"]
    settle = execution["numerical_protocol"]["settle"]
    settled_count = 0
    previous = zeros.copy()
    settle_steps = 0
    for settle_steps in range(1, math.ceil(settle["maximum_seconds"] / dt) + 1):
        mjw.step(warp_model, data)
        qpos = np.asarray(data.qpos.numpy(), dtype=np.float64)
        qvel = np.asarray(data.qvel.numpy(), dtype=np.float64)
        stable = (
            float(np.max(np.abs(qvel))) <= settle["velocity_limit_m_s"]
            and float(np.max(np.abs(qpos - previous)))
            <= settle["position_delta_limit_m"]
        )
        settled_count = settled_count + 1 if stable else 0
        previous = qpos
        if settled_count >= settle["consecutive_steps"]:
            break
    settle_pass = settled_count >= settle["consecutive_steps"]
    rest_qpos = np.asarray(data.qpos.numpy(), dtype=np.float64)
    center_joint = 4
    values = profile["values"]
    actuation_mm = values["travel_mm"] * values["actuation_fraction"]
    bottom_mm = values["travel_mm"] * values["bottom_out_fraction"]
    tip_extent_mm = tip["radius_mm"] + tip["half_length_mm"]
    approach_s = recipe["press_depth_mm"] / recipe["approach_mm_s"]
    dwell_s = recipe["dwell_ms"] / 1000.0
    release_s = recipe["press_depth_mm"] / recipe["release_mm_s"]
    motion_s = approach_s + dwell_s + release_s
    release = dict(execution["numerical_protocol"]["release"])
    if control is not None and control["control"].get("control_kind") == "RELEASE":
        release.update(control["control"]["release_protocol_override"])
    extra_s = release["additional_settle_seconds"]
    total_steps = math.ceil((motion_s + extra_s) / dt)

    actuation_count = np.zeros(nworld, dtype=np.int64)
    neighbor_contact = np.zeros(nworld, dtype=bool)
    active = np.zeros(nworld, dtype=bool)
    active_run = np.zeros(nworld, dtype=np.int64)
    maximum_active_run = np.zeros(nworld, dtype=np.int64)
    peak_mm = np.zeros(nworld, dtype=np.float64)
    peak_force = np.zeros(nworld, dtype=np.float64)
    peak_tool_compression_mm = np.zeros(nworld, dtype=np.float64)
    peak_tool_force_n = np.zeros(nworld, dtype=np.float64)
    bottom_overflow = np.zeros(nworld, dtype=bool)
    started = time.perf_counter()
    if settle_pass:
        for step in range(total_steps):
            elapsed = step * dt
            if elapsed < approach_s:
                displacement = recipe["press_depth_mm"] * elapsed / approach_s
            elif elapsed < approach_s + dwell_s:
                displacement = recipe["press_depth_mm"]
            elif elapsed < motion_s:
                displacement = recipe["press_depth_mm"] * (
                    1.0 - (elapsed - approach_s - dwell_s) / release_s
                )
            else:
                displacement = 0.0
            z_m = (
                tip_extent_mm - rest_qpos[:, center_joint] * 1000.0 - displacement
            ) / 1000.0
            data.mocap_pos.assign(
                _mocap_positions(
                    np, offsets[:, 0] / 1000.0, offsets[:, 1] / 1000.0, z_m
                )
            )
            mjw.step(warp_model, data)
            qpos = np.asarray(data.qpos.numpy(), dtype=np.float64)
            qvel = np.asarray(data.qvel.numpy(), dtype=np.float64)
            relative_mm = (qpos - rest_qpos) * 1000.0
            center_mm = relative_mm[:, center_joint]
            now_active = center_mm >= actuation_mm
            actuation_count += np.logical_and(now_active, ~active)
            active_run = np.where(now_active, active_run + 1, 0)
            maximum_active_run = np.maximum(maximum_active_run, active_run)
            active = now_active
            neighbor_contact |= np.max(np.delete(relative_mm[:, :9], center_joint, axis=1), axis=1) > execution[
                "numerical_protocol"
            ]["neighbor_contact_displacement_mm"]
            peak_mm = np.maximum(peak_mm, center_mm)
            required = (
                values["spring_n_per_mm"] * np.maximum(center_mm, 0.0)
                + values["damping_n_s_per_mm"]
                * np.maximum(qvel[:, center_joint] * 1000.0, 0.0)
            )
            peak_force = np.maximum(peak_force, required)
            if tool_compliance is not None:
                compression_mm = np.maximum(relative_mm[:, 9], 0.0)
                tool_force = (
                    tool_compliance["stiffness_n_per_mm"] * compression_mm
                    + tool_compliance["damping_n_s_per_mm"]
                    * np.maximum(qvel[:, 9] * 1000.0, 0.0)
                )
                peak_tool_compression_mm = np.maximum(
                    peak_tool_compression_mm, compression_mm
                )
                peak_tool_force_n = np.maximum(peak_tool_force_n, tool_force)
            bottom_overflow |= qpos[:, center_joint] * 1000.0 > (
                bottom_mm
                + execution["numerical_protocol"]["bottom_out_numerical_tolerance_mm"]
            )
    wp.synchronize_device(device)
    elapsed_seconds = time.perf_counter() - started
    free_after_run = int(device.free_memory)
    memory_delta = max(0, free_before - min(free_after_allocation, free_after_run))
    final_qpos = np.asarray(data.qpos.numpy(), dtype=np.float64)
    final_qvel = np.asarray(data.qvel.numpy(), dtype=np.float64)
    overflow = np.asarray(data.overflow.numpy(), dtype=np.int64)
    finite = bool(np.isfinite(final_qpos).all() and np.isfinite(final_qvel).all())
    final_position_error_mm = np.abs(
        (final_qpos[:, center_joint] - rest_qpos[:, center_joint]) * 1000.0
    )
    final_velocity_mm_s = np.abs(final_qvel[:, center_joint] * 1000.0)
    release_complete = (
        final_position_error_mm <= release["position_error_limit_mm"]
    ) & (final_velocity_mm_s <= release["velocity_limit_mm_s"])
    minimum_delay = min(fixture["recipe_design"]["os_repeat_delay_ms_samples"])
    minimum_period = min(fixture["recipe_design"]["os_repeat_period_ms_samples"])
    active_ms = maximum_active_run * dt * 1000.0
    repeats = np.where(
        active_ms >= minimum_delay,
        np.floor((active_ms - minimum_delay) / minimum_period).astype(np.int64) + 1,
        0,
    )
    rows = []
    for index in range(nworld):
        margins = depth_margin_metrics(
            float(peak_mm[index]), float(actuation_mm), float(bottom_mm)
        )
        row = {
            "row_id": (
                f"{target['target_id']}__{scenario_id}__r{recipe['recipe_index']:03d}"
                f"__l{smoke['landing_sample_indices'][index]:03d}"
            ),
            "target_id": target["target_id"],
            "scenario_id": scenario_id,
            "recipe_index": recipe["recipe_index"],
            "landing_sample_index": smoke["landing_sample_indices"][index],
            "actuation_count": int(actuation_count[index]),
            "auto_repeat_count": int(repeats[index]),
            "neighbor_contact": bool(neighbor_contact[index]),
            "bottom_out_overflow": bool(bottom_overflow[index]),
            "release_complete": bool(release_complete[index]),
            "force_within_available": bool(
                peak_force[index] <= recipe["available_press_force_n"]
            ),
            "partial_press": bool(actuation_count[index] == 0),
            "double_actuation": bool(actuation_count[index] > 1),
            "peak_penetration_mm": float(peak_mm[index]),
            "peak_required_force_n": float(peak_force[index]),
            "dwell_above_actuation_ms": float(active_ms[index]),
            **margins,
            "final_position_error_mm": float(final_position_error_mm[index]),
            "final_velocity_mm_s": float(final_velocity_mm_s[index]),
        }
        if control is not None:
            row["control_id"] = control["control"]["control_id"]
        if tool_compliance is not None:
            row["peak_tool_compression_mm"] = float(
                peak_tool_compression_mm[index]
            )
            row["peak_tool_force_n"] = float(peak_tool_force_n[index])
        row["admitted"] = bool(
            row["actuation_count"] == 1
            and row["auto_repeat_count"] == 0
            and not row["neighbor_contact"]
            and not row["bottom_out_overflow"]
            and row["release_complete"]
            and row["force_within_available"]
        )
        rows.append(row)
    stack = _stack()
    receipt = {
        "schema": "tactevra.ws2_warp_smoke_receipt.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "execution_fixture_sha256": execution["fixture_sha256"],
        "device": device_name,
        "device_name": device.name,
        "stack": stack,
        "world_count": nworld,
        "settle_pass": settle_pass,
        "settle_steps": settle_steps,
        "motion_steps": total_steps if settle_pass else 0,
        "elapsed_seconds": elapsed_seconds,
        "wall_elapsed_seconds": time.perf_counter() - overall_started,
        "device_total_memory_bytes": int(device.total_memory),
        "device_memory_delta_bytes": memory_delta,
        "device_memory_delta_fraction": memory_delta / int(device.total_memory),
        "finite": finite,
        "overflow_zero": bool((overflow == 0).all()),
        "rows": rows,
        "depth_margin_summary": {
            "minimum_actuation_margin_mm": min(
                row["actuation_margin_mm"] for row in rows
            ),
            "minimum_bottom_out_margin_mm": min(
                row["bottom_out_margin_mm"] for row in rows
            ),
            "minimum_two_sided_margin_mm": min(
                row["minimum_depth_margin_mm"] for row in rows
            ),
            "maximum_midpoint_error_mm": max(
                row["midpoint_error_mm"] for row in rows
            ),
            "selection_priority": (
                "MAXIMIZE_WORST_CASE_MINIMUM_DEPTH_MARGIN_THEN_MINIMIZE_"
                "WORST_CASE_MIDPOINT_ERROR"
            ),
            "admission_gate_changed": False,
        },
        "status": (
            "PASS_EXPLORATORY_SMOKE"
            if settle_pass and finite and (overflow == 0).all() and len(rows) == nworld
            else "STOP_EXPLORATORY_SMOKE"
        ),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_commands": [],
        "permits": [],
        "transport_operations": [],
        "physical_authority": False,
    }
    if control is not None:
        receipt["positive_control_fixture_sha256"] = control["fixture_sha256"]
        receipt["control_id"] = control["control"]["control_id"]
        control_kind = control["control"].get("control_kind", "ACTUATION")
        receipt["control_kind"] = control_kind
        receipt["effective_recipe"] = recipe
        receipt["effective_release_protocol"] = release
        if tool_compliance is not None:
            receipt["tool_compliance"] = tool_compliance
        positive_pass = bool(
            all(row["actuation_count"] == 1 for row in rows)
            and not any(row["partial_press"] for row in rows)
            and not any(row["bottom_out_overflow"] for row in rows)
            and (
                control_kind != "RELEASE"
                or all(row["release_complete"] for row in rows)
            )
            and settle_pass
            and finite
            and (overflow == 0).all()
        )
        receipt["positive_control_pass"] = positive_pass
        receipt["status"] = (
            "PASS_EXPLORATORY_POSITIVE_CONTROL"
            if positive_pass
            else "STOP_EXPLORATORY_POSITIVE_CONTROL"
        )
    return receipt


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
    parser.add_argument(
        "mode",
        choices=(
            "manifest",
            "cpu-smoke",
            "landing-prepass",
            "phone",
            "smoke-worker",
            "positive-control-worker",
            "compare",
        ),
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--left", type=Path)
    parser.add_argument("--right", type=Path)
    parser.add_argument("--execution", type=Path)
    parser.add_argument("--device", choices=DEVICES)
    parser.add_argument("--control", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    fixture = load_fixture(args.fixture.resolve(strict=True), workspace=workspace)
    if args.mode == "manifest":
        result = build_manifest(fixture, workspace=workspace)
    elif args.mode == "cpu-smoke":
        result = cpu_contact_smoke(fixture, workspace=workspace)
    elif args.mode == "landing-prepass":
        result = landing_prepass(fixture, workspace=workspace)
    elif args.mode in {"smoke-worker", "positive-control-worker"}:
        if args.execution is None or args.device is None:
            parser.error(f"{args.mode} requires --execution and --device")
        execution = load_execution_fixture(
            args.execution.resolve(strict=True), workspace=workspace, parent=fixture
        )
        control = None
        if args.mode == "positive-control-worker":
            if args.control is None:
                parser.error("positive-control-worker requires --control")
            control = load_positive_control_fixture(
                args.control.resolve(strict=True),
                workspace=workspace,
                parent=fixture,
                execution=execution,
            )
        result = run_smoke_worker(
            fixture,
            execution,
            workspace=workspace,
            device_name=args.device,
            control=control,
        )
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
