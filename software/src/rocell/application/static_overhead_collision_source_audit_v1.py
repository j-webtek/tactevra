"""Audit existing repository sources against the static collision roster.

The audit is deliberately non-promoting.  It hashes useful CAD, configuration,
and retained observation artifacts and maps them to every required body, while
preserving each source's published qualification limit.  Candidate evidence is
never converted into measured primitives, clearance, or physical authority.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .installed_collision_measurement_manifest_v1 import (
    InstalledCollisionMeasurementBindingsV1,
    load_installed_collision_measurement_manifest_for_bindings_v1,
)
from .static_overhead_collision_profile_intake_v1 import (
    static_overhead_measurement_bindings_v1,
)
from .static_simulation_context import load_static_simulation_context


SCHEMA = "rocell.static_overhead_collision_source_audit.v1"
STATUS = "BLOCKED_CANDIDATE_SOURCES_REQUIRE_QUALIFICATION"
_REVISION = re.compile(r"^[0-9a-f]{40}$")

_ROBOT_CANDIDATES = (
    (
        "software/integrations/isaac_sim/evidence/roarm_m3_link_mesh_reduction_20260929.json",
        "CONSERVATIVE_BOX_CANDIDATES_ONLY",
        "The retained reduction says candidate_profile_installable=false and retains non-watertight and replay blockers.",
    ),
    (
        "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf",
        "KINEMATIC_TOPOLOGY_ONLY",
        "The governed URDF explicitly omits visual and collision geometry.",
    ),
)

_CATALOG: dict[str, tuple[tuple[str, str, str], ...]] = {
    **{f"robot:{name}": _ROBOT_CANDIDATES for name in (
        "base_link", "link1", "link2", "link3", "link4", "link5", "gripper"
    )},
    "installation:base_and_factory_clamp": (
        (
            "software/config/live_camera_feedback_session_20261015.json",
            "INSTALLED_OBSERVATION_CONTEXT_ONLY",
            "The retained session identifies the installation epoch but contains no conservative base-and-clamp envelope.",
        ),
    ),
    "installation:static_camera_support": (
        (
            "hardware/static_overhead_camera/config/support_design.json",
            "SCREENING_DESIGN_CANDIDATE",
            "The support contract explicitly leaves exact cut lengths and physical qualification open.",
        ),
        (
            "hardware/static_overhead_camera/cad/output/assembly/printable_camera_portal_prototype.step",
            "DESIGN_CAD_NOT_INSTALLED_METROLOGY",
            "Prototype CAD does not establish the installed support placement, fasteners, or uncertainty.",
        ),
    ),
    "installation:static_camera_module": (
        (
            "software/config/camera_profiles/arducam_b0477_imx283_16mm.json",
            "CATALOG_IDENTITY_AND_OPTICS",
            "The profile binds the camera configuration but is not an installed case-envelope measurement.",
        ),
        (
            "hardware/static_overhead_camera/cad/output/assembly/camera_cage_nominal_subassembly.step",
            "NOMINAL_CAGE_CAD",
            "The cage subassembly does not qualify the received camera case or installed transform.",
        ),
    ),
    "installation:static_camera_connector": (
        (
            "hardware/static_overhead_camera/cad/output/revisions/08D-C2_usb_keeper_v1/08D-C2_ABS_USB_clearance_keeper_v1.step",
            "CONNECTOR_KEEPER_DESIGN_CAD",
            "Keeper CAD does not establish the installed plug, strain relief, placement, or uncertainty.",
        ),
    ),
    "installation:static_camera_cable": (
        (
            "software/config/live_camera_feedback_session_20261015.json",
            "CABLE_VISIBILITY_CONTEXT_ONLY",
            "The retained observations show the cable context but do not provide a fixed conservative cable envelope.",
        ),
    ),
    "attachment:contact_tool": (
        (
            "software/config/live_camera_feedback_session_20261015.json",
            "BARE_JAW_CONFIGURATION_CONTEXT",
            "The session records BARE_JAW, but the absence declaration still needs a reviewed source compatible with the measurement contract.",
        ),
    ),
    "workcell:board_solid": (
        (
            "software/freezes/ROCELL-PHASE0-RC03-INT-R1-FREEZE-013/system_manifest.json",
            "FROZEN_DIGITAL_PHYSICAL_MEASUREMENT_OPEN",
            "The frozen 610 x 457 x 18 mm board is explicitly marked physical_measurement_state=OPEN_BLOCKING.",
        ),
    ),
    "workcell:keyboard": (
        (
            "software/config/photo_keyboard_registration_manual_20261011.json",
            "MANUAL_PHOTO_ESTIMATE_ONLY",
            "The registration records 315 x 147 x 21 mm and image placement but explicitly does not establish physical metrology.",
        ),
        (
            "software/ai/eval/b0477_keyboard_overlay_20261016.json",
            "DIMENSION_CONSTRAINED_IMAGE_OVERLAY",
            "The overlay improves image alignment but does not establish a measured board-frame envelope or pose uncertainty.",
        ),
    ),
    "workcell:phone": (
        (
            "software/freezes/ROCELL-PHASE0-RC03-INT-R1-FREEZE-013/system_manifest.json",
            "SELECTED_NOMINAL_DEVICE",
            "The selected phone dimensions and placement remain physically unqualified.",
        ),
    ),
    "workcell:station:keyboard_left": (
        (
            "active-project/RoCell_v0_3/cad/step/keyboard_station_left.step",
            "CONTROLLED_DESIGN_CAD",
            "Controlled CAD does not establish the printed installed article, board transform, or manufacturing uncertainty.",
        ),
        (
            "active-project/RoCell_v0_3/config/workcell_layout.json",
            "NOMINAL_LAYOUT",
            "The layout is nominal simulation geometry rather than installed placement evidence.",
        ),
    ),
    "workcell:station:keyboard_right": (
        (
            "active-project/RoCell_v0_3/cad/step/keyboard_station_right.step",
            "CONTROLLED_DESIGN_CAD",
            "Controlled CAD does not establish the printed installed article, board transform, or manufacturing uncertainty.",
        ),
        (
            "active-project/RoCell_v0_3/config/workcell_layout.json",
            "NOMINAL_LAYOUT",
            "The layout is nominal simulation geometry rather than installed placement evidence.",
        ),
    ),
    "workcell:station:phone_tcp": (
        (
            "active-project/RoCell_v0_3/cad/step/phone_tcp_station.step",
            "CONTROLLED_DESIGN_CAD",
            "Controlled CAD does not establish the printed installed article, board transform, or manufacturing uncertainty.",
        ),
        (
            "active-project/RoCell_v0_3/config/workcell_layout.json",
            "NOMINAL_LAYOUT",
            "The layout is nominal simulation geometry rather than installed placement evidence.",
        ),
    ),
}


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


def audit_static_overhead_collision_sources_for_bindings_v1(
    source_workspace: Path,
    pending_manifest_path: Path,
    pending_manifest_file_sha256: str,
    *,
    bindings: InstalledCollisionMeasurementBindingsV1,
    source_revision: str,
) -> dict[str, Any]:
    """Map exact tracked sources to every required body without promotion."""

    if _REVISION.fullmatch(source_revision) is None:
        raise ValueError("source_revision must be a lowercase 40-character Git SHA")
    document, validation = load_installed_collision_measurement_manifest_for_bindings_v1(
        pending_manifest_path,
        pending_manifest_file_sha256,
        bindings=bindings,
    )
    required_ids = {item.body_id for item in bindings.contract.requirements}
    if set(_CATALOG) != required_ids:
        raise ValueError(
            "source catalog differs from required body roster: "
            f"missing={sorted(required_ids - set(_CATALOG))}, "
            f"unexpected={sorted(set(_CATALOG) - required_ids)}"
        )
    if validation["measured_body_count"] != 0 or set(validation["pending_body_ids"]) != required_ids:
        raise ValueError("source audit requires the exact all-pending intake manifest")

    hashed: dict[str, tuple[str, int]] = {}
    rows: list[dict[str, Any]] = []
    for requirement in bindings.contract.requirements:
        candidates = []
        for relative, evidence_class, limitation in _CATALOG[requirement.body_id]:
            path = source_workspace / relative
            if not path.is_file():
                raise FileNotFoundError(f"candidate source is missing: {relative}")
            if relative not in hashed:
                payload = path.read_bytes()
                hashed[relative] = (hashlib.sha256(payload).hexdigest(), len(payload))
            digest, byte_count = hashed[relative]
            candidates.append({
                "path": relative,
                "sha256": digest,
                "byte_count": byte_count,
                "evidence_class": evidence_class,
                "qualification": "CANDIDATE_ONLY",
                "limitation": limitation,
            })
        rows.append({
            "body_id": requirement.body_id,
            "parent_frame": requirement.parent_frame,
            "binding_mode": requirement.binding_mode.value,
            "decision": "CANDIDATE_ONLY",
            "candidate_sources": candidates,
            "accepted_measurement_source_count": 0,
            "next_action": (
                "Qualify a conservative installed envelope, placement, and uncertainty "
                "from reviewed evidence before changing this body from PENDING."
            ),
        })

    core = {
        "schema": SCHEMA,
        "status": STATUS,
        "source_revision": source_revision,
        "measurement_manifest_file_sha256": pending_manifest_file_sha256,
        "measurement_manifest_content_sha256": document["content_sha256"],
        "base_contract_sha256": bindings.contract.content_hash,
        "required_body_count": len(rows),
        "candidate_body_count": len(rows),
        "accepted_measurement_body_count": 0,
        "missing_candidate_body_count": 0,
        "unique_candidate_source_count": len(hashed),
        "body_source_coverage": rows,
        "next_required_stage": "QUALIFY_INSTALLED_ENVELOPES_PLACEMENTS_AND_UNCERTAINTIES",
        "profile_generated": False,
        "collision_screening_executed": False,
        "controller_commands": [],
        "hardware_access": False,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "report_sha256": _sha(core)}


def audit_static_overhead_collision_sources_v1(
    contract_workspace: Path,
    source_workspace: Path,
    pending_manifest_path: Path,
    pending_manifest_file_sha256: str,
    *,
    source_revision: str,
) -> dict[str, Any]:
    """Load the frozen static contract and audit a separate source tree."""

    context = load_static_simulation_context(contract_workspace)
    return audit_static_overhead_collision_sources_for_bindings_v1(
        source_workspace,
        pending_manifest_path,
        pending_manifest_file_sha256,
        bindings=static_overhead_measurement_bindings_v1(context),
        source_revision=source_revision,
    )


__all__ = [
    "SCHEMA",
    "STATUS",
    "audit_static_overhead_collision_sources_for_bindings_v1",
    "audit_static_overhead_collision_sources_v1",
]
