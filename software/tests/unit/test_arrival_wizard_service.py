from __future__ import annotations

from copy import deepcopy
import io
import json
import os
from pathlib import Path
import threading
import time
from typing import Any

from PIL import Image
import pytest

import rocell.application.arrival_wizard_service as service_module
from rocell.application.arrival_wizard_service import ArrivalWizardService
from rocell.application.wizard_actions import WizardError
from rocell.application.wizard_diagnostic_export import verify_export


WORKSPACE = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('name',['low','center','high'])
def test_unreviewed_sweep_actions_are_not_available(make_service,monkeypatch,name):
    from rocell.providers.windows import wifi_discrete_native as native
    def forbidden(**kwargs):raise AssertionError('Preview must never dispatch')
    monkeypatch.setattr(native,'run_native_roll_sweep_'+name+'_trial',forbidden)
    service,runner,_=make_service(mode='physical')
    with pytest.raises(WizardError, match='not registered'):
        service.prepare_action('run_wifi_roll_sweep_'+name+'_trial',{},service.view()['revision'])
    assert not runner.calls


def test_guided_rehearsal_actions_are_explicit_and_never_available_physically(
    make_service: Any,
) -> None:
    service, runner, source = make_service()
    view = service.view()
    assert view["commissioning_rehearsal"]["status"] == "NOT_STARTED"
    assert not Path(view["commissioning_rehearsal"]["directory"]).exists()
    ticket = service.prepare_action("rehearsal_initialize", {}, view["revision"])
    assert not Path(view["commissioning_rehearsal"]["directory"]).exists()
    assert ticket["physical_authority"] is False
    assert not runner.calls
    physical, _, _ = make_service(mode="physical")
    for action in physical.view()["actions"]:
        if action["action_id"].startswith("rehearsal_"):
            assert not action["enabled"]
    assert all(stage["state"] == "PHYSICAL_PENDING" for stage in view["stages"])


