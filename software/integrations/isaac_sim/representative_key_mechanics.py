"""Deterministic, provisional keyboard-mechanics contract for Isaac LM1.

This module deliberately contains no hardware or motion interface.  It turns a
time-ordered virtual tip trace into a geometry-derived key activation result.
All numeric mechanics are synthetic, bounded priors for simulation development;
they are not measurements or product specifications.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


PROFILE_SCHEMA = "tactevra.isaac_lm1_representative_key_mechanics.v1"
RECEIPT_SCHEMA = "tactevra.isaac_lm1_key_mechanics_contract_receipt.v1"
NATIVE_RECEIPT_SCHEMA = "tactevra.isaac_lm1_native_h_key_replay.v1"
TCP_BINDING_SCHEMA = "tactevra.isaac_lm1_robot_tcp_key_binding.v1"
TCP_CARTESIAN_SCHEDULE_SCHEMA = (
    "tactevra.isaac_lm1_robot_tcp_cartesian_schedule_request.v1"
)
TCP_IK_SCREEN_SCHEMA = "tactevra.isaac_lm1_robot_tcp_cartesian_ik_screen.v1"
TCP_COLLISION_REPLAY_REQUEST_SCHEMA = (
    "tactevra.isaac_lm1_robot_tcp_collision_replay_request.v1"
)
TCP_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v1"
)
REPRESENTATIVE_KEYS = ("H", "1", "SPACE", "ENTER", "PERIOD")
PROVISIONAL_STATUS = "PROVISIONAL_SIMULATION_ONLY"
NATIVE_H_PRESS_DEPTH_MM = 2.7
DISPOSITIONS = (
    "ACCEPTED",
    "SHALLOW_PRESS",
    "OFF_CENTER_PRESS",
    "EXCESSIVE_TRAVEL",
    "DOUBLE_ACTIVATION",
    "NEIGHBORING_KEY_CONTACT",
    "INCOMPLETE_RELEASE",
)

MECHANICS_PRIOR = {
    "travel_mm": {"nominal": 3.5, "range": [3.0, 4.0]},
    "activation_mm": {"nominal": 2.0, "range": [1.6, 2.4]},
    "release_mm": {"nominal": 1.2, "range": [0.8, 1.6]},
    "stiffness_n_per_mm": {"nominal": 0.55, "range": [0.35, 0.8]},
    "damping_n_s_per_mm": {"nominal": 0.015, "range": [0.005, 0.03]},
    "keycap_mass_kg": {"nominal": 0.005, "range": [0.003, 0.009]},
    "center_margin_mm": 2.5,
    "tip_radius_mm": 1.0,
}


class MechanicsContractError(ValueError):
    """Raised when the layout or virtual trace violates the contract."""


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MechanicsContractError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise MechanicsContractError(f"{name} must be finite")
    return result


def load_keyboard_layout(path: Path) -> dict[str, Any]:
    """Load the governed nominal profile and derive board-frame key regions."""
    raw = json.loads(path.read_bytes())
    if raw.get("schema") != "rocell.nominal_target_profiles.v1":
        raise MechanicsContractError("unexpected nominal-target schema")
    if raw.get("status") != "SIMULATION_ONLY_NOMINAL_UNMEASURED":
        raise MechanicsContractError("nominal profile status changed without review")
    keyboard = raw.get("keyboard")
    if not isinstance(keyboard, dict):
        raise MechanicsContractError("keyboard profile missing")
    origin = keyboard.get("device_origin_board_xy_mm")
    default_half = keyboard.get("key_half_extent_mm")
    if not isinstance(origin, list) or len(origin) != 2:
        raise MechanicsContractError("keyboard origin must contain two values")
    if not isinstance(default_half, list) or len(default_half) != 2:
        raise MechanicsContractError("key half extent must contain two values")
    origin_xy = [_finite_number(v, "keyboard origin") for v in origin]
    default_half_xy = [_finite_number(v, "key half extent") for v in default_half]
    if min(default_half_xy) <= 0:
        raise MechanicsContractError("key half extents must be positive")

    regions: dict[str, dict[str, list[float]]] = {}
    rows = keyboard.get("rows")
    if not isinstance(rows, list):
        raise MechanicsContractError("keyboard rows missing")
    for row in rows:
        ids = row.get("key_ids")
        first = row.get("first_center_xy_mm")
        step = row.get("step_xy_mm")
        if not isinstance(ids, list) or not isinstance(first, list) or not isinstance(step, list):
            raise MechanicsContractError("malformed keyboard row")
        if len(first) != 2 or len(step) != 2:
            raise MechanicsContractError("keyboard row coordinates must be two-dimensional")
        first_xy = [_finite_number(v, "row first center") for v in first]
        step_xy = [_finite_number(v, "row step") for v in step]
        for index, key_id in enumerate(ids):
            if not isinstance(key_id, str) or key_id in regions:
                raise MechanicsContractError("key identifiers must be unique strings")
            local = [first_xy[axis] + index * step_xy[axis] for axis in range(2)]
            regions[key_id] = {
                "center_board_xy_mm": [origin_xy[axis] + local[axis] for axis in range(2)],
                "half_extent_mm": list(default_half_xy),
            }

    explicit = keyboard.get("explicit_targets")
    if not isinstance(explicit, dict):
        raise MechanicsContractError("explicit keyboard targets missing")
    for key_id, target in explicit.items():
        center = target.get("center_xy_mm")
        half = target.get("half_extent_mm")
        if not isinstance(center, list) or len(center) != 2 or not isinstance(half, list) or len(half) != 2:
            raise MechanicsContractError(f"malformed explicit target {key_id}")
        center_xy = [_finite_number(v, f"{key_id} center") for v in center]
        half_xy = [_finite_number(v, f"{key_id} half extent") for v in half]
        if min(half_xy) <= 0:
            raise MechanicsContractError(f"{key_id} half extents must be positive")
        regions[key_id] = {
            "center_board_xy_mm": [origin_xy[axis] + center_xy[axis] for axis in range(2)],
            "half_extent_mm": half_xy,
        }

    missing = sorted(set(REPRESENTATIVE_KEYS) - regions.keys())
    if missing:
        raise MechanicsContractError(f"representative keys missing: {missing}")
    return {
        "source_profile_id": keyboard.get("profile_id"),
        "source_status": raw["status"],
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "target_plane_z_board_mm": _finite_number(
            keyboard.get("target_plane_z_board_mm"), "target plane"
        ),
        "representative_regions": {key: regions[key] for key in REPRESENTATIVE_KEYS},
        "guard_regions": regions,
    }


def build_profile(layout_path: Path) -> dict[str, Any]:
    layout = load_keyboard_layout(layout_path)
    profile = {
        "schema": PROFILE_SCHEMA,
        "status": PROVISIONAL_STATUS,
        "physical_release_effect": "NONE",
        "authority": {
            "hardware": False,
            "motion": False,
            "physical_keyboard_qualification": False,
        },
        "provenance": {
            "state": "SYNTHETIC_BOUNDED_PRIOR_NOT_PRODUCT_SPECIFICATION",
            "layout_profile_id": layout["source_profile_id"],
            "layout_status": layout["source_status"],
            "layout_sha256": layout["source_sha256"],
        },
        "coordinate_frame": "board",
        "target_plane_z_board_mm": layout["target_plane_z_board_mm"],
        "representative_keys": list(REPRESENTATIVE_KEYS),
        "regions": layout["representative_regions"],
        "guard_regions": layout["guard_regions"],
        "mechanics_prior": json.loads(json.dumps(MECHANICS_PRIOR)),
        "activation_rule": (
            "An activation is a rising compression crossing of activation_mm while armed; "
            "re-arming requires compression at or below release_mm."
        ),
        "accepted_rule": (
            "Exactly one geometry-derived activation, no neighbor or unsafe-center contact, "
            "no excessive travel, and final compression at or below release_mm."
        ),
        "dispositions": list(DISPOSITIONS),
    }
    profile["profile_sha256"] = _canonical_sha256(profile)
    return profile


def _intersects_region(x: float, y: float, radius: float, region: dict[str, Any]) -> bool:
    center = region["center_board_xy_mm"]
    half = region["half_extent_mm"]
    dx = max(abs(x - center[0]) - half[0], 0.0)
    dy = max(abs(y - center[1]) - half[1], 0.0)
    return dx * dx + dy * dy <= radius * radius


def _center_is_safe(x: float, y: float, region: dict[str, Any], margin: float) -> bool:
    center = region["center_board_xy_mm"]
    half = region["half_extent_mm"]
    safe_half = [half[0] - margin, half[1] - margin]
    return min(safe_half) > 0 and all(
        abs(value - midpoint) <= extent
        for value, midpoint, extent in zip((x, y), center, safe_half)
    )


def evaluate_trace(profile: dict[str, Any], samples: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate a virtual tip trace without accepting a caller-supplied target name."""
    if profile.get("schema") != PROFILE_SCHEMA:
        raise MechanicsContractError("unexpected mechanics profile schema")
    expected_hash = profile.get("profile_sha256")
    unhashed = {key: value for key, value in profile.items() if key != "profile_sha256"}
    if expected_hash != _canonical_sha256(unhashed):
        raise MechanicsContractError("mechanics profile hash mismatch")

    trace = list(samples)
    if len(trace) < 2:
        raise MechanicsContractError("trace must contain at least two samples")
    prior = profile["mechanics_prior"]
    activation = prior["activation_mm"]["nominal"]
    release = prior["release_mm"]["nominal"]
    travel = prior["travel_mm"]["nominal"]
    stiffness = prior["stiffness_n_per_mm"]["nominal"]
    damping = prior["damping_n_s_per_mm"]["nominal"]
    radius = prior["tip_radius_mm"]
    margin = prior["center_margin_mm"]

    parsed: list[tuple[float, float, float, float]] = []
    for index, sample in enumerate(trace):
        if not isinstance(sample, dict):
            raise MechanicsContractError("trace samples must be objects")
        parsed.append(
            (
                _finite_number(sample.get("time_s"), f"sample {index} time"),
                _finite_number(sample.get("tip_x_board_mm"), f"sample {index} x"),
                _finite_number(sample.get("tip_y_board_mm"), f"sample {index} y"),
                _finite_number(sample.get("compression_mm"), f"sample {index} compression"),
            )
        )
        if parsed[-1][3] < 0:
            raise MechanicsContractError("compression cannot be negative")
        if index and parsed[-1][0] <= parsed[index - 1][0]:
            raise MechanicsContractError("trace time must increase strictly")

    resolved_key: str | None = None
    geometry_failure: str | None = None
    activation_count = 0
    armed = True
    max_compression = 0.0
    max_force = 0.0
    previous_time, _, _, previous_compression = parsed[0]
    for time_s, x, y, compression in parsed:
        max_compression = max(max_compression, compression)
        dt = time_s - previous_time
        velocity = 0.0 if dt <= 0 else (compression - previous_compression) / dt
        force = stiffness * compression + damping * max(velocity, 0.0)
        max_force = max(max_force, force)

        if compression > 0:
            contacts = sorted(
                key
                for key, region in profile["guard_regions"].items()
                if _intersects_region(x, y, radius, region)
            )
            if len(contacts) > 1:
                geometry_failure = geometry_failure or "NEIGHBORING_KEY_CONTACT"
            elif not contacts or contacts[0] not in profile["regions"]:
                geometry_failure = geometry_failure or "OFF_CENTER_PRESS"
            else:
                candidate = contacts[0]
                if resolved_key is not None and candidate != resolved_key:
                    geometry_failure = geometry_failure or "NEIGHBORING_KEY_CONTACT"
                resolved_key = resolved_key or candidate
                if not _center_is_safe(x, y, profile["regions"][candidate], margin):
                    geometry_failure = geometry_failure or "OFF_CENTER_PRESS"

        if compression <= release:
            armed = True
        if armed and previous_compression < activation <= compression:
            activation_count += 1
            armed = False
        previous_time, previous_compression = time_s, compression

    if geometry_failure:
        disposition = geometry_failure
    elif max_compression > travel:
        disposition = "EXCESSIVE_TRAVEL"
    elif activation_count == 0:
        disposition = "SHALLOW_PRESS"
    elif activation_count > 1:
        disposition = "DOUBLE_ACTIVATION"
    elif parsed[-1][3] > release:
        disposition = "INCOMPLETE_RELEASE"
    else:
        disposition = "ACCEPTED"

    result = {
        "disposition": disposition,
        "accepted": disposition == "ACCEPTED",
        "resolved_key": resolved_key,
        "activation_count": activation_count,
        "max_compression_mm": max_compression,
        "final_compression_mm": parsed[-1][3],
        "max_estimated_force_n": max_force,
        "sample_count": len(parsed),
        "profile_sha256": profile["profile_sha256"],
        "authority": dict(profile["authority"]),
    }
    result["result_sha256"] = _canonical_sha256(result)
    return result


