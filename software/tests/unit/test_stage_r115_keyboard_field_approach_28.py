from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/"scripts"));import stage_r115_keyboard_field_approach_28;return stage_r115_keyboard_field_approach_28
def test_r115_adds_reversible_three_mm_close_approach(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    assert b"candidate\\\":\\\"r115" in combined and b"KEYBOARD_FIELD_APPROACH_28" in combined
    assert b"{2174,2312,1784,2399,2200,2040,2047}" in combined
    for command in range(400,423):assert f'{{\\"T\\":{command}}}'.encode() in combined
    assert b"CONTACT" not in combined and combined.count(b"SyncWritePosEx")==1
def test_r115_close_approach_has_only_paired_edge(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    assert b"source==KEYBOARD_FIELD_APPROACH_25&&requested==KEYBOARD_FIELD_APPROACH_28" in combined
    assert b"source==KEYBOARD_FIELD_APPROACH_28&&requested==KEYBOARD_FIELD_APPROACH_25" in combined
