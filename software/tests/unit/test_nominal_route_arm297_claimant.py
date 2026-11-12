from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software" / "integrations" / "isaac_sim"
SOURCE = INTEGRATION / "nominal_route_arm297_claimant.py"
REVIEW_SOURCE = (
    INTEGRATION / "nominal_route_arm297_claimant_review.py"
)
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CLAIMANT = _load("arm297_claimant", SOURCE)
REVIEW = _load("arm297_claimant_review_for_runtime", REVIEW_SOURCE)


def _signed(module, core, key):
    return {**core, key: module._sha(core)}


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _bundle(tmp_path: Path):
    attempt = tmp_path / "future" / "arm297-nominal-route-physics-attempt-001"
    eula_receipt = (
        tmp_path
        / "future"
        / "arm297-nominal-route-physics-eula-preflight-001"
        / "receipt.json"
    )
    memory_receipt = (
        tmp_path
        / "future"
        / "arm297-nominal-route-physics-memory-preflight-001"
        / "receipt.json"
    )
    runtime_sources = {
        key: f"{index:x}" * 64
        for index, key in enumerate(CLAIMANT.RUNTIME_SOURCE_KEYS, start=1)
    }
    plan_core = {
        "schema": CLAIMANT.PLAN_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_ARM297_LINEAGE_PLAN_REVIEW",
        "required_authorization_statement": CLAIMANT.EXACT_AUTHORIZATION,
        "superseded_authorizations_reusable": False,
        "arm295_replay_permitted": False,
        "arm296_is_attempt_authority": False,
        "claimant_review_required_before_authorization": True,
        "fresh_eula_preflight_required": True,
        "fresh_memory_preflight_required": True,
        "preflights_must_precede_attempt_claim": True,
        "terminal_status_must_precede_simulator_shutdown": True,
        "attempt_consumed": False,
        "claimant_constructed": False,
        "isaac_imported": False,
        "scene_loaded": False,
        "runtime_methods_called": [],
        "next_required_stage": "INDEPENDENT_ARM297_LINEAGE_PLAN_REVIEW",
        "runtime_sources_sha256": runtime_sources,
        "proposed_attempt_directory": str(attempt),
        "proposed_eula_receipt": str(eula_receipt),
        "proposed_memory_receipt": str(memory_receipt),
        **CLAIMANT.ZERO_AUTHORITY,
    }
    plan = _signed(CLAIMANT, plan_core, "plan_sha256")
    plan_path = tmp_path / "retained" / "plan.json"
    _write(plan_path, plan)
    plan_review_core = {
        "schema": CLAIMANT.PLAN_REVIEW_SCHEMA,
        "status": "ACCEPTED_ARM297_LINEAGE_FOR_CLAIMANT_CONSTRUCTION",
        "source_plan_sha256": plan["plan_sha256"],
        "source_plan_file_sha256": CLAIMANT._file_sha(plan_path),
        "proposed_attempt_directory": str(attempt),
        "proposed_attempt_directory_absent": True,
        "proposed_eula_receipt": str(eula_receipt),
        "proposed_eula_receipt_absent": True,
        "proposed_memory_receipt": str(memory_receipt),
        "proposed_memory_receipt_absent": True,
        "required_authorization_statement": CLAIMANT.EXACT_AUTHORIZATION,
        "attempt_consumed": False,
        "claimant_constructed": False,
        "isaac_imported": False,
        "scene_loaded": False,
        "runtime_methods_called": [],
        "next_required_stage": (
            "BUILD_SINGLE_USE_ARM297_CLAIMANT_AND_INDEPENDENT_REVIEW"
        ),
        **CLAIMANT.ZERO_AUTHORITY,
    }
    plan_review = _signed(CLAIMANT, plan_review_core, "lineage_review_sha256")
    plan_review_path = tmp_path / "retained" / "plan-review.json"
    _write(plan_review_path, plan_review)
    base_worker_core = {
        "schema": CLAIMANT.PREPARATION_SCHEMA,
        "worker_id": "arm254-space-nominal-route-physics-worker-001",
        "status": "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW",
        "required_authorization_statement": CLAIMANT.INTERNAL_WORKER_AUTHORIZATION,
        "proposed_output_directory": "C:/old/arm289-attempt-001",
        "attempt_ledger": {
            "maximum_attempt_count": 1,
            "attempts_consumed_by_preparation": 0,
            "automatic_retry": False,
        },
        "source_files_sha256": {"route_plan": "a" * 64},
        "runtime_bindings_sha256": {"robot_usd": "b" * 64},
        "isaac_backend_implemented_by_this_envelope": False,
        "isaac_execution_authorized": False,
        "isaac_started": False,
        "gpu_started": False,
        "joint_targets_materialized": False,
        "trajectory_playback_authorized": False,
        "native_replay_authorized": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }
    base_worker = _signed(CLAIMANT, base_worker_core, "worker_sha256")
    base_worker_path = tmp_path / "retained" / "base-worker.json"
    _write(base_worker_path, base_worker)
    kwargs = {
        "plan_file_sha256": CLAIMANT._file_sha(plan_path),
        "plan_review_file_sha256": CLAIMANT._file_sha(plan_review_path),
        "base_worker_file_sha256": CLAIMANT._file_sha(base_worker_path),
        "claimant_source_sha256": CLAIMANT._file_sha(SOURCE),
        "claimant_review_source_sha256": CLAIMANT._file_sha(REVIEW_SOURCE),
        "eula_preflight_source_sha256": CLAIMANT._file_sha(
            INTEGRATION / "nominal_route_isaac_eula_preflight.py"
        ),
        "memory_preflight_source_sha256": CLAIMANT._file_sha(
            INTEGRATION / "nominal_route_memory_preflight.py"
        ),
        "worker_source_sha256": CLAIMANT._file_sha(
            INTEGRATION / "nominal_route_physics_worker.py"
        ),
    }
    definition = CLAIMANT.build_claimant_definition(
        plan, plan_review, base_worker, **kwargs
    )
    return {
        "plan": plan,
        "plan_path": plan_path,
        "plan_review": plan_review,
        "plan_review_path": plan_review_path,
        "base_worker": base_worker,
        "base_worker_path": base_worker_path,
        "kwargs": kwargs,
        "definition": definition,
        "attempt": attempt,
        "eula_receipt": eula_receipt,
        "memory_receipt": memory_receipt,
    }


