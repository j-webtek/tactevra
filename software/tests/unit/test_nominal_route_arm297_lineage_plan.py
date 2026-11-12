from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
PLAN_SOURCE = INTEGRATION / "nominal_route_arm297_lineage_plan.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_arm297_lineage_plan_review.py"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PLAN = _load_module("arm297_lineage_plan_test", PLAN_SOURCE)
REVIEW = _load_module("arm297_lineage_review_test", REVIEW_SOURCE)


def _evidence():
    gate_core = {
        "schema": PLAN.GATE_SCHEMA,
        "gate_id": "arm296-constructor-completeness-gate-001",
        "status": "PASS_CORRECTED_RUNTIME_CONSTRUCTOR_COMPLETENESS",
        "source_arm295_status_sha256": PLAN.EXPECTED_ARM295_STATUS_SHA256,
        "source_corrected_binding_sha256": "a" * 64,
        "former_failure_stage": "construct_runtime",
        "former_failure_crossed": True,
        "runtime_type": "CompleteRuntimeComposition",
        "shared_solver_identity_verified": True,
        "baseline_reads": {"key_view": 1, "root_view": 1},
        "protocol_calls": {"articulation": [], "scene_query": []},
        "attempt_consumed": False,
        "isaac_imported": False,
        "isaac_started": False,
        "physics_steps": 0,
        "runtime_methods_called": [],
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    gate = {**gate_core, "gate_sha256": PLAN._sha(gate_core)}
    review_core = {
        "schema": PLAN.REVIEW_SCHEMA,
        "review_id": "arm296-constructor-completeness-gate-review-001",
        "status": "ACCEPTED_CORRECTED_RUNTIME_CONSTRUCTOR_COMPLETENESS",
        "source_gate_sha256": gate["gate_sha256"],
        "former_arm295_constructor_failure_crossed": True,
        "production_solver_and_runtime_components_verified": True,
        "shared_solver_identity_verified": True,
        "attempt_consumed": False,
        "isaac_started": False,
        "physics_steps": 0,
        "runtime_methods_called": [],
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "hardware_access": False,
        "physical_authority": False,
        "next_required_stage": (
            "PLAN_NEW_SEPARATELY_AUTHORIZED_NOMINAL_ROUTE_SIMULATION_LINEAGE"
        ),
    }
    review = {**review_core, "gate_review_sha256": PLAN._sha(review_core)}
    return gate, review


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _runtime_sources(tmp_path: Path):
    sources = {}
    for key in PLAN.RUNTIME_SOURCE_KEYS:
        path = tmp_path / "sources" / f"{key}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {key}\n", encoding="utf-8")
        sources[key] = path
    return sources


def _build(tmp_path: Path, monkeypatch):
    gate, gate_review = _evidence()
    gate_file = tmp_path / "arm296" / "receipt.json"
    review_file = tmp_path / "arm296-review" / "review.json"
    _write_json(gate_file, gate)
    _write_json(review_file, gate_review)
    sources = _runtime_sources(tmp_path)
    source_hashes = {key: PLAN._file_sha(path) for key, path in sources.items()}
    binding_hash = source_hashes["concrete_native_attempt_binding"]
    for module in (PLAN, REVIEW):
        monkeypatch.setattr(module, "EXPECTED_GATE_SHA256", gate["gate_sha256"])
        monkeypatch.setattr(
            module, "EXPECTED_REVIEW_SHA256", gate_review["gate_review_sha256"]
        )
        monkeypatch.setattr(
            module, "EXPECTED_GATE_FILE_SHA256", PLAN._file_sha(gate_file)
        )
        monkeypatch.setattr(
            module, "EXPECTED_REVIEW_FILE_SHA256", PLAN._file_sha(review_file)
        )
        monkeypatch.setattr(
            module, "EXPECTED_CORRECTED_BINDING_SHA256", binding_hash
        )
    monkeypatch.setattr(PLAN, "EXPECTED_CORRECTED_BINDING_SHA256", binding_hash)
    gate["source_corrected_binding_sha256"] = binding_hash
    gate_core = dict(gate)
    gate_core.pop("gate_sha256")
    gate["gate_sha256"] = PLAN._sha(gate_core)
    gate_review["source_gate_sha256"] = gate["gate_sha256"]
    review_core = dict(gate_review)
    review_core.pop("gate_review_sha256")
    gate_review["gate_review_sha256"] = PLAN._sha(review_core)
    _write_json(gate_file, gate)
    _write_json(review_file, gate_review)
    for module in (PLAN, REVIEW):
        monkeypatch.setattr(module, "EXPECTED_GATE_SHA256", gate["gate_sha256"])
        monkeypatch.setattr(
            module, "EXPECTED_REVIEW_SHA256", gate_review["gate_review_sha256"]
        )
        monkeypatch.setattr(
            module, "EXPECTED_GATE_FILE_SHA256", PLAN._file_sha(gate_file)
        )
        monkeypatch.setattr(
            module, "EXPECTED_REVIEW_FILE_SHA256", PLAN._file_sha(review_file)
        )

    artifact = tmp_path / "future"
    attempt = artifact / "arm297-nominal-route-physics-attempt-001"
    eula = (
        artifact
        / "arm297-nominal-route-physics-eula-preflight-001"
        / "receipt.json"
    )
    memory = (
        artifact
        / "arm297-nominal-route-physics-memory-preflight-001"
        / "receipt.json"
    )
    plan = PLAN.build_arm297_lineage_plan(
        gate,
        gate_review,
        gate_file_sha256=PLAN._file_sha(gate_file),
        review_file_sha256=PLAN._file_sha(review_file),
        plan_source_file_sha256=PLAN._file_sha(PLAN_SOURCE),
        runtime_sources_sha256=source_hashes,
        proposed_attempt_directory=attempt,
        proposed_eula_receipt=eula,
        proposed_memory_receipt=memory,
    )
    return plan, gate_file, review_file, sources


