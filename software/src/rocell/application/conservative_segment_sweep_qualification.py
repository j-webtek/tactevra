"""Conservative full-body envelopes between bounded joint samples.

Rigid bodies are enclosed by inflating their start primitives with a serial-chain
motion bound derived from the pinned URDF and exact adjacent joint deltas.  Each
configuration-sampled cable body requires a separately measured, profile-bound
root-frame envelope covering the same adjacent sample pair.

Clear envelopes prove collision freedom only for the bound geometry and policy.
They do not authorize commands, contact, transport, or physical execution.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from rocell.geometry import RigidTransform, Rotation3, Vec3
from rocell.kinematics import ARM_JOINT_NAMES
from rocell.simulation.collision import (
    CapsuleMm,
    CollisionBindingMode,
    CollisionBody,
    CollisionBodyRequirement,
    CollisionEvaluationPolicy,
    CollisionEvaluationStatus,
    CollisionEvidenceState,
    CollisionGeometryContract,
    CollisionPose,
    OrientedBoxMm,
    SampledCollisionGeometry,
    SphereMm,
    evaluate_collision_pose,
)

from ._pinned_model import load_pinned_urdf
from .bounded_segment_collision_qualification import (
    BoundedJointConfigurationSample,
    BoundedSegmentSamplingPolicy,
    MeasuredSegmentConfigurationSample,
    build_bounded_joint_sample_plan,
    qualify_bounded_segment_collisions,
)
from .context import SimulationContext
from .fk_collision_pose_adapter import MeasuredRigidAttachmentBinding
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from rocell.calibration import PlannerCalibrationSnapshot


SCHEMA = "rocell.conservative_segment_sweep_qualification.v1"
MAX_CONSERVATIVE_SEGMENT_ENVELOPES = 255


class ConservativeSegmentSweepQualificationError(ValueError):
    """Conservative sweep evidence is incomplete, crossed, or unsupported."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ConservativeSegmentSweepQualificationError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


@dataclass(frozen=True, slots=True)
class MeasuredConfigurationSweepEnvelopeBinding:
    """Measured root-frame envelope for one deformable body and sample pair."""

    segment_sequence: int
    start_sample_sha256: str
    end_sample_sha256: str
    body_id: str
    geometry_root_frame: SampledCollisionGeometry
    source_sha256: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.segment_sequence, bool)
            or not isinstance(self.segment_sequence, int)
            or self.segment_sequence < 0
        ):
            raise ConservativeSegmentSweepQualificationError(
                "segment_sequence must be a non-negative integer"
            )
        _digest(self.start_sample_sha256, "start_sample_sha256")
        _digest(self.end_sample_sha256, "end_sample_sha256")
        _digest(self.source_sha256, "source_sha256")
        if (
            not isinstance(self.body_id, str)
            or not self.body_id.strip()
            or self.body_id != self.body_id.strip()
        ):
            raise ConservativeSegmentSweepQualificationError(
                "body_id must be nonempty unpadded text"
            )
        if not isinstance(self.geometry_root_frame, SampledCollisionGeometry):
            raise TypeError("geometry_root_frame must be SampledCollisionGeometry")
        if (
            self.geometry_root_frame.evidence_state
            is not CollisionEvidenceState.ACCEPTED_MEASURED
        ):
            raise ConservativeSegmentSweepQualificationError(
                "sweep envelope must be accepted measured evidence"
            )

    @property
    def content_sha256(self) -> str:
        return _sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_sequence": self.segment_sequence,
            "start_sample_sha256": self.start_sample_sha256,
            "end_sample_sha256": self.end_sample_sha256,
            "body_id": self.body_id,
            "geometry_root_frame": self.geometry_root_frame.to_dict(),
            "source_sha256": self.source_sha256,
        }


