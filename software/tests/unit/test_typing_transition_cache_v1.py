from __future__ import annotations

from copy import deepcopy
import random

import pytest

from rocell.kinematics import ARM_JOINT_NAMES
from rocell.application.typing_transition_cache_v1 import (
    TypingTransitionCacheKeyV1,
    TypingTransitionCacheV1,
    TypingTransitionCacheV1Error,
    TypingTransitionPlanningSeedV1,
    TypingTransitionRevalidationV1,
)


H = {letter: letter * 64 for letter in "abcdef0123456789"}
VALID = "VALIDATED_FOR_CURRENT_SHADOW_ATTEMPT"


def _key(source: str = "H", destination: str = "I", **changes):
    values = {
        "source_target_id": source,
        "destination_target_id": destination,
        "direction": "SAME_TARGET" if source == destination else "FORWARD",
        "calibration_snapshot_sha256": H["a"],
        "target_catalog_sha256": H["b"],
        "tool_profile_sha256": H["c"],
        "arm_model_sha256": H["d"],
        "dynamics_profile_sha256": H["e"],
        "planner_policy_sha256": H["f"],
        "device_pose_epoch_sha256": H["0"],
    }
    values.update(changes)
    return TypingTransitionCacheKeyV1(**values)


def _seed(duration: int = 20_000_000):
    return TypingTransitionPlanningSeedV1(
        joint_positions_rad={name: 0.1 * index for index, name in enumerate(
            ARM_JOINT_NAMES)},
        estimated_duration_ns=duration,
        estimated_planning_time_saved_ns=2_000_000,
        admitted_schedule_sha256=H["1"],
    )


def _revalidation(key: TypingTransitionCacheKeyV1, **changes):
    values = {
        "key_sha256": key.key_sha256,
        "expected_start_state_sha256": H["2"],
        "observed_start_state_sha256": H["2"],
        "ik_evidence_sha256": H["3"],
        "collision_evidence_sha256": H["4"],
        "dynamics_evidence_sha256": H["5"],
        "permit_policy_evidence_sha256": H["6"],
        "ik_status": VALID,
        "collision_status": VALID,
        "dynamics_status": VALID,
        "permit_policy_status": VALID,
        "now_monotonic_ns": 100,
        "valid_until_monotonic_ns": 200,
    }
    values.update(changes)
    return TypingTransitionRevalidationV1(**values)


def test_hit_returns_only_revalidated_planning_hint_and_metrics():
    cache = TypingTransitionCacheV1(maximum_entries=2)
    key = _key()
    cache.put(key, _seed())
    result = cache.lookup(key, _revalidation(key))

    assert result["status"] == "HIT_REVALIDATED"
    assert result["planning_seed"]["estimated_duration_ns"] == 20_000_000
    assert result["requires_fresh_planning"] is True
    assert result["requires_full_safety_revalidation"] is True
    assert result["cached_schedule_admitted"] is False
    assert result["permit_id"] is None
    assert result["controller_commands"] == []
    assert result["hardware_commands_generated"] == 0
    assert result["hardware_access"] is result["physical_authority"] is False
    assert cache.metrics["hits"] == 1
    assert cache.metrics["validations"] == 1
    assert cache.metrics["estimated_time_saved_ns"] == 2_000_000


def test_absent_directional_pair_is_a_miss_without_seed():
    cache = TypingTransitionCacheV1()
    key = _key()
    result = cache.lookup(key, _revalidation(key))
    assert result["status"] == "MISS"
    assert result["planning_seed"] is None
    assert cache.metrics["misses"] == 1


@pytest.mark.parametrize("field", [
    "ik_status", "collision_status", "dynamics_status", "permit_policy_status",
])
def test_each_safety_owner_must_revalidate_on_every_hit(field: str):
    cache = TypingTransitionCacheV1()
    key = _key()
    cache.put(key, _seed())
    result = cache.lookup(key, _revalidation(key, **{field: "REJECTED"}))
    assert result["status"] == "DISCARDED_REVALIDATION_FAILED"
    assert result["planning_seed"] is None
    assert cache.metrics["discards"] == 1
    assert cache.lookup(key, _revalidation(key))["status"] == "MISS"


