from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(ROOT / "software/ai"),
    str(ROOT / "software/src"),
    str(ROOT / "software/tests/unit"),
    str(ROOT / "software/tests/integration"),
    str(ROOT / "software/ai/tests"),
]

import test_model_motion_ingress_v2 as arm  # noqa: E402
import test_precision_adapter_v2 as precision  # noqa: E402
import test_model_motion_v2_shared_gate as shared  # noqa: E402
from rocell.application import (  # noqa: E402
    ArmMotionPolicyV2,
    MeasuredTargetRegionV2,
    TrustedLocalizationQualificationV2,
)
from rocell.models import UncertaintyBoundType  # noqa: E402
from rocell_ai.precision_adapter_v2 import (  # noqa: E402
    InstalledSyntheticQualificationV0,
    adapt_pose_model_output,
)
from rocell_ai.precision_batch_producer_v2 import (  # noqa: E402
    PlacedTargetRegionMapV2,
)
from rocell_ai.scene_observation import canonical_hash  # noqa: E402
from rocell_ai.selected_intent_precision_shadow_v1 import (  # noqa: E402
    SelectedPrecisionShadowInputsV1,
    run_selected_intent_precision_shadow_v1,
)


DIGEST = "a" * 64
SCHEMA_PATH = ROOT / "software/ai/schemas/offline_intent_classification_v1.schema.json"
SCHEMA_DIGEST = hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()


def _classification() -> str:
    return json.dumps(
        {
            "schema": "rocell.offline_intent_classification.v1",
            "intent_type": "TYPE_TEXT",
            "device": "KEYBOARD",
        },
        separators=(",", ":"),
    )


def _accepted_result(*, confidence: float = 0.99, evaluated: int = precision.NOW):
    context = arm.load_simulation_context(arm.WORKSPACE, arm.MANIFEST)
    output = replace(
        precision._output(confidence=confidence, evaluated=evaluated),
        normalized_pose=(0.25, 0.1875, -math.pi / 0.2),
    )
    core = {
        "schema": "rocell.ai_localization_qualification.v0",
        "scope": "SYNTHETIC_OFFLINE_ONLY",
        "model_sha256": output.model_sha256,
        "target_catalog_sha256": context.targets.content_sha256,
        "calibration_dataset_sha256": precision.H["c"],
        "evaluation_dataset_sha256": precision.H["d"],
        "domain_id": precision.DOMAIN,
        "coverage_probability": 0.99,
        "error_bound_mm": 1.0,
        "target_ids": ["H", "I"],
    }
    qualification = {**core, "qualification_sha256": canonical_hash(core)}
    installed = InstalledSyntheticQualificationV0(qualification, precision.H["e"])
    result = adapt_pose_model_output(
        ROOT,
        output,
        domain_id=precision.DOMAIN,
        required_target_ids=("H", "H", "I"),
        trusted_qualifications={qualification["qualification_sha256"]: installed},
        expected_domain_id=precision.DOMAIN,
        now_epoch_ms=precision.NOW,
    )
    return context, result, qualification