def _transform_from_dict(value: object) -> RigidTransform:
    if not isinstance(value, Mapping):
        raise ConservativeSegmentSweepQualificationError(
            "derived pose transform must be an object"
        )
    try:
        translation = value["translation_mm"]
        rotation = value["rotation_row_major"]
        if (
            not isinstance(translation, list)
            or len(translation) != 3
            or not isinstance(rotation, list)
            or len(rotation) != 9
        ):
            raise ValueError
        return RigidTransform(
            value["parent_frame"],
            value["child_frame"],
            Rotation3(tuple(rotation)),
            Vec3(*translation),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConservativeSegmentSweepQualificationError(
            "derived pose transform is malformed"
        ) from exc


def _primitive_origin_radius(primitive: SphereMm | CapsuleMm | OrientedBoxMm) -> float:
    if isinstance(primitive, SphereMm):
        return primitive.center_mm.norm + primitive.radius_mm
    if isinstance(primitive, CapsuleMm):
        return max(primitive.start_mm.norm, primitive.end_mm.norm) + primitive.radius_mm
    return primitive.center_mm.norm + primitive.half_extents_mm.norm


def _world_envelope_primitive(
    primitive: SphereMm | CapsuleMm | OrientedBoxMm,
    root_t_parent: RigidTransform,
    motion_bound_mm: float,
) -> SphereMm | CapsuleMm | OrientedBoxMm:
    if isinstance(primitive, SphereMm):
        return SphereMm(
            root_t_parent.transform_position_mm(primitive.center_mm),
            primitive.radius_mm + motion_bound_mm,
        )
    if isinstance(primitive, CapsuleMm):
        return CapsuleMm(
            root_t_parent.transform_position_mm(primitive.start_mm),
            root_t_parent.transform_position_mm(primitive.end_mm),
            primitive.radius_mm + motion_bound_mm,
        )
    return OrientedBoxMm(
        root_t_parent.transform_position_mm(primitive.center_mm),
        primitive.half_extents_mm
        + Vec3(motion_bound_mm, motion_bound_mm, motion_bound_mm),
        root_t_parent.rotation.compose(primitive.rotation),
    )


def _link_path_bounds(model: Any) -> tuple[dict[str, float], dict[str, frozenset[str]]]:
    lengths = {model.root_link: 0.0}
    ancestors: dict[str, frozenset[str]] = {model.root_link: frozenset()}
    remaining = list(model.joints)
    while remaining:
        progressed = False
        for joint in tuple(remaining):
            if joint.parent_link not in lengths:
                continue
            if joint.joint_type == "prismatic" and joint.name in ARM_JOINT_NAMES:
                raise ConservativeSegmentSweepQualificationError(
                    "arm sweep bound does not support prismatic arm joints"
                )
            lengths[joint.child_link] = (
                lengths[joint.parent_link] + joint.origin.translation_mm.norm
            )
            inherited = set(ancestors[joint.parent_link])
            if joint.name in ARM_JOINT_NAMES:
                inherited.add(joint.name)
            ancestors[joint.child_link] = frozenset(inherited)
            remaining.remove(joint)
            progressed = True
        if not progressed:
            raise ConservativeSegmentSweepQualificationError(
                "pinned URDF topology cannot produce path bounds"
            )
    return lengths, ancestors


def evaluate_conservative_segment_sweeps_from_plan(
    context: SimulationContext,
    installed_profile: InstalledCollisionGeometryProfile,
    plan: Sequence[BoundedJointConfigurationSample],
    fk_collision_qualification: Mapping[str, Any],
    attachment_bindings: Sequence[MeasuredRigidAttachmentBinding],
    configuration_sweep_envelopes: Sequence[
        Mapping[str, MeasuredConfigurationSweepEnvelopeBinding]
    ],
) -> dict[str, Any]:
    """Evaluate conservative envelopes for an already collision-screened plan.

    This schema-neutral core lets separately lineage-bound producers reuse the
    exact sweep math without rerunning discrete FK collision qualification.
    """

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(installed_profile, InstalledCollisionGeometryProfile):
        raise TypeError("installed_profile must be InstalledCollisionGeometryProfile")
    try:
        bounded_plan = tuple(plan)
        bindings = tuple(attachment_bindings)
        envelopes = tuple(configuration_sweep_envelopes)
    except TypeError as exc:
        raise TypeError("plan, bindings, and envelopes must be finite sequences") from exc
    if (
        len(bounded_plan) < 2
        or len(bounded_plan) - 1 > MAX_CONSERVATIVE_SEGMENT_ENVELOPES
        or any(
            not isinstance(item, BoundedJointConfigurationSample)
            or item.sample_sequence != index
            for index, item in enumerate(bounded_plan)
        )
    ):
        raise ConservativeSegmentSweepQualificationError(
            "bounded sample plan is incomplete or noncanonical"
        )
    if not isinstance(fk_collision_qualification, Mapping):
        raise ConservativeSegmentSweepQualificationError(
            "FK collision qualification must be an object"
        )
    collision_sequence = fk_collision_qualification.get("collision_sequence")
    if (
        fk_collision_qualification.get("status")
        != "DISCRETE_WAYPOINTS_CLEAR_CONTINUOUS_PROOF_REQUIRED"
        or not isinstance(collision_sequence, Mapping)
        or collision_sequence.get(
            "all_waypoints_collision_free_at_supplied_samples"
        ) is not True
        or collision_sequence.get("sample_count") != len(bounded_plan)
    ):
        raise ConservativeSegmentSweepQualificationError(
            "bounded sample FK collisions must be complete and clear"
        )
    if len(envelopes) != len(bounded_plan) - 1:
        raise ConservativeSegmentSweepQualificationError(
            "exactly one sweep-envelope set is required for every adjacent sample pair"
        )

    model = load_pinned_urdf(
        context.scenario.model_path, context.scenario.model_sha256
    ).model
    path_lengths, ancestor_joints = _link_path_bounds(model)
    attachment_by_frame = {item.parent_frame: item for item in bindings}
    if len(attachment_by_frame) != len(bindings):
        raise ConservativeSegmentSweepQualificationError(
            "attachment parent frames must be unique"
        )
    for frame, binding in attachment_by_frame.items():
        path_lengths[frame] = (
            path_lengths[binding.anchor_link_frame]
            + binding.anchor_t_parent.translation_mm.norm
        )
        ancestor_joints[frame] = ancestor_joints[binding.anchor_link_frame]

    required_configuration = {
        body.body_id
        for body in installed_profile.contract.bodies
        if body.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
    }
    for body in installed_profile.contract.bodies:
        if (
            body.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
            and body.parent_frame != installed_profile.contract.root_frame
        ):
            raise ConservativeSegmentSweepQualificationError(
                "configuration sweep envelopes must be expressed in the collision root"
            )
    accepted_sources = set(installed_profile.source_bindings.values())
    pose_reports = collision_sequence.get("pose_reports")
    if not isinstance(pose_reports, list) or len(pose_reports) != len(bounded_plan):
        raise ConservativeSegmentSweepQualificationError(
            "bounded FK pose count differs from sample plan"
        )

    segment_reports: list[dict[str, Any]] = []
    all_clear = True
    collision_found = False
    all_pair_exclusions_physically_accepted = all(
        item.evidence_state.is_physically_accepted
        for item in installed_profile.contract.pair_exclusions
    )
    for segment_sequence, (start, end, envelope_set) in enumerate(
        zip(bounded_plan[:-1], bounded_plan[1:], envelopes, strict=True)
    ):
        if (
            not isinstance(envelope_set, Mapping)
            or set(envelope_set) != required_configuration
        ):
            raise ConservativeSegmentSweepQualificationError(
                f"segment {segment_sequence} envelope coverage differs"
            )
        checked_envelopes: dict[
            str, MeasuredConfigurationSweepEnvelopeBinding
        ] = {}
        for body_id, envelope in envelope_set.items():
            if not isinstance(envelope, MeasuredConfigurationSweepEnvelopeBinding):
                raise TypeError("sweep envelope values must be measured bindings")
            if (
                envelope.segment_sequence != segment_sequence
                or envelope.body_id != body_id
                or envelope.start_sample_sha256 != start.content_sha256
                or envelope.end_sample_sha256 != end.content_sha256
            ):
                raise ConservativeSegmentSweepQualificationError(
                    f"segment {segment_sequence} envelope does not bind its sample pair"
                )
            if envelope.source_sha256 not in accepted_sources:
                raise ConservativeSegmentSweepQualificationError(
                    f"segment {segment_sequence} envelope source is absent from installed profile"
                )
            checked_envelopes[body_id] = envelope

        try:
            pose_document = pose_reports[segment_sequence]["sample"]["pose"]
            transforms = {
                frame: _transform_from_dict(item)
                for frame, item in pose_document["root_t_parent"].items()
            }
        except (KeyError, TypeError, AttributeError) as exc:
            raise ConservativeSegmentSweepQualificationError(
                "bounded FK pose evidence is malformed"
            ) from exc
        delta_by_joint = {
            name: abs(
                end.joint_positions_rad[name] - start.joint_positions_rad[name]
            )
            for name in ARM_JOINT_NAMES
        }
        requirements: list[CollisionBodyRequirement] = []
        bodies: list[CollisionBody] = []
        motion_bounds: dict[str, float] = {}
        for body in installed_profile.contract.bodies:
            requirements.append(
                CollisionBodyRequirement(
                    body.body_id,
                    installed_profile.contract.root_frame,
                    body.role,
                    CollisionBindingMode.STATIC_ROOT,
                    "conservative adjacent-sample sweep envelope",
                )
            )
            if body.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED:
                envelope = checked_envelopes[body.body_id]
                primitives = envelope.geometry_root_frame.primitives
                source = f"measured sweep envelope {envelope.content_sha256}"
                motion_bounds[body.body_id] = 0.0
            elif body.binding_mode is CollisionBindingMode.STATIC_ROOT:
                primitives = body.primitives
                source = body.source_reference
                motion_bounds[body.body_id] = 0.0
            else:
                try:
                    root_t_parent = transforms[body.parent_frame]
                    chain_radius = path_lengths[body.parent_frame] + max(
                        _primitive_origin_radius(item) for item in body.primitives
                    )
                    relevant_delta = sum(
                        delta_by_joint[name]
                        for name in ancestor_joints[body.parent_frame]
                    )
                except (KeyError, ValueError) as exc:
                    raise ConservativeSegmentSweepQualificationError(
                        f"cannot derive rigid sweep bound for {body.body_id}"
                    ) from exc
                motion_bound = chain_radius * relevant_delta
                primitives = tuple(
                    _world_envelope_primitive(item, root_t_parent, motion_bound)
                    for item in body.primitives
                )
                source = (
                    f"URDF path-radius bound from {context.scenario.model_sha256}; "
                    f"source geometry {body.source_reference}"
                )
                motion_bounds[body.body_id] = motion_bound
            bodies.append(
                CollisionBody(
                    body.body_id,
                    installed_profile.contract.root_frame,
                    body.role,
                    CollisionEvidenceState.ACCEPTED_MEASURED,
                    tuple(primitives),
                    CollisionBindingMode.STATIC_ROOT,
                    source,
                )
            )
        envelope_contract = CollisionGeometryContract(
            f"{installed_profile.contract.contract_id}:segment-{segment_sequence:04d}",
            installed_profile.contract.root_frame,
            tuple(requirements),
            tuple(bodies),
            installed_profile.contract.pair_exclusions,
        )
        evaluation = evaluate_collision_pose(
            envelope_contract,
            CollisionPose(
                f"conservative-segment-{segment_sequence:04d}",
                installed_profile.contract.root_frame,
                {},
            ),
            CollisionEvaluationPolicy(
                clearance_policy=installed_profile.clearance_policy
            ),
        )
        clear = evaluation.collision_free_diagnostic
        all_clear = all_clear and clear
        collision_found = collision_found or (
            evaluation.status is CollisionEvaluationStatus.COLLISION_DETECTED
        )
        segment_reports.append(
            {
                "segment_sequence": segment_sequence,
                "start_sample_sha256": start.content_sha256,
                "end_sample_sha256": end.content_sha256,
                "joint_delta_rad": delta_by_joint,
                "rigid_motion_bound_mm_by_body": motion_bounds,
                "configuration_envelope_sha256_by_body": {
                    body_id: checked_envelopes[body_id].content_sha256
                    for body_id in sorted(checked_envelopes)
                },
                "conservative_contract_sha256": envelope_contract.content_hash,
                "collision_report_sha256": evaluation.report_hash,
                "status": evaluation.status.value,
                "collision_free_diagnostic": clear,
                "collisions": [item.to_dict() for item in evaluation.collisions],
                "pose_blockers": [
                    item.to_dict() for item in evaluation.pose_blockers
                ],
            }
        )

    if all_clear:
        status = "CONSERVATIVE_SEGMENT_SWEEPS_CLEAR_RELEASE_GATES_REMAIN"
        blockers = []
        if not all_pair_exclusions_physically_accepted:
            blockers.append("ACCEPTED_GLOBAL_PAIR_EXCLUSIONS_REQUIRED")
        blockers.extend(
            [
                "PHASE_LOCAL_CONTACT_POLICY_REQUIRED",
                "INSTALLED_PHYSICAL_QUALIFICATION_REQUIRED",
            ]
        )
        next_stage = "QUALIFY_PHASE_LOCAL_CONTACT_AND_INSTALLED_PHYSICAL_EVIDENCE"
    elif collision_found:
        status = "BLOCKED_CONSERVATIVE_SWEEP_COLLISION"
        blockers = ["CONSERVATIVE_SWEPT_ENVELOPES_INTERSECT"]
        next_stage = "CORRECT_ROUTE_OR_SWEEP_ENVELOPES"
    else:
        status = "BLOCKED_INCOMPLETE_CONSERVATIVE_SWEEP_EVIDENCE"
        blockers = ["CONSERVATIVE_SWEEP_EVALUATION_INCOMPLETE"]
        next_stage = "SUPPLY_COMPLETE_CONSERVATIVE_SWEEP_EVIDENCE"
    return {
        "status": status,
        "segment_count": len(segment_reports),
        "segment_reports": segment_reports,
        "all_conservative_segment_sweeps_clear": all_clear,
        "all_pair_exclusions_physically_accepted": (
            all_pair_exclusions_physically_accepted
        ),
        "continuous_collision_proven_for_bound_geometry": (
            all_clear and all_pair_exclusions_physically_accepted
        ),
        "blockers": blockers,
        "next_required_stage": next_stage,
    }


def qualify_conservative_segment_sweeps(
    context: SimulationContext,
    snapshot: PlannerCalibrationSnapshot,
    installed_profile: InstalledCollisionGeometryProfile,
    trajectory_screening: Mapping[str, Any],
    attachment_bindings: Sequence[MeasuredRigidAttachmentBinding],
    configuration_samples: Sequence[MeasuredSegmentConfigurationSample],
    configuration_sweep_envelopes: Sequence[
        Mapping[str, MeasuredConfigurationSweepEnvelopeBinding]
    ],
    *,
    sampling_policy: BoundedSegmentSamplingPolicy | None = None,
) -> dict[str, Any]:
    """Prove conservative clearance for every adjacent bounded sample pair."""

    selected = sampling_policy or BoundedSegmentSamplingPolicy()
    try:
        bindings = tuple(attachment_bindings)
    except TypeError as exc:
        raise TypeError("attachment_bindings must be a finite sequence") from exc
    plan = build_bounded_joint_sample_plan(trajectory_screening, selected)
    bounded = qualify_bounded_segment_collisions(
        context,
        snapshot,
        installed_profile,
        trajectory_screening,
        bindings,
        configuration_samples,
        policy=selected,
    )
    if not bounded["all_bounded_samples_collision_free"]:
        raise ConservativeSegmentSweepQualificationError(
            "bounded segment samples must be complete and collision-free"
        )
    try:
        envelopes = tuple(configuration_sweep_envelopes)
    except TypeError as exc:
        raise TypeError("configuration_sweep_envelopes must be a finite sequence") from exc
    expected_segment_count = len(plan) - 1
    if (
        expected_segment_count < 1
        or expected_segment_count > MAX_CONSERVATIVE_SEGMENT_ENVELOPES
        or len(envelopes) != expected_segment_count
    ):
        raise ConservativeSegmentSweepQualificationError(
            "exactly one sweep-envelope set is required for every adjacent sample pair"
        )

    model = load_pinned_urdf(
        context.scenario.model_path, context.scenario.model_sha256
    ).model
    path_lengths, ancestor_joints = _link_path_bounds(model)
    attachment_by_frame = {item.parent_frame: item for item in bindings}
    if len(attachment_by_frame) != len(bindings):
        raise ConservativeSegmentSweepQualificationError(
            "attachment parent frames must be unique"
        )
    for frame, binding in attachment_by_frame.items():
        path_lengths[frame] = (
            path_lengths[binding.anchor_link_frame]
            + binding.anchor_t_parent.translation_mm.norm
        )
        ancestor_joints[frame] = ancestor_joints[binding.anchor_link_frame]

    required_configuration = {
        body.body_id
        for body in installed_profile.contract.bodies
        if body.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
    }
    for body in installed_profile.contract.bodies:
        if (
            body.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
            and body.parent_frame != installed_profile.contract.root_frame
        ):
            raise ConservativeSegmentSweepQualificationError(
                "configuration sweep envelopes must be expressed in the collision root"
            )
    accepted_sources = set(installed_profile.source_bindings.values())
    pose_reports = bounded["fk_collision_qualification"]["collision_sequence"][
        "pose_reports"
    ]
    if len(pose_reports) != len(plan):
        raise ConservativeSegmentSweepQualificationError(
            "bounded FK pose count differs from sample plan"
        )

    segment_reports: list[dict[str, Any]] = []
    all_clear = True
    collision_found = False
    all_pair_exclusions_physically_accepted = all(
        item.evidence_state.is_physically_accepted
        for item in installed_profile.contract.pair_exclusions
    )
    for segment_sequence, (start, end, envelope_set) in enumerate(
        zip(plan[:-1], plan[1:], envelopes, strict=True)
    ):
        if not isinstance(envelope_set, Mapping) or set(envelope_set) != required_configuration:
            raise ConservativeSegmentSweepQualificationError(
                f"segment {segment_sequence} envelope coverage differs"
            )
        checked_envelopes: dict[str, MeasuredConfigurationSweepEnvelopeBinding] = {}
        for body_id, envelope in envelope_set.items():
            if not isinstance(envelope, MeasuredConfigurationSweepEnvelopeBinding):
                raise TypeError("sweep envelope values must be measured bindings")
            if (
                envelope.segment_sequence != segment_sequence
                or envelope.body_id != body_id
                or envelope.start_sample_sha256 != start.content_sha256
                or envelope.end_sample_sha256 != end.content_sha256
            ):
                raise ConservativeSegmentSweepQualificationError(
                    f"segment {segment_sequence} envelope does not bind its sample pair"
                )
            if envelope.source_sha256 not in accepted_sources:
                raise ConservativeSegmentSweepQualificationError(
                    f"segment {segment_sequence} envelope source is absent from installed profile"
                )
            checked_envelopes[body_id] = envelope

        pose_document = pose_reports[segment_sequence]["sample"]["pose"]
        transforms = {
            frame: _transform_from_dict(value)
            for frame, value in pose_document["root_t_parent"].items()
        }
        delta_by_joint = {
            name: abs(end.joint_positions_rad[name] - start.joint_positions_rad[name])
            for name in ARM_JOINT_NAMES
        }
        requirements: list[CollisionBodyRequirement] = []
        bodies: list[CollisionBody] = []
        motion_bounds: dict[str, float] = {}
        for body in installed_profile.contract.bodies:
            requirements.append(
                CollisionBodyRequirement(
                    body.body_id,
                    installed_profile.contract.root_frame,
                    body.role,
                    CollisionBindingMode.STATIC_ROOT,
                    "conservative adjacent-sample sweep envelope",
                )
            )
            if body.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED:
                envelope = checked_envelopes[body.body_id]
                primitives = envelope.geometry_root_frame.primitives
                source = f"measured sweep envelope {envelope.content_sha256}"
                motion_bounds[body.body_id] = 0.0
            elif body.binding_mode is CollisionBindingMode.STATIC_ROOT:
                primitives = body.primitives
                source = body.source_reference
                motion_bounds[body.body_id] = 0.0
            else:
                try:
                    root_t_parent = transforms[body.parent_frame]
                    chain_radius = path_lengths[body.parent_frame] + max(
                        _primitive_origin_radius(item) for item in body.primitives
                    )
                    relevant_delta = sum(
                        delta_by_joint[name]
                        for name in ancestor_joints[body.parent_frame]
                    )
                except (KeyError, ValueError) as exc:
                    raise ConservativeSegmentSweepQualificationError(
                        f"cannot derive rigid sweep bound for {body.body_id}"
                    ) from exc
                motion_bound = chain_radius * relevant_delta
                primitives = tuple(
                    _world_envelope_primitive(item, root_t_parent, motion_bound)
                    for item in body.primitives
                )
                source = (
                    f"URDF path-radius bound from {context.scenario.model_sha256}; "
                    f"source geometry {body.source_reference}"
                )
                motion_bounds[body.body_id] = motion_bound
            bodies.append(
                CollisionBody(
                    body.body_id,
                    installed_profile.contract.root_frame,
                    body.role,
                    CollisionEvidenceState.ACCEPTED_MEASURED,
                    tuple(primitives),
                    CollisionBindingMode.STATIC_ROOT,
                    source,
                )
            )
        envelope_contract = CollisionGeometryContract(
            f"{installed_profile.contract.contract_id}:segment-{segment_sequence:04d}",
            installed_profile.contract.root_frame,
            tuple(requirements),
            tuple(bodies),
            installed_profile.contract.pair_exclusions,
        )
        evaluation = evaluate_collision_pose(
            envelope_contract,
            CollisionPose(
                f"conservative-segment-{segment_sequence:04d}",
                installed_profile.contract.root_frame,
                {},
            ),
            CollisionEvaluationPolicy(
                clearance_policy=installed_profile.clearance_policy
            ),
        )
        clear = evaluation.collision_free_diagnostic
        all_clear = all_clear and clear
        collision_found = collision_found or (
            evaluation.status is CollisionEvaluationStatus.COLLISION_DETECTED
        )
        segment_reports.append(
            {
                "segment_sequence": segment_sequence,
                "start_sample_sha256": start.content_sha256,
                "end_sample_sha256": end.content_sha256,
                "joint_delta_rad": delta_by_joint,
                "rigid_motion_bound_mm_by_body": motion_bounds,
                "configuration_envelope_sha256_by_body": {
                    body_id: checked_envelopes[body_id].content_sha256
                    for body_id in sorted(checked_envelopes)
                },
                "conservative_contract_sha256": envelope_contract.content_hash,
                "collision_report_sha256": evaluation.report_hash,
                "status": evaluation.status.value,
                "collision_free_diagnostic": clear,
                "collisions": [item.to_dict() for item in evaluation.collisions],
                "pose_blockers": [item.to_dict() for item in evaluation.pose_blockers],
            }
        )

    if all_clear:
        status = "CONSERVATIVE_SEGMENT_SWEEPS_CLEAR_RELEASE_GATES_REMAIN"
        blockers = []
        if not all_pair_exclusions_physically_accepted:
            blockers.append("ACCEPTED_GLOBAL_PAIR_EXCLUSIONS_REQUIRED")
        blockers.extend(
            [
                "PHASE_LOCAL_CONTACT_POLICY_REQUIRED",
                "INSTALLED_PHYSICAL_QUALIFICATION_REQUIRED",
            ]
        )
        next_stage = "QUALIFY_PHASE_LOCAL_CONTACT_AND_INSTALLED_PHYSICAL_EVIDENCE"
    elif collision_found:
        status = "BLOCKED_CONSERVATIVE_SWEEP_COLLISION"
        blockers = ["CONSERVATIVE_SWEPT_ENVELOPES_INTERSECT"]
        next_stage = "CORRECT_ROUTE_OR_SWEEP_ENVELOPES"
    else:
        status = "BLOCKED_INCOMPLETE_CONSERVATIVE_SWEEP_EVIDENCE"
        blockers = ["CONSERVATIVE_SWEEP_EVALUATION_INCOMPLETE"]
        next_stage = "SUPPLY_COMPLETE_CONSERVATIVE_SWEEP_EVIDENCE"

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "trajectory_screening_sha256": trajectory_screening[
            "trajectory_screening_sha256"
        ],
        "bounded_segment_qualification_sha256": bounded[
            "bounded_segment_qualification_sha256"
        ],
        "installed_collision_profile_sha256": installed_profile.content_sha256,
        "kinematic_model_sha256": context.scenario.model_sha256,
        "segment_count": len(segment_reports),
        "segment_reports": segment_reports,
        "rigid_bound_method": (
            "start_primitive_minkowski_inflation_by_urdf_serial_chain_"
            "path_radius_times_exact_ancestor_joint_delta_sum"
        ),
        "configuration_bound_method": (
            "profile_bound_measured_root_frame_envelope_per_adjacent_sample_pair"
        ),
        "all_conservative_segment_sweeps_clear": all_clear,
        "all_pair_exclusions_physically_accepted": (
            all_pair_exclusions_physically_accepted
        ),
        "continuous_collision_proven_for_bound_geometry": (
            all_clear and all_pair_exclusions_physically_accepted
        ),
        "blockers": blockers,
        "next_required_stage": next_stage,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**report, "conservative_sweep_qualification_sha256": _sha256(report)}
