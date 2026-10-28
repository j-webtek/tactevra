"""Fused camera-state review orchestration into one supervisor permit."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.context import load_simulation_context
from rocell.application.fused_camera_state_reviewed_motion_permit_v1 import (
    FusedCameraStateReviewedMotionPermitError,
    FusedCameraStateReviewedMotionPermitSessionV1,
)
from rocell.application.single_action_execution_review_v1 import (
    SingleActionExecutionReviewError,
)
import rocell.application.t102_machine_ledger_v1 as ledger_module
from rocell.application.t102_machine_ledger_v1 import T102MachineLedgerError
from rocell.rc03.build_snapshot import Capability
from rocell.safety.supervisor import AuthorizationError, SafetySupervisor

import test_fused_camera_state_single_action_execution_review_v1 as fused_review
import test_single_action_execution_review_v1 as execution_review
from test_safety_core import (
    _advance_to_armed,
    _healthy_interlocks,
    _healthy_runtime,
    _valid_calibrations,
)


WORKSPACE = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def machine_ledger(tmp_path, monkeypatch):
    root = tmp_path / "machine-ledger"
    root.mkdir()
    monkeypatch.setattr(ledger_module, "machine_root", lambda: root)
    return root


@pytest.fixture(scope="module")
def context():
    return load_simulation_context(
        WORKSPACE, WORKSPACE / "software/config/system_manifest.json"
    )


def _session(context):
    return FusedCameraStateReviewedMotionPermitSessionV1(
        fused_review._build(context)
    )


def _arguments(now_ns: int = 1_500):
    now_s = now_ns / 1_000_000_000
    return {
        "calibrations": _valid_calibrations(),
        "interlocks": _healthy_interlocks(now_s),
        "runtime": _healthy_runtime(),
        "now_monotonic_ns": now_ns,
        "permit_ttl_ns": 400,
    }


def _supervisor(released_snapshot):
    supervisor = SafetySupervisor(released_snapshot)
    _advance_to_armed(supervisor)
    return supervisor


def test_fused_review_issues_one_exact_bound_supervisor_permit(
    context, released_snapshot,
) -> None:
    session = _session(context)
    result = session.issue(_supervisor(released_snapshot), **_arguments())
    review = fused_review._build(context)

    assert session.state == "CONSUMED"
    assert result.permit.capability is Capability.KEYBOARD_CONTACT
    assert result.permit.plan_hash == review.review_sha256
    assert result.permit.remaining_uses == 1
    assert result.admission.fused_camera_state_action_review_admission_sha256 == (
        review.fused_camera_state_action_review_admission_sha256
    )
    assert result.consumption_receipt["hardware_access"] is False
    assert result.lifecycle.snapshot()["phase"] == "ACCEPTED"
    schema = json.loads(
        (WORKSPACE / "software/ai/schemas/"
         "reviewed_motion_permit_admission_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(schema).validate(result.admission.to_dict())


def test_legacy_review_cannot_enter_fused_orchestrator(context) -> None:
    with pytest.raises(
        FusedCameraStateReviewedMotionPermitError,
        match="fused camera-state action review admission is required",
    ):
        FusedCameraStateReviewedMotionPermitSessionV1(
            execution_review._review(context)
        )


def test_invalid_ttl_rejects_before_consuming_review(
    context, released_snapshot,
) -> None:
    session = _session(context)
    invalid = {**_arguments(), "permit_ttl_ns": 501}
    with pytest.raises(
        FusedCameraStateReviewedMotionPermitError, match="would outlive"
    ):
        session.issue(_supervisor(released_snapshot), **invalid)
    assert session.state == "PENDING"

    result = session.issue(_supervisor(released_snapshot), **_arguments())
    assert result.permit.remaining_uses == 1


def test_session_cannot_consume_twice(context, released_snapshot) -> None:
    session = _session(context)
    session.issue(_supervisor(released_snapshot), **_arguments())
    with pytest.raises(SingleActionExecutionReviewError, match="already consumed"):
        session.issue(_supervisor(released_snapshot), **_arguments())


def test_reconstructed_review_cannot_reserve_with_a_new_receipt(
    context, released_snapshot,
) -> None:
    _session(context).issue(_supervisor(released_snapshot), **_arguments())
    with pytest.raises(T102MachineLedgerError, match="already spent"):
        _session(context).issue(
            _supervisor(released_snapshot), **_arguments(now_ns=1_600)
        )


def test_preflight_failure_burns_reconstructed_review(
    context, released_snapshot,
) -> None:
    blocked = {**_arguments(), "runtime": type(_healthy_runtime())()}
    with pytest.raises(AuthorizationError, match="Preflight is blocked"):
        _session(context).issue(_supervisor(released_snapshot), **blocked)
    with pytest.raises(T102MachineLedgerError, match="already spent"):
        _session(context).issue(_supervisor(released_snapshot), **_arguments())
