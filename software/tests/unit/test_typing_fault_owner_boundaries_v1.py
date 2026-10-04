from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path

import pytest

from rocell.application.model_motion_sequence_coordinator import (
    ActionDisposition,
    ModelMotionSequenceCoordinator,
    ModelMotionSequenceError,
    SequencePhase,
    VerifiedActionResult,
)
from rocell.application.context import load_simulation_context
from rocell.application.typing_collision_intake_v1 import (
    PROFILE_REQUIRED_STATUS,
    prepare_typing_collision_intake_v1,
)
from rocell.application.typing_execution_plan_v1 import TypingExecutionPlanV1Error
from rocell.application.typing_fault_campaign_v1 import (
    MAX_CAMPAIGN_CASES,
    REQUIRED_CASES,
    TypingFaultCampaignV1Error,
    TypingFaultObservationV1,
    build_typing_fault_campaign_v1,
    build_typing_fault_observation_cache_v1,
    parse_typing_fault_observation_cache_v1,
)
from rocell.application.typing_rolling_horizon_v1 import (
    invalidate_typing_rolling_horizon_v1,
    revalidate_typing_rolling_horizon_v1,
    reconcile_typing_restart_v1,
    retain_typing_dispatch_intent_v1,
)
from rocell.application.typing_joint_schedule_v1 import (
    TypingJointScheduleV1Error,
    compile_typing_joint_schedule_v1,
)
from rocell.application.typing_trajectory_ik_screen_v1 import (
    TypingTrajectoryIkScreenV1Error,
    TypingTrajectoryIkSeedV1,
    screen_typing_trajectory_ik_v1,
)
from rocell.arm.discrete_transaction import DiscreteTransaction
from rocell.arm.protocol_emulator import (
    DeterministicFeedbackSession,
    ProtocolEmulatorFault,
    ProtocolEmulatorSessionError,
    ProtocolEmulatorSessionFailure,
    ProtocolEmulatorStep,
)
from rocell.geometry import JointPosition, Point3Mm
from rocell.kinematics import ARM_JOINT_NAMES, BoardToolTipTarget, IkStatus
from rocell.typing import compile_development_text
from rocell.models import ModelMotionBatchV2Error

import test_kinematics_ik as kinematics_support
import test_model_motion_sequence_coordinator as sequence_support
import test_model_motion_ingress_v2 as ingress_support
import test_trajectory_simulation as trajectory_support
import test_typing_execution_plan_v1 as execution_support
import test_typing_joint_schedule_v1 as dynamics_support
import test_typing_rolling_horizon_v1 as horizon_support
import test_typing_trajectory_ik_screen_v1 as ik_support


WORKSPACE = Path(__file__).resolve().parents[3]
MANIFEST = WORKSPACE / "software/config/system_manifest.json"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _observation(case_id: str, evidence: object) -> TypingFaultObservationV1:
    family, reason, outcome = REQUIRED_CASES[case_id]
    return TypingFaultObservationV1(
        case_id=case_id,
        family=family,
        reason_code=reason,
        terminal_outcome=outcome,
        boundary_sha256=hashlib.sha256(_canonical(evidence)).hexdigest(),
    )


def _transaction() -> DiscreteTransaction:
    return DiscreteTransaction(
        baseline=[0, 0, 1, 0, 0, 3],
        baseline_finished_ns=1_000_000_000,
        target=math.radians(1),
        completion_budget_ns=3_000_000_000,
    )


def _emulator_observation(
    case_id: str,
    fault: ProtocolEmulatorFault,
    expected: ProtocolEmulatorSessionFailure,
) -> TypingFaultObservationV1:
    session = DeterministicFeedbackSession((ProtocolEmulatorStep(fault),))
    session.connect()
    with pytest.raises(ProtocolEmulatorSessionError) as caught:
        session.request_feedback()
    assert caught.value.failure is expected
    assert session.is_open is False
    assert session.open_count == 1 and session.close_count >= 1
    evidence = {
        "failure": caught.value.failure.value,
        "writes": [hashlib.sha256(item).hexdigest() for item in session.writes],
        "received": [hashlib.sha256(item).hexdigest()
                     for item in session.received_lines],
        "session_open": session.is_open,
        "pending_steps": session.pending_step_count,
        "hardware_access": False,
        "physical_authority": False,
    }
    return _observation(case_id, evidence)


