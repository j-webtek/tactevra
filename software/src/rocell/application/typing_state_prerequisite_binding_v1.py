"""Bind fresh observed and installed-controller state to one shadow plan.

This is the first typed ARM-146 prerequisite adapter.  It authenticates the
existing observed-state and installed-controller qualification objects against
one retained materialization and one controller session.  It removes exactly
two readiness blockers and leaves every unrelated physical gate closed.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .installed_controller_qualification_v1 import (
    EvidenceOrigin,
    InstalledControllerQualificationEvidenceV1,
    InstalledControllerQualificationReportV1,
    ReviewDisposition,
)
from .observed_planner_start_state import ObservedPlannerStartState
from .typing_permit_review_readiness_v1 import (
    BASE_BLOCKERS,
    assess_typing_permit_review_readiness_v1,
    parse_typing_permit_review_readiness_v1,
)
from .typing_shadow_materialization_v1 import parse_typing_shadow_materialization_v1


SCHEMA = "rocell.typing_state_prerequisite_binding.v1"
STATUS = "BLOCKED_REMAINING_PHYSICAL_REVIEW_PREREQUISITES"
RESOLVED = (
    "FRESH_OBSERVED_START_STATE_REQUIRED",
    "FRESH_INSTALLED_CONTROLLER_QUALIFICATION_REQUIRED",
)
_SHA = re.compile(r"^[0-9a-f]{64}$")
_MANDATORY_REMAINING = tuple(
    blocker for blocker in BASE_BLOCKERS if blocker not in RESOLVED
)
_ALLOWED_REMAINING = (
    _MANDATORY_REMAINING[:2]
    + ("INSTALLED_COLLISION_PROFILE_REQUIRED",)
    + _MANDATORY_REMAINING[2:]
)
_FIELDS = {
    "schema", "status", "request_id", "materialization_sha256",
    "permit_review_readiness_sha256", "observed_start_state_sha256",
    "installed_controller_evidence_sha256",
    "installed_controller_report_sha256", "calibration_snapshot_sha256",
    "controller_session_id", "evaluated_monotonic_ns",
    "resolved_blockers", "remaining_blockers", "permit_review_ready",
    "review_issued", "permit_issued", "eligible_for_executor",
    "automatic_retry_allowed", "controller_commands", "wire_commands",
    "hardware_commands_generated", "hardware_access", "physical_authority",
    "state_binding_sha256",
}


class TypingStatePrerequisiteBindingV1Error(ValueError):
    """State evidence is stale, crossed, unreviewed, or authoritative."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingStatePrerequisiteBindingV1Error(
            "state binding is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _positive_ns(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TypingStatePrerequisiteBindingV1Error(
            "evaluated_monotonic_ns must be positive"
        )
    return value


