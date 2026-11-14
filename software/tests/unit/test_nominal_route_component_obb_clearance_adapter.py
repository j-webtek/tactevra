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
        self.excluded_pairs = frozenset()

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


def test_backend_protocol_runs_both_proofs_without_caller_exclusions():
    module = _module()
    environment = _EnvironmentRuntime(module)
    adapter = module.ComponentObbClearanceRuntimeAdapter(
        component_runtime=_ComponentRuntime(module), environment_runtime=environment
    )
    assert environment.sweeps == 0
    result = adapter.check_continuous_clearance(
        start_sequence=1,
        end_sequence=2,
        start_joint_targets_rad=[0.0] * 6,
        end_joint_targets_rad=[0.0] * 6,
    )
    assert result["continuous"] is True
    assert environment.sweeps == 2


def test_backend_protocol_requires_bound_exclusions():
    module = _module()
    component = _ComponentRuntime(module)
    component.excluded_pairs = None
    with pytest.raises(module.ComponentObbClearanceError, match="exclusions"):
        module.ComponentObbClearanceRuntimeAdapter(
            component_runtime=component, environment_runtime=_EnvironmentRuntime(module)
        )


def test_route_wrapper_delegates_and_uses_new_clearance():
    module = _module()
    class Route:
        def regenerate_row(self, **kwargs):
            return kwargs
        def measure_tool_key(self, **kwargs):
            return kwargs
        def root_drift(self):
            return {"determinate": True}
        def check_continuous_clearance(self, **kwargs):
            raise AssertionError("old sphere self-test must not run")

    environment = _EnvironmentRuntime(module)
    clearance = module.ComponentObbClearanceRuntimeAdapter(
        component_runtime=_ComponentRuntime(module), environment_runtime=environment
    )
    runtime = module.ComponentObbRouteRuntime(route_runtime=Route(), clearance=clearance)
    assert runtime.regenerate_row(source_row={"sequence": 1}, previous_joint_targets_rad=[0] * 6)["source_row"] == {"sequence": 1}
    assert runtime.measure_tool_key(sequence=1, joint_targets_rad=[0] * 6, phase="hover")["phase"] == "hover"
    assert runtime.root_drift()["determinate"] is True
    assert runtime.check_continuous_clearance(
        start_sequence=1, end_sequence=2,
        start_joint_targets_rad=[0] * 6, end_joint_targets_rad=[0] * 6,
    )["continuous"] is True
    assert environment.sweeps == 2


def test_backend_executes_all_segments_through_composed_clearance(tmp_path):
    module = _module()
    fixture_path = ROOT / "software/tests/unit/test_nominal_route_physics_backend.py"
    spec = importlib.util.spec_from_file_location("arm255_backend_fixture", fixture_path)
    assert spec is not None and spec.loader is not None
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    backend, _, definition, route, _, output = fixtures._bundle(tmp_path)
    environment = _EnvironmentRuntime(module)
    clearance = module.ComponentObbClearanceRuntimeAdapter(
        component_runtime=_ComponentRuntime(module), environment_runtime=environment
    )
    runtime = module.ComponentObbRouteRuntime(
        route_runtime=fixtures.PassingRuntime(), clearance=clearance
    )

    result = backend.execute_backend(
        definition, route, backend_review=fixtures._accepted_review(backend, definition),
        output_directory=output, runtime=runtime,
    )

    assert result["continuous_clearance_segment_count"] == 288
    assert environment.sweeps == 576
    assert result["hardware_access"] is False


def test_native_construction_checks_scene_and_does_not_move():
    module = _module()
    def load_fixture(name):
        path = ROOT / f"software/tests/unit/test_nominal_route_native_{name}.py"
        spec = importlib.util.spec_from_file_location(f"fixture_{name}", path)
        assert spec is not None and spec.loader is not None
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        return fixture

    component_fixture = load_fixture("component_obb_binding")
    sweep_fixture = load_fixture("sweep_binding")
    component_module = component_fixture._module()
    component_definition = component_fixture._definition(component_module)
    sweep_module = sweep_fixture._module()
    sweep_definition = sweep_fixture._definition(sweep_module)
    sweep_review = {
        "schema": sweep_module.BINDING_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_NATIVE_BINDING_INTEGRATION",
        "source_binding_sha256": sweep_definition["binding_sha256"],
        "runtime_instantiation_admitted": True,
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    sweep_review["binding_review_sha256"] = sweep_module._sha(sweep_review)
    articulation = sweep_fixture._Articulation()
    query = sweep_fixture._Query()
    class Route:
        def regenerate_row(self, **kwargs): return kwargs
        def measure_tool_key(self, **kwargs): return kwargs
        def root_drift(self): return {}

    arguments = dict(
        route_runtime=Route(), component_definition=component_definition,
        component_review=component_fixture._review(component_module, component_definition),
        sweep_definition=sweep_definition, sweep_review=sweep_review,
        articulation=articulation, scene_query=query,
        environment_only_scene=True, robot_collision_query_shapes_enabled=False,
    )
    runtime = module.construct_component_obb_route_runtime(**arguments)
    assert isinstance(runtime, module.ComponentObbRouteRuntime)
    assert articulation.positions == []
    assert query.calls == []

    arguments["robot_collision_query_shapes_enabled"] = True
    from nominal_route_native_sweep_binding import NativeSweepBindingError
    with pytest.raises(NativeSweepBindingError, match="not admissible"):
        module.construct_component_obb_route_runtime(**arguments)


def test_worker_factory_callback_preserves_native_objects_and_checks_metadata(monkeypatch):
    module = _module()
    calls = []
    route = object()
    def base_factory(definition, **kwargs):
        calls.append((definition, kwargs))
        return route
    def construct(**kwargs):
        calls.append(kwargs)
        return "composed"
    monkeypatch.setattr(module, "construct_component_obb_route_runtime", construct)
    factory = module.ComponentObbRuntimeFactory(
        base_factory=base_factory, component_definition={"id": "component"},
        component_review={"id": "review"},
    )
    articulation, scene = object(), object()
    arguments = {
        "documents": {"binding_definition": {"id": "sweep"}, "binding_review": {}},
        "native_metadata": {"environment_only_scene": True, "robot_collision_query_shapes_enabled": False},
        "articulation": articulation, "scene_query": scene,
    }
    assert factory({"id": "factory"}, **arguments) == "composed"
    assert calls[1]["route_runtime"] is route
    assert calls[1]["articulation"] is articulation
    assert calls[1]["scene_query"] is scene
    arguments["native_metadata"] = {"environment_only_scene": False}
    with pytest.raises(module.ComponentObbClearanceError, match="incomplete"):
        factory({"id": "factory"}, **arguments)
    assert len(calls) == 2
