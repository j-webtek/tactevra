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
import re
from typing import Any

from rocell_ai.first_motion_clearance_waypoints import (
    _World,
    _hand_board_transform,
    _solve_seeded,
    _tip_xyz,
    bind_pose_bundle_tool_configuration,
    load_passive_tool_rerun_fixture,
    tool_configuration,
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
    if document.get("schema") not in {
        "tactevra.cpu_contact_and_ws3_fixture.v1",
        "tactevra.cpu_contact_and_ws3_fixture.v2",
    }:
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


def _world_from_exact_fixture(
    exact_fixture: dict[str, Any], *, workspace: Path
) -> _World:
    """Construct the retained exploratory world without opening hardware."""

    prior_path = _resolve(
        workspace, exact_fixture["bindings"]["prior_fixture"]["path"]
    )
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    passive_path = _resolve(workspace, prior["bindings"]["prior_fixture"]["path"])
    passive = load_passive_tool_rerun_fixture(passive_path)
    design_path = _resolve(
        workspace, passive["bindings"]["collision_design_fixture"]["path"]
    )
    return _World(json.loads(design_path.read_text(encoding="utf-8")), workspace)


def _validate_pose_family(
    result: dict[str, Any], fixture: dict[str, Any]
) -> dict[str, Any]:
    unsigned = dict(result)
    claimed = unsigned.pop("receipt_sha256", None)
    if claimed != _sha(unsigned):
        raise ValueError("pose-family result receipt mismatch")
    if result.get("schema") != "tactevra.tool_bound_pose_family_result.v1":
        raise ValueError("unexpected tool-bound pose-family schema")
    if result.get("fixture_sha256") != fixture["fixture_sha256"]:
        raise ValueError("pose-family result is bound to another fixture")
    for profile in result["profiles"]:
        bundle = profile["pose_bundle"]
        validate_pose_bundle_tool_configuration(bundle, bundle["tool_configuration"])
        if profile["tool_configuration_sha256"] != bundle[
            "tool_configuration_sha256"
        ]:
            raise ValueError("profile and pose-bundle tool hashes differ")
    if any(result.get(name) for name in COUNTER_NAMES):
        raise ValueError("pose-family result carries authority")
    if result.get("physical_authority") is not False:
        raise ValueError("pose-family result carries physical authority")
    return result


def build_candidate51_pose_family(
    fixture: dict[str, Any], *, workspace: Path
) -> dict[str, Any]:
    """Independently solve the frozen 51 targets for both 110 mm profiles."""

    if fixture["schema"] != "tactevra.cpu_contact_and_ws3_fixture.v2":
        raise ValueError("candidate51 pose generation requires the v2 fixture")
    section = fixture["sections"]["pose_generation"]
    exact_path = _resolve(
        workspace, fixture["bindings"]["exact_clearance_fixture"]["path"]
    )
    exact_fixture = json.loads(exact_path.read_text(encoding="utf-8"))
    source_path = _resolve(
        workspace, fixture["bindings"]["candidate51_pose_source"]["path"]
    )
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if source.get("target_count") != 51 or len(source.get("poses", [])) != 51:
        raise ValueError("candidate51 source does not contain exactly 51 targets")
    target_ids = tuple(row["target_id"] for row in source["poses"])
    required = set(section["required_added_target_ids"])
    if not required.issubset(target_ids) or len(set(target_ids)) != 51:
        raise ValueError("candidate51 source target identities are incomplete")
    world = _world_from_exact_fixture(exact_fixture, workspace=workspace)
    length = float(section["output_tool_length_mm"])
    solver = world.solver(length)
    poses = []
    failures = []
    for row in source["poses"]:
        target_document = row["contact_target_board_mm"]
        target = (
            float(target_document["x"]),
            float(target_document["y"]),
            float(target_document["z"]),
        )
        seed = tuple(float(value) for value in row["joint_positions_rad"])
        solved = _solve_seeded(world, solver, target, seed)
        if solved is None:
            failures.append(row["target_id"])
            continue
        achieved = _tip_xyz(world, solved, length)
        error = math.sqrt(sum(
            (actual - expected) ** 2
            for actual, expected in zip(achieved, target, strict=True)
        ))
        pose = {
            "target_id": row["target_id"],
            "contact_target_board_mm": dict(target_document),
            "joint_positions_rad": list(solved),
            "achieved_tip_board_mm": list(achieved),
            "ik_position_error_mm": error,
        }
        for optional in ("center_board_mm", "candidate_safe_half_extent_mm"):
            if optional in row:
                pose[optional] = row[optional]
        poses.append(pose)
    maximum_error = max((row["ik_position_error_mm"] for row in poses), default=None)
    if failures or len(poses) != 51:
        decision = "STOP_CANDIDATE51_UNREACHABLE_TARGET"
    elif maximum_error is None or maximum_error > float(
        section["maximum_ik_position_error_mm"]
    ):
        decision = "STOP_CANDIDATE51_IK_ERROR"
    else:
        decision = "PASS_EXPLORATORY_CANDIDATE51_110MM_POSES"

    profiles = []
    catalog_sha = fixture["bindings"]["candidate_catalog"]["sha256"]
    for exposed in section["distal_tip_exposed_length_mm"]:
        config = tool_configuration(
            exact_fixture,
            source,
            total_length_mm=length,
            exposed_length_mm=float(exposed),
            tip_radius_mm=float(section["tip_radius_mm"]),
        )
        config["target_catalog_sha256"] = catalog_sha
        base = {
            "scope": SCOPE,
            "status": decision,
            "fixture_sha256": fixture["fixture_sha256"],
            "joint_order": source["joint_order"],
            "layout_overlay": source["layout_overlay"],
            "target_count": 51,
            "solved_target_count": len(poses),
            "failed_target_ids": failures,
            "poses": poses,
            "limitations": fixture["limitations"],
        }
        bundle = bind_pose_bundle_tool_configuration(base, config)
        validate_pose_bundle_tool_configuration(bundle, config)
        profiles.append({
            "tool_configuration_sha256": bundle["tool_configuration_sha256"],
            "pose_bundle": bundle,
        })
    result = {
        "schema": "tactevra.tool_bound_pose_family_result.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "reach_by_length_mm": {
            "110.0": {
                "solved_target_count": len(poses),
                "failed_target_ids": failures,
                "all_targets_reached": not failures and len(poses) == 51,
                "maximum_ik_position_error_mm": maximum_error,
            }
        },
        "profiles": profiles,
        "profile_count": len(profiles),
        "decision": decision,
        "evaluation_opened": False,
        "gpu_job_count": 0,
        **{name: 0 for name in COUNTER_NAMES},
        "physical_authority": False,
    }
    result["receipt_sha256"] = _sha(result)
    return result


