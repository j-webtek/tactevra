"""Canonical zero-I/O PC6 typing trace manifest and deterministic replay."""

from __future__ import annotations

import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping


SCHEMA = "rocell.typing_trace_journal.v1"
REPLAY_SCHEMA = "rocell.typing_trace_replay.v1"
STATUS = "SEALED_ZERO_AUTHORITY_TRACE"
MAX_ARTIFACT_BYTES = 256 * 1024
TRACE_STAGE_ORDER = (
    "REQUEST",
    "AI_BATCH",
    "INGRESS",
    "EXECUTION_PLAN",
    "TRAJECTORY_PLAN",
    "IK_SCREEN",
    "JOINT_SCHEDULE",
    "COLLISION_SCREEN",
    "CONTROLLER_PREVIEW",
    "PERMIT_POLICY",
    "COMMAND_ENCODING",
    "DISPATCH_REHEARSAL",
    "FEEDBACK_REHEARSAL",
    "EFFECT_VERIFICATION_PLACEHOLDER",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class TypingTraceJournalV1Error(ValueError):
    """The trace is malformed, crossed, unbounded, or claims authority."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingTraceJournalV1Error("trace value is not canonical JSON") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(value: object) -> str:
    return _sha256_bytes(_canonical(value))


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise TypingTraceJournalV1Error(f"{label} must be a SHA-256 digest")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise TypingTraceJournalV1Error(f"{label} must be a bounded identifier")
    return value


def _artifact_bytes(value: object, stage: str) -> bytes:
    if not isinstance(value, bytes):
        raise TypingTraceJournalV1Error(f"{stage} artifact must be bytes")
    if not value or len(value) > MAX_ARTIFACT_BYTES:
        raise TypingTraceJournalV1Error(f"{stage} artifact size is invalid")
    return value


def build_typing_trace_journal_v1(
    artifacts: Mapping[str, bytes],
    *,
    correlation_id: str,
    request_id: str,
    ordered_target_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Seal references to every PC6 stage without retaining raw payloads."""

    correlation = _identifier(correlation_id, "correlation_id")
    request = _identifier(request_id, "request_id")
    if not isinstance(artifacts, Mapping) or tuple(artifacts) != TRACE_STAGE_ORDER:
        raise TypingTraceJournalV1Error("trace artifacts must use exact stage order")
    if (
        not isinstance(ordered_target_ids, tuple)
        or not 1 <= len(ordered_target_ids) <= 64
        or any(
            not isinstance(item, str)
            or _IDENTIFIER.fullmatch(item) is None
            for item in ordered_target_ids
        )
    ):
        raise TypingTraceJournalV1Error("ordered_target_ids are invalid")
    stages = []
    previous = "0" * 64
    for ordinal, stage in enumerate(TRACE_STAGE_ORDER):
        payload = _artifact_bytes(artifacts[stage], stage)
        core = {
            "ordinal": ordinal,
            "stage": stage,
            "artifact_bytes": len(payload),
            "artifact_sha256": _sha256_bytes(payload),
            "previous_stage_sha256": previous,
        }
        stage_sha256 = _sha256(core)
        stages.append({**core, "stage_sha256": stage_sha256})
        previous = stage_sha256
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "correlation_id": correlation,
        "request_id": request,
        "action_count": len(ordered_target_ids),
        "ordered_target_ids": list(ordered_target_ids),
        "stages": stages,
        "trace_tail_sha256": previous,
        "controller_commands": [],
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "typing_trace_journal_sha256": _sha256(core)}


