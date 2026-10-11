#!/usr/bin/env python3
"""Independent RC03 release checks for CAD, layout, plates, and traceability.

This validator deliberately does not claim physical compatibility. It proves
that the generated RC03 package agrees with its authoritative configuration:
named board features, exact-solid nominal assembly checks, the master/slave
cassette architecture, direct-applied fiducials, printable meshes, QIDI plate
manifests, and release hashes.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import trimesh

from validate_tripod_camera_intake import (
    TripodIntakeError,
    validate_tripod_camera_intake,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
STL = ROOT / "stl"
PLATES = ROOT / "print_plates_3mf"
DRAWINGS = ROOT / "drawings"
FIDUCIALS = ROOT / "fiducials"

EXPECTED_REVISION = "RC03-INT-R1"
EXPECTED_STATIONS = {
    "keyboard_left": "master",
    "keyboard_right": "slave",
    "phone_tcp": "master",
}
EXPECTED_STATION_FEATURES = {
    "keyboard_left": {
        "locator": ["KBL-LOC-ROUND", "KBL-LOC-RADIAL"],
        "retention": ["KBL-HOLD-F", "KBL-HOLD-R", "KBL-CLAMP"],
    },
    "keyboard_right": {
        "locator": [],
        "retention": ["KBR-HOLD-F", "KBR-HOLD-R", "KBR-CLAMP"],
    },
    "phone_tcp": {
        "locator": ["PT-LOC-ROUND", "PT-LOC-RADIAL"],
        "retention": ["PT-HOLD-TCP", "PT-HOLD-R1", "PT-HOLD-R2"],
    },
}
EXPECTED_FEATURE_TYPES = {
    feature_id: feature_type
    for station in EXPECTED_STATION_FEATURES.values()
    for feature_type, feature_ids in (
        ("locator_pin_blind", station["locator"]),
        ("m4_retention_through", station["retention"]),
    )
    for feature_id in feature_ids
}
EXPECTED_TAGS = {
    "T0": {"id": 0, "origin": (19.5, 12.5), "center": (47.0, 40.0)},
    "T1": {"id": 1, "origin": (412.5, 12.5), "center": (440.0, 40.0)},
    "T2": {"id": 2, "origin": (19.5, 382.5), "center": (47.0, 410.0)},
    "T3": {"id": 3, "origin": (535.5, 382.5), "center": (563.0, 410.0)},
    "K0": {"id": 4, "origin": (296.5, 281.5), "center": (324.0, 309.0)},
    "P0": {"id": 5, "origin": (431.5, 281.5), "center": (459.0, 309.0)},
}
EXPECTED_TAG_ROLES = {
    "T0": "world",
    "T1": "world",
    "T2": "world",
    "T3": "world",
    "K0": "station_check",
    "P0": "station_check",
}
TAG_TILE_MM = 55.0
TAG_DETECTION_MM = 40.0
COORD_TOLERANCE_MM = 0.01


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_text_sha256(path: Path) -> str:
    """Hash UTF-8 text after Python's universal-newline normalization."""
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def canonical_json_sha256(value: Any) -> str:
    """Hash a JSON value using the package's canonical compact serialization."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def aggregate_sha256(paths: Iterable[Path], root: Path = ROOT) -> str:
    """Hash path identities and contents in a deterministic order."""
    digest = hashlib.sha256()
    resolved = sorted({path.resolve() for path in paths}, key=lambda p: p.as_posix())
    for path in resolved:
        try:
            name = path.relative_to(root.resolve()).as_posix()
        except ValueError:
            name = path.as_posix()
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def fail(message: str) -> None:
    raise ValueError(message)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        fail(f"{label} must be numeric, not boolean")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric; received {value!r}") from exc
    if not math.isfinite(number):
        fail(f"{label} must be finite")
    return number


def _pair(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        fail(f"{label} must contain exactly two coordinates")
    return _number(value[0], f"{label}[0]"), _number(value[1], f"{label}[1]")


def _xyz_allow_null_z(value: Any, label: str) -> tuple[float, float, float | None]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        fail(f"{label} must contain exactly three coordinates")
    x = _number(value[0], f"{label}[0]")
    y = _number(value[1], f"{label}[1]")
    z = None if value[2] is None else _number(value[2], f"{label}[2]")
    return x, y, z


def _close_pair(
    a: tuple[float, float],
    b: tuple[float, float],
    tolerance: float = COORD_TOLERANCE_MM,
) -> bool:
    return abs(a[0] - b[0]) <= tolerance and abs(a[1] - b[1]) <= tolerance


def _feature_xy(feature: dict[str, Any], label: str) -> tuple[float, float]:
    for key in ("xy", "board_xy", "center_xy", "center_xy_mm"):
        if key in feature:
            return _pair(feature[key], f"{label}.{key}")
    if "x" in feature and "y" in feature:
        return _number(feature["x"], f"{label}.x"), _number(feature["y"], f"{label}.y")
    if "x_mm" in feature and "y_mm" in feature:
        return _number(feature["x_mm"], f"{label}.x_mm"), _number(feature["y_mm"], f"{label}.y_mm")
    fail(f"{label} lacks named board coordinates")


def _feature_diameter(feature: dict[str, Any], label: str) -> float:
    for key in ("diameter", "diameter_mm", "hole_diameter_mm"):
        if key in feature:
            return _number(feature[key], f"{label}.{key}")
    fail(f"{label} lacks a diameter")


def _feature_kind(feature: dict[str, Any]) -> str:
    return str(feature.get("type", feature.get("kind", ""))).strip()


def _feature_owner(feature: dict[str, Any]) -> str | None:
    for key in ("station", "owner", "station_id"):
        value = feature.get(key)
        if value is not None:
            return str(value)
    return None


def _station_feature_ids(station: dict[str, Any], family: str) -> list[str]:
    keys = {
        "locator": (
            "board_locator_ids",
            "locator_feature_ids",
            "locator_features",
            "locators",
        ),
        "retention": (
            "retention_ids",
            "retention_feature_ids",
            "retention_features",
            "retention",
        ),
    }[family]
    for key in keys:
        if key not in station:
            continue
        value = station[key]
        if isinstance(value, dict):
            value = list(value.values())
        if not isinstance(value, list):
            fail(f"station {family} references must be a list")
        result = []
        for item in value:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                feature_id = item.get("feature_id", item.get("id"))
                if not feature_id:
                    fail(f"station {family} feature object lacks an ID")
                result.append(str(feature_id))
            else:
                fail(f"station {family} reference must be a string or object")
        return result
    return []


def _station_part_filename(station: dict[str, Any], label: str) -> str:
    """Normalize a controlled station part stem to its printable filename."""
    part = str(station.get("part", "")).strip()
    if not part or Path(part).name != part:
        fail(f"{label}.part must be a bare printable part name")
    filename = part if part.lower().endswith(".stl") else f"{part}.stl"
    if Path(filename).suffix.lower() != ".stl":
        fail(f"{label}.part must identify an STL")
    return filename


def _direct_tag_entries(
    layout: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    direct = layout.get("direct_tags")
    if not isinstance(direct, dict):
        fail("workcell_layout.json must contain a direct_tags object")
    if isinstance(direct.get("tags"), dict):
        return direct, direct["tags"]
    entries = {key: value for key, value in direct.items() if key in EXPECTED_TAGS}
    return direct, entries


def validate_revision_consistency(
    jobs_doc: dict[str, Any],
    layout: dict[str, Any],
    measurement: dict[str, Any],
    build_record: dict[str, Any],
) -> None:
    revisions = {
        "print_jobs.design_revision": jobs_doc.get("design_revision"),
        "workcell_layout.release_revision": layout.get("release_revision"),
        "measurement_record.design_revision": measurement.get("design_revision"),
        "job_build_record.design_revision": build_record.get("design_revision"),
    }
    wrong = {
        name: value for name, value in revisions.items() if value != EXPECTED_REVISION
    }
    if wrong:
        fail(f"RC03 revision mismatch; expected {EXPECTED_REVISION}: {wrong}")


def validate_gate_traceability(
    jobs_doc: dict[str, Any],
    measurement: dict[str, Any],
    build_record: dict[str, Any],
) -> None:
    """Prove controlled gate mappings and postprint dependency topology."""
    jobs = jobs_doc.get("jobs", [])
    jobs_by_id = {job.get("job_id"): job for job in jobs}
    build_rows = build_record.get("jobs", [])
    builds_by_id = {row.get("job_id"): row for row in build_rows}
    if len(jobs_by_id) != len(jobs) or len(builds_by_id) != len(build_rows):
        fail("job or lifecycle records contain duplicate job IDs")
    if set(jobs_by_id) != set(builds_by_id):
        fail("print jobs and lifecycle records do not cover the same jobs")

    gates = measurement.get("gates")
    if not isinstance(gates, dict):
        fail("measurement record lacks controlled gates")

    calibration_job = jobs_by_id.get("00F")
    expected_calibration_parts = {
        "hardware_fit_gauge.stl": 1,
        "m3_head_fit_gauge.stl": 1,
    }
    if not isinstance(calibration_job, dict) or calibration_job.get("parts") != expected_calibration_parts:
        fail(
            "Job 00F must qualify the calibration puck's M3 clearance and "
            "button-head recess with hardware_fit_gauge.stl and m3_head_fit_gauge.stl"
        )
    calibration_gate = gates.get("calibration_clearance_holes_coupon_pass")
    expected_calibration_fields = {
        "m3_screw_major_diameter_mm",
        "smallest_free_hole_mm",
        "screw_head_d_mm",
        "m3_head_recess_d_mm",
        "fit_result",
    }
    if not isinstance(calibration_gate, dict) or set(
        calibration_gate.get("recorded_values", {})
    ) != expected_calibration_fields:
        fail(
            "calibration_clearance_holes_coupon_pass must record the actual M3 "
            "screw, selected clearance, and selected button-head recess"
        )
    postprint_producers: dict[str, list[str]] = {}
    assembly_mappings: dict[str, list[str]] = {}
    for job_id, build in builds_by_id.items():
        for field, expected_categories in (
            ("postprint_gate_ids", {"coupon", "first_article", "postprint"}),
            ("assembly_gate_ids", {"assembly"}),
        ):
            gate_ids = build.get(field)
            if not isinstance(gate_ids, list) or len(gate_ids) != len(set(gate_ids)):
                fail(f"{job_id}.{field} must be a unique list")
            for gate_id in gate_ids:
                gate = gates.get(gate_id)
                if not isinstance(gate, dict):
                    fail(f"{job_id}.{field} references unknown gate {gate_id}")
                if gate.get("category") not in expected_categories:
                    fail(
                        f"{job_id}.{field} maps {gate_id} with incompatible "
                        f"category {gate.get('category')!r}"
                    )
                if field == "postprint_gate_ids":
                    postprint_producers.setdefault(gate_id, []).append(job_id)
                else:
                    assembly_mappings.setdefault(gate_id, []).append(job_id)

    # The revised production rail is the qualification article for both of
    # its as-printed interfaces.  Keep these gates off Job 03C1's own print
    # prerequisites so the rail can be printed and bench-qualified before it
    # releases the dependent integrated station (Job 03A).
    phone_rail_interface_gates = {
        "phone_m4_captive_nut_coupon_pass",
        "cable_tie_saddle_coupon_pass",
    }
    for gate_id in sorted(phone_rail_interface_gates):
        producers = postprint_producers.get(gate_id, [])
        if producers != ["03C1"]:
            fail(
                f"phone-rail interface gate {gate_id} must be produced only "
                f"by Job 03C1; received {producers}"
            )

    job_03c1_prerequisites = set(jobs_by_id["03C1"].get("prerequisites", []))
    circular = sorted(phone_rail_interface_gates & job_03c1_prerequisites)
    if circular:
        fail(
            "Job 03C1 cannot depend on the phone-rail interface gates it "
            f"produces: {circular}"
        )

    job_03a_prerequisites = set(jobs_by_id["03A"].get("prerequisites", []))
    missing_03a = sorted(phone_rail_interface_gates - job_03a_prerequisites)
    if missing_03a:
        fail(
            "Job 03A must depend on both Job 03C1 phone-rail interface gates; "
            f"missing {missing_03a}"
        )

    for job_id, job in jobs_by_id.items():
        prerequisites = job.get("prerequisites")
        if not isinstance(prerequisites, list) or len(prerequisites) != len(
            set(prerequisites)
        ):
            fail(f"{job_id}.prerequisites must be a unique list")
        for gate_id in prerequisites:
            gate = gates.get(gate_id)
            if not isinstance(gate, dict):
                fail(f"{job_id} references unknown prerequisite {gate_id}")
            producers = postprint_producers.get(gate_id, [])
            if job_id in producers:
                fail(f"job {job_id} cannot depend on its own postprint gate {gate_id}")
            if gate.get("category") != "coupon":
                continue
            if len(producers) != 1:
                fail(
                    f"coupon prerequisite {gate_id} must have exactly one "
                    f"postprint producer, received {producers}"
                )

    required_physical_gates = {
        "board_fabrication_pass",
        "keyboard_fixture_assembly_pass",
        "phone_fixture_assembly_pass",
        "tag_direct_installation_pass",
        "tag_plane_placement_measured",
        "station_remove_reinstall_repeatability_pass",
    }
    missing = required_physical_gates - set(gates)
    if missing:
        fail(f"physical acceptance gate coverage regressed: {sorted(missing)}")
    for gate_id in required_physical_gates:
        if gates[gate_id].get("category") != "assembly":
            fail(f"physical acceptance gate {gate_id} must be category assembly")
        if gate_id not in assembly_mappings:
            fail(f"physical acceptance gate {gate_id} is not mapped to an assembly")

    required_physical_fields = {
        "board_fabrication_pass": {
            "width_mm",
            "depth_mm",
            "thickness_mm",
            "local_thickness_by_locator_mm",
            "local_flatness_by_station_mm",
            "overall_bow_mm",
            "blind_locator_bore_depths_mm",
            "locator_projection_measurements_mm",
            "scrap_stack_proof_load_result",
            "selected_fastener_map_sha256",
        },
        "keyboard_fixture_assembly_pass": {
            "seam_gap_mm",
            "seam_flush_mismatch_mm",
            "support_plane_flatness_mm",
            "remove_reinstall_cycles",
            "pose_measurements_xyyaw_mm_deg",
            "keyboard_pose_range_mm",
            "rocking_result",
        },
        "phone_fixture_assembly_pass": {
            "button_clearance_result",
            "camera_clearance_result",
            "usb_strain_relief_result",
            "remove_reinstall_cycles",
            "phone_pose_measurements_xyyaw_mm_deg",
            "phone_pose_range_mm",
        },
        "tag_direct_installation_pass": {
            "installed_ids",
            "orientation_result",
            "full_surface_adhesive_result",
            "tile_measurements_mm",
            "detection_edge_measurements_mm",
            "edge_lift_measurements_mm",
            "static_detection_success_by_id",
        },
        "tag_plane_placement_measured": {
            "board_z_reference",
            "measurement_method",
            "measurement_tool_id",
            "evidence_reference",
            "tags",
            "physical_metrology_calculation_record",
        },
        "station_remove_reinstall_repeatability_pass": {
            "cycles",
            "measurements_by_station",
            "range_x_mm_by_station",
            "range_y_mm_by_station",
            "range_z_mm_by_station",
            "range_yaw_deg_by_station",
            "base_contact_result_by_station",
            "structural_proof_result_by_station",
        },
    }
    for gate_id, required_fields in required_physical_fields.items():
        recorded = gates[gate_id].get("recorded_values")
        if not isinstance(recorded, dict) or not required_fields.issubset(recorded):
            actual = set(recorded) if isinstance(recorded, dict) else set()
            fail(
                f"physical acceptance schema regressed for {gate_id}: "
                f"{sorted(required_fields-actual)}"
            )

    critical_prerequisites = {
        "01": {
            "keyboard_dimensions_measured",
            "keyboard_corner_coupon_pass",
            "keyboard_station_registration_coupon_pass",
            "tray_clearance_holes_coupon_pass",
            "geometry_matches_measurements",
            "qidi_studio_roundtrip_confirmed",
        },
        "02": {
            "keyboard_dimensions_measured",
            "keyboard_seam_coupon_pass",
            "keyboard_station_registration_coupon_pass",
            "keyboard_left_first_article_pass",
            "geometry_matches_measurements",
            "qidi_studio_roundtrip_confirmed",
        },
        "03A": {
            "phone_dimensions_measured",
            "phone_side_features_measured",
            "phone_cable_measured",
            "phone_station_registration_coupon_pass",
            "phone_m4_captive_nut_coupon_pass",
            "phone_station_m3_insert_coupon_pass",
            "cable_tie_saddle_coupon_pass",
            "geometry_matches_measurements",
            "qidi_studio_roundtrip_confirmed",
        },
        "03C1": {
            "phone_width_coupon_pass",
            "cradle_m4_washer_coupon_pass",
            "geometry_matches_measurements",
            "qidi_studio_roundtrip_confirmed",
        },
        "03C2": {
            "tag_stock_measured",
            "tag_artwork_scale_pass",
            "board_setup_template_scale_pass",
            "geometry_matches_measurements",
            "qidi_studio_roundtrip_confirmed",
        },
        "03D": {
            "calibration_clearance_holes_coupon_pass",
            "geometry_matches_measurements",
            "qidi_studio_roundtrip_confirmed",
        },
    }
    for job_id, required in critical_prerequisites.items():
        actual = set(jobs_by_id[job_id]["prerequisites"])
        if not required.issubset(actual):
            fail(
                f"critical RC03 prerequisite coverage regressed for {job_id}: "
                f"{sorted(required-actual)}"
            )


def validate_bom() -> int:
    """Cross-check critical purchased quantities against the RC03 architecture."""
    path = ROOT / "BOM.csv"
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows_by_key: dict[tuple[str | None, str | None], list[dict[str, str]]] = {}
    for row in rows:
        rows_by_key.setdefault((row.get("category"), row.get("item")), []).append(
            row
        )
    expected = {
        ("Core", "Structural board"): 1,
        ("Fabrication", "Digital force gauge or calibrated weights"): 1,
        ("Fabrication", "Straightedge and feeler gauge set"): 1,
        ("Fabrication", "Low-range torque driver"): 1,
        ("Vision", "Full-surface matte adhesive AprilTag tiles"): 12,
        ("Board interface", "6 mm precision dowel pins"): 6,
        ("Board interface", "M4 board threaded interfaces"): 12,
        ("Board interface", "M4 station retention screws"): 10,
        ("Board interface", "M4 station washers"): 12,
        ("Assembly", "Keyboard rear-clamp face pad pieces"): 2,
        ("Assembly", "M4 low-profile keyboard clamp/retention screws"): 4,
        ("Phone clamp", "M4 captured hex nuts"): 4,
        ("Cable management", "Nylon cable ties"): 12,
        ("TCP receiver", "M3 heat-set inserts"): 4,
        ("TCP receiver", "M3 x 10 mm button-head screws"): 4,
    }
    for (category, item), quantity in expected.items():
        candidates = rows_by_key.get((category, item), [])
        if len(candidates) != 1:
            fail(f"BOM.csv lacks critical RC03 item {category}/{item}")
        row = candidates[0]
        if abs(_number(row.get("qty"), f"BOM {item}.qty") - quantity) > 1e-9:
            fail(f"BOM.csv quantity drift for {item}")
        if row.get("required") != "Yes":
            fail(f"BOM.csv must mark critical item {item} required")

    forbidden = {
        ("Assembly", "Keyboard station support pad pieces"),
        ("Assembly", "M4 captured nuts for keyboard clamps"),
        ("Board interface", "Precision station seating shims"),
    }
    for key in forbidden:
        if key in rows_by_key:
            fail(f"BOM.csv retains non-CAD hardware {key[0]}/{key[1]}")

    board_text = " ".join(
        (
            rows_by_key[("Core", "Structural board")][0].get(
                "specification", ""
            ),
            rows_by_key[("Core", "Structural board")][0].get("notes", ""),
        )
    ).lower()
    for fragment in ("610 x 457 x 18", "no router or cnc", "seal both faces"):
        if fragment not in board_text:
            fail(f"BOM structural-board instruction lost {fragment!r}")
    pin_text = " ".join(
        (
            rows_by_key[("Board interface", "6 mm precision dowel pins")][0].get(
                "specification", ""
            ),
            rows_by_key[("Board interface", "6 mm precision dowel pins")][0].get(
                "notes", ""
            ),
        )
    ).lower()
    for fragment in ("6 x 20", "15.0 mm", "5.0 mm"):
        if fragment not in pin_text:
            fail(f"BOM locator-pin instruction lost {fragment!r}")
    tie_text = " ".join(
        (
            rows_by_key[("Cable management", "Nylon cable ties")][0].get(
                "specification", ""
            ),
            rows_by_key[("Cable management", "Nylon cable ties")][0].get(
                "notes", ""
            ),
        )
    ).lower()
    for fragment in ("4.8 mm", "1.5 mm", "5.6 x 2.2 mm", "03c1"):
        if fragment not in tie_text:
            fail(f"BOM cable-tie instruction lost {fragment!r}")
    tag_text = " ".join(
        (
            rows_by_key[
                ("Vision", "Full-surface matte adhesive AprilTag tiles")
            ][0].get("specification", ""),
            rows_by_key[
                ("Vision", "Full-surface matte adhesive AprilTag tiles")
            ][0].get("notes", ""),
        )
    ).lower()
    for fragment in ("55.0 mm", "40.0 mm", "directly"):
        if fragment not in tag_text:
            fail(f"BOM direct-tag instruction lost {fragment!r}")
    obsolete = [
        row.get("item", "")
        for row in rows
        if "tag frame" in row.get("item", "").lower()
    ]
    if obsolete:
        fail(f"BOM still contains obsolete tag-frame hardware: {obsolete}")
    return len(rows)


def validate_fastener_map() -> int:
    """Require one explicit, measurable stack record for every M4 board interface."""
    path = ROOT / "FASTENER_MAP.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    expected = {
        "KBL-HOLD-F": (165.0, 78.0, 4.0, "conventional M4 button head"),
        "KBL-HOLD-R": (102.0, 246.0, 4.0, "conventional M4 button head"),
        "KBL-CLAMP": (165.0, 254.5, 8.0, "low-profile hand-adjustable M4"),
        "KBR-HOLD-F": (323.75, 78.0, 4.0, "conventional M4 button head"),
        "KBR-HOLD-R": (383.0, 246.0, 4.0, "conventional M4 button head"),
        "KBR-CLAMP": (320.0, 254.5, 8.0, "low-profile hand-adjustable M4"),
        "PT-HOLD-TCP": (423.0, 160.0, 9.0, "conventional M4 button head"),
        "PT-HOLD-R1": (588.8, 149.12, 8.0, "conventional M4 button head"),
        "PT-HOLD-R2": (588.8, 192.32, 8.0, "conventional M4 button head"),
    }
    by_id = {row.get("feature_id", ""): row for row in rows}
    if len(rows) != 9 or set(by_id) != set(expected):
        fail("FASTENER_MAP.csv must contain exactly the nine named M4 interfaces")
    for feature_id, (x, y, stack, hardware_class) in expected.items():
        row = by_id[feature_id]
        for key, target in (("world_x_mm", x), ("world_y_mm", y), ("printed_stack_mm", stack)):
            if abs(_number(row.get(key), f"FASTENER_MAP {feature_id}.{key}") - target) > 1e-6:
                fail(f"FASTENER_MAP.csv value drift for {feature_id}/{key}")
        if row.get("hardware_class") != hardware_class:
            fail(f"FASTENER_MAP.csv hardware class drift for {feature_id}")
        if row.get("washer_qty") != "1" or row.get("board_anchor_qty") != "1":
            fail(f"FASTENER_MAP.csv must assign one washer and anchor to {feature_id}")
        acceptance = row.get("acceptance", "")
        if "0.25-0.35 N m" not in acceptance:
            fail(f"FASTENER_MAP.csv lost torque control for {feature_id}")
    return len(rows)


def validate_direct_tags(layout: dict[str, Any]) -> dict[str, Any]:
    board_w = _number(layout["board"]["width"], "board.width")
    board_d = _number(layout["board"]["depth"], "board.depth")
    container, tags = _direct_tag_entries(layout)
    if set(tags) != set(EXPECTED_TAGS):
        fail(
            "direct tag coverage mismatch; "
            f"missing={sorted(set(EXPECTED_TAGS)-set(tags))}, "
            f"extra={sorted(set(tags)-set(EXPECTED_TAGS))}"
        )
    mounting = str(
        container.get(
            "mount",
            container.get(
                "mounting", container.get("mounting_method", "direct_adhesive")
            ),
        )
    )
    if mounting != "direct_adhesive":
        fail(f"RC03 tags must use direct_adhesive mounting, received {mounting!r}")
    tile_size = _number(
        container.get("tile_size_mm", TAG_TILE_MM), "direct_tags.tile_size_mm"
    )
    detection_size = _number(
        container.get("detection_edge_mm", TAG_DETECTION_MM),
        "direct_tags.detection_edge_mm",
    )
    if abs(tile_size - TAG_TILE_MM) > COORD_TOLERANCE_MM:
        fail(f"direct tag tile must be {TAG_TILE_MM:.1f} mm")
    if abs(detection_size - TAG_DETECTION_MM) > COORD_TOLERANCE_MM:
        fail(f"direct tag detection edge must be {TAG_DETECTION_MM:.1f} mm")
    nominal_plane = container.get("nominal_plane_z_mm")
    if nominal_plane is not None:
        _number(nominal_plane, "direct_tags.nominal_plane_z_mm")
    plane_status = str(container.get("plane_z_status", "")).strip()
    if nominal_plane is None and "MEASURE" not in plane_status.upper():
        fail(
            "direct_tags with an unasserted nominal Z must explicitly require "
            "post-install measurement"
        )
    application_tool = str(container.get("application_tool", "")).strip()
    if application_tool != "tag_application_frame_55mm":
        fail(
            "direct tag application tooling must remain "
            "tag_application_frame_55mm"
        )

    ids: set[int] = set()
    for name, expected in EXPECTED_TAGS.items():
        tag = tags[name]
        if not isinstance(tag, dict):
            fail(f"direct tag {name} must be an object")
        tag_id = int(tag.get("id", -1))
        if tag_id != expected["id"]:
            fail(f"direct tag {name} ID is {tag_id}, expected {expected['id']}")
        ids.add(tag_id)
        origin = _pair(
            tag.get("tile_origin_xy", tag.get("tile_origin_xy_mm")),
            f"direct_tags.{name}.tile_origin_xy",
        )
        center = _pair(
            tag.get("detection_center_xy", tag.get("detection_center_xy_mm")),
            f"direct_tags.{name}.detection_center_xy",
        )
        if not _close_pair(origin, expected["origin"]):
            fail(f"direct tag {name} origin regressed: {origin} != {expected['origin']}")
        if not _close_pair(center, expected["center"]):
            fail(f"direct tag {name} center regressed: {center} != {expected['center']}")
        derived = (origin[0] + tile_size / 2.0, origin[1] + tile_size / 2.0)
        if not _close_pair(center, derived):
            fail(f"direct tag {name} center is not derived from its tile origin")
        yaw = _number(
            tag.get("yaw_deg", tag.get("expected_yaw_deg_in_board_frame", 0.0)),
            f"direct_tags.{name}.yaw_deg",
        )
        if abs(yaw) > 1e-6:
            fail(f"direct tag {name} nominal yaw must be 0 degrees")
        if tag.get("marked_top_edge_faces") != "+Y / board rear":
            fail(f"direct tag {name} lacks the controlled +Y orientation witness")
        if (
            origin[0] < 0
            or origin[1] < 0
            or origin[0] + tile_size > board_w
            or origin[1] + tile_size > board_d
        ):
            fail(f"direct tag {name} leaves the structural board")
        if any(key in tag for key in ("frame_origin_xy_mm", "frame_size_mm")):
            fail(f"direct tag {name} contains obsolete tag-frame fields")
    if ids != set(range(6)):
        fail(f"direct tag IDs must be exactly 0..5, received {sorted(ids)}")
    return {
        "tile_size_mm": tile_size,
        "detection_edge_mm": detection_size,
        "nominal_plane_z_mm": nominal_plane,
        "tags": tags,
    }


def validate_layout(
    layout: dict[str, Any], parameters: dict[str, Any]
) -> dict[str, Any]:
    if layout.get("schema_version") != 3:
        fail("RC03 workcell_layout.json must use schema_version 3")
    if layout.get("release_revision") != EXPECTED_REVISION:
        fail("RC03 layout release_revision is missing or stale")
    if layout.get("units") != "mm":
        fail("workcell layout units must be mm")

    board = layout.get("board", {})
    board_w = _number(board.get("width"), "board.width")
    board_d = _number(board.get("depth"), "board.depth")
    board_t = _number(board.get("thickness"), "board.thickness")
    for key, observed in (
        ("board_w", board_w),
        ("board_d", board_d),
        ("board_t", board_t),
    ):
        expected = _number(parameters.get(key), f"parameters.{key}")
        if abs(observed - expected) > COORD_TOLERANCE_MM:
            fail(
                f"layout board {key}={observed} disagrees with parameters={expected}"
            )
    if "top surface" not in str(layout.get("origin", "")).lower():
        fail("RC03 layout origin must explicitly use the finished board top surface")
    top_surface_z = _number(board.get("top_surface_z"), "board.top_surface_z")
    bottom_surface_z = _number(
        board.get("bottom_surface_z"), "board.bottom_surface_z"
    )
    if abs(top_surface_z) > COORD_TOLERANCE_MM or abs(
        bottom_surface_z + board_t
    ) > COORD_TOLERANCE_MM:
        fail("board Z convention must be top=0 and bottom=-thickness")

    printer = layout.get("printer")
    if not isinstance(printer, dict) or printer.get("model") != "QIDI Plus4":
        fail("layout printer must identify the QIDI Plus4")
    nominal_envelope = printer.get("nominal_envelope")
    protected_envelope = printer.get("protected_envelope")
    if not isinstance(nominal_envelope, list) or len(nominal_envelope) != 3:
        fail("layout printer.nominal_envelope must contain XYZ")
    if not isinstance(protected_envelope, list) or len(protected_envelope) != 3:
        fail("layout printer.protected_envelope must contain XYZ")
    expected_nominal = [
        parameters[key] for key in ("printer_x", "printer_y", "printer_z")
    ]
    expected_protected = [
        parameters[key]
        for key in ("printer_safe_x", "printer_safe_y", "printer_safe_z")
    ]
    for index, (observed, expected) in enumerate(
        zip(nominal_envelope, expected_nominal)
    ):
        if (
            abs(_number(observed, f"printer.nominal_envelope[{index}]") - expected)
            > COORD_TOLERANCE_MM
        ):
            fail("layout nominal printer envelope disagrees with parameters")
    for index, (observed, expected) in enumerate(
        zip(protected_envelope, expected_protected)
    ):
        if (
            abs(
                _number(observed, f"printer.protected_envelope[{index}]")
                - expected
            )
            > COORD_TOLERANCE_MM
        ):
            fail("layout protected printer envelope disagrees with parameters")
    if any(
        _number(safe, "printer protected envelope")
        > _number(nominal, "printer nominal envelope")
        for safe, nominal in zip(protected_envelope, nominal_envelope)
    ):
        fail("protected printer envelope cannot exceed the nominal envelope")

    stations = layout.get("stations")
    if not isinstance(stations, dict) or set(stations) != set(EXPECTED_STATIONS):
        fail(
            "station coverage mismatch; "
            f"expected={sorted(EXPECTED_STATIONS)}, actual={sorted(stations or {})}"
        )
    station_rectangles: list[tuple[str, float, float, float, float]] = []
    locator_references: list[str] = []
    retention_references: list[str] = []
    for name, expected_role in EXPECTED_STATIONS.items():
        station = stations[name]
        role = str(station.get("role", ""))
        if role != expected_role:
            fail(f"station {name} role={role!r}, expected {expected_role!r}")
        if abs(
            _number(station.get("installed_z"), f"stations.{name}.installed_z")
            - top_surface_z
        ) > COORD_TOLERANCE_MM:
            fail(f"station {name} must install on the board top plane")
        origin = _pair(station.get("origin_xy"), f"stations.{name}.origin_xy")
        envelope = _pair(
            station.get("outer_envelope"), f"stations.{name}.outer_envelope"
        )
        if (
            min(origin) < 0
            or min(envelope) <= 0
            or origin[0] + envelope[0] > board_w
            or origin[1] + envelope[1] > board_d
        ):
            fail(f"station {name} leaves the structural board")
        _station_part_filename(station, f"stations.{name}")
        station_rectangles.append(
            (name, origin[0], origin[1], envelope[0], envelope[1])
        )

        locators = _station_feature_ids(station, "locator")
        retention = _station_feature_ids(station, "retention")
        expected_locator_count = 2 if expected_role == "master" else 0
        if len(locators) != expected_locator_count:
            fail(
                f"station {name} requires {expected_locator_count} locator board "
                f"features, received {locators}"
            )
        if len(retention) != 3:
            fail(f"station {name} requires exactly three retention board features")
        if locators != EXPECTED_STATION_FEATURES[name]["locator"]:
            fail(f"station {name} locator identities/order regressed: {locators}")
        if retention != EXPECTED_STATION_FEATURES[name]["retention"]:
            fail(f"station {name} retention identities/order regressed: {retention}")
        locator_references.extend(locators)
        retention_references.extend(retention)

    for index, (name_a, ax, ay, aw, ad) in enumerate(station_rectangles):
        for name_b, bx, by, bw, bd in station_rectangles[index + 1 :]:
            overlap = np.minimum((ax + aw, ay + ad), (bx + bw, by + bd)) - np.maximum(
                (ax, ay), (bx, by)
            )
            if (
                np.all(overlap > 1e-6)
                and {name_a, name_b} != {"keyboard_left", "keyboard_right"}
            ):
                fail(f"station overlap: {name_a}/{name_b} = {overlap}")

    features = layout.get("board_features")
    if not isinstance(features, list) or len(features) != 13:
        fail(
            f"RC03 requires exactly 13 named board features, "
            f"received {len(features or [])}"
        )
    feature_by_id: dict[str, dict[str, Any]] = {}
    type_counts: Counter[str] = Counter()
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            fail(f"board_features[{index}] must be an object")
        feature_id = str(feature.get("id", "")).strip()
        if not feature_id:
            fail(f"board_features[{index}] lacks an ID")
        if feature_id in feature_by_id:
            fail(f"duplicate board feature ID {feature_id}")
        feature_by_id[feature_id] = feature
        kind = _feature_kind(feature)
        type_counts[kind] += 1
        if kind not in {"locator_pin_blind", "m4_retention_through"}:
            fail(
                f"board feature {feature_id} has unsupported RC03 type {kind!r}"
            )
        x, y = _feature_xy(feature, f"board_features.{feature_id}")
        diameter = _feature_diameter(feature, f"board_features.{feature_id}")
        radius = diameter / 2.0
        if (
            min(x - radius, y - radius) < 0
            or x + radius > board_w
            or y + radius > board_d
        ):
            fail(f"board feature {feature_id} leaves the structural board")
        owner = _feature_owner(feature)
        if owner not in EXPECTED_STATIONS:
            fail(
                f"board feature {feature_id} has unknown station owner {owner!r}"
            )
        if kind == "locator_pin_blind":
            depth = feature.get("depth_mm", feature.get("depth"))
            depth_mm = _number(
                depth, f"board_features.{feature_id}.depth_mm"
            )
            if not (0 < depth_mm < board_t):
                fail(
                    f"blind locator {feature_id} depth must be between 0 and "
                    "board thickness"
                )

    expected_counts = Counter(
        {"locator_pin_blind": 4, "m4_retention_through": 9}
    )
    if type_counts != expected_counts:
        fail(f"named board-feature type counts regressed: {dict(type_counts)}")
    if set(feature_by_id) != set(EXPECTED_FEATURE_TYPES):
        fail(
            "named board-feature identities regressed; "
            f"missing={sorted(set(EXPECTED_FEATURE_TYPES)-set(feature_by_id))}, "
            f"extra={sorted(set(feature_by_id)-set(EXPECTED_FEATURE_TYPES))}"
        )
    for feature_id, expected_type in EXPECTED_FEATURE_TYPES.items():
        if _feature_kind(feature_by_id[feature_id]) != expected_type:
            fail(f"board feature {feature_id} type regressed")
        feature = feature_by_id[feature_id]
        expected_diameter = (
            parameters["locator_pin_d"]
            if expected_type == "locator_pin_blind"
            else parameters["m4_clearance"]
        )
        if abs(
            _feature_diameter(feature, f"board_features.{feature_id}")
            - expected_diameter
        ) > COORD_TOLERANCE_MM:
            fail(f"board feature {feature_id} diameter disagrees with parameters")
        if expected_type == "locator_pin_blind":
            if abs(
                _number(feature.get("depth"), f"board_features.{feature_id}.depth")
                - parameters["locator_blind_depth"]
            ) > COORD_TOLERANCE_MM:
                fail(f"board feature {feature_id} depth disagrees with parameters")
            if abs(
                _number(
                    feature.get("protrusion"),
                    f"board_features.{feature_id}.protrusion",
                )
                - parameters["locator_pin_protrusion"]
            ) > COORD_TOLERANCE_MM:
                fail(
                    f"board feature {feature_id} protrusion disagrees with parameters"
                )
        else:
            expected_station_clearance = (
                parameters["relieved_m4_d"]
                if feature_id.startswith("KBR-")
                else parameters["m4_clearance"]
            )
            if abs(
                _number(
                    feature.get("station_clearance_d"),
                    f"board_features.{feature_id}.station_clearance_d",
                )
                - expected_station_clearance
            ) > COORD_TOLERANCE_MM:
                fail(
                    f"board feature {feature_id} station clearance disagrees "
                    "with parameters"
                )
    locator_ids = {
        feature_id
        for feature_id, feature in feature_by_id.items()
        if _feature_kind(feature) == "locator_pin_blind"
    }
    retention_ids = {
        feature_id
        for feature_id, feature in feature_by_id.items()
        if _feature_kind(feature) == "m4_retention_through"
    }
    if (
        len(locator_references) != len(set(locator_references))
        or set(locator_references) != locator_ids
    ):
        fail(
            "station locator references do not cover the four locator features "
            "exactly once"
        )
    if (
        len(retention_references) != len(set(retention_references))
        or set(retention_references) != retention_ids
    ):
        fail(
            "station retention references do not cover the nine M4 features "
            "exactly once"
        )
    for station_name, station in stations.items():
        references = _station_feature_ids(
            station, "locator"
        ) + _station_feature_ids(station, "retention")
        station_origin = _pair(
            station.get("origin_xy"), f"stations.{station_name}.origin_xy"
        )
        for feature_id in references:
            feature = feature_by_id.get(feature_id)
            if feature is None:
                fail(f"station {station_name} references unknown feature {feature_id}")
            if _feature_owner(feature) != station_name:
                fail(
                    f"feature {feature_id} owner disagrees with station {station_name}"
                )
            local_xy = _pair(
                feature.get("local_xy"), f"board_features.{feature_id}.local_xy"
            )
            derived_xy = (
                station_origin[0] + local_xy[0],
                station_origin[1] + local_xy[1],
            )
            if not _close_pair(
                _feature_xy(feature, f"board_features.{feature_id}"), derived_xy
            ):
                fail(
                    f"board feature {feature_id} does not equal station origin + "
                    "local coordinates"
                )

    for feature_id in locator_ids:
        feature = feature_by_id[feature_id]
        interface = str(feature.get("interface", "")).lower()
        if feature_id.endswith("ROUND") and "round" not in interface:
            fail(f"locator {feature_id} must identify its round interface")
        if feature_id.endswith("RADIAL") and not {
            "radial",
            "slot",
        }.intersection(interface.replace("-", "_").split("_")):
            fail(f"locator {feature_id} must identify its radial-slot interface")
        protrusion = _number(
            feature.get("protrusion"),
            f"board_features.{feature_id}.protrusion",
        )
        if protrusion <= 0:
            fail(f"locator {feature_id} protrusion must be positive")
    for station_name in ("keyboard_left", "phone_tcp"):
        round_id, radial_id = EXPECTED_STATION_FEATURES[station_name]["locator"]
        round_xy = _feature_xy(
            feature_by_id[round_id], f"board_features.{round_id}"
        )
        radial = feature_by_id[radial_id]
        radial_xy = _feature_xy(radial, f"board_features.{radial_id}")
        delta = (radial_xy[0] - round_xy[0], radial_xy[1] - round_xy[1])
        expected_axis = "x" if abs(delta[0]) >= abs(delta[1]) else "y"
        if radial.get("slot_axis") != expected_axis:
            fail(
                f"locator {radial_id} slot_axis must follow its round/radial "
                f"baseline ({expected_axis})"
            )
        if math.hypot(*delta) < 50.0:
            fail(f"locator baseline is too short for stable indexing: {station_name}")
    for feature_id in EXPECTED_STATION_FEATURES["keyboard_right"]["retention"]:
        if feature_by_id[feature_id].get("interface") != "relieved_clamp_only":
            fail(
                f"keyboard slave feature {feature_id} must be relieved_clamp_only"
            )

    seam = layout.get("interfaces", {}).get("keyboard_master_slave")
    if not isinstance(seam, dict):
        fail("layout must contain interfaces.keyboard_master_slave")
    if (
        seam.get("master_station") != "keyboard_left"
        or seam.get("slave_station") != "keyboard_right"
    ):
        fail("keyboard seam master/slave identities regressed")
    master_origin = _pair(
        stations["keyboard_left"]["origin_xy"], "keyboard master origin"
    )
    slave_origin = _pair(
        stations["keyboard_right"]["origin_xy"], "keyboard slave origin"
    )
    master_envelope = _pair(
        stations["keyboard_left"]["outer_envelope"], "keyboard master envelope"
    )
    slave_envelope = _pair(
        stations["keyboard_right"]["outer_envelope"], "keyboard slave envelope"
    )
    overlap_x = min(
        master_origin[0] + master_envelope[0],
        slave_origin[0] + slave_envelope[0],
    ) - max(master_origin[0], slave_origin[0])
    seam_x_min = max(master_origin[0], slave_origin[0])
    seam_x_max = min(
        master_origin[0] + master_envelope[0],
        slave_origin[0] + slave_envelope[0],
    )
    if not (10.0 <= overlap_x <= 30.0):
        fail("keyboard station seam overlap must remain a narrow datum corridor")
    if abs(master_origin[1] - slave_origin[1]) > COORD_TOLERANCE_MM or abs(
        master_envelope[1] - slave_envelope[1]
    ) > COORD_TOLERANCE_MM:
        fail("keyboard master/slave stations must share their Y datum and depth")
    for end in ("front", "rear"):
        board_xy = _pair(
            seam.get(f"{end}_post_board_xy"),
            f"interfaces.keyboard_master_slave.{end}_post_board_xy",
        )
        if not (seam_x_min <= board_xy[0] <= seam_x_max):
            fail(f"keyboard seam {end} datum leaves the shared seam corridor")
        master_local = _pair(
            seam.get(f"{end}_post_master_local_xy"),
            f"interfaces.keyboard_master_slave.{end}_post_master_local_xy",
        )
        slave_local = _pair(
            seam.get(f"{end}_socket_slave_local_xy"),
            f"interfaces.keyboard_master_slave.{end}_socket_slave_local_xy",
        )
        master_board = (
            master_origin[0] + master_local[0],
            master_origin[1] + master_local[1],
        )
        slave_board = (
            slave_origin[0] + slave_local[0],
            slave_origin[1] + slave_local[1],
        )
        if not _close_pair(board_xy, master_board) or not _close_pair(
            board_xy, slave_board
        ):
            fail(f"keyboard seam {end} post/socket coordinates do not coincide")
    if seam.get("front_socket") != "round" or "radial" not in str(
        seam.get("rear_socket", "")
    ):
        fail("keyboard seam must use a round front socket and radial rear socket")
    seam_parameter_map = {
        "post_diameter": "seam_post_d",
        "round_socket_diameter": "seam_round_socket_d",
        "radial_slot_length": "seam_slot_length",
        "radial_slot_width": "seam_radial_slot_w",
        "post_height": "seam_post_h",
    }
    for interface_key, parameter_key in seam_parameter_map.items():
        if abs(
            _number(seam.get(interface_key), f"keyboard seam {interface_key}")
            - parameters[parameter_key]
        ) > COORD_TOLERANCE_MM:
            fail(
                f"keyboard seam {interface_key} disagrees with {parameter_key}"
            )

    board_locator = layout.get("interfaces", {}).get("board_locator")
    if not isinstance(board_locator, dict):
        fail("layout must contain interfaces.board_locator")
    locator_parameter_map = {
        "blind_bore_depth": "locator_blind_depth",
        "projection": "locator_pin_protrusion",
        "radial_slot_length": "locator_slot_length",
        "entry_leadin_diameter": "locator_leadin_d",
    }
    for interface_key, parameter_key in locator_parameter_map.items():
        if abs(
            _number(
                board_locator.get(interface_key), f"board locator {interface_key}"
            )
            - parameters[parameter_key]
        ) > COORD_TOLERANCE_MM:
            fail(
                f"board locator {interface_key} disagrees with {parameter_key}"
            )
    profile_parameters = {
        "keyboard_tray_profile": {
            "round_socket_diameter_candidate": "keyboard_locator_socket_d",
            "radial_slot_width_candidate": "keyboard_locator_slot_w",
        },
        "phone_cradle_profile": {
            "round_socket_diameter_candidate": "phone_locator_socket_d",
            "radial_slot_width_candidate": "phone_locator_slot_w",
        },
    }
    for profile_name, field_parameters in profile_parameters.items():
        profile = board_locator.get(profile_name)
        if not isinstance(profile, dict):
            fail(f"board locator lacks independent {profile_name} candidates")
        for key, parameter_key in field_parameters.items():
            if abs(
                _number(profile.get(key), f"board locator {profile_name}.{key}")
                - parameters[parameter_key]
            ) > COORD_TOLERANCE_MM:
                fail(
                    f"board locator {profile_name}.{key} disagrees with "
                    f"{parameter_key}"
                )
    if abs(
        parameters["locator_pin_length"]
        - parameters["locator_blind_depth"]
        - parameters["locator_pin_protrusion"]
    ) > COORD_TOLERANCE_MM:
        fail("locator pin length must equal blind depth plus projection")
    if board_t - parameters["locator_blind_depth"] < 2.0:
        fail("blind locator bores require at least 2 mm intact board thickness")
    if board_locator.get("fit_release_part") != "station_locator_fit_gauge":
        fail("board locator fit must be released by station_locator_fit_gauge")

    m3_interfaces = layout.get("interfaces", {}).get("m3_insert_pockets")
    if not isinstance(m3_interfaces, dict):
        fail("layout interfaces must define independent M3 insert pocket releases")
    expected_m3_interfaces = {
        "phone_station": {
            "parameter": "phone_station_m3_insert_pocket_d",
            "fit_release_part": "phone_m3_insert_fit_gauge",
            "production_consumer": "phone_tcp_station",
            "production_profile": "abs_rapido_cradle_0p4",
            "pocket_depth_mm": 6.2,
            "representative_field": ("residual_floor_mm", 0.3),
        },
        "compliant_tool": {
            "parameter": "compliant_tool_m3_insert_pocket_d",
            "fit_release_part": "tool_m3_insert_fit_gauge",
            "production_consumer": "compliant_tool_body",
            "production_profile": "abs_rapido_precision_0p4",
            "pocket_depth_mm": 6.2,
            "representative_field": ("edge_ligament_mm", 5.0),
        },
    }
    for role, expected in expected_m3_interfaces.items():
        interface = m3_interfaces.get(role)
        if not isinstance(interface, dict):
            fail(f"layout lacks the {role} M3 insert interface")
        for key in (
            "parameter",
            "fit_release_part",
            "production_consumer",
            "production_profile",
        ):
            if interface.get(key) != expected[key]:
                fail(f"{role} M3 insert interface has stale {key}")
        parameter_key = expected["parameter"]
        if abs(
            _number(interface.get("diameter_candidate"), f"{role} M3 diameter")
            - parameters[parameter_key]
        ) > COORD_TOLERANCE_MM:
            fail(f"{role} M3 diameter disagrees with {parameter_key}")
        if abs(
            _number(interface.get("pocket_depth_mm"), f"{role} M3 pocket depth")
            - expected["pocket_depth_mm"]
        ) > COORD_TOLERANCE_MM:
            fail(f"{role} M3 pocket depth is not production-representative")
        representative_key, representative_value = expected["representative_field"]
        if abs(
            _number(interface.get(representative_key), f"{role} M3 {representative_key}")
            - representative_value
        ) > COORD_TOLERANCE_MM:
            fail(f"{role} M3 gauge no longer represents its production {representative_key}")

    pilot_holes = layout.get("pilot_holes")
    if not isinstance(pilot_holes, list) or len(pilot_holes) != len(features):
        fail("compatibility pilot_holes must mirror all 13 named board features")
    unmatched = list(pilot_holes)
    for feature_id, feature in feature_by_id.items():
        xy = _feature_xy(feature, f"board_features.{feature_id}")
        diameter = _feature_diameter(feature, f"board_features.{feature_id}")
        matches = [
            row
            for row in unmatched
            if _close_pair(_feature_xy(row, "pilot_holes"), xy)
            and abs(_feature_diameter(row, "pilot_holes") - diameter)
            <= COORD_TOLERANCE_MM
        ]
        if len(matches) != 1:
            fail(
                f"pilot_holes does not mirror board feature {feature_id} exactly once"
            )
        unmatched.remove(matches[0])

    direct_tag_summary = validate_direct_tags(layout)
    tags = direct_tag_summary["tags"]
    for station_name, x, y, width, depth in station_rectangles:
        for tag_name, tag in tags.items():
            tx, ty = _pair(
                tag.get("tile_origin_xy", tag.get("tile_origin_xy_mm")),
                f"direct_tags.{tag_name}",
            )
            overlap = np.minimum(
                (x + width, y + depth), (tx + TAG_TILE_MM, ty + TAG_TILE_MM)
            ) - np.maximum((x, y), (tx, ty))
            if np.all(overlap > 1e-6):
                fail(
                    f"direct tag {tag_name} overlaps station {station_name} "
                    f"by {overlap}"
                )

    architecture_text = json.dumps(
        layout.get("architecture", {}), sort_keys=True
    ).lower()
    if "master" not in architecture_text or "slave" not in architecture_text:
        fail(
            "layout architecture must explicitly document the keyboard "
            "master/slave system"
        )
    architecture = layout.get("architecture", {})
    expected_architecture = {
        "type": "open_indexed_stations",
        "keyboard_interface": "left_master_right_seam_slave",
        "direct_tags": True,
        "board_feature_count": 13,
        "locator_pin_count": 4,
        "m4_retention_count": 9,
    }
    for key, expected in expected_architecture.items():
        if architecture.get(key) != expected:
            fail(f"layout architecture {key} regressed")
    physical_measurements = layout.get("physical_measurements_required")
    if not isinstance(physical_measurements, list) or len(physical_measurements) < 6:
        fail("layout must enumerate the unresolved physical measurements")

    return {
        "stations": stations,
        "features": feature_by_id,
        "feature_type_counts": dict(type_counts),
        "direct_tags": direct_tag_summary,
    }


def validate_board_coordinate_csv(layout_summary: dict[str, Any]) -> None:
    path = DRAWINGS / "board_hole_coordinates.csv"
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    features = layout_summary["features"]
    id_key = "id" if rows and "id" in rows[0] else "feature_id"
    rows_by_id = {row[id_key]: row for row in rows}
    if len(rows_by_id) != len(rows):
        fail("board_hole_coordinates.csv contains duplicate feature IDs")
    if set(rows_by_id) != set(features):
        fail(
            "board coordinate CSV does not cover named features exactly; "
            f"missing={sorted(set(features)-set(rows_by_id))}, "
            f"extra={sorted(set(rows_by_id)-set(features))}"
        )
    layout_hash = sha256(CONFIG / "workcell_layout.json")
    for feature_id, feature in features.items():
        expected_xy = _feature_xy(feature, f"board_features.{feature_id}")
        expected_diameter = _feature_diameter(
            feature, f"board_features.{feature_id}"
        )
        row = rows_by_id[feature_id]
        if row.get("release_revision") != EXPECTED_REVISION:
            fail(f"board coordinate CSV revision drifted for {feature_id}")
        if row.get("layout_sha256") != layout_hash:
            fail(f"board coordinate CSV layout hash drifted for {feature_id}")
        actual_xy = (
            _number(row.get("x", row.get("x_mm")), f"CSV {feature_id} x"),
            _number(row.get("y", row.get("y_mm")), f"CSV {feature_id} y"),
        )
        actual_diameter = _number(
            row.get("diameter", row.get("diameter_mm")),
            f"CSV {feature_id} diameter",
        )
        if not _close_pair(actual_xy, expected_xy) or abs(
            actual_diameter - expected_diameter
        ) > COORD_TOLERANCE_MM:
            fail(f"board coordinate CSV values drifted for {feature_id}")
        if row.get("type") != _feature_kind(feature):
            fail(f"board coordinate CSV type drifted for {feature_id}")
        if row.get("station") != _feature_owner(feature):
            fail(f"board coordinate CSV station drifted for {feature_id}")

        local_x = row.get("local_x_mm")
        local_y = row.get("local_y_mm")
        if local_x is not None or local_y is not None:
            expected_local = _pair(
                feature.get("local_xy"), f"board_features.{feature_id}.local_xy"
            )
            actual_local = (
                _number(local_x, f"CSV {feature_id} local_x_mm"),
                _number(local_y, f"CSV {feature_id} local_y_mm"),
            )
            if not _close_pair(actual_local, expected_local):
                fail(f"board coordinate CSV local coordinates drifted for {feature_id}")

        semantic_columns = {
            "depth": ("depth_mm", "depth"),
            "protrusion": ("protrusion_mm", "protrusion"),
            "station_clearance_d": (
                "station_clearance_d_mm",
                "station_clearance_d",
            ),
        }
        for feature_key, column_names in semantic_columns.items():
            if feature_key not in feature:
                continue
            column = next((key for key in column_names if key in row), None)
            if column is None:
                fail(
                    f"board coordinate CSV omits {feature_key} for {feature_id}"
                )
            if abs(
                _number(row[column], f"CSV {feature_id} {column}")
                - _number(feature[feature_key], f"board_features.{feature_id}.{feature_key}")
            ) > COORD_TOLERANCE_MM:
                fail(f"board coordinate CSV {feature_key} drifted for {feature_id}")
        for key in ("interface", "slot_axis"):
            expected = feature.get(key)
            if expected is None:
                expected = ""
            if key in row and row[key] != str(expected):
                fail(f"board coordinate CSV {key} drifted for {feature_id}")


def validate_tag_coordinate_csv(layout_summary: dict[str, Any]) -> None:
    """Cross-check the human placement table against the frozen tag layout."""
    path = DRAWINGS / "tag_application_coordinates.csv"
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows_by_name = {row.get("name"): row for row in rows}
    if len(rows_by_name) != len(rows) or set(rows_by_name) != set(EXPECTED_TAGS):
        fail("tag application CSV must cover all six named tags exactly once")
    expected_layout_hash = sha256(CONFIG / "workcell_layout.json")
    for name, expected in EXPECTED_TAGS.items():
        row = rows_by_name[name]
        if row.get("release_revision") != EXPECTED_REVISION:
            fail(f"tag application CSV revision drift for {name}")
        if row.get("layout_sha256") != expected_layout_hash:
            fail(f"tag application CSV layout hash drift for {name}")
        if int(row.get("id", -1)) != expected["id"]:
            fail(f"tag application CSV ID drift for {name}")
        if row.get("role") != EXPECTED_TAG_ROLES[name]:
            fail(f"tag application CSV role drift for {name}")
        if row.get("mounting") != "direct_adhesive":
            fail(f"tag application CSV mounting drift for {name}")
        if row.get("board_z_reference") != "finished sealed board top surface":
            fail(f"tag application CSV board-Z reference drift for {name}")
        origin = (
            _number(row.get("tile_origin_x_mm"), f"tag CSV {name} origin X"),
            _number(row.get("tile_origin_y_mm"), f"tag CSV {name} origin Y"),
        )
        center = (
            _number(
                row.get("detection_center_x_mm"), f"tag CSV {name} center X"
            ),
            _number(
                row.get("detection_center_y_mm"), f"tag CSV {name} center Y"
            ),
        )
        if not _close_pair(origin, expected["origin"]) or not _close_pair(
            center, expected["center"]
        ):
            fail(f"tag application CSV coordinates drifted for {name}")
        if abs(
            _number(row.get("tile_size_mm"), f"tag CSV {name} tile")
            - TAG_TILE_MM
        ) > COORD_TOLERANCE_MM:
            fail(f"tag application CSV tile size drift for {name}")
        if abs(
            _number(row.get("detection_edge_mm"), f"tag CSV {name} detection")
            - TAG_DETECTION_MM
        ) > COORD_TOLERANCE_MM:
            fail(f"tag application CSV detection edge drift for {name}")
        if abs(
            _number(row.get("expected_yaw_deg"), f"tag CSV {name} yaw")
        ) > 1e-6:
            fail(f"tag application CSV yaw drift for {name}")


def validate_documentation_sync() -> None:
    """Reject a manual or sync record generated from a different layout hash."""
    record = _load_json(DRAWINGS / "documentation_sync.json")
    layout_hash = sha256(CONFIG / "workcell_layout.json")
    manual_path = ROOT / "ASSEMBLY_MANUAL.md"
    if record.get("schema_version") != 2:
        fail("documentation sync schema version drift")
    if record.get("design_revision") != EXPECTED_REVISION:
        fail("documentation sync design revision drift")
    if record.get("expected_revision") != EXPECTED_REVISION:
        fail("documentation sync expected revision drift")
    if record.get("status") != "SYNCED":
        fail("documentation sync status is not SYNCED")
    if record.get("layout_sha256") != layout_hash:
        fail("documentation sync layout hash is stale")
    if record.get("manual_sha256") != normalized_text_sha256(manual_path):
        fail("documentation sync manual hash is stale")
    if record.get("apriltag_map_sha256") != sha256(
        FIDUCIALS / "apriltag_map.json"
    ):
        fail("documentation sync AprilTag map hash is stale")
    tag_map = _load_json(FIDUCIALS / "apriltag_map.json")
    if record.get("coordinate_source") != tag_map.get("coordinate_source"):
        fail("documentation sync coordinate source is stale")
    if record.get("tag_measurement_gate_status") != tag_map.get(
        "measurement", {}
    ).get("status"):
        fail("documentation sync tag measurement status is stale")
    expected_blocks = {
        "RC03_BOARD_FEATURES",
        "RC03_DIRECT_TAG_INSTALLATION",
        "RC03_RUNTIME_TAG_COORDINATES",
    }
    if set(record.get("controlled_blocks", [])) != expected_blocks:
        fail("documentation sync controlled block coverage drift")
    manual = manual_path.read_text(encoding="utf-8")
    for name in expected_blocks:
        if manual.count(f"<!-- BEGIN AUTO-GENERATED: {name} -->") != 1:
            fail(f"manual lacks one controlled {name} begin marker")
        if manual.count(f"<!-- END AUTO-GENERATED: {name} -->") != 1:
            fail(f"manual lacks one controlled {name} end marker")


def validate_digital_fit_report(layout: dict[str, Any]) -> int:
    """Validate the CAD generator's exact-solid nominal interference report."""
    path = CONFIG / "digital_fit_report.json"
    if not path.is_file():
        fail("missing config/digital_fit_report.json; regenerate CAD")
    report = _load_json(path)
    if report.get("schema_version") != 1:
        fail("digital-fit report schema version drift")
    if report.get("design_revision") != EXPECTED_REVISION:
        fail("digital-fit report revision drift")
    if report.get("status") != "PASS" or report.get("failures") != []:
        fail("digital-fit report contains an interference failure")

    expected_ids = {
        "keyboard_master_slave_no_solid_collision",
        "keyboard_nominal_envelope_clear_of_master_station",
        "keyboard_nominal_envelope_clear_of_slave_station",
        "keyboard_left_rear_clamp_clear_of_station",
        "keyboard_right_rear_clamp_clear_of_station",
        "KBL-CLAMP_m4_shank_clear_of_rear_clamp",
        "KBR-CLAMP_m4_shank_clear_of_rear_clamp",
        "phone_nominal_envelope_clear_of_service_station",
        "phone_nominal_envelope_clear_of_replaceable_rail",
        "phone_service_rail_clear_of_master_station",
        "tcp_target_cartridge_clear_of_master_station",
        "PT-HOLD-R1_m4_shank_clear_of_service_rail",
        "PT-HOLD-R2_m4_shank_clear_of_service_rail",
    }
    for feature in layout.get("board_features", []):
        feature_id = str(feature.get("id", ""))
        owner = str(feature.get("station", ""))
        label = (
            "nominal_pin"
            if feature.get("type") == "locator_pin_blind"
            else "m4_shank"
        )
        expected_ids.add(f"{feature_id}_{label}_clear_of_{owner}_solid")

    checks = report.get("checks")
    if not isinstance(checks, list):
        fail("digital-fit report checks must be a list")
    check_ids = [str(row.get("check_id", "")) for row in checks]
    if len(check_ids) != len(set(check_ids)):
        fail("digital-fit report contains duplicate check IDs")
    if set(check_ids) != expected_ids:
        fail(
            "digital-fit report coverage drift; "
            f"unexpected={set(check_ids)-expected_ids}, "
            f"missing={expected_ids-set(check_ids)}"
        )

    report_limit = _number(
        report.get("intersection_volume_limit_mm3"),
        "digital_fit_report.intersection_volume_limit_mm3",
    )
    if report_limit <= 0 or report_limit > 1e-6:
        fail("digital-fit intersection limit must be in (0, 1e-6] mm^3")
    for row in checks:
        check_id = str(row["check_id"])
        volume = _number(
            row.get("intersection_volume_mm3"),
            f"digital-fit {check_id}.intersection_volume_mm3",
        )
        limit = _number(row.get("limit_mm3"), f"digital-fit {check_id}.limit_mm3")
        if abs(limit - report_limit) > 1e-12:
            fail(f"digital-fit per-check limit drift: {check_id}")
        if volume < 0 or volume > limit or row.get("status") != "PASS":
            fail(f"digital-fit exact-solid collision: {check_id} ({volume} mm^3)")
    return len(checks)


