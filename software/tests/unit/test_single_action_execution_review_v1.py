from __future__ import annotations

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.installed_controller_qualification_v1 import (
    EXPECTED_ARM_JOINT_ORDER,
    EXPECTED_T102_FIELDS,
    EXPECTED_T1051_FIELDS,
    EvidenceOrigin as ControllerEvidenceOrigin,
    InstalledControllerQualificationEvidenceV1,
    InstalledControllerQualificationReportV1,
    ReviewDisposition as ControllerReviewDisposition,
)
from rocell.application.context import load_simulation_context
from rocell.arm.all_joint_command import all_joint_command
from rocell.kinematics import ARM_JOINT_NAMES
from rocell.application.phase_local_contact_envelope_gate import (
    bind_phase_local_contact_envelope_gate,
)
from rocell.application.single_action_execution_review_v1 import (
    InstalledCollisionPolicyQualificationV1,
    InstalledT102CommandProfileV1,
    PhysicalEvidenceOrigin,
    PhysicalReviewDisposition,
    SingleActionExecutionReviewError,
    SingleUseExecutionReviewGateV1,
    build_single_action_execution_review_v1,
)

import test_phase_local_contact_envelope_gate as contact
import test_trajectory_execution_envelope_v2 as envelope_v2


WORKSPACE = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def context():
    return load_simulation_context(
        WORKSPACE, WORKSPACE / "software/config/system_manifest.json"
    )


def _inputs(context):
    proposal, installed, route, sweep, envelope, allowance = (
        contact._qualified_inputs(context)
    )
    batch, _ = envelope_v2._planner_inputs()
    contact_report = bind_phase_local_contact_envelope_gate(
        proposal, installed, route, sweep, envelope,
        contact_allowance=allowance,
    )
    collision_qualification = InstalledCollisionPolicyQualificationV1(
        qualification_id="installed-keyboard-contact-v1",
        installed_collision_profile_sha256=installed.content_sha256,
        phase_local_contact_allowance_sha256=allowance.content_sha256,
        physical_measurement_evidence_sha256="1" * 64,
        independent_review_decision_sha256="2" * 64,
        captured_monotonic_ns=900,
        valid_until_monotonic_ns=10_000,
        evidence_origin=PhysicalEvidenceOrigin.PHYSICAL_RETAINED_ORIGINALS,
        review_disposition=PhysicalReviewDisposition.INDEPENDENTLY_APPROVED,
    )
    measured = envelope.measured_envelope
    controller_evidence = InstalledControllerQualificationEvidenceV1(
        qualification_id="installed-controller-arm-046",
        controller_binding_sha256="3" * 64,
        installed_firmware_evidence_sha256="4" * 64,
        qualified_protocol_source_sha256="5" * 64,
        controller_joint_mapping_evidence_sha256="6" * 64,
        controller_joint_mapping_sha256="7" * 64,
        feedback_protocol_evidence_sha256="8" * 64,
        startup_behavior_evidence_sha256="9" * 64,
        configuration_epoch_sha256=measured.configuration_epoch_sha256,
        controller_session_id=measured.controller_session_id,
        captured_monotonic_ns=900,
        valid_until_monotonic_ns=10_000,
        t102_command_fields=EXPECTED_T102_FIELDS,
        t1051_feedback_fields=EXPECTED_T1051_FIELDS,
        arm_joint_order=EXPECTED_ARM_JOINT_ORDER,
        fixed_gripper_field="hand",
        evidence_origin=ControllerEvidenceOrigin.PHYSICAL_RETAINED_ORIGINALS,
        review_disposition=ControllerReviewDisposition.INDEPENDENTLY_APPROVED,
    )
    controller_qualification = InstalledControllerQualificationReportV1(
        encoding_profile_sha256="3" * 64,
        qualification_evidence_sha256=controller_evidence.evidence_sha256,
        evaluated_monotonic_ns=950,
        blockers=(),
    )
    t102_profile = InstalledT102CommandProfileV1(
        trajectory_execution_envelope_v2_sha256=envelope.envelope_v2_sha256,
        controller_qualification_evidence_sha256=controller_evidence.evidence_sha256,
        observed_hand_feedback_sha256="a" * 64,
        reviewed_path_evidence_sha256="b" * 64,
        independent_approval_sha256="c" * 64,
        hand_target_rad=0.0, speed=20, acceleration=1,
        captured_monotonic_ns=900,
        valid_until_monotonic_ns=10_000,
        evidence_origin=PhysicalEvidenceOrigin.PHYSICAL_RETAINED_ORIGINALS,
        review_disposition=PhysicalReviewDisposition.INDEPENDENTLY_APPROVED,
    )
    return (
        batch, proposal, envelope, contact_report,
        collision_qualification, controller_evidence, controller_qualification,
        t102_profile,
    )


def _review(context):
    return build_single_action_execution_review_v1(
        *_inputs(context),
        review_id="arm-046-action-0",
        issued_monotonic_ns=1_000,
        deadline_monotonic_ns=2_000,
    )


def _t102_goal(context):
    inputs = _inputs(context)
    endpoint = inputs[2].measured_envelope.waypoints[-1].joint_positions_rad
    profile = inputs[7]
    return all_joint_command(
        [*(endpoint[name] for name in ARM_JOINT_NAMES),
         profile.hand_target_rad],
        speed=profile.speed, acceleration=profile.acceleration,
    )


def _schema(name: str) -> dict:
    return json.loads(
        (WORKSPACE / "software/ai/schemas" / name).read_text(encoding="utf-8")
    )