def _trace(center: list[float], compressions: list[float], *, x_offset: float = 0.0) -> list[dict[str, float]]:
    return [
        {
            "time_s": index * 0.02,
            "tip_x_board_mm": center[0] + x_offset,
            "tip_y_board_mm": center[1],
            "compression_mm": compression,
        }
        for index, compression in enumerate(compressions)
    ]


def run_contract_campaign(layout_path: Path) -> dict[str, Any]:
    """Run deterministic positive and negative contract cases."""
    profile = build_profile(layout_path)
    regions = profile["regions"]
    cases: list[dict[str, Any]] = []

    def run(name: str, trace: list[dict[str, float]], expected: str, expected_key: str | None) -> None:
        result = evaluate_trace(profile, trace)
        cases.append(
            {
                "name": name,
                "expected_disposition": expected,
                "expected_resolved_key": expected_key,
                "passed": result["disposition"] == expected and result["resolved_key"] == expected_key,
                "result": result,
            }
        )

    nominal = [0.0, 1.0, 2.2, 3.0, 1.2, 0.0]
    for key in REPRESENTATIVE_KEYS:
        run(f"nominal_{key.lower()}", _trace(regions[key]["center_board_xy_mm"], nominal), "ACCEPTED", key)

    h_center = regions["H"]["center_board_xy_mm"]
    run("shallow_h", _trace(h_center, [0.0, 1.0, 1.9, 0.0]), "SHALLOW_PRESS", "H")
    run("off_center_h", _trace(h_center, nominal, x_offset=5.5), "OFF_CENTER_PRESS", "H")
    run("excessive_h", _trace(h_center, [0.0, 2.2, 3.6, 0.0]), "EXCESSIVE_TRAVEL", "H")
    run("double_h", _trace(h_center, [0.0, 2.2, 0.5, 2.3, 0.0]), "DOUBLE_ACTIVATION", "H")
    run("incomplete_release_h", _trace(h_center, [0.0, 2.2, 1.5]), "INCOMPLETE_RELEASE", "H")

    j_center = profile["guard_regions"]["J"]["center_board_xy_mm"]
    midpoint = [(h_center[axis] + j_center[axis]) / 2.0 for axis in range(2)]
    neighbor_trace = _trace(midpoint, nominal)
    neighbor_profile = json.loads(json.dumps(profile))
    neighbor_profile["mechanics_prior"]["tip_radius_mm"] = 3.0
    neighbor_profile.pop("profile_sha256")
    neighbor_profile["profile_sha256"] = _canonical_sha256(neighbor_profile)
    neighbor_result = evaluate_trace(neighbor_profile, neighbor_trace)
    cases.append(
        {
            "name": "neighbor_h_j",
            "expected_disposition": "NEIGHBORING_KEY_CONTACT",
            "expected_resolved_key": None,
            "passed": neighbor_result["disposition"] == "NEIGHBORING_KEY_CONTACT",
            "result": neighbor_result,
        }
    )

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "PASS" if all(case["passed"] for case in cases) else "FAIL",
        "profile_sha256": profile["profile_sha256"],
        "case_count": len(cases),
        "passed_case_count": sum(case["passed"] for case in cases),
        "cases": cases,
        "limitations": [
            "Mechanics values are synthetic bounded priors, not measurements.",
            "The evaluator is deterministic contract logic, not native Isaac contact replay.",
            "No result grants hardware, motion, or physical keyboard authority.",
        ],
        "authority": dict(profile["authority"]),
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


def build_native_tip_trajectory(
    *, rest_top_z_m: float, tip_radius_m: float, dt: float
) -> list[dict[str, float]]:
    """Build a smooth settle/press/hold/retract trajectory for native replay."""
    if rest_top_z_m <= 0 or tip_radius_m <= 0 or dt <= 0:
        raise MechanicsContractError("native trajectory dimensions and time step must be positive")
    hover_z = rest_top_z_m + tip_radius_m + 0.002
    pressed_z = rest_top_z_m + tip_radius_m - NATIVE_H_PRESS_DEPTH_MM / 1000.0
    segments = ((60, hover_z, hover_z), (180, hover_z, pressed_z),
                (60, pressed_z, pressed_z), (180, pressed_z, hover_z),
                (120, hover_z, hover_z))
    result: list[dict[str, float]] = []
    step = 0
    for count, start, end in segments:
        for index in range(count):
            fraction = 1.0 if count == 1 else index / (count - 1)
            smooth = fraction * fraction * (3.0 - 2.0 * fraction)
            result.append({"step": step, "time_s": step * dt, "tip_z_m": start + (end - start) * smooth})
            step += 1
    return result


