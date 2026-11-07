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
    path = (
        ROOT
        / "software/integrations/isaac_sim/robot_geometry_review_candidates.py"
    )
    spec = importlib.util.spec_from_file_location("arm240_candidates", path)
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


def _gap_report() -> dict[str, object]:
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
    core: dict[str, object] = {
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
    return {**core, "report_sha256": _sha(core)}


def _mesh() -> dict[str, object]:
    value = json.loads(MESH_PATH.read_bytes())
    assert isinstance(value, dict)
    return value


def _report():
    return _module().build_robot_geometry_review_candidates(
        _gap_report(),
        _mesh(),
        gap_report_file_sha256="a" * 64,
        mesh_reduction_file_sha256="b" * 64,
    )


def test_arm240_packages_all_seven_robot_candidates_without_promotion() -> None:
    report = _report()

    assert report["status"] == (
        "BLOCKED_CANDIDATES_AWAIT_PHYSICAL_VERIFICATION"
    )
    assert report["candidate_body_count"] == 7
    assert report["candidate_primitive_count"] == 14
    assert report["accepted_body_count"] == 0
    assert report["pending_robot_body_count"] == 7
    assert report["remaining_nonrobot_pending_body_count"] == 12
    assert report["measurement_manifest_modified"] is False
    assert report["candidate_geometry_promoted_to_measurement"] is False
    assert report["installed_collision_profile_generated"] is False
    assert report["isaac_started"] is False
    assert report["hardware_access"] is False
    assert report["physical_authority"] is False
    assert report["controller_commands"] == []


def test_arm240_preserves_link_local_primitives_and_review_blockers() -> None:
    report = _report()
    rows = {row["body_id"]: row for row in report["robot_body_candidates"]}

    assert rows["robot:base_link"]["candidate_primitive_count"] == 2
    assert rows["robot:link3"]["candidate_primitive_count"] == 4
    assert rows["robot:link5"]["candidate_primitive_count"] == 1
    assert rows["robot:link5"]["partition_mode"] == (
        "WHOLE_LINK_ENVELOPE_COMPONENT_LIMIT_FALLBACK"
    )
    assert "LINK5_WHOLE_LINK_ENVELOPE_REVIEW_REQUIRED" in rows[
        "robot:link5"
    ]["review_blockers"]
    assert all(
        primitive["kind"] == "oriented_box"
        for row in rows.values()
        for primitive in row["candidate_primitives"]
    )
    assert all(
        row["geometry_uncertainty_mm"] is None
        and row["physical_model_identity_verified"] is False
        and row["icq1_status_after_packaging"] == "PENDING"
        for row in rows.values()
    )


def test_arm240_binds_exact_upstream_and_source_hashes() -> None:
    report = _report()

    assert report["source_arm239_report_file_sha256"] == "a" * 64
    assert report["source_mesh_reduction_file_sha256"] == "b" * 64
    assert report["source_upstream_commit"] == (
        "40dbd84b553695212fab713e8465f817ba95454d"
    )
    assert report["source_mesh_reduction_receipt_sha256"] == (
        "ef8d011314df145afe5db43310457671082b276023191aea47287b3ef87a7178"
    )


def test_arm240_rejects_tampered_gap_or_mesh_lineage() -> None:
    module = _module()
    gap = _gap_report()
    gap["attachment_profile"] = "no_attachment"
    with pytest.raises(module.RobotGeometryReviewCandidateError):
        module.build_robot_geometry_review_candidates(
            gap,
            _mesh(),
            gap_report_file_sha256="a" * 64,
            mesh_reduction_file_sha256="b" * 64,
        )

    mesh = copy.deepcopy(_mesh())
    mesh["links"][0]["components"][0]["maximum_vertex_overflow_mm"] = 0.1
    with pytest.raises(module.RobotGeometryReviewCandidateError):
        module.build_robot_geometry_review_candidates(
            _gap_report(),
            mesh,
            gap_report_file_sha256="a" * 64,
            mesh_reduction_file_sha256="b" * 64,
        )
