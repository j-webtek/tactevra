"""Retain the frozen exact-input IK reuse-profile qualification matrix."""

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
from rocell.application.context import SimulationContextError  # noqa: E402
from rocell.application.context_lifecycle_v1 import SimulationContextLifecycleV1  # noqa: E402
from rocell.application.operational_latency_reference_v1 import capture_operational_benchmark_environment_v1  # noqa: E402
from rocell.application.typing_ik_reuse_profile_campaign_v1 import build_typing_ik_reuse_profile_campaign_v1, parse_typing_ik_reuse_profile_campaign_v1  # noqa: E402
from rocell.application.typing_ik_reuse_profile_gate_v1 import QUALIFIED_EVIDENCE_SHA256, FrozenTypingIkReuseProfileV1, TypingIkReuseProfileGateV1Error, evaluate_typing_ik_reuse_profile_v1  # noqa: E402

DEFAULT_OUTPUT = Path("software/ai/eval/typing_ik_reuse_profile_campaign_v1.json")


def _resources(service):
    lifecycle = SimulationContextLifecycleV1.start(
        fixture.ingress_fixture.WORKSPACE, fixture.ingress_fixture.MANIFEST,
        service_instance_id=service, issued_monotonic_ns=100,
    )
    context = lifecycle.binding().context
    calibration = fixture.ik_fixture._snapshot(context).snapshot_sha256
    profile = FrozenTypingIkReuseProfileV1.from_active_context(
        context, lifecycle, calibration_snapshot_sha256=calibration,
    )
    return lifecycle, context, calibration, profile


def _run_cases():
    lifecycle, context, calibration, profile = _resources("reuse-profile-campaign")
    common = dict(calibration_snapshot_sha256=calibration,
                  evidence_sha256=QUALIFIED_EVIDENCE_SHA256)
    exact = evaluate_typing_ik_reuse_profile_v1(profile, context, lifecycle, **common)
    bad_evidence = evaluate_typing_ik_reuse_profile_v1(
        profile, context, lifecycle, calibration_snapshot_sha256=calibration,
        evidence_sha256={**QUALIFIED_EVIDENCE_SHA256,
                         "typing_shadow_service_reuse_campaign_v1": "f" * 64})
    bad_calibration = evaluate_typing_ik_reuse_profile_v1(
        profile, context, lifecycle, calibration_snapshot_sha256="f" * 64,
        evidence_sha256=QUALIFIED_EVIDENCE_SHA256)
    cases = [
        {"case": "EXACT_PROFILE_ELIGIBLE", "status": "PASS", "disposition": exact["decision"], "detail": "all frozen identities and evidence match"},
        {"case": "EVIDENCE_MISMATCH_FALLBACK", "status": "PASS", "disposition": bad_evidence["decision"], "detail": bad_evidence["blockers"][0]},
        {"case": "CALIBRATION_MISMATCH_FALLBACK", "status": "PASS", "disposition": bad_calibration["decision"], "detail": bad_calibration["blockers"][0]},
    ]
    try:
        evaluate_typing_ik_reuse_profile_v1(profile, context, lifecycle,
            **common, automatic_retry_allowed=True)
    except TypingIkReuseProfileGateV1Error as exc:
        cases.append({"case": "UNSAFE_SETTINGS_REJECTED", "status": "PASS", "disposition": "REJECTED", "detail": str(exc)})
    lifecycle.reload_sources(issued_monotonic_ns=200)
    try:
        evaluate_typing_ik_reuse_profile_v1(profile, context, lifecycle, **common)
    except SimulationContextError as exc:
        cases.append({"case": "RELOAD_STALE_REJECTED", "status": "PASS", "disposition": "REJECTED", "detail": str(exc)})
    old, old_context, old_calibration, old_profile = _resources("reuse-profile-restart-old")
    old.restart(service_instance_id="reuse-profile-restart-new", issued_monotonic_ns=300)
    try:
        evaluate_typing_ik_reuse_profile_v1(old_profile, old_context, old,
            calibration_snapshot_sha256=old_calibration,
            evidence_sha256=QUALIFIED_EVIDENCE_SHA256)
    except SimulationContextError as exc:
        cases.append({"case": "RESTART_STALE_REJECTED", "status": "PASS", "disposition": "REJECTED", "detail": str(exc)})
    return cases, profile.profile_sha256


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
        benchmark_entrypoint="software/scripts/run_typing_ik_reuse_profile_campaign_v1.py")
    if environment["repository_dirty"]: parser.error("campaign must run from a clean source commit")
    cases, profile_sha256 = _run_cases()
    report = build_typing_ik_reuse_profile_campaign_v1(
        cases, campaign_id="e2-ik-reuse-profile-001", environment=environment,
        qualified_profile_sha256=profile_sha256)
    parse_typing_ik_reuse_profile_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").write(json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    print(json.dumps({"output": output.relative_to(WORKSPACE).as_posix(), "campaign_sha256": report["campaign_sha256"], "cases": report["case_count"], "physical_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
