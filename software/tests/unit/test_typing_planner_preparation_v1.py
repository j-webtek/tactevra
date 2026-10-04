from __future__ import annotations

from dataclasses import replace

import pytest

from rocell.application.context import SimulationContextError
from rocell.application.context_lifecycle_v1 import SimulationContextLifecycleV1
from rocell.application.typing_collision_intake_v1 import (
    TypingCollisionIntakeV1Error,
    prepare_typing_collision_intake_v1,
)
from rocell.application.typing_planner_preparation_v1 import (
    prepare_typing_planner_v1,
)
from rocell.application.typing_trajectory_ik_screen_v1 import (
    TypingTrajectoryIkScreenV1Error,
    screen_typing_trajectory_ik_v1,
)

import test_typing_trajectory_ik_screen_v1 as fixture


SERVICE = "typing-planner-e1-fixture"


def _lifecycle():
    return SimulationContextLifecycleV1.start(
        fixture.WORKSPACE,
        fixture.MANIFEST,
        service_instance_id=SERVICE,
        issued_monotonic_ns=100,
    )


def test_prepared_ik_and_collision_outputs_match_full_source_path_exactly():
    lifecycle = _lifecycle()
    context = lifecycle.binding().context
    snapshot = fixture._snapshot(context)
    execution, trajectory = fixture._trajectory(context, snapshot)
    seed = fixture._seed(context, snapshot)
    prepared = prepare_typing_planner_v1(context, lifecycle)

    full_ik = screen_typing_trajectory_ik_v1(
        execution, trajectory, context, snapshot, seed,
    )
    prepared_ik = screen_typing_trajectory_ik_v1(
        execution,
        trajectory,
        context,
        snapshot,
        seed,
        prepared_planner=prepared,
        context_lifecycle=lifecycle,
    )
    assert prepared_ik == full_ik

    full_collision = prepare_typing_collision_intake_v1(
        execution, trajectory, full_ik, context, snapshot,
    )
    prepared_collision = prepare_typing_collision_intake_v1(
        execution,
        trajectory,
        prepared_ik,
        context,
        snapshot,
        prepared_planner=prepared,
        context_lifecycle=lifecycle,
    )
    assert prepared_collision == full_collision
    assert prepared.hardware_access is prepared.physical_authority is False


def test_reload_and_restart_reject_stale_preparation():
    lifecycle = _lifecycle()
    old_context = lifecycle.binding().context
    prepared = prepare_typing_planner_v1(old_context, lifecycle)
    current = lifecycle.reload_sources(issued_monotonic_ns=200)
    snapshot = fixture._snapshot(current.context)
    execution, trajectory = fixture._trajectory(current.context, snapshot)
    with pytest.raises(SimulationContextError, match="different context"):
        screen_typing_trajectory_ik_v1(
            execution,
            trajectory,
            current.context,
            snapshot,
            fixture._seed(current.context, snapshot),
            prepared_planner=prepared,
            context_lifecycle=lifecycle,
        )

    current_prepared = prepare_typing_planner_v1(current.context, lifecycle)
    restarted = lifecycle.restart(
        service_instance_id="typing-planner-e1-restarted",
        issued_monotonic_ns=300,
    )
    restarted_context = restarted.binding().context
    restarted_snapshot = fixture._snapshot(restarted_context)
    restarted_execution, restarted_trajectory = fixture._trajectory(
        restarted_context, restarted_snapshot,
    )
    with pytest.raises(SimulationContextError, match="different context"):
        screen_typing_trajectory_ik_v1(
            restarted_execution,
            restarted_trajectory,
            restarted_context,
            restarted_snapshot,
            fixture._seed(restarted_context, restarted_snapshot),
            prepared_planner=current_prepared,
            context_lifecycle=restarted,
        )


def test_mutation_and_unmanaged_preparation_fail_closed():
    lifecycle = _lifecycle()
    context = lifecycle.binding().context
    snapshot = fixture._snapshot(context)
    execution, trajectory = fixture._trajectory(context, snapshot)
    seed = fixture._seed(context, snapshot)
    prepared = prepare_typing_planner_v1(context, lifecycle)
    forged = replace(prepared, generation=prepared.generation + 1)
    with pytest.raises(SimulationContextError, match="lifecycle binding is stale"):
        screen_typing_trajectory_ik_v1(
            execution,
            trajectory,
            context,
            snapshot,
            seed,
            prepared_planner=forged,
            context_lifecycle=lifecycle,
        )
    with pytest.raises(TypingTrajectoryIkScreenV1Error, match="requires lifecycle"):
        screen_typing_trajectory_ik_v1(
            execution,
            trajectory,
            context,
            snapshot,
            seed,
            prepared_planner=prepared,
        )
    full_ik = screen_typing_trajectory_ik_v1(
        execution, trajectory, context, snapshot, seed,
    )
    with pytest.raises(TypingCollisionIntakeV1Error, match="requires lifecycle"):
        prepare_typing_collision_intake_v1(
            execution,
            trajectory,
            full_ik,
            context,
            snapshot,
            prepared_planner=prepared,
        )
