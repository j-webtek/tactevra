from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import stage_r109_keyboard_forward_calibration
    return stage_r109_keyboard_forward_calibration


def test_r109_adds_one_reversible_forward_calibration_pose(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    assert b"candidate\\\":\\\"r109" in combined
    assert b"KEYBOARD_FORWARD_CAL_1" in combined
    assert b"{2047,2136,1960,2549,2224,2040,2047}" in combined
    for command in range(400, 411):
        assert f'{{\\"T\\":{command}}}'.encode() in combined
    assert b"CONTACT" not in combined
    assert combined.count(b"SyncWritePosEx") == 1


def test_r109_forward_calibration_is_guarded_and_reversible(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    assert b"source==KEYBOARD_A_HOVER&&requested==KEYBOARD_FORWARD_CAL_1" in combined
    assert b"source==KEYBOARD_FORWARD_CAL_1&&requested==KEYBOARD_A_HOVER" in combined
    assert b"INVALID_NAMED_POSE_TRANSITION" in combined
