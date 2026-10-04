from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/tests/integration"))
import test_typing_shadow_pipeline_v1 as fixture  # noqa: E402

from rocell.application.typing_ik_reuse_profile_gate_v1 import QUALIFIED_EVIDENCE_SHA256  # noqa: E402
from rocell.application.typing_profiled_shadow_service_v1 import TypingProfiledShadowServiceV1  # noqa: E402

VALIDATOR = Draft202012Validator(json.loads((ROOT / "software/ai/schemas/typing_profiled_shadow_service_snapshot_v1.schema.json").read_text()))


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
        evidence_sha256=evidence or QUALIFIED_EVIDENCE_SHA256,
    )


def _execute(service, request_id=None):
    inputs = fixture._inputs(("H", "I"), "hi", context=service.context)
    payload_id = json.loads(inputs["payload"])["request_id"]
    request_id = payload_id if request_id is None else request_id
    if request_id != payload_id:
        document = json.loads(inputs["payload"])
        document["request_id"] = request_id
        inputs["payload"] = json.dumps(
            document, sort_keys=True, separators=(",", ":")
        ).encode()
    service.submit(request_id, inputs)
    return service.execute_next()


def test_qualified_composition_uses_existing_exact_cache_only_in_shadow():
    service = _service("profiled-qualified")
    assert _execute(service)["status"] == "SHADOW_COMPLETED"
    snapshot = service.snapshot()
    VALIDATOR.validate(snapshot)
    assert snapshot["profile_decision"] == "EXACT_INPUT_REUSE_SHADOW_ELIGIBLE"
    assert snapshot["exact_reuse_enabled"] is True
    assert snapshot["cache_counters"]["lookups"] > 0
    assert snapshot["cache_counters"]["stores"] > 0
    assert snapshot["physical_authority"] is False


def test_calibration_or_evidence_mismatch_runs_complete_solver_without_cache():
    for service in (
        _service("profiled-calibration-fallback", active_calibration="f" * 64),
        _service("profiled-evidence-fallback", evidence={**QUALIFIED_EVIDENCE_SHA256, "typing_shadow_service_reuse_campaign_v1": "f" * 64}),
    ):
        assert _execute(service)["status"] == "SHADOW_COMPLETED"
        snapshot = service.snapshot()
        VALIDATOR.validate(snapshot)
        assert snapshot["profile_decision"] == "FULL_SOLVE_ONLY"
        assert snapshot["exact_reuse_enabled"] is False
        assert snapshot["cache_counters"] == {"lookups": 0, "hits": 0, "misses": 0, "stores": 0, "capacity_skips": 0}


def test_reload_and_restart_retire_eligibility_without_retry_or_cache_use():
    for transition in ("reload", "restart"):
        service = _service(f"profiled-{transition}")
        if transition == "reload":
            service.reload_sources(issued_monotonic_ns=200)
        else:
            service.restart(service_instance_id="profiled-restarted", issued_monotonic_ns=200)
        assert service.exact_reuse_enabled is False
        assert _execute(service)["status"] == "SHADOW_COMPLETED"
        snapshot = service.snapshot()
        assert snapshot["profile_decision"] == "FULL_SOLVE_ONLY"
        assert snapshot["cache_counters"]["lookups"] == 0
        assert snapshot["automatic_retry_allowed"] is False
