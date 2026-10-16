"""Join powered setup, exact runtime, one-use journal and supervised feedback."""

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import sys
import time

from .arm_bench_qualification_contract import _canonical
from .physical_onboarding_durability import (
    safe_root,
    contained_path,
    read_bounded_regular_file,
)
from .powered_arm_feedback_contract import (
    PoweredFeedbackIntent,
    SCHEMA,
    PURPOSE,
    LIMITS,
    TELEMETRY_PURPOSE,
    TELEMETRY_LIMITS,
)
from .powered_arm_feedback_preparation import prepare_powered_feedback
from .powered_feedback_firmware_review import create_review
from .powered_feedback_attempt_store import PoweredFeedbackAttemptJournal
from .wizard_diagnostic_coordinator import decode_diagnostic_json
from rocell.providers.windows import powered_feedback_native_package as package
from rocell.providers.windows import powered_feedback_native_registration as protocol
from rocell.providers.windows.nonpurging_serial_api import DcbSettings, CommTimeouts
from rocell.providers.windows.owned_worker_process import (
    PinnedWorkerFile,
    WorkerProcessRegistration,
    WorkerProcessBudget,
    OwnedWorkerRequest,
    OwnedWorkerResult,
    OwnedWindowsWorker,
    owned_registration_document,
)

ACTION = "run_powered_arm_feedback"
TELEMETRY_ACTION = "capture_powered_arm_telemetry"


