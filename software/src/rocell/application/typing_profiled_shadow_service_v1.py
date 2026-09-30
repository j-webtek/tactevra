"""Profile-gated composition for the zero-authority typing shadow service."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from .typing_exact_ik_cache_owner_v1 import (
    _FORBIDDEN_PIPELINE_ARGUMENTS,
    TypingExactIkCacheOwnerV1,
    TypingExactIkCacheOwnerV1Error,
)
from .typing_ik_reuse_profile_gate_v1 import (
    ELIGIBLE,
    FrozenTypingIkReuseProfileV1,
    evaluate_typing_ik_reuse_profile_v1,
)
from .typing_shadow_service_v1 import TypingShadowServiceV1

SCHEMA = "rocell.typing_profiled_shadow_service_snapshot.v1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class _ProfiledOwner(TypingExactIkCacheOwnerV1):
    """Existing owner with one frozen cache-use decision."""

    def configure_profile(
        self, *, qualified_calibration_snapshot_sha256: str,
        active_calibration_snapshot_sha256: str,
        evidence_sha256: Mapping[str, str],
    ) -> None:
        self._profile_lock = RLock()
        self._qualified_calibration_snapshot_sha256 = (
            qualified_calibration_snapshot_sha256
        )
        self._active_calibration_snapshot_sha256 = (
            active_calibration_snapshot_sha256
        )
        self._evidence_sha256 = dict(evidence_sha256)
        self._profile = FrozenTypingIkReuseProfileV1.from_active_context(
            self.context, self._lifecycle,
            calibration_snapshot_sha256=qualified_calibration_snapshot_sha256,
        )
        self._refresh_profile_decision()

    def _refresh_profile_decision(self) -> None:
        self._profile_decision = evaluate_typing_ik_reuse_profile_v1(
            self._profile, self.context, self._lifecycle,
            calibration_snapshot_sha256=self._active_calibration_snapshot_sha256,
            evidence_sha256=self._evidence_sha256,
            requested_maximum_entries=self._maximum_entries,
            complete_solve_fallback_required=True,
            automatic_retry_allowed=False,
        )

    @property
    def profile_decision(self) -> dict[str, object]:
        with self._profile_lock:
            return dict(self._profile_decision)

    @property
    def exact_reuse_enabled(self) -> bool:
        return self.profile_decision["decision"] == ELIGIBLE

    def run_shadow_pipeline(self, **pipeline_inputs: Any) -> dict[str, Any]:
        overrides = _FORBIDDEN_PIPELINE_ARGUMENTS.intersection(pipeline_inputs)
        if overrides:
            raise TypingExactIkCacheOwnerV1Error(
                "owner-managed pipeline arguments cannot be overridden"
            )
        with self._lock:
            self._require_ready()
            self.binding()
            self._runs += 1
            try:
                from .typing_shadow_pipeline_v1 import run_typing_shadow_pipeline_v1
                cache = self._cache if self.exact_reuse_enabled else None
                return run_typing_shadow_pipeline_v1(
                    **pipeline_inputs,
                    context_lifecycle=self._lifecycle,
                    prepared_planner=self._prepared_planner,
                    exact_ik_result_cache=cache,
                )
            except Exception:
                self._run_failures += 1
                raise

    def reload_sources(self, *, issued_monotonic_ns: int):
        binding = super().reload_sources(issued_monotonic_ns=issued_monotonic_ns)
        with self._profile_lock:
            self._refresh_profile_decision()
        return binding

    def restart(self, *, service_instance_id: str, issued_monotonic_ns: int):
        binding = super().restart(
            service_instance_id=service_instance_id,
            issued_monotonic_ns=issued_monotonic_ns,
        )
        with self._profile_lock:
            self._refresh_profile_decision()
        return binding


class TypingProfiledShadowServiceV1:
    """Compose gate, owner, and FIFO service without execution authority."""

    def __init__(self, owner: _ProfiledOwner, service: TypingShadowServiceV1):
        self._owner = owner
        self._service = service

    @classmethod
    def start(
        cls, workspace: Path, manifest_path: Path, *, service_instance_id: str,
        issued_monotonic_ns: int,
        qualified_calibration_snapshot_sha256: str,
        active_calibration_snapshot_sha256: str,
        evidence_sha256: Mapping[str, str], maximum_entries: int = 256,
        maximum_queued: int = 32, maximum_requests: int = 4096,
    ) -> "TypingProfiledShadowServiceV1":
        owner = _ProfiledOwner.start(
            workspace, manifest_path, service_instance_id=service_instance_id,
            issued_monotonic_ns=issued_monotonic_ns,
            maximum_entries=maximum_entries,
        )
        owner.configure_profile(
            qualified_calibration_snapshot_sha256=(
                qualified_calibration_snapshot_sha256
            ),
            active_calibration_snapshot_sha256=active_calibration_snapshot_sha256,
            evidence_sha256=evidence_sha256,
        )
        service = TypingShadowServiceV1(
            owner, maximum_queued=maximum_queued,
            maximum_requests=maximum_requests,
        )
        return cls(owner, service)

    @property
    def context(self):
        return self._service.context

    @property
    def exact_reuse_enabled(self) -> bool:
        return self._owner.exact_reuse_enabled

    def submit(self, request_id: str, pipeline_inputs: Mapping[str, Any]) -> str:
        return self._service.submit(request_id, pipeline_inputs)

    def execute_next(self) -> dict[str, Any]:
        return self._service.execute_next()

    def cancel(self, request_id: str) -> dict[str, Any]:
        return self._service.cancel(request_id)

    def shadow_artifact(self, request_id: str, expected_sha256: str):
        return self._service.shadow_artifact(request_id, expected_sha256)

    def artifact_store_snapshot(self):
        return self._service.artifact_store_snapshot()

    def reload_sources(self, *, issued_monotonic_ns: int) -> None:
        self._service.reload_sources(issued_monotonic_ns=issued_monotonic_ns)

    def restart(self, *, service_instance_id: str, issued_monotonic_ns: int) -> None:
        self._service.restart(
            service_instance_id=service_instance_id,
            issued_monotonic_ns=issued_monotonic_ns,
        )

    def invalidate(self) -> None:
        self._service.invalidate()

    def snapshot(self) -> dict[str, object]:
        decision = self._owner.profile_decision
        service = self._service.snapshot()
        owner = self._owner.snapshot()
        core = {
            "schema": SCHEMA,
            "profile_decision": decision["decision"],
            "profile_decision_sha256": decision["decision_sha256"],
            "exact_reuse_enabled": self.exact_reuse_enabled,
            "complete_solve_fallback_required": True,
            "automatic_retry_allowed": False,
            "service_snapshot_sha256": service["service_snapshot_sha256"],
            "owner_snapshot_sha256": owner["owner_snapshot_sha256"],
            "cache_counters": {
                name: owner["cache"][name]
                for name in ("lookups", "hits", "misses", "stores", "capacity_skips")
            },
            "executor_attached": False,
            "controller_opened": False,
            "transport_opened": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "physical_authority": False,
        }
        return {**core, "profiled_service_snapshot_sha256": _sha(core)}


__all__ = ["SCHEMA", "TypingProfiledShadowServiceV1"]