def validate_robot_reach_screening(layout: dict[str, Any]) -> int:
    """Validate the explicitly non-release planar reach screening record."""
    path = CONFIG / "robot_reach_screening.json"
    if not path.is_file():
        fail("missing config/robot_reach_screening.json")
    report = _load_json(path)
    if report.get("schema_version") != 1:
        fail("robot reach screening schema version drift")
    if report.get("design_revision") != EXPECTED_REVISION:
        fail("robot reach screening revision drift")
    if report.get("status") != "SCREENING_ONLY_NOT_PROVEN":
        fail("robot reach screening must remain explicitly NOT_PROVEN before IK release")

    robot = report.get("robot", {})
    radius = _number(
        robot.get("published_nominal_radius_mm"),
        "robot_reach_screening.robot.published_nominal_radius_mm",
    )
    if radius != 560.0:
        fail("robot reach screening nominal radius drift")
    base_xy = _pair(
        report.get("screening_assumption", {}).get("board_frame_base_axis_xy_mm"),
        "robot_reach_screening.screening_assumption.board_frame_base_axis_xy_mm",
    )
    if not _close_pair(base_xy, (305.0, 457.0)):
        fail("robot reach screening assumption drift")

    keyboard = layout["devices"]["keyboard"]
    phone = layout["devices"]["phone"]
    phone_station = layout["stations"]["phone_tcp"]
    expected_points = {
        "board_front_left": (0.0, 0.0),
        "keyboard_front_left": _pair(
            keyboard["nominal_origin_xy"], "layout keyboard nominal origin"
        ),
        "phone_front_right": (
            _number(phone["nominal_origin_xy"][0], "phone origin X")
            + _number(phone["configured_size"][0], "phone width"),
            _number(phone["nominal_origin_xy"][1], "phone origin Y"),
        ),
        "phone_station_outer_front_right": (
            _number(phone_station["origin_xy"][0], "phone station origin X")
            + _number(phone_station["outer_envelope"][0], "phone station width"),
            _number(phone_station["origin_xy"][1], "phone station origin Y"),
        ),
        "tcp_target": _pair(
            layout["devices"]["tcp_target"]["center_xy"], "layout TCP target"
        ),
    }
    rows = report.get("planar_points")
    if not isinstance(rows, list):
        fail("robot reach screening planar_points must be a list")
    by_id = {str(row.get("point_id", "")): row for row in rows}
    if len(by_id) != len(rows) or set(by_id) != set(expected_points):
        fail("robot reach screening point coverage drift")
    for point_id, expected_xy in expected_points.items():
        row = by_id[point_id]
        xy = _pair(row.get("board_xy_mm"), f"reach point {point_id}.board_xy_mm")
        if not _close_pair(xy, expected_xy):
            fail(f"robot reach screening coordinate drift: {point_id}")
        calculated = math.hypot(xy[0] - base_xy[0], xy[1] - base_xy[1])
        recorded = _number(
            row.get("screened_radius_mm"), f"reach point {point_id}.screened_radius_mm"
        )
        margin = _number(
            row.get("nominal_radial_margin_mm"),
            f"reach point {point_id}.nominal_radial_margin_mm",
        )
        if abs(recorded - calculated) > 0.002 or abs(margin - (radius - calculated)) > 0.002:
            fail(f"robot reach screening calculation drift: {point_id}")

    blockers = report.get("release_blockers")
    if (
        not isinstance(blockers, list)
        or len(blockers) < 6
        or len(blockers) != len(set(blockers))
        or any(not isinstance(item, str) or not item.strip() for item in blockers)
    ):
        fail("robot reach screening must retain explicit, unique release blockers")
    return len(rows)


