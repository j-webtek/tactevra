"""Retain actual-emitter evidence for ledger-owned handoff assembly."""

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

from rocell.application.operational_latency_reference_v1 import capture_operational_benchmark_environment_v1  # noqa: E402
from rocell.application.typing_execution_handoff_assembler_campaign_v1 import build_typing_execution_handoff_assembler_campaign_v1, parse_typing_execution_handoff_assembler_campaign_v1  # noqa: E402
from rocell.application.typing_execution_handoff_assembler_v1 import TypingExecutionHandoffAssemblerV1Error, assemble_typing_execution_handoff_candidate_v1  # noqa: E402
try:  # Support both direct execution and package import in tests.
    from software.scripts.run_typing_command_session_ledger_campaign_v1 import _inputs, _ledger  # noqa: E402
except ModuleNotFoundError:
    from run_typing_command_session_ledger_campaign_v1 import _inputs, _ledger  # noqa: E402

DEFAULT_OUTPUT = Path(
    "software/ai/eval/typing_execution_handoff_assembler_campaign_v1.json"
)


def _record(name, observed, ledger, candidate=None, error=None):
    return {
        "case": name, "observed": observed, "candidate": candidate,
        "error": error, "ledger_snapshot": ledger.snapshot(),
        "artifact_store_snapshot": ledger.artifact_store_snapshot(),
        "zero_authority_validated": True,
    }


def _reject(name, observed, ledger, request_id):
    try:
        assemble_typing_execution_handoff_candidate_v1(ledger, request_id)
    except TypingExecutionHandoffAssemblerV1Error as exc:
        return _record(name, observed, ledger, error=str(exc))
    raise RuntimeError(f"{name} unexpectedly assembled a candidate")


def _campaign_cases():
    ledger, supervisor = _ledger()
    ledger.submit("mission-complete", "complete", _inputs(ledger, "complete"))
    ledger.run_next_shadow()
    candidate = assemble_typing_execution_handoff_candidate_v1(
        ledger, "complete"
    )
    cases = [_record(
        "COMPLETED_ASSEMBLY", "CANDIDATE_ASSEMBLED", ledger,
        candidate=candidate,
    )]
    repeated = assemble_typing_execution_handoff_candidate_v1(
        ledger, "complete"
    )
    cases.append(_record(
        "REPEAT_ASSEMBLY", "IDENTICAL_CANDIDATE_ASSEMBLED", ledger,
        candidate=repeated,
    ))
    supervisor.invalidate()
    audited = assemble_typing_execution_handoff_candidate_v1(
        ledger, "complete"
    )
    cases.append(_record(
        "POST_INVALIDATION_AUDIT_ASSEMBLY",
        "IDENTICAL_CANDIDATE_ASSEMBLED", ledger, candidate=audited,
    ))

    queued, queued_owner = _ledger()
    queued.submit("mission-queued", "queued", _inputs(queued, "queued"))
    cases.append(_reject(
        "QUEUED_REJECTED", "INCOMPLETE_CHAIN_REJECTED", queued, "queued"
    ))

    canceled, canceled_owner = _ledger()
    canceled.submit(
        "mission-canceled", "canceled", _inputs(canceled, "canceled")
    )
    canceled.cancel("canceled")
    cases.append(_reject(
        "CANCELED_REJECTED", "INCOMPLETE_CHAIN_REJECTED",
        canceled, "canceled",
    ))

    stale, stale_owner = _ledger()
    stale.submit("mission-stale", "stale", _inputs(stale, "stale"))
    stale_owner.reload_sources(issued_monotonic_ns=200)
    stale.run_next_shadow()
    cases.append(_reject(
        "STALE_REJECTED", "INCOMPLETE_CHAIN_REJECTED", stale, "stale"
    ))

    rejected, rejected_owner = _ledger(queued=1, requests=4)
    rejected.submit("mission-held", "held", _inputs(rejected, "held"))
    rejected.submit(
        "mission-rejected", "rejected", _inputs(rejected, "rejected")
    )
    cases.append(_reject(
        "ADMISSION_REJECTED", "INCOMPLETE_CHAIN_REJECTED",
        rejected, "rejected",
    ))
    cases.append(_reject(
        "UNKNOWN_REJECTED", "UNKNOWN_REQUEST_REJECTED", rejected, "unknown"
    ))

    for owner in (queued_owner, canceled_owner, stale_owner, rejected_owner):
        owner.invalidate()
    return cases, candidate["handoff_candidate_sha256"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    args = parser.parse_args(argv)
    candidate = Path(args.output)
    if candidate.is_absolute():
        parser.error("output must be workspace-relative")
    output = (WORKSPACE / candidate).resolve()
    if WORKSPACE not in output.parents:
        parser.error("output escapes workspace")
    if output.exists() or output.is_symlink():
        parser.error(f"refusing to overwrite {output}")
    environment = capture_operational_benchmark_environment_v1(
        WORKSPACE,
        captured_at_utc=datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        benchmark_entrypoint=(
            "software/scripts/run_typing_execution_handoff_assembler_campaign_v1.py"
        ),
    )
    if environment["repository_dirty"]:
        parser.error("campaign must run from a clean source commit")
    cases, reference = _campaign_cases()
    report = build_typing_execution_handoff_assembler_campaign_v1(
        cases, campaign_id="e2-execution-handoff-assembler-001",
        environment=environment, reference_candidate_sha256=reference,
    )
    parse_typing_execution_handoff_assembler_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").write(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )
    print(json.dumps({
        "output": output.relative_to(WORKSPACE).as_posix(),
        "campaign_sha256": report["campaign_sha256"],
        "outcomes": [(item["case"], item["observed"]) for item in cases],
        "eligible_for_executor": False, "physical_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