@dataclass(frozen=True, slots=True)
class PoweredFeedbackOutcome:
    process: OwnedWorkerResult
    outcome_sha256: str | None
    persistence_error: str | None
    action_id: str = ACTION

    def publication(self):
        observation = (
            (self.process.parsed_result or {}).get("child_result") or {}
        ).get("observation") or {}
        lifecycle = observation.get("lifecycle") or {}
        if self.action_id == TELEMETRY_ACTION:
            return self._telemetry_publication(observation, lifecycle)
        status, code = "FAILED", "POWERED_FEEDBACK_INCOMPLETE"
        if self.persistence_error or not self.outcome_sha256:
            code = "POWERED_FEEDBACK_PERSISTENCE_FAILED"
        elif self.process.process_created and not self.process.tree_exit_confirmed:
            code = "POWERED_PROCESS_CLEANUP_UNKNOWN"
        elif self.process.status in {"CANCELLED", "TIMED_OUT"}:
            status, code = (
                self.process.status,
                "POWERED_FEEDBACK_" + self.process.status,
            )
        elif (
            self.process.status == "SUCCEEDED"
            and self.process.process_created
            and self.process.initial_thread_resumed
            and self.process.tree_exit_confirmed
            and observation.get("status") == "FEEDBACK_OBSERVED_CLOSED"
            and lifecycle.get("cleanup_confirmed") is True
        ):
            status, code = "SUCCEEDED", "ONE_FEEDBACK_OBSERVATION_COMPLETED"
        elif (
            self.process.status == "SUCCEEDED"
            and self.process.process_created
            and self.process.initial_thread_resumed
            and self.process.tree_exit_confirmed
            and lifecycle.get("cleanup_confirmed") is True
            and lifecycle.get("confirmed_write_bytes") == 10
            and observation.get("errors") == ["FEEDBACK_DEADLINE_EXCEEDED"]
            and all(
                (observation.get(name) or {}).get("bytes") == 0
                for name in ("startup", "response", "late_cleanup_input")
            )
        ):
            # Host write completion is not proof of firmware receipt. Classify
            # only an observed clean, silent timeout, never missing child data.
            code = "POWERED_QUERY_WRITTEN_NO_REPLY"
        elif (
            self.process.status == "SUCCEEDED"
            and self.process.process_created
            and self.process.initial_thread_resumed
            and self.process.tree_exit_confirmed
            and observation.get("status") == "FAILED"
            and observation.get("errors") == ["PREEXISTING_INPUT"]
            and lifecycle.get("cleanup_confirmed") is True
            and type(lifecycle.get("confirmed_write_bytes")) is int
            and lifecycle["confirmed_write_bytes"] == 0
            and type((observation.get("startup") or {}).get("bytes")) is int
            and observation["startup"]["bytes"] > 0
        ):
            # Incoming bytes can be partial, buffered or unrelated to pose.
            # Diagnose the query/stream mismatch without claiming telemetry
            # readiness or granting a second attempt in this launch.
            code = "POWERED_INPUT_BEFORE_QUERY"
        next_step = None
        if code == "POWERED_QUERY_WRITTEN_NO_REPLY":
            next_step = (
                "No reply was observed after the completed host write. "
                "Check the ESP32 USB interface (board number 9), not the LiDAR interface; "
                "check controller state. CP210x metadata alone does not identify "
                "the application. Do not automatically retry, reset, flash or move."
            )
        elif code == "POWERED_INPUT_BEFORE_QUERY":
            next_step = (
                "Input arrived before the query; zero command bytes were written. "
                "Export and review this consumed attempt. For a new reviewed launch, "
                "use Capture arm telemetry (no commands) with current powered setup "
                "and USB correlation. Do not purge input or retry this query. "
                "These bytes alone do not prove a complete pose or fresh servo samples."
            )
        return {
            "schema": "rocell.wizard_powered_feedback_result.v1",
            "action_id": ACTION,
            "status": status,
            "code": code,
            "steps": [
                {
                    "name": "powered_feedback_attempt",
                    "exit_code": 0 if status == "SUCCEEDED" else 1,
                    "report": {
                        "status": code,
                        "process_status": self.process.status,
                        "process_created": self.process.process_created,
                        "process_tree_exit_confirmed": self.process.tree_exit_confirmed,
                        "observation_status": observation.get("status"),
                        "errors": observation.get("errors"),
                        "feedback": observation.get("feedback"),
                        "confirmed_write_bytes": lifecycle.get("confirmed_write_bytes"),
                        "serial_cleanup_confirmed": lifecycle.get("cleanup_confirmed"),
                        "response_bytes": (observation.get("response") or {}).get("bytes"),
                        "next_step": next_step,
                        "outcome_sha256": self.outcome_sha256,
                        "persistence_error": self.persistence_error,
                        "connected": False,
                        "motion_authorized": False,
                        "physical_authority": False,
                    },
                }
            ],
            "physical_authority": False,
        }

    def _telemetry_publication(self, observation, lifecycle):
        """Compact UI view; complete bytes and records stay in the native export."""
        from rocell.arm.telemetry_stream import POSE_FIELDS, OPTIONAL_FIELDS
        from .observational_capture_preview import summarize_capture
        capture = observation.get("capture") or {}
        last = capture.get("latest_pose_record") or {}
        fields = last.get("fields") or {}
        status, code = "FAILED", "POWERED_TELEMETRY_INCOMPLETE"
        if self.persistence_error or not self.outcome_sha256:
            code = "POWERED_FEEDBACK_PERSISTENCE_FAILED"
        elif self.process.process_created and not self.process.tree_exit_confirmed:
            code = "POWERED_PROCESS_CLEANUP_UNKNOWN"
        elif self.process.status in {"CANCELLED", "TIMED_OUT"}:
            status, code = self.process.status, "POWERED_TELEMETRY_" + self.process.status
        elif (self.process.status == "SUCCEEDED" and self.process.process_created
              and self.process.initial_thread_resumed and self.process.tree_exit_confirmed
              and observation.get("status") == "CAPTURED_CLOSED"
              and lifecycle.get("cleanup_confirmed") is True
              and lifecycle.get("confirmed_write_bytes") == 0):
            # An empty/partial-only capture is useful evidence, not telemetry
            # readiness. Even successful samples remain unsolicited and uncalibrated.
            if last and capture.get("pose_sample_count", 0) > 0:
                status, code = "SUCCEEDED", "UNSOLICITED_TELEMETRY_CAPTURED"
            else:
                code = "NO_COMPLETE_TELEMETRY_SAMPLE"
        return {"schema": "rocell.wizard_powered_feedback_result.v1",
                "action_id": TELEMETRY_ACTION, "status": status, "code": code,
                "physical_authority": False,
                "steps": [{"name": "powered_telemetry_capture", "exit_code": 0 if status == "SUCCEEDED" else 1,
                    "report": {"status": code, "errors": observation.get("errors"),
                        "stop_reason": observation.get("stop_reason"),
                        "capture_bytes": (capture.get("raw") or {}).get("bytes"),
                        "pose_sample_count": capture.get("pose_sample_count"),
                        "latest_observed_fields": {k: fields[k] for k in sorted(POSE_FIELDS | OPTIONAL_FIELDS) if k in fields},
                        "missing_optional_fields": last.get("missing_optional_fields"),
                        "interpretation": "UNSOLICITED_OR_BUFFERED_NOT_QUERY_REPLY",
                        "sample_freshness_verified": False,
                        "observational_wrist_preview": (summarize_capture(observation)
                            if status == 'SUCCEEDED' else None),
                        "confirmed_write_bytes": lifecycle.get("confirmed_write_bytes"),
                        "serial_cleanup_confirmed": lifecycle.get("cleanup_confirmed"),
                        "process_tree_exit_confirmed": self.process.tree_exit_confirmed,
                        "outcome_sha256": self.outcome_sha256, "persistence_error": self.persistence_error,
                        "connected": False, "motion_authorized": False, "physical_authority": False}}]}


