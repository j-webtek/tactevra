from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator
import pytest

from rocell.application.pre_camera_observability_v1 import (
    PreCameraObservabilityV1Error,
    build_pre_camera_observability_report_v1,
    parse_pre_camera_observability_report_v1,
)


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "software/scripts/build_pre_camera_observability_report_v1.py"
SCHEMA = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/pre_camera_observability_report_v1.schema.json"
).read_text(encoding="utf-8")))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _samples() -> list[dict]:
    rows = []
    sequence = 0
    outcomes = ("PASS", "BLOCKED", "PENDING")
    caches = ("MISS", "HIT", "NOT_APPLICABLE")
    for stage_number in range(11, 17):
        for index in range(20):
            outcome = outcomes[index % len(outcomes)]
            duration = stage_number * 1_000 + index
            decision = _digest(f"decision-{stage_number}-{index}")
            rows.append({
                "sequence": sequence,
                "stage_id": f"PC{stage_number}",
                "run_class": "COLD" if index < 10 else "WARM",
                "outcome": outcome,
                "started_monotonic_ns": sequence * 1_000_000,
                "finished_monotonic_ns": sequence * 1_000_000 + duration,
                "duration_ns": duration,
                "item_count": index + 1,
                "artifact_bytes": 100 + index,
                "cache_outcome": caches[index % len(caches)],
                "decision_code": {
                    "PASS": "ADMITTED", "BLOCKED": "SAFETY_BLOCKED",
                    "PENDING": "EVIDENCE_PENDING",
                }[outcome],
                "blocker_codes": [] if outcome == "PASS" else [{
                    "BLOCKED": "EVIDENCE_REJECTED",
                    "PENDING": "EVIDENCE_MISSING",
                }[outcome]],
                "decision_sha256_before": decision,
                "decision_sha256_after": decision,
                "correlation": {
                    "session_sha256": _digest(f"session-{stage_number}"),
                    "ai_batch_sha256": _digest("batch") if index % 2 else None,
                    "target_id": f"KEY_{index}" if index % 2 else None,
                    "plan_sha256": _digest("plan") if index % 3 else None,
                    "consumer_id": "planner-v2" if index % 3 else None,
                    "receipt_sha256": _digest("receipt") if index % 4 else None,
                },
            })
            sequence += 1
    return rows


def _build(samples: list[dict] | None = None) -> dict:
    return build_pre_camera_observability_report_v1(
        _samples() if samples is None else samples,
        report_id="pc17-fixture-001",
        evidence_class="SYNTHETIC_TIMING_FIXTURE",
    )


def test_report_is_strict_schema_valid_and_decision_neutral():
    report = _build()
    assert list(SCHEMA.iter_errors(report)) == []
    assert dict(parse_pre_camera_observability_report_v1(report)) == report
    assert report["sample_count"] == 120
    assert report["decision_hashes_unchanged"] is True
    assert report["timing_used_for_admission"] is False
    assert report["performance_authority"] is False
    assert report["physical_speed_claimed"] is False
    assert report["controller_commands"] == []
    assert report["hardware_writes"] == report["physical_movements"] == 0
    assert report["stage_summaries"][0]["summary"]["p95_duration_ns"] is not None
    assert report["stage_summaries"][0]["summary"]["p99_duration_ns"] is None
    assert report["overall_summary"]["p99_duration_ns"] is not None


@pytest.mark.parametrize(
    "mutation,match",
    (
        ("decision", "changed the decision"),
        ("duration", "duration differs"),
        ("outcome", "contradicts blockers"),
        ("path", "path-like"),
    ),
)
def test_unsafe_or_ambiguous_samples_reject(mutation: str, match: str):
    samples = _samples()
    if mutation == "decision":
        samples[0]["decision_sha256_after"] = "f" * 64
    elif mutation == "duration":
        samples[0]["duration_ns"] += 1
    elif mutation == "outcome":
        samples[0]["blocker_codes"] = ["SHOULD_NOT_EXIST"]
    else:
        samples[0]["correlation"]["target_id"] = "C:/private/target"
    with pytest.raises(PreCameraObservabilityV1Error, match=match):
        _build(samples)


@pytest.mark.parametrize("coverage", ("stage", "run_class", "outcome"))
def test_required_coverage_cannot_be_omitted(coverage: str):
    samples = _samples()
    if coverage == "stage":
        samples = [row for row in samples if row["stage_id"] != "PC16"]
    elif coverage == "run_class":
        samples = [row for row in samples if row["run_class"] != "WARM"]
    else:
        samples = [row for row in samples if row["outcome"] != "PENDING"]
    for sequence, row in enumerate(samples):
        row["sequence"] = sequence
    with pytest.raises(PreCameraObservabilityV1Error, match="required|cover"):
        _build(samples)


def test_rehashed_authority_mutation_still_rejects():
    report = _build()
    report["physical_authority"] = True
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    report["report_sha256"] = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()
    with pytest.raises(PreCameraObservabilityV1Error, match="derivation differs"):
        parse_pre_camera_observability_report_v1(report)


def test_cli_emits_the_same_bounded_report(tmp_path: Path):
    samples_path = tmp_path / "samples.json"
    samples_path.write_text(json.dumps(_samples()), encoding="utf-8")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join((
        str(ROOT / "software/src"), str(ROOT / "software"),
    ))
    result = subprocess.run(
        (
            sys.executable, str(SCRIPT), "--samples", str(samples_path),
            "--report-id", "pc17-fixture-001", "--evidence-class",
            "SYNTHETIC_TIMING_FIXTURE",
        ),
        capture_output=True, check=False, text=True, env=environment, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report == _build()
    assert report["camera_opened"] is report["transport_opened"] is False


def test_cli_rejects_duplicate_json_fields(tmp_path: Path):
    samples_path = tmp_path / "samples.json"
    samples_path.write_text('[{"sequence":0,"sequence":0}]', encoding="utf-8")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join((
        str(ROOT / "software/src"), str(ROOT / "software"),
    ))
    result = subprocess.run(
        (
            sys.executable, str(SCRIPT), "--samples", str(samples_path),
            "--report-id", "pc17-fixture-001", "--evidence-class",
            "SYNTHETIC_TIMING_FIXTURE",
        ),
        capture_output=True, check=False, text=True, env=environment, timeout=30,
    )
    assert result.returncode != 0
    assert "duplicate field" in result.stderr
