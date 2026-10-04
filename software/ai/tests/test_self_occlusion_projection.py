"""Read-only self-occlusion projection contract tests."""

# ruff: noqa: E402

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import jsonschema
import pytest


AI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI))

from rocell_ai.scene_observation import canonical_hash
from rocell_ai.self_occlusion_projection import (
    ProjectionEvidenceError,
    TrustedSyntheticProjectionQualificationV1,
    assess_projection_evidence,
    validate_projection_evidence,
)


H = {
    letter: hashlib.sha256(letter.encode("ascii")).hexdigest()
    for letter in "abcdefghijklmno"
}
NOW_NS = 2_000_000_200
DOMAIN = "synthetic-fixed-overview-v1"
CLOCK = "sim-exposure-clock-v1"


def _qualification() -> dict[str, object]:
    core = {
        "schema": "rocell.ai_self_occlusion_projection_qualification.v1",
        "scope": "SYNTHETIC_OFFLINE_ONLY",
        "domain_id": DOMAIN,
        "camera_calibration_sha256": H["a"],
        "camera_to_board_sha256": H["b"],
        "robot_visual_mesh_sha256": H["c"],
        "target_catalog_sha256": H["d"],
        "uncertainty_profile_sha256": H["e"],
        "projection_implementation_sha256": H["f"],
        "clock_id": CLOCK,
        "feedback_source": "MEASURED_SERVO_POSITION",
        "feedback_source_sha256": H["l"],
        "clock_correlation_sha256": H["m"],
        "interpolation_policy_id": "LINEAR_MEASURED_POSITION_BRACKET_V1",
        "interpolation_policy_sha256": H["g"],
        "maximum_feedback_bracket_gap_ns": 400,
        "maximum_evidence_age_ns": 500,
        "dilation_bound_px": 2.5,
        "dilation_derivation_sha256": H["h"],
        "charuco_reprojection_evidence_sha256": H["i"],
        "feedback_resolution_noise_evidence_sha256": H["j"],
        "backlash_repeatability_evidence_sha256": H["k"],
        "visible_overlap_upper": 0.18,
        "ambiguity_overlap_upper": 0.22,
        "physical_deployment_qualified": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": ["Synthetic contract fixture; no deployment qualification"],
    }
    return {**core, "qualification_sha256": canonical_hash(core)}


def _evidence(qualification: dict[str, object]) -> dict[str, object]:
    core = {
        "schema": "rocell.ai_self_occlusion_projection_evidence.v1",
        "scope": "SYNTHETIC_OFFLINE_ONLY",
        "projection_id": "projection-fixture-001",
        "domain_id": DOMAIN,
        "frame": {
            "frame_id": "frame-fixture-001",
            "image_sha256": H["n"],
            "exposure_timestamp_ns": 2_000_000_000,
            "exposure_start_ns": 1_999_999_980,
            "exposure_end_ns": 2_000_000_020,
            "clock_id": CLOCK,
        },
        "feedback_bracket": {
            "source": "MEASURED_SERVO_POSITION",
            "feedback_source_sha256": qualification["feedback_source_sha256"],
            "pre_sample_sha256": H["a"],
            "pre_timestamp_ns": 1_999_999_900,
            "post_sample_sha256": H["b"],
            "post_timestamp_ns": 2_000_000_100,
            "clock_id": CLOCK,
            "clock_correlation_sha256": qualification["clock_correlation_sha256"],
            "interpolation_policy_id": "LINEAR_MEASURED_POSITION_BRACKET_V1",
            "interpolation_policy_sha256": H["g"],
            "interpolated_measured_state_sha256": H["o"],
        },
        "projection_bindings": {
            "qualification_sha256": qualification["qualification_sha256"],
            **{
                field: qualification[field]
                for field in (
                    "camera_calibration_sha256",
                    "camera_to_board_sha256",
                    "robot_visual_mesh_sha256",
                    "target_catalog_sha256",
                    "uncertainty_profile_sha256",
                    "projection_implementation_sha256",
                )
            },
        },
        "dilation": {
            "bound_px": qualification["dilation_bound_px"],
            "derivation_sha256": qualification["dilation_derivation_sha256"],
        },
        "target_results": [
            {
                "target_id": "H",
                "center_covered": False,
                "safe_region_overlap_fraction": 0.10,
                "dilated_safe_region_overlap_fraction": 0.17,
                "decision": "VISIBLE",
            },
            {
                "target_id": "PERIOD",
                "center_covered": False,
                "safe_region_overlap_fraction": 0.16,
                "dilated_safe_region_overlap_fraction": 0.18,
                "decision": "ABSTAIN_AMBIGUOUS",
            },
            {
                "target_id": "ENTER",
                "center_covered": False,
                "safe_region_overlap_fraction": 0.21,
                "dilated_safe_region_overlap_fraction": 0.23,
                "decision": "ABSTAIN_SELF_OCCLUDED",
            },
            {
                "target_id": "1",
                "center_covered": True,
                "safe_region_overlap_fraction": 0.01,
                "dilated_safe_region_overlap_fraction": 0.02,
                "decision": "ABSTAIN_SELF_OCCLUDED",
            },
        ],
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": ["Projection fixture is synthetic and read only"],
    }
    return {**core, "evidence_sha256": canonical_hash(core)}


