from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = (
    ROOT
    / "software/integrations/isaac_sim/"
    "nominal_route_native_inventory_recovery_plan.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("arm295_recovery_plan", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _signed(module, core, key):
    return {**core, key: module._sha(core)}


def _bundle(tmp_path: Path):
    module = _module()
    attempt = tmp_path / "arm295-nominal-route-physics-attempt-001"
    receipt_review_core = {
        "schema": module.RECEIPT_REVIEW_SCHEMA,
        "review_id": "arm294-native-link-inventory-receipt-review-001",
        "status": module.RECEIPT_REVIEW_STATUS,
        "verified_link_names": list(module.EXPECTED_LINK_NAMES),
        "verified_link_count": 7,
        "verified_transform_batch_count": 1,
        "verified_transform_count": 7,
        "source_isaac_started": True,
        "source_physics_steps": 0,
        "governed_attempt_directory": str(attempt),
        "governed_attempt_directory_absent": True,
        "route_attempt_admitted": False,
        "launch_admitted": False,
        "isaac_started": False,
        "attempt_consumed": False,
        "worker_invoked": False,
        "backend_invoked": False,
        "timeline_played": False,
        "physics_steps": 0,
        "trajectory_playback": False,
        "joint_positions_submitted": False,
        "joint_targets_submitted": False,
        "key_contact": False,
        "automatic_retry": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": (
            "REBUILD_NEWLY_NUMBERED_ROUTE_PHYSICS_LINEAGE_WITH_FRESH_GATES"
        ),
    }
    receipt_review = _signed(
        module, receipt_review_core, "receipt_review_sha256"
    )
    arm289_status = {
        "attempt_count": 1,
        "automatic_retry": False,
        "error_message": "native articulation link inventory changed",
        "error_stage": "construct_runtime",
        "error_type": "NativeSweepBindingError",
        "hardware_access": False,
        "physical_authority": False,
        "status": "FAILED_RETAINED_NO_RETRY",
    }
    kwargs = {
        "receipt_review_file_sha256": "a" * 64,
        "arm289_status_file_sha256": "b" * 64,
        "plan_source_file_sha256": "c" * 64,
        "runtime_sources_sha256": {
            key: f"{index:x}" * 64
            for index, key in enumerate(module.RUNTIME_SOURCE_KEYS, start=1)
        },
        "proposed_attempt_directory": attempt,
        "proposed_eula_receipt": (
            tmp_path / "arm295-eula-preflight-001" / "receipt.json"
        ),
        "proposed_memory_receipt": (
            tmp_path / "arm295-memory-preflight-001" / "receipt.json"
        ),
    }
    return module, receipt_review, arm289_status, kwargs


def test_builds_inert_arm295_lineage_plan(tmp_path):
    module, review, status, kwargs = _bundle(tmp_path)
    result = module.build_plan(review, status, **kwargs)

    assert result["status"] == "READY_FOR_INDEPENDENT_ARM295_LINEAGE_PLAN_REVIEW"
    assert result["required_authorization_statement"] == module.EXACT_AUTHORIZATION
    assert result["superseded_authorizations_reusable"] is False
    assert result["fresh_eula_preflight_required"] is True
    assert result["fresh_memory_preflight_required"] is True
    assert result["authorization_observed"] is False
    assert result["attempt_claimed"] is False
    assert result["isaac_started"] is False
    assert result["physics_steps"] == 0
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False
    assert not kwargs["proposed_attempt_directory"].exists()
    assert not kwargs["proposed_eula_receipt"].parent.exists()
    assert not kwargs["proposed_memory_receipt"].parent.exists()
    assert module._require_hash(result, "plan_sha256", "plan")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("status", "REJECTED", "receipt review boundary"),
        ("verified_link_names", ["base_link"], "receipt review boundary"),
        ("source_physics_steps", 1, "receipt review boundary"),
        ("route_attempt_admitted", True, "receipt review boundary"),
    ],
)
def test_rejects_receipt_review_drift(tmp_path, field, value, message):
    module, review, status, kwargs = _bundle(tmp_path)
    changed = copy.deepcopy(review)
    changed[field] = value
    changed.pop("receipt_review_sha256")
    changed["receipt_review_sha256"] = module._sha(changed)
    with pytest.raises(module.NativeInventoryRecoveryPlanError, match=message):
        module.build_plan(changed, status, **kwargs)


def test_rejects_tampered_receipt_review_hash(tmp_path):
    module, review, status, kwargs = _bundle(tmp_path)
    review["verified_transform_count"] = 6
    with pytest.raises(module.NativeInventoryRecoveryPlanError, match="hash changed"):
        module.build_plan(review, status, **kwargs)


def test_rejects_changed_arm289_terminal_evidence(tmp_path):
    module, review, status, kwargs = _bundle(tmp_path)
    status["error_type"] = "DifferentError"
    with pytest.raises(module.NativeInventoryRecoveryPlanError, match="ARM-289"):
        module.build_plan(review, status, **kwargs)


def test_rejects_incomplete_runtime_source_inventory(tmp_path):
    module, review, status, kwargs = _bundle(tmp_path)
    kwargs["runtime_sources_sha256"].pop("physics_worker")
    with pytest.raises(module.NativeInventoryRecoveryPlanError, match="inventory"):
        module.build_plan(review, status, **kwargs)


def test_rejects_existing_future_attempt_directory(tmp_path):
    module, review, status, kwargs = _bundle(tmp_path)
    kwargs["proposed_attempt_directory"].mkdir()
    with pytest.raises(module.NativeInventoryRecoveryPlanError, match="output"):
        module.build_plan(review, status, **kwargs)


def test_rejects_precreated_gate_directories(tmp_path):
    module, review, status, kwargs = _bundle(tmp_path)
    kwargs["proposed_eula_receipt"].parent.mkdir()
    with pytest.raises(module.NativeInventoryRecoveryPlanError, match="output"):
        module.build_plan(review, status, **kwargs)


def test_plan_source_has_no_isaac_or_transport_import():
    source = SOURCE.read_text(encoding="utf-8")
    import_lines = [line.strip() for line in source.splitlines() if "import " in line]
    assert all("isaac" not in line.lower() for line in import_lines)
    assert all("serial" not in line.lower() for line in import_lines)
    assert all("socket" not in line.lower() for line in import_lines)
