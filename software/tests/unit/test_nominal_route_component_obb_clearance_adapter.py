from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
MODULE_PATH = INTEGRATION / "nominal_route_component_obb_clearance_adapter.py"


def _module():
    integration = str(INTEGRATION)
    if integration not in sys.path:
        sys.path.insert(0, integration)
    spec = importlib.util.spec_from_file_location("component_obb_adapter", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _ComponentRuntime:
    def __init__(self, module, *, center_gap=12.0):
        self.module = module
        self.center_gap = center_gap

    def bound_link_obbs(self, **_kwargs):
        bound = self.module.OrientedBoxIntervalBound
        identity = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
        return (
            bound("base", "base:0", (0.0, 0.0, 0.0), identity, (1.0, 1.0, 1.0), 0.0),
            bound("tip", "tip:0", (self.center_gap, 0.0, 0.0), identity, (1.0, 1.0, 1.0), 0.0),
        )


class _EnvironmentRuntime:
    def __init__(self, module, *, blocked=False):
        self.module = module
        self.blocked = blocked
        self.sweeps = 0

    def bound_link_spheres(self, **_kwargs):
        return (
            self.module.SphereIntervalBound("base", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0, 0.0),
            self.module.SphereIntervalBound("tip", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0, 0.0),
        )

    def sweep_sphere_any(self, **_kwargs):
        self.sweeps += 1
        return self.blocked

    def moving_self_collision_any(self, **_kwargs):
        return ("base", "tip")


def test_composition_replaces_only_self_test_and_keeps_environment_sweeps():
    module = _module()
    environment = _EnvironmentRuntime(module)

    result = module.check_composed_continuous_clearance(
        component_runtime=_ComponentRuntime(module),
        environment_runtime=environment,
        start_sequence=1,
        end_sequence=2,
        start_joint_targets_rad=[0.0] * 6,
        end_joint_targets_rad=[0.0] * 6,
        reviewed_excluded_pairs=(),
    )

    assert result["continuous"] is True
    assert result["proof_method"] == "COMPONENT_OBB_SELF_PLUS_ENVIRONMENT_SPHERE_SWEEPS"
    assert result["self_clearance"]["minimum_clearance_mm"] == pytest.approx(10.0)
    assert environment.sweeps == 2


def test_composition_does_not_query_environment_after_self_proof_failure():
    module = _module()
    environment = _EnvironmentRuntime(module)

    with pytest.raises(module.ComponentObbClearanceError):
        module.check_composed_continuous_clearance(
            component_runtime=_ComponentRuntime(module, center_gap=1.0),
            environment_runtime=environment,
            start_sequence=1,
            end_sequence=2,
            start_joint_targets_rad=[0.0] * 6,
            end_joint_targets_rad=[0.0] * 6,
            reviewed_excluded_pairs=(),
        )
    assert environment.sweeps == 0


def test_composition_still_fails_closed_on_environment_obstruction():
    module = _module()
    environment = _EnvironmentRuntime(module, blocked=True)

    with pytest.raises(module.ConservativeSweepError, match="subdivision budget"):
        module.check_composed_continuous_clearance(
            component_runtime=_ComponentRuntime(module),
            environment_runtime=environment,
            start_sequence=1,
            end_sequence=2,
            start_joint_targets_rad=[0.0] * 6,
            end_joint_targets_rad=[0.0] * 6,
            reviewed_excluded_pairs=(),
        )
