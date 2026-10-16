"""Public physical feedback joins with a sealed simulated worker outcome."""

import base64
import json
from pathlib import Path

import pytest

from rocell.application.wizard_actions import WizardError
from rocell.application.powered_feedback_attempt_store import attempt_path
from rocell.providers.windows.owned_worker_process import (
    OwnedWindowsWorker,
    OwnedWorkerResult,
    owned_request_wire,
)
from test_wizard_native_arm_integration import setup, action, ticket
from test_wizard_passive_arm_setup import ready
from test_wizard_powered_arm_setup import ACTION as SETUP_ACTION, VALUES

ACTION = "run_powered_arm_feedback"


@pytest.fixture(autouse=True)
def no_live_process(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No live feedback process may start in public integration tests")

    monkeypatch.setattr(OwnedWindowsWorker, "run", forbidden)


def install_failed_worker(monkeypatch, calls, *, successful_fixture=False, startup_bytes=None):
    def run(self, request, *, cancellation, deadline_ns):
        payload = json.loads(request.payload_json)
        root = Path(payload["root"])
        assert attempt_path(root, request.attempt_id, "prepared").is_file()
        assert attempt_path(root, request.attempt_id, "consumed").is_file()
        request_wire, request_sha = owned_request_wire(
            self.registration, request, deadline_ns=deadline_ns
        )
        self._authorizer(self.registration, request, request_sha)
        calls.append(request)
        parsed = None
        stdout = b"fixture partial output\xff"
        if successful_fixture:
            # Physical-shaped synthetic result, never evidence from this arm.
            from test_powered_feedback_observation import run as memory_observation
            from rocell.providers.windows.powered_feedback_native_wire import validate_result
            from rocell.application.arm_bench_qualification_contract import _canonical
            observation = memory_observation(**(
                {"startup_bytes": startup_bytes} if startup_bytes is not None else {}
            ))
            observation["origin"] = "PHYSICAL_OBSERVATION"
            observation["request_sha256"] = request.operation_sha256
            observation["lifecycle"]["composition"] = "WINDOWS_POWERED_FEEDBACK_ENGINEERING"
            prepared = json.loads(attempt_path(root, request.attempt_id, "prepared").read_bytes())
            native = json.loads(base64.b64decode(prepared["body"]["originals_base64"]["native_identity_original_sha256"]))
            parsed = {"schema": "rocell.owned_powered_feedback_native_result.v1",
                "attempt_id": request.attempt_id, "request_sha256": request_sha,
                "physical_authority": False, "connected": False,
                "child_result": {"schema": "rocell.powered_feedback_native_child_result.v1",
                    "claim_sha256": "e" * 64, "fresh_snapshot": native["snapshot"],
                    "observation": observation, "physical_authority": False, "connected": False}}
            validate_result(parsed, wire=json.loads(request_wire))
            stdout = _canonical(parsed)
        return OwnedWorkerResult(
            status="SUCCEEDED" if successful_fixture else "FAILED",
            primary_error=None if successful_fixture else "SYNTHETIC_NO_PROCESS",
            cleanup_errors=(),
            request_sha256=request_sha,
            attempt_id=request.attempt_id,
            process_created=successful_fixture,
            initial_thread_resumed=successful_fixture,
            tree_exit_confirmed=True,
            returncode=None,
            elapsed_ns=1,
            stdin_bytes_written=0,
            peak_observed_handles=0,
            peak_active_processes=0,
            stdout=stdout,
            stderr=b"fixture no dispatch",
            parsed_result=parsed,
        )

    monkeypatch.setattr(OwnedWindowsWorker, "run", run)


def test_public_join_consumes_once_and_exports_raw_failed_result(setup, monkeypatch):
    service, _, _, _ = ready(setup)
    assert action(service, SETUP_ACTION, **VALUES)["status"] == "SUCCEEDED"
    calls = []
    install_failed_worker(monkeypatch, calls)
    completed = action(service, ACTION, firmware_unchanged=True)
    assert completed["status"] == "FAILED", completed
    assert len(calls) == 1
    report = completed["result"]["steps"][0]["report"]
    assert report["outcome_sha256"]
    assert report["serial_cleanup_confirmed"] is None
    assert report["connected"] is report["motion_authorized"] is False
    with pytest.raises(WizardError):
        ticket(service, ACTION, firmware_unchanged=True)
    exported = action(service, "export_logs")
    assert exported["status"] == "SUCCEEDED", exported
    folder = Path(exported["result"]["receipt"]["path"])
    logs = json.loads(
        (folder / "attachment-powered-feedback-native-logs.json").read_bytes()
    )
    assert (
        b"".join(base64.b64decode(chunk) for chunk in logs["stdout_base64_chunks"])
        == b"fixture partial output\xff"
    )
    files = json.loads(
        (folder / "attachment-powered-feedback-attempt-files.json").read_bytes()
    )
    assert (
        next(record for record in files["records"] if record["stage"] == "outcome")[
            "status"
        ]
        == "BYTES_RETAINED"
    )


def test_stream_guidance_exports_original_and_cannot_switch_to_second_attempt(setup, monkeypatch):
    service, _, _, _ = ready(setup)
    action(service, SETUP_ACTION, **VALUES)
    calls = []
    partial = b'{"T":1051,"x":345.4,"t":0.0168,'
    install_failed_worker(monkeypatch, calls, successful_fixture=True, startup_bytes=partial)
    completed = action(service, ACTION, firmware_unchanged=True)
    assert completed["status"] == "FAILED", completed
    report = completed["result"]["steps"][0]["report"]
    assert report["status"] == "POWERED_INPUT_BEFORE_QUERY"
    assert report["confirmed_write_bytes"] == 0
    assert report["feedback"] is None
    assert "Capture arm telemetry" in report["next_step"]
    # Guidance is inert: switching action or recording setup again must not
    # turn one consumed connection into a second automatic attempt.
    action(service, SETUP_ACTION, **VALUES)
    for name in (ACTION, "capture_powered_arm_telemetry"):
        with pytest.raises(WizardError):
            ticket(service, name, firmware_unchanged=True)
    assert len(calls) == 1
    exported = action(service, "export_logs")
    assert exported["status"] == "SUCCEEDED", exported
    assert exported["result"]["receipt"]["valid"] is True
    folder = Path(exported["result"]["receipt"]["path"])
    logs = json.loads((folder / "attachment-powered-feedback-native-logs.json").read_bytes())
    raw = b"".join(base64.b64decode(chunk) for chunk in logs["stdout_base64_chunks"])
    observation = json.loads(raw)["child_result"]["observation"]
    assert base64.b64decode(observation["startup"]["base64"]) == partial


def test_current_powered_setup_and_unchanged_report_required(setup):
    service, _, _, _ = ready(setup)
    with pytest.raises(WizardError):
        ticket(service, ACTION, firmware_unchanged=True)
    action(service, SETUP_ACTION, **VALUES)
    with pytest.raises(WizardError):
        ticket(service, ACTION, firmware_unchanged=False)


def test_exactly_one_firmware_evidence_basis_is_required(setup):
    service, _, _, _ = ready(setup)
    action(service, SETUP_ACTION, **VALUES)
    with pytest.raises(WizardError):
        ticket(service, ACTION, firmware_unchanged=True,
               installed_r120_verified=True)
    preview = ticket(service, ACTION, firmware_unchanged=False,
                     installed_r120_verified=True)
    assert preview["action_id"] == ACTION


def test_new_setup_after_preview_invalidates_ticket(setup):
    service, _, _, _ = ready(setup)
    action(service, SETUP_ACTION, **VALUES)
    preview = ticket(service, ACTION, firmware_unchanged=True)
    action(service, SETUP_ACTION, **VALUES)
    with pytest.raises(WizardError):
        service.execute_action(preview["ticket_id"])


def test_rehearsal_cannot_dispatch_physical_feedback(setup):
    service, _, _, _ = setup("rehearsal")
    with pytest.raises(WizardError):
        ticket(service, ACTION, firmware_unchanged=True)


@pytest.mark.parametrize("save_failure", [False, True])
def test_success_publication_requires_durable_outcome(setup, monkeypatch, save_failure):
    from rocell.application.powered_feedback_attempt_store import PoweredFeedbackAttemptJournal
    service, _, _, _ = ready(setup)
    action(service, SETUP_ACTION, **VALUES)
    calls = []
    install_failed_worker(monkeypatch, calls, successful_fixture=True)
    if save_failure:
        def fail(*args, **kwargs):
            raise OSError("fixture outcome persistence failure")
        monkeypatch.setattr(PoweredFeedbackAttemptJournal, "retain_outcome", fail)
    completed = action(service, ACTION, firmware_unchanged=True)
    assert completed["status"] == ("FAILED" if save_failure else "SUCCEEDED"), completed
    report = completed["result"]["steps"][0]["report"]
    assert report["feedback"]["v"] == 1200
    assert report["serial_cleanup_confirmed"] is True
    assert report["motion_authorized"] is False
    assert action(service, "export_logs")["status"] == "SUCCEEDED"
