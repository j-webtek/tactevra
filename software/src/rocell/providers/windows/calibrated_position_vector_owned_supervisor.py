"""Inert staging for the source-pinned position-vector owned child."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys

from .arm_feedback_worker import ReviewedControllerBinding
from .calibrated_position_vector_binding import CalibratedPositionVectorBinding
from .calibrated_position_vector_native_package import CHILD, prepare
from .calibrated_position_vector_native_registration import fixed_budget
from .calibrated_position_vector_owned_protocol import (
    PAYLOAD_SCHEMA,
    REQUEST_SCHEMA,
    RESULT_SCHEMA,
    WORKER_ID,
    binding_document,
    canonical,
    decode_request,
)
from .owned_worker_process import (
    OwnedWorkerRequest,
    PinnedWorkerFile,
    WorkerProcessRegistration,
    owned_registration_document,
    owned_request_wire,
)


@dataclass(frozen=True, slots=True)
class StagedCalibratedPositionVectorWorker:
    registration: WorkerProcessRegistration
    request: OwnedWorkerRequest
    wire: bytes
    binding: CalibratedPositionVectorBinding
    working_directory: Path


def _pin(path: Path) -> PinnedWorkerFile:
    raw = path.read_bytes()
    return PinnedWorkerFile(path, hashlib.sha256(raw).hexdigest())


def stage_calibrated_position_vector_worker(
    root: Path,
    *,
    reviewed_controller: ReviewedControllerBinding,
    fresh_identity,
    request,
    controller_binding,
    installed_firmware_sha256: str,
    source_sha256: str,
    expires_monotonic_ns: int,
) -> StagedCalibratedPositionVectorWorker:
    """Create exact child files and wire without starting a process or device."""

    base = Path(root)
    if not base.is_absolute() or base.is_symlink() or not base.is_dir():
        raise ValueError("existing absolute nonsymlink staging root required")
    attempt_id = request.get("attempt_id") if type(request) is dict else None
    if type(attempt_id) is not str:
        raise ValueError("position-vector attempt id required")
    working = base.resolve() / (attempt_id + "-position-vector-child")
    working.mkdir()
    (working / "journals").mkdir()
    (working / "exports").mkdir()
    archive = prepare(working)
    executable = Path(getattr(sys, "_base_executable", sys.executable))
    archive_pin = _pin(archive)
    registration = WorkerProcessRegistration(
        WORKER_ID,
        _pin(executable),
        ("-I", "-S", str(CHILD), str(archive), archive_pin.sha256, "execute-one"),
        (_pin(CHILD), archive_pin),
        working,
        fixed_budget(),
        "PHYSICAL_UNQUALIFIED",
        REQUEST_SCHEMA,
        RESULT_SCHEMA,
    )
    registration_document = owned_registration_document(registration)
    runtime_sha256 = hashlib.sha256(canonical(registration_document)).hexdigest()
    binding = CalibratedPositionVectorBinding(
        reviewed_controller,
        fresh_identity,
        request,
        controller_binding,
        installed_firmware_sha256,
        runtime_sha256,
        expires_monotonic_ns,
    )
    payload = {
        "schema": PAYLOAD_SCHEMA,
        "root": str(base.resolve()),
        "source_sha256": source_sha256,
        "binding": binding_document(binding),
        "registration": registration_document,
    }
    outer = OwnedWorkerRequest(
        binding.request["attempt_id"],
        binding.request["runtime_session_id"],
        source_sha256,
        binding.binding_sha256,
        binding.identity.identity_sha256,
        expires_monotonic_ns,
        canonical(payload),
    )
    wire, digest = owned_request_wire(registration, outer, deadline_ns=expires_monotonic_ns)
    if decode_request(wire)["request_sha256"] != digest:
        raise ValueError("position-vector wire digest changed")
    return StagedCalibratedPositionVectorWorker(registration, outer, wire, binding, working)


__all__ = ["StagedCalibratedPositionVectorWorker", "stage_calibrated_position_vector_worker"]
