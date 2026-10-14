from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import stage_r98_wrist_probe

    return stage_r98_wrist_probe


def test_r98_is_one_shot_wrist_only(monkeypatch):
    module = _module(monkeypatch)
    files = module.sources()
    combined = b"\n".join(files.values())

    assert module.SOURCE_GOALS == (2107, 2075, 2039, 2600, 2233, 2040, 1897)
    assert module.TARGET_GOALS == (2107, 2075, 2039, 2600, 2244, 2040, 1897)
    assert [i for i, pair in enumerate(zip(module.SOURCE_GOALS, module.TARGET_GOALS))
            if pair[0] != pair[1]] == [4]
    assert combined.count(b"SyncWritePosEx") == 1
    assert b'strcmp(line_, "{\\"T\\":198}")' in combined
    assert b"startup_motion_commands\\\":0" in combined
    assert b"maximum_motion_writes\\\":1" in combined
    assert b"SOURCE_POSE_MISMATCH" in combined
    assert b"MOTION_ALREADY_CONSUMED" in combined


def test_r98_excludes_broad_surfaces(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    for token in (b"WiFi", b"WebServer", b"LittleFS", b"Preferences",
                  b"servo_.WritePosEx("):
        assert token not in combined
