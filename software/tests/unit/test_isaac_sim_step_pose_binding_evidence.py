from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
RECEIPT = (
    WORKSPACE / "software/integrations/isaac_sim/evidence"
    / "roarm_m3_step_pose_binding_20260929.json"
)


def _load() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pose_binding_receipt_is_canonical_and_zero_authority() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    assert receipt["evidence_class"] == "CAD_POSE_HYPOTHESIS_ONLY"
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_pose_binding_receipt_binds_current_inputs() -> None:
    bindings = _load()["source_bindings"]
    assert bindings["cad_usd_sha256"] == (
        "cfcd4e6170350d948de1976164665ddde99cfad457b72730f7ffcbdd119496d3"
    )
    step_receipt = (
        WORKSPACE / "software/integrations/isaac_sim/evidence"
        / "roarm_m3_step_inspection_20260929.json"
    )
    assert bindings["step_inspection_receipt_file_sha256"] == _digest(step_receipt)
    assert bindings["urdf_sha256"] == _digest(
        WORKSPACE / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    )


def test_pose_binding_derives_expected_cad_frame() -> None:
    transform = _load()["cad_T_urdf_world"]
    assert transform["rotation_row_major"] == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    assert transform["translation_mm"] == [7.005001, 0.0, 0.0]
    assert transform["provenance"] == "derived_from_pinned_cad_bounds"


def test_home_pose_is_strongly_separated_from_fixed_alternatives() -> None:
    receipt = _load()
    candidates = {item["pose_name"]: item for item in receipt["candidates"]}
    assert receipt["selected_pose_hypothesis"] == "home"
    assert receipt["runner_up_pose"] == "ready"
    assert receipt["pose_hypothesis_supported"] is True
    assert candidates["home"]["supported_witness_count"] == 6
    assert candidates["home"]["maximum_residual_mm"] == 2.215515
    assert candidates["home"]["rms_residual_mm"] == 0.90448
    assert candidates["ready"]["maximum_residual_mm"] == 133.237718
    assert candidates["zero"]["maximum_residual_mm"] == 305.130844
    assert receipt["classification_margin_max_residual_mm"] == 131.022203


def test_pose_binding_does_not_admit_link_assignment_or_collision() -> None:
    receipt = _load()
    assert receipt["dynamic_link_assignment_admissible"] is False
    assert receipt["collision_geometry_admissible"] is False
    assert receipt["clearance_replay_admissible"] is False
    assert set(receipt["blockers"]) == {
        "CAD_PRODUCT_GROUPS_NOT_ASSIGNED_TO_DYNAMIC_LINKS",
        "COLLISION_REDUCTION_NOT_REVIEWED",
        "TOOL_GEOMETRY_MISSING",
        "CAMERA_SUPPORT_GEOMETRY_MISSING",
        "ROBOT_PLACEMENT_NOMINAL_UNMEASURED",
        "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
    }
