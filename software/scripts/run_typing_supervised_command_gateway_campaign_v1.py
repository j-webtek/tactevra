"""Retain actual-emitter admission through the runtime supervisor gateway."""

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
from rocell.application.typing_runtime_supervisor_v1 import TypingRuntimeSupervisorV1  # noqa: E402
from rocell.application.typing_supervised_command_gateway_campaign_v1 import build_typing_supervised_command_gateway_campaign_v1, parse_typing_supervised_command_gateway_campaign_v1  # noqa: E402
from rocell.application.typing_supervised_command_gateway_v1 import TypingSupervisedCommandGatewayV1  # noqa: E402
from rocell_ai.profiled_service_ingress_v2 import emit_profiled_service_inputs_v2  # noqa: E402

DEFAULT_OUTPUT = Path("software/ai/eval/typing_supervised_command_gateway_campaign_v1.json")


def _supervisor(*, evidence=None, queued=2, requests=8):
    context = fixture.ingress_fixture.load_simulation_context(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST)
    calibration = fixture.ik_fixture._snapshot(context).snapshot_sha256
    return TypingRuntimeSupervisorV1.start(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST,
        service_instance_id="supervised-gateway-campaign", issued_monotonic_ns=100,
        qualified_calibration_snapshot_sha256=calibration,
        active_calibration_snapshot_sha256=calibration,
        evidence_sha256=evidence or QUALIFIED_EVIDENCE_SHA256,
        maximum_entries=256, maximum_queued=queued, maximum_requests=requests)


def _inputs(value, request_id):
    source = fixture._inputs(("R", "O", "B", "O", "T"), "robot",
                             context=value.context)
    return emit_profiled_service_inputs_v2(
        source, batch_id=f"batch-{request_id}", request_id=request_id)


def _record(name, value, admission, *, shadow=None, reference=None):
    return {"case": name, "admission_receipt": admission,
            "gateway_snapshot": value.snapshot(),
            "shadow_status": shadow["status"] if shadow is not None else None,
            "shadow_receipt_sha256": (shadow["shadow_receipt_sha256"]
                                       if shadow is not None else None),
            "reference_equivalent": (shadow is not None
                                      and shadow["shadow_receipt_sha256"] == reference)}


def _campaign_cases():
    warm_supervisor = _supervisor(); warm = TypingSupervisedCommandGatewayV1(warm_supervisor)
    measured = "measured-reference"; admission = warm.admit(measured, _inputs(warm, measured))
    shadow = warm.run_next_shadow(); reference = shadow["shadow_receipt_sha256"]
    cases = [_record("WARM_ADMISSION", warm, admission, shadow=shadow, reference=reference)]

    changed = dict(QUALIFIED_EVIDENCE_SHA256); changed[next(iter(changed))] = "f" * 64
    fallback_supervisor = _supervisor(evidence=changed)
    fallback = TypingSupervisedCommandGatewayV1(fallback_supervisor)
    admission = fallback.admit(measured, _inputs(fallback, measured)); shadow = fallback.run_next_shadow()
    cases.append(_record("FULL_SOLVE_ADMISSION", fallback, admission,
                         shadow=shadow, reference=reference))

    pressure_supervisor = _supervisor(queued=1, requests=4)
    pressure = TypingSupervisedCommandGatewayV1(pressure_supervisor)
    pressure.admit("queued", _inputs(pressure, "queued"))
    admission = pressure.admit("overflow", _inputs(pressure, "overflow"))
    cases.append(_record("QUEUE_BACKPRESSURE", pressure, admission))
    pressure.run_next_shadow()
    admission = pressure.admit("queued", _inputs(pressure, "queued"))
    cases.append(_record("INPUT_REJECTION", pressure, admission))

    bound_supervisor = _supervisor(queued=1, requests=1)
    bound = TypingSupervisedCommandGatewayV1(bound_supervisor)
    bound.admit("only", _inputs(bound, "only")); bound.run_next_shadow()
    admission = bound.admit("beyond-bound", _inputs(bound, "beyond-bound"))
    cases.append(_record("REQUEST_BOUND_BACKPRESSURE", bound, admission))

    state_supervisor = _supervisor(); state = TypingSupervisedCommandGatewayV1(state_supervisor)
    state_supervisor.reload_sources(issued_monotonic_ns=200)
    admission = state.admit("blocked", _inputs(state, "blocked"))
    cases.append(_record("REQUALIFICATION_REJECTION", state, admission))
    state_supervisor.continue_full_solve_only()
    admission = state.admit("explicit-fallback", _inputs(state, "explicit-fallback"))
    shadow = state.run_next_shadow()
    cases.append(_record("FULL_SOLVE_CONTINUATION_ADMISSION", state, admission,
                         shadow=shadow, reference=reference))

    replacement_supervisor = _supervisor()
    replacement = TypingSupervisedCommandGatewayV1(replacement_supervisor)
    admission = replacement.admit(measured, _inputs(replacement, measured))
    shadow = replacement.run_next_shadow()
    cases.append(_record("QUALIFIED_REPLACEMENT_ADMISSION", replacement, admission,
                         shadow=shadow, reference=reference))
    for item in (warm_supervisor, fallback_supervisor, pressure_supervisor,
                 bound_supervisor, state_supervisor, replacement_supervisor):
        item.invalidate()
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
        benchmark_entrypoint="software/scripts/run_typing_supervised_command_gateway_campaign_v1.py")
    if environment["repository_dirty"]: parser.error("campaign must run from a clean source commit")
    cases, reference = _campaign_cases()
    report = build_typing_supervised_command_gateway_campaign_v1(
        cases, campaign_id="e2-supervised-command-gateway-001",
        environment=environment, reference_shadow_receipt_sha256=reference)
    parse_typing_supervised_command_gateway_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").write(json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    print(json.dumps({"output": output.relative_to(WORKSPACE).as_posix(),
                      "campaign_sha256": report["campaign_sha256"],
                      "outcomes": [(item["case"], item["admission_receipt"]["status"],
                                    item["admission_receipt"]["disposition"],
                                    item["admission_receipt"]["blocker"])
                                   for item in cases],
                      "physical_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
