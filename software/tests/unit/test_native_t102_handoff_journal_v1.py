"""Durable native-handoff tests; filesystem only, with zero device I/O."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.native_t102_handoff_journal_v1 import (
    DurableNativeT102HandoffV1,
    NativeT102HandoffJournalError,
    NativeT102HandoffPhase,
    NativeT102RecoveryDisposition,
    load_native_t102_handoff_v1,
)
from rocell.application.production_controller_runtime_contract_v1 import (
    RuntimeCommandFrameV1,
)
from rocell.application.reviewed_motion_permit_bridge_v1 import (
    ReviewedMotionPermitAdmissionV1,
)
from rocell.arm.all_joint_command import all_joint_command
from rocell.arm.protocol import encode_line
from rocell.rc03.build_snapshot import Capability
from rocell.safety.permit import goal_hash


WORKSPACE = Path(__file__).resolve().parents[3]
ADAPTER = "f" * 64


def _hash(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _message(offset=0.0):
    return all_joint_command(
        [offset + value for value in (.1, .2, .3, .4, .5, .6)],
        speed=20, acceleration=1,
    )


def _frame(message=None, **changes):
    values = dict(
        sequence=1,
        correlation_id="arm050-correlation-1",
        writer_instance_id="arm050-writer",
        controller_session_id="arm050-controller-session",
        configuration_epoch_sha256="d" * 64,
        encoding_profile_sha256="e" * 64,
        issued_monotonic_ns=900,
        expires_monotonic_ns=2_000,
        wire_bytes=encode_line(message or _message()),
    )
    values.update(changes)
    return RuntimeCommandFrameV1(**values)


def _admission(message=None, **changes):
    review = "a" * 64
    values = dict(
        review_sha256=review,
        consumption_sha256="b" * 64,
        capability=Capability.KEYBOARD_CONTACT,
        snapshot_sha256="c" * 64,
        ordered_goal_sha256=(goal_hash(message or _message()),),
        permit_expires_at_monotonic=102.0,
    )
    values.update(changes)
    binding = _hash({
        "review_sha256": values["review_sha256"],
        "consumption_sha256": values["consumption_sha256"],
        "capability": values["capability"].value,
        "snapshot_sha256": values["snapshot_sha256"],
        "plan_hash": values["review_sha256"],
        "ordered_goal_sha256": list(values["ordered_goal_sha256"]),
        "permit_expires_at_monotonic": values["permit_expires_at_monotonic"],
    })
    return ReviewedMotionPermitAdmissionV1(
        **values, permit_binding_sha256=binding)


def _prepare(tmp_path):
    message = _message()
    frame = _frame(message)
    admission = _admission(message)
    journal = DurableNativeT102HandoffV1.prepare(
        tmp_path, frame, admission, adapter_candidate_sha256=ADAPTER,
        created_monotonic_ns=950,
    )
    return journal, frame, admission


def _schema(name="native_t102_handoff_snapshot_v1.schema.json"):
    return json.loads((
        WORKSPACE / "software/ai/schemas" / name
    ).read_text(encoding="utf-8"))


def test_prepared_handoff_is_durable_cancellable_and_has_no_authority(tmp_path):
    journal, _, _ = _prepare(tmp_path)
    snapshot = journal.snapshot()
    document = snapshot.to_dict()
    assert snapshot.phase is NativeT102HandoffPhase.PREPARED
    assert snapshot.recovery_disposition is (
        NativeT102RecoveryDisposition.CANCEL_AND_REPLAN_WITH_FRESH_AUTHORITY)
    assert {item.name for item in journal.directory.iterdir()} == {"prepared.json"}
    assert document["transport_open_authorized"] is False
    assert document["physical_authority"] is False
    assert document["automatic_retry_allowed"] is False
    assert document["transport_open_count"] == 0
    assert document["physical_command_writes"] == 0
    assert "fused_camera_state_action_review_admission_sha256" not in document
    assert "review_consumption_sha256" not in document
    prepared = json.loads((journal.directory / "prepared.json").read_text(
        encoding="utf-8"))
    assert "fused_camera_state_action_review_admission_sha256" not in prepared
    assert "review_consumption_sha256" not in prepared
    jsonschema.Draft202012Validator(_schema()).validate(document)
    jsonschema.Draft202012Validator(_schema(
        "native_t102_handoff_prepared_v1.schema.json"
    )).validate(prepared)


def test_claim_is_exclusive_persistent_and_restart_forbids_retry(tmp_path):
    journal, frame, admission = _prepare(tmp_path)
    claimed = journal.claim_writer(
        frame, admission, adapter_candidate_sha256=ADAPTER,
        claimed_monotonic_ns=1_000,
    )
    reopened = load_native_t102_handoff_v1(journal.directory)
    assert claimed == reopened
    assert reopened.phase is NativeT102HandoffPhase.WRITER_CLAIMED
    assert reopened.claim_sha256 is not None
    assert reopened.recovery_disposition is (
        NativeT102RecoveryDisposition.RETRY_FORBIDDEN_DISPATCH_UNCERTAIN)
    assert {item.name for item in journal.directory.iterdir()} == {
        "prepared.json", "claim.json"}
    assert reopened.to_dict()["transport_open_authorized"] is False
    jsonschema.Draft202012Validator(_schema()).validate(reopened.to_dict())
    jsonschema.Draft202012Validator(_schema(
        "native_t102_writer_claim_v1.schema.json"
    )).validate(json.loads((journal.directory / "claim.json").read_text(
        encoding="utf-8")))


def test_concurrent_claim_has_exactly_one_winner(tmp_path):
    journal, frame, admission = _prepare(tmp_path)

    def claim():
        try:
            journal.claim_writer(
                frame, admission, adapter_candidate_sha256=ADAPTER,
                claimed_monotonic_ns=1_000,
            )
            return "CLAIMED"
        except NativeT102HandoffJournalError:
            return "REJECTED"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: claim(), range(8)))
    assert outcomes.count("CLAIMED") == 1
    assert outcomes.count("REJECTED") == 7
    assert journal.snapshot().recovery_disposition is (
        NativeT102RecoveryDisposition.RETRY_FORBIDDEN_DISPATCH_UNCERTAIN)


@pytest.mark.parametrize("crossed", [
    {"controller_session_id": "crossed-session"},
    {"configuration_epoch_sha256": "1" * 64},
    {"encoding_profile_sha256": "2" * 64},
    {"writer_instance_id": "crossed-writer"},
    {"wire_bytes": encode_line(_message(.01))},
])
def test_crossed_claim_inputs_reject_without_publishing_claim(tmp_path, crossed):
    journal, frame, admission = _prepare(tmp_path)
    values = dict(
        sequence=frame.sequence,
        correlation_id=frame.correlation_id,
        writer_instance_id=frame.writer_instance_id,
        controller_session_id=frame.controller_session_id,
        configuration_epoch_sha256=frame.configuration_epoch_sha256,
        encoding_profile_sha256=frame.encoding_profile_sha256,
        issued_monotonic_ns=frame.issued_monotonic_ns,
        expires_monotonic_ns=frame.expires_monotonic_ns,
        wire_bytes=frame.wire_bytes,
    )
    values.update(crossed)
    with pytest.raises(NativeT102HandoffJournalError, match="differ"):
        journal.claim_writer(
            RuntimeCommandFrameV1(**values), admission,
            adapter_candidate_sha256=ADAPTER, claimed_monotonic_ns=1_000,
        )
    assert journal.snapshot().phase is NativeT102HandoffPhase.PREPARED
    assert not (journal.directory / "claim.json").exists()


def test_stale_or_duplicate_claim_never_opens_transport(tmp_path):
    journal, frame, admission = _prepare(tmp_path)
    with pytest.raises(NativeT102HandoffJournalError, match="timing"):
        journal.claim_writer(
            frame, admission, adapter_candidate_sha256=ADAPTER,
            claimed_monotonic_ns=2_000,
        )
    assert journal.snapshot().phase is NativeT102HandoffPhase.PREPARED
    journal.claim_writer(
        frame, admission, adapter_candidate_sha256=ADAPTER,
        claimed_monotonic_ns=1_000,
    )
    with pytest.raises(NativeT102HandoffJournalError, match="already"):
        journal.claim_writer(
            frame, admission, adapter_candidate_sha256=ADAPTER,
            claimed_monotonic_ns=1_001,
        )
    assert journal.snapshot().to_dict()["transport_open_count"] == 0


def test_duplicate_prepare_and_tampering_fail_closed(tmp_path):
    journal, frame, admission = _prepare(tmp_path)
    with pytest.raises(NativeT102HandoffJournalError, match="already exists"):
        DurableNativeT102HandoffV1.prepare(
            tmp_path, frame, admission, adapter_candidate_sha256=ADAPTER,
            created_monotonic_ns=950,
        )
    prepared = journal.directory / "prepared.json"
    value = json.loads(prepared.read_text(encoding="utf-8"))
    value["controller_session_id"] = "tampered-session"
    prepared.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    with pytest.raises(
        NativeT102HandoffJournalError, match="invalid|noncanonical",
    ):
        journal.snapshot()


def test_truncated_claim_marker_fails_closed_instead_of_resuming(tmp_path):
    journal, _, _ = _prepare(tmp_path)
    (journal.directory / "claim.json").write_bytes(b'{"schema":')
    with pytest.raises(NativeT102HandoffJournalError, match="invalid JSON"):
        journal.snapshot()
    assert (journal.directory / "claim.json").exists()


def test_unexpected_entry_and_symlink_root_fail_closed(tmp_path):
    journal, _, _ = _prepare(tmp_path)
    (journal.directory / "unexpected.txt").write_text("x", encoding="utf-8")
    with pytest.raises(NativeT102HandoffJournalError, match="entries"):
        journal.snapshot()

    link = tmp_path / "linked-root"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    with pytest.raises(NativeT102HandoffJournalError, match="root"):
        DurableNativeT102HandoffV1.prepare(
            link, _frame(), _admission(), adapter_candidate_sha256=ADAPTER,
            created_monotonic_ns=950,
        )
