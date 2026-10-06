from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

AI_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

from rocell_ai.recovery_state_machine import (  # noqa: E402
    load_recovery_fixture,
    run_recovery_campaign,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "ai/sim/evidence/workstream_4_recovery_portable_v1.json"


def test_fixture_is_frozen_portable_and_zero_authority():
    fixture = load_recovery_fixture(FIXTURE, workspace=ROOT.parent)
    assert fixture["fixture_sha256"] == (
        "51e2a8c2706c2b4907719d0391f926fa511c94d702f8af9c27ecd79431b05d78"
    )
    assert fixture["portability_amendment"]["selection_claim"] == (
        "POST_RESULT_REPRODUCTION_ONLY"
    )
    assert fixture["state_machine"]["maximum_press_retries"] == 1
    assert not any(fixture["counters"].values())
    assert fixture["physical_authority"] is False


def test_fixture_rejects_tampering(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["drift"]["translation_mm"][-1] = 11.0
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture hash"):
        load_recovery_fixture(changed, workspace=ROOT.parent)


def test_campaign_is_deterministic_complete_and_zero_authority():
    first = run_recovery_campaign(FIXTURE, workspace=ROOT.parent)
    second = run_recovery_campaign(FIXTURE, workspace=ROOT.parent)
    assert first == second
    assert first["decision"] == "PASS_EXPLORATORY_RECOVERY"
    assert first["metrics"] == {
        "scenario_count": 1244,
        "fault_detection_rate": 1.0,
        "maximum_wrong_characters_before_detection": 1,
        "recoverable_fault_count": 880,
        "recoverable_fault_success_rate": 1.0,
        "abort_expected_count": 364,
        "abort_correctness_rate": 1.0,
        "false_recovery_count": 0,
        "ambiguous_continuation_count": 0,
        "maximum_attempts": 2,
        "detection_latency_ms_range": [20, 1100],
        "total_recovery_time_ms_range": [50, 1900],
    }
    assert first["controller_commands"] == []
    assert first["hardware_writes"] == first["physical_movements"] == 0
    assert first["gpu_jobs"] == 0
    assert first["physical_authority"] is False


def test_rows_correct_single_errors_and_abort_ambiguity():
    result = run_recovery_campaign(FIXTURE, workspace=ROOT.parent)
    rows = {row["scenario_id"]: row for row in result["rows"]}
    wrong = rows["KEYBOARD:SINGLE_WRONG_PRESS:LOW"]
    assert wrong["state_trace"][-4:] == [
        "BACKSPACE_CORRECT",
        "RETRY_ONCE",
        "VERIFY",
        "COMPLETE",
    ]
    outside = rows[
        "PHONE:DRIFT_TRANSLATION_X:+10:CAP_2:IMMEDIATELY_BEFORE_CONTACT:HIGH"
    ]
    assert outside["terminal_state"] == "ABORT"
    assert outside["relocalization_success"] is False
    assert rows["PHONE:UNKNOWN_COMMITTED_TEXT:HIGH"]["state_trace"][-1] == "ABORT"
