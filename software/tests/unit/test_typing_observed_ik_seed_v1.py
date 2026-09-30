from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json

import pytest

from rocell.application.installed_controller_qualification_v1 import (
    assess_installed_controller_qualification_v1,
)
from rocell.application.observed_planner_start_state import ObservedPlannerStartState
from rocell.application.typing_observed_ik_seed_v1 import (
    SOURCE_KIND,
    TypingObservedIkSeedV1Error,
    build_typing_observed_ik_seed_v1,
    parse_typing_observed_ik_seed_v1,
)
from rocell.application.typing_state_prerequisite_binding_v1 import (
    bind_typing_state_prerequisites_v1,
)
from software.scripts import run_typing_command_session_ledger_campaign_v1 as runner

import test_installed_controller_qualification_v1 as controller
import test_typing_shadow_pipeline_v1 as shadow_fixture


def _inputs():
    ledger, _supervisor = runner._ledger()
    ledger.submit("mission-observed-seed", "seed", runner._inputs(ledger, "seed"))
    ledger.run_next_shadow()
    materialization = ledger.shadow_materialization("seed")
    context = ledger.context
    snapshot = shadow_fixture.ik_fixture._snapshot(context)
    profile = controller._profile()
    evidence = controller._evidence(profile)
    report = assess_installed_controller_qualification_v1(
        profile, evidence, evaluated_monotonic_ns=200
    )
    observed = ObservedPlannerStartState(
        run_id="run-observed-seed",
        arm_identity_sha256="1" * 64,
        controller_session_id=evidence.controller_session_id,
        request_context_sha256="2" * 64,
        feedback_receipt_sha256="3" * 64,
        calibration_snapshot_sha256=snapshot.snapshot_sha256,
        manifest_id=snapshot.manifest_id,
        active_build_id=snapshot.active_build_id,
        response_completed_monotonic_ns=100,
        available_monotonic_ns=110,
        valid_until_monotonic_ns=1_000,
        controller_joint_positions_rad={
            "b": 0.1, "s": 0.2, "e": 0.3,
            "t": 0.4, "r": 0.5, "g": 0.6,
        },
        model_joint_positions_rad={
            "b_base": 0.1, "s_shoulder": 0.2, "e_elbow": 0.3,
            "t_wrist_pitch": 0.4, "r_wrist_roll": 0.5, "g_gripper": 0.6,
        },
    )
    binding = bind_typing_state_prerequisites_v1(
        materialization, observed, evidence, report, evaluated_monotonic_ns=200
    )
    return materialization, binding, observed, context, snapshot


def test_builds_exact_fresh_observed_seed_without_authority():
    materialization, binding, observed, context, snapshot = _inputs()
    seed = build_typing_observed_ik_seed_v1(
        materialization, binding, observed, context, snapshot,
        evaluated_monotonic_ns=250,
    )
    value = seed.to_dict()
    assert parse_typing_observed_ik_seed_v1(value) == value
    assert value["source_kind"] == SOURCE_KIND
    assert value["materialization_sha256"] == materialization["materialization_sha256"]
    assert value["state_binding_sha256"] == binding["state_binding_sha256"]
    assert value["observed_start_state_sha256"] == observed.observed_start_state_sha256
    assert value["joint_positions_rad"] == dict(observed.arm_joint_positions_rad)
    assert value["controller_feedback_claimed"] is True
    assert value["physical_measurement_claimed"] is True
    assert value["ik_screening_completed"] is False
    assert value["collision_qualification_completed"] is False
    assert value["controller_commands"] == value["wire_commands"] == []
    assert value["hardware_access"] is value["physical_authority"] is False
    changed = copy.deepcopy(value)
    changed["eligible_for_executor"] = True
    with pytest.raises(TypingObservedIkSeedV1Error, match="hash differs"):
        parse_typing_observed_ik_seed_v1(changed)


def test_rejects_stale_crossed_and_future_state_binding():
    materialization, binding, observed, context, snapshot = _inputs()
    with pytest.raises(TypingObservedIkSeedV1Error, match="stale"):
        build_typing_observed_ik_seed_v1(
            materialization, binding, observed, context, snapshot,
            evaluated_monotonic_ns=1_001,
        )

    crossed = copy.deepcopy(binding)
    crossed["observed_start_state_sha256"] = "f" * 64
    with pytest.raises(TypingObservedIkSeedV1Error, match="hash differs"):
        build_typing_observed_ik_seed_v1(
            materialization, crossed, observed, context, snapshot,
            evaluated_monotonic_ns=250,
        )

    future = copy.deepcopy(binding)
    future["evaluated_monotonic_ns"] = 300
    unsigned = dict(future)
    unsigned.pop("state_binding_sha256")
    future["state_binding_sha256"] = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()
    with pytest.raises(TypingObservedIkSeedV1Error, match="predates"):
        build_typing_observed_ik_seed_v1(
            materialization, future, observed, context, snapshot,
            evaluated_monotonic_ns=250,
        )


def test_rejects_cross_calibration_and_cross_materialization():
    materialization, binding, observed, context, snapshot = _inputs()
    with pytest.raises(TypingObservedIkSeedV1Error, match="observed controller state"):
        build_typing_observed_ik_seed_v1(
            materialization, binding,
            replace(observed, calibration_snapshot_sha256="f" * 64),
            context, snapshot, evaluated_monotonic_ns=250,
        )

    crossed = copy.deepcopy(binding)
    crossed["materialization_sha256"] = "f" * 64
    unsigned = dict(crossed)
    unsigned.pop("state_binding_sha256")
    crossed["state_binding_sha256"] = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()
    with pytest.raises(TypingObservedIkSeedV1Error, match="materialization"):
        build_typing_observed_ik_seed_v1(
            materialization, crossed, observed, context, snapshot,
            evaluated_monotonic_ns=250,
        )
