from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from rocell.application.static_phase1_intrinsics_intake import (
    StaticPhase1IntrinsicsIntakeError,
    plan_static_phase1_intrinsics_intake,
)


@pytest.fixture
def workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_plan_binds_retained_runtime_and_rejects_synthetic_substitution(
    workspace_root: Path,
) -> None:
    first = plan_static_phase1_intrinsics_intake(workspace_root)
    second = plan_static_phase1_intrinsics_intake(workspace_root)

    assert first == second
    assert first["status"] == "BLOCKED_PHYSICAL_INTRINSICS_INPUTS_REQUIRED"
    assert first["retained_runtime_binding"]["mode"] == {
        "width_px": 1920,
        "height_px": 1080,
        "fps": 60.000240000960005,
        "pixel_format": "YUY2",
    }
    assert first["legacy_rehearsal_comparison"] == {
        "synthetic_mode": {
            "width_px": 5472,
            "height_px": 3648,
            "fps": 9.0,
            "pixel_format": "YUY2",
        },
        "matches_retained_runtime": False,
        "rehearsal_artifact_class": "SYNTHETIC_REHEARSAL_ONLY",
        "eligible_as_physical_intrinsics": False,
    }
    assert set(first["prerequisites"].values()) == {
        "RETAINED_CANDIDATE_PARTIAL"
    }
    assert first["collection_policy"] == {
        "repeat_board_or_tag_center_measurements": False,
        "new_target_print_requested": False,
        "accept_existing_scale_verified_target": True,
        "capture_mode_must_equal_retained_runtime": True,
        "split_must_be_committed_before_solution_review": True,
        "synthetic_rehearsal_may_fill_physical_fields": False,
    }
    assert first["capture_ready"] is False
    assert first["locked_electronic_controls"]["values"]["exposure"] == -3
    assert first["locked_electronic_controls"]["values"]["gain"] == 500
    assert first["next_action"] == (
        "COMPLETE_EXISTING_TARGET_IDENTITY_AND_PRECOMMIT_"
        "MULTIVIEW_INTRINSICS_DATASET"
    )
    assert first["authority"]["camera_opened"] is False
    assert first["authority"]["robot_commands_sent"] == 0
    assert len(first["plan_sha256"]) == 64


def _copy_inputs(source: Path, destination: Path) -> None:
    for relative in (
        "software/config/live_camera_feedback_session_20261015.json",
        "software/config/tool_attachment_profiles.json",
        "software/config/camera_profiles/arducam_b0477_imx283_16mm.json",
        "software/ai/eval/physical_installed_apriltag_xy_working_v1.json",
        "software/ai/eval/b0477_fixed_board_registration_20261016.json",
        "software/ai/eval/b0477_keyboard_overlay_20261016.json",
        "software/ai/eval/static_phase1_retained_evidence_coverage_20261016.json",
        "software/ai/eval/b0477_locked_controls_qualification_20261016.json",
        "software/tests/fixtures/camera/b0477_synthetic_intrinsics_rehearsal.json",
    ):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)


def test_plan_rejects_stale_retained_coverage(
    workspace_root: Path, tmp_path: Path,
) -> None:
    _copy_inputs(workspace_root, tmp_path)
    path = (
        tmp_path
        / "software/ai/eval/static_phase1_retained_evidence_coverage_20261016.json"
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["summary"]["route_partial_candidate_count"] = 8
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(StaticPhase1IntrinsicsIntakeError, match="coverage is stale"):
        plan_static_phase1_intrinsics_intake(tmp_path)
