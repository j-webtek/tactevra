from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/"scripts"));import stage_r100_straight_up;return stage_r100_straight_up

def test_r100_is_finite_ordered_elbow_wrist_ladder(monkeypatch):
    module=_module(monkeypatch);combined=b"\n".join(module.sources().values())
    assert module.SOURCE_POSITIONS==(2104,2079,2036,2604,2481,2041,1900)
    assert len(module.TARGETS)==16 and module.TARGETS[-1]==(1056,1933)
    assert all(a[0]>b[0] for a,b in zip(module.TARGETS,module.TARGETS[1:]))
    assert all(a[1]>b[1] for a,b in zip(module.TARGETS,module.TARGETS[1:]))
    assert combined.count(b"SyncWritePosEx")==1
    for command in range(300,316):assert f'{{\\"T\\":{command}}}'.encode() in combined
    assert b"requested!=completed_stages_" in combined
    assert b"startup_motion_commands\\\":0" in combined

def test_r100_excludes_broad_surfaces(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    for token in (b"WiFi",b"WebServer",b"LittleFS",b"Preferences",b"servo_.WritePosEx("):assert token not in combined
