from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "software/integrations/isaac_sim/nominal_route_native_clearance_adapter.py"
ARTIFACTS = Path("C:/IsaacSim/artifacts/issue190")
PREFLIGHT = ARTIFACTS / "arm264-native-binding-integration-preflight-001/preflight.json"
BINDING = ARTIFACTS / "arm262-native-sweep-binding-003/binding.json"
BINDING_REVIEW = ARTIFACTS / "arm263-native-sweep-binding-review-001/review.json"


def _module():
    integration = str(SOURCE.parent)
    if integration not in sys.path:
        sys.path.insert(0, integration)
    spec = importlib.util.spec_from_file_location("arm265_adapter", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _definition(module):
    return module.build_adapter_definition(
        _load(PREFLIGHT),
        _load(BINDING),
        _load(BINDING_REVIEW),
        preflight_file_sha256=module._file_sha(PREFLIGHT),
        binding_file_sha256=module._file_sha(BINDING),
        binding_review_file_sha256=module._file_sha(BINDING_REVIEW),
        proof_source_file_sha256=module.EXPECTED_PROOF_SOURCE_SHA256,
        binding_source_file_sha256=module.EXPECTED_BINDING_SOURCE_SHA256,
        adapter_source_file_sha256=module._file_sha(SOURCE),
    )


class _Array:
    def __init__(self, value):
        self.value = value

    def numpy(self):
        return self

    def tolist(self):
        return self.value


class _View:
    def __init__(self, articulation):
        self.articulation = articulation

    def get_link_transforms(self):
        offset = self.articulation.positions[0] if self.articulation.positions else 0.0
        rows = [
            [offset + index * 10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
            for index in range(7)
        ]
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
    link_names = ("base_link", "link1", "link2", "link3", "link4", "link5", "gripper_link")

    def __init__(self):
        self.positions = []
        self._physics_articulation_view = _View(self)

    def set_dof_positions(self, rows):
        self.positions = list(rows[0])


class _Query:
    def overlap_sphere_any(self, *args):
        return False

    def sweep_sphere_any(self, *args):
        return False


def _review(module, definition):
    core = {
        "schema": module.ADAPTER_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "source_adapter_sha256": definition["adapter_sha256"],
        "runtime_integration_admitted": True,
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "adapter_review_sha256": module._sha(core)}


def test_arm265_definition_pins_reviewed_composition_boundary():
    module = _module()
    result = _definition(module)

    assert result["status"] == "READY_FOR_INDEPENDENT_NATIVE_CLEARANCE_ADAPTER_REVIEW"
    assert result["backend_method"] == "check_continuous_clearance"
    assert result["clearance_margin_mm"] == 0.5
    assert result["maximum_subdivision_depth"] == 12
    assert len(result["accepted_exclusion_pairs"]) == 6
    assert result["environment_only_scene_required"] is True
    assert result["integration_execution_admitted"] is False
    assert result["launch_admitted"] is False


def test_arm265_definition_rejects_self_consistent_lineage_substitution():
    module = _module()
    preflight = _load(PREFLIGHT)
    preflight["status"] = "SUBSTITUTED"
    unsigned = dict(preflight)
    unsigned.pop("integration_preflight_sha256")
    preflight["integration_preflight_sha256"] = module._sha(unsigned)

    with pytest.raises(module.NativeClearanceAdapterError, match="boundary changed"):
        module.build_adapter_definition(
            preflight,
            _load(BINDING),
            _load(BINDING_REVIEW),
            preflight_file_sha256=module.EXPECTED_PREFLIGHT_FILE_SHA256,
            binding_file_sha256=module.EXPECTED_BINDING_FILE_SHA256,
            binding_review_file_sha256=module.EXPECTED_BINDING_REVIEW_FILE_SHA256,
            proof_source_file_sha256=module.EXPECTED_PROOF_SOURCE_SHA256,
            binding_source_file_sha256=module.EXPECTED_BINDING_SOURCE_SHA256,
            adapter_source_file_sha256="1" * 64,
        )


def test_arm265_runtime_composes_native_binding_into_backend_method():
    module = _module()
    definition = _definition(module)
    runtime = module.NativeClearanceRuntimeAdapter(
        definition,
        adapter_review=_review(module, definition),
        binding_definition=_load(BINDING),
        binding_review=_load(BINDING_REVIEW),
        articulation=_Articulation(),
        scene_query=_Query(),
        environment_only_scene=True,
        robot_collision_query_shapes_enabled=False,
    )

    result = runtime.check_continuous_clearance(
        start_sequence=7,
        end_sequence=8,
        start_joint_targets_rad=[0.0] * 6,
        end_joint_targets_rad=[0.001] * 6,
    )
    assert result["continuous"] is True
    assert result["determinate"] is True
    assert result["minimum_clearance_mm"] == 0.5
    assert result["proof_method"] == "CONSERVATIVE_BOUNDING_SPHERE_INTERVAL_SWEEPS"


def test_arm265_runtime_requires_environment_only_scene():
    module = _module()
    definition = _definition(module)
    with pytest.raises(module.NativeClearanceAdapterError, match="not admissible"):
        module.NativeClearanceRuntimeAdapter(
            definition,
            adapter_review=_review(module, definition),
            binding_definition=_load(BINDING),
            binding_review=_load(BINDING_REVIEW),
            articulation=_Articulation(),
            scene_query=_Query(),
            environment_only_scene=False,
            robot_collision_query_shapes_enabled=True,
        )


def test_arm265_import_and_definition_cli_have_no_runtime_side_effect():
    source = SOURCE.read_text(encoding="utf-8")
    assert "from isaacsim import" not in source
    assert "SimulationApp(" not in source
    assert "execute_backend(" not in source
    assert "serial" not in source
