"""Retain service-level mixed-request exact-reuse and lifecycle evidence."""

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
sys.path.insert(0, str(SOFTWARE / "tests" / "integration"))

import test_typing_shadow_pipeline_v1 as fixture  # noqa: E402
from rocell.application.operational_latency_reference_v1 import capture_operational_benchmark_environment_v1  # noqa: E402
from rocell.application.typing_exact_ik_cache_owner_v1 import TypingExactIkCacheOwnerV1  # noqa: E402
from rocell.application.typing_shadow_service_reuse_campaign_v1 import (  # noqa: E402
    CASES, COUNTERS, build_typing_shadow_service_reuse_campaign_v1,
    parse_typing_shadow_service_reuse_campaign_v1,
)
from rocell.application.typing_shadow_service_v1 import TypingShadowServiceV1  # noqa: E402
from rocell.models.model_motion_batch_v2 import decode_model_motion_batch_v2_json  # noqa: E402

DEFAULT_OUTPUT = Path("software/ai/eval/typing_shadow_service_reuse_campaign_v1.json")
PATTERNS = (("home", ("H", "I"), "hi"), ("robot", ("R", "O", "B", "O", "T"), "robot"),
    ("repeat", ("H", "H", "1", "PERIOD"), "hh1."), ("extremes", ("A", "Z"), "az"),
    ("number", ("1", "SPACE", "ENTER"), "1 \n"))


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def _owner(name, issued):
    return TypingExactIkCacheOwnerV1.start(fixture.ingress_fixture.WORKSPACE,
        fixture.ingress_fixture.MANIFEST, service_instance_id=f"reuse-service-{name}",
        issued_monotonic_ns=issued, maximum_entries=256)


def _with_id(inputs, request_id):
    changed = dict(inputs)
    batch = replace(decode_model_motion_batch_v2_json(changed["payload"]), request_id=request_id)
    changed["payload"] = _canonical(batch.to_dict())
    return changed


def _cache(owner): return owner.snapshot()["cache"]
def _delta(before, after): return {field: after[field] - before[field] for field in COUNTERS}


def _execute(service):
    started = time.perf_counter_ns(); receipt = service.execute_next()
    return receipt, time.perf_counter_ns() - started


def _case(name, request_ids, receipts, durations, before_owner, owner):
    after = owner.snapshot()
    return {"case": name, "status": "PASS", "request_ids": request_ids,
        "receipt_statuses": [receipt["status"] for receipt in receipts],
        "duration_ns": durations, "owner_runs_delta": after["runs"] - before_owner["runs"],
        "cache_delta": _delta(before_owner["cache"], after["cache"])}


def _campaign_cases(issued):
    owner = _owner("mixed", issued); service = TypingShadowServiceV1(owner, maximum_queued=8)
    request_ids = []
    for label, targets, text in PATTERNS:
        request_id = f"mixed-{label}"; request_ids.append(request_id)
        inputs = _with_id(fixture._inputs(targets, text, context=service.context), request_id)
        service.submit(request_id, inputs)
    before = owner.snapshot(); receipts = []; durations = []
    for _ in request_ids:
        receipt, duration = _execute(service); receipts.append(receipt); durations.append(duration)
    if [r["request_id"] for r in receipts] != request_ids:
        raise RuntimeError("mixed request FIFO order changed")
    cases = [_case("MIXED_FIFO_CACHE_REUSE", request_ids, receipts, durations, before, owner)]

    owner = _owner("cancel", issued + 1); service = TypingShadowServiceV1(owner)
    request_id = "cancel-reuse"; inputs = _with_id(fixture._inputs(context=service.context), request_id)
    service.submit(request_id, inputs); before = owner.snapshot(); started = time.perf_counter_ns()
    receipt = service.cancel(request_id); duration = time.perf_counter_ns() - started
    cases.append(_case("CANCEL_NO_CACHE_EFFECT", [request_id], [receipt], [duration], before, owner))

    for offset, transition in ((2, "RELOAD"), (4, "RESTART")):
        owner = _owner(transition.lower(), issued + offset); service = TypingShadowServiceV1(owner)
        stale_id = f"{transition.lower()}-stale"
        stale_inputs = _with_id(fixture._inputs(("H", "I"), "hi", context=service.context), stale_id)
        service.submit(stale_id, stale_inputs)
        if transition == "RELOAD": service.reload_sources(issued_monotonic_ns=issued + offset + 1)
        else: service.restart(service_instance_id="reuse-service-restarted",
                              issued_monotonic_ns=issued + offset + 1)
        before = owner.snapshot(); stale, stale_duration = _execute(service)
        current_id = f"{transition.lower()}-current"
        current_inputs = _with_id(fixture._inputs(("H", "I"), "hi", context=service.context), current_id)
        service.submit(current_id, current_inputs); current, current_duration = _execute(service)
        cases.append(_case(f"{transition}_STALE_THEN_COLD", [stale_id, current_id],
                           [stale, current], [stale_duration, current_duration], before, owner))
    assert tuple(item["case"] for item in cases) == CASES
    return cases


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix()); args = parser.parse_args(argv)
    candidate = Path(args.output)
    if candidate.is_absolute(): parser.error("output must be workspace-relative")
    output = (WORKSPACE / candidate).resolve()
    if WORKSPACE not in output.parents: parser.error("output escapes workspace")
    if output.exists() or output.is_symlink(): parser.error(f"refusing to overwrite {output}")
    environment = capture_operational_benchmark_environment_v1(WORKSPACE,
        captured_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        benchmark_entrypoint="software/scripts/run_typing_shadow_service_reuse_campaign_v1.py")
    if environment["repository_dirty"]: parser.error("campaign must run from a clean source commit")
    report = build_typing_shadow_service_reuse_campaign_v1(
        _campaign_cases(time.perf_counter_ns()), campaign_id="e2-shadow-service-reuse-001",
        environment=environment)
    parse_typing_shadow_service_reuse_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream: stream.write(_canonical(report) + b"\n")
    mixed = report["cases"][0]
    print(json.dumps({"output": output.relative_to(WORKSPACE).as_posix(),
        "campaign_sha256": report["campaign_sha256"], "cases": report["case_count"],
        "mixed_cache_delta": mixed["cache_delta"], "physical_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