def test_arm297_plan_and_review_bind_corrected_lineage_without_authority(
    tmp_path, monkeypatch
):
    plan, gate_file, review_file, sources = _build(tmp_path, monkeypatch)
    plan_file = tmp_path / "plan" / "plan.json"
    _write_json(plan_file, plan)
    review = REVIEW.review_arm297_lineage_plan(
        plan,
        plan_file_sha256=REVIEW._file_sha(plan_file),
        plan_source=PLAN_SOURCE,
        gate_receipt_file=gate_file,
        gate_review_file=review_file,
        runtime_sources=sources,
        review_source_file_sha256=REVIEW._file_sha(REVIEW_SOURCE),
    )
    assert plan["required_authorization_statement"].startswith(
        "I authorize exactly one ARM-297"
    )
    assert plan["arm295_replay_permitted"] is False
    assert plan["attempt_claimed"] is False
    assert plan["physics_steps"] == 0
    assert plan["hardware_access"] is False
    assert review["status"] == (
        "ACCEPTED_ARM297_LINEAGE_FOR_CLAIMANT_CONSTRUCTION"
    )
    assert review["proposed_attempt_directory_absent"] is True
    assert review["authorization_observed"] is False
    assert review["physical_authority"] is False


def test_arm297_plan_rejects_changed_constructor_evidence(tmp_path, monkeypatch):
    gate, gate_review = _evidence()
    gate["former_failure_crossed"] = False
    gate_core = dict(gate)
    gate_core.pop("gate_sha256")
    gate["gate_sha256"] = PLAN._sha(gate_core)
    monkeypatch.setattr(PLAN, "EXPECTED_GATE_SHA256", gate["gate_sha256"])
    with pytest.raises(PLAN.Arm297LineagePlanError, match="gate boundary"):
        PLAN.build_arm297_lineage_plan(
            gate,
            gate_review,
            gate_file_sha256=PLAN.EXPECTED_GATE_FILE_SHA256,
            review_file_sha256=PLAN.EXPECTED_REVIEW_FILE_SHA256,
            plan_source_file_sha256="a" * 64,
            runtime_sources_sha256={key: "a" * 64 for key in PLAN.RUNTIME_SOURCE_KEYS},
            proposed_attempt_directory=(tmp_path / "arm297-nominal-route-physics-attempt-001").resolve(),
            proposed_eula_receipt=(tmp_path / "arm297-nominal-route-physics-eula-preflight-001/receipt.json").resolve(),
            proposed_memory_receipt=(tmp_path / "arm297-nominal-route-physics-memory-preflight-001/receipt.json").resolve(),
        )


def test_arm297_review_rejects_runtime_source_drift(tmp_path, monkeypatch):
    plan, gate_file, review_file, sources = _build(tmp_path, monkeypatch)
    plan_file = tmp_path / "plan" / "plan.json"
    _write_json(plan_file, plan)
    sources["physics_worker"].write_text("# changed\n", encoding="utf-8")
    with pytest.raises(REVIEW.Arm297LineagePlanReviewError, match="source binding"):
        REVIEW.review_arm297_lineage_plan(
            plan,
            plan_file_sha256=REVIEW._file_sha(plan_file),
            plan_source=PLAN_SOURCE,
            gate_receipt_file=gate_file,
            gate_review_file=review_file,
            runtime_sources=sources,
            review_source_file_sha256=REVIEW._file_sha(REVIEW_SOURCE),
        )


def test_arm297_sources_have_no_simulation_or_hardware_authority():
    plan_source = PLAN_SOURCE.read_text(encoding="utf-8")
    assert "import isaacsim" not in plan_source
    assert "SimulationApp(" not in plan_source
    assert "serial.Serial" not in plan_source
    assert "run_one_attempt(" not in plan_source
    static = REVIEW._static_review(PLAN_SOURCE)
    assert static["runtime_motion_and_transport_calls_absent"] is True