def _feedback_observations() -> list[TypingFaultObservationV1]:
    late = _transaction()
    late.begin_dispatch(1_010_000_000)
    late.acknowledge(2_010_000_001)
    assert late.snapshot()["state"] == "COMMAND_OUTCOME_UNCERTAIN"

    missing = _transaction()
    missing.begin_dispatch(1_010_000_000)
    missing.acknowledge(1_020_000_000)
    missing.tick(2_020_000_001)
    assert missing.snapshot()["state"] == "FEEDBACK_GAP_EXCEEDED"

    return [
        _observation("ACK_LATE", late.snapshot()),
        _observation("FEEDBACK_MISSING", missing.snapshot()),
        _emulator_observation(
            "FEEDBACK_MALFORMED", ProtocolEmulatorFault.MALFORMED_JSON,
            ProtocolEmulatorSessionFailure.MALFORMED_JSON),
        _emulator_observation(
            "PARTIAL_WRITE", ProtocolEmulatorFault.PARTIAL_WRITE,
            ProtocolEmulatorSessionFailure.PARTIAL_WRITE),
        _emulator_observation(
            "DISCONNECT", ProtocolEmulatorFault.DISCONNECT,
            ProtocolEmulatorSessionFailure.DISCONNECT),
        _emulator_observation(
            "CONTROLLER_RESTART", ProtocolEmulatorFault.RESET_BANNER,
            ProtocolEmulatorSessionFailure.RESET_BANNER),
    ]


def _sequence_observations() -> list[TypingFaultObservationV1]:
    context, batch, ingress = sequence_support._setup()
    gate, _ = sequence_support._ready_gate(ingress)
    mismatch = ModelMotionSequenceCoordinator(
        batch, ingress, context, planner_gate=gate)
    mismatch.evaluate_next(
        sequence_support._observed("a"), evaluation_monotonic_ns=110)
    sequence_support._commit(mismatch)
    good = sequence_support._result(batch, mismatch)
    crossed = VerifiedActionResult(
        batch_sha256=good.batch_sha256,
        action_index=1,
        proposal_sha256=good.proposal_sha256,
        planner_gate_sha256=good.planner_gate_sha256,
        execution_receipt_sha256=good.execution_receipt_sha256,
        outcome_evidence_sha256=good.outcome_evidence_sha256,
        disposition=good.disposition,
    )
    with pytest.raises(ModelMotionSequenceError, match="current action"):
        mismatch.record_result(crossed)
    mismatch_snapshot = mismatch.snapshot()
    assert mismatch.phase is SequencePhase.WAITING_FOR_EXECUTION_RESULT
    assert mismatch_snapshot["automatic_retry_allowed"] is False

    gate, _ = sequence_support._ready_gate(ingress)
    ambiguous = ModelMotionSequenceCoordinator(
        batch, ingress, context, planner_gate=gate)
    ambiguous.evaluate_next(
        sequence_support._observed("b"), evaluation_monotonic_ns=110)
    sequence_support._commit(ambiguous)
    ambiguous.record_result(sequence_support._result(
        batch, ambiguous, ActionDisposition.OUTCOME_UNCERTAIN))
    ambiguous_snapshot = ambiguous.snapshot()
    assert ambiguous.phase is SequencePhase.OUTCOME_UNCERTAIN
    assert ambiguous_snapshot["blocker"] == "OUTCOME_UNCERTAIN_RETRY_FORBIDDEN"

    return [
        _observation("SEQUENCE_MISMATCH", mismatch_snapshot),
        _observation("AMBIGUOUS_COMPLETION", ambiguous_snapshot),
    ]


