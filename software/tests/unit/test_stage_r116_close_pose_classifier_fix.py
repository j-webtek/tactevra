from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/"scripts"));import stage_r116_close_pose_classifier_fix;return stage_r116_close_pose_classifier_fix
def test_r116_prefers_close_pose_before_overlapping_predecessor(monkeypatch):
    combined=b"\n".join(_module(monkeypatch).sources().values())
    assert b"candidate\\\":\\\"r116" in combined
    start=combined.find(b"Pose classify")
    close=combined.find(b"if(nearPose(p,kKeyboardFieldApproach28Positions))",start)
    prior=combined.find(b"if(nearPose(p,kKeyboardFieldApproach25Positions))",start)
    assert start>=0 and close>start and prior>close
    assert b"{2174,2312,1784,2399,2200,2040,2047}" in combined
    assert b"CONTACT" not in combined and combined.count(b"SyncWritePosEx")==1
