"""Compose component-OBB self-clearance with environment sphere sweeps."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

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


class ComponentObbRouteRuntime:
    """Adapt an existing route runtime while replacing its clearance method.

    The caller remains responsible for constructing and reviewing the native
    runtimes and for authorizing any backend execution.
    """

    def __init__(self, *, route_runtime: Any, clearance: ComponentObbClearanceRuntimeAdapter) -> None:
        if not all(
            callable(getattr(route_runtime, name, None))
            for name in ("regenerate_row", "measure_tool_key", "root_drift")
        ) or not isinstance(clearance, ComponentObbClearanceRuntimeAdapter):
            raise ComponentObbClearanceError("route runtime composition is invalid")
        self._route_runtime = route_runtime
        self._clearance = clearance

    def regenerate_row(
        self, *, source_row: Mapping[str, Any], previous_joint_targets_rad: Sequence[float]
    ) -> Mapping[str, Any]:
        return self._route_runtime.regenerate_row(
            source_row=source_row, previous_joint_targets_rad=previous_joint_targets_rad
        )

    def measure_tool_key(
        self, *, sequence: int, joint_targets_rad: Sequence[float], phase: str
    ) -> Mapping[str, Any]:
        return self._route_runtime.measure_tool_key(
            sequence=sequence, joint_targets_rad=joint_targets_rad, phase=phase
        )

    def root_drift(self) -> Mapping[str, Any]:
        return self._route_runtime.root_drift()

    def check_continuous_clearance(
        self, *, start_sequence: int, end_sequence: int,
        start_joint_targets_rad: Sequence[float], end_joint_targets_rad: Sequence[float],
    ) -> dict[str, object]:
        return self._clearance.check_continuous_clearance(
            start_sequence=start_sequence, end_sequence=end_sequence,
            start_joint_targets_rad=start_joint_targets_rad,
            end_joint_targets_rad=end_joint_targets_rad,
        )


def construct_component_obb_route_runtime(
    *,
    route_runtime: Any,
    component_definition: Mapping[str, Any],
    component_review: Mapping[str, Any],
    sweep_definition: Mapping[str, Any],
    sweep_review: Mapping[str, Any],
    articulation: Any,
    scene_query: Any,
    environment_only_scene: bool,
    robot_collision_query_shapes_enabled: bool,
) -> ComponentObbRouteRuntime:
    """Construct the two native bindings over the same supplied scene.

    This is an import-safe construction path, not an execution or launch gate.
    Both bindings validate their own source and review contracts.  In
    particular, the environment-only scene assertions must come from the
    caller's independently checked native scene metadata.
    """
    from nominal_route_native_component_obb_binding import NativeComponentObbRuntime
    from nominal_route_native_sweep_binding import NativeIsaacConservativeSweepBinding

    component = NativeComponentObbRuntime(
        component_definition, binding_review=component_review, articulation=articulation
    )
    environment = NativeIsaacConservativeSweepBinding(
        sweep_definition,
        binding_review=sweep_review,
        articulation=articulation,
        scene_query=scene_query,
        environment_only_scene=environment_only_scene,
        robot_collision_query_shapes_enabled=robot_collision_query_shapes_enabled,
    )
    return ComponentObbRouteRuntime(
        route_runtime=route_runtime,
        clearance=ComponentObbClearanceRuntimeAdapter(
            component_runtime=component, environment_runtime=environment
        ),
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
