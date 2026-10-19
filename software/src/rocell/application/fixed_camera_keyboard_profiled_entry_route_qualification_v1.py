"""Join one attachment profile's observed entry to its reconstructed route.

This boundary replays the complete 328-segment route reconstruction, selects
exactly one installed attachment profile, and binds an already-retained fresh
entry chain to the first route configuration.  It never observes hardware,
creates a controller command, or promotes physical authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

from .fixed_camera_keyboard_clearance_intake_v1 import SUPPORTED_PROFILES
from .fixed_camera_keyboard_profiled_partition_collision_evaluator_v1 import (
    STATUS_CLEAR as ROUTE_CLEAR,
    STATUS_COLLISION as ROUTE_COLLISION,
    STATUS_INCOMPLETE as ROUTE_INCOMPLETE,
)
from .fixed_camera_keyboard_profiled_route_clearance_reconstruction_v1 import (
    ZERO_AUTHORITY,
    reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1,
)
from .typing_observed_route_entry_coverage_v1 import (
    TypingObservedRouteEntryCoverageV1Error,
    parse_typing_observed_route_entry_coverage_v1,
)
from .typing_observed_route_entry_sweep_v1 import (
    CLEAR_STATUS as ENTRY_CLEAR,
    COLLISION_STATUS as ENTRY_COLLISION,
    INCOMPLETE_STATUS as ENTRY_INCOMPLETE,
    TypingObservedRouteEntrySweepV1Error,
    parse_typing_observed_route_entry_sweep_v1,
)
from .typing_observed_route_entry_v1 import (
    TypingObservedRouteEntryV1Error,
    parse_typing_observed_route_entry_v1,
)


SCHEMA = "rocell.fixed_camera_keyboard_profiled_entry_route_qualification.v1"
STATUS_PASS = "PROFILED_ENTRY_ROUTE_CLEARANCE_QUALIFIED_ZERO_AUTHORITY"
STATUS_REJECTED = "REJECTED_PROFILED_ENTRY_OR_ROUTE_COLLISION"
STATUS_BLOCKED = "BLOCKED_PROFILED_ENTRY_ROUTE_EVIDENCE_INCOMPLETE"


class FixedCameraKeyboardProfiledEntryRouteQualificationV1Error(ValueError):
    """Entry, route, profile, or retained lineage differs."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FixedCameraKeyboardProfiledEntryRouteQualificationV1Error(
            "entry-route qualification is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _entry_minimum(sweep: Mapping[str, Any]) -> tuple[float, dict[str, Any]]:
    nested = sweep.get("conservative_sweep_evaluation")
    if not isinstance(nested, Mapping):
        raise FixedCameraKeyboardProfiledEntryRouteQualificationV1Error(
            "entry sweep evaluation is absent"
        )
    reports = nested.get("segment_reports")
    if not isinstance(reports, list) or not reports:
        raise FixedCameraKeyboardProfiledEntryRouteQualificationV1Error(
            "entry sweep segment reports are absent"
        )
    minimum: float | None = None
    limiter: dict[str, Any] | None = None
    for sequence, report in enumerate(reports):
        if not isinstance(report, Mapping):
            raise FixedCameraKeyboardProfiledEntryRouteQualificationV1Error(
                "entry sweep segment report is malformed"
            )
        value = report.get("minimum_clearance_lower_bound_mm")
        pair = report.get("clearance_limiting_body_pair")
        if (
            report.get("segment_sequence") != sequence
            or report.get("clearance_lower_bound_status") != "CLEAR"
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0.0
            or not isinstance(pair, list)
            or len(pair) != 2
            or not all(isinstance(item, str) and item for item in pair)
        ):
            raise FixedCameraKeyboardProfiledEntryRouteQualificationV1Error(
                f"entry clearance report differs at segment {sequence}"
            )
        numeric = float(value)
        if minimum is None or numeric < minimum:
            minimum = numeric
            limiter = {"entry_segment_sequence": sequence, "body_pair": list(pair)}
    if (
        nested.get("minimum_clearance_lower_bound_mm") != minimum
        or nested.get("limiting_segment_sequence") != limiter["entry_segment_sequence"]
        or nested.get("limiting_body_pair") != limiter["body_pair"]
        or nested.get("all_segment_clearance_bounds_determinate") is not True
        or nested.get("all_conservative_segment_sweeps_clear") is not True
    ):
        raise FixedCameraKeyboardProfiledEntryRouteQualificationV1Error(
            "entry clearance aggregate differs"
        )
    return minimum, limiter


