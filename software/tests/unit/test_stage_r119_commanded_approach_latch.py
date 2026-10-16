from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import stage_r119_commanded_approach_latch

    return stage_r119_commanded_approach_latch


def test_r119_latches_completed_commanded_approach(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    assert b"candidate\\\":\\\"r119" in combined
    assert b"settled_approach_pose_" in combined
    assert b"withinApproachTolerance(p,target_pose_)" in combined
    assert b"settled_approach_pose_=target_pose_" in combined
    assert b"CONTACT" not in combined
    assert combined.count(b"SyncWritePosEx") == 1


def test_r119_clears_latch_when_next_named_move_starts(monkeypatch):
    combined = b"\n".join(_module(monkeypatch).sources().values())
    marker = b"motion_active_=true;trajectory_done_=false;settled_approach_pose_=UNKNOWN;target_pose_=requested"
    assert marker in combined
