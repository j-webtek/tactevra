from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import replace
import hashlib
import math
from pathlib import Path
from typing import Any

import pytest

from rocell.application.collision_readiness import (
    assess_ambient_light_b0477_collision_readiness,
    assess_current_collision_readiness,
    assess_static_b0477_collision_readiness,
    inspect_pinned_urdf_collision_evidence,
)
from rocell.application.context import (
    SimulationContextError,
    load_simulation_context,
)
from rocell.geometry import RigidTransform, Rotation3, Vec3
from rocell.simulation.collision import (
    CapsuleMm,
    CollisionBindingMode,
    CollisionBlockerCode,
    CollisionBody,
    CollisionBodyRequirement,
    CollisionBodyRole,
    CollisionClearanceEvidenceState,
    CollisionClearancePolicy,
    CollisionEvaluationPolicy,
    CollisionEvaluationStatus,
    CollisionEvidenceState,
    CollisionExclusionEvidenceState,
    CollisionExclusionScope,
    CollisionGeometryContract,
    CollisionPose,
    CollisionPairExclusion,
    CollisionResourceLimitError,
    OrientedBoxMm,
    SphereMm,
    SampledCollisionGeometry,
    audit_collision_geometry,
    evaluate_collision_pose,
    evaluate_collision_sweep,
)
from rocell.simulation.static_route_collision import (
    AMBIENT_LIGHT_ABSENT_BODY_IDS,
    AMBIENT_LIGHT_STATIC_ROUTE_BODY_REQUIREMENTS,
    STATIC_B0477_LEGACY_BODY_MIGRATION,
    STATIC_ROUTE_BODY_REQUIREMENTS,
)


WORKSPACE = Path(__file__).resolve().parents[3]
MANIFEST = WORKSPACE / "software/config/system_manifest.json"