def test_reopen_choices_are_cached_explicit_and_not_arbitrary_paths(
    make_service: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, runner, _ = make_service()
    choices = [
        {
            "choice_id": "opaque-choice-1",
            "session_id": "original-session",
            "cell_id": "original-cell",
            "directory": str(WORKSPACE / "software/runs/wizard-rehearsal/original"),
            "source_matches": True,
            "discovery_sha256": "d" * 64,
        }
    ]
    monkeypatch.setattr(service._commissioning, "reopen_choices", lambda: choices)
    monkeypatch.setattr(service._commissioning, "blocked_reason", lambda _: None)
    view = service.view()
    action = next(a for a in view["actions"] if a["action_id"] == "rehearsal_reopen")
    assert "default" not in action["fields"][0]
    assert action["fields"][0]["options"][0]["value"] == "opaque-choice-1"
    for values in ({}, {"choice_id": ""}, {"choice_id": choices[0]["directory"]}):
        with pytest.raises(WizardError):
            _ticket(service, "rehearsal_reopen", values)
    ticket = _ticket(service, "rehearsal_reopen", {"choice_id": "opaque-choice-1"})
    assert ticket["input"] == {"choice_id": "opaque-choice-1"}
    assert choices[0]["directory"] in " ".join(ticket["effects"])
    assert "requalify" in " ".join(ticket["effects"])
    assert "replayed" in " ".join(ticket["effects"])
    assert not runner.calls
    # Mutating a UI projection must not change server-side selection authority.
    action["fields"][0]["options"][0]["value"] = "not-registered"
    with pytest.raises(WizardError):
        _ticket(service, "rehearsal_reopen", {"choice_id": "not-registered"})


@pytest.mark.parametrize("stage", ["optics_intrinsics", "static_registration"])
def test_optics_collect_preview_describes_no_device_evaluation_without_running_it(
    make_service: Any, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    service, runner, _ = make_service()
    monkeypatch.setattr(service._commissioning, "blocked_reason", lambda _: None)
    original_view = service._commissioning.view
    monkeypatch.setattr(
        service._commissioning, "view", lambda: {**original_view(), "stage": stage}
    )
    ticket = _ticket(service, "rehearsal_collect", {"operator_id": "operator-fixture"})
    effects = " ".join(ticket["effects"])
    assert "binary dataset is not the evaluated pixels" in effects
    assert "reopening never reruns" in effects
    assert not runner.calls
    assert not service._commissioning.directory.exists()


@pytest.mark.parametrize(
    "stage", ["arm_identity", "power_safety", "power_on_observation"]
)
def test_arm_setup_preview_is_explicit_synthetic_and_inert(
    make_service, monkeypatch, stage
):
    service, runner, _ = make_service()
    monkeypatch.setattr(service._commissioning, "blocked_reason", lambda _: None)
    original_view = service._commissioning.view
    monkeypatch.setattr(
        service._commissioning, "view", lambda: {**original_view(), "stage": stage}
    )
    ticket = _ticket(service, "rehearsal_collect", {"operator_id": "operator-fixture"})
    effects = " ".join(ticket["effects"])
    if stage == "arm_identity":
        assert "closed injected serial metadata fixtures" in effects
        assert "neither enumerates the host nor opens" in effects
        assert "Nominal acceptance and expected-fault checks are separate" in effects
    else:
        assert "Do not energize the arm" in effects
        assert "fixed synthetic procedure observations" in effects
        assert "No startup trajectory is predicted" in effects
        assert "Successful fault handling is not nominal acceptance" in effects
    assert ticket["physical_authority"] is False
    assert not runner.calls
    assert not service._commissioning.directory.exists()


@pytest.mark.skipif(os.name != "nt", reason="Actual M1 requires Windows NTFS")
def test_arrival_reopens_original_review_through_tickets_without_replay(
    make_service: Any,
) -> None:
    original, runner, _ = make_service()

    def run(service: ArrivalWizardService, name: str, **values: Any) -> dict:
        ticket = _ticket(service, name, values)
        receipt = service.execute_action(ticket["ticket_id"])
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            operation = service.operation(receipt["operation_id"])
            if operation["status"] not in {"QUEUED", "PENDING", "RUNNING"}:
                assert operation["status"] == "SUCCEEDED", operation
                return operation
            threading.Event().wait(0.02)
        pytest.fail("No automatic replay after the test operation deadline")

    run(original, "rehearsal_initialize")
    run(original, "rehearsal_collect", operator_id="setup-operator")
    run(original, "rehearsal_assess")
    before = original.view()["commissioning_rehearsal"]
    original.shutdown()
    reopened, second_runner, _ = make_service()
    unused = Path(reopened.view()["commissioning_rehearsal"]["directory"])
    run(reopened, "rehearsal_discover")
    choices = reopened.view()["commissioning_rehearsal"]["discovery"]["choices"]
    selected = next(c for c in choices if c["session_id"] == before["session_id"])
    run(reopened, "rehearsal_reopen", choice_id=selected["choice_id"])
    restored = reopened.view()["commissioning_rehearsal"]
    assert restored["session_id"] == before["session_id"]
    assert restored["directory"] == before["directory"]
    assert restored["journal_head_sha256"] == before["journal_head_sha256"]
    assert restored["assessment"] == before["assessment"]
    assert restored["stage_state"] == "REVIEW_PENDING"
    assert reopened.view()["camera"]["image_id"] is None
    assert not unused.exists()
    with pytest.raises(WizardError, match="differ"):
        _ticket(
            reopened,
            "rehearsal_review",
            {
                "reviewer_id": "setup-operator",
                "accept_assessment": True,
            },
        )
    run(
        reopened,
        "rehearsal_review",
        reviewer_id="fresh-reviewer",
        accept_assessment=True,
    )
    assert (
        reopened.view()["commissioning_rehearsal"]["stage"] == "static_camera_contract"
    )
    assert all(s["state"] == "PHYSICAL_PENDING" for s in reopened.view()["stages"])
    assert not runner.calls and not second_runner.calls


@pytest.mark.parametrize(
    "action",
    [
        "rehearsal_collect",
        "rehearsal_camera_campaign",
        "rehearsal_owned_camera_campaign",
        "rehearsal_assess",
    ],
)
def test_failed_commissioning_cannot_show_an_old_preview_as_current(
    make_service: Any, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    service, _, _ = make_service()
    service._images = {"old-image": b"old synthetic PNG"}
    service._camera["image_id"] = "old-image"
    service._camera["image_provenance"] = (
        "SYNTHETIC_DATASET_DERIVED_PREVIEW_NOT_PHYSICAL"
    )
    monkeypatch.setattr(service._commissioning, "blocked_reason", lambda _: None)
    monkeypatch.setattr(service._commissioning, "bind", lambda action, values: values)

    def fail(*args: Any, **kwargs: Any) -> None:
        if action in {
            "rehearsal_collect",
            "rehearsal_camera_campaign",
            "rehearsal_owned_camera_campaign",
        }:
            assert service.view()["camera"]["image_id"] is None
        raise WizardError(
            "INJECTED_REHEARSAL_HOLD",
            "Prior frame is historical, not this failed operation",
        )

    monkeypatch.setattr(service._commissioning, "perform", fail)
    operation = _run(service, action)
    assert operation["status"] == "FAILED"
    assert service.view()["camera"]["image_id"] is None
    assert (
        service.view()["camera"]["image_provenance"]
        == "REHEARSAL_HELD_NO_CURRENT_PREVIEW"
    )
    with pytest.raises(WizardError):
        service.image("old-image")


class FakeRunner:
    def __init__(self, *, blocked: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.progress: Any = None
        self.blocked = blocked
        self.result_changes: dict[str, Any] = {}

    def run(
        self,
        action_id: str,
        values: dict[str, Any],
        *,
        cell_id: str,
        cancel: threading.Event,
        progress: Any,
    ) -> dict[str, Any]:
        self.calls.append((action_id, deepcopy(values)))
        self.progress = progress
        progress("Synthetic diagnostic in progress; no devices opened.")
        self.entered.set()
        if self.blocked:
            deadline = time.monotonic() + 5
            while (
                not self.release.is_set()
                and not cancel.is_set()
                and time.monotonic() < deadline
            ):
                cancel.wait(0.005)
        if cancel.is_set():
            return {
                "schema": "rocell.wizard_diagnostic_completion.v1",
                "action_id": action_id,
                "status": "CANCELLED",
                "message": "Fixture diagnostic cancelled.",
                "elapsed_s": 0.0,
                "output_limit_exceeded": False,
                "physical_authority": False,
            }
        return {
            "schema": "rocell.wizard_worker_result.v1",
            "action_id": action_id,
            "status": "CANCELLED" if cancel.is_set() else "SUCCEEDED",
            "steps": [
                {
                    "name": "fixture-check",
                    "exit_code": 0,
                    "report": {
                        "status": "COMPLETE_SYNTHETIC",
                        "nested": {"observed": [1, 2, 3]},
                    },
                }
            ],
            "device_open_count": 0,
            "serial_write_count": 0,
            "power_event_count": 0,
            "motion_command_count": 0,
            "contact_command_count": 0,
            "physical_authority": False,
            "metadata_inventory_performed": action_id == "inventory_devices",
            **self.result_changes,
        }


@pytest.fixture
def make_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    source = {"hash": "a" * 64, "calls": 0}

    def fingerprint(workspace: Path) -> str:
        source["calls"] += 1
        return source["hash"]

    monkeypatch.setattr(service_module, "source_fingerprint", fingerprint)
    instances = []

    def create(
        *, runner: Any = None, mode: str = "rehearsal", clock: Any = time.monotonic
    ) -> tuple[ArrivalWizardService, FakeRunner, dict[str, Any]]:
        selected = runner or FakeRunner()
        instance = ArrivalWizardService(
            WORKSPACE,
            runner=selected,
            mode=mode,
            clock=clock,
            export_directory=tmp_path / "exports",
            log_directory=tmp_path / "diagnostics",
        )
        instances.append(instance)
        return instance, selected, source

    yield create
    for instance in instances:
        instance.shutdown()


def _ticket(
    service: ArrivalWizardService, action: str, values: dict[str, Any] | None = None
) -> dict[str, Any]:
    return service.prepare_action(action, values or {}, service.view()["revision"])


def _complete(service: ArrivalWizardService, operation_id: str, *, timeout_s=5) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        value = service.operation(operation_id)
        if value["status"] in {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"}:
            return value
        threading.Event().wait(0.005)
    pytest.fail("diagnostic did not finish within test deadline")


def _run(
    service: ArrivalWizardService, action: str, values: dict[str, Any] | None = None, *, timeout_s=5
) -> dict[str, Any]:
    ticket = _ticket(service, action, values)
    receipt = service.execute_action(ticket["ticket_id"])
    return _complete(service, receipt["operation_id"],timeout_s=timeout_s)


def test_constructor_and_status_create_no_files_or_workers(
    make_service: Any, tmp_path: Path
) -> None:
    service, runner, source = make_service()
    assert source["calls"] == 1
    for _ in range(5):
        view = service.view()
        assert view["camera"]["status"] == view["arm"]["status"] == "NOT_CONNECTED"
        assert view["physical_authority"] is False
        assert len(view["stages"]) == 15
        assert all(stage["state"] == "PHYSICAL_PENDING" for stage in view["stages"])
        assert view["camera"]["image_id"] is None
    assert source["calls"] == 1 and not runner.calls
    assert (
        not (tmp_path / "exports").exists() and not (tmp_path / "diagnostics").exists()
    )
    _ticket(service, "run_baseline")
    assert not runner.calls and not (tmp_path / "diagnostics").exists()


def test_action_runs_once_keeps_full_result_and_does_not_qualify_hardware(
    make_service: Any,
) -> None:
    service, runner, _ = make_service()
    ticket = _ticket(service, "camera_rehearsal", {"fault": "none"})
    first = service.execute_action(ticket["ticket_id"])
    result = _complete(service, first["operation_id"])
    second = service.execute_action(ticket["ticket_id"])
    assert first["operation_id"] == second["operation_id"]
    assert len(runner.calls) == 1
    assert result["result"]["steps"][0]["report"]["nested"]["observed"] == [1, 2, 3]
    assert service.view()["camera"]["status"] == "NOT_CONNECTED"
    assert all(
        stage["state"] == "PHYSICAL_PENDING" for stage in service.view()["stages"]
    )
    assert (
        service._log.verify(service._log.directory)["status"]
        == "VERIFIED_DIAGNOSTIC_ONLY"
    )


def test_requests_are_closed_and_revision_bound(make_service: Any) -> None:
    service, runner, _ = make_service()
    with pytest.raises(WizardError, match="not registered"):
        _ticket(service, "send-raw-T104")
    with pytest.raises(WizardError, match="unsupported field"):
        _ticket(service, "run_baseline", {"port": "COM3"})
    with pytest.raises(WizardError, match="displayed view changed"):
        service.prepare_action("run_baseline", {}, True)
    with pytest.raises(WizardError, match="not registered|No ticket"):
        service.execute_action("ticket-arbitrary")
    assert not runner.calls


def test_ticket_expires_without_dispatch(make_service: Any) -> None:
    now = [100.0]
    service, runner, _ = make_service(clock=lambda: now[0])
    ticket = _ticket(service, "run_baseline")
    now[0] += 120
    with pytest.raises(WizardError, match="expired"):
        service.execute_action(ticket["ticket_id"])
    assert not runner.calls


def test_state_change_invalidates_other_prepared_ticket(make_service: Any) -> None:
    service, runner, _ = make_service()
    pending = _ticket(service, "run_baseline")
    _run(
        service,
        "record_note",
        {"note": "Reviewed cabling diagram; physical hold remains."},
    )
    with pytest.raises(WizardError, match="operation state changed"):
        service.execute_action(pending["ticket_id"])
    assert not runner.calls


def test_progress_does_not_invalidate_exact_stop_ticket(make_service: Any) -> None:
    fake = FakeRunner(blocked=True)
    service, _, _ = make_service(runner=fake)
    running = service.execute_action(_ticket(service, "run_baseline")["ticket_id"])
    assert fake.entered.wait(2)
    stop = _ticket(service, "stop_operation")
    old_revision = service.view()["revision"]
    fake.progress("Additional progress for the same active operation.")
    assert service.view()["revision"] > old_revision
    receipt = service.execute_action(stop["ticket_id"])
    assert receipt["status"] == "SUCCEEDED"
    completed = _complete(service, running["operation_id"])
    assert completed["status"] == "CANCELLED"
    assert service.view()["diagnostics"]["stop_is_robot_estop"] is False
    assert len(fake.calls) == 1


def test_busy_session_blocks_other_worker_dispatch(make_service: Any) -> None:
    fake = FakeRunner(blocked=True)
    service, _, _ = make_service(runner=fake)
    running = service.execute_action(_ticket(service, "run_baseline")["ticket_id"])
    assert fake.entered.wait(2)
    with pytest.raises(WizardError, match="running"):
        _ticket(service, "arm_rehearsal")
    fake.release.set()
    assert _complete(service, running["operation_id"])["status"] == "SUCCEEDED"
    assert len(fake.calls) == 1


def test_progress_before_prepare_allows_only_same_operation_stop(
    make_service: Any,
) -> None:
    fake = FakeRunner(blocked=True)
    service, _, _ = make_service(runner=fake)
    running = service.execute_action(_ticket(service, "run_baseline")["ticket_id"])
    assert fake.entered.wait(2)
    rendered_revision = service.view()["revision"]
    fake.progress("New progress arrived after rendering and before the click.")
    with pytest.raises(WizardError) as stale:
        service.prepare_action("arm_rehearsal", {}, rendered_revision)
    assert stale.value.code == "STALE_REVISION"
    stop = service.prepare_action("stop_operation", {}, rendered_revision)
    first = service.execute_action(stop["ticket_id"])
    second = service.execute_action(stop["ticket_id"])
    assert first["operation_id"] == second["operation_id"]
    assert _complete(service, running["operation_id"])["status"] == "CANCELLED"
    assert len(fake.calls) == 1


def test_old_stop_view_and_ticket_cannot_target_replacement_operation(
    make_service: Any,
) -> None:
    fake = FakeRunner(blocked=True)
    service, _, _ = make_service(runner=fake)
    first = service.execute_action(_ticket(service, "run_baseline")["ticket_id"])
    assert fake.entered.wait(2)
    old_revision = service.view()["revision"]
    old_ticket = service.prepare_action("stop_operation", {}, old_revision)
    fake.release.set()
    assert _complete(service, first["operation_id"])["status"] == "SUCCEEDED"
    with pytest.raises(WizardError) as finished:
        service.prepare_action("stop_operation", {}, old_revision)
    assert finished.value.code == "STALE_REVISION"
    fake.entered.clear()
    fake.release.clear()
    second = service.execute_action(_ticket(service, "run_baseline")["ticket_id"])
    assert fake.entered.wait(2)
    fake.progress("The replacement operation has its own state epoch.")
    with pytest.raises(WizardError) as replaced:
        service.prepare_action("stop_operation", {}, old_revision)
    assert replaced.value.code == "STALE_REVISION"
    with pytest.raises(WizardError) as old_execution:
        service.execute_action(old_ticket["ticket_id"])
    assert old_execution.value.code == "STALE_TICKET"
    service.execute_action(_ticket(service, "stop_operation")["ticket_id"])
    assert _complete(service, second["operation_id"])["status"] == "CANCELLED"
    assert len(fake.calls) == 2


@pytest.mark.parametrize("revision", [True, False, -1, 1.5, None, "1", 1000000])
def test_stop_progress_tolerance_rejects_invalid_or_future_revision(
    make_service: Any, revision: Any
) -> None:
    fake = FakeRunner(blocked=True)
    service, _, _ = make_service(runner=fake)
    running = service.execute_action(_ticket(service, "run_baseline")["ticket_id"])
    assert fake.entered.wait(2)
    with pytest.raises(WizardError) as error:
        service.prepare_action("stop_operation", {}, revision)
    assert error.value.code == "STALE_REVISION"
    service.execute_action(_ticket(service, "stop_operation")["ticket_id"])
    assert _complete(service, running["operation_id"])["status"] == "CANCELLED"
    assert len(fake.calls) == 1


def test_source_drift_blocks_workers_but_preserves_note_and_export(
    make_service: Any,
) -> None:
    service, runner, source = make_service()
    pending = _ticket(service, "run_baseline")
    source["hash"] = "b" * 64
    with pytest.raises(WizardError, match="Source changed"):
        service.execute_action(pending["ticket_id"])
    assert service.view()["diagnostics"]["source_changed"]
    assert (
        _run(
            service,
            "record_note",
            {"note": "Source changed; preparing an explicit restart."},
        )["status"]
        == "SUCCEEDED"
    )
    exported = _run(service, "export_logs")
    assert exported["status"] == "SUCCEEDED", exported.get('result', exported)
    assert verify_export(Path(exported["result"]["receipt"]["path"]))["valid"]
    assert not runner.calls


def test_physical_mode_has_explicit_metadata_only_device_action(
    make_service: Any,
) -> None:
    service, runner, _ = make_service(mode="physical")
    for action_id in (
        "camera_connect",
        "arm_connect",
        "execute_task",
        "camera_rehearsal",
    ):
        with pytest.raises(WizardError):
            _ticket(service, action_id)
    with pytest.raises(WizardError, match="metadata-only inspection"):
        _ticket(service, "inventory_devices", {"power_disconnected": False})
    from test_wizard_device_selection_integration import physical_fixture_report

    runner.result_changes["steps"] = [
        {
            "name": "metadata_inventory",
            "exit_code": 0,
            "report": physical_fixture_report(),
        }
    ]
    outcome = _run(service, "inventory_devices", {"power_disconnected": True})
    assert outcome["status"] == "SUCCEEDED"
    assert runner.calls == [("inventory_devices", {"power_disconnected": True, "metadata_only": False})]
    assert service.view()["arm"]["status"] == "NOT_CONNECTED"


@pytest.mark.parametrize(
    "changes",
    [
        {"physical_authority": True},
        {"device_open_count": 1},
        {"action_id": "unregistered"},
        {"status": "RUNNING"},
    ],
)
def test_malformed_or_effectful_worker_receipt_is_rejected(
    make_service: Any, changes: dict[str, Any]
) -> None:
    fake = FakeRunner()
    fake.result_changes = changes
    service, _, _ = make_service(runner=fake)
    result = _run(service, "run_baseline")
    assert result["status"] == "FAILED"
    assert result["error"]["remediation"]


def test_log_failure_latches_hold_before_worker_and_still_allows_export(
    make_service: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, runner, _ = make_service()

    def failed(*args: Any, **kwargs: Any) -> None:
        raise OSError("injected disk failure")

    monkeypatch.setattr(service._log, "append", failed)
    result = _run(service, "run_baseline")
    assert result["status"] == "FAILED" and not runner.calls
    assert service.view()["diagnostics"]["log_state"] == "HELD"
    exported = _run(service, "export_logs")
    assert exported["status"] == "FAILED"
    assert exported["action_outcome_before_log_failure"] == "SUCCEEDED"
    assert verify_export(Path(exported["result"]["receipt"]["path"]))["valid"]


def test_notes_are_redacted_before_log_and_cannot_clear_holds(
    make_service: Any,
) -> None:
    service, _, _ = make_service()
    before = service.view()["stages"]
    result = _run(
        service, "record_note", {"note": "fixed cable; password=SUPER_SECRET"}
    )
    assert result["status"] == "SUCCEEDED"
    logs = "\n".join(path.read_text() for path in service._log.directory.iterdir())
    assert "SUPER_SECRET" not in logs
    assert "[REDACTED]" in logs
    assert service.view()["stages"] == before
    assert not next(
        action
        for action in service.view()["actions"]
        if action["action_id"] == "arm_connect"
    )["enabled"]


def test_export_contains_full_result_attachment_and_lightweight_snapshot(
    make_service: Any,
) -> None:
    service, _, _ = make_service()
    result = _run(service, "run_baseline")
    exported = _run(service, "export_logs")
    assert exported["status"] == "SUCCEEDED", exported
    folder = Path(exported["result"]["receipt"]["path"])
    assert verify_export(folder)["valid"]
    attachments = list(folder.glob("attachment-result-*.json"))
    assert len(attachments) == 1
    assert json.loads(attachments[0].read_text())["steps"] == result["result"]["steps"]
    report = json.loads((folder / "report.json").read_text())
    assert all(
        "result" not in operation for operation in report["snapshot"]["operations"]
    )
    assert report["snapshot"]["result_export_policy"]["included_full_results"] == 1


def test_board_preview_uses_verified_nominal_scene_and_labels_png(
    make_service: Any,
) -> None:
    service, runner, _ = make_service()
    assert service.view()["board"]["geometry"] is None
    result = _run(service, "board_preview")
    assert result["status"] == "SUCCEEDED", result
    view = service.view()
    assert view["board"]["geometry"]["width_mm"] == 610.0
    assert view["board"]["geometry"]["height_mm"] == 457.0
    assert view["camera"]["image_provenance"] == "NOMINAL_SCHEMATIC_NOT_CAMERA_CAPTURE"
    assert view["camera"]["status"] == "NOT_CONNECTED"
    payload, content_type = service.image(view["camera"]["image_id"])
    image = Image.open(io.BytesIO(payload))
    assert image.size == (1000, 820) and content_type == "image/png"
    assert runner.calls == [("board_preview", {})]


def test_completed_history_has_explicit_retention_omissions(make_service: Any) -> None:
    service, _, _ = make_service()
    first = _run(service, "run_baseline")
    for index in range(8):
        _run(
            service,
            "record_note",
            {"note": f"Diagnostic note {index}; no physical approval."},
        )
    older = service.operation(first["operation_id"])
    assert older["result"] is None
    assert older["result_retention"] == "OMITTED_OLDER_THAN_LAST_EIGHT_RESULTS"
    exported = _run(service, "export_logs")
    assert exported["status"] == "SUCCEEDED"
    report = json.loads(
        (Path(exported["result"]["receipt"]["path"]) / "report.json").read_text()
    )
    assert report["snapshot"]["result_export_policy"]["omitted"]


def test_view_and_action_results_are_copies_and_shutdown_does_not_resume(
    make_service: Any,
) -> None:
    service, runner, _ = make_service()
    view = service.view()
    view["camera"]["status"] = "CONNECTED"
    assert service.view()["camera"]["status"] == "NOT_CONNECTED"
    service.shutdown()
    with pytest.raises(WizardError, match="shutting down"):
        _ticket(service, "run_baseline")
    assert not runner.calls


def test_failed_nested_step_cannot_claim_success(make_service: Any) -> None:
    fake = FakeRunner()
    fake.result_changes = {
        "steps": [
            {"name": "failing-baseline", "exit_code": 1, "report": {"status": "FAILED"}}
        ]
    }
    service, _, _ = make_service(runner=fake)
    result = _run(service, "run_baseline")
    assert result["status"] == "FAILED"
    assert result["result"]["code"] == "INVALID_WORKER_RESULT"
    assert "status disagrees" in result["result"]["message"]


def test_oversized_worker_result_has_explicit_retention_failure(
    make_service: Any,
) -> None:
    fake = FakeRunner()
    fake.result_changes = {
        "steps": [
            {
                "name": "oversized",
                "exit_code": 0,
                "report": {"output": "x" * (64 * 1024 + 1)},
            }
        ]
    }
    service, _, _ = make_service(runner=fake)
    result = _run(service, "run_baseline")
    assert result["status"] == "FAILED"
    assert result["result"]["code"] == "RESULT_RETENTION_LIMIT"
    assert "full-result export" in result["result"]["message"]


def test_terminal_log_failure_does_not_claim_persisted_success(
    make_service: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, runner, _ = make_service()
    original = service._log.append

    def fail_completion(kind: str, details: dict[str, Any]) -> dict[str, Any]:
        if kind == "ACTION_FINISHED":
            raise OSError("injected final-event publication failure")
        return original(kind, details)

    monkeypatch.setattr(service._log, "append", fail_completion)
    result = _run(service, "run_baseline")
    assert runner.calls == [("run_baseline", {})]
    assert result["status"] == "FAILED"
    assert result["action_outcome_before_log_failure"] == "SUCCEEDED"
    assert result["completion_log_persisted"] is False
    assert result["result"]["status"] == "SUCCEEDED"
    assert service.view()["diagnostics"]["log_state"] == "HELD"


@pytest.mark.parametrize("field", ["action_id", "metadata_inventory_performed"])
def test_shared_worker_parser_rejects_missing_required_observation(
    make_service: Any, field: str
) -> None:
    service, _, _ = make_service()
    receipt = FakeRunner().run(
        "run_baseline",
        {},
        cell_id="CELL-A",
        cancel=threading.Event(),
        progress=lambda _: None,
    )
    del receipt[field]
    with pytest.raises(WizardError):
        service._validated_result("run_baseline", receipt)