def _inputs(*, result=None, qualification=None, crossing: bool = False):
    context, accepted, accepted_qualification = _accepted_result()
    result = result or accepted
    qualification = qualification or accepted_qualification
    fixture = arm._batch(context)
    prediction = result.precision_observation["prediction"]
    placement_sha256 = precision.H["f"]
    regions = {}
    measured = []
    for target_id in ("H", "I"):
        x, y, z = prediction["targets"][target_id]["center_board_mm"]
        half = 0.5 if crossing and target_id == "H" else 2.0
        rectangle = (x - half, y - half, x + half, y + half)
        regions[target_id] = rectangle
        left, front, right, rear = rectangle
        measured.append(MeasuredTargetRegionV2(
            target_id=target_id,
            coordinate_frame="board",
            coordinate_profile="board_mm_xy_plane_v2",
            board_frame_definition_sha256=fixture.geometry.board_frame_definition_sha256,
            vertices_xy_mm=((left, front), (right, front), (right, rear), (left, rear)),
            surface_z_mm=z,
            surface_normal_error_bound_mm=0.0,
            placement_error_bound_mm=0.0,
            placement_observation_sha256=placement_sha256,
            target_catalog_sha256=context.targets.content_sha256,
        ))
    placed = PlacedTargetRegionMapV2(
        context.targets.content_sha256,
        placement_sha256,
        regions,
    )
    geometry = replace(
        fixture.geometry,
        placement_observation_sha256=placement_sha256,
        target_catalog_sha256=context.targets.content_sha256,
    )
    evidence = replace(
        fixture.evidence,
        frame_id=prediction["frame_id"],
        image_sha256=prediction["image_sha256"],
        model_id=result.model_output.model_id,
        model_sha256=prediction["model_sha256"],
        precision_observation_sha256=result.precision_observation["observation_sha256"],
        captured_at_epoch_ms=precision.NOW - 100,
        evaluated_at_epoch_ms=result.model_output.evaluated_at_epoch_ms,
        expires_at_epoch_ms=precision.NOW + 5_000,
    )
    trusted = TrustedLocalizationQualificationV2(
        qualification_sha256=qualification["qualification_sha256"],
        model_id=result.model_output.model_id,
        model_sha256=qualification["model_sha256"],
        evidence_method_sha256=precision.H["e"],
        domain_id=qualification["domain_id"],
        target_catalog_sha256=qualification["target_catalog_sha256"],
        bound_type=UncertaintyBoundType.PLANAR_L2_DISK,
        error_bound_mm=qualification["error_bound_mm"],
        coverage_probability=qualification["coverage_probability"],
        target_ids=tuple(qualification["target_ids"]),
    )
    registry = replace(
        arm._registry(context),
        frame_id=evidence.frame_id,
        image_sha256=evidence.image_sha256,
        scene_lease_expires_at_epoch_ms=precision.NOW + 6_000,
        precision_observation_sha256=evidence.precision_observation_sha256,
        placement_observation_sha256=placement_sha256,
        target_catalog_sha256=context.targets.content_sha256,
        qualification=trusted,
        target_regions=tuple(measured),
    )
    return context, SelectedPrecisionShadowInputsV1(
        batch_id="selected-precision-shadow-v1",
        capability=fixture.capability,
        geometry=geometry,
        evidence=evidence,
        adapter_result=result,
        placed_targets=placed,
        registry=registry,
        policy=ArmMotionPolicyV2(
            "keyboard-contact-conservative-v1", 25.0, arm.SpeedClass.SLOW
        ),
        observed_start_state=shared._fresh_observed_state(context),
        current_time_epoch_ms=precision.NOW,
        ingress_monotonic_ns=9_000_000_000,
        preplanner_monotonic_ns=10_000_000_000,
        planner_monotonic_ns=10_500_000_000,
    )


def _run(inputs):
    context, _ = _inputs()
    return run_selected_intent_precision_shadow_v1(
        request_id="selected-precision-real-001",
        request_text='Type "hhi" on the keyboard.',
        observation={"fresh": True, "ref": "synthetic-precision-scene"},
        model="fixture-classifier:latest",
        expected_model_digest=DIGEST,
        decoder_schema_sha256=SCHEMA_DIGEST,
        generate=lambda _payload: _classification(),
        resolve_model_digest=lambda _model: DIGEST,
        context=context,
        inputs=inputs,
    )


def test_selected_intent_and_precision_reach_arm_shadow_without_authority() -> None:
    _, inputs = _inputs()
    result = _run(inputs)

    assert result["status"] == "BLOCKED_CALIBRATION_MISSING_OR_STALE"
    assert result["ordered_target_ids"] == ["H", "H", "I"]
    assert result["precision_observation_sha256"] is not None
    assert result["qualification_sha256"] is not None
    assert result["model_motion_batch_count"] == 1
    assert result["controller_command_count"] == 0
    assert result["hardware_write_count"] == 0
    assert result["physical_movement_count"] == 0
    assert result["physical_authority"] is False


def test_missing_precision_inputs_stop_before_plan_or_batch() -> None:
    result = _run(None)
    assert result["status"] == "QUALIFIED_PERCEPTION_REQUIRED"
    assert result["model_motion_batch_count"] == 0


def test_unqualified_or_low_confidence_precision_abstains_before_ingress() -> None:
    context, _, _ = _accepted_result()
    output = precision._output(confidence=0.2)
    rejected = adapt_pose_model_output(
        ROOT,
        output,
        domain_id=precision.DOMAIN,
        required_target_ids=("H", "H", "I"),
        trusted_qualifications={},
        expected_domain_id=precision.DOMAIN,
        now_epoch_ms=precision.NOW,
    )
    _, inputs = _inputs(result=rejected)
    result = _run(inputs)
    assert context.targets.content_sha256 == inputs.geometry.target_catalog_sha256
    assert result["status"] == "PERCEPTION_ABSTAINED"
    assert result["model_motion_batch_count"] == 0


def test_uncertainty_crossing_target_region_abstains_before_ingress() -> None:
    _, inputs = _inputs(crossing=True)
    result = _run(inputs)
    assert result["status"] == "PERCEPTION_ABSTAINED"
    assert result["model_motion_batch_count"] == 0
