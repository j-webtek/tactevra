"""Lifecycle supervisor for the zero-authority profiled typing service."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from .typing_profiled_shadow_service_v1 import TypingProfiledShadowServiceV1

SCHEMA = "rocell.typing_runtime_supervisor_snapshot.v1"
WARM = "WARM"
FULL_SOLVE_ONLY = "FULL_SOLVE_ONLY"
REQUALIFICATION_REQUIRED = "REQUALIFICATION_REQUIRED"
STATES = frozenset({WARM, FULL_SOLVE_ONLY, REQUALIFICATION_REQUIRED})


class TypingRuntimeSupervisorV1Error(ValueError):
    """Supervisor state or transition is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class TypingRuntimeSupervisorV1:
    """Make fast-path eligibility and lifecycle demotion explicit."""

    def __init__(self, service: TypingProfiledShadowServiceV1) -> None:
        if not isinstance(service, TypingProfiledShadowServiceV1):
            raise TypeError("service must be TypingProfiledShadowServiceV1")
        self._lock = RLock()
        self._service = service
        self._active = True
        self._state = WARM if service.exact_reuse_enabled else FULL_SOLVE_ONLY
        self._state_reason = (
            "QUALIFIED_PROFILE" if self._state == WARM
            else "STARTUP_PROFILE_MISMATCH"
        )
        self._transitions = 0
        self._submission_rejections = 0
        self._full_solve_continuations = 0

    @classmethod
    def start(
        cls, workspace: Path, manifest_path: Path, *, service_instance_id: str,
        issued_monotonic_ns: int,
        qualified_calibration_snapshot_sha256: str,
        active_calibration_snapshot_sha256: str,
        evidence_sha256: Mapping[str, str], maximum_entries: int = 256,
        maximum_queued: int = 32, maximum_requests: int = 4096,
    ) -> "TypingRuntimeSupervisorV1":
        return cls(TypingProfiledShadowServiceV1.start(
            workspace, manifest_path,
            service_instance_id=service_instance_id,
            issued_monotonic_ns=issued_monotonic_ns,
            qualified_calibration_snapshot_sha256=(
                qualified_calibration_snapshot_sha256
            ),
            active_calibration_snapshot_sha256=(
                active_calibration_snapshot_sha256
            ),
            evidence_sha256=evidence_sha256,
            maximum_entries=maximum_entries,
            maximum_queued=maximum_queued,
            maximum_requests=maximum_requests,
        ))

    @property
    def context(self):
        with self._lock:
            self._require_active()
            return self._service.context

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def exact_reuse_enabled(self) -> bool:
        with self._lock:
            return self._state == WARM and self._service.exact_reuse_enabled

    def _require_active(self) -> None:
        if not self._active:
            raise TypingRuntimeSupervisorV1Error("supervisor is invalidated")

    def _transition(self, state: str, reason: str) -> None:
        if state not in STATES:
            raise TypingRuntimeSupervisorV1Error("supervisor state differs")
        self._state = state
        self._state_reason = reason
        self._transitions += 1

    def submit(self, request_id: str, pipeline_inputs: Mapping[str, Any]) -> str:
        with self._lock:
            self._require_active()
            if self._state == REQUALIFICATION_REQUIRED:
                self._submission_rejections += 1
                raise TypingRuntimeSupervisorV1Error(
                    "requalification required before submission"
                )
            if self._state == WARM and not self._service.exact_reuse_enabled:
                self._transition(REQUALIFICATION_REQUIRED, "PROFILE_ELIGIBILITY_LOST")
                self._submission_rejections += 1
                raise TypingRuntimeSupervisorV1Error(
                    "requalification required before submission"
                )
            return self._service.submit(request_id, pipeline_inputs)

    def execute_next(self) -> dict[str, Any]:
        with self._lock:
            self._require_active()
            return self._service.execute_next()

    def cancel(self, request_id: str) -> dict[str, Any]:
        with self._lock:
            self._require_active()
            return self._service.cancel(request_id)

    def reload_sources(self, *, issued_monotonic_ns: int) -> None:
        with self._lock:
            self._require_active()
            self._service.reload_sources(issued_monotonic_ns=issued_monotonic_ns)
            self._transition(REQUALIFICATION_REQUIRED, "SOURCES_RELOADED")

    def restart(self, *, service_instance_id: str, issued_monotonic_ns: int) -> None:
        with self._lock:
            self._require_active()
            self._service.restart(
                service_instance_id=service_instance_id,
                issued_monotonic_ns=issued_monotonic_ns,
            )
            self._transition(REQUALIFICATION_REQUIRED, "SERVICE_RESTARTED")

    def continue_full_solve_only(self) -> None:
        with self._lock:
            self._require_active()
            if self._state != REQUALIFICATION_REQUIRED:
                raise TypingRuntimeSupervisorV1Error(
                    "full-solve continuation requires requalification state"
                )
            if self._service.exact_reuse_enabled:
                raise TypingRuntimeSupervisorV1Error(
                    "full-solve continuation cannot retain exact reuse"
                )
            self._full_solve_continuations += 1
            self._transition(FULL_SOLVE_ONLY, "EXPLICIT_FULL_SOLVE_CONTINUATION")

    def invalidate(self) -> None:
        with self._lock:
            if self._active:
                self._service.invalidate()
                self._active = False
                self._transition(REQUALIFICATION_REQUIRED, "INVALIDATED")

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            service = self._service.snapshot()
            core = {
                "schema": SCHEMA,
                "active": self._active,
                "state": self._state,
                "state_reason": self._state_reason,
                "transitions": self._transitions,
                "submission_rejections": self._submission_rejections,
                "full_solve_continuations": self._full_solve_continuations,
                "exact_reuse_enabled": self.exact_reuse_enabled,
                "profile_decision": service["profile_decision"],
                "profile_decision_sha256": service["profile_decision_sha256"],
                "service_snapshot_sha256": service[
                    "profiled_service_snapshot_sha256"
                ],
                "cache_counters": dict(service["cache_counters"]),
                "complete_solve_fallback_required": True,
                "automatic_retry_allowed": False,
                "executor_attached": False,
                "controller_opened": False,
                "transport_opened": False,
                "controller_commands": [],
                "hardware_writes": 0,
                "physical_movements": 0,
                "physical_authority": False,
            }
            return {**core, "supervisor_snapshot_sha256": _sha(core)}


