from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

import rocell.application.route_bound_entry_isaac_replay_handoff_v1 as subject
from rocell.application.fixed_camera_keyboard_profiled_route_clearance_reconstruction_v1 import (
    reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1,
)
from rocell.application.fixed_camera_keyboard_route_bound_collision_qualification_v1 import (
    SCHEMA as COLLISION_SCHEMA,
    STATUS_READY as COLLISION_READY,
    ZERO_AUTHORITY as COLLISION_AUTHORITY,
)
from rocell.application.fixed_camera_keyboard_route_bound_entry_qualification_v1 import (
    SCHEMA as ENTRY_SCHEMA,
    STATUS_PASS as ENTRY_PASS,
    ZERO_AUTHORITY as ENTRY_AUTHORITY,
)

from test_profiled_entry_route_isaac_replay_handoff_v1 import (
    _qualification,
    _selected_lock,
)


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / (
    "software/ai/schemas/route_bound_entry_isaac_replay_handoff_v1.schema.json"
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


def _bundle():
    documents, evaluation, qualification = _qualification()
    route = reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1(
        documents, evaluation
    )
    profiles = {}
    for index, name in enumerate(PROFILES):
        profiles[name] = {
            "profile": name,
            "installed_collision_profile_sha256": documents[name][
                "installed_collision_profile_sha256"
            ],
            "partitioned_typing_collision_intake_sha256": documents[name][
                "partitioned_typing_collision_intake_sha256"
            ],
            "completion_sha256": str(index + 5) * 64,
            "independent_review_sha256": str(index + 7) * 64,
            "route_envelope_binding_sha256": str(index + 8) * 64,
            "route_sample_count": 329,
            "route_segment_count": 328,
        }
    collision_core = {
        "schema": COLLISION_SCHEMA,
        "status": COLLISION_READY,
        "disposition": route["disposition"],
        "profiles": profiles,
        "source_profiled_partition_collision_evaluation_sha256": evaluation[
            "profiled_partition_collision_evaluation_sha256"
        ],
        "source_profiled_route_clearance_reconstruction_sha256": route[
            "profiled_route_clearance_reconstruction_sha256"
        ],
        "profile_separation_preserved": True,
        "exact_route_binding_verified_before_evaluation": True,
        "expected_route_sample_count_per_profile": 329,
        "expected_route_segment_count_per_profile": 328,
        "blockers": route["blockers"],
        "next_required_stage": route["next_required_stage"],
        "authority": dict(COLLISION_AUTHORITY),
    }
    collision = {
        **collision_core,
        "route_bound_collision_qualification_sha256": _sha(collision_core),
    }
    selected = profiles[qualification["active_profile"]]
    entry_core = {
        "schema": ENTRY_SCHEMA,
        "status": ENTRY_PASS,
        "disposition": "PASS",
        "active_profile": qualification["active_profile"],
        "route_bound_collision_qualification_sha256": collision[
            "route_bound_collision_qualification_sha256"
        ],
        "source_profiled_partition_collision_evaluation_sha256": evaluation[
            "profiled_partition_collision_evaluation_sha256"
        ],
        "source_profiled_route_clearance_reconstruction_sha256": route[
            "profiled_route_clearance_reconstruction_sha256"
        ],
        "route_envelope_binding_sha256": selected["route_envelope_binding_sha256"],
        "installed_collision_profile_sha256": selected[
            "installed_collision_profile_sha256"
        ],
        "profiled_entry_route_qualification": qualification,
        "profiled_entry_route_qualification_sha256": qualification[
            "profiled_entry_route_qualification_sha256"
        ],
        "observed_route_entry_sha256": qualification["observed_route_entry_sha256"],
        "observed_route_entry_sweep_sha256": qualification[
            "observed_route_entry_sweep_sha256"
        ],
        "observed_route_entry_coverage_sha256": qualification[
            "observed_route_entry_coverage_sha256"
        ],
        "exact_route_binding_verified_before_entry_qualification": True,
        "profile_separation_preserved": True,
        "blockers": [],
        "next_required_stage": qualification["next_required_stage"],
        "authority": dict(ENTRY_AUTHORITY),
    }
    entry = {
        **entry_core,
        "route_bound_entry_qualification_sha256": _sha(entry_core),
    }
    return documents, evaluation, collision, entry


def _ready():
    documents, evaluation, collision, entry = _bundle()
    result = subject.prepare_route_bound_entry_isaac_replay_handoff_v1(
        collision, entry, documents, evaluation, _selected_lock()
    )
    return collision, entry, result


def test_exact_route_bound_entry_prepares_non_replanning_isaac_handoff() -> None:
    _collision, entry, result = _ready()

    assert result["status"] == subject.STATUS_READY
    assert result["blockers"] == []
    assert result["isaac_replay_handoff"]["trajectory"]["sample_count"] == 329
    assert result["isaac_replay_handoff"]["isaac_replay_request"]["replan_allowed"] is False
    assert result["profiled_entry_route_qualification_sha256"] == entry[
        "profiled_entry_route_qualification_sha256"
    ]
    assert result["authority"] == subject.ZERO_AUTHORITY
    assert subject.parse_route_bound_entry_isaac_replay_handoff_v1(result) == result
    jsonschema.Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    ).validate(result)


