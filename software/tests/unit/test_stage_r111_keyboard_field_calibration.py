from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/"scripts"))
    import stage_r111_keyboard_field_calibration
    return stage_r111_keyboard_field_calibration


def test_r111_adds_reversible_high_clearance_field_step(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    assert b"candidate\\\":\\\"r111" in combined
    assert b"KEYBOARD_FIELD_CAL_3" in combined
    assert b"{2174,2250,1846,2340,2320,2040,2047}" in combined
    for command in range(400,415): assert f'{{\\"T\\":{command}}}'.encode() in combined
    assert b"CONTACT" not in combined
    assert combined.count(b"SyncWritePosEx")==1


def test_r111_field_step_has_only_paired_edge(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    assert b"source==KEYBOARD_DIAGONAL_CAL_2&&requested==KEYBOARD_FIELD_CAL_3" in combined
    assert b"source==KEYBOARD_FIELD_CAL_3&&requested==KEYBOARD_DIAGONAL_CAL_2" in combined
    assert b"INVALID_NAMED_POSE_TRANSITION" in combined