def _review(data):
    definition_path = data["plan_path"].parent / "claimant.json"
    _write(definition_path, data["definition"])
    return REVIEW.review_claimant(
        data["definition"],
        definition_file_sha256=REVIEW._file_sha(definition_path),
        claimant_source=SOURCE,
        plan_file=data["plan_path"],
        plan_review_file=data["plan_review_path"],
        base_worker_file=data["base_worker_path"],
        claimant_review_source=REVIEW_SOURCE,
        eula_preflight_source=(
            INTEGRATION / "nominal_route_isaac_eula_preflight.py"
        ),
        memory_preflight_source=INTEGRATION / "nominal_route_memory_preflight.py",
        worker_source=INTEGRATION / "nominal_route_physics_worker.py",
    )


def _passing_eula():
    return {
        "status": "PASS_EULA_PREFLIGHT",
        "launch_admitted": True,
        "acceptance_observed": True,
        "acceptance_performed_by_preflight": False,
        "attempt_claimed": False,
        "isaac_started": False,
        "hardware_access": False,
        "physical_authority": False,
    }


def _passing_memory():
    return {
        "status": "PASS_MEMORY_PREFLIGHT",
        "launch_admitted": True,
        "attempt_claimed": False,
        "isaac_started": False,
        "hardware_access": False,
        "physical_authority": False,
    }


