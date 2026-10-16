from __future__ import annotations

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


def test_live_session_precommits_intrinsics_fit_and_holdout_views() -> None:
    session_path = (
        Path(__file__).resolve().parents[2]
        / "config/live_camera_feedback_session_20261015.json"
    )
    session = json.loads(session_path.read_text(encoding="utf-8"))
    plan = session["camera_baseline"]["intrinsics_dataset_precommit"]
    sequence = plan["capture_sequence"]

    assert [item["sequence_ordinal"] for item in sequence] == list(range(1, 27))
    assert [item["image_id"] for item in sequence[:20]] == [
        f"fit-{index:02d}" for index in range(1, 21)
    ]
    assert [item["image_id"] for item in sequence[20:]] == [
        f"holdout-{index:02d}" for index in range(1, 7)
    ]
    assert {item["split"] for item in sequence[:20]} == {"FIT"}
    assert {item["split"] for item in sequence[20:]} == {"HOLDOUT"}
    assert plan["split_policy"]["holdout_must_not_enter_fit"] is True
    assert plan["target"]["minimum_horizontal_scale_measurements"] == 4
    assert plan["target"]["minimum_vertical_scale_measurements"] == 4
    assert plan["target"]["definition_sha256"] == (
        "c8f95230bc42cd14fc546c6fed09af4780155c65da50e6c3c32a3b86eef0613e"
    )
    assert plan["target"]["printable_pdf_sha256"] == (
        "6a1d0d441b54d04b20d443eee3e84b62203e5ff0f92ef70ea48ba795af27670f"
    )
    assert plan["mode_separation"]["cross_mode_intrinsics_reuse"].startswith("FORBIDDEN")
    assert plan["authority"] == {
        "physical_calibration_valid": False,
        "registration_valid": False,
        "camera_guided_motion": False,
        "robot_motion": False,
        "contact": False,
    }
