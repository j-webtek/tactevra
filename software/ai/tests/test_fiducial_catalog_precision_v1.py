from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from rocell.geometry import RigidTransform, Rotation3, Vec3
from rocell.targets.nominal import load_nominal_target_catalog
from rocell.vision import (
    AprilTagDetection,
    AprilTagDetectionBatch,
    AprilTagPoseObservation,
    DetectorIdentity,
    FrameCaptureBinding,
    PixelCorner,
    PoseCovariance6,
    PoseEstimatorIdentity,
    TagFitDiagnostic,
    TagReference,
    TimestampQuality,
)
from rocell_ai.fiducial_catalog_precision_v1 import (
    adapt_fiducial_catalog_precision_v1,
    build_qualification,
    validate_observation,
    validate_qualification,
)


ROOT = Path(__file__).resolve().parents[3]
H = {character: character * 64 for character in "123456789abcdef"}


def _observation(*, rmse: float = 0.25, settings: str = H["a"]) -> AprilTagPoseObservation:
    frame = FrameCaptureBinding(
        capture_id="capture-0001",
        jpeg_sha256=H["1"],
        width_px=320,
        height_px=240,
        source_sequence=17,
        source_timestamp_ns=1_001,
        source_clock="camera-monotonic",
        host_request_ns=990,
        host_first_byte_ns=1_010,
        host_complete_ns=1_020,
        host_clock="host-monotonic",
        settings_sha256=settings,
        timestamp_quality=TimestampQuality.DEVICE_EXPOSURE,
        freshness_token="sequence:17",
        freshness_basis="device_sequence",
    )
    tag = TagReference("tag36h11", 2)
    detection = AprilTagDetection(
        tag=tag,
        corners_px=(
            PixelCorner(30.0, 20.0),
            PixelCorner(50.0, 20.0),
            PixelCorner(50.0, 40.0),
            PixelCorner(30.0, 40.0),
        ),
        decision_margin=75.5,
        hamming=0,
    )
    batch = AprilTagDetectionBatch(
        frame=frame,
        detector=DetectorIdentity(
            detector_id="apriltag.reference",
            version="1.2.3",
            configuration_sha256=H["2"],
            implementation_sha256=H["3"],
        ),
        detections=(detection,),
    )
    return AprilTagPoseObservation(
        detection_batch=batch,
        estimator=PoseEstimatorIdentity(
            estimator_id="pnp.reference",
            version="2.0.0",
            configuration_sha256=H["4"],
            implementation_sha256=H["5"],
        ),
        camera_intrinsics_sha256=H["6"],
        tag_map_sha256=H["7"],
        pose=RigidTransform(
            parent_frame="camera_optical",
            child_frame="board",
            rotation=Rotation3.identity(),
            translation_mm=Vec3(10.0, 20.0, 800.0),
        ),
        covariance=PoseCovariance6.diagonal(
            (0.04, 0.04, 0.09, 0.0001, 0.0001, 0.0002)
        ),
        fit_diagnostics=(
            TagFitDiagnostic(
                tag=tag,
                inlier=True,
                reprojection_residual_px=rmse,
                rejection_reason=None,
            ),
        ),
    )


def _qualification(observation: AprilTagPoseObservation, catalog, **updates):
    fields = {
        "domain_id": "B0477_RC03_TEST",
        "device": "keyboard",
        "detector_configuration_sha256": H["2"],
        "detector_implementation_sha256": H["3"],
        "estimator_configuration_sha256": H["4"],
        "estimator_implementation_sha256": H["5"],
        "camera_intrinsics_sha256": H["6"],
        "camera_settings_sha256": H["a"],
        "tag_map_sha256": H["7"],
        "target_catalog_sha256": catalog.content_sha256,
        "board_frame_definition_sha256": H["8"],
        "camera_frame": "camera_optical",
        "board_frame": "board",
        "calibration_dataset_sha256": H["9"],
        "evaluation_dataset_sha256": H["b"],
        "coverage_probability": 0.99,
        "conservative_planar_error_bound_mm": 0.8,
        "minimum_inlier_tags": 1,
        "maximum_inlier_rmse_px": 0.5,
        "covered_target_ids": ["H", "I"],
    }
    fields.update(updates)
    return build_qualification(**fields)


