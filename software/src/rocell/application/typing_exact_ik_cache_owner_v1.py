"""Single lifecycle owner for prepared typing resources and exact IK reuse."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from .context import SimulationContext, SimulationContextError
from .context_lifecycle_v1 import (
    SimulationContextLifecycleBindingV1,
    SimulationContextLifecycleV1,
)
from .typing_exact_ik_result_cache_v1 import (
    ExactTypingIkResultCacheV1,
    parse_typing_exact_ik_result_cache_snapshot_v1,
)
from .typing_planner_preparation_v1 import (
    PreparedTypingPlannerV1,
    prepare_typing_planner_v1,
)


SCHEMA = "rocell.typing_exact_ik_cache_owner_snapshot.v1"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_PIPELINE_ARGUMENTS = frozenset({
    "context_lifecycle",
    "prepared_planner",
    "exact_ik_result_cache",
})


class TypingExactIkCacheOwnerV1Error(ValueError):
    """The cache owner is inactive, unready, overridden, or malformed."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingExactIkCacheOwnerV1Error(f"{label} is not a SHA-256 digest")
    return value


class TypingExactIkCacheOwnerV1:
    """Own exactly one lifecycle, prepared planner, and exact-result cache."""

    def __init__(
        self, *, lifecycle: SimulationContextLifecycleV1,
        binding: SimulationContextLifecycleBindingV1,
        prepared_planner: PreparedTypingPlannerV1,
        cache: ExactTypingIkResultCacheV1, maximum_entries: int,
    ) -> None:
        self._lock = RLock()
        self._lifecycle = lifecycle
        self._binding = binding
        self._prepared_planner = prepared_planner
        self._cache = cache
        self._maximum_entries = maximum_entries
        self._active = True
        self._ready = True
        self._runs = 0
        self._run_failures = 0
        self._reloads = 0
        self._restarts = 0
        self._retired_caches = 0
        self._invalidations = 0
        self._refresh_failures = 0

    @classmethod
    def start(
        cls, workspace: Path, manifest_path: Path, *, service_instance_id: str,
        issued_monotonic_ns: int, maximum_entries: int = 256,
    ) -> "TypingExactIkCacheOwnerV1":
        lifecycle = SimulationContextLifecycleV1.start(
            workspace,
            manifest_path,
            service_instance_id=service_instance_id,
            issued_monotonic_ns=issued_monotonic_ns,
        )
        binding = lifecycle.binding()
        prepared = prepare_typing_planner_v1(binding.context, lifecycle)
        cache = ExactTypingIkResultCacheV1.create(
            binding.context, lifecycle, maximum_entries=maximum_entries
        )
        return cls(
            lifecycle=lifecycle,
            binding=binding,
            prepared_planner=prepared,
            cache=cache,
            maximum_entries=maximum_entries,
        )

    def _require_ready(self) -> None:
        if not self._active:
            raise TypingExactIkCacheOwnerV1Error("cache owner is invalidated")
        if not self._ready:
            raise TypingExactIkCacheOwnerV1Error("cache owner is not ready")

    def binding(self) -> SimulationContextLifecycleBindingV1:
        with self._lock:
            self._require_ready()
            binding = self._lifecycle.binding()
            if (
                binding.context is not self._binding.context
                or binding.context_epoch_sha256 != self._binding.context_epoch_sha256
                or binding.service_instance_id != self._binding.service_instance_id
                or binding.generation != self._binding.generation
            ):
                raise SimulationContextError(
                    "cache owner resources differ from the active lifecycle"
                )
            return binding

    @property
    def context(self) -> SimulationContext:
        return self.binding().context

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
                return run_typing_shadow_pipeline_v1(
                    **pipeline_inputs,
                    context_lifecycle=self._lifecycle,
                    prepared_planner=self._prepared_planner,
                    exact_ik_result_cache=self._cache,
                )
            except Exception:
                self._run_failures += 1
                raise

    def _replace_resources(
        self, binding: SimulationContextLifecycleBindingV1,
        *, transition: str,
    ) -> None:
        previous_cache = self._cache
        previous_cache.invalidate()
        self._retired_caches += 1
        self._ready = False
        try:
            prepared = prepare_typing_planner_v1(
                binding.context, self._lifecycle
            )
            cache = ExactTypingIkResultCacheV1.create(
                binding.context,
                self._lifecycle,
                maximum_entries=self._maximum_entries,
            )
        except Exception:
            self._refresh_failures += 1
            raise
        self._binding = binding
        self._prepared_planner = prepared
        self._cache = cache
        self._ready = True
        if transition == "reload":
            self._reloads += 1
        elif transition == "restart":
            self._restarts += 1
        else:
            raise AssertionError("unknown cache-owner transition")

    def reload_sources(
        self, *, issued_monotonic_ns: int,
    ) -> SimulationContextLifecycleBindingV1:
        with self._lock:
            self._require_ready()
            binding = self._lifecycle.reload_sources(
                issued_monotonic_ns=issued_monotonic_ns
            )
            self._replace_resources(binding, transition="reload")
            return binding

    def restart(
        self, *, service_instance_id: str, issued_monotonic_ns: int,
    ) -> SimulationContextLifecycleBindingV1:
        with self._lock:
            self._require_ready()
            lifecycle = self._lifecycle.restart(
                service_instance_id=service_instance_id,
                issued_monotonic_ns=issued_monotonic_ns,
            )
            self._lifecycle = lifecycle
            binding = lifecycle.binding()
            self._replace_resources(binding, transition="restart")
            return binding

    def invalidate(self) -> int:
        with self._lock:
            if self._active:
                self._cache.invalidate()
                self._retired_caches += 1
                generation = self._lifecycle.invalidate()
                self._active = False
                self._ready = False
                self._invalidations += 1
                return generation
            return self._binding.generation + 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            cache_snapshot = self._cache.snapshot()
            core = {
                "schema": SCHEMA,
                "context_epoch_sha256": self._binding.context_epoch_sha256,
                "service_instance_id": self._binding.service_instance_id,
                "generation": self._binding.generation,
                "maximum_entries": self._maximum_entries,
                "active": self._active,
                "ready": self._ready,
                "runs": self._runs,
                "run_failures": self._run_failures,
                "reloads": self._reloads,
                "restarts": self._restarts,
                "retired_caches": self._retired_caches,
                "invalidations": self._invalidations,
                "refresh_failures": self._refresh_failures,
                "cache": cache_snapshot,
                "decision_input": False,
                "timing_used_for_admission": False,
                "controller_commands": [],
                "hardware_commands_generated": 0,
                "hardware_access": False,
                "physical_authority": False,
            }
            return {**core, "owner_snapshot_sha256": _sha(core)}


