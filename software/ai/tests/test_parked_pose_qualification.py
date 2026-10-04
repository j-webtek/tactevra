from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import jsonschema
import pytest


AI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI))

from eval.evaluate_parked_pose_qualification import (  # noqa: E402
    CAMPAIGN_SCHEMA,
    RESULT_SCHEMA,
    canonical_hash,
    evaluate,
    exact_binomial_interval,
    load_strict_json,
    missing_campaign_receipt,
)


def _h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _decision(known: bool, residual: str) -> tuple[str, str, str]:
    geometric = "ABSTAIN" if known else "VISIBLE"
    learned = "ABSTAIN" if residual != "NONE" else "VISIBLE"
    fused = "ABSTAIN" if "ABSTAIN" in {geometric, learned} else "VISIBLE"
    return geometric, learned, fused


def _synthetic(index: int) -> dict:
    known = index == 0
    residual = "CABLE" if index == 1 else "TOOL" if index == 2 else "NONE"
    geometric, learned, fused = _decision(known, residual)
    return {
        "observation_id": f"synthetic-{index:03d}", "image_sha256": _h(f"image-s-{index}"),
        "known_self_occlusion": known, "residual_obstruction": residual,
        "geometric_decision": geometric, "residual_decision": learned, "fused_decision": fused,
        "lighting_variant_id": f"light-{index % 2}",
        "calibration_perturbation_id": f"cal-{index % 2}",
        "runtime_like_projection_sha256": _h(f"projection-{index}"),
        "truth_mask_label_sha256": _h(f"truth-{index}"),
        "truth_mask_used_as_model_input": False,
    }


def _physical(index: int) -> dict:
    known = index % 10 == 0
    residual = "TOOL" if index % 10 == 1 else "CABLE" if index % 10 == 2 else "NONE"
    geometric, learned, fused = _decision(known, residual)
    return {
        "observation_id": f"physical-{index:03d}", "image_sha256": _h(f"image-p-{index}"),
        "known_self_occlusion": known, "residual_obstruction": residual,
        "geometric_decision": geometric, "residual_decision": learned, "fused_decision": fused,
        "session_id": f"session-{index // 10}", "lighting_condition_id": f"physical-light-{index % 2}",
        "park_completed": True,
        "settled_before_capture": True, "exposure_binding_sha256": _h(f"exposure-{index}"),
        "measured_feedback_bracket_sha256": _h(f"feedback-{index}"),
        "projection_evidence_sha256": _h(f"projection-p-{index}"),
        "residual_observation_sha256": _h(f"residual-{index}"),
        "charuco_capture_sha256": _h(f"charuco-{index}"),
        "park_repeatability_mm": 0.2, "park_repeatability_evidence_sha256": _h(f"repeat-{index}"),
        "charuco_drift_mm": 0.3, "charuco_drift_evidence_sha256": _h(f"drift-{index}"),
    }


def _campaign() -> dict:
    core = {
        "schema": "rocell.ai_parked_pose_qualification_campaign.v1",
        "scope": "SUPERVISED_PARKED_OBSERVATION_EVIDENCE_ONLY",
        "campaign_id": "parked-pose-fixture-v1", "source_commit": "1" * 40,
        "domain_id": "fixed-overview-physical-v1",
        **{field: _h(field) for field in (
            "park_pose_identity_sha256", "camera_calibration_sha256", "camera_to_board_sha256",
            "robot_visual_mesh_sha256", "target_catalog_sha256", "projection_qualification_sha256",
            "residual_model_sha256", "fusion_policy_sha256", "repeatability_qualification_sha256",
            "charuco_drift_qualification_sha256",
        )},
        "requirements": {
            "minimum_synthetic_observations": 6,
            "required_lighting_variant_ids": ["light-0", "light-1"],
            "required_calibration_perturbation_ids": ["cal-0", "cal-1"],
            "required_synthetic_residual_obstructions": ["CABLE", "TOOL"],
            "minimum_physical_completed_cycles": 30, "minimum_physical_sessions": 3,
            "required_physical_residual_obstructions": ["CABLE", "TOOL"],
            "required_physical_lighting_condition_ids": ["physical-light-0", "physical-light-1"],
            "maximum_park_repeatability_mm": 0.5, "maximum_charuco_drift_mm": 0.5,
        },
        "synthetic_observations": [_synthetic(index) for index in range(6)],
        "physical_cycles": [_physical(index) for index in range(30)],
        "collection_effects": {
            "hardware_write_count": 30, "physical_movement_count": 30,
            "authorization_evidence_sha256": _h("collection-authorization"),
        },
        "controller_authority": False, "hardware_writes": 0, "physical_movements": 0,
        "limitations": ["In-memory structural fixture; not retained physical evidence"],
    }
    return {**core, "campaign_sha256": canonical_hash(core)}