def bind_robot_tcp_contact_requirement(
    profile: dict[str, Any],
    bundle: dict[str, Any],
    *,
    key_id: str = "H",
    press_depth_mm: float = NATIVE_H_PRESS_DEPTH_MM,
) -> dict[str, Any]:
    """Bind a replay schedule endpoint to the proven key-mechanics stroke.

    This is deliberately a zero-authority planning contract.  It does not
    invent joint angles: an insufficient endpoint produces the corrected
    board-frame TCP target that the governed IK/schedule pipeline must solve
    and replay before native robot/key contact can be claimed.
    """
    if profile.get("schema") != PROFILE_SCHEMA:
        raise MechanicsContractError("unexpected mechanics profile schema")
    expected_profile_hash = profile.get("profile_sha256")
    unsigned_profile = {
        name: value for name, value in profile.items() if name != "profile_sha256"
    }
    if expected_profile_hash != _canonical_sha256(unsigned_profile):
        raise MechanicsContractError("mechanics profile hash mismatch")
    if key_id not in profile.get("regions", {}):
        raise MechanicsContractError("robot TCP binding requires a representative key")

    depth = _finite_number(press_depth_mm, "press depth")
    activation = _finite_number(
        profile["mechanics_prior"]["activation_mm"]["nominal"], "activation depth"
    )
    travel = _finite_number(
        profile["mechanics_prior"]["travel_mm"]["nominal"], "key travel"
    )
    if not activation <= depth <= travel:
        raise MechanicsContractError("press depth must be inside activation and travel bounds")

    if bundle.get("schema") not in {
        "tactevra.arm_joint_schedule_replay_bundle.v1",
        "tactevra.arm_joint_schedule_replay_bundle.v2",
    }:
        raise MechanicsContractError("unsupported replay bundle schema")
    claimed_bundle_hash = bundle.get("bundle_sha256")
    unsigned_bundle = dict(bundle)
    unsigned_bundle.pop("bundle_sha256", None)
    if claimed_bundle_hash != _canonical_sha256(unsigned_bundle):
        raise MechanicsContractError("replay bundle hash mismatch")
    if (
        bundle.get("hardware_access") is not False
        or bundle.get("physical_authority") is not False
        or bundle.get("controller_commands") != []
        or bundle.get("hardware_writes") != 0
        or bundle.get("physical_movements") != 0
    ):
        raise MechanicsContractError("replay bundle crossed the zero-authority boundary")

    endpoints = [
        item
        for item in bundle.get("samples", [])
        if item.get("target_id") == key_id
        and item.get("phase") == "CONTACT"
        and item.get("phase_endpoint") is True
    ]
    if not endpoints:
        raise MechanicsContractError("replay bundle lacks the requested contact endpoint")
    targets = [item.get("expected_tool_tip_board_mm") for item in endpoints]
    if any(not isinstance(target, list) or len(target) != 3 for target in targets):
        raise MechanicsContractError("contact endpoint lacks a board-frame TCP target")
    parsed_targets = [
        [_finite_number(value, "contact endpoint coordinate") for value in target]
        for target in targets
    ]
    if any(
        not math.isclose(value, parsed_targets[0][axis], abs_tol=1e-9)
        for target in parsed_targets[1:]
        for axis, value in enumerate(target)
    ):
        raise MechanicsContractError("repeated key contact endpoints disagree")

    center = profile["regions"][key_id]["center_board_xy_mm"]
    source_target = parsed_targets[0]
    if not all(
        math.isclose(source_target[axis], center[axis], abs_tol=1e-6)
        for axis in range(2)
    ):
        raise MechanicsContractError("contact endpoint is not centered on the selected key")
    target_plane = _finite_number(profile["target_plane_z_board_mm"], "target plane")
    scheduled_compression = max(0.0, target_plane - source_target[2])
    corrected_target = [center[0], center[1], target_plane - depth]
    sufficient = activation <= scheduled_compression <= travel
    result: dict[str, Any] = {
        "schema": TCP_BINDING_SCHEMA,
        "status": (
            "READY_FOR_DRIVE_CONTROLLED_NATIVE_REPLAY"
            if sufficient
            else "BLOCKED_CONTACT_ENDPOINT_REQUIRES_OVERTRAVEL"
        ),
        "key_id": key_id,
        "source_bundle_sha256": claimed_bundle_hash,
        "profile_sha256": expected_profile_hash,
        "source_contact_endpoint_count": len(endpoints),
        "source_contact_target_board_mm": source_target,
        "source_scheduled_compression_mm": scheduled_compression,
        "activation_depth_mm": activation,
        "travel_limit_mm": travel,
        "required_press_depth_mm": depth,
        "required_contact_target_board_mm": corrected_target,
        "joint_schedule_regeneration_required": not sufficient,
        "ik_qualification_required": True,
        "native_replay_required": True,
        "authority": dict(profile["authority"]),
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "corrected_target_is_cartesian_input_not_an_ik_solution",
            "mechanics_are_synthetic_bounded_priors_not_physical_measurements",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    result["binding_sha256"] = _canonical_sha256(result)
    return result


def build_robot_tcp_cartesian_schedule_request(
    profile: dict[str, Any],
    bundle: dict[str, Any],
    *,
    key_id: str = "H",
    press_depth_mm: float = NATIVE_H_PRESS_DEPTH_MM,
) -> dict[str, Any]:
    """Regenerate Cartesian key-contact inputs without reusing stale IK.

    The retained replay bundle is useful for ordered semantics and timing, but
    its joint positions solve the old surface-only contact endpoint. This
    contract therefore copies only Cartesian samples, replaces each selected
    CONTACT endpoint with the mechanics-compatible target, and makes fresh IK
    and collision qualification mandatory.
    """
    binding = bind_robot_tcp_contact_requirement(
        profile, bundle, key_id=key_id, press_depth_mm=press_depth_mm
    )
    source_samples = bundle.get("samples")
    if not isinstance(source_samples, list) or not source_samples:
        raise MechanicsContractError("replay bundle samples are missing")

    regenerated_samples: list[dict[str, Any]] = []
    modified_sequences: list[int] = []
    for sequence, source in enumerate(source_samples):
        if not isinstance(source, dict) or source.get("sequence") != sequence:
            raise MechanicsContractError("replay bundle sample sequence is not contiguous")
        point = source.get("expected_tool_tip_board_mm")
        if not isinstance(point, list) or len(point) != 3:
            raise MechanicsContractError("replay bundle sample lacks a Cartesian target")
        target = [
            _finite_number(value, f"sample {sequence} Cartesian coordinate")
            for value in point
        ]
        if (
            source.get("target_id") == key_id
            and source.get("phase") == "CONTACT"
            and source.get("phase_endpoint") is True
        ):
            target = list(binding["required_contact_target_board_mm"])
            if target != point:
                modified_sequences.append(sequence)
        regenerated_samples.append({
            "sequence": sequence,
            "time_from_start_ns": source.get("time_from_start_ns"),
            "phase": source.get("phase"),
            "phase_endpoint": source.get("phase_endpoint"),
            "action_index": source.get("action_index"),
            "target_id": source.get("target_id"),
            "expected_tool_tip_board_mm": target,
        })

    if len(modified_sequences) != binding["source_contact_endpoint_count"]:
        raise MechanicsContractError(
            "Cartesian regeneration did not replace every selected contact endpoint"
        )
    contact_order = [
        sample["target_id"]
        for sample in regenerated_samples
        if sample["phase"] == "CONTACT" and sample["phase_endpoint"] is True
    ]
    if contact_order != bundle.get("ordered_target_ids"):
        raise MechanicsContractError("Cartesian regeneration changed target order or repetitions")

    result: dict[str, Any] = {
        "schema": TCP_CARTESIAN_SCHEDULE_SCHEMA,
        "status": "READY_FOR_IK_QUALIFICATION",
        "source_bundle_sha256": bundle["bundle_sha256"],
        "source_binding_sha256": binding["binding_sha256"],
        "profile_sha256": profile["profile_sha256"],
        "key_id": key_id,
        "sample_count": len(regenerated_samples),
        "total_time_ns": bundle.get("total_time_ns"),
        "ordered_target_ids": list(bundle.get("ordered_target_ids", [])),
        "modified_contact_sequences": modified_sequences,
        "required_contact_target_board_mm": list(
            binding["required_contact_target_board_mm"]
        ),
        "samples": regenerated_samples,
        "joint_positions_included": False,
        "source_joint_positions_reused": False,
        "ik_qualification_required": True,
        "collision_qualification_required": True,
        "native_replay_required": True,
        "authority": dict(profile["authority"]),
        "hardware_access": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "cartesian_schedule_is_not_an_ik_solution",
            "source_joint_positions_are_intentionally_excluded",
            "collision_and_native_contact_are_not_yet_qualified",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    result["request_sha256"] = _canonical_sha256(result)
    return result


def screen_robot_tcp_cartesian_schedule_ik(
    request: dict[str, Any],
    source_bundle: dict[str, Any],
    profile: dict[str, Any],
    *,
    workspace: Path,
) -> dict[str, Any]:
    """Solve a regenerated Cartesian request with the canonical IK gates."""
    if request.get("schema") != TCP_CARTESIAN_SCHEDULE_SCHEMA:
        raise MechanicsContractError("unexpected Cartesian schedule request schema")
    claimed_request_hash = request.get("request_sha256")
    unsigned_request = dict(request)
    unsigned_request.pop("request_sha256", None)
    if claimed_request_hash != _canonical_sha256(unsigned_request):
        raise MechanicsContractError("Cartesian schedule request hash mismatch")
    claimed_bundle_hash = source_bundle.get("bundle_sha256")
    unsigned_bundle = dict(source_bundle)
    unsigned_bundle.pop("bundle_sha256", None)
    if claimed_bundle_hash != _canonical_sha256(unsigned_bundle):
        raise MechanicsContractError("IK source bundle hash mismatch")
    if request.get("source_bundle_sha256") != claimed_bundle_hash:
        raise MechanicsContractError("Cartesian request and IK source bundle differ")
    expected_request = build_robot_tcp_cartesian_schedule_request(
        profile, source_bundle
    )
    if expected_request.get("request_sha256") != claimed_request_hash:
        raise MechanicsContractError(
            "Cartesian request differs from the governed mechanics regeneration"
        )
    for document, label in ((request, "request"), (source_bundle, "source bundle")):
        if (
            document.get("hardware_access") is not False
            or document.get("controller_commands") != []
            or document.get("hardware_writes") != 0
            or document.get("physical_movements") != 0
        ):
            raise MechanicsContractError(f"{label} crossed the zero-authority boundary")

    samples = request.get("samples")
    source_samples = source_bundle.get("samples")
    if (
        not isinstance(samples, list)
        or not isinstance(source_samples, list)
        or not samples
        or len(samples) != len(source_samples)
        or len(samples) > 256
    ):
        raise MechanicsContractError("IK sample count is absent, crossed, or out of bounds")
    modified = request.get("modified_contact_sequences")
    if not isinstance(modified, list) or not modified:
        raise MechanicsContractError("IK request lacks modified contact sequences")
    modified_set = set(modified)
    if len(modified_set) != len(modified):
        raise MechanicsContractError("modified contact sequences are not unique")
    for sequence, (sample, source) in enumerate(zip(samples, source_samples)):
        if sample.get("sequence") != sequence or source.get("sequence") != sequence:
            raise MechanicsContractError("IK sample sequence is not contiguous")
        for field in (
            "time_from_start_ns", "phase", "phase_endpoint", "action_index", "target_id"
        ):
            if sample.get(field) != source.get(field):
                raise MechanicsContractError("Cartesian request changed source semantics")
        if sequence not in modified_set and (
            sample.get("expected_tool_tip_board_mm")
            != source.get("expected_tool_tip_board_mm")
        ):
            raise MechanicsContractError("Cartesian request changed an unselected endpoint")
        if sequence in modified_set and (
            sample.get("expected_tool_tip_board_mm")
            != request.get("required_contact_target_board_mm")
        ):
            raise MechanicsContractError("modified contact target differs from the request")

    try:
        from rocell.application._pinned_model import load_pinned_urdf
        from rocell.application.context import load_simulation_context
        from rocell.application.trajectory_simulation import (
            CartesianRouteWaypoint,
            TrajectorySimulationPolicy,
            evaluate_joint_trajectory_solution,
        )
        from rocell.application.typing_trajectory_ik_screen_v1 import (
            canonicalize_typing_ik_evidence_v1,
        )
        from rocell.geometry import JointPosition, Point3Mm
        from rocell.kinematics import (
            ARM_JOINT_NAMES,
            BoardToolTipTarget,
            IkOptions,
            RoArmM3NumericalIk,
        )
        from rocell.motion import MotionPhase
        from rocell.simulation.virtual_profile import load_virtual_commissioning_profile
    except ImportError as exc:
        raise MechanicsContractError(
            "canonical IK runtime is unavailable; include software/src on PYTHONPATH"
        ) from exc

    root = workspace.resolve(strict=True)
    context = load_simulation_context(
        root, root / "software/config/system_manifest.json"
    )
    virtual_profile = load_virtual_commissioning_profile(context)
    expected_virtual_hash = source_bundle.get("source", {}).get(
        "virtual_profile_sha256"
    )
    if virtual_profile.source_sha256 != expected_virtual_hash:
        raise MechanicsContractError("virtual commissioning profile lineage changed")
    tool_length_mm = float(
        virtual_profile.study_input.keyboard_tool_length_mm
    )
    scenario = context.scenario
    model = load_pinned_urdf(scenario.model_path, scenario.model_sha256).model
    initial_seed = source_samples[0].get("joint_positions_rad")
    if not isinstance(initial_seed, dict) or tuple(initial_seed) != ARM_JOINT_NAMES:
        raise MechanicsContractError("source bundle lacks the canonical initial joint seed")
    previous = {
        name: _finite_number(initial_seed[name], f"initial seed {name}")
        for name in ARM_JOINT_NAMES
    }
    bounds = scenario.controller_joint_intersection_rad
    solver = RoArmM3NumericalIk(
        model=model,
        board_T_world=virtual_profile.study_input.board_T_vendor_world,
        hand_tcp_to_tip_z_mm=-tool_length_mm,
        fixed_gripper_position=scenario.fixed_gripper_position,
        ready_arm_joint_positions={
            name: JointPosition.radians(value) for name, value in previous.items()
        },
        gripper_bounds_rad=scenario.controller_gripper_intersection_rad,
        options=IkOptions(
            max_attempts=scenario.ik_policy.max_attempts,
            max_iterations_per_attempt=scenario.ik_policy.max_iterations_per_attempt,
        ),
        joint_bounds_rad=bounds,
    )
    policy = TrajectorySimulationPolicy(
        maximum_cartesian_step_mm=30.0,
        maximum_joint_step_rad=0.35,
        minimum_normalized_arm_joint_margin=0.01,
        maximum_refinement_rounds=0,
        maximum_waypoints_per_round=256,
        maximum_total_ik_solves=256,
        maximum_route_targets=len(request["ordered_target_ids"]),
    )
    results: list[dict[str, Any]] = []
    previous_point = None
    for sample in samples:
        point = Point3Mm("board", *sample["expected_tool_tip_board_mm"])
        distance = (
            0.0
            if previous_point is None
            else math.dist(
                (previous_point.x, previous_point.y, previous_point.z),
                (point.x, point.y, point.z),
            )
        )
        waypoint = CartesianRouteWaypoint(
            sequence=sample["sequence"],
            phase=MotionPhase(sample["phase"]),
            action_index=sample["action_index"],
            semantic_target=sample["target_id"],
            point_board=point,
            distance_from_previous_mm=distance,
            source_geometric_sequence=sample["sequence"],
            source_check_id=claimed_request_hash,
            source_path_check_passed=True,
            inherited_collision_ids=(),
            phase_endpoint=sample["phase_endpoint"],
        )
        solved = solver.solve(
            BoardToolTipTarget(point),
            seed_joint_positions=({
                name: JointPosition.radians(value)
                for name, value in previous.items()
            },),
        )
        evaluated = evaluate_joint_trajectory_solution(
            waypoint, solved, solver, bounds, previous, policy
        )
        canonical = canonicalize_typing_ik_evidence_v1(evaluated.to_dict())
        results.append(canonical)
        if not evaluated.accepted:
            break
        previous = dict(evaluated.solution_arm_joint_positions_rad)
        previous_point = point

    all_accepted = len(results) == len(samples) and all(
        item["accepted"] for item in results
    )
    accepted = [item for item in results if item["accepted"]]
    result: dict[str, Any] = {
        "schema": TCP_IK_SCREEN_SCHEMA,
        "status": (
            "READY_FOR_COLLISION_QUALIFICATION"
            if all_accepted
            else "BLOCKED_CANONICAL_IK_OR_CONTINUITY"
        ),
        "source_request_sha256": claimed_request_hash,
        "source_bundle_sha256": claimed_bundle_hash,
        "virtual_profile_sha256": virtual_profile.source_sha256,
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "kinematic_model_sha256": scenario.model_sha256,
        "tool_length_mm": tool_length_mm,
        "initial_seed_source": "SOURCE_BUNDLE_SAMPLE_0_ONLY",
        "initial_seed_joint_positions_rad": {
            name: float(initial_seed[name]) for name in ARM_JOINT_NAMES
        },
        "policy": policy.to_dict(),
        "sample_count": len(samples),
        "evaluated_sample_count": len(results),
        "ik_all_samples_accepted": all_accepted,
        "joint_results": results,
        "modified_contact_results": [
            results[index] for index in modified if index < len(results)
        ],
        "metrics": {
            "maximum_position_error_mm": max(
                (item["position_error_mm"] for item in accepted), default=None
            ),
            "minimum_normalized_arm_joint_margin": min(
                (
                    item["minimum_normalized_arm_joint_margin"]
                    for item in accepted
                ),
                default=None,
            ),
            "maximum_adjacent_joint_delta_rad": max(
                (item["maximum_joint_delta_rad"] for item in accepted), default=None
            ),
        },
        "collision_screening_executed": False,
        "continuous_collision_proven": False,
        "next_required_stage": (
            "SCREEN_EXACT_JOINT_RESULTS_AGAINST_COLLISION_GEOMETRY"
            if all_accepted
            else "CORRECT_IK_COMPATIBILITY_OR_ROUTE_CONTINUITY"
        ),
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "virtual_profile_is_an_unmeasured_simulation_only_overlay",
            "collision_and_native_contact_are_not_yet_qualified",
            "initial_seed_is_retained_source_evidence_not_controller_feedback",
            "no_hardware_motion_or_physical_keyboard_authority",
        ],
    }
    result["receipt_sha256"] = _canonical_sha256(result)
    return result


def build_robot_tcp_collision_replay_request(
    ik_receipt: dict[str, Any],
    collision_candidate: dict[str, Any],
    toolchain_lock: dict[str, Any],
) -> dict[str, Any]:
    """Bind accepted IK results to bounded zero-authority collision samples.

    The retained candidate geometry is deliberately simulation-only and
    uninstalled.  This request can drive an Isaac diagnostic, but cannot clear
    installed-geometry or physical-motion gates.
    """
    if ik_receipt.get("schema") != TCP_IK_SCREEN_SCHEMA:
        raise MechanicsContractError("unexpected IK receipt schema")
    claimed_ik_hash = ik_receipt.get("receipt_sha256")
    unsigned_ik = dict(ik_receipt)
    unsigned_ik.pop("receipt_sha256", None)
    if claimed_ik_hash != _canonical_sha256(unsigned_ik):
        raise MechanicsContractError("IK receipt hash mismatch")
    if (
        ik_receipt.get("status") != "READY_FOR_COLLISION_QUALIFICATION"
        or ik_receipt.get("ik_all_samples_accepted") is not True
        or ik_receipt.get("evaluated_sample_count") != ik_receipt.get("sample_count")
    ):
        raise MechanicsContractError("collision replay requires an all-accepted IK receipt")
    for document, label in ((ik_receipt, "IK receipt"), (collision_candidate, "collision candidate")):
        if (
            document.get("physical_authority") is not False
            or document.get("hardware_access", False) is not False
            or document.get("hardware_write_count", document.get("hardware_writes")) != 0
            or document.get("physical_movement_count", document.get("physical_movements")) != 0
            or document.get("commands", document.get("controller_commands")) != []
        ):
            raise MechanicsContractError(f"{label} crossed the zero-authority boundary")

    claimed_candidate_hash = collision_candidate.get("candidate_sha256")
    unsigned_candidate = dict(collision_candidate)
    unsigned_candidate.pop("candidate_sha256", None)
    if claimed_candidate_hash != _canonical_sha256(unsigned_candidate):
        raise MechanicsContractError("collision candidate hash mismatch")
    if (
        collision_candidate.get("schema")
        != "tactevra.simulation_collision_candidate.v1"
        or collision_candidate.get("scope")
        != "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
        or collision_candidate.get("installed") is not False
        or collision_candidate.get("installed_profile_eligible") is not False
    ):
        raise MechanicsContractError("collision candidate boundary changed")

    if (
        toolchain_lock.get("schema") != "rocell.isaac_sim_toolchain_lock.v1"
        or toolchain_lock.get("selection_status") != "SELECTED"
        or toolchain_lock.get("hardware_access") is not False
        or toolchain_lock.get("physical_authority") is not False
        or toolchain_lock.get("wire_commands") != []
    ):
        raise MechanicsContractError("Isaac toolchain lock is not selected zero-authority")

    try:
        from rocell.application.bounded_segment_collision_qualification import (
            BoundedSegmentSamplingPolicy,
            build_bounded_joint_sample_plan_from_results,
        )
        from rocell.kinematics import ARM_JOINT_NAMES
    except ImportError as exc:
        raise MechanicsContractError(
            "bounded collision runtime is unavailable; include software/src on PYTHONPATH"
        ) from exc

    joint_results = ik_receipt.get("joint_results")
    if not isinstance(joint_results, list):
        raise MechanicsContractError("IK receipt joint results are absent")
    policy = BoundedSegmentSamplingPolicy(
        maximum_joint_step_rad=0.05,
        maximum_samples=256,
    )
    plan = build_bounded_joint_sample_plan_from_results(
        ik_receipt.get("initial_seed_joint_positions_rad"),
        joint_results,
        policy,
    )
    candidate_blockers = collision_candidate.get("blockers")
    if (
        not isinstance(candidate_blockers, list)
        or not candidate_blockers
        or not all(isinstance(item, str) and item for item in candidate_blockers)
    ):
        raise MechanicsContractError("collision candidate blockers are absent")
    bodies = collision_candidate.get("robot_bodies")
    workcell = collision_candidate.get("workcell_bodies")
    if not isinstance(bodies, list) or not bodies or not isinstance(workcell, list) or not workcell:
        raise MechanicsContractError("collision candidate body coverage is absent")

    request: dict[str, Any] = {
        "schema": TCP_COLLISION_REPLAY_REQUEST_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC",
        "source_ik_receipt_sha256": claimed_ik_hash,
        "source_request_sha256": ik_receipt["source_request_sha256"],
        "source_bundle_sha256": ik_receipt["source_bundle_sha256"],
        "collision_candidate_sha256": claimed_candidate_hash,
        "collision_candidate_status": collision_candidate["status"],
        "collision_candidate_installed": False,
        "collision_candidate_blockers": list(candidate_blockers),
        "toolchain_lock_sha256": _canonical_sha256(toolchain_lock),
        "toolchain": {
            name: toolchain_lock[name]
            for name in (
                "isaac_sim_version", "installation_sha256",
                "extension_lock_sha256", "settings_profile_sha256",
                "runner_platform", "launch_method",
            )
        },
        "joint_order": list(ARM_JOINT_NAMES),
        "source_joint_result_count": len(joint_results),
        "bounded_sample_count": len(plan),
        "bounded_sampling_policy": policy.to_dict(),
        "bounded_samples": [item.to_dict() for item in plan],
        "collision_scopes": [
            "ROBOT_SELF_COLLISION",
            "ROBOT_TO_WORKCELL",
            "ROBOT_TOOL_CAMERA_SUPPORT_DIAGNOSTIC_WHERE_BOUND",
        ],
        "diagnostic_only": True,
        "installed_collision_qualified": False,
        "continuous_collision_proven": False,
        "native_contact_replay_authorized": False,
        "next_required_stage": "RUN_SELECTED_ISAAC_COLLISION_DIAGNOSTIC_AND_RETAIN_PAIR_EVIDENCE",
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "exploratory_collision_candidate_is_uninstalled",
            "bounded_sampling_is_not_continuous_swept_volume_proof",
            "missing_candidate_bodies_remain_explicit_blockers",
            "diagnostic_result_cannot_promote_installed_or_physical_gates",
        ],
    }
    request["request_sha256"] = _canonical_sha256(request)
    return request


