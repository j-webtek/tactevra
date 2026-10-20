"""Bind configuration-sampled envelope evidence to one exact profiled route.

The installed envelope intake validates posture-local and adjacent-sweep
geometry.  This boundary additionally proves that every posture belongs to the
exact ordered 329-configuration route behind one attachment profile and that
all 328 adjacent route segments have envelope coverage.  It remains an offline
zero-authority receipt; the current intake evidence class is synthetic and
cannot satisfy installed qualification.  A second additive join accepts only
the existing independently reviewed, profile-separated evidence result and
binds its measured geometry to the same exact route without granting execution
authority.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Mapping

from rocell.simulation.collision import (
    CollisionBindingMode,
    CollisionEvidenceState,
)

from .installed_cable_envelope_intake_v1 import (
    EVIDENCE_CLASS,
    InstalledCableEnvelopeIntakeV1,
)
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .partitioned_typing_collision_intake_v1 import (
    READY_STATUS as PARTITION_READY,
    SCHEMA as PARTITION_SCHEMA,
)

if TYPE_CHECKING:
    from .fixed_camera_keyboard_profiled_collision_evidence_admission_v1 import (
        FixedCameraKeyboardProfiledCollisionEvidenceAdmissionResultV1,
    )


SCHEMA = "rocell.profiled_route_cable_envelope_binding.v1"
STATUS = "ROUTE_BOUND_SYNTHETIC_ENVELOPE_INSTALLED_QUALIFICATION_BLOCKED"
ADMITTED_SCHEMA = (
    "rocell.admitted_profiled_route_configuration_envelope_binding.v1"
)
ADMITTED_STATUS = (
    "ADMITTED_REVIEWED_CONFIGURATION_ENVELOPE_ROUTE_BOUND_ZERO_AUTHORITY"
)
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


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


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


def bind_admitted_profiled_route_configuration_envelope_v1(
    partition_document: Mapping[str, Any],
    installed_profile: InstalledCollisionGeometryProfile,
    admission: FixedCameraKeyboardProfiledCollisionEvidenceAdmissionResultV1,
    *,
    attachment_profile: str,
    sampled_body_id: str = "attachment:moving_camera_cable",
) -> dict[str, Any]:
    """Join independently reviewed measured evidence to one exact route.

    The upstream admission has already strict-decoded the completed evidence and
    its disjoint review.  This join independently rechecks that admission's
    sealed public records, the installed profile, every partition sample, every
    adjacent sweep, and the repeated partition boundary before emitting a
    zero-authority route binding.
    """

    # Keep this dependency local: the base offline package intentionally omits
    # the numerical stack used by the installed evidence admission workflow.
    from .fixed_camera_keyboard_profiled_collision_evidence_admission_v1 import (
        RECEIPT_SCHEMA as ADMISSION_RECEIPT_SCHEMA,
        RECEIPT_STATUS as ADMISSION_RECEIPT_STATUS,
        SCHEMA as ADMISSION_SCHEMA,
        STATUS as ADMISSION_STATUS,
        ZERO_AUTHORITY as ADMISSION_ZERO_AUTHORITY,
        FixedCameraKeyboardProfiledCollisionEvidenceAdmissionResultV1,
    )

    if not isinstance(installed_profile, InstalledCollisionGeometryProfile):
        raise TypeError("installed_profile must be InstalledCollisionGeometryProfile")
    if not isinstance(
        admission, FixedCameraKeyboardProfiledCollisionEvidenceAdmissionResultV1
    ):
        raise TypeError(
            "admission must be FixedCameraKeyboardProfiledCollisionEvidenceAdmissionResultV1"
        )
    if attachment_profile not in {"no_attachment", "stylus_attachment"}:
        raise ProfiledRouteCableEnvelopeBindingV1Error(
            "attachment_profile is not supported"
        )

    manifest = admission.manifest
    manifest_core = dict(manifest)
    manifest_sha256 = manifest_core.pop(
        "profiled_collision_evidence_admission_manifest_sha256", None
    )
    receipt = admission.receipt
    profiles = manifest.get("profiles", {})
    profile_row = profiles.get(attachment_profile)
    evidence = admission.admitted_profiles.get(attachment_profile)
    if (
        manifest.get("schema") != ADMISSION_SCHEMA
        or manifest.get("status") != ADMISSION_STATUS
        or manifest_sha256 != _sha(manifest_core)
        or manifest.get("profile_separation_preserved") is not True
        or manifest.get("independent_reviews_verified") is not True
        or manifest.get("typed_evaluator_inputs_decoded") is not True
        or manifest.get("authority") != ADMISSION_ZERO_AUTHORITY
        or set(profiles) != {"no_attachment", "stylus_attachment"}
        or set(admission.admitted_profiles)
        != {"no_attachment", "stylus_attachment"}
        or receipt.get("schema") != ADMISSION_RECEIPT_SCHEMA
        or receipt.get("status") != ADMISSION_RECEIPT_STATUS
        or receipt.get("profile_separation_preserved") is not True
        or receipt.get("independent_reviews_verified") is not True
        or receipt.get("authority") != ADMISSION_ZERO_AUTHORITY
        or not isinstance(profile_row, Mapping)
        or evidence is None
        or evidence.profile != attachment_profile
        or not _is_digest(evidence.completion_sha256)
        or not _is_digest(evidence.review_sha256)
        or profile_row.get("installed_collision_profile_sha256")
        != installed_profile.content_sha256
        or profile_row.get("completion_sha256") != evidence.completion_sha256
        or profile_row.get("review_sha256") != evidence.review_sha256
    ):
        raise ProfiledRouteCableEnvelopeBindingV1Error(
            "reviewed evidence admission or selected profile lineage differs"
        )

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
        != installed_profile.content_sha256
        or not isinstance(slots, Mapping)
        or profile_row.get("required_evidence_slots") != slots
        or slots.get("unique_route_configuration_count")
        != EXPECTED_ROUTE_SAMPLE_COUNT
        or slots.get("route_segment_count") != EXPECTED_ROUTE_SEGMENT_COUNT
    ):
        raise ProfiledRouteCableEnvelopeBindingV1Error(
            "partition route and admitted installed profile lineage differ"
        )

    sampled_body_ids = {
        body.body_id
        for body in installed_profile.contract.bodies
        if body.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
    }
    if sampled_body_ids != {sampled_body_id}:
        raise ProfiledRouteCableEnvelopeBindingV1Error(
            "installed profile configuration-sampled body inventory differs"
        )

    route = _route_samples(document)
    partitions = document["partitions"]
    geometry_partitions = evidence.configuration_geometry_by_partition
    sweep_partitions = evidence.sweep_envelopes_by_partition
    if (
        len(geometry_partitions) != len(partitions)
        or len(sweep_partitions) != len(partitions)
    ):
        raise ProfiledRouteCableEnvelopeBindingV1Error(
            "admitted evidence partition coverage differs"
        )

    accepted_sources = set(installed_profile.source_bindings.values())
    posture_bindings: list[dict[str, Any]] = []
    segment_bindings: list[dict[str, Any]] = []
    previous_terminal: tuple[str, str] | None = None
    for partition_index, partition in enumerate(partitions):
        plan = partition["bounded_joint_sample_plan"]
        geometry_samples = geometry_partitions[partition_index]
        sweep_samples = sweep_partitions[partition_index]
        if (
            len(geometry_samples) != len(plan)
            or len(sweep_samples) != len(plan) - 1
        ):
            raise ProfiledRouteCableEnvelopeBindingV1Error(
                f"admitted evidence coverage differs in partition {partition_index}"
            )
        partition_start = partition["source_result_start_index"]
        for local_sequence, (sample, bindings) in enumerate(
            zip(plan, geometry_samples, strict=True)
        ):
            binding = bindings.get(sampled_body_id)
            if (
                set(bindings) != sampled_body_ids
                or binding is None
                or binding.body_id != sampled_body_id
                or binding.source_sha256 not in accepted_sources
                or binding.geometry.evidence_state
                is not CollisionEvidenceState.ACCEPTED_MEASURED
            ):
                raise ProfiledRouteCableEnvelopeBindingV1Error(
                    f"admitted posture evidence differs at {partition_index}:{local_sequence}"
                )
            sample_sha256 = _sha(sample)
            geometry_sha256 = _sha(binding.geometry.to_dict())
            if partition_index and local_sequence == 0:
                if previous_terminal != (geometry_sha256, binding.source_sha256):
                    raise ProfiledRouteCableEnvelopeBindingV1Error(
                        f"rechecked boundary geometry differs: {partition_index - 1}"
                    )
                continue
            route_sequence = partition_start + local_sequence
            posture_bindings.append(
                {
                    "route_sample_sequence": route_sequence,
                    "route_sample_sha256": sample_sha256,
                    "joint_state_sha256": _sha(sample["joint_positions_rad"]),
                    "configuration_geometry_sha256": geometry_sha256,
                    "source_sha256": binding.source_sha256,
                    "primitive_count": len(binding.geometry.primitives),
                }
            )
            previous_terminal = (geometry_sha256, binding.source_sha256)

        for local_sequence, bindings in enumerate(sweep_samples):
            binding = bindings.get(sampled_body_id)
            start_sha256 = _sha(plan[local_sequence])
            end_sha256 = _sha(plan[local_sequence + 1])
            route_sequence = partition_start + local_sequence
            if (
                set(bindings) != sampled_body_ids
                or binding is None
                or binding.body_id != sampled_body_id
                or binding.segment_sequence != local_sequence
                or binding.start_sample_sha256 != start_sha256
                or binding.end_sample_sha256 != end_sha256
                or binding.source_sha256 not in accepted_sources
                or binding.geometry_root_frame.evidence_state
                is not CollisionEvidenceState.ACCEPTED_MEASURED
            ):
                raise ProfiledRouteCableEnvelopeBindingV1Error(
                    f"admitted sweep evidence differs at {partition_index}:{local_sequence}"
                )
            segment_bindings.append(
                {
                    "route_segment_sequence": route_sequence,
                    "start_route_sample_sha256": _sha(route[route_sequence]),
                    "end_route_sample_sha256": _sha(route[route_sequence + 1]),
                    "sweep_geometry_sha256": _sha(
                        binding.geometry_root_frame.to_dict()
                    ),
                    "source_sha256": binding.source_sha256,
                    "primitive_count": len(
                        binding.geometry_root_frame.primitives
                    ),
                }
            )

    if (
        len(posture_bindings) != EXPECTED_ROUTE_SAMPLE_COUNT
        or [row["route_sample_sequence"] for row in posture_bindings]
        != list(range(EXPECTED_ROUTE_SAMPLE_COUNT))
        or len(segment_bindings) != EXPECTED_ROUTE_SEGMENT_COUNT
        or [row["route_segment_sequence"] for row in segment_bindings]
        != list(range(EXPECTED_ROUTE_SEGMENT_COUNT))
    ):
        raise ProfiledRouteCableEnvelopeBindingV1Error(
            "admitted evidence does not exactly cover the route"
        )

    clearance = installed_profile.clearance_policy
    core = {
        "schema": ADMITTED_SCHEMA,
        "status": ADMITTED_STATUS,
        "evidence_class": "REVIEWED_INSTALLED",
        "attachment_profile": attachment_profile,
        "installed_collision_profile_sha256": installed_profile.content_sha256,
        "partitioned_typing_collision_intake_sha256": document[
            "partitioned_typing_collision_intake_sha256"
        ],
        "profiled_collision_evidence_admission_manifest_sha256": manifest_sha256,
        "completion_sha256": evidence.completion_sha256,
        "independent_review_sha256": evidence.review_sha256,
        "sampled_body_id": sampled_body_id,
        "accepted_source_sha256_values": sorted(
            {row["source_sha256"] for row in posture_bindings + segment_bindings}
        ),
        "clearance_policy": {
            "minimum_separation_mm": clearance.minimum_separation_mm,
            "geometry_uncertainty_mm_per_body": (
                clearance.geometry_uncertainty_mm_per_body
            ),
            "pose_uncertainty_mm_per_body": clearance.pose_uncertainty_mm_per_body,
            "source_reference": clearance.source_reference,
        },
        "route_sample_count": len(posture_bindings),
        "route_segment_count": len(segment_bindings),
        "posture_bindings": posture_bindings,
        "segment_bindings": segment_bindings,
        "next_required_stage": "RUN_PROFILE_BOUND_PARTITION_COLLISION_EVALUATORS",
        "authority": dict(ZERO_AUTHORITY),
    }
    return {
        **core,
        "admitted_profiled_route_configuration_envelope_binding_sha256": _sha(core),
    }


__all__ = [
    "EXPECTED_ROUTE_SAMPLE_COUNT",
    "EXPECTED_ROUTE_SEGMENT_COUNT",
    "ADMITTED_SCHEMA",
    "ADMITTED_STATUS",
    "SCHEMA",
    "STATUS",
    "ZERO_AUTHORITY",
    "ProfiledRouteCableEnvelopeBindingV1Error",
    "bind_profiled_route_cable_envelope_v1",
    "bind_admitted_profiled_route_configuration_envelope_v1",
]