def validate_camera_architecture_decision(measurement: dict[str, Any]) -> int:
    """Validate the selected, unqualified static-overhead tripod architecture."""
    path = CONFIG / "camera_architecture_decision.json"
    if not path.is_file():
        fail("missing config/camera_architecture_decision.json")
    record = _load_json(path)
    if record.get("schema_version") != 2:
        fail("camera architecture decision schema version drift")
    if record.get("design_revision") != EXPECTED_REVISION:
        fail("camera architecture decision revision drift")
    if record.get("status") != "STATIC_OVERHEAD_TRIPOD_SELECTED_UNQUALIFIED":
        fail("camera architecture must select the unqualified static-overhead tripod")
    active = record.get("active_route", {})
    if (
        active.get("route_id") != "camera_overhead_primary"
        or active.get("support_type") != "independent_commercial_floor_tripod"
        or active.get("selected") is not True
        or active.get("qualified") is not False
        or active.get("physical_release_effect") != "NONE"
    ):
        fail("camera architecture active tripod route drift")
    if measurement.get("selected_routes", {}).get("camera_mast_optional") is not False:
        fail("measurement record must keep the superseded fixed-mast route unselected")
    fallback_gate = measurement.get("gates", {}).get(
        "fixed_camera_fallback_architecture_released"
    )
    if not isinstance(fallback_gate, dict) or fallback_gate.get("status") != "NOT_TESTED":
        fail("fixed-camera fallback engineering gate must remain NOT_TESTED on the held RC03 release")
    jobs = _load_json(CONFIG / "print_jobs.json").get("jobs", [])
    expected_fallback_jobs = {"03C3", "06", "07A", "07B"}
    gated_fallback_jobs = {
        job.get("job_id")
        for job in jobs
        if "fixed_camera_fallback_architecture_released"
        in job.get("prerequisites", [])
    }
    if gated_fallback_jobs != expected_fallback_jobs:
        fail("fixed-camera fallback engineering gate must interlock jobs 03C3, 06, 07A, and 07B")
    for job in jobs:
        if job.get("job_id") in expected_fallback_jobs and (
            job.get("selection") != "camera_mast_optional"
            or job.get("lifecycle") != "SUPERSEDED_DO_NOT_PRINT"
        ):
            fail(f"camera fallback job {job.get('job_id')} is not superseded")
    superseded = record.get("superseded_routes")
    if not isinstance(superseded, list) or not any(
        row.get("route_id") == "camera_mast_optional"
        and set(row.get("jobs", [])) == expected_fallback_jobs
        and row.get("treatment") == "SUPERSEDED_DO_NOT_PRINT"
        for row in superseded
    ):
        fail("camera architecture lacks the historical mast-job disposition")
    try:
        intake = validate_tripod_camera_intake()
    except (OSError, UnicodeError, json.JSONDecodeError, TripodIntakeError) as exc:
        fail(f"invalid tripod installation intake: {exc}")
    if (
        intake.get("schema") != "rocell.rc03.tripod_camera_installation_intake.v1"
        or intake.get("authority", {}).get("physical_release_effect") != "NONE"
        or any(
            intake.get("authority", {}).get(key) is not False
            for key in ("fabrication", "physical_installation", "robot_power", "motion", "contact")
        )
    ):
        fail("tripod installation intake must remain hash-bound and zero authority")
    return len(superseded)


