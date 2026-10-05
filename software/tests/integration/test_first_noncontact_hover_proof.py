from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    ROOT / "software" / "integrations" / "isaac_sim" / "first_noncontact_hover_proof.py"
)
SPEC = importlib.util.spec_from_file_location("first_noncontact_hover_proof", MODULE_PATH)
assert SPEC and SPEC.loader
PROOF = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROOF)
EVIDENCE = ROOT / "software" / "integrations" / "isaac_sim" / "evidence"
BUNDLE_PATH = EVIDENCE / "actual_emitter_joint_schedule_bundle_9e5c878_20260929.json"
REPLAY_PATH = EVIDENCE / "actual_emitter_joint_schedule_isaac_replay_9e5c878_20260929.json"
PROOF_PATH = EVIDENCE / "first_noncontact_h_hover_proof_20261004.json"


def _inputs():
    bundle_bytes = BUNDLE_PATH.read_bytes()
    replay_bytes = REPLAY_PATH.read_bytes()
    return json.loads(bundle_bytes), bundle_bytes, json.loads(replay_bytes), replay_bytes


def test_retained_replay_proves_contiguous_first_h_hover_without_contact():
    proof = PROOF.build_first_hover_proof(*_inputs())
    assert proof["status"] == "PASS_KINEMATIC_HOVER_WITH_BLOCKERS"
    assert proof["prefix"] == {
        "sample_count": 35,
        "first_sequence": 0,
        "last_sequence": 34,
        "contact_sample_count": 0,
        "endpoint": {
            "action_index": 0,
            "target_id": "H",
            "phase": "HOVER",
            "phase_endpoint": True,
            "time_from_start_ns": 7853052914,
            "expected_tool_tip_board_mm": [216.55, 154.0, 26.0],
        },
    }
    assert proof["conservative_replay_bounds"]["maximum_prefix_tool_tip_error_mm"] < 0.25
    assert proof["producer_scope"]["deployment_qualification_claimed"] is False
    assert proof["hardware_writes"] == proof["physical_movements"] == 0


def test_committed_proof_is_exactly_reproducible():
    expected = PROOF.build_first_hover_proof(*_inputs())
    retained = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
    assert retained == expected
    unsigned = dict(retained)
    claimed = unsigned.pop("proof_sha256")
    assert PROOF._digest(PROOF._canonical(unsigned)) == claimed


def test_mutated_bundle_is_rejected_before_hover_derivation():
    bundle, bundle_bytes, replay, replay_bytes = _inputs()
    bundle["samples"][34]["target_id"] = "I"
    bundle_bytes = json.dumps(bundle, indent=2, sort_keys=True).encode() + b"\n"
    with pytest.raises(ValueError, match="bundle_sha256"):
        PROOF.build_first_hover_proof(bundle, bundle_bytes, replay, replay_bytes)


def test_unbound_replay_receipt_is_rejected():
    bundle, bundle_bytes, replay, replay_bytes = _inputs()
    replay["source_bindings"]["bundle_sha256"] = "0" * 64
    replay_bytes = json.dumps(replay, indent=2, sort_keys=True).encode() + b"\n"
    with pytest.raises(ValueError, match="receipt_sha256"):
        PROOF.build_first_hover_proof(bundle, bundle_bytes, replay, replay_bytes)


def test_contact_before_first_hover_is_rejected_even_with_valid_digest():
    bundle, _, replay, replay_bytes = _inputs()
    bundle = copy.deepcopy(bundle)
    bundle["samples"][10]["phase"] = "CONTACT"
    unsigned = dict(bundle)
    unsigned.pop("bundle_sha256")
    bundle["bundle_sha256"] = PROOF._digest(PROOF._canonical(unsigned))
    bundle_bytes = json.dumps(bundle, indent=2, sort_keys=True).encode() + b"\n"
    replay = copy.deepcopy(replay)
    replay["source_bindings"]["bundle_file_sha256"] = PROOF._digest(bundle_bytes)
    replay["source_bindings"]["bundle_sha256"] = bundle["bundle_sha256"]
    unsigned_replay = dict(replay)
    unsigned_replay.pop("receipt_sha256")
    replay["receipt_sha256"] = PROOF._digest(PROOF._canonical(unsigned_replay))
    replay_bytes = json.dumps(replay, indent=2, sort_keys=True).encode() + b"\n"
    with pytest.raises(ValueError, match="contact occurs"):
        PROOF.build_first_hover_proof(bundle, bundle_bytes, replay, replay_bytes)


def test_any_physical_authority_claim_is_rejected():
    bundle, bundle_bytes, replay, replay_bytes = _inputs()
    replay["physical_authority"] = True
    unsigned = dict(replay)
    unsigned.pop("receipt_sha256")
    replay["receipt_sha256"] = PROOF._digest(PROOF._canonical(unsigned))
    replay_bytes = json.dumps(replay, indent=2, sort_keys=True).encode() + b"\n"
    with pytest.raises(ValueError, match="zero-authority"):
        PROOF.build_first_hover_proof(bundle, bundle_bytes, replay, replay_bytes)
