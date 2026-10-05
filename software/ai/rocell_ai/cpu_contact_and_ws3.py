"""CPU-only contact screens and continuous-typing preparation.

This module has no controller, transport, permit, hardware adapter, or physical
authority.  It reuses the frozen exact convex-sweep implementation and refuses
to run the WS3 policy screen until a separately admitted WS2 recipe is bound.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from rocell_ai.first_motion_clearance_waypoints import (
    _World,
    _hand_board_transform,
    load_passive_tool_rerun_fixture,
    validate_pose_bundle_tool_configuration,
)
from rocell_ai.tool_bound_exact_clearance import (
    _aabb_box_lower_bound_mm,
    _collider_box_distance_mm,
    _component_shapes,
    _key_boxes,
    _swept_collider_and_aabb,
    _translated_transform,
    load_pose_family_result,
)

SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
COUNTER_NAMES = (
    "hardware_write_count",
    "physical_movement_count",
    "real_command_count",
    "permit_count",
    "transport_count",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _resolve(workspace: Path, path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else workspace / candidate


def load_cpu_contact_fixture(path: Path, *, workspace: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    claimed = document.pop("fixture_sha256", None)
    if claimed != _sha(document):
        raise ValueError("CPU contact/WS3 fixture hash mismatch")
    document["fixture_sha256"] = claimed
    if document.get("schema") != "tactevra.cpu_contact_and_ws3_fixture.v1":
        raise ValueError("unexpected CPU contact/WS3 fixture schema")
    if document.get("scope") != SCOPE or document.get("physical_authority") is not False:
        raise ValueError("fixture is not zero-authority simulation")
    if any(document.get("counters", {}).get(name, 0) for name in COUNTER_NAMES):
        raise ValueError("fixture contains authority-bearing counters")
    if document["runtime_manifest"].get("gpu_jobs_authorized") is not False:
        raise ValueError("fixture authorizes GPU work")
    for name, section in document["sections"].items():
        section_copy = dict(section)
        section_claim = section_copy.pop("section_sha256", None)
        if section_claim != _sha(section_copy):
            raise ValueError(f"section hash mismatch: {name}")
    for binding in document["bindings"].values():
        source = _resolve(workspace, binding["path"])
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source changed: {binding['path']}")
    return document


def _load_geometry(
    fixture: dict[str, Any], *, workspace: Path
) -> tuple[dict[str, Any], dict[str, Any], _World]:
    exact_path = _resolve(
        workspace, fixture["bindings"]["exact_clearance_fixture"]["path"]
    )
    exact_fixture = json.loads(exact_path.read_text(encoding="utf-8"))
    pose_path = _resolve(
        workspace, fixture["bindings"]["tool_110mm_pose_family"]["path"]
    )
    pose_family = load_pose_family_result(pose_path, exact_fixture)
    expected = set(fixture["sections"]["stage_ef_contact"][
        "tool_configuration_sha256"
    ])
    observed = {row["tool_configuration_sha256"] for row in pose_family["profiles"]}
    if observed != expected:
        raise ValueError("110 mm pose family profile identity mismatch")
    for profile in pose_family["profiles"]:
        bundle = profile["pose_bundle"]
        config = bundle["tool_configuration"]
        validate_pose_bundle_tool_configuration(bundle, config)
        if float(config["total_hand_tcp_to_tip_length_mm"]) != 110.0:
            raise ValueError("pose bundle is not bound to the 110 mm tool")
        if float(config["distal_tip_radius_mm"]) != 3.0:
            raise ValueError("pose bundle is not bound to the 3 mm tip")

    prior_path = _resolve(
        workspace, exact_fixture["bindings"]["prior_fixture"]["path"]
    )
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    passive_path = _resolve(workspace, prior["bindings"]["prior_fixture"]["path"])
    passive = load_passive_tool_rerun_fixture(passive_path)
    design_path = _resolve(
        workspace, passive["bindings"]["collision_design_fixture"]["path"]
    )
    world = _World(json.loads(design_path.read_text(encoding="utf-8")), workspace)
    return exact_fixture, pose_family, world


def _nearest_key_distance(
    swept: Any,
    swept_aabb: tuple[Any, Any],
    keys: list[dict[str, Any]],
    *,
    requested_target_id: str,
    component: str,
) -> tuple[float, str | None]:
    candidates = sorted(
        (
            _aabb_box_lower_bound_mm(
                swept_aabb,
                box_center_mm=key["center"],
                box_size_mm=key["size"],
            ),
            key,
        )
        for key in keys
        if not (
            component == "DISTAL_TIP" and key["target_id"] == requested_target_id
        )
    )
    minimum = float("inf")
    limiting_key = None
    for lower_bound, key in candidates:
        if lower_bound >= minimum - 1e-12:
            break
        distance = _collider_box_distance_mm(
            swept,
            box_center_mm=key["center"],
            box_size_mm=key["size"],
        )
        if distance < minimum:
            minimum = distance
            limiting_key = key["target_id"]
    return minimum, limiting_key


def run_stage_ef_contact_screen(
    fixture: dict[str, Any], *, workspace: Path
) -> dict[str, Any]:
    """Screen exact press/release sweeps for each bound 110 mm pose."""

    exact_fixture, pose_family, world = _load_geometry(fixture, workspace=workspace)
    section = fixture["sections"]["stage_ef_contact"]
    widths = tuple(float(value) for value in section["keycap_width_height_mm"])
    thicknesses = tuple(float(value) for value in section["keycap_thickness_mm"])
    thresholds = tuple(float(value) for value in section[
        "minimum_non_target_clearance_mm"
    ])
    rows: list[dict[str, Any]] = []
    global_minimum = float("inf")
    for profile in pose_family["profiles"]:
        bundle = profile["pose_bundle"]
        config = bundle["tool_configuration"]
        length = float(config["total_hand_tcp_to_tip_length_mm"])
        components = _component_shapes(exact_fixture, workspace, config)
        boxes = {
            (width, thickness): _key_boxes(bundle, width, thickness)
            for width in widths
            for thickness in thicknesses
        }
        for pose in bundle["poses"]:
            target_id = pose["target_id"]
            xyz = pose["contact_target_board_mm"]
            contact = (float(xyz["x"]), float(xyz["y"]), float(xyz["z"]))
            joints = tuple(float(value) for value in pose["joint_positions_rad"])
            final_transform = _hand_board_transform(world, joints)
            for hover_mm in section["hover_height_above_contact_mm"]:
                hover = (contact[0], contact[1], contact[2] + float(hover_mm))
                contact_transform = _translated_transform(
                    final_transform, contact, length
                )
                hover_transform = _translated_transform(final_transform, hover, length)
                for stage, start_transform, end_transform in (
                    ("E_PRESS", hover_transform, contact_transform),
                    ("F_RELEASE", contact_transform, hover_transform),
                ):
                    minimum = float("inf")
                    limiting: dict[str, Any] | None = None
                    target_contact_all_shapes = True
                    for component in components:
                        swept, swept_aabb = _swept_collider_and_aabb(
                            component["vertices"],
                            start_transform,
                            end_transform,
                            margin_mm=component["margin_mm"],
                        )
                        for width in widths:
                            for thickness in thicknesses:
                                key_rows = boxes[(width, thickness)]
                                if component["component"] == "DISTAL_TIP":
                                    own = next(
                                        row
                                        for row in key_rows
                                        if row["target_id"] == target_id
                                    )
                                    own_distance = _collider_box_distance_mm(
                                        swept,
                                        box_center_mm=own["center"],
                                        box_size_mm=own["size"],
                                    )
                                    target_contact_all_shapes &= own_distance <= 1e-6
                                distance, key_id = _nearest_key_distance(
                                    swept,
                                    swept_aabb,
                                    key_rows,
                                    requested_target_id=target_id,
                                    component=component["component"],
                                )
                                if distance < minimum:
                                    minimum = distance
                                    limiting = {
                                        "key_id": key_id,
                                        "component": component["component"],
                                        "key_width_mm": width,
                                        "key_thickness_mm": thickness,
                                    }
                    passes = {
                        str(value): minimum + 1e-9 >= value for value in thresholds
                    }
                    decision = (
                        "PASS_EXPLORATORY_STAGE_CONTACT"
                        if target_contact_all_shapes and all(passes.values())
                        else "STOP_TARGET_OR_NEIGHBOR_CONTACT"
                    )
                    global_minimum = min(global_minimum, minimum)
                    rows.append(
                        {
                            "tool_configuration_sha256": profile[
                                "tool_configuration_sha256"
                            ],
                            "tip_exposed_length_mm": config[
                                "distal_tip_exposed_length_mm"
                            ],
                            "target_id": target_id,
                            "stage": stage,
                            "hover_height_mm": float(hover_mm),
                            "target_contact_all_geometry_endpoints": bool(
                                target_contact_all_shapes
                            ),
                            "minimum_non_target_clearance_mm": minimum,
                            "limiting_case": limiting,
                            "threshold_pass": passes,
                            "decision": decision,
                        }
                    )
    result = {
        "schema": "tactevra.stage_ef_exact_contact_result.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "section_sha256": section["section_sha256"],
        "pose_family_receipt_sha256": pose_family["receipt_sha256"],
        "row_count": len(rows),
        "target_count": len({row["target_id"] for row in rows}),
        "global_minimum_non_target_clearance_mm": global_minimum,
        "pass_row_count": sum(
            row["decision"] == "PASS_EXPLORATORY_STAGE_CONTACT" for row in rows
        ),
        "rows": rows,
        "decision": (
            "PASS_EXPLORATORY_STAGE_EF_EXACT_CONTACT"
            if all(
                row["decision"] == "PASS_EXPLORATORY_STAGE_CONTACT" for row in rows
            )
            else "STOP_STAGE_EF_CONTACT"
        ),
        "gpu_job_count": 0,
        **{name: 0 for name in COUNTER_NAMES},
        "physical_authority": False,
        "limitations": fixture["limitations"],
    }
    result["receipt_sha256"] = _sha(result)
    return result


def run_phone_capacitive_matrix(fixture: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the frozen analytic phone area/timing matrix."""

    section = fixture["sections"]["phone_capacitive"]
    rows = []
    for radius in section["contact_radius_mm"]:
        for fraction in section["effective_contact_area_fraction"]:
            area = math.pi * float(radius) ** 2 * float(fraction)
            for minimum_area in section["minimum_registration_area_mm2"]:
                for duration in section["duration_ms"]:
                    for minimum_tap in section["minimum_tap_duration_ms"]:
                        for long_press in section["long_press_threshold_ms"]:
                            area_ok = area + 1e-12 >= float(minimum_area)
                            duration_ok = float(duration) >= float(minimum_tap)
                            long_press_detected = float(duration) >= float(long_press)
                            admitted = area_ok and duration_ok and not long_press_detected
                            rows.append(
                                {
                                    "contact_radius_mm": float(radius),
                                    "effective_contact_area_fraction": float(fraction),
                                    "effective_contact_area_mm2": area,
                                    "minimum_registration_area_mm2": float(minimum_area),
                                    "duration_ms": float(duration),
                                    "minimum_tap_duration_ms": float(minimum_tap),
                                    "long_press_threshold_ms": float(long_press),
                                    "area_sufficient": area_ok,
                                    "duration_sufficient": duration_ok,
                                    "long_press_detected": long_press_detected,
                                    "admitted_tap": admitted,
                                }
                            )
    by_radius: dict[str, dict[str, Any]] = {}
    for radius in section["contact_radius_mm"]:
        radius_rows = [row for row in rows if row["contact_radius_mm"] == radius]
        by_radius[str(float(radius))] = {
            "admitted_cell_count": sum(row["admitted_tap"] for row in radius_rows),
            "cell_count": len(radius_rows),
            "any_admitted": any(row["admitted_tap"] for row in radius_rows),
            "all_declared_cells_admitted": all(
                row["admitted_tap"] for row in radius_rows
            ),
            "maximum_effective_area_mm2": max(
                row["effective_contact_area_mm2"] for row in radius_rows
            ),
            "minimum_effective_area_mm2": min(
                row["effective_contact_area_mm2"] for row in radius_rows
            ),
        }
    ceiling = float(section["keyboard_shared_tip_radius_ceiling_mm"])
    small = [
        row for radius, row in by_radius.items() if float(radius) <= ceiling
    ]
    large = [
        row for radius, row in by_radius.items() if float(radius) > ceiling
    ]
    if any(row["all_declared_cells_admitted"] for row in small):
        decision = "ONE_TIP_SUPPORTED_ACROSS_DECLARED_RANGES"
    elif not any(row["any_admitted"] for row in small) and any(
        row["any_admitted"] for row in large
    ):
        decision = "TWO_TIPS_REQUIRED_ACROSS_DECLARED_RANGES"
    else:
        decision = "UNRESOLVED_PHYSICAL_MEASUREMENT_REQUIRED"
    result = {
        "schema": "tactevra.phone_capacitive_contact_result.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "section_sha256": section["section_sha256"],
        "row_count": len(rows),
        "admitted_tap_count": sum(row["admitted_tap"] for row in rows),
        "long_press_count": sum(row["long_press_detected"] for row in rows),
        "by_radius": by_radius,
        "decision": decision,
        "rows": rows,
        "gpu_job_count": 0,
        **{name: 0 for name in COUNTER_NAMES},
        "physical_authority": False,
        "limitations": fixture["limitations"],
    }
    result["receipt_sha256"] = _sha(result)
    return result


