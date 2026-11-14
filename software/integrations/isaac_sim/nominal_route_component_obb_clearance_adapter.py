"""Compose component-OBB self-clearance with environment sphere sweeps."""

from __future__ import annotations

import hashlib
import json
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


class ComponentObbRuntimeFactory:
    """Adapt the existing native factory to the worker's factory protocol.

    The wrapped factory still validates its own inputs and captures baselines.
    This adapter then constructs the new clearance bindings with the same
    articulation, query, and scene metadata supplied to that factory.
    """

    def __init__(
        self, *, base_factory: Any, component_definition: Mapping[str, Any],
        component_review: Mapping[str, Any],
    ) -> None:
        if not callable(base_factory):
            raise ComponentObbClearanceError("base runtime factory is absent")
        self._base_factory = base_factory
        self._component_definition = component_definition
        self._component_review = component_review

    def __call__(self, definition: Mapping[str, Any], **kwargs: Any) -> ComponentObbRouteRuntime:
        documents = kwargs.get("documents")
        metadata = kwargs.get("native_metadata")
        if (
            not isinstance(documents, Mapping)
            or not isinstance(metadata, Mapping)
            or metadata.get("environment_only_scene") is not True
            or metadata.get("robot_collision_query_shapes_enabled") is not False
            or "binding_definition" not in documents
            or "binding_review" not in documents
            or "articulation" not in kwargs
            or "scene_query" not in kwargs
        ):
            raise ComponentObbClearanceError("native runtime factory inputs are incomplete")
        route_runtime = self._base_factory(definition, **kwargs)
        return construct_component_obb_route_runtime(
            route_runtime=route_runtime,
            component_definition=self._component_definition,
            component_review=self._component_review,
            sweep_definition=documents["binding_definition"],
            sweep_review=documents["binding_review"],
            articulation=kwargs["articulation"],
            scene_query=kwargs["scene_query"],
            environment_only_scene=metadata["environment_only_scene"],
            robot_collision_query_shapes_enabled=metadata["robot_collision_query_shapes_enabled"],
        )


def build_component_obb_concrete_binding(
    paths: Any, *, component_definition: Mapping[str, Any],
    component_review: Mapping[str, Any],
) -> tuple[Any, dict[str, object]]:
    """Build a deferred worker with component clearance, without launching it.

    The legacy builder retains responsibility for validating pinned scene,
    route, worker, and factory artifacts. Component review and definition are
    checked again when the native runtime is constructed after a separate
    authorized claim; this function does not manufacture either record.
    """
    from nominal_route_concrete_native_attempt_binding import (
        build_concrete_native_attempt_binding,
    )
    from nominal_route_native_runtime_factory import construct_runtime
    from nominal_route_native_component_obb_binding import (
        DEFINITION_SCHEMA, REVIEW_SCHEMA, _sha, build_definition,
    )

    repo_root = paths.repo_root
    integration = repo_root / "software/integrations/isaac_sim"
    partition = integration / "evidence/roarm_m3_triangle_partition_link2_20261005.json"
    binding_source = integration / "nominal_route_native_component_obb_binding.py"
    urdf = repo_root / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    def digest(path: Any) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        expected_definition = build_definition(
            json.loads(partition.read_bytes()), partition_file_sha256=digest(partition),
            urdf_file_sha256=digest(urdf), binding_source_file_sha256=digest(binding_source),
            urdf_text=urdf.read_text(encoding="utf-8"),
        )
    except (OSError, ValueError) as exc:
        raise ComponentObbClearanceError("component source inputs are invalid") from exc

    binding_hash = component_definition.get("binding_sha256")
    review_hash = component_review.get("review_sha256")
    if (
        component_definition != expected_definition
        or component_definition.get("schema") != DEFINITION_SCHEMA
        or component_definition.get("status") != "READY_FOR_INDEPENDENT_COMPONENT_OBB_BINDING_REVIEW"
        or binding_hash != _sha({k: v for k, v in component_definition.items() if k != "binding_sha256"})
        or component_review.get("schema") != REVIEW_SCHEMA
        or component_review.get("status") != "ACCEPTED_FOR_COMPONENT_OBB_RUNTIME_INTEGRATION"
        or component_review.get("source_binding_sha256") != binding_hash
        or component_review.get("runtime_instantiation_admitted") is not True
        or component_review.get("launch_admitted") is not False
        or component_review.get("hardware_access") is not False
        or component_review.get("physical_authority") is not False
        or review_hash != _sha({k: v for k, v in component_review.items() if k != "review_sha256"})
    ):
        raise ComponentObbClearanceError("component definition or review is invalid")

    factory = ComponentObbRuntimeFactory(
        base_factory=construct_runtime,
        component_definition=component_definition,
        component_review=component_review,
    )
    concrete = build_concrete_native_attempt_binding(paths, runtime_factory=factory)
    receipt = {
        "schema": "tactevra.arm301.component_obb_concrete_binding.v1",
        "status": "PREPARED_FOR_INDEPENDENT_REVIEW",
        "legacy_binding_id": concrete.receipt.get("binding_id"),
        "component_definition_sha256": component_definition.get("binding_sha256"),
        "component_review_sha256": component_review.get("review_sha256"),
        "component_review_validated_at_binding": True,
        "component_review_revalidation_required_at_native_construction": True,
        "launch_admitted": False,
        "attempt_consumed": False,
        "isaac_started": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    return concrete.backend, receipt


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
