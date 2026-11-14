"""Compose component-OBB self-clearance with environment sphere sweeps."""

from __future__ import annotations

from typing import Any, Sequence

from nominal_route_component_obb_clearance import (
    ComponentObbClearanceError,
    ComponentObbRuntime,
    OrientedBoxIntervalBound,
    check_continuous_self_clearance,
)
from nominal_route_conservative_sweep_adapter import (
    ConservativeSweepError,
    ConservativeSweepRuntime,
    SphereIntervalBound,
    check_continuous_clearance as check_environment_clearance,
)


class _EnvironmentSweepOnlyRuntime:
    """Disable coarse sphere self-tests only after the OBB proof passes."""

    def __init__(self, runtime: ConservativeSweepRuntime) -> None:
        self._runtime = runtime

    def bound_link_spheres(
        self,
        *,
        start_joint_targets_rad: Sequence[float],
        end_joint_targets_rad: Sequence[float],
    ) -> Sequence[SphereIntervalBound]:
        return self._runtime.bound_link_spheres(
            start_joint_targets_rad=start_joint_targets_rad,
            end_joint_targets_rad=end_joint_targets_rad,
        )

    def sweep_sphere_any(self, **kwargs: Any) -> bool:
        return self._runtime.sweep_sphere_any(**kwargs)

    def moving_self_collision_any(self, **_kwargs: Any) -> tuple[str, str] | None:
        return None


class ComponentObbClearanceRuntimeAdapter:
    """Expose the route backend clearance protocol over both proof runtimes.

    Construction does not call either runtime or authorize a simulator launch.
    Exclusions come from the reviewed component binding rather than the route
    caller; the underlying proof still fails closed on an indeterminate pair.
    """

    def __init__(
        self,
        *,
        component_runtime: ComponentObbRuntime,
        environment_runtime: ConservativeSweepRuntime,
    ) -> None:
        if not callable(getattr(component_runtime, "bound_link_obbs", None)):
            raise ComponentObbClearanceError("component runtime protocol is absent")
        if not all(
            callable(getattr(environment_runtime, name, None))
            for name in ("bound_link_spheres", "sweep_sphere_any")
        ):
            raise ComponentObbClearanceError("environment runtime protocol is absent")
        exclusions = getattr(component_runtime, "excluded_pairs", None)
        if not isinstance(exclusions, frozenset):
            raise ComponentObbClearanceError("reviewed component exclusions are absent")
        self._component_runtime = component_runtime
        self._environment_runtime = environment_runtime
        self._excluded_pairs = tuple(sorted(exclusions))

    def check_continuous_clearance(
        self,
        *,
        start_sequence: int,
        end_sequence: int,
        start_joint_targets_rad: Sequence[float],
        end_joint_targets_rad: Sequence[float],
    ) -> dict[str, object]:
        return check_composed_continuous_clearance(
            component_runtime=self._component_runtime,
            environment_runtime=self._environment_runtime,
            start_sequence=start_sequence,
            end_sequence=end_sequence,
            start_joint_targets_rad=start_joint_targets_rad,
            end_joint_targets_rad=end_joint_targets_rad,
            reviewed_excluded_pairs=self._excluded_pairs,
        )


def check_composed_continuous_clearance(
    *,
    component_runtime: ComponentObbRuntime,
    environment_runtime: ConservativeSweepRuntime,
    start_sequence: int,
    end_sequence: int,
    start_joint_targets_rad: Sequence[float],
    end_joint_targets_rad: Sequence[float],
    reviewed_excluded_pairs: Sequence[tuple[str, str]],
) -> dict[str, object]:
    """Require both continuous self and environment clearance proofs."""

    self_result = check_continuous_self_clearance(
        component_runtime,
        start_sequence=start_sequence,
        end_sequence=end_sequence,
        start_joint_targets_rad=start_joint_targets_rad,
        end_joint_targets_rad=end_joint_targets_rad,
        reviewed_excluded_pairs=reviewed_excluded_pairs,
    )
    environment_result = check_environment_clearance(
        _EnvironmentSweepOnlyRuntime(environment_runtime),
        start_sequence=start_sequence,
        end_sequence=end_sequence,
        start_joint_targets_rad=start_joint_targets_rad,
        end_joint_targets_rad=end_joint_targets_rad,
        reviewed_excluded_pairs=(),
    )
    return {
        "start_sequence": start_sequence,
        "end_sequence": end_sequence,
        "continuous": True,
        "determinate": True,
        "minimum_clearance_mm": min(
            float(self_result["minimum_clearance_mm"]),
            float(environment_result["minimum_clearance_mm"]),
        ),
        "colliding_body_pair": None,
        "proof_method": "COMPONENT_OBB_SELF_PLUS_ENVIRONMENT_SPHERE_SWEEPS",
        "self_clearance": self_result,
        "environment_clearance": environment_result,
    }
