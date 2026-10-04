"""Bounded lifecycle-scoped exact-result cache for offline typing IK."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from threading import RLock
from typing import Any, Mapping

from rocell.kinematics import IkResult

from .context import SimulationContext, SimulationContextError
from .context_lifecycle_v1 import (
    SimulationContextLifecycleBindingV1,
    SimulationContextLifecycleV1,
)


SCHEMA = "rocell.typing_exact_ik_result_cache_snapshot.v1"
_HASH = re.compile(r"^[0-9a-f]{64}$")


class TypingExactIkResultCacheV1Error(ValueError):
    """Cache state is stale, corrupt, unbounded, or authoritative."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingExactIkResultCacheV1Error(f"{label} is not a SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True)
class _Entry:
    result: IkResult
    result_sha256: str


class ExactTypingIkResultCacheV1:
    """Cache exact deterministic results within one active context generation."""

    def __init__(
        self, *, context: SimulationContext, context_epoch_sha256: str,
        service_instance_id: str, generation: int, maximum_entries: int,
    ) -> None:
        if (
            isinstance(maximum_entries, bool)
            or not isinstance(maximum_entries, int)
            or not 1 <= maximum_entries <= 4096
        ):
            raise TypingExactIkResultCacheV1Error(
                "maximum_entries must be in [1, 4096]"
            )
        self._lock = RLock()
        self._context = context
        self._context_epoch_sha256 = _digest(
            context_epoch_sha256, "context epoch"
        )
        self._service_instance_id = service_instance_id
        self._generation = generation
        self._maximum_entries = maximum_entries
        self._entries: dict[str, _Entry] = {}
        self._active = True
        self._lookups = 0
        self._hits = 0
        self._misses = 0
        self._stores = 0
        self._capacity_skips = 0

    @classmethod
    def create(
        cls, context: SimulationContext, lifecycle: SimulationContextLifecycleV1,
        *, maximum_entries: int = 256,
    ) -> "ExactTypingIkResultCacheV1":
        if not isinstance(lifecycle, SimulationContextLifecycleV1):
            raise TypeError("lifecycle must be SimulationContextLifecycleV1")
        with lifecycle.validation_scope(context) as binding:
            return cls(
                context=binding.context,
                context_epoch_sha256=binding.context_epoch_sha256,
                service_instance_id=binding.service_instance_id,
                generation=binding.generation,
                maximum_entries=maximum_entries,
            )

    def _validate(self, binding: SimulationContextLifecycleBindingV1) -> None:
        if not isinstance(binding, SimulationContextLifecycleBindingV1):
            raise TypeError("binding must be SimulationContextLifecycleBindingV1")
        if not self._active:
            raise TypingExactIkResultCacheV1Error("IK cache is invalidated")
        if self._context is not binding.context:
            raise SimulationContextError("IK cache belongs to a different context")
        if (
            self._context_epoch_sha256 != binding.context_epoch_sha256
            or self._service_instance_id != binding.service_instance_id
            or self._generation != binding.generation
        ):
            raise SimulationContextError("IK cache lifecycle binding is stale")

    def lookup(
        self, solver_input_sha256: str,
        binding: SimulationContextLifecycleBindingV1,
    ) -> IkResult | None:
        key = _digest(solver_input_sha256, "solver input")
        with self._lock:
            self._validate(binding)
            self._lookups += 1
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            if not isinstance(entry.result, IkResult):
                raise TypingExactIkResultCacheV1Error(
                    "cached IK result has the wrong type"
                )
            if _sha(entry.result.to_dict()) != entry.result_sha256:
                raise TypingExactIkResultCacheV1Error(
                    "cached IK result integrity differs"
                )
            self._hits += 1
            return entry.result

    def remember(
        self, solver_input_sha256: str, result: IkResult,
        binding: SimulationContextLifecycleBindingV1,
    ) -> bool:
        key = _digest(solver_input_sha256, "solver input")
        if not isinstance(result, IkResult):
            raise TypeError("result must be an IkResult")
        result_sha256 = _sha(result.to_dict())
        with self._lock:
            self._validate(binding)
            existing = self._entries.get(key)
            if existing is not None:
                if existing.result_sha256 != result_sha256:
                    raise TypingExactIkResultCacheV1Error(
                        "same solver input produced a different IK result"
                    )
                return False
            if len(self._entries) >= self._maximum_entries:
                self._capacity_skips += 1
                return False
            self._entries[key] = _Entry(result=result, result_sha256=result_sha256)
            self._stores += 1
            return True

    def invalidate(self) -> None:
        with self._lock:
            self._entries.clear()
            self._active = False

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            core = {
                "schema": SCHEMA,
                "context_epoch_sha256": self._context_epoch_sha256,
                "service_instance_id": self._service_instance_id,
                "generation": self._generation,
                "maximum_entries": self._maximum_entries,
                "entry_count": len(self._entries),
                "active": self._active,
                "lookups": self._lookups,
                "hits": self._hits,
                "misses": self._misses,
                "stores": self._stores,
                "capacity_skips": self._capacity_skips,
                "decision_input": False,
                "timing_used_for_admission": False,
                "controller_commands": [],
                "hardware_commands_generated": 0,
                "hardware_access": False,
                "physical_authority": False,
            }
            return {**core, "cache_snapshot_sha256": _sha(core)}


def parse_typing_exact_ik_result_cache_snapshot_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    fields = {
        "schema", "context_epoch_sha256", "service_instance_id", "generation",
        "maximum_entries", "entry_count", "active", "lookups", "hits",
        "misses", "stores", "capacity_skips", "decision_input",
        "timing_used_for_admission", "controller_commands",
        "hardware_commands_generated", "hardware_access", "physical_authority",
        "cache_snapshot_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingExactIkResultCacheV1Error("cache snapshot fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("cache_snapshot_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingExactIkResultCacheV1Error("cache snapshot hash differs")
    if value.get("schema") != SCHEMA:
        raise TypingExactIkResultCacheV1Error("cache snapshot schema differs")
    _digest(value.get("context_epoch_sha256"), "context epoch")
    for field in (
        "generation", "maximum_entries", "entry_count", "lookups", "hits",
        "misses", "stores", "capacity_skips",
    ):
        item = value.get(field)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise TypingExactIkResultCacheV1Error(f"{field} is invalid")
    if (
        not 1 <= value["maximum_entries"] <= 4096
        or value["entry_count"] > value["maximum_entries"]
        or value["lookups"] != value["hits"] + value["misses"]
        or value["stores"] < value["entry_count"]
    ):
        raise TypingExactIkResultCacheV1Error("cache counters differ")
    if not isinstance(value.get("active"), bool):
        raise TypingExactIkResultCacheV1Error("active must be boolean")
    service = value.get("service_instance_id")
    if not isinstance(service, str) or not service or len(service) > 192:
        raise TypingExactIkResultCacheV1Error("service identity is invalid")
    if (
        value.get("decision_input") is not False
        or value.get("timing_used_for_admission") is not False
        or value.get("controller_commands") != []
        or value.get("hardware_commands_generated") != 0
        or value.get("hardware_access") is not False
        or value.get("physical_authority") is not False
    ):
        raise TypingExactIkResultCacheV1Error("cache snapshot violates zero authority")
    return value


__all__ = [
    "SCHEMA", "ExactTypingIkResultCacheV1", "TypingExactIkResultCacheV1Error",
    "parse_typing_exact_ik_result_cache_snapshot_v1",
]