def _rehash(document: dict[str, object]) -> dict[str, object]:
    document["evidence_sha256"] = canonical_hash(
        {key: value for key, value in document.items() if key != "evidence_sha256"}
    )
    return document


def _fixture():
    qualification = _qualification()
    trusted = TrustedSyntheticProjectionQualificationV1(qualification)
    evidence = _evidence(qualification)
    return qualification, trusted, evidence


def _assess(evidence, trusted, **overrides):
    values = {
        "trusted_synthetic_qualifications": {trusted.sha256: trusted},
        "expected_domain_id": DOMAIN,
        "now_timestamp_ns": NOW_NS,
        "now_clock_id": CLOCK,
    }
    values.update(overrides)
    return assess_projection_evidence(evidence, **values)


def test_schema_and_validator_accept_read_only_synthetic_evidence():
    qualification, trusted, evidence = _fixture()
    for name, document in (
        ("self_occlusion_projection_qualification_v1.schema.json", qualification),
        ("self_occlusion_projection_evidence_v1.schema.json", evidence),
    ):
        schema = json.loads((AI / "schemas" / name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(document)
    report = _assess(evidence, trusted)
    assert report["decision"] == "ACCEPTED_SYNTHETIC_OFFLINE_ONLY"
    assert report["reasons"] == []
    assert [item["decision"] for item in report["target_decisions"]] == [
        "VISIBLE",
        "ABSTAIN_AMBIGUOUS",
        "ABSTAIN_SELF_OCCLUDED",
        "ABSTAIN_SELF_OCCLUDED",
    ]
    assert report["hardware_writes"] == report["physical_movements"] == 0
    assert report["physical_authority"] is False


def test_evidence_cannot_self_install_qualification():
    _, trusted, evidence = _fixture()
    report = _assess(evidence, trusted, trusted_synthetic_qualifications={})
    assert report["decision"] == "ABSTAIN"
    assert report["reasons"] == ["projection_qualification_not_installed"]


@pytest.mark.parametrize("source", ["COMMANDED_POSITION", "LATEST_POSITION"])
def test_non_measured_feedback_sources_are_rejected(source):
    _, _, evidence = _fixture()
    evidence["feedback_bracket"]["source"] = source
    with pytest.raises(ProjectionEvidenceError, match="source is prohibited"):
        validate_projection_evidence(_rehash(evidence))


@pytest.mark.parametrize(
    "mutation, message",
    [
        ("missing_pre", "fields differ"),
        ("clock", "clocks differ"),
        ("not_bracketed", "does not bracket"),
        ("raw_joint", "fields differ"),
        ("authority", "physical authority"),
    ],
)
def test_missing_or_tampered_temporal_and_authority_fields_are_rejected(mutation, message):
    _, _, evidence = _fixture()
    if mutation == "missing_pre":
        del evidence["feedback_bracket"]["pre_timestamp_ns"]
    elif mutation == "clock":
        evidence["feedback_bracket"]["clock_id"] = "different-clock"
    elif mutation == "not_bracketed":
        evidence["feedback_bracket"]["pre_timestamp_ns"] = 2_000_000_000
    elif mutation == "raw_joint":
        evidence["feedback_bracket"]["joint_positions"] = [0, 0, 0, 0, 0]
    else:
        evidence["physical_authority"] = True
    with pytest.raises(ProjectionEvidenceError, match=message):
        validate_projection_evidence(_rehash(evidence))


def test_wide_bracket_stale_evidence_and_wrong_clock_abstain():
    _, trusted, evidence = _fixture()
    wide = deepcopy(evidence)
    wide["feedback_bracket"]["pre_timestamp_ns"] = 1_999_999_600
    wide_report = _assess(_rehash(wide), trusted)
    stale_report = _assess(evidence, trusted, now_timestamp_ns=2_000_000_521)
    clock_report = _assess(evidence, trusted, now_clock_id="different-clock")
    assert wide_report["reasons"] == ["projection_feedback_bracket_too_wide"]
    assert stale_report["reasons"] == ["projection_evidence_stale"]
    assert clock_report["reasons"] == ["projection_clock_unverified"]


def test_domain_binding_and_calibrated_dilation_mismatches_abstain():
    _, trusted, evidence = _fixture()
    domain_report = _assess(evidence, trusted, expected_domain_id="other-domain")
    altered = deepcopy(evidence)
    altered["dilation"]["bound_px"] = 3.0
    altered_report = _assess(_rehash(altered), trusted)
    assert domain_report["reasons"] == ["projection_domain_unverified"]
    assert altered_report["reasons"] == ["projection_dilation_unverified"]


def test_feedback_source_and_clock_correlation_hashes_must_match_policy():
    _, trusted, evidence = _fixture()
    altered = deepcopy(evidence)
    altered["feedback_bracket"]["feedback_source_sha256"] = H["c"]
    altered["feedback_bracket"]["clock_correlation_sha256"] = H["d"]
    report = _assess(_rehash(altered), trusted)
    assert report["reasons"] == [
        "projection_measured_feedback_source_unverified",
        "projection_clock_correlation_unverified",
    ]


def test_identity_mismatch_and_hash_tampering_fail_closed():
    _, trusted, evidence = _fixture()
    altered = deepcopy(evidence)
    altered["projection_bindings"]["robot_visual_mesh_sha256"] = H["o"]
    report = _assess(_rehash(altered), trusted)
    assert report["reasons"] == ["projection_robot_visual_mesh_mismatch"]
    altered["evidence_sha256"] = H["a"]
    with pytest.raises(ProjectionEvidenceError, match="hash mismatch"):
        _assess(altered, trusted)


@pytest.mark.parametrize(
    "center,dilated,decision",
    [
        (False, 0.179999, "VISIBLE"),
        (False, 0.18, "ABSTAIN_AMBIGUOUS"),
        (False, 0.22, "ABSTAIN_AMBIGUOUS"),
        (False, 0.220001, "ABSTAIN_SELF_OCCLUDED"),
        (True, 0.01, "ABSTAIN_SELF_OCCLUDED"),
    ],
)
def test_frozen_overlap_boundaries_are_deterministic(center, dilated, decision):
    qualification, _, evidence = _fixture()
    evidence["target_results"] = [
        {
            "target_id": "H",
            "center_covered": center,
            "safe_region_overlap_fraction": min(0.01, dilated),
            "dilated_safe_region_overlap_fraction": dilated,
            "decision": decision,
        }
    ]
    validate_projection_evidence(_rehash(evidence))
    assert qualification["visible_overlap_upper"] == 0.18
    assert qualification["ambiguity_overlap_upper"] == 0.22


def test_synthetic_qualification_cannot_claim_physical_deployment():
    qualification = _qualification()
    qualification["physical_deployment_qualified"] = True
    core = {key: value for key, value in qualification.items() if key != "qualification_sha256"}
    qualification["qualification_sha256"] = canonical_hash(core)
    with pytest.raises(ProjectionEvidenceError, match="cannot qualify deployment"):
        TrustedSyntheticProjectionQualificationV1(qualification)
