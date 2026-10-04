"""Screen the observed-to-PARK entry envelope against installed geometry.

ARM-150 supplies the exact bounded joint samples.  This adapter translates
those samples into the existing FK collision boundary while requiring measured,
profile-bound rigid attachments and configuration-sampled geometry.  A clear
discrete result still requires continuous sweep and physical dynamics evidence.
No commands or execution authority are produced.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from rocell.calibration import PlannerCalibrationSnapshot

from .bounded_segment_collision_qualification import (
    MeasuredSegmentConfigurationSample,
)
from .context import SimulationContext
from .fk_collision_pose_adapter import (
    FkCollisionPoseAdapterError,
    MeasuredRigidAttachmentBinding,
    derive_and_evaluate_fk_waypoint_collisions,
)
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .measured_trajectory_screening import SCHEMA as TRAJECTORY_SCREENING_SCHEMA
from .typing_observed_route_entry_v1 import (
    TypingObservedRouteEntryV1Error,
    parse_typing_observed_route_entry_v1,
)


SCHEMA = "rocell.typing_observed_route_entry_collision.v1"
CLEAR_STATUS = "ENTRY_SAMPLES_CLEAR_CONTINUOUS_PROOF_REQUIRED"
COLLISION_STATUS = "BLOCKED_ENTRY_SAMPLE_COLLISION_DETECTED"
INCOMPLETE_STATUS = "BLOCKED_INCOMPLETE_ENTRY_COLLISION_EVIDENCE"
REQUIRED_NEXT_EVIDENCE = (
    "DEPLOYMENT_QUALIFIED_PLAN_REQUIRED",
    "CONTINUOUS_ENTRY_SWEEP_QUALIFICATION_REQUIRED",
    "PHYSICALLY_QUALIFIED_DYNAMICS_REQUIRED",
    "INDEPENDENT_EFFECT_VERIFIER_REQUIRED",
    "PER_ACTION_REVIEW_BINDINGS_REQUIRED",
)
_SHA = re.compile(r"^[0-9a-f]{64}$")
_NESTED_STATUSES = {
    "DISCRETE_WAYPOINTS_CLEAR_CONTINUOUS_PROOF_REQUIRED",
    "BLOCKED_COLLISION_DETECTED",
    "BLOCKED_INCOMPLETE_WAYPOINT_COLLISION_EVIDENCE",
}
_FIELDS = {
    "schema", "status", "request_id", "materialization_sha256",
    "observed_route_entry_sha256", "observed_trajectory_ik_sha256",
    "observed_ik_seed_sha256", "observed_start_state_sha256",
    "calibration_snapshot_sha256", "build_snapshot_sha256",
    "controller_session_id", "installed_collision_profile_sha256",
    "collision_contract_sha256", "expanded_trajectory_screening_sha256",
    "sample_count", "sample_plan_sha256", "fk_collision_sequence_sha256",
    "fk_collision_qualification", "entry_sample_collision_screening_executed",
    "all_entry_samples_collision_free", "continuous_collision_proven",
    "measured_dynamics_qualified", "required_next_evidence",
    "permit_review_ready", "eligible_for_executor", "automatic_retry_allowed",
    "controller_commands", "wire_commands", "hardware_commands_generated",
    "hardware_access", "physical_authority",
    "observed_route_entry_collision_sha256",
}


class TypingObservedRouteEntryCollisionV1Error(ValueError):
    """Entry collision evidence is incomplete, crossed, or modified."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingObservedRouteEntryCollisionV1Error(
            "entry collision report is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _expanded_trajectory(
    entry: Mapping[str, Any],
    context: SimulationContext,
    profile: InstalledCollisionGeometryProfile,
) -> dict[str, Any]:
    waypoints: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for index, sample in enumerate(entry["sample_plan"]):
        waypoints.append(
            {
                "sequence": index,
                "sample_id": sample["sample_id"],
                "source_segment_index": sample["source_segment_index"],
                "subdivision_index": sample["subdivision_index"],
                "subdivision_count": sample["subdivision_count"],
                "interpolation_ratio": sample["interpolation_ratio"],
                "source_observed_route_entry_sha256": entry[
                    "observed_route_entry_sha256"
                ],
            }
        )
        results.append(
            {
                "waypoint_sequence": index,
                "accepted": True,
                "solution_arm_joint_positions_rad": sample[
                    "joint_positions_rad"
                ],
                "source_sample_sha256": sample["sample_sha256"],
            }
        )
    core: dict[str, Any] = {
        "schema": TRAJECTORY_SCREENING_SCHEMA,
        "calibration_snapshot_sha256": entry["calibration_snapshot_sha256"],
        "build_snapshot_sha256": entry["build_snapshot_sha256"],
        "kinematic_model_sha256": context.scenario.model_sha256,
        "installed_collision_profile_sha256": profile.content_sha256,
        "collision_contract_sha256": profile.contract.content_hash,
        "ik_all_waypoints_accepted": True,
        "waypoints": waypoints,
        "joint_results": results,
        "source_trajectory_screening_sha256": entry[
            "canonical_ik_screen_sha256"
        ],
        "source_observed_route_entry_sha256": entry[
            "observed_route_entry_sha256"
        ],
        "bounded_segment_sampling_policy_sha256": entry["sampling_policy"][
            "sampling_policy_sha256"
        ],
    }
    return {**core, "trajectory_screening_sha256": _sha(core)}


