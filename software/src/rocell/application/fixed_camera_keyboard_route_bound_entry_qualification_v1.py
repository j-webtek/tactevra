"""Bind fresh ICQ-7 entry evidence to an exact reviewed route qualification.

PR #392 made the route collision evaluator conditional on independently
reviewed, profile-separated configuration-envelope evidence.  The older ICQ-7
entry join predates that boundary and can therefore be called directly from a
partition evaluation.  This adapter closes that lineage gap: it independently
reconstructs the route referenced by the sealed route-bound receipt before it
allows the existing selected-profile entry qualifier to run.

The result remains advisory and zero-authority.  It opens no camera, controller,
simulator, or hardware transport and emits no command.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .fixed_camera_keyboard_route_bound_collision_qualification_v1 import (
    SCHEMA as ROUTE_BOUND_SCHEMA,
    STATUS_BLOCKED as ROUTE_BOUND_BLOCKED,
    STATUS_READY as ROUTE_BOUND_READY,
    STATUS_REJECTED as ROUTE_BOUND_REJECTED,
    ZERO_AUTHORITY as ROUTE_BOUND_ZERO_AUTHORITY,
)


SUPPORTED_PROFILES = ("no_attachment", "stylus_attachment")
ENTRY_SCHEMA = "rocell.fixed_camera_keyboard_profiled_entry_route_qualification.v1"
ENTRY_PASS = "PROFILED_ENTRY_ROUTE_CLEARANCE_QUALIFIED_ZERO_AUTHORITY"
ENTRY_REJECTED = "REJECTED_PROFILED_ENTRY_OR_ROUTE_COLLISION"
ENTRY_BLOCKED = "BLOCKED_PROFILED_ENTRY_ROUTE_EVIDENCE_INCOMPLETE"
ENTRY_ZERO_AUTHORITY: Mapping[str, object] = {
    "controller_commands": [],
    "hardware_commands_generated": 0,
    "hardware_access": False,
    "physical_movements": 0,
    "physical_authority": False,
}
ROUTE_RECONSTRUCTION_READY = "ROUTE_CLEARANCE_RECONSTRUCTED_FRESH_ENTRY_REQUIRED"
ROUTE_RECONSTRUCTION_REJECTED = "REJECTED_ROUTE_COLLISION_DETECTED"
ROUTE_RECONSTRUCTION_BLOCKED = "BLOCKED_ROUTE_CLEARANCE_EVIDENCE_INCOMPLETE"
SCHEMA = "rocell.fixed_camera_keyboard_route_bound_entry_qualification.v1"
STATUS_PASS = "ROUTE_BOUND_PROFILED_ENTRY_ROUTE_QUALIFIED_ZERO_AUTHORITY"
STATUS_REJECTED = "REJECTED_ROUTE_BOUND_PROFILED_ENTRY_OR_ROUTE_COLLISION"
STATUS_BLOCKED = "BLOCKED_ROUTE_BOUND_PROFILED_ENTRY_ROUTE_EVIDENCE_INCOMPLETE"
ZERO_AUTHORITY: Mapping[str, object] = {
    "exact_route_binding_verified": True,
    "installed_geometry_collision_screening_executed": True,
    "controller_commands": [],
    "hardware_commands_generated": 0,
    "hardware_writes": 0,
    "hardware_access": False,
    "physical_movements": 0,
    "physical_authority": False,
    "physical_release_effect": "NONE",
}
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "schema",
    "status",
    "disposition",
    "active_profile",
    "route_bound_collision_qualification_sha256",
    "source_profiled_partition_collision_evaluation_sha256",
    "source_profiled_route_clearance_reconstruction_sha256",
    "route_envelope_binding_sha256",
    "installed_collision_profile_sha256",
    "profiled_entry_route_qualification",
    "profiled_entry_route_qualification_sha256",
    "observed_route_entry_sha256",
    "observed_route_entry_sweep_sha256",
    "observed_route_entry_coverage_sha256",
    "exact_route_binding_verified_before_entry_qualification",
    "profile_separation_preserved",
    "blockers",
    "next_required_stage",
    "authority",
    "route_bound_entry_qualification_sha256",
}


class FixedCameraKeyboardRouteBoundEntryQualificationV1Error(ValueError):
    """The route-bound receipt, entry evidence, or selected profile differs."""


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
        raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
            "route-bound entry qualification is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sealed(value: Mapping[str, Any], hash_field: str, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    core = dict(value)
    supplied = core.pop(hash_field, None)
    if not isinstance(supplied, str) or supplied != _sha(core):
        raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
            f"{label} hash differs"
        )
    return dict(value)


def _reconstruct_route(
    partition_documents: Mapping[str, Mapping[str, Any]],
    collision_evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    # Keep collision/numerical dependencies out of the lightweight base import.
    from .fixed_camera_keyboard_profiled_route_clearance_reconstruction_v1 import (
        reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1,
    )

    return reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1(
        partition_documents, collision_evaluation
    )


def _qualify_entry(
    partition_documents: Mapping[str, Mapping[str, Any]],
    collision_evaluation: Mapping[str, Any],
    active_profile: str,
    observed_route_entry: Mapping[str, Any] | None,
    observed_route_entry_sweep: Mapping[str, Any] | None,
    observed_route_entry_coverage: Mapping[str, Any] | None,
) -> dict[str, Any]:
    # ICQ-7 numerical dependencies are required only on an admitted route.
    from .fixed_camera_keyboard_profiled_entry_route_qualification_v1 import (
        qualify_fixed_camera_keyboard_profiled_entry_route_v1,
    )

    return qualify_fixed_camera_keyboard_profiled_entry_route_v1(
        partition_documents,
        collision_evaluation,
        active_profile,
        observed_route_entry,
        observed_route_entry_sweep,
        observed_route_entry_coverage,
    )


def verify_fixed_camera_keyboard_route_bound_collision_receipt_v1(
    receipt: Mapping[str, Any],
    partition_documents: Mapping[str, Mapping[str, Any]],
    collision_evaluation: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    route_bound = _sealed(
        receipt,
        "route_bound_collision_qualification_sha256",
        "route-bound collision qualification",
    )
    if route_bound.get("schema") != ROUTE_BOUND_SCHEMA:
        raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
            "route-bound collision qualification schema differs"
        )
    profiles = route_bound.get("profiles")
    if not isinstance(profiles, Mapping) or set(profiles) != set(SUPPORTED_PROFILES):
        raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
            "route-bound receipt must preserve the exact supported profile set"
        )
    if (
        route_bound.get("profile_separation_preserved") is not True
        or route_bound.get("exact_route_binding_verified_before_evaluation") is not True
        or route_bound.get("expected_route_sample_count_per_profile") != 329
        or route_bound.get("expected_route_segment_count_per_profile") != 328
        or route_bound.get("authority") != dict(ROUTE_BOUND_ZERO_AUTHORITY)
    ):
        raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
            "route-bound verification or authority differs"
        )
    for profile_name in SUPPORTED_PROFILES:
        profile = profiles[profile_name]
        if (
            not isinstance(profile, Mapping)
            or profile.get("profile") != profile_name
            or profile.get("route_sample_count") != 329
            or profile.get("route_segment_count") != 328
            or any(
                _SHA.fullmatch(str(profile.get(field, ""))) is None
                for field in (
                    "installed_collision_profile_sha256",
                    "partitioned_typing_collision_intake_sha256",
                    "completion_sha256",
                    "independent_review_sha256",
                    "route_envelope_binding_sha256",
                )
            )
        ):
            raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
                f"route-bound profile evidence differs: {profile_name}"
            )

    route = _reconstruct_route(partition_documents, collision_evaluation)
    expected_route_status = {
        ROUTE_BOUND_READY: ROUTE_RECONSTRUCTION_READY,
        ROUTE_BOUND_REJECTED: ROUTE_RECONSTRUCTION_REJECTED,
        ROUTE_BOUND_BLOCKED: ROUTE_RECONSTRUCTION_BLOCKED,
    }.get(route_bound.get("status"))
    evaluation_hash = collision_evaluation.get(
        "profiled_partition_collision_evaluation_sha256"
    )
    if (
        expected_route_status is None
        or route.get("status") != expected_route_status
        or route_bound.get(
            "source_profiled_partition_collision_evaluation_sha256"
        )
        != evaluation_hash
        or route_bound.get(
            "source_profiled_route_clearance_reconstruction_sha256"
        )
        != route.get("profiled_route_clearance_reconstruction_sha256")
        or route_bound.get("disposition") != route.get("disposition")
        or route_bound.get("blockers") != route.get("blockers")
        or route_bound.get("next_required_stage") != route.get("next_required_stage")
    ):
        raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
            "route-bound receipt and reconstructed route lineage differ"
        )
    return route_bound, route


def qualify_fixed_camera_keyboard_route_bound_entry_v1(
    route_bound_collision_qualification: Mapping[str, Any],
    partition_documents: Mapping[str, Mapping[str, Any]],
    collision_evaluation: Mapping[str, Any],
    active_profile: str,
    observed_route_entry: Mapping[str, Any] | None = None,
    observed_route_entry_sweep: Mapping[str, Any] | None = None,
    observed_route_entry_coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Join exact-route review lineage to the existing fresh-entry boundary."""

    if active_profile not in SUPPORTED_PROFILES:
        raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
            "active_profile is not supported"
        )
    route_bound, route = verify_fixed_camera_keyboard_route_bound_collision_receipt_v1(
        route_bound_collision_qualification,
        partition_documents,
        collision_evaluation,
    )
    selected = route_bound["profiles"][active_profile]
    entry_qualification: dict[str, Any] | None = None

    if route_bound["status"] == ROUTE_BOUND_READY:
        entry_qualification = _qualify_entry(
            partition_documents,
            collision_evaluation,
            active_profile,
            observed_route_entry,
            observed_route_entry_sweep,
            observed_route_entry_coverage,
        )
        if (
            entry_qualification.get(
                "profiled_route_clearance_reconstruction_sha256"
            )
            != route["profiled_route_clearance_reconstruction_sha256"]
            or entry_qualification.get("installed_collision_profile_sha256")
            != selected["installed_collision_profile_sha256"]
            or entry_qualification.get("active_profile") != active_profile
            or entry_qualification.get("profile_separation_preserved") is not True
        ):
            raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
                "fresh entry qualification and route-bound profile lineage differ"
            )
        nested_status = entry_qualification.get("status")
        status = {
            ENTRY_PASS: STATUS_PASS,
            ENTRY_REJECTED: STATUS_REJECTED,
            ENTRY_BLOCKED: STATUS_BLOCKED,
        }.get(nested_status)
        if status is None:
            raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
                "fresh entry qualification status differs"
            )
        disposition = entry_qualification["disposition"]
        blockers = list(entry_qualification["blockers"])
        next_stage = entry_qualification["next_required_stage"]
    elif route_bound["status"] == ROUTE_BOUND_REJECTED:
        status = STATUS_REJECTED
        disposition = "REJECT"
        blockers = list(route_bound["blockers"])
        next_stage = route_bound["next_required_stage"]
    else:
        status = STATUS_BLOCKED
        disposition = "BLOCKED"
        blockers = list(route_bound["blockers"])
        next_stage = route_bound["next_required_stage"]

    def nested_hash(field: str) -> str | None:
        return entry_qualification.get(field) if entry_qualification is not None else None

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "disposition": disposition,
        "active_profile": active_profile,
        "route_bound_collision_qualification_sha256": route_bound[
            "route_bound_collision_qualification_sha256"
        ],
        "source_profiled_partition_collision_evaluation_sha256": route_bound[
            "source_profiled_partition_collision_evaluation_sha256"
        ],
        "source_profiled_route_clearance_reconstruction_sha256": route_bound[
            "source_profiled_route_clearance_reconstruction_sha256"
        ],
        "route_envelope_binding_sha256": selected[
            "route_envelope_binding_sha256"
        ],
        "installed_collision_profile_sha256": selected[
            "installed_collision_profile_sha256"
        ],
        "profiled_entry_route_qualification": entry_qualification,
        "profiled_entry_route_qualification_sha256": nested_hash(
            "profiled_entry_route_qualification_sha256"
        ),
        "observed_route_entry_sha256": nested_hash("observed_route_entry_sha256"),
        "observed_route_entry_sweep_sha256": nested_hash(
            "observed_route_entry_sweep_sha256"
        ),
        "observed_route_entry_coverage_sha256": nested_hash(
            "observed_route_entry_coverage_sha256"
        ),
        "exact_route_binding_verified_before_entry_qualification": True,
        "profile_separation_preserved": True,
        "blockers": blockers,
        "next_required_stage": next_stage,
        "authority": dict(ZERO_AUTHORITY),
    }
    return {**core, "route_bound_entry_qualification_sha256": _sha(core)}


