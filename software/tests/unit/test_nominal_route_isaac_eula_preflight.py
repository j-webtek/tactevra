from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    path = (
        ROOT / "software/integrations/isaac_sim/nominal_route_isaac_eula_preflight.py"
    )
    spec = importlib.util.spec_from_file_location(
        "nominal_route_isaac_eula_preflight", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_eula_preflight_passes_only_for_exact_operator_signal() -> None:
    module = _module()

    result = module.evaluate_eula_preflight({"OMNI_KIT_ACCEPT_EULA": "YES"})

    assert result["status"] == "PASS_EULA_PREFLIGHT"
    assert result["launch_admitted"] is True
    assert result["acceptance_observed"] is True
    assert result["acceptance_performed_by_preflight"] is False
    assert result["attempt_claimed"] is False
    assert result["isaac_started"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"OMNI_KIT_ACCEPT_EULA": ""},
        {"OMNI_KIT_ACCEPT_EULA": "yes"},
        {"OMNI_KIT_ACCEPT_EULA": "NO"},
        {"OMNI_KIT_ACCEPT_EULA": "YES "},
    ],
)
def test_eula_preflight_fails_closed_without_exact_signal(environment) -> None:
    module = _module()

    result = module.evaluate_eula_preflight(environment)

    assert result["status"] == "FAIL_EULA_PREFLIGHT"
    assert result["launch_admitted"] is False
    assert result["acceptance_observed"] is False
    assert result["acceptance_performed_by_preflight"] is False
    assert result["operator_action_required"] is not None
    assert result["attempt_claimed"] is False
    assert result["automatic_retry"] is False
    assert result["trajectory_playback"] is False
    assert result["joint_targets_submitted"] is False
