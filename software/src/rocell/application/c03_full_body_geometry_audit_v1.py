"""Audit full-body geometry inputs for the exact C03 route without screening it."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .c03_route_collision_handoff_v1 import prepare_c03_route_collision_handoff_v1
from .collision_readiness import assess_current_collision_readiness
from .context import SimulationContext
from .installed_collision_measurement_manifest_v1 import (
    build_installed_collision_nominal_proxy_audit_v1,
    build_installed_collision_nominal_source_inventory_v1,
)


SCHEMA = "tactevra.c03_full_body_geometry_audit.v1"
MESH_BINDING_SCHEMA = "tactevra.isaac_sim_upstream_link_mesh_binding.v1"
MESH_REDUCTION_SCHEMA = "tactevra.isaac_sim_link_mesh_reduction.v1"
EXPECTED_MESH_BINDING_RECEIPT_SHA256 = (
    "dbb8b56a602ac4c2b69073af23d61700aee12c0153080bdf58b7f5990b92646e"
)
EXPECTED_MESH_REDUCTION_RECEIPT_SHA256 = (
    "ef8d011314df145afe5db43310457671082b276023191aea47287b3ef87a7178"
)
ROBOT_LINK_BODY_IDS = {
    "base_link": "robot:base_link",
    "link1": "robot:link1",
    "link2": "robot:link2",
    "link3": "robot:link3",
    "link4": "robot:link4",
    "link5": "robot:link5",
    "gripper_link": "robot:gripper",
}


class C03FullBodyGeometryAuditV1Error(ValueError):
    """A retained geometry input is malformed, mutated, or authority bearing."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _verified_receipt(
    value: Mapping[str, Any], *, schema: str, expected_receipt: str, label: str
) -> dict[str, Any]:
    document = dict(value)
    claimed = document.pop("receipt_sha256", None)
    if (
        value.get("schema") != schema
        or claimed != expected_receipt
        or claimed != _sha256(document)
    ):
        raise C03FullBodyGeometryAuditV1Error(f"{label} identity differs")
    if (
        value.get("hardware_access") is not False
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
        or value.get("physical_authority") is not False
    ):
        raise C03FullBodyGeometryAuditV1Error(f"{label} carries authority")
    return dict(value)


