"""Reconstruct one zero-authority C03 qualification receipt from ICQ-6/7.

This boundary consumes sealed compact artifacts only.  It does not replan,
evaluate geometry, create commands, or grant execution authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

from rocell.kinematics import ARM_JOINT_NAMES

from .c03_observed_route_entry_qualification_v1 import (
    CLEAR_STATUS as ENTRY_CLEAR,
    COLLISION_STATUS as ENTRY_COLLISION,
    INDETERMINATE_STATUS as ENTRY_INDETERMINATE,
    parse_c03_observed_route_entry_qualification_v1,
)
from .c03_partition_collision_evaluator_v1 import (
    CONTINUOUS_CLEAR_STATUS,
    CONTINUOUS_COLLISION_STATUS,
    CONTINUOUS_INDETERMINATE_STATUS,
    CONTINUOUS_SCHEMA,
)
from .c03_cable_envelope_intake_v1 import (
    READY_STATUS as CABLE_READY,
    REPORT_SCHEMA as CABLE_SCHEMA,
)
from .partitioned_typing_collision_intake_v1 import (
    READY_STATUS as INTAKE_READY,
    SCHEMA as INTAKE_SCHEMA,
)


SCHEMA = "tactevra.c03_aggregate_qualification_receipt.v1"
PASS = "PASS"
REJECT = "REJECT"
BLOCKED = "BLOCKED"

_HANDOFF_FIELDS = {
    "schema", "source_result_receipt_sha256", "source_route_receipt_sha256",
    "ordered_targets", "trajectory_sample_count", "collision_intake",
    "installed_collision_gate_cleared", "controller_commands",
    "hardware_commands_generated", "hardware_access", "hardware_writes",
    "physical_movements", "physical_authority", "c03_collision_handoff_sha256",
}
_CONTINUOUS_FIELDS = {
    "schema", "status", "continuous_method",
    "c03_cable_envelope_intake_report_sha256",
    "partition_collision_evaluation_sha256_values", "partition_count",
    "owned_segment_count", "segment_reports",
    "all_owned_segments_assigned_exactly_once",
    "cross_partition_boundary_rechecks_reproduced",
    "continuous_collision_proven_for_bound_geometry",
    "installed_physical_qualification_complete", "blockers",
    "indeterminate_reason", "controller_commands", "wire_commands",
    "hardware_commands_generated", "hardware_access", "hardware_writes",
    "physical_movements", "physical_authority",
    "c03_continuous_segment_qualification_sha256",
}
_OUTPUT_FIELDS = {
    "schema", "disposition", "reason", "source_result_receipt_sha256",
    "source_route_receipt_sha256", "c03_collision_handoff_sha256",
    "c03_observed_route_entry_qualification_sha256",
    "c03_cable_envelope_intake_report_sha256",
    "c03_continuous_segment_qualification_sha256",
    "installed_collision_profile_sha256", "collision_contract_sha256",
    "tool_configuration_sha256", "target_catalog_sha256",
    "calibration_snapshot_sha256", "build_snapshot_sha256",
    "kinematic_model_sha256", "observed_start_state_sha256",
    "controller_session_id", "ordered_targets", "partition_count",
    "entry_segment_count", "route_segment_count", "aggregate_segment_count",
    "entry_to_route_maximum_joint_difference_rad",
    "all_route_segments_covered_exactly_once",
    "partition_boundaries_reproduced", "observation_fresh_at_evaluation",
    "clearance_summary", "limitations", "required_next_evidence",
    "permit_review_ready", "eligible_for_executor", "automatic_retry_allowed",
    "controller_commands", "wire_commands", "hardware_commands_generated",
    "hardware_access", "hardware_writes", "physical_movements",
    "physical_authority", "c03_aggregate_qualification_receipt_sha256",
}


class C03AggregateQualificationReceiptV1Error(ValueError):
    """Sealed ICQ evidence is changed, crossed, duplicated, or malformed."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise C03AggregateQualificationReceiptV1Error(
            "aggregate evidence is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sealed(value: object, fields: set[str], hash_field: str, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise C03AggregateQualificationReceiptV1Error(f"{label} fields differ")
    document = dict(value)
    claimed = document.pop(hash_field, None)
    if not isinstance(claimed, str) or claimed != _sha(document):
        raise C03AggregateQualificationReceiptV1Error(f"{label} hash differs")
    return dict(value)