def run_feedback(
    *,
    root,
    session_id,
    operation_id,
    source_sha256,
    startup_operation_id,
    expected_startup_sha256,
    native_original,
    generic_review,
    history_original,
    protocol_original,
    installed_firmware_evidence_original=None,
    deadline_ns,
    cancellation,
    check_current,
    action_id=ACTION,
):
    if action_id not in (ACTION, TELEMETRY_ACTION):
        raise ValueError("Closed powered action required")
    telemetry = action_id == TELEMETRY_ACTION
    root = safe_root(Path(root))
    # Validate opaque identifiers before incorporating them into any path.
    import re

    for value in (operation_id, startup_operation_id):
        if (
            type(value) is not str
            or re.fullmatch(r"operation-[a-f0-9]{32}", value) is None
        ):
            raise ValueError("Exact service operation IDs required")
    check_current()
    startup_raw = read_bounded_regular_file(
        contained_path(
            root,
            startup_operation_id + "-powered-startup-original.json",
            label="powered startup",
        ),
        maximum_bytes=32768,
    )
    if hashlib.sha256(startup_raw).hexdigest() != expected_startup_sha256:
        raise ValueError("Powered startup original changed")
    startup = decode_diagnostic_json(startup_raw, maximum=32768)
    directory = root / (operation_id + "-powered-native-child")
    directory.mkdir(exist_ok=False)

    def pin(path):
        return PinnedWorkerFile(
            path,
            hashlib.sha256(
                read_bounded_regular_file(path, maximum_bytes=32 * 1024 * 1024)
            ).hexdigest(),
        )

    archive = pin(package.prepare(directory))
    registration = WorkerProcessRegistration(
        protocol.WORKER_ID,
        pin(Path(getattr(sys, "_base_executable", sys.executable))),
        ("-I", "-S", str(package.CHILD), str(archive.path), archive.sha256, "observe"),
        (pin(package.CHILD), archive),
        directory,
        WorkerProcessBudget(
            run_timeout_ms=20000,
            cleanup_timeout_ms=2000,
            stdin_bytes=65536,
            stdout_bytes=256 * 1024,
            stderr_bytes=8192,
            process_count=1,
        ),
        "PHYSICAL_UNQUALIFIED",
        protocol.REQUEST_SCHEMA,
        protocol.RESULT_SCHEMA,
    )
    runtime = owned_registration_document(registration)
    runtime_raw = _canonical(runtime)
    profile = _canonical(
        {
            "schema": "rocell.fixed_powered_feedback_serial_profile.v1",
            "dcb": asdict(DcbSettings()),
            "timeouts": asdict(CommTimeouts()),
        }
    )
    firmware = create_review(
        session_id=session_id,
        source_sha256=source_sha256,
        operator_id=startup["operator_id"],
        history_original=history_original,
        protocol_review_original=protocol_original,
        installed_firmware_evidence_original=installed_firmware_evidence_original,
    )
    originals = {
        "powered_startup_original_sha256": startup_raw,
        "native_identity_original_sha256": native_original,
        "runtime_sha256": runtime_raw,
        "serial_profile_sha256": profile,
        "protocol_review_sha256": protocol_original,
        "firmware_compatibility_review_sha256": firmware,
    }
    refs = {name: hashlib.sha256(raw).hexdigest() for name, raw in originals.items()}
    refs["source_sha256"] = source_sha256
    intent = PoweredFeedbackIntent(
        _canonical(
            dict(
                schema=SCHEMA,
                purpose=TELEMETRY_PURPOSE if telemetry else PURPOSE,
                mode="physical",
                session_id=session_id,
                attempt_id=operation_id,
                references=refs,
                limits=TELEMETRY_LIMITS if telemetry else LIMITS,
                startup_recorded_monotonic_ns=startup["recorded_monotonic_ns"],
                parent_deadline_monotonic_ns=deadline_ns,
            )
        )
    )
    prepared = prepare_powered_feedback(
        intent=intent,
        root=root,
        startup_operation_id=startup_operation_id,
        current_source_sha256=source_sha256,
        native_original=native_original,
        generic_review=generic_review,
        runtime_original=runtime_raw,
        serial_profile_original=profile,
        protocol_review_original=protocol_original,
        firmware_review_original=firmware,
        now_monotonic_ns=time.monotonic_ns(),
    )
    journal = PoweredFeedbackAttemptJournal(
        root,
        prepared,
        startup_operation_id=startup_operation_id,
        current_source_sha256=source_sha256,
        now_monotonic_ns=time.monotonic_ns(),
    )
    check_current()
    receipt = journal.consume(
        current_source_sha256=source_sha256, now_monotonic_ns=time.monotonic_ns()
    )
    payload = dict(
        schema=protocol.PAYLOAD_SCHEMA,
        root=str(root),
        intent=intent.to_dict(),
        consumption_sha256=receipt["consumption_sha256"],
        registration=runtime,
    )
    outer = OwnedWorkerRequest(
        operation_id,
        session_id,
        source_sha256,
        intent.request_sha256,
        refs["native_identity_original_sha256"],
        deadline_ns,
        _canonical(payload),
    )
    protocol.validate_registration(registration, outer)

    def authorize(actual_registration, actual_request, digest):
        if actual_registration != registration or actual_request != outer:
            raise ValueError("Powered dispatch inputs changed")
        check_current()
        intent.require_time_available(time.monotonic_ns())

    owned = OwnedWindowsWorker(registration, authorizer=authorize).run(
        outer, cancellation=cancellation, deadline_ns=deadline_ns
    )
    outcome_sha, error = None, None
    try:
        outcome_sha = journal.retain_outcome(
            stdout=owned.stdout, stderr=owned.stderr, process_status=owned.status
        )
    except Exception as failure:
        error = type(failure).__name__
    return PoweredFeedbackOutcome(owned, outcome_sha, error, action_id)
