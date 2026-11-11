from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software" / "integrations" / "isaac_sim"
PLAN_SOURCE = INTEGRATION / "nominal_route_native_inventory_recovery_plan.py"
REVIEW_SOURCE = (
    INTEGRATION / "nominal_route_native_inventory_recovery_plan_review.py"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PLAN = _load("arm295_plan_for_review", PLAN_SOURCE)
REVIEW = _load("arm295_plan_review", REVIEW_SOURCE)


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _evidence(tmp_path: Path):
    attempt = tmp_path / "future" / "arm295-nominal-route-physics-attempt-001"
    receipt_core = {
        "schema": PLAN.RECEIPT_REVIEW_SCHEMA,
        "review_id": "arm294-native-link-inventory-receipt-review-001",
        "status": PLAN.RECEIPT_REVIEW_STATUS,
        "verified_link_names": list(PLAN.EXPECTED_LINK_NAMES),
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
    receipt_review = {
        **receipt_core,
        "receipt_review_sha256": PLAN._sha(receipt_core),
    }
    status = {
        "attempt_count": 1,
        "automatic_retry": False,
        "error_message": "native articulation link inventory changed",
        "error_stage": "construct_runtime",
        "error_type": "NativeSweepBindingError",
        "hardware_access": False,
        "physical_authority": False,
        "status": "FAILED_RETAINED_NO_RETRY",
    }
    receipt_path = tmp_path / "retained" / "arm294-review.json"
    status_path = tmp_path / "retained" / "arm289-status.json"
    _write(receipt_path, receipt_review)
    _write(status_path, status)
    runtime_sources = {}
    for index, key in enumerate(PLAN.RUNTIME_SOURCE_KEYS):
        path = tmp_path / "sources" / f"{key}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# source {index}: {key}\n", encoding="utf-8")
        runtime_sources[key] = path
    plan = PLAN.build_plan(
        receipt_review,
        status,
        receipt_review_file_sha256=PLAN._file_sha(receipt_path),
        arm289_status_file_sha256=PLAN._file_sha(status_path),
        plan_source_file_sha256=PLAN._file_sha(PLAN_SOURCE),
        runtime_sources_sha256={
            key: PLAN._file_sha(path) for key, path in runtime_sources.items()
        },
        proposed_attempt_directory=attempt,
        proposed_eula_receipt=(
            tmp_path / "future" / "arm295-eula-preflight-001" / "receipt.json"
        ),
        proposed_memory_receipt=(
            tmp_path / "future" / "arm295-memory-preflight-001" / "receipt.json"
        ),
    )
    plan_path = tmp_path / "retained" / "arm295-plan.json"
    _write(plan_path, plan)
    return {
        "plan": plan,
        "plan_path": plan_path,
        "receipt_path": receipt_path,
        "status_path": status_path,
        "runtime_sources": runtime_sources,
        "attempt": attempt,
    }


def _review(data):
    return REVIEW.review_plan(
        data["plan"],
        plan_file_sha256=REVIEW._file_sha(data["plan_path"]),
        plan_source=PLAN_SOURCE,
        receipt_review_file=data["receipt_path"],
        arm289_status_file=data["status_path"],
        runtime_sources=data["runtime_sources"],
        review_source_file_sha256=REVIEW._file_sha(REVIEW_SOURCE),
    )


def test_accepts_exact_inert_arm295_lineage_plan(tmp_path):
    data = _evidence(tmp_path)
    result = _review(data)

    assert result["status"] == (
        "ACCEPTED_FOR_FRESH_PREFLIGHT_AND_CLAIMANT_CONSTRUCTION"
    )
    assert result["source_plan_sha256"] == data["plan"]["plan_sha256"]
    assert result["required_authorization_statement"] == REVIEW.EXPECTED_AUTHORIZATION
    assert result["proposed_attempt_directory_absent"] is True
    assert result["authorization_observed"] is False
    assert result["attempt_claimed"] is False
    assert result["isaac_started"] is False
    assert result["physics_steps"] == 0
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False
    assert REVIEW._require_hash(result, "review_sha256", "review")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("status", "REJECTED", "plan boundary"),
        ("target_id", "ENTER", "plan boundary"),
        ("superseded_authorizations_reusable", True, "plan boundary"),
        ("authorization_observed", True, "plan boundary"),
        ("physics_steps", 1, "plan boundary"),
    ],
)
def test_rejects_resigned_plan_boundary_drift(tmp_path, field, value, message):
    data = _evidence(tmp_path)
    changed = copy.deepcopy(data["plan"])
    changed[field] = value
    changed.pop("plan_sha256")
    changed["plan_sha256"] = REVIEW._sha(changed)
    data["plan"] = changed
    _write(data["plan_path"], changed)
    with pytest.raises(REVIEW.NativeInventoryRecoveryPlanReviewError, match=message):
        _review(data)