def parse_fixed_camera_keyboard_route_bound_entry_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a retained route-bound fresh-entry receipt independently."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
            "route-bound entry qualification fields differ"
        )
    document = _sealed(
        value,
        "route_bound_entry_qualification_sha256",
        "route-bound entry qualification",
    )
    nested = document["profiled_entry_route_qualification"]
    if nested is None:
        nested_hash = None
        allowed_pairs = {
            (STATUS_REJECTED, "REJECT"),
            (STATUS_BLOCKED, "BLOCKED"),
        }
        observed_hashes = (None, None, None)
    elif isinstance(nested, Mapping):
        nested_document = _sealed(
            nested,
            "profiled_entry_route_qualification_sha256",
            "profiled entry-route qualification",
        )
        nested_hash = nested_document["profiled_entry_route_qualification_sha256"]
        nested_status = nested_document.get("status")
        expected = {
            ENTRY_PASS: (STATUS_PASS, "PASS"),
            ENTRY_REJECTED: (STATUS_REJECTED, "REJECT"),
            ENTRY_BLOCKED: (STATUS_BLOCKED, "BLOCKED"),
        }.get(nested_status)
        if expected is None:
            raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
                "nested entry qualification status differs"
            )
        allowed_pairs = {expected}
        observed_hashes = (
            nested_document.get("observed_route_entry_sha256"),
            nested_document.get("observed_route_entry_sweep_sha256"),
            nested_document.get("observed_route_entry_coverage_sha256"),
        )
        if (
            nested_document.get("schema") != ENTRY_SCHEMA
            or nested_document.get("active_profile") != document["active_profile"]
            or nested_document.get("installed_collision_profile_sha256")
            != document["installed_collision_profile_sha256"]
            or nested_document.get(
                "profiled_route_clearance_reconstruction_sha256"
            )
            != document["source_profiled_route_clearance_reconstruction_sha256"]
            or nested_document.get("profile_separation_preserved") is not True
            or nested_document.get("authority") != dict(ENTRY_ZERO_AUTHORITY)
            or nested_document.get("blockers") != document["blockers"]
            or nested_document.get("next_required_stage")
            != document["next_required_stage"]
        ):
            raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
                "nested entry qualification lineage differs"
            )
    else:
        raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
            "nested entry qualification is malformed"
        )

    digest_fields = (
        "route_bound_collision_qualification_sha256",
        "source_profiled_partition_collision_evaluation_sha256",
        "source_profiled_route_clearance_reconstruction_sha256",
        "route_envelope_binding_sha256",
        "installed_collision_profile_sha256",
    )
    if (
        document["schema"] != SCHEMA
        or document["active_profile"] not in SUPPORTED_PROFILES
        or any(_SHA.fullmatch(str(document[field])) is None for field in digest_fields)
        or document["profiled_entry_route_qualification_sha256"] != nested_hash
        or (
            document["observed_route_entry_sha256"],
            document["observed_route_entry_sweep_sha256"],
            document["observed_route_entry_coverage_sha256"],
        )
        != observed_hashes
        or (document["status"], document["disposition"]) not in allowed_pairs
        or not isinstance(document["blockers"], list)
        or len(set(document["blockers"])) != len(document["blockers"])
        or any(not isinstance(item, str) or not item for item in document["blockers"])
        or (document["status"] == STATUS_PASS and document["blockers"] != [])
        or (document["status"] != STATUS_PASS and not document["blockers"])
        or not isinstance(document["next_required_stage"], str)
        or not document["next_required_stage"]
        or document["exact_route_binding_verified_before_entry_qualification"]
        is not True
        or document["profile_separation_preserved"] is not True
        or document["authority"] != dict(ZERO_AUTHORITY)
    ):
        raise FixedCameraKeyboardRouteBoundEntryQualificationV1Error(
            "route-bound entry lineage, result, or authority differs"
        )
    return dict(value)


__all__ = [
    "SCHEMA",
    "STATUS_PASS",
    "STATUS_REJECTED",
    "STATUS_BLOCKED",
    "ZERO_AUTHORITY",
    "FixedCameraKeyboardRouteBoundEntryQualificationV1Error",
    "parse_fixed_camera_keyboard_route_bound_entry_v1",
    "qualify_fixed_camera_keyboard_route_bound_entry_v1",
    "verify_fixed_camera_keyboard_route_bound_collision_receipt_v1",
]
