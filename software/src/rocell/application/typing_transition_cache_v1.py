"""Bounded, zero-authority planning-seed cache for PC7 shadow qualification.

The cache never stores controller bytes, permits, or an executable schedule.
A hit exposes only a solver seed and timing estimate after fresh evidence has
revalidated every safety owner.  The caller must still run the planner and all
admission boundaries again.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping

from rocell.kinematics import ARM_JOINT_NAMES


SCHEMA = "rocell.typing_transition_cache.v1"
ENTRY_SCHEMA = "rocell.typing_transition_cache_entry.v1"
RESULT_SCHEMA = "rocell.typing_transition_cache_lookup.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DIRECTIONS = frozenset({"FORWARD", "REVERSE", "SAME_TARGET"})
_VALIDATION_STATUS = "VALIDATED_FOR_CURRENT_SHADOW_ATTEMPT"
_IDENTITY_FIELDS = frozenset({
    "calibration_snapshot_sha256",
    "target_catalog_sha256",
    "tool_profile_sha256",
    "arm_model_sha256",
    "dynamics_profile_sha256",
    "planner_policy_sha256",
    "device_pose_epoch_sha256",
})


class TypingTransitionCacheV1Error(ValueError):
    """A cache identity, entry, or revalidation record is malformed."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingTransitionCacheV1Error("value is not canonical JSON") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise TypingTransitionCacheV1Error(
            f"{label} must be a lowercase SHA-256 digest")
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 128
    ):
        raise TypingTransitionCacheV1Error(
            f"{label} must be bounded nonempty unpadded text")
    return value