@pytest.mark.parametrize("changes", [
    {"observed_start_state_sha256": H["7"]},
    {"now_monotonic_ns": 201},
    {"key_sha256": H["8"]},
])
def test_drift_staleness_or_crossed_key_discards_entry(changes):
    cache = TypingTransitionCacheV1()
    key = _key()
    cache.put(key, _seed())
    result = cache.lookup(key, _revalidation(key, **changes))
    assert result["status"] == "DISCARDED_REVALIDATION_FAILED"
    assert cache.metrics["current_entries"] == 0


def test_corruption_is_detected_and_discarded_without_authority():
    cache = TypingTransitionCacheV1()
    key = _key()
    digest = cache.put(key, _seed())
    corrupted = deepcopy(cache._entries[digest])
    corrupted["planning_seed"]["estimated_duration_ns"] += 1
    cache._entries[digest] = corrupted

    result = cache.lookup(key, _revalidation(key))
    assert result["status"] == "DISCARDED_CORRUPT"
    assert result["controller_commands"] == []
    assert cache.metrics["corruptions"] == 1
    assert cache.metrics["current_entries"] == 0


def test_fifo_eviction_is_bounded_and_deterministic():
    cache = TypingTransitionCacheV1(maximum_entries=2)
    first = _key("A", "B")
    second = _key("B", "C")
    third = _key("C", "D")
    cache.put(first, _seed(1))
    cache.put(second, _seed(2))
    cache.put(third, _seed(3))

    assert cache.metrics["current_entries"] == 2
    assert cache.metrics["evictions"] == 1
    assert cache.lookup(first, _revalidation(first))["status"] == "MISS"
    assert cache.lookup(second, _revalidation(second))["status"] == (
        "HIT_REVALIDATED")


def test_identity_invalidation_removes_only_stale_entries():
    cache = TypingTransitionCacheV1()
    current = _key("H", "I", device_pose_epoch_sha256=H["0"])
    stale = _key("I", "J", device_pose_epoch_sha256=H["9"])
    cache.put(current, _seed())
    cache.put(stale, _seed())

    assert cache.invalidate_identity("device_pose_epoch_sha256", H["0"]) == 1
    assert cache.metrics["invalidations"] == 1
    assert cache.lookup(current, _revalidation(current))["status"] == (
        "HIT_REVALIDATED")


@pytest.mark.parametrize("field", [
    "calibration_snapshot_sha256",
    "target_catalog_sha256",
    "tool_profile_sha256",
    "arm_model_sha256",
    "dynamics_profile_sha256",
    "planner_policy_sha256",
    "device_pose_epoch_sha256",
])
def test_every_bound_identity_invalidates_crossed_entries(field: str):
    cache = TypingTransitionCacheV1()
    stale = _key()
    cache.put(stale, _seed())
    assert cache.invalidate_identity(field, H["9"]) == 1
    assert cache.metrics["current_entries"] == 0


def test_seeded_randomized_capacity_campaign_is_deterministic_and_bounded():
    def campaign():
        rng = random.Random(20260928)
        cache = TypingTransitionCacheV1(maximum_entries=8)
        statuses = []
        targets = tuple("ABCDEFGHIJKL")
        for _ in range(128):
            source, destination = rng.sample(targets, 2)
            direction = "FORWARD" if source < destination else "REVERSE"
            key = _key(source, destination, direction=direction)
            cache.put(key, _seed(rng.randint(1, 1_000_000)))
            statuses.append(cache.lookup(key, _revalidation(key))["status"])
        return statuses, dict(cache.metrics)

    first = campaign()
    second = campaign()
    assert first == second
    assert set(first[0]) == {"HIT_REVALIDATED"}
    assert first[1]["current_entries"] == 8
    assert first[1]["hits"] == 128
    assert first[1]["evictions"] > 0


def test_key_direction_and_cache_capacity_are_strict():
    with pytest.raises(TypingTransitionCacheV1Error, match="direction disagrees"):
        _key("H", "H", direction="FORWARD")
    with pytest.raises(TypingTransitionCacheV1Error, match="maximum_entries"):
        TypingTransitionCacheV1(maximum_entries=65)
