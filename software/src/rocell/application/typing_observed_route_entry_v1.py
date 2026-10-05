"""Build a bounded observed-pose to retained-route-entry joint envelope.

The envelope uses the shared bounded segment sampler and the first accepted
canonical IK result from ARM-149.  It is a deterministic sample plan only: no
installed collision, swept-volume, dynamics, controller command, or execution
authority is inferred.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping

from rocell.kinematics import ARM_JOINT_NAMES

from .bounded_segment_collision_qualification import (
    BoundedJointConfigurationSample,
    BoundedSegmentCollisionQualificationError,
    BoundedSegmentSamplingPolicy,
    build_bounded_joint_sample_plan_from_results,
)
from .typing_observed_ik_seed_v1 import TypingObservedIkSeedV1
from .typing_observed_trajectory_ik_v1 import (
    READY_STATUS as OBSERVED_IK_READY_STATUS,
    TypingObservedTrajectoryIkV1Error,
    parse_typing_observed_trajectory_ik_v1,
)


SCHEMA = "rocell.typing_observed_route_entry.v1"
STATUS = "READY_FOR_ENTRY_COLLISION_AND_DYNAMICS_QUALIFICATION"
REQUIRED_NEXT_EVIDENCE = (
    "DEPLOYMENT_QUALIFIED_PLAN_REQUIRED",
    "OBSERVED_START_TO_ROUTE_ENTRY_COLLISION_QUALIFICATION_REQUIRED",
    "PHYSICALLY_QUALIFIED_DYNAMICS_REQUIRED",
    "INSTALLED_COLLISION_PROFILE_REQUIRED",
    "CONTINUOUS_COLLISION_QUALIFICATION_REQUIRED",
    "INDEPENDENT_EFFECT_VERIFIER_REQUIRED",
    "PER_ACTION_REVIEW_BINDINGS_REQUIRED",
)
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "schema", "status", "request_id", "materialization_sha256",
    "observed_trajectory_ik_sha256", "observed_ik_seed_sha256",
    "observed_start_state_sha256", "canonical_ik_screen_sha256",
    "calibration_snapshot_sha256", "build_snapshot_sha256",
    "controller_session_id", "sampling_policy", "route_entry_waypoint_sequence",
    "route_entry_phase", "route_entry_target_id", "start_joint_positions_rad",
    "entry_joint_positions_rad", "sample_count", "maximum_joint_gap_rad",
    "sample_plan", "route_entry_envelope_completed",
    "route_entry_collision_qualified", "measured_dynamics_qualified",
    "continuous_collision_proven", "required_next_evidence",
    "permit_review_ready", "eligible_for_executor", "automatic_retry_allowed",
    "controller_commands", "wire_commands", "hardware_commands_generated",
    "hardware_access", "physical_authority", "observed_route_entry_sha256",
}


class TypingObservedRouteEntryV1Error(ValueError):
    """Observed-to-entry sampling input, lineage, or envelope differs."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingObservedRouteEntryV1Error(
            "observed route entry is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _joint_map(value: object, label: str) -> dict[str, float]:
    if not isinstance(value, Mapping) or set(value) != set(ARM_JOINT_NAMES):
        raise TypingObservedRouteEntryV1Error(
            f"{label} must exactly cover canonical arm joints"
        )
    result: dict[str, float] = {}
    for name in ARM_JOINT_NAMES:
        raw = value[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypingObservedRouteEntryV1Error(f"{label}.{name} is not numeric")
        number = float(raw)
        if not math.isfinite(number):
            raise TypingObservedRouteEntryV1Error(f"{label}.{name} is not finite")
        result[name] = number
    return result


def build_typing_observed_route_entry_v1(
    observed_trajectory_ik: Mapping[str, Any],
    seed: TypingObservedIkSeedV1,
    *,
    policy: BoundedSegmentSamplingPolicy | None = None,
) -> dict[str, Any]:
    """Expand observed joints to the first retained-route solution."""

    if not isinstance(observed_trajectory_ik, Mapping):
        raise TypeError("observed_trajectory_ik must be a mapping")
    if not isinstance(seed, TypingObservedIkSeedV1):
        raise TypeError("seed must be a TypingObservedIkSeedV1")
    try:
        source = parse_typing_observed_trajectory_ik_v1(observed_trajectory_ik)
    except TypingObservedTrajectoryIkV1Error as exc:
        raise TypingObservedRouteEntryV1Error(str(exc)) from exc
    selected = policy or BoundedSegmentSamplingPolicy()
    if not isinstance(selected, BoundedSegmentSamplingPolicy):
        raise TypeError("policy must be a BoundedSegmentSamplingPolicy")
    if (
        source["status"] != OBSERVED_IK_READY_STATUS
        or source["ik_all_samples_accepted"] is not True
    ):
        raise TypingObservedRouteEntryV1Error(
            "an all-accepted observed-state IK screen is required"
        )
    if (
        source["observed_ik_seed_sha256"] != seed.observed_ik_seed_sha256
        or source["observed_start_state_sha256"]
        != seed.observed_start_state_sha256
        or source["materialization_sha256"] != seed.materialization_sha256
        or source["controller_session_id"] != seed.controller_session_id
    ):
        raise TypingObservedRouteEntryV1Error(
            "observed IK screen belongs to a different seed or session"
        )
    canonical = source["canonical_ik_screen"]
    results = canonical.get("joint_results")
    if not isinstance(results, list) or not results:
        raise TypingObservedRouteEntryV1Error(
            "canonical IK screen contains no route-entry result"
        )
    first = results[0]
    if (
        not isinstance(first, Mapping)
        or first.get("waypoint_sequence") != 0
        or first.get("accepted") is not True
    ):
        raise TypingObservedRouteEntryV1Error(
            "first retained route waypoint is not an accepted canonical result"
        )
    try:
        samples = build_bounded_joint_sample_plan_from_results(
            seed.joint_positions_rad, (first,), selected
        )
    except BoundedSegmentCollisionQualificationError as exc:
        raise TypingObservedRouteEntryV1Error(str(exc)) from exc
    start = _joint_map(seed.joint_positions_rad, "start_joint_positions_rad")
    endpoint = _joint_map(
        first.get("solution_arm_joint_positions_rad"),
        "entry_joint_positions_rad",
    )
    sample_plan = [
        {**sample.to_dict(), "sample_sha256": sample.content_sha256}
        for sample in samples
    ]
    maximum_gap = max(
        (
            max(
                abs(right.joint_positions_rad[name] - left.joint_positions_rad[name])
                for name in ARM_JOINT_NAMES
            )
            for left, right in zip(samples, samples[1:])
        ),
        default=0.0,
    )
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "request_id": source["request_id"],
        "materialization_sha256": source["materialization_sha256"],
        "observed_trajectory_ik_sha256": source["observed_trajectory_ik_sha256"],
        "observed_ik_seed_sha256": seed.observed_ik_seed_sha256,
        "observed_start_state_sha256": seed.observed_start_state_sha256,
        "canonical_ik_screen_sha256": source["canonical_ik_screen_sha256"],
        "calibration_snapshot_sha256": source["calibration_snapshot_sha256"],
        "build_snapshot_sha256": source["build_snapshot_sha256"],
        "controller_session_id": source["controller_session_id"],
        "sampling_policy": {
            **selected.to_dict(), "sampling_policy_sha256": selected.content_sha256,
        },
        "route_entry_waypoint_sequence": 0,
        "route_entry_phase": first["phase"],
        "route_entry_target_id": first["semantic_target"],
        "start_joint_positions_rad": start,
        "entry_joint_positions_rad": endpoint,
        "sample_count": len(samples),
        "maximum_joint_gap_rad": maximum_gap,
        "sample_plan": sample_plan,
        "route_entry_envelope_completed": True,
        "route_entry_collision_qualified": False,
        "measured_dynamics_qualified": False,
        "continuous_collision_proven": False,
        "required_next_evidence": list(REQUIRED_NEXT_EVIDENCE),
        "permit_review_ready": False,
        "eligible_for_executor": False,
        "automatic_retry_allowed": False,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "observed_route_entry_sha256": _sha(core)}