def validate_ws2_recipe_binding(
    fixture: dict[str, Any], *, workspace: Path
) -> dict[str, Any]:
    section = fixture["sections"]["workstream_3"]
    binding = section.get("press_recipe_binding")
    if binding is None:
        raise ValueError("WS3 blocked: admitted WS2 press recipe is not bound")
    path = _resolve(workspace, binding["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != binding["sha256"]:
        raise ValueError("WS2 press recipe file hash mismatch")
    recipe = json.loads(path.read_text(encoding="utf-8"))
    if recipe.get("schema") != section["required_press_recipe_schema"]:
        raise ValueError("WS2 press recipe schema mismatch")
    if recipe.get("decision") != section["required_press_recipe_status"]:
        raise ValueError("WS2 press recipe is not admitted")
    unsigned = dict(recipe)
    claimed = unsigned.pop("receipt_sha256", None)
    if claimed != _sha(unsigned):
        raise ValueError("WS2 press recipe receipt mismatch")
    if any(recipe.get(name, 0) for name in COUNTER_NAMES):
        raise ValueError("WS2 press recipe carries authority")
    if recipe.get("physical_authority") is not False:
        raise ValueError("WS2 press recipe carries physical authority")
    return recipe


def prepare_ws3_transition_harness(
    fixture: dict[str, Any], *, workspace: Path
) -> dict[str, Any]:
    """Validate geometry and enumerate WS3 while preserving the recipe block."""

    _, pose_family, _ = _load_geometry(fixture, workspace=workspace)
    section = fixture["sections"]["workstream_3"]
    target_orders = [
        tuple(row["target_id"] for row in profile["pose_bundle"]["poses"])
        for profile in pose_family["profiles"]
    ]
    if any(order != target_orders[0] for order in target_orders[1:]):
        raise ValueError("tool configurations disagree on target order")
    target_ids = target_orders[0]
    pair_count = len(target_ids) ** 2
    scenario_count = (
        pair_count
        * len(pose_family["profiles"])
        * len(section["hover_height_above_contact_mm"])
        * len(section["transit_height_board_z_mm"])
    )
    blocked_reason = None
    try:
        recipe = validate_ws2_recipe_binding(fixture, workspace=workspace)
    except ValueError as exc:
        recipe = None
        blocked_reason = str(exc)
    result = {
        "schema": "tactevra.ws3_transition_harness_readiness.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "section_sha256": section["section_sha256"],
        "pose_family_receipt_sha256": pose_family["receipt_sha256"],
        "target_count": len(target_ids),
        "ordered_pair_count": pair_count,
        "includes_repeat_pairs": True,
        "transition_scenario_count": scenario_count,
        "tool_configuration_count": len(pose_family["profiles"]),
        "path_phases": section["path_phases"],
        "exact_distance_method": section["distance_method"],
        "collision_screen_implemented": True,
        "press_recipe_receipt_sha256": (
            recipe["receipt_sha256"] if recipe is not None else None
        ),
        "policy_recommendation": None,
        "decision": (
            section["admitted_decision"]
            if recipe is not None
            else section["blocked_decision"]
        ),
        "blocked_reason": blocked_reason,
        "gpu_job_count": 0,
        **{name: 0 for name in COUNTER_NAMES},
        "physical_authority": False,
        "limitations": fixture["limitations"],
    }
    result["receipt_sha256"] = _sha(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("stage-ef", "phone", "ws3-prepare"))
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--workspace", default=Path("."), type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    fixture = load_cpu_contact_fixture(args.fixture, workspace=workspace)
    if args.mode == "stage-ef":
        result = run_stage_ef_contact_screen(fixture, workspace=workspace)
    elif args.mode == "phone":
        result = run_phone_capacitive_matrix(fixture)
    else:
        result = prepare_ws3_transition_harness(fixture, workspace=workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "decision": result["decision"],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()

