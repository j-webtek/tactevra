from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/"scripts"))
    import stage_r113_keyboard_field_approach_20
    return stage_r113_keyboard_field_approach_20


def test_r113_adds_second_reversible_ten_mm_approach(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    assert b"candidate\\\":\\\"r113" in combined
    assert b"KEYBOARD_FIELD_APPROACH_20" in combined
    assert b"{2174,2293,1803,2383,2234,2040,2047}" in combined
    for command in range(400,419): assert f'{{\\"T\\":{command}}}'.encode() in combined
    assert b"CONTACT" not in combined
    assert combined.count(b"SyncWritePosEx")==1


def test_r113_approach_has_only_paired_edge(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    assert b"source==KEYBOARD_FIELD_APPROACH_10&&requested==KEYBOARD_FIELD_APPROACH_20" in combined
    assert b"source==KEYBOARD_FIELD_APPROACH_20&&requested==KEYBOARD_FIELD_APPROACH_10" in combined
    assert b"INVALID_NAMED_POSE_TRANSITION" in combined
