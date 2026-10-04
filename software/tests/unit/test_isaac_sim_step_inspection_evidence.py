from __future__ import annotations

import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
RECEIPT = (
    WORKSPACE / "software/integrations/isaac_sim/evidence"
    / "roarm_m3_step_inspection_20260929.json"
)


def _load() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_step_inspection_receipt_is_canonical_and_zero_authority() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    assert receipt["evidence_class"] == "PINNED_CAD_INSPECTION_ONLY"
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_step_inspection_receipt_binds_official_archive_and_member() -> None:
    source = _load()["source"]
    assert source == {
        "archive_name": "RoArm-M3_STEP_260310.zip",
        "archive_sha256": "1e2111145276aac14e521f47990fc41de87e2e735623d115a39cc176c9762da2",
        "archive_size_bytes": 5_117_961,
        "archive_url": "https://files.waveshare.com/wiki/RoArm-M3/RoArm-M3_STEP_260310.zip",
        "redistribution": "external_only_license_scope_unconfirmed",
        "step_member": "RoArm-M3_STEP/RoArm-M3.step",
        "step_sha256": "728eb52f0bdd32dc0b907c9bb983d3d0b8adf7a5ea945949785a6e496f5089ff",
        "step_size_bytes": 26_671_289,
    }


def test_step_inspection_receipt_binds_converter_and_repeatable_usd() -> None:
    receipt = _load()
    assert receipt["converter"]["identity"] == (
        "omni.kit.converter.hoops_core 512.0.0 "
        "hoops_cad_converter 11.3.6+v11-3-6.4666.4a1c16a1.gl"
    )
    files = receipt["external_files"]
    assert files == [{
        "path": "roarm_m3_official.usda",
        "sha256": "cfcd4e6170350d948de1976164665ddde99cfad457b72730f7ffcbdd119496d3",
        "size_bytes": 26_872_057,
    }]
    assert canonical_sha256(files) == receipt["external_files_manifest_sha256"]


def test_step_inspection_receipt_has_exact_stage_inventory() -> None:
    stage = _load()["stage"]
    assert stage == {
        "assembly_bounds_mm": {
            "minimum": [-48.994985, -42.71, 0.0],
            "maximum": [356.851785, 42.51, 389.380716],
        },
        "collision_prim_count": 0,
        "default_prim": "/roarm_m3_official",
        "mesh_count": 770,
        "meters_per_unit": 0.001,
        "named_product_count": 1297,
        "prim_count": 2893,
        "unique_product_id_count": 745,
        "up_axis": "Z",
    }


def test_collision_seeds_are_upstream_but_unassigned() -> None:
    receipt = _load()
    components = receipt["candidate_collision_seed_components"]
    assert [item["product_id"] for item in components] == [
        "AL-BASE", "AL-SHOULDER", "AL-ELBOW-A", "AL-ELBOW-B",
    ]
    assert all(item["provenance"] == "upstream_step_assembly_component" for item in components)
    assert all(item["dynamic_link_assignment"] is None for item in components)
    assert all(item["status"] == "INSPECTION_ONLY_UNASSIGNED_TO_DYNAMIC_LINK" for item in components)


def test_step_inspection_does_not_admit_collision_or_clearance() -> None:
    receipt = _load()
    assert receipt["dynamic_link_assignment_admissible"] is False
    assert receipt["collision_geometry_admissible"] is False
    assert receipt["clearance_replay_admissible"] is False
    assert set(receipt["blockers"]) == {
        "CAD_ASSEMBLY_POSE_NOT_BOUND_TO_URDF_JOINT_STATE",
        "CAD_COMPONENTS_NOT_ASSIGNED_TO_DYNAMIC_LINKS",
        "COLLISION_REDUCTION_NOT_REVIEWED",
        "TOOL_GEOMETRY_MISSING",
        "CAMERA_SUPPORT_GEOMETRY_MISSING",
        "ROBOT_PLACEMENT_NOMINAL_UNMEASURED",
        "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
    }
