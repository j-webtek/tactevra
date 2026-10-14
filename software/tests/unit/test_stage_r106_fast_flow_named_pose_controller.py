from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import stage_r106_fast_flow_named_pose_controller
    return stage_r106_fast_flow_named_pose_controller


def test_r106_raises_envelope_without_changing_curve_or_period(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    assert b"candidate\\\":\\\"r106" in combined
    assert b"{220,220,220,220,150,220,220}" in combined
    assert b"kDurationMargin=1.05f" in combined
    assert b"speeds[7]={400,400,400,400,400,400,400}" in combined
    assert b"accelerations[7]={30,30,30,30,30,30,30}" in combined
    assert b"kControlPeriodMs=25" in combined
    assert b"u*u*u*(u*(u*6.0f-15.0f)+10.0f)" in combined
    assert combined.count(b"SyncWritePosEx") == 1


def test_r106_preserves_guarded_named_surface(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    assert b"INVALID_NAMED_POSE_TRANSITION" in combined
    assert b"ABORT_HOLD_SENT_TERMINAL_LOCK" in combined
    for command in (105, 400, 401, 402):
        assert f'{{\\"T\\":{command}}}'.encode() in combined
    for token in (b"WiFi", b"WebServer", b"LittleFS", b"Preferences", b"servo_.WritePosEx("):
        assert token not in combined
