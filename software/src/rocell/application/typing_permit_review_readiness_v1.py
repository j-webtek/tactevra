"""Fail-closed readiness map from retained typing plans to physical review.

The shadow pipeline intentionally stops before physical qualification.  This
module makes that boundary machine-readable: it validates the exact retained
five-stage bundle, records what is already available, and names every adapter
that must still bind physical-original evidence before the existing
``single_action_execution_review_v1`` boundary may be called.

It does not accept caller assertions that evidence exists.  Later adapters must
consume and authenticate the actual evidence types.  Consequently this v1
report can only be blocked and can never issue a review, permit, or command.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .typing_shadow_materialization_v1 import (
    STAGES,
    STAGE_HASH_FIELDS,
    parse_typing_shadow_materialization_v1,
)


SCHEMA = "rocell.typing_permit_review_readiness.v1"
STATUS = "BLOCKED_PHYSICAL_REVIEW_PREREQUISITES_REQUIRED"
SATISFIED = (
    "EXACT_SHADOW_PIPELINE_RECEIPT_RETAINED",
    "FIVE_PLANNING_STAGE_BODIES_RETAINED",
    "PLANNING_STAGE_HASH_LINEAGE_VERIFIED",
)
BASE_BLOCKERS = (
    "DEPLOYMENT_QUALIFIED_PLAN_REQUIRED",
    "MEASURED_TRAJECTORY_ENVELOPE_REQUIRED",
    "CONTINUOUS_COLLISION_QUALIFICATION_REQUIRED",
    "FRESH_OBSERVED_START_STATE_REQUIRED",
    "FRESH_INSTALLED_CONTROLLER_QUALIFICATION_REQUIRED",
    "INDEPENDENT_EFFECT_VERIFIER_REQUIRED",
    "PER_ACTION_REVIEW_BINDINGS_REQUIRED",
)
ADAPTERS = {
    "DEPLOYMENT_QUALIFIED_PLAN_REQUIRED": (
        "qualified_model_motion_batch_to_execution_plan"
    ),
    "MEASURED_TRAJECTORY_ENVELOPE_REQUIRED": "trajectory_execution_envelope_v2",
    "INSTALLED_COLLISION_PROFILE_REQUIRED": "installed_collision_geometry",
    "CONTINUOUS_COLLISION_QUALIFICATION_REQUIRED": (
        "conservative_segment_sweep_qualification"
    ),
    "FRESH_OBSERVED_START_STATE_REQUIRED": "observed_planner_start_state",
    "FRESH_INSTALLED_CONTROLLER_QUALIFICATION_REQUIRED": (
        "installed_controller_qualification_v1"
    ),
    "INDEPENDENT_EFFECT_VERIFIER_REQUIRED": (
        "independent_effect_verifier_binding"
    ),
    "PER_ACTION_REVIEW_BINDINGS_REQUIRED": "single_action_execution_review_v1",
}
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "schema",
    "status",
    "request_id",
    "materialization_sha256",
    "shadow_pipeline_sha256",
    "retained_stage_count",
    "retained_stage_hashes",
    "satisfied_prerequisites",
    "blockers",
    "next_required_adapters",
    "synthetic_materialization_accepted_for_execution",
    "permit_review_ready",
    "review_issued",
    "permit_issued",
    "eligible_for_executor",
    "automatic_retry_allowed",
    "controller_commands",
    "wire_commands",
    "hardware_commands_generated",
    "hardware_access",
    "physical_authority",
    "readiness_sha256",
}


class TypingPermitReviewReadinessV1Error(ValueError):
    """The retained planning bundle cannot support an exact readiness report."""


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
        raise TypingPermitReviewReadinessV1Error(
            "readiness value is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def assess_typing_permit_review_readiness_v1(
    materialization: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the exact non-authoritative gap between shadow and review.

    No optional evidence arguments are accepted deliberately.  Physical
    prerequisites become satisfied only when their typed adapters exist and
    authenticate their source records, rather than when a caller supplies a
    Boolean or digest.
    """

    if not isinstance(materialization, Mapping):
        raise TypeError("materialization must be a mapping")
    try:
        parsed = parse_typing_shadow_materialization_v1(materialization)
    except (TypeError, ValueError) as exc:
        raise TypingPermitReviewReadinessV1Error(
            "shadow materialization is invalid"
        ) from exc

    collision = parsed["stage_artifacts"]["typing_collision_intake"]
    blockers = list(BASE_BLOCKERS)
    if (
        collision.get("installed_collision_profile_sha256") is None
        or collision.get("status")
        == "BLOCKED_INSTALLED_COLLISION_PROFILE_REQUIRED"
    ):
        blockers.insert(2, "INSTALLED_COLLISION_PROFILE_REQUIRED")

    # A shadow collision intake must never be treated as continuous clearance.
    if collision.get("continuous_collision_proven") is not False:
        raise TypingPermitReviewReadinessV1Error(
            "shadow collision intake authority differs"
        )

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "request_id": parsed["request_id"],
        "materialization_sha256": parsed["materialization_sha256"],
        "shadow_pipeline_sha256": parsed["shadow_pipeline_sha256"],
        "retained_stage_count": len(STAGES),
        "retained_stage_hashes": dict(parsed["stage_hashes"]),
        "satisfied_prerequisites": list(SATISFIED),
        "blockers": blockers,
        "next_required_adapters": [
            {"blocker": blocker, "adapter": ADAPTERS[blocker]}
            for blocker in blockers
        ],
        "synthetic_materialization_accepted_for_execution": False,
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
    return {**core, "readiness_sha256": _sha(core)}


