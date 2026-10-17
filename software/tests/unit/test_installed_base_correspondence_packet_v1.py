from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell.application.installed_base_correspondence_packet_v1 import (
    CANDIDATE_STATUS,
    FAILED_STATUS,
    PENDING_STATUS,
    build_pending_installed_base_correspondence_packet_v1,
    fit_installed_base_position_candidate_v1,
)
from rocell.geometry.transforms import RigidTransform, Vec3
from rocell.models.frames import Point3Mm


WORKSPACE = Path(__file__).resolve().parents[3]
INTAKE = WORKSPACE / "software/ai/eval/installed_base_transform_intake_20261017.json"
WHEN = "2026-10-17T14:00:00Z"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pending() -> dict[str, object]:
    return build_pending_installed_base_correspondence_packet_v1(
        INTAKE,
        _file_sha256(INTAKE),
        packet_id="installed-base-correspondences-20261017-v1",
        created_at_utc=WHEN,
    )


def _rehash(document: dict[str, object]) -> None:
    unsigned = {
        key: value for key, value in document.items() if key != "content_sha256"
    }
    document["content_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def test_pending_packet_is_deterministic_precommitted_and_zero_authority() -> None:
    first = _pending()
    second = _pending()
    split = first["precommitted_split"]
    assert first == second
    assert first["status"] == PENDING_STATUS
    assert split["training_slot_count"] == 6
    assert split["held_out_slot_count"] == 2
    assert len(split["slots"]) == 8
    assert sum(row["split"] == "TRAINING" for row in split["slots"]) == 6
    assert sum(row["split"] == "HELD_OUT" for row in split["slots"]) == 2
    assert first["fixed_context"]["neutral_observation_servo_positions"] == [
        2052,
        2149,
        1956,
        2550,
        2227,
        2041,
        2042,
    ]
    assert first["controller_commands"] == []
    assert first["hardware_access"] is False
    assert first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_packet_rejects_wrong_intake_hash_and_unaccepted_prerequisites() -> None:
    with pytest.raises(ValueError, match="file hash mismatch"):
        build_pending_installed_base_correspondence_packet_v1(
            INTAKE, "0" * 64, packet_id="x", created_at_utc=WHEN
        )
    with pytest.raises(ValueError, match="prerequisites are not accepted"):
        fit_installed_base_position_candidate_v1(_pending())


def test_completed_synthetic_packet_fits_position_candidate_only() -> None:
    packet = _pending()
    packet["prerequisite_status"] = {
        key: "ACCEPTED_PHYSICAL_ARTIFACT" for key in packet["prerequisite_status"]
    }
    truth = RigidTransform.from_rpy_translation_mm(
        "B",
        "base_link",
        translation_mm=Vec3(310.0, 445.0, 72.0),
        roll_rad=0.04,
        pitch_rad=-0.08,
        yaw_rad=-1.7,
    )
    points = (
        (-100.0, -80.0, 20.0),
        (110.0, -70.0, 25.0),
        (-120.0, 90.0, 22.0),
        (125.0, 95.0, 30.0),
        (-55.0, 15.0, 110.0),
        (65.0, 20.0, 105.0),
        (5.0, -35.0, 60.0),
        (10.0, 75.0, 58.0),
    )
    for index, (row, xyz) in enumerate(
        zip(packet["precommitted_split"]["slots"], points)
    ):
        target = truth.transform_point(Point3Mm("base_link", *xyz))
        row.update(
            status="MEASURED",
            pose_label=f"fixture-{index}",
            base_point_xyz_mm=list(xyz),
            board_point_xyz_mm=[target.x, target.y, target.z],
            controller_feedback_sha256="a" * 64,
            base_point_derivation_sha256="c" * 64,
            camera_observation_sha256="b" * 64,
            board_point_measurement_sha256="d" * 64,
            captured_at_utc=WHEN,
            notes="synthetic test only",
        )
    _rehash(packet)
    result = fit_installed_base_position_candidate_v1(packet)
    candidate = result["rigid_correspondence"]["candidate_transform"]
    assert result["status"] == CANDIDATE_STATUS
    assert result["position_diagnostic_pass"] is True
    assert candidate["translation_mm"] == pytest.approx([310.0, 445.0, 72.0])
    assert result["installed_base_transform_complete"] is False
    assert "orientation-diverse pose validation" in result["remaining_requirements"]
    assert result["controller_commands"] == []
    assert result["physical_authority"] is False


def test_changed_precommitted_split_fails_closed() -> None:
    packet = _pending()
    packet["prerequisite_status"] = {
        key: "ACCEPTED_PHYSICAL_ARTIFACT" for key in packet["prerequisite_status"]
    }
    packet["precommitted_split"]["slots"][0]["split"] = "HELD_OUT"
    _rehash(packet)
    with pytest.raises(ValueError, match="six training and two held out"):
        fit_installed_base_position_candidate_v1(packet)


def test_failed_diagnostic_is_not_labeled_as_position_candidate() -> None:
    packet = _pending()
    packet["prerequisite_status"] = {
        key: "ACCEPTED_PHYSICAL_ARTIFACT" for key in packet["prerequisite_status"]
    }
    points = (
        (-100.0, -80.0, 20.0),
        (110.0, -70.0, 25.0),
        (-120.0, 90.0, 22.0),
        (125.0, 95.0, 30.0),
        (-55.0, 15.0, 110.0),
        (65.0, 20.0, 105.0),
        (5.0, -35.0, 60.0),
        (10.0, 75.0, 58.0),
    )
    for index, (row, xyz) in enumerate(
        zip(packet["precommitted_split"]["slots"], points)
    ):
        target = list(xyz)
        if index >= 6:
            target = [value + 20.0 for value in xyz]
        row.update(
            status="MEASURED",
            pose_label=f"fixture-{index}",
            base_point_xyz_mm=list(xyz),
            board_point_xyz_mm=target,
            controller_feedback_sha256="a" * 64,
            base_point_derivation_sha256="c" * 64,
            camera_observation_sha256="b" * 64,
            board_point_measurement_sha256="d" * 64,
            captured_at_utc=WHEN,
        )
    _rehash(packet)

    result = fit_installed_base_position_candidate_v1(packet)

    assert result["position_diagnostic_pass"] is False
    assert result["status"] == FAILED_STATUS
    assert result["physical_authority"] is False
