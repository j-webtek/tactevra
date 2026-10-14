from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import stage_r99_upright_wrist
    return stage_r99_upright_wrist


def test_r99_is_ordered_wrist_only(monkeypatch):
    module = _module(monkeypatch)
    combined = b"\n".join(module.sources().values())
    assert module.SOURCE_POSITIONS == (2104,2079,2036,2604,2241,2041,1895)
    assert module.FIXED_GOALS[:4] == (2107,2075,2039,2600)
    assert module.FIXED_GOALS[5:] == (2040,1897)
    assert module.WRIST_TARGETS == (2321,2401,2485)
    assert combined.count(b"SyncWritePosEx") == 1
    for command in (199,200,201):
        assert f'strcmp(line_, "{{\\"T\\":{command}}}")'.encode() in combined
    assert b"requested_stage != completed_stages_" in combined
    assert b"startup_motion_commands\\\":0" in combined
    assert b"maximum_motion_writes\\\":3" in combined


def test_r99_excludes_broad_surfaces(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    for token in (b"WiFi",b"WebServer",b"LittleFS",b"Preferences",b"servo_.WritePosEx("):
        assert token not in combined
