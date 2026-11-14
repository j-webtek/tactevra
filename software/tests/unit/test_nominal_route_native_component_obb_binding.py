from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
MODULE_PATH = INTEGRATION / "nominal_route_native_component_obb_binding.py"
PARTITION_PATH = (
    INTEGRATION / "evidence/roarm_m3_triangle_partition_link2_20261005.json"
)
URDF_PATH = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"


def _module():
    integration = str(INTEGRATION)
    if integration not in sys.path:
        sys.path.insert(0, integration)
    spec = importlib.util.spec_from_file_location("native_component_obb_binding", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _definition(module):
    return module.build_definition(
        json.loads(PARTITION_PATH.read_text(encoding="utf-8")),
        partition_file_sha256=module._file_sha(PARTITION_PATH),
        urdf_file_sha256=module._file_sha(URDF_PATH),
        binding_source_file_sha256=module._file_sha(MODULE_PATH),
        urdf_text=URDF_PATH.read_text(encoding="utf-8"),
    )


class _Array:
    def __init__(self, value):
        self.value = value

    def numpy(self):
        return self

    def tolist(self):
        return self.value


class _Articulation:
    def __init__(self, module):
        self.dof_names = module.EXPECTED_DOF_NAMES
        self.link_names = module.NATIVE_LINKS
        self.positions = None

    def set_dof_positions(self, rows):
        self.positions = rows

    def get_link_transforms(self):
        return _Array(
            [[
                [index / 10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
                for index, _name in enumerate(self.link_names)
            ]]
        )


def _review(module, definition):
    core = {
        "schema": module.REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_COMPONENT_OBB_RUNTIME_INTEGRATION",
        "source_binding_sha256": definition["binding_sha256"],
        "runtime_instantiation_admitted": True,
        "launch_admitted": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "review_sha256": module._sha(core)}


def test_definition_promotes_containment_not_finite_replay_or_never_pairs():
    module = _module()
    result = _definition(module)

    assert result["status"] == "READY_FOR_INDEPENDENT_COMPONENT_OBB_BINDING_REVIEW"
    assert len(result["component_obbs"]) == 29
    assert result["containment_contract"] == {
        "all_assigned_triangle_vertices_contained": True,
        "maximum_serialized_vertex_overflow_mm": 0.0,
        "continuous_method": "SAT_GAP_MINUS_EVERY_POINT_PATH_DEVIATION",
        "clearance_margin_mm": 0.5,
        "maximum_subdivision_depth": 12,
        "indeterminate_disposition": "FAIL_CLOSED",
    }
    assert result["finite_replay_promoted"] is False
    assert result["srdf_never_exclusions_promoted"] is False
    assert result["launch_admitted"] is False
    assert result["physical_authority"] is False


def test_definition_rejects_self_consistent_partition_substitution():
    module = _module()
    changed = json.loads(PARTITION_PATH.read_text(encoding="utf-8"))
    changed["summary"]["candidate_primitive_count"] = 28
    unsigned = dict(changed)
    unsigned.pop("receipt_sha256")
    changed["receipt_sha256"] = module._sha(unsigned)

    with pytest.raises(module.NativeComponentObbBindingError, match="source changed"):
        module.build_definition(
            changed,
            partition_file_sha256=module.EXPECTED_PARTITION_FILE_SHA256,
            urdf_file_sha256=module.EXPECTED_URDF_SHA256,
            binding_source_file_sha256="1" * 64,
            urdf_text=URDF_PATH.read_text(encoding="utf-8"),
        )


def test_definition_rejects_urdf_text_not_matching_claimed_digest():
    module = _module()
    text = URDF_PATH.read_text(encoding="utf-8")
    with pytest.raises(module.NativeComponentObbBindingError, match="source changed"):
        module.build_definition(
            json.loads(PARTITION_PATH.read_text(encoding="utf-8")),
            partition_file_sha256=module._file_sha(PARTITION_PATH),
            urdf_file_sha256=module._file_sha(URDF_PATH),
            binding_source_file_sha256=module._file_sha(MODULE_PATH),
            urdf_text=text + "\n<!-- substituted -->",
        )


@pytest.mark.parametrize("field", ["launch_admitted", "hardware_access", "physical_authority"])
def test_native_runtime_rejects_review_with_authority(field):
    module = _module()
    definition = _definition(module)
    review = _review(module, definition)
    review[field] = True
    review.pop("review_sha256")
    review["review_sha256"] = module._sha(review)
    with pytest.raises(module.NativeComponentObbBindingError, match="not admitted"):
        module.NativeComponentObbRuntime(
            definition, binding_review=review, articulation=_Articulation(module)
        )


def test_native_runtime_emits_world_obbs_and_conservative_path_bounds():
    module = _module()
    definition = _definition(module)
    articulation = _Articulation(module)
    runtime = module.NativeComponentObbRuntime(
        definition,
        binding_review=_review(module, definition),
        articulation=articulation,
    )

    bounds = runtime.bound_link_obbs(
        start_joint_targets_rad=[0.0] * 6,
        end_joint_targets_rad=[0.01] * 6,
    )

    assert len(bounds) == 29
    assert bounds[0].link_name == "robot:base_link"
    assert bounds[0].max_point_path_deviation_mm == 0.0
    assert bounds[-1].link_name == "robot:gripper"
    assert bounds[-1].max_point_path_deviation_mm > 0.0
    assert articulation.positions == [[0.0] * 6]
    assert runtime.excluded_pairs == frozenset(
        tuple(sorted(pair))
        for pair in definition["accepted_exclusion_pairs"]
    )


def test_native_runtime_rejects_unreviewed_instantiation():
    module = _module()
    definition = _definition(module)
    review = _review(module, definition)
    review["status"] = "UNREVIEWED"
    unsigned = dict(review)
    unsigned.pop("review_sha256")
    review["review_sha256"] = module._sha(unsigned)

    with pytest.raises(module.NativeComponentObbBindingError, match="not admitted"):
        module.NativeComponentObbRuntime(
            definition,
            binding_review=review,
            articulation=_Articulation(module),
        )


def test_component_point_bounds_cover_interpolated_urdf_motion():
    import itertools
    import math
    import random

    pytest.importorskip("scipy")
    sys.path.insert(0, str(ROOT / "software/src"))
    from rocell.geometry.urdf import JointPosition, UrdfModel

    audit_path = INTEGRATION / "arm301_source_route_obb_audit.py"
    spec = importlib.util.spec_from_file_location("component_bound_fk_fixture", audit_path)
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    module = _module()
    definition = _definition(module)
    runtime = module.NativeComponentObbRuntime(
        definition, binding_review=_review(module, definition),
        articulation=audit._OfflineArticulation(URDF_PATH),
    )
    model = UrdfModel.from_file(URDF_PATH)
    rng = random.Random(301)

    def point(transform, component, signs):
        local_rotation = component["local_rotation_row_major"]
        extents = component["half_extents_mm"]
        local = [component["local_center_mm"][i] + sum(
            local_rotation[i * 3 + j] * extents[j] * signs[j] for j in range(3)
        ) for i in range(3)]
        rotation = transform.rotation.matrix
        translation = transform.translation_mm
        return [getattr(translation, axis) + sum(
            rotation[i * 3 + j] * local[j] for j in range(3)
        ) for i, axis in enumerate(("x", "y", "z"))]

    for _ in range(8):
        start = [rng.uniform(-0.4, 0.4) for _ in range(5)] + [rng.uniform(0.3, 1.2)]
        end = [value + rng.uniform(-0.2, 0.2) for value in start]
        bounds = runtime.bound_link_obbs(start_joint_targets_rad=start, end_joint_targets_rad=end)
        transforms = []
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            positions = [a + fraction * (b - a) for a, b in zip(start, end)]
            transforms.append(model.forward_kinematics({
                name: JointPosition.radians(value)
                for name, value in zip(module.EXPECTED_DOF_NAMES, positions)
            }))
        for component, bound in zip(definition["component_obbs"], bounds):
            name = component["native_link_name"]
            for signs in itertools.product((-1, 1), repeat=3):
                origin = point(transforms[0][name], component, signs)
                for current in transforms[1:]:
                    target = point(current[name], component, signs)
                    distance = math.dist(origin, target)
                    assert distance <= bound.max_point_path_deviation_mm + 1e-7