def qualify_fixed_camera_keyboard_profiled_entry_route_v1(
    partition_documents: Mapping[str, Mapping[str, Any]],
    collision_evaluation: Mapping[str, Any],
    active_profile: str,
    observed_route_entry: Mapping[str, Any] | None = None,
    observed_route_entry_sweep: Mapping[str, Any] | None = None,
    observed_route_entry_coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce a selected-profile PASS, REJECT, or BLOCKED receipt."""

    if active_profile not in SUPPORTED_PROFILES:
        raise FixedCameraKeyboardProfiledEntryRouteQualificationV1Error(
            "active_profile is not supported"
        )
    route = reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1(
        partition_documents, collision_evaluation
    )
    profile_evaluation = collision_evaluation["profiles"][active_profile]
    profile_status = profile_evaluation["status"]
    selected = route["profiles"][active_profile]
    document = partition_documents[active_profile]
    route_start = document["partitions"][0]["bounded_joint_sample_plan"][0][
        "joint_positions_rad"
    ]

    entry = sweep = coverage = None
    entry_minimum: float | None = None
    entry_limiter: dict[str, Any] | None = None
    entry_bound = False
    continuity = False
    coverage_bound = False
    blockers: list[str] = []

    supplied = (
        observed_route_entry is not None,
        observed_route_entry_sweep is not None,
        observed_route_entry_coverage is not None,
    )
    if any(supplied):
        if observed_route_entry is None:
            blockers.append("FRESH_OBSERVED_ROUTE_ENTRY_REQUIRED")
        else:
            try:
                entry = parse_typing_observed_route_entry_v1(observed_route_entry)
            except (TypeError, TypingObservedRouteEntryV1Error) as exc:
                raise FixedCameraKeyboardProfiledEntryRouteQualificationV1Error(
                    str(exc)
                ) from exc
        if observed_route_entry_sweep is None:
            blockers.append("OBSERVED_ENTRY_CONTINUOUS_SWEEP_REQUIRED")
        else:
            try:
                sweep = parse_typing_observed_route_entry_sweep_v1(
                    observed_route_entry_sweep
                )
            except (TypeError, TypingObservedRouteEntrySweepV1Error) as exc:
                raise FixedCameraKeyboardProfiledEntryRouteQualificationV1Error(
                    str(exc)
                ) from exc
        if observed_route_entry_coverage is not None:
            try:
                coverage = parse_typing_observed_route_entry_coverage_v1(
                    observed_route_entry_coverage
                )
            except (TypeError, TypingObservedRouteEntryCoverageV1Error) as exc:
                raise FixedCameraKeyboardProfiledEntryRouteQualificationV1Error(
                    str(exc)
                ) from exc
    else:
        blockers.append("FRESH_OBSERVED_START_AND_ENTRY_QUALIFICATION_REQUIRED")

    if entry is not None and sweep is not None:
        if (
            sweep["observed_route_entry_sha256"] != entry["observed_route_entry_sha256"]
            or sweep["request_id"] != entry["request_id"]
            or sweep["materialization_sha256"] != entry["materialization_sha256"]
            or sweep["controller_session_id"] != entry["controller_session_id"]
            or sweep["calibration_snapshot_sha256"]
            != entry["calibration_snapshot_sha256"]
            or sweep["build_snapshot_sha256"] != entry["build_snapshot_sha256"]
            or entry["calibration_snapshot_sha256"]
            != route["calibration_snapshot_sha256"]
            or entry["build_snapshot_sha256"] != route["build_snapshot_sha256"]
            or sweep["installed_collision_profile_sha256"]
            != selected["installed_collision_profile_sha256"]
        ):
            raise FixedCameraKeyboardProfiledEntryRouteQualificationV1Error(
                "entry, route, profile, build, calibration, or session lineage differs"
            )
        entry_bound = True
        continuity = entry["entry_joint_positions_rad"] == route_start
        if not continuity:
            blockers.append("OBSERVED_ENTRY_ROUTE_START_JOINT_MISMATCH")
        if sweep["status"] == ENTRY_CLEAR:
            entry_minimum, entry_limiter = _entry_minimum(sweep)
            if coverage is None:
                blockers.append("OBSERVED_ENTRY_RETAINED_TELEMETRY_COVERAGE_REQUIRED")
            else:
                dynamics = coverage["observed_route_entry_tracking"][
                    "observed_route_entry_dynamics"
                ]
                if (
                    coverage["request_id"] != entry["request_id"]
                    or coverage["materialization_sha256"]
                    != entry["materialization_sha256"]
                    or coverage["controller_session_id"]
                    != entry["controller_session_id"]
                    or coverage["build_snapshot_sha256"]
                    != entry["build_snapshot_sha256"]
                    or dynamics["observed_route_entry_sha256"]
                    != entry["observed_route_entry_sha256"]
                    or dynamics["observed_route_entry_sweep_sha256"]
                    != sweep["observed_route_entry_sweep_sha256"]
                ):
                    raise FixedCameraKeyboardProfiledEntryRouteQualificationV1Error(
                        "retained entry coverage lineage differs"
                    )
                coverage_bound = True
        elif sweep["status"] == ENTRY_INCOMPLETE:
            blockers.append("OBSERVED_ENTRY_CONTINUOUS_SWEEP_INCOMPLETE")

    route_minimum = selected["minimum_clearance_lower_bound_mm"]
    minimum: float | None = None
    limiter: dict[str, Any] | None = None
    if entry_minimum is not None and route_minimum is not None:
        if entry_minimum <= route_minimum:
            minimum = entry_minimum
            limiter = {"phase": "ENTRY", **(entry_limiter or {})}
        else:
            minimum = route_minimum
            limiter = {
                "phase": "ROUTE",
                **(selected["limiting_route_segment"] or {}),
            }

    if profile_status == ROUTE_COLLISION or (
        sweep is not None and sweep["status"] == ENTRY_COLLISION
    ):
        status = STATUS_REJECTED
        disposition = "REJECT"
        blockers = [
            "SELECTED_PROFILE_ROUTE_COLLISION_DETECTED"
            if profile_status == ROUTE_COLLISION
            else "OBSERVED_ENTRY_COLLISION_DETECTED"
        ]
        next_stage = "CORRECT_SELECTED_PROFILE_ROUTE_OR_ENTRY"
    elif profile_status == ROUTE_INCOMPLETE:
        status = STATUS_BLOCKED
        disposition = "BLOCKED"
        blockers = ["SELECTED_PROFILE_ROUTE_CLEARANCE_EVIDENCE_INCOMPLETE"]
        next_stage = "SUPPLY_SELECTED_PROFILE_ROUTE_CLEARANCE_EVIDENCE"
    elif (
        profile_status == ROUTE_CLEAR
        and sweep is not None
        and sweep["status"] == ENTRY_CLEAR
        and coverage_bound
        and entry_bound
        and continuity
        and not blockers
    ):
        status = STATUS_PASS
        disposition = "PASS"
        next_stage = "INDEPENDENT_RELEASE_GATES_REMAIN"
    else:
        status = STATUS_BLOCKED
        disposition = "BLOCKED"
        next_stage = "COMPLETE_FRESH_SELECTED_PROFILE_ENTRY_EVIDENCE"

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "disposition": disposition,
        "active_profile": active_profile,
        "installed_collision_profile_sha256": selected[
            "installed_collision_profile_sha256"
        ],
        "profiled_route_clearance_reconstruction_sha256": route[
            "profiled_route_clearance_reconstruction_sha256"
        ],
        "observed_route_entry_sha256": (
            entry["observed_route_entry_sha256"] if entry is not None else None
        ),
        "observed_route_entry_sweep_sha256": (
            sweep["observed_route_entry_sweep_sha256"] if sweep is not None else None
        ),
        "observed_route_entry_coverage_sha256": (
            coverage["observed_route_entry_coverage_sha256"]
            if coverage is not None
            else None
        ),
        "calibration_snapshot_sha256": route["calibration_snapshot_sha256"],
        "build_snapshot_sha256": route["build_snapshot_sha256"],
        "route_segment_count": selected["route_segment_count"],
        "entry_sample_count": entry["sample_count"] if entry is not None else None,
        "entry_segment_count": (sweep["segment_count"] if sweep is not None else None),
        "route_minimum_clearance_lower_bound_mm": route_minimum,
        "entry_minimum_clearance_lower_bound_mm": entry_minimum,
        "minimum_clearance_lower_bound_mm": minimum,
        "limiting_entry_or_route_segment": limiter,
        "fresh_observed_entry_bound": entry_bound,
        "entry_route_joint_continuity_proven": continuity,
        "selected_profile_route_continuously_clear": profile_status == ROUTE_CLEAR,
        "observed_entry_continuously_clear": (
            sweep is not None and sweep["status"] == ENTRY_CLEAR
        ),
        "retained_entry_telemetry_coverage_qualified": coverage_bound,
        "profile_separation_preserved": True,
        "blockers": blockers,
        "next_required_stage": next_stage,
        "authority": dict(ZERO_AUTHORITY),
    }
    return {**core, "profiled_entry_route_qualification_sha256": _sha(core)}


__all__ = [
    "SCHEMA",
    "STATUS_PASS",
    "STATUS_REJECTED",
    "STATUS_BLOCKED",
    "FixedCameraKeyboardProfiledEntryRouteQualificationV1Error",
    "qualify_fixed_camera_keyboard_profiled_entry_route_v1",
]
