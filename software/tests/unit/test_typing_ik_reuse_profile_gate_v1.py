from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/tests/integration"))
import test_typing_shadow_pipeline_v1 as fixture  # noqa: E402

from rocell.application.context import SimulationContextError  # noqa: E402
from rocell.application.context_lifecycle_v1 import SimulationContextLifecycleV1  # noqa: E402
from rocell.application.typing_ik_reuse_profile_gate_v1 import (  # noqa: E402
    ELIGIBLE, FULL_SOLVE_ONLY, QUALIFIED_EVIDENCE_SHA256,
    FrozenTypingIkReuseProfileV1, TypingIkReuseProfileGateV1Error,
    evaluate_typing_ik_reuse_profile_v1,
)

VALIDATOR = Draft202012Validator(json.loads((ROOT / "software/ai/schemas/typing_ik_reuse_profile_decision_v1.schema.json").read_text()))


def _resources(service="reuse-profile-test"):
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


def _evaluate(lifecycle, context, calibration, profile, **changes):
    arguments = dict(calibration_snapshot_sha256=calibration,
                     evidence_sha256=QUALIFIED_EVIDENCE_SHA256)
    arguments.update(changes)
    return evaluate_typing_ik_reuse_profile_v1(profile, context, lifecycle, **arguments)


def test_exact_frozen_profile_is_shadow_eligible_and_zero_authority():
    lifecycle, context, calibration, profile = _resources()
    decision = _evaluate(lifecycle, context, calibration, profile)
    VALIDATOR.validate(decision)
    assert decision["decision"] == ELIGIBLE
    assert decision["blockers"] == []
    assert decision["candidate_used_for_admission"] is False
    assert decision["controller_commands"] == []
    assert decision["hardware_writes"] == decision["physical_movements"] == 0
    assert decision["physical_authority"] is False


@pytest.mark.parametrize("change, blocker", [
    ({"evidence_sha256": {**QUALIFIED_EVIDENCE_SHA256, "typing_shadow_service_reuse_campaign_v1": "f" * 64}}, "QUALIFIED_EVIDENCE_MISMATCH"),
    ({"calibration_snapshot_sha256": "f" * 64}, "CALIBRATION_SNAPSHOT_SHA256_MISMATCH"),
])
def test_unqualified_identity_falls_back_to_complete_solve(change, blocker):
    lifecycle, context, calibration, profile = _resources()
    decision = _evaluate(lifecycle, context, calibration, profile, **change)
    VALIDATOR.validate(decision)
    assert decision["decision"] == FULL_SOLVE_ONLY
    assert blocker in decision["blockers"]


def test_profile_identity_mismatch_falls_back_without_authority():
    lifecycle, context, calibration, profile = _resources()
    changed = replace(profile, build_snapshot_sha256="f" * 64)
    decision = _evaluate(lifecycle, context, calibration, changed)
    assert decision["decision"] == FULL_SOLVE_ONLY
    assert decision["blockers"] == ["BUILD_SNAPSHOT_SHA256_MISMATCH"]
    assert decision["physical_authority"] is False


@pytest.mark.parametrize("changes, match", [
    ({"requested_maximum_entries": 257}, "capacity"),
    ({"complete_solve_fallback_required": False}, "fallback"),
    ({"automatic_retry_allowed": True}, "retry"),
])
def test_unsafe_runtime_settings_are_rejected(changes, match):
    lifecycle, context, calibration, profile = _resources()
    with pytest.raises(TypingIkReuseProfileGateV1Error, match=match):
        _evaluate(lifecycle, context, calibration, profile, **changes)


def test_reload_restart_and_crossed_context_reject_stale_profile():
    lifecycle, context, calibration, profile = _resources("reuse-profile-stale")
    lifecycle.reload_sources(issued_monotonic_ns=200)
    with pytest.raises(SimulationContextError):
        _evaluate(lifecycle, context, calibration, profile)

    old, old_context, old_calibration, old_profile = _resources("reuse-profile-old")
    replacement = old.restart(service_instance_id="reuse-profile-new", issued_monotonic_ns=300)
    with pytest.raises(SimulationContextError):
        _evaluate(old, old_context, old_calibration, old_profile)
    with pytest.raises(SimulationContextError):
        _evaluate(replacement, old_context, old_calibration, old_profile)
