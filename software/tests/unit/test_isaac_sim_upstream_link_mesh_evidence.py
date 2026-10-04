from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
RECEIPT = (
    WORKSPACE / "software/integrations/isaac_sim/evidence"
    / "roarm_m3_upstream_link_meshes_20260929.json"
)


def _load() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_upstream_mesh_receipt_is_canonical_and_zero_authority() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    assert receipt["evidence_class"] == "UPSTREAM_LINK_MESH_GROUPING_ONLY"
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_upstream_mesh_receipt_binds_governed_sources() -> None:
    bindings = _load()["source_bindings"]
    assert bindings["upstream_commit"] == "40dbd84b553695212fab713e8465f817ba95454d"
    assert bindings["upstream_tree_oid_sha1"] == "3a1d24388e15b318ba0c5305a94b5140b5b239bd"
    assert bindings["xacro_sha256"] == (
        "b6333849d0e377008eee0a87a5b8cdcf44f7a73edf3d7600e95506a023a234b6"
    )
    assert bindings["governed_urdf_sha256"] == _digest(
        WORKSPACE / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    )
    step_receipt = (
        WORKSPACE / "software/integrations/isaac_sim/evidence"
        / "roarm_m3_step_inspection_20260929.json"
    )
    pose_receipt = (
        WORKSPACE / "software/integrations/isaac_sim/evidence"
        / "roarm_m3_step_pose_binding_20260929.json"
    )
    assert bindings["step_receipt_file_sha256"] == _digest(step_receipt)
    assert bindings["pose_receipt_file_sha256"] == _digest(pose_receipt)


def test_xacro_has_seven_identical_visual_collision_mesh_bindings() -> None:
    receipt = _load()
    assert receipt["xacro_binding"] == {
        "link_count": 7,
        "link_mesh_grouping_supported": True,
        "mesh_origin_rpy": [0.0, 0.0, 0.0],
        "mesh_origin_xyz": [0.0, 0.0, 0.0],
        "mesh_scale": [0.001, 0.001, 0.001],
        "visual_and_collision_references_identical": True,
    }
    meshes = {item["link_name"]: item for item in receipt["mesh_inventory"]}
    assert set(meshes) == {
        "base_link", "link1", "link2", "link3", "link4", "link5", "gripper_link",
    }
    assert {name: item["sha256"] for name, item in meshes.items()} == {
        "base_link": "55cbfcc2cfb995ab11d8a6ce7c2132283721b9c69cd05b4c7b9d6404e9d8fded",
        "link1": "022fdd2df4fa57748f56337fb1b3b3cce81dd116e0f608ccab51d6f1eacb552c",
        "link2": "5acd32a9f662221deb58ea2ca338c5d6726cbcd7664e7dcdb93bac722820b025",
        "link3": "80c4e9b1084bf1c7d975398eb11e7ba4e7dc69e62ff4adefcac38a0e0f5a4069",
        "link4": "bb334cafafa5f5adeedb4d430b325b436eafa833fa851ea782d9c785698f8c09",
        "link5": "1d63f374a78c1419b21eec63fa8efeef40d0d42ca89c5de3ceb0d86476d9c7eb",
        "gripper_link": "7946a374e24a2f467a0581b4946e0ec41b1b86a92f070bc00aa9bced1bf65a56",
    }


def test_mesh_union_matches_step_envelope_but_topology_requires_reduction() -> None:
    receipt = _load()
    totals = receipt["mesh_totals"]
    assert totals == {
        "connected_body_count": 19,
        "non_watertight_mesh_count": 2,
        "processed_vertex_count": 19030,
        "referenced_mesh_count": 7,
        "triangle_count": 38344,
        "unreferenced_mesh_paths": [
            "src/roarm_main/roarm_description/meshes/roarm_m3/gripper_left_link.stl"
        ],
        "watertight_mesh_count": 5,
    }
    comparison = receipt["home_pose_step_envelope_comparison"]
    assert comparison["pass"] is True
    assert comparison["maximum_absolute_bound_residual_mm"] == 1.910001
    assert comparison["threshold_mm"] == 2.0


def test_upstream_grouping_does_not_admit_raw_mesh_collision() -> None:
    receipt = _load()
    assert receipt["step_product_mapping_admissible"] is False
    assert receipt["raw_mesh_collision_admissible"] is False
    assert receipt["reduced_collision_geometry_admissible"] is False
    assert receipt["clearance_replay_admissible"] is False
    assert {
        "RAW_VISUAL_TRIANGLE_MESHES_ARE_NOT_REDUCED_COLLISION_SHAPES",
        "LINK1_AND_LINK5_MESHES_ARE_NOT_WATERTIGHT",
        "GRIPPER_LEFT_MESH_IS_UNREFERENCED_BY_XACRO",
        "SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED",
    } <= set(receipt["blockers"])
