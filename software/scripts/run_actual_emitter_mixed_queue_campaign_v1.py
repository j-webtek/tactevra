"""Retain cold/warm mixed-queue actual-emitter service evidence."""

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
sys.path[:0] = [str(SOFTWARE / "src"), str(SOFTWARE / "ai"),
                str(SOFTWARE / "tests" / "integration")]
import test_typing_shadow_pipeline_v1 as fixture  # noqa: E402
from rocell.application.actual_emitter_mixed_queue_campaign_v1 import PATTERNS, build_actual_emitter_mixed_queue_campaign_v1, parse_actual_emitter_mixed_queue_campaign_v1, percentile_nearest_rank_v1  # noqa: E402
from rocell.application.operational_latency_reference_v1 import capture_operational_benchmark_environment_v1  # noqa: E402
from rocell.application.typing_ik_reuse_profile_gate_v1 import QUALIFIED_EVIDENCE_SHA256  # noqa: E402
from rocell.application.typing_profiled_shadow_service_v1 import TypingProfiledShadowServiceV1  # noqa: E402
from rocell_ai.profiled_service_ingress_v2 import emit_profiled_service_inputs_v2  # noqa: E402

DEFAULT_OUTPUT = Path("software/ai/eval/actual_emitter_mixed_queue_campaign_v1.json")
COUNTERS = ("lookups", "hits", "misses", "stores", "capacity_skips")
TEXT = {"HOME_TRANSITION": "hi", "WORD_ROBOT": "robot",
        "REPEAT_NUMBER_PUNCTUATION": "hh1.", "ALPHABETIC_EXTREMES": "az",
        "NUMBER_SPACE_ENTER": "1 \n"}


def _service():
    context = fixture.ingress_fixture.load_simulation_context(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST)
    calibration = fixture.ik_fixture._snapshot(context).snapshot_sha256
    return TypingProfiledShadowServiceV1.start(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST,
        service_instance_id="actual-emitter-mixed-queue", issued_monotonic_ns=100,
        qualified_calibration_snapshot_sha256=calibration,
        active_calibration_snapshot_sha256=calibration,
        evidence_sha256=QUALIFIED_EVIDENCE_SHA256,
        maximum_queued=8, maximum_requests=16)


def _counters(service): return service.snapshot()["cache_counters"]
def _delta(before, after): return {name: after[name] - before[name] for name in COUNTERS}


def _round(service, label):
    request_ids = []; payloads = []
    for pattern_id, targets in PATTERNS:
        request_id = f"mixed-{label.lower()}-{pattern_id.lower()}"
        source = fixture._inputs(targets, TEXT[pattern_id], context=service.context)
        inputs = emit_profiled_service_inputs_v2(
            source, batch_id=f"batch-{request_id}", request_id=request_id)
        service.submit(request_id, inputs)
        request_ids.append(request_id)
        payloads.append(hashlib.sha256(inputs["payload"]).hexdigest())
    before = _counters(service); statuses = []; durations = []
    for request_id in request_ids:
        started = time.perf_counter_ns(); receipt = service.execute_next()
        durations.append(time.perf_counter_ns() - started)
        statuses.append(receipt["status"])
        if receipt["request_id"] != request_id:
            raise RuntimeError("FIFO request order changed")
    return {"round": label, "request_ids": request_ids,
            "payload_sha256": payloads, "receipt_statuses": statuses,
            "duration_ns": durations,
            "p50_duration_ns": percentile_nearest_rank_v1(durations, 0.50),
            "p95_duration_ns": percentile_nearest_rank_v1(durations, 0.95),
            "cache_delta": _delta(before, _counters(service))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix()); args = parser.parse_args(argv)
    candidate = Path(args.output)
    if candidate.is_absolute(): parser.error("output must be workspace-relative")
    output = (WORKSPACE / candidate).resolve()
    if WORKSPACE not in output.parents: parser.error("output escapes workspace")
    if output.exists() or output.is_symlink(): parser.error(f"refusing to overwrite {output}")
    environment = capture_operational_benchmark_environment_v1(
        WORKSPACE, captured_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        benchmark_entrypoint="software/scripts/run_actual_emitter_mixed_queue_campaign_v1.py")
    if environment["repository_dirty"]: parser.error("campaign must run from a clean source commit")
    service = _service(); rounds = [_round(service, "COLD"), _round(service, "WARM")]
    report = build_actual_emitter_mixed_queue_campaign_v1(
        rounds, campaign_id="e2-actual-emitter-mixed-queue-001",
        environment=environment, request_order_preserved=True)
    parse_actual_emitter_mixed_queue_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").write(json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    print(json.dumps({"output": output.relative_to(WORKSPACE).as_posix(), "campaign_sha256": report["campaign_sha256"], "cold_p95_ns": rounds[0]["p95_duration_ns"], "warm_p95_ns": rounds[1]["p95_duration_ns"], "physical_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