def validate_hardware_candidate_registry(
    measurement: dict[str, Any],
) -> tuple[int, int]:
    """Validate traceable candidates without promoting them to release evidence."""
    path = CONFIG / "hardware_candidates.json"
    if not path.is_file():
        fail("missing config/hardware_candidates.json")
    registry = _load_json(path)
    if registry.get("schema_version") != 1:
        fail("hardware candidate registry schema version drift")
    if registry.get("document_type") != "rocell.hardware_candidate_registry":
        fail("hardware candidate registry document type drift")
    if registry.get("registry_revision") != EXPECTED_REVISION:
        fail("hardware candidate registry revision drift")
    if registry.get("status") != "CANDIDATE_UNVERIFIED":
        fail("hardware candidate registry must remain CANDIDATE_UNVERIFIED")
    if registry.get("release_authority") is not False:
        fail("hardware candidate registry cannot be release authority")
    if registry.get("route_selection_authority") is not False:
        fail("hardware candidate registry cannot select routes")

    candidates = registry.get("candidates")
    sources = registry.get("sources")
    if not isinstance(candidates, list) or len(candidates) < 22:
        fail("hardware candidate registry lacks required candidate coverage")
    if not isinstance(sources, list) or len(sources) < 30:
        fail("hardware candidate registry lacks required source coverage")
    source_by_id = {str(row.get("source_id", "")): row for row in sources}
    if len(source_by_id) != len(sources) or "" in source_by_id:
        fail("hardware candidate registry has missing or duplicate source IDs")
    candidate_ids: set[str] = set()
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id", ""))
        if not candidate_id or candidate_id in candidate_ids:
            fail("hardware candidate registry has missing or duplicate candidate IDs")
        candidate_ids.add(candidate_id)
        if candidate.get("status") != "CANDIDATE_UNVERIFIED":
            fail(f"hardware candidate {candidate_id} has a false release status")
        if not str(candidate.get("manufacturer", "")).strip() or not str(
            candidate.get("mpn", "")
        ).strip():
            fail(f"hardware candidate {candidate_id} lacks an exact identity")
        source_ids = candidate.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            fail(f"hardware candidate {candidate_id} lacks source traceability")
        if any(source_id not in source_by_id for source_id in source_ids):
            fail(f"hardware candidate {candidate_id} has an unresolved source")
        if not any(
            source_by_id[source_id].get("type") != "controlled_local"
            for source_id in source_ids
        ):
            fail(f"hardware candidate {candidate_id} lacks external identity evidence")

    expected_routes = {
        "phone_stylus_route": True,
        "keyboard_rod_route": True,
        "camera_mast_optional": False,
    }
    selected_routes = measurement.get("selected_routes", {})
    snapshot = registry.get("route_scope_snapshot", {})
    if (
        selected_routes != expected_routes
        or snapshot.get("selected_routes") != expected_routes
    ):
        fail("hardware candidate registry route snapshot drift")

    screening = registry.get("fastener_stack_screening", {})
    if (
        screening.get("cad_modified") is not True
        or screening.get("digital_correction_applied") is not True
        or screening.get("dependent_cad_stl_step_3mf_regenerated") is not True
        or screening.get("digital_exact_fit_result") != "PASS"
        or screening.get("physical_qualification_complete") is not False
    ):
        fail("hardware candidate registry TCP correction state drift")
    stacks = screening.get("stacks")
    if not isinstance(stacks, list):
        fail("hardware candidate registry fastener stacks must be a list")
    stack_by_id = {str(row.get("stack_id", "")): row for row in stacks}
    if len(stack_by_id) != len(stacks):
        fail("hardware candidate registry has duplicate stack IDs")
    current = stack_by_id.get("TCP-CURRENT-9P0MM-M4X25", {})
    historical = stack_by_id.get("TCP-HISTORICAL-10P5MM-M4X25", {})
    if (
        current.get("location_count") != 1
        or abs(
            _number(current.get("island_height_mm"), "TCP island height") - 10.5
        )
        > 0.001
        or abs(
            _number(current.get("washer_recess_depth_mm"), "TCP washer recess")
            - 1.5
        )
        > 0.001
        or abs(
            _number(current.get("effective_printed_seat_mm"), "TCP effective seat")
            - 9.0
        )
        > 0.001
        or _number(
            current.get("conservative_screening_engagement_mm"),
            "TCP conservative engagement",
        )
        < 5.0
    ):
        fail("hardware candidate registry current TCP stack drift")
    if (
        historical.get("location_count") != 0
        or historical.get("historical_only") is not True
    ):
        fail("hardware candidate registry historical TCP stack became current")

    camera = registry.get("camera_architecture_boundary", {})
    if (
        camera.get("status") != "SELECTED_UNQUALIFIED"
        or camera.get("primary_architecture") != "static_overhead_eye_to_hand"
        or camera.get("primary_route") != "camera_overhead_primary"
        or camera.get("release_effect") != "PHYSICAL_QUALIFICATION_HOLD"
        or camera.get("legacy_mast_route") != "camera_mast_optional"
        or camera.get("legacy_mast_selected") is not False
        or camera.get("legacy_mast_treatment") != "SUPERSEDED_DO_NOT_PRINT"
    ):
        fail("hardware candidate registry camera boundary drift")
    return len(candidates), len(sources)


