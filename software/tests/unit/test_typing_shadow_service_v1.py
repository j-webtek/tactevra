from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from threading import Event, Thread

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/tests/integration"))

import test_model_motion_ingress_v2 as ingress_fixture  # noqa: E402
import test_typing_shadow_pipeline_v1 as shadow_fixture  # noqa: E402
from rocell.application.typing_exact_ik_cache_owner_v1 import (  # noqa: E402
    TypingExactIkCacheOwnerV1,
)
from rocell.application.typing_shadow_service_v1 import (  # noqa: E402
    TypingShadowServiceV1,
    TypingShadowServiceV1Error,
    parse_typing_shadow_service_receipt_v1,
    parse_typing_shadow_service_snapshot_v1,
)


def _owner(service: str = "typing-shadow-service-test") -> TypingExactIkCacheOwnerV1:
    return TypingExactIkCacheOwnerV1.start(
        ingress_fixture.WORKSPACE,
        ingress_fixture.MANIFEST,
        service_instance_id=service,
        issued_monotonic_ns=100,
        maximum_entries=256,
    )


def _request_id(inputs: dict) -> str:
    return json.loads(inputs["payload"])["request_id"]


def _with_request_id(inputs: dict, request_id: str) -> dict:
    changed = dict(inputs)
    payload = json.loads(changed["payload"])
    payload["request_id"] = request_id
    changed["payload"] = json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return changed


def _rehash_receipt(receipt: dict) -> None:
    import rocell.application.typing_shadow_service_v1 as service_module

    core = {
        key: value for key, value in receipt.items()
        if key != "service_receipt_sha256"
    }
    receipt["service_receipt_sha256"] = service_module._sha(core)


def _rehash_snapshot(snapshot: dict) -> None:
    import rocell.application.typing_shadow_service_v1 as service_module

    core = {
        key: value for key, value in snapshot.items()
        if key != "service_snapshot_sha256"
    }
    snapshot["service_snapshot_sha256"] = service_module._sha(core)


def test_service_completes_one_generation_bound_shadow_request():
    owner = _owner()
    service = TypingShadowServiceV1(owner, maximum_queued=2)
    inputs = shadow_fixture._inputs(context=service.context)
    request_id = _request_id(inputs)

    request_sha256 = service.submit(request_id, inputs)
    receipt = service.execute_next()
    snapshot = service.snapshot()

    assert receipt["status"] == "SHADOW_COMPLETED"
    assert receipt["request_sha256"] == request_sha256
    assert dict(parse_typing_shadow_service_receipt_v1(receipt)) == receipt
    assert snapshot["submitted"] == snapshot["completed"] == 1
    assert snapshot["queued"] == 0
    assert owner.snapshot()["runs"] == 1
    assert dict(parse_typing_shadow_service_snapshot_v1(snapshot)) == snapshot
    assert receipt["controller_commands"] == []
    assert receipt["hardware_access"] is receipt["physical_authority"] is False


def test_cancellation_is_only_before_admission_and_never_runs_owner():
    owner = _owner("typing-shadow-service-cancel")
    service = TypingShadowServiceV1(owner)
    inputs = shadow_fixture._inputs(context=service.context)
    request_id = _request_id(inputs)
    service.submit(request_id, inputs)

    receipt = service.cancel(request_id)

    assert receipt["status"] == "CANCELED_BEFORE_ADMISSION"
    assert dict(parse_typing_shadow_service_receipt_v1(receipt)) == receipt
    assert owner.snapshot()["runs"] == 0
    with pytest.raises(TypingShadowServiceV1Error, match="not queued"):
        service.cancel(request_id)
    with pytest.raises(TypingShadowServiceV1Error, match="cannot be reused"):
        service.submit(request_id, inputs)