def test_builds_inert_fresh_gate_claimant(tmp_path):
    data = _bundle(tmp_path)
    definition = data["definition"]
    assert definition["required_authorization_statement"] == CLAIMANT.EXACT_AUTHORIZATION
    assert definition["worker_authorization_is_internal_compatibility_token"] is True
    assert definition["worker_preparation"]["proposed_output_directory"] == str(
        data["attempt"]
    )
    assert definition["worker_preparation"]["required_authorization_statement"] == (
        CLAIMANT.INTERNAL_WORKER_AUTHORIZATION
    )
    assert definition["authorization_observed"] is False
    assert definition["attempt_claimed"] is False
    assert definition["isaac_started"] is False
    assert definition["hardware_access"] is False
    assert definition["physical_authority"] is False


def test_independent_review_accepts_exact_claimant(tmp_path):
    result = _review(_bundle(tmp_path))
    assert result["status"] == (
        "ACCEPTED_FOR_EXACT_ARM297_ONE_ATTEMPT_AUTHORIZATION"
    )
    assert result["fresh_gates_precede_attempt_claim"] is True
    assert result["both_receipts_precede_attempt_claim"] is True
    assert result["failure_terminalization_precedes_shutdown"] is True
    assert result["old_authorizations_rejected"] is True
    assert result["launch_admitted"] is True
    assert result["attempt_claimed"] is False
    assert result["isaac_started"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False
    assert REVIEW._require_hash(result, "claimant_review_sha256", "review")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("required_authorization_statement", "old authorization"),
        ("authorization_reusable", True),
        ("hardware_access", True),
        ("automatic_retry", True),
    ],
)
def test_independent_review_rejects_resigned_claimant_drift(
    tmp_path, field, value
):
    data = _bundle(tmp_path)
    changed = copy.deepcopy(data["definition"])
    changed[field] = value
    changed.pop("claimant_sha256")
    changed["claimant_sha256"] = REVIEW._sha(changed)
    data["definition"] = changed
    with pytest.raises(REVIEW.Arm297ClaimantReviewError):
        _review(data)


def test_independent_review_rejects_bound_source_drift(tmp_path):
    data = _bundle(tmp_path)
    data["base_worker_path"].write_text("{}\n", encoding="utf-8")
    with pytest.raises(REVIEW.Arm297ClaimantReviewError):
        _review(data)


def test_independent_review_rejects_precreated_attempt_output(tmp_path):
    data = _bundle(tmp_path)
    data["attempt"].mkdir(parents=True)
    with pytest.raises(
        REVIEW.Arm297ClaimantReviewError,
        match="review boundary",
    ):
        _review(data)


def test_claimant_and_reviewer_have_no_direct_motion_or_transport_surface():
    text = SOURCE.read_text(encoding="utf-8")
    for token in (
        "set_dof_positions(",
        "set_dof_position_targets(",
        "set_joint_position_targets(",
        "serial.Serial(",
        "SimulationManager.step(",
    ):
        assert token not in text


@pytest.mark.parametrize(
    ("target", "key", "value"),
    [
        ("plan", "superseded_authorizations_reusable", True),
        ("plan", "authorization_observed", True),
        ("review", "proposed_attempt_directory_absent", False),
        ("worker", "isaac_started", True),
    ],
)
def test_build_rejects_lineage_or_authority_drift(tmp_path, target, key, value):
    data = _bundle(tmp_path)
    plan = copy.deepcopy(data["plan"])
    review = copy.deepcopy(data["plan_review"])
    worker = copy.deepcopy(data["base_worker"])
    document = {"plan": plan, "review": review, "worker": worker}[target]
    hash_key = {
        "plan": "plan_sha256",
        "review": "lineage_review_sha256",
        "worker": "worker_sha256",
    }[target]
    document[key] = value
    document.pop(hash_key)
    document[hash_key] = CLAIMANT._sha(document)
    if target == "plan":
        review["source_plan_sha256"] = document[hash_key]
        review.pop("lineage_review_sha256")
        review["lineage_review_sha256"] = CLAIMANT._sha(review)
    with pytest.raises(CLAIMANT.Arm297ClaimantError):
        CLAIMANT.build_claimant_definition(
            plan, review, worker, **data["kwargs"]
        )