def _transform(frame: str, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> RigidTransform:
    return RigidTransform("root", frame, Rotation3.identity(), Vec3(x, y, z))


def _synthetic_clearance(
    minimum_separation_mm: float = 0.001,
    *,
    geometry_uncertainty_mm_per_body: float = 0.0,
    pose_uncertainty_mm_per_body: float = 0.0,
) -> CollisionClearancePolicy:
    return CollisionClearancePolicy(
        minimum_separation_mm,
        geometry_uncertainty_mm_per_body,
        pose_uncertainty_mm_per_body,
        CollisionClearanceEvidenceState.SYNTHETIC_TEST_ONLY,
        "unit-test synthetic clearance fixture",
    )


def _policy(**kwargs: Any) -> CollisionEvaluationPolicy:
    return CollisionEvaluationPolicy(
        clearance_policy=_synthetic_clearance(),
        **kwargs,
    )


def _two_body_contract(
    first: SphereMm | CapsuleMm | OrientedBoxMm,
    second: SphereMm | CapsuleMm | OrientedBoxMm,
    *,
    excluded: bool = False,
) -> CollisionGeometryContract:
    requirements = (
        CollisionBodyRequirement("first", "first_frame", CollisionBodyRole.ROBOT_LINK),
        CollisionBodyRequirement("second", "second_frame", CollisionBodyRole.ATTACHMENT),
    )
    bodies = (
        CollisionBody(
            "first",
            "first_frame",
            CollisionBodyRole.ROBOT_LINK,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            (first,),
            source_reference="unit-test fixture",
        ),
        CollisionBody(
            "second",
            "second_frame",
            CollisionBodyRole.ATTACHMENT,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            (second,),
            source_reference="unit-test fixture",
        ),
    )
    return CollisionGeometryContract(
        "synthetic-two-body-v1",
        "root",
        requirements,
        bodies,
        (
            (
                CollisionPairExclusion(
                    "first",
                    "second",
                    CollisionExclusionScope.SYNTHETIC_TEST_ONLY,
                    CollisionExclusionEvidenceState.SYNTHETIC_TEST_ONLY,
                    "synthetic pair exclusion exercises explicit exclusion behavior",
                    "unit-test fixture",
                ),
            )
            if excluded
            else ()
        ),
    )


def _origin_pose() -> CollisionPose:
    return CollisionPose(
        "origin",
        "root",
        {
            "first_frame": _transform("first_frame"),
            "second_frame": _transform("second_frame"),
        },
    )


def test_current_artifact_audit_is_context_bound_and_names_every_gap() -> None:
    context = load_simulation_context(WORKSPACE, MANIFEST)
    report = assess_current_collision_readiness(context)

    assert report.status == "COLLISION_DIAGNOSTIC_BLOCKED_REQUIRED_GEOMETRY_INCOMPLETE"
    assert report.manifest_id == context.snapshot.manifest_id
    assert report.urdf_sha256 == context.scenario.model_sha256
    assert report.alignment_status == "PASS_NOMINAL_ALIGNMENT_WITH_PHYSICAL_HOLDS"
    assert set(report.missing_required_body_ids) == {
        "robot:base_link",
        "robot:link1",
        "robot:link2",
        "robot:link3",
        "robot:link4",
        "robot:link5",
        "robot:gripper",
    }
    assert set(report.unknown_required_body_ids) == {
        "installation:base_and_factory_clamp",
        "attachment:camera_holder",
        "attachment:camera_module",
        "attachment:camera_connector",
        "attachment:moving_camera_cable",
        "attachment:contact_tool",
    }
    assert len(report.contract.requirements) == 19
    assert set(report.geometry_audit.diagnostic_only_body_ids) == {
        "workcell:board_solid",
        "workcell:keyboard",
        "workcell:phone",
        "workcell:station:keyboard_left",
        "workcell:station:keyboard_right",
        "workcell:station:phone_tcp",
    }
    document = report.to_dict()
    assert document["verified_sources"]["urdf"]["collision_elements_present"] is False
    assert document["verified_sources"]["urdf"]["collision_element_count"] == 0
    assert document["verified_sources"]["urdf"]["collision_link_names"] == []
    assert document["verified_context"]["snapshot_safe_to_power_robot"] is False
    assert document["verified_context"]["snapshot_contact_enabled"] is False
    assert document["authority"]["hardware_commands_generated"] == 0
    assert document["authority"]["contact_enabled_by_report"] is False
    assert document["authority"]["safe_to_power_robot_conferred_by_report"] is False
    assert len(report.report_hash) == 64
    assert report.contract.pair_exclusions
    assert all(
        item.scope is CollisionExclusionScope.URDF_ADJACENT_DIAGNOSTIC
        and item.evidence_state
        is CollisionExclusionEvidenceState.PINNED_KINEMATIC_DIAGNOSTIC
        for item in report.contract.pair_exclusions
    )
    assert report.geometry_audit.diagnostic_only_exclusion_pairs
    assert (
        document["contract"]["exclusion_policy"]
        ["phase_specific_tool_or_contact_allowances_are_global_exclusions"]
        is False
    )


def test_static_b0477_contract_migration_is_explicit_and_drops_moving_camera() -> None:
    context = load_simulation_context(WORKSPACE, MANIFEST)
    legacy = assess_current_collision_readiness(context)
    report = assess_static_b0477_collision_readiness(context)
    required = {item.body_id: item for item in report.contract.requirements}
    catalog_ids = {item.body_id for item in STATIC_ROUTE_BODY_REQUIREMENTS}

    assert legacy.contract.contract_id == (
        "ROCELL-ROARM-M3-RC03-PREHARDWARE-COLLISION-V1"
    )
    assert report.contract.contract_id == (
        "ROCELL-ROARM-M3-RC03-STATIC-B0477-PREHARDWARE-COLLISION-V2"
    )
    assert report.to_dict()["schema"] == (
        "rocell.static_b0477_collision_readiness.v2"
    )
    assert catalog_ids <= set(required)
    assert len(report.contract.requirements) == 32
    assert report.contract.pair_exclusions == ()
    assert report.geometry_audit.diagnostic_only_exclusion_pairs == ()
    assert set(report.geometry_audit.diagnostic_only_body_ids) == {
        "diagnostic_proxy:board_solid",
        "diagnostic_proxy:keyboard",
        "diagnostic_proxy:phone",
        "diagnostic_proxy:station:keyboard_left",
        "diagnostic_proxy:station:keyboard_right",
        "diagnostic_proxy:station:phone_tcp",
    }
    assert "attachment:moving_camera_cable" not in required
    assert required["cable:fixed_usb_route"].binding_mode is (
        CollisionBindingMode.STATIC_ROOT
    )
    assert required["attachment:arm_harness"].binding_mode is (
        CollisionBindingMode.CONFIGURATION_SAMPLED
    )
    assert {
        old_id for old_id, _ in STATIC_B0477_LEGACY_BODY_MIGRATION
    } == {
        "installation:base_and_factory_clamp",
        "attachment:camera_holder",
        "attachment:camera_module",
        "attachment:camera_connector",
        "attachment:moving_camera_cable",
        "attachment:contact_tool",
    }
    migrated_ids = {
        body_id
        for _, replacements in STATIC_B0477_LEGACY_BODY_MIGRATION
        for body_id in replacements
    }
    assert migrated_ids <= catalog_ids


def test_ambient_light_v3_removes_only_nonexistent_fixed_light_hardware() -> None:
    context = load_simulation_context(WORKSPACE, MANIFEST)
    retained = assess_static_b0477_collision_readiness(context)
    report = assess_ambient_light_b0477_collision_readiness(context)
    required = {item.body_id for item in report.contract.requirements}
    catalog_ids = {
        item.body_id for item in AMBIENT_LIGHT_STATIC_ROUTE_BODY_REQUIREMENTS
    }

    assert report.contract.contract_id.endswith(
        "AMBIENT-LIGHT-B0477-PREHARDWARE-COLLISION-V3"
    )
    assert report.to_dict()["schema"] == (
        "rocell.ambient_light_b0477_collision_readiness.v3"
    )
    assert len(report.contract.requirements) == 28
    assert catalog_ids <= required
    assert not (set(AMBIENT_LIGHT_ABSENT_BODY_IDS) & required)
    assert {item.body_id for item in retained.contract.requirements} - required == set(
        AMBIENT_LIGHT_ABSENT_BODY_IDS
    )
    assert "installation:base_clamp" in required
    assert any(
        "variable ambient illumination" in limitation
        for limitation in report.to_dict()["limitations"]
    )
    assert report.to_dict()["authority"]["hardware_commands_generated"] == 0


def test_exact_pinned_urdf_snapshot_inventories_collision_tags(tmp_path: Path) -> None:
    payload = b"""<?xml version='1.0'?>
<robot name='fixture'>
  <link name='base'>
    <collision><geometry><sphere radius='0.01'/></geometry></collision>
  </link>
</robot>
"""
    source = tmp_path / "fixture.urdf"
    source.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    evidence = inspect_pinned_urdf_collision_evidence(source, digest)

    assert evidence.loaded_model.sha256 == digest
    assert evidence.collision_elements_present
    assert evidence.collision_element_count == 1
    assert evidence.collision_link_names == ("base",)
    assert evidence.collision_elements_outside_links == 0


def test_current_artifact_audit_revalidates_in_memory_context() -> None:
    context = load_simulation_context(WORKSPACE, MANIFEST)
    altered_scene = replace(
        context.scene,
        assumptions=context.scene.assumptions + ("in-memory drift",),
    )
    with pytest.raises(SimulationContextError, match="scene differs"):
        assess_current_collision_readiness(replace(context, scene=altered_scene))


def test_incomplete_geometry_blocks_before_pair_testing_and_cannot_report_clear() -> None:
    requirement = CollisionBodyRequirement(
        "unknown-camera", "camera", CollisionBodyRole.CAMERA
    )
    body = CollisionBody(
        "unknown-camera",
        "camera",
        CollisionBodyRole.CAMERA,
        CollisionEvidenceState.UNKNOWN,
        source_reference="installed depth and transform absent",
    )
    contract = CollisionGeometryContract("blocked", "root", (requirement,), (body,))
    report = evaluate_collision_pose(contract, CollisionPose("pose", "root", {}))

    assert report.status is CollisionEvaluationStatus.BLOCKED_INCOMPLETE_GEOMETRY
    assert not report.evaluation_complete
    assert not report.collision_free_diagnostic
    assert report.checked_body_pair_count == 0
    assert report.geometry_audit.diagnostic_blockers[0].code is (
        CollisionBlockerCode.REQUIRED_BODY_GEOMETRY_UNKNOWN
    )


def test_empty_required_body_set_cannot_vacuously_report_collision_free() -> None:
    with pytest.raises(ValueError, match="at least one required body"):
        CollisionGeometryContract("empty", "root", (), ())


def test_pinned_and_synthetic_geometry_are_diagnostic_only() -> None:
    contract = _two_body_contract(
        SphereMm(Vec3.zero(), 1.0),
        SphereMm(Vec3(10.0, 0.0, 0.0), 1.0),
    )
    audit = audit_collision_geometry(contract)

    assert audit.diagnostic_ready
    assert not audit.physical_geometry_complete
    assert set(audit.diagnostic_only_body_ids) == {"first", "second"}
    assert audit.to_dict()["authority"]["can_release_physical_gates"] is False


def test_static_root_parent_mismatch_blocks_at_geometry_audit_boundary() -> None:
    requirement = CollisionBodyRequirement(
        "fixture",
        "wrong_root",
        CollisionBodyRole.STATIC_ENVIRONMENT,
        CollisionBindingMode.STATIC_ROOT,
    )
    body = CollisionBody(
        "fixture",
        "wrong_root",
        CollisionBodyRole.STATIC_ENVIRONMENT,
        CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
        (OrientedBoxMm(Vec3.zero(), Vec3(1.0, 1.0, 1.0)),),
        CollisionBindingMode.STATIC_ROOT,
        "unit-test malformed static binding",
    )
    contract = CollisionGeometryContract("bad-static", "root", (requirement,), (body,))

    audit = audit_collision_geometry(contract)
    report = evaluate_collision_pose(contract, CollisionPose("pose", "root", {}), _policy())

    assert not audit.diagnostic_ready
    assert audit.diagnostic_blockers[0].code is (
        CollisionBlockerCode.STATIC_ROOT_PARENT_NOT_CONTRACT_ROOT
    )
    assert report.status is CollisionEvaluationStatus.BLOCKED_INCOMPLETE_GEOMETRY
    assert report.checked_body_pair_count == 0


class _LyingMapping(Mapping[str, Any]):
    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values = dict(values)
        self.iterated = 0

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        for key in self._values:
            self.iterated += 1
            yield key

    def __len__(self) -> int:
        return 0


def test_pose_transform_materialization_does_not_trust_mapping_len() -> None:
    transforms = _LyingMapping(
        {
            f"frame-{index}": _transform(f"frame-{index}")
            for index in range(257)
        }
    )
    with pytest.raises(CollisionResourceLimitError, match="pose transforms items"):
        CollisionPose("adversarial", "root", transforms)
    assert transforms.iterated == 257


def test_sampled_geometry_materialization_does_not_trust_mapping_len() -> None:
    sample = SampledCollisionGeometry(
        (SphereMm(Vec3.zero(), 1.0),),
        CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
        "unit-test sample",
    )
    configurations = _LyingMapping(
        {f"body-{index}": sample for index in range(129)}
    )
    with pytest.raises(CollisionResourceLimitError, match="configuration geometry items"):
        CollisionPose("adversarial", "root", {}, configurations)
    assert configurations.iterated == 129


def test_clearance_policy_is_required_and_inflates_near_separation() -> None:
    contract = _two_body_contract(
        SphereMm(Vec3.zero(), 1.0), SphereMm(Vec3.zero(), 1.0)
    )
    pose = CollisionPose(
        "near",
        "root",
        {
            "first_frame": _transform("first_frame"),
            "second_frame": _transform("second_frame", 2.2),
        },
    )

    missing = evaluate_collision_pose(contract, pose)
    violating = evaluate_collision_pose(
        contract,
        pose,
        CollisionEvaluationPolicy(clearance_policy=_synthetic_clearance(0.3)),
    )
    clear = evaluate_collision_pose(
        contract,
        pose,
        CollisionEvaluationPolicy(clearance_policy=_synthetic_clearance(0.1)),
    )

    assert missing.status is CollisionEvaluationStatus.BLOCKED_CLEARANCE_POLICY
    assert missing.pose_blockers[0].code is CollisionBlockerCode.CLEARANCE_POLICY_MISSING
    assert violating.status is CollisionEvaluationStatus.COLLISION_DETECTED
    assert clear.status is CollisionEvaluationStatus.CLEAR_AT_SAMPLED_POSE
    assert clear.collision_free_diagnostic


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (SphereMm(Vec3.zero(), 1.0), SphereMm(Vec3(1.5, 0.0, 0.0), 1.0)),
        (
            SphereMm(Vec3.zero(), 1.0),
            CapsuleMm(Vec3(1.5, -2.0, 0.0), Vec3(1.5, 2.0, 0.0), 0.6),
        ),
        (
            CapsuleMm(Vec3(-2.0, 0.0, 0.0), Vec3(2.0, 0.0, 0.0), 0.25),
            CapsuleMm(Vec3(0.0, -2.0, 0.0), Vec3(0.0, 2.0, 0.0), 0.25),
        ),
        (
            SphereMm(Vec3(1.5, 0.0, 0.0), 0.6),
            OrientedBoxMm(Vec3.zero(), Vec3(1.0, 1.0, 1.0)),
        ),
        (
            CapsuleMm(Vec3(-2.0, 0.0, 0.0), Vec3(2.0, 0.0, 0.0), 0.1),
            OrientedBoxMm(Vec3.zero(), Vec3(0.5, 0.5, 0.5)),
        ),
        (
            OrientedBoxMm(Vec3.zero(), Vec3(1.0, 1.0, 1.0)),
            OrientedBoxMm(
                Vec3(1.5, 0.0, 0.0),
                Vec3(1.0, 0.5, 0.5),
                Rotation3.from_rpy(0.0, 0.0, math.pi / 4.0),
            ),
        ),
    ],
    ids=(
        "sphere-sphere",
        "sphere-capsule",
        "capsule-capsule",
        "sphere-obb",
        "capsule-obb",
        "obb-obb",
    ),
)
def test_narrow_phase_primitive_pairs_detect_collision(
    first: SphereMm | CapsuleMm | OrientedBoxMm,
    second: SphereMm | CapsuleMm | OrientedBoxMm,
) -> None:
    report = evaluate_collision_pose(
        _two_body_contract(first, second), _origin_pose(), _policy()
    )

    assert report.status is CollisionEvaluationStatus.COLLISION_DETECTED
    assert report.evaluation_complete
    assert not report.collision_free_diagnostic
    assert report.broad_phase_candidate_count == 1
    assert report.narrow_phase_primitive_pair_test_count == 1
    assert len(report.collisions) == 1


