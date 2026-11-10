from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    path = ROOT / "software/integrations/isaac_sim/nominal_route_memory_preflight.py"
    spec = importlib.util.spec_from_file_location(
        "nominal_route_memory_preflight", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_memory_preflight_passes_with_safe_margin() -> None:
    module = _module()
    snapshot = module.MemorySnapshot(
        total_physical_bytes=128 * module.GIB,
        available_physical_bytes=96 * module.GIB,
        commit_limit_bytes=224 * module.GIB,
        available_commit_bytes=192 * module.GIB,
    )

    result = module.evaluate_memory_preflight(snapshot)

    assert result["status"] == "PASS_MEMORY_PREFLIGHT"
    assert result["launch_admitted"] is True
    assert result["checks"] == {
        "available_commit": True,
        "available_physical": True,
        "commit_utilization": True,
    }
    assert result["attempt_claimed"] is False
    assert result["isaac_started"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False


def test_memory_preflight_fails_before_claim_when_commit_is_low() -> None:
    module = _module()
    snapshot = module.MemorySnapshot(
        total_physical_bytes=128 * module.GIB,
        available_physical_bytes=4 * module.GIB,
        commit_limit_bytes=224 * module.GIB,
        available_commit_bytes=1 * module.GIB,
    )

    result = module.evaluate_memory_preflight(snapshot)

    assert result["status"] == "FAIL_MEMORY_PREFLIGHT"
    assert result["launch_admitted"] is False
    assert result["checks"] == {
        "available_commit": False,
        "available_physical": False,
        "commit_utilization": False,
    }
    assert result["attempt_claimed"] is False
    assert result["automatic_retry"] is False
    assert result["trajectory_playback"] is False
    assert result["joint_targets_submitted"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"minimum_available_commit_bytes": 0},
        {"minimum_available_physical_bytes": 0},
        {"maximum_commit_utilization": 1.0},
    ],
)
def test_memory_preflight_rejects_invalid_thresholds(kwargs) -> None:
    module = _module()
    snapshot = module.MemorySnapshot(
        total_physical_bytes=128 * module.GIB,
        available_physical_bytes=96 * module.GIB,
        commit_limit_bytes=224 * module.GIB,
        available_commit_bytes=192 * module.GIB,
    )

    with pytest.raises(module.MemoryPreflightError):
        module.evaluate_memory_preflight(snapshot, **kwargs)
