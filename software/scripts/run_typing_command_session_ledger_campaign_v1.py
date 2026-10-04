"""Retain actual-emitter session correlation through shadow completion."""

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
from rocell.application.typing_command_session_ledger_campaign_v1 import build_typing_command_session_ledger_campaign_v1, parse_typing_command_session_ledger_campaign_v1  # noqa: E402
from rocell.application.typing_command_session_ledger_v1 import TypingCommandSessionLedgerV1, TypingCommandSessionLedgerV1Error  # noqa: E402
from rocell.application.typing_ik_reuse_profile_gate_v1 import QUALIFIED_EVIDENCE_SHA256  # noqa: E402
from rocell.application.typing_runtime_supervisor_v1 import TypingRuntimeSupervisorV1  # noqa: E402
from rocell.application.typing_supervised_command_gateway_v1 import TypingSupervisedCommandGatewayV1  # noqa: E402
from rocell_ai.profiled_service_ingress_v2 import emit_profiled_service_inputs_v2  # noqa: E402

DEFAULT_OUTPUT = Path("software/ai/eval/typing_command_session_ledger_campaign_v1.json")


def _ledger(*, sessions=8, queued=2, requests=8):
    context = fixture.ingress_fixture.load_simulation_context(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST)
    calibration = fixture.ik_fixture._snapshot(context).snapshot_sha256
    supervisor = TypingRuntimeSupervisorV1.start(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST,
        service_instance_id="session-ledger-campaign", issued_monotonic_ns=100,
        qualified_calibration_snapshot_sha256=calibration,
        active_calibration_snapshot_sha256=calibration,
        evidence_sha256=QUALIFIED_EVIDENCE_SHA256,
        maximum_entries=256, maximum_queued=queued, maximum_requests=requests)
    ledger = TypingCommandSessionLedgerV1(
        TypingSupervisedCommandGatewayV1(supervisor),
        maximum_sessions=sessions)
    return ledger, supervisor


def _inputs(value, request_id, text="robot"):
    source = fixture._inputs(tuple(text.upper()), text, context=value.context)
    return emit_profiled_service_inputs_v2(
        source, batch_id=f"batch-{request_id}", request_id=request_id)


def _record(name, ledger, initial, outcome, observed):
    return {"case": name, "initial_receipt": initial,
            "outcome_receipt": outcome, "observed": observed,
            "ledger_snapshot": ledger.snapshot(), "chain_validated": True}


def _campaign_cases():
    ledger, supervisor = _ledger()
    initial = ledger.submit("mission-complete", "complete", _inputs(ledger, "complete"))
    outcome = ledger.run_next_shadow()
    cases = [_record("COMPLETED_CHAIN", ledger, initial, outcome, "TERMINAL_RECORDED")]
    supervisor.invalidate()

    ledger, supervisor = _ledger()
    inputs = _inputs(ledger, "replay")
    initial = ledger.submit("mission-replay", "replay", inputs)
    outcome = ledger.submit("mission-replay", "replay", inputs)
    cases.append(_record("IDEMPOTENT_REPLAY", ledger, initial, outcome,
                         "IDENTICAL_RECEIPT_REPLAYED")); supervisor.invalidate()

    ledger, supervisor = _ledger()
    initial = ledger.submit("mission-cancel", "cancel", _inputs(ledger, "cancel"))
    outcome = ledger.cancel("cancel")
    cases.append(_record("CANCELED_CHAIN", ledger, initial, outcome,
                         "TERMINAL_RECORDED")); supervisor.invalidate()

    ledger, supervisor = _ledger()
    initial = ledger.submit("mission-stale", "stale", _inputs(ledger, "stale"))
    supervisor.reload_sources(issued_monotonic_ns=200)
    outcome = ledger.run_next_shadow()
    cases.append(_record("STALE_CHAIN", ledger, initial, outcome,
                         "TERMINAL_RECORDED")); supervisor.invalidate()

    ledger, supervisor = _ledger(queued=1, requests=4)
    ledger.submit("mission-pressure", "held", _inputs(ledger, "held"))
    initial = ledger.submit("mission-pressure", "overflow", _inputs(ledger, "overflow"))
    cases.append(_record("ADMISSION_REJECTION", ledger, initial, initial,
                         "TERMINAL_RECORDED")); supervisor.invalidate()

    ledger, supervisor = _ledger(sessions=1)
    ledger.submit("mission-capacity", "retained", _inputs(ledger, "retained"))
    initial = ledger.submit("mission-capacity", "capacity", _inputs(ledger, "capacity"))
    cases.append(_record("CAPACITY_REJECTION", ledger, initial, initial,
                         "TERMINAL_NOT_RETAINED")); supervisor.invalidate()

    ledger, supervisor = _ledger()
    initial = ledger.submit("mission-conflict", "conflict", _inputs(ledger, "conflict"))
    try:
        ledger.submit("mission-conflict", "conflict", _inputs(ledger, "conflict", "robots"))
    except TypingCommandSessionLedgerV1Error as exc:
        if str(exc) != "request identity was reused with different input": raise
    else: raise RuntimeError("conflicting duplicate was accepted")
    cases.append(_record("CONFLICTING_DUPLICATE_REJECTION", ledger, initial, None,
                         "CONFLICT_REJECTED")); supervisor.invalidate()

    ledger, supervisor = _ledger()
    initial = ledger.submit("mission-lookup", "lookup", _inputs(ledger, "lookup"))
    ledger.run_next_shadow(); outcome = ledger.get("lookup")
    cases.append(_record("TERMINAL_LOOKUP_REPLAY", ledger, initial, outcome,
                         "IDENTICAL_RECEIPT_REPLAYED")); supervisor.invalidate()
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
        benchmark_entrypoint="software/scripts/run_typing_command_session_ledger_campaign_v1.py")
    if environment["repository_dirty"]: parser.error("campaign must run from a clean source commit")
    report = build_typing_command_session_ledger_campaign_v1(
        _campaign_cases(), campaign_id="e2-command-session-ledger-001",
        environment=environment)
    parse_typing_command_session_ledger_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").write(json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    print(json.dumps({"output": output.relative_to(WORKSPACE).as_posix(),
                      "campaign_sha256": report["campaign_sha256"],
                      "outcomes": [(item["case"], item["observed"]) for item in report["cases"]],
                      "physical_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
