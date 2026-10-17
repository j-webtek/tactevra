"""Bind the retained-start entry bridge to the static-camera collision roster."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from rocell.application._pinned_model import load_pinned_urdf
from rocell.application.static_simulation_context import (
    load_static_simulation_context,
    static_simulation_context_hashes,
)
from rocell.simulation.collision import (
    CollisionBindingMode,
    audit_collision_geometry,
    build_roarm_m3_static_overhead_collision_contract,
)

from .current_start_entry_bridge import run as run_entry_bridge
from .scene_observation import canonical_hash


SCHEMA = "rocell.current_start_entry_collision_intake.v1"
STATUS = "BLOCKED_STATIC_OVERHEAD_INSTALLED_COLLISION_PROFILE_REQUIRED"


def run(
    intake: Mapping[str, Any], *, workspace: Path, profile_path: Path
) -> dict[str, Any]:
    """Emit exact installed-geometry slots for the sampled entry bridge."""

    bridge = run_entry_bridge(intake, workspace=workspace, profile_path=profile_path)
    if bridge.get("status") != (
        "REFERENCE_ENTRY_BRIDGE_SAMPLED_COLLISION_EVIDENCE_REQUIRED"
    ):
        raise ValueError("static collision intake requires the reviewed entry bridge")
    context = load_static_simulation_context(workspace)
    loaded = load_pinned_urdf(
        context.scenario.model_path, context.scenario.model_sha256
    )
    contract = build_roarm_m3_static_overhead_collision_contract(
        loaded.model, context.scene
    )
    audit = audit_collision_geometry(contract)
    requirements_by_mode = {
        mode.value: [
            item.body_id for item in contract.requirements if item.binding_mode is mode
        ]
        for mode in CollisionBindingMode
    }
    configuration_ids = requirements_by_mode[
        CollisionBindingMode.CONFIGURATION_SAMPLED.value
    ]
    sample_count = bridge.get("sample_count")
    if not isinstance(sample_count, int) or sample_count < 2:
        raise ValueError("entry bridge must contain at least two samples")
    core = {
        "schema": SCHEMA,
        "status": STATUS,
        "scope": "OFFLINE_STATIC_OVERHEAD_COLLISION_EVIDENCE_INTAKE_ONLY",
        "entry_bridge_report_sha256": bridge["report_sha256"],
        "entry_bridge_sample_count": sample_count,
        "entry_bridge_adjacent_segment_count": sample_count - 1,
        "static_context_source_sha256": dict(static_simulation_context_hashes(context)),
        "kinematic_model_sha256": loaded.sha256,
        "collision_contract": contract.to_dict(),
        "collision_contract_sha256": contract.content_hash,
        "collision_geometry_audit": audit.to_dict(),
        "required_body_ids_by_binding_mode": requirements_by_mode,
        "required_configuration_body_ids": configuration_ids,
        "required_configuration_geometry_binding_count": (
            sample_count * len(configuration_ids)
        ),
        "required_configuration_sweep_envelope_count": (
            (sample_count - 1) * len(configuration_ids)
        ),
        "static_camera_profile_separation": {
            "architecture": "RIGID_STATIC_OVERHEAD_EYE_TO_HAND",
            "fixed_body_ids": [
                "installation:static_camera_support",
                "installation:static_camera_module",
                "installation:static_camera_connector",
                "installation:static_camera_cable",
            ],
            "arm_camera_body_ids_present": False,
            "attachment_profile": bridge["frozen_hypothesis"]["tool_case_id"],
        },
        "blockers": [
            "ACCEPTED_MEASURED_STATIC_OVERHEAD_COLLISION_PROFILE_REQUIRED",
            "ACCEPTED_GLOBAL_PAIR_EXCLUSIONS_REQUIRED",
            "ACCEPTED_MEASURED_CLEARANCE_AND_UNCERTAINTY_POLICY_REQUIRED",
            "CONSERVATIVE_INTER_SAMPLE_SWEEP_PROOF_REQUIRED_AFTER_DISCRETE_CLEARANCE",
            "COMMISSIONED_START_AND_FRAME_CALIBRATION_REQUIRED_FOR_EXECUTION",
        ],
        "next_required_stage": (
            "MEASURE_STATIC_OVERHEAD_PROFILE_THEN_EVALUATE_ALL_ENTRY_SAMPLES"
        ),
        "collision_screening_executed": False,
        "continuous_path_proven": False,
        "physical_execution_authorized": False,
        "controller_commands": [],
        "transport_writes": 0,
        "hardware_access": False,
    }
    return {**core, "report_sha256": canonical_hash(core)}


__all__ = ["SCHEMA", "STATUS", "run"]
