from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import stage_r108_keyboard_air_action_controller
    return stage_r108_keyboard_air_action_controller


def test_r108_adds_only_guarded_keyboard_air_phases(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    assert b"candidate\\\":\\\"r108" in combined
    assert b"KEYBOARD_A_HOVER" in combined
    assert b"KEYBOARD_A_LOW_AIR" in combined
    assert b"{2047,2093,2021,2618,2197,2040,2047}" in combined
    assert b"{2047,2105,2009,2630,2173,2040,2047}" in combined
    for command in range(105, 106):
        assert f'{{\\"T\\":{command}}}'.encode() in combined
    for command in range(400, 409):
        assert f'{{\\"T\\":{command}}}'.encode() in combined
    assert b"CONTACT" not in combined
    assert combined.count(b"SyncWritePosEx") == 1


def test_r108_limits_new_transition_graph(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    for transition in (
        b"source==AIR_HOVER_A&&requested==KEYBOARD_A_HOVER",
        b"source==KEYBOARD_A_HOVER&&requested==KEYBOARD_A_LOW_AIR",
        b"source==KEYBOARD_A_LOW_AIR&&requested==KEYBOARD_A_HOVER",
        b"source==KEYBOARD_A_HOVER&&requested==AIR_HOVER_A",
    ):
        assert transition in combined
    assert b"INVALID_NAMED_POSE_TRANSITION" in combined
