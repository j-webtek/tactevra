"""Strict zero-authority handoff from an admitted C03 route to collision intake."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .bounded_segment_collision_qualification import BoundedSegmentSamplingPolicy
from .context import SimulationContext
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .partitioned_typing_collision_intake_v1 import (
    prepare_partitioned_typing_collision_intake_v1,
)


SCHEMA = "tactevra.c03_collision_handoff.v1"
EXPECTED_DECISION = "PASS_C03_110MM_CANDIDATE_ROUTE_IK_CONTINUITY"
EXPECTED_TARGETS = ("H", "E", "L", "L", "O", "SPACE", "2", "0", "2", "6")


class C03RouteCollisionHandoffV1Error(ValueError):
    """C03 route evidence is incomplete, mutated, or authority bearing."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _verified_receipt(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    document = dict(value)
    claimed = document.pop(field, None)
    if not isinstance(claimed, str) or claimed != _sha256(document):
        raise C03RouteCollisionHandoffV1Error(f"invalid {field}")
    return dict(value)


def prepare_c03_route_collision_handoff_v1(
    result: Mapping[str, Any],
    context: SimulationContext,
    *,
    installed_profile: InstalledCollisionGeometryProfile | None = None,
    sampling_policy: BoundedSegmentSamplingPolicy | None = None,
    maximum_partitions: int = 64,
) -> dict[str, Any]:
    """Verify the exact route result and enumerate its collision partitions."""

    outer = _verified_receipt(result, "receipt_sha256")
    route_value = outer.get("route_result")
    if not isinstance(route_value, Mapping):
        raise C03RouteCollisionHandoffV1Error("route_result must be an object")
    route = _verified_receipt(route_value, "receipt_sha256")
    if (
        outer.get("decision") != EXPECTED_DECISION
        or route.get("decision") != EXPECTED_DECISION
        or tuple(route.get("ordered_targets", ())) != EXPECTED_TARGETS
        or route.get("canonical_ik_route_accepted") is not True
        or route.get("canonical_joint_continuity_accepted") is not True
        or route.get("trajectory_sample_count") != route.get("ik_accepted_sample_count")
        or route.get("collision_screen_executed") is not False
        or outer.get("collision_screen_executed") is not False
        or outer.get("installed_collision_gate_cleared") is not False
    ):
        raise C03RouteCollisionHandoffV1Error("C03 route admission contract differs")
    forbidden = (
        outer.get("hardware_writes"),
        outer.get("physical_movements"),
        outer.get("hardware_commands_generated"),
    )
    if outer.get("physical_authority") is not False or any(forbidden):
        raise C03RouteCollisionHandoffV1Error("C03 route carries physical authority")

    intake = prepare_partitioned_typing_collision_intake_v1(
        route["ik_screen"],
        context,
        expected_execution_plan_sha256=route["execution_plan_sha256"],
        expected_trajectory_plan_sha256=route["trajectory_plan_sha256"],
        expected_calibration_snapshot_sha256=route["calibration_snapshot_sha256"],
        installed_profile=installed_profile,
        sampling_policy=sampling_policy,
        maximum_partitions=maximum_partitions,
    )
    core = {
        "schema": SCHEMA,
        "source_result_receipt_sha256": outer["receipt_sha256"],
        "source_route_receipt_sha256": route["receipt_sha256"],
        "ordered_targets": list(EXPECTED_TARGETS),
        "trajectory_sample_count": route["trajectory_sample_count"],
        "collision_intake": intake,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "c03_collision_handoff_sha256": _sha256(core)}


__all__ = [
    "SCHEMA",
    "C03RouteCollisionHandoffV1Error",
    "prepare_c03_route_collision_handoff_v1",
]
