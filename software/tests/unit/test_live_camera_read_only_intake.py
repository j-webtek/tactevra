from __future__ import annotations

import importlib.util
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
    assert result["all_required_tags_visible"] is False
    assert result["registration_authority"] is False


def test_name_rejects_multiline_text() -> None:
    with pytest.raises(ValueError):
        MODULE._name("camera\nsecond line")
