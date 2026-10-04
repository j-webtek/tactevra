"""Lifecycle-bound, decision-neutral verification of endpoint-result reuse."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import re
from threading import RLock
from typing import Any, Mapping

from rocell.kinematics import ARM_JOINT_NAMES

from .context import SimulationContext, SimulationContextError
from .context_lifecycle_v1 import (
    SimulationContextLifecycleBindingV1,
    SimulationContextLifecycleV1,
)
from .trajectory_simulation import JointTrajectoryWaypointResult
from .typing_trajectory_plan_v1 import TypingScreeningSampleV1


SCHEMA = "rocell.typing_endpoint_reuse_verifier_snapshot.v1"
_HASH = re.compile(r"^[0-9a-f]{64}$")


class TypingEndpointReuseVerifierV1Error(ValueError):
    """Endpoint reuse evidence is stale, corrupt, inconsistent, or authoritative."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingEndpointReuseVerifierV1Error(
            f"{label} is not a SHA-256 digest"
        )
    return value


def _joint_state(value: Mapping[str, float]) -> dict[str, float]:
    if not isinstance(value, Mapping) or tuple(value) != ARM_JOINT_NAMES:
        raise TypingEndpointReuseVerifierV1Error(
            "joint state does not use canonical joint order"
        )
    result: dict[str, float] = {}
    for name in ARM_JOINT_NAMES:
        raw = value[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypingEndpointReuseVerifierV1Error("joint state differs")
        result[name] = float(raw)
    try:
        _canonical(result)
    except ValueError as exc:
        raise TypingEndpointReuseVerifierV1Error(
            "joint state contains a nonfinite value"
        ) from exc
    return result


@dataclass(frozen=True, slots=True)
class _Entry:
    endpoint_sha256: str
    solution_joint_state: Mapping[str, float]
    solution_joint_state_sha256: str
    entry_sha256: str
    observation_count: int


class TypingEndpointReuseVerifierV1:
    """Compare repeated endpoint candidates to canonical reference solutions."""

    def __init__(
        self, *, context: SimulationContext, context_epoch_sha256: str,
        service_instance_id: str, generation: int, maximum_entries: int,
        maximum_samples: int,
    ) -> None:
        if (
            isinstance(maximum_entries, bool)
            or not isinstance(maximum_entries, int)
            or not 1 <= maximum_entries <= 4096
        ):
            raise TypingEndpointReuseVerifierV1Error(
                "maximum_entries must be in [1, 4096]"
            )
        self._lock = RLock()
        self._context = context
        self._context_epoch_sha256 = _digest(
            context_epoch_sha256, "context epoch"
        )
        if (
            not isinstance(service_instance_id, str)
            or not service_instance_id
            or len(service_instance_id) > 192
        ):
            raise TypingEndpointReuseVerifierV1Error(
                "service identity is invalid"
            )
        self._service_instance_id = service_instance_id
        self._generation = generation
        self._maximum_entries = maximum_entries
        if (
            isinstance(maximum_samples, bool)
            or not isinstance(maximum_samples, int)
            or not 1 <= maximum_samples <= 16384
        ):
            raise TypingEndpointReuseVerifierV1Error(
                "maximum_samples must be in [1, 16384]"
            )
        self._maximum_samples = maximum_samples
        self._decision_context_sha256: str | None = None
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._active = True
        self._observed_samples = 0
        self._endpoint_observations = 0
        self._lookups = 0
        self._hits = 0
        self._misses = 0
        self._stores = 0
        self._capacity_skips = 0
        self._matches = 0
        self._conflicts = 0

    @classmethod
    def create(
        cls, context: SimulationContext, lifecycle: SimulationContextLifecycleV1,
        *, maximum_entries: int = 256,
        maximum_samples: int = 4096,
    ) -> "TypingEndpointReuseVerifierV1":
        if not isinstance(lifecycle, SimulationContextLifecycleV1):
            raise TypeError("lifecycle must be SimulationContextLifecycleV1")
        with lifecycle.validation_scope(context) as binding:
            return cls(
                context=binding.context,
                context_epoch_sha256=binding.context_epoch_sha256,
                service_instance_id=binding.service_instance_id,
                generation=binding.generation,
                maximum_entries=maximum_entries,
                maximum_samples=maximum_samples,
            )

    def _validate(self, binding: SimulationContextLifecycleBindingV1) -> None:
        if not isinstance(binding, SimulationContextLifecycleBindingV1):
            raise TypeError("binding must be SimulationContextLifecycleBindingV1")
        if not self._active:
            raise TypingEndpointReuseVerifierV1Error(
                "endpoint reuse verifier is invalidated"
            )
        if self._context is not binding.context:
            raise SimulationContextError(
                "endpoint reuse verifier belongs to a different context"
            )
        if (
            self._context_epoch_sha256 != binding.context_epoch_sha256
            or self._service_instance_id != binding.service_instance_id
            or self._generation != binding.generation
        ):
            raise SimulationContextError(
                "endpoint reuse verifier lifecycle binding is stale"
            )

    def observe(
        self, sample: TypingScreeningSampleV1,
        evaluated: JointTrajectoryWaypointResult, *,
        decision_context_sha256: str,
        binding: SimulationContextLifecycleBindingV1,
    ) -> None:
        if not isinstance(sample, TypingScreeningSampleV1):
            raise TypeError("sample must be TypingScreeningSampleV1")
        if not isinstance(evaluated, JointTrajectoryWaypointResult):
            raise TypeError("evaluated must be JointTrajectoryWaypointResult")
        decision_context = _digest(decision_context_sha256, "decision context")
        with self._lock:
            self._validate(binding)
            if self._observed_samples >= self._maximum_samples:
                raise TypingEndpointReuseVerifierV1Error(
                    "endpoint reuse observation bound exceeded"
                )
            if self._decision_context_sha256 is None:
                self._decision_context_sha256 = decision_context
            elif self._decision_context_sha256 != decision_context:
                raise TypingEndpointReuseVerifierV1Error(
                    "endpoint reuse decision context differs"
                )
            self._observed_samples += 1
            if not sample.phase_endpoint or not evaluated.accepted:
                return
            self._endpoint_observations += 1
            endpoint_core = {
                "phase": sample.phase.value,
                "target_id": sample.target_id,
                "point_board_mm": {
                    "frame": sample.point.frame,
                    "x": sample.point.x,
                    "y": sample.point.y,
                    "z": sample.point.z,
                },
            }
            endpoint = _sha(endpoint_core)
            solution = _joint_state(
                dict(evaluated.solution_arm_joint_positions_rad)
            )
            solution_sha = _sha(solution)
            self._lookups += 1
            entry = self._entries.get(endpoint)
            if entry is None:
                self._misses += 1
                if len(self._entries) >= self._maximum_entries:
                    self._capacity_skips += 1
                    return
                core = {
                    "endpoint_sha256": endpoint,
                    "solution_joint_state": solution,
                    "solution_joint_state_sha256": solution_sha,
                }
                self._entries[endpoint] = _Entry(
                    **core, entry_sha256=_sha(core), observation_count=1,
                )
                self._stores += 1
                return
            self._hits += 1
            core = {
                "endpoint_sha256": entry.endpoint_sha256,
                "solution_joint_state": dict(entry.solution_joint_state),
                "solution_joint_state_sha256": entry.solution_joint_state_sha256,
            }
            if (
                _sha(core) != entry.entry_sha256
                or _sha(dict(entry.solution_joint_state))
                != entry.solution_joint_state_sha256
            ):
                raise TypingEndpointReuseVerifierV1Error(
                    "endpoint reuse entry integrity differs"
                )
            if entry.solution_joint_state_sha256 != solution_sha:
                self._conflicts += 1
                raise TypingEndpointReuseVerifierV1Error(
                    "endpoint reuse candidate differs from canonical solution"
                )
            self._matches += 1
            self._entries[endpoint] = _Entry(
                endpoint_sha256=entry.endpoint_sha256,
                solution_joint_state=entry.solution_joint_state,
                solution_joint_state_sha256=entry.solution_joint_state_sha256,
                entry_sha256=entry.entry_sha256,
                observation_count=entry.observation_count + 1,
            )

    def invalidate(self) -> None:
        with self._lock:
            self._entries.clear()
            self._active = False

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            entries = [
                {
                    "endpoint_sha256": entry.endpoint_sha256,
                    "solution_joint_state_sha256": (
                        entry.solution_joint_state_sha256
                    ),
                    "observation_count": entry.observation_count,
                    "entry_sha256": entry.entry_sha256,
                }
                for entry in self._entries.values()
            ]
            core = {
                "schema": SCHEMA,
                "context_epoch_sha256": self._context_epoch_sha256,
                "service_instance_id": self._service_instance_id,
                "generation": self._generation,
                "decision_context_sha256": self._decision_context_sha256,
                "maximum_entries": self._maximum_entries,
                "maximum_samples": self._maximum_samples,
                "entry_count": len(entries),
                "active": self._active,
                "observed_sample_count": self._observed_samples,
                "endpoint_observation_count": self._endpoint_observations,
                "lookups": self._lookups,
                "hits": self._hits,
                "misses": self._misses,
                "stores": self._stores,
                "capacity_skips": self._capacity_skips,
                "canonical_matches": self._matches,
                "canonical_conflicts": self._conflicts,
                "entries": entries,
                "candidate_used_for_decision": False,
                "diagnostics_used_for_admission": False,
                "warm_start_authorized": False,
                "controller_commands": [],
                "hardware_commands_generated": 0,
                "hardware_access": False,
                "physical_authority": False,
            }
            return {**core, "verifier_snapshot_sha256": _sha(core)}


def parse_typing_endpoint_reuse_verifier_snapshot_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    fields = {
        "schema", "context_epoch_sha256", "service_instance_id", "generation",
        "decision_context_sha256", "maximum_entries", "maximum_samples",
        "entry_count", "active",
        "observed_sample_count", "endpoint_observation_count", "lookups",
        "hits", "misses", "stores", "capacity_skips", "canonical_matches",
        "canonical_conflicts", "entries", "candidate_used_for_decision",
        "diagnostics_used_for_admission", "warm_start_authorized",
        "controller_commands", "hardware_commands_generated", "hardware_access",
        "physical_authority", "verifier_snapshot_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingEndpointReuseVerifierV1Error("verifier snapshot fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("verifier_snapshot_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingEndpointReuseVerifierV1Error("verifier snapshot hash differs")
    if value.get("schema") != SCHEMA:
        raise TypingEndpointReuseVerifierV1Error("verifier schema differs")
    _digest(value.get("context_epoch_sha256"), "context epoch")
    decision_context = value.get("decision_context_sha256")
    if decision_context is not None:
        _digest(decision_context, "decision context")
    integers = (
        "generation", "maximum_entries", "maximum_samples", "entry_count",
        "observed_sample_count",
        "endpoint_observation_count", "lookups", "hits", "misses", "stores",
        "capacity_skips", "canonical_matches", "canonical_conflicts",
    )
    if any(
        isinstance(value.get(field), bool)
        or not isinstance(value.get(field), int)
        or value[field] < 0
        for field in integers
    ):
        raise TypingEndpointReuseVerifierV1Error("verifier counters differ")
    entries = value.get("entries")
    if not isinstance(entries, list) or len(entries) != value["entry_count"]:
        raise TypingEndpointReuseVerifierV1Error("verifier entries differ")
    seen = set()
    observations = 0
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {
            "endpoint_sha256", "solution_joint_state_sha256",
            "observation_count", "entry_sha256",
        }:
            raise TypingEndpointReuseVerifierV1Error("verifier entry differs")
        endpoint = _digest(entry.get("endpoint_sha256"), "endpoint")
        _digest(entry.get("solution_joint_state_sha256"), "solution state")
        _digest(entry.get("entry_sha256"), "entry")
        count = entry.get("observation_count")
        if endpoint in seen or isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise TypingEndpointReuseVerifierV1Error("verifier entry differs")
        seen.add(endpoint)
        observations += count
    if (
        not 1 <= value["maximum_entries"] <= 4096
        or not 1 <= value["maximum_samples"] <= 16384
        or value["observed_sample_count"] > value["maximum_samples"]
        or value["entry_count"] > value["maximum_entries"]
        or value["lookups"] != value["hits"] + value["misses"]
        or value["stores"] < value["entry_count"]
        or value["misses"] != value["stores"] + value["capacity_skips"]
        or value["canonical_matches"] + value["canonical_conflicts"]
        != value["hits"]
        or value["endpoint_observation_count"] != value["lookups"]
        or (
            value["active"]
            and observations != value["stores"] + value["canonical_matches"]
        )
        or (not value["active"] and entries != [])
    ):
        raise TypingEndpointReuseVerifierV1Error("verifier derivation differs")
    service = value.get("service_instance_id")
    if not isinstance(service, str) or not service or len(service) > 192:
        raise TypingEndpointReuseVerifierV1Error("service identity differs")
    if not isinstance(value.get("active"), bool):
        raise TypingEndpointReuseVerifierV1Error("active differs")
    if (
        value.get("candidate_used_for_decision") is not False
        or value.get("diagnostics_used_for_admission") is not False
        or value.get("warm_start_authorized") is not False
        or value.get("controller_commands") != []
        or value.get("hardware_commands_generated") != 0
        or value.get("hardware_access") is not False
        or value.get("physical_authority") is not False
    ):
        raise TypingEndpointReuseVerifierV1Error(
            "verifier snapshot violates zero authority"
        )
    return value


__all__ = [
    "SCHEMA", "TypingEndpointReuseVerifierV1",
    "TypingEndpointReuseVerifierV1Error",
    "parse_typing_endpoint_reuse_verifier_snapshot_v1",
]
