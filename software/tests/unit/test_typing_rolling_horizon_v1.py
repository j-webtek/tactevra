from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from rocell.application.typing_execution_plan_v1 import (
    TypingExecutionConfigV1,
    compile_typing_execution_plan_v1,
)
from rocell.application.typing_rolling_horizon_v1 import (
    TypingObservedExecutionBindingV1,
    TypingRollingHorizonV1Error,
    complete_typing_current_action_v1,
    invalidate_typing_rolling_horizon_v1,
    parse_typing_rolling_horizon_v1,
    prepare_typing_rolling_horizon_v1,
    reconcile_typing_restart_v1,
    retain_typing_dispatch_intent_v1,
    revalidate_typing_rolling_horizon_v1,
)
from rocell.models import (
    Interaction,
    ModelMotionBatchV2,
    ModelMotionProposalV2,
    MotionCapabilityV2,
    MotionEvidenceV2,
    MotionGeometryV2,
    MotionUncertaintyV2,
    Point3Mm,
    ProposalDevice,
    SpeedClass,
    UncertaintyBoundType,
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _plan():
    targets = (("H", 0.0), ("H", 0.0), ("1", 20.0), ("PERIOD", 40.0))
    proposals = tuple(
        ModelMotionProposalV2(
            proposal_id=f"p-{index}", action_index=index,
            device=ProposalDevice.KEYBOARD, target_id=target,
            target=Point3Mm("board", x, 5.0, 2.0),
            interaction=Interaction.CONTACT, observation_confidence=0.99,
        )
        for index, (target, x) in enumerate(targets)
    )
    batch = ModelMotionBatchV2(
        batch_id="batch", request_id="request", intent_plan_sha256="1" * 64,
        device=ProposalDevice.KEYBOARD,
        capability=MotionCapabilityV2("keyboard-v1", "2" * 64),
        geometry=MotionGeometryV2(
            coordinate_profile="board_mm_xy_plane_v2", coordinate_units="mm",
            board_frame_definition_sha256="3" * 64,
            placement_observation_sha256="4" * 64,
            target_catalog_sha256="5" * 64,
        ),
        evidence=MotionEvidenceV2(
            capture_id="capture", frame_id="frame", image_sha256="6" * 64,
            camera_identity_sha256="7" * 64, capture_clock_domain_id="clock",
            model_id="model", model_sha256="8" * 64,
            scene_observation_sha256="9" * 64,
            precision_observation_sha256="a" * 64,
            fusion_decision_sha256="b" * 64, scene_lease_id="lease",
            scene_lease_issuer_id="issuer", scene_lease_sha256="c" * 64,
            captured_at_epoch_ms=1, evaluated_at_epoch_ms=2,
            expires_at_epoch_ms=10_000,
        ),
        uncertainty=MotionUncertaintyV2(
            bound_type=UncertaintyBoundType.PLANAR_L2_DISK,
            error_bound_mm=1.0, coverage_probability=0.99,
            qualification_sha256="d" * 64, evidence_method_sha256="e" * 64,
            domain_id="keyboard-v1", covered_target_ids=("H", "1", "PERIOD"),
        ),
        proposals=proposals,
    )
    ingress = {
        "schema": "rocell.model_motion_ingress.v2",
        "status": "ACCEPTED_V2_FOR_FRESH_SEQUENTIAL_PLANNER_GATES",
        "batch_sha256": batch.batch_sha256,
        "intent_plan_sha256": batch.intent_plan_sha256,
        "request_id": batch.request_id,
        "ordered_target_ids": [item.target_id for item in proposals],
        "controller_commands": [], "hardware_commands_generated": 0,
        "hardware_access": False, "physical_authority": False,
    }
    ingress["ingress_sha256"] = hashlib.sha256(_canonical(ingress)).hexdigest()
    config = TypingExecutionConfigV1(
        config_id="typing-v1", calibration_snapshot_sha256="f" * 64,
        tool_profile_sha256="0" * 64, dynamics_profile_sha256="1" * 64,
        route_reference_point=Point3Mm("board", -20.0, 0.0, 22.0),
        hover_clearance_mm=20.0, settle_position_tolerance_mm=0.5,
        settle_velocity_tolerance_mm_s=1.0, settle_hold_ms=100,
        preview_horizon=1, speed_class=SpeedClass.SLOW,
    )
    return compile_typing_execution_plan_v1(batch, ingress, config=config)


def _binding(**changes):
    values = dict(
        observed_start_state_sha256="2" * 64,
        feedback_receipt_sha256="3" * 64,
        configuration_epoch_sha256="4" * 64,
        calibration_snapshot_sha256="f" * 64,
        tool_profile_sha256="0" * 64,
        dynamics_profile_sha256="1" * 64,
        controller_session_id="session-1",
        valid_until_monotonic_ns=2_000,
    )
    values.update(changes)
    return TypingObservedExecutionBindingV1(**values)


def _state():
    return prepare_typing_rolling_horizon_v1(
        _plan(), _binding(), action_index=0, now_monotonic_ns=1_000,
        deadline_monotonic_ns=1_500,
    )


def test_one_current_and_one_zero_authority_preview_preserve_repetition():
    state = _state()
    assert state["current"]["target_id"] == "H"
    assert state["preview"]["target_id"] == "H"
    assert state["current"]["action_index"] == 0
    assert state["preview"]["action_index"] == 1
    assert state["current"]["action_sha256"] != state["preview"]["action_sha256"]
    for slot in (state["current"], state["preview"]):
        assert slot["permit_id"] is None and slot["permit_issued"] is False
        assert slot["controller_commands"] == []
        assert slot["physical_authority"] is False


@pytest.mark.parametrize("reason", [
    "OBSERVED_STATE_DRIFT", "CALIBRATION_CHANGED", "TOOL_PROFILE_CHANGED",
    "DYNAMICS_PROFILE_CHANGED", "CONFIGURATION_EPOCH_CHANGED", "EVIDENCE_STALE",
    "CONTROLLER_SESSION_CHANGED", "CANCELLED", "DEADLINE_EXPIRED",
])
def test_all_forced_invalidation_families_discard_current_and_preview(reason):
    invalid = invalidate_typing_rolling_horizon_v1(_state(), reason=reason)
    assert invalid["phase"] == "INVALIDATED"
    assert invalid["current"] is invalid["preview"] is None
    assert invalid["automatic_retry_allowed"] is False
    parse_typing_rolling_horizon_v1(invalid)


def test_binding_must_match_plan_and_be_fresh():
    plan = _plan()
    with pytest.raises(TypingRollingHorizonV1Error, match="tool profile"):
        prepare_typing_rolling_horizon_v1(
            plan, _binding(tool_profile_sha256="9" * 64), action_index=0,
            now_monotonic_ns=1_000, deadline_monotonic_ns=1_500,
        )
    with pytest.raises(TypingRollingHorizonV1Error, match="stale"):
        prepare_typing_rolling_horizon_v1(
            plan, _binding(valid_until_monotonic_ns=900), action_index=0,
            now_monotonic_ns=1_000, deadline_monotonic_ns=1_500,
        )


@pytest.mark.parametrize(("change", "expected"), [
    ({"controller_session_id": "session-2"}, "CONTROLLER_SESSION_CHANGED"),
    ({"configuration_epoch_sha256": "8" * 64}, "CONFIGURATION_EPOCH_CHANGED"),
    ({"calibration_snapshot_sha256": "8" * 64}, "CALIBRATION_CHANGED"),
    ({"tool_profile_sha256": "8" * 64}, "TOOL_PROFILE_CHANGED"),
    ({"dynamics_profile_sha256": "8" * 64}, "DYNAMICS_PROFILE_CHANGED"),
    ({"observed_start_state_sha256": "8" * 64}, "OBSERVED_STATE_DRIFT"),
    ({"feedback_receipt_sha256": "8" * 64}, "OBSERVED_STATE_DRIFT"),
])
def test_revalidation_detects_lineage_drift_and_discards_preview(change, expected):
    invalid = revalidate_typing_rolling_horizon_v1(
        _state(), _binding(**change), now_monotonic_ns=1_100)
    assert invalid["phase"] == "INVALIDATED"
    assert invalid["invalidation_reason"] == expected
    assert invalid["preview"] is None


def test_revalidation_detects_evidence_and_deadline_expiry():
    stale = revalidate_typing_rolling_horizon_v1(
        _state(), _binding(), now_monotonic_ns=2_001)
    assert stale["invalidation_reason"] == "EVIDENCE_STALE"
    deadline = revalidate_typing_rolling_horizon_v1(
        _state(), _binding(), now_monotonic_ns=1_501)
    assert deadline["invalidation_reason"] == "DEADLINE_EXPIRED"


def test_pre_dispatch_restart_reconstructs_without_replay_or_authority():
    restored = reconcile_typing_restart_v1(_state())
    assert restored["phase"] == "RECONSTRUCTED_PRE_DISPATCH"
    assert restored["restart_reconciliation"] == "PRE_DISPATCH_INTENT_RECONSTRUCTED_NO_REPLAY"
    assert restored["current"]["action_index"] == 0
    assert restored["preview"]["action_index"] == 1
    assert restored["controller_commands"] == []


def test_post_intent_restart_is_uncertain_and_retry_forbidden():
    retained = retain_typing_dispatch_intent_v1(
        _state(), dispatch_intent_sha256="5" * 64)
    assert retained["preview"] is None
    uncertain = reconcile_typing_restart_v1(retained)
    assert uncertain["phase"] == "OUTCOME_UNCERTAIN"
    assert uncertain["restart_reconciliation"] == "POST_DISPATCH_OR_AMBIGUOUS_RESTART_RETRY_FORBIDDEN"
    assert uncertain["automatic_retry_allowed"] is False
    assert uncertain["preview"] is None


def test_completion_is_bound_to_retained_intent_and_advances_only_by_new_prepare():
    retained = retain_typing_dispatch_intent_v1(
        _state(), dispatch_intent_sha256="5" * 64)
    completed = complete_typing_current_action_v1(
        retained, completion_receipt_sha256="6" * 64)
    assert completed["phase"] == "COMPLETED"
    assert completed["action_index"] == 0
    assert completed["preview"] is None
    next_state = prepare_typing_rolling_horizon_v1(
        _plan(), _binding(observed_start_state_sha256="7" * 64),
        action_index=1, now_monotonic_ns=1_100, deadline_monotonic_ns=1_600,
    )
    assert next_state["action_index"] == 1


def test_parser_rejects_rehashed_authority_and_crossed_epoch_mutations():
    for mutation in ("authority", "epoch"):
        document = deepcopy(_state())
        document.pop("rolling_horizon_sha256")
        if mutation == "authority":
            document["preview"]["permit_issued"] = True
        else:
            document["configuration_epoch_sha256"] = "8" * 64
        document["rolling_horizon_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
        with pytest.raises(TypingRollingHorizonV1Error):
            parse_typing_rolling_horizon_v1(document)


def test_same_input_is_deterministic_and_terminal_restart_is_rejected():
    assert _state() == _state()
    invalid = invalidate_typing_rolling_horizon_v1(_state(), reason="CANCELLED")
    with pytest.raises(TypingRollingHorizonV1Error, match="terminal"):
        reconcile_typing_restart_v1(invalid)
