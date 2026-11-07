from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MESH_PATH = (
    ROOT
    / "software/integrations/isaac_sim/evidence/"
    "roarm_m3_link_mesh_reduction_20261004.json"
)


def _module():
    path = ROOT / "software/integrations/isaac_sim/robot_geometry_review_gate.py"
    spec = importlib.util.spec_from_file_location("arm241_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _request():
    module = _module()
    arm240_path = (
        ROOT
        / "software/integrations/isaac_sim/robot_geometry_review_candidates.py"
    )
    spec = importlib.util.spec_from_file_location("arm240_candidates_for_gate", arm240_path)
    assert spec is not None and spec.loader is not None
    arm240 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arm240)
    robot_ids = [
        "robot:base_link",
        "robot:link1",
        "robot:link2",
        "robot:link3",
        "robot:link4",
        "robot:link5",
        "robot:gripper",
    ]
    rows = [{"body_id": body_id} for body_id in robot_ids]
    rows.extend({"body_id": f"pending:{index}"} for index in range(12))
    gap_core = {
        "schema": "tactevra.isaac_lm4_installed_measurement_gap_matrix.v1",
        "status": "BLOCKED_NO_ACCEPTED_MEASUREMENT_PROMOTIONS",
        "attachment_profile": "stylus_attachment",
        "body_gap_matrix": rows,
        "required_body_count": 19,
        "accepted_body_count": 0,
        "pending_body_count": 19,
        "nominal_values_promoted_to_measurement": False,
        "measurement_manifest_modified": False,
        "physical_authority": False,
    }
    gap = {**gap_core, "report_sha256": _sha(gap_core)}
    mesh = json.loads(MESH_PATH.read_bytes())
    report = arm240.build_robot_geometry_review_candidates(
        gap,
        mesh,
        gap_report_file_sha256="a" * 64,
        mesh_reduction_file_sha256="b" * 64,
    )
    return module.build_review_request(
        report, arm240_file_sha256="c" * 64
    )


def _review(request):
    decisions = []
    for row in request["review_rows"]:
        findings = {
            finding: {
                "accepted": True,
                "evidence_sha256": "e" * 64,
                "source_reference": f"review evidence for {finding}",
            }
            for finding in row["required_acceptance_findings"]
        }
        decisions.append(
            {
                "body_id": row["body_id"],
                "candidate_sha256": row["candidate_sha256"],
                "disposition": "ACCEPT_FOR_ICQ1_ROBOT_ROW",
                "reviewer": "synthetic unit-test reviewer",
                "geometry_uncertainty_mm": 0.5,
                "findings": findings,
            }
        )
    core = {
        "schema": "tactevra.isaac_lm4_robot_geometry_engineering_review.v1",
        "source_request_sha256": request["request_sha256"],
        "decisions": decisions,
    }
    return {**core, "review_sha256": _sha(core)}


def test_arm241_request_binds_all_candidates_without_promotion() -> None:
    request = _request()

    assert request["status"] == "BLOCKED_REVIEW_RECORD_REQUIRED"
    assert request["review_body_count"] == 7
    assert request["candidate_primitive_count"] == 14
    assert request["accepted_body_count"] == 0
    assert request["pending_robot_body_count"] == 7
    assert request["remaining_nonrobot_pending_body_count"] == 12
    assert request["measurement_manifest_modified"] is False
    assert request["installed_collision_profile_generated"] is False
    assert request["isaac_started"] is False
    assert request["hardware_access"] is False
    assert request["physical_authority"] is False


def test_arm241_link5_requires_explicit_negative_result_disposition() -> None:
    request = _request()
    rows = {row["body_id"]: row for row in request["review_rows"]}

    assert "ARM196_NEGATIVE_ROUTE_RESULT_EXPLICITLY_ADDRESSED" in rows[
        "robot:link5"
    ]["required_acceptance_findings"]
    assert request["arm196_link5_negative_result"]["native_receipt_sha256"] == (
        "e1a6ddc7c52ec5acda2eee9e0ae628d705a44d85ca4f9db009a67b80a6e8b7b"
    )


def test_arm241_complete_synthetic_review_only_emits_eligibility() -> None:
    module = _module()
    request = _request()
    assessment = module.assess_review(request, _review(request))

    assert assessment["accepted_body_count"] == 7
    assert assessment["pending_robot_body_count"] == 0
    assert assessment["remaining_nonrobot_pending_body_count"] == 12
    assert assessment["measurement_manifest_modified"] is False
    assert assessment["installed_collision_profile_generated"] is False
    assert assessment["collision_screening_executed"] is False
    assert assessment["physical_authority"] is False


@pytest.mark.parametrize("mutation", ["missing", "wrong_hash", "zero_uncertainty"])
def test_arm241_rejects_incomplete_or_unbound_review(mutation: str) -> None:
    module = _module()
    request = _request()
    review = _review(request)
    if mutation == "missing":
        review["decisions"].pop()
    elif mutation == "wrong_hash":
        review["decisions"][0]["candidate_sha256"] = "0" * 64
    else:
        review["decisions"][0]["geometry_uncertainty_mm"] = 0.0
    unsigned = dict(review)
    unsigned.pop("review_sha256")
    review["review_sha256"] = _sha(unsigned)

    with pytest.raises(module.RobotGeometryReviewGateError):
        module.assess_review(request, review)


def test_arm241_rejects_tampered_request_lineage() -> None:
    module = _module()
    request = _request()
    tampered = copy.deepcopy(request)
    tampered["remaining_nonrobot_pending_body_count"] = 0

    with pytest.raises(module.RobotGeometryReviewGateError):
        module.assess_review(tampered, _review(request))
