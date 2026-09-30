"""Exercise bounded operational disturbances against the actual-emitter service."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

WORKSPACE = Path(__file__).resolve().parents[2]
SOFTWARE = WORKSPACE / "software"
sys.path[:0] = [str(SOFTWARE / "src"), str(SOFTWARE / "ai"),
                str(SOFTWARE / "tests" / "integration")]
import test_typing_shadow_pipeline_v1 as fixture  # noqa: E402
from rocell.application.actual_emitter_disturbance_campaign_v1 import build_actual_emitter_disturbance_campaign_v1, parse_actual_emitter_disturbance_campaign_v1  # noqa: E402
from rocell.application.actual_emitter_mixed_queue_campaign_v1 import PATTERNS  # noqa: E402
from rocell.application.operational_latency_reference_v1 import capture_operational_benchmark_environment_v1  # noqa: E402
from rocell.application.typing_ik_reuse_profile_gate_v1 import QUALIFIED_EVIDENCE_SHA256  # noqa: E402
from rocell.application.typing_profiled_shadow_service_v1 import TypingProfiledShadowServiceV1  # noqa: E402
from rocell.application.typing_shadow_service_v1 import TypingShadowServiceV1Error  # noqa: E402
from rocell_ai.profiled_service_ingress_v2 import emit_profiled_service_inputs_v2  # noqa: E402

DEFAULT_OUTPUT = Path("software/ai/eval/actual_emitter_disturbance_campaign_v1.json")
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
        service_instance_id="actual-emitter-disturbance", issued_monotonic_ns=100,
        qualified_calibration_snapshot_sha256=calibration,
        active_calibration_snapshot_sha256=calibration,
        evidence_sha256=QUALIFIED_EVIDENCE_SHA256,
        maximum_entries=256, maximum_queued=8, maximum_requests=64)


def _inputs(service, request_id, pattern_index=1):
    name, targets = PATTERNS[pattern_index % len(PATTERNS)]
    source = fixture._inputs(targets, TEXT[name], context=service.context)
    return emit_profiled_service_inputs_v2(
        source, batch_id=f"batch-{request_id}", request_id=request_id)


def _counters(service): return service.snapshot()["cache_counters"]
def _delta(before, after): return {name: after[name] - before[name] for name in COUNTERS}


def _prewarm(service, prefix):
    for index in range(len(PATTERNS)):
        request_id = f"{prefix}-{index}"
        service.submit(request_id, _inputs(service, request_id, index))
    for _ in PATTERNS:
        assert service.execute_next()["status"] == "SHADOW_COMPLETED"


def _completed(service, request_ids):
    statuses = []; observed = []
    for _ in request_ids:
        receipt = service.execute_next(); statuses.append(receipt["status"])
        observed.append(receipt["request_id"])
    if observed != list(request_ids): raise RuntimeError("FIFO order changed")
    return statuses


def _case(name, statuses, messages, activity, service, *, shadow=None, reference=None):
    return {"case": name, "statuses": statuses, "request_order_preserved": True,
            "rejection_messages": messages, "cache_activity": activity,
            "exact_reuse_enabled_after": service.exact_reuse_enabled,
            "automatic_retries": 0,
            "reference_equivalent": shadow is not None and shadow == reference,
            "shadow_receipt_sha256": shadow}


def _campaign_cases():
    service = _service(); _prewarm(service, "warm")
    reference_id = "measured-reference"
    before = _counters(service)
    service.submit(reference_id, _inputs(service, reference_id))
    reference_receipt = service.execute_next(); reference = reference_receipt["shadow_receipt_sha256"]
    cases = [_case("WARM_BASELINE", [reference_receipt["status"]], [],
                   _delta(before, _counters(service)), service,
                   shadow=reference, reference=reference)]

    saturation_ids = [f"saturation-{index}" for index in range(8)]
    for index, request_id in enumerate(saturation_ids):
        service.submit(request_id, _inputs(service, request_id, index))
    messages = []
    try: service.submit("saturation-overflow", _inputs(service, "saturation-overflow"))
    except TypingShadowServiceV1Error as exc: messages.append(str(exc))
    else: raise RuntimeError("queue saturation did not reject")
    before = _counters(service); statuses = _completed(service, saturation_ids)
    cases.append(_case("QUEUE_SATURATION", statuses, messages,
                       _delta(before, _counters(service)), service))

    cancel_ids = [f"cancel-pressure-{index}" for index in range(8)]
    for index, request_id in enumerate(cancel_ids):
        service.submit(request_id, _inputs(service, request_id, index))
    canceled = []
    for index in (1, 4, 7): canceled.append(service.cancel(cancel_ids[index])["status"])
    survivors = [item for index, item in enumerate(cancel_ids) if index not in (1, 4, 7)]
    before = _counters(service); completed = _completed(service, survivors)
    cases.append(_case("CANCEL_PRESSURE", canceled + completed, [],
                       _delta(before, _counters(service)), service))

    before = _counters(service); malformed = []
    try: service.submit("wrong-submit-id", _inputs(service, "payload-id"))
    except TypingShadowServiceV1Error as exc: malformed.append(str(exc))
    bad = _inputs(service, "forbidden-input"); bad["context_lifecycle"] = None
    try: service.submit("forbidden-input", bad)
    except TypingShadowServiceV1Error as exc: malformed.append(str(exc))
    try: service.submit(reference_id, _inputs(service, reference_id))
    except TypingShadowServiceV1Error as exc: malformed.append(str(exc))
    cases.append(_case("MALFORMED_REJECTION", [], malformed,
                       _delta(before, _counters(service)), service))

    reload_ids = [f"reload-stale-{index}" for index in range(3)]
    for index, request_id in enumerate(reload_ids):
        service.submit(request_id, _inputs(service, request_id, index))
    service.reload_sources(issued_monotonic_ns=200)
    stale = _completed(service, reload_ids)
    post_reload = "post-reload-full-solve"
    service.submit(post_reload, _inputs(service, post_reload))
    stale.append(service.execute_next()["status"])
    cases.append(_case("RELOAD_STALE_AND_FALLBACK", stale, [],
                       _counters(service), service))

    restart = _service(); _prewarm(restart, "restart-warm")
    restart_ids = [f"restart-stale-{index}" for index in range(2)]
    for index, request_id in enumerate(restart_ids):
        restart.submit(request_id, _inputs(restart, request_id, index))
    restart.restart(service_instance_id="actual-emitter-disturbance-new",
                    issued_monotonic_ns=300)
    stale = _completed(restart, restart_ids)
    post_restart = "post-restart-full-solve"
    restart.submit(post_restart, _inputs(restart, post_restart))
    stale.append(restart.execute_next()["status"])
    cases.append(_case("RESTART_STALE_AND_FALLBACK", stale, [],
                       _counters(restart), restart))

    replacement = _service(); _prewarm(replacement, "replacement-warm")
    before = _counters(replacement)
    replacement.submit(reference_id, _inputs(replacement, reference_id))
    receipt = replacement.execute_next(); shadow = receipt["shadow_receipt_sha256"]
    cases.append(_case("QUALIFIED_REPLACEMENT_RECOVERY", [receipt["status"]], [],
                       _delta(before, _counters(replacement)), replacement,
                       shadow=shadow, reference=reference))
    service.invalidate(); restart.invalidate(); replacement.invalidate()
    return cases, reference


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
        benchmark_entrypoint="software/scripts/run_actual_emitter_disturbance_campaign_v1.py")
    if environment["repository_dirty"]: parser.error("campaign must run from a clean source commit")
    cases, reference = _campaign_cases()
    report = build_actual_emitter_disturbance_campaign_v1(
        cases, campaign_id="e2-actual-emitter-disturbance-001",
        environment=environment, reference_shadow_receipt_sha256=reference)
    parse_actual_emitter_disturbance_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").write(json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    print(json.dumps({"output": output.relative_to(WORKSPACE).as_posix(),
                      "campaign_sha256": report["campaign_sha256"],
                      "cases": [item["case"] for item in cases],
                      "physical_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
