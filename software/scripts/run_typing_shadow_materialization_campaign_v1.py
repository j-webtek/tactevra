"""Retain actual-emitter evidence for five-stage shadow materialization."""

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
from rocell.application.typing_command_session_ledger_v1 import TypingCommandSessionLedgerV1Error  # noqa: E402
from rocell.application.typing_shadow_materialization_campaign_v1 import build_typing_shadow_materialization_campaign_v1, parse_typing_shadow_materialization_campaign_v1  # noqa: E402
from rocell.application.typing_shadow_materialization_v1 import TypingShadowMaterializationV1Error, parse_typing_shadow_materialization_v1  # noqa: E402
try:  # Support direct execution and package import.
    from software.scripts.run_typing_command_session_ledger_campaign_v1 import _inputs, _ledger  # noqa: E402
except ModuleNotFoundError:
    from run_typing_command_session_ledger_campaign_v1 import _inputs, _ledger  # noqa: E402

DEFAULT_OUTPUT = Path(
    "software/ai/eval/typing_shadow_materialization_campaign_v1.json"
)


def _record(name, observed, ledger, materialization=None, error=None):
    return {
        "case": name, "observed": observed,
        "materialization": materialization, "error": error,
        "ledger_snapshot": ledger.snapshot(),
        "zero_authority_validated": True,
    }


def _unavailable(name, ledger, request_id):
    try:
        ledger.shadow_materialization(request_id)
    except TypingCommandSessionLedgerV1Error as exc:
        return _record(
            name, "NO_MATERIALIZATION_RETAINED", ledger, error=str(exc)
        )
    raise RuntimeError(f"{name} unexpectedly retained materialization")


def _campaign_cases():
    ledger, supervisor = _ledger()
    ledger.submit("mission-material", "material", _inputs(ledger, "material"))
    ledger.run_next_shadow()
    bundle = ledger.shadow_materialization("material")
    cases = [_record(
        "COMPLETED_MATERIALIZATION", "FIVE_STAGES_RETAINED", ledger,
        materialization=bundle,
    )]
    repeated = ledger.shadow_materialization("material")
    cases.append(_record(
        "REPEAT_RETRIEVAL", "IDENTICAL_MATERIALIZATION_RETRIEVED", ledger,
        materialization=repeated,
    ))
    supervisor.invalidate()
    audited = ledger.shadow_materialization("material")
    cases.append(_record(
        "POST_INVALIDATION_AUDIT_RETRIEVAL",
        "IDENTICAL_MATERIALIZATION_RETRIEVED", ledger,
        materialization=audited,
    ))

    changed = copy.deepcopy(bundle)
    changed["stage_artifacts"]["typing_joint_schedule"]["hardware_access"] = True
    try:
        parse_typing_shadow_materialization_v1(changed)
    except TypingShadowMaterializationV1Error as exc:
        cases.append(_record(
            "TAMPER_REJECTED", "CONTENT_TAMPER_REJECTED", ledger,
            error=str(exc),
        ))
    else:
        raise RuntimeError("materialization tamper was accepted")

    queued, queued_owner = _ledger()
    queued.submit("mission-queued", "queued", _inputs(queued, "queued"))
    cases.append(_unavailable(
        "QUEUED_HAS_NO_MATERIALIZATION", queued, "queued"
    ))
    canceled, canceled_owner = _ledger()
    canceled.submit(
        "mission-canceled", "canceled", _inputs(canceled, "canceled")
    )
    canceled.cancel("canceled")
    cases.append(_unavailable(
        "CANCELED_HAS_NO_MATERIALIZATION", canceled, "canceled"
    ))
    stale, stale_owner = _ledger()
    stale.submit("mission-stale", "stale", _inputs(stale, "stale"))
    stale_owner.reload_sources(issued_monotonic_ns=200)
    stale.run_next_shadow()
    cases.append(_unavailable(
        "STALE_HAS_NO_MATERIALIZATION", stale, "stale"
    ))
    cases.append(_unavailable(
        "UNKNOWN_HAS_NO_MATERIALIZATION", stale, "unknown"
    ))
    for owner in (queued_owner, canceled_owner, stale_owner):
        owner.invalidate()
    return cases, bundle["materialization_sha256"]


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
            "software/scripts/run_typing_shadow_materialization_campaign_v1.py"
        ),
    )
    if environment["repository_dirty"]:
        parser.error("campaign must run from a clean source commit")
    cases, reference = _campaign_cases()
    report = build_typing_shadow_materialization_campaign_v1(
        cases, campaign_id="e2-shadow-materialization-001",
        environment=environment, reference_materialization_sha256=reference,
    )
    parse_typing_shadow_materialization_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").write(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )
    print(json.dumps({
        "output": output.relative_to(WORKSPACE).as_posix(),
        "campaign_sha256": report["campaign_sha256"],
        "outcomes": [(item["case"], item["observed"]) for item in cases],
        "permit_review_ready": False, "physical_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
