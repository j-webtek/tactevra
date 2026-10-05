from __future__ import annotations

import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
RECEIPT = (
    WORKSPACE
    / "software/integrations/isaac_sim/evidence"
    / "roarm_m3_fk_parity_20260929.json"
)


def _load() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_fk_receipt_is_hash_bound_and_zero_authority() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    assert receipt["evidence_class"] == "KINEMATIC_PARITY_DIAGNOSTIC_ONLY"
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_fk_receipt_exposes_complete_source_dof_order() -> None:
    receipt = _load()
    expected = [
        "base_link_to_link1", "link1_to_link2", "link2_to_link3",
        "link3_to_link4", "link4_to_link5", "link5_to_gripper_link",
    ]
    assert receipt["source_movable_joint_order"] == expected
    assert receipt["observed_articulation_dof_order"] == expected
    assert receipt["missing_articulation_dofs"] == []
    assert receipt["mapping_complete"] is True


def test_fk_receipt_passes_governed_corpus_inside_thresholds() -> None:
    receipt = _load()
    assert receipt["parity_pass"] is True
    assert receipt["qualification_status"] == "PARITY_ONLY"
    assert [case["name"] for case in receipt["cases"]] == ["zero", "home", "ready"]
    assert all(case["pass"] for case in receipt["cases"])
    assert max(case["translation_error_mm"] for case in receipt["cases"]) < 0.00013
    assert max(case["rotation_error_deg"] for case in receipt["cases"]) <= 0.05


def test_fk_receipt_retains_non_dynamic_scope() -> None:
    receipt = _load()
    assert set(receipt["limitations"]) == {
        "meshless_kinematic_projection",
        "teleport_without_dynamic_step",
        "invalid_imported_mass_and_inertia_placeholders",
        "no_dynamics_collision_contact_or_render_qualification",
        "no_physical_qualification",
    }