def _crash_observations() -> list[TypingFaultObservationV1]:
    before = reconcile_typing_restart_v1(horizon_support._state())
    assert before["phase"] == "RECONSTRUCTED_PRE_DISPATCH"
    assert before["automatic_retry_allowed"] is False

    observations = [_observation("CRASH_BEFORE_INTENT", before)]
    for case_id in (
        "CRASH_AFTER_DURABLE_INTENT",
        "CRASH_DURING_DISPATCH",
        "CRASH_AFTER_POSSIBLE_CONTACT",
        "CRASH_BEFORE_EFFECT_VERIFICATION",
    ):
        retained = retain_typing_dispatch_intent_v1(
            horizon_support._state(), dispatch_intent_sha256="f" * 64)
        uncertain = reconcile_typing_restart_v1(retained)
        assert uncertain["phase"] == "OUTCOME_UNCERTAIN"
        assert uncertain["automatic_retry_allowed"] is False
        assert uncertain["restart_reconciliation"] == (
            "POST_DISPATCH_OR_AMBIGUOUS_RESTART_RETRY_FORBIDDEN")
        observations.append(_observation(
            case_id, {"scenario": case_id, "reconciliation": uncertain}))
    return observations


def test_real_feedback_sequence_and_restart_boundaries_cover_pc5_families():
    actual = [
        *_feedback_observations(),
        *_sequence_observations(),
        *_crash_observations(),
    ]
    assert len(actual) == 13
    assert {item.case_id for item in actual} == {
        "ACK_LATE", "FEEDBACK_MISSING", "FEEDBACK_MALFORMED",
        "PARTIAL_WRITE", "DISCONNECT", "CONTROLLER_RESTART",
        "SEQUENCE_MISMATCH", "AMBIGUOUS_COMPLETION",
        "CRASH_BEFORE_INTENT", "CRASH_AFTER_DURABLE_INTENT",
        "CRASH_DURING_DISPATCH", "CRASH_AFTER_POSSIBLE_CONTACT",
        "CRASH_BEFORE_EFFECT_VERIFICATION",
    }
    assert all(item.automatic_retry_allowed is False for item in actual)
    assert all(item.hardware_access is False for item in actual)

    actual_by_id = {item.case_id: item for item in actual}
    complete = []
    for case_id, (family, reason, outcome) in REQUIRED_CASES.items():
        complete.append(actual_by_id.get(case_id) or TypingFaultObservationV1(
            case_id=case_id, family=family, reason_code=reason,
            terminal_outcome=outcome,
            boundary_sha256=hashlib.sha256(case_id.encode()).hexdigest(),
        ))
    report = build_typing_fault_campaign_v1(
        complete, qualification_basis_sha256="a" * 64)
    assert report["case_count"] == 35
    assert report["transport_write_count"] == 0
    assert report["physical_authority"] is False


