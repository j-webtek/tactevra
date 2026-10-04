"""Retain a clean-commit lifecycle and fault campaign for the IK cache owner."""

from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys
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
from rocell.application.typing_exact_ik_cache_owner_campaign_v1 import (  # noqa: E402
    CASES,
    build_typing_exact_ik_cache_owner_campaign_v1,
    parse_typing_exact_ik_cache_owner_campaign_v1,
)
from rocell.application.typing_exact_ik_cache_owner_v1 import (  # noqa: E402
    TypingExactIkCacheOwnerV1,
    TypingExactIkCacheOwnerV1Error,
)


DEFAULT_OUTPUT = Path(
    "software/ai/eval/typing_exact_ik_cache_owner_campaign_v1.json"
)
SERVICE = "typing-exact-ik-cache-owner-campaign"


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


def _inputs(owner: TypingExactIkCacheOwnerV1):
    return shadow_fixture._inputs(
        ("R", "O", "B", "O", "T"), "robot", context=owner.context
    )


def _case(
    name: str, transition: str, old_cache_retired: bool,
    execution_status: str, receipt_sha256: str | None,
    receipt_matches_reference: bool | None,
    owner: TypingExactIkCacheOwnerV1,
) -> dict:
    return {
        "case": name,
        "status": "PASS",
        "transition": transition,
        "old_cache_retired": old_cache_retired,
        "execution_status": execution_status,
        "receipt_sha256": receipt_sha256,
        "receipt_matches_reference": receipt_matches_reference,
        "after_owner_snapshot": owner.snapshot(),
    }


def _blocked(owner: TypingExactIkCacheOwnerV1, inputs: dict) -> None:
    try:
        owner.run_shadow_pipeline(**inputs)
    except TypingExactIkCacheOwnerV1Error:
        return
    raise RuntimeError("unready owner unexpectedly executed")


def _campaign_cases() -> list[dict]:
    issued = time.perf_counter_ns()

    normal = _owner("normal", issued)
    normal_inputs = _inputs(normal)
    reference = normal.run_shadow_pipeline(**normal_inputs)
    warm = normal.run_shadow_pipeline(**normal_inputs)
    if warm != reference:
        raise RuntimeError("normal cold and warm receipts differ")
    reference_sha = reference["typing_shadow_pipeline_sha256"]
    cases = [_case(
        "NORMAL_COLD_WARM", "NONE", False, "PASSED", reference_sha, True,
        normal,
    )]

    reload_owner = _owner("reload", issued + 1)
    reload_inputs = _inputs(reload_owner)
    reload_reference = reload_owner.run_shadow_pipeline(**reload_inputs)
    reload_old_cache = reload_owner._cache
    reload_binding = reload_owner.reload_sources(issued_monotonic_ns=issued + 2)
    reload_receipt = reload_owner.run_shadow_pipeline(**shadow_fixture._inputs(
        ("R", "O", "B", "O", "T"), "robot", context=reload_binding.context
    ))
    cases.append(_case(
        "RELOAD_RETIREMENT", "RELOAD",
        reload_old_cache.snapshot()["active"] is False,
        "PASSED", reload_receipt["typing_shadow_pipeline_sha256"],
        reload_receipt == reload_reference == reference, reload_owner,
    ))

    restart_owner = _owner("restart", issued + 3)
    restart_inputs = _inputs(restart_owner)
    restart_reference = restart_owner.run_shadow_pipeline(**restart_inputs)
    restart_old_cache = restart_owner._cache
    restart_binding = restart_owner.restart(
        service_instance_id=f"{SERVICE}-restart-new",
        issued_monotonic_ns=issued + 4,
    )
    restart_receipt = restart_owner.run_shadow_pipeline(**shadow_fixture._inputs(
        ("R", "O", "B", "O", "T"), "robot", context=restart_binding.context
    ))
    cases.append(_case(
        "RESTART_RETIREMENT", "RESTART",
        restart_old_cache.snapshot()["active"] is False,
        "PASSED", restart_receipt["typing_shadow_pipeline_sha256"],
        restart_receipt == restart_reference == reference, restart_owner,
    ))

    invalidated = _owner("invalidate", issued + 5)
    invalidated_inputs = _inputs(invalidated)
    invalidated.run_shadow_pipeline(**invalidated_inputs)
    invalidated_old_cache = invalidated._cache
    invalidated.invalidate()
    _blocked(invalidated, invalidated_inputs)
    cases.append(_case(
        "EXPLICIT_INVALIDATION", "INVALIDATE",
        invalidated_old_cache.snapshot()["active"] is False,
        "BLOCKED", None, None, invalidated,
    ))

    reload_failure = _owner("reload-failure", issued + 6)
    reload_failure_inputs = _inputs(reload_failure)
    reload_failure.run_shadow_pipeline(**reload_failure_inputs)
    reload_failure_old_cache = reload_failure._cache
    with patch(
        "rocell.application.typing_exact_ik_cache_owner_v1."
        "prepare_typing_planner_v1",
        side_effect=RuntimeError("forced reload preparation failure"),
    ):
        try:
            reload_failure.reload_sources(issued_monotonic_ns=issued + 7)
        except RuntimeError as exc:
            if str(exc) != "forced reload preparation failure":
                raise
        else:
            raise RuntimeError("forced reload preparation unexpectedly passed")
    _blocked(reload_failure, reload_failure_inputs)
    cases.append(_case(
        "RELOAD_REFRESH_FAILURE", "RELOAD",
        reload_failure_old_cache.snapshot()["active"] is False,
        "BLOCKED", None, None, reload_failure,
    ))

    restart_failure = _owner("restart-failure", issued + 8)
    restart_failure_inputs = _inputs(restart_failure)
    restart_failure.run_shadow_pipeline(**restart_failure_inputs)
    restart_failure_old_cache = restart_failure._cache
    with patch(
        "rocell.application.typing_exact_ik_cache_owner_v1."
        "prepare_typing_planner_v1",
        side_effect=RuntimeError("forced restart preparation failure"),
    ):
        try:
            restart_failure.restart(
                service_instance_id=f"{SERVICE}-restart-failure-new",
                issued_monotonic_ns=issued + 9,
            )
        except RuntimeError as exc:
            if str(exc) != "forced restart preparation failure":
                raise
        else:
            raise RuntimeError("forced restart preparation unexpectedly passed")
    _blocked(restart_failure, restart_failure_inputs)
    cases.append(_case(
        "RESTART_REFRESH_FAILURE", "RESTART",
        restart_failure_old_cache.snapshot()["active"] is False,
        "BLOCKED", None, None, restart_failure,
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
            "software/scripts/run_typing_exact_ik_cache_owner_campaign_v1.py"
        ),
    )
    if environment["repository_dirty"]:
        parser.error("campaign must run from a clean source commit")
    report = build_typing_exact_ik_cache_owner_campaign_v1(
        _campaign_cases(),
        campaign_id="e2-exact-ik-cache-owner-001",
        environment=environment,
    )
    parse_typing_exact_ik_cache_owner_campaign_v1(report)
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