def parse_typing_exact_ik_cache_owner_snapshot_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    fields = {
        "schema", "context_epoch_sha256", "service_instance_id", "generation",
        "maximum_entries", "active", "ready", "runs", "run_failures",
        "reloads", "restarts", "retired_caches", "invalidations",
        "refresh_failures", "cache", "decision_input",
        "timing_used_for_admission", "controller_commands",
        "hardware_commands_generated", "hardware_access", "physical_authority",
        "owner_snapshot_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingExactIkCacheOwnerV1Error("cache owner snapshot fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("owner_snapshot_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingExactIkCacheOwnerV1Error("cache owner snapshot hash differs")
    if value.get("schema") != SCHEMA:
        raise TypingExactIkCacheOwnerV1Error("cache owner snapshot schema differs")
    _digest(value.get("context_epoch_sha256"), "context epoch")
    service = value.get("service_instance_id")
    if not isinstance(service, str) or not service or len(service) > 192:
        raise TypingExactIkCacheOwnerV1Error("service identity differs")
    for field in (
        "generation", "maximum_entries", "runs", "run_failures", "reloads",
        "restarts", "retired_caches", "invalidations", "refresh_failures",
    ):
        item = value.get(field)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise TypingExactIkCacheOwnerV1Error(f"{field} differs")
    if not 1 <= value["maximum_entries"] <= 4096:
        raise TypingExactIkCacheOwnerV1Error("maximum_entries differs")
    if not isinstance(value.get("active"), bool) or not isinstance(
        value.get("ready"), bool
    ):
        raise TypingExactIkCacheOwnerV1Error("owner state flags differ")
    cache = dict(parse_typing_exact_ik_result_cache_snapshot_v1(value.get("cache")))
    if (
        cache["context_epoch_sha256"] != value["context_epoch_sha256"]
        or cache["service_instance_id"] != value["service_instance_id"]
        or cache["generation"] != value["generation"]
        or cache["maximum_entries"] != value["maximum_entries"]
        or cache["active"] != (value["active"] and value["ready"])
    ):
        raise TypingExactIkCacheOwnerV1Error(
            "cache and owner lifecycle identities differ"
        )
    if (
        value["run_failures"] > value["runs"]
        or value["retired_caches"]
        != (
            value["reloads"] + value["restarts"] + value["invalidations"]
            + value["refresh_failures"]
        )
    ):
        raise TypingExactIkCacheOwnerV1Error("owner counters differ")
    if (
        value.get("decision_input") is not False
        or value.get("timing_used_for_admission") is not False
        or value.get("controller_commands") != []
        or value.get("hardware_commands_generated") != 0
        or value.get("hardware_access") is not False
        or value.get("physical_authority") is not False
    ):
        raise TypingExactIkCacheOwnerV1Error(
            "cache owner snapshot violates zero authority"
        )
    return value


__all__ = [
    "SCHEMA", "TypingExactIkCacheOwnerV1", "TypingExactIkCacheOwnerV1Error",
    "parse_typing_exact_ik_cache_owner_snapshot_v1",
]