def test_runtime_retains_fresh_gates_before_single_worker_delegation(tmp_path):
    data = _bundle(tmp_path)
    review = _review(data)
    events = []

    def worker(preparation, **kwargs):
        events.append("worker")
        assert data["eula_receipt"].exists()
        assert data["memory_receipt"].exists()
        assert kwargs["authorization_statement"] == (
            CLAIMANT.INTERNAL_WORKER_AUTHORIZATION
        )
        assert preparation["proposed_output_directory"] == str(data["attempt"])
        return {"status": "delegated"}

    claimant = CLAIMANT.Arm297Claimant(
        data["definition"],
        review,
        eula_collector=lambda: events.append("eula_collect") or {},
        eula_evaluator=lambda _: events.append("eula_evaluate") or _passing_eula(),
        memory_collector=lambda: events.append("memory_collect") or object(),
        memory_evaluator=lambda _: events.append("memory_evaluate")
        or _passing_memory(),
        worker_runner=worker,
    )
    result = claimant.run(
        authorization_statement=CLAIMANT.EXACT_AUTHORIZATION,
        output_directory=data["attempt"],
        fresh_eula_receipt=data["eula_receipt"],
        fresh_memory_receipt=data["memory_receipt"],
        current_runtime_sources_sha256=data["plan"]["runtime_sources_sha256"],
        current_source_files_sha256={},
        current_runtime_bindings_sha256={},
        backend=lambda _: {},
    )
    assert result == {"status": "delegated"}
    assert events == [
        "eula_collect",
        "eula_evaluate",
        "memory_collect",
        "memory_evaluate",
        "worker",
    ]
    with pytest.raises(CLAIMANT.Arm297ClaimantError):
        claimant.run(
            authorization_statement=CLAIMANT.EXACT_AUTHORIZATION,
            output_directory=data["attempt"],
            fresh_eula_receipt=data["eula_receipt"],
            fresh_memory_receipt=data["memory_receipt"],
            current_runtime_sources_sha256=data["plan"]["runtime_sources_sha256"],
            current_source_files_sha256={},
            current_runtime_bindings_sha256={},
            backend=lambda _: {},
        )


def test_runtime_clone_is_accepted_by_actual_fail_closed_worker(tmp_path):
    data = _bundle(tmp_path)

    def backend(output_directory):
        claimed = json.loads(
            (output_directory / "status.json").read_text(encoding="utf-8")
        )
        assert claimed["status"] == "ATTEMPT_CLAIMED_BACKEND_PENDING"
        terminal = {
            "status": "PASS_SYNTHETIC_BACKEND_COMPATIBILITY",
            "attempt_count": 1,
            "automatic_retry": False,
            "hardware_access": False,
            "physical_authority": False,
        }
        _write(output_directory / "status.json", terminal)
        return terminal

    claimant = CLAIMANT.Arm297Claimant(
        data["definition"],
        _review(data),
        eula_evaluator=lambda _: _passing_eula(),
        memory_collector=lambda: object(),
        memory_evaluator=lambda _: _passing_memory(),
    )
    result = claimant.run(
        authorization_statement=CLAIMANT.EXACT_AUTHORIZATION,
        output_directory=data["attempt"],
        fresh_eula_receipt=data["eula_receipt"],
        fresh_memory_receipt=data["memory_receipt"],
        current_runtime_sources_sha256=data["plan"]["runtime_sources_sha256"],
        current_source_files_sha256=data["definition"]["worker_preparation"][
            "source_files_sha256"
        ],
        current_runtime_bindings_sha256=data["definition"]["worker_preparation"][
            "runtime_bindings_sha256"
        ],
        backend=backend,
    )
    assert result["status"] == "PASS_SYNTHETIC_BACKEND_COMPATIBILITY"
    assert data["attempt"].is_dir()


