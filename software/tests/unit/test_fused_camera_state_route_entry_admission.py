from __future__ import annotations

import copy
import hashlib
import json

import pytest

from rocell.application import fused_camera_state_route_entry_admission as subject
from rocell.application.calibrated_position_vector_state_snapshot_read_admission import (
    SNAPSHOT_READ_ADMISSION_RECEIPT_SCHEMA,
)
from rocell.application.camera_feedback_state_fusion_admission import (
    FUSION_ADMISSION_RECEIPT_SCHEMA,
)
from rocell.application.fixed_camera_keyboard_route_bound_entry_qualification_v1 import (
    SCHEMA as ENTRY_SCHEMA,
    STATUS_PASS as ENTRY_PASS,
    ZERO_AUTHORITY as ENTRY_ZERO_AUTHORITY,
)
from rocell.application.fused_camera_state_planning_admission import (
    PLANNING_ADMISSION_RECEIPT_SCHEMA,
)
from rocell.application.fused_camera_state_route_qualification_admission import (
    SCHEMA as ROUTE_SCHEMA,
    STATUS as ROUTE_STATUS,
    ZERO_AUTHORITY as ROUTE_ZERO_AUTHORITY,
)
from rocell.arm.position_vector_calibration import JOINT_ORDER
from rocell.calibration.position_vector_campaign import canonical_sha256
from rocell.kinematics import ARM_JOINT_NAMES


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


def _feedback() -> dict:
    return {
        "schema": "rocell.calibrated_position_vector_feedback.v1",
        "calibration_id": "calibration-01",
        "response_profile": "position_vector_named_pose",
        "source_pose": "PARK",
        "motion_active": False,
        "trajectory_progress_permille": 1000,
        "raw_position_counts": [1000] * 7,
        "position_order_servo_ids": [11, 12, 13, 14, 15, 16, 17],
        "canonical_joint_order": list(JOINT_ORDER),
        "canonical_joints_rad": {
            name: index / 10 for index, name in enumerate(JOINT_ORDER)
        },
        "shoulder_pair_residual_counts": 0,
        "calibration_evidence": {"source": "test"},
        "accepted_as_calibrated_joint_state": True,
        "motion_authorized": False,
        "physical_authority": False,
    }


def _fixtures():
    feedback = _feedback()
    snapshot = {
        "schema": SNAPSHOT_READ_ADMISSION_RECEIPT_SCHEMA,
        "status": "CALIBRATED_STATE_SNAPSHOT_READ_ADMITTED",
        "snapshot_id": "calibrated-state-snapshot:" + "1" * 64,
        "runtime_session_id": "feedback-runtime-session-01",
        "attachment_profile": "no_attachment",
        "valid_until": "2026-10-25T14:02:40-04:00",
        "calibrated_feedback": feedback,
        "calibrated_state_snapshot_read_admitted": True,
        "named_reader_snapshot_use_authorized": True,
        "automatic_retry_allowed": False,
        "motion_authorized": False,
        "physical_authority": False,
    }
    fusion = {
        "schema": FUSION_ADMISSION_RECEIPT_SCHEMA,
        "status": "CAMERA_FEEDBACK_STATE_FUSION_ADMITTED",
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_read_receipt_sha256": canonical_sha256(snapshot),
        "attachment_profile": "no_attachment",
        "valid_until": "2026-10-25T14:02:39-04:00",
        "calibrated_feedback": feedback,
        "camera_feedback_state_fusion_admitted": True,
        "planning_authorized": False,
        "automatic_retry_allowed": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "physical_authority": False,
    }
    planning = {
        "schema": PLANNING_ADMISSION_RECEIPT_SCHEMA,
        "status": "FUSED_CAMERA_STATE_PLANNING_ADMITTED",
        "planning_admission_id": "fused-camera-state-planning:" + "2" * 64,
        "fusion_receipt_sha256": canonical_sha256(fusion),
        "attachment_profile": "no_attachment",
        "valid_until": "2026-10-25T14:02:38-04:00",
        "calibrated_feedback": feedback,
        "fused_camera_state_planning_admitted": True,
        "plan_candidate_emitted": True,
        "automatic_retry_allowed": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "physical_authority": False,
    }
    route_core = {
        "schema": ROUTE_SCHEMA,
        "status": ROUTE_STATUS,
        "planning_admission_id": planning["planning_admission_id"],
        "planning_receipt_sha256": canonical_sha256(planning),
        "attachment_profile": "no_attachment",
        "target_key_id": "K00",
        "route_bound_collision_qualification_sha256": "3" * 64,
        "route_envelope_binding_sha256": "4" * 64,
        "installed_collision_profile_sha256": "5" * 64,
        "consumed_at": "2026-10-25T14:02:34-04:00",
        "profile_separation_preserved": True,
        "exact_target_route_binding_verified": True,
        "next_required_gate": "ROUTE_BOUND_FRESH_OBSERVED_ENTRY_QUALIFICATION",
        "authority": dict(ROUTE_ZERO_AUTHORITY),
    }
    route = {**route_core, "route_qualification_admission_sha256": _sha(route_core)}
    start = {
        arm_name: feedback["canonical_joints_rad"][feedback_name]
        for arm_name, feedback_name in zip(
            ARM_JOINT_NAMES, JOINT_ORDER[:5], strict=True
        )
    }
    observed = {
        "observed_route_entry_sha256": "6" * 64,
        "controller_session_id": snapshot["runtime_session_id"],
        "start_joint_positions_rad": start,
    }
    entry = {
        "schema": ENTRY_SCHEMA,
        "status": ENTRY_PASS,
        "disposition": "PASS",
        "active_profile": "no_attachment",
        "route_bound_collision_qualification_sha256": route[
            "route_bound_collision_qualification_sha256"
        ],
        "route_envelope_binding_sha256": route["route_envelope_binding_sha256"],
        "installed_collision_profile_sha256": route[
            "installed_collision_profile_sha256"
        ],
        "observed_route_entry_sha256": observed["observed_route_entry_sha256"],
        "blockers": [],
        "authority": dict(ENTRY_ZERO_AUTHORITY),
        "route_bound_entry_qualification_sha256": "7" * 64,
    }
    return snapshot, fusion, planning, route, entry, observed