def test_crossing_submillimetre_capsules_use_scale_relative_segment_math() -> None:
    first = CapsuleMm(
        Vec3(-0.0005, 0.0, 0.0),
        Vec3(0.0005, 0.0, 0.0),
        0.000001,
    )
    crossing = CapsuleMm(
        Vec3(0.0, -0.0005, 0.0),
        Vec3(0.0, 0.0005, 0.0),
        0.000001,
    )
    separated = CapsuleMm(
        Vec3(0.0, -0.0005, 0.00001),
        Vec3(0.0, 0.0005, 0.00001),
        0.000001,
    )
    tiny_policy = CollisionEvaluationPolicy(
        clearance_policy=_synthetic_clearance(0.000000001)
    )

    collision = evaluate_collision_pose(
        _two_body_contract(first, crossing), _origin_pose(), tiny_policy
    )
    clear = evaluate_collision_pose(
        _two_body_contract(first, separated), _origin_pose(), tiny_policy
    )

    assert collision.status is CollisionEvaluationStatus.COLLISION_DETECTED
    assert clear.status is CollisionEvaluationStatus.CLEAR_AT_SAMPLED_POSE


def test_broad_phase_rejects_separated_bodies_and_reports_clear_diagnostic() -> None:
    contract = _two_body_contract(
        SphereMm(Vec3.zero(), 1.0), SphereMm(Vec3.zero(), 1.0)
    )
    pose = CollisionPose(
        "separated",
        "root",
        {
            "first_frame": _transform("first_frame", -20.0),
            "second_frame": _transform("second_frame", 20.0),
        },
    )
    report = evaluate_collision_pose(contract, pose, _policy())

    assert report.status is CollisionEvaluationStatus.CLEAR_AT_SAMPLED_POSE
    assert report.collision_free_diagnostic
    assert report.checked_body_pair_count == 1
    assert report.broad_phase_candidate_count == 0
    assert report.narrow_phase_primitive_pair_test_count == 0
    assert report.to_dict()["authority"]["can_release_physical_gates"] is False


