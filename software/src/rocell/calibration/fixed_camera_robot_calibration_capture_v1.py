"""Build passive fixed-camera/robot calibration correspondences.

This module accepts already captured camera and T=1051 feedback records.  It
does not open either device and cannot command the robot.  Each capture binds a
six-tag board-pose observation, one calibrated tool-reference observation, and
feedback before and after the frame.  The feedback is checked for stationarity
and reproduced with the pinned firmware kinematics before an unreviewed
board-to-robot correspondence is emitted.

Only the bare-jaw profile can establish the shared board-to-robot transform.
Stylus geometry remains a separate TCP and installed-clearance calibration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from rocell.arm.feedback import FeedbackError, Feedback1051, parse_feedback_line
from rocell.arm.protocol import ProtocolError
from rocell.kinematics.firmware_reference import REFERENCE_SHA256, forward


CAPTURE_INPUT_SCHEMA = "rocell.fixed_camera_robot_calibration_capture_input.v1"
CAPTURE_RESULT_SCHEMA = "rocell.fixed_camera_robot_calibration_capture.v1"
CAMPAIGN_RESULT_SCHEMA = "rocell.fixed_camera_robot_calibration_campaign.v1"
MEASUREMENT_SCHEMA = "rocell.board_to_robot_measurements.v1"
POSE_FIT_TAG_IDS = (0, 1, 2, 3)
HELD_OUT_TAG_IDS = (4, 5)
BOARD_WIDTH_MM = 610.0
BOARD_DEPTH_MM = 457.0
MAX_REPROJECTION_RMS_PX = 2.0
MAX_TOOL_REFERENCE_UNCERTAINTY_MM = 3.0
MAX_BRACKET_NS = 1_000_000_000
MAX_JOINT_SPAN_RAD = 0.01
MAX_ENDPOINT_SPAN_MM = 2.0
MAX_REPORTED_FK_ERROR_MM = 5.0
MAX_CAPTURE_FILE_BYTES = 1024 * 1024


class FixedCameraRobotCalibrationCaptureError(ValueError):
    """A passive capture or campaign is inconsistent or incomplete."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FixedCameraRobotCalibrationCaptureError(
                f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant {value}")


def _read_capture_file(
    path: Path,
    *,
    expected_sha256: str | None = None,
) -> Mapping[str, Any]:
    """Load one bounded capture file and optionally pin its exact bytes."""
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise FixedCameraRobotCalibrationCaptureError(
            f"could not read capture file {path}: {exc}") from exc
    if not payload or len(payload) > MAX_CAPTURE_FILE_BYTES:
        raise FixedCameraRobotCalibrationCaptureError(
            f"capture file {path} must contain 1 to {MAX_CAPTURE_FILE_BYTES} bytes")
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if expected_sha256 is not None:
        expected = _sha(expected_sha256, "expected capture file SHA-256")
        if actual_sha256 != expected:
            raise FixedCameraRobotCalibrationCaptureError(
                f"capture file SHA-256 mismatch for {path}")
    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except FixedCameraRobotCalibrationCaptureError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise FixedCameraRobotCalibrationCaptureError(
            f"capture file {path} is not strict UTF-8 JSON: {exc}") from exc
    return _mapping(document, f"capture file {path}")


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FixedCameraRobotCalibrationCaptureError(
            "value is not canonical JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        raise FixedCameraRobotCalibrationCaptureError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise FixedCameraRobotCalibrationCaptureError(
            f"{label} fields differ; missing={sorted(fields - set(value))}, "
            f"unexpected={sorted(set(value) - fields)}")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FixedCameraRobotCalibrationCaptureError(f"{label} must be nonempty text")
    return value.strip()