def test_cancellation_after_reload_remains_a_valid_zero_run_terminal_receipt():
    owner = _owner("typing-shadow-service-cancel-after-reload")
    service = TypingShadowServiceV1(owner)
    inputs = shadow_fixture._inputs(context=service.context)
    request_id = _request_id(inputs)
    service.submit(request_id, inputs)
    service.reload_sources(issued_monotonic_ns=200)

    receipt = service.cancel(request_id)

    assert receipt["status"] == "CANCELED_BEFORE_ADMISSION"
    assert (
        receipt["submitted_context_epoch_sha256"],
        receipt["submitted_service_instance_id"],
        receipt["submitted_generation"],
    ) != (
        receipt["active_context_epoch_sha256"],
        receipt["active_service_instance_id"],
        receipt["active_generation"],
    )
    assert dict(parse_typing_shadow_service_receipt_v1(receipt)) == receipt
    assert owner.snapshot()["runs"] == 0


@pytest.mark.parametrize("transition", ("reload", "restart"))
def test_queued_request_is_rejected_after_generation_transition(transition: str):
    owner = _owner(f"typing-shadow-service-stale-{transition}")
    service = TypingShadowServiceV1(owner)
    inputs = shadow_fixture._inputs(context=service.context)
    request_id = _request_id(inputs)
    service.submit(request_id, inputs)

    if transition == "reload":
        service.reload_sources(issued_monotonic_ns=200)
    else:
        service.restart(
            service_instance_id="typing-shadow-service-restarted",
            issued_monotonic_ns=200,
        )
    receipt = service.execute_next()

    assert receipt["status"] == "STALE_GENERATION_REJECTED"
    assert (
        receipt["submitted_context_epoch_sha256"],
        receipt["submitted_service_instance_id"],
        receipt["submitted_generation"],
    ) != (
        receipt["active_context_epoch_sha256"],
        receipt["active_service_instance_id"],
        receipt["active_generation"],
    )
    assert dict(parse_typing_shadow_service_receipt_v1(receipt)) == receipt
    assert owner.snapshot()["runs"] == 0


def test_queue_and_lifetime_bounds_fail_closed_without_reordering():
    owner = _owner("typing-shadow-service-bounds")
    service = TypingShadowServiceV1(
        owner, maximum_queued=1, maximum_requests=2
    )
    first = shadow_fixture._inputs(context=service.context)
    first_id = _request_id(first)
    second_id = "second-shadow-request"
    second = _with_request_id(first, second_id)
    service.submit(first_id, first)
    with pytest.raises(TypingShadowServiceV1Error, match="queue is full"):
        service.submit(second_id, second)
    assert service.execute_next()["request_id"] == first_id
    service.submit(second_id, second)
    assert service.cancel(second_id)["request_id"] == second_id
    with pytest.raises(TypingShadowServiceV1Error, match="bound is exhausted"):
        service.submit("third-shadow-request", _with_request_id(first, "third-shadow-request"))


def test_invalidation_accounts_for_every_queued_request_without_execution():
    owner = _owner("typing-shadow-service-invalidate")
    service = TypingShadowServiceV1(owner)
    inputs = shadow_fixture._inputs(context=service.context)
    service.submit(_request_id(inputs), inputs)

    service.invalidate()
    snapshot = service.snapshot()

    assert snapshot["active"] is False
    assert snapshot["queued"] == 0
    assert snapshot["invalidated_queued"] == 1
    assert snapshot["invalidations"] == 1
    assert owner.snapshot()["runs"] == 0
    assert dict(parse_typing_shadow_service_snapshot_v1(snapshot)) == snapshot
    with pytest.raises(TypingShadowServiceV1Error, match="invalidated"):
        service.execute_next()