def validate_fiducial_map(
    layout: dict[str, Any], measurement: dict[str, Any]
) -> None:
    tag_map = _load_json(FIDUCIALS / "apriltag_map.json")
    direct_container, layout_tags = _direct_tag_entries(layout)
    if tag_map.get("schema") != "rocell.apriltag_map.v2":
        fail("AprilTag map schema drift")
    if tag_map.get("schema_version") != 2:
        fail("AprilTag map schema version drift")
    if tag_map.get("design_revision") != EXPECTED_REVISION:
        fail("AprilTag map design revision drift")
    if tag_map.get("layout_sha256") != sha256(CONFIG / "workcell_layout.json"):
        fail("AprilTag map was generated from a different layout hash")
    if tag_map.get("family") != "tag36h11":
        fail("AprilTag family drift")
    if tag_map.get("mounting") != "direct_adhesive":
        fail("AprilTag map mounting drift")
    if tag_map.get("board_z_reference") != "finished sealed board top surface":
        fail("AprilTag map board-Z reference drift")
    if tag_map.get("paper_top_edge_faces") != "+Y / board rear for every tag":
        fail("AprilTag map orientation witness drift")
    map_tags = tag_map.get("tags")
    if not isinstance(map_tags, dict) or set(map_tags) != set(EXPECTED_TAGS):
        fail("apriltag_map.json must cover T0/T1/T2/T3/K0/P0 exactly")
    if abs(
        _number(tag_map.get("tile_size_mm"), "apriltag_map.tile_size_mm")
        - TAG_TILE_MM
    ) > COORD_TOLERANCE_MM:
        fail("AprilTag map tile size drift")
    if abs(
        _number(
            tag_map.get("detection_edge_mm"), "apriltag_map.detection_edge_mm"
        )
        - TAG_DETECTION_MM
    ) > COORD_TOLERANCE_MM:
        fail("AprilTag map detection-edge drift")
    if "frame_size_mm" in tag_map:
        fail("direct-adhesive AprilTag map must not contain frame_size_mm")

    gate = measurement.get("gates", {}).get("tag_plane_placement_measured")
    if not isinstance(gate, dict):
        fail("measurement_record.json lacks tag_plane_placement_measured")
    recorded_values = gate.get("recorded_values")
    if not isinstance(recorded_values, dict) or not isinstance(
        recorded_values.get("tags"), dict
    ):
        fail(
            "tag_plane_placement_measured.recorded_values must contain a tags "
            "mapping"
        )
    if recorded_values.get("board_z_reference") != (
        "finished sealed board top surface"
    ):
        fail("tag-plane measurement board-Z reference drift")
    measured = recorded_values["tags"]
    required_measurement_keys = {
        "center_x_mm",
        "center_y_mm",
        "plane_z_mm",
        "yaw_deg",
    }
    if set(measured) != set(EXPECTED_TAGS):
        fail("tag-plane measurement schema must contain all six named tags")
    for name, row in measured.items():
        if not isinstance(row, dict) or set(row) != required_measurement_keys:
            fail(f"tag-plane measurement fields drift for {name}")
    gate_pass = gate.get("status") == "PASS"
    coordinate_source = tag_map.get("coordinate_source")
    expected_source = "measured_installation" if gate_pass else "nominal_layout"
    if coordinate_source != expected_source:
        fail(
            f"AprilTag map coordinate_source={coordinate_source!r}, "
            f"expected {expected_source!r}"
        )
    map_measurement = tag_map.get("measurement")
    if not isinstance(map_measurement, dict):
        fail("AprilTag map lacks measurement provenance")
    if map_measurement.get("gate") != "tag_plane_placement_measured":
        fail("AprilTag map measurement gate identity drift")
    if map_measurement.get("status") != gate.get("status"):
        fail("AprilTag map measurement status is stale")
    expected_nominal_plane = direct_container.get("nominal_plane_z_mm")
    actual_nominal_plane = tag_map.get("direct_tag_plane_nominal_z_mm")
    if expected_nominal_plane is None:
        if actual_nominal_plane is not None:
            fail("AprilTag map asserts a nominal plane absent from the layout")
    elif abs(
        _number(actual_nominal_plane, "AprilTag map nominal plane")
        - _number(expected_nominal_plane, "layout nominal tag plane")
    ) > COORD_TOLERANCE_MM:
        fail("AprilTag map nominal plane drift")
    expected_ids = {name: row["id"] for name, row in EXPECTED_TAGS.items()}
    if tag_map.get("ids") != expected_ids:
        fail("AprilTag map ID lookup drift")

    for name, expected in EXPECTED_TAGS.items():
        map_tag = map_tags[name]
        if int(map_tag.get("id", -1)) != expected["id"]:
            fail(f"AprilTag map ID mismatch for {name}")
        if map_tag.get("role") != EXPECTED_TAG_ROLES[name]:
            fail(f"AprilTag map role mismatch for {name}")
        if map_tag.get("mounting") != "direct_adhesive":
            fail(f"AprilTag map {name} must state direct_adhesive mounting")
        if map_tag.get("coordinate_source") != coordinate_source:
            fail(f"AprilTag map per-tag coordinate source drift for {name}")
        origin = _pair(
            map_tag.get("tile_origin_xy_mm"),
            f"apriltag_map.{name}.tile_origin_xy_mm",
        )
        if not _close_pair(origin, expected["origin"]):
            fail(f"AprilTag map tile origin drift for {name}")
        nominal_center = _pair(
            map_tag.get("nominal_detection_center_xy_mm"),
            f"apriltag_map.{name}.nominal_detection_center_xy_mm",
        )
        if not _close_pair(nominal_center, expected["center"]):
            fail(f"AprilTag map nominal center drift for {name}")
        x, y, z = _xyz_allow_null_z(
            map_tag.get("detection_center_xyz_mm"),
            f"apriltag_map.{name}.detection_center_xyz_mm",
        )
        yaw = _number(
            map_tag.get("expected_yaw_deg_in_board_frame"),
            f"apriltag_map.{name}.yaw",
        )
        if gate_pass:
            row = measured[name]
            expected_xyz = (
                _number(
                    row.get("center_x_mm"), f"measured.{name}.center_x_mm"
                ),
                _number(
                    row.get("center_y_mm"), f"measured.{name}.center_y_mm"
                ),
                _number(row.get("plane_z_mm"), f"measured.{name}.plane_z_mm"),
            )
            expected_yaw = _number(
                row.get("yaw_deg"), f"measured.{name}.yaw_deg"
            )
            if (
                z is None
                or max(
                    abs(x - expected_xyz[0]),
                    abs(y - expected_xyz[1]),
                    abs(z - expected_xyz[2]),
                )
                > COORD_TOLERANCE_MM
                or abs(yaw - expected_yaw) > 1e-6
            ):
                fail(
                    f"AprilTag map does not match measured installation for {name}"
                )
        else:
            center = _pair(
                layout_tags[name].get(
                    "detection_center_xy",
                    layout_tags[name].get("detection_center_xy_mm"),
                ),
                f"layout direct tag {name}",
            )
            if not _close_pair((x, y), center) or z is not None:
                fail(
                    f"nominal AprilTag map must use layout XY and null Z for {name}"
                )
            if abs(yaw) > 1e-6:
                fail(f"nominal AprilTag yaw must be zero for {name}")


