"""Retain a clean-commit endpoint-reuse qualification campaign."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

WORKSPACE = Path(__file__).resolve().parents[2]
SOFTWARE = WORKSPACE / "software"
sys.path.insert(0, str(SOFTWARE / "src"))
sys.path.insert(0, str(SOFTWARE / "tests" / "unit"))
sys.path.insert(0, str(SOFTWARE / "tests" / "integration"))

import test_typing_shadow_pipeline_v1 as fixture  # noqa: E402
import rocell.application.typing_endpoint_reuse_verifier_v1 as verifier_module  # noqa: E402
from rocell.application.context import SimulationContextError  # noqa: E402
from rocell.application.context_lifecycle_v1 import SimulationContextLifecycleV1  # noqa: E402
from rocell.application.operational_latency_reference_v1 import capture_operational_benchmark_environment_v1  # noqa: E402
from rocell.application.typing_endpoint_reuse_campaign_v1 import (  # noqa: E402
    FAULT_CASES, ROUTE_CASES, build_typing_endpoint_reuse_campaign_v1,
    parse_typing_endpoint_reuse_campaign_v1,
)
from rocell.application.typing_endpoint_reuse_verifier_v1 import TypingEndpointReuseVerifierV1, TypingEndpointReuseVerifierV1Error  # noqa: E402
from rocell.application.typing_planner_preparation_v1 import prepare_typing_planner_v1  # noqa: E402
from rocell.application.typing_shadow_pipeline_v1 import run_typing_shadow_pipeline_v1  # noqa: E402
from rocell.application.typing_trajectory_ik_screen_v1 import TypingTrajectoryIkScreenV1Error  # noqa: E402

DEFAULT_OUTPUT = Path("software/ai/eval/typing_endpoint_reuse_campaign_v1.json")
PATTERNS = (
    ("HOME_TRANSITION", ("H", "I"), "hi"),
    ("WORD_ROBOT", ("R", "O", "B", "O", "T"), "robot"),
    ("REPEAT_NUMBER_PUNCTUATION", ("H", "H", "1", "PERIOD"), "hh1."),
    ("ALPHABETIC_EXTREMES", ("A", "Z"), "az"),
    ("NUMBER_SPACE_ENTER", ("1", "SPACE", "ENTER"), "1 \n"),
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def _resources(service: str, issued: int):
    lifecycle = SimulationContextLifecycleV1.start(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST,
        service_instance_id=service, issued_monotonic_ns=issued,
    )
    context = lifecycle.binding().context
    return lifecycle, context, prepare_typing_planner_v1(context, lifecycle)


def _execute(targets, text, lifecycle, context, prepared, verifier=None):
    kwargs = fixture._inputs(targets, text, context=context)
    extra = {} if verifier is None else {
        "context_lifecycle": lifecycle, "prepared_planner": prepared,
        "endpoint_reuse_verifier": verifier,
    }
    return run_typing_shadow_pipeline_v1(**kwargs, **extra)


def _expect(error, action) -> None:
    try:
        action()
    except error:
        return
    raise RuntimeError(f"expected {error.__name__}")


def _route_cases(issued: int):
    lifecycle, context, prepared = _resources("endpoint-reuse-campaign", issued)
    verifier = TypingEndpointReuseVerifierV1.create(
        context, lifecycle, maximum_entries=256, maximum_samples=4096,
    )
    cases = []
    for name, targets, text in PATTERNS:
        reference = _execute(targets, text, lifecycle, context, prepared)
        observed = _execute(targets, text, lifecycle, context, prepared, verifier)
        reference_sha = reference["typing_shadow_pipeline_sha256"]
        observed_sha = observed["typing_shadow_pipeline_sha256"]
        if reference != observed:
            raise RuntimeError(f"{name} decision receipt changed")
        cases.append({
            "case": name, "target_ids": list(targets), "status": "PASS",
            "reference_receipt_sha256": reference_sha,
            "observed_receipt_sha256": observed_sha,
            "receipt_matches_reference": True,
            "after_verifier_snapshot": verifier.snapshot(),
        })
    if tuple(item["case"] for item in cases) != ROUTE_CASES:
        raise RuntimeError("route case order differs")
    return cases


def _fault_cases(issued: int):
    results = []
    def add(case, outcome="REJECTED", preserved=None):
        results.append({"case": case, "status": "PASS", "outcome": outcome,
                        "canonical_receipt_preserved": preserved})

    lifecycle, context, prepared = _resources("capacity", issued + 1)
    bounded = TypingEndpointReuseVerifierV1.create(context, lifecycle, maximum_entries=1)
    reference = _execute(("H", "I"), "hi", lifecycle, context, prepared)
    observed = _execute(("H", "I"), "hi", lifecycle, context, prepared, bounded)
    if reference != observed or bounded.snapshot()["capacity_skips"] < 1:
        raise RuntimeError("capacity case differs")
    add("CAPACITY_BOUNDED", "BOUNDED", True)

    lifecycle, context, prepared = _resources("sample", issued + 2)
    sample = TypingEndpointReuseVerifierV1.create(context, lifecycle, maximum_samples=1)
    _expect(TypingEndpointReuseVerifierV1Error, lambda: _execute(
        ("H", "I"), "hi", lifecycle, context, prepared, sample))
    add("SAMPLE_BOUND_REJECTED")

    lifecycle, context, prepared = _resources("invalidate", issued + 3)
    invalidated = TypingEndpointReuseVerifierV1.create(context, lifecycle)
    invalidated.invalidate()
    _expect(TypingEndpointReuseVerifierV1Error, lambda: _execute(
        ("H",), "h", lifecycle, context, prepared, invalidated))
    add("INVALIDATED_REJECTED")

    lifecycle, context, prepared = _resources("corrupt", issued + 4)
    corrupt = TypingEndpointReuseVerifierV1.create(context, lifecycle)
    _execute(("H", "H"), "hh", lifecycle, context, prepared, corrupt)
    key = next(iter(corrupt._entries)); entry = corrupt._entries[key]
    corrupt._entries[key] = replace(entry, entry_sha256="f" * 64)
    _expect(TypingEndpointReuseVerifierV1Error, lambda: _execute(
        ("H",), "h", lifecycle, context, prepared, corrupt))
    add("CORRUPTION_REJECTED")

    lifecycle, context, prepared = _resources("conflict", issued + 5)
    conflict = TypingEndpointReuseVerifierV1.create(context, lifecycle)
    _execute(("H", "H"), "hh", lifecycle, context, prepared, conflict)
    key = next(iter(conflict._entries)); entry = conflict._entries[key]
    changed = dict(entry.solution_joint_state); joint = next(iter(changed)); changed[joint] += 0.01
    solution_sha = verifier_module._sha(changed)
    core = {"endpoint_sha256": entry.endpoint_sha256, "solution_joint_state": changed,
            "solution_joint_state_sha256": solution_sha}
    conflict._entries[key] = replace(entry, solution_joint_state=changed,
        solution_joint_state_sha256=solution_sha, entry_sha256=verifier_module._sha(core))
    _expect(TypingEndpointReuseVerifierV1Error, lambda: _execute(
        ("H",), "h", lifecycle, context, prepared, conflict))
    add("CONFLICT_REJECTED")

    lifecycle, context, prepared = _resources("decision", issued + 6)
    decision = TypingEndpointReuseVerifierV1.create(context, lifecycle)
    _execute(("H",), "h", lifecycle, context, prepared, decision)
    decision._decision_context_sha256 = "f" * 64
    _expect(TypingEndpointReuseVerifierV1Error, lambda: _execute(
        ("H",), "h", lifecycle, context, prepared, decision))
    add("DECISION_CONTEXT_REJECTED")

    lifecycle, context, prepared = _resources("reload", issued + 7)
    stale = TypingEndpointReuseVerifierV1.create(context, lifecycle)
    lifecycle.reload_sources(issued_monotonic_ns=issued + 8)
    _expect(SimulationContextError, lambda: _execute(
        ("H",), "h", lifecycle, context, prepared, stale))
    add("RELOAD_STALE_REJECTED")

    lifecycle, context, prepared = _resources("restart", issued + 9)
    stale = TypingEndpointReuseVerifierV1.create(context, lifecycle)
    replacement = lifecycle.restart(service_instance_id="restart-new",
                                    issued_monotonic_ns=issued + 10)
    new_context = replacement.binding().context
    _expect(SimulationContextError, lambda: _execute(
        ("H",), "h", replacement, new_context,
        prepare_typing_planner_v1(new_context, replacement), stale))
    add("RESTART_STALE_REJECTED")

    first, first_context, _ = _resources("first", issued + 11)
    crossed = TypingEndpointReuseVerifierV1.create(first_context, first)
    second, second_context, second_prepared = _resources("second", issued + 12)
    _expect(SimulationContextError, lambda: _execute(
        ("H",), "h", second, second_context, second_prepared, crossed))
    add("CROSSED_CONTEXT_REJECTED")

    lifecycle, context, _ = _resources("unmanaged", issued + 13)
    unmanaged = TypingEndpointReuseVerifierV1.create(context, lifecycle)
    _expect(TypingTrajectoryIkScreenV1Error, lambda: run_typing_shadow_pipeline_v1(
        **fixture._inputs(("H",), "h", context=context),
        endpoint_reuse_verifier=unmanaged))
    add("UNMANAGED_REJECTED")
    if tuple(item["case"] for item in results) != FAULT_CASES:
        raise RuntimeError("fault case order differs")
    return results


def main(argv=None) -> int:
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
        benchmark_entrypoint="software/scripts/run_typing_endpoint_reuse_campaign_v1.py")
    if environment["repository_dirty"]: parser.error("campaign must run from a clean source commit")
    issued = time.perf_counter_ns()
    report = build_typing_endpoint_reuse_campaign_v1(
        _route_cases(issued), _fault_cases(issued),
        campaign_id="e2-endpoint-reuse-001", environment=environment)
    parse_typing_endpoint_reuse_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream: stream.write(_canonical(report) + b"\n")
    final = report["final_verifier_snapshot"]
    print(json.dumps({"output": output.relative_to(WORKSPACE).as_posix(),
        "campaign_sha256": report["campaign_sha256"], "route_cases": 5,
        "fault_cases": 10, "observed_samples": final["observed_sample_count"],
        "unique_endpoints": final["entry_count"], "repeat_matches": final["canonical_matches"],
        "physical_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
