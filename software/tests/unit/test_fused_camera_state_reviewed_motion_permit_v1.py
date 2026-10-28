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
    execute_fused_camera_state_reviewed_t102_runtime_rehearsal_v1,
    prepare_fused_camera_state_native_t102_handoff_v1,
)
from rocell.application.production_controller_runtime_contract_v1 import (
    ProductionControllerRuntimeContractV1,
    ProductionControllerRuntimeManifestV1,
    RuntimeCommandFrameV1,
)
from rocell.application.reviewed_motion_sole_writer_v1 import (
    IncapableReviewedMotionIoV1,
    IncapableWriteFault,
)
from rocell.application.single_action_execution_review_v1 import (
    SingleActionExecutionReviewError,
)
import rocell.application.t102_machine_ledger_v1 as ledger_module
from rocell.application.t102_machine_ledger_v1 import T102MachineLedgerError
from rocell.arm.all_joint_command import JOINT_FIELDS
from rocell.arm.protocol import encode_line
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
ADAPTER = "f" * 64


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


def _runtime_frame(context, *, offset: float = 0.0):
    inputs = execution_review._inputs(context)
    measured = inputs[2].measured_envelope
    goal = execution_review._t102_goal(context)
    if offset:
        goal = {**goal, "base": goal["base"] + offset}
    manifest = ProductionControllerRuntimeManifestV1(
        runtime_id="arm-159-fused-runtime",
        candidate_app_sha256="a" * 64,
        protocol_source_sha256="b" * 64,
        controller_joint_mapping_sha256="c" * 64,
        configuration_epoch_sha256=measured.configuration_epoch_sha256,
        expected_encoding_profile_sha256="3" * 64,
        controller_session_id=measured.controller_session_id,
    )
    frame = RuntimeCommandFrameV1(
        sequence=1,
        correlation_id="arm-159-fused-action-0",
        writer_instance_id="arm-159-writer",
        controller_session_id=manifest.controller_session_id,
        configuration_epoch_sha256=manifest.configuration_epoch_sha256,
        encoding_profile_sha256=manifest.expected_encoding_profile_sha256,
        issued_monotonic_ns=1_550,
        expires_monotonic_ns=1_900,
        wire_bytes=encode_line(goal),
    )
    return goal, frame, ProductionControllerRuntimeContractV1(manifest)


def _ack():
    return encode_line({"T": 1021, "status": "ACCEPTED_ONCE", "ordinal": 1})


def _feedback(goal, captured_monotonic_ns):
    return {
        "captured_monotonic_ns": captured_monotonic_ns,
        "response_bytes": encode_line({
            "T": 1051,
            **dict(zip(("b", "s", "e", "t", "r", "g"),
                       (goal[name] for name in JOINT_FIELDS))),
        }),
    }


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


