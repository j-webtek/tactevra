"""Manual-photo preparation remains explicit and incapable of device I/O."""

from rocell.application.first_motion_contract import fixed_command
from rocell.application.manual_photo_first_motion_prep import prepare


def test_preflight_binds_photo_and_stops_before_live_admission(monkeypatch, tmp_path):
    annotation = tmp_path / "annotation.json"
    profile = tmp_path / "profile.json"
    photo = tmp_path / "photo.jpg"
    for path in (annotation, profile, photo):
        path.write_bytes(path.name.encode("ascii"))

    def registration(annotation_path, profile_path, photo_path):
        assert (annotation_path, profile_path, photo_path) == (
            annotation.resolve(), profile.resolve(), photo.resolve())
        return {
            "photo_sha256": "a" * 64,
            "source_photo_bytes_verified": True,
            "source_photo_dimensions_verified": True,
            "profile_sha256": "b" * 64,
            "board_frame": "RC03_B_FRONT_LEFT_X_RIGHT_Y_REAR_MM",
            "fiducial_count": 8,
            "fiducial_max_residual_mm": 1.2,
            "housing_corner_max_residual_mm": 7.1,
            "study_xy_margin_mm": 15.0,
        }

    monkeypatch.setattr(
        "rocell.application.manual_photo_first_motion_prep.estimate_files", registration)
    result = prepare(annotation, profile, photo)
    assert result["status"] == "HOLD_FOR_LIVE_ADMISSION_INPUTS"
    assert result["only_prepared_physical_command"] == fixed_command()
    assert "CURRENT_READ_ONLY_CONTROLLER_SNAPSHOT" in result["required_live_inputs"]
    assert not result["device_io_performed"]
    assert not result["physical_authority"]
    assert not result["motion_authorized"]
    assert not result["keyboard_motion_prepared"]
