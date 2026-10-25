"""Exact owned-process registration for one position-vector feedback query."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

from .calibrated_position_vector_owned_protocol import (
    REQUEST_SCHEMA,
    RESULT_SCHEMA,
    WORKER_ID,
    canonical,
    validate_payload,
)
from .owned_worker_process import (
    OwnedWorkerRequest,
    WorkerProcessBudget,
    WorkerProcessRegistration,
    decode_owned_json,
    owned_registration_document,
)


def fixed_budget() -> WorkerProcessBudget:
    return WorkerProcessBudget(
        run_timeout_ms=10_000,
        cleanup_timeout_ms=2_000,
        stdin_bytes=65_536,
        stdout_bytes=256 * 1024,
        stderr_bytes=8_192,
        process_count=1,
    )


def validate_registration(
    registration: WorkerProcessRegistration, outer: OwnedWorkerRequest
) -> dict:
    from .calibrated_position_vector_native_package import CHILD, expected_archive
    from .owned_arm_feedback_package import MAX_FILE_BYTES, _read

    if type(registration) is not WorkerProcessRegistration or type(outer) is not OwnedWorkerRequest:
        raise ValueError("exact registration and request types required")
    registration.__post_init__()
    outer.__post_init__()
    payload = decode_owned_json(outer.payload_json, maximum=60 * 1024)
    payload, binding = validate_payload(payload)
    request = binding.request
    directory = Path(payload["root"]) / (request["attempt_id"] + "-position-vector-child")
    if not (
        registration.worker_id == WORKER_ID
        and registration.composition == "PHYSICAL_UNQUALIFIED"
        and registration.request_schema == REQUEST_SCHEMA
        and registration.result_schema == RESULT_SCHEMA
        and registration.working_directory == directory
        and registration.budget == fixed_budget()
    ):
        raise ValueError("position-vector registration domain changed")
    executable = registration.executable
    if not (
        executable.path == Path(getattr(sys, "_base_executable", sys.executable))
        and executable.sha256
        == hashlib.sha256(_read(executable.path, executable.maximum_bytes)).hexdigest()
    ):
        raise ValueError("position-vector interpreter changed")
    pins = registration.package_files
    if not (
        len(pins) == 2
        and pins[0].path == CHILD
        and pins[1].path == directory / "calibrated-position-vector-native.zip"
        and registration.argv
        == ("-I", "-S", str(CHILD), str(pins[1].path), pins[1].sha256, "execute-one")
        and pins[0].sha256 == hashlib.sha256(_read(CHILD, MAX_FILE_BYTES)).hexdigest()
        and pins[1].sha256 == hashlib.sha256(expected_archive()).hexdigest()
        and hashlib.sha256(_read(pins[1].path, pins[1].maximum_bytes)).hexdigest()
        == pins[1].sha256
    ):
        raise ValueError("position-vector child package changed")
    if canonical(payload["registration"]) != canonical(owned_registration_document(registration)):
        raise ValueError("position-vector registration original changed")
    if not (
        outer.attempt_id == request["attempt_id"]
        and outer.session_id == request["runtime_session_id"]
        and outer.source_sha256 == payload["source_sha256"]
        and outer.operation_sha256 == binding.binding_sha256
        and outer.selected_identity_sha256 == binding.identity.identity_sha256
        and outer.expires_at_ns == binding.expires_monotonic_ns
    ):
        raise ValueError("position-vector outer request mismatch")
    return payload


__all__ = ["fixed_budget", "validate_registration"]
