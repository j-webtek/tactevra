from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

import rocell.application.pre_camera_host_benchmark_v1 as benchmark
from rocell.application.pre_camera_observability_v1 import (
    parse_pre_camera_observability_report_v1,
)


ROOT = Path(__file__).resolve().parents[3]
RETAINED = ROOT / "software/ai/eval/pre_camera_host_benchmark_v1.json"
VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/pre_camera_observability_report_v1.schema.json"
).read_text(encoding="utf-8")))


def test_retained_host_report_is_strict_and_hardware_incapable():
    report = json.loads(RETAINED.read_text(encoding="utf-8"))
    assert list(VALIDATOR.iter_errors(report)) == []
    assert dict(parse_pre_camera_observability_report_v1(report)) == report
    assert report["evidence_class"] == "HOST_MEASURED_OFFLINE"
    assert report["sample_count"] == 120
    assert [row["stage_id"] for row in report["stage_summaries"]] == [
        "PC11", "PC12", "PC13", "PC14", "PC15", "PC16",
    ]
    assert all(row["summary"]["sample_count"] == 20 for row in report["stage_summaries"])
    assert all(row["summary"]["p95_duration_ns"] is not None for row in report["stage_summaries"])
    assert report["overall_summary"]["p99_duration_ns"] is not None
    assert set(report["overall_summary"]["outcome_counts"]) == {
        "PASS", "BLOCKED", "PENDING",
    }
    assert all(
        row["decision_sha256_before"] == row["decision_sha256_after"]
        for row in report["samples"]
    )
    assert report["timing_used_for_admission"] is False
    assert report["performance_authority"] is False
    assert report["physical_speed_claimed"] is False
    assert report["camera_opened"] is report["transport_opened"] is False
    assert report["controller_started"] is report["physical_authority"] is False
    assert report["controller_commands"] == []
    assert report["hardware_writes"] == report["physical_movements"] == 0


def test_runner_preserves_decisions_with_deterministic_stage_adapter(
    monkeypatch, tmp_path: Path,
):
    def fake_stage(stage: str, workspace: Path, fixture: Path, variant: int):
        del workspace, fixture
        if stage in {"PC11", "PC14"}:
            outcome = ("PASS", "BLOCKED", "PENDING")[variant % 3]
        elif stage in {"PC13", "PC16"}:
            outcome = "BLOCKED" if variant % 2 else "PASS"
        else:
            outcome = "PASS"
        blockers = [] if outcome == "PASS" else [f"{stage}_{outcome}_FIXTURE"]
        decision = {
            "stage": stage, "variant": variant, "outcome": outcome,
            "physical_authority": False,
        }
        return lambda: dict(decision), outcome, blockers, 1

    ticks = iter(range(1_000_000, 2_000_000))
    monkeypatch.setattr(benchmark, "_stage_operation", fake_stage)
    monkeypatch.setattr(benchmark.time, "perf_counter_ns", lambda: next(ticks))
    report = benchmark.run_pre_camera_host_benchmark_v1(
        tmp_path, samples_per_stage=20, report_id="pc17-test-run",
    )
    assert report["sample_count"] == 120
    assert report["overall_summary"]["minimum_duration_ns"] == 1
    assert report["overall_summary"]["maximum_duration_ns"] == 1
    assert all(
        row["decision_sha256_before"] == row["decision_sha256_after"]
        for row in report["samples"]
    )
    assert report["physical_authority"] is False