def test_real_planning_boundaries_cover_every_pc5_planning_case():
    observations: list[TypingFaultObservationV1] = []

    solver = kinematics_support._solver()
    unreachable = solver.solve(
        BoardToolTipTarget(Point3Mm("board", 5_000, -5_000, 5_000)))
    assert unreachable.status is IkStatus.NO_CONVERGED_SOLUTION
    assert unreachable.solution_arm_joint_positions == ()
    observations.append(_observation("IK_UNREACHABLE", unreachable.to_dict()))

    context = load_simulation_context(WORKSPACE, MANIFEST)
    snapshot = ik_support._snapshot(context)
    execution, trajectory = ik_support._trajectory(context, snapshot)
    seed_values = ik_support._ready_joint_values(context)
    seed_values[ARM_JOINT_NAMES[0]] = 1_000.0
    bad_seed = TypingTrajectoryIkSeedV1(
        seed_id="joint-limit-loss",
        calibration_snapshot_sha256=snapshot.snapshot_sha256,
        build_snapshot_sha256=context.snapshot.snapshot_hash,
        joint_positions_rad=seed_values,
    )
    with pytest.raises(TypingTrajectoryIkScreenV1Error, match="planner bounds") as limit:
        screen_typing_trajectory_ik_v1(
            execution, trajectory, context, snapshot, bad_seed)
    observations.append(_observation(
        "JOINT_LIMIT_LOSS", {"error": str(limit.value)}))

    target = kinematics_support._reachable_target(solver.model)
    singular_state = {
        name: JointPosition.radians(value)
        for name, value in zip(
            ARM_JOINT_NAMES, (0.0, 0.0, 0.0, 0.0, -math.pi / 2.0), strict=True)
    }
    singular = solver.diagnose_weighted_task_jacobian(target, singular_state)
    assert singular.full_column_rank is False
    assert singular.normalized_minimum_singular_value == 0.0
    observations.append(_observation("SINGULARITY", singular.to_dict()))

    discontinuity = trajectory_support._run_with_test_solver(
        context,
        compile_development_text("keyboard", "a"),
        trajectory_support._nominal_study(context),
        trajectory_support.TrajectorySimulationPolicy(
            maximum_cartesian_step_mm=100.0,
            maximum_joint_step_rad=0.10,
            maximum_refinement_rounds=1,
        ),
        trajectory_support._alternating_branch_fake_ik_class(),
    )
    assert discontinuity.termination_reason == "REFINEMENT_ROUND_LIMIT_EXHAUSTED"
    assert all(
        round_.failure_reason == "MAXIMUM_ADJACENT_JOINT_DELTA_EXCEEDED"
        for round_ in discontinuity.rounds)
    observations.append(_observation("DISCONTINUITY", discontinuity.to_dict()))

    dynamics_plan = dynamics_support._plan()
    with pytest.raises(TypingJointScheduleV1Error, match="exceeds the profile") as overflow:
        compile_typing_joint_schedule_v1(
            dynamics_plan,
            dynamics_support._ik_report(dynamics_plan),
            dynamics_support._profile(maximum_time_scale_factor=1.01),
        )
    observations.append(_observation(
        "DYNAMICS_OVERFLOW", {"error": str(overflow.value)}))

    accepted_ik = screen_typing_trajectory_ik_v1(
        execution, trajectory, context, snapshot,
        ik_support._seed(context, snapshot))
    collision = prepare_typing_collision_intake_v1(
        execution, trajectory, accepted_ik, context, snapshot)
    assert collision["status"] == PROFILE_REQUIRED_STATUS
    assert "INSTALLED_COLLISION_PROFILE_REQUIRED" in collision["blockers"]
    observations.append(_observation("COLLISION_EVIDENCE_ABSENT", collision))

    with pytest.raises(TypingExecutionPlanV1Error, match="hover_clearance") as clearance:
        replace(execution_support._config(), hover_clearance_mm=0.0)
    observations.append(_observation(
        "CLEARANCE_LOSS", {"error": str(clearance.value)}))

    assert {item.case_id for item in observations} == {
        "IK_UNREACHABLE", "JOINT_LIMIT_LOSS", "SINGULARITY", "DISCONTINUITY",
        "DYNAMICS_OVERFLOW", "COLLISION_EVIDENCE_ABSENT", "CLEARANCE_LOSS",
    }
    assert all(item.controller_commands == () for item in observations)
    assert all(item.hardware_access is False for item in observations)
    assert all(item.physical_authority is False for item in observations)


