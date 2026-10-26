from __future__ import annotations

import copy
import hashlib
import json

import pytest

from rocell.application import fused_camera_state_action_review_admission as subject
from rocell.application.fixed_camera_keyboard_route_bound_entry_qualification_v1 import (
    STATUS_PASS as ENTRY_PASS,
    ZERO_AUTHORITY as ENTRY_ZERO_AUTHORITY,
)
from rocell.application.fused_camera_state_route_entry_admission import (
    SCHEMA as ROUTE_ENTRY_SCHEMA,
    STATUS as ROUTE_ENTRY_STATUS,
    ZERO_AUTHORITY as ROUTE_ENTRY_ZERO_AUTHORITY,
)
from rocell.application.fused_camera_state_route_qualification_admission import (
    SCHEMA as ROUTE_SCHEMA,
    STATUS as ROUTE_STATUS,
    ZERO_AUTHORITY as ROUTE_ZERO_AUTHORITY,
)


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


def _seal(value: dict, field: str) -> dict:
    value[field] = _sha(value)
    return value


def _fixtures():
    route = _seal(
        {
            "schema": ROUTE_SCHEMA,
            "status": ROUTE_STATUS,
            "planning_admission_id": "fused-camera-state-planning:" + "1" * 64,
            "planning_receipt_sha256": "2" * 64,
            "attachment_profile": "no_attachment",
            "target_key_id": "K00",
            "target_action_indices": [3, 7],
            "typing_execution_plan_sha256": "3" * 64,
            "typing_trajectory_plan_sha256": "4" * 64,
            "route_bound_collision_qualification_sha256": "5" * 64,
            "route_envelope_binding_sha256": "6" * 64,
            "installed_collision_profile_sha256": "7" * 64,
            "consumed_at": "2026-10-26T18:00:00+00:00",
            "profile_separation_preserved": True,
            "exact_target_route_binding_verified": True,
            "next_required_gate": "ROUTE_BOUND_FRESH_OBSERVED_ENTRY_QUALIFICATION",
            "authority": dict(ROUTE_ZERO_AUTHORITY),
        },
        "route_qualification_admission_sha256",
    )
    nested = {
        "retained_entry_telemetry_coverage_qualified": True,
        "selected_profile_route_continuously_clear": True,
        "observed_entry_continuously_clear": True,
        "entry_route_joint_continuity_proven": True,
    }
    entry = {
        "schema": "rocell.fixed_camera_keyboard_route_bound_entry_qualification.v1",
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
        "profiled_entry_route_qualification": nested,
        "observed_route_entry_coverage_sha256": "8" * 64,
        "blockers": [],
        "authority": dict(ENTRY_ZERO_AUTHORITY),
        "route_bound_entry_qualification_sha256": "9" * 64,
    }
    route_entry = _seal(
        {
            "schema": ROUTE_ENTRY_SCHEMA,
            "status": ROUTE_ENTRY_STATUS,
            "route_qualification_admission_sha256": route[
                "route_qualification_admission_sha256"
            ],
            "route_bound_entry_qualification_sha256": entry[
                "route_bound_entry_qualification_sha256"
            ],
            "target_key_id": "K00",
            "attachment_profile": "no_attachment",
            "runtime_session_id": "runtime-session-01",
            "route_envelope_binding_sha256": route[
                "route_envelope_binding_sha256"
            ],
            "installed_collision_profile_sha256": route[
                "installed_collision_profile_sha256"
            ],
            "consumed_at": "2026-10-26T18:00:00+00:00",
            "fresh_state_lineage_verified": True,
            "calibrated_start_matches_observed_entry": True,
            "profile_separation_preserved": True,
            "next_required_gate": "INDEPENDENT_EXECUTION_RELEASE_GATES",
            "authority": dict(ROUTE_ENTRY_ZERO_AUTHORITY),
        },
        "route_entry_admission_sha256",
    )
    common = {
        "route_entry_admission_sha256": route_entry[
            "route_entry_admission_sha256"
        ],
        "route_qualification_admission_sha256": route[
            "route_qualification_admission_sha256"
        ],
        "target_key_id": "K00",
        "action_index": 3,
        "attachment_profile": "no_attachment",
    }
    verifier = _seal(
        {
            "schema": subject.EFFECT_VERIFIER_SCHEMA,
            "status": subject.EFFECT_VERIFIER_STATUS,
            **common,
            "verifier_id": "keyboard-outcome-observer-01",
            "observer_context_sha256": "a" * 64,
            "expected_effect_sha256": "b" * 64,
            "evidence_origin": "PHYSICAL_RETAINED_ORIGINALS",
            "review_disposition": "INDEPENDENTLY_APPROVED",
            "independent_from_motion_writer": True,
            "configured_at": "2026-10-26T17:59:00+00:00",
            "valid_until": "2026-10-26T18:04:00+00:00",
            "maximum_observation_latency_ms": 500,
            "automatic_retry_allowed": False,
            "controller_commands": [],
            "hardware_access": False,
            "physical_authority": False,
        },
        "effect_verifier_binding_sha256",
    )
    operator = _seal(
        {
            "schema": subject.OPERATOR_CONFIRMATION_SCHEMA,
            "status": subject.OPERATOR_CONFIRMATION_STATUS,
            **common,
            "operator_id": "operator-01",
            "runtime_session_id": "runtime-session-01",
            "confirmed_at": "2026-10-26T18:00:01+00:00",
            "valid_until": "2026-10-26T18:00:10+00:00",
            "operator_present": True,
            "shutdown_reachable": True,
            "area_clear": True,
            "arm_secured_and_stationary": True,
            "automatic_retry_allowed": False,
            "motion_authorized": False,
            "physical_authority": False,
        },
        "operator_confirmation_sha256",
    )
    policy = _seal(
        {
            "schema": subject.ACTION_POLICY_SCHEMA,
            "status": subject.ACTION_POLICY_STATUS,
            **common,
            "policy_id": "keyboard-contact-review-v1",
            "interaction": "CONTACT",
            "expected_effect_sha256": "b" * 64,
            "effect_verifier_binding_sha256": verifier[
                "effect_verifier_binding_sha256"
            ],
            "per_action_review_required": True,
            "single_use_required": True,
            "automatic_retry_allowed": False,
            "review_issued": False,
            "permit_issued": False,
            "controller_commands": [],
            "hardware_access": False,
            "physical_authority": False,
        },
        "action_review_policy_sha256",
    )
    return route_entry, route, entry, verifier, operator, policy


