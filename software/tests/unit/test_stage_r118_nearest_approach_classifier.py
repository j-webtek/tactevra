from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import stage_r118_nearest_approach_classifier

    return stage_r118_nearest_approach_classifier


def test_r118_uses_bounded_nearest_approach_classifier(monkeypatch):
    module = _module(monkeypatch)
    combined = b"\n".join(module.sources().values())
    assert b"candidate\\\":\\\"r118" in combined
    assert b"boundedApproachError" in combined
    assert b"classifyKeyboardApproach" in combined
    assert b"max_error<=20" in combined
    assert b"CONTACT" not in combined
    assert combined.count(b"SyncWritePosEx") == 1


def test_r118_classifies_observed_settle_as_28_and_nominal_endpoints_exactly(monkeypatch):
    module = _module(monkeypatch)
    observed = (2167, 2330, 1777, 2408, 2199, 2041, 2042)
    assert module.classify_keyboard_approach(observed) == "KEYBOARD_FIELD_APPROACH_28"
    for name, positions in module.APPROACH_POSES.items():
        assert module.classify_keyboard_approach(positions) == name


def test_r118_rejects_pose_outside_bounded_tolerance(monkeypatch):
    module = _module(monkeypatch)
    outside = tuple(value + 21 for value in module.APPROACH_POSES["KEYBOARD_FIELD_APPROACH_28"])
    assert module.classify_keyboard_approach(outside) is None
