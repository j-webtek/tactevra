from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.typing_trace_journal_v1 import (
    MAX_ARTIFACT_BYTES,
    TRACE_STAGE_ORDER,
    TypingTraceJournalV1Error,
    build_typing_trace_journal_v1,
    parse_typing_trace_journal_v1,
    replay_typing_trace_journal_v1,
)


WORKSPACE = Path(__file__).resolve().parents[3]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _artifacts() -> dict[str, bytes]:
    return {
        stage: _canonical({"schema": f"fixture.{stage.lower()}.v1", "ordinal": index})
        for index, stage in enumerate(TRACE_STAGE_ORDER)
    }


def _journal():
    return build_typing_trace_journal_v1(
        _artifacts(), correlation_id="trace-robot-001", request_id="request-robot",
        ordered_target_ids=("R", "O", "B", "O", "T"))


def _rehash(document: dict) -> None:
    document.pop("typing_trace_journal_sha256", None)
    document["typing_trace_journal_sha256"] = hashlib.sha256(
        _canonical(document)).hexdigest()


def test_trace_is_deterministic_ordered_hash_chained_and_zero_authority():
    first, second = _journal(), _journal()
    assert first == second
    parsed = parse_typing_trace_journal_v1(
        first, expected_correlation_id="trace-robot-001",
        expected_request_id="request-robot")
    assert tuple(item["stage"] for item in parsed["stages"]) == TRACE_STAGE_ORDER
    assert parsed["ordered_target_ids"] == ("R", "O", "B", "O", "T")
    assert parsed["controller_commands"] == ()
    assert parsed["hardware_access"] is parsed["physical_authority"] is False
    schema = json.loads((
        WORKSPACE / "software/ai/schemas/typing_trace_journal_v1.schema.json"
    ).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(first)


def test_replay_is_identical_and_hardware_incapable():
    replay = replay_typing_trace_journal_v1(
        _journal(), _artifacts(), expected_correlation_id="trace-robot-001",
        expected_request_id="request-robot")
    assert replay["status"] == "IDENTICAL" and replay["identical"] is True
    assert replay["missing_stages"] == replay["mutated_stages"] == []
    assert replay["controller_commands"] == []
    assert replay["hardware_access"] is replay["physical_authority"] is False


def test_replay_detects_missing_mutated_truncated_and_extra_artifacts():
    artifacts = _artifacts()
    artifacts.pop("IK_SCREEN")
    artifacts["JOINT_SCHEDULE"] += b"mutation"
    artifacts["COLLISION_SCREEN"] = b""
    artifacts["UNREVIEWED"] = b"extra"
    replay = replay_typing_trace_journal_v1(
        _journal(), artifacts, expected_correlation_id="trace-robot-001",
        expected_request_id="request-robot")
    assert replay["status"] == "REPLAY_REJECTED"
    assert replay["identical"] is False
    assert replay["missing_stages"] == ["IK_SCREEN"]
    assert replay["mutated_stages"] == ["JOINT_SCHEDULE", "COLLISION_SCREEN"]
    assert replay["extra_stages"] == ["UNREVIEWED"]


@pytest.mark.parametrize(("field", "value", "message"), [
    ("correlation_id", "trace-other", "correlation identity is crossed"),
    ("request_id", "request-other", "request identity is crossed"),
])
def test_replay_rejects_crossed_identity(field, value, message):
    arguments = dict(
        expected_correlation_id="trace-robot-001",
        expected_request_id="request-robot")
    arguments[f"expected_{field}"] = value
    with pytest.raises(TypingTraceJournalV1Error, match=message):
        replay_typing_trace_journal_v1(_journal(), _artifacts(), **arguments)


def test_independently_rehashed_reorder_and_truncation_reject():
    reordered = deepcopy(_journal())
    reordered["stages"].reverse()
    _rehash(reordered)
    with pytest.raises(TypingTraceJournalV1Error, match="order or bounds"):
        parse_typing_trace_journal_v1(reordered)

    truncated = deepcopy(_journal())
    truncated["stages"].pop()
    _rehash(truncated)
    with pytest.raises(TypingTraceJournalV1Error, match="accounting"):
        parse_typing_trace_journal_v1(truncated)


def test_artifacts_are_bounded_and_exactly_ordered():
    artifacts = _artifacts()
    artifacts["REQUEST"] = b"x" * (MAX_ARTIFACT_BYTES + 1)
    with pytest.raises(TypingTraceJournalV1Error, match="size"):
        build_typing_trace_journal_v1(
            artifacts, correlation_id="trace-robot-001", request_id="request-robot",
            ordered_target_ids=("R",))
    reordered = {key: _artifacts()[key] for key in reversed(TRACE_STAGE_ORDER)}
    with pytest.raises(TypingTraceJournalV1Error, match="exact stage order"):
        build_typing_trace_journal_v1(
            reordered, correlation_id="trace-robot-001", request_id="request-robot",
            ordered_target_ids=("R",))
