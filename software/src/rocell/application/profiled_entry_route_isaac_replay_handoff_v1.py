"""Prepare an exact, zero-authority WP3 replay handoff.

The adapter binds one selected attachment profile's qualified entry-plus-route
receipt to the exact 329 configuration samples behind its 328 route segments.
It never imports Isaac Sim, starts a process, opens hardware, or emits a
controller command.  An unselected toolchain lock remains a named blocker.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping

from rocell.integrations.isaac_sim.contracts import IsaacSimContractError
from rocell.integrations.isaac_sim.toolchain_lock import (
    LOCK_SCHEMA,
    IsaacSimToolchainLock,
)

from .fixed_camera_keyboard_clearance_intake_v1 import SUPPORTED_PROFILES
from .fixed_camera_keyboard_profiled_entry_route_qualification_v1 import (
    SCHEMA as QUALIFICATION_SCHEMA,
    STATUS_PASS as QUALIFICATION_PASS,
)
from .fixed_camera_keyboard_profiled_route_clearance_reconstruction_v1 import (
    reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1,
)
from .partitioned_typing_collision_intake_v1 import (
    READY_STATUS as PARTITION_READY,
    SCHEMA as PARTITION_SCHEMA,
)


SCHEMA = "rocell.profiled_entry_route_isaac_replay_handoff.v1"
STATUS_READY = "READY_FOR_NATIVE_ISAAC_REPLAY_ZERO_AUTHORITY"
STATUS_TOOLCHAIN_BLOCKED = "BLOCKED_ISAAC_TOOLCHAIN_LOCK_UNSELECTED"
STATUS_QUALIFICATION_BLOCKED = "BLOCKED_PROFILED_ENTRY_ROUTE_QUALIFICATION_REQUIRED"
EXPECTED_ROUTE_SEGMENT_COUNT = 328
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "schema",
    "status",
    "active_profile",
    "profile_separation_preserved",
    "profiled_entry_route_qualification_sha256",
    "partitioned_typing_collision_intake_sha256",
    "installed_collision_profile_sha256",
    "calibration_snapshot_sha256",
    "build_snapshot_sha256",
    "trajectory",
    "toolchain_lock_sha256",
    "toolchain_selection_status",
    "isaac_replay_request",
    "blockers",
    "next_required_stage",
    "authority",
    "isaac_replay_handoff_sha256",
}
_TRAJECTORY_FIELDS = {"sample_count", "segment_count", "samples", "trajectory_sha256"}
_SAMPLE_FIELDS = {
    "route_sample_sequence",
    "source_segment_index",
    "joint_positions_rad",
    "source_sample_sha256",
}
_REQUEST_FIELDS = {
    "active_profile",
    "qualification_sha256",
    "partitioned_typing_collision_intake_sha256",
    "trajectory_sha256",
    "toolchain_lock_sha256",
    "isaac_sim_version",
    "installation_sha256",
    "extension_lock_sha256",
    "settings_profile_sha256",
    "random_seed",
    "replan_allowed",
    "request_sha256",
}
ZERO_AUTHORITY: Mapping[str, object] = {
    "controller_commands": [],
    "hardware_commands_generated": 0,
    "hardware_access": False,
    "physical_movements": 0,
    "physical_authority": False,
}


class ProfiledEntryRouteIsaacReplayHandoffV1Error(ValueError):
    """The qualification, profile route, or toolchain lineage differs."""


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            f"{label} is not a lowercase SHA-256 digest"
        )
    return value


def _require_exact_fields(
    value: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(value) != expected:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            f"{label} fields differ"
        )


def _require_joint_map(value: object, label: str) -> dict[str, float]:
    if (
        not isinstance(value, Mapping)
        or not value
        or any(not isinstance(name, str) or not name for name in value)
    ):
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            f"{label} must contain named joints"
        )
    result: dict[str, float] = {}
    for name, raw in value.items():
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                f"{label}.{name} is not numeric"
            )
        number = float(raw)
        if not math.isfinite(number):
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                f"{label}.{name} is not finite"
            )
        result[name] = number
    return result


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
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "Isaac replay handoff is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sealed(value: Mapping[str, Any], hash_field: str, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    core = dict(value)
    supplied = core.pop(hash_field, None)
    if not isinstance(supplied, str) or supplied != _sha(core):
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(f"{label} hash differs")
    return dict(value)


def parse_profiled_entry_route_isaac_replay_handoff_v1(
    value: Mapping[str, Any],
    *,
    require_ready: bool = False,
    toolchain_lock: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Independently validate a retained WP3 handoff before native intake."""

    if not isinstance(value, Mapping):
        raise TypeError("profiled_entry_route_isaac_replay_handoff must be an object")
    document = dict(value)
    _require_exact_fields(document, _FIELDS, "Isaac replay handoff")
    document = _sealed(
        document,
        "isaac_replay_handoff_sha256",
        "Isaac replay handoff",
    )
    if document.get("schema") != SCHEMA:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "Isaac replay handoff schema differs"
        )
    status = document.get("status")
    if status not in {
        STATUS_READY,
        STATUS_TOOLCHAIN_BLOCKED,
        STATUS_QUALIFICATION_BLOCKED,
    }:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "Isaac replay handoff status differs"
        )
    if document.get("active_profile") not in SUPPORTED_PROFILES:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "Isaac replay handoff active profile is unsupported"
        )
    if document.get("profile_separation_preserved") is not True:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "Isaac replay handoff crossed attachment profiles"
        )
    for field in (
        "profiled_entry_route_qualification_sha256",
        "partitioned_typing_collision_intake_sha256",
        "installed_collision_profile_sha256",
        "calibration_snapshot_sha256",
        "build_snapshot_sha256",
        "toolchain_lock_sha256",
    ):
        _require_sha256(document.get(field), field)
    if document.get("authority") != dict(ZERO_AUTHORITY):
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "Isaac replay handoff violates the zero-authority contract"
        )
    blockers = document.get("blockers")
    if (
        not isinstance(blockers, list)
        or any(not isinstance(item, str) or not item for item in blockers)
        or len(blockers) != len(set(blockers))
    ):
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "Isaac replay handoff blockers are invalid"
        )
    if not isinstance(document.get("next_required_stage"), str) or not document[
        "next_required_stage"
    ]:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "Isaac replay handoff next stage is invalid"
        )

    trajectory_raw = document.get("trajectory")
    if not isinstance(trajectory_raw, Mapping):
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "Isaac replay trajectory is absent"
        )
    trajectory = dict(trajectory_raw)
    _require_exact_fields(trajectory, _TRAJECTORY_FIELDS, "Isaac replay trajectory")
    trajectory = _sealed(trajectory, "trajectory_sha256", "Isaac replay trajectory")
    samples = trajectory.get("samples")
    if (
        trajectory.get("sample_count") != EXPECTED_ROUTE_SEGMENT_COUNT + 1
        or trajectory.get("segment_count") != EXPECTED_ROUTE_SEGMENT_COUNT
        or not isinstance(samples, list)
        or len(samples) != EXPECTED_ROUTE_SEGMENT_COUNT + 1
    ):
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "Isaac replay trajectory extent differs"
        )
    for sequence, sample_raw in enumerate(samples):
        if not isinstance(sample_raw, Mapping):
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                f"Isaac replay sample {sequence} is malformed"
            )
        sample = dict(sample_raw)
        _require_exact_fields(sample, _SAMPLE_FIELDS, f"Isaac replay sample {sequence}")
        if sample.get("route_sample_sequence") != sequence:
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                f"Isaac replay sample sequence differs at {sequence}"
            )
        source_segment = sample.get("source_segment_index")
        if source_segment is not None and (
            isinstance(source_segment, bool) or not isinstance(source_segment, int)
        ):
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                f"Isaac replay source segment differs at {sequence}"
            )
        _require_joint_map(
            sample.get("joint_positions_rad"),
            f"Isaac replay sample {sequence}.joint_positions_rad",
        )
        _require_sha256(
            sample.get("source_sample_sha256"),
            f"Isaac replay sample {sequence}.source_sample_sha256",
        )

    request_raw = document.get("isaac_replay_request")
    if status == STATUS_READY:
        if document.get("toolchain_selection_status") != "SELECTED":
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                "ready Isaac replay handoff lacks a selected toolchain"
            )
        if blockers:
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                "ready Isaac replay handoff retains blockers"
            )
        if not isinstance(request_raw, Mapping):
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                "ready Isaac replay handoff has no request"
            )
        request = dict(request_raw)
        _require_exact_fields(request, _REQUEST_FIELDS, "Isaac replay request")
        request = _sealed(request, "request_sha256", "Isaac replay request")
        for field in (
            "qualification_sha256",
            "partitioned_typing_collision_intake_sha256",
            "trajectory_sha256",
            "toolchain_lock_sha256",
            "installation_sha256",
            "extension_lock_sha256",
            "settings_profile_sha256",
        ):
            _require_sha256(request.get(field), f"Isaac replay request.{field}")
        if (
            request.get("active_profile") != document["active_profile"]
            or request.get("qualification_sha256")
            != document["profiled_entry_route_qualification_sha256"]
            or request.get("partitioned_typing_collision_intake_sha256")
            != document["partitioned_typing_collision_intake_sha256"]
            or request.get("trajectory_sha256") != trajectory_raw["trajectory_sha256"]
            or request.get("toolchain_lock_sha256")
            != document["toolchain_lock_sha256"]
            or not isinstance(request.get("isaac_sim_version"), str)
            or not request["isaac_sim_version"]
            or request.get("random_seed") != 0
            or request.get("replan_allowed") is not False
        ):
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                "Isaac replay request and handoff lineage differ"
            )
    else:
        if request_raw is not None or not blockers:
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                "blocked Isaac replay handoff request or blockers differ"
            )
        if document.get("toolchain_selection_status") not in {"SELECTED", "UNSELECTED"}:
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                "blocked Isaac replay handoff toolchain status differs"
            )

    if require_ready and status != STATUS_READY:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "native Isaac intake requires a READY handoff"
        )
    if require_ready:
        if not isinstance(toolchain_lock, Mapping):
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                "native Isaac intake requires the selected toolchain lock"
            )
        lock = dict(toolchain_lock)
        try:
            selected_lock = IsaacSimToolchainLock.from_dict(lock)
        except IsaacSimContractError as exc:
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(str(exc)) from exc
        request = dict(request_raw)  # status READY proved this mapping above
        if (
            _sha(lock) != document["toolchain_lock_sha256"]
            or request["isaac_sim_version"] != selected_lock.isaac_sim_version
            or request["installation_sha256"] != selected_lock.installation_sha256
            or request["extension_lock_sha256"]
            != selected_lock.extension_lock_sha256
            or request["settings_profile_sha256"]
            != selected_lock.settings_profile_sha256
        ):
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                "native Isaac intake toolchain identity differs"
            )
    return dict(value)


