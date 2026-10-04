"""Decision-neutral observation of exact typing phase endpoints."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import re
from typing import Any, Mapping

from rocell.kinematics import ARM_JOINT_NAMES

from .trajectory_simulation import JointTrajectoryWaypointResult
from .typing_trajectory_plan_v1 import TypingScreeningSampleV1


SCHEMA = "rocell.typing_endpoint_atlas_observation.v1"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "schema", "route_id", "typing_trajectory_plan_sha256",
    "typing_trajectory_ik_screen_sha256", "observed_sample_count",
    "endpoint_observation_count", "unique_endpoint_count",
    "repeated_endpoint_observation_count", "stable_endpoint_count",
    "variable_endpoint_count", "transition_observation_count",
    "unique_transition_count", "endpoint_observations", "endpoint_atlas",
    "transition_atlas", "atlas_use_authorized", "decision_input",
    "timing_used_for_admission", "controller_commands",
    "hardware_commands_generated", "hardware_access", "physical_authority",
    "endpoint_atlas_observation_sha256",
}
_OBSERVATION_FIELDS = {
    "sequence", "sample_sequence", "endpoint_sequence", "action_index",
    "phase", "target_id", "point_board_mm", "endpoint_sha256",
    "solver_input_sha256", "incoming_joint_state_sha256",
    "solution_joint_state_sha256",
}
_ATLAS_FIELDS = {
    "endpoint_sha256", "phase", "target_id", "point_board_mm",
    "observation_count", "solution_joint_state_sha256s",
    "solution_variant_count", "stable_solution_observed",
}
_TRANSITION_FIELDS = {
    "source_endpoint_sha256", "destination_endpoint_sha256",
    "observation_count",
}


class TypingEndpointAtlasObserverV1Error(ValueError):
    """Endpoint observations are malformed, incomplete, or authoritative."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingEndpointAtlasObserverV1Error(
            f"{label} is not a SHA-256 digest"
        )
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 128
        or value != value.strip() or ":\\" in value or "://" in value
        or value.startswith(("/", "\\"))
    ):
        raise TypingEndpointAtlasObserverV1Error(
            f"{label} is invalid or path-like"
        )
    return value


