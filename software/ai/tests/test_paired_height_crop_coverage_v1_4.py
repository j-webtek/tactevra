from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.screen_paired_height_crop_coverage_v1_4 import select_center  # noqa: E402


@dataclass(frozen=True)
class _Center:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class _Target:
    device: str
    target_id: str
    center: _Center


def test_center_selection_maximizes_complete_crop_and_reports_tolerance() -> None:
    targets = [
        _Target("keyboard", "left", _Center(25.0, 50.0, 0.0)),
        _Target("phone", "right", _Center(75.0, 50.0, 0.0)),
    ]
    result = select_center(
        targets,
        [100],
        width_px=100,
        height_px=100,
        focal_px=100.0,
        extent_mm=20.0,
        preferred_xy_mm=(45.0, 50.0),
    )
    assert result["selected_center_board_xy_mm"] == [50.0, 50.0]
    assert result["maximum_minimum_floating_border_px"] == 15.0
    assert result["full_containment_center_intervals_mm"]["x"] == [35.0, 65.0]
    assert result["mounting_tolerance"]["isotropic_before_alignment_reserve_mm"] == 15.0