def _sha(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise FixedCameraRobotCalibrationCaptureError(
            f"{label} must be a lowercase SHA-256 digest")
    return text


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FixedCameraRobotCalibrationCaptureError(
            f"{label} must be a nonnegative integer")
    return value


def _number(value: object, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FixedCameraRobotCalibrationCaptureError(f"{label} must be finite")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise FixedCameraRobotCalibrationCaptureError(f"{label} must be finite")
    return result


def _vector3(value: object, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise FixedCameraRobotCalibrationCaptureError(
            f"{label} must contain exactly three numbers")
    return tuple(_number(item, f"{label}[{index}]") for index, item in enumerate(value))  # type: ignore[return-value]


def _distance(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _feedback_xyz(feedback: Feedback1051, label: str) -> tuple[float, float, float]:
    values = (feedback.x_mm, feedback.y_mm, feedback.z_mm)
    if any(value is None for value in values):
        raise FixedCameraRobotCalibrationCaptureError(
            f"{label} lacks reported endpoint XYZ")
    return tuple(float(value) for value in values)  # type: ignore[arg-type,return-value]


def _feedback_joints(feedback: Feedback1051, label: str) -> tuple[float, ...]:
    values = (
        feedback.base_rad, feedback.shoulder_rad, feedback.elbow_rad,
        feedback.wrist_pitch_rad, feedback.wrist_roll_rad, feedback.gripper_rad,
    )
    if any(value is None for value in values):
        raise FixedCameraRobotCalibrationCaptureError(
            f"{label} lacks all six joint angles")
    return tuple(float(value) for value in values)  # type: ignore[arg-type,return-value]


def _parse_feedback(value: object, label: str) -> Feedback1051:
    if not isinstance(value, str) or not value:
        raise FixedCameraRobotCalibrationCaptureError(
            f"{label} must be nonempty text")
    line = value
    if len(line.encode("utf-8")) > 64 * 1024:
        raise FixedCameraRobotCalibrationCaptureError(f"{label} exceeds byte limit")
    try:
        return parse_feedback_line(line)
    except (FeedbackError, ProtocolError, UnicodeError, ValueError) as exc:
        raise FixedCameraRobotCalibrationCaptureError(
            f"{label} is not valid T=1051 feedback") from exc


def compile_capture(document: Mapping[str, Any]) -> dict[str, Any]:
    """Verify one passive camera/feedback bracket and emit a correspondence."""
    value = _mapping(document, "capture")
    _exact(value, {
        "schema", "capture_id", "installation_epoch_id", "profile", "role",
        "frame", "board_pose", "tool_reference", "robot_feedback",
        "kinematic_binding",
    }, "capture")
    if value.get("schema") != CAPTURE_INPUT_SCHEMA:
        raise FixedCameraRobotCalibrationCaptureError("unexpected capture schema")
    capture_id = _text(value.get("capture_id"), "capture_id")
    installation_epoch_id = _text(
        value.get("installation_epoch_id"), "installation_epoch_id")
    if value.get("profile") != "no_attachment":
        raise FixedCameraRobotCalibrationCaptureError(
            "shared board transform requires the no_attachment bare-jaw profile")
    role = value.get("role")
    if role not in ("FIT", "HOLDOUT"):
        raise FixedCameraRobotCalibrationCaptureError("role must be FIT or HOLDOUT")

    frame = _mapping(value.get("frame"), "frame")
    _exact(frame, {
        "capture_id", "frame_sha256", "captured_at_ns", "clock_id",
        "camera_identity_sha256", "settings_sha256",
    }, "frame")
    if _text(frame.get("capture_id"), "frame.capture_id") != capture_id:
        raise FixedCameraRobotCalibrationCaptureError("frame capture identity differs")
    frame_sha = _sha(frame.get("frame_sha256"), "frame.frame_sha256")
    captured_at_ns = _integer(frame.get("captured_at_ns"), "frame.captured_at_ns")
    clock_id = _text(frame.get("clock_id"), "frame.clock_id")
    camera_identity_sha = _sha(
        frame.get("camera_identity_sha256"), "frame.camera_identity_sha256")
    settings_sha = _sha(frame.get("settings_sha256"), "frame.settings_sha256")

    board_pose = _mapping(value.get("board_pose"), "board_pose")
    _exact(board_pose, {
        "observation_sha256", "frame_sha256", "camera_intrinsics_sha256",
        "tag_map_sha256", "pose_fit_tag_ids", "held_out_tag_ids",
        "reprojection_rms_px", "held_out_max_residual_px",
    }, "board_pose")
    if _sha(board_pose.get("frame_sha256"), "board_pose.frame_sha256") != frame_sha:
        raise FixedCameraRobotCalibrationCaptureError(
            "board pose is bound to a different frame")
    pose_sha = _sha(board_pose.get("observation_sha256"), "board pose digest")
    intrinsics_sha = _sha(
        board_pose.get("camera_intrinsics_sha256"), "camera intrinsics digest")
    tag_map_sha = _sha(board_pose.get("tag_map_sha256"), "tag map digest")
    fit_tags = board_pose.get("pose_fit_tag_ids")
    held_out_tags = board_pose.get("held_out_tag_ids")
    if (not isinstance(fit_tags, list) or tuple(fit_tags) != POSE_FIT_TAG_IDS
            or any(isinstance(tag, bool) or not isinstance(tag, int)
                   for tag in fit_tags)):
        raise FixedCameraRobotCalibrationCaptureError(
            "board pose must fit ordered tag IDs 0 through 3")
    if (not isinstance(held_out_tags, list)
            or tuple(held_out_tags) != HELD_OUT_TAG_IDS
            or any(isinstance(tag, bool) or not isinstance(tag, int)
                   for tag in held_out_tags)):
        raise FixedCameraRobotCalibrationCaptureError(
            "board pose must independently check ordered tag IDs 4 and 5")
    reprojection_rms = _number(
        board_pose.get("reprojection_rms_px"), "reprojection RMS", minimum=0.0)
    if reprojection_rms > MAX_REPROJECTION_RMS_PX:
        raise FixedCameraRobotCalibrationCaptureError(
            "board pose reprojection RMS exceeds 2 px")
    held_out_residual = _number(
        board_pose.get("held_out_max_residual_px"),
        "held-out tag residual", minimum=0.0)
    if held_out_residual > MAX_REPROJECTION_RMS_PX:
        raise FixedCameraRobotCalibrationCaptureError(
            "held-out tag residual exceeds 2 px")

    tool = _mapping(value.get("tool_reference"), "tool_reference")
    _exact(tool, {
        "method", "observation_sha256", "frame_sha256", "detector_id",
        "detector_version", "configuration_sha256", "implementation_sha256",
        "board_xyz_mm", "uncertainty_mm",
    }, "tool_reference")
    if tool.get("method") != "CALIBRATED_FIXED_CAMERA_BARE_JAW_REFERENCE":
        raise FixedCameraRobotCalibrationCaptureError(
            "tool reference must come from the calibrated fixed-camera bare-jaw detector")
    if _sha(tool.get("frame_sha256"), "tool frame digest") != frame_sha:
        raise FixedCameraRobotCalibrationCaptureError(
            "tool reference is bound to a different frame")
    tool_sha = _sha(tool.get("observation_sha256"), "tool observation digest")
    _text(tool.get("detector_id"), "tool detector_id")
    _text(tool.get("detector_version"), "tool detector_version")
    _sha(tool.get("configuration_sha256"), "tool detector configuration")
    _sha(tool.get("implementation_sha256"), "tool detector implementation")
    board_xyz = _vector3(tool.get("board_xyz_mm"), "tool board_xyz_mm")
    if not (0.0 <= board_xyz[0] <= BOARD_WIDTH_MM
            and 0.0 <= board_xyz[1] <= BOARD_DEPTH_MM):
        raise FixedCameraRobotCalibrationCaptureError(
            "tool board observation lies outside the RC03 board")
    uncertainty = _number(tool.get("uncertainty_mm"), "tool uncertainty", minimum=0.0)
    if uncertainty > MAX_TOOL_REFERENCE_UNCERTAINTY_MM:
        raise FixedCameraRobotCalibrationCaptureError(
            "tool reference uncertainty exceeds 3 mm")

    robot = _mapping(value.get("robot_feedback"), "robot_feedback")
    _exact(robot, {
        "robot_base_identity", "clock_id", "pre_timestamp_ns",
        "post_timestamp_ns", "pre_feedback_line", "post_feedback_line",
    }, "robot_feedback")
    robot_identity = _text(robot.get("robot_base_identity"), "robot identity")
    if _text(robot.get("clock_id"), "robot clock_id") != clock_id:
        raise FixedCameraRobotCalibrationCaptureError(
            "camera and robot feedback clocks differ")
    pre_ns = _integer(robot.get("pre_timestamp_ns"), "pre_timestamp_ns")
    post_ns = _integer(robot.get("post_timestamp_ns"), "post_timestamp_ns")
    if not pre_ns <= captured_at_ns <= post_ns:
        raise FixedCameraRobotCalibrationCaptureError(
            "robot feedback does not bracket the camera frame")
    if post_ns - pre_ns > MAX_BRACKET_NS:
        raise FixedCameraRobotCalibrationCaptureError(
            "camera/robot feedback bracket exceeds one second")
    pre = _parse_feedback(robot.get("pre_feedback_line"), "pre_feedback_line")
    post = _parse_feedback(robot.get("post_feedback_line"), "post_feedback_line")

    binding = _mapping(value.get("kinematic_binding"), "kinematic_binding")
    _exact(binding, {
        "model_id", "reference_sha256", "robot_frame", "endpoint_frame",
    }, "kinematic_binding")
    if (binding.get("model_id") != "roarm_m3_firmware_reference_v1"
            or _sha(binding.get("reference_sha256"), "kinematic reference")
            != REFERENCE_SHA256
            or binding.get("robot_frame") != "robot_base"
            or binding.get("endpoint_frame") != "bare_jaw_reference"):
        raise FixedCameraRobotCalibrationCaptureError(
            "kinematic binding differs from the pinned bare-jaw reference")

    pre_joints = _feedback_joints(pre, "pre feedback")
    post_joints = _feedback_joints(post, "post feedback")
    joint_span = max(abs(a - b) for a, b in zip(pre_joints, post_joints, strict=True))
    if joint_span > MAX_JOINT_SPAN_RAD:
        raise FixedCameraRobotCalibrationCaptureError(
            "robot joints changed during camera capture")
    pre_fk = forward(*pre_joints[:4])[:3]
    post_fk = forward(*post_joints[:4])[:3]
    endpoint_span = _distance(pre_fk, post_fk)
    if endpoint_span > MAX_ENDPOINT_SPAN_MM:
        raise FixedCameraRobotCalibrationCaptureError(
            "robot endpoint changed during camera capture")
    reported_errors = (
        _distance(_feedback_xyz(pre, "pre feedback"), pre_fk),
        _distance(_feedback_xyz(post, "post feedback"), post_fk),
    )
    if max(reported_errors) > MAX_REPORTED_FK_ERROR_MM:
        raise FixedCameraRobotCalibrationCaptureError(
            "reported endpoint differs from pinned forward kinematics")
    robot_xyz = tuple((a + b) * 0.5 for a, b in zip(pre_fk, post_fk, strict=True))

    return {
        "schema": CAPTURE_RESULT_SCHEMA,
        "status": "PASSIVE_CORRESPONDENCE_CAPTURED",
        "capture_id": capture_id,
        "capture_input_sha256": _digest(value),
        "installation_epoch_id": installation_epoch_id,
        "profile": "no_attachment",
        "role": role,
        "bindings": {
            "frame_sha256": frame_sha,
            "camera_identity_sha256": camera_identity_sha,
            "settings_sha256": settings_sha,
            "board_pose_observation_sha256": pose_sha,
            "camera_intrinsics_sha256": intrinsics_sha,
            "tag_map_sha256": tag_map_sha,
            "tool_reference_observation_sha256": tool_sha,
            "kinematic_reference_sha256": REFERENCE_SHA256,
            "robot_base_identity": robot_identity,
        },
        "correspondence": {
            "point_id": capture_id,
            "role": role,
            "board_xyz_mm": [round(v, 6) for v in board_xyz],
            "robot_xyz_mm": [round(v, 6) for v in robot_xyz],
        },
        "quality": {
            "pose_fit_tag_ids": list(POSE_FIT_TAG_IDS),
            "held_out_tag_ids": list(HELD_OUT_TAG_IDS),
            "board_pose_reprojection_rms_px": reprojection_rms,
            "held_out_max_residual_px": held_out_residual,
            "tool_reference_uncertainty_mm": uncertainty,
            "maximum_joint_span_rad": joint_span,
            "endpoint_span_mm": endpoint_span,
            "maximum_reported_fk_error_mm": max(reported_errors),
            "feedback_bracket_ns": post_ns - pre_ns,
        },
        "review_status": "UNREVIEWED_CAPTURE",
        "hardware_access": False,
        "controller_commands": [],
        "motion_targets_emitted": False,
        "motion_authorized": False,
        "contact_authorized": False,
    }


def _spans_board_axes(points: Sequence[tuple[float, float, float]]) -> bool:
    for i in range(len(points) - 2):
        for j in range(i + 1, len(points) - 1):
            for k in range(j + 1, len(points)):
                ax, ay, _ = points[i]
                bx, by, _ = points[j]
                cx, cy, _ = points[k]
                twice_area = abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))
                if twice_area >= 200.0:
                    return True
    return False


def compile_campaign(captures: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate passive captures into an exact, still-unreviewed worksheet."""
    if not isinstance(captures, (list, tuple)) or len(captures) > 64:
        raise FixedCameraRobotCalibrationCaptureError(
            "campaign must contain at most 64 captures")
    results = [compile_capture(capture) for capture in captures]
    if len(results) < 5:
        raise FixedCameraRobotCalibrationCaptureError(
            "campaign requires at least three fit and two holdout captures")
    ids = [result["capture_id"] for result in results]
    if len(set(ids)) != len(ids):
        raise FixedCameraRobotCalibrationCaptureError("capture IDs must be unique")
    for binding, label in (
        ("frame_sha256", "camera frames"),
        ("board_pose_observation_sha256", "board-pose observations"),
        ("tool_reference_observation_sha256", "tool-reference observations"),
    ):
        values = [result["bindings"][binding] for result in results]
        if len(set(values)) != len(values):
            raise FixedCameraRobotCalibrationCaptureError(
                f"campaign {label} must be unique")
    fit = [result for result in results if result["role"] == "FIT"]
    holdout = [result for result in results if result["role"] == "HOLDOUT"]
    if len(fit) < 3 or len(holdout) < 2:
        raise FixedCameraRobotCalibrationCaptureError(
            "campaign requires at least three fit and two holdout captures")
    if not _spans_board_axes([
        tuple(row["correspondence"]["board_xyz_mm"]) for row in fit
    ]):
        raise FixedCameraRobotCalibrationCaptureError(
            "fit capture points must span both board axes")
    first = results[0]
    invariant_fields = (
        "camera_identity_sha256", "settings_sha256", "camera_intrinsics_sha256",
        "tag_map_sha256", "kinematic_reference_sha256", "robot_base_identity",
    )
    for result in results[1:]:
        if result["installation_epoch_id"] != first["installation_epoch_id"]:
            raise FixedCameraRobotCalibrationCaptureError(
                "capture installation epochs differ")
        if any(result["bindings"][field] != first["bindings"][field]
               for field in invariant_fields):
            raise FixedCameraRobotCalibrationCaptureError(
                "capture camera, robot, or calibration bindings drifted")

    measurement = {
        "schema": MEASUREMENT_SCHEMA,
        "status": "DRAFT_UNREVIEWED",
        "source_frame": "RC03_board",
        "target_frame": "robot_base",
        "units": "mm",
        "measurement_method": "independent_robot_to_board_correspondences",
        "board": {"width_mm": BOARD_WIDTH_MM, "depth_mm": BOARD_DEPTH_MM},
        "installation": {
            "robot_base_identity": first["bindings"]["robot_base_identity"],
            "board_identity": "RC03-INT-R1",
            "installation_unchanged": False,
            "reseat_check_passed": False,
        },
        "review": {
            "reviewed": False,
            "reviewer": "",
            "reviewed_at": "",
            "notes": (
                "Generated from passive fixed-camera and bracketed robot telemetry; "
                "capture hashes are retained in the campaign result."),
        },
        "correspondences": [result["correspondence"] for result in results],
        "thresholds": {
            "max_fit_rms_residual_mm": 3.0,
            "max_fit_residual_mm": 5.0,
            "max_holdout_residual_mm": 5.0,
        },
    }
    return {
        "schema": CAMPAIGN_RESULT_SCHEMA,
        "status": "MEASUREMENT_DRAFT_READY_FOR_INDEPENDENT_REVIEW",
        "installation_epoch_id": first["installation_epoch_id"],
        "profile": "no_attachment",
        "capture_result_sha256s": [_digest(result) for result in results],
        "capture_count": len(results),
        "fit_count": len(fit),
        "holdout_count": len(holdout),
        "measurement_draft": measurement,
        "measurement_draft_sha256": _digest(measurement),
        "stylus_profile_status": "SEPARATE_TCP_AND_CLEARANCE_CAPTURE_REQUIRED",
        "review_status": "UNREVIEWED_CAMPAIGN",
        "hardware_access": False,
        "controller_commands": [],
        "motion_targets_emitted": False,
        "motion_authorized": False,
        "contact_authorized": False,
    }


def compile_files(
    paths: Sequence[Path],
    *,
    campaign: bool,
    expected_sha256s: Sequence[str] = (),
) -> dict[str, Any]:
    """Compile hash-pinnable retained capture files without device access."""
    selected_paths = tuple(paths)
    selected_hashes = tuple(expected_sha256s)
    if not selected_paths:
        raise FixedCameraRobotCalibrationCaptureError(
            "at least one retained capture file is required")
    if selected_hashes and len(selected_hashes) != len(selected_paths):
        raise FixedCameraRobotCalibrationCaptureError(
            "expected SHA-256 count must equal capture file count")
    documents = [
        _read_capture_file(
            path,
            expected_sha256=(selected_hashes[index] if selected_hashes else None),
        )
        for index, path in enumerate(selected_paths)
    ]
    if campaign:
        return compile_campaign(documents)
    if len(documents) != 1:
        raise FixedCameraRobotCalibrationCaptureError(
            "single-capture mode accepts exactly one file; use --campaign")
    return compile_capture(documents[0])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compile retained fixed-camera/robot calibration records without "
            "opening the camera or robot"
        ))
    parser.add_argument(
        "captures", type=Path, nargs="+", help="Retained capture-input JSON files")
    parser.add_argument(
        "--campaign", action="store_true",
        help="Aggregate at least three FIT and two HOLDOUT capture files")
    parser.add_argument(
        "--expected-sha256", action="append", default=[], metavar="SHA256",
        help=(
            "Exact file-byte SHA-256 pin; repeat once per capture in input order"
        ))
    args = parser.parse_args(argv)
    try:
        result = compile_files(
            args.captures,
            campaign=args.campaign,
            expected_sha256s=args.expected_sha256,
        )
    except FixedCameraRobotCalibrationCaptureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


__all__ = [
    "CAPTURE_INPUT_SCHEMA", "CAPTURE_RESULT_SCHEMA", "CAMPAIGN_RESULT_SCHEMA",
    "MAX_CAPTURE_FILE_BYTES", "FixedCameraRobotCalibrationCaptureError",
    "compile_capture", "compile_campaign", "compile_files",
]


if __name__ == "__main__":
    raise SystemExit(main())
