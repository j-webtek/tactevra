"""Pure T=1051 response classification; no device I/O."""

import pytest

from rocell.arm.feedback_profile import (
    Feedback1051Profile,
    classify_feedback_1051_profile,
)


POSITION_VECTOR = {
    "T": 1051,
    "p": [2050, 2147, 1958, 2550, 2227, 2041, 2042],
    "pose": "KEYBOARD_FORWARD_CAL_1",
    "motion_active": False,
    "trajectory_progress_permille": 1000,
}


def test_classifies_exact_installed_position_vector_without_interpretation():
    assert (
        classify_feedback_1051_profile(POSITION_VECTOR)
        is Feedback1051Profile.POSITION_VECTOR_NAMED_POSE
    )


def test_classifies_full_waveshare_profile():
    message = {
        "T": 1051, "x": 300, "y": 0, "z": 200, "tit": 0,
        "b": 0, "s": 0, "e": 1.5, "t": 0, "r": 0, "g": 3, "v": 1200,
    }
    assert (
        classify_feedback_1051_profile(message)
        is Feedback1051Profile.FULL_WAVESHARE
    )


def test_invalid_full_profile_is_unknown():
    message = {
        "T": 1051, "x": 300, "y": 0, "z": 200, "tit": 0,
        "b": 0, "s": 0, "e": 1.5, "t": 0, "r": 0, "g": 3,
        "v": float("nan"),
    }
    assert classify_feedback_1051_profile(message) is Feedback1051Profile.UNKNOWN


@pytest.mark.parametrize(
    "change",
    [
        {"T": 104},
        {"p": [2050] * 6},
        {"p": [2050] * 6 + [4096]},
        {"p": [2050] * 6 + [True]},
        {"pose": ""},
        {"pose": "bad pose"},
        {"motion_active": 0},
        {"trajectory_progress_permille": 1001},
        {"extra": "unreviewed"},
    ],
)
def test_malformed_or_extended_position_vector_is_unknown(change):
    message = {**POSITION_VECTOR, **change}
    assert classify_feedback_1051_profile(message) is Feedback1051Profile.UNKNOWN
