from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from rocell.application.static_intrinsics_multiview_contract import (
    StaticIntrinsicsMultiviewContractError,
    build_static_intrinsics_multiview_contract,
)


@pytest.fixture
def workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_contract_freezes_split_and_varied_view_slots(workspace_root: Path) -> None:
    first = build_static_intrinsics_multiview_contract(workspace_root)
    second = build_static_intrinsics_multiview_contract(workspace_root)
    assert first == second
    commitment = first["dataset_commitment"]
    assert commitment["total_slots"] == 32
    assert commitment["training_slots"] == 24
    assert commitment["held_out_slots"] == 8
    assert commitment["split_frozen_before_capture"] is True
    assert commitment["fixed_pose_duplicates_eligible"] is False
    assert len({row["requested_image_region"] for row in commitment["slots"]}) == 9
    assert first["target_intake"]["new_target_print_requested"] is False
    assert first["collection_rules"]["move_target_only"] is True
    assert first["authority"]["robot_commands_sent"] == 0
    assert len(first["contract_sha256"]) == 64


def test_contract_rejects_unqualified_camera_source(
    workspace_root: Path, tmp_path: Path,
) -> None:
    relative = Path(
        "software/ai/eval/b0477_locked_controls_qualification_20261016.json"
    )
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    shutil.copy2(workspace_root / relative, target)
    document = json.loads(target.read_text(encoding="utf-8"))
    document["status"] = "UNQUALIFIED"
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(
        StaticIntrinsicsMultiviewContractError,
        match="controls are not reopen-qualified",
    ):
        build_static_intrinsics_multiview_contract(tmp_path)
