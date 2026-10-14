from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/"scripts"))
    import stage_r114_keyboard_field_approach_25
    return stage_r114_keyboard_field_approach_25


def test_r114_adds_reversible_five_mm_visual_approach(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    assert b"candidate\\\":\\\"r114" in combined
    assert b"KEYBOARD_FIELD_APPROACH_25" in combined
    assert b"{2174,2305,1791,2393,2213,2040,2047}" in combined
    for command in range(400,421): assert f'{{\\"T\\":{command}}}'.encode() in combined
    assert b"CONTACT" not in combined
    assert combined.count(b"SyncWritePosEx")==1


def test_r114_visual_approach_has_only_paired_edge(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    assert b"source==KEYBOARD_FIELD_APPROACH_20&&requested==KEYBOARD_FIELD_APPROACH_25" in combined
    assert b"source==KEYBOARD_FIELD_APPROACH_25&&requested==KEYBOARD_FIELD_APPROACH_20" in combined
    assert b"INVALID_NAMED_POSE_TRANSITION" in combined