def test_review_binds_exact_lineages_and_consumes_once(context) -> None:
    review = _review(context)
    review_document = review.to_dict()
    jsonschema.Draft202012Validator(
        _schema("single_action_execution_review_v1.schema.json")
    ).validate(review_document)
    assert review_document["permit_issued"] is False
    assert review_document["controller_commands"] == []
    assert review_document["physical_authority"] is False

    gate = SingleUseExecutionReviewGateV1(review)
    receipt = gate.consume(review.review_sha256, consumed_monotonic_ns=1_500)
    jsonschema.Draft202012Validator(
        _schema("single_action_execution_review_consumption_v1.schema.json")
    ).validate(receipt)
    assert gate.state == "CONSUMED"
    assert receipt["permit_issued"] is False
    with pytest.raises(SingleActionExecutionReviewError, match="already consumed"):
        gate.consume(review.review_sha256, consumed_monotonic_ns=1_600)


def test_collision_policy_qualification_has_closed_schema(context) -> None:
    qualification = _inputs(context)[4]
    jsonschema.Draft202012Validator(
        _schema("installed_collision_policy_qualification_v1.schema.json")
    ).validate(qualification.to_dict())
    assert qualification.execution_review_ready is True


def test_review_rejects_crossed_and_synthetic_qualification(context) -> None:
    values = list(_inputs(context))
    values[3] = {**values[3], "proposal_v2_sha256": "f" * 64}
    with pytest.raises(SingleActionExecutionReviewError, match="content hash"):
        build_single_action_execution_review_v1(
            *values, review_id="crossed", issued_monotonic_ns=1_000,
            deadline_monotonic_ns=2_000,
        )

    values = list(_inputs(context))
    values[4] = replace(
        values[4], evidence_origin=PhysicalEvidenceOrigin.SYNTHETIC_TEST_ONLY)
    with pytest.raises(SingleActionExecutionReviewError, match="not independently"):
        build_single_action_execution_review_v1(
            *values, review_id="synthetic", issued_monotonic_ns=1_000,
            deadline_monotonic_ns=2_000,
        )


def test_review_rejects_stale_controller_or_collision_evidence(context) -> None:
    values = list(_inputs(context))
    values[4] = replace(values[4], valid_until_monotonic_ns=999)
    with pytest.raises(SingleActionExecutionReviewError, match="stale"):
        build_single_action_execution_review_v1(
            *values, review_id="stale", issued_monotonic_ns=1_000,
            deadline_monotonic_ns=2_000,
        )

    values = list(_inputs(context))
    values[4] = replace(values[4], valid_until_monotonic_ns=1_500)
    with pytest.raises(SingleActionExecutionReviewError, match="outlives"):
        build_single_action_execution_review_v1(
            *values, review_id="outlives-collision", issued_monotonic_ns=1_000,
            deadline_monotonic_ns=2_000,
        )

    values = list(_inputs(context))
    values[7] = replace(
        values[7], evidence_origin=PhysicalEvidenceOrigin.SYNTHETIC_TEST_ONLY)
    with pytest.raises(SingleActionExecutionReviewError,
                       match="approved single-T102"):
        build_single_action_execution_review_v1(
            *values, review_id="synthetic-t102", issued_monotonic_ns=1_000,
            deadline_monotonic_ns=2_000,
        )

    values = list(_inputs(context))
    values[6] = replace(values[6], blockers=("EVIDENCE_STALE",))
    with pytest.raises(SingleActionExecutionReviewError, match="not ready"):
        build_single_action_execution_review_v1(
            *values, review_id="blocked", issued_monotonic_ns=1_000,
            deadline_monotonic_ns=2_000,
        )


def test_review_rejects_crossed_controller_epoch_and_session(context) -> None:
    for change in (
        {"configuration_epoch_sha256": "f" * 64},
        {"controller_session_id": "other-controller-session"},
    ):
        values = list(_inputs(context))
        values[5] = replace(values[5], **change)
        values[6] = replace(
            values[6],
            qualification_evidence_sha256=values[5].evidence_sha256,
        )
        with pytest.raises(
            SingleActionExecutionReviewError, match="execution envelope"
        ):
            build_single_action_execution_review_v1(
                *values, review_id="crossed-controller",
                issued_monotonic_ns=1_000, deadline_monotonic_ns=2_000,
            )


def test_review_cancellation_expiry_and_digest_mismatch_fail_closed(context) -> None:
    review = _review(context)
    cancelled = SingleUseExecutionReviewGateV1(review)
    cancelled.cancel()
    with pytest.raises(SingleActionExecutionReviewError, match="cancelled"):
        cancelled.consume(review.review_sha256, consumed_monotonic_ns=1_500)

    expired = SingleUseExecutionReviewGateV1(review)
    with pytest.raises(SingleActionExecutionReviewError, match="expired"):
        expired.consume(review.review_sha256, consumed_monotonic_ns=2_001)
    assert expired.state == "PENDING"

    mismatched = SingleUseExecutionReviewGateV1(review)
    with pytest.raises(SingleActionExecutionReviewError, match="does not match"):
        mismatched.consume("f" * 64, consumed_monotonic_ns=1_500)
    assert mismatched.state == "PENDING"


def test_review_consumption_is_atomic_under_concurrency(context) -> None:
    review = _review(context)
    gate = SingleUseExecutionReviewGateV1(review)

    def consume_once():
        try:
            gate.consume(review.review_sha256, consumed_monotonic_ns=1_500)
            return "CONSUMED"
        except SingleActionExecutionReviewError:
            return "REJECTED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(lambda _: consume_once(), range(2)))
    assert outcomes == ["CONSUMED", "REJECTED"]
    assert gate.state == "CONSUMED"