def test_fused_permit_rehearses_one_t102_write_ack_and_settlement(
    context, released_snapshot,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    goal, frame, runtime = _runtime_frame(context)
    report = execute_fused_camera_state_reviewed_t102_runtime_rehearsal_v1(
        result,
        frame,
        runtime,
        IncapableReviewedMotionIoV1(),
        _ack(),
        [_feedback(goal, 1_700), _feedback(goal, 1_750)],
        writer_instance_id="arm-159-writer",
        dispatch_monotonic_ns=1_600,
        assessment_monotonic_ns=1_800,
    )

    assert report["status"] == "COMPLETED"
    assert report["fused_camera_state_action_review_admission_sha256"] == (
        result.admission.fused_camera_state_action_review_admission_sha256
    )
    assert report["review_consumption_sha256"] == (
        result.consumption_receipt["consumption_sha256"]
    )
    assert report["dispatch"]["write_attempts"] == 1
    assert report["acknowledgment"]["status"] == "ACCEPTED_ONCE"
    assert report["settlement"]["status"] == (
        "OBSERVED_SETTLED_JOINT_ARRIVAL"
    )
    assert report["automatic_retry_allowed"] is False
    assert report["physical_command_writes"] == 0
    assert result.permit.remaining_uses == 0
    schema = json.loads(
        (WORKSPACE / "software/ai/schemas/"
         "reviewed_t102_runtime_execution_rehearsal_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(schema).validate(report)


def test_fused_permit_prepares_cancellable_native_handoff_without_claim(
    context, released_snapshot, tmp_path,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    _, frame, _ = _runtime_frame(context)
    handoff_root = tmp_path / "handoffs"
    handoff_root.mkdir()
    journal = prepare_fused_camera_state_native_t102_handoff_v1(
        result,
        frame,
        handoff_root,
        adapter_candidate_sha256=ADAPTER,
        created_monotonic_ns=1_600,
    )

    snapshot = journal.snapshot()
    document = snapshot.to_dict()
    prepared = json.loads(
        (journal.directory / "prepared.json").read_text(encoding="utf-8")
    )
    assert document["phase"] == "PREPARED"
    assert document["recovery_disposition"] == (
        "CANCEL_AND_REPLAN_WITH_FRESH_AUTHORITY"
    )
    assert document["fused_camera_state_action_review_admission_sha256"] == (
        result.admission.fused_camera_state_action_review_admission_sha256
    )
    assert document["review_consumption_sha256"] == (
        result.admission.consumption_sha256
    )
    assert prepared["permit_binding_sha256"] == (
        result.admission.permit_binding_sha256
    )
    assert prepared["fused_camera_state_action_review_admission_sha256"] == (
        result.admission.fused_camera_state_action_review_admission_sha256
    )
    assert prepared["review_consumption_sha256"] == (
        result.admission.consumption_sha256
    )
    assert {item.name for item in journal.directory.iterdir()} == {
        "prepared.json"
    }
    assert document["transport_open_count"] == 0
    assert document["physical_command_writes"] == 0
    assert result.permit.remaining_uses == 1
    assert result.lifecycle.snapshot()["phase"] == "ACCEPTED"
    for name, value in (
        ("native_t102_handoff_snapshot_v1.schema.json", document),
        ("native_t102_handoff_prepared_v1.schema.json", prepared),
    ):
        schema = json.loads(
            (WORKSPACE / "software/ai/schemas" / name).read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(value)


def test_crossed_fused_native_handoff_rejects_before_publishing(
    context, released_snapshot, tmp_path,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    _, frame, _ = _runtime_frame(context, offset=0.1)
    handoff_root = tmp_path / "handoffs"
    handoff_root.mkdir()
    with pytest.raises(
        FusedCameraStateReviewedMotionPermitError, match="differs"
    ):
        prepare_fused_camera_state_native_t102_handoff_v1(
            result,
            frame,
            handoff_root,
            adapter_candidate_sha256=ADAPTER,
            created_monotonic_ns=1_600,
        )
    assert tuple(handoff_root.iterdir()) == ()
    assert result.permit.remaining_uses == 1


def test_fused_runtime_write_uncertainty_is_terminal_without_retry(
    context, released_snapshot,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    _, frame, runtime = _runtime_frame(context)
    io = IncapableReviewedMotionIoV1(IncapableWriteFault.PARTIAL_WRITE)
    report = execute_fused_camera_state_reviewed_t102_runtime_rehearsal_v1(
        result,
        frame,
        runtime,
        io,
        _ack(),
        (),
        writer_instance_id="arm-159-writer",
        dispatch_monotonic_ns=1_600,
        assessment_monotonic_ns=1_800,
    )

    assert report["status"] == "UNCERTAIN"
    assert report["acknowledgment"] is None
    assert report["settlement"] is None
    assert report["automatic_retry_allowed"] is False
    assert report["follow_on_movement_authorized"] is False
    assert io.write_attempts == 1
    assert result.permit.remaining_uses == 0


def test_crossed_fused_t102_goal_rejects_before_consumption_or_write(
    context, released_snapshot,
) -> None:
    result = _session(context).issue(
        _supervisor(released_snapshot), **_arguments()
    )
    _, frame, runtime = _runtime_frame(context, offset=0.1)
    io = IncapableReviewedMotionIoV1()
    with pytest.raises(ValueError, match="identity differs"):
        execute_fused_camera_state_reviewed_t102_runtime_rehearsal_v1(
            result,
            frame,
            runtime,
            io,
            _ack(),
            (),
            writer_instance_id="arm-159-writer",
            dispatch_monotonic_ns=1_600,
            assessment_monotonic_ns=1_800,
        )
    assert io.write_attempts == 0
    assert result.permit.remaining_uses == 1
