from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
REVIEW_SOURCE = (
    ROOT / "software/integrations/isaac_sim/nominal_route_proof_input_review.py"
)
PROPOSAL_SOURCE = (
    ROOT / "software/integrations/isaac_sim/nominal_route_proof_input_proposal.py"
)
PREFLIGHT_SOURCE = (
    ROOT / "software/integrations/isaac_sim/nominal_route_native_binding_preflight.py"
)
MESH_RECEIPT = (
    ROOT / "software/integrations/isaac_sim/evidence/"
    "roarm_m3_upstream_link_mesh_binding_20261004.json"
)
URDF = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _modules():
    return (
        _load_module("arm259_for_review", PROPOSAL_SOURCE),
        _load_module("arm260_review", REVIEW_SOURCE),
    )


def _bundle():
    producer, reviewer = _modules()
    receipt = producer._load_object(MESH_RECEIPT)
    urdf_bytes = URDF.read_bytes()
    mesh_file_hash = producer._file_sha(MESH_RECEIPT)
    urdf_hash = producer._file_sha(URDF)
    proposal = producer.build_proposal(
        receipt,
        urdf_bytes,
        mesh_receipt_file_sha256=mesh_file_hash,
        urdf_file_sha256=urdf_hash,
    )
    return reviewer, proposal, receipt, urdf_bytes, mesh_file_hash, urdf_hash


def _review(proposal=None):
    reviewer, original, receipt, urdf_bytes, mesh_file_hash, urdf_hash = _bundle()
    selected = original if proposal is None else proposal
    return reviewer.build_review(
        selected,
        receipt,
        urdf_bytes,
        proposal_file_sha256="1" * 64,
        mesh_receipt_file_sha256=mesh_file_hash,
        urdf_file_sha256=urdf_hash,
    )


def _rehash_proposal(proposal, reviewer):
    profile = proposal["sphere_profile_proposal"]
    profile_core = dict(profile)
    profile_core.pop("profile_sha256", None)
    profile["profile_sha256"] = reviewer._sha(profile_core)
    policy = proposal["pair_policy_proposal"]
    policy_core = dict(policy)
    policy_core.pop("policy_sha256", None)
    policy["policy_sha256"] = reviewer._sha(policy_core)
    proposal_core = dict(proposal)
    proposal_core.pop("proposal_sha256", None)
    proposal["proposal_sha256"] = reviewer._sha(proposal_core)


def test_arm260_independently_certifies_both_exact_proof_inputs():
    result = _review()

    assert result["status"] == "ACCEPTED_FOR_NATIVE_BINDING_IMPLEMENTATION"
    assert result["certified_sphere_profile"]["status"] == (
        "CERTIFIED_FOR_SIMULATION_CONTINUOUS_CLEARANCE"
    )
    assert result["accepted_pair_policy"]["status"] == (
        "ACCEPTED_FOR_SIMULATION_CONTINUOUS_CLEARANCE"
    )
    assert len(result["certified_sphere_profile"]["link_spheres"]) == 7
    assert len(result["accepted_pair_policy"]["accepted_exclusion_pairs"]) == 6
    assert all(
        "proposal_requires" not in item
        for item in result["certified_sphere_profile"]["limitations"]
    )
    assert all(
        "proposal_requires" not in item
        for item in result["accepted_pair_policy"]["limitations"]
    )


def test_arm260_certified_outputs_satisfy_arm258_proof_input_gate():
    result = _review()
    preflight = _load_module("arm258_gate_for_review", PREFLIGHT_SOURCE)

    assert preflight._sphere_profile_ready(result["certified_sphere_profile"])
    assert preflight._proof_policy_ready(result["accepted_pair_policy"])


def test_arm260_records_complete_independent_findings():
    findings = _review()["review_findings"]

    assert findings == {
        "all_seven_source_mesh_bounds_reopened": True,
        "all_seven_sphere_centers_and_upward_rounded_radii_recomputed": True,
        "all_fifty_six_aabb_corners_contained": True,
        "all_six_direct_urdf_adjacency_pairs_rederived": True,
        "no_srdf_never_or_sample_derived_exclusion_present": True,
        "simulation_model_only_scope_preserved": True,
        "zero_hardware_and_physical_authority_preserved": True,
    }


def test_arm260_rejects_self_consistent_shrunken_sphere():
    reviewer, proposal, *_ = _bundle()
    changed = copy.deepcopy(proposal)
    changed["sphere_profile_proposal"]["link_spheres"][0]["radius_mm"] -= 0.001
    _rehash_proposal(changed, reviewer)

    with pytest.raises(ValueError, match="sphere profile"):
        _review(changed)


def test_arm260_rejects_self_consistent_non_direct_pair():
    reviewer, proposal, *_ = _bundle()
    changed = copy.deepcopy(proposal)
    changed["pair_policy_proposal"]["accepted_exclusion_pairs"].append(
        ["robot:base_link", "robot:link3"]
    )
    _rehash_proposal(changed, reviewer)

    with pytest.raises(ValueError, match="pair policy"):
        _review(changed)


def test_arm260_rejects_unhashed_proposal_drift():
    reviewer, proposal, *_ = _bundle()
    changed = copy.deepcopy(proposal)
    changed["launch_admitted"] = True

    with pytest.raises(ValueError, match="proposal hash"):
        _review(changed)


def test_arm260_grants_no_launch_attempt_or_physical_authority():
    result = _review()

    assert result["certified_inputs_emitted"] is True
    assert result["native_binding_admitted"] is False
    assert result["launch_admitted"] is False
    assert result["attempt_consumed"] is False
    assert result["isaac_started"] is False
    assert result["trajectory_playback"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False
    assert result["controller_commands"] == []
    assert result["wire_commands"] == []
    assert result["gate_promotions"] == []


def test_arm260_import_has_no_isaac_or_hardware_side_effect():
    source = REVIEW_SOURCE.read_text(encoding="utf-8")

    assert "from isaacsim import" not in source
    assert "SimulationApp(" not in source
    assert "serial" not in source
