from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
RECEIPT = (
    WORKSPACE / "software/integrations/isaac_sim/evidence"
    / "rc03_nominal_rigid_scene_20260929.json"
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_scene_receipt_is_hash_bound_and_zero_authority() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    assert receipt["evidence_class"] == "RIGID_SCENE_COMPOSITION_ONLY"
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_scene_receipt_binds_current_governed_sources() -> None:
    receipt = _load()
    bindings = receipt["source_bindings"]
    assert bindings["nominal_target_profiles_sha256"] == _digest(
        WORKSPACE / "software/config/nominal_target_profiles.json"
    )
    assert bindings["simulation_hardware_profile_sha256"] == _digest(
        WORKSPACE / "software/config/simulation_hardware_profile.json"
    )
    assert bindings["robot_import_receipt_file_sha256"] == _digest(
        WORKSPACE / "software/integrations/isaac_sim/evidence/roarm_m3_urdf_import_20260929.json"
    )
    scene_sources = receipt["source_scene"]["source_hashes"]
    rc03 = WORKSPACE / "active-project/RoCell_v0_3"
    assert scene_sources == {
        "config/workcell_layout.json": _digest(rc03 / "config/workcell_layout.json"),
        "fiducials/apriltag_map.json": _digest(rc03 / "fiducials/apriltag_map.json"),
    }


def test_scene_receipt_has_exact_rigid_projection_and_composed_robot() -> None:
    receipt = _load()
    assert receipt["design_revision"] == "RC03-INT-R1"
    assert receipt["stage"] == {
        "default_prim": "/RC03", "meters_per_unit": 1.0, "up_axis": "Z",
    }
    assert len(receipt["obstacles"]) == 6
    assert len({item["obstacle_id"] for item in receipt["obstacles"]}) == 6
    assert len(receipt["fiducials"]) == 6
    assert {item["tag_id"] for item in receipt["fiducials"]} == set(range(6))
    assert receipt["nominal_h_target"]["center_board_mm"] == [216.55, 154.0, 21.0]
    validation = receipt["stage_validation"]
    assert len(validation["collision_prim_paths"]) == 6
    assert validation["composed_robot_joint_count"] == 6
    assert len(validation["composed_robot_joint_paths"]) == 6
    assert validation["h_target_prim_valid"] is True


def test_scene_receipt_binds_external_stage_manifest() -> None:
    receipt = _load()
    files = receipt["external_files"]
    assert files == [{
        "path": "rc03_nominal_rigid_scene.usda",
        "sha256": "77600a60975daaa4d58a20f597851a5d397ed9c452d44ab47ea1832bf42e0f35",
        "size_bytes": 6847,
    }]
    assert canonical_sha256(files) == receipt["external_files_manifest_sha256"]


def test_scene_receipt_blocks_collision_and_hover_claims() -> None:
    receipt = _load()
    assert receipt["collision_query_admissible"] is False
    assert receipt["hover_replay_admissible"] is False
    assert set(receipt["blockers"]) == {
        "ARM_LINK_COLLISION_GEOMETRY_MISSING",
        "ARM_INERTIAL_PROPERTIES_INVALID",
        "CAMERA_SUPPORT_COLLISION_GEOMETRY_MISSING",
        "FIXTURE_SOLID_HEIGHTS_REPLACED_BY_35MM_PROXIES",
        "ROBOT_PLACEMENT_NOMINAL_UNMEASURED",
        "TOOL_COLLISION_GEOMETRY_MISSING",
        "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
    }
    assert "no_dynamics_or_trajectory_replay" in receipt["limitations"]
    assert "no_clearance_contact_render_or_physical_qualification" in receipt["limitations"]
