from __future__ import annotations

from threading import Event, Thread

import pytest

import rocell.application.context_lifecycle_v1 as lifecycle_module
from rocell.application.context import SimulationContextError
from rocell.application.context_lifecycle_v1 import SimulationContextLifecycleV1
from rocell.application.model_motion_ingress_v2 import ModelMotionIngressV2Error
from rocell.application.model_motion_registry_v2 import ingest_with_trusted_registry_v2

import test_model_motion_ingress_v2 as fixture


SERVICE = "planner-service-e1-lifecycle"


def _start(service: str = SERVICE) -> SimulationContextLifecycleV1:
    return SimulationContextLifecycleV1.start(
        fixture.WORKSPACE,
        fixture.MANIFEST,
        service_instance_id=service,
        issued_monotonic_ns=100,
    )


def _ingest(context, *, context_lifecycle=None, **extra):
    plan = fixture._plan()
    return ingest_with_trusted_registry_v2(
        fixture._batch(context, plan=plan),
        plan,
        context,
        registry=fixture._registry(context),
        current_time_epoch_ms=fixture.T0 + 3_000,
        current_monotonic_ns=9_000_000_000,
        context_lifecycle=context_lifecycle,
        **extra,
    )


def test_lifecycle_managed_ingress_matches_full_validation_exactly():
    lifecycle = _start()
    binding = lifecycle.binding()
    full = _ingest(binding.context)
    managed = _ingest(binding.context, context_lifecycle=lifecycle)
    assert managed == full
    assert managed["ingress_sha256"] == full["ingress_sha256"]
    assert binding.generation == 0
    assert binding.hardware_access is binding.physical_authority is False


def test_reload_atomically_advances_generation_and_rejects_old_context():
    lifecycle = _start()
    old = lifecycle.binding()
    current = lifecycle.reload_sources(issued_monotonic_ns=200)
    assert current.generation == old.generation + 1
    assert current.context is not old.context
    assert current.context_epoch_sha256 == old.context_epoch_sha256
    with pytest.raises(SimulationContextError, match="not the lifecycle's active"):
        _ingest(old.context, context_lifecycle=lifecycle)
    assert _ingest(current.context, context_lifecycle=lifecycle)["physical_authority"] is False


def test_failed_reload_preserves_previous_active_generation(monkeypatch):
    lifecycle = _start()
    before = lifecycle.binding()

    def fail_load(*_args, **_kwargs):
        raise SimulationContextError("synthetic source failure")

    monkeypatch.setattr(lifecycle_module, "load_simulation_context", fail_load)
    with pytest.raises(SimulationContextError, match="synthetic source failure"):
        lifecycle.reload_sources(issued_monotonic_ns=200)
    after = lifecycle.binding()
    assert after == before


def test_invalidation_and_restart_revoke_old_service_state():
    lifecycle = _start()
    old = lifecycle.binding()
    restarted = lifecycle.restart(
        service_instance_id="planner-service-e1-restarted",
        issued_monotonic_ns=300,
    )
    with pytest.raises(SimulationContextError, match="invalidated"):
        lifecycle.binding()
    current = restarted.binding()
    assert current.service_instance_id != old.service_instance_id
    assert current.context is not old.context
    assert _ingest(current.context, context_lifecycle=restarted)["hardware_access"] is False
    assert restarted.invalidate() == 1
    assert restarted.invalidate() == 1
    with pytest.raises(SimulationContextError, match="invalidated"):
        restarted.binding()


def test_lifecycle_lock_prevents_invalidation_during_admission_scope():
    lifecycle = _start()
    context = lifecycle.binding().context
    scope_entered = Event()
    release_scope = Event()
    invalidated = Event()

    def hold_scope():
        with lifecycle.validation_scope(context):
            scope_entered.set()
            assert release_scope.wait(2)

    def invalidate():
        lifecycle.invalidate()
        invalidated.set()

    holder = Thread(target=hold_scope)
    holder.start()
    assert scope_entered.wait(2)
    invalidator = Thread(target=invalidate)
    invalidator.start()
    assert not invalidated.wait(0.05)
    release_scope.set()
    holder.join(2)
    invalidator.join(2)
    assert invalidated.is_set()
    assert not holder.is_alive() and not invalidator.is_alive()


def test_lifecycle_rejects_manual_identity_and_wrong_type():
    lifecycle = _start()
    binding = lifecycle.binding()
    with pytest.raises(ModelMotionIngressV2Error, match="manual lease identity"):
        _ingest(
            binding.context,
            context_lifecycle=lifecycle,
            context_validation_lease=binding.lease,
        )
    with pytest.raises(TypeError, match="context_lifecycle"):
        _ingest(binding.context, context_lifecycle=object())
