from __future__ import annotations

import json
from pathlib import Path

import pytest

from rocell.application.b0477_locked_controls_qualification import (
    B0477LockedControlsQualificationError,
    qualify_b0477_locked_controls,
)


def _write_sources(root: Path) -> tuple[Path, Path, Path]:
    device_path = r"\\?\usb#vid_04b4&pid_0477&mi_00#unit#{camera}\global"
    lock = {
        "schema": "rocell.camera_bench_control_lock.v1",
        "device_name": "Arducam B0477 (USB3 20MP)",
        "device_path": device_path,
        "changes": [
            {"name": name, "requested_value": value, "after_value": value, "after_mode": "manual", "readback_matches": True}
            for name, value in (("white_balance", 4500), ("gain", 500), ("exposure", -3))
        ],
        "control_set_calls": 3,
        "camera_only": True,
        "arm_access": False,
    }
    controls = [
        {"name": name, "current_value": value, "reported_mode": "manual"}
        for name, value in {
            "brightness": 0,
            "contrast": 10,
            "saturation": 10,
            "white_balance": 4500,
            "gain": 500,
            "exposure": -3,
        }.items()
    ] + [
        {"name": "iris", "value_observed": False},
        {"name": "focus", "value_observed": False},
    ]
    observation = {
        "schema": "rocell.camera_bench_control_observation.v1",
        "device_name": "Arducam B0477 (USB3 20MP)",
        "device_path": device_path,
        "controls": controls,
    }
    cycles = []
    for cycle in range(2):
        frames = []
        for frame in range(3):
            ordinal = cycle * 3 + frame
            frames.append(
                {
                    "sha256": f"{ordinal + 1:064x}",
                    "scene_assessment": {
                        "all_required_tags_visible": ordinal < 4,
                        "detected_tag36h11_ids": [0, 1, 2, 3, 4, 5] if ordinal < 4 else [1, 2, 3, 4, 5],
                        "mean_luma_8bit": 108.0 + ordinal / 10,
                        "laplacian_variance": 72.0 + ordinal / 10,
                        "fraction_luma_ge_247": 0.00002,
                    },
                }
            )
        cycles.append(
            {
                "reopen_ordinal": cycle,
                "camera_closed": True,
                "negotiated_mode": {
                    "width_px": 1920,
                    "height_px": 1080,
                    "fps": 60.000240000960005,
                    "identity": r"USB\VID_04B4&PID_0477&MI_00\8&257B140A&0&0000",
                    "settings_sha256": "a" * 64,
                    "details": {"observed_pixel_format": "YUY2"},
                },
                "frames": frames,
            }
        )
    capture = {
        "schema": "rocell.live_camera_read_only_intake.v1",
        "friendly_name": "Arducam B0477 (USB3 20MP)",
        "persistent_device_identity": r"USB\VID_04B4&PID_0477&MI_00\8&257B140A&0&0000",
        "camera_closed": True,
        "requested_mode": {"backend": "CAP_DSHOW", "fourcc": "YUY2", "fps": 60.0, "height_px": 1080, "width_px": 1920},
        "reopen_cycles": cycles,
    }
    paths = root / "lock.json", root / "capture.json", root / "observation.json"
    for path, document in zip(paths, (lock, capture, observation), strict=True):
        path.write_text(json.dumps(document), encoding="utf-8")
    return paths


def test_qualification_seals_exact_reopen_stable_controls(tmp_path: Path) -> None:
    first = qualify_b0477_locked_controls(*_write_sources(tmp_path))
    second = qualify_b0477_locked_controls(*_write_sources(tmp_path))
    assert first == second
    assert first["locked_electronic_controls"]["exposure"] == -3
    assert first["locked_electronic_controls"]["gain"] == 500
    assert first["reopen_qualification"]["all_six_tags_frame_count"] == 4
    assert first["authority"]["robot_commands_sent"] == 0
    assert len(first["qualification_sha256"]) == 64


def test_qualification_rejects_changed_manual_readback(tmp_path: Path) -> None:
    lock_path, capture_path, observation_path = _write_sources(tmp_path)
    document = json.loads(observation_path.read_text(encoding="utf-8"))
    document["controls"][4]["current_value"] = 501
    observation_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(B0477LockedControlsQualificationError, match="gain persistence"):
        qualify_b0477_locked_controls(lock_path, capture_path, observation_path)
