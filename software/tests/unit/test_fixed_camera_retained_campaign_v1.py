from __future__ import annotations

from types import SimpleNamespace

import pytest

import rocell.calibration.fixed_camera_retained_campaign_v1 as subject
from rocell.calibration.fixed_camera_retained_campaign_v1 import (
    FixedCameraRetainedCampaignError,
    RetainedFixedCameraObservationSourceV1,
    compile_retained_fixed_camera_calibration_campaign_v1,
)

from test_fixed_camera_board_pose_extractor_v1 import _tag_map
from test_fixed_camera_robot_calibration_capture_v1 import _capture


def source(name: str, role: str) -> RetainedFixedCameraObservationSourceV1:
    return RetainedFixedCameraObservationSourceV1(
        bracket_record_path=f"{name}-bracket.json",
        jpeg_path=f"{name}.jpg",
        intrinsics_record_path="shared-intrinsics.json",
        tag_evidence_path=f"{name}-tags.json",
        bare_jaw_calibration_path="shared-jaw-calibration.json",
        bare_jaw_landmark_evidence_path=f"{name}-jaw-landmarks.json",
        expected_bracket_record_file_sha256="1" * 64,
        expected_jpeg_file_sha256="2" * 64,
        expected_intrinsics_file_sha256="3" * 64,
        expected_tag_evidence_file_sha256="4" * 64,
        expected_bare_jaw_calibration_file_sha256="5" * 64,
        expected_bare_jaw_landmark_evidence_file_sha256="6" * 64,
        role=role,
    )


def campaign_sources() -> list[RetainedFixedCameraObservationSourceV1]:
    return [
        source("fit-a", "FIT"),
        source("fit-b", "FIT"),
        source("fit-c", "FIT"),
        source("holdout-a", "HOLDOUT"),
        source("holdout-b", "HOLDOUT"),
    ]


def captures() -> dict[str, dict]:
    return {
        "fit-a": _capture("fit-a", board_xyz=(40.0, 40.0, 0.0)),
        "fit-b": _capture(
            "fit-b",
            board_xyz=(560.0, 45.0, 0.0),
            joints=(0.4, 0.55, 1.1, -0.2, 0.0, 0.0),
        ),
        "fit-c": _capture(
            "fit-c",
            board_xyz=(60.0, 410.0, 0.0),
            joints=(-0.4, 0.6, 1.05, -0.2, 0.0, 0.0),
        ),
        "holdout-a": _capture(
            "holdout-a",
            role="HOLDOUT",
            board_xyz=(545.0, 400.0, 0.0),
            joints=(0.25, 0.7, 0.95, -0.3, 0.0, 0.0),
        ),
        "holdout-b": _capture(
            "holdout-b",
            role="HOLDOUT",
            board_xyz=(305.0, 228.5, 0.0),
            joints=(-0.1, 0.65, 1.0, -0.25, 0.0, 0.0),
        ),
    }


def install_retained_compiler(monkeypatch: pytest.MonkeyPatch) -> None:
    values = captures()

    def compile_one(**kwargs: object) -> SimpleNamespace:
        name = str(kwargs["bracket_record_path"]).removesuffix("-bracket.json")
        capture = values[name]
        assert kwargs["role"] == capture["role"]
        return SimpleNamespace(
            observation=SimpleNamespace(capture_input=capture),
            sha256=(name.encode().hex() + "0" * 64)[:64],
            receipt=lambda: {
                "capture_id": name,
                "source_file_sha256": {"bracket_record": "1" * 64},
            },
        )

    monkeypatch.setattr(
        subject,
        "compile_retained_fixed_camera_calibration_observation_v1",
        compile_one,
    )


def test_composes_five_exact_sources_through_existing_campaign_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_retained_compiler(monkeypatch)

    result = compile_retained_fixed_camera_calibration_campaign_v1(
        campaign_sources(), tag_map=_tag_map()
    )

    assert result.campaign_result["capture_count"] == 5
    assert result.campaign_result["fit_count"] == 3
    assert result.campaign_result["holdout_count"] == 2
    assert result.campaign_result["review_status"] == "UNREVIEWED_CAMPAIGN"
    receipt = result.receipt()
    assert len(receipt["observation_sha256s"]) == 5
    assert len(receipt["observation_receipt_sha256s"]) == 5
    assert receipt["measurement_draft_sha256"] == result.campaign_result[
        "measurement_draft_sha256"
    ]
    assert receipt["authority"]["controller_commands"] == []
    assert receipt["authority"]["physical_release_effect"] == "NONE"
    assert len(result.sha256) == 64


def test_campaign_rejects_reused_retained_frame_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = captures()
    values["holdout-b"]["frame"]["frame_sha256"] = values["fit-a"]["frame"][
        "frame_sha256"
    ]
    values["holdout-b"]["board_pose"]["frame_sha256"] = values["fit-a"][
        "frame"
    ]["frame_sha256"]
    values["holdout-b"]["tool_reference"]["frame_sha256"] = values["fit-a"][
        "frame"
    ]["frame_sha256"]

    def compile_one(**kwargs: object) -> SimpleNamespace:
        name = str(kwargs["bracket_record_path"]).removesuffix("-bracket.json")
        return SimpleNamespace(
            observation=SimpleNamespace(capture_input=values[name]),
            sha256="7" * 64,
            receipt=lambda: {"capture_id": name},
        )

    monkeypatch.setattr(
        subject,
        "compile_retained_fixed_camera_calibration_observation_v1",
        compile_one,
    )

    with pytest.raises(ValueError, match="camera frames must be unique"):
        compile_retained_fixed_camera_calibration_campaign_v1(
            campaign_sources(), tag_map=_tag_map()
        )


def test_rejects_invalid_source_collection_before_reading_files() -> None:
    with pytest.raises(FixedCameraRetainedCampaignError, match="list or tuple"):
        compile_retained_fixed_camera_calibration_campaign_v1(  # type: ignore[arg-type]
            "not-a-source-list", tag_map=_tag_map()
        )
    with pytest.raises(FixedCameraRetainedCampaignError, match="1 to 64"):
        compile_retained_fixed_camera_calibration_campaign_v1(
            [], tag_map=_tag_map()
        )
    with pytest.raises(FixedCameraRetainedCampaignError, match="every source"):
        compile_retained_fixed_camera_calibration_campaign_v1(  # type: ignore[list-item]
            [object()], tag_map=_tag_map()
        )
