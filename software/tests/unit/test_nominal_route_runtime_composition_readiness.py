from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "software/integrations/isaac_sim/nominal_route_runtime_composition_readiness.py"


def _module(name="arm266_readiness"):
    spec = importlib.util.spec_from_file_location(name, SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _authority():
    return {
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }


def _inputs(module):
    backend_core = {
        "schema": module.BACKEND_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_BACKEND_AND_RUNTIME_ADAPTER_REVIEW",
        "runtime_protocol": {
            "canonical_ik": "ONE_ACCEPTED_DETERMINATE_RESULT_PER_REGENERATED_ROW",
            "continuous_clearance": "CONTINUOUS_QUERY_NOT_DISCRETE_SAMPLING",
            "tool_key_metrics": "ONE_DETERMINATE_RESULT_PER_REGENERATED_ROW",
            "root_drift": "ONE_DETERMINATE_TERMINAL_OBSERVATION",
            "all_outputs_before_shutdown": True,
        },
        "acceptance": {
            "minimum_noncontact_tool_key_clearance_mm": 0.5,
            "maximum_adjacent_joint_step_rad": 0.05,
        },
        **_authority(),
    }
    backend = {**backend_core, "backend_sha256": module._sha(backend_core)}
    adapter_core = {
        "schema": module.ADAPTER_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_NATIVE_CLEARANCE_ADAPTER_REVIEW",
        "backend_method": "check_continuous_clearance",
        "clearance_margin_mm": 0.5,
        "maximum_subdivision_depth": 12,
        "environment_only_scene_required": True,
        "robot_collision_query_shapes_enabled": False,
        **_authority(),
    }
    adapter = {**adapter_core, "adapter_sha256": module._sha(adapter_core)}
    review_core = {
        "schema": module.REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "source_adapter_sha256": adapter["adapter_sha256"],
        "runtime_integration_admitted": True,
        "next_required_stage": "PREPARE_ZERO_AUTHORITY_NOMINAL_ROUTE_RUNTIME_COMPOSITION",
        **_authority(),
    }
    review = {**review_core, "adapter_review_sha256": module._sha(review_core)}
    module.EXPECTED_BACKEND_SHA256 = backend["backend_sha256"]
    module.EXPECTED_ADAPTER_SHA256 = adapter["adapter_sha256"]
    module.EXPECTED_REVIEW_SHA256 = review["adapter_review_sha256"]
    module.EXPECTED_BACKEND_FILE_SHA256 = "1" * 64
    module.EXPECTED_ADAPTER_FILE_SHA256 = "2" * 64
    module.EXPECTED_REVIEW_FILE_SHA256 = "3" * 64
    return backend, adapter, review


def _build(module):
    backend, adapter, review = _inputs(module)
    return module.build_runtime_composition_readiness(
        backend,
        adapter,
        review,
        backend_file_sha256="1" * 64,
        adapter_file_sha256="2" * 64,
        review_file_sha256="3" * 64,
        backend_source_file_sha256="4" * 64,
        adapter_source_file_sha256="5" * 64,
        readiness_source_file_sha256="6" * 64,
    )


def test_arm266_orders_exact_remaining_runtime_methods():
    module = _module()
    result = _build(module)
    assert result["reviewed_methods"] == ["check_continuous_clearance"]
    assert result["remaining_methods"] == [
        "regenerate_row",
        "measure_tool_key",
        "root_drift",
    ]
    assert [item["method"] for item in result["ordered_implementation_stages"]] == result[
        "remaining_methods"
    ]
    assert result["next_required_stage"] == "IMPLEMENT_AND_REVIEW_CANONICAL_IK_ROW_ADAPTER"


def test_arm266_remains_zero_authority_and_fail_closed():
    module = _module()
    result = _build(module)
    assert result["composition_complete"] is False
    assert result["composition_execution_admitted"] is False
    assert result["launch_admitted"] is False
    assert result["attempt_consumed"] is False
    assert result["joint_targets_submitted"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False


def test_arm266_rejects_review_substitution_even_when_rehashed():
    module = _module()
    backend, adapter, review = _inputs(module)
    review["status"] = "SUBSTITUTED"
    unsigned = dict(review)
    unsigned.pop("adapter_review_sha256")
    review["adapter_review_sha256"] = module._sha(unsigned)
    with pytest.raises(module.RuntimeCompositionReadinessError, match="boundary changed"):
        module.build_runtime_composition_readiness(
            backend,
            adapter,
            review,
            backend_file_sha256="1" * 64,
            adapter_file_sha256="2" * 64,
            review_file_sha256="3" * 64,
            backend_source_file_sha256="4" * 64,
            adapter_source_file_sha256="5" * 64,
            readiness_source_file_sha256="6" * 64,
        )


def test_arm266_import_and_cli_have_no_runtime_side_effects():
    source = SOURCE.read_text(encoding="utf-8")
    assert "from isaacsim import" not in source
    assert "SimulationApp(" not in source
    assert "execute_backend(" not in source
    assert "NativeClearanceRuntimeAdapter(" not in source