def parse_typing_runtime_supervisor_snapshot_v1(value: Mapping[str, object]):
    fields = {"schema", "active", "state", "state_reason", "transitions",
              "submission_rejections", "full_solve_continuations",
              "exact_reuse_enabled", "profile_decision",
              "profile_decision_sha256", "service_snapshot_sha256",
              "cache_counters",
              "complete_solve_fallback_required", "automatic_retry_allowed",
              "executor_attached", "controller_opened", "transport_opened",
              "controller_commands", "hardware_writes", "physical_movements",
              "physical_authority", "supervisor_snapshot_sha256"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingRuntimeSupervisorV1Error("supervisor snapshot fields differ")
    unsigned = dict(value); supplied = unsigned.pop("supervisor_snapshot_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingRuntimeSupervisorV1Error("supervisor snapshot hash differs")
    if (value["schema"] != SCHEMA or value["state"] not in STATES
            or not isinstance(value["active"], bool)
            or not isinstance(value["state_reason"], str)
            or not value["state_reason"]):
        raise TypingRuntimeSupervisorV1Error("supervisor snapshot identity differs")
    for field in ("transitions", "submission_rejections", "full_solve_continuations",
                  "hardware_writes", "physical_movements"):
        item = value[field]
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise TypingRuntimeSupervisorV1Error("supervisor counters differ")
    counters = value["cache_counters"]
    counter_fields = {"lookups", "hits", "misses", "stores", "capacity_skips"}
    if (not isinstance(counters, Mapping) or set(counters) != counter_fields
            or any(isinstance(item, bool) or not isinstance(item, int) or item < 0
                   for item in counters.values())
            or counters["lookups"] != counters["hits"] + counters["misses"]):
        raise TypingRuntimeSupervisorV1Error("supervisor cache counters differ")
    if value["exact_reuse_enabled"] is not (value["state"] == WARM):
        raise TypingRuntimeSupervisorV1Error("supervisor reuse state differs")
    if (value["complete_solve_fallback_required"] is not True
            or value["automatic_retry_allowed"] is not False
            or value["executor_attached"] is not False
            or value["controller_opened"] is not False
            or value["transport_opened"] is not False
            or value["controller_commands"] != []
            or value["hardware_writes"] != 0
            or value["physical_movements"] != 0
            or value["physical_authority"] is not False):
        raise TypingRuntimeSupervisorV1Error("supervisor authority differs")
    return value


__all__ = ["SCHEMA", "WARM", "FULL_SOLVE_ONLY", "REQUALIFICATION_REQUIRED",
           "STATES", "TypingRuntimeSupervisorV1",
           "TypingRuntimeSupervisorV1Error",
           "parse_typing_runtime_supervisor_snapshot_v1"]
