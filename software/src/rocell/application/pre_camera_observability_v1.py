"""Decision-neutral timing and observability contract for PC11-PC16."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence


SCHEMA = "rocell.pre_camera_observability_report.v1"
STAGES = ("PC11", "PC12", "PC13", "PC14", "PC15", "PC16")
RUN_CLASSES = {"COLD", "WARM"}
OUTCOMES = {"PASS", "BLOCKED", "PENDING"}
CACHE_OUTCOMES = {"HIT", "MISS", "NOT_APPLICABLE"}
MAX_SAMPLES = 4096
MAX_ARTIFACT_BYTES = 1 << 34
MAX_ITEM_COUNT = 1_000_000
_HASH = re.compile(r"^[0-9a-f]{64}$")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$")
_REPORT_FIELDS = {
    "schema", "report_id", "evidence_class", "stage_catalog",
    "sample_count", "samples", "stage_summaries", "overall_summary",
    "decision_hashes_unchanged", "timing_used_for_admission",
    "performance_authority", "physical_speed_claimed", "camera_opened",
    "transport_opened", "controller_started", "controller_commands",
    "hardware_writes", "physical_movements", "physical_authority",
    "report_sha256",
}
_SAMPLE_FIELDS = {
    "sequence", "stage_id", "run_class", "outcome", "started_monotonic_ns",
    "finished_monotonic_ns", "duration_ns", "item_count", "artifact_bytes",
    "cache_outcome", "decision_code", "blocker_codes",
    "decision_sha256_before", "decision_sha256_after", "correlation",
}
_CORRELATION_FIELDS = {
    "session_sha256", "ai_batch_sha256", "target_id", "plan_sha256",
    "consumer_id", "receipt_sha256",
}
_SUMMARY_FIELDS = {
    "sample_count", "total_duration_ns", "minimum_duration_ns",
    "maximum_duration_ns", "p50_duration_ns", "p95_duration_ns",
    "p99_duration_ns", "total_item_count", "total_artifact_bytes",
    "run_class_counts", "outcome_counts", "cache_outcome_counts",
    "decision_codes", "blocker_codes",
}


class PreCameraObservabilityV1Error(ValueError):
    """An observation can affect decisions or violates bounded telemetry."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise PreCameraObservabilityV1Error(f"{label} is not a SHA-256 digest")
    return value


def _code(value: object, label: str) -> str:
    if not isinstance(value, str) or _CODE.fullmatch(value) is None:
        raise PreCameraObservabilityV1Error(f"{label} is not a stable code")
    return value


def _identifier(value: object, label: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if (
        not isinstance(value, str) or not value or len(value) > 192
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:@/-"
               for character in value)
        or ":\\" in value or "://" in value or value.startswith(("/", "\\"))
        or (
            len(value) >= 3 and value[0].isalpha()
            and value[1] == ":" and value[2] in "\\/"
        )
    ):
        raise PreCameraObservabilityV1Error(f"{label} is invalid or path-like")
    return value


