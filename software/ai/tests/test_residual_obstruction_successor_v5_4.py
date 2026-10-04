from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.audit_residual_obstruction_v5_4_fixture import audit  # noqa: E402
from sim.build_residual_obstruction_successor_v5_4 import build  # noqa: E402

V5 = AI_ROOT / "sim/evidence/residual_obstruction_successor_v5.json"
V5_3 = AI_ROOT / "eval/residual_obstruction_v5_3_safety_gate_amendment_v1.json"
PRETRAINING = AI_ROOT / "sim/evidence/residual_obstruction_pretraining_v1.json"
FIXTURE = AI_ROOT / "sim/evidence/residual_obstruction_successor_v5_4.json"
AUDIT = AI_ROOT / "eval/residual_obstruction_v5_4_fixture_audit_v1.json"
FIXTURE_SCHEMA = AI_ROOT / "schemas/residual_obstruction_successor_fixture_v5_4.schema.json"
AUDIT_SCHEMA = AI_ROOT / "schemas/residual_obstruction_v5_4_fixture_audit_v1.schema.json"
COMMIT = "1d717b246932ce4b3230ecc8f20df886f26caf00"


def _build() -> dict:
    return build(source_commit=COMMIT, v5_path=V5, v5_3_path=V5_3, pretraining_path=PRETRAINING)


def _audit(fixture: Path = FIXTURE) -> dict:
    return audit(source_commit=COMMIT, fixture_path=fixture, v5_path=V5, v5_3_path=V5_3, pretraining_path=PRETRAINING)


def test_exact_rotation_is_balanced_and_evaluation_stays_closed() -> None:
    fixture = _build()
    rotation = fixture["evaluation_rotation"]
    assert rotation["scene_count"] == 224
    assert rotation["observation_identities"] == 96768
    assert rotation["targets_with_minimum_exposure"] == 12
    assert rotation["targets_with_maximum_exposure"] == 63
    assert rotation["every_scene_contains_keyboard_and_phone"] is True
    assert fixture["power_binding"]["assumed_true_rates"] == {
        "pooled_all_obstruction_miss": 0.005,
        "cable_family_miss": 0.005,
        "dark_cable_30_60_miss": 0.005,
        "visible_false_stop": 0.03,
    }
    assert fixture["evaluation_opened"] is False
    assert fixture["render_sequence"]["evaluation_render_before_development_pass_prohibited"] is True


def test_development_support_is_sufficient_for_paired_diagnostics() -> None:
    support = _build()["development_selection"]
    assert support["candidate_count"] == 2
    assert support["same_rows_for_every_candidate"] is True
    assert support["per_target_support"] == {
        "scene_identities": 8,
        "appearance_identities": 3,
        "visible_rows": 96,
        "all_obstruction_rows": 192,
        "cable_abstain_rows": 96,
        "dark_cable_30_60_abstain_rows": 48,
        "dark_cable_10_boundary_visible_rows": 24,
    }
    assert support["adequacy"].endswith("NOT_POWERED_SAFETY")


def test_retained_fixture_and_audit_are_deterministic_and_valid() -> None:
    fixture_schema = json.loads(FIXTURE_SCHEMA.read_text(encoding="utf-8"))
    audit_schema = json.loads(AUDIT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(fixture_schema)
    Draft202012Validator.check_schema(audit_schema)
    retained_fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    retained_audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    Draft202012Validator(fixture_schema).validate(retained_fixture)
    Draft202012Validator(audit_schema).validate(retained_audit)
    assert retained_fixture == _build()
    assert retained_audit == _audit()
    assert retained_audit["status"] == "PASS_FIXTURE_READY_FOR_TRAINING_DEVELOPMENT_RENDERER_IMPLEMENTATION"
    assert retained_audit["evaluation_render_authorized"] is False


def test_audit_rejects_rotation_tampering(tmp_path: Path) -> None:
    fixture = deepcopy(_build())
    fixture["evaluation_rotation"]["scenes"][0]["targets"].reverse()
    core = {key: value for key, value in fixture.items() if key != "bundle_sha256"}
    from eval.audit_residual_obstruction_v5_4_fixture import canonical_hash  # noqa: PLC0415
    fixture["bundle_sha256"] = canonical_hash(core)
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError, match="scene target rotation mismatch"):
        _audit(path)