def test_pose_report_binds_deterministic_contract_pose_and_policy_content() -> None:
    contract = _two_body_contract(
        SphereMm(Vec3.zero(), 1.0), SphereMm(Vec3.zero(), 1.0)
    )
    pose = CollisionPose(
        "bound-pose",
        "root",
        {
            "first_frame": _transform("first_frame", -20.0),
            "second_frame": _transform("second_frame", 20.0),
        },
    )
    policy = _policy()
    report = evaluate_collision_pose(contract, pose, policy)
    repeated = evaluate_collision_pose(contract, pose, policy)
    bindings = report.to_dict()["input_bindings"]

    assert bindings["contract"]["sha256"] == contract.content_hash
    assert bindings["contract"]["content"] == contract.to_dict()
    assert bindings["pose"]["sha256"] == pose.content_hash
    assert bindings["pose"]["content"] == pose.to_dict()
    assert bindings["policy"]["sha256"] == policy.content_hash
    assert bindings["policy"]["content"] == policy.to_dict()
    assert report.report_hash == repeated.report_hash

    altered_pose = CollisionPose(
        "bound-pose",
        "root",
        {
            "first_frame": _transform("first_frame", -20.0),
            "second_frame": _transform("second_frame", 21.0),
        },
    )
    altered_policy = CollisionEvaluationPolicy(
        clearance_policy=_synthetic_clearance(0.002)
    )
    assert altered_pose.content_hash != pose.content_hash
    assert altered_policy.content_hash != policy.content_hash