def parse_typing_trace_journal_v1(
    document: Mapping[str, Any],
    *,
    expected_correlation_id: str | None = None,
    expected_request_id: str | None = None,
) -> Mapping[str, Any]:
    """Verify exact fields, identities, chain order, hashes, and zero authority."""

    fields = {
        "schema", "status", "correlation_id", "request_id", "action_count",
        "ordered_target_ids", "stages", "trace_tail_sha256",
        "controller_commands", "hardware_access", "physical_authority",
        "typing_trace_journal_sha256",
    }
    if not isinstance(document, Mapping) or set(document) != fields:
        raise TypingTraceJournalV1Error("trace journal fields are not exact")
    unsigned = dict(document)
    claimed = _digest(
        unsigned.pop("typing_trace_journal_sha256"),
        "typing_trace_journal_sha256",
    )
    if _sha256(unsigned) != claimed:
        raise TypingTraceJournalV1Error("trace journal hash is invalid")
    if document["schema"] != SCHEMA or document["status"] != STATUS:
        raise TypingTraceJournalV1Error("trace journal schema or status is invalid")
    correlation = _identifier(document["correlation_id"], "correlation_id")
    request = _identifier(document["request_id"], "request_id")
    if expected_correlation_id is not None and correlation != _identifier(
        expected_correlation_id, "expected_correlation_id"
    ):
        raise TypingTraceJournalV1Error("trace correlation identity is crossed")
    if expected_request_id is not None and request != _identifier(
        expected_request_id, "expected_request_id"
    ):
        raise TypingTraceJournalV1Error("trace request identity is crossed")
    targets = document["ordered_target_ids"]
    if (
        not isinstance(targets, list)
        or not 1 <= len(targets) <= 64
        or any(not isinstance(item, str) or _IDENTIFIER.fullmatch(item) is None
               for item in targets)
        or isinstance(document["action_count"], bool)
        or document["action_count"] != len(targets)
    ):
        raise TypingTraceJournalV1Error("trace action accounting is invalid")
    stages = document["stages"]
    if not isinstance(stages, list) or len(stages) != len(TRACE_STAGE_ORDER):
        raise TypingTraceJournalV1Error("trace stage accounting is invalid")
    previous = "0" * 64
    frozen_stages = []
    for ordinal, (expected_stage, item) in enumerate(zip(TRACE_STAGE_ORDER, stages)):
        stage_fields = {
            "ordinal", "stage", "artifact_bytes", "artifact_sha256",
            "previous_stage_sha256", "stage_sha256",
        }
        if not isinstance(item, Mapping) or set(item) != stage_fields:
            raise TypingTraceJournalV1Error("trace stage fields are not exact")
        if (
            isinstance(item["ordinal"], bool)
            or not isinstance(item["ordinal"], int)
            or item["ordinal"] != ordinal
            or item["stage"] != expected_stage
            or isinstance(item["artifact_bytes"], bool)
            or not isinstance(item["artifact_bytes"], int)
            or not 1 <= item["artifact_bytes"] <= MAX_ARTIFACT_BYTES
            or item["previous_stage_sha256"] != previous
        ):
            raise TypingTraceJournalV1Error("trace stage order or bounds are invalid")
        _digest(item["artifact_sha256"], "artifact_sha256")
        claimed_stage = _digest(item["stage_sha256"], "stage_sha256")
        if _sha256({key: item[key] for key in item if key != "stage_sha256"}) != claimed_stage:
            raise TypingTraceJournalV1Error("trace stage hash is invalid")
        previous = claimed_stage
        frozen_stages.append(MappingProxyType(dict(item)))
    if _digest(document["trace_tail_sha256"], "trace_tail_sha256") != previous:
        raise TypingTraceJournalV1Error("trace tail is invalid")
    if (
        document["controller_commands"] != []
        or document["hardware_access"] is not False
        or document["physical_authority"] is not False
    ):
        raise TypingTraceJournalV1Error("trace journal violates zero authority")
    frozen = dict(document)
    frozen["ordered_target_ids"] = tuple(targets)
    frozen["stages"] = tuple(frozen_stages)
    frozen["controller_commands"] = ()
    return MappingProxyType(frozen)


def replay_typing_trace_journal_v1(
    document: Mapping[str, Any],
    artifacts: Mapping[str, bytes],
    *,
    expected_correlation_id: str,
    expected_request_id: str,
) -> dict[str, Any]:
    """Compare retained artifacts with the sealed trace; never execute them."""

    trace = parse_typing_trace_journal_v1(
        document,
        expected_correlation_id=expected_correlation_id,
        expected_request_id=expected_request_id,
    )
    if (
        not isinstance(artifacts, Mapping)
        or any(not isinstance(key, str) for key in artifacts)
    ):
        raise TypingTraceJournalV1Error("replay artifacts must be a string-keyed mapping")
    missing: list[str] = []
    mutated: list[str] = []
    extra = sorted(set(artifacts) - set(TRACE_STAGE_ORDER))
    for item in trace["stages"]:
        stage = item["stage"]
        if stage not in artifacts:
            missing.append(stage)
            continue
        try:
            payload = _artifact_bytes(artifacts[stage], stage)
        except TypingTraceJournalV1Error:
            mutated.append(stage)
            continue
        if (
            len(payload) != item["artifact_bytes"]
            or _sha256_bytes(payload) != item["artifact_sha256"]
        ):
            mutated.append(stage)
    identical = not missing and not mutated and not extra
    core = {
        "schema": REPLAY_SCHEMA,
        "status": "IDENTICAL" if identical else "REPLAY_REJECTED",
        "typing_trace_journal_sha256": trace["typing_trace_journal_sha256"],
        "correlation_id": trace["correlation_id"],
        "request_id": trace["request_id"],
        "identical": identical,
        "missing_stages": missing,
        "mutated_stages": mutated,
        "extra_stages": extra,
        "controller_commands": [],
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "typing_trace_replay_sha256": _sha256(core)}


__all__ = [
    "MAX_ARTIFACT_BYTES", "REPLAY_SCHEMA", "SCHEMA", "STATUS",
    "TRACE_STAGE_ORDER", "TypingTraceJournalV1Error",
    "build_typing_trace_journal_v1", "parse_typing_trace_journal_v1",
    "replay_typing_trace_journal_v1",
]
