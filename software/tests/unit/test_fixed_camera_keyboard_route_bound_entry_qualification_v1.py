from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

import rocell.application.fixed_camera_keyboard_route_bound_entry_qualification_v1 as subject
from rocell.application.fixed_camera_keyboard_profiled_entry_route_qualification_v1 import (
    SCHEMA as ENTRY_SCHEMA,
    STATUS_BLOCKED as ENTRY_BLOCKED,
    STATUS_PASS as ENTRY_PASS,
    ZERO_AUTHORITY as ENTRY_ZERO_AUTHORITY,
)
from rocell.application.fixed_camera_keyboard_profiled_route_clearance_reconstruction_v1 import (
    STATUS_BLOCKED as ROUTE_BLOCKED,
    STATUS_READY as ROUTE_READY,
    STATUS_REJECTED as ROUTE_REJECTED,
)
from rocell.application.fixed_camera_keyboard_route_bound_collision_qualification_v1 import (
    SCHEMA as ROUTE_BOUND_SCHEMA,
    STATUS_BLOCKED as ROUTE_BOUND_BLOCKED,
    STATUS_READY as ROUTE_BOUND_READY,
    STATUS_REJECTED as ROUTE_BOUND_REJECTED,
    ZERO_AUTHORITY as ROUTE_BOUND_ZERO_AUTHORITY,
)


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / (
    "software/ai/schemas/"
    "fixed_camera_keyboard_route_bound_entry_qualification_v1.schema.json"
)
PROFILES = ("no_attachment", "stylus_attachment")


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


def _route(status: str = ROUTE_READY) -> dict:
    disposition = "REJECT" if status == ROUTE_REJECTED else "BLOCKED"
    blocker = {
        ROUTE_READY: "FRESH_OBSERVED_START_AND_ENTRY_QUALIFICATION_REQUIRED",
        ROUTE_REJECTED: "PROFILE_BOUND_ROUTE_COLLISION_DETECTED",
        ROUTE_BLOCKED: "PROFILE_BOUND_ROUTE_CLEARANCE_EVIDENCE_INCOMPLETE",
    }[status]
    return {
        "status": status,
        "disposition": disposition,
        "profiled_route_clearance_reconstruction_sha256": "c" * 64,
        "blockers": [blocker],
        "next_required_stage": "NEXT_STAGE",
    }


def _route_bound(status: str = ROUTE_BOUND_READY) -> dict:
    route_status = {
        ROUTE_BOUND_READY: ROUTE_READY,
        ROUTE_BOUND_REJECTED: ROUTE_REJECTED,
        ROUTE_BOUND_BLOCKED: ROUTE_BLOCKED,
    }[status]
    route = _route(route_status)
    profiles = {
        name: {
            "profile": name,
            "installed_collision_profile_sha256": str(index + 1) * 64,
            "partitioned_typing_collision_intake_sha256": str(index + 3) * 64,
            "completion_sha256": str(index + 5) * 64,
            "independent_review_sha256": str(index + 7) * 64,
            "route_envelope_binding_sha256": str(index + 8) * 64,
            "route_sample_count": 329,
            "route_segment_count": 328,
        }
        for index, name in enumerate(PROFILES)
    }
    core = {
        "schema": ROUTE_BOUND_SCHEMA,
        "status": status,
        "disposition": route["disposition"],
        "profiles": profiles,
        "source_profiled_partition_collision_evaluation_sha256": "b" * 64,
        "source_profiled_route_clearance_reconstruction_sha256": "c" * 64,
        "profile_separation_preserved": True,
        "exact_route_binding_verified_before_evaluation": True,
        "expected_route_sample_count_per_profile": 329,
        "expected_route_segment_count_per_profile": 328,
        "blockers": route["blockers"],
        "next_required_stage": route["next_required_stage"],
        "authority": dict(ROUTE_BOUND_ZERO_AUTHORITY),
    }
    return {**core, "route_bound_collision_qualification_sha256": _sha(core)}


def _entry(status: str = ENTRY_PASS) -> dict:
    disposition = "PASS" if status == ENTRY_PASS else "BLOCKED"
    blockers = [] if status == ENTRY_PASS else ["FRESH_ENTRY_REQUIRED"]
    core = {
        "schema": ENTRY_SCHEMA,
        "status": status,
        "disposition": disposition,
        "active_profile": "no_attachment",
        "installed_collision_profile_sha256": "1" * 64,
        "profiled_route_clearance_reconstruction_sha256": "c" * 64,
        "observed_route_entry_sha256": "d" * 64,
        "observed_route_entry_sweep_sha256": "e" * 64,
        "observed_route_entry_coverage_sha256": "f" * 64,
        "profile_separation_preserved": True,
        "blockers": blockers,
        "next_required_stage": "NATIVE_REPLAY" if not blockers else "FRESH_ENTRY",
        "authority": dict(ENTRY_ZERO_AUTHORITY),
    }
    return {**core, "profiled_entry_route_qualification_sha256": _sha(core)}


def _install_stubs(monkeypatch, route_status=ROUTE_READY, entry_status=ENTRY_PASS):
    calls: list[str] = []

    def reconstruct(documents, evaluation):
        calls.append("reconstruct")
        return _route(route_status)

    def qualify(*args):
        calls.append("qualify_entry")
        return _entry(entry_status)

    monkeypatch.setattr(
        subject,
        "_reconstruct_route",
        reconstruct,
    )
    monkeypatch.setattr(
        subject,
        "_qualify_entry",
        qualify,
    )
    return calls