def _admit(monkeypatch, fixtures, *, install_parsers=True, **overrides):
    snapshot, fusion, planning, route, entry, observed = fixtures
    if install_parsers:
        monkeypatch.setattr(
            subject,
            "parse_fixed_camera_keyboard_route_bound_entry_v1",
            lambda value: dict(value),
        )
        monkeypatch.setattr(
            subject,
            "parse_typing_observed_route_entry_v1",
            lambda value: dict(value),
        )
    values = {
        "snapshot_read_receipt_document": snapshot,
        "fusion_receipt_document": fusion,
        "planning_receipt_document": planning,
        "route_qualification_admission_document": route,
        "route_bound_entry_qualification_document": entry,
        "observed_route_entry_document": observed,
        "current_attachment_profile": "no_attachment",
        "consumed_at": "2026-10-25T14:02:36-04:00",
    }
    values.update(overrides)
    return subject.admit_fused_camera_state_route_entry(**values)


def _reseal_route(route):
    core = dict(route)
    core.pop("route_qualification_admission_sha256")
    route["route_qualification_admission_sha256"] = _sha(core)


def test_binds_fresh_calibrated_state_to_exact_qualified_route_entry(monkeypatch):
    result = _admit(monkeypatch, _fixtures())

    assert result["status"] == subject.STATUS
    assert result["calibrated_start_matches_observed_entry"] is True
    assert result["fresh_state_lineage_verified"] is True
    assert result["attachment_profile"] == "no_attachment"
    assert result["target_key_id"] == "K00"
    assert result["next_required_gate"] == subject.NEXT_REQUIRED_GATE
    assert result["authority"] == subject.ZERO_AUTHORITY
    core = dict(result)
    assert core.pop("route_entry_admission_sha256") == _sha(core)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("snapshot", "lineage differs"),
        ("planning", "lineage differs"),
        ("profile", "attachment profile differs"),
        ("stale", "stale"),
        ("session", "different controller runtime session"),
        ("joints", "start joints differ"),
        ("route", "qualified route and observed entry lineage differs"),
        ("entry_blocked", "not a zero-authority PASS"),
    ),
)
def test_rejects_crossed_stale_or_nonpassing_entry_lineage(
    monkeypatch, mutation, message
):
    fixtures = list(copy.deepcopy(_fixtures()))
    overrides = {}
    if mutation == "snapshot":
        fixtures[1]["snapshot_read_receipt_sha256"] = "f" * 64
    elif mutation == "planning":
        fixtures[3]["planning_receipt_sha256"] = "f" * 64
        _reseal_route(fixtures[3])
    elif mutation == "profile":
        overrides["current_attachment_profile"] = "stylus_attachment"
    elif mutation == "stale":
        overrides["consumed_at"] = "2026-10-25T14:02:41-04:00"
    elif mutation == "session":
        fixtures[5]["controller_session_id"] = "other-session"
    elif mutation == "joints":
        fixtures[5]["start_joint_positions_rad"][ARM_JOINT_NAMES[0]] += 0.01
    elif mutation == "route":
        fixtures[4]["route_envelope_binding_sha256"] = "f" * 64
    else:
        fixtures[4]["status"] = "BLOCKED_ROUTE_BOUND_PROFILED_ENTRY_ROUTE_EVIDENCE_INCOMPLETE"
        fixtures[4]["disposition"] = "BLOCKED"
        fixtures[4]["blockers"] = ["FRESH_ENTRY_REQUIRED"]

    with pytest.raises(
        subject.FusedCameraStateRouteEntryAdmissionError, match=message
    ):
        _admit(monkeypatch, tuple(fixtures), **overrides)


def test_rejects_tampered_route_admission_before_parsing_entry(monkeypatch):
    fixtures = list(_fixtures())
    fixtures[3]["target_key_id"] = "K01"
    calls = []
    monkeypatch.setattr(
        subject,
        "parse_fixed_camera_keyboard_route_bound_entry_v1",
        lambda value: calls.append("entry"),
    )

    with pytest.raises(
        subject.FusedCameraStateRouteEntryAdmissionError,
        match="route qualification admission hash differs",
    ):
        _admit(monkeypatch, tuple(fixtures), install_parsers=False)
    assert calls == []
