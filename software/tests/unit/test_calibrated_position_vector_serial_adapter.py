import json
from datetime import datetime, timedelta, timezone

import pytest

from rocell.application.calibrated_position_vector_feedback_execution import (
    EXCHANGE_EVIDENCE_SCHEMA,
)
from rocell.calibration.position_vector_campaign import (
    CALIBRATED_FEEDBACK_REQUEST_CONTRACT,
)
from rocell.providers.windows import calibrated_position_vector_serial_adapter as subject


POSITION_VECTOR_REPLY = (
    b'{"T":1051,"p":[2050,2147,1958,2550,2227,2041,2042],'
    b'"pose":"KEYBOARD_FORWARD_CAL_1","motion_active":false,'
    b'"trajectory_progress_permille":1000}\n'
)
FULL_WAVESHARE_REPLY = (
    b'{"T":1051,"x":300,"y":0,"z":200,"tit":0,"b":0,"s":0,'
    b'"e":1.5,"t":0,"r":0,"g":3,"v":1200}\n'
)


def request(attempt_id="position-vector-attempt-01"):
    return {
        "schema": subject.REQUEST_SCHEMA,
        "attempt_id": attempt_id,
        "runtime_session_id": "position-vector-runtime-01",
        "request_execution_approval_receipt_sha256": "a" * 64,
        "execution_prerequisites_sha256": "b" * 64,
        "request_contract": dict(CALIBRATED_FEEDBACK_REQUEST_CONTRACT),
    }


class Clock:
    def __init__(self):
        self.wall = datetime(2026, 10, 25, 18, 1, tzinfo=timezone.utc)
        self.mono = 100.0

    def now(self):
        value = self.wall
        self.wall += timedelta(milliseconds=1)
        return value

    def monotonic(self):
        return self.mono

    def sleep(self, seconds):
        self.mono += seconds
        self.wall += timedelta(seconds=seconds)


class FakeTransport:
    def __init__(
        self,
        response=POSITION_VECTOR_REPLY,
        *,
        startup=b"",
        short_write=None,
        close_fails=False,
        fragments=(),
    ):
        self.startup = startup
        self.response = response
        self.short_write = short_write
        self.close_fails = close_fails
        self.fragments = list(fragments)
        self.open_count = 0
        self.write_calls = []
        self.read_count = 0
        self.closed = False
        self.written = False
        self.confirmed_write_bytes = 0

    def open(self):
        self.open_count += 1

    @property
    def in_waiting(self):
        if self.startup and not self.written:
            return len(self.startup)
        if not self.written:
            return 0
        if self.fragments:
            return min(self.fragments[0], len(self.response))
        return len(self.response)

    def read(self, size, *, timeout_ms):
        del timeout_ms
        self.read_count += 1
        source = self.startup if self.startup and not self.written else self.response
        count = min(size, len(source))
        result = source[:count]
        if source is self.startup:
            self.startup = source[count:]
        else:
            self.response = source[count:]
            if self.fragments:
                self.fragments.pop(0)
        return result

    def write(self, payload):
        self.write_calls.append(payload)
        self.written = True
        self.confirmed_write_bytes = (
            len(payload) if self.short_write is None else self.short_write
        )
        return self.confirmed_write_bytes

    def close(self):
        self.closed = True
        if self.close_fails:
            raise OSError("simulated close failure")

    def status(self):
        return {
            "confirmed_write_bytes": self.confirmed_write_bytes,
            "cleanup_confirmed": self.closed and not self.close_fails,
        }