def test_unexpected_shadow_failure_is_accounted_and_never_retried(monkeypatch):
    owner = _owner("typing-shadow-service-unexpected-failure")
    service = TypingShadowServiceV1(owner)
    inputs = shadow_fixture._inputs(context=service.context)
    service.submit(_request_id(inputs), inputs)

    def fail(**_pipeline_inputs):
        raise RuntimeError("forced unexpected failure")

    monkeypatch.setattr(owner, "run_shadow_pipeline", fail)
    receipt = service.execute_next()
    snapshot = service.snapshot()

    assert receipt["status"] == "SHADOW_REJECTED"
    assert receipt["automatic_retry_allowed"] is False
    assert snapshot["shadow_rejected"] == 1
    assert snapshot["queued"] == 0
    assert dict(parse_typing_shadow_service_receipt_v1(receipt)) == receipt
    assert dict(parse_typing_shadow_service_snapshot_v1(snapshot)) == snapshot


def test_reload_waits_for_admitted_request_and_cannot_split_generation(monkeypatch):
    owner = _owner("typing-shadow-service-race")
    service = TypingShadowServiceV1(owner)
    inputs = shadow_fixture._inputs(context=service.context)
    service.submit(_request_id(inputs), inputs)
    entered = Event()
    release = Event()
    reload_done = Event()
    receipts: list[dict] = []
    errors: list[BaseException] = []
    original = owner.run_shadow_pipeline

    def paused_run(**pipeline_inputs):
        entered.set()
        if not release.wait(5):
            raise AssertionError("test did not release admitted request")
        return original(**pipeline_inputs)

    monkeypatch.setattr(owner, "run_shadow_pipeline", paused_run)

    def execute() -> None:
        try:
            receipts.append(service.execute_next())
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            errors.append(exc)

    def reload_sources() -> None:
        try:
            service.reload_sources(issued_monotonic_ns=200)
            reload_done.set()
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            errors.append(exc)

    execution_thread = Thread(target=execute)
    execution_thread.start()
    assert entered.wait(5)
    reload_thread = Thread(target=reload_sources)
    reload_thread.start()
    assert reload_done.wait(0.05) is False
    release.set()
    execution_thread.join(5)
    reload_thread.join(5)

    assert not errors
    assert not execution_thread.is_alive() and not reload_thread.is_alive()
    assert receipts[0]["status"] == "SHADOW_COMPLETED"
    assert reload_done.is_set()
    snapshot = service.snapshot()
    assert snapshot["completed"] == 1
    assert snapshot["reloads"] == 1


@pytest.mark.parametrize("mutation,match", (
    ("hash", "hash differs"),
    ("lifecycle", "lifecycle differs"),
    ("authority", "zero authority"),
))
def test_receipt_mutations_fail_closed(mutation: str, match: str):
    owner = _owner(f"typing-shadow-service-receipt-{mutation}")
    service = TypingShadowServiceV1(owner)
    inputs = shadow_fixture._inputs(context=service.context)
    service.submit(_request_id(inputs), inputs)
    receipt = copy.deepcopy(service.execute_next())
    if mutation == "hash":
        receipt["service_receipt_sha256"] = "f" * 64
    elif mutation == "lifecycle":
        receipt["active_generation"] += 1
        _rehash_receipt(receipt)
    else:
        receipt["hardware_access"] = True
        _rehash_receipt(receipt)
    with pytest.raises(TypingShadowServiceV1Error, match=match):
        parse_typing_shadow_service_receipt_v1(receipt)


@pytest.mark.parametrize("mutation,match", (
    ("hash", "hash differs"),
    ("counter", "counters differ"),
    ("bound", "counters differ"),
    ("authority", "zero authority"),
))
def test_snapshot_mutations_fail_closed(mutation: str, match: str):
    snapshot = copy.deepcopy(TypingShadowServiceV1(_owner()).snapshot())
    if mutation == "hash":
        snapshot["service_snapshot_sha256"] = "f" * 64
    elif mutation == "counter":
        snapshot["submitted"] += 1
        _rehash_snapshot(snapshot)
    elif mutation == "bound":
        snapshot["maximum_queued"] = 65
        _rehash_snapshot(snapshot)
    else:
        snapshot["executor_attached"] = True
        _rehash_snapshot(snapshot)
    with pytest.raises(TypingShadowServiceV1Error, match=match):
        parse_typing_shadow_service_snapshot_v1(snapshot)