def _admit(monkeypatch, fixtures, **overrides):
    route_entry, route, entry, verifier, operator, policy = fixtures
    monkeypatch.setattr(
        subject,
        "parse_fixed_camera_keyboard_route_bound_entry_v1",
        lambda value: dict(value),
    )
    arguments = {
        "route_entry_admission_document": route_entry,
        "route_qualification_admission_document": route,
        "route_bound_entry_qualification_document": entry,
        "effect_verifier_binding_document": verifier,
        "operator_confirmation_document": operator,
        "action_review_policy_document": policy,
        "selected_action_index": 3,
        "consumed_at": "2026-10-26T18:00:04+00:00",
    }
    arguments.update(overrides)
    return subject.admit_fused_camera_state_action_review(**arguments)


def _reseal(value: dict, field: str) -> None:
    value.pop(field)
    value[field] = _sha(value)


def test_admits_one_exact_fresh_action_to_existing_review_boundary(monkeypatch):
    result = _admit(monkeypatch, _fixtures())

    assert result["status"] == subject.STATUS
    assert result["target_key_id"] == "K00"
    assert result["action_index"] == 3
    assert result["interaction"] == "CONTACT"
    assert result["entry_dynamics_and_coverage_verified"] is True
    assert result["current_operator_verified"] is True
    assert result["independent_effect_verifier_verified"] is True
    assert result["next_required_gate"] == subject.NEXT_REQUIRED_GATE
    assert result["authority"] == subject.ZERO_AUTHORITY
    core = dict(result)
    assert core.pop("action_review_admission_sha256") == _sha(core)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("stale_route", "route-entry admission is stale"),
        ("wrong_action", "does not belong"),
        ("crossed_route", "route-entry and exact-route lineage differs"),
        ("coverage", "dynamics, coverage, continuity, or collision"),
        ("operator_session", "different runtime session"),
        ("operator_missing", "operator confirmation is not current"),
        ("verifier_writer", "effect verifier is not fresh"),
        ("verifier_effect", "policy and effect verifier binding differ"),
        ("policy_action", "action review policy differs"),
    ),
)
def test_rejects_stale_crossed_or_incomplete_release_prerequisites(
    monkeypatch, mutation, message
):
    fixtures = list(copy.deepcopy(_fixtures()))
    overrides = {}
    if mutation == "stale_route":
        overrides["consumed_at"] = "2026-10-26T18:00:06+00:00"
    elif mutation == "wrong_action":
        overrides["selected_action_index"] = 4
    elif mutation == "crossed_route":
        fixtures[0]["route_envelope_binding_sha256"] = "f" * 64
        _reseal(fixtures[0], "route_entry_admission_sha256")
    elif mutation == "coverage":
        fixtures[2]["profiled_entry_route_qualification"][
            "retained_entry_telemetry_coverage_qualified"
        ] = False
    elif mutation == "operator_session":
        fixtures[4]["runtime_session_id"] = "other-session"
        _reseal(fixtures[4], "operator_confirmation_sha256")
    elif mutation == "operator_missing":
        fixtures[4]["operator_present"] = False
        _reseal(fixtures[4], "operator_confirmation_sha256")
    elif mutation == "verifier_writer":
        fixtures[3]["independent_from_motion_writer"] = False
        _reseal(fixtures[3], "effect_verifier_binding_sha256")
    elif mutation == "verifier_effect":
        fixtures[3]["expected_effect_sha256"] = "f" * 64
        _reseal(fixtures[3], "effect_verifier_binding_sha256")
    else:
        fixtures[5]["action_index"] = 7
        _reseal(fixtures[5], "action_review_policy_sha256")

    with pytest.raises(subject.FusedCameraStateActionReviewAdmissionError, match=message):
        _admit(monkeypatch, tuple(fixtures), **overrides)


def test_tampered_route_entry_rejects_before_entry_parser(monkeypatch):
    fixtures = list(_fixtures())
    fixtures[0]["target_key_id"] = "K01"
    calls: list[str] = []
    monkeypatch.setattr(
        subject,
        "parse_fixed_camera_keyboard_route_bound_entry_v1",
        lambda value: calls.append("entry"),
    )

    with pytest.raises(
        subject.FusedCameraStateActionReviewAdmissionError,
        match="route-entry admission hash differs",
    ):
        subject.admit_fused_camera_state_action_review(
            route_entry_admission_document=fixtures[0],
            route_qualification_admission_document=fixtures[1],
            route_bound_entry_qualification_document=fixtures[2],
            effect_verifier_binding_document=fixtures[3],
            operator_confirmation_document=fixtures[4],
            action_review_policy_document=fixtures[5],
            selected_action_index=3,
            consumed_at="2026-10-26T18:00:04+00:00",
        )
    assert calls == []
