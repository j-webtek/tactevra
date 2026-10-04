from __future__ import annotations

from dataclasses import replace

import pytest

from rocell.application.context import (
    SimulationContextError,
    issue_simulation_context_validation_lease_v1,
    revalidate_simulation_context,
    simulation_context_epoch_sha256,
    validate_simulation_context_lease_v1,
)
from rocell.application.model_motion_registry_v2 import (
    ingest_with_trusted_registry_v2,
)

import test_model_motion_ingress_v2 as fixture


SERVICE = "planner-service-e1-fixture"
GENERATION = 7


def _context_and_lease():
    context = fixture.load_simulation_context(fixture.WORKSPACE, fixture.MANIFEST)
    lease = issue_simulation_context_validation_lease_v1(
        context, service_instance_id=SERVICE, generation=GENERATION,
        issued_monotonic_ns=123,
    )
    return context, lease


def _warm_ingress(context, lease):
    plan = fixture._plan()
    return ingest_with_trusted_registry_v2(
        fixture._batch(context, plan=plan), plan, context,
        registry=fixture._registry(context),
        current_time_epoch_ms=fixture.T0 + 3_000,
        current_monotonic_ns=9_000_000_000,
        context_validation_lease=lease,
        active_context_epoch_sha256=lease.context_epoch_sha256,
        active_service_instance_id=SERVICE,
        active_context_generation=GENERATION,
    )


def test_warm_lease_matches_full_cold_admission_exactly():
    context, lease = _context_and_lease()
    plan = fixture._plan()
    batch = fixture._batch(context, plan=plan)
    registry = fixture._registry(context)
    cold = ingest_with_trusted_registry_v2(
        batch, plan, context, registry=registry,
        current_time_epoch_ms=fixture.T0 + 3_000,
        current_monotonic_ns=9_000_000_000,
    )
    warm = ingest_with_trusted_registry_v2(
        batch, plan, context, registry=registry,
        current_time_epoch_ms=fixture.T0 + 3_000,
        current_monotonic_ns=9_000_000_000,
        context_validation_lease=lease,
        active_context_epoch_sha256=lease.context_epoch_sha256,
        active_service_instance_id=SERVICE,
        active_context_generation=GENERATION,
    )
    assert warm == cold
    assert warm["ingress_sha256"] == cold["ingress_sha256"]
    assert lease.hardware_access is lease.physical_authority is False


@pytest.mark.parametrize("change,match", (
    ("epoch", "epoch changed"),
    ("service", "service restart"),
    ("generation", "generation was invalidated"),
    ("context", "different object"),
))
def test_epoch_restart_generation_and_context_changes_fail_closed(change: str, match: str):
    context, lease = _context_and_lease()
    active_epoch = lease.context_epoch_sha256
    service = SERVICE
    generation = GENERATION
    selected_context = context
    if change == "epoch":
        active_epoch = "f" * 64
    elif change == "service":
        service = "restarted-planner-service"
    elif change == "generation":
        generation += 1
    else:
        selected_context = replace(context)
    with pytest.raises(SimulationContextError, match=match):
        validate_simulation_context_lease_v1(
            selected_context, lease,
            active_context_epoch_sha256=active_epoch,
            active_service_instance_id=service,
            active_generation=generation,
        )


def test_lease_mutation_and_partial_warm_arguments_fail_closed():
    context, lease = _context_and_lease()
    forged = replace(lease, generation=GENERATION + 1)
    with pytest.raises(SimulationContextError, match="hash differs"):
        validate_simulation_context_lease_v1(
            context, forged,
            active_context_epoch_sha256=forged.context_epoch_sha256,
            active_service_instance_id=SERVICE,
            active_generation=GENERATION + 1,
        )
    with pytest.raises(SimulationContextError, match="requires epoch"):
        revalidate_simulation_context(context, lease=lease)
    with pytest.raises(SimulationContextError, match="without a validation lease"):
        revalidate_simulation_context(
            context, active_context_epoch_sha256=lease.context_epoch_sha256,
        )


def test_epoch_is_content_bound_and_warm_admission_remains_zero_authority():
    context, lease = _context_and_lease()
    assert simulation_context_epoch_sha256(context) == lease.context_epoch_sha256
    ingress = _warm_ingress(context, lease)
    assert ingress["controller_commands"] == []
    assert ingress["hardware_access"] is ingress["physical_authority"] is False
