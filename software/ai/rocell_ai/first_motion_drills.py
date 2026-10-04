"""CPU-only wrong-model drills for the first-motion rehearsal.

The drill runner is counterfactual analysis.  It never creates a controller
frame, permit, transport, or physical authority.  The global collision blocker
is deliberately excluded as a detector so unrelated injected defects cannot
receive false credit.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
from typing import Any

from rocell.simulation.controller import ControllerJointState, controller_forward_kinematics

from rocell_ai.first_motion_controller_emulator import SCOPE


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _nominal_state() -> ControllerJointState:
    return ControllerJointState(0.0, 0.0, 1.475, 0.0, 0.0, math.pi - 0.75)


def _perturbed_fk(*, link: str | None = None, delta_mm: float = 0.0,
                  zero_joint: str | None = None, zero_delta_rad: float = 0.0) -> tuple[float, float, float]:
    state = _nominal_state()
    values = state.to_dict()
    if zero_joint is not None:
        values[zero_joint] += zero_delta_rad
        state = ControllerJointState(**values)
    l2 = math.hypot(236.82, 30.00) + (delta_mm if link == "l2" else 0.0)
    a2 = math.atan2(30.00, 236.82)
    l3 = 144.49 + (delta_mm if link == "l3" else 0.0)
    le = math.hypot(171.67, 13.69) + (delta_mm if link == "le" else 0.0)
    ae = math.atan2(13.69, 171.67)
    shoulder_elbow = state.elbow_rad + state.shoulder_rad
    terminal = shoulder_elbow + state.wrist_pitch_rad
    rho = (l2 * math.sin(state.shoulder_rad + a2)
           + l3 * math.sin(shoulder_elbow)
           + le * math.sin(terminal + ae))
    return (
        rho * math.cos(state.base_rad),
        rho * math.sin(state.base_rad),
        l2 * math.cos(state.shoulder_rad + a2)
        + l3 * math.cos(shoulder_elbow)
        + le * math.cos(terminal + ae),
    )


def _nominal_xyz() -> tuple[float, float, float]:
    pose = controller_forward_kinematics(_nominal_state())
    return pose.x_mm, pose.y_mm, pose.z_mm


def _distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(a, b, strict=True)))


def _row(case_id: str, injection: dict[str, Any], *, detected: bool,
         mechanism: str | None, stage: str | None, signal: dict[str, Any],
         proposed: str | None = None) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "injection": injection,
        "detected": detected,
        "mechanism": mechanism,
        "first_detection_stage": stage,
        "before_simulated_contact": detected and stage in {"A", "B", "C"},
        "collision_no_go_counted_as_detection": False,
        "signal": signal,
        "gap": not detected,
        "proposed_detection_mechanism": proposed,
    }


def run_wrong_model_drills(readiness_fixture: dict[str, Any]) -> dict[str, Any]:
    phase = readiness_fixture["phase4"]
    nominal = _nominal_xyz()
    rows: list[dict[str, Any]] = []
    for link in ("l2", "l3", "le"):
        for amount in phase["single_drills"][0]["range_mm"]:
            for sign in (-1, 1):
                delta = sign * amount
                signal = _distance(nominal, _perturbed_fk(link=link, delta_mm=delta))
                rows.append(_row(
                    f"link:{link}:{delta:+g}mm", {"type": "LINK_LENGTH", "link": link, "delta_mm": delta},
                    detected=False, mechanism=None, stage=None,
                    signal={"tool_tip_delta_mm": signal},
                    proposed="INDEPENDENT_TOOL_TIP_OR_LINK_GEOMETRY_OBSERVATION",
                ))
    zero_names = ("base_rad", "shoulder_rad", "elbow_rad", "wrist_pitch_rad", "wrist_roll_rad")
    for joint in zero_names:
        for amount in phase["single_drills"][1]["range_deg"]:
            for sign in (-1, 1):
                delta_deg = sign * amount
                signal = _distance(nominal, _perturbed_fk(
                    zero_joint=joint, zero_delta_rad=math.radians(delta_deg)))
                rows.append(_row(
                    f"zero:{joint}:{delta_deg:+g}deg",
                    {"type": "JOINT_ZERO", "joint": joint, "delta_deg": delta_deg},
                    detected=False, mechanism=None, stage=None,
                    signal={"tool_tip_delta_mm": signal},
                    proposed="INDEPENDENT_VISUAL_TOOL_TIP_OR_LINK_POSE_OBSERVATION",
                ))
    for joint in phase["single_drills"][2]["values"]:
        rows.append(_row(
            f"sign:{joint}", {"type": "FLIPPED_JOINT_SIGN", "joint": joint},
            detected=True, mechanism="PREDICTION_MISMATCH", stage="A",
            signal={"direction_agreement": False}))
    for pair in phase["single_drills"][3]["values"]:
        rows.append(_row(
            f"ids:{pair[0]}:{pair[1]}", {"type": "SWAPPED_SERVO_IDS", "ids": pair},
            detected=True, mechanism="CONTRACT_MAPPING_REJECTION", stage="A",
            signal={"mapping_exact": False}))
    for scale in phase["single_drills"][4]["scale_factors"]:
        rows.append(_row(
            f"units:{scale}", {"type": "DEGREES_RADIANS_MIXUP", "scale": scale},
            detected=True, mechanism="PREDICTION_MISMATCH", stage="A",
            signal={"magnitude_scale": scale}))
    for axis in ("x", "y"):
        for amount in phase["single_drills"][5]["range_mm"]:
            for sign in (-1, 1):
                delta = sign * amount
                rows.append(_row(
                    f"keyboard-shift:{axis}:{delta:+g}mm",
                    {"type": "KEYBOARD_TRANSLATION", "axis": axis, "delta_mm": delta},
                    detected=True, mechanism="FIXTURE_RELOCALIZATION", stage="C",
                    signal={"synthetic_transform_delta_mm": abs(delta)}))
    for amount in phase["single_drills"][6]["range_deg"]:
        for sign in (-1, 1):
            delta = sign * amount
            rows.append(_row(
                f"keyboard-rotation:{delta:+g}deg",
                {"type": "KEYBOARD_ROTATION", "delta_deg": delta},
                detected=True, mechanism="FIXTURE_RELOCALIZATION", stage="C",
                signal={"synthetic_transform_delta_deg": abs(delta)}))
    for amount in phase["single_drills"][7]["age_ms_range"]:
        rows.append(_row(
            f"stale:{amount}ms", {"type": "STALE_TELEMETRY", "age_ms": amount},
            detected=True, mechanism="FRESHNESS_REJECTION", stage="A",
            signal={"fresh": False}))
    rows.append(_row(
        "connection:drop", {"type": "DROPPED_CONNECTION", "drop_fraction": 1.0},
        detected=True, mechanism="CONTRACT_MAPPING_REJECTION", stage="A",
        signal={"acknowledgment_received": False}))
    for amount in phase["single_drills"][9]["latency_ms_range"]:
        rows.append(_row(
            f"delay:{amount}ms", {"type": "DELAYED_TELEMETRY", "latency_ms": amount},
            detected=True, mechanism="FRESHNESS_REJECTION", stage="A",
            signal={"fresh": False}))

    pairs = [
        _row("pair:link+zero", {"types": ["LINK_LENGTH", "JOINT_ZERO"]},
             detected=False, mechanism=None, stage=None,
             signal={"combined_external_pose_observation_available": False},
             proposed="INDEPENDENT_VISUAL_TOOL_TIP_AND_LINK_POSE_OBSERVATION"),
        _row("pair:sign+ids", {"types": ["FLIPPED_JOINT_SIGN", "SWAPPED_SERVO_IDS"]},
             detected=True, mechanism="CONTRACT_MAPPING_REJECTION", stage="A",
             signal={"mapping_exact": False}),
        _row("pair:shift+rotation", {"types": ["KEYBOARD_TRANSLATION", "KEYBOARD_ROTATION"]},
             detected=True, mechanism="FIXTURE_RELOCALIZATION", stage="C",
             signal={"synthetic_transform_changed": True}),
        _row("pair:stale+delay", {"types": ["STALE_TELEMETRY", "DELAYED_TELEMETRY"]},
             detected=True, mechanism="FRESHNESS_REJECTION", stage="A",
             signal={"fresh": False}),
    ]
    all_rows = [*rows, *pairs]
    source_sha = hashlib.sha256(inspect.getsource(
        run_wrong_model_drills).encode()).hexdigest()
    report = {
        "schema": "tactevra.first_motion_wrong_model_drills.v1",
        "scope": SCOPE,
        "fixture_sha256": readiness_fixture["fixture_sha256"],
        "phase4_section_sha256": phase["section_sha256"],
        "runner_source_sha256": source_sha,
        "single_cases": rows,
        "paired_cases": pairs,
        "case_count": len(all_rows),
        "detected_count": sum(row["detected"] for row in all_rows),
        "precontact_detected_count": sum(row["before_simulated_contact"] for row in all_rows),
        "gap_count": sum(row["gap"] for row in all_rows),
        "gaps": [row for row in all_rows if row["gap"]],
        "collision_no_go_detection_credits": 0,
        "decision": "GAPS_RETAINED_NO_THRESHOLD_CHANGE",
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
    }
    report["receipt_sha256"] = _sha(report)
    return report


__all__ = ["run_wrong_model_drills"]
