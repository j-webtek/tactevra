from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import stage_r120_commanded_pose_latch
    return stage_r120_commanded_pose_latch


def test_r120_latches_every_recorded_commanded_pose(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    assert b"candidate\\\":\\\"r120" in combined
    assert b"settled_commanded_pose_" in combined
    assert b"withinCommandedTolerance(p,target_pose_)" in combined
    assert b"if(pose==KEYBOARD_FIELD_CAL_3)return kKeyboardFieldCal3Positions" in combined
    assert b"if(pose==KEYBOARD_A_HOVER)return kKeyboardAHoverPositions" in combined
    assert b"CONTACT" not in combined
    assert combined.count(b"SyncWritePosEx") == 1


def test_r120_uses_same_bounded_settle_window_for_named_poses(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    assert b"if(abs(p[i]-expected[i])>20" in combined
    assert b"settled_commanded_pose_=UNKNOWN;target_pose_=requested" in combined
