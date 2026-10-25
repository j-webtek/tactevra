"""One-use, bounded process boundary with closed purpose-specific registrations.

This is not a UI command runner or a device authorizer. The exact passive child
requires retained consumed originals and source/runtime binding; its serial API
is still source-held. Other physical registrations remain held. Process exit
never proves device cleanup, final power state or commissioning acceptance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Callable

REQUEST_SCHEMA = "rocell.owned_worker_fixture_request.v1"
RESULT_SCHEMA = "rocell.owned_worker_fixture_result.v1"
FIXTURE_PATH = Path(__file__).with_name("_owned_process_fixture.py")
SCENARIOS = frozenset(
    {
        "nominal",
        "stall",
        "stalled-input",
        "stdout-flood",
        "stderr-flood",
        "malformed",
        "wrong-binding",
        "exit-failure",
        "spawn-child",
        "breakaway",
        "memory-limit",
        "handle-flood",
    }
)
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
# At most one unresolved owner is retained in-process. Never free buffers still
# referenced by overlapped I/O or admit another worker after uncertain cleanup.
_UNRESOLVED_BACKEND: Any = None
_DISPATCH_LOCK = threading.Lock()


class OwnedWorkerError(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise OwnedWorkerError(code)


def _integer(value: Any, low: int, high: int) -> None:
    _require(type(value) is int and low <= value <= high, "INVALID_INTEGER_BUDGET")


def _hash(value: Any) -> None:
    _require(type(value) is str and bool(_HASH.fullmatch(value)), "INVALID_SHA256")


def _path(value: Any) -> None:
    _require(
        isinstance(value, Path)
        and value.is_absolute()
        and value != Path(value.anchor)
        and ".." not in value.parts
        and not str(value).startswith(("\\\\", "//")),
        "INVALID_ASSIGNED_PATH",
    )


def _json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def decode_owned_json(payload: bytes, *, maximum: int, maximum_nodes: int = 4096) -> dict[str, Any]:
    """Finite strict JSON; no duplicate fields, coercion, nonfinite values."""
    _require(type(payload) is bytes and 0 < len(payload) <= maximum, "IPC_BYTE_LIMIT")
    _require(type(maximum_nodes) is int and 1<=maximum_nodes<=16384, "IPC_NODE_BUDGET")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            _require(key not in result, "DUPLICATE_JSON_FIELD")
            result[key] = value
        return result

    def bad(_: str) -> Any:
        raise OwnedWorkerError("NONFINITE_JSON")

    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=pairs, parse_constant=bad
        )
        nodes = 0

        def check(item: Any, depth: int = 0) -> None:
            nonlocal nodes
            nodes += 1
            _require(nodes <= maximum_nodes and depth <= 16, "IPC_STRUCTURE_LIMIT")
            if type(item) is dict:
                for key, child in item.items():
                    check(key, depth + 1)
                    check(child, depth + 1)
            elif type(item) is list:
                for child in item:
                    check(child, depth + 1)
            elif type(item) is float:
                _require(math.isfinite(item), "NONFINITE_JSON")
            else:
                _require(item is None or type(item) in {str, int, bool}, "INVALID_JSON")

        check(value)
        _require(type(value) is dict, "IPC_OBJECT_REQUIRED")
        return value
    except (UnicodeError, RecursionError) as exc:
        raise OwnedWorkerError("INVALID_JSON") from exc


@dataclass(frozen=True)
class PinnedWorkerFile:
    path: Path
    sha256: str
    maximum_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        _path(self.path)
        _hash(self.sha256)
        _integer(self.maximum_bytes, 1, 256 * 1024 * 1024)


@dataclass(frozen=True)
class WorkerProcessBudget:
    run_timeout_ms: int = 5000
    cleanup_timeout_ms: int = 2000
    stdin_bytes: int = 64 * 1024
    stdout_bytes: int = 256 * 1024
    stderr_bytes: int = 64 * 1024
    process_count: int = 4
    process_memory_bytes: int = 256 * 1024 * 1024
    job_memory_bytes: int = 512 * 1024 * 1024
    observed_handles_per_process: int = 512

    def __post_init__(self) -> None:
        for key, low, high in (
            ("run_timeout_ms", 100, 60_000),
            ("cleanup_timeout_ms", 100, 5000),
            ("stdin_bytes", 512, 64 * 1024),
            ("stdout_bytes", 128, 256 * 1024),
            ("stderr_bytes", 128, 64 * 1024),
            ("process_count", 1, 4),
            ("process_memory_bytes", 32 * 1024 * 1024, 1024 * 1024 * 1024),
            ("job_memory_bytes", 32 * 1024 * 1024, 2 * 1024 * 1024 * 1024),
            ("observed_handles_per_process", 32, 4096),
        ):
            _integer(getattr(self, key), low, high)
        _require(
            self.job_memory_bytes >= self.process_memory_bytes, "INVALID_MEMORY_BUDGET"
        )


@dataclass(frozen=True)
class WorkerProcessRegistration:
    worker_id: str
    executable: PinnedWorkerFile
    argv: tuple[str, ...]
    package_files: tuple[PinnedWorkerFile, ...]
    working_directory: Path
    budget: WorkerProcessBudget = field(default_factory=WorkerProcessBudget)
    composition: str = "PHYSICAL_UNQUALIFIED"
    request_schema: str = REQUEST_SCHEMA
    result_schema: str = RESULT_SCHEMA

    def __post_init__(self) -> None:
        _require(
            type(self.worker_id) is str and bool(_ID.fullmatch(self.worker_id)),
            "INVALID_WORKER_ID",
        )
        _require(
            type(self.executable) is PinnedWorkerFile, "PINNED_EXECUTABLE_REQUIRED"
        )
        self.executable.__post_init__()
        _require(
            self.executable.path.suffix.lower() == ".exe", "EXACT_EXECUTABLE_REQUIRED"
        )
        _require(
            type(self.argv) is tuple
            and 1 <= len(self.argv) <= 16
            and all(
                type(arg) is str and "\0" not in arg and len(arg) <= 4096
                for arg in self.argv
            )
            and sum(map(len, self.argv)) <= 16_000,
            "EXACT_ARGV_REQUIRED",
        )
        _require(
            type(self.package_files) is tuple
            and 1 <= len(self.package_files) <= 8
            and all(type(item) is PinnedWorkerFile for item in self.package_files),
            "PACKAGE_PINS_REQUIRED",
        )
        for item in self.package_files:
            item.__post_init__()
        _require(
            len({p.path for p in (self.executable,) + self.package_files})
            == 1 + len(self.package_files),
            "DUPLICATE_PACKAGE_PIN",
        )
        _path(self.working_directory)
        _require(type(self.budget) is WorkerProcessBudget, "TYPED_BUDGET_REQUIRED")
        self.budget.__post_init__()
        _require(
            self.composition in {"INCAPABLE_PROCESS_FIXTURE", "PHYSICAL_UNQUALIFIED"},
            "UNKNOWN_COMPOSITION",
        )


@dataclass(frozen=True)
class OwnedWorkerRequest:
    attempt_id: str
    session_id: str
    source_sha256: str
    operation_sha256: str
    selected_identity_sha256: str
    expires_at_ns: int
    payload_json: bytes = b"{}"

    def __post_init__(self) -> None:
        for value in (self.attempt_id, self.session_id):
            _require(
                type(value) is str and bool(_ID.fullmatch(value)), "INVALID_REQUEST_ID"
            )
        for value in (
            self.source_sha256,
            self.operation_sha256,
            self.selected_identity_sha256,
        ):
            _hash(value)
        _integer(self.expires_at_ns, 1, 2**63 - 1)
        payload = decode_owned_json(self.payload_json, maximum=60 * 1024)
        if payload.get("schema") == "rocell.positional_campaign_native_handoff.v1":
            # Format support only. Native launch remains held until campaign
            # prelaunch, supervision and parent retention are composed.
            from .positional_campaign_native_protocol import validate_payload

            validate_payload(payload)
            return
        if payload.get("schema") == "rocell.wrist_correction_native_handoff.v1":
            # Format support only; no correction execution branch is enabled.
            from .wrist_correction_native_protocol import validate_payload

            validate_payload(payload)
            return
        if payload.get("schema") == "rocell.absolute_wrist_native_handoff.v1":
            # Parsing alone grants no launch permission; run checks the fixed
            # registration, reserved approval, and owned process receipt.
            from .absolute_wrist_native_protocol import validate_payload

            validate_payload(payload)
            return
        if payload.get("schema") == "rocell.observational_native_handoff.v1":
            # Parsing is not admission; the fixed physical branch checks launch records.
            from .observational_native_protocol import validate_payload

            validate_payload(payload)
            return
        if payload.get("schema") == "rocell.first_motion_native_handoff.v1":
            # Data-format support only; no physical registration/launch branch.
            from .first_motion_native_protocol import validate_payload

            validate_payload(payload)
            return
        if payload.get("schema") == "rocell.endpoint_native_handoff.v1":
            from .endpoint_native_registration import validate_payload

            validate_payload(payload)
            return
        if payload.get("schema") == "rocell.powered_feedback_native_handoff.v1":
            from .powered_feedback_native_registration import validate_payload

            validate_payload(payload)
            return
        if payload.get("schema") == "rocell.calibrated_position_vector_native_handoff.v1":
            from .calibrated_position_vector_owned_protocol import validate_payload

            validate_payload(payload)
            return
        if (
            payload.get("schema")
            == "rocell.owned_powered_feedback_rehearsal_payload.v1"
        ):
            from .powered_feedback_process_codec import validate_payload

            validate_payload(payload)
            return
        if payload.get("schema") == "rocell.passive_native_child_handoff.v1":
            from .passive_native_registration import validate_payload

            validate_payload(payload)
            return
        if payload.get("schema") == "rocell.owned_passive_arm_fixture_payload.v1":
            from .passive_arm_process_codec import validate_payload

            validate_payload(payload)
            return
        if payload.get("schema") in {
            "rocell.owned_camera_fixture_payload.v1",
            "rocell.owned_camera_fixture_payload.v2",
        }:
            from .owned_camera_codec import validate_payload

            validate_payload(payload)
            return
        _require(
            set(payload) <= {"padding"}
            and ("padding" not in payload or type(payload["padding"]) is str),
            "FIXTURE_PAYLOAD_SCHEMA_MISMATCH",
        )


def owned_registration_document(
    registration: WorkerProcessRegistration,
) -> dict[str, Any]:
    """Canonical pure registration projection shared by preparation/admission."""
    return {
        **asdict(registration),
        "argv": list(registration.argv),
        "executable": {
            **asdict(registration.executable),
            "path": str(registration.executable.path),
        },
        "package_files": [
            {**asdict(pin), "path": str(pin.path)} for pin in registration.package_files
        ],
        "working_directory": str(registration.working_directory),
    }


def owned_request_wire(
    registration: WorkerProcessRegistration,
    request: OwnedWorkerRequest,
    *,
    deadline_ns: int,
) -> tuple[bytes, str]:
    """Pure exact input/digest; no authority, filesystem access or dispatch."""
    _require(
        type(registration) is WorkerProcessRegistration
        and type(request) is OwnedWorkerRequest,
        "EXACT_REQUEST_REQUIRED",
    )
    registration.__post_init__()
    request.__post_init__()
    _integer(deadline_ns, 1, request.expires_at_ns)
    body = {
        "schema": registration.request_schema,
        "worker_id": registration.worker_id,
        "attempt_id": request.attempt_id,
        "session_id": request.session_id,
        "source_sha256": request.source_sha256,
        "operation_sha256": request.operation_sha256,
        "selected_identity_sha256": request.selected_identity_sha256,
        "expires_at_monotonic_ns": request.expires_at_ns,
        "parent_deadline_monotonic_ns": deadline_ns,
        "payload": decode_owned_json(request.payload_json, maximum=60 * 1024),
        "registration_sha256": hashlib.sha256(
            _json(owned_registration_document(registration))
        ).hexdigest(),
    }
    request_sha = hashlib.sha256(_json(body)).hexdigest()
    wire = _json({**body, "request_sha256": request_sha}) + b"\n"
    _require(len(wire) <= registration.budget.stdin_bytes, "STDIN_LIMIT")
    return wire, request_sha


@dataclass(frozen=True)
class OwnedWorkerResult:
    status: str
    primary_error: str | None
    cleanup_errors: tuple[str, ...]
    request_sha256: str
    attempt_id: str
    process_created: bool
    initial_thread_resumed: bool
    tree_exit_confirmed: bool
    returncode: int | None
    elapsed_ns: int
    stdin_bytes_written: int
    peak_observed_handles: int
    peak_active_processes: int
    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)
    parsed_result: dict[str, Any] | None = None
    owned_process_id: int = 0
    finished_monotonic_ns: int = 0

    def to_dict(self) -> dict[str, Any]:
        value = {
            key: item
            for key, item in asdict(self).items()
            if key not in {"stdout", "stderr"}
        }
        for key in ("stdout", "stderr"):
            data = getattr(self, key)
            value[key + "_bytes"] = len(data)
            value[key + "_sha256"] = hashlib.sha256(data).hexdigest()
        value.update(
            schema="rocell.owned_worker_process_result.v1",
            physical_authority=False,
            physical_provider_qualified=False,
            device_cleanup_confirmed=False,
            final_power_state="UNKNOWN_REQUIRES_SEPARATE_OBSERVATION",
            handle_limit_kind="SAMPLED_NOT_KERNEL_ENFORCED",
            retries=0,
        )
        return value


class OwnedWindowsWorker:
    """Inert construction/status; one explicit run, including failed admission."""

    def __init__(
        self,
        registration: WorkerProcessRegistration,
        *,
        authorizer: Callable[
            [WorkerProcessRegistration, OwnedWorkerRequest, str], None
        ],
        _backend_factory: Callable[[], Any] | None = None,
        _clock: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        _require(
            type(registration) is WorkerProcessRegistration,
            "REGISTERED_WORKER_REQUIRED",
        )
        registration.__post_init__()
        _require(callable(authorizer), "EXTERNAL_AUTHORIZER_REQUIRED")
        self.registration = registration
        self._authorizer, self._backend_factory, self._clock = (
            authorizer,
            _backend_factory,
            _clock,
        )
        self._consumed = False
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        return {
            "worker_id": self.registration.worker_id,
            "consumed": self._consumed,
            "physical_provider_qualified": False,
            "physical_authority": False,
            "native_activation": "HELD",
            "implicit_dispatch": False,
            "process_cleanup_hold": _UNRESOLVED_BACKEND is not None,
        }

    def run(
        self,
        request: OwnedWorkerRequest,
        *,
        cancellation: threading.Event,
        deadline_ns: int,
    ) -> OwnedWorkerResult:
        global _UNRESOLVED_BACKEND
        with self._lock:
            _require(not self._consumed, "WORKER_ALREADY_CONSUMED")
            self._consumed = True
        started = self._clock()
        reg = self.registration
        request_sha = "0" * 64
        primary = None
        native = None
        parsed = None
        camera_payload = None
        passive_payload = None
        native_passive_payload = None
        native_powered_payload = None
        native_endpoint_payload = None
        native_first_motion_payload = None
        native_observational_payload = None
        native_absolute_wrist_payload = None
        native_correction_payload = None
        native_campaign_payload = None
        native_position_vector_payload = None
        position_vector_wire = None
        correction_wire = None
        native_start_ns = started
        powered_rehearsal_payload = None
        owns_dispatch = False
        try:
            _require(type(request) is OwnedWorkerRequest, "EXACT_REQUEST_REQUIRED")
            request.__post_init__()
            reg.__post_init__()
            _require(_UNRESOLVED_BACKEND is None, "PROCESS_CLEANUP_HOLD")
            owns_dispatch = _DISPATCH_LOCK.acquire(blocking=False)
            _require(owns_dispatch, "OWNED_PROCESS_ALREADY_RUNNING")
            _require(_UNRESOLVED_BACKEND is None, "PROCESS_CLEANUP_HOLD")
            _require(
                isinstance(cancellation, threading.Event), "CANCELLATION_EVENT_REQUIRED"
            )
            _integer(deadline_ns, 1, request.expires_at_ns)

            if reg.request_schema == 'rocell.owned_positional_campaign_request.v1':
                # Preserve request association even when native admission holds
                # before child creation; otherwise diagnostics carry a zero hash.
                from .positional_campaign_native_protocol import decode_request
                campaign_wire, request_sha = owned_request_wire(reg, request, deadline_ns=deadline_ns)
                decode_request(campaign_wire)

            def verify_native_passive_entry():
                from rocell.application.passive_arm_child_claim import (
                    verify_consumed_attempt,
                )
                from .passive_native_registration import validate_payload

                verify_consumed_attempt(
                    root=Path(native_passive_payload["root"]),
                    request=validate_payload(native_passive_payload),
                    expected_consumption_sha256=native_passive_payload[
                        "consumption_sha256"
                    ],
                    registration=native_passive_payload["registration"],
                    now_monotonic_ns=self._clock(),
                )

            def verify_native_powered_entry():
                from rocell.application.powered_feedback_child_claim import (
                    verify_consumed_attempt,
                )
                from .powered_feedback_native_registration import validate_payload

                verify_consumed_attempt(
                    root=Path(native_powered_payload["root"]),
                    intent=validate_payload(native_powered_payload),
                    expected_consumption_sha256=native_powered_payload[
                        "consumption_sha256"
                    ],
                    runtime_original=_json(native_powered_payload["registration"]),
                    current_source_sha256=request.source_sha256,
                    now_monotonic_ns=self._clock(),
                )

            def verify_native_endpoint_entry():
                from .endpoint_native_registration import verify_reserved_entry
                verify_reserved_entry(native_endpoint_payload,clock_ns=self._clock)

            def verify_native_first_motion_entry():
                from .first_motion_prelaunch import verify_reserved_first_motion_entry
                from .first_motion_native_package import CHILD
                verify_reserved_first_motion_entry(native_first_motion_payload,
                    workspace=CHILD.parents[5],clock_ns=self._clock)

            def verify_native_observational_entry():
                from .observational_prelaunch import verify_reserved_observational_entry
                from .observational_native_package import CHILD
                verify_reserved_observational_entry(native_observational_payload,
                    workspace=CHILD.parents[5], clock_ns=self._clock)

            def verify_native_absolute_wrist_entry():
                from .absolute_wrist_prelaunch import verify_reserved_absolute_wrist_entry
                from .absolute_wrist_native_package import CHILD
                verify_reserved_absolute_wrist_entry(native_absolute_wrist_payload,
                    workspace=CHILD.parents[5], clock_ns=self._clock)

            def verify_native_correction_entry():
                from .wrist_correction_prelaunch import verify_reserved_correction_entry
                from .wrist_correction_native_package import CHILD
                verify_reserved_correction_entry(native_correction_payload,
                    workspace=CHILD.parents[5],clock_ns=self._clock)

            def verify_native_campaign_entry():
                from .positional_campaign_prelaunch import verify_reserved_campaign_entry
                from .positional_campaign_native_package import CHILD
                verify_reserved_campaign_entry(CHILD.parents[5], campaign_wire,
                    cancellation=cancellation, clock_ns=self._clock)

            if reg.request_schema == 'rocell.owned_positional_campaign_request.v1':
                from .positional_campaign_native_registration import validate_registration
                campaign_decoded = decode_request(campaign_wire)
                _require(campaign_decoded['payload']['campaign_intent']['schema'] in
                    ('rocell.attended_positional_intent.v2', 'rocell.attended_positional_intent.v3',
                     'rocell.attended_positional_intent.v4', 'rocell.attended_positional_intent.v5',
                     'rocell.attended_positional_intent.v6', 'rocell.attended_positional_intent.v7',
                     'rocell.attended_positional_intent.v8', 'rocell.attended_positional_intent.v9',
                     'rocell.attended_positional_intent.v10', 'rocell.attended_positional_intent.v11',
                     'rocell.attended_positional_intent.v12', 'rocell.attended_positional_intent.v13',
                     'rocell.attended_positional_intent.v14',
                     'rocell.attended_positional_intent.v15',
                     'rocell.attended_positional_intent.v16',
                     'rocell.attended_positional_intent.v17', 'rocell.attended_positional_intent.v18', 'rocell.attended_positional_intent.v19', 'rocell.attended_positional_intent.v20','rocell.attended_positional_intent.v21','rocell.attended_positional_intent.v22'),
                    'CAMPAIGN_BOUNDED_ATTENDED_V2_REQUIRED')
                validate_registration(reg, campaign_wire)
                verify_native_campaign_entry()
                native_campaign_payload = campaign_decoded['payload']
            elif reg.request_schema == 'rocell.owned_wrist_correction_native_request.v1':
                from .wrist_correction_native_registration import validate_registration
                native_correction_payload = validate_registration(reg, request)
                _require(deadline_ns == request.expires_at_ns, 'CORRECTION_EXACT_DEADLINE_REQUIRED')
                correction_wire, request_sha = owned_request_wire(reg,request,deadline_ns=deadline_ns)
                verify_native_correction_entry()
            elif reg.request_schema == 'rocell.owned_absolute_wrist_native_request.v1':
                from .absolute_wrist_native_registration import validate_registration
                native_absolute_wrist_payload = validate_registration(reg, request)
                _require(deadline_ns == request.expires_at_ns, 'ABSOLUTE_WRIST_EXACT_DEADLINE_REQUIRED')
                verify_native_absolute_wrist_entry()
            elif reg.request_schema == 'rocell.owned_observational_native_request.v1':
                from .observational_native_registration import validate_registration
                native_observational_payload = validate_registration(reg, request)
                _require(deadline_ns == request.expires_at_ns, 'OBSERVATIONAL_EXACT_DEADLINE_REQUIRED')
                verify_native_observational_entry()
            elif reg.request_schema == 'rocell.owned_first_motion_native_request.v1':
                from .first_motion_native_registration import validate_registration
                native_first_motion_payload = validate_registration(reg,request)
                _require(deadline_ns==request.expires_at_ns,'COMMISSIONING_EXACT_DEADLINE_REQUIRED')
                verify_native_first_motion_entry()
            elif reg.request_schema == 'rocell.owned_endpoint_native_request.v1':
                from .endpoint_native_registration import validate_registration
                native_endpoint_payload = validate_registration(reg,request)
                _require(deadline_ns==request.expires_at_ns,'ENDPOINT_EXACT_DEADLINE_REQUIRED')
                verify_native_endpoint_entry()
            elif reg.request_schema == "rocell.owned_powered_feedback_native_request.v1":
                from .powered_feedback_native_registration import validate_registration

                native_powered_payload = validate_registration(reg, request)
                _require(
                    deadline_ns == request.expires_at_ns,
                    "POWERED_EXACT_DEADLINE_REQUIRED",
                )
                verify_native_powered_entry()
            elif reg.request_schema == "rocell.owned_calibrated_position_vector_request.v1":
                from .calibrated_position_vector_native_registration import validate_registration
                from .calibrated_position_vector_owned_protocol import decode_request

                native_position_vector_payload = validate_registration(reg, request)
                _require(
                    deadline_ns == request.expires_at_ns,
                    "POSITION_VECTOR_EXACT_DEADLINE_REQUIRED",
                )
                position_vector_wire, request_sha = owned_request_wire(
                    reg, request, deadline_ns=deadline_ns
                )
                decode_request(position_vector_wire)
            elif reg.request_schema == "rocell.owned_passive_native_request.v1":
                from .passive_native_registration import validate_registration

                native_passive_payload = validate_registration(reg, request)
                _require(
                    deadline_ns == request.expires_at_ns,
                    "PASSIVE_EXACT_DEADLINE_REQUIRED",
                )
                verify_native_passive_entry()
            else:
                _require(
                    reg.composition == "INCAPABLE_PROCESS_FIXTURE",
                    "PHYSICAL_PROVIDER_QUALIFICATION_HELD",
                )
            if (native_passive_payload is not None or native_powered_payload is not None
                    or native_endpoint_payload is not None or native_first_motion_payload is not None
                    or native_observational_payload is not None or native_absolute_wrist_payload is not None
                    or native_correction_payload is not None or native_campaign_payload is not None
                    or native_position_vector_payload is not None):
                pass  # Exact registration and consumed originals checked above.
            elif (
                reg.request_schema
                == "rocell.owned_powered_feedback_rehearsal_request.v1"
            ):
                from .powered_feedback_process_codec import validate_registration

                powered_rehearsal_payload = validate_registration(reg, request)
                _require(
                    deadline_ns == request.expires_at_ns,
                    "POWERED_EXACT_DEADLINE_REQUIRED",
                )
            elif reg.request_schema == "rocell.owned_passive_arm_fixture_request.v1":
                from .passive_arm_process_codec import validate_registration

                passive_payload = validate_registration(reg, request)
                _require(
                    deadline_ns == request.expires_at_ns,
                    "PASSIVE_EXACT_DEADLINE_REQUIRED",
                )
            elif reg.request_schema in {
                "rocell.owned_camera_fixture_request.v1",
                "rocell.owned_camera_fixture_request.v2",
            }:
                from .owned_camera_codec import validate_camera_registration

                camera_payload = validate_camera_registration(reg, request)
            else:
                _require(
                    reg.request_schema == REQUEST_SCHEMA
                    and reg.result_schema == RESULT_SCHEMA,
                    "UNREGISTERED_PROTOCOL",
                )
                _require(
                    reg.argv[:3] == ("-I", "-S", str(FIXTURE_PATH))
                    and len(reg.argv) == 4
                    and reg.argv[3] in SCENARIOS
                    and any(p.path == FIXTURE_PATH for p in reg.package_files)
                    and reg.executable.path
                    == Path(getattr(sys, "_base_executable", sys.executable)),
                    "UNREGISTERED_FIXTURE_COMMAND",
                )
                # A camera payload cannot be carried by the older fixture codec.
                payload = decode_owned_json(request.payload_json, maximum=60 * 1024)
                _require(set(payload) <= {"padding"}, "FIXTURE_PAYLOAD_SCHEMA_MISMATCH")
            wire, request_sha = owned_request_wire(
                reg, request, deadline_ns=deadline_ns
            )
            reviewed_registration = asdict(reg)
            reviewed_request = asdict(request)
            required_ns = (
                reg.budget.run_timeout_ms + reg.budget.cleanup_timeout_ms
            ) * 1_000_000
            if native_campaign_payload is not None:
                # The intent's 30 seconds include preparation. Reserve the
                # remaining 24-second open/two-leg/cleanup budget, never renew it.
                campaign_body = native_campaign_payload['campaign_intent']
                required_ns = (47 if campaign_body['schema'] in ('rocell.attended_positional_intent.v18','rocell.attended_positional_intent.v19','rocell.attended_positional_intent.v20','rocell.attended_positional_intent.v21','rocell.attended_positional_intent.v22') else 40 if campaign_body['schema']=='rocell.attended_positional_intent.v14' else 24)*1_000_000_000
            _require(not cancellation.is_set(), "CANCELLED_BEFORE_DISPATCH")
            _require(
                self._clock() + required_ns <= deadline_ns,
                "LIFETIME_BUDGET_DOES_NOT_FIT",
            )
            if self._backend_factory is None:
                from rocell.providers.windows._owned_worker_win32 import (
                    WindowsOwnedProcess,
                    WindowsOwnedPassivePipeProcess,
                )

                native = (
                    WindowsOwnedPassivePipeProcess()
                    if native_passive_payload is not None
                    or native_powered_payload is not None
                    or native_endpoint_payload is not None
                    or native_first_motion_payload is not None
                    or native_observational_payload is not None
                    or native_absolute_wrist_payload is not None
                    or native_correction_payload is not None
                    or native_campaign_payload is not None
                    or native_position_vector_payload is not None
                    else WindowsOwnedProcess()
                )
            else:
                native = self._backend_factory()
            native.pin(reg)
            _require(not cancellation.is_set(), "CANCELLED_BEFORE_DISPATCH")
            _require(
                self._clock() + required_ns <= deadline_ns,
                "LIFETIME_BUDGET_DOES_NOT_FIT",
            )
            _require(
                self._authorizer(reg, request, request_sha) is None,
                "AUTHORIZER_RETURN_MUST_BE_NONE",
            )
            _require(not cancellation.is_set(), "CANCELLED_BEFORE_DISPATCH")
            _require(
                self._clock() + required_ns <= deadline_ns,
                "LIFETIME_BUDGET_DOES_NOT_FIT",
            )
            run_deadline = self._clock() + reg.budget.run_timeout_ms * 1_000_000
            if native_campaign_payload is not None:
                run_deadline = min(run_deadline, deadline_ns-reg.budget.cleanup_timeout_ms*1_000_000)

            def before_execution() -> None:
                _require(not cancellation.is_set(), "CANCELLED_BEFORE_DISPATCH")
                _require(self._clock() < run_deadline, "TIMED_OUT")
                # Even frozen dataclasses may be deliberately mutated through
                # object.__setattr__. Never execute changed authority inputs.
                _require(
                    asdict(reg) == reviewed_registration
                    and asdict(request) == reviewed_request,
                    "ADMISSION_INPUT_CHANGED",
                )
                if native_passive_payload is not None:
                    verify_native_passive_entry()
                    _require(self._clock() < run_deadline, "TIMED_OUT")
                if native_powered_payload is not None:
                    verify_native_powered_entry()
                    _require(self._clock() < run_deadline, "TIMED_OUT")
                if native_endpoint_payload is not None:
                    verify_native_endpoint_entry()
                    _require(self._clock() < run_deadline, 'TIMED_OUT')
                if native_first_motion_payload is not None:
                    verify_native_first_motion_entry()
                    _require(self._clock() < run_deadline, 'TIMED_OUT')
                if native_observational_payload is not None:
                    verify_native_observational_entry()
                    _require(self._clock() < run_deadline, 'TIMED_OUT')
                if native_absolute_wrist_payload is not None:
                    verify_native_absolute_wrist_entry()
                    _require(self._clock() < run_deadline, 'TIMED_OUT')
                if native_correction_payload is not None:
                    verify_native_correction_entry()
                    _require(self._clock() < run_deadline, 'TIMED_OUT')
                if native_campaign_payload is not None:
                    verify_native_campaign_entry()
                    _require(self._clock() < run_deadline, 'TIMED_OUT')
                if native_position_vector_payload is not None:
                    from .calibrated_position_vector_owned_protocol import decode_request
                    decode_request(position_vector_wire)
                    _require(self._clock() < run_deadline, "TIMED_OUT")

            native_start_ns = self._clock()
            native.start(reg, wire, check=before_execution)
            while True:
                if cancellation.is_set():
                    raise OwnedWorkerError("CANCELLED")
                if self._clock() >= run_deadline:
                    raise OwnedWorkerError("TIMED_OUT")
                finished = native.poll(reg.budget)
                _require(not cancellation.is_set(), "CANCELLED")
                _require(self._clock() < run_deadline, "TIMED_OUT")
                if finished:
                    break
                cancellation.wait(0.01)
            if camera_payload is None:
                _require(native.returncode == 0, "WORKER_EXIT_FAILED")
            parsed = decode_owned_json(native.stdout, maximum=reg.budget.stdout_bytes)
            if native_campaign_payload is not None:
                from .positional_campaign_native_protocol import decode_result
                parsed = decode_result(native.stdout, request_raw=wire)
            elif native_position_vector_payload is not None:
                from .calibrated_position_vector_owned_protocol import (
                    decode_request,
                    verify_exported_journal,
                )

                parsed = decode_owned_json(native.stdout, maximum=reg.budget.stdout_bytes)
                verify_exported_journal(
                    parsed,
                    wire=decode_request(position_vector_wire),
                    working_directory=reg.working_directory,
                )
            elif native_correction_payload is not None:
                from .wrist_correction_native_result import decode_result
                # Full reconstruction happens only after process cleanup and
                # raw diagnostic retention in the finalization below.
                parsed = decode_result(native.stdout,request_raw=wire)
            elif native_absolute_wrist_payload is not None:
                from .absolute_wrist_native_result import validate_result
                from .absolute_wrist_native_protocol import decode_request, validate_payload
                from rocell.application.absolute_wrist_worker_claim import verify_absolute_wrist_worker_receipt
                summary = validate_result(parsed, wire=decode_request(wire))
                verify_absolute_wrist_worker_receipt(native_absolute_wrist_payload['root'],
                    validate_payload(native_absolute_wrist_payload), claim_sha256=summary['claim_sha256'],
                    launch_sha256=native_absolute_wrist_payload['launch_sha256'], owned_process_id=native.pid,
                    runtime_sha256=hashlib.sha256(_json(native_absolute_wrist_payload['registration'])).hexdigest(),
                    finished_ns=self._clock())
            elif native_observational_payload is not None:
                from .observational_native_result import validate_result
                from .observational_native_protocol import decode_request, validate_payload
                from rocell.application.observational_worker_claim import verify_observational_worker_receipt
                summary = validate_result(parsed, wire=decode_request(wire))
                verify_observational_worker_receipt(native_observational_payload['root'],
                    validate_payload(native_observational_payload), claim_sha256=summary['claim_sha256'],
                    launch_sha256=native_observational_payload['launch_sha256'], owned_process_id=native.pid,
                    runtime_sha256=hashlib.sha256(_json(native_observational_payload['registration'])).hexdigest(),
                    finished_ns=self._clock())
            elif native_first_motion_payload is not None:
                from .first_motion_native_result import validate_result
                from .first_motion_native_protocol import decode_request,validate_payload
                from rocell.application.first_motion_worker_claim import verify_first_motion_worker_receipt
                summary = validate_result(parsed,wire=decode_request(wire))
                verify_first_motion_worker_receipt(native_first_motion_payload['root'],
                    validate_payload(native_first_motion_payload),claim_sha256=summary['claim_sha256'],
                    launch_sha256=native_first_motion_payload['launch_sha256'],owned_process_id=native.pid,
                    runtime_sha256=hashlib.sha256(_json(native_first_motion_payload['registration'])).hexdigest(),
                    finished_ns=self._clock())
            elif native_endpoint_payload is not None:
                from .endpoint_native_result import validate_result
                from .endpoint_native_wire import decode_request
                from rocell.application.endpoint_worker_claim import verify_endpoint_worker_receipt
                from .endpoint_native_registration import validate_payload
                summary = validate_result(parsed,wire=decode_request(wire))
                verify_endpoint_worker_receipt(native_endpoint_payload['root'],
                    validate_payload(native_endpoint_payload),claim_sha256=summary['claim_sha256'],
                    launch_sha256=native_endpoint_payload['launch_sha256'],owned_process_id=native.pid,
                    runtime_sha256=hashlib.sha256(_json(native_endpoint_payload['registration'])).hexdigest(),
                    finished_ns=self._clock())
            elif native_powered_payload is not None:
                from .powered_feedback_native_wire import (
                    decode_request,
                    validate_result,
                )
                from rocell.application.powered_feedback_child_claim import _read

                validate_result(parsed, wire=decode_request(wire))
                claimed, claim_sha = _read(
                    Path(native_powered_payload["root"]), request.attempt_id, "claimed"
                )
                _require(
                    claim_sha == parsed["child_result"]["claim_sha256"]
                    and claimed.get("consumption_sha256")
                    == native_powered_payload["consumption_sha256"]
                    and claimed.get("request_sha256") == request.operation_sha256,
                    "POWERED_CHILD_CLAIM_RESULT_MISMATCH",
                )
            elif native_passive_payload is not None:
                from .passive_native_wire import decode_request, validate_result
                from rocell.application.passive_arm_attempt_store import inspect_attempt

                validate_result(parsed, wire=decode_request(wire))
                claimed = inspect_attempt(
                    Path(native_passive_payload["root"]), request.attempt_id
                )["records"]["claimed"]
                _require(
                    claimed is not None
                    and hashlib.sha256(_json(claimed)).hexdigest()
                    == parsed["child_result"]["claim_sha256"]
                    and claimed["body"].get("consumption_sha256")
                    == native_passive_payload["consumption_sha256"]
                    and claimed["body"].get("request_sha256")
                    == request.operation_sha256,
                    "PASSIVE_CHILD_CLAIM_RESULT_MISMATCH",
                )
            elif powered_rehearsal_payload is not None:
                from .powered_feedback_process_codec import validate_result

                validate_result(
                    parsed,
                    payload=powered_rehearsal_payload,
                    request_sha256=request_sha,
                    attempt_id=request.attempt_id,
                )
            elif passive_payload is not None:
                from .passive_arm_process_codec import validate_result

                validate_result(
                    parsed,
                    payload=passive_payload,
                    request_sha256=request_sha,
                    attempt_id=request.attempt_id,
                )
            elif camera_payload is not None:
                from .owned_camera_codec import validate_camera_result

                validate_camera_result(
                    parsed,
                    payload=camera_payload,
                    request_sha256=request_sha,
                    attempt_id=request.attempt_id,
                    returncode=native.returncode,
                )
                # A valid failed native receipt is retained, not erased by the
                # process exit diagnostic. Device cleanup is still independent.
                if native.returncode != 0:
                    primary = "WORKER_EXIT_FAILED"
            else:
                _require(
                    set(parsed)
                    == {
                        "schema",
                        "request_sha256",
                        "attempt_id",
                        "physical_authority",
                        "fixture_result",
                    }
                    and parsed["schema"] == reg.result_schema
                    and parsed["request_sha256"] == request_sha
                    and parsed["attempt_id"] == request.attempt_id
                    and parsed["physical_authority"] is False
                    and type(parsed["fixture_result"]) is dict
                    and set(parsed["fixture_result"])
                    == {"scenario", "child_pid", "detail"}
                    and parsed["fixture_result"]["scenario"] == reg.argv[3]
                    and type(parsed["fixture_result"]["child_pid"]) is int
                    and 0 <= parsed["fixture_result"]["child_pid"] <= 2**32 - 1
                    and type(parsed["fixture_result"]["detail"]) is str
                    and len(parsed["fixture_result"]["detail"]) <= 128,
                    "RESULT_BINDING_OR_SCHEMA_MISMATCH",
                )
            _require(not cancellation.is_set(), "CANCELLED")
            _require(self._clock() < run_deadline, "TIMED_OUT")
        except BaseException as error:
            primary = (
                str(error) if type(error) is OwnedWorkerError else type(error).__name__
            )
            if isinstance(error, OSError):
                label = error.args[-1] if error.args else "UNKNOWN"
                if type(label) is str and re.fullmatch(r"[A-Za-z0-9_]{1,64}", label):
                    primary = "OS_ERROR:" + label
            parsed = None
        cleanup: tuple[str, ...] = ()
        observed: dict[str, Any] = {}

        def snapshot() -> None:
            if native is None:
                return
            for name, default in (
                ("created", False),
                ("pid", 0),
                ("resumed", False),
                ("tree_exited", False),
                ("returncode", None),
                ("written", 0),
                ("peak_handles", 0),
                ("peak_processes", 0),
                ("stdout", b""),
                ("stderr", b""),
            ):
                try:
                    value = getattr(native, name)
                    valid = (
                        (value is None or type(value) is int)
                        if name == "returncode"
                        else type(value) is type(default)
                    )
                    if valid:
                        observed[name] = value
                except Exception:
                    pass
                observed.setdefault(name, default)

        snapshot()
        if native is not None:
            cleanup_deadline = (
                time.monotonic_ns() + reg.budget.cleanup_timeout_ms * 1_000_000
            )
            if type(deadline_ns) is int and deadline_ns > 0:
                cleanup_deadline = min(cleanup_deadline, deadline_ns)
            try:
                cleanup = native.cleanup(cleanup_deadline)
                if (
                    type(cleanup) is not tuple
                    or len(cleanup) > 256
                    or any(type(code) is not str or len(code) > 128 for code in cleanup)
                ):
                    cleanup = ("INVALID_CLEANUP_RECEIPT",)
            except BaseException as error:
                cleanup = ("CLEANUP_EXCEPTION:" + type(error).__name__,)
            if time.monotonic_ns() > cleanup_deadline:
                cleanup = (*cleanup, "CLEANUP_DEADLINE_EXCEEDED")
            snapshot()
            if cleanup:
                _UNRESOLVED_BACKEND = native
        if primary is None and native is not None:
            if cancellation.is_set():
                primary = "CANCELLED"
            elif self._clock() >= deadline_ns:
                primary = "TIMED_OUT"
        status = "SUCCEEDED" if primary is None and not cleanup else "FAILED"
        if primary in {"CANCELLED", "CANCELLED_BEFORE_DISPATCH"}:
            status = "CANCELLED"
        elif primary == "TIMED_OUT":
            status = "TIMED_OUT"
        try:
            result = OwnedWorkerResult(
                status,
                primary,
                cleanup,
                request_sha,
                getattr(request, "attempt_id", "invalid-request"),
                observed.get("created", False),
                observed.get("resumed", False),
                observed.get("tree_exited", False),
                observed.get("returncode"),
                max(0, self._clock() - started),
                observed.get("written", 0),
                observed.get("peak_handles", 0),
                observed.get("peak_processes", 0),
                observed.get("stdout", b""),
                observed.get("stderr", b""),
                parsed,
                observed.get("pid", 0),
                self._clock(),
            )
            if native_correction_payload is not None and correction_wire is not None:
                from rocell.application.wrist_correction_process_finalization import finalize_correction_process
                from .bench_review_key import load_host_wrist_correction_review_authority
                from .wrist_correction_native_package import CHILD
                try:
                    authority = load_host_wrist_correction_review_authority(CHILD.parents[5])
                except Exception:
                    # Retain original output even if the key is unavailable;
                    # semantic reconstruction will remain held.
                    authority = None
                try:
                    finalized = finalize_correction_process(correction_wire,result,
                        assigned_root=Path(native_correction_payload['root']),authority=authority,
                        process_started_ns=native_start_ns)
                    result = replace(result,parsed_result=finalized)
                except Exception as error:
                    result = replace(result,status='FAILED',
                        primary_error=result.primary_error or 'CORRECTION_FINALIZATION_FAILED',
                        cleanup_errors=(*result.cleanup_errors,'CORRECTION_FINALIZATION:'+type(error).__name__),
                        parsed_result=None)
            return result
        finally:
            if owns_dispatch:
                _DISPATCH_LOCK.release()
