"""Conservative, simulation-only screen for the selected floor tripod.

The geometry in this module is deliberately synthetic.  It can reject a
candidate arrangement, but it cannot qualify received hardware or authorize
installation, motion, or contact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _resolve(workspace: Path, path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else workspace / candidate


def load_tripod_screen_fixture(path: Path, *, workspace: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _sha(value) != claimed:
        raise ValueError("tripod-screen fixture hash mismatch")
    value["fixture_sha256"] = claimed
    if value["scope"] != "SYNTHETIC_TRIPOD_SCREEN_ONLY" or value["physical_authority"]:
        raise ValueError("tripod-screen fixture changed zero-authority scope")
    if any(value["counters"].values()):
        raise ValueError("tripod-screen fixture contains nonzero authority counters")
    for name, binding in value["bindings"].items():
        source = _resolve(workspace, binding["path"])
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound tripod-screen input changed: {name}")
    candidate = json.loads(_resolve(
        workspace, value["bindings"]["tripod_candidate"]["path"]
    ).read_text(encoding="utf-8"))
    expected = value["selected_support"]
    if candidate["candidate_id"] != expected["candidate_id"]:
        raise ValueError("wrong tripod candidate selected")
    if candidate["architecture"]["support_type"] != expected["support_type"]:
        raise ValueError("wrong support model selected")
    if candidate["decision_state"] != "SELECTED_UNQUALIFIED":
        raise ValueError("tripod candidate selection state changed")
    return value


def _aabb_distance(left: dict[str, list[float]], right: dict[str, list[float]]) -> float:
    gaps = []
    penetrations = []
    for axis in range(3):
        gap = max(left["min"][axis] - right["max"][axis],
                  right["min"][axis] - left["max"][axis], 0.0)
        gaps.append(gap)
        overlap = min(left["max"][axis], right["max"][axis]) - max(
            left["min"][axis], right["min"][axis])
        penetrations.append(overlap)
    if any(gaps):
        return math.sqrt(sum(gap * gap for gap in gaps))
    return -min(penetrations)


def _box(body_id: str, minimum: list[float], maximum: list[float],
         evidence: str = "SYNTHETIC_TEST_ONLY") -> dict[str, Any]:
    return {"body_id": body_id, "kind": "AABB", "min": minimum,
            "max": maximum, "evidence_state": evidence}


def _bodies(spec: dict[str, Any], height: float) -> list[dict[str, Any]]:
    x, y = spec["column_center_board_xy_mm"]
    optical_x, optical_y = spec["optical_axis_board_xy_mm"]
    floor = spec["floor_z_mm"]
    foot_radius = spec["footprint_radius_mm"]
    column_radius = spec["column_radius_mm"]
    neck_radius = spec["neck_radius_mm"]
    cable_radius = spec["cable_radius_mm"]
    bodies = [
        _box("tripod:floor_footprint", [x-foot_radius, y-foot_radius, floor],
             [x+foot_radius, y+foot_radius, floor+spec["foot_height_mm"]]),
        _box("tripod:column", [x-column_radius, y-column_radius, floor],
             [x+column_radius, y+column_radius, height+spec["neck_above_optical_mm"]]),
        _box("tripod:head", [x-55, y-55, height+35], [x+55, y+55, height+125]),
        _box("tripod:overhead_neck",
             [min(x, optical_x)-neck_radius, min(y, optical_y)-neck_radius, height+60],
             [max(x, optical_x)+neck_radius, max(y, optical_y)+neck_radius, height+140]),
        _box("tripod:adapter", [optical_x-35, optical_y-35, height+40],
             [optical_x+35, optical_y+35, height+85]),
        _box("tripod:b0477_camera", [optical_x-40, optical_y-40, height],
             [optical_x+40, optical_y+40, height+65]),
        _box("tripod:usb_cable_service_loop",
             [min(x, optical_x)-cable_radius, min(y, optical_y)-cable_radius,
              height-spec["cable_drop_below_optical_mm"]-cable_radius],
             [max(x, optical_x)+cable_radius, max(y, optical_y)+cable_radius,
              height-spec["cable_drop_below_optical_mm"]+cable_radius]),
        _box("tripod:operator_keepout", [x-250, y-250, floor],
             [x+250, y+250, 0.0]),
    ]
    for index, angle_deg in enumerate((90.0, 210.0, 330.0), start=1):
        angle = math.radians(angle_deg)
        fx, fy = x + foot_radius * math.cos(angle), y + foot_radius * math.sin(angle)
        bodies.append(_box(f"tripod:leg_{index}",
                           [min(x, fx)-30, min(y, fy)-30, floor],
                           [max(x, fx)+30, max(y, fy)+30, floor+110]))
    return bodies


def run_tripod_support_screen(fixture: dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    camera = json.loads(_resolve(
        workspace, fixture["bindings"]["camera_profile"]["path"]
    ).read_text(encoding="utf-8"))
    architecture = json.loads(_resolve(
        workspace, fixture["bindings"]["camera_architecture"]["path"]
    ).read_text(encoding="utf-8"))
    fov = camera["published_optics"]
    required = architecture["optical_screening"]["provisional_required_coverage_mm"]
    screen = fixture["screen"]
    swept = screen["approved_motion_swept_aabb_mm"]
    rows = []
    inventory = set()
    for height in screen["optical_height_samples_mm"]:
        bodies = _bodies(screen, float(height))
        inventory.update(body["body_id"] for body in bodies)
        distances = {body["body_id"]: _aabb_distance(body, swept) for body in bodies}
        limiting_id = min(distances, key=distances.get)
        clearance = distances[limiting_id]
        width = 2.0 * height * math.tan(math.radians(fov["field_of_view_horizontal_deg"] / 2.0))
        depth = 2.0 * height * math.tan(math.radians(fov["field_of_view_vertical_deg"] / 2.0))
        coverage = width >= required[0] and depth >= required[1]
        collision_clear = clearance >= screen["required_clearance_mm"]
        rows.append({
            "optical_height_mm": height,
            "coverage_mm": [width, depth],
            "complete_provisional_coverage": coverage,
            "minimum_swept_volume_clearance_mm": clearance,
            "limiting_body_id": limiting_id,
            "collision_clear_with_margin": collision_clear,
            "visibility_state": "PROVISIONAL_FULL_ENVELOPE_VISIBLE" if coverage else "STOP_INCOMPLETE_ENVELOPE",
            "decision": "PASS_SYNTHETIC_ONLY" if coverage and collision_clear else "STOP",
        })
    nominal = next(row for row in rows if row["optical_height_mm"] == screen["nominal_height_mm"])
    result = {
        "schema": "tactevra.tripod_support_screen_result.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "selected_support": fixture["selected_support"],
        "body_inventory": sorted(inventory),
        "body_count": len(inventory),
        "height_results": rows,
        "nominal_height_result": nominal,
        "wrong_model_checks": {
            "tripod_candidate_identity_bound": True,
            "independent_floor_tripod_required": True,
            "legacy_mast_or_portal_accepted": False,
        },
        "decision": "PASS_NOMINAL_SYNTHETIC_SCREEN_PHYSICAL_BLOCKED"
                    if nominal["decision"] == "PASS_SYNTHETIC_ONLY"
                    else "STOP_NOMINAL_SYNTHETIC_SCREEN",
        "official_readiness": "NOT_READY_FOR_FIRST_POWERED_MOTION",
        "physical_authority": False,
        "counters": fixture["counters"],
        "limitations": fixture["limitations"],
    }
    result["receipt_sha256"] = _sha(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = load_tripod_screen_fixture(args.fixture, workspace=args.workspace)
    result = run_tripod_support_screen(fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": result["decision"],
                      "receipt_sha256": result["receipt_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["load_tripod_screen_fixture", "run_tripod_support_screen"]
