"""Select a fixed nadir camera center from complete model crop footprints.

This is a synthetic geometry screen.  It does not calibrate a camera or grant
physical authority.  Both model candidates consume the same 48 mm source
footprint and differ only in their final 96/192 pixel resampling.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.resolve(strict=True).read_bytes()).hexdigest()


def _lower_envelope_maximum(lines: list[tuple[float, float]]) -> tuple[float, float]:
    """Return x and value maximizing min(a*x+b) for affine lines."""
    candidates: set[float] = set()
    for index, (left_a, left_b) in enumerate(lines):
        for right_a, right_b in lines[index + 1 :]:
            if left_a != right_a:
                candidates.add((right_b - left_b) / (left_a - right_a))
    if not candidates:
        raise ValueError("crop screen requires intersecting border constraints")
    scored = [(min(a * value + b for a, b in lines), value) for value in candidates]
    score, value = max(scored)
    return value, score


def _closest_feasible(
    lines: list[tuple[float, float]], threshold: float, preferred: float
) -> float:
    lower = float("-inf")
    upper = float("inf")
    for slope, intercept in lines:
        if slope > 0:
            lower = max(lower, (threshold - intercept) / slope)
        elif slope < 0:
            upper = min(upper, (threshold - intercept) / slope)
        elif intercept < threshold:
            raise ValueError("no camera center can satisfy the crop threshold")
    if lower > upper:
        raise ValueError("crop threshold has an empty camera-center interval")
    return min(max(preferred, lower), upper)


def select_center(
    targets: list[Any],
    heights_mm: list[int],
    *,
    width_px: int,
    height_px: int,
    focal_px: float,
    extent_mm: float,
    preferred_xy_mm: tuple[float, float],
) -> dict[str, Any]:
    half = extent_mm / 2.0
    center_u = width_px / 2.0
    center_v = height_px / 2.0
    x_lines: list[tuple[float, float]] = []
    y_lines: list[tuple[float, float]] = []
    physical_x_lower: list[tuple[float, dict[str, Any]]] = []
    physical_x_upper: list[tuple[float, dict[str, Any]]] = []
    physical_y_lower: list[tuple[float, dict[str, Any]]] = []
    physical_y_upper: list[tuple[float, dict[str, Any]]] = []
    for target in targets:
        for height in heights_mm:
            depth = float(height) - float(target.center.z)
            scale = focal_px / depth
            identity = {
                "device": target.device,
                "target_id": target.target_id,
                "height_board_mm": height,
                "pixels_per_mm": scale,
            }
            # u = center_u + scale * (x - camera_x)
            x_lines.append((-scale, center_u + scale * (target.center.x - half)))
            x_lines.append((scale, width_px - center_u - scale * (target.center.x + half)))
            physical_x_lower.append(
                (target.center.x + half - (width_px - center_u) / scale, {**identity, "edge": "right"})
            )
            physical_x_upper.append(
                (target.center.x - half + center_u / scale, {**identity, "edge": "left"})
            )
            # v = center_v - scale * (y - camera_y)
            y_lines.append((scale, center_v - scale * (target.center.y + half)))
            y_lines.append((-scale, height_px - center_v + scale * (target.center.y - half)))
            physical_y_lower.append(
                (target.center.y + half - center_v / scale, {**identity, "edge": "top"})
            )
            physical_y_upper.append(
                (target.center.y - half + (height_px - center_v) / scale, {**identity, "edge": "bottom"})
            )

    best_x, best_x_margin = _lower_envelope_maximum(x_lines)
    best_y, best_y_margin = _lower_envelope_maximum(y_lines)
    optimum = min(best_x_margin, best_y_margin)
    selected_x = _closest_feasible(x_lines, optimum, preferred_xy_mm[0])
    selected_y = _closest_feasible(y_lines, optimum, preferred_xy_mm[1])

    x_lower = max(physical_x_lower, key=lambda item: item[0])
    x_upper = min(physical_x_upper, key=lambda item: item[0])
    y_lower = max(physical_y_lower, key=lambda item: item[0])
    y_upper = min(physical_y_upper, key=lambda item: item[0])
    tolerance_x = min(selected_x - x_lower[0], x_upper[0] - selected_x)
    tolerance_y = min(selected_y - y_lower[0], y_upper[0] - selected_y)
    max_scale = max(
        focal_px / (float(height) - float(target.center.z))
        for target in targets
        for height in heights_mm
    )
    alignment_reserve_px = 2.0
    alignment_reserve_mm = alignment_reserve_px / max_scale
    return {
        "selected_center_board_xy_mm": [selected_x, selected_y],
        "maximum_minimum_floating_border_px": optimum,
        "axis_optima": {
            "x": {"center_mm": best_x, "border_px": best_x_margin},
            "y": {"center_mm": best_y, "border_px": best_y_margin},
        },
        "full_containment_center_intervals_mm": {
            "x": [x_lower[0], x_upper[0]],
            "y": [y_lower[0], y_upper[0]],
        },
        "limiting_interval_constraints": {
            "x_lower": x_lower[1],
            "x_upper": x_upper[1],
            "y_lower": y_lower[1],
            "y_upper": y_upper[1],
        },
        "mounting_tolerance": {
            "meaning": "SYNTHETIC_NOMINAL_CENTER_TRANSLATION_THAT_RETAINS_COMPLETE_48_MM_FLOATING_CROPS",
            "horizontal_each_direction_mm": tolerance_x,
            "vertical_each_direction_mm": tolerance_y,
            "isotropic_before_alignment_reserve_mm": min(tolerance_x, tolerance_y),
            "integer_yuy2_alignment_reserve_px": alignment_reserve_px,
            "integer_yuy2_alignment_reserve_mm_at_max_scale": alignment_reserve_mm,
            "conservative_isotropic_after_alignment_reserve_mm": (
                min(tolerance_x, tolerance_y) - alignment_reserve_mm
            ),
            "physical_qualification": False,
        },
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    workspace = args.workspace.resolve(strict=True)
    family = json.loads(args.camera_family.resolve(strict=True).read_text(encoding="utf-8"))
    probe_path = args.projection.resolve(strict=True)
    spec = importlib.util.spec_from_file_location("paired_height_projection", probe_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load projection implementation")
    projection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(projection)

    import sys

    sys.path.insert(0, str(workspace / "software" / "src"))
    from rocell.targets.nominal import load_nominal_target_catalog

    catalog = load_nominal_target_catalog(workspace, args.target_catalog.resolve(strict=True))
    targets = sorted(
        [*catalog.keyboard_targets.values(), *catalog.phone_targets.values()],
        key=lambda item: (item.device, item.target_id),
    )
    sensor = family["sensor_mode"]
    lens = family["lens_candidates"][0]
    intrinsics = projection._native_sensor_intrinsics(
        sensor["width_px"], sensor["height_px"], sensor["pixel_pitch_um"], lens["focal_length_mm"]
    )
    heights = [700, 850, 1000]
    footprint = select_center(
        targets,
        heights,
        width_px=sensor["width_px"],
        height_px=sensor["height_px"],
        focal_px=intrinsics["fx_px"],
        extent_mm=48.0,
        preferred_xy_mm=(305.0, 228.5),
    )
    center = footprint["selected_center_board_xy_mm"]
    rows: list[dict[str, Any]] = []
    for profile in family["distortion"]["screening_profiles"]:
        distortion = {key: profile[key] for key in ("k1", "k2", "p1", "p2", "k3")}
        for target in targets:
            for height in heights:
                crop = projection._fixed_physical_crop_box(
                    (target.center.x, target.center.y, target.center.z),
                    (48.0, 48.0),
                    center,
                    height,
                    intrinsics,
                    distortion,
                    width_px=sensor["width_px"],
                    height_px=sensor["height_px"],
                    board_y_to_image_v_sign=-1,
                )["native_box_ltrb_px"]
                left, top, right, bottom = crop
                margins = {
                    "left": left,
                    "top": top,
                    "right": sensor["width_px"] - right,
                    "bottom": sensor["height_px"] - bottom,
                }
                edge = min(margins, key=margins.get)
                rows.append(
                    {
                        "distortion_profile_id": profile["id"],
                        "device": target.device,
                        "target_id": target.target_id,
                        "height_board_mm": height,
                        "minimum_border_px": margins[edge],
                        "limiting_edge": edge,
                        "fully_contained": all(value >= 0.0 for value in margins.values()),
                    }
                )
    per_profile = {}
    for profile in family["distortion"]["screening_profiles"]:
        subset = [row for row in rows if row["distortion_profile_id"] == profile["id"]]
        limiting = min(subset, key=lambda row: row["minimum_border_px"])
        per_profile[profile["id"]] = {
            "all_240_target_height_footprints_contained": all(row["fully_contained"] for row in subset),
            "minimum_border_px": limiting["minimum_border_px"],
            "limiting_row": limiting,
        }
    return {
        "schema": "tactevra.ai_paired_height_full_crop_coverage.v1",
        "status": "PASS_SYNTHETIC_FULL_CROP_COVERAGE" if all(
            value["all_240_target_height_footprints_contained"] for value in per_profile.values()
        ) else "FAIL_SYNTHETIC_FULL_CROP_COVERAGE",
        "source_commit": args.source_commit,
        "scope": "SYNTHETIC_ANALYTIC_SCREEN_NO_CAMERA_OR_PHYSICAL_QUALIFICATION",
        "bindings": {
            "camera_family_sha256": sha256_file(args.camera_family),
            "target_catalog_sha256": sha256_file(args.target_catalog),
            "projection_implementation_sha256": sha256_file(probe_path),
        },
        "target_count": len(targets),
        "heights_board_mm": heights,
        "model_consumed_footprint": {
            "physical_extent_xy_mm": [48.0, 48.0],
            "branches": [
                {"model_input_px": [96, 96], "source_footprint": "SAME_NATIVE_PIXELS"},
                {"model_input_px": [192, 192], "source_footprint": "SAME_NATIVE_PIXELS"},
            ],
            "unused_72_mm_fixture_declaration_removed": True,
        },
        "selection_rule": "MAXIMIZE_MINIMUM_NOMINAL_FLOATING_CROP_BORDER_THEN_MINIMIZE_TRANSLATION_FROM_PRIOR_CENTER",
        "prior_center_board_xy_mm": [305.0, 228.5],
        "selection": footprint,
        "distortion_diagnostics": per_profile,
        "training_rerender": {
            "all_rows_required": True,
            "expected_training_rows": 46080,
            "reuse_from_rejected_v1_3_forbidden": True,
            "reason": "camera center changes source geometry for every row",
        },
        "development_rows_opened": 0,
        "evaluation_identities_opened": 0,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "The mounting tolerance uses published nominal optics and synthetic target geometry.",
            "The distortion profiles are exploratory and are not measured B0477 calibration.",
            "Physical commissioning must measure the installed optical-axis center and recheck complete crop containment.",
            "This screen does not establish parked-arm mesh clearance.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--camera-family", type=Path, required=True)
    parser.add_argument("--target-catalog", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sha256": sha256_file(args.output), "status": result["status"]}, sort_keys=True))
    return 0 if result["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
