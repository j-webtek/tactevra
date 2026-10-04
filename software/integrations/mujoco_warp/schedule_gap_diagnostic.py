"""Attribute the retained schedule-to-FK gap without making a physical claim."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


SAMPLE_COUNT = 133
EXPECTED_ARM_REPORT_SHA256 = (
    "681455f0b734e924f0074ccfb7228ecb94c04ba62f5657f9d66b27af438c618b"
)
EXPECTED_MW2F_SHA256 = (
    "036581d32fddcfeaa0c0c32be9b9b6aa17cf1f644913816540ec8f0822e6bbc6"
)
EXPECTED_ARM_SOURCE_COMMIT = "5072c163152848bd8d78fa3fbc024e32177ac98d"
VECTOR_TOLERANCE_MM = 1e-9
SCALAR_TOLERANCE_MM = 1e-9


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _vector(value: Any, name: str) -> list[float]:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 3
        or not all(isinstance(item, (int, float)) and math.isfinite(item) for item in value)
    ):
        raise ValueError(f"{name} must be a finite three-vector")
    return [float(item) for item in value]


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _summary(values: list[float]) -> dict[str, float]:
    return {
        "minimum": min(values),
        "median": statistics.median(values),
        "p95": _percentile(values, 0.95),
        "maximum": max(values),
    }


def _pearson(left: list[float], right: list[float]) -> float | None:
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    left_delta = [value - left_mean for value in left]
    right_delta = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum(value * value for value in left_delta)
        * sum(value * value for value in right_delta)
    )
    if denominator == 0.0:
        return None
    return sum(a * b for a, b in zip(left_delta, right_delta, strict=True)) / denominator


def validate_inputs(arm_report: dict[str, Any], mw2f: dict[str, Any]) -> None:
    if arm_report.get("arm_source_commit") != EXPECTED_ARM_SOURCE_COMMIT:
        raise ValueError("arm source commit changed")
    ik = arm_report.get("ik", {})
    if ik.get("schema") != "rocell.typing_trajectory_ik_screen.v1":
        raise ValueError("unsupported arm IK report")
    results = ik.get("joint_results", [])
    if len(results) != SAMPLE_COUNT or ik.get("sample_count") != SAMPLE_COUNT:
        raise ValueError("arm report must contain exactly 133 IK samples")
    if ik.get("hardware_access") is not False or ik.get("physical_authority") is not False:
        raise ValueError("arm report carries authority")
    if ik.get("hardware_commands_generated") != 0 or ik.get("controller_commands") != []:
        raise ValueError("arm report records controller output")
    if mw2f.get("schema") != "rocell.mujoco_warp_schedule_fk_differential.v1":
        raise ValueError("unsupported MW2F receipt")
    rows = mw2f.get("rows", [])
    if len(rows) != SAMPLE_COUNT or mw2f.get("sample_count") != SAMPLE_COUNT:
        raise ValueError("MW2F receipt must contain exactly 133 rows")
    if [row.get("sequence") for row in rows] != list(range(SAMPLE_COUNT)):
        raise ValueError("MW2F row order changed")
    if mw2f.get("hardware_access") is not False or mw2f.get("physical_authority") is not False:
        raise ValueError("MW2F receipt carries authority")
    if mw2f.get("hardware_write_count") != 0 or mw2f.get("physical_movement_count") != 0:
        raise ValueError("MW2F receipt records physical activity")
    for sequence, (result, row) in enumerate(zip(results, rows, strict=True)):
        if result.get("waypoint_sequence") != sequence:
            raise ValueError("arm IK result order changed")
        if result.get("phase") != row.get("phase"):
            raise ValueError("phase semantics changed")
        if result.get("semantic_target") != row.get("target_id"):
            raise ValueError("target semantics changed")
        if result.get("accepted") is not True or result.get("ik_status") != "CONVERGED":
            raise ValueError("arm IK sample is not admitted")
        if result.get("hardware_commands_generated") != 0:
            raise ValueError("arm IK sample records controller output")
        _vector(result.get("achieved_tip_position_board_mm"), "achieved tip")
        jacobian = result.get("solver_weighted_task_jacobian", {})
        target = jacobian.get("target_tip_position_board_mm", {})
        _vector([target.get("x"), target.get("y"), target.get("z")], "target tip")
        condition = jacobian.get("condition_number")
        if not isinstance(condition, (int, float)) or not math.isfinite(condition):
            raise ValueError("Jacobian condition number is invalid")
        if jacobian.get("full_column_rank") is not True:
            raise ValueError("Jacobian rank admission changed")


def diagnose(arm_report: dict[str, Any], mw2f: dict[str, Any]) -> dict[str, Any]:
    validate_inputs(arm_report, mw2f)
    ik_results = arm_report["ik"]["joint_results"]
    rows: list[dict[str, Any]] = []
    by_phase: dict[str, list[float]] = defaultdict(list)
    residuals: list[float] = []
    reaches: list[float] = []
    conditions: list[float] = []
    sequences: list[float] = []
    for sequence, (result, source) in enumerate(zip(ik_results, mw2f["rows"], strict=True)):
        achieved = _vector(result["achieved_tip_position_board_mm"], "achieved tip")
        jacobian = result["solver_weighted_task_jacobian"]
        target_record = jacobian["target_tip_position_board_mm"]
        desired = _vector(
            [target_record["x"], target_record["y"], target_record["z"]], "target tip"
        )
        schedule_reference = _vector(
            source["schedule_reference_tip_board_mm"], "schedule reference"
        )
        rocell_tip = _vector(source["rocell_tip_board_mm"], "RoCell tip")
        desired_vs_schedule = math.dist(desired, schedule_reference)
        achieved_vs_rocell = math.dist(achieved, rocell_tip)
        computed_residual = math.dist(desired, achieved)
        reported_residual = float(result["position_error_mm"])
        residual_delta = abs(computed_residual - reported_residual)
        reach_xy = math.hypot(desired[0], desired[1])
        condition = float(jacobian["condition_number"])
        row = {
            "sequence": sequence,
            "phase": source["phase"],
            "target_id": source["target_id"],
            "desired_vs_schedule_reference_mm": desired_vs_schedule,
            "achieved_vs_rocell_fk_mm": achieved_vs_rocell,
            "computed_ik_residual_mm": computed_residual,
            "reported_ik_residual_mm": reported_residual,
            "computed_vs_reported_residual_delta_mm": residual_delta,
            "desired_xy_radius_from_board_origin_mm": reach_xy,
            "solver_weighted_jacobian_condition_number": condition,
            "attempt_count": int(result["attempt_count"]),
            "selected_attempt_index": int(result["selected_attempt_index"]),
        }
        rows.append(row)
        residuals.append(computed_residual)
        reaches.append(reach_xy)
        conditions.append(condition)
        sequences.append(float(sequence))
        by_phase[source["phase"]].append(computed_residual)

    maximum_row = max(rows, key=lambda row: row["computed_ik_residual_mm"])
    metrics = {
        "ik_residual_mm": _summary(residuals),
        "maximum_desired_vs_schedule_reference_mm": max(
            row["desired_vs_schedule_reference_mm"] for row in rows
        ),
        "maximum_achieved_vs_rocell_fk_mm": max(
            row["achieved_vs_rocell_fk_mm"] for row in rows
        ),
        "maximum_computed_vs_reported_residual_delta_mm": max(
            row["computed_vs_reported_residual_delta_mm"] for row in rows
        ),
        "maximum_residual_row": maximum_row,
        "phase_residual_mm": {
            phase: _summary(values) for phase, values in sorted(by_phase.items())
        },
        "diagnostic_pearson_correlation": {
            "residual_vs_board_origin_xy_radius": _pearson(residuals, reaches),
            "residual_vs_solver_weighted_jacobian_condition_number": _pearson(
                residuals, conditions
            ),
            "residual_vs_sequence": _pearson(residuals, sequences),
        },
    }
    gates = {
        "all_133_rows_exact_order_and_semantics": len(rows) == SAMPLE_COUNT,
        "desired_waypoints_equal_schedule_reference": metrics[
            "maximum_desired_vs_schedule_reference_mm"
        ]
        <= VECTOR_TOLERANCE_MM,
        "serialized_joints_reproduce_reported_achieved_fk": metrics[
            "maximum_achieved_vs_rocell_fk_mm"
        ]
        <= VECTOR_TOLERANCE_MM,
        "computed_residual_equals_reported_ik_residual": metrics[
            "maximum_computed_vs_reported_residual_delta_mm"
        ]
        <= SCALAR_TOLERANCE_MM,
    }
    result: dict[str, Any] = {
        "schema": "rocell.mujoco_warp_schedule_gap_diagnostic.v1",
        "status": "CONFIRMED_ACCEPTED_IK_RESIDUAL" if all(gates.values()) else "UNRESOLVED",
        "scope": "SYNTHETIC_OFFLINE_KINEMATIC_ATTRIBUTION_ONLY",
        "sample_count": SAMPLE_COUNT,
        "tolerances_mm": {
            "vector_reconciliation": VECTOR_TOLERANCE_MM,
            "reported_residual_reconciliation": SCALAR_TOLERANCE_MM,
        },
        "metrics": metrics,
        "gates": gates,
        "rows": rows,
        "interpretation": {
            "schedule_gap_source": "ACCEPTED_NUMERICAL_INVERSE_KINEMATICS_RESIDUAL",
            "serialization_rounding_supported": False,
            "backend_geometry_mismatch_supported": False,
            "four_backend_parity_claim": "IMPLEMENTATION_CONSISTENCY_ONLY",
            "physical_arm_accuracy_claim": "NOT_TESTED_REQUIRES_PHYSICAL_CALIBRATION",
        },
        "hardware_access": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physics_step_count": 0,
        "physical_authority": False,
        "controller_commands": [],
        "limitations": [
            "all compared backends derive from the same governed URDF and can share the same physical-model error",
            "board placement and tool length remain unmeasured simulation-only overlays",
            "correlations are descriptive diagnostics and do not establish causation or a physical bound",
            "no uncertainty, safe-region, silhouette, collision, dynamics, contact, or hardware qualification",
        ],
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm-report", type=Path, required=True)
    parser.add_argument("--mw2f", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sha256(args.arm_report) != EXPECTED_ARM_REPORT_SHA256:
        raise ValueError("arm report SHA-256 mismatch")
    if sha256(args.mw2f) != EXPECTED_MW2F_SHA256:
        raise ValueError("MW2F SHA-256 mismatch")
    arm_report = json.loads(args.arm_report.read_text(encoding="utf-8"))
    mw2f = json.loads(args.mw2f.read_text(encoding="utf-8"))
    result = diagnose(arm_report, mw2f)
    result["source_file_sha256"] = {
        "promoted_arm_report": EXPECTED_ARM_REPORT_SHA256,
        "mw2f_cuda0_receipt": EXPECTED_MW2F_SHA256,
    }
    result["receipt_sha256"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "metrics": result["metrics"]}, sort_keys=True))
    return 0 if result["status"] == "CONFIRMED_ACCEPTED_IK_RESIDUAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