def validate_sidecar_job_metadata(sidecar: dict[str, Any], job: dict[str, Any]) -> None:
    """Require generated sidecar release metadata to match the job source exactly."""
    job_id = job["job_id"]
    expected = {
        "job_id": job_id,
        "design_revision": EXPECTED_REVISION,
        "plate_file": job["plate_file"],
        "stage": job["stage"],
        "selection": job["selection"],
        "purpose": job["purpose"],
        "prerequisites": job["prerequisites"],
        "process_profile_name": job["profile"],
    }
    for key, value in expected.items():
        if sidecar.get(key) != value:
            fail(f"sidecar {key} mismatch: {job_id}")


def expected_qidi_process_document(
    profile_name: str,
    profile: dict[str, Any],
    profiles: dict[str, Any],
) -> dict[str, Any]:
    """Reconstruct the exact importable QIDI process-preset artifact."""
    qidi = profile.get("qidi_studio")
    if not isinstance(qidi, dict):
        fail(f"used process profile lacks qidi_studio settings: {profile_name}")
    native_overrides = qidi.get("native_overrides")
    if not isinstance(native_overrides, dict) or not native_overrides:
        fail(f"used process profile lacks native QIDI overrides: {profile_name}")
    for key in ("base_process_preset", "import_name"):
        if not isinstance(qidi.get(key), str) or not qidi[key].strip():
            fail(f"used process profile lacks qidi_studio.{key}: {profile_name}")

    slicer = profiles.get("slicer_contract")
    if not isinstance(slicer, dict):
        fail("print_profiles.json lacks slicer_contract")
    version = slicer.get("verified_config_version")
    if not isinstance(version, str) or not version.strip():
        fail("slicer_contract.verified_config_version must be nonblank")

    document = {
        "from": "User",
        "inherits": qidi["base_process_preset"],
        "name": qidi["import_name"],
        "print_settings_id": qidi["import_name"],
        "version": version,
        "compatible_printers": [slicer["machine_preset"]],
    }
    document.update(native_overrides)
    return document


