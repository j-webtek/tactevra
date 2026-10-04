"""Retain a clean-commit fault campaign for the typing shadow service."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from threading import Event, Thread
import time
from unittest.mock import patch


WORKSPACE = Path(__file__).resolve().parents[2]
SOFTWARE = WORKSPACE / "software"
sys.path.insert(0, str(SOFTWARE / "src"))
sys.path.insert(0, str(SOFTWARE / "tests" / "unit"))
sys.path.insert(0, str(SOFTWARE / "tests" / "integration"))

import test_model_motion_ingress_v2 as ingress_fixture  # noqa: E402
import test_typing_shadow_pipeline_v1 as shadow_fixture  # noqa: E402
from rocell.application.operational_latency_reference_v1 import (  # noqa: E402
    capture_operational_benchmark_environment_v1,
)
from rocell.application.typing_exact_ik_cache_owner_v1 import (  # noqa: E402
    TypingExactIkCacheOwnerV1,
)
from rocell.application.typing_shadow_service_campaign_v1 import (  # noqa: E402
    CASES,
    build_typing_shadow_service_campaign_v1,
    parse_typing_shadow_service_campaign_v1,
)
from rocell.application.typing_shadow_service_v1 import (  # noqa: E402
    TypingShadowServiceV1,
    TypingShadowServiceV1Error,
)


DEFAULT_OUTPUT = Path(
    "software/ai/eval/typing_shadow_service_campaign_v1.json"
)
SERVICE = "typing-shadow-service-campaign"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _output_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError("output must be workspace-relative")
    resolved = (WORKSPACE / candidate).resolve()
    if WORKSPACE not in resolved.parents:
        raise ValueError("output escapes workspace")
    return resolved


def _owner(suffix: str, issued: int) -> TypingExactIkCacheOwnerV1:
    return TypingExactIkCacheOwnerV1.start(
        ingress_fixture.WORKSPACE,
        ingress_fixture.MANIFEST,
        service_instance_id=f"{SERVICE}-{suffix}",
        issued_monotonic_ns=issued,
        maximum_entries=256,
    )


def _inputs(service: TypingShadowServiceV1) -> dict:
    return shadow_fixture._inputs(
        ("R", "O", "B", "O", "T"), "robot", context=service.context
    )


def _request_id(inputs: dict) -> str:
    return json.loads(inputs["payload"])["request_id"]


def _with_request_id(inputs: dict, request_id: str) -> dict:
    changed = dict(inputs)
    payload = json.loads(changed["payload"])
    payload["request_id"] = request_id
    changed["payload"] = _canonical(payload)
    return changed


def _case(
    name: str, outcome: str, service: TypingShadowServiceV1,
    owner: TypingExactIkCacheOwnerV1, *, receipt: dict | None = None,
    transition_waited: bool = False,
) -> dict:
    return {
        "case": name,
        "status": "PASS",
        "observed_outcome": outcome,
        "service_receipt": receipt,
        "shadow_receipt_sha256": (
            receipt["shadow_receipt_sha256"]
            if receipt is not None and receipt["status"] == "SHADOW_COMPLETED"
            else None
        ),
        "owner_runs": owner.snapshot()["runs"],
        "transition_waited": transition_waited,
        "after_service_snapshot": service.snapshot(),
    }


def _campaign_cases() -> list[dict]:
    issued = time.perf_counter_ns()

    fifo_owner = _owner("fifo", issued)
    fifo = TypingShadowServiceV1(fifo_owner, maximum_queued=2)
    fifo_inputs = _inputs(fifo)
    fifo.submit(_request_id(fifo_inputs), fifo_inputs)
    fifo_receipt = fifo.execute_next()
    cases = [_case(
        "FIFO_COMPLETION", "SHADOW_COMPLETED", fifo, fifo_owner,
        receipt=fifo_receipt,
    )]

    cancel_owner = _owner("cancel", issued + 1)
    cancel = TypingShadowServiceV1(cancel_owner)
    cancel_inputs = _inputs(cancel)
    cancel_id = _request_id(cancel_inputs)
    cancel.submit(cancel_id, cancel_inputs)
    cancel_receipt = cancel.cancel(cancel_id)
    cases.append(_case(
        "CANCEL_BEFORE_ADMISSION", "CANCELED_BEFORE_ADMISSION",
        cancel, cancel_owner, receipt=cancel_receipt,
    ))

    reload_owner = _owner("reload-stale", issued + 2)
    reload_service = TypingShadowServiceV1(reload_owner)
    reload_inputs = _inputs(reload_service)
    reload_service.submit(_request_id(reload_inputs), reload_inputs)
    reload_service.reload_sources(issued_monotonic_ns=issued + 3)
    reload_receipt = reload_service.execute_next()
    cases.append(_case(
        "RELOAD_STALE_REJECTION", "STALE_GENERATION_REJECTED",
        reload_service, reload_owner, receipt=reload_receipt,
    ))

    restart_owner = _owner("restart-stale", issued + 4)
    restart_service = TypingShadowServiceV1(restart_owner)
    restart_inputs = _inputs(restart_service)
    restart_service.submit(_request_id(restart_inputs), restart_inputs)
    restart_service.restart(
        service_instance_id=f"{SERVICE}-restart-stale-new",
        issued_monotonic_ns=issued + 5,
    )
    restart_receipt = restart_service.execute_next()
    cases.append(_case(
        "RESTART_STALE_REJECTION", "STALE_GENERATION_REJECTED",
        restart_service, restart_owner, receipt=restart_receipt,
    ))

    bound_owner = _owner("queue-bound", issued + 6)
    bound = TypingShadowServiceV1(
        bound_owner, maximum_queued=1, maximum_requests=2
    )
    bound_inputs = _inputs(bound)
    bound_id = _request_id(bound_inputs)
    bound.submit(bound_id, bound_inputs)
    try:
        bound.submit(
            "queue-bound-second",
            _with_request_id(bound_inputs, "queue-bound-second"),
        )
    except TypingShadowServiceV1Error as exc:
        if str(exc) != "shadow service queue is full":
            raise
    else:
        raise RuntimeError("queue bound unexpectedly admitted second request")
    bound.cancel(bound_id)
    cases.append(_case(
        "QUEUE_BOUND_REJECTION", "SUBMISSION_REJECTED_QUEUE_FULL",
        bound, bound_owner,
    ))

    invalid_owner = _owner("invalidate", issued + 7)
    invalid = TypingShadowServiceV1(invalid_owner)
    invalid_inputs = _inputs(invalid)
    invalid.submit(_request_id(invalid_inputs), invalid_inputs)
    invalid.invalidate()
    cases.append(_case(
        "EXPLICIT_INVALIDATION", "SERVICE_INVALIDATED",
        invalid, invalid_owner,
    ))

    failure_owner = _owner("unexpected-failure", issued + 8)
    failure = TypingShadowServiceV1(failure_owner)
    failure_inputs = _inputs(failure)
    failure.submit(_request_id(failure_inputs), failure_inputs)
    with patch.object(
        failure_owner, "run_shadow_pipeline",
        side_effect=RuntimeError("forced unexpected shadow failure"),
    ):
        failure_receipt = failure.execute_next()
    cases.append(_case(
        "UNEXPECTED_SHADOW_FAILURE", "SHADOW_REJECTED",
        failure, failure_owner, receipt=failure_receipt,
    ))

    race_owner = _owner("admission-race", issued + 9)
    race = TypingShadowServiceV1(race_owner)
    race_inputs = _inputs(race)
    race.submit(_request_id(race_inputs), race_inputs)
    entered = Event()
    release = Event()
    reload_done = Event()
    receipts: list[dict] = []
    errors: list[BaseException] = []
    original = race_owner.run_shadow_pipeline

    def paused_run(**pipeline_inputs):
        entered.set()
        if not release.wait(10):
            raise RuntimeError("campaign did not release admitted request")
        return original(**pipeline_inputs)

    def execute() -> None:
        try:
            receipts.append(race.execute_next())
        except BaseException as exc:
            errors.append(exc)

    def reload_sources() -> None:
        try:
            race.reload_sources(issued_monotonic_ns=issued + 10)
            reload_done.set()
        except BaseException as exc:
            errors.append(exc)

    with patch.object(race_owner, "run_shadow_pipeline", side_effect=paused_run):
        execution_thread = Thread(target=execute)
        execution_thread.start()
        if not entered.wait(10):
            raise RuntimeError("admission race never entered the owner")
        reload_thread = Thread(target=reload_sources)
        reload_thread.start()
        transition_waited = not reload_done.wait(0.05)
        release.set()
        execution_thread.join(10)
        reload_thread.join(10)
    if errors or execution_thread.is_alive() or reload_thread.is_alive():
        raise RuntimeError(f"admission race failed: {errors!r}")
    cases.append(_case(
        "ADMISSION_RELOAD_SERIALIZATION", "SHADOW_COMPLETED",
        race, race_owner, receipt=receipts[0],
        transition_waited=transition_waited,
    ))

    assert tuple(item["case"] for item in cases) == CASES
    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    args = parser.parse_args(argv)
    output = _output_path(args.output)
    if output.exists() or output.is_symlink():
        parser.error(f"refusing to overwrite {output}")
    environment = capture_operational_benchmark_environment_v1(
        WORKSPACE,
        captured_at_utc=datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        benchmark_entrypoint=(
            "software/scripts/run_typing_shadow_service_campaign_v1.py"
        ),
    )
    if environment["repository_dirty"]:
        parser.error("campaign must run from a clean source commit")
    report = build_typing_shadow_service_campaign_v1(
        _campaign_cases(), campaign_id="e2-typing-shadow-service-001",
        environment=environment,
    )
    parse_typing_shadow_service_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(_canonical(report) + b"\n")
    print(json.dumps({
        "output": output.relative_to(WORKSPACE).as_posix(),
        "campaign_sha256": report["campaign_sha256"],
        "cases": [
            {"case": item["case"], "status": item["status"]}
            for item in report["cases"]
        ],
        "physical_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
