from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import sys

import pytest
import jsonschema

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/tests/unit"))

import test_model_motion_ingress_v2 as ingress_fixture  # noqa: E402
import test_typing_trajectory_ik_screen_v1 as ik_fixture  # noqa: E402
from rocell.application.model_motion_ingress_v2 import MeasuredTargetRegionV2  # noqa: E402
from rocell.application.context import SimulationContextError  # noqa: E402
from rocell.application.context_lifecycle_v1 import SimulationContextLifecycleV1  # noqa: E402
from rocell.application.pre_camera_typing_qualification_basis_v1 import (  # noqa: E402
    load_pre_camera_typing_qualification_basis_v1,
)
from rocell.application.typing_execution_plan_v1 import TypingExecutionConfigV1  # noqa: E402
from rocell.application.typing_joint_schedule_v1 import (  # noqa: E402
    dynamics_profile_from_pc0_basis_v1,
)
from rocell.application.typing_shadow_pipeline_v1 import (  # noqa: E402
    STATUS,
    TypingShadowPipelineV1Error,
    parse_typing_shadow_pipeline_v1,
    run_typing_shadow_pipeline_v1,
)
from rocell.application.typing_planner_preparation_v1 import (  # noqa: E402
    prepare_typing_planner_v1,
)
from rocell.application.typing_ik_effort_telemetry_v1 import (  # noqa: E402
    TypingIkEffortRecorderV1,
    TypingIkEffortTelemetryV1Error,
    parse_typing_ik_effort_telemetry_v1,
)
from rocell.application.typing_exact_ik_result_cache_v1 import (  # noqa: E402
    ExactTypingIkResultCacheV1,
    TypingExactIkResultCacheV1Error,
    parse_typing_exact_ik_result_cache_snapshot_v1,
)
from rocell.application.typing_trajectory_ik_screen_v1 import (  # noqa: E402
    TypingTrajectoryIkScreenV1Error,
)
from rocell.application.typing_trajectory_plan_v1 import TypingTrajectoryPolicyV1  # noqa: E402
from rocell.models import (  # noqa: E402
    ActionPlan,
    Device,
    ModelMotionBatchV2,
    Point3Mm,
    PressKey,
    SpeedClass,
)


