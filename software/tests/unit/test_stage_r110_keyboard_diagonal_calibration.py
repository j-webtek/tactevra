from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import stage_r110_keyboard_diagonal_calibration
    return stage_r110_keyboard_diagonal_calibration


def test_r110_adds_only_reversible_diagonal_air_calibration(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    assert b"candidate\\\":\\\"r110" in combined
    assert b"KEYBOARD_DIAGONAL_CAL_2" in combined
    assert b"{2105,2180,1916,2473,2257,2040,2047}" in combined
    for command in range(400, 413):
        assert f'{{\\"T\\":{command}}}'.encode() in combined
    assert b"CONTACT" not in combined
    assert combined.count(b"SyncWritePosEx") == 1


def test_r110_diagonal_calibration_transition_is_narrow(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    assert b"source==KEYBOARD_FORWARD_CAL_1&&requested==KEYBOARD_DIAGONAL_CAL_2" in combined
    assert b"source==KEYBOARD_DIAGONAL_CAL_2&&requested==KEYBOARD_FORWARD_CAL_1" in combined
    assert b"INVALID_NAMED_POSE_TRANSITION" in combined
