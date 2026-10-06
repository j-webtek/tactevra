from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
INTEGRATION = WORKSPACE / "software/integrations/isaac_sim"
EVIDENCE = INTEGRATION / "evidence"
FILES = {
    "obb": "roarm_m3_targeted_obb_link2_20261005.json",
    "obb_replay": "roarm_m3_collision_joint_space_link2_20261005.json",
    "partition": "roarm_m3_triangle_partition_link2_20261005.json",
    "partition_replay": (
        "roarm_m3_collision_joint_space_triangle_partition_20261005.json"
    ),
    "policy": "roarm_m3_self_collision_policy_review_20261005.json",
    "never": "roarm_m3_srdf_never_pair_review_20261005.json",
    "stress_replay": "roarm_m3_collision_policy_stress_replay_20261005.json",
    "stress": "roarm_m3_collision_policy_stress_assessment_20261005.json",
}


def _load(name: str) -> dict:
    return json.loads((EVIDENCE / FILES[name]).read_text(encoding="utf-8"))


def _load_module(name: str, path: Path):
    sys.path.insert(0, str(INTEGRATION))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_receipts_are_canonical_and_zero_authority() -> None:
    for filename in FILES.values():
        receipt = json.loads((EVIDENCE / filename).read_text(encoding="utf-8"))
        claimed = receipt.pop("receipt_sha256")
        assert canonical_sha256(receipt) == claimed
        assert receipt["hardware_access"] is receipt["physical_authority"] is False
        assert receipt["wire_commands"] == []
        assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_obb_failure_is_preserved_before_partition_successor() -> None:
    candidate, replay = _load("obb"), _load("obb_replay")
    assert candidate["summary"]["refined_primitive_count"] == 2
    assert candidate["summary"]["maximum_vertex_overflow_mm"] == 0.0
    assert replay["summary"] == {
        "AGREEMENT_COLLISION": 57,
        "AGREEMENT_FREE": 780,
        "CANDIDATE_FALSE_NEGATIVE": 0,
        "CANDIDATE_FALSE_POSITIVE": 192,
        "PAIR_CASES": 1029,
    }
    assert replay["adjacency_scope_summary"]["NONADJACENT"][
        "CANDIDATE_FALSE_POSITIVE"] == 1


def test_partition_removes_nonadjacent_false_positive_without_false_negative() -> None:
    candidate, replay = _load("partition"), _load("partition_replay")
    assert candidate["summary"]["partition_primitive_count"] == 16
    assert candidate["summary"]["candidate_primitive_count"] == 29
    assert candidate["summary"]["maximum_vertex_overflow_mm"] == 0.0
    assert replay["summary"] == {
        "AGREEMENT_COLLISION": 57,
        "AGREEMENT_FREE": 807,
        "CANDIDATE_FALSE_NEGATIVE": 0,
        "CANDIDATE_FALSE_POSITIVE": 165,
        "PAIR_CASES": 1029,
    }
    assert replay["adjacency_scope_summary"]["NONADJACENT"] == {
        "AGREEMENT_COLLISION": 3,
        "AGREEMENT_FREE": 732,
        "CANDIDATE_FALSE_NEGATIVE": 0,
        "CANDIDATE_FALSE_POSITIVE": 0,
    }
    assert "NONADJACENT_FALSE_POSITIVE_OBSERVED" not in replay["blockers"]


def test_pair_reviews_remain_counterfactual_and_uninstalled() -> None:
    policy, never = _load("policy"), _load("never")
    assert policy["summary"]["unsupported_false_positive_pair_count"] == 0
    assert policy["summary"]["false_positive_case_count"] == 165
    assert never["summary"]["never_pair_count"] == 6
    assert never["summary"]["supported_never_pair_count"] == 6
    assert never["summary"]["contradicted_never_pair_count"] == 0
    assert policy["exclusion_profile_installable"] is False
    assert never["never_exclusions_installable"] is False


def test_held_out_stress_preserves_blockers_and_reports_residuals() -> None:
    replay, assessment = _load("stress_replay"), _load("stress")
    assert replay["pose_count"] == 256
    assert replay["method"]["halton_start_index"] == 1001
    assert replay["summary"]["CANDIDATE_FALSE_NEGATIVE"] == 0
    assert assessment["summary"]["supported_never_pair_count"] == 6
    assert assessment["summary"]["contradicted_never_pair_count"] == 0
    assert assessment["summary"]["retained_pair_counts"] == {
        "AGREEMENT_COLLISION": 36,
        "AGREEMENT_FREE": 2255,
        "CANDIDATE_FALSE_NEGATIVE": 0,
        "CANDIDATE_FALSE_POSITIVE": 13,
    }
    assert assessment["effective_exclusions"] == []
    assert assessment["collision_query_admissible"] is False
    assert assessment["clearance_replay_admissible"] is False


def test_stress_loader_rejects_tampering(tmp_path: Path) -> None:
    module = _load_module(
        "collision_policy_stress_probe",
        INTEGRATION / "collision_policy_stress_probe.py",
    )
    changed = _load("stress_replay")
    changed["pose_count"] = 255
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="receipt hash mismatch"):
        module._load_stress_replay(path)