def execute(tmp_path, transport, *, attempt_id="position-vector-attempt-01"):
    clock = Clock()
    factory_calls = []

    def factory():
        factory_calls.append(True)
        return transport

    evidence = subject.execute_position_vector_serial_exchange(
        request(attempt_id),
        journal_root=tmp_path,
        transport_factory=factory,
        clock=clock.now,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return evidence, factory_calls


def test_one_fixed_fragmented_exchange_returns_exact_application_evidence(tmp_path):
    transport = FakeTransport(fragments=(7, 19, 31, 1000))
    evidence, factory_calls = execute(tmp_path, transport)

    assert factory_calls == [True]
    assert transport.open_count == 1
    assert transport.write_calls == [b'{"T":105}\n']
    assert transport.closed is True
    assert evidence["schema"] == EXCHANGE_EVIDENCE_SCHEMA
    assert evidence["status"] == "RESPONSE_OBSERVED_CLOSED"
    assert evidence["request_count"] == 1
    assert evidence["write_attempt_count"] == 1
    assert evidence["confirmed_write_bytes"] == 10
    assert evidence["automatic_retry_count"] == 0
    assert evidence["response_count"] == 1
    assert evidence["motion_command_count"] == 0
    assert evidence["response_line_utf8"].encode() == POSITION_VECTOR_REPLY

    retained = subject.load_position_vector_serial_attempt(
        tmp_path / "position-vector-feedback-position-vector-attempt-01"
    )
    assert retained["recovery_disposition"] == "TERMINAL_NO_REPLAY"
    assert retained["result"]["result"]["exchange_evidence"] == evidence
    assert [event["stage"] for event in retained["events"]] == [
        "INTENT_COMMITTED",
        "TRANSPORT_FACTORY_COMMITTED",
        "OPEN_ATTEMPT_COMMITTED",
        "OPEN_CONFIRMED",
        "QUIET_INPUT_CONFIRMED",
        "WRITE_ATTEMPT_COMMITTED",
        "WRITE_COMPLETED",
        "POSITION_VECTOR_RESPONSE_CONFIRMED",
        "CLOSE_ATTEMPT_COMMITTED",
        "TERMINAL_SUCCESS",
    ]


@pytest.mark.parametrize(
    "transport,code,write_count",
    [
        (FakeTransport(startup=b"old-response\n"), "PREEXISTING_INPUT", 0),
        (FakeTransport(short_write=3), "SHORT_WRITE_NO_RETRY", 1),
        (FakeTransport(response=FULL_WAVESHARE_REPLY), "POSITION_VECTOR_PROFILE_REQUIRED", 1),
        (FakeTransport(response=b"not-json\n"), "INVALID_FEEDBACK_RESPONSE", 1),
        (FakeTransport(close_fails=True), "CLOSE_FAILED", 1),
    ],
)
def test_failures_are_terminal_closed_and_never_retried(
    tmp_path, transport, code, write_count
):
    clock = Clock()
    with pytest.raises(subject.PositionVectorSerialAdapterError, match=code) as caught:
        subject.execute_position_vector_serial_exchange(
            request(),
            journal_root=tmp_path,
            transport_factory=lambda: transport,
            clock=clock.now,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

    assert len(transport.write_calls) == write_count
    assert transport.open_count == 1
    assert transport.closed is True
    retained = subject.load_position_vector_serial_attempt(
        caught.value.journal_directory
    )
    assert retained["recovery_disposition"] == "TERMINAL_NO_REPLAY"
    result = retained["result"]["result"]
    assert result["status"] == "FAILED_NO_RETRY"
    assert result["error"] == code


def test_factory_failure_is_recorded_before_factory_call_and_terminal(tmp_path):
    clock = Clock()

    def factory():
        raise OSError("simulated construction failure")

    with pytest.raises(subject.PositionVectorSerialAdapterError, match="OSError") as caught:
        subject.execute_position_vector_serial_exchange(
            request(), journal_root=tmp_path, transport_factory=factory,
            clock=clock.now, monotonic=clock.monotonic, sleep=clock.sleep,
        )
    retained = subject.load_position_vector_serial_attempt(caught.value.journal_directory)
    assert [event["stage"] for event in retained["events"]][:2] == [
        "INTENT_COMMITTED", "TRANSPORT_FACTORY_COMMITTED"
    ]
    assert retained["result"]["result"]["error"] == "OSError"


def test_existing_attempt_directory_refuses_replay_before_factory(tmp_path):
    execute(tmp_path, FakeTransport())
    calls = []
    with pytest.raises(FileExistsError):
        subject.execute_position_vector_serial_exchange(
            request(), journal_root=tmp_path,
            transport_factory=lambda: calls.append(True),
        )
    assert calls == []


def test_interrupted_journal_forbids_retry_and_tampering_is_detected(tmp_path):
    clock = Clock()
    journal = subject._AttemptJournal.begin(tmp_path, request(), clock.now)
    retained = subject.load_position_vector_serial_attempt(journal.directory)
    assert retained["recovery_disposition"] == "RETRY_FORBIDDEN_EXECUTION_UNCERTAIN"

    events = journal.directory / "events.jsonl"
    first = json.loads(events.read_text(encoding="utf-8").splitlines()[0])
    first["stage"] = "ALTERED"
    events.write_text(json.dumps(first) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="event chain"):
        subject.load_position_vector_serial_attempt(journal.directory)


@pytest.mark.parametrize(
    "change,match",
    [
        ({"schema": "wrong"}, "schema"),
        ({"attempt_id": "../escape"}, "bounded identifier"),
        ({"request_contract": {}}, "contract"),
        ({"extra": True}, "fields"),
    ],
)
def test_invalid_request_rejects_before_journal_or_transport(tmp_path, change, match):
    value = request()
    value.update(change)
    calls = []
    with pytest.raises(ValueError, match=match):
        subject.execute_position_vector_serial_exchange(
            value, journal_root=tmp_path,
            transport_factory=lambda: calls.append(True),
        )
    assert calls == []
    assert list(tmp_path.iterdir()) == []
