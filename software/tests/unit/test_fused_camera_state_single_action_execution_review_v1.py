from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import jsonschema
import pytest

from rocell.application.context import load_simulation_context
from rocell.application.fused_camera_state_action_review_admission import (
    NEXT_REQUIRED_GATE,
    SCHEMA as ACTION_ADMISSION_SCHEMA,
    STATUS as ACTION_ADMISSION_STATUS,
    ZERO_AUTHORITY as ACTION_ADMISSION_ZERO_AUTHORITY,
)
from rocell.application.fused_camera_state_single_action_execution_review_v1 import (
    FusedCameraStateSingleActionExecutionReviewError,
    build_fused_camera_state_single_action_execution_review_v1,
)
from rocell.application.single_action_execution_review_v1 import (
    PhysicalEvidenceOrigin,
    SingleActionExecutionReviewError,
)

import test_single_action_execution_review_v1 as execution_review


@pytest.fixture(scope="module")
def context():
    return load_simulation_context(
        execution_review.WORKSPACE,
        execution_review.WORKSPACE / "software/config/system_manifest.json",
    )


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _admission(inputs, **changes):
    proposal = inputs[1]
    collision_qualification = inputs[4]
    core = {
        "schema": ACTION_ADMISSION_SCHEMA,
        "status": ACTION_ADMISSION_STATUS,
        "route_entry_admission_sha256": "1" * 64,
        "route_qualification_admission_sha256": "2" * 64,
        "route_bound_entry_qualification_sha256": "3" * 64,
        "action_review_policy_sha256": "4" * 64,
        "operator_confirmation_sha256": "5" * 64,
        "effect_verifier_binding_sha256": "6" * 64,
        "target_key_id": proposal.target_id,
        "action_index": proposal.action_index,
        "interaction": proposal.interaction.value,
        "expected_effect_sha256": "7" * 64,
        "attachment_profile": "no_attachment",
        "runtime_session_id": inputs[2].measured_envelope.controller_session_id,
        "route_envelope_binding_sha256": "8" * 64,
        "installed_collision_profile_sha256": (
            collision_qualification.installed_collision_profile_sha256
        ),
        "observed_route_entry_coverage_sha256": "9" * 64,
        "consumed_at": "2026-10-27T12:00:00+00:00",
        "valid_until": "2026-10-27T12:00:05+00:00",
        "fresh_route_entry_verified": True,
        "entry_dynamics_and_coverage_verified": True,
        "current_operator_verified": True,
        "independent_effect_verifier_verified": True,
        "per_action_policy_verified": True,
        "next_required_gate": NEXT_REQUIRED_GATE,
        "authority": dict(ACTION_ADMISSION_ZERO_AUTHORITY),
    }
    core.update(changes)
    return {**core, "action_review_admission_sha256": _sha(core)}


def _build(context, admission=None, **changes):
    inputs = list(execution_review._inputs(context))
    document = _admission(inputs) if admission is None else admission
    arguments = {
        "review_id": "fused-camera-action-0",
        "reviewed_at": "2026-10-27T12:00:01+00:00",
        "issued_monotonic_ns": 1_000,
        "deadline_monotonic_ns": 2_000,
    }
    arguments.update(changes)
    return build_fused_camera_state_single_action_execution_review_v1(
        document, *inputs, **arguments
    )


def test_fused_admission_creates_exact_zero_authority_review(context) -> None:
    inputs = execution_review._inputs(context)
    admission = _admission(inputs)
    review = _build(context, admission)
    document = review.to_dict()

    assert document["fused_camera_state_action_review_admission_sha256"] == (
        admission["action_review_admission_sha256"]
    )
    assert document["action_index"] == admission["action_index"]
    assert document["proposal_v2_sha256"] == inputs[1].proposal_sha256
    assert document["permit_issued"] is False
    assert document["hardware_access"] is False
    assert document["physical_authority"] is False
    jsonschema.Draft202012Validator(
        execution_review._schema("single_action_execution_review_v1.schema.json")
    ).validate(document)


def test_legacy_review_remains_valid_without_fused_admission(context) -> None:
    document = execution_review._review(context).to_dict()

    assert "fused_camera_state_action_review_admission_sha256" not in document
    jsonschema.Draft202012Validator(
        execution_review._schema("single_action_execution_review_v1.schema.json")
    ).validate(document)


def test_rejects_tampered_or_extended_admission(context) -> None:
    inputs = execution_review._inputs(context)
    tampered = _admission(inputs)
    tampered["target_key_id"] = "I"
    with pytest.raises(
        FusedCameraStateSingleActionExecutionReviewError, match="hash differs"
    ):
        _build(context, tampered)

    extended = _admission(inputs)
    extended["unexpected"] = False
    extended["action_review_admission_sha256"] = _sha(
        {key: value for key, value in extended.items()
         if key != "action_review_admission_sha256"}
    )
    with pytest.raises(
        FusedCameraStateSingleActionExecutionReviewError, match="fields differ"
    ):
        _build(context, extended)


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ({"target_key_id": "I"}, "selected model action"),
        ({"action_index": 1}, "selected model action"),
        ({"interaction": "HOVER"}, "selected model action"),
        ({"runtime_session_id": "other-session"}, "controller session"),
        ({"installed_collision_profile_sha256": "f" * 64}, "collision profile"),
    ),
)
def test_rejects_crossed_action_session_or_profile(context, change, message) -> None:
    inputs = execution_review._inputs(context)
    admission = _admission(inputs, **change)

    with pytest.raises(
        FusedCameraStateSingleActionExecutionReviewError, match=message
    ):
        _build(context, admission)


def test_rejects_stale_admission_or_review_that_outlives_it(context) -> None:
    inputs = execution_review._inputs(context)
    admission = _admission(inputs)
    with pytest.raises(
        FusedCameraStateSingleActionExecutionReviewError, match="unavailable or stale"
    ):
        _build(
            context,
            admission,
            reviewed_at="2026-10-27T12:00:06+00:00",
        )

    with pytest.raises(
        FusedCameraStateSingleActionExecutionReviewError, match="outlives"
    ):
        _build(
            context,
            admission,
            deadline_monotonic_ns=4_000_002_000,
        )


def test_existing_controller_collision_contact_and_t102_checks_remain_authoritative(
    context,
) -> None:
    inputs = list(execution_review._inputs(context))
    admission = _admission(inputs)
    inputs[4] = replace(
        inputs[4], evidence_origin=PhysicalEvidenceOrigin.SYNTHETIC_TEST_ONLY
    )

    with pytest.raises(SingleActionExecutionReviewError, match="not independently"):
        build_fused_camera_state_single_action_execution_review_v1(
            admission,
            *inputs,
            review_id="fused-camera-action-0",
            reviewed_at="2026-10-27T12:00:01+00:00",
            issued_monotonic_ns=1_000,
            deadline_monotonic_ns=2_000,
        )
