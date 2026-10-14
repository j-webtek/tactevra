from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/"scripts"));import stage_r101_return_folded;return stage_r101_return_folded

def test_r101_reverses_r100_and_is_finite(monkeypatch):
    module=_module(monkeypatch);combined=b"\n".join(module.sources().values())
    assert module.SOURCE_POSITIONS==(2104,2078,2036,1059,1932,2041,1900)
    assert len(module.TARGETS)==16 and module.TARGETS[-1]==(2604,2485)
    assert all(a[0]<b[0] for a,b in zip(module.TARGETS,module.TARGETS[1:]))
    assert all(a[1]<b[1] for a,b in zip(module.TARGETS,module.TARGETS[1:]))
    assert combined.count(b"SyncWritePosEx")==1
    assert b'\\"candidate\\":\\"r101\\"' in combined
    assert b"startup_motion_commands\\\":0" in combined

def test_r101_excludes_broad_surfaces(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    for token in (b"WiFi",b"WebServer",b"LittleFS",b"Preferences",b"servo_.WritePosEx("):assert token not in combined