def test_explicit_exclusion_is_the_only_way_to_skip_a_nonstatic_pair() -> None:
    contract = _two_body_contract(
        SphereMm(Vec3.zero(), 2.0),
        SphereMm(Vec3.zero(), 2.0),
        excluded=True,
    )
    report = evaluate_collision_pose(contract, _origin_pose(), _policy())

    assert report.collision_free_diagnostic
    assert report.checked_body_pair_count == 0
    exclusion = contract.pair_exclusions[0]
    assert exclusion.scope is CollisionExclusionScope.SYNTHETIC_TEST_ONLY
    assert exclusion.rationale
    assert not exclusion.evidence_state.is_physically_accepted
    assert audit_collision_geometry(contract).diagnostic_only_exclusion_pairs == (
        ("first", "second"),
    )


def test_missing_pose_transform_fails_closed() -> None:
    contract = _two_body_contract(
        SphereMm(Vec3.zero(), 1.0), SphereMm(Vec3.zero(), 1.0)
    )
    pose = CollisionPose(
        "missing-second",
        "root",
        {"first_frame": _transform("first_frame")},
    )
    report = evaluate_collision_pose(contract, pose, _policy())

    assert report.status is CollisionEvaluationStatus.BLOCKED_INCOMPLETE_POSE
    assert not report.collision_free_diagnostic
    assert report.pose_blockers[0].body_id == "second"
    assert report.pose_blockers[0].code is CollisionBlockerCode.POSE_TRANSFORM_MISSING


