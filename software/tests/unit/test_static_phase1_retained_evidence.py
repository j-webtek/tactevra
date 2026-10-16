from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from rocell.application.static_phase1_retained_evidence import (
    StaticPhase1RetainedEvidenceError,
    assess_static_phase1_retained_evidence,
)


@pytest.fixture
def workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_retained_evidence_maps_exact_keyboard_closure_without_promotion(
    workspace_root: Path,
) -> None:
    first = assess_static_phase1_retained_evidence(workspace_root)
    second = assess_static_phase1_retained_evidence(workspace_root)

    assert first == second
    assert first["status"] == (
        "RETAINED_EVIDENCE_MAPPED_PHYSICAL_CALIBRATION_BLOCKED"
    )
    assert first["summary"] == {
        "route_artifact_count": 11,
        "route_partial_candidate_count": 9,
        "route_missing_candidate_count": 2,
        "physically_complete_artifact_count": 0,
        "repeated_measurement_requested": False,
    }
    assert first["full_keyboard_closure_ids"][-1] == (
        "phase1_keyboard_outcome_observer"
    )
    by_id = {row["artifact_id"]: row for row in first["coverage"]}
    assert by_id["phase1_measured_tag_map"]["retained_facts"][
        "tag_centers_xy_mm"
    ] == {
        "T0": [27.32, 33.31],
        "T1": [403.66, 38.45],
        "T2": [32.55, 429.5],
        "T3": [581.38, 431.47],
        "K0": [240.17, 265.84],
        "P0": [442.05, 270.39],
    }
    assert by_id["phase1_keyboard_target_map"]["retained_facts"][
        "reviewed_target_count"
    ] == 46
    assert by_id["phase1_static_intrinsics"]["coverage_status"] == (
        "NO_RETAINED_CANDIDATE"
    )
    assert by_id["phase1_arm_board"]["coverage_status"] == (
        "NO_RETAINED_CANDIDATE"
    )
    assert all(row["physical_artifact_created"] is False for row in first["coverage"])
    assert first["authority"] == {
        "physical_artifacts_created": 0,
        "physical_registry_written": False,
        "camera_opened": False,
        "robot_transport_opened": False,
        "robot_commands_sent": 0,
        "physical_authority": False,
    }
    assert len(first["coverage_sha256"]) == 64


def _copy_inputs(source: Path, destination: Path) -> None:
    for relative in (
        "software/config/live_camera_feedback_session_20261015.json",
        "software/config/tool_attachment_profiles.json",
        "software/ai/eval/physical_installed_apriltag_xy_working_v1.json",
        "software/ai/eval/b0477_fixed_board_registration_20261016.json",
        "software/ai/eval/b0477_keyboard_overlay_20261016.json",
        "software/ai/eval/b0477_locked_controls_qualification_20261016.json",
    ):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)


def test_retained_evidence_rejects_changed_tag_measurements(
    workspace_root: Path, tmp_path: Path,
) -> None:
    _copy_inputs(workspace_root, tmp_path)
    path = tmp_path / "software/ai/eval/physical_installed_apriltag_xy_working_v1.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["tags"]["T0"]["working_detection_center_xy_mm"][0] += 1.0
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(StaticPhase1RetainedEvidenceError, match="binding is stale"):
        assess_static_phase1_retained_evidence(tmp_path)