def bind_typing_state_prerequisites_v1(
    materialization: Mapping[str, Any],
    observed_start: ObservedPlannerStartState,
    controller_evidence: InstalledControllerQualificationEvidenceV1,
    controller_report: InstalledControllerQualificationReportV1,
    *,
    evaluated_monotonic_ns: int,
) -> dict[str, Any]:
    """Bind current state evidence without creating review or motion authority."""

    if not isinstance(materialization, Mapping):
        raise TypeError("materialization must be a mapping")
    if not isinstance(observed_start, ObservedPlannerStartState):
        raise TypeError("observed_start must be an ObservedPlannerStartState")
    if not isinstance(
        controller_evidence, InstalledControllerQualificationEvidenceV1
    ):
        raise TypeError("controller_evidence has the wrong type")
    if not isinstance(
        controller_report, InstalledControllerQualificationReportV1
    ):
        raise TypeError("controller_report has the wrong type")
    now = _positive_ns(evaluated_monotonic_ns)
    materialized = parse_typing_shadow_materialization_v1(materialization)
    readiness = assess_typing_permit_review_readiness_v1(materialized)
    parse_typing_permit_review_readiness_v1(readiness)

    ik = materialized["stage_artifacts"]["typing_trajectory_ik_screen"]
    calibration_sha = ik.get("calibration_snapshot_sha256")
    if (
        not isinstance(calibration_sha, str)
        or _SHA.fullmatch(calibration_sha) is None
        or observed_start.calibration_snapshot_sha256 != calibration_sha
    ):
        raise TypingStatePrerequisiteBindingV1Error(
            "observed state calibration differs from the retained plan"
        )
    if not (
        observed_start.available_monotonic_ns
        <= now
        <= observed_start.valid_until_monotonic_ns
    ):
        raise TypingStatePrerequisiteBindingV1Error(
            "observed planner start state is unavailable or stale"
        )
    if (
        controller_evidence.evidence_origin
        is not EvidenceOrigin.PHYSICAL_RETAINED_ORIGINALS
        or controller_evidence.review_disposition
        is not ReviewDisposition.INDEPENDENTLY_APPROVED
        or not (
            controller_evidence.captured_monotonic_ns
            <= now
            <= controller_evidence.valid_until_monotonic_ns
        )
    ):
        raise TypingStatePrerequisiteBindingV1Error(
            "installed controller evidence is unavailable, stale, or unapproved"
        )
    report = controller_report.to_dict()
    if (
        report["status"] != "READY_FOR_ZERO_WRITE_PROFILE_BINDING"
        or report["profile_binding_ready"] is not True
        or report["execution_authorized"] is not False
        or controller_report.qualification_evidence_sha256
        != controller_evidence.evidence_sha256
    ):
        raise TypingStatePrerequisiteBindingV1Error(
            "installed controller qualification is not ready or has crossed lineage"
        )
    if controller_evidence.controller_session_id != observed_start.controller_session_id:
        raise TypingStatePrerequisiteBindingV1Error(
            "observed and installed-controller sessions differ"
        )

    remaining = [
        blocker for blocker in readiness["blockers"] if blocker not in RESOLVED
    ]
    if len(remaining) != len(readiness["blockers"]) - len(RESOLVED):
        raise TypingStatePrerequisiteBindingV1Error(
            "readiness report does not contain the expected state blockers"
        )
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "request_id": materialized["request_id"],
        "materialization_sha256": materialized["materialization_sha256"],
        "permit_review_readiness_sha256": readiness["readiness_sha256"],
        "observed_start_state_sha256": observed_start.observed_start_state_sha256,
        "installed_controller_evidence_sha256": controller_evidence.evidence_sha256,
        "installed_controller_report_sha256": controller_report.report_sha256,
        "calibration_snapshot_sha256": calibration_sha,
        "controller_session_id": observed_start.controller_session_id,
        "evaluated_monotonic_ns": now,
        "resolved_blockers": list(RESOLVED),
        "remaining_blockers": remaining,
        "permit_review_ready": False,
        "review_issued": False,
        "permit_issued": False,
        "eligible_for_executor": False,
        "automatic_retry_allowed": False,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "state_binding_sha256": _sha(core)}


def parse_typing_state_prerequisite_binding_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a sealed, still-blocked state prerequisite binding."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingStatePrerequisiteBindingV1Error(
            "state prerequisite binding fields differ"
        )
    unsigned = dict(value)
    supplied = unsigned.pop("state_binding_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingStatePrerequisiteBindingV1Error("state binding hash differs")
    digests = (
        "materialization_sha256", "permit_review_readiness_sha256",
        "observed_start_state_sha256", "installed_controller_evidence_sha256",
        "installed_controller_report_sha256", "calibration_snapshot_sha256",
    )
    if (
        value["schema"] != SCHEMA
        or value["status"] != STATUS
        or not isinstance(value["request_id"], str)
        or not value["request_id"]
        or any(_SHA.fullmatch(value[field] or "") is None for field in digests)
        or not isinstance(value["controller_session_id"], str)
        or not value["controller_session_id"]
        or _positive_ns(value["evaluated_monotonic_ns"]) <= 0
        or value["resolved_blockers"] != list(RESOLVED)
        or tuple(value["remaining_blockers"])
        not in (_MANDATORY_REMAINING, _ALLOWED_REMAINING)
        or value["permit_review_ready"] is not False
        or value["review_issued"] is not False
        or value["permit_issued"] is not False
        or value["eligible_for_executor"] is not False
        or value["automatic_retry_allowed"] is not False
        or value["controller_commands"] != []
        or value["wire_commands"] != []
        or value["hardware_commands_generated"] != 0
        or value["hardware_access"] is not False
        or value["physical_authority"] is not False
    ):
        raise TypingStatePrerequisiteBindingV1Error(
            "state binding identity, blockers, or authority differs"
        )
    return dict(value)


__all__ = [
    "RESOLVED", "SCHEMA", "STATUS", "TypingStatePrerequisiteBindingV1Error",
    "bind_typing_state_prerequisites_v1",
    "parse_typing_state_prerequisite_binding_v1",
]
