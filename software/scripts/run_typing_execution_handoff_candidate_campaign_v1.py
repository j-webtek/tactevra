"""Retain actual-emitter evidence for the blocked execution handoff candidate."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

WORKSPACE = Path(__file__).resolve().parents[2]
SOFTWARE = WORKSPACE / "software"
sys.path[:0] = [str(SOFTWARE / "src"), str(SOFTWARE / "ai"),
                str(SOFTWARE / "tests" / "integration")]
from rocell.application.operational_latency_reference_v1 import capture_operational_benchmark_environment_v1  # noqa: E402
from rocell.application.typing_execution_handoff_candidate_campaign_v1 import build_typing_execution_handoff_candidate_campaign_v1, parse_typing_execution_handoff_candidate_campaign_v1  # noqa: E402
from rocell.application.typing_execution_handoff_candidate_v1 import TypingExecutionHandoffCandidateV1Error, build_typing_execution_handoff_candidate_v1, parse_typing_execution_handoff_candidate_v1  # noqa: E402
from rocell.application.typing_shadow_pipeline_v1 import run_typing_shadow_pipeline_v1  # noqa: E402
from run_typing_command_session_ledger_campaign_v1 import _inputs, _ledger  # noqa: E402

DEFAULT_OUTPUT = Path("software/ai/eval/typing_execution_handoff_candidate_campaign_v1.json")


def _completed(request_id):
    ledger, supervisor = _ledger()
    inputs = _inputs(ledger, request_id)
    shadow = run_typing_shadow_pipeline_v1(**inputs)
    ledger.submit(f"mission-{request_id}", request_id, inputs)
    session = ledger.run_next_shadow()
    admission = ledger.admission_receipt(request_id)
    service = ledger.terminal_service_receipt(request_id)
    return ledger, supervisor, session, admission, service, shadow


def _case(name, observed, candidate=None, error=None):
    return {"case": name, "observed": observed, "candidate": candidate,
            "error": error, "zero_authority_validated": True}


def _expect_error(name, observed, args):
    try: build_typing_execution_handoff_candidate_v1(*args)
    except TypingExecutionHandoffCandidateV1Error as exc:
        return _case(name, observed, error=str(exc))
    raise RuntimeError(f"{name} unexpectedly built a candidate")


def _campaign_cases():
    ledger, supervisor, session, admission, service, shadow = _completed("handoff")
    candidate = build_typing_execution_handoff_candidate_v1(
        session, admission, service, shadow)
    cases = [_case("VALID_COMPLETED_CHAIN", "CANDIDATE_RETAINED", candidate)]
    rebuilt = build_typing_execution_handoff_candidate_v1(
        session, admission, service, shadow)
    cases.append(_case("DETERMINISTIC_REBUILD",
                       "IDENTICAL_CANDIDATE_REBUILT", rebuilt))

    canceled_ledger, canceled_supervisor = _ledger()
    canceled_inputs = _inputs(canceled_ledger, "canceled")
    canceled_shadow = run_typing_shadow_pipeline_v1(**canceled_inputs)
    canceled_ledger.submit("mission-canceled", "canceled", canceled_inputs)
    canceled_session = canceled_ledger.cancel("canceled")
    canceled_admission = canceled_ledger.admission_receipt("canceled")
    canceled_service = canceled_ledger.terminal_service_receipt("canceled")
    cases.append(_expect_error("NONCOMPLETED_SESSION_REJECTED",
        "SESSION_REJECTED", (canceled_session, canceled_admission,
                              canceled_service, canceled_shadow)))

    other_ledger, other_supervisor, other_session, other_admission, other_service, other_shadow = _completed("other")
    cases.append(_expect_error("ADMISSION_LINEAGE_REJECTED", "ADMISSION_REJECTED",
        (session, other_admission, service, shadow)))
    cases.append(_expect_error("SERVICE_LINEAGE_REJECTED", "SERVICE_REJECTED",
        (session, admission, other_service, shadow)))
    cases.append(_expect_error("SHADOW_LINEAGE_REJECTED", "SHADOW_REJECTED",
        (session, admission, service, other_shadow)))
    cases.append(_case("BLOCKERS_PRESERVED", "BLOCKERS_EXPLICIT", candidate))

    changed = copy.deepcopy(candidate); changed["eligible_for_executor"] = True
    unsigned = dict(changed); unsigned.pop("handoff_candidate_sha256")
    from rocell.application.typing_execution_handoff_candidate_v1 import _sha
    changed["handoff_candidate_sha256"] = _sha(unsigned)
    try: parse_typing_execution_handoff_candidate_v1(changed)
    except TypingExecutionHandoffCandidateV1Error as exc:
        cases.append(_case("AUTHORITY_TAMPER_REJECTED", "AUTHORITY_REJECTED",
                           error=str(exc)))
    else: raise RuntimeError("authority tamper was accepted")
    supervisor.invalidate(); canceled_supervisor.invalidate(); other_supervisor.invalidate()
    return cases, candidate["handoff_candidate_sha256"]


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
        benchmark_entrypoint="software/scripts/run_typing_execution_handoff_candidate_campaign_v1.py")
    if environment["repository_dirty"]: parser.error("campaign must run from a clean source commit")
    cases, reference = _campaign_cases()
    report = build_typing_execution_handoff_candidate_campaign_v1(
        cases, campaign_id="e2-execution-handoff-candidate-001",
        environment=environment, reference_candidate_sha256=reference)
    parse_typing_execution_handoff_candidate_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").write(json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    print(json.dumps({"output": output.relative_to(WORKSPACE).as_posix(),
                      "campaign_sha256": report["campaign_sha256"],
                      "outcomes": [(item["case"], item["observed"]) for item in cases],
                      "eligible_for_executor": False,
                      "physical_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