def validate_preset_artifacts(
    sidecar: dict[str, Any],
    job: dict[str, Any],
    profiles: dict[str, Any],
    plate_path: Path,
) -> tuple[Path, Path]:
    """Validate the complete human/QIDI preset contract for one print job."""
    job_id = job["job_id"]
    profile_name = job["profile"]
    profile = profiles["process_profiles"][profile_name]
    filament_name = profile.get("filament_preset")
    filament_presets = profiles.get("filament_presets")
    if not isinstance(filament_presets, dict):
        fail("print_profiles.json lacks filament_presets")
    if not isinstance(filament_name, str) or filament_name not in filament_presets:
        fail(f"used profile lacks a controlled filament preset: {profile_name}")
    filament = filament_presets[filament_name]

    contract = sidecar.get("preset_contract")
    if not isinstance(contract, dict):
        fail(f"sidecar lacks preset_contract: {job_id}")
    if contract.get("schema_version") != 1:
        fail(f"unsupported preset_contract schema: {job_id}")

    expected_human_path = plate_path.with_suffix(".PRINT_SETTINGS.md")
    expected_process_relative = (
        Path("slicer_profiles")
        / "QIDI_PLUS4"
        / f"{profile_name}.process.json"
    ).as_posix()
    expected_process_path = ROOT / Path(expected_process_relative)

    expected_assignments = [
        {
            "stl": filename,
            "quantity": quantity,
            "filament_preset": filament_name,
            "process_preset": profile_name,
        }
        for filename, quantity in sorted(job["parts"].items())
    ]
    expected_contract_values = {
        "slicer": profiles.get("slicer_contract"),
        "preset_data_status": profile.get("preset_data_status"),
        "filament_preset_name": filament_name,
        "filament_preset": filament,
        "process_preset_name": profile_name,
        "process_preset": profile,
        "human_settings_file": expected_human_path.name,
        "qidi_process_profile_file": expected_process_relative,
        "filament_preset_sha256": canonical_json_sha256(filament),
        "unresolved_fields": filament.get("unresolved_fields", []),
        "part_assignments": expected_assignments,
    }
    for key, expected in expected_contract_values.items():
        if contract.get(key) != expected:
            fail(f"preset_contract {key} mismatch: {job_id}")

    if not expected_human_path.is_file():
        fail(f"missing human print-settings artifact: {job_id}")
    if not expected_process_path.is_file():
        fail(f"missing QIDI process-profile artifact: {job_id}")

    human_hash = sha256(expected_human_path)
    process_file_hash = sha256(expected_process_path)
    expected_resolved_preset = {
        "design_revision": EXPECTED_REVISION,
        "slicer": profiles["slicer_contract"],
        "printer": profiles["printer"],
        "filament_preset_name": filament_name,
        "filament_preset": filament,
        "process_preset_name": profile_name,
        "process_preset": profile,
        "qidi_process_profile_sha256": process_file_hash,
    }
    resolved_hash = canonical_json_sha256(expected_resolved_preset)
    expected_hashes = {
        "human_settings_sha256": human_hash,
        "qidi_process_profile_sha256": process_file_hash,
        "resolved_preset_sha256": resolved_hash,
    }
    for key, expected in expected_hashes.items():
        if contract.get(key) != expected:
            fail(f"preset_contract {key} mismatch: {job_id}")
        if sidecar.get(key) != expected:
            fail(f"sidecar {key} mismatch: {job_id}")
    if sidecar.get("filament_preset_sha256") != canonical_json_sha256(filament):
        fail(f"sidecar filament-preset hash mismatch: {job_id}")
    for key in ("human_settings_file", "qidi_process_profile_file"):
        if sidecar.get(key) != contract.get(key):
            fail(f"sidecar/preset_contract {key} mismatch: {job_id}")

    process_document = _load_json(expected_process_path)
    if process_document != expected_qidi_process_document(
        profile_name, profile, profiles
    ):
        fail(f"QIDI process-profile content mismatch: {profile_name}")

    human_text = expected_human_path.read_text(encoding="utf-8")
    qidi = profile["qidi_studio"]
    required_human_lines = (
        f"# Job {job_id} — exact print settings",
        f"- Plate: `{plate_path.name}`",
        f"- Verified QIDI Studio configuration: "
        f"`{profiles['slicer_contract']['verified_config_version']}`",
        f"- Printer: `{profiles['slicer_contract']['machine_preset']}`",
        f"- Build surface: `{profiles['slicer_contract']['build_surface']}`",
        f"- Filament preset ID: `{filament_name}`",
        f"- Process profile ID: `{profile_name}`",
        f"- Imported process name: `{qidi['import_name']}`",
        f"- Import process file: `../{expected_process_relative}`",
        f"- Plate SHA-256: `{sidecar['plate_sha256']}`",
        f"- Process profile SHA-256: `{sidecar['process_profile_sha256']}`",
        f"- Filament preset SHA-256: `{canonical_json_sha256(filament)}`",
        f"- Resolved preset SHA-256: `{resolved_hash}`",
        f"- QIDI process file SHA-256: `{process_file_hash}`",
    )
    for required_line in required_human_lines:
        if required_line not in human_text:
            fail(f"human print-settings identity/hash mismatch: {job_id}")

    return expected_human_path, expected_process_path


