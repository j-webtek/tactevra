"""Retain a clean-commit exact IK cache timing and invalidation campaign."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time


WORKSPACE = Path(__file__).resolve().parents[2]
SOFTWARE = WORKSPACE / "software"
sys.path.insert(0, str(SOFTWARE / "src"))
sys.path.insert(0, str(SOFTWARE / "tests" / "unit"))
sys.path.insert(0, str(SOFTWARE / "tests" / "integration"))

import test_model_motion_ingress_v2 as ingress_fixture  # noqa: E402
import test_typing_shadow_pipeline_v1 as shadow_fixture  # noqa: E402

from rocell.application.context import SimulationContextError  # noqa: E402
from rocell.application.context_lifecycle_v1 import (  # noqa: E402
    SimulationContextLifecycleV1,
)
from rocell.application.operational_latency_reference_v1 import (  # noqa: E402
    capture_operational_benchmark_environment_v1,
)
from rocell.application.typing_exact_ik_cache_benchmark_v1 import (  # noqa: E402
    INVALIDATION_CASES,
    MINIMUM_SAMPLES_PER_PATH,
    PATHS,
    build_typing_exact_ik_cache_benchmark_v1,
    parse_typing_exact_ik_cache_benchmark_v1,
)
from rocell.application.typing_exact_ik_result_cache_v1 import (  # noqa: E402
    ExactTypingIkResultCacheV1,
    TypingExactIkResultCacheV1Error,
)
from rocell.application.typing_planner_preparation_v1 import (  # noqa: E402
    prepare_typing_planner_v1,
)
from rocell.application.typing_shadow_pipeline_v1 import (  # noqa: E402
    TypingShadowPipelineV1Error,
    run_typing_shadow_pipeline_v1,
)
from rocell.application.typing_trajectory_ik_screen_v1 import (  # noqa: E402
    TypingTrajectoryIkScreenV1Error,
)


DEFAULT_OUTPUT = Path(
    "software/ai/eval/typing_exact_ik_cache_benchmark_v1.json"
)
SERVICE = "typing-exact-ik-cache-benchmark"
COUNTERS = ("lookups", "hits", "misses", "stores", "capacity_skips")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _output_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError("output must be workspace-relative")
    resolved = (WORKSPACE / candidate).resolve()
    if WORKSPACE not in resolved.parents:
        raise ValueError("output escapes workspace")
    return resolved


def _start(service: str, issued: int) -> SimulationContextLifecycleV1:
    return SimulationContextLifecycleV1.start(
        ingress_fixture.WORKSPACE,
        ingress_fixture.MANIFEST,
        service_instance_id=service,
        issued_monotonic_ns=issued,
    )


def _blocked(case: str, action) -> dict[str, str]:
    try:
        action()
    except (
        SimulationContextError,
        TypingExactIkResultCacheV1Error,
        TypingShadowPipelineV1Error,
        TypingTrajectoryIkScreenV1Error,
    ):
        return {"case": case, "status": "BLOCKED"}
    raise RuntimeError(f"invalidation case unexpectedly passed: {case}")


def _managed(service: str, issued: int):
    lifecycle = _start(service, issued)
    context = lifecycle.binding().context
    return (
        lifecycle,
        context,
        shadow_fixture._inputs(("R", "O", "B", "O", "T"), "robot", context=context),
        prepare_typing_planner_v1(context, lifecycle),
    )


def _run_managed(inputs, lifecycle, prepared, cache=None):
    arguments = {
        "context_lifecycle": lifecycle,
        "prepared_planner": prepared,
    }
    if cache is not None:
        arguments["exact_ik_result_cache"] = cache
    return run_typing_shadow_pipeline_v1(**inputs, **arguments)


def _invalidation_results() -> list[dict[str, str]]:
    explicit_lifecycle, explicit_context, explicit_inputs, explicit_prepared = (
        _managed(f"{SERVICE}-explicit", 101)
    )
    explicit_cache = ExactTypingIkResultCacheV1.create(
        explicit_context, explicit_lifecycle
    )
    explicit_cache.invalidate()

    reload_lifecycle, reload_context, reload_inputs, reload_prepared = _managed(
        f"{SERVICE}-reload", 201
    )
    reload_cache = ExactTypingIkResultCacheV1.create(
        reload_context, reload_lifecycle
    )
    reload_lifecycle.reload_sources(issued_monotonic_ns=202)

    restart_lifecycle, restart_context, restart_inputs, restart_prepared = _managed(
        f"{SERVICE}-restart", 301
    )
    restart_cache = ExactTypingIkResultCacheV1.create(
        restart_context, restart_lifecycle
    )
    restart_lifecycle.restart(
        service_instance_id=f"{SERVICE}-restart-new",
        issued_monotonic_ns=302,
    )

    crossed_a, crossed_context, _, _ = _managed(f"{SERVICE}-crossed-a", 401)
    crossed_cache = ExactTypingIkResultCacheV1.create(crossed_context, crossed_a)
    crossed_b, _, crossed_inputs, crossed_prepared = _managed(
        f"{SERVICE}-crossed-b", 402
    )

    corrupt_lifecycle, corrupt_context, corrupt_inputs, corrupt_prepared = _managed(
        f"{SERVICE}-corrupt", 501
    )
    corrupt_cache = ExactTypingIkResultCacheV1.create(
        corrupt_context, corrupt_lifecycle
    )
    _run_managed(
        corrupt_inputs, corrupt_lifecycle, corrupt_prepared, corrupt_cache
    )
    key = next(iter(corrupt_cache._entries))
    corrupt_cache._entries[key] = replace(
        corrupt_cache._entries[key], result_sha256="f" * 64
    )

    unmanaged_lifecycle, unmanaged_context, unmanaged_inputs, _ = _managed(
        f"{SERVICE}-unmanaged", 601
    )
    unmanaged_cache = ExactTypingIkResultCacheV1.create(
        unmanaged_context, unmanaged_lifecycle
    )

    results = [
        _blocked(
            "EXPLICIT_INVALIDATION",
            lambda: _run_managed(
                explicit_inputs, explicit_lifecycle, explicit_prepared,
                explicit_cache,
            ),
        ),
        _blocked(
            "CONTEXT_RELOAD",
            lambda: _run_managed(
                reload_inputs, reload_lifecycle, reload_prepared, reload_cache
            ),
        ),
        _blocked(
            "SERVICE_RESTART",
            lambda: _run_managed(
                restart_inputs, restart_lifecycle, restart_prepared,
                restart_cache,
            ),
        ),
        _blocked(
            "CROSSED_CONTEXT",
            lambda: _run_managed(
                crossed_inputs, crossed_b, crossed_prepared, crossed_cache
            ),
        ),
        _blocked(
            "INTEGRITY_CORRUPTION",
            lambda: _run_managed(
                corrupt_inputs, corrupt_lifecycle, corrupt_prepared,
                corrupt_cache,
            ),
        ),
        _blocked(
            "UNMANAGED_CACHE",
            lambda: run_typing_shadow_pipeline_v1(
                **unmanaged_inputs, exact_ik_result_cache=unmanaged_cache
            ),
        ),
    ]
    assert tuple(item["case"] for item in results) == INVALIDATION_CASES
    return results


def _counter_delta(before: dict, after: dict) -> dict[str, int]:
    return {field: after[field] - before[field] for field in COUNTERS}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--samples-per-path", type=int, default=MINIMUM_SAMPLES_PER_PATH
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    args = parser.parse_args(argv)
    if not MINIMUM_SAMPLES_PER_PATH <= args.samples_per_path <= 1000:
        parser.error("samples-per-path must be between 10 and 1000")
    output = _output_path(args.output)
    if output.exists() or output.is_symlink():
        parser.error(f"refusing to overwrite {output}")
    environment = capture_operational_benchmark_environment_v1(
        WORKSPACE,
        captured_at_utc=datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        benchmark_entrypoint=(
            "software/scripts/run_typing_exact_ik_cache_benchmark_v1.py"
        ),
    )
    if environment["repository_dirty"]:
        parser.error("benchmark must run from a clean source commit")

    lifecycle, context, inputs, prepared = _managed(
        SERVICE, time.perf_counter_ns()
    )
    warm_cache = ExactTypingIkResultCacheV1.create(
        context, lifecycle, maximum_entries=256
    )
    expected_receipt = _run_managed(inputs, lifecycle, prepared, warm_cache)
    warm_snapshot = warm_cache.snapshot()
    if warm_snapshot["misses"] <= 0 or warm_snapshot["capacity_skips"] != 0:
        raise RuntimeError("warm-cache preparation is incomplete")

    samples = []
    for iteration in range(args.samples_per_path):
        ordered_paths = PATHS[iteration % len(PATHS):] + PATHS[:iteration % len(PATHS)]
        for path in ordered_paths:
            cache = None
            if path == "CACHE_COLD":
                cache = ExactTypingIkResultCacheV1.create(
                    context, lifecycle, maximum_entries=256
                )
            elif path == "CACHE_WARM":
                cache = warm_cache
            elif path == "CACHE_CAPACITY_ONE":
                cache = ExactTypingIkResultCacheV1.create(
                    context, lifecycle, maximum_entries=1
                )
            before = cache.snapshot() if cache is not None else None
            started = time.perf_counter_ns()
            receipt = _run_managed(inputs, lifecycle, prepared, cache)
            duration = time.perf_counter_ns() - started
            if receipt != expected_receipt:
                raise RuntimeError("cache benchmark changed canonical output")
            counters = {field: 0 for field in COUNTERS}
            if cache is not None and before is not None:
                counters = _counter_delta(before, cache.snapshot())
            samples.append({
                "sequence": len(samples),
                "path": path,
                "duration_ns": duration,
                "receipt_sha256": receipt["typing_shadow_pipeline_sha256"],
                "stage_hashes_sha256": hashlib.sha256(
                    _canonical(receipt["stage_hashes"])
                ).hexdigest(),
                **counters,
            })

    report = build_typing_exact_ik_cache_benchmark_v1(
        samples,
        report_id="e2-exact-ik-cache-benchmark-001",
        environment=environment,
        invalidation_results=_invalidation_results(),
    )
    parse_typing_exact_ik_cache_benchmark_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(_canonical(report) + b"\n")
    print(json.dumps({
        "output": output.relative_to(WORKSPACE).as_posix(),
        "report_sha256": report["report_sha256"],
        "summaries": report["summaries"],
        "cache_totals": report["cache_totals"],
        "invalidation_results": report["invalidation_results"],
        "physical_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
