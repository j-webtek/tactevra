from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import stage_r107_air_hover_named_pose_controller
    return stage_r107_air_hover_named_pose_controller


def test_r107_adds_guarded_air_hover_without_contact(monkeypatch):
    module = _module(monkeypatch)
    combined = b"\n".join(module.sources().values())
    assert b"candidate\\\":\\\"r107" in combined
    assert b"AIR_HOVER_A" in combined
    assert b"{2041,2081,2033,2609,2233,2041,2047}" in combined
    assert b"{2047,2075,2039,2600,2233,2040,2047}" in combined
    for command in (105, 400, 401, 402, 403, 404):
        assert f'{{\\"T\\":{command}}}'.encode() in combined
    assert b"CONTACT" not in combined
    assert combined.count(b"SyncWritePosEx") == 1


def test_r107_preserves_fast_flow_engine_and_transition_guard(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    assert b"LIMIT_DERIVED_QUINTIC_40HZ" in combined
    assert b"kDurationMargin=1.05f" in combined
    assert b"source==FOLDED&&requested==AIR_HOVER_A" in combined
    assert b"source==AIR_HOVER_A&&requested==FOLDED" in combined
    assert b"INVALID_NAMED_POSE_TRANSITION" in combined
    for token in (b"WiFi", b"WebServer", b"LittleFS", b"Preferences", b"servo_.WritePosEx("):
        assert token not in combined
