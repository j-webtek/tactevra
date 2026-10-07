from __future__ import annotations

import copy
from pathlib import Path

import pytest

from rocell.application.c03_route_collision_handoff_v1 import (
    C03RouteCollisionHandoffV1Error,
    prepare_c03_route_collision_handoff_v1,
)
from rocell.application.context import load_simulation_context
from rocell.application.partitioned_typing_collision_intake_v1 import (
    PROFILE_REQUIRED_STATUS,
    READY_STATUS,
)

from test_partitioned_typing_collision_intake_v1 import _inputs
from test_typing_trajectory_ik_screen_v1 import _installed_profile


WORKSPACE = Path(__file__).resolve().parents[3]
MANIFEST = WORKSPACE / "software/config/system_manifest.json"


@pytest.fixture(scope="module")
def sim_context():
    return load_simulation_context(WORKSPACE, MANIFEST)


def _result(sim_context):
    snapshot, execution, trajectory, ik = _inputs(sim_context)
    route = {
        "decision": "PASS_C03_110MM_CANDIDATE_ROUTE_IK_CONTINUITY",
        "ordered_targets": [
            "H", "E", "L", "L", "O", "SPACE", "2", "0", "2", "6",
        ],
        "canonical_ik_route_accepted": True,
        "canonical_joint_continuity_accepted": True,
        "trajectory_sample_count": len(ik["joint_results"]),
        "ik_accepted_sample_count": len(ik["joint_results"]),
        "collision_screen_executed": False,
        "execution_plan_sha256": execution.plan_sha256,
        "trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "calibration_snapshot_sha256": snapshot.snapshot_sha256,
        "ik_screen": ik,
    }
    from rocell.application.c03_route_collision_handoff_v1 import _sha256

    route["receipt_sha256"] = _sha256(route)
    outer = {
        "decision": route["decision"],
        "route_result": route,
        "collision_screen_executed": False,
        "installed_collision_gate_cleared": False,
        "hardware_commands_generated": 0,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    outer["receipt_sha256"] = _sha256(outer)
    return outer


def test_handoff_partitions_exact_route_and_retains_profile_blocker(sim_context):
    report = prepare_c03_route_collision_handoff_v1(_result(sim_context), sim_context)
    assert report["collision_intake"]["status"] == PROFILE_REQUIRED_STATUS
    assert report["collision_intake"]["required_evidence_slots"]["route_segment_count"] > 0
    assert report["installed_collision_gate_cleared"] is False
    assert report["physical_authority"] is False


def test_handoff_accepts_matching_profile_but_does_not_clear_collision(sim_context):
    report = prepare_c03_route_collision_handoff_v1(
        _result(sim_context),
        sim_context,
        installed_profile=_installed_profile(sim_context),
    )
    assert report["collision_intake"]["status"] == READY_STATUS
    assert report["collision_intake"]["continuous_collision_proven"] is False
    assert report["installed_collision_gate_cleared"] is False


def test_handoff_rejects_mutation_and_authority(sim_context):
    changed = copy.deepcopy(_result(sim_context))
    changed["physical_authority"] = True
    with pytest.raises(C03RouteCollisionHandoffV1Error, match="invalid receipt"):
        prepare_c03_route_collision_handoff_v1(changed, sim_context)
