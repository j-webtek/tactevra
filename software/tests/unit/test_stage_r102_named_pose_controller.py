from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/"scripts"));import stage_r102_named_pose_controller;return stage_r102_named_pose_controller

def test_r102_has_only_guarded_named_moves(monkeypatch):
    module=_module(monkeypatch);combined=b"\n".join(module.sources().values())
    assert module.FOLDED_POSITIONS==(2104,2079,2036,2604,2484,2041,1900)
    assert module.UPRIGHT_POSITIONS==(2104,2079,2036,1059,1932,2041,1900)
    assert combined.count(b"SyncWritePosEx")==2
    for command in (105,400,401,402):assert f'{{\\"T\\":{command}}}'.encode() in combined
    assert b"INVALID_NAMED_POSE_TRANSITION" in combined
    assert b"ABORT_HOLD_SENT_TERMINAL_LOCK" in combined
    assert b"elbow_speed\\\":20" in combined and b"wrist_speed\\\":7" in combined
    assert b"startup_motion_commands\\\":0" in combined

def test_r102_excludes_generic_and_network_surfaces(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    for token in (b"WiFi",b"WebServer",b"LittleFS",b"Preferences",b"servo_.WritePosEx("):assert token not in combined
