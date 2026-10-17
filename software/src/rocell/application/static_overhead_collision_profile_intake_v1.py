"""Prepare and consume static-overhead installed-collision measurements.

This adapter joins the selected static-camera source graph to the reusable
ICQ-1/ICQ-2 manifest pipeline. It produces a digital pending manifest without
inventing dimensions and can later build a zero-authority installed profile
from a complete, hash-bound manifest. It never opens hardware or emits motion.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rocell.application._pinned_model import load_pinned_urdf
from rocell.application.installed_collision_measurement_manifest_v1 import (
    InstalledCollisionMeasurementBindingsV1,
    render_installed_collision_measurement_worksheet_v1,
    validate_installed_collision_measurement_manifest_v1,
)
from rocell.application.installed_collision_profile_builder_v1 import (
    InstalledCollisionProfileBuildResultV1,
    build_installed_collision_profile_for_bindings_v1,
)
from rocell.application.static_simulation_context import (
    StaticSimulationContext,
    load_static_simulation_context,
    revalidate_static_simulation_context,
)
from rocell.simulation.collision import (
    build_roarm_m3_static_overhead_collision_contract,
)


SCHEMA = "rocell.static_overhead_collision_profile_intake.v1"
PENDING_STATUS = "BLOCKED_STATIC_OVERHEAD_MEASUREMENTS_PENDING"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def static_overhead_measurement_bindings_v1(
    context: StaticSimulationContext,
) -> InstalledCollisionMeasurementBindingsV1:
    """Derive exact manifest bindings from one revalidated static context."""

    revalidate_static_simulation_context(context)
    loaded = load_pinned_urdf(
        context.scenario.model_path,
        context.scenario.model_sha256,
    )
    contract = build_roarm_m3_static_overhead_collision_contract(
        loaded.model,
        context.scene,
    )
    active_build_id = context.snapshot.active_build_id
    if active_build_id is None:
        raise ValueError("static context active build id is unavailable")
    return InstalledCollisionMeasurementBindingsV1(
        contract=contract,
        manifest_id=context.snapshot.manifest_id,
        manifest_sha256=context.snapshot.manifest_sha256,
        active_build_id=active_build_id,
        build_snapshot_sha256=context.snapshot.snapshot_hash,
        robot_model_sha256=loaded.sha256,
    )


def build_pending_static_overhead_measurement_manifest_v1(
    context: StaticSimulationContext,
    *,
    measurement_manifest_id: str,
    captured_at_utc: str,
) -> dict[str, Any]:
    """Create an exact pending manifest for on-screen completion."""

    if not isinstance(measurement_manifest_id, str) or not measurement_manifest_id.strip():
        raise ValueError("measurement_manifest_id must be non-empty text")
    if not isinstance(captured_at_utc, str) or not captured_at_utc.endswith("Z"):
        raise ValueError("captured_at_utc must be an ISO-8601 UTC timestamp")
    bindings = static_overhead_measurement_bindings_v1(context)
    retained_notes = {
        "attachment:contact_tool": (
            "Retained attachment profile: BARE_JAW. TCP and conservative collision "
            "envelope remain pending acceptance."
        ),
        "installation:static_camera_support": (
            "Retained static-support design candidate is source-bound; installed "
            "placement, envelope, and uncertainty remain pending acceptance."
        ),
        "installation:static_camera_module": (
            "Retained module identity: Arducam B0477 IMX283 with 16 mm lens; installed "
            "case envelope and uncertainty remain pending acceptance."
        ),
        "workcell:board_solid": (
            "Retained candidate dimensions: 610 x 457 mm board footprint and 18 mm "
            "nominal thickness; source/uncertainty acceptance remains pending."
        ),
        "workcell:keyboard": (
            "Retained dimension-constrained keyboard candidate: 315 x 147 x 21 mm; "
            "reviewed overlay placement and installed uncertainty remain pending acceptance."
        ),
    }
    body_measurements = []
    for requirement in bindings.contract.requirements:
        body_measurements.append(
            {
                "body_id": requirement.body_id,
                "parent_frame": requirement.parent_frame,
                "role": requirement.role.value,
                "binding_mode": requirement.binding_mode.value,
                "status": "PENDING",
                "source_ids": [],
                "coordinate_frame": requirement.parent_frame,
                "units": "mm",
                "geometry_uncertainty_mm": None,
                "envelope_primitives": [],
                "notes": retained_notes.get(
                    requirement.body_id,
                    "Pending conservative installed envelope and reviewed source evidence.",
                ),
            }
        )
    document: dict[str, Any] = {
        "schema": "rocell.installed_collision_measurement_manifest.v1",
        "measurement_manifest_id": measurement_manifest_id.strip(),
        "captured_at_utc": captured_at_utc,
        "manifest_id": bindings.manifest_id,
        "manifest_sha256": bindings.manifest_sha256,
        "active_build_id": bindings.active_build_id,
        "build_snapshot_sha256": bindings.build_snapshot_sha256,
        "robot_model_sha256": bindings.robot_model_sha256,
        "base_contract_sha256": bindings.contract.content_hash,
        "root_frame": bindings.contract.root_frame,
        "sources": [],
        "body_measurements": body_measurements,
        "clearance_measurement": {
            "status": "PENDING",
            "source_ids": [],
            "minimum_separation_mm": None,
            "geometry_uncertainty_mm_per_body": None,
            "pose_uncertainty_mm_per_body": None,
            "notes": "Pending reviewed installed clearance and uncertainty policy.",
        },
    }
    document["content_sha256"] = _sha(document)
    return document


def prepare_static_overhead_measurement_packet_v1(
    workspace: Path,
    *,
    measurement_manifest_id: str,
    captured_at_utc: str,
) -> tuple[dict[str, Any], bytes, str, str]:
    """Return the pending document, canonical bytes, report, and worksheet."""

    context = load_static_simulation_context(workspace)
    bindings = static_overhead_measurement_bindings_v1(context)
    document = build_pending_static_overhead_measurement_manifest_v1(
        context,
        measurement_manifest_id=measurement_manifest_id,
        captured_at_utc=captured_at_utc,
    )
    payload = _canonical(document)
    file_sha256 = hashlib.sha256(payload).hexdigest()
    validation = validate_installed_collision_measurement_manifest_v1(
        document,
        contract=bindings.contract,
        expected_manifest_id=bindings.manifest_id,
        expected_manifest_sha256=bindings.manifest_sha256,
        expected_active_build_id=bindings.active_build_id,
        expected_build_snapshot_sha256=bindings.build_snapshot_sha256,
        expected_robot_model_sha256=bindings.robot_model_sha256,
        file_sha256=file_sha256,
    )
    core = {
        "schema": SCHEMA,
        "status": PENDING_STATUS,
        "measurement_manifest_file_sha256": file_sha256,
        "measurement_manifest_content_sha256": document["content_sha256"],
        "base_contract_sha256": bindings.contract.content_hash,
        "required_body_count": len(bindings.contract.requirements),
        "validation": validation,
        "next_required_stage": "COMPLETE_HASH_BOUND_MEASUREMENTS_THEN_BUILD_PROFILE",
        "profile_generated": False,
        "collision_screening_executed": False,
        "controller_commands": [],
        "hardware_access": False,
        "physical_movements": 0,
        "physical_authority": False,
    }
    report = {**core, "report_sha256": _sha(core)}
    worksheet = render_installed_collision_measurement_worksheet_v1(bindings.contract)
    return report, payload, file_sha256, worksheet


def build_static_overhead_collision_profile_v1(
    workspace: Path,
    measurement_manifest_path: Path,
    measurement_manifest_file_sha256: str,
) -> InstalledCollisionProfileBuildResultV1:
    """Build a zero-authority profile from completed static-camera evidence."""

    context = load_static_simulation_context(workspace)
    return build_installed_collision_profile_for_bindings_v1(
        measurement_manifest_path,
        measurement_manifest_file_sha256,
        bindings=static_overhead_measurement_bindings_v1(context),
    )


__all__ = [
    "PENDING_STATUS",
    "SCHEMA",
    "build_pending_static_overhead_measurement_manifest_v1",
    "build_static_overhead_collision_profile_v1",
    "prepare_static_overhead_measurement_packet_v1",
    "static_overhead_measurement_bindings_v1",
]
