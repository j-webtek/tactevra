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
    assert result["geometry_scope"] == "MODEL_GEOMETRY_ONLY"
    assert result["physical_geometry_qualified"] is False
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
    class SeparatedArticulation(sweep_fixture._Articulation):
        def get_link_transforms(self):
            return [[[float(index), 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
                     for index, _name in enumerate(self.link_names)]]

    articulation = SeparatedArticulation()
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

    result = runtime.check_continuous_clearance(
        start_sequence=1, end_sequence=2,
        start_joint_targets_rad=[0.0] * 6, end_joint_targets_rad=[0.0] * 6,
    )
    assert result["continuous"] is True
    assert result["proof_method"] == "COMPONENT_OBB_SELF_PLUS_ENVIRONMENT_SPHERE_SWEEPS"
    assert len(query.calls) == 7
    assert all(call[0] == "overlap" for call in query.calls)

    # A native query hit must still stop the composed route proof.
    query.overlaps = [True] * 20
    with pytest.raises(module.ConservativeSweepError, match="subdivision budget"):
        runtime.check_continuous_clearance(
            start_sequence=1, end_sequence=2,
            start_joint_targets_rad=[0.0] * 6, end_joint_targets_rad=[0.0] * 6,
        )

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
    component_definition = {"id": "component", "nested": {"value": 1}}
    component_review = {"id": "review", "nested": {"value": 2}}
    factory = module.ComponentObbRuntimeFactory(
        base_factory=base_factory, component_definition=component_definition,
        component_review=component_review,
    )
    component_definition["nested"]["value"] = 99
    component_review["nested"]["value"] = 99
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
    assert calls[1]["component_definition"]["nested"]["value"] == 1
    assert calls[1]["component_review"]["nested"]["value"] == 2
    arguments["native_metadata"] = {"environment_only_scene": False}
    with pytest.raises(module.ComponentObbClearanceError, match="incomplete"):
        factory({"id": "factory"}, **arguments)
    assert len(calls) == 2


def test_single_use_worker_passes_composed_runtime_to_backend(tmp_path, monkeypatch):
    import json

    module = _module()
    path = ROOT / "software/tests/unit/test_nominal_route_native_runtime_worker_integration.py"
    spec = importlib.util.spec_from_file_location("worker_integration_fixture", path)
    assert spec is not None and spec.loader is not None
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    worker = fixture._load("component_worker_test", fixture.SOURCE)
    events = []
    native = {name: object() for name in ("articulation", "scene_query", "key_view", "root_view")}
    runtime = object()

    def base_factory(_definition, **kwargs):
        events.append("base_factory")
        assert kwargs["articulation"] is native["articulation"]
        return object()

    def compose(**kwargs):
        events.append("component_factory")
        assert kwargs["articulation"] is native["articulation"]
        assert kwargs["scene_query"] is native["scene_query"]
        return runtime

    def execute(*_args, **kwargs):
        events.append("execute")
        assert kwargs["runtime"] is runtime
        return {"status": "PASS"}

    monkeypatch.setattr(module, "construct_component_obb_route_runtime", compose)
    factory = module.ComponentObbRuntimeFactory(
        base_factory=base_factory, component_definition={}, component_review={}
    )
    backend = worker.OneAttemptNativeBackend(
        fixture._definition(worker), session_factory=lambda: fixture._Session(events, native),
        construct_runtime_fn=factory, execute_backend_fn=execute,
        backend_definition={}, route={}, factory_definition={}, factory_review={},
        factory_plan={}, factory_plan_review={},
        documents={"binding_definition": {}, "binding_review": {}}, solver_kwargs={},
        native_metadata={"environment_only_scene": True, "robot_collision_query_shapes_enabled": False},
    )
    output = tmp_path / "claimed"
    output.mkdir()
    (output / "status.json").write_text(json.dumps(fixture.CLAIM))
    assert backend(output) == {"status": "PASS"}
    assert events == ["start", "load", "initialize", "settle", "objects", "base_factory", "component_factory", "execute", "shutdown"]
    with pytest.raises(worker.NativeRuntimeWorkerIntegrationError, match="retry refused"):
        backend(output)


def test_offline_audit_rejects_unpinned_route(tmp_path):
    pytest.importorskip("scipy")
    route = tmp_path / "route.json"
    route.write_text("{}", encoding="utf-8")
    audit_path = INTEGRATION / "arm301_source_route_obb_audit.py"
    spec = importlib.util.spec_from_file_location("arm301_offline_audit_test", audit_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match="route file digest changed"):
        module.audit(route)


def test_whole_component_audit_rejects_changed_reduction(tmp_path, monkeypatch):
    import json
    pytest.importorskip("scipy")
    route = tmp_path / "route.json"
    route.write_text(json.dumps({"episode_id": "episode-ef340d0ad2740c118d87", "joint_targets": []}))
    spec = importlib.util.spec_from_file_location("arm301_whole_audit_test", INTEGRATION / "arm301_source_route_obb_audit.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROUTE_SHA256", module._file_sha(route))
    import nominal_route_whole_component_candidate as candidate
    monkeypatch.setattr(candidate, "REDUCTION_FILE_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="reduction file changed"):
        module.audit(route, whole_components=True)


def test_whole_component_inventory_rejects_missing_or_altered_box():
    import copy
    pytest.importorskip("scipy")
    spec = importlib.util.spec_from_file_location("arm301_inventory_test", INTEGRATION / "arm301_source_route_obb_audit.py")
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    box = {"kind": "oriented_box", "center_mm": [0, 0, 0],
           "rotation_row_major": [1, 0, 0, 0, 1, 0, 0, 0, 1], "half_extents_mm": [1, 1, 1]}
    reduction = {"links": [{"link_name": "link", "components": [
        {"candidate_primitive": box, "component_index": i, "maximum_vertex_overflow_mm": 0.0}
        for i in range(14)]}]}
    definition = {"component_obbs": [
        {"native_link_name": "link", "primitive_name": f"robot:link:{i}",
         "local_center_mm": [0, 0, 0], "local_rotation_row_major": box["rotation_row_major"],
         "half_extents_mm": [1, 1, 1]} for i in range(14)]}
    audit._verify_whole_component_inventory(definition, reduction)
    changed = copy.deepcopy(definition)
    changed["component_obbs"][0]["half_extents_mm"][0] = 0.5
    with pytest.raises(ValueError, match="inventory differs"):
        audit._verify_whole_component_inventory(changed, reduction)
    with pytest.raises(ValueError, match="inventory differs"):
        audit._verify_whole_component_inventory({"component_obbs": definition["component_obbs"][:-1]}, reduction)


def test_concrete_binding_admits_only_reviewed_simulation_surrogate_without_starting_session(monkeypatch):
    import types

    module = _module()
    seen = []
    backend = object()
    def base_factory(*_args, **_kwargs):
        raise AssertionError("deferred factory must not run during construction")
    def concrete_builder(paths, *, runtime_factory):
        seen.append((paths, runtime_factory))
        return types.SimpleNamespace(backend=backend, receipt={"binding_id": "legacy"})
    monkeypatch.setitem(sys.modules, "nominal_route_concrete_native_attempt_binding",
                        types.SimpleNamespace(build_concrete_native_attempt_binding=concrete_builder))
    monkeypatch.setitem(sys.modules, "nominal_route_native_runtime_factory",
                        types.SimpleNamespace(construct_runtime=base_factory))
    import nominal_route_native_component_obb_binding as component_binding
    import json
    partition = INTEGRATION / "evidence/roarm_m3_triangle_partition_link2_20261005.json"
    urdf = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    source = INTEGRATION / "nominal_route_native_component_obb_binding.py"
    definition = component_binding.build_definition(
        json.loads(partition.read_bytes()), partition_file_sha256=component_binding._file_sha(partition),
        urdf_file_sha256=component_binding._file_sha(urdf),
        binding_source_file_sha256=component_binding._file_sha(source),
        urdf_text=urdf.read_text(encoding="utf-8"),
    )
    review = {
        "schema": component_binding.REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_COMPONENT_OBB_RUNTIME_INTEGRATION",
        "source_binding_sha256": definition["binding_sha256"],
        "runtime_instantiation_admitted": True, "launch_admitted": False,
        "hardware_access": False, "physical_authority": False,
    }
    review["review_sha256"] = component_binding._sha(review)
    paths = types.SimpleNamespace(repo_root=ROOT)
    with pytest.raises(module.ComponentObbClearanceError, match="simulation surrogate scope"):
        module.build_component_obb_concrete_binding(
            paths, component_definition=definition, component_review=review,
        )
    assert seen == []
    from nominal_route_whole_component_candidate import build_candidate
    whole = build_candidate(ROOT)
    whole_review = dict(review)
    whole_review["source_binding_sha256"] = whole["binding_sha256"]
    whole_review["geometry_scope"] = "SIMULATED_VENDOR_MESH_CONVEX_HULL_SURROGATE"
    whole_review["physical_geometry_qualified"] = False
    whole_review.pop("review_sha256")
    whole_review["review_sha256"] = component_binding._sha(whole_review)
    actual_backend, binding_receipt = module.build_component_obb_concrete_binding(
        paths, component_definition=whole, component_review=whole_review,
    )
    assert actual_backend is backend
    assert isinstance(seen[0][1], module.ComponentObbRuntimeFactory)
    assert binding_receipt["geometry_scope"] == "SIMULATED_VENDOR_MESH_CONVEX_HULL_SURROGATE"
    assert binding_receipt["physical_geometry_qualified"] is False
    assert binding_receipt["isaac_started"] is False
    assert len(whole["component_obbs"]) == 14
    seen.clear()
    unscoped = dict(whole_review)
    unscoped.pop("geometry_scope")
    unscoped.pop("review_sha256")
    unscoped["review_sha256"] = component_binding._sha(unscoped)
    with pytest.raises(module.ComponentObbClearanceError, match="simulation surrogate scope"):
        module.build_component_obb_concrete_binding(
            paths, component_definition=whole, component_review=unscoped,
        )
    physical_claim = dict(whole_review)
    physical_claim["physical_geometry_qualified"] = True
    physical_claim.pop("review_sha256")
    physical_claim["review_sha256"] = component_binding._sha(physical_claim)
    with pytest.raises(module.ComponentObbClearanceError, match="simulation surrogate scope"):
        module.build_component_obb_concrete_binding(
            paths, component_definition=whole, component_review=physical_claim,
        )
    assert seen == []
    import copy
    altered = copy.deepcopy(whole)
    altered["component_obbs"][0]["half_extents_mm"][0] *= 0.5
    altered.pop("binding_sha256")
    altered["binding_sha256"] = component_binding._sha(altered)
    altered_review = dict(whole_review)
    altered_review["source_binding_sha256"] = altered["binding_sha256"]
    altered_review.pop("review_sha256")
    altered_review["review_sha256"] = component_binding._sha(altered_review)
    with pytest.raises(module.ComponentObbClearanceError, match="review is invalid"):
        module.build_component_obb_concrete_binding(
            paths, component_definition=altered, component_review=altered_review,
        )
    assert seen == []
    changed = dict(definition)
    changed["component_obbs"] = []
    changed.pop("binding_sha256")
    changed["binding_sha256"] = component_binding._sha(changed)
    changed_review = dict(review)
    changed_review["source_binding_sha256"] = changed["binding_sha256"]
    changed_review.pop("review_sha256")
    changed_review["review_sha256"] = component_binding._sha(changed_review)
    with pytest.raises(module.ComponentObbClearanceError, match="review is invalid"):
        module.build_component_obb_concrete_binding(
            paths, component_definition=changed, component_review=changed_review,
        )
    review["hardware_access"] = True
    with pytest.raises(module.ComponentObbClearanceError, match="review is invalid"):
        module.build_component_obb_concrete_binding(
            paths, component_definition=definition, component_review=review,
        )


def test_review_file_prepares_deferred_component_backend_and_detects_replacement(tmp_path, monkeypatch):
    import hashlib
    import json
    from types import SimpleNamespace

    monkeypatch.syspath_prepend(str(INTEGRATION))
    import arm301_prepare_component_backend as entry
    import nominal_route_concrete_native_attempt_binding as concrete
    import nominal_route_native_component_obb_binding as component

    paths = entry.BindingPaths(tmp_path, ROOT, tmp_path / "unused-attempt")
    definition = entry.build_candidate(ROOT)
    review = {
        "schema": component.REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_COMPONENT_OBB_RUNTIME_INTEGRATION",
        "source_binding_sha256": definition["binding_sha256"],
        "runtime_instantiation_admitted": True,
        "geometry_scope": "SIMULATED_VENDOR_MESH_CONVEX_HULL_SURROGATE",
        "physical_geometry_qualified": False,
        "launch_admitted": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    review["review_sha256"] = component._sha(review)
    review_file = tmp_path / "fixture-review.json"
    review_file.write_bytes(json.dumps(review).encode())
    digest = hashlib.sha256(review_file.read_bytes()).hexdigest()
    calls = []

    def construct(binding_paths, *, runtime_factory):
        calls.append(binding_paths)
        return SimpleNamespace(backend=pytest.fail, receipt={"binding_id": "fixture"})

    monkeypatch.setattr(concrete, "build_concrete_native_attempt_binding", construct)
    builder = entry.ReviewedComponentBindingBuilder(review_file, digest)
    binding = builder(paths)
    assert binding.backend is pytest.fail
    assert binding.receipt["component_review_file_sha256"] == digest
    assert binding.receipt["component_definition_sha256"] == definition["binding_sha256"]
    assert binding.receipt["attempt_consumed"] is False
    review_file.write_bytes(review_file.read_bytes() + b" ")
    with pytest.raises(ValueError, match="file digest changed"):
        builder(paths)
    assert calls == [paths]
    assert not paths.governed_attempt_directory.exists()



def test_nominal_workcell_screen_places_obstacles_relative_to_the_native_base(monkeypatch):
    import json
    pytest.importorskip("scipy")
    monkeypatch.syspath_prepend(str(INTEGRATION))
    import arm301_source_route_obb_audit as audit

    layout = json.loads((ROOT / "active-project/RoCell_v0_3/config/workcell_layout.json").read_bytes())
    urdf = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    # A 90-degree base yaw and a nonzero base height expose frame inversions
    # and double application of the fixed URDF base offset (70.1 mm).
    route = {"robot_placement_matrix_row_major": [
        0, -1, 0, 100, 1, 0, 0, 200, 0, 0, 1, 90, 0, 0, 0, 1,
    ]}
    board, keyboard = audit._workcell_boxes(route, layout, urdf)
    assert board.start_center_mm == pytest.approx((28.5, -205, -28.9))
    assert keyboard.start_center_mm == pytest.approx((-41.5, -142.5, -9.4))
    assert keyboard.half_extents_mm == pytest.approx((157.5, 73.5, 10.5))
    assert keyboard.start_axes_row_major == pytest.approx((0, 1, 0, -1, 0, 0, 0, 0, 1))



def test_local_space_stroke_returns_to_hover_with_episode_geometry(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace
    pytest.importorskip("scipy")
    monkeypatch.syspath_prepend(str(INTEGRATION))
    monkeypatch.syspath_prepend(str(ROOT / "software/src"))
    import arm301_source_route_obb_audit as audit

    profile_path = ROOT / "software/config/virtual_commissioning_profile.json"
    profile = json.loads(profile_path.read_bytes())
    route = {
        "episode_id": "fixture",
        "source_bindings": {"virtual_profile_sha256": audit._file_sha(profile_path)},
        "robot_placement_matrix_row_major": profile["study_input"]["physical_placement_input"]["matrix_row_major"],
        "randomized_key_center_board_xy_mm": [224.0, 111.0],
        "target_region": {"half_extent_mm": [48, 7]},
        "contact_endpoint_sequences": [0],
        "joint_targets": [{"joint_position_target_rad": [-0.096, 0.807, 1.698, -0.866, 0, 0]}],
    }
    paths = SimpleNamespace(repo_root=ROOT, route=tmp_path / "fixture.json",
                            layout=ROOT / "software/config/nominal_target_profiles.json")
    paths.route.write_text(json.dumps(route))
    result = audit._corrected_space_cycle(route, paths)
    assert result["waypoints_rad"][0] == result["waypoints_rad"][-1]
    assert 2.4 <= result["maximum_geometric_depth_mm"] < 3
    assert result["minimum_xy_edge_margin_mm"] >= 2.5
    assert result["final_gap_mm"] == pytest.approx(9, abs=0.05)
    park = [0.082, 1.054, 0.717, -0.132, 0, 0]
    route["joint_targets"].insert(0, {"phase": "PARK", "joint_position_target_rad": park})
    route["contact_endpoint_sequences"] = [1]
    paths.route.write_text(json.dumps(route))
    connected = audit._connected_stroke(route, paths)
    assert connected["waypoints_rad"][0] == connected["waypoints_rad"][-1] == park
    assert connected["clearance_segments"] == len(connected["waypoints_rad"]) - 1
    assert connected["approach_return_minimum_tool_clearance_mm"] > 0.5
    assert connected["arm_workcell_clearance"]["keyboard_envelope"]["segments_unresolved"] == 0
    route["source_bindings"]["virtual_profile_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="profile or keyboard layout"):
        audit._corrected_space_cycle(route, paths)
