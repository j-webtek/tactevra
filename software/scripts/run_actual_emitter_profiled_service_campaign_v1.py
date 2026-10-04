"""Retain actual shared-emitter bytes through the profiled shadow service."""

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
from rocell.application.actual_emitter_profiled_service_campaign_v1 import build_actual_emitter_profiled_service_campaign_v1, parse_actual_emitter_profiled_service_campaign_v1  # noqa: E402
from rocell.application.operational_latency_reference_v1 import capture_operational_benchmark_environment_v1  # noqa: E402
from rocell.application.typing_ik_reuse_profile_gate_v1 import QUALIFIED_EVIDENCE_SHA256  # noqa: E402
from rocell.application.typing_profiled_shadow_service_v1 import TypingProfiledShadowServiceV1  # noqa: E402
from rocell_ai.profiled_service_ingress_v2 import emit_profiled_service_inputs_v2  # noqa: E402

DEFAULT_OUTPUT = Path("software/ai/eval/actual_emitter_profiled_service_campaign_v1.json")
COUNTERS = ("lookups", "hits", "misses", "stores", "capacity_skips")
TARGETS = ("R", "O", "B", "O", "T")


def _calibration():
    context = fixture.ingress_fixture.load_simulation_context(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST)
    return fixture.ik_fixture._snapshot(context).snapshot_sha256


def _service(name, *, active_calibration=None, evidence=None):
    calibration = _calibration()
    return TypingProfiledShadowServiceV1.start(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST,
        service_instance_id=name, issued_monotonic_ns=100,
        qualified_calibration_snapshot_sha256=calibration,
        active_calibration_snapshot_sha256=active_calibration or calibration,
        evidence_sha256=evidence or QUALIFIED_EVIDENCE_SHA256)


def _inputs(service, request_id):
    source = fixture._inputs(TARGETS, "robot", context=service.context)
    return emit_profiled_service_inputs_v2(
        source, batch_id=f"actual-emitter-{request_id}", request_id=request_id)


def _counters(service): return service.snapshot()["cache_counters"]
def _delta(before, after): return {name: after[name] - before[name] for name in COUNTERS}


def _run(service, case, request_id, *, cancel=False):
    inputs = _inputs(service, request_id)
    payload_sha = hashlib.sha256(inputs["payload"]).hexdigest()
    before = _counters(service); started = time.perf_counter_ns()
    service.submit(request_id, inputs)
    receipt = service.cancel(request_id) if cancel else service.execute_next()
    duration = time.perf_counter_ns() - started
    snapshot = service.snapshot()
    return {"case": case, "status": receipt["status"],
            "profile_decision": snapshot["profile_decision"],
            "duration_ns": duration, "payload_sha256": payload_sha,
            "cache_delta": _delta(before, snapshot["cache_counters"])}


def _cases():
    qualified = _service("actual-emitter-qualified")
    cases = [
        _run(qualified, "QUALIFIED_COLD", "actual-robot-cold"),
        _run(qualified, "QUALIFIED_WARM", "actual-robot-warm"),
    ]
    calibration = _service("actual-emitter-calibration", active_calibration="f" * 64)
    cases.append(_run(calibration, "CALIBRATION_FALLBACK", "actual-robot-calibration"))
    evidence = _service("actual-emitter-evidence", evidence={**QUALIFIED_EVIDENCE_SHA256, "typing_shadow_service_reuse_campaign_v1": "f" * 64})
    cases.append(_run(evidence, "EVIDENCE_FALLBACK", "actual-robot-evidence"))
    cancel = _service("actual-emitter-cancel")
    cases.append(_run(cancel, "CANCEL_BEFORE_ADMISSION", "actual-robot-cancel", cancel=True))
    reload_service = _service("actual-emitter-reload")
    reload_service.reload_sources(issued_monotonic_ns=200)
    cases.append(_run(reload_service, "RELOAD_FALLBACK", "actual-robot-reload"))
    restart_service = _service("actual-emitter-restart")
    restart_service.restart(service_instance_id="actual-emitter-restarted", issued_monotonic_ns=200)
    cases.append(_run(restart_service, "RESTART_FALLBACK", "actual-robot-restart"))
    return cases


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
        benchmark_entrypoint="software/scripts/run_actual_emitter_profiled_service_campaign_v1.py")
    if environment["repository_dirty"]: parser.error("campaign must run from a clean source commit")
    report = build_actual_emitter_profiled_service_campaign_v1(
        _cases(), campaign_id="e2-actual-emitter-profiled-service-001",
        environment=environment, ordered_targets=TARGETS)
    parse_actual_emitter_profiled_service_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").write(json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    print(json.dumps({"output": output.relative_to(WORKSPACE).as_posix(), "campaign_sha256": report["campaign_sha256"], "cases": report["case_count"], "physical_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