def _run(monkeypatch, entry_status=ENTRY_PASS):
    calls = _install_stubs(monkeypatch, entry_status=entry_status)
    result = subject.qualify_fixed_camera_keyboard_route_bound_entry_v1(
        _route_bound(),
        {name: {} for name in PROFILES},
        {"profiled_partition_collision_evaluation_sha256": "b" * 64},
        "no_attachment",
        {"entry": True},
        {"sweep": True},
        {"coverage": True},
    )
    return calls, result


def test_exact_route_binding_is_required_before_fresh_entry_qualification(monkeypatch):
    calls, result = _run(monkeypatch)

    assert calls == ["reconstruct", "qualify_entry"]
    assert result["status"] == subject.STATUS_PASS
    assert result["disposition"] == "PASS"
    assert result["route_envelope_binding_sha256"] == "8" * 64
    assert result["profiled_entry_route_qualification_sha256"] == result[
        "profiled_entry_route_qualification"
    ]["profiled_entry_route_qualification_sha256"]
    assert result["exact_route_binding_verified_before_entry_qualification"] is True
    assert result["authority"] == subject.ZERO_AUTHORITY
    assert subject.parse_fixed_camera_keyboard_route_bound_entry_v1(result) == result
    jsonschema.Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    ).validate(result)


def test_fresh_entry_blocker_remains_distinct_and_sealed(monkeypatch):
    calls, result = _run(monkeypatch, ENTRY_BLOCKED)

    assert calls == ["reconstruct", "qualify_entry"]
    assert result["status"] == subject.STATUS_BLOCKED
    assert result["disposition"] == "BLOCKED"
    assert result["blockers"] == ["FRESH_ENTRY_REQUIRED"]
    assert subject.parse_fixed_camera_keyboard_route_bound_entry_v1(result) == result


@pytest.mark.parametrize(
    ("route_bound_status", "route_status", "expected"),
    (
        (ROUTE_BOUND_REJECTED, ROUTE_REJECTED, subject.STATUS_REJECTED),
        (ROUTE_BOUND_BLOCKED, ROUTE_BLOCKED, subject.STATUS_BLOCKED),
    ),
)
def test_rejected_or_incomplete_route_never_calls_entry_qualification(
    monkeypatch, route_bound_status, route_status, expected
):
    calls = _install_stubs(monkeypatch, route_status=route_status)
    result = subject.qualify_fixed_camera_keyboard_route_bound_entry_v1(
        _route_bound(route_bound_status),
        {name: {} for name in PROFILES},
        {"profiled_partition_collision_evaluation_sha256": "b" * 64},
        "no_attachment",
    )

    assert calls == ["reconstruct"]
    assert result["status"] == expected
    assert result["profiled_entry_route_qualification"] is None
    assert result["observed_route_entry_sha256"] is None
    assert subject.parse_fixed_camera_keyboard_route_bound_entry_v1(result) == result


def test_tampered_route_bound_receipt_fails_before_reconstruction(monkeypatch):
    calls = _install_stubs(monkeypatch)
    changed = _route_bound()
    changed["profiles"]["no_attachment"]["route_envelope_binding_sha256"] = "9" * 64

    with pytest.raises(
        subject.FixedCameraKeyboardRouteBoundEntryQualificationV1Error,
        match="hash differs",
    ):
        subject.qualify_fixed_camera_keyboard_route_bound_entry_v1(
            changed,
            {name: {} for name in PROFILES},
            {"profiled_partition_collision_evaluation_sha256": "b" * 64},
            "no_attachment",
        )
    assert calls == []


def test_crossed_entry_profile_fails_closed(monkeypatch):
    calls = _install_stubs(monkeypatch)

    def crossed(*args):
        value = _entry()
        core = dict(value)
        core.pop("profiled_entry_route_qualification_sha256")
        core["active_profile"] = "stylus_attachment"
        return {**core, "profiled_entry_route_qualification_sha256": _sha(core)}

    monkeypatch.setattr(
        subject,
        "_qualify_entry",
        crossed,
    )
    with pytest.raises(
        subject.FixedCameraKeyboardRouteBoundEntryQualificationV1Error,
        match="lineage differ",
    ):
        subject.qualify_fixed_camera_keyboard_route_bound_entry_v1(
            _route_bound(),
            {name: {} for name in PROFILES},
            {"profiled_partition_collision_evaluation_sha256": "b" * 64},
            "no_attachment",
        )
    assert calls == ["reconstruct"]


def test_parser_rejects_resealed_authority_tamper(monkeypatch):
    _calls, result = _run(monkeypatch)
    changed = copy.deepcopy(result)
    changed["authority"]["physical_authority"] = True
    core = dict(changed)
    core.pop("route_bound_entry_qualification_sha256")
    changed["route_bound_entry_qualification_sha256"] = _sha(core)

    with pytest.raises(
        subject.FixedCameraKeyboardRouteBoundEntryQualificationV1Error,
        match="authority differs",
    ):
        subject.parse_fixed_camera_keyboard_route_bound_entry_v1(changed)


def test_parser_rejects_resealed_status_disposition_cross(monkeypatch):
    calls = _install_stubs(monkeypatch, route_status=ROUTE_BLOCKED)
    result = subject.qualify_fixed_camera_keyboard_route_bound_entry_v1(
        _route_bound(ROUTE_BOUND_BLOCKED),
        {name: {} for name in PROFILES},
        {"profiled_partition_collision_evaluation_sha256": "b" * 64},
        "no_attachment",
    )
    assert calls == ["reconstruct"]
    changed = copy.deepcopy(result)
    changed["disposition"] = "REJECT"
    core = dict(changed)
    core.pop("route_bound_entry_qualification_sha256")
    changed["route_bound_entry_qualification_sha256"] = _sha(core)

    with pytest.raises(
        subject.FixedCameraKeyboardRouteBoundEntryQualificationV1Error,
        match="authority differs",
    ):
        subject.parse_fixed_camera_keyboard_route_bound_entry_v1(changed)
