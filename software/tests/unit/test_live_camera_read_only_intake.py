from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/live_camera_read_only_intake.py"
SPEC = importlib.util.spec_from_file_location("live_camera_read_only_intake", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_identity_is_one_canonical_usb_pnp_id() -> None:
    value = r"usb\vid_04b4&pid_0477&mi_00\8&257b140a&0&0000"
    assert MODULE._identity(value) == value.upper()


@pytest.mark.parametrize("value", ["0", "B0477", r"PCI\VID_04B4&PID_0477\x"])
def test_identity_rejects_nonpersistent_selectors(value: str) -> None:
    with pytest.raises(ValueError):
        MODULE._identity(value)


def test_assessment_never_grants_registration() -> None:
    image = np.full((64, 96, 3), 127, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    result = MODULE.assess_jpeg(encoded.tobytes(), cv2)
    assert result["mean_luma_8bit"] == pytest.approx(127, abs=1)
    assert result["detected_tag36h11_ids"] == []
    assert [item["profile"] for item in result["detector_profile_results"]] == [
        "opencv_default",
        "small_tag_apriltag_refinement",
    ]
    assert result["all_required_tags_visible"] is False
    assert result["registration_authority"] is False


def test_assessment_unions_only_decoded_ids_across_profiles(monkeypatch) -> None:
    image = np.full((64, 96, 3), 127, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok

    results = iter(
        [
            ([], np.array([[0], [1], [3]], dtype=np.int32), [object()]),
            ([], np.array([[1], [2], [3]], dtype=np.int32), [object(), object()]),
        ]
    )

    class FakeDetector:
        def __init__(self, _dictionary, _parameters) -> None:
            pass

        def detectMarkers(self, _gray):
            return next(results)

    monkeypatch.setattr(cv2.aruco, "ArucoDetector", FakeDetector)
    result = MODULE.assess_jpeg(encoded.tobytes(), cv2)
    assert result["detected_tag36h11_ids"] == [0, 1, 2, 3]
    assert result["rejected_quad_candidates"] == 3
    assert result["all_required_tags_visible"] is False
    assert result["registration_authority"] is False


def test_name_rejects_multiline_text() -> None:
    with pytest.raises(ValueError):
        MODULE._name("camera\nsecond line")


def test_live_session_binds_measured_fixed_board_registration() -> None:
    software_root = Path(__file__).resolve().parents[2]
    session_path = software_root / "config/live_camera_feedback_session_20261015.json"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    camera = session["camera_baseline"]
    plan = camera["fixed_board_planar_registration"]
    result_path = software_root.parent / plan["artifact_path"]
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert "intrinsics_dataset_precommit" not in camera
    assert plan["board_size_xy_mm"] == [610.0, 457.0]
    assert plan["tag_detection_edge_mm"] == 40.0
    assert plan["fit_tag_ids"] == [0, 1, 2, 3]
    assert plan["held_out_check_tag_ids"] == [4, 5]
    assert (
        plan["artifact_sha256"] == hashlib.sha256(result_path.read_bytes()).hexdigest()
    )
    assert result["validation"]["held_out_station_center_check_count"] == 20
    assert plan["authority"] == {
        "robot_transport_opened": False,
        "robot_motion": False,
        "camera_guided_motion": False,
        "contact": False,
    }