def _joint_state(value: Mapping[str, float], label: str) -> dict[str, float]:
    if not isinstance(value, Mapping) or tuple(value) != ARM_JOINT_NAMES:
        raise TypingEndpointAtlasObserverV1Error(
            f"{label} does not use canonical joint order"
        )
    result = {}
    for name in ARM_JOINT_NAMES:
        raw = value[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypingEndpointAtlasObserverV1Error(f"{label}.{name} differs")
        result[name] = float(raw)
    try:
        _canonical(result)
    except ValueError as exc:
        raise TypingEndpointAtlasObserverV1Error(
            f"{label} contains a nonfinite value"
        ) from exc
    return result


class TypingEndpointAtlasRecorderV1:
    """Observe accepted phase endpoints after the canonical IK decision."""

    def __init__(self, route_id: str, *, maximum_samples: int = 4096) -> None:
        self._route_id = _identifier(route_id, "route_id")
        if (
            isinstance(maximum_samples, bool)
            or not isinstance(maximum_samples, int)
            or not 1 <= maximum_samples <= 4096
        ):
            raise TypingEndpointAtlasObserverV1Error(
                "maximum_samples must be in [1, 4096]"
            )
        self._maximum_samples = maximum_samples
        self._observed_samples = 0
        self._endpoints: list[dict[str, Any]] = []

    def observe(
        self, sample: TypingScreeningSampleV1,
        evaluated: JointTrajectoryWaypointResult, *,
        incoming_joint_positions_rad: Mapping[str, float],
        solver_input_sha256: str,
    ) -> None:
        if self._observed_samples >= self._maximum_samples:
            raise TypingEndpointAtlasObserverV1Error(
                "endpoint observation sample bound exceeded"
            )
        if not isinstance(sample, TypingScreeningSampleV1):
            raise TypeError("sample must be TypingScreeningSampleV1")
        if not isinstance(evaluated, JointTrajectoryWaypointResult):
            raise TypeError("evaluated must be JointTrajectoryWaypointResult")
        if sample.sequence != self._observed_samples:
            raise TypingEndpointAtlasObserverV1Error(
                "endpoint observation sequence differs"
            )
        if evaluated.waypoint_sequence != sample.sequence:
            raise TypingEndpointAtlasObserverV1Error(
                "sample and evaluated waypoint differ"
            )
        self._observed_samples += 1
        if not sample.phase_endpoint or not evaluated.accepted:
            return
        incoming = _joint_state(
            incoming_joint_positions_rad, "incoming_joint_positions_rad"
        )
        solved = _joint_state(
            dict(evaluated.solution_arm_joint_positions_rad),
            "solution_joint_positions_rad",
        )
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
        self._endpoints.append({
            "sequence": len(self._endpoints),
            "sample_sequence": sample.sequence,
            "endpoint_sequence": sample.endpoint_sequence,
            "action_index": sample.action_index,
            **endpoint_core,
            "endpoint_sha256": _sha(endpoint_core),
            "solver_input_sha256": _digest(
                solver_input_sha256, "solver input"
            ),
            "incoming_joint_state_sha256": _sha(incoming),
            "solution_joint_state_sha256": _sha(solved),
        })

    def build(
        self, *, typing_trajectory_plan_sha256: str,
        typing_trajectory_ik_screen_sha256: str,
    ) -> dict[str, Any]:
        endpoints = [dict(item) for item in self._endpoints]
        grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for item in endpoints:
            entry = grouped.setdefault(item["endpoint_sha256"], {
                "endpoint_sha256": item["endpoint_sha256"],
                "phase": item["phase"],
                "target_id": item["target_id"],
                "point_board_mm": item["point_board_mm"],
                "observation_count": 0,
                "solution_joint_state_sha256s": [],
            })
            entry["observation_count"] += 1
            if item["solution_joint_state_sha256"] not in (
                entry["solution_joint_state_sha256s"]
            ):
                entry["solution_joint_state_sha256s"].append(
                    item["solution_joint_state_sha256"]
                )
        atlas = []
        for entry in grouped.values():
            solutions = sorted(entry["solution_joint_state_sha256s"])
            atlas.append({
                **entry,
                "solution_joint_state_sha256s": solutions,
                "solution_variant_count": len(solutions),
                "stable_solution_observed": len(solutions) == 1,
            })
        transitions: OrderedDict[tuple[str, str], int] = OrderedDict()
        for left, right in zip(endpoints, endpoints[1:]):
            key = (left["endpoint_sha256"], right["endpoint_sha256"])
            transitions[key] = transitions.get(key, 0) + 1
        transition_atlas = [
            {
                "source_endpoint_sha256": source,
                "destination_endpoint_sha256": destination,
                "observation_count": count,
            }
            for (source, destination), count in transitions.items()
        ]
        core = {
            "schema": SCHEMA,
            "route_id": self._route_id,
            "typing_trajectory_plan_sha256": _digest(
                typing_trajectory_plan_sha256, "trajectory plan"
            ),
            "typing_trajectory_ik_screen_sha256": _digest(
                typing_trajectory_ik_screen_sha256, "IK screen"
            ),
            "observed_sample_count": self._observed_samples,
            "endpoint_observation_count": len(endpoints),
            "unique_endpoint_count": len(atlas),
            "repeated_endpoint_observation_count": len(endpoints) - len(atlas),
            "stable_endpoint_count": sum(
                item["stable_solution_observed"] for item in atlas
            ),
            "variable_endpoint_count": sum(
                not item["stable_solution_observed"] for item in atlas
            ),
            "transition_observation_count": max(0, len(endpoints) - 1),
            "unique_transition_count": len(transition_atlas),
            "endpoint_observations": endpoints,
            "endpoint_atlas": atlas,
            "transition_atlas": transition_atlas,
            "atlas_use_authorized": False,
            "decision_input": False,
            "timing_used_for_admission": False,
            "controller_commands": [],
            "hardware_commands_generated": 0,
            "hardware_access": False,
            "physical_authority": False,
        }
        return {**core, "endpoint_atlas_observation_sha256": _sha(core)}


def parse_typing_endpoint_atlas_observation_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingEndpointAtlasObserverV1Error("observation fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("endpoint_atlas_observation_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingEndpointAtlasObserverV1Error("observation hash differs")
    if value.get("schema") != SCHEMA:
        raise TypingEndpointAtlasObserverV1Error("observation schema differs")
    _identifier(value.get("route_id"), "route_id")
    _digest(value.get("typing_trajectory_plan_sha256"), "trajectory plan")
    _digest(value.get("typing_trajectory_ik_screen_sha256"), "IK screen")
    numeric = (
        "observed_sample_count", "endpoint_observation_count",
        "unique_endpoint_count", "repeated_endpoint_observation_count",
        "stable_endpoint_count", "variable_endpoint_count",
        "transition_observation_count", "unique_transition_count",
    )
    if any(
        isinstance(value.get(field), bool)
        or not isinstance(value.get(field), int)
        or value[field] < 0
        for field in numeric
    ):
        raise TypingEndpointAtlasObserverV1Error("observation counts differ")
    observations = value.get("endpoint_observations")
    atlas = value.get("endpoint_atlas")
    transitions = value.get("transition_atlas")
    if not all(isinstance(item, list) for item in (observations, atlas, transitions)):
        raise TypingEndpointAtlasObserverV1Error("atlas collections differ")
    if len(observations) > value["observed_sample_count"]:
        raise TypingEndpointAtlasObserverV1Error("endpoint sample counts differ")
    endpoint_ids = []
    solution_groups: OrderedDict[str, set[str]] = OrderedDict()
    counts: OrderedDict[str, int] = OrderedDict()
    for sequence, item in enumerate(observations):
        if (
            not isinstance(item, Mapping) or set(item) != _OBSERVATION_FIELDS
            or item.get("sequence") != sequence
        ):
            raise TypingEndpointAtlasObserverV1Error(
                "endpoint observation sequence differs"
            )
        endpoint = _digest(item.get("endpoint_sha256"), "endpoint")
        endpoint_core = {
            "phase": item.get("phase"),
            "target_id": item.get("target_id"),
            "point_board_mm": item.get("point_board_mm"),
        }
        if _sha(endpoint_core) != endpoint:
            raise TypingEndpointAtlasObserverV1Error(
                "endpoint observation identity differs"
            )
        _digest(item.get("solver_input_sha256"), "solver input")
        _digest(item.get("incoming_joint_state_sha256"), "incoming state")
        solution = _digest(
            item.get("solution_joint_state_sha256"), "solution state"
        )
        endpoint_ids.append(endpoint)
        counts[endpoint] = counts.get(endpoint, 0) + 1
        solution_groups.setdefault(endpoint, set()).add(solution)
    expected_transitions: OrderedDict[tuple[str, str], int] = OrderedDict()
    for source, destination in zip(endpoint_ids, endpoint_ids[1:]):
        key = (source, destination)
        expected_transitions[key] = expected_transitions.get(key, 0) + 1
    observed_transition_map = OrderedDict()
    for item in transitions:
        if not isinstance(item, Mapping) or set(item) != _TRANSITION_FIELDS:
            raise TypingEndpointAtlasObserverV1Error("transition differs")
        source = _digest(item.get("source_endpoint_sha256"), "source endpoint")
        destination = _digest(
            item.get("destination_endpoint_sha256"), "destination endpoint"
        )
        count = item.get("observation_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise TypingEndpointAtlasObserverV1Error("transition count differs")
        observed_transition_map[(source, destination)] = count
    if observed_transition_map != expected_transitions:
        raise TypingEndpointAtlasObserverV1Error("transition atlas differs")
    atlas_ids = []
    stable = 0
    for item in atlas:
        if not isinstance(item, Mapping) or set(item) != _ATLAS_FIELDS:
            raise TypingEndpointAtlasObserverV1Error("endpoint atlas differs")
        endpoint = _digest(item.get("endpoint_sha256"), "atlas endpoint")
        solutions = item.get("solution_joint_state_sha256s")
        if not isinstance(solutions, list) or solutions != sorted(set(solutions)):
            raise TypingEndpointAtlasObserverV1Error("solution variants differ")
        for solution in solutions:
            _digest(solution, "atlas solution")
        observed_stable = len(solutions) == 1
        if (
            item.get("observation_count") != counts.get(endpoint)
            or set(solutions) != solution_groups.get(endpoint)
            or item.get("solution_variant_count") != len(solutions)
            or item.get("stable_solution_observed") is not observed_stable
        ):
            raise TypingEndpointAtlasObserverV1Error("endpoint atlas differs")
        first = observations[endpoint_ids.index(endpoint)]
        if any(
            item.get(field) != first.get(field)
            for field in ("phase", "target_id", "point_board_mm")
        ):
            raise TypingEndpointAtlasObserverV1Error(
                "endpoint atlas metadata differs"
            )
        stable += observed_stable
        atlas_ids.append(endpoint)
    if atlas_ids != list(counts):
        raise TypingEndpointAtlasObserverV1Error("endpoint atlas order differs")
    endpoint_count = len(observations)
    unique_count = len(counts)
    expected_counts = {
        "endpoint_observation_count": endpoint_count,
        "unique_endpoint_count": unique_count,
        "repeated_endpoint_observation_count": endpoint_count - unique_count,
        "stable_endpoint_count": stable,
        "variable_endpoint_count": unique_count - stable,
        "transition_observation_count": max(0, endpoint_count - 1),
        "unique_transition_count": len(expected_transitions),
    }
    if any(value.get(field) != expected for field, expected in expected_counts.items()):
        raise TypingEndpointAtlasObserverV1Error("atlas aggregate counts differ")
    if (
        value.get("atlas_use_authorized") is not False
        or value.get("decision_input") is not False
        or value.get("timing_used_for_admission") is not False
        or value.get("controller_commands") != []
        or value.get("hardware_commands_generated") != 0
        or value.get("hardware_access") is not False
        or value.get("physical_authority") is not False
    ):
        raise TypingEndpointAtlasObserverV1Error(
            "endpoint observation violates zero authority"
        )
    return value


__all__ = [
    "SCHEMA", "TypingEndpointAtlasObserverV1Error",
    "TypingEndpointAtlasRecorderV1",
    "parse_typing_endpoint_atlas_observation_v1",
]