def qualify_typing_observed_route_entry_collision_v1(
    observed_route_entry: Mapping[str, Any],
    context: SimulationContext,
    snapshot: PlannerCalibrationSnapshot,
    installed_profile: InstalledCollisionGeometryProfile,
    attachment_bindings: Sequence[MeasuredRigidAttachmentBinding],
    configuration_samples: Sequence[MeasuredSegmentConfigurationSample],
) -> dict[str, Any]:
    """Run installed full-body collision checks over every entry sample."""

    try:
        entry = parse_typing_observed_route_entry_v1(observed_route_entry)
    except TypingObservedRouteEntryV1Error as exc:
        raise TypingObservedRouteEntryCollisionV1Error(str(exc)) from exc
    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(snapshot, PlannerCalibrationSnapshot):
        raise TypeError("snapshot must be a PlannerCalibrationSnapshot")
    if not isinstance(installed_profile, InstalledCollisionGeometryProfile):
        raise TypeError("installed_profile must be an InstalledCollisionGeometryProfile")
    try:
        supplied = tuple(configuration_samples)
    except TypeError as exc:
        raise TypeError("configuration_samples must be a finite sequence") from exc
    if len(supplied) != entry["sample_count"]:
        raise TypingObservedRouteEntryCollisionV1Error(
            "configuration geometry must cover every observed entry sample"
        )
    geometry: list[Mapping[str, Any]] = []
    for sample, evidence in zip(entry["sample_plan"], supplied, strict=True):
        if not isinstance(evidence, MeasuredSegmentConfigurationSample):
            raise TypeError(
                "configuration_samples must contain measured segment samples"
            )
        if (
            evidence.sample_sequence != sample["sample_sequence"]
            or evidence.sample_plan_sha256 != sample["sample_sha256"]
        ):
            raise TypingObservedRouteEntryCollisionV1Error(
                f"configuration sample {sample['sample_sequence']} does not bind its entry sample"
            )
        geometry.append(evidence.geometry_by_body)

    expanded = _expanded_trajectory(entry, context, installed_profile)
    try:
        collision = derive_and_evaluate_fk_waypoint_collisions(
            context,
            snapshot,
            installed_profile,
            expanded,
            attachment_bindings,
            tuple(geometry),
        )
    except FkCollisionPoseAdapterError as exc:
        raise TypingObservedRouteEntryCollisionV1Error(str(exc)) from exc
    nested_status = collision["status"]
    if nested_status == "DISCRETE_WAYPOINTS_CLEAR_CONTINUOUS_PROOF_REQUIRED":
        status = CLEAR_STATUS
        all_clear = True
    elif nested_status == "BLOCKED_COLLISION_DETECTED":
        status = COLLISION_STATUS
        all_clear = False
    else:
        status = INCOMPLETE_STATUS
        all_clear = False
    sample_hashes = [sample["sample_sha256"] for sample in entry["sample_plan"]]
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "request_id": entry["request_id"],
        "materialization_sha256": entry["materialization_sha256"],
        "observed_route_entry_sha256": entry["observed_route_entry_sha256"],
        "observed_trajectory_ik_sha256": entry["observed_trajectory_ik_sha256"],
        "observed_ik_seed_sha256": entry["observed_ik_seed_sha256"],
        "observed_start_state_sha256": entry["observed_start_state_sha256"],
        "calibration_snapshot_sha256": entry["calibration_snapshot_sha256"],
        "build_snapshot_sha256": entry["build_snapshot_sha256"],
        "controller_session_id": entry["controller_session_id"],
        "installed_collision_profile_sha256": installed_profile.content_sha256,
        "collision_contract_sha256": installed_profile.contract.content_hash,
        "expanded_trajectory_screening_sha256": expanded[
            "trajectory_screening_sha256"
        ],
        "sample_count": entry["sample_count"],
        "sample_plan_sha256": _sha(sample_hashes),
        "fk_collision_sequence_sha256": collision[
            "fk_collision_sequence_sha256"
        ],
        "fk_collision_qualification": collision,
        "entry_sample_collision_screening_executed": True,
        "all_entry_samples_collision_free": all_clear,
        "continuous_collision_proven": False,
        "measured_dynamics_qualified": False,
        "required_next_evidence": list(REQUIRED_NEXT_EVIDENCE),
        "permit_review_ready": False,
        "eligible_for_executor": False,
        "automatic_retry_allowed": False,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "observed_route_entry_collision_sha256": _sha(core)}


