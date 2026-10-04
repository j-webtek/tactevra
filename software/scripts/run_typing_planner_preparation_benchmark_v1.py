"""Retain a clean-commit full-source versus prepared typing benchmark."""

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
from rocell.application.typing_planner_preparation_benchmark_v1 import (  # noqa: E402
    INVALIDATION_CASES,
    MINIMUM_SAMPLES_PER_PATH,
    build_typing_planner_preparation_benchmark_v1,
    parse_typing_planner_preparation_benchmark_v1,
)
from rocell.application.typing_planner_preparation_v1 import (  # noqa: E402
    prepare_typing_planner_v1,
)
from rocell.application.typing_shadow_pipeline_v1 import (  # noqa: E402
    TypingShadowPipelineV1Error,
    run_typing_shadow_pipeline_v1,
)


DEFAULT_OUTPUT = Path(
    "software/ai/eval/typing_planner_preparation_benchmark_v1.json"
)
SERVICE = "typing-planner-preparation-benchmark"


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
    except (SimulationContextError, TypingShadowPipelineV1Error):
        return {"case": case, "status": "BLOCKED"}
    raise RuntimeError(f"invalidation case unexpectedly passed: {case}")


def _invalidation_results() -> list[dict[str, str]]:
    reload_lifecycle = _start(f"{SERVICE}-reload", 101)
    reload_context = reload_lifecycle.binding().context
    reload_inputs = shadow_fixture._inputs(context=reload_context)
    reload_prepared = prepare_typing_planner_v1(
        reload_context, reload_lifecycle
    )
    reload_lifecycle.reload_sources(issued_monotonic_ns=102)

    restart_lifecycle = _start(f"{SERVICE}-restart-old", 201)
    restart_context = restart_lifecycle.binding().context
    restart_inputs = shadow_fixture._inputs(context=restart_context)
    restart_prepared = prepare_typing_planner_v1(
        restart_context, restart_lifecycle
    )
    restart_lifecycle.restart(
        service_instance_id=f"{SERVICE}-restart-new",
        issued_monotonic_ns=202,
    )

    mutate_lifecycle = _start(f"{SERVICE}-mutate", 301)
    mutate_context = mutate_lifecycle.binding().context
    mutate_inputs = shadow_fixture._inputs(context=mutate_context)
    mutate_prepared = prepare_typing_planner_v1(mutate_context, mutate_lifecycle)
    forged = replace(
        mutate_prepared,
        preparation_sha256="f" * 64,
    )

    unmanaged_lifecycle = _start(f"{SERVICE}-unmanaged", 401)
    unmanaged_context = unmanaged_lifecycle.binding().context
    unmanaged_inputs = shadow_fixture._inputs(context=unmanaged_context)
    unmanaged_prepared = prepare_typing_planner_v1(
        unmanaged_context, unmanaged_lifecycle
    )

    results = [
        _blocked(
            "CONTEXT_RELOAD",
            lambda: run_typing_shadow_pipeline_v1(
                **reload_inputs,
                context_lifecycle=reload_lifecycle,
                prepared_planner=reload_prepared,
            ),
        ),
        _blocked(
            "SERVICE_RESTART",
            lambda: run_typing_shadow_pipeline_v1(
                **restart_inputs,
                context_lifecycle=restart_lifecycle,
                prepared_planner=restart_prepared,
            ),
        ),
        _blocked(
            "PREPARATION_MUTATED",
            lambda: run_typing_shadow_pipeline_v1(
                **mutate_inputs,
                context_lifecycle=mutate_lifecycle,
                prepared_planner=forged,
            ),
        ),
        _blocked(
            "UNMANAGED_PREPARATION",
            lambda: run_typing_shadow_pipeline_v1(
                **unmanaged_inputs,
                prepared_planner=unmanaged_prepared,
            ),
        ),
    ]
    assert tuple(item["case"] for item in results) == INVALIDATION_CASES
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--samples-per-path", type=int, default=MINIMUM_SAMPLES_PER_PATH
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    args = parser.parse_args(argv)
    if not MINIMUM_SAMPLES_PER_PATH <= args.samples_per_path <= 1000:
        parser.error("samples-per-path must be between 20 and 1000")
    output = _output_path(args.output)
    if output.exists() or output.is_symlink():
        parser.error(f"refusing to overwrite {output}")
    environment = capture_operational_benchmark_environment_v1(
        WORKSPACE,
        captured_at_utc=datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        benchmark_entrypoint=(
            "software/scripts/run_typing_planner_preparation_benchmark_v1.py"
        ),
    )
    if environment["repository_dirty"]:
        parser.error("benchmark must run from a clean source commit")

    lifecycle = _start(SERVICE, time.perf_counter_ns())
    binding = lifecycle.binding()
    inputs = shadow_fixture._inputs(context=binding.context)
    preparation_started = time.perf_counter_ns()
    prepared = prepare_typing_planner_v1(binding.context, lifecycle)
    preparation_duration = time.perf_counter_ns() - preparation_started

    samples = []
    expected_receipt = None
    for path in ("FULL_SOURCE_PIPELINE", "EPOCH_PREPARED_PIPELINE"):
        for _ in range(args.samples_per_path):
            optimized = {} if path == "FULL_SOURCE_PIPELINE" else {
                "context_lifecycle": lifecycle,
                "prepared_planner": prepared,
            }
            started = time.perf_counter_ns()
            receipt = run_typing_shadow_pipeline_v1(**inputs, **optimized)
            duration = time.perf_counter_ns() - started
            if expected_receipt is None:
                expected_receipt = receipt
            elif receipt != expected_receipt:
                raise RuntimeError("full and prepared pipeline outputs differ")
            samples.append({
                "sequence": len(samples),
                "path": path,
                "duration_ns": duration,
                "receipt_sha256": receipt["typing_shadow_pipeline_sha256"],
                "stage_hashes_sha256": hashlib.sha256(
                    _canonical(receipt["stage_hashes"])
                ).hexdigest(),
            })

    report = build_typing_planner_preparation_benchmark_v1(
        samples,
        report_id="e1-typing-preparation-benchmark-001",
        environment=environment,
        context_epoch_sha256=binding.context_epoch_sha256,
        lease_sha256=binding.lease.lease_sha256,
        preparation_sha256=prepared.preparation_sha256,
        model_sha256=prepared.loaded_model.sha256,
        preparation_duration_ns=preparation_duration,
        invalidation_results=_invalidation_results(),
    )
    parse_typing_planner_preparation_benchmark_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(_canonical(report) + b"\n")
    print(json.dumps({
        "output": output.relative_to(WORKSPACE).as_posix(),
        "report_sha256": report["report_sha256"],
        "preparation_duration_ns": report["preparation_duration_ns"],
        "summaries": report["summaries"],
        "semantic_equivalence": report["semantic_equivalence"],
        "physical_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