def _inputs(
    targets: tuple[str, ...] = ("H", "I"), text: str = "hi", *, context=None,
):
    if context is None:
        context = ingress_fixture.load_simulation_context(
            ingress_fixture.WORKSPACE, ingress_fixture.MANIFEST
        )
    snapshot = ik_fixture._snapshot(context)
    solved_tip = ik_fixture._ready_tip(context, snapshot)
    # This retained-evidence fixture needs one canonical input point across
    # supported Python/libm builds; the solver itself is tested separately.
    tip = Point3Mm(
        solved_tip.frame,
        round(solved_tip.x, 6),
        round(solved_tip.y, 6),
        round(solved_tip.z, 6),
    )
    plan = ActionPlan.from_text(
        device=Device.KEYBOARD,
        profile_id="keyboard-development-v1",
        text=text,
        actions=tuple(PressKey(target) for target in targets),
        required_calibrations=("keyboard_pose", "keyboard_tcp"),
    )
    unique_targets = tuple(dict.fromkeys(targets))
    contacts = {
        target_id: Point3Mm(
            "board", tip.x + 0.2 * index, tip.y, tip.z - 5.0
        )
        for index, target_id in enumerate(unique_targets)
    }
    base = ingress_fixture._batch(context, plan=plan)
    batch = ModelMotionBatchV2(
        batch_id=base.batch_id,
        request_id=base.request_id,
        intent_plan_sha256=base.intent_plan_sha256,
        device=base.device,
        capability=base.capability,
        geometry=base.geometry,
        evidence=base.evidence,
        uncertainty=replace(base.uncertainty, covered_target_ids=unique_targets),
        proposals=tuple(
            ingress_fixture._proposal(
                context, target_id, index, target=contacts[target_id]
            )
            for index, target_id in enumerate(targets)
        ),
    )
    regions = tuple(
        MeasuredTargetRegionV2(
            target_id=target_id,
            coordinate_frame="board",
            coordinate_profile="board_mm_xy_plane_v2",
            board_frame_definition_sha256=ingress_fixture.H["d"],
            vertices_xy_mm=(
                (point.x - 5.0, point.y - 5.0),
                (point.x + 5.0, point.y - 5.0),
                (point.x + 5.0, point.y + 5.0),
                (point.x - 5.0, point.y + 5.0),
            ),
            surface_z_mm=point.z,
            surface_normal_error_bound_mm=0.1,
            placement_error_bound_mm=0.25,
            placement_observation_sha256=ingress_fixture.H["e"],
            target_catalog_sha256=context.targets.content_sha256,
        )
        for target_id, point in contacts.items()
    )
    registry = ingress_fixture._registry(
        context,
        qualification=ingress_fixture._qualification(
            context, target_ids=unique_targets
        ),
        target_regions=regions,
    )
    execution_config = TypingExecutionConfigV1(
        config_id="pc2-golden-hi-offline",
        calibration_snapshot_sha256=snapshot.snapshot_sha256,
        tool_profile_sha256="0" * 64,
        dynamics_profile_sha256="1" * 64,
        route_reference_point=Point3Mm("board", tip.x, tip.y, tip.z),
        hover_clearance_mm=5.0,
        settle_position_tolerance_mm=0.5,
        settle_velocity_tolerance_mm_s=1.0,
        settle_hold_ms=100,
        preview_horizon=1,
        speed_class=SpeedClass.SLOW,
    )
    basis = load_pre_camera_typing_qualification_basis_v1(ROOT)
    return {
        "payload": json.dumps(
            batch.to_dict(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8"),
        "intent_plan": plan,
        "context": context,
        "registry": registry,
        "current_time_epoch_ms": ingress_fixture.T0 + 3_000,
        "ingress_monotonic_ns": 9_000_000_000,
        "preplanner_monotonic_ns": 10_000_000_000,
        "execution_config": execution_config,
        "trajectory_policy": TypingTrajectoryPolicyV1(
            policy_id="pc2-golden-quintic",
            maximum_cartesian_step_mm=1.0,
            maximum_velocity_mm_s=40.0,
            maximum_acceleration_mm_s2=80.0,
            maximum_jerk_mm_s3=400.0,
            hover_settle_ms=100,
            contact_dwell_ms=60,
        ),
        "calibration_snapshot": snapshot,
        "ik_seed": ik_fixture._seed(context, snapshot),
        "joint_dynamics_profile": dynamics_profile_from_pc0_basis_v1(basis),
    }


def test_real_boundaries_produce_one_deterministic_honest_blocker_receipt():
    inputs = _inputs()
    first = run_typing_shadow_pipeline_v1(**inputs)
    second = run_typing_shadow_pipeline_v1(**inputs)

    assert first == second
    assert first["status"] == STATUS
    assert first["ordered_target_ids"] == ["H", "I"]
    assert first["terminal_stage"] == "COLLISION_EVIDENCE_INTAKE"
    assert first["terminal_stage_status"] == (
        "BLOCKED_INSTALLED_COLLISION_PROFILE_REQUIRED"
    )
    assert "INSTALLED_COLLISION_PROFILE_REQUIRED" in first["terminal_blockers"]
    assert len(first["stage_hashes"]) == 9
    assert first["controller_commands"] == []
    assert first["hardware_commands_generated"] == 0
    assert first["hardware_access"] is first["physical_authority"] is False
    schema = json.loads(
        (ROOT / "software/ai/schemas/typing_shadow_pipeline_v1.schema.json")
        .read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(first)
    parsed = parse_typing_shadow_pipeline_v1(first)
    assert tuple(parsed["ordered_target_ids"]) == ("H", "I")


def test_epoch_prepared_pipeline_is_exactly_equivalent_to_full_source_path():
    lifecycle = SimulationContextLifecycleV1.start(
        ingress_fixture.WORKSPACE,
        ingress_fixture.MANIFEST,
        service_instance_id="typing-shadow-e1-integration",
        issued_monotonic_ns=100,
    )
    context = lifecycle.binding().context
    inputs = _inputs(context=context)
    reference = run_typing_shadow_pipeline_v1(**inputs)
    prepared = prepare_typing_planner_v1(context, lifecycle)
    recorder = TypingIkEffortRecorderV1()
    optimized = run_typing_shadow_pipeline_v1(
        **inputs,
        context_lifecycle=lifecycle,
        prepared_planner=prepared,
        ik_effort_recorder=recorder,
    )
    assert optimized == reference
    assert optimized["hardware_access"] is optimized["physical_authority"] is False
    effort = recorder.build(
        typing_trajectory_plan_sha256=optimized["stage_hashes"][
            "typing_trajectory_plan_sha256"
        ],
        typing_trajectory_ik_screen_sha256=optimized["stage_hashes"][
            "typing_trajectory_ik_screen_sha256"
        ],
    )
    assert effort["sample_count"] > 0
    assert effort["decision_input"] is False


def test_ik_effort_side_channel_preserves_every_canonical_decision_hash():
    inputs = _inputs(("R", "O", "B", "O", "T"), "robot")
    reference = run_typing_shadow_pipeline_v1(**inputs)
    recorder = TypingIkEffortRecorderV1()
    observed = run_typing_shadow_pipeline_v1(
        **inputs,
        ik_effort_recorder=recorder,
    )
    assert observed == reference
    report = recorder.build(
        typing_trajectory_plan_sha256=observed["stage_hashes"][
            "typing_trajectory_plan_sha256"
        ],
        typing_trajectory_ik_screen_sha256=observed["stage_hashes"][
            "typing_trajectory_ik_screen_sha256"
        ],
    )
    assert dict(parse_typing_ik_effort_telemetry_v1(report)) == report
    assert report["sample_count"] > 0
    assert report["totals"]["attempt_count"] >= report["sample_count"]
    assert report["totals"]["total_iterations"] > 0
    assert report["totals"]["previous_solution_seed_supplied_count"] == (
        report["sample_count"] - 1
    )
    assert report["decision_input"] is False
    assert report["controller_commands"] == []
    assert report["hardware_access"] is report["physical_authority"] is False

    changed = json.loads(json.dumps(report))
    changed["totals"]["total_iterations"] += 1
    changed.pop("typing_ik_effort_telemetry_sha256")
    import hashlib

    changed["typing_ik_effort_telemetry_sha256"] = hashlib.sha256(
        json.dumps(
            changed, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()
    with pytest.raises(TypingIkEffortTelemetryV1Error, match="totals differ"):
        parse_typing_ik_effort_telemetry_v1(changed)


def test_ik_effort_recorder_is_bounded_and_append_only():
    inputs = _inputs()
    recorder = TypingIkEffortRecorderV1(maximum_samples=1)
    with pytest.raises(TypingIkEffortTelemetryV1Error, match="bound exceeded"):
        run_typing_shadow_pipeline_v1(**inputs, ik_effort_recorder=recorder)


def test_exact_ik_cache_cold_warm_and_disabled_receipts_are_identical():
    lifecycle = SimulationContextLifecycleV1.start(
        ingress_fixture.WORKSPACE,
        ingress_fixture.MANIFEST,
        service_instance_id="typing-exact-cache-integration",
        issued_monotonic_ns=100,
    )
    context = lifecycle.binding().context
    inputs = _inputs(("R", "O", "B", "O", "T"), "robot", context=context)
    reference = run_typing_shadow_pipeline_v1(**inputs)
    prepared = prepare_typing_planner_v1(context, lifecycle)
    cache = ExactTypingIkResultCacheV1.create(
        context, lifecycle, maximum_entries=256
    )
    common = {
        "context_lifecycle": lifecycle,
        "prepared_planner": prepared,
        "exact_ik_result_cache": cache,
    }
    cold = run_typing_shadow_pipeline_v1(**inputs, **common)
    cold_snapshot = cache.snapshot()
    warm = run_typing_shadow_pipeline_v1(**inputs, **common)
    warm_snapshot = cache.snapshot()

    assert cold == warm == reference
    assert dict(
        parse_typing_exact_ik_result_cache_snapshot_v1(warm_snapshot)
    ) == warm_snapshot
    assert cold_snapshot["misses"] > 0
    assert cold_snapshot["stores"] == cold_snapshot["entry_count"]
    assert warm_snapshot["hits"] - cold_snapshot["hits"] == (
        warm_snapshot["lookups"] - cold_snapshot["lookups"]
    )
    assert warm_snapshot["misses"] == cold_snapshot["misses"]
    assert warm_snapshot["decision_input"] is False
    assert warm_snapshot["controller_commands"] == []
    assert warm_snapshot["hardware_access"] is False
    assert warm_snapshot["physical_authority"] is False


def test_exact_ik_cache_capacity_and_invalidation_never_change_receipt():
    lifecycle = SimulationContextLifecycleV1.start(
        ingress_fixture.WORKSPACE,
        ingress_fixture.MANIFEST,
        service_instance_id="typing-exact-cache-bounded",
        issued_monotonic_ns=200,
    )
    context = lifecycle.binding().context
    inputs = _inputs(context=context)
    reference = run_typing_shadow_pipeline_v1(**inputs)
    prepared = prepare_typing_planner_v1(context, lifecycle)
    cache = ExactTypingIkResultCacheV1.create(
        context, lifecycle, maximum_entries=1
    )
    bounded = run_typing_shadow_pipeline_v1(
        **inputs,
        context_lifecycle=lifecycle,
        prepared_planner=prepared,
        exact_ik_result_cache=cache,
    )
    assert bounded == reference
    snapshot = cache.snapshot()
    assert snapshot["entry_count"] == 1
    assert snapshot["capacity_skips"] > 0

    cache.invalidate()
    invalidated = cache.snapshot()
    assert invalidated["active"] is False
    assert invalidated["entry_count"] == 0
    assert dict(
        parse_typing_exact_ik_result_cache_snapshot_v1(invalidated)
    ) == invalidated
    with pytest.raises(TypingExactIkResultCacheV1Error, match="invalidated"):
        run_typing_shadow_pipeline_v1(
            **inputs,
            context_lifecycle=lifecycle,
            prepared_planner=prepared,
            exact_ik_result_cache=cache,
        )


def test_exact_ik_cache_integrity_and_lifecycle_binding_fail_closed():
    lifecycle = SimulationContextLifecycleV1.start(
        ingress_fixture.WORKSPACE,
        ingress_fixture.MANIFEST,
        service_instance_id="typing-exact-cache-integrity",
        issued_monotonic_ns=300,
    )
    context = lifecycle.binding().context
    inputs = _inputs(context=context)
    prepared = prepare_typing_planner_v1(context, lifecycle)
    cache = ExactTypingIkResultCacheV1.create(context, lifecycle)
    common = {
        "context_lifecycle": lifecycle,
        "prepared_planner": prepared,
        "exact_ik_result_cache": cache,
    }
    run_typing_shadow_pipeline_v1(**inputs, **common)

    from dataclasses import replace as dataclass_replace

    key = next(iter(cache._entries))
    cache._entries[key] = dataclass_replace(
        cache._entries[key], result_sha256="f" * 64
    )
    with pytest.raises(TypingExactIkResultCacheV1Error, match="integrity"):
        run_typing_shadow_pipeline_v1(**inputs, **common)

    lifecycle.reload_sources(issued_monotonic_ns=301)
    with pytest.raises(SimulationContextError):
        run_typing_shadow_pipeline_v1(**inputs, **common)


def test_exact_ik_cache_requires_managed_prepared_pipeline():
    inputs = _inputs()
    lifecycle = SimulationContextLifecycleV1.start(
        ingress_fixture.WORKSPACE,
        ingress_fixture.MANIFEST,
        service_instance_id="typing-exact-cache-unmanaged",
        issued_monotonic_ns=400,
    )
    cache = ExactTypingIkResultCacheV1.create(
        lifecycle.binding().context, lifecycle
    )
    with pytest.raises(TypingTrajectoryIkScreenV1Error, match="lifecycle"):
        run_typing_shadow_pipeline_v1(
            **inputs,
            exact_ik_result_cache=cache,
        )


@pytest.mark.parametrize(
    ("targets", "text"),
    (
        (("R", "O", "B", "O", "T"), "robot"),
        (("H", "H", "1", "PERIOD"), "hh1."),
    ),
)
def test_golden_typing_sequences_preserve_order_through_every_real_stage(
    targets: tuple[str, ...], text: str
):
    report = run_typing_shadow_pipeline_v1(**_inputs(targets, text))
    fixture = json.loads(
        (ROOT / "software/tests/fixtures/typing_shadow_pipeline_v1_golden.json")
        .read_text(encoding="utf-8")
    )
    fixture_key = "type_robot" if text == "robot" else "repeat_punctuation"

    assert report == fixture[fixture_key]
    assert report["ordered_target_ids"] == list(targets)
    assert report["action_count"] == len(targets)
    assert report["terminal_stage"] == "COLLISION_EVIDENCE_INTAKE"
    assert report["hardware_commands_generated"] == 0


def test_payload_mutation_fails_at_strict_decoder_before_any_stage_receipt():
    inputs = _inputs()
    payload = bytearray(inputs["payload"])
    payload[-2] = ord("x")
    inputs["payload"] = bytes(payload)

    with pytest.raises(ValueError):
        run_typing_shadow_pipeline_v1(**inputs)


def _rehash_receipt(document: dict[str, object]) -> None:
    import hashlib

    document.pop("typing_shadow_pipeline_sha256", None)
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    document["typing_shadow_pipeline_sha256"] = hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("profile_hash", "stage hashes"),
        ("timestamp_lineage", "terminal blocker"),
        ("action_count", "ordered targets"),
        ("authority", "zero authority"),
        ("extra", "fields differ"),
    ),
)
def test_rehashed_receipt_mutations_still_fail_the_owning_rule(
    mutation: str, message: str
):
    receipt = run_typing_shadow_pipeline_v1(**_inputs())
    changed = json.loads(json.dumps(receipt))
    if mutation == "profile_hash":
        changed["stage_hashes"] = dict(reversed(changed["stage_hashes"].items()))
    elif mutation == "timestamp_lineage":
        changed["terminal_blockers"] = list(reversed(changed["terminal_blockers"]))
    elif mutation == "action_count":
        changed["action_count"] += 1
    elif mutation == "authority":
        changed["hardware_access"] = True
    else:
        changed["unexpected"] = True
    _rehash_receipt(changed)

    with pytest.raises(TypingShadowPipelineV1Error, match=message):
        parse_typing_shadow_pipeline_v1(changed)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("duplicate_json", "duplicate JSON"),
        ("batch_hash", "batch_sha256"),
        ("intent", "differs from the semantic plan"),
        ("stale_capture", "future-dated or expired"),
        ("expired_preplanner", "expired before planning"),
        ("calibration", "identities differ"),
        ("seed", "identities differ"),
        ("dynamics", "exceeds the profile"),
    ),
)
def test_single_field_stage_mutations_fail_at_the_earliest_owner(
    mutation: str, message: str
):
    inputs = _inputs()
    if mutation == "duplicate_json":
        inputs["payload"] = inputs["payload"].replace(
            b'"batch_id":', b'"batch_id":"duplicate","batch_id":', 1
        )
    elif mutation == "batch_hash":
        payload = json.loads(inputs["payload"])
        payload["request_id"] = "mutated"
        inputs["payload"] = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    elif mutation == "intent":
        inputs["intent_plan"] = ActionPlan.from_text(
            device=Device.KEYBOARD,
            profile_id="keyboard-development-v1",
            text="different",
            actions=(PressKey("H"), PressKey("I")),
            required_calibrations=("keyboard_pose", "keyboard_tcp"),
        )
    elif mutation == "stale_capture":
        inputs["current_time_epoch_ms"] = ingress_fixture.T0 + 10_000
    elif mutation == "expired_preplanner":
        inputs["preplanner_monotonic_ns"] = 16_000_000_000
    elif mutation == "calibration":
        inputs["execution_config"] = replace(
            inputs["execution_config"], calibration_snapshot_sha256="f" * 64
        )
    elif mutation == "seed":
        inputs["ik_seed"] = replace(
            inputs["ik_seed"], build_snapshot_sha256="f" * 64
        )
    else:
        profile = inputs["joint_dynamics_profile"]
        inputs["joint_dynamics_profile"] = replace(
            profile,
            maximum_velocity_rad_s={name: 1e-6 for name in profile.maximum_velocity_rad_s},
            maximum_acceleration_rad_s2={
                name: 1e-6 for name in profile.maximum_acceleration_rad_s2
            },
            maximum_jerk_rad_s3={name: 1e-6 for name in profile.maximum_jerk_rad_s3},
            maximum_time_scale_factor=1.0,
        )

    with pytest.raises(ValueError, match=message):
        run_typing_shadow_pipeline_v1(**inputs)
