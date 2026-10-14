from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/"scripts"));import stage_r117_keyboard_field_approach_38;return stage_r117_keyboard_field_approach_38
def test_r117_adds_reversible_ten_mm_visual_approach(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    assert b"candidate\\\":\\\"r117" in combined and b"KEYBOARD_FIELD_APPROACH_38" in combined
    assert b"{2174,2337,1759,2416,2158,2040,2047}" in combined
    for command in range(400,425):assert f'{{\\"T\\":{command}}}'.encode() in combined
    assert b"CONTACT" not in combined and combined.count(b"SyncWritePosEx")==1
def test_r117_close_approach_has_only_paired_edge_and_closest_classifier_first(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    assert b"source==KEYBOARD_FIELD_APPROACH_28&&requested==KEYBOARD_FIELD_APPROACH_38" in combined
    assert b"source==KEYBOARD_FIELD_APPROACH_38&&requested==KEYBOARD_FIELD_APPROACH_28" in combined
    start=combined.find(b"Pose classify")
    close=combined.find(b"if(nearPose(p,kKeyboardFieldApproach38Positions))",start)
    prior=combined.find(b"if(nearPose(p,kKeyboardFieldApproach28Positions))",start)
    assert start>=0 and close>start and prior>close