def _integer(value: object, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise PreCameraObservabilityV1Error(f"{label} is outside its bound")
    return value


def _normalize_sample(value: object, sequence: int) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _SAMPLE_FIELDS:
        raise PreCameraObservabilityV1Error(f"sample {sequence} fields differ")
    if value.get("sequence") != sequence:
        raise PreCameraObservabilityV1Error(f"sample {sequence} sequence differs")
    stage = value.get("stage_id")
    run_class = value.get("run_class")
    outcome = value.get("outcome")
    cache = value.get("cache_outcome")
    if stage not in STAGES or run_class not in RUN_CLASSES or outcome not in OUTCOMES:
        raise PreCameraObservabilityV1Error(f"sample {sequence} classification differs")
    if cache not in CACHE_OUTCOMES:
        raise PreCameraObservabilityV1Error(f"sample {sequence} cache outcome differs")
    started = _integer(value.get("started_monotonic_ns"), "started time", 2**63 - 1)
    finished = _integer(value.get("finished_monotonic_ns"), "finished time", 2**63 - 1)
    duration = _integer(value.get("duration_ns"), "duration", 2**63 - 1)
    if finished < started or finished - started != duration:
        raise PreCameraObservabilityV1Error(f"sample {sequence} monotonic duration differs")
    before = _digest(value.get("decision_sha256_before"), "decision before")
    after = _digest(value.get("decision_sha256_after"), "decision after")
    if before != after:
        raise PreCameraObservabilityV1Error(
            f"sample {sequence} instrumentation changed the decision"
        )
    blockers = value.get("blocker_codes")
    if (
        not isinstance(blockers, list) or len(blockers) > 64
        or len(blockers) != len(set(blockers))
    ):
        raise PreCameraObservabilityV1Error(f"sample {sequence} blockers differ")
    normalized_blockers = [_code(item, "blocker code") for item in blockers]
    if (outcome == "PASS") != (not normalized_blockers):
        raise PreCameraObservabilityV1Error(
            f"sample {sequence} outcome contradicts blockers"
        )
    correlation = value.get("correlation")
    if not isinstance(correlation, Mapping) or set(correlation) != _CORRELATION_FIELDS:
        raise PreCameraObservabilityV1Error(f"sample {sequence} correlation differs")
    normalized_correlation = {
        "session_sha256": _digest(
            correlation.get("session_sha256"), "session correlation"
        ),
        "ai_batch_sha256": _digest(
            correlation.get("ai_batch_sha256"), "AI batch correlation", nullable=True
        ),
        "target_id": _identifier(
            correlation.get("target_id"), "target correlation", nullable=True
        ),
        "plan_sha256": _digest(
            correlation.get("plan_sha256"), "plan correlation", nullable=True
        ),
        "consumer_id": _identifier(
            correlation.get("consumer_id"), "consumer correlation", nullable=True
        ),
        "receipt_sha256": _digest(
            correlation.get("receipt_sha256"), "receipt correlation", nullable=True
        ),
    }
    return {
        "sequence": sequence, "stage_id": stage, "run_class": run_class,
        "outcome": outcome, "started_monotonic_ns": started,
        "finished_monotonic_ns": finished, "duration_ns": duration,
        "item_count": _integer(value.get("item_count"), "item count", MAX_ITEM_COUNT),
        "artifact_bytes": _integer(
            value.get("artifact_bytes"), "artifact bytes", MAX_ARTIFACT_BYTES
        ),
        "cache_outcome": cache,
        "decision_code": _code(value.get("decision_code"), "decision code"),
        "blocker_codes": normalized_blockers,
        "decision_sha256_before": before, "decision_sha256_after": after,
        "correlation": normalized_correlation,
    }


def _nearest_rank(values: list[int], probability: float) -> int:
    ordered = sorted(values)
    return ordered[max(1, math.ceil(probability * len(ordered))) - 1]


def _summary(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    durations = [row["duration_ns"] for row in samples]
    count = len(samples)
    return {
        "sample_count": count,
        "total_duration_ns": sum(durations),
        "minimum_duration_ns": min(durations) if durations else None,
        "maximum_duration_ns": max(durations) if durations else None,
        "p50_duration_ns": _nearest_rank(durations, 0.50) if count >= 2 else None,
        "p95_duration_ns": _nearest_rank(durations, 0.95) if count >= 20 else None,
        "p99_duration_ns": _nearest_rank(durations, 0.99) if count >= 100 else None,
        "total_item_count": sum(row["item_count"] for row in samples),
        "total_artifact_bytes": sum(row["artifact_bytes"] for row in samples),
        "run_class_counts": {
            name: sum(row["run_class"] == name for row in samples)
            for name in sorted(RUN_CLASSES)
        },
        "outcome_counts": {
            name: sum(row["outcome"] == name for row in samples)
            for name in sorted(OUTCOMES)
        },
        "cache_outcome_counts": {
            name: sum(row["cache_outcome"] == name for row in samples)
            for name in sorted(CACHE_OUTCOMES)
        },
        "decision_codes": sorted({row["decision_code"] for row in samples}),
        "blocker_codes": sorted({
            blocker for row in samples for blocker in row["blocker_codes"]
        }),
    }


def build_pre_camera_observability_report_v1(
    samples: Sequence[Mapping[str, Any]], *, report_id: str,
    evidence_class: str,
) -> dict[str, Any]:
    """Aggregate bounded observations without feeding timing into admission."""

    if not 1 <= len(samples) <= MAX_SAMPLES:
        raise PreCameraObservabilityV1Error("sample count is outside its bound")
    normalized = [_normalize_sample(row, index) for index, row in enumerate(samples)]
    observed_stages = {row["stage_id"] for row in normalized}
    if observed_stages != set(STAGES):
        raise PreCameraObservabilityV1Error("observations do not cover PC11-PC16")
    if {row["run_class"] for row in normalized} != RUN_CLASSES:
        raise PreCameraObservabilityV1Error("cold and warm observations are required")
    if {row["outcome"] for row in normalized} != OUTCOMES:
        raise PreCameraObservabilityV1Error("pass, blocked, and pending are required")
    if evidence_class not in {"HOST_MEASURED_OFFLINE", "SYNTHETIC_TIMING_FIXTURE"}:
        raise PreCameraObservabilityV1Error("evidence class differs")
    stage_summaries = [
        {
            "stage_id": stage,
            "summary": _summary([
                row for row in normalized if row["stage_id"] == stage
            ]),
        }
        for stage in STAGES
    ]
    core = {
        "schema": SCHEMA,
        "report_id": _identifier(report_id, "report_id"),
        "evidence_class": evidence_class,
        "stage_catalog": list(STAGES), "sample_count": len(normalized),
        "samples": normalized, "stage_summaries": stage_summaries,
        "overall_summary": _summary(normalized),
        "decision_hashes_unchanged": True,
        "timing_used_for_admission": False, "performance_authority": False,
        "physical_speed_claimed": False, "camera_opened": False,
        "transport_opened": False, "controller_started": False,
        "controller_commands": [], "hardware_writes": 0,
        "physical_movements": 0, "physical_authority": False,
    }
    return {**core, "report_sha256": _sha(core)}


def parse_pre_camera_observability_report_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise PreCameraObservabilityV1Error("observability report fields differ")
    unsigned = dict(value)
    digest = unsigned.pop("report_sha256")
    if not isinstance(digest, str) or _sha(unsigned) != digest:
        raise PreCameraObservabilityV1Error("observability report hash mismatch")
    samples = value.get("samples")
    if not isinstance(samples, list):
        raise PreCameraObservabilityV1Error("observability samples differ")
    rebuilt = build_pre_camera_observability_report_v1(
        samples, report_id=value.get("report_id"),
        evidence_class=value.get("evidence_class"),
    )
    if rebuilt != dict(value):
        raise PreCameraObservabilityV1Error("observability derivation differs")
    return MappingProxyType(dict(value))


def _load_samples(path: Path) -> list[dict[str, Any]]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise PreCameraObservabilityV1Error(
                    f"sample file contains duplicate field {key!r}"
                )
            result[key] = item
        return result

    def reject_constant(value: str) -> None:
        raise PreCameraObservabilityV1Error(
            f"sample file contains non-finite value {value}"
        )

    try:
        if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise PreCameraObservabilityV1Error("sample file is unavailable or oversized")
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise PreCameraObservabilityV1Error("sample file is not JSON") from exc
    if not isinstance(value, list):
        raise PreCameraObservabilityV1Error("sample file must contain an array")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--report-id", required=True)
    parser.add_argument(
        "--evidence-class", choices=(
            "HOST_MEASURED_OFFLINE", "SYNTHETIC_TIMING_FIXTURE"
        ), required=True,
    )
    args = parser.parse_args(argv)
    try:
        report = build_pre_camera_observability_report_v1(
            _load_samples(args.samples), report_id=args.report_id,
            evidence_class=args.evidence_class,
        )
        parse_pre_camera_observability_report_v1(report)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


__all__ = [
    "CACHE_OUTCOMES", "MAX_SAMPLES", "OUTCOMES", "RUN_CLASSES", "SCHEMA",
    "STAGES", "PreCameraObservabilityV1Error",
    "build_pre_camera_observability_report_v1",
    "parse_pre_camera_observability_report_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())
