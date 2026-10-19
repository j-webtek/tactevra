from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

import rocell.application.profiled_entry_route_isaac_replay_handoff_v1 as subject
from rocell.application.fixed_camera_keyboard_profiled_entry_route_qualification_v1 import (
    qualify_fixed_camera_keyboard_profiled_entry_route_v1,
)

from test_fixed_camera_keyboard_profiled_entry_route_qualification_v1 import (
    _bundle,
)


SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "ai/schemas/profiled_entry_route_isaac_replay_handoff_v1.schema.json"
)
LOCK_PATH = Path(__file__).resolve().parents[2] / "config/isaac_sim_toolchain_lock.json"


def _qualification():
    documents, evaluation, entry, sweep, coverage = _bundle()
    receipt = qualify_fixed_camera_keyboard_profiled_entry_route_v1(
        documents,
        evaluation,
        "no_attachment",
        entry,
        sweep,
        coverage,
    )
    return documents, evaluation, receipt


def _selected_lock() -> dict:
    return {
        "schema": "rocell.isaac_sim_toolchain_lock.v1",
        "selection_status": "SELECTED",
        "isaac_sim_version": "test-only",
        "installation_sha256": "1" * 64,
        "extension_lock_sha256": "2" * 64,
        "settings_profile_sha256": "3" * 64,
        "runner_platform": "offline-test",
        "launch_method": "test-only",
        "license_review_status": "REVIEWED_FOR_INTERNAL_INTEGRATION",
        "hardware_access": False,
        "physical_authority": False,
        "wire_commands": [],
    }


def test_current_selected_lock_prepares_exact_route_for_native_replay() -> None:
    documents, evaluation, qualification = _qualification()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    result = subject.prepare_profiled_entry_route_isaac_replay_handoff_v1(
        qualification,
        documents,
        evaluation,
        lock,
    )
    assert result["status"] == subject.STATUS_READY
    assert result["trajectory"]["sample_count"] == 329
    assert result["trajectory"]["segment_count"] == 328
    assert result["isaac_replay_request"]["replan_allowed"] is False
    assert result["isaac_replay_request"]["isaac_sim_version"] == "6.1.0.0"
    assert result["blockers"] == []
    assert result["authority"] == subject.ZERO_AUTHORITY
    jsonschema.Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    ).validate(result)


def test_selected_lock_prepares_exact_non_replanning_request() -> None:
    documents, evaluation, qualification = _qualification()
    result = subject.prepare_profiled_entry_route_isaac_replay_handoff_v1(
        qualification,
        documents,
        evaluation,
        _selected_lock(),
    )
    assert result["status"] == subject.STATUS_READY
    assert result["blockers"] == []
    assert result["isaac_replay_request"]["replan_allowed"] is False
    assert (
        result["isaac_replay_request"]["trajectory_sha256"]
        == result["trajectory"]["trajectory_sha256"]
    )


def test_crossed_attachment_profile_is_rejected() -> None:
    documents, evaluation, qualification = _qualification()
    crossed = copy.deepcopy(qualification)
    crossed["active_profile"] = "stylus_attachment"
    core = dict(crossed)
    core.pop("profiled_entry_route_qualification_sha256")
    import hashlib

    crossed["profiled_entry_route_qualification_sha256"] = hashlib.sha256(
        json.dumps(
            core,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    with pytest.raises(
        subject.ProfiledEntryRouteIsaacReplayHandoffV1Error,
        match="lineage differ",
    ):
        subject.prepare_profiled_entry_route_isaac_replay_handoff_v1(
            crossed,
            documents,
            evaluation,
            _selected_lock(),
        )


def test_tampered_qualification_is_rejected() -> None:
    documents, evaluation, qualification = _qualification()
    qualification = copy.deepcopy(qualification)
    qualification["route_segment_count"] = 327
    with pytest.raises(
        subject.ProfiledEntryRouteIsaacReplayHandoffV1Error,
        match="qualification hash differs",
    ):
        subject.prepare_profiled_entry_route_isaac_replay_handoff_v1(
            qualification,
            documents,
            evaluation,
            _selected_lock(),
        )
