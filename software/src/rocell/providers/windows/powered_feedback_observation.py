"""One T105 rehearsal using the production non-purging serial lifecycle.

Rehearsal and physical entry points require distinct exact APIs and provenance.
Physical entry requires a live-claim-admitted facade; the source-pinned supervisor
must independently admit the runtime before invoking this lifecycle.
"""

import base64
import hashlib
import time
from threading import Event

from rocell.application.physical_connection_contracts import EvidenceOrigin
from rocell.arm.feedback_profile import (
    Feedback1051Profile,
    classify_feedback_1051_profile,
)
from rocell.arm.feedback_wire import validate_feedback_response_line
from .nonpurging_serial_api import IncapableWin32SerialApi
from .nonpurging_serial_backend import NonPurgingSerialConnection
from .powered_feedback_binding import PoweredFeedbackBinding


def observe_rehearsal(binding, api, cancellation):
    if (
        type(binding) is not PoweredFeedbackBinding
        or type(api) is not IncapableWin32SerialApi
        or type(cancellation) is not Event
        or binding.origin is not EvidenceOrigin.SYNTHETIC_REHEARSAL
        or binding.intent.to_dict()["mode"] != "rehearsal"
    ):
        raise ValueError("Exact hardware-incapable powered-feedback rehearsal required")
    return _observe(binding, api, cancellation)


def observe_physical(binding, api, cancellation):
    from .powered_feedback_serial_api import WindowsPoweredFeedbackSerialApi

    if (
        type(binding) is not PoweredFeedbackBinding
        or type(api) is not WindowsPoweredFeedbackSerialApi
        or type(cancellation) is not Event
        or binding.origin is not EvidenceOrigin.PHYSICAL_OBSERVATION
        or binding.intent.to_dict()["mode"] != "physical"
        or api.admitted_request_sha256 != binding.intent.request_sha256
    ):
        raise ValueError("Exact live-claim-admitted powered feedback required")
    return _observe(binding, api, cancellation)


def _observe(binding, api, cancellation):
    binding.__post_init__()
    intent = binding.intent
    from rocell.application.powered_arm_feedback_contract import PURPOSE
    if intent.to_dict()["purpose"] != PURPOSE:
        raise ValueError("Query lifecycle requires a query-purpose intent")
    started = time.monotonic_ns()
    intent.require_time_available(started)
    limits = intent.to_dict()["limits"]
    deadline = started + limits["observation_timeout_ms"] * 1_000_000
    owner = NonPurgingSerialConnection(binding, api=api)
    startup, response = bytearray(), bytearray()
    errors, feedback = [], None
    reads = 0

    def check_time():
        if cancellation.is_set():
            raise RuntimeError("CANCELLED")
        if time.monotonic_ns() >= deadline:
            raise RuntimeError("FEEDBACK_DEADLINE_EXCEEDED")

    def retain(target, maximum):
        nonlocal reads
        count = owner.in_waiting
        while count:
            check_time()
            if reads >= limits["maximum_read_calls"] or len(target) >= maximum:
                raise RuntimeError("FEEDBACK_INPUT_LIMIT")
            reads += 1
            block = owner.read(min(count, 256, maximum - len(target)), timeout_ms=100)
            target.extend(block)
            count = owner.in_waiting

    def quiet(target, maximum):
        until = time.monotonic_ns() + limits["quiet_interval_ms"] * 1_000_000
        while True:
            check_time()
            retain(target, maximum)
            if target:
                raise RuntimeError(
                    "PREEXISTING_INPUT" if target is startup else "EXTRA_RESPONSE_INPUT"
                )
            if time.monotonic_ns() >= until:
                return
            cancellation.wait(0.01)

    try:
        check_time()
        owner.open()
        # Never flush startup input: preserve it and reject the attempt before
        # writing. T1051 has no transaction ID to distinguish an old reply.
        quiet(startup, limits["maximum_startup_bytes"])
        check_time()
        owner.write(intent.outbound_line)
        while not response.endswith(b"\n"):
            check_time()
            retain(response, limits["maximum_response_bytes"])
            if response.count(b"\n") > 1:
                raise RuntimeError("MULTIPLE_RESPONSE_LINES")
            if not response.endswith(b"\n"):
                cancellation.wait(0.01)
        feedback = validate_feedback_response_line(
            bytes(response), max_line_bytes=limits["maximum_response_bytes"]
        )
        profile = classify_feedback_1051_profile(feedback)
        if profile is not Feedback1051Profile.FULL_WAVESHARE:
            raise RuntimeError(
                "INSTALLED_POSITION_VECTOR_FEEDBACK_PROFILE"
                if profile is Feedback1051Profile.POSITION_VECTOR_NAMED_POSE
                else "INCOMPLETE_POWERED_FEEDBACK"
            )
        extra = bytearray()
        try:
            # A second packet makes this single-response observation ambiguous.
            # A quiet interval reduces ambiguity; it cannot prove causality.
            quiet(extra, limits["maximum_response_bytes"] - len(response))
        finally:
            response.extend(extra)
    except Exception as error:
        code = getattr(error, "code", None)
        if code is None:
            code = getattr(getattr(error, "failure", None), "value", None)
        errors.append(
            code
            or (str(error) if type(error) is RuntimeError else type(error).__name__)
        )
        feedback = None
    finally:
        observation_finished = time.monotonic_ns()
        try:
            owner.close()
        except Exception as error:
            errors.append(getattr(error, "code", type(error).__name__))
    finished = time.monotonic_ns()
    lifecycle = owner.status()
    if finished - observation_finished > limits["cleanup_timeout_ms"] * 1_000_000:
        errors.append("CLEANUP_DEADLINE_EXCEEDED")
    if not lifecycle["cleanup_confirmed"]:
        errors.append("CLEANUP_UNKNOWN")
    if finished > intent.to_dict()["parent_deadline_monotonic_ns"]:
        errors.append("PARENT_DEADLINE_EXCEEDED")

    def blob(raw):
        return {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "base64": base64.b64encode(raw).decode("ascii"),
        }

    return {
        "schema": "rocell.powered_feedback_observation.v1",
        "origin": binding.origin.value,
        "request_sha256": intent.request_sha256,
        "status": (
            "FEEDBACK_OBSERVED_CLOSED"
            if feedback is not None and not errors
            else "FAILED"
        ),
        "errors": errors,
        "feedback": feedback,
        "startup": blob(startup),
        "response": blob(response),
        "late_cleanup_input": blob(owner.late_read_bytes),
        "lifecycle": lifecycle,
        "started_monotonic_ns": started,
        "observation_finished_monotonic_ns": observation_finished,
        "finished_monotonic_ns": finished,
        "physical_authority": False,
        "connected": False,
        "motion_authorized": False,
    }