def validate_part_and_plate_package(
    jobs_doc: dict[str, Any],
    profiles: dict[str, Any],
    parameters: dict[str, Any],
    layout_summary: dict[str, Any],
) -> tuple[int, int, list[dict[str, Any]], list[Path]]:
    jobs = jobs_doc["jobs"]
    if len({job["job_id"] for job in jobs}) != len(jobs):
        fail("duplicate job ID")
    if len({job["plate_file"] for job in jobs}) != len(jobs):
        fail("duplicate plate filename")

    configured_parts = {filename for job in jobs for filename in job["parts"]}
    disk_parts = {path.name for path in STL.glob("*.stl")} - {
        "BOARD_REFERENCE_DO_NOT_PRINT.stl"
    }
    if configured_parts != disk_parts:
        fail(
            f"printable STL coverage mismatch; missing={disk_parts-configured_parts}, "
            f"extra={configured_parts-disk_parts}"
        )
    obsolete_frames = sorted(
        name for name in configured_parts if name.startswith("tag_frame_")
    )
    if obsolete_frames:
        fail(
            f"RC03 direct-tag release still contains obsolete tag frames: "
            f"{obsolete_frames}"
        )
    station_parts = {
        _station_part_filename(row, f"stations.{name}")
        for name, row in layout_summary["stations"].items()
    }
    if not station_parts.issubset(configured_parts):
        fail(
            "station parts are not covered by controlled jobs: "
            f"{station_parts-configured_parts}"
        )

    with (ROOT / "PART_VALIDATION.csv").open(encoding="utf-8") as handle:
        validation_rows = list(csv.DictReader(handle))
    validation_by_stl = {
        Path(row["stl"]).name: row for row in validation_rows
    }
    if len(validation_by_stl) != len(validation_rows):
        fail("PART_VALIDATION.csv contains duplicate STL rows")
    if set(validation_by_stl) != configured_parts:
        fail("PART_VALIDATION.csv does not cover every printable STL exactly")
    expected_step_files = {
        Path(row["step"]).name for row in validation_rows
    } | {
        "board_610x457x18_RC03.step",
        "RoCell_RC03_INT_R1_full_assembly.step",
    }
    disk_step_files = {
        path.name for path in (ROOT / "cad" / "step").glob("*.step")
    }
    if disk_step_files != expected_step_files:
        fail(
            "STEP package coverage mismatch; "
            f"missing={expected_step_files-disk_step_files}, "
            f"extra={disk_step_files-expected_step_files}"
        )

    mesh_count = 0
    mesh_geometry: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for filename in sorted(configured_parts):
        mesh = trimesh.load_mesh(STL / filename, force="mesh")
        components = len(mesh.split(only_watertight=False))
        if (
            not mesh.is_watertight
            or not mesh.is_winding_consistent
            or components != 1
            or mesh.volume <= 0
        ):
            fail(
                f"invalid STL {filename}: watertight={mesh.is_watertight}, "
                f"winding={mesh.is_winding_consistent}, components={components}, "
                f"volume={mesh.volume}"
            )
        if np.any(
            mesh.extents
            > np.array(
                [
                    parameters["printer_safe_x"],
                    parameters["printer_safe_y"],
                    parameters["printer_safe_z"],
                ]
            )
            + 1e-6
        ):
            fail(f"STL exceeds protected Plus4 envelope: {filename} {mesh.extents}")
        row = validation_by_stl[filename]
        if row.get("part") != Path(filename).stem:
            fail(f"PART_VALIDATION.csv part identity drift: {filename}")
        step_path = ROOT / str(row.get("step", ""))
        if not step_path.is_file() or step_path.suffix.lower() != ".step":
            fail(f"PART_VALIDATION.csv STEP reference is missing: {filename}")
        expected_flags = {
            "watertight",
            "winding_consistent",
            "single_body",
            "positive_volume",
            "fits_plus4_nominal_305x305x280",
            "fits_plus4_protected_envelope",
        }
        if any(str(row.get(key, "")).lower() != "true" for key in expected_flags):
            fail(f"PART_VALIDATION.csv acceptance flag drift: {filename}")
        if int(row.get("connected_components", 0)) != 1:
            fail(f"PART_VALIDATION.csv component count drift: {filename}")
        recorded_extents = np.array(
            [
                _number(row.get(key), f"PART_VALIDATION {filename}.{key}")
                for key in ("extent_x_mm", "extent_y_mm", "extent_z_mm")
            ]
        )
        if not np.allclose(recorded_extents, mesh.extents, atol=0.05):
            fail(f"PART_VALIDATION.csv mesh extents drift: {filename}")
        mesh_geometry[filename] = (
            np.asarray(mesh.bounds, dtype=float),
            np.asarray(mesh.extents, dtype=float),
        )
        mesh_count += 1

    for station_name, station in layout_summary["stations"].items():
        filename = _station_part_filename(station, f"stations.{station_name}")
        bounds, extents = mesh_geometry[filename]
        expected_xy = np.asarray(
            _pair(
                station.get("outer_envelope"),
                f"stations.{station_name}.outer_envelope",
            )
        )
        if not np.allclose(extents[:2], expected_xy, atol=0.05):
            fail(
                f"station mesh XY envelope disagrees with layout: {station_name}"
            )
        if not np.allclose(bounds[0], np.zeros(3), atol=0.01):
            fail(f"station mesh {station_name} must export with base at local XYZ zero")

    expected_profile_gate = {
        "abs_rapido_tray_structural_0p4": "abs_rapido_tray_profile_calibrated",
        "abs_rapido_cradle_0p4": "abs_rapido_cradle_profile_calibrated",
        "abs_rapido_general_0p4": "abs_rapido_general_profile_calibrated",
        "abs_rapido_precision_0p4": "abs_rapido_precision_profile_calibrated",
        "abs_rapido_calibration_0p4": "abs_rapido_calibration_profile_calibrated",
        "petg_general_0p4": "petg_general_profile_calibrated",
        "petg_adapter_0p4": "petg_adapter_profile_calibrated",
        "tpu95a_0p4": "tpu_profile_calibrated",
        "asa_structural_0p4": "asa_profile_calibrated",
    }
    expected_plate_files: set[str] = set()
    expected_human_settings: set[Path] = set()
    expected_process_profiles: set[Path] = set()
    total_objects = 0
    plate_summary: list[dict[str, Any]] = []
    hash_inputs: list[Path] = []
    for job in jobs:
        job_id = job["job_id"]
        profile_name = job["profile"]
        if profile_name not in profiles["process_profiles"]:
            fail(f"unknown profile in {job_id}: {profile_name}")
        if profile_name not in expected_profile_gate:
            fail(f"profile {profile_name} lacks an explicit release gate mapping")
        prerequisites = set(job["prerequisites"])
        required_common = {
            "plus4_machine_confirmed",
            "plus4_protected_envelope_verified",
            "nozzle_0p4_confirmed",
            expected_profile_gate[profile_name],
        }
        if not required_common.issubset(prerequisites):
            fail(
                f"{job_id} lacks process qualification: "
                f"{required_common-prerequisites}"
            )
        if (
            job["stage"] != "diagnostic"
            and "qidi_studio_roundtrip_confirmed" not in prerequisites
        ):
            fail(
                f"non-diagnostic job lacks native QIDI Studio round-trip gate: "
                f"{job_id}"
            )

        plate_path = PLATES / job["plate_file"]
        sidecar_path = plate_path.with_suffix(".print.json")
        expected_plate_files.add(plate_path.name)
        if not plate_path.exists() or not sidecar_path.exists():
            fail(f"missing plate or sidecar: {job_id}")
        sidecar = _load_json(sidecar_path)
        if (
            sidecar.get("job_id") != job_id
            or sidecar.get("design_revision") != EXPECTED_REVISION
        ):
            fail(f"sidecar identity/revision mismatch: {job_id}")
        if sidecar.get("parts") != job["parts"]:
            fail(f"sidecar manifest/profile mismatch: {job_id}")
        if sidecar.get("printer") != profiles["printer"]:
            fail(f"sidecar printer contract mismatch: {job_id}")
        if sidecar.get("process_profile") != profiles["process_profiles"][profile_name]:
            fail(f"sidecar embedded process-profile mismatch: {job_id}")
        validate_sidecar_job_metadata(sidecar, job)
        if set(sidecar.get("source_stl_sha256", {})) != set(job["parts"]):
            fail(f"sidecar source hash coverage mismatch: {job_id}")
        if sidecar.get("plate_sha256") != sha256(plate_path):
            fail(f"plate hash mismatch: {job_id}")
        for filename, digest in sidecar["source_stl_sha256"].items():
            if digest != sha256(STL / filename):
                fail(f"source STL hash mismatch: {job_id}/{filename}")
        profile_payload = json.dumps(
            profiles["process_profiles"][profile_name],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if sidecar.get("process_profile_sha256") != hashlib.sha256(
            profile_payload
        ).hexdigest():
            fail(f"process-profile hash mismatch: {job_id}")
        human_settings_path, process_profile_path = validate_preset_artifacts(
            sidecar, job, profiles, plate_path
        )
        expected_human_settings.add(human_settings_path)
        expected_process_profiles.add(process_profile_path)

        scene = trimesh.load(plate_path, force="scene")
        if scene.is_empty or len(scene.geometry) != sum(job["parts"].values()):
            fail(f"3MF build-item count/read-back failure: {job_id}")
        bounds = np.asarray(scene.bounds)
        extents = bounds[1] - bounds[0]
        if np.any(
            extents > np.array(profiles["printer"]["safe_plate_envelope_mm"]) + 1e-6
        ):
            fail(f"plate exceeds protected envelope: {job_id}")
        center = (bounds[0, :2] + bounds[1, :2]) / 2
        if not np.allclose(
            center,
            np.array(profiles["printer"]["nominal_build_volume_mm"][:2]) / 2,
            atol=0.01,
        ):
            fail(f"plate is not centered on nominal bed: {job_id} center={center}")
        sidecar_extent = np.asarray(sidecar.get("plate_envelope_mm"), dtype=float)
        if sidecar_extent.shape != (3,) or not np.allclose(
            sidecar_extent, np.round(extents, 1), atol=0.05
        ):
            fail(f"sidecar plate envelope mismatch: {job_id}")
        total_objects += len(scene.geometry)
        plate_summary.append(
            {
                "job_id": job_id,
                "plate_file": plate_path.name,
                "objects": len(scene.geometry),
                "extent": [round(float(value), 1) for value in extents],
                "profile": profile_name,
            }
        )
        hash_inputs.extend(
            (plate_path, sidecar_path, human_settings_path, process_profile_path)
        )

    disk_plates = {path.name for path in PLATES.glob("*.3mf")}
    if disk_plates != expected_plate_files:
        fail(
            f"plate directory drift; unexpected={disk_plates-expected_plate_files}, "
            f"missing={expected_plate_files-disk_plates}"
        )
    disk_human_settings = set(PLATES.glob("*.PRINT_SETTINGS.md"))
    if disk_human_settings != expected_human_settings:
        fail(
            "human print-settings coverage drift; "
            f"unexpected={disk_human_settings-expected_human_settings}, "
            f"missing={expected_human_settings-disk_human_settings}"
        )
    process_profile_dir = ROOT / "slicer_profiles" / "QIDI_PLUS4"
    disk_process_profiles = set(process_profile_dir.glob("*.process.json"))
    if disk_process_profiles != expected_process_profiles:
        fail(
            "QIDI process-profile coverage drift; "
            f"unexpected={disk_process_profiles-expected_process_profiles}, "
            f"missing={expected_process_profiles-disk_process_profiles}"
        )
    with (ROOT / "PLATE_MANIFEST.csv").open(encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    manifest_by_id = {row["job_id"]: row for row in manifest}
    jobs_by_id = {job["job_id"]: job for job in jobs}
    if set(manifest_by_id) != set(jobs_by_id) or len(manifest_by_id) != len(
        manifest
    ):
        fail("PLATE_MANIFEST.csv job coverage/uniqueness mismatch")
    summary_by_id = {row["job_id"]: row for row in plate_summary}
    for job_id, job in jobs_by_id.items():
        row = manifest_by_id[job_id]
        summary = summary_by_id[job_id]
        expected_values = {
            "plate_file": job["plate_file"],
            "stage": job["stage"],
            "selection": job["selection"],
            "material": profiles["process_profiles"][job["profile"]]["material"],
            "process_profile": job["profile"],
            "nozzle_mm": str(profiles["process_profiles"][job["profile"]]["nozzle_mm"]),
            "layer_mm": str(profiles["process_profiles"][job["profile"]]["layer_height_mm"]),
            "purpose": job["purpose"],
            "prerequisites": ";".join(job["prerequisites"]),
            "objects": str(sum(job["parts"].values())),
        }
        for key, expected in expected_values.items():
            if row.get(key) != expected:
                fail(
                    f"PLATE_MANIFEST.csv {job_id}.{key}={row.get(key)!r}, "
                    f"expected {expected!r}"
                )
        for axis, expected in zip(
            ("extent_x_mm", "extent_y_mm", "extent_z_mm"), summary["extent"]
        ):
            if abs(
                _number(row.get(axis), f"manifest {job_id}.{axis}") - expected
            ) > 0.05:
                fail(f"PLATE_MANIFEST.csv extent mismatch: {job_id}/{axis}")
    return mesh_count, total_objects, plate_summary, hash_inputs


def main() -> None:
    jobs_doc = _load_json(CONFIG / "print_jobs.json")
    profiles = _load_json(CONFIG / "print_profiles.json")
    parameters = _load_json(CONFIG / "parameters.json")
    layout = _load_json(CONFIG / "workcell_layout.json")
    measurement = _load_json(CONFIG / "measurement_record.json")
    build_record = _load_json(CONFIG / "job_build_record.json")

    validate_revision_consistency(jobs_doc, layout, measurement, build_record)
    validate_gate_traceability(jobs_doc, measurement, build_record)
    bom_lines = validate_bom()
    fastener_rows = validate_fastener_map()
    layout_summary = validate_layout(layout, parameters)
    validate_board_coordinate_csv(layout_summary)
    validate_tag_coordinate_csv(layout_summary)
    validate_fiducial_map(layout, measurement)
    validate_documentation_sync()
    digital_fit_checks = validate_digital_fit_report(layout)
    reach_screening_points = validate_robot_reach_screening(layout)
    camera_alignment_requirements = validate_camera_architecture_decision(measurement)
    hardware_candidate_count, hardware_source_count = (
        validate_hardware_candidate_registry(measurement)
    )
    mesh_count, total_objects, plate_summary, plate_hash_inputs = (
        validate_part_and_plate_package(
            jobs_doc, profiles, parameters, layout_summary
        )
    )

    step_paths = sorted((ROOT / "cad" / "step").glob("*.step"))
    drawing_paths = sorted(path for path in DRAWINGS.glob("*") if path.is_file())
    fiducial_paths = sorted(path for path in FIDUCIALS.glob("*") if path.is_file())
    generator_paths = [
        ROOT / "scripts" / name
        for name in (
            "generate_cad.py",
            "build_print_plates.py",
            "generate_drawings.py",
            "generate_fiducials.py",
            "sync_documentation.py",
            "validate_print_readiness.py",
            "generate_build_tracker.py",
            "validate_release_package.py",
        )
    ]
    controlled_inputs = [
        CONFIG / "parameters.json",
        CONFIG / "print_jobs.json",
        CONFIG / "print_profiles.json",
        CONFIG / "workcell_layout.json",
        CONFIG / "measurement_record.json",
        CONFIG / "job_build_record.json",
        CONFIG / "digital_fit_report.json",
        CONFIG / "robot_reach_screening.json",
        CONFIG / "camera_architecture_decision.json",
        CONFIG / "hardware_candidates.json",
        DRAWINGS / "board_hole_coordinates.csv",
        DRAWINGS / "tag_application_coordinates.csv",
        DRAWINGS / "documentation_sync.json",
        FIDUCIALS / "apriltag_map.json",
        ROOT / "ASSEMBLY_MANUAL.md",
        ROOT / "PART_VALIDATION.csv",
        ROOT / "PLATE_MANIFEST.csv",
        ROOT / "BOM.csv",
        ROOT / "FASTENER_MAP.csv",
        *sorted(STL.glob("*.stl")),
        *step_paths,
        *drawing_paths,
        *fiducial_paths,
        *generator_paths,
        *plate_hash_inputs,
    ]
    release_hash = aggregate_sha256(controlled_inputs)
    if re.fullmatch(r"[0-9a-f]{64}", release_hash) is None:
        fail("internal error: invalid RC03 aggregate release hash")

    layout_hash = sha256(CONFIG / "workcell_layout.json")
    cad_generator_hash = sha256(ROOT / "scripts" / "generate_cad.py")
    report = {
        "design_revision": EXPECTED_REVISION,
        "status": "PASS",
        "layout_sha256": layout_hash,
        "cad_generator_sha256": cad_generator_hash,
        "release_input_sha256": release_hash,
        "printable_stls": mesh_count,
        "step_models": len(step_paths),
        "configured_jobs": len(jobs_doc["jobs"]),
        "bom_lines": bom_lines,
        "fastener_map_rows": fastener_rows,
        "plate_objects": total_objects,
        "named_board_features": len(layout_summary["features"]),
        "nominal_exact_solid_fit_checks": digital_fit_checks,
        "robot_planar_reach_screening_points": reach_screening_points,
        "camera_architecture_alignment_requirements": camera_alignment_requirements,
        "traceable_unverified_hardware_candidates": hardware_candidate_count,
        "hardware_candidate_sources": hardware_source_count,
        "named_board_feature_types": layout_summary["feature_type_counts"],
        "direct_tags": len(layout_summary["direct_tags"]["tags"]),
        "all_stls_watertight_single_body": True,
        "all_parts_and_plates_fit_protected_plus4_envelope": True,
        "all_3mf_files_roundtrip_in_independent_reader": True,
        "all_sidecar_source_profile_and_plate_hashes_match": True,
        "all_human_print_settings_files_match_sidecar_hashes": True,
        "all_qidi_process_profiles_match_config_and_sidecar_hashes": True,
        "all_resolved_slicer_preset_contracts_match": True,
        "all_non_diagnostic_jobs_require_native_qidi_roundtrip": True,
        "rc03_named_layout_and_direct_tag_regressions_pass": True,
        "board_coordinate_csv_matches_named_features": True,
        "tag_coordinate_csv_matches_layout_hash": True,
        "fiducial_map_matches_layout_or_measured_installation": True,
        "manual_matches_layout_hash": True,
        "bom_critical_quantities_match_rc03_architecture": True,
        "fastener_map_covers_all_nine_board_interfaces": True,
        "nominal_exact_solid_fit_checks_pass": True,
        "robot_reach_screening_honestly_not_proven": True,
        "arm_camera_intent_conflict_honestly_held": True,
        "hardware_candidates_are_traceable_but_not_release_authority": True,
    }
    (ROOT / "RELEASE_VALIDATION.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# CAD and release-package verification",
        "",
        f"**Revision `{EXPECTED_REVISION}` — automated status: PASS**",
        "",
        f"**Controlled release-input SHA-256:** `{release_hash}`",
        "",
        f"**Authoritative layout SHA-256:** `{layout_hash}`",
        "",
        f"**CAD generator SHA-256:** `{cad_generator_hash}`",
        "",
        "The release validator independently checks the RC03 master/slave cassette architecture, four blind locator features, nine M4 retention features, nominal exact-solid fit, six direct-applied tags, board-coordinate outputs, printable meshes, QIDI plate manifests, sidecars, per-job human settings, importable QIDI process profiles, resolved preset contracts, source/profile/plate hashes, and protected Plus4 envelopes.",
        "",
        f"- Printable STL models: **{mesh_count}**",
        f"- STEP models/assemblies: **{len(step_paths)}**",
        f"- Controlled print jobs: **{len(jobs_doc['jobs'])}**",
        f"- Controlled BOM lines: **{bom_lines}**",
        f"- Named M4 fastener stacks: **{fastener_rows}**",
        f"- Nominal exact-solid fit checks: **{digital_fit_checks}**",
        f"- Robot planar reach screening points: **{reach_screening_points}** (screening only; IK/collision proof remains blocked)",
        f"- Arm-camera alignment requirements: **{camera_alignment_requirements}** (engineering hold; exact specification absent)",
        f"- Traceable hardware candidates: **{hardware_candidate_count}** across **{hardware_source_count}** resolved sources (all unverified)",
        f"- Total placed 3MF objects: **{total_objects}**",
        "- Named board features: **13** (4 locator + 9 retention)",
        "- Direct-applied runtime tags: **6**",
        "",
        "## QIDI Plus4 plate read-back",
        "",
        "| Job | Plate | Objects | Envelope mm | Profile |",
        "|---|---|---:|---:|---|",
    ]
    for row in plate_summary:
        lines.append(
            f"| {row['job_id']} | `{row['plate_file']}` | {row['objects']} | "
            f"{' x '.join(str(value) for value in row['extent'])} | "
            f"`{row['profile']}` |"
        )
    lines += [
        "",
        "## Release boundary",
        "",
        "This PASS proves package consistency, not physical fit. Printing remains locked by PRINT_READINESS until the exact board, devices, hardware, filament lots, locator coupons, QIDI Studio projects, first articles, tag placement, flatness, and ten-cycle repeatability gates are measured and recorded.",
        "",
        "Re-run `python scripts/validate_release_package.py` after every CAD, layout, profile, job, plate, drawing, fiducial-map, or evidence-schema change.",
    ]
    (ROOT / "CAD_VERIFICATION.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