def test_crossed_route_bound_collision_receipt_fails_before_nested_handoff(
    monkeypatch,
) -> None:
    documents, evaluation, collision, entry = _bundle()
    crossed = copy.deepcopy(collision)
    crossed["profiles"]["no_attachment"]["route_envelope_binding_sha256"] = "9" * 64
    core = dict(crossed)
    core.pop("route_bound_collision_qualification_sha256")
    crossed["route_bound_collision_qualification_sha256"] = _sha(core)
    called = False

    def unexpected(*args):
        nonlocal called
        called = True
        raise AssertionError("nested handoff must not run")

    monkeypatch.setattr(subject, "_prepare_nested", unexpected)
    with pytest.raises(
        subject.RouteBoundEntryIsaacReplayHandoffV1Error,
        match="lineage differ",
    ):
        subject.prepare_route_bound_entry_isaac_replay_handoff_v1(
            crossed, entry, documents, evaluation, _selected_lock()
        )
    assert called is False


def test_tampered_route_bound_entry_fails_closed() -> None:
    documents, evaluation, collision, entry = _bundle()
    entry["route_envelope_binding_sha256"] = "9" * 64
    with pytest.raises(ValueError, match="hash differs"):
        subject.prepare_route_bound_entry_isaac_replay_handoff_v1(
            collision, entry, documents, evaluation, _selected_lock()
        )


def test_blocked_entry_stops_before_nested_handoff(monkeypatch) -> None:
    documents, evaluation, collision, entry = _bundle()
    blocked = copy.deepcopy(entry)
    blocked["status"] = "BLOCKED_ROUTE_BOUND_PROFILED_ENTRY_ROUTE_EVIDENCE_INCOMPLETE"
    blocked["disposition"] = "BLOCKED"
    blocked["blockers"] = ["FRESH_ENTRY_REQUIRED"]
    blocked["next_required_stage"] = "CAPTURE_FRESH_ENTRY"
    blocked["profiled_entry_route_qualification"] = None
    blocked["profiled_entry_route_qualification_sha256"] = None
    blocked["observed_route_entry_sha256"] = None
    blocked["observed_route_entry_sweep_sha256"] = None
    blocked["observed_route_entry_coverage_sha256"] = None
    core = dict(blocked)
    core.pop("route_bound_entry_qualification_sha256")
    blocked["route_bound_entry_qualification_sha256"] = _sha(core)

    def unexpected(*args):
        raise AssertionError("nested handoff must not run")

    monkeypatch.setattr(subject, "_prepare_nested", unexpected)
    result = subject.prepare_route_bound_entry_isaac_replay_handoff_v1(
        collision, blocked, documents, evaluation, _selected_lock()
    )

    assert result["status"] == subject.STATUS_BLOCKED
    assert result["isaac_replay_handoff"] is None
    assert result["blockers"] == ["FRESH_ENTRY_REQUIRED"]
    assert subject.parse_route_bound_entry_isaac_replay_handoff_v1(result) == result


def test_parser_rejects_resealed_authority_tamper() -> None:
    _collision, _entry, result = _ready()
    changed = copy.deepcopy(result)
    changed["authority"]["physical_authority"] = True
    core = dict(changed)
    core.pop("route_bound_isaac_replay_handoff_sha256")
    changed["route_bound_isaac_replay_handoff_sha256"] = _sha(core)

    with pytest.raises(
        subject.RouteBoundEntryIsaacReplayHandoffV1Error,
        match="authority differs",
    ):
        subject.parse_route_bound_entry_isaac_replay_handoff_v1(changed)


def test_parser_rejects_resealed_ready_blockers() -> None:
    _collision, _entry, result = _ready()
    changed = copy.deepcopy(result)
    changed["blockers"] = ["UNEXPECTED"]
    core = dict(changed)
    core.pop("route_bound_isaac_replay_handoff_sha256")
    changed["route_bound_isaac_replay_handoff_sha256"] = _sha(core)

    with pytest.raises(
        subject.RouteBoundEntryIsaacReplayHandoffV1Error,
        match="lineage differs",
    ):
        subject.parse_route_bound_entry_isaac_replay_handoff_v1(changed)
