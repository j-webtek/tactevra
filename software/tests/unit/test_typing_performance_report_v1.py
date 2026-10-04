from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from rocell.application.pre_camera_typing_qualification_basis_v1 import (
    load_pre_camera_typing_qualification_basis_v1,
)
from rocell.application.typing_performance_report_v1 import (
    REQUIRED_SCENARIOS,
    STAGES,
    TypingBenchmarkPolicyV1,
    TypingBenchmarkSampleV1,
    TypingPerformanceReportV1Error,
    build_typing_performance_report_v1,
)


H = "a" * 64
ROOT = Path(__file__).resolve().parents[3]


def _policy():
    basis = load_pre_camera_typing_qualification_basis_v1(ROOT)
    return basis, TypingBenchmarkPolicyV1.from_pc0_basis(basis)


def _samples(iterations: int = 50):
    result = []
    for scenario_index, scenario in enumerate(REQUIRED_SCENARIOS):
        for iteration in range(iterations):
            base = 1_000 + scenario_index * 100 + iteration
            stages = {stage: base + index for index, stage in enumerate(STAGES)}
            result.append(TypingBenchmarkSampleV1(
                scenario=scenario,
                iteration=iteration,
                action_count=64 if scenario == "LONG_STRING" else 4,
                cache_state=(
                    "COLD" if scenario == "COLD_CACHE"
                    else "WARM" if scenario == "WARM_CACHE"
                    else "NOT_APPLICABLE"),
                cache_result=(
                    "MISS" if scenario == "COLD_CACHE"
                    else "HIT_REVALIDATED" if scenario == "WARM_CACHE"
                    else "NOT_APPLICABLE"),
                outcome=("REJECTED" if scenario == "FORCED_REJECTION"
                         else "ADMITTED"),
                stage_cpu_ns=stages,
                total_cpu_ns=sum(stages.values()) + 100,
                peak_screening_samples=4096 if scenario == "LONG_STRING" else 200,
                serialized_artifact_bytes=100_000 + base,
                peak_process_memory_bytes=32 * 1024 * 1024,
                predicted_route_duration_ns=(
                    2_000_000 if scenario == "DIRECT_HOVER"
                    else 5_000_000 if scenario == "PARK_BASELINE"
                    else 3_000_000),
                estimated_cache_time_saved_ns=(
                    500 if scenario == "WARM_CACHE" else 0),
            ))
    return result


def test_complete_benchmark_report_has_percentiles_resources_and_no_authority():
    basis, policy = _policy()
    report = build_typing_performance_report_v1(
        _samples(), policy=policy, qualification_basis_sha256=basis.basis_sha256)
    assert report["status"] == "PASS_SYNTHETIC_OFFLINE"
    assert report["sample_count"] == 450
    assert tuple(report["scenario_order"]) == REQUIRED_SCENARIOS
    assert report["stage_cpu_ns"]["planning"]["count"] == 450
    assert report["stage_cpu_ns"]["planning"]["p50"] <= (
        report["stage_cpu_ns"]["planning"]["p95"])
    assert report["stage_cpu_ns"]["planning"]["p95"] <= (
        report["stage_cpu_ns"]["planning"]["p99"])
    assert all(report["resources"]["ceilings_passed"].values())
    assert report["cache"] == {
        "cold_misses": 50,
        "warm_hits": 50,
        "estimated_time_saved_ns": 25_000,
    }
    assert report["route_comparison"]["direct_hover_predicted_p50_ns"] < (
        report["route_comparison"]["park_baseline_predicted_p50_ns"])
    assert report["simulation_timing_is_physical_claim"] is False
    assert report["measured_typing_speed_claimed"] is False
    assert report["controller_commands"] == []
    assert report["hardware_commands_generated"] == 0
    assert report["hardware_access"] is report["physical_authority"] is False


def test_report_is_byte_deterministic_for_identical_samples():
    basis, policy = _policy()
    first = build_typing_performance_report_v1(
        _samples(), policy=policy, qualification_basis_sha256=basis.basis_sha256)
    second = build_typing_performance_report_v1(
        _samples(), policy=policy, qualification_basis_sha256=basis.basis_sha256)
    assert first == second


def test_missing_scenario_iterations_reject():
    basis, policy = _policy()
    samples = [sample for sample in _samples() if sample.scenario != "PUNCTUATION"]
    with pytest.raises(TypingPerformanceReportV1Error, match="PUNCTUATION"):
        build_typing_performance_report_v1(
            samples, policy=policy,
            qualification_basis_sha256=basis.basis_sha256)


@pytest.mark.parametrize(("field", "value", "message"), (
    ("action_count", 129, "ceilings"),
    ("peak_screening_samples", 4097, "ceilings"),
    ("serialized_artifact_bytes", 2_097_153, "ceilings"),
    ("peak_process_memory_bytes", 256 * 1024 * 1024 + 1, "ceilings"),
))
def test_resource_ceiling_excess_rejects(field: str, value: int, message: str):
    basis, policy = _policy()
    samples = _samples()
    samples[0] = replace(samples[0], **{field: value})
    with pytest.raises(TypingPerformanceReportV1Error, match=message):
        build_typing_performance_report_v1(
            samples, policy=policy,
            qualification_basis_sha256=basis.basis_sha256)


def test_duplicate_sample_identity_and_false_forced_acceptance_reject():
    basis, policy = _policy()
    samples = _samples()
    with pytest.raises(TypingPerformanceReportV1Error, match="duplicated"):
        build_typing_performance_report_v1(
            samples + [samples[0]], policy=policy,
            qualification_basis_sha256=basis.basis_sha256)
    rejection = next(
        sample for sample in samples if sample.scenario == "FORCED_REJECTION")
    with pytest.raises(TypingPerformanceReportV1Error, match="must reject"):
        replace(rejection, outcome="ADMITTED")
