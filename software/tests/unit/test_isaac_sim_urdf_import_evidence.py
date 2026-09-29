from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
RECEIPT = (
    WORKSPACE
    / "software/integrations/isaac_sim/evidence"
    / "roarm_m3_urdf_import_20260929.json"
)
URDF = WORKSPACE / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"


def _load() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_import_receipt_is_hash_bound_to_governed_urdf() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    assert hashlib.sha256(URDF.read_bytes()).hexdigest() == receipt["source"]["sha256"]
    assert receipt["source"]["sha256"] == (
        "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
    )


def test_import_receipt_maps_unique_links_and_movable_joints() -> None:
    receipt = _load()
    links = receipt["links"]
    joints = receipt["joints"]
    assert len(links) == 9
    assert len({link["name"] for link in links}) == len(links)
    assert {link["name"] for link in links} == {
        "world", "base_link", "link1", "link2", "link3", "link4", "link5",
        "gripper_link", "hand_tcp",
    }
    assert len(joints) == 6
    assert len({joint["name"] for joint in joints}) == len(joints)
    assert {joint["name"] for joint in joints} == {
        "base_link_to_link1", "link1_to_link2", "link2_to_link3",
        "link3_to_link4", "link4_to_link5", "link5_to_gripper_link",
    }
    assert all(joint["type"] == "PhysicsRevoluteJoint" for joint in joints)


def test_import_receipt_records_fixed_joint_collapse_explicitly() -> None:
    fixed = _load()["fixed_joint_resolution"]
    assert {entry["source_joint"] for entry in fixed} == {
        "world_to_base_link", "link5_to_hand_tcp",
    }
    assert all(entry["representation"] == "COLLAPSED_TO_NESTED_XFORM" for entry in fixed)
    assert {entry["source_child_link"] for entry in fixed} == {"base_link", "hand_tcp"}


def test_import_receipt_binds_external_usd_without_committing_it() -> None:
    receipt = _load()
    files = receipt["external_files"]
    assert canonical_sha256(files) == receipt["external_files_manifest_sha256"]
    assert files == [{
        "path": "roarm_m3_kinematic_40dbd84/roarm_m3_kinematic_40dbd84.usda",
        "sha256": "492ebbc606aa050251074736dbedd3fa5bb72ba6d8175269ba7c955f52e180b6",
        "size_bytes": 11450,
    }]
    assert not (WORKSPACE / files[0]["path"]).exists()


def test_import_receipt_is_kinematic_only_and_zero_authority() -> None:
    receipt = _load()
    assert receipt["schema"] == "tactevra.isaac_sim_urdf_import.v1"
    assert receipt["evidence_class"] == "KINEMATIC_IMPORT_ONLY"
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0
    assert set(receipt["limitations"]) == {
        "meshless_kinematic_projection",
        "zero_effort_and_velocity_placeholders",
        "no_inertial_or_dynamic_qualification",
        "no_fk_parity_result",
        "no_physical_qualification",
    }