def test_body_pair_and_policy_hard_caps_fail_before_unbounded_work() -> None:
    requirements = tuple(
        CollisionBodyRequirement(f"body-{index}", f"frame-{index}", CollisionBodyRole.ROBOT_LINK)
        for index in range(3)
    )
    bodies = tuple(
        CollisionBody(
            f"body-{index}",
            f"frame-{index}",
            CollisionBodyRole.ROBOT_LINK,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            (SphereMm(Vec3.zero(), 1.0),),
            source_reference="unit-test fixture",
        )
        for index in range(3)
    )
    contract = CollisionGeometryContract("three", "root", requirements, bodies)
    pose = CollisionPose(
        "pose",
        "root",
        {f"frame-{index}": _transform(f"frame-{index}") for index in range(3)},
    )

    with pytest.raises(CollisionResourceLimitError, match="body-pair count"):
        evaluate_collision_pose(
            contract,
            pose,
            _policy(maximum_body_pairs_per_pose=1),
        )
    with pytest.raises(CollisionResourceLimitError, match="hard maximum"):
        CollisionEvaluationPolicy(maximum_sweep_samples=513)


def test_primitive_collection_uses_a_hard_max_plus_one_sentinel() -> None:
    with pytest.raises(CollisionResourceLimitError, match="hard maximum 64"):
        CollisionBody(
            "too-many-primitives",
            "frame",
            CollisionBodyRole.ROBOT_LINK,
            CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
            tuple(SphereMm(Vec3(float(index), 0.0, 0.0), 1.0) for index in range(65)),
            source_reference="unit-test fixture",
        )


