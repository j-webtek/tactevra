from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    ROOT
    / "software/integrations/isaac_sim/nominal_route_component_obb_clearance.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("component_obb_clearance", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Runtime:
    def __init__(self, module, *, center_gap=12.0, deviation_per_rad=0.0):
        self.module = module
        self.center_gap = center_gap
        self.deviation_per_rad = deviation_per_rad
        self.calls = []

    def bound_link_obbs(self, *, start_joint_targets_rad, end_joint_targets_rad):
        delta = max(
            abs(right - left)
            for left, right in zip(start_joint_targets_rad, end_joint_targets_rad)
        )
        deviation = self.deviation_per_rad * delta
        self.calls.append((tuple(start_joint_targets_rad), tuple(end_joint_targets_rad)))
        bound = self.module.OrientedBoxIntervalBound
        identity = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
        return (
            bound("robot:base", "base:0", (0.0, 0.0, 0.0), identity, (1.0, 1.0, 1.0), 0.0),
            bound(
                "robot:link2",
                "link2:0",
                (self.center_gap, 0.0, 0.0),
                identity,
                (1.0, 1.0, 1.0),
                deviation,
            ),
        )


def test_component_obb_proves_direct_continuous_separation():
    module = _module()
    runtime = _Runtime(module)

    result = module.check_continuous_self_clearance(
        runtime,
        start_sequence=10,
        end_sequence=11,
        start_joint_targets_rad=[0.0] * 6,
        end_joint_targets_rad=[0.01] * 6,
    )

    assert result == {
        "start_sequence": 10,
        "end_sequence": 11,
        "continuous": True,
        "determinate": True,
        "minimum_clearance_mm": pytest.approx(10.0),
        "colliding_body_pair": None,
        "proof_method": "COMPONENT_OBB_SAT_WITH_POINT_PATH_BOUNDS",
        "intervals_inspected": 1,
        "maximum_subdivision_depth": 0,
    }


def test_component_obb_bisects_only_an_indeterminate_parent_interval():
    module = _module()
    runtime = _Runtime(module, deviation_per_rad=12.0)

    result = module.check_continuous_self_clearance(
        runtime,
        start_sequence=20,
        end_sequence=21,
        start_joint_targets_rad=[0.0] * 6,
        end_joint_targets_rad=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    assert result["intervals_inspected"] == 3
    assert result["maximum_subdivision_depth"] == 1
    assert result["minimum_clearance_mm"] == pytest.approx(4.0)


def test_component_obb_fails_closed_when_static_boxes_overlap():
    module = _module()
    runtime = _Runtime(module, center_gap=1.0)

    with pytest.raises(
        module.ComponentObbClearanceError,
        match="subdivision budget exhausted.*robot:base.*robot:link2",
    ):
        module.check_continuous_self_clearance(
            runtime,
            start_sequence=30,
            end_sequence=31,
            start_joint_targets_rad=[0.0] * 6,
            end_joint_targets_rad=[0.0] * 6,
            max_depth=2,
        )


def test_component_obb_honors_only_explicit_reviewed_exclusion():
    module = _module()
    runtime = _Runtime(module, center_gap=1.0)

    with pytest.raises(module.ComponentObbClearanceError, match="no reviewed"):
        module.check_continuous_self_clearance(
            runtime,
            start_sequence=40,
            end_sequence=41,
            start_joint_targets_rad=[0.0] * 6,
            end_joint_targets_rad=[0.0] * 6,
            reviewed_excluded_pairs=[("robot:base", "robot:link2")],
        )


def test_component_obb_rejects_non_orthonormal_axes():
    module = _module()
    runtime = _Runtime(module)
    original = runtime.bound_link_obbs

    def changed(**kwargs):
        rows = list(original(**kwargs))
        row = rows[0]
        rows[0] = module.OrientedBoxIntervalBound(
            row.link_name,
            row.primitive_name,
            row.start_center_mm,
            (2.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            row.half_extents_mm,
            row.max_point_path_deviation_mm,
        )
        return rows

    runtime.bound_link_obbs = changed
    with pytest.raises(module.ComponentObbClearanceError, match="orthonormal"):
        module.check_continuous_self_clearance(
            runtime,
            start_sequence=50,
            end_sequence=51,
            start_joint_targets_rad=[0.0] * 6,
            end_joint_targets_rad=[0.0] * 6,
        )