def assess_c03_full_body_geometry_readiness_v1(
    result: Mapping[str, Any],
    context: SimulationContext,
    *,
    mesh_binding: Mapping[str, Any],
    mesh_reduction: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind candidate geometry identities and enumerate blockers before screening."""

    handoff = prepare_c03_route_collision_handoff_v1(result, context)
    binding = _verified_receipt(
        mesh_binding,
        schema=MESH_BINDING_SCHEMA,
        expected_receipt=EXPECTED_MESH_BINDING_RECEIPT_SHA256,
        label="mesh binding",
    )
    reduction = _verified_receipt(
        mesh_reduction,
        schema=MESH_REDUCTION_SCHEMA,
        expected_receipt=EXPECTED_MESH_REDUCTION_RECEIPT_SHA256,
        label="mesh reduction",
    )
    source = reduction.get("source_bindings")
    if (
        not isinstance(source, Mapping)
        or source.get("mesh_receipt_sha256") != binding["receipt_sha256"]
        or reduction.get("candidate_profile_installable") is not False
        or reduction.get("clearance_replay_admissible") is not False
        or reduction.get("reduced_collision_geometry_admissible") is not False
    ):
        raise C03FullBodyGeometryAuditV1Error(
            "mesh reduction does not retain its fail-closed source binding"
        )

    rows = reduction.get("links")
    if not isinstance(rows, list):
        raise C03FullBodyGeometryAuditV1Error("mesh reduction links must be an array")
    candidate_links: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise C03FullBodyGeometryAuditV1Error("mesh reduction link is malformed")
        link_name = row.get("link_name")
        components = row.get("components")
        if (
            link_name not in ROBOT_LINK_BODY_IDS
            or link_name in candidate_links
            or not isinstance(components, list)
            or not components
        ):
            raise C03FullBodyGeometryAuditV1Error(
                "mesh reduction link inventory differs"
            )
        candidate_links[str(link_name)] = {
            "body_id": ROBOT_LINK_BODY_IDS[str(link_name)],
            "link_name": link_name,
            "candidate_primitive_count": len(components),
            "candidate_only": True,
        }
    if set(candidate_links) != set(ROBOT_LINK_BODY_IDS):
        raise C03FullBodyGeometryAuditV1Error("mesh reduction omits a robot link")

    readiness = assess_current_collision_readiness(context)
    required = {item.body_id for item in readiness.contract.requirements}
    candidate_body_ids = {row["body_id"] for row in candidate_links.values()}
    proxy_audit = build_installed_collision_nominal_proxy_audit_v1(context)
    static_proxy_ids = {
        "workcell:board_solid",
        "workcell:keyboard",
        "workcell:phone",
        "workcell:station:keyboard_left",
        "workcell:station:keyboard_right",
        "workcell:station:phone_tcp",
    }
    if not proxy_audit["all_nominal_solids_contained"]:
        raise C03FullBodyGeometryAuditV1Error(
            "nominal environment proxies do not contain their source solids"
        )
    source_inventory = build_installed_collision_nominal_source_inventory_v1(context)
    source_rows = {
        row["body_id"]: row for row in source_inventory["bodies"]
    }
    source_only_ids = sorted(required - candidate_body_ids - static_proxy_ids)
    if set(source_rows) != required:
        raise C03FullBodyGeometryAuditV1Error(
            "nominal source inventory differs from the active body contract"
        )
    configuration_sampled_missing_ids = sorted(
        item.body_id
        for item in readiness.contract.requirements
        if item.binding_mode.value == "CONFIGURATION_SAMPLED"
    )
    blockers = [
        "CANDIDATE_ROBOT_BOXES_NOT_QUALIFIED",
        "ROBOT_PLACEMENT_NOMINAL_UNMEASURED",
        "SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED",
        "CONTACT_TOOL_TRANSFORM_AND_ENVELOPE_NOT_INSTALLED",
        "BASE_AND_FACTORY_CLAMP_GEOMETRY_NOT_INSTALLED",
        "CAMERA_ATTACHMENT_GEOMETRY_NOT_INSTALLED",
        "MOVING_CAMERA_CABLE_CONFIGURATION_SAMPLES_MISSING",
        "INSTALLED_CLEARANCE_POLICY_PENDING",
    ]
    core = {
        "schema": SCHEMA,
        "source_result_receipt_sha256": result["receipt_sha256"],
        "source_handoff_sha256": handoff["c03_collision_handoff_sha256"],
        "mesh_binding_receipt_sha256": binding["receipt_sha256"],
        "mesh_reduction_receipt_sha256": reduction["receipt_sha256"],
        "nominal_source_inventory_sha256": source_inventory["content_sha256"],
        "nominal_proxy_audit_sha256": proxy_audit["content_sha256"],
        "route_waypoint_count": handoff["trajectory_sample_count"],
        "required_body_count": len(required),
        "candidate_robot_body_count": len(candidate_body_ids),
        "candidate_robot_primitive_count": sum(
            row["candidate_primitive_count"] for row in candidate_links.values()
        ),
        "candidate_robot_bodies": [candidate_links[key] for key in sorted(candidate_links)],
        "nominal_static_proxy_body_ids": sorted(static_proxy_ids),
        "source_only_body_ids": source_only_ids,
        "configuration_sampled_missing_body_ids": configuration_sampled_missing_ids,
        "blockers": blockers,
        "full_body_geometry_complete": False,
        "candidate_profile_installable": False,
        "collision_screen_executed": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "full_body_geometry_audit_sha256": _sha256(core)}


__all__ = [
    "C03FullBodyGeometryAuditV1Error",
    "SCHEMA",
    "assess_c03_full_body_geometry_readiness_v1",
]