def _zero_authority(value: Mapping[str, Any], label: str) -> None:
    if (
        value.get("controller_commands") != []
        or value.get("wire_commands", []) != []
        or value.get("hardware_commands_generated", 0) != 0
        or value.get("hardware_access") is not False
        or value.get("hardware_writes", 0) != 0
        or value.get("physical_movements", 0) != 0
        or value.get("physical_authority") is not False
    ):
        raise C03AggregateQualificationReceiptV1Error(
            f"{label} carries or omits zero-authority evidence"
        )


def _joint_map(value: object, label: str) -> dict[str, float]:
    if not isinstance(value, Mapping) or set(value) != set(ARM_JOINT_NAMES):
        raise C03AggregateQualificationReceiptV1Error(
            f"{label} must exactly cover arm joints"
        )
    result = {name: float(value[name]) for name in ARM_JOINT_NAMES}
    if any(not math.isfinite(item) for item in result.values()):
        raise C03AggregateQualificationReceiptV1Error(f"{label} is not finite")
    return result


def _collision_pair(entry: Mapping[str, Any]) -> list[str] | None:
    candidates: list[Mapping[str, Any]] = []
    bounded = entry.get("bounded_collision_qualification")
    if isinstance(bounded, Mapping):
        fk = bounded.get("fk_collision_qualification")
        if isinstance(fk, Mapping):
            sequence = fk.get("collision_sequence")
            if isinstance(sequence, Mapping):
                for pose in sequence.get("pose_reports", []):
                    if isinstance(pose, Mapping):
                        candidates.extend(
                            item for item in pose.get("collisions", [])
                            if isinstance(item, Mapping)
                        )
    sweep = entry.get("continuous_sweep_qualification")
    if isinstance(sweep, Mapping):
        for segment in sweep.get("segment_reports", []):
            if isinstance(segment, Mapping):
                candidates.extend(
                    item for item in segment.get("collisions", [])
                    if isinstance(item, Mapping)
                )
    for item in candidates:
        first, second = item.get("first_body_id"), item.get("second_body_id")
        if isinstance(first, str) and isinstance(second, str):
            return [first, second]
    return None


