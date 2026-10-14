#!/usr/bin/env python3
"""Validate the Phase-0 system freeze against the controlled RC03 build."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = WORKSPACE / "software" / "config" / "system_manifest.json"
DEFAULT_CAMERA_MANIFEST = WORKSPACE / "software" / "config" / "camera_manifest.json"
SIMULATION_BUNDLE_ARTIFACT_PATHS = {
    "simulation_hardware_profile": "software/config/simulation_hardware_profile.json",
    "nominal_target_profiles": "software/config/nominal_target_profiles.json",
    "arm_frame_contract": "software/config/arm_frame_contract.json",
    "camera_manifest": "software/config/camera_manifest.json",
    "local_roarm_urdf": "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf",
    # The unmeasured rank-1 layout is a separately locked input.  Keeping it in
    # this independent release validator prevents a virtual commissioning run
    # from silently drifting away from the scenario validated by the runtime.
    "virtual_commissioning_profile": (
        "software/config/virtual_commissioning_profile.json"
    ),
}
REQUIRED_SNAPSHOT_PATHS = {
    "BOM.csv",
    "config/workcell_layout.json",
    "config/parameters.json",
    "config/print_profiles.json",
    "config/print_jobs.json",
    "config/measurement_record.json",
    "config/assembly_steps.json",
    "config/v1_prehardware_configuration.json",
    "config/camera_architecture_decision.json",
    "config/hardware_candidates.json",
    "config/digital_fit_report.json",
    "config/robot_reach_screening.json",
    "fiducials/apriltag_map.json",
    "BUILD_BY_STEP/ACTIVE_BUILD.json",
    "BUILD_BY_STEP/INDEX.json",
    "BUILD_BY_STEP/PACKAGE_VALIDATION.json",
    "drawings/documentation_sync.json",
    "RELEASE_VALIDATION.json",
    "PRINT_READINESS.json",
    "BUILD_TRACKER.json",
    "PREHARDWARE_READINESS.json",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_simulation_bundle(
    manifest: dict[str, Any],
    simulation_bundle: dict[str, Any],
    errors: list[str],
) -> None:
    """Validate the software bundle independently of RC03 snapshot health."""

    if simulation_bundle.get("schema") != "rocell.simulation_bundle_lock.v1":
        errors.append("Simulation bundle lock schema is not v1")
    if simulation_bundle.get("schema_version") != 1:
        errors.append("Simulation bundle lock schema_version is not 1")
    if simulation_bundle.get("status") != (
        "SIMULATION_ONLY_LOCKED_PHYSICAL_AUTHORITY_NONE"
    ):
        errors.append("Simulation bundle is not in its locked simulation-only state")
    if simulation_bundle.get("simulation_only") is not True:
        errors.append("Simulation bundle lock no longer declares simulation_only=true")
    if simulation_bundle.get("physical_release_effect") != "NONE":
        errors.append("Simulation bundle lock unexpectedly affects physical release")
    if simulation_bundle.get("system_manifest_id") != manifest.get("manifest_id"):
        errors.append("Simulation bundle lock is not bound to the active system freeze")
    if simulation_bundle.get("design_revision") != manifest.get("rc03", {}).get(
        "design_revision"
    ):
        errors.append("Simulation bundle lock design revision differs from RC03")
    bundle_artifacts = simulation_bundle.get("artifacts", {})
    if not isinstance(bundle_artifacts, dict):
        errors.append("Simulation bundle artifacts must be an object")
        bundle_artifacts = {}
    if set(bundle_artifacts) != set(SIMULATION_BUNDLE_ARTIFACT_PATHS):
        errors.append("Simulation bundle artifact set changed")
    for artifact_id, expected_relative in SIMULATION_BUNDLE_ARTIFACT_PATHS.items():
        artifact = bundle_artifacts.get(artifact_id, {})
        if not isinstance(artifact, dict):
            errors.append(f"Simulation bundle artifact {artifact_id} is not an object")
            continue
        if artifact.get("path") != expected_relative:
            errors.append(f"Simulation bundle artifact {artifact_id} path changed")
            continue
        artifact_path = (WORKSPACE / expected_relative).resolve()
        try:
            artifact_path.relative_to(WORKSPACE)
        except ValueError:
            errors.append(f"Simulation bundle artifact {artifact_id} escapes the workspace")
            continue
        if not artifact_path.is_file():
            errors.append(f"Simulation bundle artifact {artifact_id} is missing")
            continue
        actual_digest = sha256(artifact_path)
        if artifact.get("sha256") != actual_digest:
            errors.append(
                f"Simulation bundle artifact {artifact_id} hash mismatch: "
                f"expected {artifact.get('sha256')}, got {actual_digest}"
            )


def main() -> int:
    manifest_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_MANIFEST
    errors: list[str] = []
    blockers: list[str] = []

    if not manifest_path.is_file():
        print(json.dumps({"status": "FAIL", "errors": [f"Missing manifest: {manifest_path}"]}, indent=2))
        return 1

    manifest = load_json(manifest_path)
    camera_manifest_path = manifest_path.parent / "camera_manifest.json"
    if not camera_manifest_path.is_file():
        errors.append(f"Missing camera binding manifest: {camera_manifest_path}")
        camera_manifest: dict[str, Any] = {}
    else:
        camera_manifest = load_json(camera_manifest_path)
    companion_paths = {
        "runtime": manifest_path.parent / "runtime.json",
        "arm_connection": manifest_path.parent / "arm_connection.json",
        "arm_frame_contract": manifest_path.parent / "arm_frame_contract.json",
        "simulation_bundle_lock": manifest_path.parent / "simulation_bundle_lock.json",
        "gate_projection": manifest_path.parent / "gate_projection.json",
        "calibration_registry": WORKSPACE / "software" / "calibrations" / "registry.json",
    }
    companions: dict[str, dict[str, Any]] = {}
    for name, path in companion_paths.items():
        if not path.is_file():
            errors.append(f"Missing {name} configuration: {path}")
            companions[name] = {}
        else:
            companions[name] = load_json(path)
    if manifest.get("schema_version") != 1:
        errors.append("Unsupported system manifest schema_version")
    if manifest.get("status") != "FROZEN_DIGITAL_ENGINEERING_HOLDS_CONTACT_BLOCKED":
        errors.append("System manifest no longer records the frozen engineering-holds/contact-blocked state")
    validate_simulation_bundle(manifest, companions["simulation_bundle_lock"], errors)
    # Reuse the runtime's stricter cross-artifact validator as well as the
    # standalone checks above.  This keeps this release tool synchronized with
    # target/layout, frame-contract, and provenance invariants used by services.
    source_root = WORKSPACE / "software" / "src"
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    try:
        from rocell.simulation import load_simulation_bundle_lock

        load_simulation_bundle_lock(
            WORKSPACE,
            lock_path=companion_paths["simulation_bundle_lock"],
        )
    except (ImportError, OSError, TypeError, ValueError) as exc:
        errors.append(f"Strict simulation bundle validation failed: {exc}")

    # The onboarding foundation is additive to the active Freeze-011 build.
    # Validate its complete zero-authority contract graph without treating its
    # open implementation gates as an RC03 release or adding it to the frozen
    # simulation bundle.
    try:
        from rocell.application.physical_onboarding_foundation import (
            load_physical_onboarding_foundation,
        )

        onboarding_foundation = load_physical_onboarding_foundation(WORKSPACE)
        if onboarding_foundation.runtime_activation is not False:
            errors.append("Physical-onboarding foundation unexpectedly activates runtime")
        if not onboarding_foundation.zero_physical_authority:
            errors.append("Physical-onboarding foundation exceeds zero authority")
    except (ImportError, OSError, TypeError, ValueError) as exc:
        errors.append(f"Strict physical-onboarding foundation validation failed: {exc}")

    rc03 = manifest.get("rc03", {})
    rc03_root = WORKSPACE / rc03.get("root", "")
    if not rc03_root.is_dir():
        errors.append(f"Missing RC03 root: {rc03_root}")
    else:
        snapshot = rc03.get("source_snapshot", [])
        snapshot_paths = [source.get("path") for source in snapshot]
        duplicate_paths = sorted(
            path for path, count in Counter(snapshot_paths).items() if path is not None and count > 1
        )
        if duplicate_paths:
            errors.append(f"Duplicate frozen RC03 source paths: {duplicate_paths}")
        missing_snapshot_paths = sorted(REQUIRED_SNAPSHOT_PATHS - set(snapshot_paths))
        if missing_snapshot_paths:
            errors.append(f"Required RC03 sources are absent from the freeze: {missing_snapshot_paths}")

        for source in snapshot:
            source_path = rc03_root / source["path"]
            if not source_path.is_file():
                errors.append(f"Missing frozen RC03 source: {source['path']}")
                continue
            actual = sha256(source_path)
            if actual != source["sha256"]:
                errors.append(
                    f"Frozen source hash mismatch for {source['path']}: "
                    f"expected {source['sha256']}, got {actual}"
                )

    if not errors:
        layout = load_json(rc03_root / "config" / "workcell_layout.json")
        parameters = load_json(rc03_root / "config" / "parameters.json")
        print_profiles = load_json(rc03_root / "config" / "print_profiles.json")
        print_jobs = load_json(rc03_root / "config" / "print_jobs.json")
        measurement = load_json(rc03_root / "config" / "measurement_record.json")
        v1_config = load_json(rc03_root / "config" / "v1_prehardware_configuration.json")
        camera_decision = load_json(rc03_root / "config" / "camera_architecture_decision.json")
        hardware_candidates = load_json(rc03_root / "config" / "hardware_candidates.json")
        digital_fit = load_json(rc03_root / "config" / "digital_fit_report.json")
        reach_screening = load_json(rc03_root / "config" / "robot_reach_screening.json")
        tag_map = load_json(rc03_root / "fiducials" / "apriltag_map.json")
        active_build = load_json(rc03_root / "BUILD_BY_STEP" / "ACTIVE_BUILD.json")
        package_validation = load_json(rc03_root / "BUILD_BY_STEP" / "PACKAGE_VALIDATION.json")
        release_validation = load_json(rc03_root / "RELEASE_VALIDATION.json")
        print_readiness = load_json(rc03_root / "PRINT_READINESS.json")
        build_tracker = load_json(rc03_root / "BUILD_TRACKER.json")
        prehardware = load_json(rc03_root / "PREHARDWARE_READINESS.json")

        expected_revision = rc03["design_revision"]
        for label, actual_revision in (
            ("workcell layout", layout.get("release_revision")),
            ("measurement record", measurement.get("design_revision")),
            ("tag map", tag_map.get("design_revision")),
            ("release validation", release_validation.get("design_revision")),
            ("camera decision", camera_decision.get("design_revision")),
            ("prehardware readiness", prehardware.get("design_revision")),
            ("V1 prehardware configuration", v1_config.get("baseline_design_revision")),
            ("digital fit report", digital_fit.get("design_revision")),
            ("reach screening", reach_screening.get("design_revision")),
            ("hardware candidate registry", hardware_candidates.get("registry_revision")),
        ):
            if actual_revision != expected_revision:
                errors.append(f"{label} revision is {actual_revision!r}, expected {expected_revision!r}")

        expected_envelope = manifest["hardware"]["printer"]["provisional_protected_envelope_mm"]
        actual_envelopes = {
            "workcell layout": layout["printer"]["protected_envelope"],
            "parameters": [
                parameters["printer_safe_x"],
                parameters["printer_safe_y"],
                parameters["printer_safe_z"],
            ],
            "print profiles": print_profiles["printer"]["safe_plate_envelope_mm"],
            "V1 prehardware configuration": v1_config["configuration"]["printer"][
                "provisional_protected_envelope_mm"
            ],
            "prehardware readiness": prehardware["provisional_protected_envelope_mm"],
        }
        for label, actual_envelope in actual_envelopes.items():
            if actual_envelope != expected_envelope:
                errors.append(
                    f"{label} protected envelope is {actual_envelope!r}, expected {expected_envelope!r}"
                )

        expected_board = manifest["hardware"]["board"]
        actual_board = layout["board"]
        actual_dimensions = [actual_board["width"], actual_board["depth"], actual_board["thickness"]]
        if actual_dimensions != expected_board["dimensions_mm"]:
            errors.append(f"Board dimensions changed: {actual_dimensions}")
        if layout.get("origin") != expected_board["frame_origin"] or layout.get("axes") != expected_board["axes"]:
            errors.append("Board frame contract changed")

        keyboard = manifest["hardware"]["keyboard"]
        if layout["devices"]["keyboard"]["nominal_size"] != keyboard["nominal_dimensions_mm"]:
            errors.append("Keyboard nominal dimensions no longer match the freeze")
        if layout["devices"]["keyboard"]["nominal_origin_xy"] != keyboard["nominal_board_origin_xy_mm"]:
            errors.append("Keyboard nominal board origin no longer matches the freeze")

        phone = manifest["hardware"]["phone"]
        configured_phone = layout["devices"]["phone"]
        if configured_phone["configured_size"] != phone["nominal_dimensions_width_length_thickness_mm"]:
            errors.append("Phone configured dimensions no longer match the bare-body freeze")
        if configured_phone["nominal_origin_xy"] != phone["nominal_board_origin_xy_mm"]:
            errors.append("Phone nominal board origin no longer matches the freeze")
        if configured_phone["nominal_screen_plane_z"] != phone["nominal_screen_plane_z_mm"]:
            errors.append("Phone nominal screen Z no longer matches the freeze")

        for route, route_contract in manifest["mission_routes"].items():
            actual_selected = measurement.get("selected_routes", {}).get(route)
            if actual_selected is not route_contract["selected"]:
                errors.append(f"RC03 route {route}={actual_selected!r}, expected {route_contract['selected']!r}")

        camera = manifest["hardware"]["camera"]
        expected_camera_contract = {
            "architecture": "arm_mounted_eye_on_arm",
            "primary_operational_role": True,
            "camera_carrier_frame": "E",
            "optical_frame": "C_arm",
            "hand_eye_extrinsic": "E_T_Carm",
        }
        for field, expected_value in expected_camera_contract.items():
            if camera.get(field) != expected_value:
                errors.append(
                    f"Primary camera {field} is {camera.get(field)!r}, expected {expected_value!r}"
                )

        expected_camera_manifest = {
            "schema_version": 1,
            "system_freeze_id": manifest.get("manifest_id"),
            "status": "STANDALONE_HOLDER_FROZEN_USB_CAMERA_CANDIDATE_SELECTED_PHYSICAL_IDENTITY_BLOCKED",
            "architecture": "eye_on_moving_upper_arm",
        }
        for field, expected_value in expected_camera_manifest.items():
            if camera_manifest.get(field) != expected_value:
                errors.append(
                    f"Camera manifest {field} is {camera_manifest.get(field)!r}, "
                    f"expected {expected_value!r}"
                )
        primary_camera = camera_manifest.get("primary", {})
        if primary_camera.get("backend") != "usb_opencv":
            errors.append("Selected direct-fit USB camera backend must remain usb_opencv")
        if primary_camera.get("camera_model") is not None:
            errors.append("Camera model was frozen without physical identity evidence")
        if primary_camera.get("numeric_camera_index_is_identity") is not False:
            errors.append("Camera manifest must not treat a numeric camera index as identity")
        holder = camera_manifest.get("holder", {})
        if holder.get("camera_hole_center_spacing_mm") != [21.0, 13.5]:
            errors.append("Bundled-holder camera hole spacing changed from the official 21 x 13.5 mm pattern")
        optional_esp = camera_manifest.get("optional_backends", {}).get("esp_http_mjpeg", {})
        if optional_esp.get("selected") is not False:
            errors.append("ESP camera backend cannot be selected before the physical identity gate")
        if camera.get("camera_binding_manifest") != "software/config/camera_manifest.json":
            errors.append("System manifest camera binding path changed")
        if camera.get("purchased_package_camera_included") is not False:
            errors.append("Standalone RoArm package must not claim that a camera is included")
        if camera.get("purchased_package_holder_included") is not True:
            errors.append("Standalone RoArm package must retain the included camera holder")
        selected_candidate = primary_camera.get("selected_candidate", {})
        if selected_candidate.get("model") != "IMX335 5MP USB Camera (B)":
            errors.append("Selected direct-fit camera candidate changed")
        if selected_candidate.get("camera_hole_center_spacing_mm") != [21.0, 13.5]:
            errors.append("Selected camera candidate no longer matches the holder hole pattern")
        if camera.get("optional_esp_backend_selected") is not False:
            errors.append("System manifest unexpectedly selects the optional ESP camera backend")

        runtime_config = companions["runtime"]
        if runtime_config.get("live_hardware_enabled") is not False:
            errors.append("Runtime configuration unexpectedly enables live hardware")
        if runtime_config.get("contact_enabled") is not False:
            errors.append("Runtime configuration unexpectedly enables contact")
        arm_connection = companions["arm_connection"]
        if arm_connection.get("port") is not None:
            errors.append("Arm serial port was bound before the physical identity/power gate")
        if arm_connection.get("auto_connect") is not False:
            errors.append("Arm connection must remain explicitly opened")
        if arm_connection.get("rts") is not False or arm_connection.get("dtr") is not False:
            errors.append("Arm serial RTS/DTR reset protection changed")
        arm_frame_contract = companions["arm_frame_contract"]
        if arm_frame_contract.get("schema") != "rocell.arm_frame_contract.v2":
            errors.append("Arm frame contract schema is not the separated-frame v2 contract")
        if arm_frame_contract.get("status") != "OPEN_BLOCKING_NOT_COMMISSIONED":
            errors.append("Arm frame contract was released without commissioning evidence")
        required_frames = {"Wv", "R_u", "R_ctrl", "E", "holder", "C_arm", "G", "T", "B"}
        if set(arm_frame_contract.get("frames", {})) != required_frames:
            errors.append("Arm frame contract no longer defines the exact separated frame set")
        separation = arm_frame_contract.get("frame_separation", {})
        if separation.get("controller_frame_equivalence") != "NOT_ASSUMED":
            errors.append("Arm frame contract unexpectedly aliases the controller frame")
        prohibited_aliases = set(separation.get("prohibited_aliases", []))
        if not {"R_ctrl=Wv", "R_ctrl=R_u", "E=link2", "G=T"} <= prohibited_aliases:
            errors.append("Arm frame contract lost required prohibited frame aliases")
        camera_installation = arm_frame_contract.get("camera_installation", {})
        if camera_installation.get("carrier_link") != "link2" or camera_installation.get("carrier_frame") != "E":
            errors.append("Arm frame contract camera carrier is not E on link2")
        if camera_installation.get("link2_T_holder") is not None or camera_installation.get("holder_T_C_arm") is not None:
            errors.append("Unmeasured camera installation transforms were populated without commissioning")
        controller_correlation = arm_frame_contract.get("controller_model_correlation", {})
        if controller_correlation.get("R_ctrl_correlation_artifact") is not None:
            errors.append("R_ctrl correlation artifact was populated without commissioning")
        motion_t104 = arm_frame_contract.get("motion_t104", {})
        if motion_t104.get("cartesian_frame") != "R_ctrl":
            errors.append("T=104 is no longer explicitly bound to R_ctrl")
        if motion_t104.get("prohibited_alternative") != "T=1041":
            errors.append("Arm frame contract no longer prohibits T=1041")
        feedback_t1051 = arm_frame_contract.get("feedback_t1051", {})
        if feedback_t1051.get("cartesian_frame") != "R_ctrl":
            errors.append("T=1051 diagnostics are no longer explicitly bound to R_ctrl")
        if feedback_t1051.get("endpoint_fields_are_complete_Wv_T_G") is not False:
            errors.append("T=1051 endpoint fields unexpectedly claim a complete Wv_T_G pose")
        pins = arm_frame_contract.get("pinned_sources", {})
        if pins.get("local_kinematic_projection_sha256") != "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190":
            errors.append("Arm frame contract local kinematic projection pin changed")
        gate_projection = companions["gate_projection"]
        if gate_projection.get("system_manifest_id") != manifest.get("manifest_id"):
            errors.append("Gate projection is not bound to the active system freeze")
        projected = gate_projection.get("capabilities", {})
        for capability in ("arm_feedback", "empty_cell_motion", "keyboard_contact", "phone_contact"):
            if projected.get(capability, {}).get("allowed") is not False:
                errors.append(f"Gate projection unexpectedly allows {capability}")
        calibration_registry = companions["calibration_registry"]
        if calibration_registry.get("system_manifest_id") != manifest.get("manifest_id"):
            errors.append("Calibration registry is not bound to the active system freeze")
        if calibration_registry.get("active_build_id") != rc03.get("active_build_id"):
            errors.append("Calibration registry and RC03 active build IDs differ")

        if camera_decision.get("schema_version") != 2:
            errors.append("Camera architecture decision is not the fail-closed tripod v2 record")
        if camera_decision.get("status") != "STATIC_OVERHEAD_TRIPOD_SELECTED_UNQUALIFIED":
            errors.append("Camera architecture does not select the unqualified overhead tripod")
        active_camera_route = camera_decision.get("active_route", {})
        expected_active_camera_route = {
            "route_id": "camera_overhead_primary",
            "architecture": "static_overhead_eye_to_hand",
            "support_type": "independent_commercial_floor_tripod",
            "selected": True,
            "qualified": False,
            "physical_release_effect": "NONE",
        }
        for field, expected_value in expected_active_camera_route.items():
            if active_camera_route.get(field) != expected_value:
                errors.append(
                    f"Camera tripod route {field} is {active_camera_route.get(field)!r}, "
                    f"expected {expected_value!r}"
                )
        camera_installation_state = camera_decision.get("installation_state", {})
        if camera_installation_state.get("intake_status") != "AWAITING_RECEIVED_HARDWARE_MEASUREMENTS":
            errors.append("Camera tripod intake was advanced without received-hardware measurements")
        if camera_installation_state.get("motion_authorized") is not False:
            errors.append("Camera tripod decision unexpectedly authorizes motion")
        if camera_installation_state.get("contact_authorized") is not False:
            errors.append("Camera tripod decision unexpectedly authorizes contact")
        superseded_camera_routes = {
            row.get("route_id"): row
            for row in camera_decision.get("superseded_routes", [])
            if isinstance(row, dict)
        }
        mast_disposition = superseded_camera_routes.get("camera_mast_optional", {})
        if mast_disposition.get("treatment") != "SUPERSEDED_DO_NOT_PRINT":
            errors.append("Camera decision does not preserve the superseded mast disposition")
        if set(mast_disposition.get("jobs", [])) != {"03C3", "06", "07A", "07B"}:
            errors.append("Camera decision superseded mast-job set changed")
        if superseded_camera_routes.get("arm_mounted_camera_phase_1", {}).get("treatment") != "HISTORICAL_UNSELECTED":
            errors.append("Camera decision does not retain the historical arm-camera disposition")
        if measurement.get("selected_routes", {}).get("camera_mast_optional") is not False:
            errors.append("RC03 camera_mast_optional route is unexpectedly selected")

        fallback_gate_id = "fixed_camera_fallback_architecture_released"
        fallback_gate = measurement.get("gates", {}).get(fallback_gate_id, {})
        if fallback_gate.get("status") != "NOT_TESTED":
            errors.append("Fixed-camera fallback release gate is no longer held at NOT_TESTED")
        fallback_jobs = {
            job.get("job_id"): job
            for job in print_jobs.get("jobs", [])
            if job.get("selection") == "camera_mast_optional"
        }
        expected_fallback_job_ids = {"03C3", "06", "07A", "07B"}
        if set(fallback_jobs) != expected_fallback_job_ids:
            errors.append(
                f"Fixed-camera fallback jobs changed: {sorted(fallback_jobs)}, "
                f"expected {sorted(expected_fallback_job_ids)}"
            )
        for job_id, job in fallback_jobs.items():
            if fallback_gate_id not in job.get("prerequisites", []):
                errors.append(f"Fallback camera job {job_id} lacks the architecture release interlock")
            if job.get("lifecycle") != "SUPERSEDED_DO_NOT_PRINT":
                errors.append(f"Fallback camera job {job_id} is not marked superseded")
        frozen_fallback_gate = manifest["current_build_state"].get(
            "fixed_camera_fallback_release_gate", {}
        )
        if frozen_fallback_gate.get("gate_id") != fallback_gate_id:
            errors.append("Manifest fixed-camera fallback gate identity changed")
        if frozen_fallback_gate.get("status") != "NOT_TESTED":
            errors.append("Manifest unexpectedly releases the fixed-camera fallback")
        if set(frozen_fallback_gate.get("protected_job_ids", [])) != expected_fallback_job_ids:
            errors.append("Manifest fixed-camera fallback protected-job set changed")
        if "FIXED_CAMERA_FALLBACK_ARCHITECTURE_NOT_RELEASED" not in blockers:
            blockers.append("FIXED_CAMERA_FALLBACK_ARCHITECTURE_NOT_RELEASED")

        camera_alignment = v1_config.get("configuration", {}).get("camera_architecture_alignment", {})
        if camera_alignment.get("release_effect") != "ENGINEERING_ALIGNMENT_HOLD":
            errors.append("V1 camera architecture release effect no longer matches the hold")
        if camera_alignment.get("alignment_record") != "config/camera_architecture_decision.json":
            errors.append("V1 camera architecture alignment record changed")
        if camera_alignment.get("exact_specification_reference") is not None:
            errors.append("V1 configuration claims an exact arm camera without a freeze revision")

        candidate_camera_boundary = hardware_candidates.get("camera_architecture_boundary", {})
        expected_candidate_camera_boundary = {
            "status": "SELECTED_UNQUALIFIED",
            "primary_architecture": "static_overhead_eye_to_hand",
            "primary_route": "camera_overhead_primary",
            "release_effect": "PHYSICAL_QUALIFICATION_HOLD",
            "legacy_mast_route": "camera_mast_optional",
            "legacy_mast_selected": False,
            "legacy_mast_treatment": "SUPERSEDED_DO_NOT_PRINT",
        }
        for field, expected_value in expected_candidate_camera_boundary.items():
            if candidate_camera_boundary.get(field) != expected_value:
                errors.append(
                    f"Hardware candidate camera boundary {field} is "
                    f"{candidate_camera_boundary.get(field)!r}, expected {expected_value!r}"
                )

        if not errors and "CAMERA_ARCHITECTURE_ALIGNMENT_HOLD" not in blockers:
            blockers.append("CAMERA_ARCHITECTURE_ALIGNMENT_HOLD")

        expected_tags = manifest["fiducials"]
        if tag_map.get("family") != expected_tags["family"]:
            errors.append("AprilTag family changed")
        if tag_map.get("detection_edge_mm") != expected_tags["detection_edge_mm"]:
            errors.append("AprilTag detection edge changed")
        if tag_map.get("tile_size_mm") != expected_tags["tile_size_mm"]:
            errors.append("AprilTag tile size changed")
        actual_ids = {name: data["id"] for name, data in tag_map["tags"].items()}
        if actual_ids != expected_tags["tag_ids"]:
            errors.append(f"AprilTag identity map changed: {actual_ids}")

        with (rc03_root / "BOM.csv").open(encoding="utf-8", newline="") as stream:
            bom = list(csv.DictReader(stream))
        bom_by_item = {row["item"]: row for row in bom}
        if manifest["hardware"]["robot"]["model"] not in bom_by_item:
            errors.append("Frozen RoArm-M3 Pro is missing from the RC03 BOM")
        keyboard_row = bom_by_item.get("Compact keyboard", {})
        if manifest["hardware"]["keyboard"]["model"] not in keyboard_row.get("specification", ""):
            errors.append("Frozen Perixx keyboard does not match the RC03 BOM")
        if manifest["hardware"]["phone"]["model"] not in bom_by_item:
            errors.append("Frozen Samsung phone is missing from the RC03 BOM")

        if release_validation.get("status") != "PASS":
            errors.append("RC03 digital release validation is not PASS")
        if package_validation.get("status") != "PASS":
            errors.append("RC03 build-step package validation is not PASS")
        if package_validation.get("physical_release") != "UNRELEASED":
            errors.append("Unexpected physical-release state; revise the freeze before use")

        expected_prehardware_state = "DIGITALLY_CONSISTENT_ENGINEERING_AND_PHYSICAL_RELEASE_BLOCKED"
        if prehardware.get("state") != expected_prehardware_state:
            errors.append(
                f"Prehardware state is {prehardware.get('state')!r}, expected {expected_prehardware_state!r}"
            )
        if prehardware.get("summary", {}).get("digital_fail") != 0:
            errors.append("Prehardware readiness contains a digital failure")
        if prehardware.get("summary", {}).get("engineering_hold") != 2:
            errors.append("Prehardware readiness no longer reports the two frozen engineering holds")
        for field in (
            "safe_to_start_production_printing",
            "safe_to_drill_final_anchor_bores",
            "safe_to_power_robot",
        ):
            if prehardware.get(field) is not False:
                errors.append(f"Prehardware readiness unexpectedly sets {field}=true")

        checks_by_id = {row.get("check_id"): row for row in prehardware.get("checks", [])}
        expected_checks = {
            "protected_envelope_sources": "DIGITAL_PASS",
            "robot_reach_kinematics": "ENGINEERING_HOLD",
            "camera_architecture_alignment": "ENGINEERING_HOLD",
        }
        for check_id, expected_status in expected_checks.items():
            actual_status = checks_by_id.get(check_id, {}).get("status")
            if actual_status != expected_status:
                errors.append(
                    f"Prehardware check {check_id} is {actual_status!r}, expected {expected_status!r}"
                )

        gate_counts = Counter(
            gate.get("status") for gate in measurement.get("gates", {}).values()
        )
        if dict(gate_counts) != prehardware.get("measurement_gate_status_counts"):
            errors.append("Measurement gate counts disagree with the prehardware readiness report")

        current_state = manifest["current_build_state"]
        if current_state.get("prehardware_readiness_state") != expected_prehardware_state:
            errors.append("Manifest prehardware readiness state no longer matches the generated report")
        if current_state.get("prehardware_digital_pass_count") != prehardware.get("summary", {}).get("digital_pass"):
            errors.append("Manifest prehardware DIGITAL_PASS count no longer matches the generated report")
        if current_state.get("prehardware_digital_fail_count") != prehardware.get("summary", {}).get("digital_fail"):
            errors.append("Manifest prehardware DIGITAL_FAIL count no longer matches the generated report")
        expected_engineering_holds = {
            "CAMERA_ARCHITECTURE_ALIGNMENT_HOLD",
            "ROBOT_REACH_SCREENING_ONLY_NOT_PROVEN",
        }
        if set(current_state.get("engineering_holds", [])) != expected_engineering_holds:
            errors.append("Manifest engineering-hold set changed")
        if reach_screening.get("status") != "SCREENING_ONLY_NOT_PROVEN":
            errors.append("Robot reach report no longer matches the frozen screening-only hold")
        for field in (
            "safe_to_start_production_printing",
            "safe_to_drill_final_anchor_bores",
            "safe_to_power_robot",
        ):
            if current_state.get(field) is not False:
                errors.append(f"Manifest unexpectedly sets {field}=true")
        if gate_counts.get("PASS", 0) != current_state["physical_gate_pass_count"]:
            errors.append("Physical PASS gate count no longer matches the freeze")
        if gate_counts.get("NOT_TESTED", 0) != current_state["physical_gate_not_tested_count"]:
            errors.append("Physical NOT_TESTED gate count no longer matches the freeze")

        print_summary = print_readiness.get("summary", {})
        selected_jobs = print_summary.get("total_jobs", 0) - print_summary.get("not_selected", 0)
        if selected_jobs != current_state["selected_jobs"]:
            errors.append("Selected print-job count no longer matches the freeze")
        if print_summary.get("ready") != current_state["ready_jobs"]:
            errors.append("Ready print-job count no longer matches the freeze")
        if print_summary.get("waiting") != current_state["waiting_jobs"]:
            errors.append("Waiting print-job count no longer matches the freeze")
        if build_tracker.get("summary", {}).get("selected_jobs") != current_state["selected_jobs"]:
            errors.append("Build tracker selected-job count no longer matches the freeze")

        if current_state.get("contact_enabled") is not False:
            errors.append("Manifest unexpectedly enables contact")
        if rc03.get("physical_release_status") != "UNRELEASED":
            errors.append("Manifest physical release is no longer UNRELEASED")
        if prehardware.get("safe_to_power_robot") is not False:
            errors.append("Prehardware report unexpectedly permits robot power")

        required_contact_blockers = {
            "CONTACT_GUARD_CONTROLLED_ADDENDUM_MISSING",
            "GRAVITY_SAFE_POWER_LOSS_CONTROLLED_ADDENDUM_MISSING",
            "MOTION_AND_CONTACT_LIMIT_APPROVAL_MISSING",
            "FINAL_COMMISSIONING_MISSING",
            "ROBOT_REACH_SCREENING_ONLY_NOT_PROVEN",
            "FIXED_CAMERA_FALLBACK_ARCHITECTURE_NOT_RELEASED",
        }
        missing_contact_blockers = sorted(required_contact_blockers - set(manifest.get("hard_blockers", [])))
        if missing_contact_blockers:
            errors.append(f"Required contact blockers are absent: {missing_contact_blockers}")

        if active_build.get("active_build_id") is None:
            blockers.append("ACTIVE_BUILD_ID_NULL")
        if tag_map.get("coordinate_source") != "measured_installation" or tag_map.get("measurement", {}).get("status") != "PASS":
            blockers.append("MEASURED_TAG_MAP_MISSING")
        if print_readiness.get("summary", {}).get("ready", 0) == 0:
            blockers.append("NO_PRINT_JOB_READY")

        gate_statuses = [gate.get("status") for gate in measurement.get("gates", {}).values()]
        if any(status != "PASS" for status in gate_statuses):
            blockers.append("PHYSICAL_GATES_INCOMPLETE")

    blockers.extend(
        blocker for blocker in manifest.get("hard_blockers", []) if blocker not in blockers
    )
    result = {
        "manifest_id": manifest.get("manifest_id"),
        "camera_manifest_id": camera_manifest.get("manifest_id"),
        "simulation_bundle_id": companions.get("simulation_bundle_lock", {}).get(
            "bundle_id"
        ),
        "status": "FAIL" if errors else "ALIGNED_CAMERA_HOLD_CONTACT_BLOCKED",
        "contact_enabled": False,
        "errors": errors,
        "blockers": blockers,
    }
    print(json.dumps(result, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
