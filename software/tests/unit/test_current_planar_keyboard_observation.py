from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.application import current_planar_keyboard_observation as observation


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_current_planar_observation_projects_all_reviewed_targets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    frames = tmp_path / "frames"
    frames.mkdir()
    frame = frames / "frame.jpg"
    frame.write_bytes(b"synthetic-frame")
    (frames / "derived-overlay.jpg").write_bytes(b"derived-not-a-source-frame")
    _write(
        frames / "receipt.json",
        {
            "reopen_cycles": [
                {
                    "frames": [
                        {
                            "file_name": frame.name,
                            "sha256": _hash(frame),
                            "scene_assessment": {"laplacian_variance": 100.0},
                        }
                    ]
                }
            ]
        },
    )
    centers = {
        "T0": [20.0, 20.0],
        "T1": [200.0, 20.0],
        "T2": [20.0, 200.0],
        "T3": [200.0, 200.0],
        "K0": [80.0, 100.0],
        "P0": [160.0, 100.0],
    }
    registration = tmp_path / "registration.json"
    _write(
        registration,
        {"inputs": {"tag_centers_xy_mm": centers, "tag_detection_edge_mm": 20.0}},
    )
    targets = {
        f"K{index}": {
            "image_fitted_center_keyboard_xy_mm": [float(index), 10.0],
            "nominal_half_extent_mm": [4.0, 4.0],
        }
        for index in range(46)
    }
    overlay = tmp_path / "overlay.json"
    _write(
        overlay,
        {
            "schema": "rocell.fixed_camera_keyboard_overlay.v1",
            "workcell_epoch_id": "epoch-1",
            "inputs": {"board_registration_sha256": _hash(registration)},
            "board_plane_interpretation": {
                "dimension_constrained_front_left_xy_mm": [50.0, 60.0],
                "dimension_constrained_yaw_deg": 0.0,
            },
            "keyboard_geometry": {"projected_targets": targets},
        },
    )
    stationary = frames / "stationary.json"
    _write(
        stationary,
        {
            "schema": "rocell.fixed_board_stationary_observation.v1",
            "inputs": {
                "registration_sha256": _hash(registration),
                "receipt_sha256": _hash(frames / "receipt.json"),
            },
            "assessment": {
                "camera_scene_agrees": True,
                "maximum_reference_center_shift_mm": 1.0,
            },
        },
    )

    def fake_detect(_path: Path):
        detected = {}
        for tag_id, key in enumerate(("T0", "T1", "T2", "T3", "K0", "P0")):
            detected[tag_id] = observation._tag_board_corners(centers[key], 20.0)
        return detected, [640, 480]

    monkeypatch.setattr(observation, "_detect", fake_detect)
    report = observation.build_current_planar_observation(
        tmp_path,
        frames,
        stationary,
        registration,
        overlay,
        created_at="2026-10-16T00:00:00+00:00",
    )

    assert report["status"] == "CURRENT_PLANAR_KEYBOARD_OBSERVATION_READ_ONLY"
    assert report["target_count"] == 46
    assert report["targets"]["K5"]["board_center_xy_mm"] == [55.0, 70.0]
    assert report["targets"]["K5"]["current_center_px"] == [55.0, 70.0]
    assert report["current_frame"]["world_corner_fit_rmse_px"] < 1e-6
    assert report["authority"]["physical_authority"] is False
