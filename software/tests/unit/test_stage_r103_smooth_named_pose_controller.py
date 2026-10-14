from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import stage_r103_smooth_named_pose_controller

    return stage_r103_smooth_named_pose_controller


def test_r103_uses_one_clocked_quintic_trajectory(monkeypatch):
    module = _module(monkeypatch)
    combined = b"\n".join(module.sources().values())
    assert module.FOLDED_POSITIONS == (2104, 2079, 2036, 2604, 2484, 2041, 1900)
    assert module.UPRIGHT_POSITIONS == (2104, 2079, 2036, 1059, 1932, 2041, 1900)
    assert combined.count(b"SyncWritePosEx") == 1
    assert b"kTrajectoryDurationMs=20000" in combined
    assert b"kControlPeriodMs=25" in combined
    assert b"u*u*u*(u*(u*6.0f-15.0f)+10.0f)" in combined
    assert b"trajectory_progress_permille" in combined
    for command in (105, 400, 401, 402):
        assert f'{{\\"T\\":{command}}}'.encode() in combined


def test_r103_keeps_guardrails_and_no_startup_or_network_motion(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    assert b"INVALID_NAMED_POSE_TRANSITION" in combined
    assert b"ABORT_HOLD_SENT_TERMINAL_LOCK" in combined
    assert b"startup_motion_commands\\\":0" in combined
    for token in (b"WiFi", b"WebServer", b"LittleFS", b"Preferences", b"servo_.WritePosEx("):
        assert token not in combined