def _adapt(observation, catalog, qualification, **updates):
    arguments = {
        "device": "keyboard",
        "required_target_ids": ("H", "I"),
        "domain_id": "B0477_RC03_TEST",
        "board_frame_definition_sha256": H["8"],
        "trusted_qualifications": (
            {} if qualification is None else {qualification["qualification_sha256"]: qualification}
        ),
        "qualification_sha256": (
            None if qualification is None else qualification["qualification_sha256"]
        ),
        "current_host_ns": 1_100,
        "maximum_age_ns": 1_000,
    }
    arguments.update(updates)
    return adapt_fiducial_catalog_precision_v1(observation, catalog, **arguments)


def test_exact_pose_and_catalog_qualification_is_admitted_with_zero_authority() -> None:
    catalog = load_nominal_target_catalog(ROOT)
    observation = _observation()
    qualification = _qualification(observation, catalog)
    result = _adapt(observation, catalog, qualification)

    assert result["abstain"] is False
    assert result["abstain_reasons"] == []
    assert result["required_target_ids"] == ["H", "I"]
    assert [row["target_id"] for row in result["targets"]] == ["H", "I"]
    assert result["source_hashes"]["target_catalog_sha256"] == catalog.content_sha256
    assert result["authority"] == {
        "physical_authority": "NONE",
        "physical_commands_generated": 0,
        "can_authorize_motion": False,
        "can_release_physical_gates": False,
    }
    assert len(result["observation_sha256"]) == 64


def test_missing_qualification_abstains_as_localization_uncalibrated() -> None:
    catalog = load_nominal_target_catalog(ROOT)
    result = _adapt(_observation(), catalog, None)
    assert result["abstain"] is True
    assert result["abstain_reasons"] == ["localization_uncalibrated"]
    assert result["qualification_sha256"] is None


@pytest.mark.parametrize(
    ("qualification_update", "adapter_update", "reason"),
    [
        ({"domain_id": "OTHER"}, {}, "wrong_domain"),
        ({"camera_intrinsics_sha256": H["c"]}, {}, "wrong_camera_intrinsics"),
        ({"camera_settings_sha256": H["c"]}, {}, "wrong_camera_settings"),
        ({"tag_map_sha256": H["c"]}, {}, "wrong_tag_map"),
        ({"target_catalog_sha256": H["c"]}, {}, "wrong_target_catalog"),
        ({"board_frame_definition_sha256": H["c"]}, {}, "wrong_board_frame"),
        ({"covered_target_ids": ["H"]}, {}, "uncovered_target"),
        ({"minimum_inlier_tags": 2}, {}, "insufficient_inlier_tags"),
        ({}, {"current_host_ns": 3_000}, "stale_evidence"),
    ],
)
def test_applicability_mismatch_abstains(qualification_update, adapter_update, reason) -> None:
    catalog = load_nominal_target_catalog(ROOT)
    observation = _observation()
    qualification = _qualification(observation, catalog, **qualification_update)
    result = _adapt(observation, catalog, qualification, **adapter_update)
    assert result["abstain"] is True
    assert reason in result["abstain_reasons"]


def test_high_reprojection_residual_abstains() -> None:
    catalog = load_nominal_target_catalog(ROOT)
    observation = _observation(rmse=0.75)
    qualification = _qualification(observation, catalog)
    result = _adapt(observation, catalog, qualification)
    assert result["abstain_reasons"] == ["reprojection_residual_exceeded"]


def test_qualification_hash_tampering_is_rejected() -> None:
    catalog = load_nominal_target_catalog(ROOT)
    qualification = _qualification(_observation(), catalog)
    qualification["coverage_probability"] = 0.98
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_qualification(qualification)


def test_observation_tampering_is_rejected() -> None:
    catalog = load_nominal_target_catalog(ROOT)
    observation = _observation()
    qualification = _qualification(observation, catalog)
    result = _adapt(observation, catalog, qualification)
    result["targets"][0]["center_board_mm"][0] += 1.0
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_observation(result)


def test_nominal_catalog_scope_cannot_be_relabelled_physical() -> None:
    catalog = load_nominal_target_catalog(ROOT)
    qualification = _qualification(_observation(), catalog)
    qualification["scope"] = "PHYSICAL_DEPLOYMENT"
    with pytest.raises(ValueError, match="synthetic offline"):
        validate_qualification(qualification)
