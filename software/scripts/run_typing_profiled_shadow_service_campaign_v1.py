"""Retain the profile-gated shadow-service composition campaign."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

WORKSPACE = Path(__file__).resolve().parents[2]
SOFTWARE = WORKSPACE / "software"
sys.path.insert(0, str(SOFTWARE / "src"))
sys.path.insert(0, str(SOFTWARE / "tests" / "integration"))
import test_typing_shadow_pipeline_v1 as fixture  # noqa: E402
from rocell.application.operational_latency_reference_v1 import capture_operational_benchmark_environment_v1  # noqa: E402
from rocell.application.typing_ik_reuse_profile_gate_v1 import QUALIFIED_EVIDENCE_SHA256  # noqa: E402
from rocell.application.typing_profiled_shadow_service_campaign_v1 import build_typing_profiled_shadow_service_campaign_v1, parse_typing_profiled_shadow_service_campaign_v1  # noqa: E402
from rocell.application.typing_profiled_shadow_service_v1 import TypingProfiledShadowServiceV1  # noqa: E402

DEFAULT_OUTPUT = Path("software/ai/eval/typing_profiled_shadow_service_campaign_v1.json")


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


def _execute(service):
    inputs = fixture._inputs(("H", "I"), "hi", context=service.context)
    request_id = json.loads(inputs["payload"])["request_id"]
    service.submit(request_id, inputs)
    receipt = service.execute_next()
    snapshot = service.snapshot()
    return receipt, snapshot


def _case(name, receipt, snapshot):
    return {"case": name, "status": receipt["status"],
            "profile_decision": snapshot["profile_decision"],
            "exact_reuse_enabled": snapshot["exact_reuse_enabled"],
            "cache_counters": snapshot["cache_counters"]}


def _cases():
    qualified = _service("profiled-campaign-qualified")
    qualified_receipt, qualified_snapshot = _execute(qualified)
    calibration = _service("profiled-campaign-calibration", active_calibration="f" * 64)
    calibration_receipt, calibration_snapshot = _execute(calibration)
    evidence = _service("profiled-campaign-evidence", evidence={**QUALIFIED_EVIDENCE_SHA256, "typing_shadow_service_reuse_campaign_v1": "f" * 64})
    evidence_receipt, evidence_snapshot = _execute(evidence)
    reload_service = _service("profiled-campaign-reload")
    reload_service.reload_sources(issued_monotonic_ns=200)
    reload_receipt, reload_snapshot = _execute(reload_service)
    restart_service = _service("profiled-campaign-restart")
    restart_service.restart(service_instance_id="profiled-campaign-restarted", issued_monotonic_ns=200)
    restart_receipt, restart_snapshot = _execute(restart_service)
    equivalent = len({qualified_receipt["shadow_receipt_sha256"], calibration_receipt["shadow_receipt_sha256"], evidence_receipt["shadow_receipt_sha256"]}) == 1
    return [
        _case("QUALIFIED_CACHE_PATH", qualified_receipt, qualified_snapshot),
        _case("CALIBRATION_FULL_SOLVE_PATH", calibration_receipt, calibration_snapshot),
        _case("EVIDENCE_FULL_SOLVE_PATH", evidence_receipt, evidence_snapshot),
        _case("RELOAD_RETIRES_PROFILE", reload_receipt, reload_snapshot),
        _case("RESTART_RETIRES_PROFILE", restart_receipt, restart_snapshot),
    ], equivalent


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
        benchmark_entrypoint="software/scripts/run_typing_profiled_shadow_service_campaign_v1.py")
    if environment["repository_dirty"]: parser.error("campaign must run from a clean source commit")
    cases, equivalent = _cases()
    report = build_typing_profiled_shadow_service_campaign_v1(
        cases, campaign_id="e2-profiled-shadow-service-001", environment=environment,
        reference_receipts_equivalent=equivalent)
    parse_typing_profiled_shadow_service_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").write(json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    print(json.dumps({"output": output.relative_to(WORKSPACE).as_posix(), "campaign_sha256": report["campaign_sha256"], "cases": report["case_count"], "physical_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
