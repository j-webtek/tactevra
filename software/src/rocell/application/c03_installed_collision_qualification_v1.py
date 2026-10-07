"""Bind the exact C03 route to measured installed-collision evidence.

This boundary composes the strict C03 route handoff with the deterministic
installed-collision-profile builder.  Missing or incomplete measurements stay
explicit blockers.  A complete manifest produces only a zero-authority profile
and a partitioned evidence intake; it never claims continuous collision
clearance, generates controller commands, or grants execution authority.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .bounded_segment_collision_qualification import BoundedSegmentSamplingPolicy
from .c03_route_collision_handoff_v1 import prepare_c03_route_collision_handoff_v1
from .context import SimulationContext
from .installed_collision_profile_builder_v1 import (
    BUILT_STATUS,
    build_installed_collision_profile_v1,
    load_installed_collision_geometry_profile_from_bytes_v1,
)
from .partitioned_typing_collision_intake_v1 import READY_STATUS


SCHEMA = "tactevra.c03_installed_collision_qualification.v1"
MANIFEST_REQUIRED_STATUS = "BLOCKED_MEASUREMENT_MANIFEST_REQUIRED"
READY_FOR_EVIDENCE_STATUS = "READY_FOR_PARTITIONED_COLLISION_EVIDENCE"


class C03InstalledCollisionQualificationV1Error(ValueError):
    """The supplied measurement input is ambiguous or internally inconsistent."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def prepare_c03_installed_collision_qualification_v1(
    result: Mapping[str, Any],
    context: SimulationContext,
    *,
    measurement_manifest_path: str | Path | None = None,
    expected_measurement_manifest_file_sha256: str | None = None,
    sampling_policy: BoundedSegmentSamplingPolicy | None = None,
    maximum_partitions: int = 64,
) -> dict[str, Any]:
    """Build the measured profile when possible and expose remaining evidence slots."""

    supplied = measurement_manifest_path is not None
    hash_supplied = expected_measurement_manifest_file_sha256 is not None
    if supplied != hash_supplied:
        raise C03InstalledCollisionQualificationV1Error(
            "measurement manifest path and expected file SHA-256 must be supplied together"
        )

    # Authenticate the exact admitted route before reading caller-selected
    # measurement bytes. Reuse this profile-free handoff unless a complete
    # manifest produces a profile that must be bound into a second handoff.
    handoff = prepare_c03_route_collision_handoff_v1(
        result,
        context,
        sampling_policy=sampling_policy,
        maximum_partitions=maximum_partitions,
    )
    profile_build = None
    installed_profile = None
    if supplied:
        profile_build = build_installed_collision_profile_v1(
            measurement_manifest_path,
            expected_measurement_manifest_file_sha256,
            context=context,
        )
        if profile_build.status == BUILT_STATUS:
            if (
                profile_build.profile_bytes is None
                or profile_build.profile_file_sha256 is None
                or profile_build.profile_document is None
            ):
                raise C03InstalledCollisionQualificationV1Error(
                    "successful profile build omitted required profile bytes"
                )
            installed_profile = load_installed_collision_geometry_profile_from_bytes_v1(
                profile_build.profile_bytes,
                profile_build.profile_file_sha256,
                context=context,
                expected_source_bindings=profile_build.profile_document[
                    "source_bindings"
                ],
            )
            handoff = prepare_c03_route_collision_handoff_v1(
                result,
                context,
                installed_profile=installed_profile,
                sampling_policy=sampling_policy,
                maximum_partitions=maximum_partitions,
            )
    intake = handoff["collision_intake"]
    if profile_build is None:
        status = MANIFEST_REQUIRED_STATUS
        blockers = [
            "INSTALLED_COLLISION_MEASUREMENT_MANIFEST_REQUIRED",
            *intake["blockers"],
        ]
        next_stage = "CAPTURE_HASH_BOUND_INSTALLED_COLLISION_MEASUREMENTS"
    elif profile_build.status != BUILT_STATUS:
        status = profile_build.status
        blockers = [
            *profile_build.blockers,
            *intake["blockers"],
        ]
        next_stage = "COMPLETE_INSTALLED_COLLISION_MEASUREMENTS"
    else:
        if intake["status"] != READY_STATUS:
            raise C03InstalledCollisionQualificationV1Error(
                "built profile did not enter the partitioned collision evidence intake"
            )
        status = READY_FOR_EVIDENCE_STATUS
        blockers = list(intake["blockers"])
        next_stage = intake["next_required_stage"]

    # Preserve order while avoiding duplicated blockers from the composed layers.
    blockers = list(dict.fromkeys(blockers))
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "measurement_manifest_supplied": supplied,
        "measurement_manifest_file_sha256": (
            None
            if profile_build is None
            else profile_build.measurement_manifest_file_sha256
        ),
        "measurement_manifest_content_sha256": (
            None
            if profile_build is None
            else profile_build.measurement_manifest_content_sha256
        ),
        "profile_build": (None if profile_build is None else profile_build.to_dict()),
        "profile_file_sha256": (
            None if profile_build is None else profile_build.profile_file_sha256
        ),
        "c03_collision_handoff": handoff,
        "blockers": blockers,
        "next_required_stage": next_stage,
        "installed_geometry_collision_screening_executed": False,
        "continuous_collision_proven": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {
        **core,
        "c03_installed_collision_qualification_sha256": _sha256(core),
    }


__all__ = [
    "MANIFEST_REQUIRED_STATUS",
    "READY_FOR_EVIDENCE_STATUS",
    "SCHEMA",
    "C03InstalledCollisionQualificationV1Error",
    "prepare_c03_installed_collision_qualification_v1",
]
