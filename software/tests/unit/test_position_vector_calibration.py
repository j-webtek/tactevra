import copy
import math

import pytest

from rocell.arm.position_vector_calibration import (
    JOINT_ORDER,
    PositionVectorCalibrationError,
    convert_position_vector_feedback,
    describe_uncalibrated_position_vector,
    load_position_vector_calibration,
)


STEP = 2 * math.pi / 4096
MESSAGE = {
    "T": 1051,
    "p": [2050, 2147, 1958, 2550, 2227, 2041, 2042],
    "pose": "KEYBOARD_FORWARD_CAL_1",
    "motion_active": False,
    "trajectory_progress_permille": 1000,
}
CONTROLLER = {
    "vid": "10c4",
    "pid": "ea60",
    "unit_serial": "52E4E1E8337FEF119E92181CEDD322A4",
    "firmware_sha256": "a" * 64,
}


def artifact():
    definitions = [
        ("base", 0, 2048.0, -STEP, -math.pi, math.pi),
        ("shoulder", 1, 2048.0, STEP, -math.pi / 2, math.pi / 2),
        ("elbow", 3, 1024.0, STEP, 0.0, 2.95),
        ("wrist_pitch", 4, 2048.0, STEP, -math.pi / 2, math.pi / 2),
        ("wrist_roll", 5, 2048.0, -STEP, -math.pi, math.pi),
        ("gripper", 6, 2048.0, -STEP, 0.0, 1.5),
    ]
    return {
        "schema": "rocell.position_vector_calibration.v1",
        "calibration_id": "synthetic-reviewed-calibration",
        "response_profile": "POSITION_VECTOR_NAMED_POSE",
        "controller_binding": dict(CONTROLLER),
        "position_order_servo_ids": list(range(11, 18)),
        "joint_order": list(JOINT_ORDER),
        "joints": [
            {
                "joint": joint,
                "primary_index": index,
                "count_zero": zero,
                "radians_per_count": scale,
                "minimum_rad": minimum,
                "maximum_rad": maximum,
                "training_sample_count": 12,
                "held_out_sample_count": 4,
                "held_out_max_abs_error_rad": 0.01,
                "accepted_max_abs_error_rad": 0.02,
            }
            for joint, index, zero, scale, minimum, maximum in definitions
        ],
        "shoulder_pair": {
            "driving_index": 1,
            "driven_index": 2,
            "nominal_sum_counts": 4105,
            "runtime_tolerance_counts": 16,
            "training_max_abs_residual_counts": 11,
            "held_out_max_abs_residual_counts": 12,
        },
        "evidence": {
            "dataset_sha256": "b" * 64,
            "fit_report_sha256": "c" * 64,
            "independent_review_sha256": "d" * 64,
        },
    }


def test_current_observation_retains_semantics_without_promoting_counts():
    report = describe_uncalibrated_position_vector(MESSAGE)
    assert report["status"] == "CALIBRATION_REQUIRED"
    assert report["position_order_servo_ids"] == list(range(11, 18))
    assert report["raw_position_counts"] == MESSAGE["p"]
    assert not report["accepted_as_calibrated_joint_state"]
    assert not report["motion_authorized"] and not report["physical_authority"]


def test_reviewed_artifact_converts_all_six_canonical_joints():
    result = convert_position_vector_feedback(MESSAGE, artifact(), CONTROLLER)
    joints = result["canonical_joints_rad"]
    assert list(joints) == list(JOINT_ORDER)
    assert joints["base"] == pytest.approx(-2 * STEP)
    assert joints["shoulder"] == pytest.approx(99 * STEP)
    assert joints["elbow"] == pytest.approx(1526 * STEP)
    assert joints["wrist_pitch"] == pytest.approx(179 * STEP)
    assert joints["wrist_roll"] == pytest.approx(7 * STEP)
    assert joints["gripper"] == pytest.approx(6 * STEP)
    assert result["shoulder_pair_residual_counts"] == 0
    assert result["accepted_as_calibrated_joint_state"]
    assert not result["motion_authorized"] and not result["physical_authority"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(position_order_servo_ids=[11, 12, 14, 13, 15, 16, 17]),
        lambda value: value["joints"][1].update(primary_index=2),
        lambda value: value["joints"][0].update(training_sample_count=1),
        lambda value: value["joints"][0].update(held_out_sample_count=0),
        lambda value: value["joints"][0].update(held_out_max_abs_error_rad=0.03),
        lambda value: value["shoulder_pair"].update(held_out_max_abs_residual_counts=17),
        lambda value: value["evidence"].update(fit_report_sha256="b" * 64),
    ],
)
def test_incomplete_or_unvalidated_calibration_is_rejected(mutate):
    candidate = artifact()
    mutate(candidate)
    with pytest.raises(PositionVectorCalibrationError):
        load_position_vector_calibration(candidate)


def test_controller_identity_and_firmware_are_exactly_bound():
    changed = dict(CONTROLLER, firmware_sha256="e" * 64)
    with pytest.raises(PositionVectorCalibrationError, match="controller binding"):
        convert_position_vector_feedback(MESSAGE, artifact(), changed)


def test_runtime_shoulder_disagreement_fails_closed():
    message = copy.deepcopy(MESSAGE)
    message["p"][2] += 17
    with pytest.raises(PositionVectorCalibrationError, match="mirrored-shoulder"):
        convert_position_vector_feedback(message, artifact(), CONTROLLER)


def test_joint_value_outside_validated_range_fails_closed():
    candidate = artifact()
    candidate["joints"][0].update(minimum_rad=-0.001, maximum_rad=0.001)
    with pytest.raises(PositionVectorCalibrationError, match="outside its validated range"):
        convert_position_vector_feedback(MESSAGE, candidate, CONTROLLER)


def test_unknown_response_shape_cannot_enter_calibration_boundary():
    message = dict(MESSAGE, extra=True)
    with pytest.raises(PositionVectorCalibrationError, match="exact installed"):
        describe_uncalibrated_position_vector(message)
    with pytest.raises(PositionVectorCalibrationError, match="exact installed"):
        convert_position_vector_feedback(message, artifact(), CONTROLLER)
