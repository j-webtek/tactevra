"""Bind configuration-sampled envelope evidence to one exact profiled route.

The installed envelope intake validates posture-local and adjacent-sweep
geometry.  This boundary additionally proves that every posture belongs to the
exact ordered 329-configuration route behind one attachment profile and that
all 328 adjacent route segments have envelope coverage.  It remains an offline
zero-authority receipt; the current intake evidence class is synthetic and
cannot satisfy installed qualification.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .installed_cable_envelope_intake_v1 import (
    EVIDENCE_CLASS,
    InstalledCableEnvelopeIntakeV1,
)
from .partitioned_typing_collision_intake_v1 import (
    READY_STATUS as PARTITION_READY,
    SCHEMA as PARTITION_SCHEMA,
)


SCHEMA = "rocell.profiled_route_cable_envelope_binding.v1"
STATUS = "ROUTE_BOUND_SYNTHETIC_ENVELOPE_INSTALLED_QUALIFICATION_BLOCKED"
EXPECTED_ROUTE_SAMPLE_COUNT = 329
EXPECTED_ROUTE_SEGMENT_COUNT = 328
ZERO_AUTHORITY: Mapping[str, object] = {
    "qualification_installed": False,
    "hardware_access": False,
    "controller_commands": [],
    "hardware_writes": 0,
    "physical_movements": 0,
    "physical_authority": False,
}


class ProfiledRouteCableEnvelopeBindingV1Error(ValueError):
    """Envelope evidence or route ownership cannot form one exact binding."""


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
        raise ProfiledRouteCableEnvelopeBindingV1Error(
            "route envelope evidence is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sealed(value: Mapping[str, Any], field: str, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    core = dict(value)
    supplied = core.pop(field, None)
    if not isinstance(supplied, str) or supplied != _sha(core):
        raise ProfiledRouteCableEnvelopeBindingV1Error(f"{label} hash differs")
    return dict(value)


def _route_samples(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    partitions = document.get("partitions")
    boundaries = document.get("boundary_lineage")
    if (
        not isinstance(partitions, list)
        or not partitions
        or not isinstance(boundaries, list)
        or len(boundaries) != len(partitions) - 1
    ):
        raise ProfiledRouteCableEnvelopeBindingV1Error(
            "route partitions or boundaries are incomplete"
        )

    samples: list[Mapping[str, Any]] = []
    expected_segment = 0
    previous_terminal: Mapping[str, Any] | None = None
    for partition_index, partition_raw in enumerate(partitions):
        partition = _sealed(
            partition_raw,
            "partition_intake_sha256",
            f"partition {partition_index}",
        )
        plan = partition.get("bounded_joint_sample_plan")
        start = partition.get("source_result_start_index")
        count = partition.get("source_result_count")
        end = partition.get("source_result_end_index_exclusive")
        if (
            partition.get("partition_index") != partition_index
            or start != expected_segment
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count <= 0
            or end != start + count
            or not isinstance(plan, list)
            or len(plan) != count + 1
            or any(not isinstance(sample, Mapping) for sample in plan)
        ):
            raise ProfiledRouteCableEnvelopeBindingV1Error(
                f"route partition ownership differs: {partition_index}"
            )
        if previous_terminal is None:
            samples.extend(plan)
        else:
            boundary = _sealed(
                boundaries[partition_index - 1],
                "boundary_lineage_sha256",
                f"partition boundary {partition_index - 1}",
            )
            successor = plan[0]
            if (
                boundary.get("predecessor_partition_index") != partition_index - 1
                or boundary.get("successor_partition_index") != partition_index
                or boundary.get("source_boundary_result_index") != start - 1
                or boundary.get("predecessor_terminal_sample_sha256")
                != _sha(previous_terminal)
                or boundary.get("successor_boundary_recheck_sample_sha256")
                != _sha(successor)
                or boundary.get("maximum_joint_difference_rad") != 0.0
                or boundary.get("boundary_recheck_required") is not True
                or boundary.get("extra_zero_length_sweep_envelope_required") is not False
                or previous_terminal.get("joint_positions_rad")
                != successor.get("joint_positions_rad")
            ):
                raise ProfiledRouteCableEnvelopeBindingV1Error(
                    f"route boundary lineage differs: {partition_index - 1}"
                )
            samples.extend(plan[1:])
        previous_terminal = plan[-1]
        expected_segment = end

    if (
        expected_segment != EXPECTED_ROUTE_SEGMENT_COUNT
        or len(samples) != EXPECTED_ROUTE_SAMPLE_COUNT
    ):
        raise ProfiledRouteCableEnvelopeBindingV1Error(
            "route extent differs from 329 configurations and 328 segments"
        )
    return samples


def bind_profiled_route_cable_envelope_v1(
    partition_document: Mapping[str, Any],
    envelope: InstalledCableEnvelopeIntakeV1,
) -> dict[str, Any]:
    """Bind a complete envelope intake to every sample and segment of a route."""

    if not isinstance(envelope, InstalledCableEnvelopeIntakeV1):
        raise TypeError("envelope must be InstalledCableEnvelopeIntakeV1")
    document = _sealed(
        partition_document,
        "partitioned_typing_collision_intake_sha256",
        "partitioned route",
    )
    slots = document.get("required_evidence_slots")
    if (
        document.get("schema") != PARTITION_SCHEMA
        or document.get("status") != PARTITION_READY
        or document.get("installed_collision_profile_sha256")
        != envelope.profile.content_sha256
        or not isinstance(slots, Mapping)
        or slots.get("route_segment_count") != EXPECTED_ROUTE_SEGMENT_COUNT
    ):
        raise ProfiledRouteCableEnvelopeBindingV1Error(
            "partition route and installed envelope profile lineage differ"
        )

    route = _route_samples(document)
    if (
        len(envelope.postures) != len(route)
        or len(envelope.swept_envelopes) != len(route) - 1
    ):
        raise ProfiledRouteCableEnvelopeBindingV1Error(
            "envelope evidence does not cover every route sample and segment"
        )

    posture_bindings: list[dict[str, Any]] = []
    for sequence, (sample, posture) in enumerate(zip(route, envelope.postures, strict=True)):
        joints = sample.get("joint_positions_rad")
        if (
            not isinstance(joints, Mapping)
            or posture.get("sequence") != sequence
            or posture.get("joint_state_sha256") != _sha(joints)
        ):
            raise ProfiledRouteCableEnvelopeBindingV1Error(
                f"envelope posture differs from route sample: {sequence}"
            )
        posture_bindings.append(
            {
                "route_sample_sequence": sequence,
                "posture_id": posture["posture_id"],
                "route_sample_sha256": _sha(sample),
                "joint_state_sha256": posture["joint_state_sha256"],
                "capsule_count": len(posture["capsules"]),
            }
        )

    segment_bindings: list[dict[str, Any]] = []
    for sequence, sweep in enumerate(envelope.swept_envelopes):
        first = posture_bindings[sequence]
        second = posture_bindings[sequence + 1]
        if (
            sweep.get("sequence") != sequence
            or sweep.get("start_posture_id") != first["posture_id"]
            or sweep.get("end_posture_id") != second["posture_id"]
        ):
            raise ProfiledRouteCableEnvelopeBindingV1Error(
                f"envelope sweep differs from route segment: {sequence}"
            )
        segment_bindings.append(
            {
                "route_segment_sequence": sequence,
                "start_route_sample_sha256": first["route_sample_sha256"],
                "end_route_sample_sha256": second["route_sample_sha256"],
                "start_posture_id": first["posture_id"],
                "end_posture_id": second["posture_id"],
                "capsule_count": len(sweep["capsules"]),
            }
        )

    core = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_class": EVIDENCE_CLASS,
        "installed_collision_profile_sha256": envelope.profile.content_sha256,
        "partitioned_typing_collision_intake_sha256": document[
            "partitioned_typing_collision_intake_sha256"
        ],
        "sampled_body_id": envelope.sampled_body_id,
        "source_sha256": envelope.source_sha256,
        "envelope_intake_sha256": envelope.content_sha256,
        "maximum_uncertainty_mm": envelope.maximum_uncertainty_mm,
        "route_sample_count": len(posture_bindings),
        "route_segment_count": len(segment_bindings),
        "posture_bindings": posture_bindings,
        "segment_bindings": segment_bindings,
        "blockers": ["REVIEWED_INSTALLED_CONFIGURATION_ENVELOPE_EVIDENCE_REQUIRED"],
        "authority": dict(ZERO_AUTHORITY),
    }
    return {**core, "profiled_route_cable_envelope_binding_sha256": _sha(core)}


__all__ = [
    "EXPECTED_ROUTE_SAMPLE_COUNT",
    "EXPECTED_ROUTE_SEGMENT_COUNT",
    "SCHEMA",
    "STATUS",
    "ZERO_AUTHORITY",
    "ProfiledRouteCableEnvelopeBindingV1Error",
    "bind_profiled_route_cable_envelope_v1",
]