def parse_typing_observed_route_entry_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the complete bounded entry sample plan and closed gates."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingObservedRouteEntryV1Error("observed route entry fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("observed_route_entry_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingObservedRouteEntryV1Error("observed route entry hash differs")
    digests = (
        "materialization_sha256", "observed_trajectory_ik_sha256",
        "observed_ik_seed_sha256", "observed_start_state_sha256",
        "canonical_ik_screen_sha256", "calibration_snapshot_sha256",
        "build_snapshot_sha256",
    )
    policy = value["sampling_policy"]
    if not isinstance(policy, Mapping):
        raise TypingObservedRouteEntryV1Error(
            "observed route entry sampling policy differs"
        )
    try:
        selected = BoundedSegmentSamplingPolicy(
            maximum_joint_step_rad=policy["maximum_joint_step_rad"],
            maximum_samples=policy["maximum_samples"],
        )
    except (KeyError, TypeError, BoundedSegmentCollisionQualificationError) as exc:
        raise TypingObservedRouteEntryV1Error(
            "observed route entry sampling policy differs"
        ) from exc
    if (
        set(policy)
        != {"maximum_joint_step_rad", "maximum_samples", "sampling_policy_sha256"}
        or policy["sampling_policy_sha256"] != selected.content_sha256
    ):
        raise TypingObservedRouteEntryV1Error(
            "observed route entry sampling policy hash differs"
        )
    raw_samples = value["sample_plan"]
    if not isinstance(raw_samples, list) or not raw_samples:
        raise TypingObservedRouteEntryV1Error("observed route entry samples are absent")
    parsed_samples: list[BoundedJointConfigurationSample] = []
    for index, item in enumerate(raw_samples):
        if not isinstance(item, Mapping):
            raise TypingObservedRouteEntryV1Error("entry sample is not an object")
        sample = BoundedJointConfigurationSample(
            sample_sequence=item.get("sample_sequence"),
            source_segment_index=item.get("source_segment_index"),
            subdivision_index=item.get("subdivision_index"),
            subdivision_count=item.get("subdivision_count"),
            interpolation_ratio=item.get("interpolation_ratio"),
            joint_positions_rad=item.get("joint_positions_rad"),
        )
        if (
            set(item) != set(sample.to_dict()) | {"sample_sha256"}
            or item.get("sample_id") != sample.sample_id
            or item.get("sample_sha256") != sample.content_sha256
            or sample.sample_sequence != index
            or sample.source_segment_index != 0
            or isinstance(sample.subdivision_index, bool)
            or not isinstance(sample.subdivision_index, int)
            or isinstance(sample.subdivision_count, bool)
            or not isinstance(sample.subdivision_count, int)
            or sample.subdivision_count < 1
            or sample.subdivision_index != index
            or sample.subdivision_count != len(raw_samples) - 1
            or isinstance(sample.interpolation_ratio, bool)
            or not isinstance(sample.interpolation_ratio, (int, float))
            or not math.isfinite(float(sample.interpolation_ratio))
            or not math.isclose(
                float(sample.interpolation_ratio),
                index / (len(raw_samples) - 1),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            raise TypingObservedRouteEntryV1Error(
                "entry sample identity, order, or hash differs"
            )
        parsed_samples.append(sample)
    maximum_gap = max(
        (
            max(
                abs(right.joint_positions_rad[name] - left.joint_positions_rad[name])
                for name in ARM_JOINT_NAMES
            )
            for left, right in zip(parsed_samples, parsed_samples[1:])
        ),
        default=0.0,
    )
    if (
        value["schema"] != SCHEMA
        or value["status"] != STATUS
        or any(_SHA.fullmatch(value[field] or "") is None for field in digests)
        or not isinstance(value["request_id"], str)
        or not value["request_id"]
        or not isinstance(value["controller_session_id"], str)
        or not value["controller_session_id"]
        or value["route_entry_waypoint_sequence"] != 0
        or value["route_entry_phase"] != "PARK"
        or value["route_entry_target_id"] is not None
        or value["sample_count"] != len(parsed_samples)
        or len(parsed_samples) > selected.maximum_samples
        or parsed_samples[0].interpolation_ratio != 0.0
        or parsed_samples[-1].interpolation_ratio != 1.0
        or parsed_samples[0].joint_positions_rad
        != _joint_map(value["start_joint_positions_rad"], "start joints")
        or parsed_samples[-1].joint_positions_rad
        != _joint_map(value["entry_joint_positions_rad"], "entry joints")
        or not math.isclose(
            value["maximum_joint_gap_rad"], maximum_gap,
            rel_tol=0.0, abs_tol=1e-12,
        )
        or maximum_gap > selected.maximum_joint_step_rad + 1e-12
        or value["route_entry_envelope_completed"] is not True
        or value["route_entry_collision_qualified"] is not False
        or value["measured_dynamics_qualified"] is not False
        or value["continuous_collision_proven"] is not False
        or value["required_next_evidence"] != list(REQUIRED_NEXT_EVIDENCE)
        or value["permit_review_ready"] is not False
        or value["eligible_for_executor"] is not False
        or value["automatic_retry_allowed"] is not False
        or value["controller_commands"] != []
        or value["wire_commands"] != []
        or value["hardware_commands_generated"] != 0
        or value["hardware_access"] is not False
        or value["physical_authority"] is not False
    ):
        raise TypingObservedRouteEntryV1Error(
            "observed route entry lineage, samples, gates, or authority differs"
        )
    return dict(value)


__all__ = [
    "REQUIRED_NEXT_EVIDENCE", "SCHEMA", "STATUS",
    "TypingObservedRouteEntryV1Error", "build_typing_observed_route_entry_v1",
    "parse_typing_observed_route_entry_v1",
]
