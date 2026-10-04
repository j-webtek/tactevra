"""Strict representative-corpus campaign for typing endpoint observations."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .operational_latency_reference_v1 import (
    validate_operational_benchmark_environment_v1,
)
from .typing_endpoint_atlas_observer_v1 import (
    TypingEndpointAtlasObserverV1Error,
    parse_typing_endpoint_atlas_observation_v1,
)


SCHEMA = "rocell.typing_endpoint_atlas_campaign.v1"
CASE_IDS = (
    "home-transition",
    "word-robot",
    "repeat-number-punctuation",
    "alphabetic-extremes",
    "number-space-enter",
)
CASE_TARGETS = {
    "home-transition": ("H", "I"),
    "word-robot": ("R", "O", "B", "O", "T"),
    "repeat-number-punctuation": ("H", "H", "1", "PERIOD"),
    "alphabetic-extremes": ("A", "Z"),
    "number-space-enter": ("1", "SPACE", "ENTER"),
}
_HASH = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "schema", "campaign_id", "evidence_class", "environment", "case_count",
    "cases", "aggregate", "all_cases_passed", "decision_hashes_unchanged",
    "atlas_use_authorized", "warm_start_authorized",
    "diagnostics_used_for_admission", "performance_authority",
    "controller_opened", "transport_opened", "controller_commands",
    "hardware_writes", "physical_movements", "physical_authority",
    "campaign_sha256",
}
_CASE_FIELDS = {
    "case_id", "target_ids", "status", "reference_receipt_sha256",
    "observed_receipt_sha256", "receipt_matches_reference", "observation",
}
_AGGREGATE_FIELDS = {
    "route_count", "observed_sample_count", "endpoint_observation_count",
    "unique_endpoint_count", "repeated_endpoint_observation_count",
    "repeated_endpoint_identity_count", "stable_endpoint_count",
    "variable_endpoint_count", "stable_reuse_candidate_count",
    "variable_reuse_candidate_count", "maximum_solution_variant_count",
    "transition_observation_count", "unique_transition_count",
    "repeated_transition_identity_count", "endpoint_atlas", "transition_atlas",
}


class TypingEndpointAtlasCampaignV1Error(ValueError):
    """Atlas campaign evidence is incomplete, inconsistent, or authoritative."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingEndpointAtlasCampaignV1Error(
            f"{label} is not a SHA-256 digest"
        )
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 192
        or value != value.strip() or ":\\" in value or "://" in value
        or value.startswith(("/", "\\"))
    ):
        raise TypingEndpointAtlasCampaignV1Error(
            f"{label} is invalid or path-like"
        )
    return value


