from __future__ import annotations

import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
EVIDENCE = WORKSPACE / "software/integrations/isaac_sim/evidence"
VARIANT = EVIDENCE / "roarm_m3_targeted_obb_link2_20260929.json"
REPLAY = EVIDENCE / "roarm_m3_collision_joint_space_link2_20260929.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_link2_variant_receipts_are_canonical_and_zero_authority() -> None:
    for path in (VARIANT, REPLAY):
        receipt = _load(path)
        claimed = receipt.pop("receipt_sha256")
        assert canonical_sha256(receipt) == claimed
        assert receipt["hardware_access"] is receipt["physical_authority"] is False
        assert receipt["wire_commands"] == []
        assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_link2_variant_refines_only_two_link2_components() -> None:
    receipt = _load(VARIANT)
    assert receipt["method"]["target_links"] == ["link2"]
    assert receipt["summary"]["refined_primitive_count"] == 2
    assert receipt["summary"]["candidate_primitive_count"] == 14
    assert receipt["summary"]["maximum_vertex_overflow_mm"] == 0.0
    metrics = receipt["target_metrics"]
    assert metrics[0]["new_to_old_volume_ratio"] == 1.0
    assert metrics[1]["new_to_old_volume_ratio"] == 0.941967


def test_link2_replay_preserves_baseline_classifications_without_false_negatives() -> None:
    baseline = _load(EVIDENCE / "roarm_m3_collision_joint_space_20260929.json")
    replay = _load(REPLAY)
    assert baseline["summary"]["CANDIDATE_FALSE_POSITIVE"] == 192
    assert replay["summary"]["CANDIDATE_FALSE_POSITIVE"] == 192
    assert replay["summary"]["CANDIDATE_FALSE_NEGATIVE"] == 0
    assert replay["summary"]["PAIR_CASES"] == 1029


def test_link2_replay_retains_one_nonadjacent_false_positive() -> None:
    replay = _load(REPLAY)
    scopes = replay["adjacency_scope_summary"]
    assert scopes["ADJACENT"]["CANDIDATE_FALSE_POSITIVE"] == 191
    assert scopes["NONADJACENT"]["CANDIDATE_FALSE_POSITIVE"] == 1
    pairs = {tuple(row["body_pair"]): row for row in replay["pair_summary"]}
    witness = pairs[("link2", "gripper_link")]
    assert witness["counts"]["CANDIDATE_FALSE_POSITIVE"] == 1
    assert witness["kinematically_adjacent"] is False


def test_link2_variant_remains_uninstalled_and_exclusion_free() -> None:
    variant = _load(VARIANT)
    replay = _load(REPLAY)
    assert variant["candidate_profile_installable"] is False
    assert variant["collision_query_admissible"] is False
    assert replay["candidate_profile_installable"] is False
    assert replay["collision_query_admissible"] is False
    assert replay["pair_exclusions_admissible"] is False
    assert replay["clearance_replay_admissible"] is False
