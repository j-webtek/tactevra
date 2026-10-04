"""Retain actual-emitter evidence for immutable shadow-artifact storage."""

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
from rocell.application.typing_shadow_artifact_store_campaign_v1 import build_typing_shadow_artifact_store_campaign_v1, parse_typing_shadow_artifact_store_campaign_v1  # noqa: E402
from rocell.application.typing_shadow_artifact_store_v1 import TypingShadowArtifactStoreV1, TypingShadowArtifactStoreV1Error  # noqa: E402
from run_typing_command_session_ledger_campaign_v1 import _inputs, _ledger  # noqa: E402

DEFAULT_OUTPUT = Path(
    "software/ai/eval/typing_shadow_artifact_store_campaign_v1.json"
)


def _case(name, observed, snapshot, artifact=None, error=None):
    return {
        "case": name, "observed": observed, "artifact": artifact,
        "error": error, "store_snapshot": snapshot,
        "zero_authority_validated": True,
    }


def _campaign_cases():
    ledger, supervisor = _ledger()
    ledger.submit("mission-runtime", "runtime", _inputs(ledger, "runtime"))
    terminal = ledger.run_next_shadow()
    artifact = ledger.shadow_artifact("runtime")
    reference = terminal["shadow_receipt_sha256"]
    cases = [_case(
        "RUNTIME_RETENTION", "ARTIFACT_RETAINED",
        ledger.artifact_store_snapshot(), artifact=artifact,
    )]
    repeat = ledger.shadow_artifact("runtime")
    cases.append(_case(
        "REPEAT_RETRIEVAL", "IDENTICAL_ARTIFACT_RETRIEVED",
        ledger.artifact_store_snapshot(), artifact=repeat,
    ))

    store = TypingShadowArtifactStoreV1(maximum_entries=1)
    store.put("runtime", artifact)
    try:
        store.get("runtime", "f" * 64)
    except TypingShadowArtifactStoreV1Error as exc:
        cases.append(_case(
            "WRONG_HASH_REJECTED", "CONTENT_ADDRESS_REJECTED",
            store.snapshot(), error=str(exc),
        ))
    else:
        raise RuntimeError("wrong artifact hash was accepted")

    try:
        store.get("unknown", reference)
    except TypingShadowArtifactStoreV1Error as exc:
        cases.append(_case(
            "UNKNOWN_REQUEST_REJECTED", "UNKNOWN_REQUEST_REJECTED",
            store.snapshot(), error=str(exc),
        ))
    else:
        raise RuntimeError("unknown artifact request was accepted")

    changed = copy.deepcopy(artifact)
    changed["request_id"] = "changed"
    try:
        store.put("runtime", changed)
    except TypingShadowArtifactStoreV1Error as exc:
        cases.append(_case(
            "REPLACEMENT_REJECTED", "REPLACEMENT_REJECTED",
            store.snapshot(), error=str(exc),
        ))
    else:
        raise RuntimeError("artifact replacement was accepted")

    other_ledger, other_supervisor = _ledger()
    other_ledger.submit("mission-other", "other", _inputs(other_ledger, "other"))
    other_ledger.run_next_shadow()
    other_artifact = other_ledger.shadow_artifact("other")
    try:
        store.put("other", other_artifact)
    except TypingShadowArtifactStoreV1Error as exc:
        cases.append(_case(
            "CAPACITY_EXHAUSTION", "CAPACITY_REJECTED",
            store.snapshot(), error=str(exc),
        ))
    else:
        raise RuntimeError("artifact capacity bound was bypassed")

    canceled_ledger, canceled_supervisor = _ledger()
    canceled_ledger.submit(
        "mission-canceled", "canceled", _inputs(canceled_ledger, "canceled")
    )
    canceled_ledger.cancel("canceled")
    try:
        canceled_ledger.shadow_artifact("canceled")
    except TypingCommandSessionLedgerV1Error as exc:
        cases.append(_case(
            "CANCELED_HAS_NO_ARTIFACT", "NO_ARTIFACT_RETAINED",
            canceled_ledger.artifact_store_snapshot(), error=str(exc),
        ))
    else:
        raise RuntimeError("canceled request retained an artifact")

    stale_ledger, stale_supervisor = _ledger()
    stale_ledger.submit("mission-stale", "stale", _inputs(stale_ledger, "stale"))
    stale_supervisor.reload_sources(issued_monotonic_ns=200)
    stale_ledger.run_next_shadow()
    try:
        stale_ledger.shadow_artifact("stale")
    except TypingCommandSessionLedgerV1Error as exc:
        cases.append(_case(
            "STALE_HAS_NO_ARTIFACT", "NO_ARTIFACT_RETAINED",
            stale_ledger.artifact_store_snapshot(), error=str(exc),
        ))
    else:
        raise RuntimeError("stale request retained an artifact")

    for owner in (supervisor, other_supervisor, canceled_supervisor,
                  stale_supervisor):
        owner.invalidate()
    return cases, reference


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
            "software/scripts/run_typing_shadow_artifact_store_campaign_v1.py"
        ),
    )
    if environment["repository_dirty"]:
        parser.error("campaign must run from a clean source commit")
    cases, reference = _campaign_cases()
    report = build_typing_shadow_artifact_store_campaign_v1(
        cases, campaign_id="e2-shadow-artifact-store-001",
        environment=environment, reference_artifact_sha256=reference,
    )
    parse_typing_shadow_artifact_store_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").write(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )
    print(json.dumps({
        "output": output.relative_to(WORKSPACE).as_posix(),
        "campaign_sha256": report["campaign_sha256"],
        "outcomes": [(item["case"], item["observed"]) for item in cases],
        "physical_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
