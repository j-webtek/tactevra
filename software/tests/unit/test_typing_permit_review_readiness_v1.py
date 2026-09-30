from __future__ import annotations

import copy

import pytest

from rocell.application.typing_permit_review_readiness_v1 import (
    TypingPermitReviewReadinessV1Error,
    assess_typing_permit_review_readiness_v1,
    parse_typing_permit_review_readiness_v1,
)
from software.scripts import run_typing_command_session_ledger_campaign_v1 as runner


def _materialization():
    ledger, _supervisor = runner._ledger()
    ledger.submit("mission-ready", "ready", runner._inputs(ledger, "ready"))
    ledger.run_next_shadow()
    return ledger.shadow_materialization("ready")


def test_current_shadow_reports_exact_physical_review_gap():
    value = assess_typing_permit_review_readiness_v1(_materialization())
    assert parse_typing_permit_review_readiness_v1(value) == value
    assert value["retained_stage_count"] == 5
    assert value["satisfied_prerequisites"] == [
        "EXACT_SHADOW_PIPELINE_RECEIPT_RETAINED",
        "FIVE_PLANNING_STAGE_BODIES_RETAINED",
        "PLANNING_STAGE_HASH_LINEAGE_VERIFIED",
    ]
    assert value["blockers"] == [
        "DEPLOYMENT_QUALIFIED_PLAN_REQUIRED",
        "MEASURED_TRAJECTORY_ENVELOPE_REQUIRED",
        "INSTALLED_COLLISION_PROFILE_REQUIRED",
        "CONTINUOUS_COLLISION_QUALIFICATION_REQUIRED",
        "FRESH_OBSERVED_START_STATE_REQUIRED",
        "FRESH_INSTALLED_CONTROLLER_QUALIFICATION_REQUIRED",
        "INDEPENDENT_EFFECT_VERIFIER_REQUIRED",
        "PER_ACTION_REVIEW_BINDINGS_REQUIRED",
    ]
    assert value["permit_review_ready"] is False
    assert value["controller_commands"] == value["wire_commands"] == []
    assert value["hardware_access"] is value["physical_authority"] is False


def test_readiness_is_deterministic_and_binds_materialization():
    materialization = _materialization()
    first = assess_typing_permit_review_readiness_v1(materialization)
    second = assess_typing_permit_review_readiness_v1(materialization)
    assert first == second
    assert first["materialization_sha256"] == materialization[
        "materialization_sha256"
    ]
    assert first["retained_stage_hashes"] == materialization["stage_hashes"]


def test_materialization_and_report_tampering_are_rejected():
    materialization = _materialization()
    changed = copy.deepcopy(materialization)
    changed["request_id"] = "different"
    with pytest.raises(TypingPermitReviewReadinessV1Error):
        assess_typing_permit_review_readiness_v1(changed)

    report = assess_typing_permit_review_readiness_v1(materialization)
    report["permit_review_ready"] = True
    with pytest.raises(TypingPermitReviewReadinessV1Error):
        parse_typing_permit_review_readiness_v1(report)

    report = assess_typing_permit_review_readiness_v1(materialization)
    report["unexpected"] = False
    with pytest.raises(TypingPermitReviewReadinessV1Error, match="fields"):
        parse_typing_permit_review_readiness_v1(report)


def test_shadow_collision_intake_cannot_claim_continuous_clearance():
    materialization = _materialization()
    changed = copy.deepcopy(materialization)
    collision = changed["stage_artifacts"]["typing_collision_intake"]
    collision["continuous_collision_proven"] = True
    # Rehashing only the outer bundle must not make altered stage content valid.
    with pytest.raises(TypingPermitReviewReadinessV1Error):
        assess_typing_permit_review_readiness_v1(changed)
