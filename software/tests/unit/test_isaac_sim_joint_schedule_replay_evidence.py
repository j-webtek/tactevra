from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "software/integrations/isaac_sim/evidence"
BUNDLE = EVIDENCE / "representative_joint_schedule_bundle_5072_20260929.json"
RECEIPT = EVIDENCE / "joint_schedule_isaac_replay_5072_20260929.json"
STATUS = EVIDENCE / "joint_schedule_isaac_replay_5072_20260929.status.json"


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def test_retained_replay_bundle_is_hash_bound_ordered_and_zero_authority():
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    unsigned = dict(bundle)
    claimed = unsigned.pop("bundle_sha256")
    assert _digest(_canonical(unsigned)) == claimed
    assert bundle["source"]["arm_commit"] == (
        "5072c163152848bd8d78fa3fbc024e32177ac98d"
    )
    assert bundle["ordered_target_ids"] == ["H", "H", "1", "PERIOD"]
    assert bundle["sample_count"] == len(bundle["samples"]) == 133
    assert [
        sample["target_id"] for sample in bundle["samples"]
        if sample["phase"] == "CONTACT" and sample["phase_endpoint"]
    ] == bundle["ordered_target_ids"]
    assert bundle["controller_commands"] == []
    assert bundle["hardware_writes"] == bundle["physical_movements"] == 0
    assert bundle["hardware_access"] is bundle["physical_authority"] is False


def test_retained_isaac_replay_is_bound_and_within_thresholds():
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    unsigned = dict(receipt)
    claimed = unsigned.pop("receipt_sha256")
    assert _digest(_canonical(unsigned)) == claimed == status["receipt_sha256"]
    assert status["status"] == "PASS"
    assert receipt["source_bindings"]["bundle_file_sha256"] == _digest(
        BUNDLE.read_bytes()
    )
    assert receipt["source_bindings"]["virtual_profile_sha256"] == _digest(
        (ROOT / "software/config/virtual_commissioning_profile.json").read_bytes()
    )
    assert receipt["sample_count"] == 133
    assert receipt["ordered_contact_target_ids"] == ["H", "H", "1", "PERIOD"]
    assert receipt["maximum_tool_tip_error_mm"] <= (
        receipt["thresholds"]["maximum_tool_tip_error_mm"]
    )
    assert receipt["maximum_joint_tracking_error_rad"] <= (
        receipt["thresholds"]["maximum_joint_tracking_error_rad"]
    )
    assert receipt["all_samples_pass"] is True


def test_retained_isaac_replay_does_not_claim_collision_or_physical_evidence():
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
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
    assert "no_contact_force_key_travel_or_physical_qualification" in receipt[
        "limitations"
    ]
