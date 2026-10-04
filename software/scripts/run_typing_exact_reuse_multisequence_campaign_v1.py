"""Retain a clean-commit five-sequence exact-input substitution campaign."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

WORKSPACE = Path(__file__).resolve().parents[2]
SOFTWARE = WORKSPACE / "software"
sys.path.insert(0, str(SOFTWARE / "src"))
sys.path.insert(0, str(SOFTWARE / "tests" / "integration"))

import test_typing_shadow_pipeline_v1 as fixture  # noqa: E402
from rocell.application.context_lifecycle_v1 import SimulationContextLifecycleV1  # noqa: E402
from rocell.application.operational_latency_reference_v1 import capture_operational_benchmark_environment_v1  # noqa: E402
from rocell.application.typing_exact_ik_result_cache_v1 import ExactTypingIkResultCacheV1  # noqa: E402
from rocell.application.typing_exact_reuse_multisequence_campaign_v1 import (  # noqa: E402
    CASES, build_typing_exact_reuse_multisequence_campaign_v1,
    parse_typing_exact_reuse_multisequence_campaign_v1,
)
from rocell.application.typing_planner_preparation_v1 import prepare_typing_planner_v1  # noqa: E402
from rocell.application.typing_shadow_pipeline_v1 import run_typing_shadow_pipeline_v1  # noqa: E402

DEFAULT_OUTPUT = Path("software/ai/eval/typing_exact_reuse_multisequence_campaign_v1.json")
COUNTERS = ("lookups", "hits", "misses", "stores", "capacity_skips")
PATTERNS = (
    ("HOME_TRANSITION", ("H", "I"), "hi"),
    ("WORD_ROBOT", ("R", "O", "B", "O", "T"), "robot"),
    ("REPEAT_NUMBER_PUNCTUATION", ("H", "H", "1", "PERIOD"), "hh1."),
    ("ALPHABETIC_EXTREMES", ("A", "Z"), "az"),
    ("NUMBER_SPACE_ENTER", ("1", "SPACE", "ENTER"), "1 \n"),
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _delta(before, after):
    return {field: after[field] - before[field] for field in COUNTERS}


def _run(inputs, lifecycle, prepared, cache=None):
    extra = {"context_lifecycle": lifecycle, "prepared_planner": prepared}
    if cache is not None: extra["exact_ik_result_cache"] = cache
    started = time.perf_counter_ns()
    receipt = run_typing_shadow_pipeline_v1(**inputs, **extra)
    return receipt, time.perf_counter_ns() - started


def _cases(issued):
    lifecycle = SimulationContextLifecycleV1.start(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST,
        service_instance_id="exact-reuse-multisequence", issued_monotonic_ns=issued)
    context = lifecycle.binding().context
    prepared = prepare_typing_planner_v1(context, lifecycle)
    cases = []
    for name, targets, text in PATTERNS:
        inputs = fixture._inputs(targets, text, context=context)
        reference, reference_duration = _run(inputs, lifecycle, prepared)
        cache = ExactTypingIkResultCacheV1.create(context, lifecycle, maximum_entries=256)
        before = cache.snapshot()
        cold, cold_duration = _run(inputs, lifecycle, prepared, cache)
        cold_counters = _delta(before, cache.snapshot())
        before = cache.snapshot()
        warm, warm_duration = _run(inputs, lifecycle, prepared, cache)
        warm_counters = _delta(before, cache.snapshot())
        if not reference == cold == warm:
            raise RuntimeError(f"{name} exact-input substitution changed output")
        receipt_sha = reference["typing_shadow_pipeline_sha256"]
        stage_sha = hashlib.sha256(_canonical(reference["stage_hashes"])).hexdigest()
        cases.append({"case": name, "target_ids": list(targets), "status": "PASS",
            "sample_count": cold_counters["lookups"],
            "reference_duration_ns": reference_duration, "cold_duration_ns": cold_duration,
            "warm_duration_ns": warm_duration,
            "reference_receipt_sha256": receipt_sha, "cold_receipt_sha256": receipt_sha,
            "warm_receipt_sha256": receipt_sha, "reference_stage_sha256": stage_sha,
            "cold_stage_sha256": stage_sha, "warm_stage_sha256": stage_sha,
            "cold_counters": cold_counters, "warm_counters": warm_counters})
    assert tuple(item["case"] for item in cases) == CASES
    return cases


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    args = parser.parse_args(argv)
    candidate = Path(args.output)
    if candidate.is_absolute(): parser.error("output must be workspace-relative")
    output = (WORKSPACE / candidate).resolve()
    if WORKSPACE not in output.parents: parser.error("output escapes workspace")
    if output.exists() or output.is_symlink(): parser.error(f"refusing to overwrite {output}")
    environment = capture_operational_benchmark_environment_v1(
        WORKSPACE, captured_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        benchmark_entrypoint="software/scripts/run_typing_exact_reuse_multisequence_campaign_v1.py")
    if environment["repository_dirty"]: parser.error("campaign must run from a clean source commit")
    report = build_typing_exact_reuse_multisequence_campaign_v1(
        _cases(time.perf_counter_ns()), campaign_id="e2-exact-reuse-multisequence-001",
        environment=environment)
    parse_typing_exact_reuse_multisequence_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream: stream.write(_canonical(report) + b"\n")
    print(json.dumps({"output": output.relative_to(WORKSPACE).as_posix(),
        "campaign_sha256": report["campaign_sha256"], "cases": report["case_count"],
        "samples": report["total_samples"], "cold_hits": report["total_cold_hits"],
        "warm_hits": report["total_warm_hits"], "physical_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