def parse_typing_permit_review_readiness_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one exact v1 blocked-readiness document."""

    if not isinstance(value, Mapping):
        raise TypingPermitReviewReadinessV1Error("readiness report is not an object")
    if set(value) != _FIELDS:
        raise TypingPermitReviewReadinessV1Error("readiness report fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("readiness_sha256", None)
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingPermitReviewReadinessV1Error("readiness hash differs")
    if (
        value.get("schema") != SCHEMA
        or value.get("status") != STATUS
        or not isinstance(value.get("request_id"), str)
        or not value["request_id"]
        or _SHA.fullmatch(value.get("materialization_sha256", "")) is None
        or _SHA.fullmatch(value.get("shadow_pipeline_sha256", "")) is None
        or value.get("retained_stage_count") != len(STAGES)
        or not isinstance(value.get("retained_stage_hashes"), Mapping)
        or set(value["retained_stage_hashes"]) != set(STAGE_HASH_FIELDS.values())
        or any(
            _SHA.fullmatch(digest or "") is None
            for digest in value["retained_stage_hashes"].values()
        )
        or value.get("satisfied_prerequisites") != list(SATISFIED)
        or not isinstance(value.get("blockers"), list)
        or not value["blockers"]
        or len(value["blockers"]) != len(set(value["blockers"]))
        or any(blocker not in ADAPTERS for blocker in value["blockers"])
        or value.get("next_required_adapters")
        != [
            {"blocker": blocker, "adapter": ADAPTERS[blocker]}
            for blocker in value["blockers"]
        ]
        or value.get("synthetic_materialization_accepted_for_execution") is not False
        or value.get("permit_review_ready") is not False
        or value.get("review_issued") is not False
        or value.get("permit_issued") is not False
        or value.get("eligible_for_executor") is not False
        or value.get("automatic_retry_allowed") is not False
        or value.get("controller_commands") != []
        or value.get("wire_commands") != []
        or value.get("hardware_commands_generated") != 0
        or value.get("hardware_access") is not False
        or value.get("physical_authority") is not False
    ):
        raise TypingPermitReviewReadinessV1Error(
            "readiness status, blockers, or authority differs"
        )
    return dict(value)


__all__ = [
    "ADAPTERS",
    "BASE_BLOCKERS",
    "SATISFIED",
    "SCHEMA",
    "STATUS",
    "TypingPermitReviewReadinessV1Error",
    "assess_typing_permit_review_readiness_v1",
    "parse_typing_permit_review_readiness_v1",
]
