"""Deterministic zero-authority collision evaluation for one C03 partition.

This stage composes the already admitted installed profile, root-fixed rigid
bindings, configuration samples, and conservative cable envelopes.  It reports
discrete and envelope intersections without claiming the ICQ-6 continuous
proof, controller commands, or physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from rocell.calibration import PlannerCalibrationSnapshot
from rocell.geometry import JointPosition, RigidTransform, Rotation3, Vec3
from rocell.kinematics import ARM_JOINT_NAMES
from rocell.simulation.collision import (
    CollisionBindingMode,
    CollisionBody,
    CollisionBodyRequirement,
    CollisionClearancePolicy,
    CollisionEvaluationPolicy,
    CollisionEvaluationStatus,
    CollisionEvidenceState,
    CollisionGeometryContract,
    CollisionPose,
    CollisionResourceLimitError,
    _candidate_body_pairs,
    _inflate_world_primitive,
    _pose_body_primitives,
    _primitive_bounds,
    evaluate_collision_pose,
)

from ._pinned_model import load_pinned_urdf
from .bounded_segment_collision_qualification import (
    BoundedJointConfigurationSample,
    MeasuredSegmentConfigurationSample,
)
from .c03_cable_envelope_intake_v1 import (
    READY_STATUS as CABLE_READY_STATUS,
    C03CableEnvelopeIntakeV1Result,
)
from .c03_installed_collision_qualification_v1 import (
    READY_FOR_EVIDENCE_STATUS,
)
from .c03_rigid_attachment_binding_v1 import READY_STATUS as RIGID_READY_STATUS
from .collision_readiness import assess_current_collision_readiness
from .conservative_segment_sweep_qualification import (
    _link_path_bounds,
    _primitive_origin_radius,
    _world_envelope_primitive,
)
from .context import SimulationContext, revalidate_simulation_context
from .installed_collision_geometry import InstalledCollisionGeometryProfile


SCHEMA = "tactevra.c03_partition_collision_evaluation.v1"
CLEAR_STATUS = "PARTITION_ENVELOPES_CLEAR_ICQ6_PROOF_REQUIRED"
COLLISION_STATUS = "BLOCKED_PARTITION_COLLISION_DETECTED"
INCOMPLETE_STATUS = "BLOCKED_INCOMPLETE_PARTITION_EVIDENCE"
RESOURCE_STATUS = "BLOCKED_PARTITION_RESOURCE_LIMIT"
ERROR_STATUS = "BLOCKED_PARTITION_EVALUATOR_ERROR"


class C03PartitionCollisionEvaluatorV1Error(ValueError):
    """The caller supplied incompatible API values rather than evidence."""


class _IncompleteEvidence(ValueError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _validated_report(
    value: object, *, schema: str, status: str, hash_field: str, label: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _IncompleteEvidence(f"{label} must be an object")
    report = dict(value)
    digest = report.pop(hash_field, None)
    if (
        value.get("schema") != schema
        or value.get("status") != status
        or not isinstance(digest, str)
        or digest != _sha(report)
    ):
        raise _IncompleteEvidence(f"{label} is not exact and ready")
    return dict(value)


def _transform(value: object, root_frame: str, label: str) -> RigidTransform:
    if not isinstance(value, Mapping):
        raise _IncompleteEvidence(f"{label} transform is missing")
    rotation = value.get("rotation_row_major")
    translation = value.get("translation_mm")
    if (
        value.get("to_frame") != root_frame
        or not isinstance(value.get("from_frame"), str)
        or not isinstance(rotation, list)
        or len(rotation) != 9
        or not isinstance(translation, list)
        or len(translation) != 3
    ):
        raise _IncompleteEvidence(f"{label} transform is malformed")
    try:
        return RigidTransform(
            root_frame,
            value["from_frame"],
            Rotation3(tuple(float(item) for item in rotation)),
            Vec3(*(float(item) for item in translation)),
        )
    except (TypeError, ValueError) as exc:
        raise _IncompleteEvidence(f"{label} transform is invalid") from exc


def _bounds_gap_mm(left: object, right: object) -> float:
    left_min = (left.minimum_mm.x, left.minimum_mm.y, left.minimum_mm.z)
    left_max = (left.maximum_mm.x, left.maximum_mm.y, left.maximum_mm.z)
    right_min = (right.minimum_mm.x, right.minimum_mm.y, right.minimum_mm.z)
    right_max = (right.maximum_mm.x, right.maximum_mm.y, right.maximum_mm.z)
    return math.sqrt(sum(
        max(
            left_min[axis] - right_max[axis],
            right_min[axis] - left_max[axis],
            0.0,
        ) ** 2
        for axis in range(3)
    ))


def _clearance_summary(
    contract: CollisionGeometryContract,
    pose: CollisionPose,
    policy: CollisionEvaluationPolicy,
) -> dict[str, Any]:
    world, blockers = _pose_body_primitives(contract, pose)
    if blockers or policy.clearance_policy is None:
        raise _IncompleteEvidence(
            "collision pose cannot produce clearance evidence: "
            + "; ".join(item.detail for item in blockers)
        )
    inflation = policy.clearance_policy.per_body_inflation_mm
    inflated = {
        body_id: tuple(_inflate_world_primitive(item, inflation) for item in items)
        for body_id, items in world.items()
    }
    bounds = {
        body_id: tuple(_primitive_bounds(item) for item in items)
        for body_id, items in inflated.items()
    }
    tested = _candidate_body_pairs(contract, inflated)
    pair_rows: list[dict[str, Any]] = []
    for left_id, right_id in tested:
        gap = min(
            _bounds_gap_mm(left, right)
            for left in bounds[left_id]
            for right in bounds[right_id]
        )
        pair_rows.append({
            "body_pair": [left_id, right_id],
            "conservative_aabb_clearance_lower_bound_mm": gap,
        })
    pair_rows.sort(key=lambda item: (item["conservative_aabb_clearance_lower_bound_mm"], item["body_pair"]))
    exclusions = [list(item.pair) for item in contract.pair_exclusions]
    roles = contract.bodies_by_id
    implicit = []
    ordered = sorted(inflated)
    exclusion_set = {tuple(item) for item in exclusions}
    for index, left_id in enumerate(ordered):
        for right_id in ordered[index + 1:]:
            pair = (left_id, right_id)
            if pair in exclusion_set:
                continue
            if roles[left_id].role.value == roles[right_id].role.value == "STATIC_ENVIRONMENT":
                implicit.append(list(pair))
    limiting = pair_rows[0] if pair_rows else None
    return {
        "tested_body_pair_count": len(tested),
        "tested_body_pairs": [item["body_pair"] for item in pair_rows],
        "declared_excluded_body_pairs": exclusions,
        "implicit_static_static_excluded_body_pairs": implicit,
        "minimum_clearance_lower_bound_mm": (
            None if limiting is None
            else limiting["conservative_aabb_clearance_lower_bound_mm"]
        ),
        "limiting_body_pair": None if limiting is None else limiting["body_pair"],
        "clearance_measurement": (
            "minimum Euclidean separation between uncertainty-inflated world AABBs; "
            "zero is conservative and may mean overlapping bounds without primitive collision"
        ),
    }


@dataclass(frozen=True, slots=True)
class C03PartitionCollisionResourcePolicy:
    maximum_samples: int = 256
    maximum_segments: int = 255
    maximum_total_primitive_pair_tests: int = 2_000_000

    def __post_init__(self) -> None:
        for value, maximum, label in (
            (self.maximum_samples, 256, "maximum_samples"),
            (self.maximum_segments, 255, "maximum_segments"),
            (
                self.maximum_total_primitive_pair_tests,
                10_000_000,
                "maximum_total_primitive_pair_tests",
            ),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise C03PartitionCollisionEvaluatorV1Error(
                    f"{label} must be an integer in [1, {maximum}]"
                )

    @property
    def content_sha256(self) -> str:
        return _sha(self.to_dict())

    def to_dict(self) -> dict[str, int]:
        return {
            "maximum_samples": self.maximum_samples,
            "maximum_segments": self.maximum_segments,
            "maximum_total_primitive_pair_tests": self.maximum_total_primitive_pair_tests,
        }


def _result(
    *, status: str, partition_index: int, lineage: Mapping[str, Any],
    policy: C03PartitionCollisionResourcePolicy, sample_reports: Sequence[Mapping[str, Any]] = (),
    segment_reports: Sequence[Mapping[str, Any]] = (), blockers: Sequence[str] = (),
    error: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "partition_index": partition_index,
        **lineage,
        "resource_policy": {**policy.to_dict(), "content_sha256": policy.content_sha256},
        "sample_count": len(sample_reports),
        "segment_count": len(segment_reports),
        "sample_reports": list(sample_reports),
        "segment_reports": list(segment_reports),
        "all_declared_evidence_slots_consumed_exactly_once": status in {CLEAR_STATUS, COLLISION_STATUS},
        "discrete_samples_collision_free": (
            bool(sample_reports)
            and all(item["collision_free_diagnostic"] for item in sample_reports)
        ),
        "conservative_envelopes_collision_free": (
            bool(segment_reports)
            and all(item["collision_free_diagnostic"] for item in segment_reports)
        ),
        "continuous_collision_proven": False,
        "blockers": list(blockers),
        "evaluator_error": error,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "c03_partition_collision_evaluation_sha256": _sha(core)}


def evaluate_c03_collision_partition_v1(
    context: SimulationContext,
    snapshot: PlannerCalibrationSnapshot,
    installed_profile: InstalledCollisionGeometryProfile,
    qualification: Mapping[str, Any],
    rigid_binding_report: Mapping[str, Any],
    cable_intake: C03CableEnvelopeIntakeV1Result,
    partition_index: int,
    *,
    resource_policy: C03PartitionCollisionResourcePolicy | None = None,
) -> dict[str, Any]:
    """Evaluate one admitted C03 partition with no execution authority."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(snapshot, PlannerCalibrationSnapshot):
        raise TypeError("snapshot must be a PlannerCalibrationSnapshot")
    if not isinstance(installed_profile, InstalledCollisionGeometryProfile):
        raise TypeError("installed_profile must be InstalledCollisionGeometryProfile")
    if not isinstance(cable_intake, C03CableEnvelopeIntakeV1Result):
        raise TypeError("cable_intake must be C03CableEnvelopeIntakeV1Result")
    if isinstance(partition_index, bool) or not isinstance(partition_index, int):
        raise TypeError("partition_index must be an integer")
    selected = resource_policy or C03PartitionCollisionResourcePolicy()
    if not isinstance(selected, C03PartitionCollisionResourcePolicy):
        raise TypeError("resource_policy must be C03PartitionCollisionResourcePolicy")

    lineage: dict[str, Any] = {}
    try:
        revalidate_simulation_context(context)
        qualified = _validated_report(
            qualification,
            schema="tactevra.c03_installed_collision_qualification.v1",
            status=READY_FOR_EVIDENCE_STATUS,
            hash_field="c03_installed_collision_qualification_sha256",
            label="qualification",
        )
        rigid = _validated_report(
            rigid_binding_report,
            schema="tactevra.c03_rigid_attachment_binding_report.v1",
            status=RIGID_READY_STATUS,
            hash_field="c03_rigid_attachment_binding_report_sha256",
            label="rigid binding report",
        )
        cable = _validated_report(
            cable_intake.report,
            schema="tactevra.c03_cable_envelope_intake_report.v1",
            status=CABLE_READY_STATUS,
            hash_field="c03_cable_envelope_intake_report_sha256",
            label="cable intake report",
        )
        intake = qualified["c03_collision_handoff"]["collision_intake"]
        partitions = intake["partitions"]
        if not 0 <= partition_index < len(partitions):
            raise _IncompleteEvidence("partition index is outside admitted route")
        partition = partitions[partition_index]
        lineage = {
            "c03_installed_collision_qualification_sha256": qualified[
                "c03_installed_collision_qualification_sha256"
            ],
            "c03_rigid_attachment_binding_report_sha256": rigid[
                "c03_rigid_attachment_binding_report_sha256"
            ],
            "c03_cable_envelope_intake_report_sha256": cable[
                "c03_cable_envelope_intake_report_sha256"
            ],
            "partitioned_typing_collision_intake_sha256": intake[
                "partitioned_typing_collision_intake_sha256"
            ],
            "partition_sha256": partition["partition_sha256"],
            "installed_collision_profile_sha256": installed_profile.content_sha256,
            "collision_contract_sha256": installed_profile.contract.content_hash,
        }
        if (
            intake["installed_collision_profile_sha256"] != installed_profile.content_sha256
            or intake["collision_contract_sha256"] != installed_profile.contract.content_hash
            or qualified["profile_file_sha256"] != installed_profile.file_sha256
            or snapshot.snapshot_sha256 != intake["calibration_snapshot_sha256"]
            or context.snapshot.snapshot_hash != intake["build_snapshot_sha256"]
            or context.scenario.model_sha256 != intake["kinematic_model_sha256"]
            or rigid["c03_installed_collision_qualification_sha256"] != lineage[
                "c03_installed_collision_qualification_sha256"
            ]
            or cable["c03_rigid_attachment_binding_report_sha256"] != lineage[
                "c03_rigid_attachment_binding_report_sha256"
            ]
            or cable["partitioned_typing_collision_intake_sha256"] != lineage[
                "partitioned_typing_collision_intake_sha256"
            ]
        ):
            raise _IncompleteEvidence("context, profile, or evidence lineage differs")

        plan_rows = partition["bounded_joint_sample_plan"]
        samples = cable_intake.configuration_samples_by_partition[partition_index]
        sweeps = cable_intake.sweep_envelopes_by_partition[partition_index]
        if (
            len(plan_rows) != partition["required_evidence_slots"]["configuration_sample_count"]
            or len(samples) != len(plan_rows)
            or len(sweeps) != len(plan_rows) - 1
        ):
            raise _IncompleteEvidence("partition evidence slot coverage differs")
        sample_binding_hashes = [
            _sha({
                "sample_sequence": item.sample_sequence,
                "sample_plan_sha256": item.sample_plan_sha256,
                "geometry_binding_sha256_by_body": {
                    body_id: item.geometry_by_body[body_id].content_sha256
                    for body_id in sorted(item.geometry_by_body)
                },
            })
            for item in samples
        ]
        sweep_binding_hashes = [
            _sha({
                "geometry_binding_sha256_by_body": {
                    body_id: item[body_id].content_sha256
                    for body_id in sorted(item)
                },
            })
            for item in sweeps
        ]
        if (
            sample_binding_hashes
            != cable["configuration_sample_binding_sha256_by_partition"][partition_index]
            or sweep_binding_hashes
            != cable["configuration_sweep_binding_sha256_by_partition"][partition_index]
        ):
            raise _IncompleteEvidence("typed cable evidence differs from its intake receipt")
        if len(plan_rows) > selected.maximum_samples or len(sweeps) > selected.maximum_segments:
            return _result(
                status=RESOURCE_STATUS,
                partition_index=partition_index,
                lineage=lineage,
                policy=selected,
                blockers=["PARTITION_RESOURCE_LIMIT_EXCEEDED"],
            )

        plan: list[BoundedJointConfigurationSample] = []
        for index, row in enumerate(plan_rows):
            sample = BoundedJointConfigurationSample(
                row["sample_sequence"], row["source_segment_index"],
                row["subdivision_index"], row["subdivision_count"],
                float(row["interpolation_ratio"]), dict(row["joint_positions_rad"]),
            )
            if sample.sample_sequence != index or sample.content_sha256 != _sha(row):
                raise _IncompleteEvidence("bounded sample plan is not canonical")
            evidence = samples[index]
            if (
                not isinstance(evidence, MeasuredSegmentConfigurationSample)
                or evidence.sample_sequence != index
                or evidence.sample_plan_sha256 != sample.content_sha256
            ):
                raise _IncompleteEvidence("configuration sample lineage differs")
            plan.append(sample)

        root_frame = installed_profile.contract.root_frame
        root_fixed: dict[str, RigidTransform] = {}
        uncertainty_by_frame: dict[str, dict[str, float]] = {}
        for row in rigid["transform_bindings"]:
            frame = row["frame"]
            transform = _transform(row["root_T_frame"], root_frame, frame)
            if transform.child_frame != frame or frame in root_fixed:
                raise _IncompleteEvidence("rigid transform coverage is crossed")
            root_fixed[frame] = transform
            uncertainty_by_frame[frame] = {
                "translation_uncertainty_mm": float(row["translation_uncertainty_mm"]),
                "rotation_uncertainty_deg": float(row["rotation_uncertainty_deg"]),
            }
        if set(root_fixed) != set(intake["required_rigid_attachment_frames"]):
            raise _IncompleteEvidence("rigid transform coverage differs")

        readiness = assess_current_collision_readiness(context)
        if (
            installed_profile.manifest_id != context.snapshot.manifest_id
            or installed_profile.build_snapshot_sha256 != context.snapshot.snapshot_hash
            or installed_profile.robot_model_sha256 != context.scenario.model_sha256
            or installed_profile.base_contract_sha256 != readiness.contract.content_hash
        ):
            raise _IncompleteEvidence("installed profile differs from active context")

        maximum_rigid_uncertainty = 0.0
        for body in installed_profile.contract.bodies:
            if body.parent_frame not in root_fixed:
                continue
            evidence = uncertainty_by_frame[body.parent_frame]
            radius = max((_primitive_origin_radius(item) for item in body.primitives), default=0.0)
            rotational = radius * math.radians(evidence["rotation_uncertainty_deg"])
            maximum_rigid_uncertainty = max(
                maximum_rigid_uncertainty,
                evidence["translation_uncertainty_mm"] + rotational,
            )
        base_clearance = installed_profile.clearance_policy
        derived_clearance = CollisionClearancePolicy(
            base_clearance.minimum_separation_mm,
            base_clearance.geometry_uncertainty_mm_per_body + maximum_rigid_uncertainty,
            base_clearance.pose_uncertainty_mm_per_body,
            base_clearance.evidence_state,
            base_clearance.source_reference + "; plus conservative maximum C03 rigid-transform uncertainty",
        )
        evaluation_policy = CollisionEvaluationPolicy(clearance_policy=derived_clearance)

        model = load_pinned_urdf(
            context.scenario.model_path, context.scenario.model_sha256
        ).model
        board_t_world = RigidTransform(
            root_frame,
            model.root_link,
            snapshot.board_T_vendor_world.rotation,
            snapshot.board_T_vendor_world.translation_mm,
        )
        movable = set(model.movable_joint_names)
        remaining = movable - set(ARM_JOINT_NAMES)
        if len(remaining) != 1:
            raise _IncompleteEvidence("pinned URDF gripper topology differs")
        gripper_name = next(iter(remaining))
        rigid_parent_frames = {
            body.parent_frame
            for body in installed_profile.contract.bodies
            if body.binding_mode is CollisionBindingMode.RIGID_FRAME
        }
        required_configuration = {
            body.body_id
            for body in installed_profile.contract.bodies
            if body.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
        }
        poses: list[CollisionPose] = []
        sample_reports: list[dict[str, Any]] = []
        primitive_tests = 0
        for index, (planned, evidence) in enumerate(zip(plan, samples, strict=True)):
            joint_positions = {
                name: JointPosition.radians(float(planned.joint_positions_rad[name]))
                for name in ARM_JOINT_NAMES
            }
            joint_positions[gripper_name] = context.scenario.fixed_gripper_position
            world = model.forward_kinematics(joint_positions)
            model_transforms = {
                frame: board_t_world.compose(transform)
                for frame, transform in world.items()
            }
            root_transforms = {
                frame: model_transforms[frame]
                for frame in rigid_parent_frames if frame in model_transforms
            }
            root_transforms.update(root_fixed)
            for body in installed_profile.contract.bodies:
                if body.binding_mode is not CollisionBindingMode.CONFIGURATION_SAMPLED:
                    continue
                if body.parent_frame == root_frame:
                    root_transforms.setdefault(
                        body.parent_frame, RigidTransform.identity(root_frame)
                    )
                elif body.parent_frame in model_transforms:
                    root_transforms.setdefault(
                        body.parent_frame, model_transforms[body.parent_frame]
                    )
                elif body.parent_frame in root_fixed:
                    root_transforms.setdefault(
                        body.parent_frame, root_fixed[body.parent_frame]
                    )
            if set(evidence.geometry_by_body) != required_configuration:
                raise _IncompleteEvidence("configuration body coverage differs")
            sampled = {
                body_id: binding.geometry
                for body_id, binding in evidence.geometry_by_body.items()
            }
            pose = CollisionPose(
                f"c03-partition-{partition_index:04d}-sample-{index:04d}",
                root_frame, root_transforms, sampled,
            )
            poses.append(pose)
            evaluation = evaluate_collision_pose(
                installed_profile.contract, pose, evaluation_policy
            )
            primitive_tests += evaluation.narrow_phase_primitive_pair_test_count
            if primitive_tests > selected.maximum_total_primitive_pair_tests:
                return _result(
                    status=RESOURCE_STATUS, partition_index=partition_index,
                    lineage=lineage, policy=selected,
                    sample_reports=sample_reports,
                    blockers=["PARTITION_PRIMITIVE_PAIR_TEST_LIMIT_EXCEEDED"],
                )
            clearance = _clearance_summary(
                installed_profile.contract, pose, evaluation_policy
            )
            sample_reports.append({
                "sample_sequence": index,
                "sample_plan_sha256": planned.content_sha256,
                "configuration_evidence_sha256_by_body": {
                    body_id: evidence.geometry_by_body[body_id].content_sha256
                    for body_id in sorted(evidence.geometry_by_body)
                },
                "collision_report_sha256": evaluation.report_hash,
                "status": evaluation.status.value,
                "collision_free_diagnostic": evaluation.collision_free_diagnostic,
                "checked_body_pair_count": evaluation.checked_body_pair_count,
                "narrow_phase_primitive_pair_test_count": evaluation.narrow_phase_primitive_pair_test_count,
                "collisions": [item.to_dict() for item in evaluation.collisions],
                "pose_blockers": [item.to_dict() for item in evaluation.pose_blockers],
                "uncertainty_inflation": derived_clearance.to_dict(),
                **clearance,
            })

        path_lengths, ancestor_joints = _link_path_bounds(model)
        segment_reports: list[dict[str, Any]] = []
        for segment_index, (start, end, envelopes) in enumerate(
            zip(plan[:-1], plan[1:], sweeps, strict=True)
        ):
            if set(envelopes) != required_configuration:
                raise _IncompleteEvidence("segment envelope body coverage differs")
            delta = {
                name: abs(end.joint_positions_rad[name] - start.joint_positions_rad[name])
                for name in ARM_JOINT_NAMES
            }
            bodies: list[CollisionBody] = []
            requirements: list[CollisionBodyRequirement] = []
            motion_bounds: dict[str, float] = {}
            start_pose = poses[segment_index]
            for body in installed_profile.contract.bodies:
                requirements.append(CollisionBodyRequirement(
                    body.body_id, root_frame, body.role,
                    CollisionBindingMode.STATIC_ROOT,
                    "C03 conservative adjacent-sample envelope",
                ))
                if body.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED:
                    envelope = envelopes[body.body_id]
                    if (
                        envelope.segment_sequence != segment_index
                        or envelope.start_sample_sha256 != start.content_sha256
                        or envelope.end_sample_sha256 != end.content_sha256
                    ):
                        raise _IncompleteEvidence("segment envelope lineage differs")
                    primitives = envelope.geometry_root_frame.primitives
                    source = f"measured C03 sweep {envelope.content_sha256}"
                    motion_bounds[body.body_id] = 0.0
                elif body.binding_mode is CollisionBindingMode.STATIC_ROOT:
                    primitives = body.primitives
                    source = body.source_reference
                    motion_bounds[body.body_id] = 0.0
                elif body.parent_frame in root_fixed:
                    transform = root_fixed[body.parent_frame]
                    primitives = tuple(
                        _world_envelope_primitive(item, transform, 0.0)
                        for item in body.primitives
                    )
                    source = f"root-fixed C03 binding {body.parent_frame}"
                    motion_bounds[body.body_id] = 0.0
                else:
                    transform = start_pose.root_t_parent.get(body.parent_frame)
                    if transform is None:
                        raise _IncompleteEvidence("segment rigid parent transform is missing")
                    chain_radius = path_lengths[body.parent_frame] + max(
                        _primitive_origin_radius(item) for item in body.primitives
                    )
                    motion = chain_radius * sum(
                        delta[name] for name in ancestor_joints[body.parent_frame]
                    )
                    primitives = tuple(
                        _world_envelope_primitive(item, transform, motion)
                        for item in body.primitives
                    )
                    source = "pinned URDF path-radius motion bound"
                    motion_bounds[body.body_id] = motion
                bodies.append(CollisionBody(
                    body.body_id, root_frame, body.role,
                    CollisionEvidenceState.ACCEPTED_MEASURED,
                    tuple(primitives), CollisionBindingMode.STATIC_ROOT, source,
                ))
            envelope_contract = CollisionGeometryContract(
                f"{installed_profile.contract.contract_id}:c03-p{partition_index:04d}-s{segment_index:04d}",
                root_frame, tuple(requirements), tuple(bodies),
                installed_profile.contract.pair_exclusions,
            )
            envelope_pose = CollisionPose(
                f"c03-partition-{partition_index:04d}-segment-{segment_index:04d}",
                root_frame, {},
            )
            evaluation = evaluate_collision_pose(
                envelope_contract, envelope_pose, evaluation_policy
            )
            primitive_tests += evaluation.narrow_phase_primitive_pair_test_count
            if primitive_tests > selected.maximum_total_primitive_pair_tests:
                return _result(
                    status=RESOURCE_STATUS, partition_index=partition_index,
                    lineage=lineage, policy=selected,
                    sample_reports=sample_reports, segment_reports=segment_reports,
                    blockers=["PARTITION_PRIMITIVE_PAIR_TEST_LIMIT_EXCEEDED"],
                )
            clearance = _clearance_summary(
                envelope_contract, envelope_pose, evaluation_policy
            )
            segment_reports.append({
                "segment_sequence": segment_index,
                "start_sample_sha256": start.content_sha256,
                "end_sample_sha256": end.content_sha256,
                "configuration_envelope_sha256_by_body": {
                    body_id: envelopes[body_id].content_sha256
                    for body_id in sorted(envelopes)
                },
                "rigid_motion_bound_mm_by_body": motion_bounds,
                "collision_report_sha256": evaluation.report_hash,
                "status": evaluation.status.value,
                "collision_free_diagnostic": evaluation.collision_free_diagnostic,
                "checked_body_pair_count": evaluation.checked_body_pair_count,
                "narrow_phase_primitive_pair_test_count": evaluation.narrow_phase_primitive_pair_test_count,
                "collisions": [item.to_dict() for item in evaluation.collisions],
                "pose_blockers": [item.to_dict() for item in evaluation.pose_blockers],
                "uncertainty_inflation": derived_clearance.to_dict(),
                **clearance,
            })

        collision_found = any(
            item["status"] == CollisionEvaluationStatus.COLLISION_DETECTED.value
            for item in [*sample_reports, *segment_reports]
        )
        incomplete_found = any(
            item["status"] not in {
                CollisionEvaluationStatus.COLLISION_DETECTED.value,
                CollisionEvaluationStatus.CLEAR_AT_SAMPLED_POSE.value,
            }
            for item in [*sample_reports, *segment_reports]
        )
        if incomplete_found:
            return _result(
                status=INCOMPLETE_STATUS, partition_index=partition_index,
                lineage=lineage, policy=selected, sample_reports=sample_reports,
                segment_reports=segment_reports,
                blockers=["COLLISION_EVALUATION_INCOMPLETE"],
            )
        if collision_found:
            return _result(
                status=COLLISION_STATUS, partition_index=partition_index,
                lineage=lineage, policy=selected, sample_reports=sample_reports,
                segment_reports=segment_reports,
                blockers=["PARTITION_COLLISION_DETECTED"],
            )
        return _result(
            status=CLEAR_STATUS, partition_index=partition_index,
            lineage=lineage, policy=selected, sample_reports=sample_reports,
            segment_reports=segment_reports,
            blockers=[
                "ICQ6_CONTINUOUS_SEGMENT_PROOF_REQUIRED",
                "FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION",
                "INSTALLED_PHYSICAL_QUALIFICATION_REQUIRED",
            ],
        )
    except _IncompleteEvidence as exc:
        return _result(
            status=INCOMPLETE_STATUS, partition_index=partition_index,
            lineage=lineage, policy=selected,
            blockers=["INCOMPLETE_OR_CROSSED_PARTITION_EVIDENCE"],
            error={"type": type(exc).__name__, "message": str(exc)},
        )
    except CollisionResourceLimitError as exc:
        return _result(
            status=RESOURCE_STATUS, partition_index=partition_index,
            lineage=lineage, policy=selected,
            blockers=["COLLISION_KERNEL_RESOURCE_LIMIT"],
            error={"type": type(exc).__name__, "message": str(exc)},
        )
    except Exception as exc:  # preserve evaluator failures as a distinct receipt
        return _result(
            status=ERROR_STATUS, partition_index=partition_index,
            lineage=lineage, policy=selected,
            blockers=["PARTITION_COLLISION_EVALUATOR_ERROR"],
            error={"type": type(exc).__name__, "message": str(exc)},
        )


__all__ = [
    "CLEAR_STATUS", "COLLISION_STATUS", "ERROR_STATUS", "INCOMPLETE_STATUS",
    "RESOURCE_STATUS", "SCHEMA", "C03PartitionCollisionEvaluatorV1Error",
    "C03PartitionCollisionResourcePolicy", "evaluate_c03_collision_partition_v1",
]
