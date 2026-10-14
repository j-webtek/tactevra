from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import stage_r105_minimum_time_named_pose_controller
    return stage_r105_minimum_time_named_pose_controller


def test_r105_computes_limit_derived_quintic_duration(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    for token in (
        b"LIMIT_DERIVED_QUINTIC_40HZ", b"computeDurationMs",
        b"velocity_time=1.875f", b"acceleration_time=sqrtf(5.773503f",
        b"jerk_time=cbrtf(60.0f", b"kDurationMargin=1.08f",
    ):
        assert token in combined
    assert b"kTrajectoryDurationMs" not in combined
    assert b"speeds[7]={240,240,240,240,240,240,240}" in combined
    assert combined.count(b"SyncWritePosEx") == 1


def test_r105_preserves_named_pose_guards(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    assert b"INVALID_NAMED_POSE_TRANSITION" in combined
    assert b"ABORT_HOLD_SENT_TERMINAL_LOCK" in combined
    assert b"startup_motion_commands\\\":0" in combined
    for token in (b"WiFi", b"WebServer", b"LittleFS", b"Preferences", b"servo_.WritePosEx("):
        assert token not in combined
