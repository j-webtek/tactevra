from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "software/integrations/isaac_sim/evidence"
ACTUAL_BUNDLE = (
    EVIDENCE / "actual_emitter_joint_schedule_bundle_9e5c878_20260929.json"
)
ACTUAL_RECEIPT = (
    EVIDENCE
    / "actual_emitter_joint_schedule_isaac_replay_9e5c878_20260929.json"
)
ACTUAL_STATUS = ACTUAL_RECEIPT.with_name(
    "actual_emitter_joint_schedule_isaac_replay_9e5c878_20260929.status.json"
)


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def test_actual_emitter_replay_binds_latest_source_and_synthetic_scope():
    bundle = json.loads(ACTUAL_BUNDLE.read_text(encoding="utf-8"))
    unsigned = dict(bundle)
    claimed = unsigned.pop("bundle_sha256")
    assert _digest(_canonical(unsigned)) == claimed
    assert bundle["schema"] == "tactevra.arm_joint_schedule_replay_bundle.v2"
    assert bundle["source"]["arm_commit"] == (
        "9e5c878852da6a6e8509598bce9ce43f218efc70"
    )
    assert bundle["producer"] == {
        "kind": "ACTUAL_SHARED_EMITTER",
        "input_sha256": "b5dc580825819a27a5aba3e58275453aa4c7c0a6b365d24a80a9b2c095f06c6d",
        "payload_sha256": bundle["source"]["batch_sha256"],
        "synthetic_observations": True,
        "deployment_qualification_claimed": False,
    }
    assert bundle["ordered_target_ids"] == ["H", "H", "1", "PERIOD"]
    assert bundle["sample_count"] == 133


def test_actual_emitter_isaac_replay_preserves_prior_metrics_and_authority():
    receipt = json.loads(ACTUAL_RECEIPT.read_text(encoding="utf-8"))
    status = json.loads(ACTUAL_STATUS.read_text(encoding="utf-8"))
    unsigned = dict(receipt)
    claimed = unsigned.pop("receipt_sha256")
    assert _digest(_canonical(unsigned)) == claimed == status["receipt_sha256"]
    assert status["status"] == "PASS"
    assert receipt["source_bindings"]["bundle_file_sha256"] == _digest(
        ACTUAL_BUNDLE.read_bytes()
    )
    assert receipt["ordered_contact_target_ids"] == ["H", "H", "1", "PERIOD"]
    assert receipt["maximum_tool_tip_error_mm"] <= receipt["thresholds"][
        "maximum_tool_tip_error_mm"
    ]
    assert receipt["maximum_joint_tracking_error_rad"] <= receipt["thresholds"][
        "maximum_joint_tracking_error_rad"
    ]
    assert receipt["all_samples_pass"] is True
    assert receipt["physics_steps"] == 0
    assert receipt["controller_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert "INSTALLED_GEOMETRY_COLLISION_SCREENING_REQUIRED" in receipt[
        "remaining_blockers"
    ]
    assert "installed_geometry_collision_screening_not_executed" in receipt[
        "limitations"
    ]