def admit_robot_tcp_collision_diagnostic(
    request: dict[str, Any],
    ik_receipt: dict[str, Any],
    collision_candidate: dict[str, Any],
    virtual_profile_bytes: bytes,
    robot_usd_bytes: bytes,
    import_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Validate all native collision inputs before Isaac or a GPU can start."""
    claimed_request_hash = request.get("request_sha256")
    unsigned_request = dict(request)
    unsigned_request.pop("request_sha256", None)
    if claimed_request_hash != _canonical_sha256(unsigned_request):
        raise MechanicsContractError("collision diagnostic request hash mismatch")
    if (
        request.get("schema") != TCP_COLLISION_REPLAY_REQUEST_SCHEMA
        or request.get("status") != "READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC"
        or request.get("diagnostic_only") is not True
        or request.get("installed_collision_qualified") is not False
        or request.get("continuous_collision_proven") is not False
        or request.get("native_contact_replay_authorized") is not False
    ):
        raise MechanicsContractError("collision diagnostic request boundary changed")
    for document, label in (
        (request, "collision request"),
        (ik_receipt, "IK receipt"),
        (import_receipt, "robot import receipt"),
    ):
        if (
            document.get("hardware_access") is not False
            or document.get("physical_authority") is not False
            or document.get("hardware_writes") != 0
            or document.get("physical_movements") != 0
        ):
            raise MechanicsContractError(f"{label} crossed the zero-authority boundary")
    if (
        collision_candidate.get("physical_authority") is not False
        or collision_candidate.get("hardware_write_count") != 0
        or collision_candidate.get("physical_movement_count") != 0
        or collision_candidate.get("commands") != []
    ):
        raise MechanicsContractError("collision candidate crossed the zero-authority boundary")

    claimed_ik_hash = ik_receipt.get("receipt_sha256")
    unsigned_ik = dict(ik_receipt)
    unsigned_ik.pop("receipt_sha256", None)
    if claimed_ik_hash != _canonical_sha256(unsigned_ik):
        raise MechanicsContractError("collision diagnostic IK receipt hash mismatch")
    if (
        request.get("source_ik_receipt_sha256") != claimed_ik_hash
        or request.get("source_request_sha256") != ik_receipt.get("source_request_sha256")
        or request.get("source_bundle_sha256") != ik_receipt.get("source_bundle_sha256")
    ):
        raise MechanicsContractError("collision request and IK lineage differ")

    claimed_candidate_hash = collision_candidate.get("candidate_sha256")
    unsigned_candidate = dict(collision_candidate)
    unsigned_candidate.pop("candidate_sha256", None)
    if claimed_candidate_hash != _canonical_sha256(unsigned_candidate):
        raise MechanicsContractError("collision diagnostic candidate hash mismatch")
    if (
        request.get("collision_candidate_sha256") != claimed_candidate_hash
        or collision_candidate.get("schema") != "tactevra.simulation_collision_candidate.v1"
        or collision_candidate.get("installed") is not False
        or collision_candidate.get("installed_profile_eligible") is not False
        or request.get("collision_candidate_blockers") != collision_candidate.get("blockers")
    ):
        raise MechanicsContractError("collision request and candidate boundary differ")

    samples = request.get("bounded_samples")
    joint_order = request.get("joint_order")
    if (
        not isinstance(samples, list)
        or not samples
        or len(samples) != request.get("bounded_sample_count")
        or len(samples) > 256
        or not isinstance(joint_order, list)
        or len(joint_order) != 5
        or [sample.get("sample_sequence") for sample in samples]
        != list(range(len(samples)))
    ):
        raise MechanicsContractError("bounded collision samples are invalid")
    for sample in samples:
        positions = sample.get("joint_positions_rad")
        if not isinstance(positions, dict) or list(positions) != joint_order:
            raise MechanicsContractError("bounded collision joint order changed")
        for name in joint_order:
            _finite_number(positions.get(name), f"bounded sample joint {name}")

    if hashlib.sha256(virtual_profile_bytes).hexdigest() != ik_receipt.get(
        "virtual_profile_sha256"
    ):
        raise MechanicsContractError("virtual profile differs from the accepted IK receipt")
    profile = json.loads(virtual_profile_bytes)
    placement = profile.get("study_input", {}).get("physical_placement_input")
    matrix = placement.get("matrix_row_major") if isinstance(placement, dict) else None
    if not isinstance(matrix, list) or len(matrix) != 16:
        raise MechanicsContractError("virtual profile lacks the governed robot placement")
    for value in matrix:
        _finite_number(value, "robot placement matrix value")

    claimed_import_hash = import_receipt.get("receipt_sha256")
    unsigned_import = dict(import_receipt)
    unsigned_import.pop("receipt_sha256", None)
    if claimed_import_hash != _canonical_sha256(unsigned_import):
        raise MechanicsContractError("robot import receipt hash mismatch")
    external_files = import_receipt.get("external_files")
    robot_usd_hash = hashlib.sha256(robot_usd_bytes).hexdigest()
    if (
        import_receipt.get("schema") != "tactevra.isaac_sim_urdf_import.v1"
        or not isinstance(external_files, list)
        or len(external_files) != 1
        or external_files[0].get("sha256") != robot_usd_hash
        or external_files[0].get("size_bytes") != len(robot_usd_bytes)
    ):
        raise MechanicsContractError("robot USD differs from its governed import receipt")
    normalization = import_receipt.get("articulation_root_normalization")
    expected_dofs = joint_order + ["link5_to_gripper_link"]
    if not isinstance(normalization, dict) or normalization.get(
        "expected_live_dof_order"
    ) != expected_dofs:
        raise MechanicsContractError("robot import articulation order changed")

    robot_bodies = collision_candidate.get("robot_bodies")
    workcell_bodies = collision_candidate.get("workcell_bodies")
    if not isinstance(robot_bodies, list) or not robot_bodies \
            or not isinstance(workcell_bodies, list) or not workcell_bodies:
        raise MechanicsContractError("collision candidate body coverage is absent")
    for body in robot_bodies + workcell_bodies:
        primitives = body.get("primitives") if isinstance(body, dict) else None
        if not isinstance(primitives, list) or not primitives:
            raise MechanicsContractError("collision candidate body lacks primitives")
        for primitive in primitives:
            if (
                primitive.get("kind") != "oriented_box"
                or primitive.get("rotation_row_major")
                != [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
                or len(primitive.get("center_mm", [])) != 3
                or len(primitive.get("half_extents_mm", [])) != 3
            ):
                raise MechanicsContractError(
                    "native diagnostic currently requires axis-aligned candidate boxes"
                )
            for value in primitive["center_mm"]:
                _finite_number(value, "collision box center")
            for value in primitive["half_extents_mm"]:
                if _finite_number(value, "collision box half extent") <= 0.0:
                    raise MechanicsContractError("collision box half extent must be positive")

    admission: dict[str, Any] = {
        "schema": "tactevra.isaac_lm1_robot_tcp_collision_admission.v1",
        "status": "READY_TO_START_SELECTED_ISAAC_COLLISION_DIAGNOSTIC",
        "request_sha256": claimed_request_hash,
        "ik_receipt_sha256": claimed_ik_hash,
        "collision_candidate_sha256": claimed_candidate_hash,
        "virtual_profile_sha256": hashlib.sha256(virtual_profile_bytes).hexdigest(),
        "robot_import_receipt_sha256": claimed_import_hash,
        "robot_usd_sha256": robot_usd_hash,
        "toolchain_lock_sha256": request.get("toolchain_lock_sha256"),
        "bounded_sample_count": len(samples),
        "robot_body_count": len(robot_bodies),
        "workcell_body_count": len(workcell_bodies),
        "robot_placement_matrix_row_major": matrix,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
        "limitations": [
            "exploratory_uninstalled_collision_candidate_only",
            "discrete_overlap_queries_are_not_continuous_collision_proof",
            "candidate_blockers_remain_unresolved",
            "no_native_contact_or_physical_authority",
        ],
    }
    admission["admission_sha256"] = _canonical_sha256(admission)
    return admission


def run_robot_tcp_collision_diagnostic(
    *,
    request_path: Path,
    ik_receipt_path: Path,
    collision_candidate_path: Path,
    virtual_profile_path: Path,
    robot_usd_path: Path,
    import_receipt_path: Path,
    output_path: Path,
    status_path: Path,
) -> dict[str, Any]:
    """Run discrete Isaac overlap queries with no controller or hardware authority."""
    request = json.loads(request_path.resolve(strict=True).read_bytes())
    ik_receipt = json.loads(ik_receipt_path.resolve(strict=True).read_bytes())
    collision_candidate = json.loads(
        collision_candidate_path.resolve(strict=True).read_bytes()
    )
    virtual_profile_bytes = virtual_profile_path.resolve(strict=True).read_bytes()
    robot_usd = robot_usd_path.resolve(strict=True)
    robot_usd_bytes = robot_usd.read_bytes()
    import_receipt = json.loads(import_receipt_path.resolve(strict=True).read_bytes())
    admission = admit_robot_tcp_collision_diagnostic(
        request,
        ik_receipt,
        collision_candidate,
        virtual_profile_bytes,
        robot_usd_bytes,
        import_receipt,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    app = None
    try:
        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "multi_gpu": False})
        import omni.timeline
        import omni.usd
        from isaacsim.core.experimental.prims import Articulation
        from isaacsim.core.simulation_manager import SimulationManager
        from omni.physx import get_physx_scene_query_interface
        from pxr import Gf, PhysicsSchemaTools, UsdGeom, UsdPhysics

        if not omni.usd.get_context().open_stage(str(robot_usd)):
            raise RuntimeError("Isaac could not open the governed robot USD")
        for _ in range(5):
            app.update()
        stage = omni.usd.get_context().get_stage()

        prim_by_name: dict[str, Any] = {}
        for prim in stage.Traverse():
            prim_by_name.setdefault(prim.GetName(), prim)
        collision_path_to_body: dict[str, str] = {}
        query_paths: list[tuple[str, str]] = []

        def author_box(path: str, body_id: str, primitive: dict[str, Any]) -> None:
            cube = UsdGeom.Cube.Define(stage, path)
            cube.CreateSizeAttr(1.0)
            xform = UsdGeom.Xformable(cube)
            center = primitive["center_mm"]
            half = primitive["half_extents_mm"]
            xform.AddTranslateOp().Set(Gf.Vec3d(*(value / 1000.0 for value in center)))
            xform.AddScaleOp().Set(Gf.Vec3d(*(2.0 * value / 1000.0 for value in half)))
            UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
            collision_path_to_body[path] = body_id

        for body_index, body in enumerate(collision_candidate["robot_bodies"]):
            parent = prim_by_name.get(body["parent_frame"])
            if parent is None or not parent.IsValid():
                raise RuntimeError(
                    f"robot collision parent frame is unavailable: {body['parent_frame']}"
                )
            root = f"{parent.GetPath()}/TactevraCollisionDiagnostic_{body_index:02d}"
            UsdGeom.Xform.Define(stage, root)
            for primitive_index, primitive in enumerate(body["primitives"]):
                path = f"{root}/box_{primitive_index:02d}"
                author_box(path, body["body_id"], primitive)
                query_paths.append((path, body["body_id"]))

        workcell_root = "/TactevraCollisionDiagnostic/Workcell"
        UsdGeom.Xform.Define(stage, workcell_root)
        for body_index, body in enumerate(collision_candidate["workcell_bodies"]):
            root = f"{workcell_root}/body_{body_index:02d}"
            UsdGeom.Xform.Define(stage, root)
            for primitive_index, primitive in enumerate(body["primitives"]):
                path = f"{root}/box_{primitive_index:02d}"
                author_box(path, body["body_id"], primitive)

        SimulationManager.initialize_physics()
        for _ in range(10):
            app.update()
        articulation = Articulation("/roarm_m3")
        expected_dofs = request["joint_order"] + ["link5_to_gripper_link"]
        if list(articulation.dof_names) != expected_dofs:
            raise RuntimeError("Isaac articulation DOF order differs from the request")
        if not articulation.is_physics_tensor_entity_valid():
            raise RuntimeError("Isaac physics articulation view is unavailable")

        matrix = admission["robot_placement_matrix_row_major"]
        yaw = math.atan2(matrix[4], matrix[0])
        base_translation = [matrix[3] / 1000.0, matrix[7] / 1000.0, matrix[11] / 1000.0]
        base_quaternion_wxyz = [math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)]
        timeline = omni.timeline.get_timeline_interface()
        timeline.play()
        app.update()
        scene_query = get_physx_scene_query_interface()
        observed_samples = []
        all_pairs: set[tuple[str, str]] = set()
        for sample in request["bounded_samples"]:
            desired = [
                sample["joint_positions_rad"][name] for name in request["joint_order"]
            ] + [0.0]
            articulation.set_world_poses([base_translation], [base_quaternion_wxyz])
            articulation.set_dof_positions([desired])
            app.update()
            sample_pairs: set[tuple[str, str]] = set()
            for query_path, query_body in query_paths:
                hits: list[str] = []

                def report_hit(hit: Any) -> bool:
                    collision_path = str(getattr(hit, "collision", ""))
                    rigid_path = str(getattr(hit, "rigid_body", ""))
                    other = collision_path_to_body.get(collision_path)
                    if other is None:
                        other = collision_path_to_body.get(rigid_path)
                    if other is not None and other != query_body:
                        hits.append(other)
                    return True

                encoded = PhysicsSchemaTools.encodeSdfPath(query_path)
                scene_query.overlap_shape(encoded[0], encoded[1], report_hit, False)
                for other_body in hits:
                    sample_pairs.add(tuple(sorted((query_body, other_body))))
            all_pairs.update(sample_pairs)
            observed_samples.append({
                "sample_sequence": sample["sample_sequence"],
                "sample_id": sample["sample_id"],
                "source_segment_index": sample["source_segment_index"],
                "joint_positions_rad": sample["joint_positions_rad"],
                "collision_pair_count": len(sample_pairs),
                "collision_pairs": [list(pair) for pair in sorted(sample_pairs)],
            })
        timeline.stop()

        adjacent_pairs = {
            tuple(sorted(pair)) for pair in (
                ("robot:base_link", "robot:link1"),
                ("robot:link1", "robot:link2"),
                ("robot:link2", "robot:link3"),
                ("robot:link3", "robot:link4"),
                ("robot:link5", "robot:gripper"),
            )
        }
        pair_sample_counts = {
            pair: sum(pair in {
                tuple(item) for item in sample["collision_pairs"]
            } for sample in observed_samples)
            for pair in all_pairs
        }
        pair_observations = [
            {
                "body_pair": list(pair),
                "sample_count": pair_sample_counts[pair],
                "persistent_across_all_samples": (
                    pair_sample_counts[pair] == len(observed_samples)
                ),
                "classification": (
                    "KINEMATIC_NEIGHBOR_EXCLUSION_REVIEW_REQUIRED"
                    if pair in adjacent_pairs
                    else "UNREVIEWED_COLLISION_OBSERVATION"
                ),
            }
            for pair in sorted(all_pairs)
        ]

        receipt: dict[str, Any] = {
            "schema": TCP_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA,
            "status": (
                "DIAGNOSTIC_OVERLAPS_OBSERVED"
                if all_pairs else "DIAGNOSTIC_NO_OVERLAPS_OBSERVED"
            ),
            "evidence_class": "NATIVE_ISAAC_EXPLORATORY_COLLISION_DIAGNOSTIC_ONLY",
            "admission_sha256": admission["admission_sha256"],
            "source_bindings": {
                key: admission[key] for key in (
                    "request_sha256",
                    "ik_receipt_sha256",
                    "collision_candidate_sha256",
                    "virtual_profile_sha256",
                    "robot_import_receipt_sha256",
                    "robot_usd_sha256",
                    "toolchain_lock_sha256",
                )
            },
            "bounded_sample_count": len(observed_samples),
            "samples_with_overlaps": sum(
                item["collision_pair_count"] > 0 for item in observed_samples
            ),
            "unique_collision_pair_count": len(all_pairs),
            "unique_collision_pairs": [list(pair) for pair in sorted(all_pairs)],
            "pair_observations": pair_observations,
            "samples": observed_samples,
            "collision_screening_executed": True,
            "installed_collision_qualified": False,
            "continuous_collision_proven": False,
            "native_contact_replay_authorized": False,
            "candidate_blockers": collision_candidate["blockers"],
            "hardware_access": False,
            "physical_authority": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "gate_promotions": [],
            "limitations": admission["limitations"] + [
                "adjacent_link_pairs_are_retained_without_policy_exclusion",
                "overlap_results_do_not_measure_clearance_distance",
            ],
        }
        receipt["receipt_sha256"] = _canonical_sha256(receipt)
        output_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        status_path.write_text(json.dumps({
            "status": receipt["status"],
            "receipt_sha256": receipt["receipt_sha256"],
            "bounded_sample_count": receipt["bounded_sample_count"],
            "samples_with_overlaps": receipt["samples_with_overlaps"],
            "unique_collision_pair_count": receipt["unique_collision_pair_count"],
        }, sort_keys=True) + "\n", encoding="utf-8")
        return receipt
    except BaseException as exc:
        status_path.write_text(json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
        }, sort_keys=True) + "\n", encoding="utf-8")
        raise
    finally:
        if app is not None:
            app.close()


def assess_native_key_trace(
    profile: dict[str, Any],
    native_samples: Iterable[dict[str, Any]],
    *,
    rest_key_z_m: float | None = None,
) -> dict[str, Any]:
    """Convert native key displacement into the shared mechanism-state contract."""
    rows = list(native_samples)
    if len(rows) < 2:
        raise MechanicsContractError("native trace must contain at least two samples")
    rest_z = _finite_number(
        rows[0].get("key_center_z_m") if rest_key_z_m is None else rest_key_z_m,
        "native rest key z",
    )
    h_center = profile["regions"]["H"]["center_board_xy_mm"]
    contract_trace = []
    native_contact_steps = 0
    for index, row in enumerate(rows):
        key_z = _finite_number(row.get("key_center_z_m"), f"native sample {index} key z")
        separation = _finite_number(row.get("tip_key_separation_m"), f"native sample {index} separation")
        if separation <= 0.00005:
            native_contact_steps += 1
        contract_trace.append({
            "time_s": _finite_number(row.get("time_s"), f"native sample {index} time"),
            "tip_x_board_mm": h_center[0],
            "tip_y_board_mm": h_center[1],
            "compression_mm": max(0.0, (rest_z - key_z) * 1000.0),
        })
    result = evaluate_trace(profile, contract_trace)
    result["native_contact_step_count"] = native_contact_steps
    result["native_contact_observed"] = native_contact_steps > 0
    result["native_trace_sample_count"] = len(rows)
    result["result_sha256"] = _canonical_sha256(
        {key: value for key, value in result.items() if key != "result_sha256"}
    )
    return result


def run_native_h_probe(
    layout_path: Path, *, output_path: Path | None = None, status_path: Path | None = None
) -> dict[str, Any]:
    """Run a zero-authority native Isaac prismatic-key contact replay."""
    profile = build_profile(layout_path)
    h_region = profile["regions"]["H"]
    prior = profile["mechanics_prior"]
    dt = 1.0 / 120.0
    key_half_x_m = h_region["half_extent_mm"][0] / 1000.0
    key_half_y_m = h_region["half_extent_mm"][1] / 1000.0
    key_half_z_m = 0.003
    key_top_z_m = profile["target_plane_z_board_mm"] / 1000.0
    key_center_z_m = key_top_z_m - key_half_z_m
    tip_radius_m = prior["tip_radius_mm"] / 1000.0
    trajectory = build_native_tip_trajectory(
        rest_top_z_m=key_top_z_m, tip_radius_m=tip_radius_m, dt=dt
    )
    app = None
    try:
        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "multi_gpu": False})
        import omni.usd
        import warp as wp
        from isaacsim.core.experimental.prims import RigidPrim
        from isaacsim.core.simulation_manager import SimulationManager
        from pxr import Gf, Sdf, UsdGeom, UsdPhysics

        omni.usd.get_context().new_stage()
        for _ in range(5):
            app.update()
        stage = omni.usd.get_context().get_stage()
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        scene = UsdPhysics.Scene.Define(stage, "/World/physicsScene")
        scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
        # The provisional key mechanism represents the keyboard's preloaded
        # dome/scissor return, not a free keycap.  Isolate that one-dimensional
        # response from gravity until measured preload data is available.
        scene.CreateGravityMagnitudeAttr().Set(0.0)

        key_path = "/World/HKey"
        key_geom = UsdGeom.Cube.Define(stage, key_path)
        key_geom.CreateSizeAttr(2.0)
        key_xform = UsdGeom.Xformable(key_geom.GetPrim())
        key_xform.AddTranslateOp().Set(Gf.Vec3d(
            h_region["center_board_xy_mm"][0] / 1000.0,
            h_region["center_board_xy_mm"][1] / 1000.0,
            key_center_z_m,
        ))
        key_xform.AddScaleOp().Set(Gf.Vec3f(key_half_x_m, key_half_y_m, key_half_z_m))
        key_prim = key_geom.GetPrim()
        UsdPhysics.CollisionAPI.Apply(key_prim)
        UsdPhysics.RigidBodyAPI.Apply(key_prim)
        mass = UsdPhysics.MassAPI.Apply(key_prim)
        mass.CreateMassAttr().Set(prior["keycap_mass_kg"]["nominal"])

        joint = UsdPhysics.PrismaticJoint.Define(stage, "/World/HKeyJoint")
        joint.CreateBody1Rel().SetTargets([Sdf.Path(key_path)])
        joint.CreateAxisAttr().Set(UsdPhysics.Tokens.z)
        joint.CreateLocalPos0Attr().Set(Gf.Vec3f(
            h_region["center_board_xy_mm"][0] / 1000.0,
            h_region["center_board_xy_mm"][1] / 1000.0,
            key_center_z_m,
        ))
        joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
        joint.CreateLowerLimitAttr().Set(-prior["travel_mm"]["nominal"] / 1000.0)
        joint.CreateUpperLimitAttr().Set(0.0)
        drive = UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "linear")
        drive.CreateTypeAttr().Set("force")
        drive.CreateTargetPositionAttr().Set(0.0)
        drive.CreateStiffnessAttr().Set(prior["stiffness_n_per_mm"]["nominal"] * 1000.0)
        drive.CreateDampingAttr().Set(prior["damping_n_s_per_mm"]["nominal"] * 1000.0)

        tip_path = "/World/VirtualTip"
        tip_geom = UsdGeom.Sphere.Define(stage, tip_path)
        tip_geom.CreateRadiusAttr().Set(tip_radius_m)
        tip_prim = tip_geom.GetPrim()
        UsdPhysics.CollisionAPI.Apply(tip_prim)
        tip_body = UsdPhysics.RigidBodyAPI.Apply(tip_prim)
        tip_body.CreateKinematicEnabledAttr().Set(True)
        UsdPhysics.MassAPI.Apply(tip_prim).CreateMassAttr().Set(0.02)

        SimulationManager.set_physics_dt(dt)
        SimulationManager.initialize_physics()
        key_view = RigidPrim(key_path)
        tip_view = RigidPrim(tip_path)
        x_m = h_region["center_board_xy_mm"][0] / 1000.0
        y_m = h_region["center_board_xy_mm"][1] / 1000.0
        tip_view.set_world_poses([[x_m, y_m, trajectory[0]["tip_z_m"]]], [[1.0, 0.0, 0.0, 0.0]])
        SimulationManager.step(steps=30)
        settled_z = float(key_view.get_world_poses()[0].numpy().tolist()[0][2])
        tip_device = tip_view._physics_rigid_body_view.get_transforms().device  # noqa: SLF001
        tip_indices = wp.array([0], dtype=wp.uint32, device=tip_device)

        native_samples = []
        for command in trajectory:
            # A kinematic target is consumed by the solver and therefore
            # transfers contact force.  set_world_poses would teleport the
            # sphere and can overlap the key without producing an impulse.
            tip_targets = wp.array(
                [[x_m, y_m, command["tip_z_m"], 0.0, 0.0, 0.0, 1.0]],
                dtype=wp.float32,
                device=tip_device,
            )
            tip_view._physics_rigid_body_view.set_kinematic_targets(  # noqa: SLF001
                tip_targets, tip_indices
            )
            SimulationManager.step(steps=1)
            observed_key_z = float(key_view.get_world_poses()[0].numpy().tolist()[0][2])
            key_top = observed_key_z + key_half_z_m
            tip_bottom = command["tip_z_m"] - tip_radius_m
            native_samples.append({
                "step": command["step"],
                "time_s": command["time_s"],
                "tip_center_z_m": command["tip_z_m"],
                "key_center_z_m": observed_key_z,
                "tip_key_separation_m": tip_bottom - key_top,
            })
        assessment = assess_native_key_trace(
            profile, native_samples, rest_key_z_m=settled_z
        )
        passed = assessment["accepted"] and assessment["resolved_key"] == "H" and assessment["native_contact_observed"]
        receipt: dict[str, Any] = {
            "schema": NATIVE_RECEIPT_SCHEMA,
            "status": "PASS" if passed else "BLOCKED_NATIVE_KEY_MECHANICS",
            "evidence_class": "PROVISIONAL_NATIVE_ISAAC_KEY_MECHANICS",
            "profile_sha256": profile["profile_sha256"],
            "layout_sha256": profile["provenance"]["layout_sha256"],
            "physics_dt_s": dt,
            "physics_steps": 30 + len(native_samples),
            "state_teleports_after_initialization": 0,
            "commanded_key": "H",
            "assessment": assessment,
            "native_trace": native_samples,
            "authority": dict(profile["authority"]),
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "isolated_native_key_and_virtual_tip_not_full_robot_contact",
                "gravity_disabled_to_model_preloaded_keyboard_return_mechanism",
                "synthetic_bounded_mechanics_priors_not_product_measurements",
                "no_physical_keyboard_controller_timing_torque_or_safety_authority",
            ],
        }
        receipt["receipt_sha256"] = _canonical_sha256(receipt)
        if output_path is not None:
            output_path.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        if status_path is not None:
            status_path.write_text(json.dumps({
                "status": receipt["status"],
                "receipt_sha256": receipt["receipt_sha256"],
            }, sort_keys=True) + "\n", encoding="utf-8")
        return receipt
    except BaseException as exc:
        if status_path is not None:
            status_path.write_text(json.dumps({
                "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
            }, sort_keys=True) + "\n", encoding="utf-8")
        raise
    finally:
        if app is not None:
            app.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    parser.add_argument("--native-h-probe", action="store_true")
    parser.add_argument(
        "--robot-tcp-bundle",
        type=Path,
        help="audit a zero-authority replay bundle against the H-key mechanics stroke",
    )
    parser.add_argument(
        "--regenerate-cartesian-schedule",
        action="store_true",
        help="emit a mechanics-compatible Cartesian request for fresh IK qualification",
    )
    parser.add_argument(
        "--cartesian-request",
        type=Path,
        help="screen a regenerated Cartesian request through canonical IK gates",
    )
    parser.add_argument(
        "--ik-source-bundle",
        type=Path,
        help="retained bundle supplying lineage and the sample-0 synthetic seed",
    )
    parser.add_argument(
        "--ik-receipt",
        type=Path,
        help="emit a bounded collision-diagnostic request from accepted IK evidence",
    )
    parser.add_argument(
        "--collision-candidate",
        type=Path,
        help="simulation-only collision candidate for the bounded diagnostic",
    )
    parser.add_argument(
        "--toolchain-lock",
        type=Path,
        help="selected zero-authority Isaac runner lock for the diagnostic",
    )
    parser.add_argument(
        "--run-collision-diagnostic",
        action="store_true",
        help="run the bounded request through native Isaac overlap queries",
    )
    parser.add_argument("--collision-request", type=Path)
    parser.add_argument("--virtual-profile", type=Path)
    parser.add_argument("--robot-usd", type=Path)
    parser.add_argument("--import-receipt", type=Path)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        if args.native_h_probe and args.robot_tcp_bundle is not None:
            raise MechanicsContractError(
                "native H probe and robot TCP binding audit are mutually exclusive"
            )
        if args.regenerate_cartesian_schedule and args.robot_tcp_bundle is None:
            raise MechanicsContractError(
                "Cartesian regeneration requires --robot-tcp-bundle"
            )
        if (args.cartesian_request is None) != (args.ik_source_bundle is None):
            raise MechanicsContractError(
                "IK screening requires both --cartesian-request and --ik-source-bundle"
            )
        request_collision_arguments = (
            args.ik_receipt, args.collision_candidate, args.toolchain_lock
        )
        if not args.run_collision_diagnostic and any(
            item is not None for item in request_collision_arguments
        ) and not all(item is not None for item in request_collision_arguments):
            raise MechanicsContractError(
                "collision request requires --ik-receipt, --collision-candidate, and --toolchain-lock"
            )
        if args.cartesian_request is not None and (
            args.native_h_probe or args.robot_tcp_bundle is not None
            or args.ik_receipt is not None
        ):
            raise MechanicsContractError(
                "IK screening is mutually exclusive with native and binding modes"
            )
        if args.run_collision_diagnostic:
            native_arguments = (
                args.collision_request,
                args.ik_receipt,
                args.collision_candidate,
                args.virtual_profile,
                args.robot_usd,
                args.import_receipt,
            )
            if not all(item is not None for item in native_arguments):
                raise MechanicsContractError(
                    "native collision diagnostic requires --collision-request, --ik-receipt, "
                    "--collision-candidate, --virtual-profile, --robot-usd, and --import-receipt"
                )
            if (
                args.toolchain_lock is not None
                or args.native_h_probe
                or args.robot_tcp_bundle is not None
                or args.cartesian_request is not None
            ):
                raise MechanicsContractError(
                    "native collision diagnostic is mutually exclusive with generation modes"
                )
            result = run_robot_tcp_collision_diagnostic(
                request_path=args.collision_request,
                ik_receipt_path=args.ik_receipt,
                collision_candidate_path=args.collision_candidate,
                virtual_profile_path=args.virtual_profile,
                robot_usd_path=args.robot_usd,
                import_receipt_path=args.import_receipt,
                output_path=args.output,
                status_path=args.status_output,
            )
        elif args.ik_receipt is not None:
            if args.native_h_probe or args.robot_tcp_bundle is not None:
                raise MechanicsContractError(
                    "collision request is mutually exclusive with native and binding modes"
                )
            result = build_robot_tcp_collision_replay_request(
                json.loads(args.ik_receipt.resolve(strict=True).read_bytes()),
                json.loads(args.collision_candidate.resolve(strict=True).read_bytes()),
                json.loads(args.toolchain_lock.resolve(strict=True).read_bytes()),
            )
        elif args.cartesian_request is not None:
            profile = build_profile(args.layout.resolve(strict=True))
            result = screen_robot_tcp_cartesian_schedule_ik(
                json.loads(args.cartesian_request.resolve(strict=True).read_bytes()),
                json.loads(args.ik_source_bundle.resolve(strict=True).read_bytes()),
                profile,
                workspace=args.workspace,
            )
        elif args.native_h_probe:
            result = run_native_h_probe(
                args.layout.resolve(strict=True),
                output_path=args.output,
                status_path=args.status_output,
            )
        elif args.robot_tcp_bundle is not None:
            profile = build_profile(args.layout.resolve(strict=True))
            bundle = json.loads(args.robot_tcp_bundle.resolve(strict=True).read_bytes())
            if args.regenerate_cartesian_schedule:
                result = build_robot_tcp_cartesian_schedule_request(profile, bundle)
            else:
                result = bind_robot_tcp_contact_requirement(profile, bundle)
        else:
            result = run_contract_campaign(args.layout.resolve(strict=True))
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        evidence_sha256 = result.get(
            "receipt_sha256",
            result.get("binding_sha256", result.get("request_sha256")),
        )
        if not isinstance(evidence_sha256, str):
            raise MechanicsContractError("result lacks an evidence digest")
        args.status_output.write_text(json.dumps({
            "status": result["status"],
            "receipt_sha256": evidence_sha256,
        }, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if result["status"] in {
            "PASS", "READY_FOR_DRIVE_CONTROLLED_NATIVE_REPLAY",
            "READY_FOR_IK_QUALIFICATION", "READY_FOR_COLLISION_QUALIFICATION",
            "READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC",
            "DIAGNOSTIC_OVERLAPS_OBSERVED", "DIAGNOSTIC_NO_OVERLAPS_OBSERVED",
        } else 2
    except BaseException as exc:
        args.status_output.write_text(json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
        }, sort_keys=True) + "\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