def build_c03_aggregate_qualification_receipt_v1(
    entry_receipt: Mapping[str, Any],
    collision_handoff: Mapping[str, Any],
    cable_intake_report: Mapping[str, Any],
    continuous_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct exact entry plus continuous route evidence."""

    try:
        entry = parse_c03_observed_route_entry_qualification_v1(entry_receipt)
    except ValueError as exc:
        raise C03AggregateQualificationReceiptV1Error(
            f"observed entry receipt differs: {exc}"
        ) from exc
    handoff = _sealed(
        collision_handoff, _HANDOFF_FIELDS, "c03_collision_handoff_sha256",
        "collision handoff",
    )
    intake_raw = handoff["collision_intake"]
    if not isinstance(intake_raw, Mapping):
        raise C03AggregateQualificationReceiptV1Error("collision intake is absent")
    intake = dict(intake_raw)
    intake_digest = intake.pop("partitioned_typing_collision_intake_sha256", None)
    if (
        intake_raw.get("schema") != INTAKE_SCHEMA
        or intake_raw.get("status") != INTAKE_READY
        or intake_digest != _sha(intake)
    ):
        raise C03AggregateQualificationReceiptV1Error("collision intake differs")
    cable = dict(cable_intake_report) if isinstance(cable_intake_report, Mapping) else {}
    cable_digest = cable.pop("c03_cable_envelope_intake_report_sha256", None)
    if (
        cable_intake_report.get("schema") != CABLE_SCHEMA
        or cable_intake_report.get("status") != CABLE_READY
        or cable_digest != _sha(cable)
    ):
        raise C03AggregateQualificationReceiptV1Error("cable intake report differs")
    continuous = _sealed(
        continuous_receipt, _CONTINUOUS_FIELDS,
        "c03_continuous_segment_qualification_sha256", "continuous receipt",
    )
    if (
        handoff.get("schema") != "tactevra.c03_collision_handoff.v1"
        or continuous.get("schema") != CONTINUOUS_SCHEMA
        or continuous.get("status") not in {
            CONTINUOUS_CLEAR_STATUS,
            CONTINUOUS_COLLISION_STATUS,
            CONTINUOUS_INDETERMINATE_STATUS,
        }
    ):
        raise C03AggregateQualificationReceiptV1Error(
            "handoff or continuous receipt schema/status differs"
        )
    for value, label in ((entry, "entry"), (handoff, "handoff"),
                         (intake_raw, "intake"), (cable_intake_report, "cable"),
                         (continuous, "continuous")):
        _zero_authority(value, label)

    identity_pairs = (
        (entry["source_result_receipt_sha256"], handoff["source_result_receipt_sha256"]),
        (entry["source_route_receipt_sha256"], handoff["source_route_receipt_sha256"]),
        (entry["c03_collision_handoff_sha256"], handoff["c03_collision_handoff_sha256"]),
        (entry["installed_collision_profile_sha256"], intake_raw["installed_collision_profile_sha256"]),
        (entry["collision_contract_sha256"], intake_raw["collision_contract_sha256"]),
        (entry["calibration_snapshot_sha256"], intake_raw["calibration_snapshot_sha256"]),
        (entry["build_snapshot_sha256"], intake_raw["build_snapshot_sha256"]),
        (entry["kinematic_model_sha256"], intake_raw["kinematic_model_sha256"]),
        (cable_intake_report.get("partitioned_typing_collision_intake_sha256"), intake_digest),
        (cable_intake_report.get("installed_collision_profile_content_sha256"), intake_raw["installed_collision_profile_sha256"]),
        (cable_intake_report.get("collision_contract_sha256"), intake_raw["collision_contract_sha256"]),
        (continuous["c03_cable_envelope_intake_report_sha256"], cable_digest),
    )
    if any(left != right for left, right in identity_pairs):
        raise C03AggregateQualificationReceiptV1Error(
            "entry, route, profile, cable, or continuous lineage crosses"
        )
    if entry["sampling_policy"] != intake_raw["sampling_policy"]:
        raise C03AggregateQualificationReceiptV1Error("sampling policy differs")

    partitions = intake_raw.get("partitions")
    if not isinstance(partitions, list) or not partitions:
        raise C03AggregateQualificationReceiptV1Error("route partitions are absent")
    expected_segments: list[dict[str, Any]] = []
    previous_terminal: Mapping[str, float] | None = None
    for partition_index, partition in enumerate(partitions):
        if not isinstance(partition, Mapping) or partition.get("partition_index") != partition_index:
            raise C03AggregateQualificationReceiptV1Error("partition order differs")
        plan = partition.get("bounded_joint_sample_plan")
        if not isinstance(plan, list) or len(plan) < 2:
            raise C03AggregateQualificationReceiptV1Error("partition samples differ")
        first_joints = _joint_map(plan[0].get("joint_positions_rad"), "partition start")
        terminal_joints = _joint_map(plan[-1].get("joint_positions_rad"), "partition terminal")
        if previous_terminal is not None and first_joints != previous_terminal:
            raise C03AggregateQualificationReceiptV1Error("partition boundary joints differ")
        previous_terminal = terminal_joints
        for segment_index, (start, end) in enumerate(zip(plan, plan[1:])):
            expected_segments.append({
                "owned_segment_sequence": len(expected_segments),
                "partition_index": partition_index,
                "segment_sequence": segment_index,
                "start_sample_sha256": _sha(start),
                "end_sample_sha256": _sha(end),
            })
    entry_end = _joint_map(entry["route_entry_joint_positions_rad"], "entry endpoint")
    route_start = _joint_map(
        partitions[0]["bounded_joint_sample_plan"][0]["joint_positions_rad"],
        "route start",
    )
    boundary_delta = max(abs(entry_end[name] - route_start[name]) for name in ARM_JOINT_NAMES)
    if boundary_delta != 0.0:
        raise C03AggregateQualificationReceiptV1Error(
            "observed entry does not terminate at the exact route start"
        )

    segments = continuous.get("segment_reports")
    if not isinstance(segments, list) or len(segments) != len(expected_segments):
        raise C03AggregateQualificationReceiptV1Error("route segment coverage differs")
    clearances: list[dict[str, Any]] = []
    for expected, segment in zip(expected_segments, segments, strict=True):
        if not isinstance(segment, Mapping) or any(
            segment.get(field) != expected[field] for field in expected
        ):
            raise C03AggregateQualificationReceiptV1Error(
                "route segment identity or order differs"
            )
        value = segment.get("minimum_clearance_lower_bound_mm")
        pair = segment.get("limiting_body_pair")
        if (
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value)) or float(value) < 0.0
            or not isinstance(pair, list) or len(pair) != 2
            or any(not isinstance(item, str) or not item for item in pair)
        ):
            raise C03AggregateQualificationReceiptV1Error(
                "route clearance evidence differs"
            )
        clearances.append({
            "scope": "ROUTE_SEGMENT",
            "owned_segment_sequence": expected["owned_segment_sequence"],
            "minimum_clearance_lower_bound_mm": float(value),
            "limiting_body_pair": list(pair),
        })

    boundary_rows = cable_intake_report.get("boundary_rechecks")
    boundary_ok = (
        isinstance(boundary_rows, list)
        and cable_intake_report.get("boundary_recheck_count") == len(boundary_rows)
        and len(boundary_rows) == max(0, len(partitions) - 1)
        and all(isinstance(item, Mapping) and item.get("exact_match") is True for item in boundary_rows)
        and continuous["cross_partition_boundary_rechecks_reproduced"] is True
    )
    coverage_ok = (
        cable_intake_report.get("partition_count") == len(partitions)
        and cable_intake_report.get("owned_segment_count") == len(expected_segments)
        and continuous["partition_count"] == len(partitions)
        and continuous["owned_segment_count"] == len(expected_segments)
        and continuous["all_owned_segments_assigned_exactly_once"] is True
    )
    fresh = entry["evaluated_monotonic_ns"] <= entry[
        "observation_valid_until_monotonic_ns"
    ]
    entry_pair = _collision_pair(entry)
    if entry["status"] == ENTRY_COLLISION:
        aggregate_minimum, limiting_pair = 0.0, entry_pair
    else:
        limiting = min(clearances, key=lambda item: (
            item["minimum_clearance_lower_bound_mm"], item["limiting_body_pair"]
        ))
        aggregate_minimum = limiting["minimum_clearance_lower_bound_mm"]
        limiting_pair = limiting["limiting_body_pair"]

    collision = (
        entry["status"] == ENTRY_COLLISION
        or continuous["status"] == CONTINUOUS_COLLISION_STATUS
    )
    incomplete = (
        entry["status"] == ENTRY_INDETERMINATE
        or continuous["status"] == CONTINUOUS_INDETERMINATE_STATUS
        or not coverage_ok or not boundary_ok or not fresh
        or entry["status"] == ENTRY_CLEAR
    )
    if collision:
        disposition, reason = REJECT, "collision exists in entry or route evidence"
    elif incomplete:
        disposition, reason = BLOCKED, (
            "entry or route evidence is incomplete, stale, or lacks a numeric "
            "entry clearance margin"
        )
    elif entry["status"] == ENTRY_CLEAR and continuous["status"] == CONTINUOUS_CLEAR_STATUS:
        disposition, reason = PASS, "entry and every owned route segment are collision clear"
    else:
        disposition, reason = BLOCKED, "entry or route disposition is unsupported"

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "disposition": disposition,
        "reason": reason,
        "source_result_receipt_sha256": handoff["source_result_receipt_sha256"],
        "source_route_receipt_sha256": handoff["source_route_receipt_sha256"],
        "c03_collision_handoff_sha256": handoff["c03_collision_handoff_sha256"],
        "c03_observed_route_entry_qualification_sha256": entry["c03_observed_route_entry_qualification_sha256"],
        "c03_cable_envelope_intake_report_sha256": cable_digest,
        "c03_continuous_segment_qualification_sha256": continuous["c03_continuous_segment_qualification_sha256"],
        "installed_collision_profile_sha256": entry["installed_collision_profile_sha256"],
        "collision_contract_sha256": entry["collision_contract_sha256"],
        "tool_configuration_sha256": entry["tool_configuration_sha256"],
        "target_catalog_sha256": entry["target_catalog_sha256"],
        "calibration_snapshot_sha256": entry["calibration_snapshot_sha256"],
        "build_snapshot_sha256": entry["build_snapshot_sha256"],
        "kinematic_model_sha256": entry["kinematic_model_sha256"],
        "observed_start_state_sha256": entry["observed_start_state_sha256"],
        "controller_session_id": entry["controller_session_id"],
        "ordered_targets": list(handoff["ordered_targets"]),
        "partition_count": len(partitions),
        "entry_segment_count": entry["segment_count"],
        "route_segment_count": len(expected_segments),
        "aggregate_segment_count": entry["segment_count"] + len(expected_segments),
        "entry_to_route_maximum_joint_difference_rad": boundary_delta,
        "all_route_segments_covered_exactly_once": coverage_ok,
        "partition_boundaries_reproduced": boundary_ok,
        "observation_fresh_at_evaluation": fresh,
        "clearance_summary": {
            "minimum_clearance_lower_bound_mm": aggregate_minimum,
            "limiting_body_pair": limiting_pair,
            "route_segment_clearances": clearances,
            "entry_numeric_clearance_available": entry["status"] == ENTRY_COLLISION,
            "entry_clearance_rule": (
                "collision implies zero lower bound; clear ICQ-7 v1 evidence supplies "
                "collision status but no numeric entry margin"
            ),
        },
        "limitations": [
            "SIMULATION_ONLY_UNLESS_ALL_SOURCE_EVIDENCE_IS_PHYSICALLY_QUALIFIED",
            "ICQ7_V1_CLEAR_ENTRY_HAS_NO_NUMERIC_CLEARANCE_MARGIN",
            "QUALIFICATION_RECEIPT_HAS_NO_EXECUTION_AUTHORITY",
        ],
        "required_next_evidence": [
            "PHYSICAL_INSTALLED_PROFILE_REQUIRED",
            "FRESH_OBSERVED_STATE_REQUIRED_AT_USE",
            "PHYSICALLY_QUALIFIED_DYNAMICS_REQUIRED",
            "INDEPENDENT_EFFECT_VERIFIER_REQUIRED",
            "SEPARATE_EXECUTION_PERMIT_REQUIRED",
        ],
        "permit_review_ready": False,
        "eligible_for_executor": False,
        "automatic_retry_allowed": False,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "c03_aggregate_qualification_receipt_sha256": _sha(core)}


def parse_c03_aggregate_qualification_receipt_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    receipt = _sealed(
        value, _OUTPUT_FIELDS, "c03_aggregate_qualification_receipt_sha256",
        "aggregate receipt",
    )
    _zero_authority(receipt, "aggregate receipt")
    if (
        receipt.get("schema") != SCHEMA
        or receipt.get("disposition") not in {PASS, REJECT, BLOCKED}
        or receipt.get("permit_review_ready") is not False
        or receipt.get("eligible_for_executor") is not False
        or receipt.get("automatic_retry_allowed") is not False
        or receipt.get("aggregate_segment_count")
        != receipt.get("entry_segment_count") + receipt.get("route_segment_count")
    ):
        raise C03AggregateQualificationReceiptV1Error(
            "aggregate disposition, accounting, or gates differ"
        )
    return dict(value)


__all__ = [
    "SCHEMA", "PASS", "REJECT", "BLOCKED",
    "C03AggregateQualificationReceiptV1Error",
    "build_c03_aggregate_qualification_receipt_v1",
    "parse_c03_aggregate_qualification_receipt_v1",
]
