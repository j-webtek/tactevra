from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    ROOT / "software/integrations/isaac_sim/nominal_route_native_sweep_binding.py"
)
URDF_PATH = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"


def _module():
    integration = str(MODULE_PATH.parent)
    if integration not in sys.path:
        sys.path.insert(0, integration)
    spec = importlib.util.spec_from_file_location("arm262_binding", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sources(module):
    spheres = []
    for index, name in enumerate(module.PROFILE_TO_NATIVE_LINK):
        spheres.append(
            {
                "link_name": name,
                "local_center_mm": [float(index), 0.0, 0.0],
                "radius_mm": float(index + 1),
            }
        )
    profile_core = {
        "source_urdf_sha256": module.EXPECTED_URDF_SHA256,
        "link_spheres": spheres,
    }
    profile = {**profile_core, "profile_sha256": module._sha(profile_core)}
    policy_core = {
        "source_urdf_sha256": module.EXPECTED_URDF_SHA256,
        "accepted_exclusion_pairs": [
            [left, right]
            for left, right in zip(
                tuple(module.PROFILE_TO_NATIVE_LINK)[:-1],
                tuple(module.PROFILE_TO_NATIVE_LINK)[1:],
            )
        ],
    }
    policy = {**policy_core, "policy_sha256": module._sha(policy_core)}
    review_core = {
        "schema": module.REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_NATIVE_BINDING_IMPLEMENTATION",
        "native_binding_admitted": False,
        "certified_sphere_profile": profile,
        "accepted_pair_policy": policy,
    }
    review = {**review_core, "review_sha256": module._sha(review_core)}
    readiness_core = {
        "schema": module.READINESS_SCHEMA,
        "status": "READY_TO_IMPLEMENT_NATIVE_BINDING",
        "blockers": [],
        "launch_admitted": False,
        "attempt_consumed": False,
        "certified_proof_inputs": {
            "arm260_review_sha256": review["review_sha256"],
            "certified_sphere_profile_sha256": profile["profile_sha256"],
            "accepted_pair_policy_sha256": policy["policy_sha256"],
        },
    }
    readiness = {
        **readiness_core,
        "preflight_sha256": module._sha(readiness_core),
    }
    module.EXPECTED_READINESS_SHA256 = readiness["preflight_sha256"]
    module.EXPECTED_REVIEW_SHA256 = review["review_sha256"]
    module.EXPECTED_PROFILE_SHA256 = profile["profile_sha256"]
    module.EXPECTED_POLICY_SHA256 = policy["policy_sha256"]
    return readiness, review


def _definition(module):
    readiness, review = _sources(module)
    return module.build_binding_definition(
        readiness,
        review,
        readiness_file_sha256=module.EXPECTED_READINESS_FILE_SHA256,
        review_file_sha256=module.EXPECTED_REVIEW_FILE_SHA256,
        urdf_file_sha256=module._file_sha(URDF_PATH),
        binding_source_file_sha256=module._file_sha(MODULE_PATH),
        urdf_text=URDF_PATH.read_text(encoding="utf-8"),
    )


class _Array:
    def __init__(self, value):
        self._value = value

    def numpy(self):
        return self

    def tolist(self):
        return self._value


class _View:
    def __init__(self, articulation):
        self.articulation = articulation

    def get_link_transforms(self):
        rows = []
        offset = self.articulation.positions[0] if self.articulation.positions else 0.0
        for index, _name in enumerate(self.articulation.link_names):
            rows.append(
                [offset + index / 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
            )
        return _Array([rows])


class _Articulation:
    dof_names = (
        "base_link_to_link1",
        "link1_to_link2",
        "link2_to_link3",
        "link3_to_link4",
        "link4_to_link5",
        "link5_to_gripper_link",
    )
    link_names = (
        "base_link",
        "link1",
        "link2",
        "link3",
        "link4",
        "link5",
        "gripper_link",
    )

    def __init__(self):
        self.positions = []
        self._physics_articulation_view = _View(self)

    def get_link_transforms(self):
        return self._physics_articulation_view.get_link_transforms()

    def set_dof_positions(self, rows):
        self.positions = list(rows[0])


class _PublicArticulationView:
    """Match the narrow wrapper supplied by the native Isaac session."""

    def __init__(self, articulation):
        self._articulation = articulation

    @property
    def dof_names(self):
        return self._articulation.dof_names

    @property
    def link_names(self):
        return self._articulation.link_names

    def get_link_transforms(self):
        return self._articulation.get_link_transforms()

    def set_dof_positions(self, rows):
        self._articulation.set_dof_positions(rows)


class _Query:
    def __init__(self, result=False, overlaps=()):
        self.result = result
        self.overlaps = list(overlaps)
        self.calls = []

    def overlap_sphere_any(self, *args):
        self.calls.append(("overlap", *args))
        return self.overlaps.pop(0) if self.overlaps else False

    def sweep_sphere_any(self, *args):
        self.calls.append(("sweep", *args))
        return self.result


def _runtime(module, *, query=None, articulation=None):
    definition = _definition(module)
    review_core = {
        "schema": module.BINDING_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_NATIVE_BINDING_INTEGRATION",
        "source_binding_sha256": definition["binding_sha256"],
        "runtime_instantiation_admitted": True,
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    binding_review = {
        **review_core,
        "binding_review_sha256": module._sha(review_core),
    }
    return module.NativeIsaacConservativeSweepBinding(
        definition,
        binding_review=binding_review,
        articulation=articulation or _Articulation(),
        scene_query=query or _Query(),
        environment_only_scene=True,
        robot_collision_query_shapes_enabled=False,
    )


def test_arm262_definition_pins_certified_lineage_and_derives_bounds():
    module = _module()
    result = _definition(module)

    assert result["status"] == "READY_FOR_INDEPENDENT_NATIVE_BINDING_REVIEW"
    assert result["source_readiness_sha256"] == module.EXPECTED_READINESS_SHA256
    assert result["source_review_sha256"] == module.EXPECTED_REVIEW_SHA256
    assert len(result["link_spheres"]) == 7
    assert len(result["accepted_exclusion_pairs"]) == 6
    assert result["path_lipschitz_mm_per_rad"]["robot:base_link"] == {}
    assert set(result["path_lipschitz_mm_per_rad"]["robot:gripper"]) == set(
        module.EXPECTED_DOF_NAMES
    )
    assert result["launch_admitted"] is False
    assert result["attempt_consumed"] is False
    assert result["physical_authority"] is False


@pytest.mark.parametrize("source", ["readiness", "review"])
def test_arm262_definition_rejects_self_consistent_source_substitution(source):
    module = _module()
    readiness, review = _sources(module)
    changed = readiness if source == "readiness" else review
    changed["status"] = "SUBSTITUTED"
    key = "preflight_sha256" if source == "readiness" else "review_sha256"
    unsigned = dict(changed)
    unsigned.pop(key)
    changed[key] = module._sha(unsigned)

    with pytest.raises(module.NativeSweepBindingError, match="source contract"):
        module.build_binding_definition(
            readiness,
            review,
            readiness_file_sha256=module.EXPECTED_READINESS_FILE_SHA256,
            review_file_sha256=module.EXPECTED_REVIEW_FILE_SHA256,
            urdf_file_sha256=module._file_sha(URDF_PATH),
            binding_source_file_sha256="1" * 64,
            urdf_text=URDF_PATH.read_text(encoding="utf-8"),
        )


def test_arm262_runtime_uses_native_fk_and_conservative_path_bound():
    module = _module()
    runtime = _runtime(module)
    bounds = runtime.bound_link_spheres(
        start_joint_targets_rad=[0.0] * 6,
        end_joint_targets_rad=[0.01] * 6,
    )

    assert len(bounds) == 7
    assert bounds[0].link_name == "robot:base_link"
    assert bounds[0].max_center_path_deviation_mm == 0.0
    assert bounds[-1].max_center_path_deviation_mm > 0.0
    assert bounds[-1].end_center_mm[0] - bounds[-1].start_center_mm[0] == pytest.approx(
        10.0
    )


def test_arm262_runtime_converts_mm_to_native_metre_sweep():
    module = _module()
    query = _Query(result=True)
    runtime = _runtime(module, query=query)

    assert (
        runtime.sweep_sphere_any(
            start_center_mm=[100.0, 200.0, 300.0],
            end_center_mm=[100.0, 200.0, 400.0],
            radius_mm=25.0,
            moving_link="robot:link2",
        )
        is True
    )
    assert query.calls == [
        ("overlap", 0.025, (0.1, 0.2, 0.3)),
        ("sweep", 0.025, (0.1, 0.2, 0.3), (0.0, 0.0, 1.0), 0.1, True),
        ("overlap", 0.025, (0.1, 0.2, 0.4)),
    ]


def test_arm262_runtime_checks_stationary_overlap_without_zero_length_sweep():
    module = _module()
    query = _Query(overlaps=[True])
    runtime = _runtime(module, query=query)

    assert runtime.sweep_sphere_any(
        start_center_mm=[0.0, 0.0, 0.0],
        end_center_mm=[0.0, 0.0, 0.0],
        radius_mm=10.0,
        moving_link="robot:base_link",
    ) is True
    assert query.calls == [("overlap", 0.01, (0.0, 0.0, 0.0))]


def test_arm262_runtime_self_collision_is_continuous_and_exclusion_scoped():
    module = _module()
    runtime = _runtime(module)
    bound = module.SphereIntervalBound
    rows = [
        bound(
            name,
            (10000.0 + index * 1000.0, 0.0, 0.0),
            (10000.0 + index * 1000.0, 0.0, 0.0),
            1.0,
            0.0,
        )
        for index, name in enumerate(module.PROFILE_TO_NATIVE_LINK)
    ]
    rows[2] = bound(
        "robot:link2", (10.0, -10.0, 0.0), (10.0, 10.0, 0.0), 2.0, 0.0
    )
    rows[4] = bound(
        "robot:link4", (0.0, 0.0, 0.0), (20.0, 0.0, 0.0), 2.0, 0.0
    )

    certified = runtime._excluded_pairs
    assert runtime.moving_self_collision_any(
        bounds=rows, excluded_pairs=certified
    ) == ("robot:link2", "robot:link4")
    changed = frozenset(set(certified) | {("robot:link2", "robot:link4")})
    with pytest.raises(module.NativeSweepBindingError, match="certified policy"):
        runtime.moving_self_collision_any(bounds=rows, excluded_pairs=changed)


def test_arm262_runtime_honors_a_certified_exclusion():
    module = _module()
    runtime = _runtime(module)
    bound = module.SphereIntervalBound
    rows = [
        bound(
            name,
            (10000.0 + index * 1000.0, 0.0, 0.0),
            (10000.0 + index * 1000.0, 0.0, 0.0),
            1.0,
            0.0,
        )
        for index, name in enumerate(module.PROFILE_TO_NATIVE_LINK)
    ]
    excluded = next(iter(runtime._excluded_pairs))
    for name in excluded:
        index = list(module.PROFILE_TO_NATIVE_LINK).index(name)
        rows[index] = bound(name, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 2.0, 0.0)
    assert (
        runtime.moving_self_collision_any(
            bounds=rows,
            excluded_pairs=runtime._excluded_pairs,
        )
        is None
    )


def test_arm262_runtime_requires_environment_only_query_scene():
    module = _module()
    definition = _definition(module)
    review_core = {
        "schema": module.BINDING_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_NATIVE_BINDING_INTEGRATION",
        "source_binding_sha256": definition["binding_sha256"],
        "runtime_instantiation_admitted": True,
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    with pytest.raises(module.NativeSweepBindingError, match="not admissible"):
        module.NativeIsaacConservativeSweepBinding(
            definition,
            binding_review={
                **review_core,
                "binding_review_sha256": module._sha(review_core),
            },
            articulation=_Articulation(),
            scene_query=_Query(),
            environment_only_scene=False,
            robot_collision_query_shapes_enabled=True,
        )


def test_arm262_runtime_uses_reviewed_public_link_transform_protocol():
    module = _module()
    native = _Articulation()
    public_view = _PublicArticulationView(native)
    runtime = _runtime(module, articulation=public_view)

    assert not hasattr(runtime._articulation, "_physics_articulation_view")
    centers = runtime._world_centers([0.25, 0.0, 0.0, 0.0, 0.0, 0.0])

    assert native.positions == [0.25, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert set(centers) == set(module.PROFILE_TO_NATIVE_LINK)


def test_arm262_runtime_rejects_missing_public_link_transform_protocol():
    module = _module()
    definition = _definition(module)
    review_core = {
        "schema": module.BINDING_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_NATIVE_BINDING_INTEGRATION",
        "source_binding_sha256": definition["binding_sha256"],
        "runtime_instantiation_admitted": True,
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    articulation = _Articulation()
    articulation.get_link_transforms = None

    with pytest.raises(module.NativeSweepBindingError, match="not admissible"):
        module.NativeIsaacConservativeSweepBinding(
            definition,
            binding_review={
                **review_core,
                "binding_review_sha256": module._sha(review_core),
            },
            articulation=articulation,
            scene_query=_Query(),
            environment_only_scene=True,
            robot_collision_query_shapes_enabled=False,
        )


def test_arm262_runtime_rejects_unreviewed_binding():
    module = _module()
    definition = _definition(module)
    review_core = {
        "schema": module.BINDING_REVIEW_SCHEMA,
        "status": "PENDING_INDEPENDENT_REVIEW",
        "source_binding_sha256": definition["binding_sha256"],
        "runtime_instantiation_admitted": False,
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    with pytest.raises(module.NativeSweepBindingError, match="not admissible"):
        module.NativeIsaacConservativeSweepBinding(
            definition,
            binding_review={
                **review_core,
                "binding_review_sha256": module._sha(review_core),
            },
            articulation=_Articulation(),
            scene_query=_Query(),
            environment_only_scene=True,
            robot_collision_query_shapes_enabled=False,
        )


def test_arm262_import_and_definition_cli_have_no_native_side_effect():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "from isaacsim import" not in source
    assert "SimulationApp(" not in source
    assert "serial" not in source
    assert "execute_backend(" not in source