def _write(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _rehash(document: dict) -> None:
    document["campaign_sha256"] = canonical_hash(
        {key: value for key, value in document.items() if key != "campaign_sha256"}
    )


def test_schemas_and_missing_campaign_receipt_are_strict():
    for path in (CAMPAIGN_SCHEMA, RESULT_SCHEMA):
        jsonschema.Draft202012Validator.check_schema(load_strict_json(path))
    result = missing_campaign_receipt()
    assert result["status"] == "INCOMPLETE"
    assert result["incomplete_reasons"] == ["campaign_not_collected"]
    assert result["campaign_sha256"] is None
    assert result["physical_deployment_qualified"] is False
    assert result["hardware_writes"] == result["physical_movements"] == 0


def test_exact_clopper_pearson_interval_keeps_small_sample_limit_visible():
    interval = exact_binomial_interval(0, 30)
    assert interval["lower_95"] == 0.0
    assert interval["upper_95"] == pytest.approx(1.0 - 0.025 ** (1.0 / 30.0))
    assert interval["upper_95"] > 0.10


def test_complete_structural_fixture_reaches_owner_review_only(tmp_path):
    result = evaluate(_write(tmp_path / "campaign.json", _campaign()))
    assert result["status"] == "EVIDENCE_COMPLETE_FOR_OWNER_REVIEW"
    assert all(result["criteria"].values())
    assert result["physical"]["completed_cycle_count"] == 30
    assert result["physical"]["session_count"] == 3
    assert result["physical"]["false_stops"]["trials"] == 21
    assert result["physical"]["false_stops"]["upper_95"] > 0.10
    assert result["physical_deployment_qualified"] is False
    assert result["controller_authority"] is False


def test_missing_cycles_and_sessions_remain_incomplete(tmp_path):
    campaign = _campaign()
    campaign["physical_cycles"] = campaign["physical_cycles"][:20]
    _rehash(campaign)
    result = evaluate(_write(tmp_path / "campaign.json", campaign))
    assert result["status"] == "INCOMPLETE"
    assert "physical_minimum_completed_cycles_met" in result["incomplete_reasons"]
    assert "physical_minimum_sessions_met" in result["incomplete_reasons"]


def test_tampering_duplicate_identity_and_non_or_fusion_are_rejected(tmp_path):
    campaign = _campaign()
    campaign["campaign_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="campaign SHA-256 mismatch"):
        evaluate(_write(tmp_path / "tampered.json", campaign))

    campaign = _campaign()
    campaign["physical_cycles"][0]["observation_id"] = campaign["synthetic_observations"][0]["observation_id"]
    _rehash(campaign)
    with pytest.raises(ValueError, match="duplicate observation identity"):
        evaluate(_write(tmp_path / "duplicate.json", campaign))

    campaign = _campaign()
    campaign["physical_cycles"][0]["fused_decision"] = "VISIBLE"
    _rehash(campaign)
    with pytest.raises(ValueError, match="fusion is not conservative OR"):
        evaluate(_write(tmp_path / "fusion.json", campaign))


def test_truth_mask_input_unsettled_cycles_and_unbound_collection_fail_closed(tmp_path):
    campaign = _campaign()
    campaign["synthetic_observations"][0]["truth_mask_used_as_model_input"] = True
    _rehash(campaign)
    with pytest.raises(ValueError, match="schema validation failed"):
        evaluate(_write(tmp_path / "truth-input.json", campaign))

    campaign = _campaign()
    campaign["physical_cycles"][0]["settled_before_capture"] = False
    _rehash(campaign)
    result = evaluate(_write(tmp_path / "unsettled.json", campaign))
    assert result["status"] == "INCOMPLETE"
    assert result["criteria"]["physical_all_rows_completed_and_settled"] is False

    campaign = _campaign()
    campaign["collection_effects"]["authorization_evidence_sha256"] = None
    _rehash(campaign)
    with pytest.raises(ValueError, match="authorized collection effects"):
        evaluate(_write(tmp_path / "unbound.json", campaign))


def test_duplicate_json_fields_are_rejected(tmp_path):
    path = tmp_path / "duplicate-fields.json"
    path.write_text('{"schema":"one","schema":"two"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON field"):
        load_strict_json(path)