def test_runtime_rejects_inexact_authority_before_gate_collection(tmp_path):
    data = _bundle(tmp_path)
    events = []
    claimant = CLAIMANT.Arm297Claimant(
        data["definition"],
        _review(data),
        eula_collector=lambda: events.append("gate") or {},
    )
    with pytest.raises(CLAIMANT.Arm297ClaimantError):
        claimant.run(
            authorization_statement="wrong",
            output_directory=data["attempt"],
            fresh_eula_receipt=data["eula_receipt"],
            fresh_memory_receipt=data["memory_receipt"],
            current_runtime_sources_sha256=data["plan"]["runtime_sources_sha256"],
            current_source_files_sha256={},
            current_runtime_bindings_sha256={},
            backend=lambda _: {},
        )
    assert events == []


def test_runtime_rejects_source_drift_before_gate_collection(tmp_path):
    data = _bundle(tmp_path)
    events = []
    claimant = CLAIMANT.Arm297Claimant(
        data["definition"],
        _review(data),
        eula_collector=lambda: events.append("gate") or {},
    )
    drift = dict(data["plan"]["runtime_sources_sha256"])
    drift["native_sweep_binding"] = "f" * 64
    with pytest.raises(CLAIMANT.Arm297ClaimantError):
        claimant.run(
            authorization_statement=CLAIMANT.EXACT_AUTHORIZATION,
            output_directory=data["attempt"],
            fresh_eula_receipt=data["eula_receipt"],
            fresh_memory_receipt=data["memory_receipt"],
            current_runtime_sources_sha256=drift,
            current_source_files_sha256={},
            current_runtime_bindings_sha256={},
            backend=lambda _: {},
        )
    assert events == []


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("definition", "authorization_reusable", True),
        ("definition", "required_authorization_statement", "old authorization"),
        ("review", "old_authorizations_rejected", False),
        ("review", "internal_worker_token_is_not_external_authority", False),
        ("review", "both_receipts_precede_attempt_claim", False),
    ],
)
def test_runtime_constructor_rejects_resigned_authority_drift(
    tmp_path, target, field, value
):
    data = _bundle(tmp_path)
    definition = copy.deepcopy(data["definition"])
    review = _review(data)
    document = definition if target == "definition" else review
    hash_key = "claimant_sha256" if target == "definition" else "claimant_review_sha256"
    document[field] = value
    document.pop(hash_key)
    document[hash_key] = CLAIMANT._sha(document)
    if target == "definition":
        review["source_claimant_sha256"] = definition["claimant_sha256"]
        review.pop("claimant_review_sha256")
        review["claimant_review_sha256"] = CLAIMANT._sha(review)
    with pytest.raises(CLAIMANT.Arm297ClaimantError):
        CLAIMANT.Arm297Claimant(definition, review)


@pytest.mark.parametrize("failed_gate", ["eula", "memory"])
def test_runtime_refuses_failed_fresh_gate_without_worker(tmp_path, failed_gate):
    data = _bundle(tmp_path)
    events = []
    eula = _passing_eula()
    memory = _passing_memory()
    if failed_gate == "eula":
        eula["status"] = "FAIL_EULA_PREFLIGHT"
    else:
        memory["status"] = "FAIL_MEMORY_PREFLIGHT"
    claimant = CLAIMANT.Arm297Claimant(
        data["definition"],
        _review(data),
        eula_evaluator=lambda _: eula,
        memory_collector=lambda: object(),
        memory_evaluator=lambda _: memory,
        worker_runner=lambda *args, **kwargs: events.append("worker"),
    )
    with pytest.raises(CLAIMANT.Arm297ClaimantError):
        claimant.run(
            authorization_statement=CLAIMANT.EXACT_AUTHORIZATION,
            output_directory=data["attempt"],
            fresh_eula_receipt=data["eula_receipt"],
            fresh_memory_receipt=data["memory_receipt"],
            current_runtime_sources_sha256=data["plan"]["runtime_sources_sha256"],
            current_source_files_sha256={},
            current_runtime_bindings_sha256={},
            backend=lambda _: {},
        )
    assert events == []
    assert not data["attempt"].exists()
