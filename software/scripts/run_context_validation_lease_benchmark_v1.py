"""Retain a clean-commit benchmark of full and leased context validation."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys
import time


WORKSPACE = Path(__file__).resolve().parents[2]
SOFTWARE = WORKSPACE / "software"
sys.path.insert(0, str(SOFTWARE / "src"))
sys.path.insert(0, str(SOFTWARE / "tests" / "unit"))

import test_model_motion_ingress_v2 as fixture  # noqa: E402

from rocell.application.context import (  # noqa: E402
    SimulationContextError,
    issue_simulation_context_validation_lease_v1,
    validate_simulation_context_lease_v1,
)
from rocell.application.context_validation_lease_benchmark_v1 import (  # noqa: E402
    INVALIDATION_CASES,
    MINIMUM_SAMPLES_PER_PATH,
    build_context_validation_lease_benchmark_v1,
    parse_context_validation_lease_benchmark_v1,
)
from rocell.application.model_motion_registry_v2 import (  # noqa: E402
    ingest_with_trusted_registry_v2,
)
from rocell.application.operational_latency_reference_v1 import (  # noqa: E402
    capture_operational_benchmark_environment_v1,
)


DEFAULT_OUTPUT = Path("software/ai/eval/context_validation_lease_benchmark_v1.json")
SERVICE = "planner-service-e1-benchmark"
GENERATION = 1


def _output_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError("output must be workspace-relative")
    resolved = (WORKSPACE / candidate).resolve()
    if WORKSPACE not in resolved.parents:
        raise ValueError("output escapes workspace")
    return resolved


def _invalidation_results(context, lease) -> list[dict[str, str]]:
    cases = (
        ("CONTEXT_EPOCH_CHANGED", context, "f" * 64, SERVICE, GENERATION, lease),
        ("SERVICE_INSTANCE_RESTARTED", context, lease.context_epoch_sha256,
         "planner-service-restarted", GENERATION, lease),
        ("SERVICE_GENERATION_CHANGED", context, lease.context_epoch_sha256,
         SERVICE, GENERATION + 1, lease),
        ("CONTEXT_OBJECT_REPLACED", replace(context), lease.context_epoch_sha256,
         SERVICE, GENERATION, lease),
        ("LEASE_CONTENT_MUTATED", context, lease.context_epoch_sha256,
         SERVICE, GENERATION + 1, replace(lease, generation=GENERATION + 1)),
    )
    results = []
    for case, selected_context, epoch, service, generation, selected_lease in cases:
        try:
            validate_simulation_context_lease_v1(
                selected_context, selected_lease,
                active_context_epoch_sha256=epoch,
                active_service_instance_id=service,
                active_generation=generation,
            )
        except SimulationContextError:
            results.append({"case": case, "status": "BLOCKED"})
        else:
            raise RuntimeError(f"invalidation case unexpectedly passed: {case}")
    assert tuple(item["case"] for item in results) == INVALIDATION_CASES
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-per-path", type=int, default=MINIMUM_SAMPLES_PER_PATH)
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    args = parser.parse_args(argv)
    if not MINIMUM_SAMPLES_PER_PATH <= args.samples_per_path <= 1000:
        parser.error("samples-per-path must be between 20 and 1000")
    output = _output_path(args.output)
    if output.exists() or output.is_symlink():
        parser.error(f"refusing to overwrite {output}")
    environment = capture_operational_benchmark_environment_v1(
        WORKSPACE,
        captured_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        benchmark_entrypoint=(
            "software/scripts/run_context_validation_lease_benchmark_v1.py"
        ),
    )
    if environment["repository_dirty"]:
        parser.error("benchmark must run from a clean source commit")

    context = fixture.load_simulation_context(fixture.WORKSPACE, fixture.MANIFEST)
    plan = fixture._plan()
    batch = fixture._batch(context, plan=plan)
    registry = fixture._registry(context)
    common = {
        "registry": registry,
        "current_time_epoch_ms": fixture.T0 + 3_000,
        "current_monotonic_ns": 9_000_000_000,
    }
    lease = issue_simulation_context_validation_lease_v1(
        context, service_instance_id=SERVICE, generation=GENERATION,
        issued_monotonic_ns=time.perf_counter_ns(),
    )
    samples = []
    expected_ingress = None
    for path in ("FULL_SOURCE_REVALIDATION", "EPOCH_BOUND_LEASE"):
        for _ in range(args.samples_per_path):
            warm = {} if path == "FULL_SOURCE_REVALIDATION" else {
                "context_validation_lease": lease,
                "active_context_epoch_sha256": lease.context_epoch_sha256,
                "active_service_instance_id": SERVICE,
                "active_context_generation": GENERATION,
            }
            started = time.perf_counter_ns()
            ingress = ingest_with_trusted_registry_v2(
                batch, plan, context, **common, **warm,
            )
            duration = time.perf_counter_ns() - started
            if expected_ingress is None:
                expected_ingress = ingress
            elif ingress != expected_ingress:
                raise RuntimeError("full and leased ingress outputs differ")
            samples.append({
                "sequence": len(samples), "path": path,
                "duration_ns": duration,
                "ingress_sha256": ingress["ingress_sha256"],
            })
    report = build_context_validation_lease_benchmark_v1(
        samples, report_id="e1-context-lease-benchmark-001",
        environment=environment,
        context_epoch_sha256=lease.context_epoch_sha256,
        lease_sha256=lease.lease_sha256,
        invalidation_results=_invalidation_results(context, lease),
    )
    parse_context_validation_lease_benchmark_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(json.dumps(
            report, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8") + b"\n")
    print(json.dumps({
        "output": output.relative_to(WORKSPACE).as_posix(),
        "report_sha256": report["report_sha256"],
        "summaries": report["summaries"],
        "semantic_equivalence": report["semantic_equivalence"],
        "physical_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