def _nonnegative_ns(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypingTransitionCacheV1Error(
            f"{label} must be a nonnegative integer")
    return value


def _joint_positions(value: object) -> MappingProxyType:
    if not isinstance(value, Mapping) or tuple(value) != ARM_JOINT_NAMES:
        raise TypingTransitionCacheV1Error(
            "joint_positions_rad must use canonical joint order")
    parsed: dict[str, float] = {}
    for name in ARM_JOINT_NAMES:
        raw = value[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypingTransitionCacheV1Error(
                f"joint_positions_rad.{name} must be numeric")
        number = float(raw)
        if not math.isfinite(number):
            raise TypingTransitionCacheV1Error(
                f"joint_positions_rad.{name} must be finite")
        parsed[name] = number
    return MappingProxyType(parsed)


@dataclass(frozen=True, slots=True)
class TypingTransitionCacheKeyV1:
    source_target_id: str
    destination_target_id: str
    direction: str
    calibration_snapshot_sha256: str
    target_catalog_sha256: str
    tool_profile_sha256: str
    arm_model_sha256: str
    dynamics_profile_sha256: str
    planner_policy_sha256: str
    device_pose_epoch_sha256: str

    def __post_init__(self) -> None:
        _identifier(self.source_target_id, "source_target_id")
        _identifier(self.destination_target_id, "destination_target_id")
        if self.direction not in _DIRECTIONS:
            raise TypingTransitionCacheV1Error("direction is invalid")
        if (
            self.source_target_id == self.destination_target_id
            and self.direction != "SAME_TARGET"
        ) or (
            self.source_target_id != self.destination_target_id
            and self.direction == "SAME_TARGET"
        ):
            raise TypingTransitionCacheV1Error(
                "direction disagrees with the directional target pair")
        for field in _IDENTITY_FIELDS:
            _digest(getattr(self, field), field)

    def to_dict(self) -> dict[str, str]:
        return {
            "source_target_id": self.source_target_id,
            "destination_target_id": self.destination_target_id,
            "direction": self.direction,
            "calibration_snapshot_sha256": self.calibration_snapshot_sha256,
            "target_catalog_sha256": self.target_catalog_sha256,
            "tool_profile_sha256": self.tool_profile_sha256,
            "arm_model_sha256": self.arm_model_sha256,
            "dynamics_profile_sha256": self.dynamics_profile_sha256,
            "planner_policy_sha256": self.planner_policy_sha256,
            "device_pose_epoch_sha256": self.device_pose_epoch_sha256,
        }

    @property
    def key_sha256(self) -> str:
        return _sha256(self.to_dict())


@dataclass(frozen=True, slots=True)
class TypingTransitionPlanningSeedV1:
    joint_positions_rad: Mapping[str, float]
    estimated_duration_ns: int
    estimated_planning_time_saved_ns: int
    admitted_schedule_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "joint_positions_rad", _joint_positions(
            self.joint_positions_rad))
        if _nonnegative_ns(self.estimated_duration_ns, "estimated_duration_ns") == 0:
            raise TypingTransitionCacheV1Error(
                "estimated_duration_ns must be positive")
        _nonnegative_ns(
            self.estimated_planning_time_saved_ns,
            "estimated_planning_time_saved_ns",
        )
        _digest(self.admitted_schedule_sha256, "admitted_schedule_sha256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "joint_positions_rad": dict(self.joint_positions_rad),
            "estimated_duration_ns": self.estimated_duration_ns,
            "estimated_planning_time_saved_ns": (
                self.estimated_planning_time_saved_ns),
            "admitted_schedule_sha256": self.admitted_schedule_sha256,
        }


@dataclass(frozen=True, slots=True)
class TypingTransitionRevalidationV1:
    key_sha256: str
    expected_start_state_sha256: str
    observed_start_state_sha256: str
    ik_evidence_sha256: str
    collision_evidence_sha256: str
    dynamics_evidence_sha256: str
    permit_policy_evidence_sha256: str
    ik_status: str
    collision_status: str
    dynamics_status: str
    permit_policy_status: str
    now_monotonic_ns: int
    valid_until_monotonic_ns: int

    def __post_init__(self) -> None:
        for field in (
            "key_sha256", "expected_start_state_sha256",
            "observed_start_state_sha256", "ik_evidence_sha256",
            "collision_evidence_sha256", "dynamics_evidence_sha256",
            "permit_policy_evidence_sha256",
        ):
            _digest(getattr(self, field), field)
        for field in (
            "ik_status", "collision_status", "dynamics_status",
            "permit_policy_status",
        ):
            _identifier(getattr(self, field), field)
        now = _nonnegative_ns(self.now_monotonic_ns, "now_monotonic_ns")
        valid = _nonnegative_ns(
            self.valid_until_monotonic_ns, "valid_until_monotonic_ns")
        if valid < now:
            return

    @property
    def accepted(self) -> bool:
        return (
            self.expected_start_state_sha256 == self.observed_start_state_sha256
            and self.now_monotonic_ns <= self.valid_until_monotonic_ns
            and self.ik_status == _VALIDATION_STATUS
            and self.collision_status == _VALIDATION_STATUS
            and self.dynamics_status == _VALIDATION_STATUS
            and self.permit_policy_status == _VALIDATION_STATUS
        )


class TypingTransitionCacheV1:
    """Deterministic FIFO cache whose outputs remain planning hints only."""

    def __init__(self, *, maximum_entries: int = 64) -> None:
        if (
            isinstance(maximum_entries, bool)
            or not isinstance(maximum_entries, int)
            or not 1 <= maximum_entries <= 64
        ):
            raise TypingTransitionCacheV1Error(
                "maximum_entries must be an integer in [1, 64]")
        self.maximum_entries = maximum_entries
        self._entries: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._metrics = {
            "hits": 0,
            "misses": 0,
            "validations": 0,
            "discards": 0,
            "corruptions": 0,
            "evictions": 0,
            "invalidations": 0,
            "estimated_time_saved_ns": 0,
        }

    @staticmethod
    def _entry(
        key: TypingTransitionCacheKeyV1,
        seed: TypingTransitionPlanningSeedV1,
    ) -> dict[str, Any]:
        core = {
            "schema": ENTRY_SCHEMA,
            "key": key.to_dict(),
            "key_sha256": key.key_sha256,
            "planning_seed": seed.to_dict(),
            "controller_commands": [],
            "hardware_access": False,
            "physical_authority": False,
        }
        return {**core, "entry_sha256": _sha256(core)}

    def put(
        self,
        key: TypingTransitionCacheKeyV1,
        seed: TypingTransitionPlanningSeedV1,
    ) -> str:
        if not isinstance(key, TypingTransitionCacheKeyV1):
            raise TypeError("key must be a TypingTransitionCacheKeyV1")
        if not isinstance(seed, TypingTransitionPlanningSeedV1):
            raise TypeError("seed must be a TypingTransitionPlanningSeedV1")
        digest = key.key_sha256
        if digest in self._entries:
            del self._entries[digest]
        elif len(self._entries) == self.maximum_entries:
            self._entries.popitem(last=False)
            self._metrics["evictions"] += 1
        self._entries[digest] = self._entry(key, seed)
        return digest

    def _parse_entry(
        self, document: Mapping[str, Any], expected_key: TypingTransitionCacheKeyV1,
    ) -> TypingTransitionPlanningSeedV1:
        expected = {
            "schema", "key", "key_sha256", "planning_seed", "controller_commands",
            "hardware_access", "physical_authority", "entry_sha256",
        }
        if not isinstance(document, Mapping) or set(document) != expected:
            raise TypingTransitionCacheV1Error("cache entry fields are not exact")
        unsigned = dict(document)
        claimed = unsigned.pop("entry_sha256")
        if _digest(claimed, "entry_sha256") != _sha256(unsigned):
            raise TypingTransitionCacheV1Error("cache entry hash is invalid")
        if (
            document["schema"] != ENTRY_SCHEMA
            or document["key"] != expected_key.to_dict()
            or document["key_sha256"] != expected_key.key_sha256
            or document["controller_commands"] != []
            or document["hardware_access"] is not False
            or document["physical_authority"] is not False
        ):
            raise TypingTransitionCacheV1Error(
                "cache entry identity or authority is invalid")
        seed = document["planning_seed"]
        if not isinstance(seed, Mapping):
            raise TypingTransitionCacheV1Error("planning seed is invalid")
        return TypingTransitionPlanningSeedV1(**seed)

    def lookup(
        self,
        key: TypingTransitionCacheKeyV1,
        revalidation: TypingTransitionRevalidationV1,
    ) -> dict[str, Any]:
        if not isinstance(key, TypingTransitionCacheKeyV1):
            raise TypeError("key must be a TypingTransitionCacheKeyV1")
        if not isinstance(revalidation, TypingTransitionRevalidationV1):
            raise TypeError(
                "revalidation must be a TypingTransitionRevalidationV1")
        digest = key.key_sha256
        entry = self._entries.get(digest)
        if entry is None:
            self._metrics["misses"] += 1
            return self._result("MISS", key, None)
        self._metrics["validations"] += 1
        try:
            seed = self._parse_entry(entry, key)
        except TypingTransitionCacheV1Error:
            del self._entries[digest]
            self._metrics["corruptions"] += 1
            self._metrics["discards"] += 1
            return self._result("DISCARDED_CORRUPT", key, None)
        if revalidation.key_sha256 != digest or not revalidation.accepted:
            del self._entries[digest]
            self._metrics["discards"] += 1
            return self._result("DISCARDED_REVALIDATION_FAILED", key, None)
        self._metrics["hits"] += 1
        self._metrics["estimated_time_saved_ns"] += (
            seed.estimated_planning_time_saved_ns)
        return self._result("HIT_REVALIDATED", key, seed)

    def invalidate_identity(self, field: str, current_sha256: str) -> int:
        if field not in _IDENTITY_FIELDS:
            raise TypingTransitionCacheV1Error("identity field is not cache-bound")
        _digest(current_sha256, field)
        removed = 0
        for digest, entry in tuple(self._entries.items()):
            key = entry.get("key")
            if not isinstance(key, Mapping) or key.get(field) != current_sha256:
                del self._entries[digest]
                removed += 1
        self._metrics["invalidations"] += removed
        return removed

    def invalidate_all(self) -> int:
        removed = len(self._entries)
        self._entries.clear()
        self._metrics["invalidations"] += removed
        return removed

    def _result(
        self,
        status: str,
        key: TypingTransitionCacheKeyV1,
        seed: TypingTransitionPlanningSeedV1 | None,
    ) -> dict[str, Any]:
        return {
            "schema": RESULT_SCHEMA,
            "status": status,
            "key_sha256": key.key_sha256,
            "planning_seed": None if seed is None else seed.to_dict(),
            "requires_fresh_planning": True,
            "requires_full_safety_revalidation": True,
            "cached_schedule_admitted": False,
            "permit_id": None,
            "permit_issued": False,
            "controller_commands": [],
            "hardware_commands_generated": 0,
            "hardware_access": False,
            "physical_authority": False,
        }

    @property
    def metrics(self) -> Mapping[str, int]:
        return MappingProxyType({
            "schema_version": 1,
            "maximum_entries": self.maximum_entries,
            "current_entries": len(self._entries),
            **self._metrics,
        })


__all__ = [
    "ENTRY_SCHEMA", "RESULT_SCHEMA", "SCHEMA", "TypingTransitionCacheKeyV1",
    "TypingTransitionCacheV1", "TypingTransitionCacheV1Error",
    "TypingTransitionPlanningSeedV1", "TypingTransitionRevalidationV1",
]