def _route_samples(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    partitions = document.get("partitions")
    boundaries = document.get("boundary_lineage")
    if not isinstance(partitions, list) or not partitions:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "selected profile route partitions are absent"
        )
    if not isinstance(boundaries, list) or len(boundaries) != len(partitions) - 1:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "selected profile partition boundaries differ"
        )
    samples: list[dict[str, Any]] = []
    expected_segment = 0
    previous_terminal: Mapping[str, Any] | None = None
    for partition_index, partition_raw in enumerate(partitions):
        if not isinstance(partition_raw, Mapping):
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                "selected profile partition is malformed"
            )
        partition = dict(partition_raw)
        partition_hash = partition.pop("partition_intake_sha256", None)
        plan = partition_raw.get("bounded_joint_sample_plan")
        count = partition_raw.get("source_result_count")
        start = partition_raw.get("source_result_start_index")
        end = partition_raw.get("source_result_end_index_exclusive")
        if (
            partition_hash != _sha(partition)
            or partition_raw.get("partition_index") != partition_index
            or start != expected_segment
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count <= 0
            or end != start + count
            or not isinstance(plan, list)
            or len(plan) != count + 1
            or any(not isinstance(sample, Mapping) for sample in plan)
        ):
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                f"selected profile partition ownership differs: {partition_index}"
            )
        if previous_terminal is not None:
            boundary_raw = boundaries[partition_index - 1]
            if not isinstance(boundary_raw, Mapping):
                raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                    "selected profile boundary is malformed"
                )
            boundary = dict(boundary_raw)
            boundary_hash = boundary.pop("boundary_lineage_sha256", None)
            if (
                boundary_hash != _sha(boundary)
                or boundary_raw.get("predecessor_partition_index")
                != partition_index - 1
                or boundary_raw.get("successor_partition_index") != partition_index
                or boundary_raw.get("source_boundary_result_index") != start - 1
                or boundary_raw.get("predecessor_terminal_sample_sha256")
                != _sha(previous_terminal)
                or boundary_raw.get("successor_boundary_recheck_sample_sha256")
                != _sha(plan[0])
                or boundary_raw.get("maximum_joint_difference_rad") != 0.0
                or previous_terminal.get("joint_positions_rad")
                != plan[0].get("joint_positions_rad")
            ):
                raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                    f"selected profile boundary lineage differs: {partition_index - 1}"
                )
        for sample in plan if not samples else plan[1:]:
            joints = sample.get("joint_positions_rad")
            if not isinstance(joints, Mapping) or not joints:
                raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
                    "selected profile route sample has no joint positions"
                )
            route_sequence = len(samples)
            samples.append(
                {
                    "route_sample_sequence": route_sequence,
                    "source_segment_index": sample.get("source_segment_index"),
                    "joint_positions_rad": dict(joints),
                    "source_sample_sha256": _sha(sample),
                }
            )
        expected_segment = end
        previous_terminal = plan[-1]
    if expected_segment != EXPECTED_ROUTE_SEGMENT_COUNT:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "selected profile route does not contain exactly 328 segments"
        )
    if len(samples) != EXPECTED_ROUTE_SEGMENT_COUNT + 1:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "selected profile route does not contain exactly 329 configurations"
        )
    return samples