def _load_geometry(
    fixture: dict[str, Any], *, workspace: Path
) -> tuple[dict[str, Any], dict[str, Any], _World]:
    exact_path = _resolve(
        workspace, fixture["bindings"]["exact_clearance_fixture"]["path"]
    )
    exact_fixture = json.loads(exact_path.read_text(encoding="utf-8"))
    if fixture["schema"] == "tactevra.cpu_contact_and_ws3_fixture.v1":
        pose_path = _resolve(
            workspace, fixture["bindings"]["tool_110mm_pose_family"]["path"]
        )
        pose_family = load_pose_family_result(pose_path, exact_fixture)
        expected = set(fixture["sections"]["stage_ef_contact"][
            "tool_configuration_sha256"
        ])
    else:
        pose_path = _resolve(
            workspace, fixture["sections"]["pose_generation"][
                "external_output_path"
            ]
        )
        pose_family = _validate_pose_family(
            json.loads(pose_path.read_text(encoding="utf-8")), fixture
        )
        expected = {
            row["tool_configuration_sha256"] for row in pose_family["profiles"]
        }
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

    world = _world_from_exact_fixture(exact_fixture, workspace=workspace)
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
        ((
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
         )),
        key=lambda item: (item[0], item[1]["target_id"]),
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


def assess_c02_ws3_recipe_compatibility(
    *,
    c02_final_path: Path,
    c02_final_sha256: str,
    ws2_physics_path: Path,
    ws2_physics_sha256: str,
    c03_fixture: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed unless C02's selected tip matches the C03 tool geometry.

    This assessment deliberately does not create a WS2 recipe envelope.  It is
    the identity gate before the existing 2,601-pair screen can be opened.
    """

    if hashlib.sha256(c02_final_path.read_bytes()).hexdigest() != c02_final_sha256:
        raise ValueError("C02 final-admission file hash mismatch")
    if hashlib.sha256(ws2_physics_path.read_bytes()).hexdigest() != ws2_physics_sha256:
        raise ValueError("WS2 physics fixture file hash mismatch")
    final = json.loads(c02_final_path.read_text(encoding="utf-8"))
    claimed = final.get("result_sha256")
    unsigned = dict(final)
    unsigned.pop("result_sha256", None)
    if claimed != _sha(unsigned):
        raise ValueError("C02 final-admission result hash mismatch")
    if final.get("decision") != "COMPLETE_ROBUST_UNIVERSAL_SIMULATION_ONLY":
        raise ValueError("C02 final admission is not a robust simulation result")
    if final.get("physical_authority") is not False:
        raise ValueError("C02 final admission carries physical authority")
    if int(final.get("hardware_write_count", 0)) or int(
        final.get("physical_movement_count", 0)
    ):
        raise ValueError("C02 final admission carries nonzero physical counters")

    universal = final.get("summary", {}).get("universal_families", [])
    if not universal:
        raise ValueError("C02 final admission has no universal recipe")
    selected = universal[0]
    tip_id = str(selected["tip_id"])
    match = re.fullmatch(r"capsule-r(?P<radius>[0-9.]+)-m(?P<multiple>[0-9.]+)", tip_id)
    if match is None:
        raise ValueError("C02 selected tip identity is not a supported capsule")
    radius_mm = float(match.group("radius"))
    multiple = float(match.group("multiple"))
    physics = json.loads(ws2_physics_path.read_text(encoding="utf-8"))
    capsule = physics["contact_model"]["tip_families"]["capsule"]
    if radius_mm not in [float(v) for v in capsule["radius_samples_mm"]]:
        raise ValueError("C02 selected capsule radius is absent from physics fixture")
    if multiple not in [
        float(v) for v in capsule["half_length_radius_multiple_samples"]
    ]:
        raise ValueError("C02 selected capsule multiplier is absent from physics fixture")

    section = c03_fixture["sections"]["workstream_3"]
    c03_radius_mm = float(section["tip_radius_mm"])
    half_length_mm = radius_mm * multiple
    exposed_length_mm = 2.0 * half_length_mm
    allowed_exposed_lengths = [
        float(value) for value in section["distal_tip_exposed_length_mm"]
    ]
    geometry_matches = math.isclose(
        radius_mm, c03_radius_mm, abs_tol=1e-12
    ) and any(
        math.isclose(exposed_length_mm, value, abs_tol=1e-12)
        for value in allowed_exposed_lengths
    )
    decision = (
        "READY_TO_BUILD_ZERO_AUTHORITY_RECIPE_ENVELOPE"
        if geometry_matches
        else "STOP_C02_C03_TOOL_IDENTITY_MISMATCH"
    )
    result = {
        "schema": "tactevra.c02_c03_recipe_binding_assessment.v1",
        "scope": SCOPE,
        "decision": decision,
        "c02_final_file_sha256": c02_final_sha256,
        "c02_result_sha256": claimed,
        "c02_campaign_receipt_sha256": final["campaign_receipt_sha256"],
        "c02_selected_universal_recipe": selected,
        "c02_tip_geometry": {
            "tip_id": tip_id,
            "shape": "capsule",
            "radius_mm": radius_mm,
            "half_length_mm": half_length_mm,
            "exposed_length_mm": exposed_length_mm,
        },
        "c03_fixture_sha256": c03_fixture["fixture_sha256"],
        "c03_expected_tip_geometry": {
            "shape": "capsule",
            "radius_mm": c03_radius_mm,
            "allowed_exposed_length_mm": allowed_exposed_lengths,
            "tool_length_mm": float(section["tool_length_mm"]),
        },
        "target_count": int(selected["target_count"]),
        "ordered_pair_count": int(section["ordered_pair_count"]),
        "recipe_envelope_emitted": False,
        "all_pairs_screen_executed": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
        "limitations": [
            "C02 qualifies contact only inside its synthetic sampled ranges.",
            "C03 is frozen around a 110 mm tool with a 3 mm distal-tip radius.",
            "A 6 mm C02 tip cannot be silently substituted into the 3 mm C03 geometry.",
            "Reorientation and full robot/tool/workcell continuous collision remain outside the prepared key-only screen.",
            "No arm-lane or integration gate is changed by this assessment.",
        ],
        "next_dependency": (
            "BUILD_HASH_BOUND_ZERO_AUTHORITY_RECIPE_ENVELOPE"
            if geometry_matches
            else (
                "PREDECLARE_AND_RUN_51_TARGET_6MM_C03_GEOMETRY_FEASIBILITY_OR_"
                "OBTAIN_A_C02_UNIVERSAL_RECIPE_FOR_THE_3MM_TIP"
            )
        ),
    }
    result["receipt_sha256"] = _sha(result)
    return result


def build_ws2_recipe_envelope(
    assessment: dict[str, Any],
) -> dict[str, Any]:
    """Bind one admitted C02 contact identity for the CPU-only WS3 screen."""

    if assessment.get("schema") != "tactevra.c02_c03_recipe_binding_assessment.v1":
        raise ValueError("unexpected C02/C03 assessment schema")
    unsigned = dict(assessment)
    claimed = unsigned.pop("receipt_sha256", None)
    if claimed != _sha(unsigned):
        raise ValueError("C02/C03 assessment receipt mismatch")
    if assessment.get("decision") != "READY_TO_BUILD_ZERO_AUTHORITY_RECIPE_ENVELOPE":
        raise ValueError("C02/C03 assessment is not geometry compatible")
    if assessment.get("physical_authority") is not False or any(
        assessment.get(name, 0) for name in COUNTER_NAMES
    ):
        raise ValueError("C02/C03 assessment carries authority")
    selected = assessment["c02_selected_universal_recipe"]
    geometry = assessment["c02_tip_geometry"]
    expected = assessment["c03_expected_tip_geometry"]
    if int(selected["target_count"]) != int(assessment["target_count"]):
        raise ValueError("selected C02 recipe does not cover the declared targets")
    if not math.isclose(
        float(geometry["radius_mm"]), float(expected["radius_mm"]), abs_tol=1e-12
    ) or not any(
        math.isclose(
            float(geometry["exposed_length_mm"]), float(value), abs_tol=1e-12
        )
        for value in expected["allowed_exposed_length_mm"]
    ):
        raise ValueError("selected C02 tool geometry is not admitted by C03")
    result = {
        "schema": "tactevra.ws2_press_recipe_envelope.v1",
        "scope": SCOPE,
        "decision": "PASS_EXPLORATORY_WS2_RECIPE_ENVELOPE",
        "assessment_receipt_sha256": claimed,
        "c02_final_file_sha256": assessment["c02_final_file_sha256"],
        "c02_result_sha256": assessment["c02_result_sha256"],
        "c02_campaign_receipt_sha256": assessment[
            "c02_campaign_receipt_sha256"
        ],
        "c03_fixture_sha256": assessment["c03_fixture_sha256"],
        "selected_universal_recipe": selected,
        "tool_geometry": geometry,
        "tool_length_mm": float(expected["tool_length_mm"]),
        "target_count": int(assessment["target_count"]),
        "ordered_pair_count": int(assessment["ordered_pair_count"]),
        "limitations": assessment["limitations"] + [
            "This envelope binds a synthetic contact candidate for CPU geometry screening only.",
            "It grants no motion policy, execution permit, controller command, or physical authority.",
        ],
        **{name: 0 for name in COUNTER_NAMES},
        "physical_authority": False,
    }
    result["receipt_sha256"] = _sha(result)
    return result


def _select_recipe_pose_family(
    pose_family: dict[str, Any], recipe: dict[str, Any]
) -> dict[str, Any]:
    geometry = recipe["tool_geometry"]
    tool_length_mm = float(recipe["tool_length_mm"])
    selected = []
    for profile in pose_family["profiles"]:
        config = profile["pose_bundle"]["tool_configuration"]
        if (
            math.isclose(
                float(config["distal_tip_radius_mm"]),
                float(geometry["radius_mm"]),
                abs_tol=1e-12,
            )
            and math.isclose(
                float(config["distal_tip_exposed_length_mm"]),
                float(geometry["exposed_length_mm"]),
                abs_tol=1e-12,
            )
            and math.isclose(
                float(config["total_hand_tcp_to_tip_length_mm"]),
                tool_length_mm,
                abs_tol=1e-12,
            )
        ):
            selected.append(profile)
    if len(selected) != 1:
        raise ValueError("WS2 recipe must select exactly one C03 pose profile")
    result = dict(pose_family)
    result["profiles"] = selected
    result["profile_count"] = 1
    return result


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
    if recipe is not None:
        pose_family = _select_recipe_pose_family(pose_family, recipe)
        target_orders = [
            tuple(row["target_id"] for row in profile["pose_bundle"]["poses"])
            for profile in pose_family["profiles"]
        ]
        target_ids = target_orders[0]
        pair_count = len(target_ids) ** 2
        scenario_count = (
            pair_count
            * len(pose_family["profiles"])
            * len(section["hover_height_above_contact_mm"])
            * len(section["transit_height_board_z_mm"])
        )
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


def run_ws3_transition_screen(
    fixture: dict[str, Any], *, workspace: Path
) -> dict[str, Any]:
    """Run the frozen exact key-clearance screen after WS2 admits a recipe.

    Source release uses the source pose orientation. Rise, transit, and descent
    use the destination approach orientation. The reorientation between those
    two fixed-orientation families is intentionally outside this key-only
    screen and remains a workcell collision-planning dependency.
    """

    recipe = validate_ws2_recipe_binding(fixture, workspace=workspace)
    exact_fixture, pose_family, world = _load_geometry(fixture, workspace=workspace)
    pose_family = _select_recipe_pose_family(pose_family, recipe)
    section = fixture["sections"]["workstream_3"]
    ef_section = fixture["sections"]["stage_ef_contact"]
    widths = tuple(float(value) for value in ef_section["keycap_width_height_mm"])
    thicknesses = tuple(float(value) for value in ef_section["keycap_thickness_mm"])
    thresholds = tuple(float(value) for value in section["minimum_clearance_mm"])
    rows: list[dict[str, Any]] = []
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
        poses = {row["target_id"]: row for row in bundle["poses"]}
        transforms = {}
        contacts = {}
        for target_id, pose in poses.items():
            xyz = pose["contact_target_board_mm"]
            contacts[target_id] = (
                float(xyz["x"]), float(xyz["y"]), float(xyz["z"])
            )
            transforms[target_id] = _hand_board_transform(
                world, tuple(float(value) for value in pose["joint_positions_rad"])
            )
        for source_id, source_pose in poses.items():
            del source_pose
            for destination_id in poses:
                source_contact = contacts[source_id]
                destination_contact = contacts[destination_id]
                source_orientation = transforms[source_id]
                destination_orientation = transforms[destination_id]
                for hover_mm in section["hover_height_above_contact_mm"]:
                    source_hover = (
                        source_contact[0], source_contact[1],
                        source_contact[2] + float(hover_mm),
                    )
                    destination_hover = (
                        destination_contact[0], destination_contact[1],
                        destination_contact[2] + float(hover_mm),
                    )
                    for transit_z in section["transit_height_board_z_mm"]:
                        source_transit = (
                            source_contact[0], source_contact[1], float(transit_z)
                        )
                        destination_transit = (
                            destination_contact[0], destination_contact[1],
                            float(transit_z),
                        )
                        phase_points = (
                            (
                                "SOURCE_RELEASE", source_orientation,
                                source_contact, source_hover, source_id,
                            ),
                            (
                                "SOURCE_RISE", destination_orientation,
                                source_hover, source_transit, None,
                            ),
                            (
                                "TRANSIT", destination_orientation,
                                source_transit, destination_transit, None,
                            ),
                            (
                                "DESTINATION_DESCENT", destination_orientation,
                                destination_transit, destination_hover, None,
                            ),
                        )
                        minimum = float("inf")
                        limiting = None
                        for phase, orientation, start, end, admitted_target in phase_points:
                            start_transform = _translated_transform(
                                orientation, start, length
                            )
                            end_transform = _translated_transform(orientation, end, length)
                            for component in components:
                                swept, swept_aabb = _swept_collider_and_aabb(
                                    component["vertices"], start_transform,
                                    end_transform, margin_mm=component["margin_mm"]
                                )
                                for width in widths:
                                    for thickness in thicknesses:
                                        distance, key_id = _nearest_key_distance(
                                            swept,
                                            swept_aabb,
                                            boxes[(width, thickness)],
                                            requested_target_id=(
                                                admitted_target
                                                if admitted_target is not None
                                                else "__NO_ADMITTED_TARGET__"
                                            ),
                                            component=component["component"],
                                        )
                                        if distance < minimum:
                                            minimum = distance
                                            limiting = {
                                                "phase": phase,
                                                "key_id": key_id,
                                                "component": component["component"],
                                                "key_width_mm": width,
                                                "key_thickness_mm": thickness,
                                            }
                        passes = {
                            str(value): minimum + 1e-9 >= value
                            for value in thresholds
                        }
                        rows.append({
                            "tool_configuration_sha256": profile[
                                "tool_configuration_sha256"
                            ],
                            "source_target_id": source_id,
                            "destination_target_id": destination_id,
                            "hover_height_mm": float(hover_mm),
                            "transit_height_mm": float(transit_z),
                            "minimum_key_clearance_mm": minimum,
                            "limiting_case": limiting,
                            "threshold_pass": passes,
                            "decision": (
                                "PASS_EXPLORATORY_TRANSITION_KEY_CLEARANCE"
                                if all(passes.values())
                                else "STOP_TRANSITION_KEY_CLEARANCE"
                            ),
                        })
    decision = (
        "PASS_EXPLORATORY_WS3_EXACT_KEY_CLEARANCE"
        if all(
            row["decision"] == "PASS_EXPLORATORY_TRANSITION_KEY_CLEARANCE"
            for row in rows
        )
        else "STOP_WS3_EXACT_KEY_CLEARANCE"
    )
    result = {
        "schema": "tactevra.ws3_exact_key_clearance_result.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "section_sha256": section["section_sha256"],
        "pose_family_receipt_sha256": pose_family["receipt_sha256"],
        "press_recipe_receipt_sha256": recipe["receipt_sha256"],
        "row_count": len(rows),
        "minimum_key_clearance_mm": min(row["minimum_key_clearance_mm"] for row in rows),
        "pass_row_count": sum(
            row["decision"] == "PASS_EXPLORATORY_TRANSITION_KEY_CLEARANCE"
            for row in rows
        ),
        "rows": rows,
        "policy_recommendation": None,
        "decision": decision,
        "gpu_job_count": 0,
        **{name: 0 for name in COUNTER_NAMES},
        "physical_authority": False,
        "limitations": fixture["limitations"] + [
            "Key-only screening omits the source-to-destination orientation change.",
            "Full robot/workcell continuous collision screening remains required.",
        ],
    }
    result["receipt_sha256"] = _sha(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=(
        "pose-family", "stage-ef", "phone", "ws3-prepare", "ws3-screen"
    ))
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--workspace", default=Path("."), type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    fixture = load_cpu_contact_fixture(args.fixture, workspace=workspace)
    if args.mode == "pose-family":
        result = build_candidate51_pose_family(fixture, workspace=workspace)
    elif args.mode == "stage-ef":
        result = run_stage_ef_contact_screen(fixture, workspace=workspace)
    elif args.mode == "phone":
        result = run_phone_capacitive_matrix(fixture)
    elif args.mode == "ws3-prepare":
        result = prepare_ws3_transition_harness(fixture, workspace=workspace)
    else:
        result = run_ws3_transition_screen(fixture, workspace=workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "decision": result["decision"],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