def test_rejects_tampered_plan_hash(tmp_path):
    data = _evidence(tmp_path)
    data["plan"]["target_id"] = "ENTER"
    with pytest.raises(
        REVIEW.NativeInventoryRecoveryPlanReviewError, match="hash changed"
    ):
        _review(data)


def test_rejects_runtime_source_drift(tmp_path):
    data = _evidence(tmp_path)
    data["runtime_sources"]["native_sweep_binding"].write_text(
        "# drift\n", encoding="utf-8"
    )
    with pytest.raises(
        REVIEW.NativeInventoryRecoveryPlanReviewError, match="file binding"
    ):
        _review(data)


def test_rejects_retained_receipt_review_file_drift(tmp_path):
    data = _evidence(tmp_path)
    data["receipt_path"].write_text("{}\n", encoding="utf-8")
    with pytest.raises(
        REVIEW.NativeInventoryRecoveryPlanReviewError, match="receipt review"
    ):
        _review(data)


def test_rejects_resigned_retained_receipt_semantic_drift(tmp_path):
    data = _evidence(tmp_path)
    receipt = json.loads(data["receipt_path"].read_text(encoding="utf-8"))
    receipt["source_physics_steps"] = 1
    receipt.pop("receipt_review_sha256")
    receipt["receipt_review_sha256"] = REVIEW._sha(receipt)
    _write(data["receipt_path"], receipt)
    data["plan"]["source_arm294_receipt_review_sha256"] = receipt[
        "receipt_review_sha256"
    ]
    data["plan"]["source_arm294_receipt_review_file_sha256"] = REVIEW._file_sha(
        data["receipt_path"]
    )
    data["plan"].pop("plan_sha256")
    data["plan"]["plan_sha256"] = REVIEW._sha(data["plan"])
    _write(data["plan_path"], data["plan"])
    with pytest.raises(
        REVIEW.NativeInventoryRecoveryPlanReviewError,
        match="retained receipt review boundary",
    ):
        _review(data)


def test_rejects_retained_arm289_semantic_drift(tmp_path):
    data = _evidence(tmp_path)
    status = json.loads(data["status_path"].read_text(encoding="utf-8"))
    status["error_type"] = "DifferentError"
    _write(data["status_path"], status)
    data["plan"]["source_arm289_status_file_sha256"] = REVIEW._file_sha(
        data["status_path"]
    )
    data["plan"].pop("plan_sha256")
    data["plan"]["plan_sha256"] = REVIEW._sha(data["plan"])
    _write(data["plan_path"], data["plan"])
    with pytest.raises(
        REVIEW.NativeInventoryRecoveryPlanReviewError,
        match="terminal evidence changed",
    ):
        _review(data)


def test_rejects_attempt_directory_created_after_plan(tmp_path):
    data = _evidence(tmp_path)
    data["attempt"].mkdir(parents=True)
    with pytest.raises(
        REVIEW.NativeInventoryRecoveryPlanReviewError, match="output boundary"
    ):
        _review(data)


def test_reviewer_source_has_no_isaac_or_transport_import():
    source = REVIEW_SOURCE.read_text(encoding="utf-8")
    import_lines = [line.strip() for line in source.splitlines() if "import " in line]
    assert all("isaac" not in line.lower() for line in import_lines)
    assert all("serial" not in line.lower() for line in import_lines)
    assert all("socket" not in line.lower() for line in import_lines)