def _moving_sphere_contract() -> CollisionGeometryContract:
    return CollisionGeometryContract(
        "moving-sphere",
        "root",
        (
            CollisionBodyRequirement(
                "moving", "moving_frame", CollisionBodyRole.ROBOT_LINK
            ),
            CollisionBodyRequirement(
                "fixture",
                "root",
                CollisionBodyRole.STATIC_ENVIRONMENT,
                CollisionBindingMode.STATIC_ROOT,
            ),
        ),
        (
            CollisionBody(
                "moving",
                "moving_frame",
                CollisionBodyRole.ROBOT_LINK,
                CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
                (SphereMm(Vec3.zero(), 1.0),),
                source_reference="unit-test fixture",
            ),
            CollisionBody(
                "fixture",
                "root",
                CollisionBodyRole.STATIC_ENVIRONMENT,
                CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
                (OrientedBoxMm(Vec3.zero(), Vec3(1.0, 1.0, 1.0)),),
                CollisionBindingMode.STATIC_ROOT,
                "unit-test fixture",
            ),
        ),
    )


def test_discrete_sweep_detects_midpath_collision_and_disclaims_continuous_proof() -> None:
    contract = _moving_sphere_contract()
    start = CollisionPose(
        "start", "root", {"moving_frame": _transform("moving_frame", -10.0)}
    )
    end = CollisionPose(
        "end", "root", {"moving_frame": _transform("moving_frame", 10.0)}
    )
    report = evaluate_collision_sweep(
        contract,
        start,
        end,
        _policy(maximum_surface_step_mm=1.0),
    )

    assert report.status is CollisionEvaluationStatus.COLLISION_DETECTED
    assert report.collisions
    assert not report.collision_free_at_discrete_samples
    assert not report.continuous_collision_proof
    document = report.to_dict()
    assert document["continuous_collision_proof"] is False
    assert "Discrete samples" in document["limitations"][0]
    assert document["authority"]["hardware_commands_generated"] == 0


def test_clear_discrete_sweep_is_not_promoted_to_continuous_or_physical_proof() -> None:
    contract = _moving_sphere_contract()
    start = CollisionPose(
        "start", "root", {"moving_frame": _transform("moving_frame", -10.0)}
    )
    end = CollisionPose(
        "end", "root", {"moving_frame": _transform("moving_frame", -6.0)}
    )
    policy = _policy(maximum_surface_step_mm=1.0)
    report = evaluate_collision_sweep(
        contract,
        start,
        end,
        policy,
    )

    assert report.status is CollisionEvaluationStatus.CLEAR_AT_DISCRETE_SWEEP_SAMPLES
    assert report.collision_free_at_discrete_samples
    assert report.evaluation_complete
    assert not report.continuous_collision_proof
    assert len(report.samples) == report.planned_sample_count
    bindings = report.to_dict()["input_bindings"]
    assert bindings["contract"]["sha256"] == contract.content_hash
    assert bindings["start_pose"]["sha256"] == start.content_hash
    assert bindings["end_pose"]["sha256"] == end.content_hash
    assert bindings["policy"]["sha256"] == policy.content_hash
    assert len(report.report_hash) == 64


def test_sweep_sample_cap_is_enforced_before_sampling() -> None:
    contract = _moving_sphere_contract()
    start = CollisionPose(
        "start", "root", {"moving_frame": _transform("moving_frame", -100.0)}
    )
    end = CollisionPose(
        "end", "root", {"moving_frame": _transform("moving_frame", 100.0)}
    )
    with pytest.raises(CollisionResourceLimitError, match="sweep requires"):
        evaluate_collision_sweep(
            contract,
            start,
            end,
            _policy(
                maximum_surface_step_mm=1.0,
                maximum_sweep_samples=10,
            ),
        )


