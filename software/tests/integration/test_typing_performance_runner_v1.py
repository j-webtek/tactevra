from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/tests/unit"))

from test_typing_shadow_pipeline_v1 import _inputs  # noqa: E402

from rocell.application.typing_performance_runner_v1 import (  # noqa: E402
    profile_forced_decode_rejection_v1,
    profile_typing_shadow_pipeline_v1,
)
from rocell.application.typing_shadow_pipeline_v1 import (  # noqa: E402
    run_typing_shadow_pipeline_v1,
)


def test_profiled_runner_matches_existing_receipt_and_has_no_authority():
    inputs = _inputs(("R", "O", "B", "O", "T"), "robot")
    expected = run_typing_shadow_pipeline_v1(**inputs)
    profiled = profile_typing_shadow_pipeline_v1(
        **inputs,
        scenario="COLD_CACHE",
        iteration=0,
        cache_state="COLD",
        cache_result="MISS",
        estimated_cache_time_saved_ns=0,
    )
    assert profiled.receipt == expected
    sample = profiled.sample
    assert sample.action_count == 5
    assert sample.total_cpu_ns >= sum(sample.stage_cpu_ns.values())
    assert all(value >= 0 for value in sample.stage_cpu_ns.values())
    assert sum(sample.stage_cpu_ns.values()) > 0
    assert sample.stage_cpu_ns["preview_validation"] == 0
    assert sample.stage_cpu_ns["encoding"] == 0
    assert sample.peak_screening_samples > 0
    assert sample.serialized_artifact_bytes > 0
    assert sample.peak_process_memory_bytes > 0
    assert sample.predicted_route_duration_ns > 0
    assert profiled.receipt["controller_commands"] == []
    assert profiled.receipt["hardware_commands_generated"] == 0
    assert profiled.receipt["hardware_access"] is False
    assert profiled.receipt["physical_authority"] is False


def test_warm_profile_records_only_declared_cache_estimate():
    inputs = _inputs(("H", "H", "1", "PERIOD"), "hh1.")
    profiled = profile_typing_shadow_pipeline_v1(
        **inputs,
        scenario="WARM_CACHE",
        iteration=1,
        cache_state="WARM",
        cache_result="HIT_REVALIDATED",
        estimated_cache_time_saved_ns=1234,
    )
    assert profiled.sample.cache_result == "HIT_REVALIDATED"
    assert profiled.sample.estimated_cache_time_saved_ns == 1234
    assert profiled.receipt["status"] == (
        "BLOCKED_AT_HONEST_COLLISION_EVIDENCE_BOUNDARY")


def test_forced_decode_rejection_is_measured_without_later_stages():
    sample = profile_forced_decode_rejection_v1(b"{}", iteration=4)
    assert sample.scenario == "FORCED_REJECTION"
    assert sample.outcome == "REJECTED"
    assert sample.stage_cpu_ns["decode"] >= 0
    assert all(
        value == 0
        for stage, value in sample.stage_cpu_ns.items()
        if stage != "decode"
    )
    assert sample.predicted_route_duration_ns == 0
