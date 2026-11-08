from __future__ import annotations

import copy
import importlib.util
import itertools
import math
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "software/integrations/isaac_sim/nominal_route_proof_input_proposal.py"
MESH_RECEIPT = (
    ROOT / "software/integrations/isaac_sim/evidence/"
    "roarm_m3_upstream_link_mesh_binding_20261004.json"
)
URDF = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"


def _module():
    spec = importlib.util.spec_from_file_location("arm259_proposal", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build():
    module = _module()
    return module.build_proposal(
        module._load_object(MESH_RECEIPT),
        URDF.read_bytes(),
        mesh_receipt_file_sha256=module._file_sha(MESH_RECEIPT),
        urdf_file_sha256=module._file_sha(URDF),
    )


def test_arm259_builds_seven_review_only_conservative_spheres():
    result = _build()
    profile = result["sphere_profile_proposal"]

    assert result["status"] == "READY_FOR_INDEPENDENT_PROOF_INPUT_REVIEW"
    assert profile["status"] == (
        "PROPOSED_FOR_INDEPENDENT_SIMULATION_CONTINUOUS_CLEARANCE_REVIEW"
    )
    assert [row["link_name"] for row in profile["link_spheres"]] == [
        "robot:base_link",
        "robot:link1",
        "robot:link2",
        "robot:link3",
        "robot:link4",
        "robot:link5",
        "robot:gripper",
    ]
    assert result["certified_inputs_emitted"] is False
    assert result["native_binding_admitted"] is False


def test_arm259_every_retained_aabb_corner_is_inside_its_sphere():
    profile = _build()["sphere_profile_proposal"]

    for row in profile["link_spheres"]:
        minimum, maximum = row["source_bounds_mm"]
        center = row["local_center_mm"]
        radius = row["radius_mm"]
        for corner in itertools.product(*zip(minimum, maximum)):
            distance = math.sqrt(
                sum(
                    (coordinate - origin) ** 2
                    for coordinate, origin in zip(corner, center)
                )
            )
            assert distance <= radius
        assert round(radius, 6) == radius


def test_arm259_pair_policy_contains_only_six_direct_urdf_adjacencies():
    policy = _build()["pair_policy_proposal"]

    assert policy["status"] == (
        "PROPOSED_FOR_INDEPENDENT_SIMULATION_CONTINUOUS_CLEARANCE_REVIEW"
    )
    assert policy["accepted_exclusion_pairs"] == [
        ["robot:base_link", "robot:link1"],
        ["robot:gripper", "robot:link5"],
        ["robot:link1", "robot:link2"],
        ["robot:link2", "robot:link3"],
        ["robot:link3", "robot:link4"],
        ["robot:link4", "robot:link5"],
    ]
    assert policy["finite_sample_evidence_used_for_exclusion"] is False


def test_arm259_proposal_is_deterministic_and_hash_bound():
    first = _build()
    second = _build()

    assert first == second
    unsigned = dict(first)
    claimed = unsigned.pop("proposal_sha256")
    assert claimed == _module()._sha(unsigned)


def test_arm259_proposals_do_not_self_satisfy_arm258_certification_gate():
    arm258_path = (
        ROOT
        / "software/integrations/isaac_sim/nominal_route_native_binding_preflight.py"
    )
    spec = importlib.util.spec_from_file_location("arm258_gate", arm258_path)
    assert spec is not None and spec.loader is not None
    arm258 = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = arm258
    spec.loader.exec_module(arm258)
    proposal = _build()

    assert arm258._sphere_profile_ready(proposal["sphere_profile_proposal"]) is False
    assert arm258._proof_policy_ready(proposal["pair_policy_proposal"]) is False


def test_arm259_rejects_mesh_receipt_drift():
    module = _module()
    receipt = module._load_object(MESH_RECEIPT)
    changed = copy.deepcopy(receipt)
    changed["mesh_inventory"][0]["local_bounds_source_units"][0][0] -= 1.0

    with pytest.raises(module.ProofInputProposalError, match="receipt hash"):
        module.build_proposal(
            changed,
            URDF.read_bytes(),
            mesh_receipt_file_sha256=module._file_sha(MESH_RECEIPT),
            urdf_file_sha256=module._file_sha(URDF),
        )


def test_arm259_rejects_urdf_identity_drift():
    module = _module()

    with pytest.raises(module.ProofInputProposalError, match="URDF file identity"):
        module.build_proposal(
            module._load_object(MESH_RECEIPT),
            URDF.read_bytes(),
            mesh_receipt_file_sha256=module._file_sha(MESH_RECEIPT),
            urdf_file_sha256="f" * 64,
        )


def test_arm259_import_has_no_isaac_or_hardware_side_effect():
    source = SOURCE.read_text(encoding="utf-8")

    assert "from isaacsim import" not in source
    assert "SimulationApp(" not in source
    assert "serial" not in source
    result = _build()
    assert result["isaac_started"] is False
    assert result["attempt_consumed"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False
    assert result["controller_commands"] == []
    assert result["wire_commands"] == []
