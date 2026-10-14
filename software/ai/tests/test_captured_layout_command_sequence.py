from pathlib import Path

from rocell_ai.captured_layout_command_sequence import (
    FAULTS,
    run_captured_layout_sequence,
)
from rocell_ai.first_motion_consolidated import load_consolidated_fixture


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "software/ai/sim/evidence/first_motion_consolidated_tripod_v2.json"


def test_full_sequence_and_faults_remain_in_memory() -> None:
    result = run_captured_layout_sequence(
        load_consolidated_fixture(FIXTURE, workspace=ROOT),
        workspace=ROOT,
        target_id="G",
    )

    assert [row["phase"] for row in result["commands"]] == [
        "START_ASCEND", "START_TRANSIT", "START_DESCEND",
        "TARGET_ASCEND", "TARGET_TRANSIT", "TARGET_DESCEND",
        "PRESS", "RETRACT",
        "RETURN_ASCEND", "RETURN_TRANSIT", "RETURN_DESCEND",
    ]
    assert result["command_count"] == 11
    assert result["all_nominal_commands_settled"] is True
    assert {row["fault"] for row in result["fault_rehearsals"]} == set(FAULTS)
    assert result["all_faults_terminal_no_retry"] is True
    assert all(row["plant_status"].startswith("FAULT_")
               for row in result["fault_rehearsals"])
    assert result["minimum_non_target_key_clearance_mm"] > 0.0
    assert result["official_readiness"] == "NOT_READY_FOR_FIRST_POWERED_MOTION"
    assert result["hardware_write_count"] == result["physical_movement_count"] == 0
    assert result["real_command_count"] == result["transport_count"] == 0
    assert result["physical_authority"] is False
    for row in [*result["commands"], *result["fault_rehearsals"]]:
        assert row["hardware_write_count"] == row["physical_movement_count"] == 0
        assert row["real_transport_open_count"] == 0
        assert row["physical_authority"] is False
