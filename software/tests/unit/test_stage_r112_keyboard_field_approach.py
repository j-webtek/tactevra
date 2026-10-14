from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/"scripts"))
    import stage_r112_keyboard_field_approach
    return stage_r112_keyboard_field_approach


def test_r112_adds_reversible_ten_mm_approach(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    assert b"candidate\\\":\\\"r112" in combined
    assert b"KEYBOARD_FIELD_APPROACH_10" in combined
    assert b"{2174,2271,1825,2362,2277,2040,2047}" in combined
    for command in range(400,417): assert f'{{\\"T\\":{command}}}'.encode() in combined
    assert b"CONTACT" not in combined
    assert combined.count(b"SyncWritePosEx")==1


def test_r112_approach_has_only_paired_edge(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    assert b"source==KEYBOARD_FIELD_CAL_3&&requested==KEYBOARD_FIELD_APPROACH_10" in combined
    assert b"source==KEYBOARD_FIELD_APPROACH_10&&requested==KEYBOARD_FIELD_CAL_3" in combined
    assert b"INVALID_NAMED_POSE_TRANSITION" in combined
