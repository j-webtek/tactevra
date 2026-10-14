"""Photo-to-board fit remains a bounded offline estimate, never a command."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from rocell.application.photo_keyboard_registration import estimate, estimate_files


ROOT = Path(__file__).resolve().parents[2]


def inputs():
    annotation = json.loads((ROOT / "config/photo_keyboard_registration_20260925.json")
                            .read_text(encoding="utf-8"))
    profile_path = ROOT / "config/static_nominal_target_profiles.json"
    profile_bytes = profile_path.read_bytes()
    return annotation, json.loads(profile_bytes)["keyboard"], hashlib.sha256(profile_bytes).hexdigest()


def test_photo_estimate_uses_board_marks_and_known_housing_dimensions():
    annotation, profile, digest = inputs()
    result = estimate(annotation, profile, profile_sha256=digest)
    assert result["fiducial_count"] == 8
    assert result["fiducial_max_residual_mm"] < 2
    assert result["housing_corner_max_residual_mm"] < 8
    assert result["fitted_front_left_board_xy_mm"] == pytest.approx([78.7, 77.92], abs=0.1)
    assert result["fitted_local_yaw_deg"] == pytest.approx(180.302, abs=0.1)
    assert result["nominal_key_centers_board_xy_mm"]["B"] == pytest.approx(
        [271.17, 177.94], abs=0.1)
    assert len(result["nominal_key_centers_board_xy_mm"]) == 46
    assert not result["keyboard_registered"]
    assert not result["motion_authorized"]


def test_bad_fiducial_or_dimension_is_rejected():
    annotation, profile, digest = inputs()
    shifted = deepcopy(annotation)
    shifted["fiducials"][3]["pixel_xy"][0] += 100
    with pytest.raises(ValueError, match="coherent planar fit"):
        estimate(shifted, profile, profile_sha256=digest)
    wrong_size = deepcopy(annotation)
    wrong_size["housing_dimensions_mm"][0] = 300
    with pytest.raises(ValueError, match="housing dimensions"):
        estimate(wrong_size, profile, profile_sha256=digest)


def test_source_jpeg_dimensions_must_match_annotation(tmp_path):
    annotation, _, _ = inputs()
    # Structurally valid 2 x 3 JPEG for the bounded header parser.
    photo = tmp_path / "photo.jpg"
    payload = (b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x03\x00\x02" +
               b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00\xff\xd9")
    photo.write_bytes(payload)
    annotation["photo"]["sha256"] = hashlib.sha256(payload).hexdigest()
    annotation_path = tmp_path / "annotation.json"
    annotation_path.write_text(json.dumps(annotation), encoding="utf-8")
    profile_path = ROOT / "config/static_nominal_target_profiles.json"
    with pytest.raises(ValueError, match="dimensions have changed"):
        estimate_files(annotation_path, profile_path, photo)
