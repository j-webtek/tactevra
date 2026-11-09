from __future__ import annotations

import copy
import ast
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
BINDING_SOURCE = (
    ROOT / "software/integrations/isaac_sim/nominal_route_native_sweep_binding.py"
)
REVIEW_SOURCE = (
    ROOT
    / "software/integrations/isaac_sim/nominal_route_native_sweep_binding_review.py"
)
URDF = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"


def _load_module(name: str, path: Path):
    integration = str(path.parent)
    if integration not in sys.path:
        sys.path.insert(0, integration)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bundle():
    binding_module = _load_module("arm262_for_arm263", BINDING_SOURCE)
    reviewer = _load_module("arm263_review", REVIEW_SOURCE)
    spheres = [
        {
            "link_name": name,
            "local_center_mm": [float(index), 0.0, 0.0],
            "radius_mm": float(index + 1),
        }
        for index, name in enumerate(binding_module.PROFILE_TO_NATIVE_LINK)
    ]
    profile_core = {
        "source_urdf_sha256": binding_module.EXPECTED_URDF_SHA256,
        "link_spheres": spheres,
    }
    profile = {
        **profile_core,
        "profile_sha256": binding_module._sha(profile_core),
    }
    policy_core = {
        "source_urdf_sha256": binding_module.EXPECTED_URDF_SHA256,
        "accepted_exclusion_pairs": [
            [left, right]
            for left, right in zip(
                tuple(binding_module.PROFILE_TO_NATIVE_LINK)[:-1],
                tuple(binding_module.PROFILE_TO_NATIVE_LINK)[1:],
            )
        ],
    }
    policy = {
        **policy_core,
        "policy_sha256": binding_module._sha(policy_core),
    }
    proof_core = {
        "schema": binding_module.REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_NATIVE_BINDING_IMPLEMENTATION",
        "native_binding_admitted": False,
        "certified_sphere_profile": profile,
        "accepted_pair_policy": policy,
    }
    proof = {**proof_core, "review_sha256": binding_module._sha(proof_core)}
    readiness_core = {
        "schema": binding_module.READINESS_SCHEMA,
        "status": "READY_TO_IMPLEMENT_NATIVE_BINDING",
        "blockers": [],
        "launch_admitted": False,
        "attempt_consumed": False,
        "certified_proof_inputs": {
            "arm260_review_sha256": proof["review_sha256"],
            "certified_sphere_profile_sha256": profile["profile_sha256"],
            "accepted_pair_policy_sha256": policy["policy_sha256"],
        },
    }
    readiness = {
        **readiness_core,
        "preflight_sha256": binding_module._sha(readiness_core),
    }
    binding_module.EXPECTED_READINESS_SHA256 = readiness["preflight_sha256"]
    binding_module.EXPECTED_REVIEW_SHA256 = proof["review_sha256"]
    binding_module.EXPECTED_PROFILE_SHA256 = profile["profile_sha256"]
    binding_module.EXPECTED_POLICY_SHA256 = policy["policy_sha256"]
    readiness_file_hash = "c" * 64
    proof_file_hash = "d" * 64
    source_bytes = BINDING_SOURCE.read_bytes()
    source_hash = binding_module._file_sha(BINDING_SOURCE)
    urdf_bytes = URDF.read_bytes()
    binding_module.EXPECTED_READINESS_FILE_SHA256 = readiness_file_hash
    binding_module.EXPECTED_REVIEW_FILE_SHA256 = proof_file_hash
    binding = binding_module.build_binding_definition(
        readiness,
        proof,
        readiness_file_sha256=readiness_file_hash,
        review_file_sha256=proof_file_hash,
        urdf_file_sha256=binding_module._file_sha(URDF),
        binding_source_file_sha256=source_hash,
        urdf_text=urdf_bytes.decode("utf-8"),
    )
    binding_file_hash = "e" * 64
    reviewer.EXPECTED_BINDING_SHA256 = binding["binding_sha256"]
    reviewer.EXPECTED_BINDING_FILE_SHA256 = binding_file_hash
    reviewer.EXPECTED_BINDING_SOURCE_SHA256 = source_hash
    reviewer.EXPECTED_READINESS_FILE_SHA256 = readiness_file_hash
    reviewer.EXPECTED_PROOF_REVIEW_FILE_SHA256 = proof_file_hash
    return {
        "binding_module": binding_module,
        "reviewer": reviewer,
        "binding": binding,
        "readiness": readiness,
        "proof": proof,
        "urdf_bytes": urdf_bytes,
        "source_bytes": source_bytes,
        "binding_file_hash": binding_file_hash,
        "readiness_file_hash": readiness_file_hash,
        "proof_file_hash": proof_file_hash,
        "source_hash": source_hash,
    }


