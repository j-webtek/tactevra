from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from rocell.application.static_intrinsics_target_reconciliation import (
    StaticIntrinsicsTargetReconciliationError,
    reconcile_static_intrinsics_target,
)


@pytest.fixture
def workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_reconciliation_preserves_completed_board_measurements(
    workspace_root: Path,
) -> None:
    first = reconcile_static_intrinsics_target(workspace_root)
    second = reconcile_static_intrinsics_target(workspace_root)

    assert first == second
    assert first["status"] == "FIXED_BOARD_RECONCILED_MOVABLE_TARGET_REQUIRED"
    board = first["completed_fixed_board_evidence"]
    assert board["board_size_xy_mm"] == [610.0, 457.0]
    assert board["tag_detection_edge_mm"] == 40.0
    assert board["tag_tile_edge_mm"] == 55.0
    assert board["tag_ids"] == [0, 1, 2, 3, 4, 5]
    assert board["repeat_board_or_tag_measurements_required"] is False
    decision = first["intrinsics_observability_decision"]
    assert decision["fixed_board_eligible_as_multiview_intrinsics_dataset"] is False
    assert decision["existing_board_measurements_are_rejected"] is False
    assert first["legacy_target_record"]["eligible_for_capture"] is False
    assert {row["target_class"] for row in first["accepted_existing_target_classes"]} == {
        "CHARUCO",
        "APRILTAG_GRID",
    }
    assert first["collection_policy"]["new_target_print_requested"] is False
    assert first["authority"]["robot_commands_sent"] == 0
    assert len(first["reconciliation_sha256"]) == 64


def test_reconciliation_rejects_changed_board_schema(
    workspace_root: Path, tmp_path: Path,
) -> None:
    relatives = (
        "software/ai/eval/physical_installed_apriltag_xy_working_v1.json",
        "software/ai/eval/b0477_fixed_board_registration_20261016.json",
        "software/ai/eval/static_intrinsics_multiview_capture_contract_20261016.json",
        "software/ai/eval/physical_charuco_probe_blocked_v1.json",
    )
    for relative in relatives:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(workspace_root / relative, destination)
    board_path = (
        tmp_path
        / "software/ai/eval/physical_installed_apriltag_xy_working_v1.json"
    )
    board = json.loads(board_path.read_text(encoding="utf-8"))
    board["schema"] = "wrong"
    board_path.write_text(json.dumps(board), encoding="utf-8")

    with pytest.raises(
        StaticIntrinsicsTargetReconciliationError,
        match="schema differs",
    ):
        reconcile_static_intrinsics_target(tmp_path)