def test_configuration_sampled_body_never_claims_contract_physical_completeness() -> None:
    requirement = CollisionBodyRequirement(
        "cable",
        "root",
        CollisionBodyRole.CABLE,
        CollisionBindingMode.CONFIGURATION_SAMPLED,
    )
    body = CollisionBody(
        "cable",
        "root",
        CollisionBodyRole.CABLE,
        CollisionEvidenceState.ACCEPTED_MEASURED,
        (),
        CollisionBindingMode.CONFIGURATION_SAMPLED,
        "accepted cable identity but configuration-dependent shape",
    )
    contract = CollisionGeometryContract("accepted-cable", "root", (requirement,), (body,))
    audit = audit_collision_geometry(contract)
    unknown_sample = SampledCollisionGeometry(
        (CapsuleMm(Vec3.zero(), Vec3(1.0, 0.0, 0.0), 0.1),),
        CollisionEvidenceState.UNKNOWN,
        "shape awaiting configuration-correlated evidence",
    )
    pose = CollisionPose(
        "sample",
        "root",
        {"root": RigidTransform.identity("root")},
        {"cable": unknown_sample},
    )
    report = evaluate_collision_pose(contract, pose, _policy())

    assert audit.diagnostic_ready
    assert not audit.physical_geometry_complete
    assert audit.configuration_sampled_body_ids == ("cable",)
    assert report.status is CollisionEvaluationStatus.BLOCKED_INCOMPLETE_POSE
    assert report.pose_blockers[0].code is (
        CollisionBlockerCode.CONFIGURATION_GEOMETRY_EVIDENCE_UNUSABLE
    )
    sample_content = report.to_dict()["input_bindings"]["pose"]["content"]
    assert sample_content["configuration_geometry"]["cable"]["evidence_state"] == "UNKNOWN"
    assert (
        sample_content["configuration_geometry"]["cable"]["source_reference"]
        == "shape awaiting configuration-correlated evidence"
    )


def test_configuration_sampled_cable_can_be_checked_at_pose_but_blocks_endpoint_sweep() -> None:
    contract = CollisionGeometryContract(
        "cable-fixture",
        "root",
        (
            CollisionBodyRequirement(
                "cable",
                "root",
                CollisionBodyRole.CABLE,
                CollisionBindingMode.CONFIGURATION_SAMPLED,
            ),
            CollisionBodyRequirement(
                "fixture",
                "root",
                CollisionBodyRole.STATIC_ENVIRONMENT,
                CollisionBindingMode.STATIC_ROOT,
            ),
        ),
        (
            CollisionBody(
                "cable",
                "root",
                CollisionBodyRole.CABLE,
                CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
                (),
                CollisionBindingMode.CONFIGURATION_SAMPLED,
                "unit-test sampled cable",
            ),
            CollisionBody(
                "fixture",
                "root",
                CollisionBodyRole.STATIC_ENVIRONMENT,
                CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
                (OrientedBoxMm(Vec3.zero(), Vec3(1.0, 1.0, 1.0)),),
                CollisionBindingMode.STATIC_ROOT,
                "unit-test fixture",
            ),
        ),
    )
    cable_shape = SampledCollisionGeometry(
        (CapsuleMm(Vec3(-5.0, 0.0, 0.0), Vec3(5.0, 0.0, 0.0), 0.5),),
        CollisionEvidenceState.SYNTHETIC_TEST_ONLY,
        "unit-test cable configuration",
    )
    pose = CollisionPose(
        "cable-pose",
        "root",
        {"root": RigidTransform.identity("root")},
        {"cable": cable_shape},
    )
    pose_report = evaluate_collision_pose(contract, pose, _policy())

    assert pose_report.status is CollisionEvaluationStatus.COLLISION_DETECTED
    sweep_report = evaluate_collision_sweep(contract, pose, pose, _policy())
    assert sweep_report.status is CollisionEvaluationStatus.BLOCKED_DEFORMABLE_SWEEP
    assert not sweep_report.evaluation_complete
    assert sweep_report.blockers[0].code is (
        CollisionBlockerCode.DEFORMABLE_SWEEP_INTERMEDIATE_GEOMETRY_UNAVAILABLE
    )
