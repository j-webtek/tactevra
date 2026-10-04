from __future__ import annotations

import copy
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/tests/integration"))

import test_model_motion_ingress_v2 as ingress_fixture  # noqa: E402
import test_typing_shadow_pipeline_v1 as shadow_fixture  # noqa: E402
from rocell.application.context import SimulationContextError  # noqa: E402
from rocell.application.typing_exact_ik_cache_owner_v1 import (  # noqa: E402
    TypingExactIkCacheOwnerV1,
    TypingExactIkCacheOwnerV1Error,
    parse_typing_exact_ik_cache_owner_snapshot_v1,
)
from rocell.application.typing_shadow_pipeline_v1 import (  # noqa: E402
    run_typing_shadow_pipeline_v1,
)


def _owner(service: str = "typing-cache-owner-test") -> TypingExactIkCacheOwnerV1:
    return TypingExactIkCacheOwnerV1.start(
        ingress_fixture.WORKSPACE,
        ingress_fixture.MANIFEST,
        service_instance_id=service,
        issued_monotonic_ns=100,
        maximum_entries=256,
    )


def _rehash(snapshot: dict) -> None:
    import rocell.application.typing_exact_ik_cache_owner_v1 as owner_module
    core = {
        key: value for key, value in snapshot.items()
        if key != "owner_snapshot_sha256"
    }
    snapshot["owner_snapshot_sha256"] = owner_module._sha(core)


def test_owner_cold_warm_receipts_and_diagnostics_are_exact():
    owner = _owner()
    inputs = shadow_fixture._inputs(
        ("R", "O", "B", "O", "T"), "robot", context=owner.context
    )
    reference = run_typing_shadow_pipeline_v1(**inputs)
    cold = owner.run_shadow_pipeline(**inputs)
    cold_snapshot = owner.snapshot()
    warm = owner.run_shadow_pipeline(**inputs)
    warm_snapshot = owner.snapshot()

    assert cold == warm == reference
    assert dict(
        parse_typing_exact_ik_cache_owner_snapshot_v1(warm_snapshot)
    ) == warm_snapshot
    assert cold_snapshot["cache"]["misses"] > 0
    assert warm_snapshot["cache"]["hits"] > cold_snapshot["cache"]["hits"]
    assert warm_snapshot["cache"]["misses"] == cold_snapshot["cache"]["misses"]
    assert warm_snapshot["runs"] == 2
    assert warm_snapshot["run_failures"] == 0
    assert warm_snapshot["decision_input"] is False
    assert warm_snapshot["controller_commands"] == []
    assert warm_snapshot["hardware_access"] is False
    assert warm_snapshot["physical_authority"] is False


def test_owner_reload_and_restart_automatically_retire_old_caches():
    owner = _owner("typing-cache-owner-transitions")
    original_inputs = shadow_fixture._inputs(context=owner.context)
    owner.run_shadow_pipeline(**original_inputs)
    first_cache = owner._cache

    reload_binding = owner.reload_sources(issued_monotonic_ns=200)
    assert first_cache.snapshot()["active"] is False
    assert owner.snapshot()["cache"]["entry_count"] == 0
    assert owner.snapshot()["reloads"] == 1
    with pytest.raises(SimulationContextError):
        owner.run_shadow_pipeline(**original_inputs)
    reload_inputs = shadow_fixture._inputs(context=reload_binding.context)
    owner.run_shadow_pipeline(**reload_inputs)
    second_cache = owner._cache

    restart_binding = owner.restart(
        service_instance_id="typing-cache-owner-restarted",
        issued_monotonic_ns=300,
    )
    assert second_cache.snapshot()["active"] is False
    snapshot = owner.snapshot()
    assert snapshot["restarts"] == 1
    assert snapshot["retired_caches"] == 2
    assert snapshot["cache"]["entry_count"] == 0
    restart_inputs = shadow_fixture._inputs(context=restart_binding.context)
    owner.run_shadow_pipeline(**restart_inputs)
    assert owner.snapshot()["cache"]["misses"] > 0


def test_owner_blocks_overrides_and_explicit_invalidation():
    owner = _owner("typing-cache-owner-override")
    inputs = shadow_fixture._inputs(context=owner.context)
    with pytest.raises(TypingExactIkCacheOwnerV1Error, match="overridden"):
        owner.run_shadow_pipeline(**inputs, exact_ik_result_cache=None)

    assert owner.invalidate() == 1
    snapshot = owner.snapshot()
    assert snapshot["active"] is False
    assert snapshot["ready"] is False
    assert snapshot["invalidations"] == 1
    assert snapshot["retired_caches"] == 1
    assert snapshot["cache"]["active"] is False
    assert dict(
        parse_typing_exact_ik_cache_owner_snapshot_v1(snapshot)
    ) == snapshot
    with pytest.raises(TypingExactIkCacheOwnerV1Error, match="invalidated"):
        owner.run_shadow_pipeline(**inputs)


@pytest.mark.parametrize("mutation,match", (
    ("hash", "hash differs"),
    ("identity", "lifecycle identities differ"),
    ("counter", "owner counters differ"),
    ("authority", "zero authority"),
))
def test_owner_diagnostic_mutations_fail_closed(mutation: str, match: str):
    snapshot = copy.deepcopy(_owner().snapshot())
    if mutation == "hash":
        snapshot["owner_snapshot_sha256"] = "f" * 64
    elif mutation == "identity":
        snapshot["generation"] += 1
        _rehash(snapshot)
    elif mutation == "counter":
        snapshot["retired_caches"] += 1
        _rehash(snapshot)
    else:
        snapshot["physical_authority"] = True
        _rehash(snapshot)
    with pytest.raises(TypingExactIkCacheOwnerV1Error, match=match):
        parse_typing_exact_ik_cache_owner_snapshot_v1(snapshot)