def _aggregate(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    endpoints: OrderedDict[str, dict[str, Any]] = OrderedDict()
    transitions: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
    observed_samples = 0
    endpoint_observations = 0
    transition_observations = 0
    for observation in observations:
        route_id = observation["route_id"]
        observed_samples += observation["observed_sample_count"]
        route_endpoints = observation["endpoint_observations"]
        endpoint_observations += len(route_endpoints)
        for item in route_endpoints:
            identity = item["endpoint_sha256"]
            entry = endpoints.setdefault(identity, {
                "endpoint_sha256": identity,
                "phase": item["phase"],
                "target_id": item["target_id"],
                "point_board_mm": item["point_board_mm"],
                "observation_count": 0,
                "route_ids": [],
                "solution_joint_state_sha256s": [],
            })
            if any(
                entry[field] != item[field]
                for field in ("phase", "target_id", "point_board_mm")
            ):
                raise TypingEndpointAtlasCampaignV1Error(
                    "endpoint hash maps to inconsistent metadata"
                )
            entry["observation_count"] += 1
            if route_id not in entry["route_ids"]:
                entry["route_ids"].append(route_id)
            solution = item["solution_joint_state_sha256"]
            if solution not in entry["solution_joint_state_sha256s"]:
                entry["solution_joint_state_sha256s"].append(solution)
        for left, right in zip(route_endpoints, route_endpoints[1:]):
            key = (left["endpoint_sha256"], right["endpoint_sha256"])
            entry = transitions.setdefault(key, {
                "source_endpoint_sha256": key[0],
                "destination_endpoint_sha256": key[1],
                "observation_count": 0,
                "route_ids": [],
            })
            entry["observation_count"] += 1
            if route_id not in entry["route_ids"]:
                entry["route_ids"].append(route_id)
            transition_observations += 1
    endpoint_atlas = []
    for entry in endpoints.values():
        routes = sorted(entry["route_ids"])
        solutions = sorted(entry["solution_joint_state_sha256s"])
        endpoint_atlas.append({
            **entry,
            "route_ids": routes,
            "route_count": len(routes),
            "solution_joint_state_sha256s": solutions,
            "solution_variant_count": len(solutions),
            "stable_solution_observed": len(solutions) == 1,
            "reuse_candidate_observed": entry["observation_count"] > 1,
        })
    transition_atlas = []
    for entry in transitions.values():
        routes = sorted(entry["route_ids"])
        transition_atlas.append({
            **entry, "route_ids": routes, "route_count": len(routes),
        })
    repeated_endpoints = [
        item for item in endpoint_atlas if item["observation_count"] > 1
    ]
    stable_endpoints = [
        item for item in endpoint_atlas if item["stable_solution_observed"]
    ]
    return {
        "route_count": len(observations),
        "observed_sample_count": observed_samples,
        "endpoint_observation_count": endpoint_observations,
        "unique_endpoint_count": len(endpoint_atlas),
        "repeated_endpoint_observation_count": (
            endpoint_observations - len(endpoint_atlas)
        ),
        "repeated_endpoint_identity_count": len(repeated_endpoints),
        "stable_endpoint_count": len(stable_endpoints),
        "variable_endpoint_count": len(endpoint_atlas) - len(stable_endpoints),
        "stable_reuse_candidate_count": sum(
            item["stable_solution_observed"] for item in repeated_endpoints
        ),
        "variable_reuse_candidate_count": sum(
            not item["stable_solution_observed"] for item in repeated_endpoints
        ),
        "maximum_solution_variant_count": max(
            (item["solution_variant_count"] for item in endpoint_atlas),
            default=0,
        ),
        "transition_observation_count": transition_observations,
        "unique_transition_count": len(transition_atlas),
        "repeated_transition_identity_count": sum(
            item["observation_count"] > 1 for item in transition_atlas
        ),
        "endpoint_atlas": endpoint_atlas,
        "transition_atlas": transition_atlas,
    }


def build_typing_endpoint_atlas_campaign_v1(
    cases: Sequence[Mapping[str, Any]], *, campaign_id: str,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
        raise TypingEndpointAtlasCampaignV1Error("cases are not a sequence")
    if len(cases) != len(CASE_IDS):
        raise TypingEndpointAtlasCampaignV1Error("case count differs")
    normalized = []
    observations = []
    for index, item in enumerate(cases):
        if not isinstance(item, Mapping) or set(item) != _CASE_FIELDS:
            raise TypingEndpointAtlasCampaignV1Error("case fields differ")
        case_id = item.get("case_id")
        if case_id != CASE_IDS[index]:
            raise TypingEndpointAtlasCampaignV1Error("case order differs")
        target_ids = item.get("target_ids")
        if target_ids != list(CASE_TARGETS[case_id]):
            raise TypingEndpointAtlasCampaignV1Error("case targets differ")
        reference = _digest(
            item.get("reference_receipt_sha256"), "reference receipt"
        )
        observed = _digest(
            item.get("observed_receipt_sha256"), "observed receipt"
        )
        if (
            item.get("status") != "PASS"
            or item.get("receipt_matches_reference") is not True
            or observed != reference
        ):
            raise TypingEndpointAtlasCampaignV1Error(
                f"{case_id} decision receipt differs"
            )
        try:
            observation = dict(parse_typing_endpoint_atlas_observation_v1(
                item.get("observation")
            ))
        except TypingEndpointAtlasObserverV1Error as exc:
            raise TypingEndpointAtlasCampaignV1Error(
                f"{case_id} observation is invalid: {exc}"
            ) from exc
        if observation["route_id"] != case_id:
            raise TypingEndpointAtlasCampaignV1Error(
                f"{case_id} route identity differs"
            )
        normalized.append({
            "case_id": case_id,
            "target_ids": list(target_ids),
            "status": "PASS",
            "reference_receipt_sha256": reference,
            "observed_receipt_sha256": observed,
            "receipt_matches_reference": True,
            "observation": observation,
        })
        observations.append(observation)
    aggregate = _aggregate(observations)
    core = {
        "schema": SCHEMA,
        "campaign_id": _identifier(campaign_id, "campaign_id"),
        "evidence_class": "HOST_MEASURED_OFFLINE",
        "environment": validate_operational_benchmark_environment_v1(environment),
        "case_count": len(normalized),
        "cases": normalized,
        "aggregate": aggregate,
        "all_cases_passed": True,
        "decision_hashes_unchanged": True,
        "atlas_use_authorized": False,
        "warm_start_authorized": False,
        "diagnostics_used_for_admission": False,
        "performance_authority": False,
        "controller_opened": False,
        "transport_opened": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "campaign_sha256": _sha(core)}


def parse_typing_endpoint_atlas_campaign_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingEndpointAtlasCampaignV1Error("campaign fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("campaign_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingEndpointAtlasCampaignV1Error("campaign hash differs")
    if not isinstance(value.get("aggregate"), Mapping) or set(
        value["aggregate"]
    ) != _AGGREGATE_FIELDS:
        raise TypingEndpointAtlasCampaignV1Error("aggregate fields differ")
    rebuilt = build_typing_endpoint_atlas_campaign_v1(
        value.get("cases"), campaign_id=value.get("campaign_id"),
        environment=value.get("environment"),
    )
    if rebuilt != dict(value):
        raise TypingEndpointAtlasCampaignV1Error(
            "campaign derivation or authority fields differ"
        )
    return value


__all__ = [
    "CASE_IDS", "CASE_TARGETS", "SCHEMA",
    "TypingEndpointAtlasCampaignV1Error",
    "build_typing_endpoint_atlas_campaign_v1",
    "parse_typing_endpoint_atlas_campaign_v1",
]
