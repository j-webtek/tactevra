"""Carry the exact reviewed-route entry chain into the ICQ-9 handoff.

The older Isaac adapter accepts the nested ICQ-7 qualification directly.  This
adapter requires the later route-bound collision and entry receipts, verifies
them against the supplied route, and only then delegates to that adapter.  It
opens no simulator, camera, controller, or hardware transport.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .fixed_camera_keyboard_route_bound_entry_qualification_v1 import (
    STATUS_BLOCKED as ENTRY_BLOCKED,
    STATUS_PASS as ENTRY_PASS,
    STATUS_REJECTED as ENTRY_REJECTED,
    ZERO_AUTHORITY as ENTRY_ZERO_AUTHORITY,
    parse_fixed_camera_keyboard_route_bound_entry_v1,
    verify_fixed_camera_keyboard_route_bound_collision_receipt_v1,
)


SCHEMA = "rocell.route_bound_entry_isaac_replay_handoff.v1"
STATUS_READY = "READY_ROUTE_BOUND_NATIVE_ISAAC_REPLAY_ZERO_AUTHORITY"
STATUS_BLOCKED = "BLOCKED_ROUTE_BOUND_NATIVE_ISAAC_REPLAY_EVIDENCE_INCOMPLETE"
STATUS_REJECTED = "REJECTED_ROUTE_BOUND_ENTRY_OR_ROUTE_COLLISION"
NESTED_READY = "READY_FOR_NATIVE_ISAAC_REPLAY_ZERO_AUTHORITY"
ZERO_AUTHORITY: Mapping[str, object] = {
    "exact_route_binding_verified": True,
    "fresh_entry_binding_verified": True,
    "replan_allowed": False,
    "controller_commands": [],
    "hardware_commands_generated": 0,
    "hardware_writes": 0,
    "hardware_access": False,
    "physical_movements": 0,
    "physical_authority": False,
}
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "schema",
    "status",
    "active_profile",
    "route_bound_collision_qualification_sha256",
    "route_bound_entry_qualification_sha256",
    "route_envelope_binding_sha256",
    "installed_collision_profile_sha256",
    "profiled_entry_route_qualification_sha256",
    "isaac_replay_handoff",
    "isaac_replay_handoff_sha256",
    "profile_separation_preserved",
    "exact_route_and_fresh_entry_verified_before_handoff",
    "blockers",
    "next_required_stage",
    "authority",
    "route_bound_isaac_replay_handoff_sha256",
}


class RouteBoundEntryIsaacReplayHandoffV1Error(ValueError):
    """The reviewed route, fresh entry, or Isaac handoff lineage differs."""


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
        raise RouteBoundEntryIsaacReplayHandoffV1Error(
            "route-bound Isaac handoff is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sealed(value: Mapping[str, Any], hash_field: str, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    core = dict(value)
    supplied = core.pop(hash_field, None)
    if not isinstance(supplied, str) or supplied != _sha(core):
        raise RouteBoundEntryIsaacReplayHandoffV1Error(f"{label} hash differs")
    return dict(value)


def _prepare_nested(
    qualification: Mapping[str, Any],
    partition_documents: Mapping[str, Mapping[str, Any]],
    collision_evaluation: Mapping[str, Any],
    toolchain_lock: Mapping[str, Any],
) -> dict[str, Any]:
    from .profiled_entry_route_isaac_replay_handoff_v1 import (
        prepare_profiled_entry_route_isaac_replay_handoff_v1,
    )

    return prepare_profiled_entry_route_isaac_replay_handoff_v1(
        qualification, partition_documents, collision_evaluation, toolchain_lock
    )


def prepare_route_bound_entry_isaac_replay_handoff_v1(
    route_bound_collision_qualification: Mapping[str, Any],
    route_bound_entry_qualification: Mapping[str, Any],
    partition_documents: Mapping[str, Mapping[str, Any]],
    collision_evaluation: Mapping[str, Any],
    toolchain_lock: Mapping[str, Any],
) -> dict[str, Any]:
    """Prepare an ICQ-9 handoff only from the exact reviewed route-entry chain."""

    entry = parse_fixed_camera_keyboard_route_bound_entry_v1(
        route_bound_entry_qualification
    )
    route_bound, route = verify_fixed_camera_keyboard_route_bound_collision_receipt_v1(
        route_bound_collision_qualification,
        partition_documents,
        collision_evaluation,
    )
    active_profile = entry["active_profile"]
    selected = route_bound["profiles"][active_profile]
    if (
        entry["route_bound_collision_qualification_sha256"]
        != route_bound["route_bound_collision_qualification_sha256"]
        or entry["source_profiled_route_clearance_reconstruction_sha256"]
        != route["profiled_route_clearance_reconstruction_sha256"]
        or entry["route_envelope_binding_sha256"]
        != selected["route_envelope_binding_sha256"]
        or entry["installed_collision_profile_sha256"]
        != selected["installed_collision_profile_sha256"]
        or entry["profile_separation_preserved"] is not True
        or entry["authority"] != dict(ENTRY_ZERO_AUTHORITY)
    ):
        raise RouteBoundEntryIsaacReplayHandoffV1Error(
            "route-bound collision and fresh-entry lineage differ"
        )

    nested_handoff: dict[str, Any] | None = None
    qualification = entry["profiled_entry_route_qualification"]
    if entry["status"] == ENTRY_PASS:
        if not isinstance(qualification, Mapping):
            raise RouteBoundEntryIsaacReplayHandoffV1Error(
                "passing route-bound entry has no nested qualification"
            )
        nested_handoff = _prepare_nested(
            qualification,
            partition_documents,
            collision_evaluation,
            toolchain_lock,
        )
        if (
            nested_handoff.get("active_profile") != active_profile
            or nested_handoff.get("profiled_entry_route_qualification_sha256")
            != entry["profiled_entry_route_qualification_sha256"]
            or nested_handoff.get("installed_collision_profile_sha256")
            != entry["installed_collision_profile_sha256"]
            or nested_handoff.get("profile_separation_preserved") is not True
        ):
            raise RouteBoundEntryIsaacReplayHandoffV1Error(
                "nested Isaac handoff and route-bound entry lineage differ"
            )
        if nested_handoff.get("status") == NESTED_READY:
            status = STATUS_READY
            blockers: list[str] = []
            next_stage = "RUN_EXACT_NATIVE_ISAAC_REPLAY_AND_RETAIN_RECEIPT"
        else:
            status = STATUS_BLOCKED
            blockers = list(nested_handoff.get("blockers", []))
            next_stage = str(nested_handoff.get("next_required_stage", ""))
    elif entry["status"] == ENTRY_REJECTED:
        status = STATUS_REJECTED
        blockers = list(entry["blockers"])
        next_stage = entry["next_required_stage"]
    elif entry["status"] == ENTRY_BLOCKED:
        status = STATUS_BLOCKED
        blockers = list(entry["blockers"])
        next_stage = entry["next_required_stage"]
    else:  # Parser above makes this unreachable; retain an explicit fail-closed edge.
        raise RouteBoundEntryIsaacReplayHandoffV1Error(
            "route-bound entry status differs"
        )

    nested_hash = (
        nested_handoff.get("isaac_replay_handoff_sha256")
        if nested_handoff is not None
        else None
    )
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "active_profile": active_profile,
        "route_bound_collision_qualification_sha256": route_bound[
            "route_bound_collision_qualification_sha256"
        ],
        "route_bound_entry_qualification_sha256": entry[
            "route_bound_entry_qualification_sha256"
        ],
        "route_envelope_binding_sha256": entry["route_envelope_binding_sha256"],
        "installed_collision_profile_sha256": entry[
            "installed_collision_profile_sha256"
        ],
        "profiled_entry_route_qualification_sha256": entry[
            "profiled_entry_route_qualification_sha256"
        ],
        "isaac_replay_handoff": nested_handoff,
        "isaac_replay_handoff_sha256": nested_hash,
        "profile_separation_preserved": True,
        "exact_route_and_fresh_entry_verified_before_handoff": True,
        "blockers": blockers,
        "next_required_stage": next_stage,
        "authority": dict(ZERO_AUTHORITY),
    }
    return {**core, "route_bound_isaac_replay_handoff_sha256": _sha(core)}


def parse_route_bound_entry_isaac_replay_handoff_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a retained route-bound ICQ-9 handoff independently."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise RouteBoundEntryIsaacReplayHandoffV1Error(
            "route-bound Isaac handoff fields differ"
        )
    document = _sealed(
        value,
        "route_bound_isaac_replay_handoff_sha256",
        "route-bound Isaac handoff",
    )
    nested = document["isaac_replay_handoff"]
    if nested is None:
        nested_hash = None
        allowed = {STATUS_BLOCKED, STATUS_REJECTED}
    elif isinstance(nested, Mapping):
        from .profiled_entry_route_isaac_replay_handoff_v1 import (
            parse_profiled_entry_route_isaac_replay_handoff_v1,
        )

        parsed = parse_profiled_entry_route_isaac_replay_handoff_v1(nested)
        nested_hash = parsed["isaac_replay_handoff_sha256"]
        allowed = {STATUS_READY} if parsed["status"] == NESTED_READY else {STATUS_BLOCKED}
        if (
            parsed["active_profile"] != document["active_profile"]
            or parsed["profiled_entry_route_qualification_sha256"]
            != document["profiled_entry_route_qualification_sha256"]
            or parsed["installed_collision_profile_sha256"]
            != document["installed_collision_profile_sha256"]
            or parsed["blockers"] != document["blockers"]
            or parsed["next_required_stage"] != document["next_required_stage"]
        ):
            raise RouteBoundEntryIsaacReplayHandoffV1Error(
                "nested Isaac handoff lineage differs"
            )
    else:
        raise RouteBoundEntryIsaacReplayHandoffV1Error(
            "nested Isaac handoff is malformed"
        )

    digest_fields = (
        "route_bound_collision_qualification_sha256",
        "route_bound_entry_qualification_sha256",
        "route_envelope_binding_sha256",
        "installed_collision_profile_sha256",
    )
    if (
        document["schema"] != SCHEMA
        or document["status"] not in allowed
        or document["active_profile"] not in ("no_attachment", "stylus_attachment")
        or any(_SHA.fullmatch(str(document[field])) is None for field in digest_fields)
        or (
            document["profiled_entry_route_qualification_sha256"] is not None
            and _SHA.fullmatch(
                str(document["profiled_entry_route_qualification_sha256"])
            )
            is None
        )
        or document["isaac_replay_handoff_sha256"] != nested_hash
        or document["profile_separation_preserved"] is not True
        or document["exact_route_and_fresh_entry_verified_before_handoff"] is not True
        or not isinstance(document["blockers"], list)
        or len(document["blockers"]) != len(set(document["blockers"]))
        or any(not isinstance(item, str) or not item for item in document["blockers"])
        or (document["status"] == STATUS_READY and document["blockers"])
        or (document["status"] != STATUS_READY and not document["blockers"])
        or not isinstance(document["next_required_stage"], str)
        or not document["next_required_stage"]
        or document["authority"] != dict(ZERO_AUTHORITY)
    ):
        raise RouteBoundEntryIsaacReplayHandoffV1Error(
            "route-bound Isaac handoff lineage, result, or authority differs"
        )
    return dict(value)


__all__ = [
    "SCHEMA",
    "STATUS_READY",
    "STATUS_BLOCKED",
    "STATUS_REJECTED",
    "ZERO_AUTHORITY",
    "RouteBoundEntryIsaacReplayHandoffV1Error",
    "parse_route_bound_entry_isaac_replay_handoff_v1",
    "prepare_route_bound_entry_isaac_replay_handoff_v1",
]
