"""Run profiled collision qualification only from exact-route evidence bindings.

This zero-authority boundary independently verifies that each reviewed installed
configuration-envelope receipt covers the exact ordered route behind its
profile partition document.  Only then does it invoke the existing partition
collision evaluator and ICQ-8 route-clearance reconstruction.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Mapping

from .fixed_camera_keyboard_clearance_intake_v1 import SUPPORTED_PROFILES
from .partitioned_typing_collision_intake_v1 import (
    READY_STATUS as PARTITION_READY,
    SCHEMA as PARTITION_SCHEMA,
)
from .profiled_route_cable_envelope_binding_v1 import (
    ADMITTED_SCHEMA as ROUTE_BINDING_SCHEMA,
    ADMITTED_STATUS as ROUTE_BINDING_STATUS,
    EXPECTED_ROUTE_SAMPLE_COUNT,
    EXPECTED_ROUTE_SEGMENT_COUNT,
    ZERO_AUTHORITY as ROUTE_BINDING_ZERO_AUTHORITY,
)

if TYPE_CHECKING:
    from rocell.calibration import PlannerCalibrationSnapshot

    from .context import SimulationContext
    from .fixed_camera_keyboard_profiled_collision_evidence_admission_v1 import (
        AdmittedProfileCollisionEvidenceV1,
    )
    from .installed_collision_geometry import InstalledCollisionGeometryProfile


SCHEMA = "rocell.fixed_camera_keyboard_route_bound_collision_qualification.v1"
STATUS_READY = "ROUTE_BOUND_CLEARANCE_RECONSTRUCTED_FRESH_ENTRY_REQUIRED"
STATUS_REJECTED = "REJECTED_ROUTE_BOUND_COLLISION_DETECTED"
STATUS_BLOCKED = "BLOCKED_ROUTE_BOUND_CLEARANCE_EVIDENCE_INCOMPLETE"
ZERO_AUTHORITY: Mapping[str, object] = {
    "installed_geometry_collision_screening_executed": True,
    "fresh_observed_start_state_present": False,
    "controller_commands": [],
    "hardware_commands_generated": 0,
    "hardware_writes": 0,
    "hardware_access": False,
    "physical_movements": 0,
    "physical_authority": False,
    "physical_release_effect": "NONE",
}


class FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(ValueError):
    """Profile, route, reviewed evidence, or downstream lineage differs."""


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
        raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
            "route-bound qualification evidence is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sealed(value: Mapping[str, Any], hash_field: str, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    core = dict(value)
    supplied = core.pop(hash_field, None)
    if not isinstance(supplied, str) or supplied != _sha(core):
        raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
            f"{label} hash differs"
        )
    return dict(value)


def _profile_map(value: Mapping[str, Any], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != set(SUPPORTED_PROFILES):
        raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
            f"{label} must contain the exact supported profile set"
        )


def _route_samples(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    partitions = document.get("partitions")
    if not isinstance(partitions, list) or not partitions:
        raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
            "partition route is absent"
        )
    route: list[Mapping[str, Any]] = []
    for partition_index, partition in enumerate(partitions):
        if not isinstance(partition, Mapping):
            raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
                "partition route is malformed"
            )
        plan = partition.get("bounded_joint_sample_plan")
        if not isinstance(plan, list) or len(plan) < 2:
            raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
                "partition sample plan is incomplete"
            )
        rows = plan if partition_index == 0 else plan[1:]
        route.extend(rows)
    if len(route) != EXPECTED_ROUTE_SAMPLE_COUNT:
        raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
            "partition route extent differs"
        )
    return route


def _clearance_policy(profile: Any) -> dict[str, Any]:
    policy = profile.clearance_policy
    return {
        "minimum_separation_mm": policy.minimum_separation_mm,
        "geometry_uncertainty_mm_per_body": policy.geometry_uncertainty_mm_per_body,
        "pose_uncertainty_mm_per_body": policy.pose_uncertainty_mm_per_body,
        "source_reference": policy.source_reference,
    }


def _verify_profile_binding(
    profile_name: str,
    partition_document: Mapping[str, Any],
    evidence: Any,
    installed_profile: Any,
    route_binding: Mapping[str, Any],
) -> dict[str, Any]:
    document = _sealed(
        partition_document,
        "partitioned_typing_collision_intake_sha256",
        f"partition document {profile_name}",
    )
    binding = _sealed(
        route_binding,
        "admitted_profiled_route_configuration_envelope_binding_sha256",
        f"route binding {profile_name}",
    )
    posture_bindings = binding.get("posture_bindings")
    segment_bindings = binding.get("segment_bindings")
    accepted_sources = binding.get("accepted_source_sha256_values")
    if (
        document.get("schema") != PARTITION_SCHEMA
        or document.get("status") != PARTITION_READY
        or binding.get("schema") != ROUTE_BINDING_SCHEMA
        or binding.get("status") != ROUTE_BINDING_STATUS
        or binding.get("evidence_class") != "REVIEWED_INSTALLED"
        or binding.get("attachment_profile") != profile_name
        or getattr(evidence, "profile", None) != profile_name
        or binding.get("installed_collision_profile_sha256")
        != installed_profile.content_sha256
        or document.get("installed_collision_profile_sha256")
        != installed_profile.content_sha256
        or binding.get("partitioned_typing_collision_intake_sha256")
        != document["partitioned_typing_collision_intake_sha256"]
        or binding.get("completion_sha256")
        != getattr(evidence, "completion_sha256", None)
        or binding.get("independent_review_sha256")
        != getattr(evidence, "review_sha256", None)
        or binding.get("clearance_policy") != _clearance_policy(installed_profile)
        or binding.get("authority") != ROUTE_BINDING_ZERO_AUTHORITY
        or binding.get("route_sample_count") != EXPECTED_ROUTE_SAMPLE_COUNT
        or binding.get("route_segment_count") != EXPECTED_ROUTE_SEGMENT_COUNT
        or not isinstance(posture_bindings, list)
        or len(posture_bindings) != EXPECTED_ROUTE_SAMPLE_COUNT
        or not isinstance(segment_bindings, list)
        or len(segment_bindings) != EXPECTED_ROUTE_SEGMENT_COUNT
        or not isinstance(accepted_sources, list)
        or not accepted_sources
        or accepted_sources != sorted(set(accepted_sources))
    ):
        raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
            f"reviewed route binding lineage differs: {profile_name}"
        )

    route = _route_samples(document)
    used_sources: set[str] = set()
    for sequence, (sample, row) in enumerate(
        zip(route, posture_bindings, strict=True)
    ):
        if not isinstance(row, Mapping):
            raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
                f"posture binding is malformed: {profile_name}:{sequence}"
            )
        used_sources.add(str(row.get("source_sha256")))
        if (
            row.get("route_sample_sequence") != sequence
            or row.get("route_sample_sha256") != _sha(sample)
            or row.get("joint_state_sha256")
            != _sha(sample.get("joint_positions_rad"))
            or row.get("source_sha256") not in accepted_sources
        ):
            raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
                f"posture binding route ownership differs: {profile_name}:{sequence}"
            )

    for sequence, row in enumerate(segment_bindings):
        if not isinstance(row, Mapping):
            raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
                f"segment binding is malformed: {profile_name}:{sequence}"
            )
        used_sources.add(str(row.get("source_sha256")))
        if (
            row.get("route_segment_sequence") != sequence
            or row.get("start_route_sample_sha256") != _sha(route[sequence])
            or row.get("end_route_sample_sha256") != _sha(route[sequence + 1])
            or row.get("source_sha256") not in accepted_sources
        ):
            raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
                f"segment binding route ownership differs: {profile_name}:{sequence}"
            )
    if used_sources != set(accepted_sources):
        raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
            f"accepted source coverage differs: {profile_name}"
        )

    return {
        "profile": profile_name,
        "installed_collision_profile_sha256": installed_profile.content_sha256,
        "partitioned_typing_collision_intake_sha256": document[
            "partitioned_typing_collision_intake_sha256"
        ],
        "completion_sha256": binding["completion_sha256"],
        "independent_review_sha256": binding["independent_review_sha256"],
        "route_envelope_binding_sha256": binding[
            "admitted_profiled_route_configuration_envelope_binding_sha256"
        ],
        "route_sample_count": EXPECTED_ROUTE_SAMPLE_COUNT,
        "route_segment_count": EXPECTED_ROUTE_SEGMENT_COUNT,
    }


def qualify_fixed_camera_keyboard_route_bound_collisions_v1(
    context: SimulationContext,
    calibration_snapshot: PlannerCalibrationSnapshot,
    partition_documents: Mapping[str, Mapping[str, Any]],
    admitted_profiles: Mapping[str, AdmittedProfileCollisionEvidenceV1],
    installed_collision_profiles: Mapping[str, InstalledCollisionGeometryProfile],
    route_envelope_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Verify exact-route evidence, then run partition evaluation and ICQ-8."""

    for value, label in (
        (partition_documents, "partition_documents"),
        (admitted_profiles, "admitted_profiles"),
        (installed_collision_profiles, "installed_collision_profiles"),
        (route_envelope_bindings, "route_envelope_bindings"),
    ):
        _profile_map(value, label)

    profiles = {
        profile_name: _verify_profile_binding(
            profile_name,
            partition_documents[profile_name],
            admitted_profiles[profile_name],
            installed_collision_profiles[profile_name],
            route_envelope_bindings[profile_name],
        )
        for profile_name in SUPPORTED_PROFILES
    }

    # Keep numerical collision dependencies out of the lightweight base import.
    from .fixed_camera_keyboard_profiled_partition_collision_evaluator_v1 import (
        evaluate_fixed_camera_keyboard_profiled_collision_partitions_v1,
    )
    from .fixed_camera_keyboard_profiled_route_clearance_reconstruction_v1 import (
        STATUS_BLOCKED as RECONSTRUCTION_BLOCKED,
        STATUS_READY as RECONSTRUCTION_READY,
        STATUS_REJECTED as RECONSTRUCTION_REJECTED,
        reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1,
    )

    evaluation = evaluate_fixed_camera_keyboard_profiled_collision_partitions_v1(
        context,
        calibration_snapshot,
        partition_documents,
        admitted_profiles,
        installed_collision_profiles,
    )
    reconstruction = reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1(
        partition_documents,
        evaluation,
    )
    reconstruction_status = reconstruction.get("status")
    status = {
        RECONSTRUCTION_READY: STATUS_READY,
        RECONSTRUCTION_REJECTED: STATUS_REJECTED,
        RECONSTRUCTION_BLOCKED: STATUS_BLOCKED,
    }.get(reconstruction_status)
    if status is None:
        raise FixedCameraKeyboardRouteBoundCollisionQualificationV1Error(
            "route clearance reconstruction status differs"
        )

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "disposition": reconstruction["disposition"],
        "profiles": profiles,
        "source_profiled_partition_collision_evaluation_sha256": evaluation[
            "profiled_partition_collision_evaluation_sha256"
        ],
        "source_profiled_route_clearance_reconstruction_sha256": reconstruction[
            "profiled_route_clearance_reconstruction_sha256"
        ],
        "profile_separation_preserved": True,
        "exact_route_binding_verified_before_evaluation": True,
        "expected_route_sample_count_per_profile": EXPECTED_ROUTE_SAMPLE_COUNT,
        "expected_route_segment_count_per_profile": EXPECTED_ROUTE_SEGMENT_COUNT,
        "blockers": list(reconstruction["blockers"]),
        "next_required_stage": reconstruction["next_required_stage"],
        "authority": dict(ZERO_AUTHORITY),
    }
    return {
        **core,
        "route_bound_collision_qualification_sha256": _sha(core),
    }


__all__ = [
    "SCHEMA",
    "STATUS_READY",
    "STATUS_REJECTED",
    "STATUS_BLOCKED",
    "ZERO_AUTHORITY",
    "FixedCameraKeyboardRouteBoundCollisionQualificationV1Error",
    "qualify_fixed_camera_keyboard_route_bound_collisions_v1",
]
