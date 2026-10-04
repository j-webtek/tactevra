"""Run and retain the T0-T5 host-measured operational latency reference."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


WORKSPACE = Path(__file__).resolve().parents[2]
SOFTWARE = WORKSPACE / "software"
sys.path.insert(0, str(SOFTWARE / "src"))
sys.path.insert(0, str(SOFTWARE / "tests" / "unit"))
sys.path.insert(0, str(SOFTWARE / "tests" / "integration"))

from test_typing_shadow_pipeline_v1 import _inputs  # noqa: E402

from rocell.application.operational_latency_reference_v1 import (  # noqa: E402
    MINIMUM_RUNS_PER_CLASS,
    build_operational_latency_reference_v1,
    capture_operational_benchmark_environment_v1,
    measure_operational_planning_trace_v1,
    parse_operational_latency_reference_v1,
)


DEFAULT_OUTPUT = Path("software/ai/eval/operational_latency_reference_v1.json")


def _output_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError("output must be workspace-relative")
    resolved = (WORKSPACE / candidate).resolve()
    if WORKSPACE not in resolved.parents:
        raise ValueError("output escapes workspace")
    return resolved


def _trace(inputs: dict, *, run_class: str, index: int) -> dict:
    subset = {
        key: inputs[key]
        for key in (
            "payload", "intent_plan", "context", "registry",
            "current_time_epoch_ms", "ingress_monotonic_ns",
            "preplanner_monotonic_ns", "execution_config", "trajectory_policy",
        )
    }
    return measure_operational_planning_trace_v1(
        **subset, trace_id=f"e0-{run_class.lower()}-{index:03d}",
        run_class=run_class,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-per-class", type=int, default=MINIMUM_RUNS_PER_CLASS)
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    args = parser.parse_args(argv)
    if not MINIMUM_RUNS_PER_CLASS <= args.runs_per_class <= 100:
        parser.error("runs-per-class must be between 20 and 100")
    output = _output_path(args.output)
    if output.exists() or output.is_symlink():
        parser.error(f"refusing to overwrite {output}")
    environment = capture_operational_benchmark_environment_v1(
        WORKSPACE,
        captured_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    if environment["repository_dirty"]:
        parser.error("benchmark must run from a clean source commit")
    traces = []
    for index in range(args.runs_per_class):
        traces.append(_trace(_inputs(("R", "O", "B", "O", "T"), "robot"),
                             run_class="COLD", index=index))
    warm_inputs = _inputs(("R", "O", "B", "O", "T"), "robot")
    for index in range(args.runs_per_class):
        traces.append(_trace(warm_inputs, run_class="WARM", index=index))
    report = build_operational_latency_reference_v1(
        traces, report_id="e0-operational-reference-001", environment=environment,
    )
    parse_operational_latency_reference_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(json.dumps(
            report, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8") + b"\n")
    print(json.dumps({
        "output": output.relative_to(WORKSPACE).as_posix(),
        "trace_count": report["trace_count"],
        "report_sha256": report["report_sha256"],
        "terminal_scope": report["terminal_scope"],
        "physical_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
