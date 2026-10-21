"""Fail-closed classification of installed T=1051 response shapes.

Classification preserves transport evidence without turning an installed
firmware payload into calibrated joint state.  It performs no device I/O and
grants no execution or physical authority.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from .feedback import FeedbackError, parse_feedback_1051


FULL_FEEDBACK_FIELDS = frozenset(
    {"x", "y", "z", "tit", "b", "s", "e", "t", "r", "g", "v"}
)
POSITION_VECTOR_FIELDS = frozenset(
    {"T", "p", "pose", "motion_active", "trajectory_progress_permille"}
)


class Feedback1051Profile(str, Enum):
    FULL_WAVESHARE = "FULL_WAVESHARE"
    POSITION_VECTOR_NAMED_POSE = "POSITION_VECTOR_NAMED_POSE"
    UNKNOWN = "UNKNOWN"


def classify_feedback_1051_profile(message: Mapping[str, Any]) -> Feedback1051Profile:
    """Classify only exact, bounded response shapes.

    The seven-count vector remains raw controller data.  This function does
    not infer a count-to-joint mapping or treat the named pose as provenance.
    """

    if not isinstance(message, Mapping) or message.get("T") != 1051:
        return Feedback1051Profile.UNKNOWN
    if FULL_FEEDBACK_FIELDS.issubset(message):
        try:
            parse_feedback_1051(message)
        except FeedbackError:
            return Feedback1051Profile.UNKNOWN
        return Feedback1051Profile.FULL_WAVESHARE
    if set(message) != POSITION_VECTOR_FIELDS:
        return Feedback1051Profile.UNKNOWN
    positions = message.get("p")
    pose = message.get("pose")
    motion_active = message.get("motion_active")
    progress = message.get("trajectory_progress_permille")
    if (
        not isinstance(positions, list)
        or len(positions) != 7
        or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= 4095
            for value in positions
        )
        or not isinstance(pose, str)
        or not 1 <= len(pose) <= 64
        or any(not (character.isascii() and (character.isalnum() or character in "_.-"))
               for character in pose)
        or not isinstance(motion_active, bool)
        or isinstance(progress, bool)
        or not isinstance(progress, int)
        or not 0 <= progress <= 1000
    ):
        return Feedback1051Profile.UNKNOWN
    return Feedback1051Profile.POSITION_VECTOR_NAMED_POSE


__all__ = [
    "FULL_FEEDBACK_FIELDS",
    "POSITION_VECTOR_FIELDS",
    "Feedback1051Profile",
    "classify_feedback_1051_profile",
]
