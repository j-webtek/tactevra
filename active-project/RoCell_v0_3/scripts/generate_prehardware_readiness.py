#!/usr/bin/env python3
"""Generate an honest digital-feasibility report without granting physical PASSes."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import validate_print_readiness as readiness


ROOT = Path(__file__).resolve().parents[1]
JSON_OUTPUT = ROOT / "PREHARDWARE_READINESS.json"
MARKDOWN_OUTPUT = ROOT / "PREHARDWARE_READINESS.md"
FASTENER_REQUIRED_FIELDS = (
    "selected_length_mm",
    "anchor_type",
    "anchor_manufacturer_part",
    "bore_mode",
    "final_board_bore_mm",
    "bore_depth_mm_or_through",
    "install_face",
    "pilot_diameter_mm",
    "qualification_reference",
)


def read_json(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def read_csv(relative: str) -> list[dict[str, str]]:
    with (ROOT / relative).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "pass"}


def check(check_id: str, status: str, finding: str, action: str = "") -> dict[str, str]:
    return {
        "check_id": check_id,
        "status": status,
        "finding": finding,
        "required_action": action,
    }


def build_report() -> dict[str, Any]:
    parameters = read_json("config/parameters.json")
    layout = read_json("config/workcell_layout.json")
    jobs = read_json("config/print_jobs.json")
    measurement = read_json("config/measurement_record.json")
    parts = read_csv("PART_VALIDATION.csv")
    plates = read_csv("PLATE_MANIFEST.csv")
    fasteners = read_csv("FASTENER_MAP.csv")
    digital_fit = read_json("config/digital_fit_report.json")
    reach_screening = read_json("config/robot_reach_screening.json")
    camera_architecture = read_json("config/camera_architecture_decision.json")
    tripod_intake = read_json("config/tripod_camera_installation_intake_v1.json")

    checks: list[dict[str, str]] = []
    revisions = {
        jobs.get("design_revision"),
        measurement.get("design_revision"),
        layout.get("release_revision"),
    }
    revision_ok = len(revisions) == 1 and None not in revisions
    checks.append(
        check(
            "revision_consistency",
            "DIGITAL_PASS" if revision_ok else "DIGITAL_FAIL",
            f"Controlled revisions found: {sorted(str(value) for value in revisions)}.",
            "Regenerate from one controlled revision." if not revision_ok else "",
        )
    )

    protected = tuple(float(parameters[key]) for key in (
        "printer_safe_x", "printer_safe_y", "printer_safe_z"
    ))
    expected_protected = tuple(float(value) for value in layout["printer"]["protected_envelope"])
    profile_protected = tuple(
        float(value) for value in read_json("config/print_profiles.json")["printer"]["safe_plate_envelope_mm"]
    )
    envelope_sources_match = protected == expected_protected == profile_protected
    checks.append(
        check(
            "protected_envelope_sources",
            "DIGITAL_PASS" if envelope_sources_match else "DIGITAL_FAIL",
            f"CAD/layout/profile provisional envelope values are {protected}, {expected_protected}, and {profile_protected} mm.",
            "Make all protected-envelope sources identical." if not envelope_sources_match else "",
        )
    )

    protected_field = "fits_plus4_protected_envelope"
    expected_printable_parts = {
        part_name.removesuffix(".stl")
        for job in jobs["jobs"]
        for part_name in job["parts"]
    }
    actual_printable_parts = {row.get("part", "") for row in parts}
    part_failures = [
        row.get("part", "UNKNOWN")
        for row in parts
        if not all(
            truthy(row.get(field))
            for field in (
                "watertight",
                "winding_consistent",
                "single_body",
                "positive_volume",
                protected_field,
            )
        )
    ]
    checks.append(
        check(
            "printable_mesh_geometry",
            "DIGITAL_PASS"
            if not part_failures and actual_printable_parts == expected_printable_parts
            else "DIGITAL_FAIL",
            f"{len(parts)} printable STL rows checked against {len(expected_printable_parts)} configured unique parts; failures: {part_failures or 'none'}.",
            (
                "Repair/regenerate failed STLs and reconcile configured versus validated part names."
                if part_failures or actual_printable_parts != expected_printable_parts
                else ""
            ),
        )
    )

    part_axis_maxima: dict[str, dict[str, Any]] = {}
    plate_axis_maxima: dict[str, dict[str, Any]] = {}
    for axis_index, axis in enumerate(("x", "y", "z")):
        part_row = max(parts, key=lambda row: float(row[f"extent_{axis}_mm"]))
        plate_row = max(plates, key=lambda row: float(row[f"extent_{axis}_mm"]))
        part_axis_maxima[axis] = {
            "part": part_row["part"],
            "extent_mm": float(part_row[f"extent_{axis}_mm"]),
            "protected_margin_mm": round(
                protected[axis_index] - float(part_row[f"extent_{axis}_mm"]), 3
            ),
        }
        plate_axis_maxima[axis] = {
            "job_id": plate_row["job_id"],
            "extent_mm": float(plate_row[f"extent_{axis}_mm"]),
            "protected_margin_mm": round(
                protected[axis_index] - float(plate_row[f"extent_{axis}_mm"]), 3
            ),
        }
    plate_failures = [
        row["job_id"]
        for row in plates
        if any(
            float(row[f"extent_{axis}_mm"]) > protected[index] + 1e-9
            for index, axis in enumerate(("x", "y", "z"))
        )
    ]
    checks.append(
        check(
            "configured_plate_envelopes",
            "DIGITAL_PASS" if not plate_failures and len(plates) == len(jobs["jobs"]) else "DIGITAL_FAIL",
            f"{len(plates)} configured plate envelopes checked against {protected} mm; failures: {plate_failures or 'none'}.",
            "Repack any failed plate without scaling its objects." if plate_failures else "",
        )
    )

    all_jobs_have_machine_gate = all(
        "plus4_protected_envelope_verified" in job.get("prerequisites", [])
        for job in jobs["jobs"]
    )
    checks.append(
        check(
            "physical_printer_envelope_interlock",
            "DIGITAL_PASS" if all_jobs_have_machine_gate else "DIGITAL_FAIL",
            "Every print job requires the actual-machine protected-envelope gate."
            if all_jobs_have_machine_gate
            else "One or more jobs can bypass the actual-machine protected-envelope gate.",
            "Add plus4_protected_envelope_verified to every job prerequisite."
            if not all_jobs_have_machine_gate
            else "",
        )
    )

    stations = layout["stations"]
    board = layout["board"]
    station_edge_clearances: dict[str, dict[str, float]] = {}
    station_bounds_ok = True
    for name, station in stations.items():
        x, y = (float(value) for value in station["origin_xy"])
        width, depth = (float(value) for value in station["outer_envelope"])
        clearances = {
            "left_mm": x,
            "front_mm": y,
            "right_mm": float(board["width"]) - x - width,
            "rear_mm": float(board["depth"]) - y - depth,
        }
        station_edge_clearances[name] = {
            key: round(value, 3) for key, value in clearances.items()
        }
        station_bounds_ok &= min(clearances.values()) >= -1e-9
    checks.append(
        check(
            "station_board_bounds",
            "DIGITAL_PASS" if station_bounds_ok else "DIGITAL_FAIL",
            f"All three station envelopes remain on the 610 x 457 mm board: {station_edge_clearances}.",
            "Move or resize any station that leaves the board." if not station_bounds_ok else "",
        )
    )

    digital_fit_ok = (
        digital_fit.get("design_revision") == measurement["design_revision"]
        and digital_fit.get("status") == "PASS"
        and digital_fit.get("checks")
        and not digital_fit.get("failures")
    )
    checks.append(
        check(
            "nominal_exact_solid_fit",
            "DIGITAL_PASS" if digital_fit_ok else "DIGITAL_FAIL",
            f"Exact-solid nominal fit report contains {len(digital_fit.get('checks', []))} checks and status {digital_fit.get('status')}.",
            "Regenerate CAD and resolve every device, seam, locator-pin, or M4-shank interference."
            if not digital_fit_ok
            else "",
        )
    )

    reach_points = reach_screening.get("planar_points", [])
    minimum_nominal_radial_margin = min(
        (float(row["nominal_radial_margin_mm"]) for row in reach_points),
        default=float("nan"),
    )
    reach_proven = reach_screening.get("status") == "IK_COLLISION_AND_POSE_PROVEN"
    checks.append(
        check(
            "robot_reach_kinematics",
            "ENGINEERING_PASS_RECORDED" if reach_proven else "ENGINEERING_HOLD",
            (
                f"Planar screening covers {len(reach_points)} points; its smallest nominal radial margin is "
                f"{minimum_nominal_radial_margin:.3f} mm, but status is {reach_screening.get('status')}. "
                "This does not prove target Z/orientation, joint limits, singularities, payload, or collisions."
            ),
            "Measure T_board_base and the exact tool TCP/mass, then prove every approach/contact/retreat pose by IK and collision analysis before reduced-speed empty-cell motion."
            if not reach_proven
            else "",
        )
    )

    camera_selected = (
        camera_architecture.get("status")
        == "STATIC_OVERHEAD_TRIPOD_SELECTED_UNQUALIFIED"
    )
    camera_qualified = tripod_intake.get("status") == "QUALIFIED"
    checks.append(
        check(
            "camera_architecture_alignment",
            "ENGINEERING_PASS_RECORDED"
            if camera_selected and camera_qualified
            else "ENGINEERING_HOLD",
            (
                "Phase 1 selects the Arducam B0477 on an independent commercial floor tripod as the static overhead eye-to-hand primary. "
                f"Decision status is {camera_architecture.get('status')}; installation intake status is "
                f"{tripod_intake.get('status')}. The legacy RC03 mast jobs are SUPERSEDED_DO_NOT_PRINT."
            ),
            "Complete the hash-bound tripod receipt, mount-interface, support-geometry, installed-pose, stability, all-tag/crop visibility, collision, witness, and wrong-model records before installation or motion."
            if not camera_qualified
            else "",
        )
    )

    features = layout["board_features"]
    locator_features = [row for row in features if row["type"] == "locator_pin_blind"]
    retention_features = [row for row in features if row["type"] == "m4_retention_through"]
    feature_center_edge_mm: dict[str, float] = {}
    for feature in features:
        x = float(feature["x"])
        y = float(feature["y"])
        feature_center_edge_mm[feature["id"]] = round(
            min(x, y, float(board["width"]) - x, float(board["depth"]) - y), 3
        )
    minimum_feature_id = min(feature_center_edge_mm, key=feature_center_edge_mm.get)
    feature_count_ok = len(locator_features) == 4 and len(retention_features) == 9
    checks.append(
        check(
            "named_board_interface_architecture",
            "DIGITAL_PASS" if feature_count_ok else "DIGITAL_FAIL",
            f"Board has {len(locator_features)} blind locators and {len(retention_features)} threaded-retention centers. Minimum center-to-board-edge distance is {feature_center_edge_mm[minimum_feature_id]:.2f} mm at {minimum_feature_id}.",
            "Restore the controlled 4-locator/9-retainer architecture." if not feature_count_ok else "",
        )
    )

    worst_case_blind_floor = round(
        readiness.BOARD_THICKNESS_MIN_MM
        - (
            readiness.BOARD_LOCATOR_BORE_DEPTH_NOMINAL_MM
            + readiness.BOARD_LOCATOR_BORE_DEPTH_TOLERANCE_MM
        ),
        3,
    )
    blind_floor_ok = worst_case_blind_floor >= readiness.BOARD_MINIMUM_BLIND_BORE_FLOOR_MM
    checks.append(
        check(
            "locator_blind_floor_tolerance_stack",
            "DIGITAL_PASS" if blind_floor_ok else "DIGITAL_FAIL",
            f"Worst released board/depth stack leaves {worst_case_blind_floor:.2f} mm of intact board versus the {readiness.BOARD_MINIMUM_BLIND_BORE_FLOOR_MM:.2f} mm minimum.",
            "Reduce bore depth tolerance or increase minimum board thickness."
            if not blind_floor_ok
            else "",
        )
    )

    unresolved_fasteners: dict[str, list[str]] = {}
    for row in fasteners:
        missing = [field for field in FASTENER_REQUIRED_FIELDS if not str(row.get(field, "")).strip()]
        if missing:
            unresolved_fasteners[row.get("feature_id", "UNKNOWN")] = missing
    checks.append(
        check(
            "board_fastener_release",
            "PHYSICAL_HOLD" if unresolved_fasteners else "PHYSICAL_PASS_RECORDED",
            f"{len(unresolved_fasteners)} of {len(fasteners)} board fastener stacks remain unresolved.",
            "Select one exact anchor system and complete all nine rows from matching 18 mm scrap-board tests."
            if unresolved_fasteners
            else "Retain the qualification evidence and map hash.",
        )
    )

    protected_gate = measurement["gates"]["plus4_protected_envelope_verified"]
    checks.append(
        check(
            "actual_printer_clearance",
            "PHYSICAL_PASS_RECORDED" if protected_gate["status"] == "PASS" else "PHYSICAL_HOLD",
            f"plus4_protected_envelope_verified is {protected_gate['status']}.",
            "Run and record the actual-machine X/Y/Z, purge, carriage, and enclosure clearance check."
            if protected_gate["status"] != "PASS"
            else "",
        )
    )

    physical_gate_groups = (
        (
            "print_process_qualification",
            (
                "nozzle_0p4_confirmed",
                "abs_rapido_general_profile_calibrated",
                "abs_rapido_tray_profile_calibrated",
                "abs_rapido_cradle_profile_calibrated",
                "abs_rapido_precision_profile_calibrated",
                "petg_adapter_profile_calibrated",
                "abs_rapido_calibration_profile_calibrated",
                "tpu_profile_calibrated",
                "qidi_studio_roundtrip_confirmed",
            ),
            "Physically confirm the nozzle; qualify the exact QIDI ABS Rapido, retained PETG adapter, and TPU lots against their assigned profiles; and complete the native QIDI Studio round trip for every active job.",
        ),
        (
            "reference_hardware_measurements",
            (
                "keyboard_dimensions_measured",
                "phone_dimensions_measured",
                "phone_side_features_measured",
                "phone_cable_measured",
                "gripper_interface_measured",
                "spring_dimensions_measured",
                "camera_mount_interface_measured",
            ),
            "Measure the exact reference devices, cable, gripper, spring, and camera; regenerate affected geometry from accepted values.",
        ),
        (
            "printed_interface_qualification",
            tuple(
                gate_id
                for gate_id, gate in measurement["gates"].items()
                if gate["category"] in {"coupon", "first_article", "postprint"}
                and not gate_id.startswith("asa_")
                and not gate_id.startswith("mast_")
            ),
            "Print and accept every active profile-specific coupon, first article, production interface, and matched spare.",
        ),
        (
            "board_physical_acceptance",
            ("board_setup_template_scale_pass", "board_fabrication_pass"),
            "Accept the physical guide scale and board, then bind the board record to the qualified fastener-map hash.",
        ),
        (
            "vision_physical_acceptance",
            (
                "tag_artwork_scale_pass",
                "tag_direct_installation_pass",
                "tag_plane_placement_measured",
            ),
            "Validate physical tag scale/stock, install all six tags, and record their optical-plane metrology.",
        ),
        (
            "mechanical_repeatability",
            (
                "keyboard_fixture_assembly_pass",
                "phone_fixture_assembly_pass",
                "station_remove_reinstall_repeatability_pass",
            ),
            "Complete the station/device dry fits and ten-cycle pose/rocking/structural proofs.",
        ),
        (
            "powered_safety_and_commissioning",
            (
                "commissioning_motion_contact_limits_approved",
                "workcell_commissioning_pass",
            ),
            "Release the reinforcement, anti-shift, enclosed E-stop, camera, robot limits/programs, reach, empty motion, and controlled first-contact evidence before power-up.",
        ),
    )
    for group_id, gate_ids, required_action in physical_gate_groups:
        statuses = {gate_id: measurement["gates"][gate_id]["status"] for gate_id in gate_ids}
        passed = statuses and all(status == "PASS" for status in statuses.values())
        checks.append(
            check(
                group_id,
                "PHYSICAL_PASS_RECORDED" if passed else "PHYSICAL_HOLD",
                f"Gate state: {statuses}.",
                "" if passed else required_action,
            )
        )

    routes = measurement.get("selected_routes", {})
    selected_tool_routes = [
        route for route in readiness.TOOL_ROUTE_IDS if routes.get(route, False)
    ]
    checks.append(
        check(
            "tool_route_selection",
            "DECISION_OPEN" if not selected_tool_routes else "CANDIDATE_SELECTED",
            f"Selected tool routes in the physical evidence record: {selected_tool_routes or 'none'}.",
            "Freeze the V1 intended use and select exactly one released tool route, or redesign two complete labeled tools."
            if not selected_tool_routes
            else "Physically qualify every selected route.",
        )
    )

    physical_gate_counts: dict[str, int] = {}
    for gate in measurement["gates"].values():
        physical_gate_counts[gate["status"]] = physical_gate_counts.get(gate["status"], 0) + 1
    digital_failures = [row for row in checks if row["status"] == "DIGITAL_FAIL"]
    engineering_holds = [row for row in checks if row["status"] == "ENGINEERING_HOLD"]
    physical_holds = [row for row in checks if row["status"] == "PHYSICAL_HOLD"]
    decisions_open = [row for row in checks if row["status"] == "DECISION_OPEN"]
    state = (
        "DIGITAL_DEFECTS_PRESENT"
        if digital_failures
        else "DIGITALLY_CONSISTENT_ENGINEERING_AND_PHYSICAL_RELEASE_BLOCKED"
        if engineering_holds or physical_holds or decisions_open
        else "PREHARDWARE_CHECKS_CLEAR_REVIEW_PHYSICAL_RECORDS"
    )

    return {
        "schema_version": 1,
        "design_revision": measurement["design_revision"],
        "report_scope": "digital and record-state review only; not a physical release",
        "state": state,
        "safe_to_start_production_printing": False,
        "safe_to_drill_final_anchor_bores": not unresolved_fasteners,
        "safe_to_power_robot": measurement["gates"]["workcell_commissioning_pass"]["status"] == "PASS",
        "provisional_protected_envelope_mm": list(protected),
        "part_axis_maxima": part_axis_maxima,
        "plate_axis_maxima": plate_axis_maxima,
        "station_edge_clearances_mm": station_edge_clearances,
        "board_feature_center_edge_distances_mm": feature_center_edge_mm,
        "worst_case_locator_blind_floor_mm": worst_case_blind_floor,
        "unresolved_fastener_fields_by_feature": unresolved_fasteners,
        "measurement_gate_status_counts": physical_gate_counts,
        "summary": {
            "digital_pass": sum(row["status"] == "DIGITAL_PASS" for row in checks),
            "digital_fail": len(digital_failures),
            "engineering_hold": len(engineering_holds),
            "physical_hold": len(physical_holds),
            "decision_open": len(decisions_open),
            "checks": len(checks),
        },
        "checks": checks,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# RoCell pre-hardware readiness",
        "",
        f"**Controlled revision:** `{report['design_revision']}`  ",
        f"**State:** `{report['state']}`  ",
        "**This is not a physical release.** A digital PASS means the files and nominal tolerance stack agree; it does not prove printed fit, anchor strength, robot reach, camera stability, or safe powered motion.",
        "",
        "## Immediate verdict",
        "",
        f"- Digital checks: {summary['digital_pass']} PASS / {summary['digital_fail']} FAIL.",
        f"- Explicit engineering holds: {summary['engineering_hold']}.",
        f"- Explicit physical holds: {summary['physical_hold']}.",
        f"- Open configuration decisions: {summary['decision_open']}.",
        f"- Production printing authorized: **{'YES' if report['safe_to_start_production_printing'] else 'NO'}**.",
        f"- Final anchor drilling authorized: **{'YES' if report['safe_to_drill_final_anchor_bores'] else 'NO'}**.",
        f"- Powered robot motion authorized: **{'YES' if report['safe_to_power_robot'] else 'NO'}**.",
        "",
        "The current geometry is a credible build candidate. Do not cross the three NO gates above until their named evidence is complete.",
        "",
        "## Calculated dimensional reserves",
        "",
        f"Provisional protected printer envelope: `{report['provisional_protected_envelope_mm']}` mm.",
        "",
        "| Axis | Largest STL / extent | STL reserve | Largest plate / extent | Plate reserve |",
        "| --- | --- | ---: | --- | ---: |",
    ]
    for axis in ("x", "y", "z"):
        part = report["part_axis_maxima"][axis]
        plate = report["plate_axis_maxima"][axis]
        lines.append(
            f"| {axis.upper()} | `{part['part']}` / {part['extent_mm']:.2f} mm | "
            f"{part['protected_margin_mm']:.2f} mm | Job `{plate['job_id']}` / "
            f"{plate['extent_mm']:.2f} mm | {plate['protected_margin_mm']:.2f} mm |"
        )
    lines.extend(
        [
            "",
            f"Worst released blind-locator floor stack: **{report['worst_case_locator_blind_floor_mm']:.2f} mm** intact board, above the 2.00 mm minimum.",
            "",
            "## Check register",
            "",
            "| Check | State | Finding | Required action |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in report["checks"]:
        lines.append(
            "| `{}` | **{}** | {} | {} |".format(
                row["check_id"],
                row["status"],
                row["finding"].replace("|", "/"),
                (row["required_action"] or "None for this scope.").replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## What still proves the build",
            "",
            "1. Verify the actual QIDI Plus4 protected envelope, nozzle, build surface, slicer version, and calibrated material profiles.",
            "2. Measure the exact keyboard, bare phone, USB cable, pins, inserts, nuts, washers, screws, spring, tool contact, camera, clamp, and board.",
            "3. Print and accept the profile-specific coupons and first articles; regenerate only from accepted measurements.",
            "4. Qualify one exact board anchor on matching 18 mm scrap and complete all nine fastener rows before final anchor drilling.",
            "5. Release and install the reinforcement plate, anti-shift system, enclosed E-stop/power cutoff, and rigid camera support.",
            "6. Prove station/device repeatability, tool force/travel/TCP, robot reach and empty-cell clearances, vision, E-stop behavior, and controlled first contact.",
            "",
            "Regenerate this report with `python scripts/generate_prehardware_readiness.py` after any controlled source or evidence change.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    report = build_report()
    JSON_OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    MARKDOWN_OUTPUT.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    if report["summary"]["digital_fail"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
