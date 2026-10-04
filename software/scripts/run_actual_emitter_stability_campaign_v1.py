"""Retain repeated cold/warm actual-emitter stability evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

WORKSPACE = Path(__file__).resolve().parents[2]
SOFTWARE = WORKSPACE / "software"
sys.path[:0] = [str(SOFTWARE / "src"), str(SOFTWARE / "ai"),
                str(SOFTWARE / "tests" / "integration")]
import test_typing_shadow_pipeline_v1 as fixture  # noqa: E402
from rocell.application.actual_emitter_mixed_queue_campaign_v1 import PATTERNS  # noqa: E402
from rocell.application.actual_emitter_stability_campaign_v1 import EXPECTED_CYCLES, build_actual_emitter_stability_campaign_v1, parse_actual_emitter_stability_campaign_v1  # noqa: E402
from rocell.application.operational_latency_reference_v1 import capture_operational_benchmark_environment_v1  # noqa: E402
from rocell.application.typing_ik_reuse_profile_gate_v1 import QUALIFIED_EVIDENCE_SHA256  # noqa: E402
from rocell.application.typing_profiled_shadow_service_v1 import TypingProfiledShadowServiceV1  # noqa: E402
from rocell_ai.profiled_service_ingress_v2 import emit_profiled_service_inputs_v2  # noqa: E402

DEFAULT_OUTPUT = Path("software/ai/eval/actual_emitter_stability_campaign_v1.json")
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
        service_instance_id="actual-emitter-stability", issued_monotonic_ns=100,
        qualified_calibration_snapshot_sha256=calibration,
        active_calibration_snapshot_sha256=calibration,
        evidence_sha256=QUALIFIED_EVIDENCE_SHA256,
        maximum_entries=256, maximum_queued=8, maximum_requests=16)


def _counters(service): return service.snapshot()["cache_counters"]
def _delta(before, after): return {name: after[name] - before[name] for name in COUNTERS}


def _round(service, prefix):
    ids = []
    for pattern_id, targets in PATTERNS:
        request_id = f"{prefix}-{pattern_id.lower()}"
        source = fixture._inputs(targets, TEXT[pattern_id], context=service.context)
        inputs = emit_profiled_service_inputs_v2(
            source, batch_id=f"batch-{request_id}", request_id=request_id)
        service.submit(request_id, inputs); ids.append(request_id)
    before = _counters(service); durations = []; hashes = []
    for request_id in ids:
        started = time.perf_counter_ns(); receipt = service.execute_next()
        durations.append(time.perf_counter_ns() - started)
        if receipt["request_id"] != request_id or receipt["status"] != "SHADOW_COMPLETED":
            raise RuntimeError("FIFO completion changed")
        hashes.append(receipt["shadow_receipt_sha256"])
    return durations, hashes, _delta(before, _counters(service))


def _cycle(index):
    cold = _service()
    cold_durations, cold_hashes, cold_delta = _round(cold, f"measured-{index:02d}")
    cold.invalidate(); cold_invalidated = True
    warm = _service()
    _round(warm, f"prewarm-{index:02d}")
    warm_durations, warm_hashes, warm_delta = _round(warm, f"measured-{index:02d}")
    warm.invalidate(); warm_invalidated = True
    return {"cycle": index, "cold_duration_ns": cold_durations,
            "warm_duration_ns": warm_durations, "cold_cache_delta": cold_delta,
            "warm_cache_delta": warm_delta,
            "cold_shadow_receipt_sha256": cold_hashes,
            "warm_shadow_receipt_sha256": warm_hashes,
            "receipts_equivalent": cold_hashes == warm_hashes,
            "cold_invalidated": cold_invalidated,
            "warm_invalidated": warm_invalidated}


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
        benchmark_entrypoint="software/scripts/run_actual_emitter_stability_campaign_v1.py")
    if environment["repository_dirty"]: parser.error("campaign must run from a clean source commit")
    cycles = [_cycle(index) for index in range(1, EXPECTED_CYCLES + 1)]
    report = build_actual_emitter_stability_campaign_v1(
        cycles, campaign_id="e2-actual-emitter-stability-001",
        environment=environment, request_order_preserved=True)
    parse_actual_emitter_stability_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").write(json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    print(json.dumps({"output": output.relative_to(WORKSPACE).as_posix(),
                      "campaign_sha256": report["campaign_sha256"],
                      "samples_per_lane": report["samples_per_lane"],
                      "cold_latency": report["cold_latency"],
                      "warm_latency": report["warm_latency"],
                      "physical_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
