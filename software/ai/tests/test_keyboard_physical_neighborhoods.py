from pathlib import Path

from ai.sim import keyboard_physical_neighborhoods as subject


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = (
    ROOT
    / "software/ai/sim/evidence/workstream_2_keyboard_physical_neighborhoods_v1.json"
)


def test_layout_is_complete_nonoverlapping_and_provenanced():
    fixture = subject.load_fixture(FIXTURE)
    result = subject.deduplicated_neighborhoods(fixture)
    assert len(result["layout"]) == 51
    assert result["overlap_pairs"] == []
    assert result["signature_count"] == 45
    assert all(
        row["center_source"] and row["dimension_source"] for row in result["layout"]
    )


def test_stabilized_targets_are_never_signature_merged():
    fixture = subject.load_fixture(FIXTURE)
    result = subject.deduplicated_neighborhoods(fixture)
    lookup = {row["target_id"]: row for row in result["neighborhoods"]}
    signatures = {
        lookup[target]["signature_sha256"] for target in ("SHIFT", "ENTER", "SPACE")
    }
    assert len(signatures) == 3
    assert all(
        lookup[target]["mechanism_class"].startswith("STABILIZED")
        for target in ("SHIFT", "ENTER", "SPACE")
    )


def test_enter_and_space_geometry_do_not_overlap_any_key():
    fixture = subject.load_fixture(FIXTURE)
    layout = subject.physical_layout(fixture)
    assert not [
        row
        for row in subject.overlap_pairs(layout)
        if {row["left"], row["right"]} & {"ENTER", "SPACE"}
    ]