def _review(bundle=None, *, binding=None, source_bytes=None):
    values = _bundle() if bundle is None else bundle
    reviewer = values["reviewer"]
    return reviewer.build_review(
        values["binding"] if binding is None else binding,
        values["readiness"],
        values["proof"],
        values["urdf_bytes"],
        values["source_bytes"] if source_bytes is None else source_bytes,
        binding_file_sha256=values["binding_file_hash"],
        readiness_file_sha256=values["readiness_file_hash"],
        proof_review_file_sha256=values["proof_file_hash"],
        urdf_file_sha256=reviewer.EXPECTED_URDF_SHA256,
        binding_source_file_sha256=values["source_hash"],
        binding_module=values["binding_module"],
    )


def _rehash_binding(bundle, changed):
    core = dict(changed)
    core.pop("binding_sha256", None)
    changed["binding_sha256"] = bundle["reviewer"]._sha(core)
    bundle["reviewer"].EXPECTED_BINDING_SHA256 = changed["binding_sha256"]


def test_arm263_accepts_exact_binding_for_runtime_instantiation_only():
    result = _review()

    assert result["status"] == "ACCEPTED_FOR_NATIVE_BINDING_INTEGRATION"
    assert result["runtime_instantiation_admitted"] is True
    assert result["launch_admitted"] is False
    assert result["attempt_consumed"] is False
    assert result["isaac_started"] is False
    assert result["trajectory_playback"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False
    assert result["controller_commands"] == []
    assert result["wire_commands"] == []
    assert result["gate_promotions"] == []
    assert all(result["review_findings"].values())


def test_arm263_receipt_satisfies_the_arm262_constructor_gate():
    bundle = _bundle()
    receipt = _review(bundle)
    module = bundle["binding_module"]

    runtime = module.NativeIsaacConservativeSweepBinding(
        bundle["binding"],
        binding_review=receipt,
        articulation=bundle["reviewer"]._Articulation(),
        scene_query=bundle["reviewer"]._Query(),
        environment_only_scene=True,
        robot_collision_query_shapes_enabled=False,
    )

    assert len(
        runtime.bound_link_spheres(
            start_joint_targets_rad=[0.0] * 6,
            end_joint_targets_rad=[0.01] * 6,
        )
    ) == 7


def test_arm263_independently_rederives_every_path_coefficient():
    bundle = _bundle()
    reviewer = bundle["reviewer"]

    assert reviewer._independent_path_coefficients(
        bundle["binding"]["link_spheres"], bundle["urdf_bytes"]
    ) == bundle["binding"]["path_lipschitz_mm_per_rad"]


def test_arm263_rejects_self_consistent_path_bound_drift():
    bundle = _bundle()
    changed = copy.deepcopy(bundle["binding"])
    changed["path_lipschitz_mm_per_rad"]["robot:gripper"][
        "base_link_to_link1"
    ] += 0.001
    _rehash_binding(bundle, changed)

    with pytest.raises(ValueError, match="coefficients"):
        _review(bundle, binding=changed)


def test_arm263_rejects_self_consistent_runtime_contract_drift():
    bundle = _bundle()
    changed = copy.deepcopy(bundle["binding"])
    changed["runtime_contract"]["clearance_margin_mm"] = 0.0
    _rehash_binding(bundle, changed)

    with pytest.raises(ValueError, match="runtime contract"):
        _review(bundle, binding=changed)


def test_arm263_rejects_self_consistent_authority_drift():
    bundle = _bundle()
    changed = copy.deepcopy(bundle["binding"])
    changed["launch_admitted"] = True
    _rehash_binding(bundle, changed)

    with pytest.raises(ValueError, match="identity or boundary"):
        _review(bundle, binding=changed)


def test_arm263_rejects_binding_source_drift():
    bundle = _bundle()

    with pytest.raises(ValueError, match="identity or boundary"):
        _review(bundle, source_bytes=bundle["source_bytes"] + b"\n# drift\n")


def test_arm263_source_review_rejects_runtime_import_and_launch_call():
    reviewer = _bundle()["reviewer"]

    with pytest.raises(ValueError, match="forbidden runtime"):
        reviewer._review_source(b"import isaacsim\n")
    with pytest.raises(ValueError, match="method surface"):
        reviewer._review_source(b"SimulationApp()\n")


def test_arm263_import_and_review_cli_are_zero_authority():
    source = REVIEW_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "from isaacsim import" not in source
    assert not any(name.startswith(("isaacsim", "serial")) for name in imported)
    assert "SimulationApp" not in called
    assert "execute_backend" not in called
