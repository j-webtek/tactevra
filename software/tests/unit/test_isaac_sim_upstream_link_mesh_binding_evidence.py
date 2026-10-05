from __future__ import annotations

import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
RECEIPT = (
    WORKSPACE / "software/integrations/isaac_sim/evidence"
    / "roarm_m3_upstream_link_mesh_binding_20261004.json"
)


def _load() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_receipt_is_canonical_and_zero_authority() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    assert receipt["evidence_class"] == "UPSTREAM_LINK_MESH_BINDING_ONLY"
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_receipt_binds_the_pinned_official_sources() -> None:
    bindings = _load()["source_bindings"]
    assert bindings == {
        "upstream_repository": "https://github.com/waveshareteam/roarm_ws",
        "upstream_commit": "40dbd84b553695212fab713e8465f817ba95454d",
        "upstream_tree_oid_sha1": "3a1d24388e15b318ba0c5305a94b5140b5b239bd",
        "xacro_git_path": (
            "src/roarm_main/roarm_description/urdf/roarm_m3/roarm_m3.xacro"
        ),
        "xacro_sha256": "b6333849d0e377008eee0a87a5b8cdcf44f7a73edf3d7600e95506a023a234b6",
    }


def test_xacro_has_seven_identical_visual_collision_mesh_bindings() -> None:
    receipt = _load()
    assert receipt["xacro_binding"] == {
        "link_count": 7,
        "mesh_origin_rpy": [0.0, 0.0, 0.0],
        "mesh_origin_xyz": [0.0, 0.0, 0.0],
        "mesh_scale": [0.001, 0.001, 0.001],
        "visual_and_collision_references_identical": True,
    }
    meshes = {item["link_name"]: item for item in receipt["mesh_inventory"]}
    assert {name: item["sha256"] for name, item in meshes.items()} == {
        "base_link": "55cbfcc2cfb995ab11d8a6ce7c2132283721b9c69cd05b4c7b9d6404e9d8fded",
        "link1": "022fdd2df4fa57748f56337fb1b3b3cce81dd116e0f608ccab51d6f1eacb552c",
        "link2": "5acd32a9f662221deb58ea2ca338c5d6726cbcd7664e7dcdb93bac722820b025",
        "link3": "80c4e9b1084bf1c7d975398eb11e7ba4e7dc69e62ff4adefcac38a0e0f5a4069",
        "link4": "bb334cafafa5f5adeedb4d430b325b436eafa833fa851ea782d9c785698f8c09",
        "link5": "1d63f374a78c1419b21eec63fa8efeef40d0d42ca89c5de3ceb0d86476d9c7eb",
        "gripper_link": "7946a374e24a2f467a0581b4946e0ec41b1b86a92f070bc00aa9bced1bf65a56",
    }


def test_topology_requires_reduced_collision_geometry() -> None:
    receipt = _load()
    assert receipt["mesh_totals"] == {
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
    assert receipt["raw_mesh_collision_admissible"] is False
    assert receipt["reduced_collision_geometry_admissible"] is False
    assert receipt["clearance_replay_admissible"] is False
    assert {
        "RAW_VISUAL_TRIANGLE_MESHES_ARE_NOT_REDUCED_COLLISION_SHAPES",
        "LINK1_AND_LINK5_MESHES_ARE_NOT_WATERTIGHT",
        "GRIPPER_LEFT_MESH_IS_UNREFERENCED_BY_XACRO",
        "MESH_TO_GOVERNED_ROBOT_FRAME_NOT_PROVEN_HERE",
    } <= set(receipt["blockers"])
