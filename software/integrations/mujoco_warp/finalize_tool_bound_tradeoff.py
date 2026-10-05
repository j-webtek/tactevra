"""Combine frozen reach, continuous-clearance, and residual evidence.

This finalizer does not run physics and does not change a threshold.  It joins
the three independently produced evidence families and reports the shortest
*exploratory* feasible tool length for every frozen parameter cell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _receipt_valid(value: dict[str, Any]) -> bool:
    unsigned = dict(value)
    claimed = unsigned.pop("receipt_sha256", None)
    return isinstance(claimed, str) and claimed == _sha(unsigned)


def _gpu_payload(value: dict[str, Any]) -> bytes:
    payload = dict(value)
    for key in ("device", "stack", "receipt_sha256"):
        payload.pop(key, None)
    return _canonical(payload)


def _scenario_key(scenario: dict[str, Any]) -> tuple[float, float, float]:
    return (
        float(scenario["random_joint_noise_sigma_rad"]),
        float(scenario["fixed_backlash_and_systematic_magnitude_rad_each"]),
        float(scenario["per_key_calibration_residual_fraction"]),
    )


def _residual_cells(result: dict[str, Any]) -> dict[tuple[float, ...], dict[str, Any]]:
    cells: dict[tuple[float, ...], dict[str, Any]] = {}
    for scenario in result["scenarios"]:
        prefix = _scenario_key(scenario)
        for cell in scenario["safe_width_cells"]:
            key = prefix + (float(cell["effective_safe_half_width_mm"]),)
            if key in cells:
                raise ValueError(f"duplicate residual cell {key}")
            cells[key] = cell
    return cells


def finalize(
    fixture_path: Path,
    pose_family_path: Path,
    clearance_path: Path,
    residual_paths: dict[tuple[int, int], Path],
) -> dict[str, Any]:
    fixture = _load(fixture_path)
    poses = _load(pose_family_path)
    clearance = _load(clearance_path)
    if fixture.get("fixture_sha256") != _sha({
        key: value for key, value in fixture.items() if key != "fixture_sha256"
    }):
        raise ValueError("fixture receipt mismatch")
    if not _receipt_valid(poses) or not _receipt_valid(clearance):
        raise ValueError("pose-family or clearance receipt mismatch")
    if poses["fixture_sha256"] != fixture["fixture_sha256"]:
        raise ValueError("pose-family fixture mismatch")
    if clearance["fixture_sha256"] != fixture["fixture_sha256"]:
        raise ValueError("clearance fixture mismatch")
    if clearance["pose_family_receipt_sha256"] != poses["receipt_sha256"]:
        raise ValueError("clearance pose-family mismatch")

    lengths = [int(value) for value in fixture["length_sweep"][
        "total_hand_tcp_to_tip_length_mm"]]
    exposures = [float(value) for value in fixture["length_sweep"][
        "distal_tip_exposed_length_mm"]]
    radii = [float(value) for value in fixture["length_sweep"][
        "distal_tip_radius_mm"]]
    thresholds = [float(value) for value in fixture["continuous_geometry"][
        "minimum_clearance_mm_range"]]
    expected_residual_lengths = [length for length in lengths if poses[
        "reach_by_length_mm"][str(float(length))]["all_targets_reached"]]
    if sorted(length for length, _ in residual_paths) != sorted(
        expected_residual_lengths * 2
    ):
        raise ValueError("residual path coverage does not match reachable lengths")

    residual: dict[int, dict[int, dict[str, Any]]] = {}
    agreement: dict[str, Any] = {}
    for length in expected_residual_lengths:
        by_gpu: dict[int, dict[str, Any]] = {}
        for gpu in (0, 1):
            value = _load(residual_paths[(length, gpu)])
            if not _receipt_valid(value):
                raise ValueError(f"residual receipt mismatch for {length}/gpu{gpu}")
            if value["fixture_sha256"] != fixture["fixture_sha256"]:
                raise ValueError(f"residual fixture mismatch for {length}/gpu{gpu}")
            if value["pose_family_receipt_sha256"] != poses["receipt_sha256"]:
                raise ValueError(f"residual pose mismatch for {length}/gpu{gpu}")
            by_gpu[gpu] = value
        exact = _gpu_payload(by_gpu[0]) == _gpu_payload(by_gpu[1])
        cells0, cells1 = _residual_cells(by_gpu[0]), _residual_cells(by_gpu[1])
        if cells0.keys() != cells1.keys():
            raise ValueError(f"cross-GPU cell mismatch for {length}")
        count_agreement = all(
            cells0[key]["total_misses"] == cells1[key]["total_misses"]
            for key in cells0
        )
        max_numeric_delta = max(
            abs(float(cells0[key][metric]) - float(cells1[key][metric]))
            for key in cells0
            for metric in (
                "maximum_target_miss_ucb",
                "minimum_margin_mm",
                "minimum_target_p01_margin_mm",
            )
        )
        agreement[str(length)] = {
            "device_independent_payload_exact": exact,
            "all_total_miss_counts_exact": count_agreement,
            "maximum_reported_numeric_delta": max_numeric_delta,
            "cell_count": len(cells0),
        }
        if not count_agreement:
            raise ValueError(f"cross-GPU miss-count disagreement for {length}")
        residual[length] = by_gpu

    clearance_by_profile = {
        row["tool_configuration_sha256"]: row for row in clearance["profiles"]
    }
    profile_by_axes = {
        (
            int(row["pose_bundle"]["tool_configuration"][
                "total_hand_tcp_to_tip_length_mm"]),
            float(row["pose_bundle"]["tool_configuration"][
                "distal_tip_exposed_length_mm"]),
            float(row["pose_bundle"]["tool_configuration"][
                "distal_tip_radius_mm"]),
        ): row
        for row in poses["profiles"]
    }
    residual_axes = list(_residual_cells(residual[expected_residual_lengths[0]][0]))
    matrix: list[dict[str, Any]] = []
    selected_counts: dict[str, int] = {}
    for exposure in exposures:
        for radius in radii:
            for threshold in thresholds:
                for axes in residual_axes:
                    candidates: list[dict[str, Any]] = []
                    for length in lengths:
                        pose = profile_by_axes[(length, exposure, radius)]
                        clear = clearance_by_profile[
                            pose["tool_configuration_sha256"]]
                        reach_pass = clear["reachable_target_count"] == 46
                        clearance_pass = bool(clear["threshold_pass"][str(threshold)])
                        residual_pass = False
                        residual_summary = None
                        if length in residual:
                            cell0 = _residual_cells(residual[length][0])[axes]
                            cell1 = _residual_cells(residual[length][1])[axes]
                            residual_pass = (
                                cell0["total_misses"] == 0
                                and cell1["total_misses"] == 0
                                and float(cell0["minimum_margin_mm"]) >= 0.0
                                and float(cell1["minimum_margin_mm"]) >= 0.0
                            )
                            residual_summary = {
                                "total_misses_each_gpu": [
                                    cell0["total_misses"], cell1["total_misses"]
                                ],
                                "minimum_margin_mm": min(
                                    float(cell0["minimum_margin_mm"]),
                                    float(cell1["minimum_margin_mm"]),
                                ),
                                "minimum_target_p01_margin_mm": min(
                                    float(cell0["minimum_target_p01_margin_mm"]),
                                    float(cell1["minimum_target_p01_margin_mm"]),
                                ),
                            }
                        candidates.append({
                            "tool_length_mm": length,
                            "tool_configuration_sha256": pose[
                                "tool_configuration_sha256"],
                            "reach_pass": reach_pass,
                            "clearance_pass": clearance_pass,
                            "residual_pass": residual_pass,
                            "residual": residual_summary,
                        })
                    selected = next((
                        row for row in candidates
                        if row["reach_pass"] and row["clearance_pass"]
                        and row["residual_pass"]
                    ), None)
                    selected_length = (
                        selected["tool_length_mm"] if selected is not None else None
                    )
                    key = "NONE" if selected_length is None else str(selected_length)
                    selected_counts[key] = selected_counts.get(key, 0) + 1
                    matrix.append({
                        "tip_exposed_length_mm": exposure,
                        "tip_radius_mm": radius,
                        "minimum_clearance_threshold_mm": threshold,
                        "random_joint_noise_sigma_rad": axes[0],
                        "fixed_source_magnitude_rad": axes[1],
                        "residual_fraction": axes[2],
                        "effective_safe_half_width_mm": axes[3],
                        "selected_shortest_exploratory_length_mm": selected_length,
                        "candidates": candidates,
                    })

    inputs = {
        "fixture": {"sha256": _file_sha(fixture_path),
                    "fixture_sha256": fixture["fixture_sha256"]},
        "pose_family": {"sha256": _file_sha(pose_family_path),
                        "receipt_sha256": poses["receipt_sha256"]},
        "continuous_clearance": {"sha256": _file_sha(clearance_path),
                                 "receipt_sha256": clearance["receipt_sha256"]},
        "residual": {
            f"{length}_cuda{gpu}": {
                "sha256": _file_sha(path),
                "receipt_sha256": residual[length][gpu]["receipt_sha256"],
            }
            for (length, gpu), path in sorted(residual_paths.items())
        },
    }
    unsigned = {
        "schema": "tactevra.tool_bound_tradeoff_result.v1",
        "scope": "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY",
        "status": "COMPLETE_EXPLORATORY_WITH_FAILED_CELLS",
        "inputs": inputs,
        "cross_gpu_agreement": agreement,
        "matrix_cell_count": len(matrix),
        "selected_length_cell_counts": selected_counts,
        "selection_matrix": matrix,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
        "limitations": [
            "all geometry and uncertainty values remain synthetic ranges",
            "a selected matrix cell is not a physical tool recommendation",
            "installed geometry and physical arm accuracy remain unqualified",
        ],
    }
    unsigned["receipt_sha256"] = _sha(unsigned)
    return unsigned


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--pose-family", type=Path, required=True)
    parser.add_argument("--clearance", type=Path, required=True)
    parser.add_argument("--residual-110-cuda0", type=Path, required=True)
    parser.add_argument("--residual-110-cuda1", type=Path, required=True)
    parser.add_argument("--residual-120-cuda0", type=Path, required=True)
    parser.add_argument("--residual-120-cuda1", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = finalize(
        args.fixture,
        args.pose_family,
        args.clearance,
        {
            (110, 0): args.residual_110_cuda0,
            (110, 1): args.residual_110_cuda1,
            (120, 0): args.residual_120_cuda0,
            (120, 1): args.residual_120_cuda1,
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": result["status"],
        "matrix_cell_count": result["matrix_cell_count"],
        "selected_length_cell_counts": result["selected_length_cell_counts"],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
