"""Retain runtime-supervisor transition evidence from actual-emitter bytes."""

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
from rocell.application.operational_latency_reference_v1 import capture_operational_benchmark_environment_v1  # noqa: E402
from rocell.application.typing_ik_reuse_profile_gate_v1 import QUALIFIED_EVIDENCE_SHA256  # noqa: E402
from rocell.application.typing_runtime_supervisor_campaign_v1 import build_typing_runtime_supervisor_campaign_v1, parse_typing_runtime_supervisor_campaign_v1  # noqa: E402
from rocell.application.typing_runtime_supervisor_v1 import TypingRuntimeSupervisorV1, TypingRuntimeSupervisorV1Error  # noqa: E402
from rocell_ai.profiled_service_ingress_v2 import emit_profiled_service_inputs_v2  # noqa: E402

DEFAULT_OUTPUT = Path("software/ai/eval/typing_runtime_supervisor_campaign_v1.json")


def _start(*, evidence=None):
    context = fixture.ingress_fixture.load_simulation_context(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST)
    calibration = fixture.ik_fixture._snapshot(context).snapshot_sha256
    return TypingRuntimeSupervisorV1.start(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST,
        service_instance_id="runtime-supervisor-campaign", issued_monotonic_ns=100,
        qualified_calibration_snapshot_sha256=calibration,
        active_calibration_snapshot_sha256=calibration,
        evidence_sha256=evidence or QUALIFIED_EVIDENCE_SHA256,
        maximum_entries=256, maximum_queued=8, maximum_requests=32)


def _inputs(value, request_id):
    source = fixture._inputs(("R", "O", "B", "O", "T"), "robot",
                             context=value.context)
    return emit_profiled_service_inputs_v2(
        source, batch_id=f"batch-{request_id}", request_id=request_id)


def _prewarm(value, prefix):
    for index in range(2):
        request_id = f"{prefix}-{index}"
        value.submit(request_id, _inputs(value, request_id))
        assert value.execute_next()["status"] == "SHADOW_COMPLETED"


def _record(name, value, *, status=None, rejection=None, shadow=None, reference=None):
    snap = value.snapshot()
    return {"case": name, "state": snap["state"],
            "state_reason": snap["state_reason"], "active": snap["active"],
            "exact_reuse_enabled": snap["exact_reuse_enabled"], "status": status,
            "submission_rejection": rejection,
            "cache_counters": snap["cache_counters"],
            "reference_equivalent": shadow is not None and shadow == reference,
            "shadow_receipt_sha256": shadow, "automatic_retries": 0,
            "snapshot_sha256": snap["supervisor_snapshot_sha256"]}


def _campaign_cases():
    warm = _start(); _prewarm(warm, "warm")
    cases = [_record("QUALIFIED_WARM_START", warm)]
    measured_id = "measured-reference"
    warm.submit(measured_id, _inputs(warm, measured_id))
    reference_receipt = warm.execute_next(); reference = reference_receipt["shadow_receipt_sha256"]

    changed = dict(QUALIFIED_EVIDENCE_SHA256); changed[next(iter(changed))] = "f" * 64
    fallback = _start(evidence=changed)
    fallback.submit(measured_id, _inputs(fallback, measured_id))
    receipt = fallback.execute_next()
    cases.append(_record("STARTUP_MISMATCH_FULL_SOLVE", fallback,
                         status=receipt["status"],
                         shadow=receipt["shadow_receipt_sha256"], reference=reference))

    reload = _start(); reload.submit("reload-queued", _inputs(reload, "reload-queued"))
    reload.reload_sources(issued_monotonic_ns=200)
    rejection = None
    try: reload.submit("reload-blocked", _inputs(reload, "reload-blocked"))
    except TypingRuntimeSupervisorV1Error as exc: rejection = str(exc)
    receipt = reload.execute_next()
    cases.append(_record("RELOAD_REQUIRES_REQUALIFICATION", reload,
                         status=receipt["status"], rejection=rejection))

    restart = _start(); restart.submit("restart-queued", _inputs(restart, "restart-queued"))
    restart.restart(service_instance_id="runtime-supervisor-campaign-new",
                    issued_monotonic_ns=300)
    rejection = None
    try: restart.submit("restart-blocked", _inputs(restart, "restart-blocked"))
    except TypingRuntimeSupervisorV1Error as exc: rejection = str(exc)
    receipt = restart.execute_next()
    cases.append(_record("RESTART_REQUIRES_REQUALIFICATION", restart,
                         status=receipt["status"], rejection=rejection))

    reload.continue_full_solve_only()
    reload.submit("explicit-fallback", _inputs(reload, "explicit-fallback"))
    receipt = reload.execute_next()
    cases.append(_record("EXPLICIT_FULL_SOLVE_CONTINUATION", reload,
                         status=receipt["status"]))

    replacement = _start(); _prewarm(replacement, "replacement")
    replacement.submit(measured_id, _inputs(replacement, measured_id))
    receipt = replacement.execute_next(); shadow = receipt["shadow_receipt_sha256"]
    cases.append(_record("QUALIFIED_REPLACEMENT_WARM", replacement,
                         status=receipt["status"], shadow=shadow, reference=reference))

    replacement.invalidate(); rejection = None
    try: replacement.submit("invalidated", {})
    except TypingRuntimeSupervisorV1Error as exc: rejection = str(exc)
    cases.append(_record("INVALIDATION_TERMINAL", replacement, rejection=rejection))
    warm.invalidate(); fallback.invalidate(); reload.invalidate(); restart.invalidate()
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
        benchmark_entrypoint="software/scripts/run_typing_runtime_supervisor_campaign_v1.py")
    if environment["repository_dirty"]: parser.error("campaign must run from a clean source commit")
    cases, reference = _campaign_cases()
    report = build_typing_runtime_supervisor_campaign_v1(
        cases, campaign_id="e2-runtime-supervisor-001", environment=environment,
        reference_shadow_receipt_sha256=reference)
    parse_typing_runtime_supervisor_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").write(json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    print(json.dumps({"output": output.relative_to(WORKSPACE).as_posix(),
                      "campaign_sha256": report["campaign_sha256"],
                      "states": [item["state"] for item in cases],
                      "physical_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
