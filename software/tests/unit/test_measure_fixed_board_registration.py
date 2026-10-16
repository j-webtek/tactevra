from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "software/scripts/measure_fixed_board_registration.py"
SPEC = importlib.util.spec_from_file_location(
    "measure_fixed_board_registration", SCRIPT
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_installed_tag_corner_order_matches_board_axes() -> None:
    corners = MODULE.tag_board_corners([100.0, 200.0], 40.0)
    np.testing.assert_allclose(
        corners,
        [[80.0, 220.0], [120.0, 220.0], [120.0, 180.0], [80.0, 180.0]],
    )


def test_report_recovers_fixed_planar_mapping_and_holds_out_station_tags(
    tmp_path: Path, monkeypatch
) -> None:
    import cv2

    observations = json.loads(
        (
            ROOT / "software/ai/eval/physical_installed_apriltag_xy_working_v1.json"
        ).read_text(encoding="utf-8")
    )
    observation_path = tmp_path / "observations.json"
    observation_path.write_text(json.dumps(observations), encoding="utf-8")
    frames = tmp_path / "frames"
    frames.mkdir()
    names = ["frame-00.jpg", "frame-01.jpg"]
    receipt_frames = []
    for index, name in enumerate(names):
        payload = f"synthetic-{index}".encode()
        (frames / name).write_bytes(payload)
        receipt_frames.append(
            {
                "file_name": name,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    (frames / "receipt.json").write_text(
        json.dumps(
            {
                "persistent_device_identity": "synthetic-camera",
                "requested_mode": {"width_px": 1920, "height_px": 1080},
                "reopen_cycles": [
                    {
                        "negotiated_mode": {"settings_sha256": "1" * 64},
                        "frames": receipt_frames,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    expected = np.asarray(
        [[2.6, 0.2, 80.0], [-0.1, -1.9, 1010.0], [0.0001, 0.0002, 1.0]],
        dtype=np.float64,
    )
    records = {int(value["id"]): value for value in observations["tags"].values()}

    def fake_detect(path: Path):
        detections = {}
        for tag_id, record in records.items():
            board = MODULE.tag_board_corners(
                record["working_detection_center_xy_mm"], 40.0
            )
            image = cv2.perspectiveTransform(board.reshape(-1, 1, 2), expected).reshape(
                -1, 2
            )
            image += 0.02 if path.name.endswith("01.jpg") else 0.0
            detections[tag_id] = image
        return detections, {tag_id: "synthetic" for tag_id in detections}, [1920, 1080]

    monkeypatch.setattr(MODULE, "detect_tags", fake_detect)
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    report = MODULE.build_report(
        frames, observation_path, created_at="2026-10-16T00:00:00+00:00"
    )

    validation = report["validation"]
    assert validation["fit_eligible_frame_count"] == 2
    assert validation["world_corner_fit_rmse_px"] < 0.02
    assert validation["held_out_station_center_max_error_mm"] < 0.02
    assert report["authority"]["robot_motion"] is False
    assert report["use"]["not_established"]
