from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
RECEIPT = (
    WORKSPACE / "software/integrations/isaac_sim/evidence"
    / "roarm_m3_step_link_membership_candidates_20260929.json"
)


def _load() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_membership_receipt_is_canonical_and_zero_authority() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    assert receipt["evidence_class"] == "CAD_LINK_MEMBERSHIP_CANDIDATES_ONLY"
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_membership_receipt_binds_current_inputs() -> None:
    bindings = _load()["source_bindings"]
    assert bindings["cad_usd_sha256"] == (
        "cfcd4e6170350d948de1976164665ddde99cfad457b72730f7ffcbdd119496d3"
    )
    pose_receipt = (
        WORKSPACE / "software/integrations/isaac_sim/evidence"
        / "roarm_m3_step_pose_binding_20260929.json"
    )
    assert bindings["pose_receipt_file_sha256"] == _digest(pose_receipt)
    assert bindings["pose_receipt_sha256"] == (
        "3817f28d9171ee3cb33d024f3f31e57495b02fb383ba60277953f6148ba00f3f"
    )
    assert bindings["urdf_sha256"] == _digest(
        WORKSPACE / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    )


def test_complete_direct_component_partition_is_retained() -> None:
    receipt = _load()
    inventory = receipt["inventory"]
    components = receipt["components"]
    assert inventory == {
        "ambiguous_component_count": 114,
        "complete_mesh_partition": True,
        "covered_mesh_count": 770,
        "direct_component_count": 162,
        "joint_crossing_component_count": 19,
        "reviewed_assignment_count": 0,
        "stage_mesh_count": 770,
        "unambiguous_candidate_count": 48,
    }
    assert len(components) == 162
    assert len({item["instance_path"] for item in components}) == 162
    assert sum(item["mesh_count"] for item in components) == 770
    assert all(len(item["nearest_candidates"]) == 2 for item in components)
    assert all(item["reviewed_dynamic_link_assignment"] is None for item in components)


def test_candidate_distribution_and_joint_crossings_are_stable() -> None:
    components = _load()["components"]
    nearest = Counter(item["nearest_candidates"][0]["link_name"] for item in components)
    assert nearest == {
        "base_link": 33,
        "link1": 35,
        "link2": 27,
        "link3": 26,
        "link4": 11,
        "link5": 23,
        "gripper_link": 7,
    }
    crossing_products = {
        item["product_id"] for item in components if item["crossed_joint_origins"]
    }
    assert {
        "ST3215", "ST3215_1", "ST3215_2", "ST3215_3", "ST3215_4",
        "SCS215", "SCS215_1", "AL-SHOULDER", "AL-ELBOW-A",
    } <= crossing_products


def test_candidates_do_not_admit_link_assignment_or_collision() -> None:
    receipt = _load()
    assert receipt["dynamic_link_assignment_admissible"] is False
    assert receipt["collision_geometry_admissible"] is False
    assert receipt["clearance_replay_admissible"] is False
    assert set(receipt["blockers"]) == {
        "FIXED_POSE_STEP_HAS_NO_REVIEWED_JOINT_OR_MATE_GRAPH",
        "BASE_LINK_AND_LINK1_REQUIRE_MOTION_SEPARATION_EVIDENCE",
        "DISTAL_LINK5_AND_GRIPPER_REQUIRE_MOTION_SEPARATION_EVIDENCE",
        "JOINT_CROSSING_COMPONENT_GROUPS_REQUIRE_LEAF_LEVEL_REVIEW",
        "COLLISION_REDUCTION_NOT_REVIEWED",
        "TOOL_GEOMETRY_MISSING",
        "CAMERA_SUPPORT_GEOMETRY_MISSING",
        "ROBOT_PLACEMENT_NOMINAL_UNMEASURED",
        "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
    }