def parse_typing_observed_route_entry_collision_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate sealed nested collision evidence and closed execution gates."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingObservedRouteEntryCollisionV1Error(
            "entry collision report fields differ"
        )
    unsigned = dict(value)
    supplied = unsigned.pop("observed_route_entry_collision_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingObservedRouteEntryCollisionV1Error(
            "entry collision report hash differs"
        )
    collision = value["fk_collision_qualification"]
    if not isinstance(collision, Mapping):
        raise TypingObservedRouteEntryCollisionV1Error(
            "FK collision qualification is absent"
        )
    nested = dict(collision)
    nested_hash = nested.pop("fk_collision_sequence_sha256", None)
    nested_status = collision.get("status")
    collision_sequence = collision.get("collision_sequence")
    if (
        nested_status not in _NESTED_STATUSES
        or not isinstance(collision_sequence, Mapping)
    ):
        raise TypingObservedRouteEntryCollisionV1Error(
            "FK collision qualification status or sequence differs"
        )
    expected_status = (
        CLEAR_STATUS
        if nested_status == "DISCRETE_WAYPOINTS_CLEAR_CONTINUOUS_PROOF_REQUIRED"
        else COLLISION_STATUS
        if nested_status == "BLOCKED_COLLISION_DETECTED"
        else INCOMPLETE_STATUS
    )
    expected_clear = expected_status == CLEAR_STATUS
    digests = (
        "materialization_sha256", "observed_route_entry_sha256",
        "observed_trajectory_ik_sha256", "observed_ik_seed_sha256",
        "observed_start_state_sha256", "calibration_snapshot_sha256",
        "build_snapshot_sha256", "installed_collision_profile_sha256",
        "collision_contract_sha256", "expanded_trajectory_screening_sha256",
        "sample_plan_sha256", "fk_collision_sequence_sha256",
    )
    if (
        value["schema"] != SCHEMA
        or any(_SHA.fullmatch(value[field] or "") is None for field in digests)
        or not isinstance(value["request_id"], str)
        or not value["request_id"]
        or not isinstance(value["controller_session_id"], str)
        or not value["controller_session_id"]
        or not isinstance(value["sample_count"], int)
        or isinstance(value["sample_count"], bool)
        or value["sample_count"] < 2
        or not isinstance(nested_hash, str)
        or nested_hash != _sha(nested)
        or value["fk_collision_sequence_sha256"] != nested_hash
        or collision.get("trajectory_screening_sha256")
        != value["expanded_trajectory_screening_sha256"]
        or collision.get("calibration_snapshot_sha256")
        != value["calibration_snapshot_sha256"]
        or collision.get("installed_collision_profile_sha256")
        != value["installed_collision_profile_sha256"]
        or collision_sequence.get("collision_contract_sha256")
        != value["collision_contract_sha256"]
        or collision_sequence.get("sample_count")
        != value["sample_count"]
        or collision_sequence.get("status") != nested_status
        or collision_sequence.get("all_waypoints_collision_free_at_supplied_samples")
        is not expected_clear
        or collision.get("continuous_collision_proven") is not False
        or collision.get("controller_commands") != []
        or collision.get("hardware_commands_generated") != 0
        or collision.get("hardware_access") is not False
        or collision.get("physical_authority") is not False
        or value["status"] != expected_status
        or value["entry_sample_collision_screening_executed"] is not True
        or value["all_entry_samples_collision_free"] is not expected_clear
        or value["continuous_collision_proven"] is not False
        or value["measured_dynamics_qualified"] is not False
        or value["required_next_evidence"] != list(REQUIRED_NEXT_EVIDENCE)
        or value["permit_review_ready"] is not False
        or value["eligible_for_executor"] is not False
        or value["automatic_retry_allowed"] is not False
        or value["controller_commands"] != []
        or value["wire_commands"] != []
        or value["hardware_commands_generated"] != 0
        or value["hardware_access"] is not False
        or value["physical_authority"] is not False
    ):
        raise TypingObservedRouteEntryCollisionV1Error(
            "entry collision lineage, result, gates, or authority differs"
        )
    return dict(value)


__all__ = [
    "CLEAR_STATUS", "COLLISION_STATUS", "INCOMPLETE_STATUS",
    "REQUIRED_NEXT_EVIDENCE", "SCHEMA",
    "TypingObservedRouteEntryCollisionV1Error",
    "parse_typing_observed_route_entry_collision_v1",
    "qualify_typing_observed_route_entry_collision_v1",
]