def prepare_profiled_entry_route_isaac_replay_handoff_v1(
    qualification_receipt: Mapping[str, Any],
    partition_documents: Mapping[str, Mapping[str, Any]],
    collision_evaluation: Mapping[str, Any],
    toolchain_lock: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind exact qualified route samples to a fail-closed Isaac WP3 handoff."""

    qualification = _sealed(
        qualification_receipt,
        "profiled_entry_route_qualification_sha256",
        "profiled entry-route qualification",
    )
    if qualification.get("schema") != QUALIFICATION_SCHEMA:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "profiled entry-route qualification schema differs"
        )
    active_profile = qualification.get("active_profile")
    if active_profile not in SUPPORTED_PROFILES:
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "qualification active profile is unsupported"
        )
    if not isinstance(partition_documents, Mapping) or set(partition_documents) != set(
        SUPPORTED_PROFILES
    ):
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "partition documents must preserve both attachment profiles"
        )
    route = reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1(
        partition_documents, collision_evaluation
    )
    if route["profiled_route_clearance_reconstruction_sha256"] != qualification.get(
        "profiled_route_clearance_reconstruction_sha256"
    ):
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "route reconstruction and qualification lineage differ"
        )
    partition = _sealed(
        partition_documents[active_profile],
        "partitioned_typing_collision_intake_sha256",
        "selected profile partition document",
    )
    selected_route = route["profiles"][active_profile]
    if (
        partition.get("schema") != PARTITION_SCHEMA
        or partition.get("status") != PARTITION_READY
        or partition.get("installed_collision_profile_sha256")
        != qualification.get("installed_collision_profile_sha256")
        or selected_route.get("source_partitioned_typing_collision_intake_sha256")
        != partition.get("partitioned_typing_collision_intake_sha256")
        or route.get("calibration_snapshot_sha256")
        != qualification.get("calibration_snapshot_sha256")
        or route.get("build_snapshot_sha256")
        != qualification.get("build_snapshot_sha256")
        or partition.get("required_evidence_slots", {}).get("route_segment_count")
        != qualification.get("route_segment_count")
    ):
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "selected profile route and qualification lineage differ"
        )
    samples = _route_samples(partition)
    trajectory_core = {
        "sample_count": len(samples),
        "segment_count": len(samples) - 1,
        "samples": samples,
    }
    trajectory = {
        **trajectory_core,
        "trajectory_sha256": _sha(trajectory_core),
    }

    if not isinstance(toolchain_lock, Mapping):
        raise TypeError("toolchain_lock must be an object")
    lock = dict(toolchain_lock)
    if (
        lock.get("schema") != LOCK_SCHEMA
        or lock.get("hardware_access") is not False
        or lock.get("physical_authority") is not False
        or lock.get("wire_commands") != []
    ):
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "toolchain lock violates the zero-authority contract"
        )
    lock_sha = _sha(lock)
    qualification_passed = (
        qualification.get("status") == QUALIFICATION_PASS
        and qualification.get("disposition") == "PASS"
        and qualification.get("profile_separation_preserved") is True
        and qualification.get("entry_route_joint_continuity_proven") is True
        and qualification.get("selected_profile_route_continuously_clear") is True
        and qualification.get("observed_entry_continuously_clear") is True
        and qualification.get("retained_entry_telemetry_coverage_qualified") is True
        and qualification.get("blockers") == []
        and qualification.get("authority") == dict(ZERO_AUTHORITY)
    )

    selected_lock: IsaacSimToolchainLock | None = None
    if lock.get("selection_status") == "SELECTED":
        try:
            selected_lock = IsaacSimToolchainLock.from_dict(lock)
        except IsaacSimContractError as exc:
            raise ProfiledEntryRouteIsaacReplayHandoffV1Error(str(exc)) from exc
    elif lock.get("selection_status") != "UNSELECTED":
        raise ProfiledEntryRouteIsaacReplayHandoffV1Error(
            "toolchain lock selection status is invalid"
        )

    if not qualification_passed:
        status = STATUS_QUALIFICATION_BLOCKED
        blockers = ["PROFILED_ENTRY_ROUTE_QUALIFICATION_REQUIRED"]
        next_stage = "COMPLETE_FRESH_SELECTED_PROFILE_ENTRY_ROUTE_QUALIFICATION"
    elif selected_lock is None:
        status = STATUS_TOOLCHAIN_BLOCKED
        blockers = ["ISAAC_SIM_TOOLCHAIN_LOCK_UNSELECTED"]
        next_stage = "SELECT_AND_REVIEW_EXACT_ISAAC_SIM_TOOLCHAIN_LOCK"
    else:
        status = STATUS_READY
        blockers = []
        next_stage = "RUN_EXACT_NATIVE_ISAAC_REPLAY_AND_RETAIN_RECEIPT"

    request = None
    if status == STATUS_READY and selected_lock is not None:
        request_core = {
            "active_profile": active_profile,
            "qualification_sha256": qualification[
                "profiled_entry_route_qualification_sha256"
            ],
            "partitioned_typing_collision_intake_sha256": partition[
                "partitioned_typing_collision_intake_sha256"
            ],
            "trajectory_sha256": trajectory["trajectory_sha256"],
            "toolchain_lock_sha256": lock_sha,
            "isaac_sim_version": selected_lock.isaac_sim_version,
            "installation_sha256": selected_lock.installation_sha256,
            "extension_lock_sha256": selected_lock.extension_lock_sha256,
            "settings_profile_sha256": selected_lock.settings_profile_sha256,
            "random_seed": 0,
            "replan_allowed": False,
        }
        request = {**request_core, "request_sha256": _sha(request_core)}

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "active_profile": active_profile,
        "profile_separation_preserved": True,
        "profiled_entry_route_qualification_sha256": qualification[
            "profiled_entry_route_qualification_sha256"
        ],
        "partitioned_typing_collision_intake_sha256": partition[
            "partitioned_typing_collision_intake_sha256"
        ],
        "installed_collision_profile_sha256": qualification[
            "installed_collision_profile_sha256"
        ],
        "calibration_snapshot_sha256": qualification["calibration_snapshot_sha256"],
        "build_snapshot_sha256": qualification["build_snapshot_sha256"],
        "trajectory": trajectory,
        "toolchain_lock_sha256": lock_sha,
        "toolchain_selection_status": lock["selection_status"],
        "isaac_replay_request": request,
        "blockers": blockers,
        "next_required_stage": next_stage,
        "authority": dict(ZERO_AUTHORITY),
    }
    return {**core, "isaac_replay_handoff_sha256": _sha(core)}


__all__ = [
    "SCHEMA",
    "STATUS_READY",
    "STATUS_TOOLCHAIN_BLOCKED",
    "STATUS_QUALIFICATION_BLOCKED",
    "ProfiledEntryRouteIsaacReplayHandoffV1Error",
    "parse_profiled_entry_route_isaac_replay_handoff_v1",
    "prepare_profiled_entry_route_isaac_replay_handoff_v1",
]
