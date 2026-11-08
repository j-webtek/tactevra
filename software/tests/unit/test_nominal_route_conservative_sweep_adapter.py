from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    path = (
        ROOT
        / "software/integrations/isaac_sim/nominal_route_conservative_sweep_adapter.py"
    )
    spec = importlib.util.spec_from_file_location("arm257_adapter", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Runtime:
    def __init__(self, module, *, blocked_until_span=float("inf"), collision=None):
        self.module = module
        self.blocked_until_span = blocked_until_span
        self.collision = collision
        self.radii = []

    def bound_link_spheres(self, *, start_joint_targets_rad, end_joint_targets_rad):
        span = abs(end_joint_targets_rad[0] - start_joint_targets_rad[0])
        return [
            self.module.SphereIntervalBound(
                "wrist",
                (start_joint_targets_rad[0] * 100.0, 0.0, 0.0),
                (end_joint_targets_rad[0] * 100.0, 0.0, 0.0),
                2.0,
                span * 10.0,
            )
        ]

    def sweep_sphere_any(self, **kwargs):
        self.radii.append(kwargs["radius_mm"])
        span = abs(kwargs["end_center_mm"][0] - kwargs["start_center_mm"][0])
        return span > self.blocked_until_span

    def moving_self_collision_any(self, **kwargs):
        return self.collision


def test_arm257_clear_interval_uses_inflated_certified_envelope():
    module = _module()
    runtime = Runtime(module)

    result = module.check_continuous_clearance(
        runtime,
        start_sequence=4,
        end_sequence=5,
        start_joint_targets_rad=[0.0] * 6,
        end_joint_targets_rad=[0.01] + [0.0] * 5,
    )

    assert result["continuous"] is True
    assert result["minimum_clearance_mm"] == 0.5
    assert result["intervals_inspected"] == 1
    assert runtime.radii == [pytest.approx(2.6)]


def test_arm257_recursively_refines_conservative_hits():
    module = _module()
    runtime = Runtime(module, blocked_until_span=0.26)

    result = module.check_continuous_clearance(
        runtime,
        start_sequence=10,
        end_sequence=11,
        start_joint_targets_rad=[0.0] * 6,
        end_joint_targets_rad=[0.01] + [0.0] * 5,
        max_depth=3,
    )

    assert result["intervals_inspected"] == 7
    assert result["maximum_subdivision_depth"] == 2


def test_arm257_fails_closed_when_subdivision_budget_exhausts():
    module = _module()
    runtime = Runtime(module, blocked_until_span=-1.0)

    with pytest.raises(module.ConservativeSweepError, match="budget exhausted"):
        module.check_continuous_clearance(
            runtime,
            start_sequence=1,
            end_sequence=2,
            start_joint_targets_rad=[0.0] * 6,
            end_joint_targets_rad=[0.01] + [0.0] * 5,
            max_depth=2,
        )


def test_arm257_rejects_unreviewed_moving_self_collision():
    module = _module()
    runtime = Runtime(module, collision=("wrist", "forearm"))

    with pytest.raises(module.ConservativeSweepError, match="self collision"):
        module.check_continuous_clearance(
            runtime,
            start_sequence=1,
            end_sequence=2,
            start_joint_targets_rad=[0.0] * 6,
            end_joint_targets_rad=[0.01] + [0.0] * 5,
        )


def test_arm257_allows_only_explicit_reviewed_pair_exclusion():
    module = _module()
    runtime = Runtime(module, collision=("wrist", "forearm"))

    result = module.check_continuous_clearance(
        runtime,
        start_sequence=1,
        end_sequence=2,
        start_joint_targets_rad=[0.0] * 6,
        end_joint_targets_rad=[0.01] + [0.0] * 5,
        reviewed_excluded_pairs=[("forearm", "wrist")],
    )

    assert result["determinate"] is True


@pytest.mark.parametrize(
    "start,end,margin",
    [
        ([0.0] * 5, [0.0] * 6, 0.5),
        ([0.0] * 6, [0.0] * 6, 0.49),
        ([float("nan")] + [0.0] * 5, [0.0] * 6, 0.5),
    ],
)
def test_arm257_rejects_invalid_or_weakened_contract(start, end, margin):
    module = _module()
    with pytest.raises(module.ConservativeSweepError):
        module.check_continuous_clearance(
            Runtime(module),
            start_sequence=1,
            end_sequence=2,
            start_joint_targets_rad=start,
            end_joint_targets_rad=end,
            clearance_margin_mm=margin,
        )


def test_arm257_import_is_isaac_and_hardware_side_effect_free():
    source = (
        ROOT
        / "software/integrations/isaac_sim/nominal_route_conservative_sweep_adapter.py"
    ).read_text(encoding="utf-8")
    assert "from isaacsim import" not in source
    assert "SimulationApp(" not in source
    assert "serial" not in source