def test_real_runtime_and_cache_boundaries_cover_every_pc5_runtime_case():
    cancelled = invalidate_typing_rolling_horizon_v1(
        horizon_support._state(), reason="CANCELLED")
    expired = invalidate_typing_rolling_horizon_v1(
        horizon_support._state(), reason="DEADLINE_EXPIRED")
    assert cancelled["phase"] == expired["phase"] == "INVALIDATED"
    assert cancelled["current"] is cancelled["preview"] is None
    assert expired["current"] is expired["preview"] is None

    corruption_observation = _observation(
        "CACHE_CORRUPTION", {"source": "cache-corruption-owner-boundary"})
    cache = build_typing_fault_observation_cache_v1(
        (corruption_observation,), qualification_basis_sha256="a" * 64)
    corrupt = deepcopy(cache)
    corrupt.pop("fault_cache_sha256")
    corrupt["entries"][0]["observation"]["boundary_sha256"] = "f" * 64
    corrupt["fault_cache_sha256"] = hashlib.sha256(_canonical(corrupt)).hexdigest()
    with pytest.raises(TypingFaultCampaignV1Error, match="entry hash") as corruption:
        parse_typing_fault_observation_cache_v1(
            corrupt, expected_qualification_basis_sha256="a" * 64)

    identity_observation = _observation(
        "CACHE_IDENTITY_CROSSING", {"source": "cache-identity-owner-boundary"})
    crossed = build_typing_fault_observation_cache_v1(
        (identity_observation,), qualification_basis_sha256="a" * 64)
    with pytest.raises(TypingFaultCampaignV1Error, match="identity is crossed") as identity:
        parse_typing_fault_observation_cache_v1(
            crossed, expected_qualification_basis_sha256="b" * 64)

    with pytest.raises(TypingFaultCampaignV1Error, match="bounded capacity") as resource:
        build_typing_fault_observation_cache_v1(
            (corruption_observation,) * (MAX_CAMPAIGN_CASES + 1),
            qualification_basis_sha256="a" * 64,
        )

    observations = [
        _observation("CANCELLATION", cancelled),
        _observation("DEADLINE_EXPIRY", expired),
        _observation("CACHE_CORRUPTION", {"error": str(corruption.value)}),
        _observation("CACHE_IDENTITY_CROSSING", {"error": str(identity.value)}),
        _observation("RESOURCE_EXHAUSTION", {"error": str(resource.value)}),
    ]
    assert {item.case_id for item in observations} == {
        "CACHE_CORRUPTION", "CACHE_IDENTITY_CROSSING", "DEADLINE_EXPIRY",
        "CANCELLATION", "RESOURCE_EXHAUSTION",
    }
    assert all(item.automatic_retry_allowed is False for item in observations)
    assert all(item.physical_authority is False for item in observations)


def test_real_identity_and_order_boundaries_cover_every_pc5_identity_case():
    stale = revalidate_typing_rolling_horizon_v1(
        horizon_support._state(), horizon_support._binding(),
        now_monotonic_ns=2_001)
    assert stale["phase"] == "INVALIDATED"
    assert stale["invalidation_reason"] == "EVIDENCE_STALE"
    assert stale["current"] is stale["preview"] is None

    crossed = revalidate_typing_rolling_horizon_v1(
        horizon_support._state(),
        horizon_support._binding(calibration_snapshot_sha256="8" * 64),
        now_monotonic_ns=1_100,
    )
    assert crossed["phase"] == "INVALIDATED"
    assert crossed["invalidation_reason"] == "CALIBRATION_CHANGED"
    assert crossed["current"] is crossed["preview"] is None

    context = load_simulation_context(WORKSPACE, MANIFEST)
    with pytest.raises(ModelMotionBatchV2Error, match="ordered and contiguous") as order:
        ingress_support._batch(
            context,
            proposals=(
                ingress_support._proposal(context, "H", 1),
                ingress_support._proposal(context, "I", 0),
            ),
        )

    observations = [
        _observation("EVIDENCE_STALE", stale),
        _observation("IDENTITY_CROSSED", crossed),
        _observation("ACTION_ORDER_INVALID", {"error": str(order.value)}),
    ]
    assert {item.case_id for item in observations} == {
        "EVIDENCE_STALE", "IDENTITY_CROSSED", "ACTION_ORDER_INVALID",
    }
    assert all(item.automatic_retry_allowed is False for item in observations)
    assert all(item.controller_commands == () for item in observations)
    assert all(item.physical_authority is False for item in observations)


def test_fault_cache_malformed_observation_has_stable_typed_failure():
    cache = build_typing_fault_observation_cache_v1(
        (_observation("CACHE_CORRUPTION", {"source": "malformed-fields"}),),
        qualification_basis_sha256="a" * 64,
    )
    malformed = deepcopy(cache)
    malformed.pop("fault_cache_sha256")
    malformed["entries"][0]["observation"].pop("reason_code")
    malformed["entries"][0]["entry_sha256"] = hashlib.sha256(
        _canonical(malformed["entries"][0]["observation"])).hexdigest()
    malformed["fault_cache_sha256"] = hashlib.sha256(
        _canonical(malformed)).hexdigest()
    with pytest.raises(
        TypingFaultCampaignV1Error,
        match="observation fields are not exact",
    ):
        parse_typing_fault_observation_cache_v1(
            malformed, expected_qualification_basis_sha256="a" * 64)
