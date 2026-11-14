from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
SOURCE = INTEGRATION / "nominal_route_arm300_claimant.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_arm300_claimant_review.py"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CLAIMANT = _load("arm300_claimant_test", SOURCE)
REVIEW = _load("arm300_claimant_review_test", REVIEW_SOURCE)


def _signed(module, core: dict, key: str) -> dict:
    return {**core, key: module._sha(core)}


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _bundle(tmp_path: Path):
    future = tmp_path / "future"
    attempt = future / "arm300-attempt"
    eula_receipt = future / "arm300-eula" / "receipt.json"
    memory_receipt = future / "arm300-memory" / "receipt.json"
    runtime_sources = {
        key: f"{index:x}" * 64
        for index, key in enumerate(CLAIMANT.RUNTIME_SOURCE_KEYS, start=1)
    }
    outputs = {
        "attempt_directory": str(attempt),
        "eula_receipt": str(eula_receipt),
        "memory_receipt": str(memory_receipt),
    }
    plan_core = {
        "schema": CLAIMANT.PLAN_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_ARM300_LINEAGE_REVIEW",
        "episode_id": "episode-ef340d0ad2740c118d87",
        "target_id": "SPACE",
        "source_arm298_terminal_sha256": "a" * 64,
        "source_arm298_terminal_status": {"status": "FAILED_RETAINED_NO_RETRY"},
        "repository_commit": "f84c69dc99f1df546dd27aec9c757c0a54e6033b",
        "plan_source_file_sha256": "b" * 64,
        "runtime_sources_sha256": runtime_sources,
        "qualified_interpreter": {"path": "C:/isaac/python.exe", "file_sha256": "c" * 64},
        "proposed_outputs": outputs,
        "required_future_authorization_statement": (
            CLAIMANT.EXACT_FUTURE_AUTHORIZATION
        ),
        "next_required_stage": "INDEPENDENT_ARM300_LINEAGE_REVIEW",
        **CLAIMANT.LINEAGE_ZERO_AUTHORITY,
    }
    plan = _signed(CLAIMANT, plan_core, "plan_sha256")
    plan_path = tmp_path / "retained" / "plan.json"
    _write(plan_path, plan)
    review_core = {
        "schema": CLAIMANT.PLAN_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ARM300_CLAIMANT_CONSTRUCTION",
        "source_plan_sha256": plan["plan_sha256"],
        "source_plan_file_sha256": CLAIMANT._file_sha(plan_path),
        "review_source_file_sha256": "d" * 64,
        "recomputed_runtime_sources_sha256": runtime_sources,
        "fresh_outputs_verified_absent": True,
        "required_future_authorization_statement": (
            CLAIMANT.EXACT_FUTURE_AUTHORIZATION
        ),
        "next_required_stage": "BUILD_AND_REVIEW_ARM300_SINGLE_USE_CLAIMANT",
        "runtime_and_transport_imports_absent": True,
        "runtime_motion_and_transport_calls_absent": True,
        **CLAIMANT.LINEAGE_ZERO_AUTHORITY,
    }
    plan_review = _signed(CLAIMANT, review_core, "review_sha256")
    plan_review_path = tmp_path / "retained" / "plan-review.json"
    _write(plan_review_path, plan_review)
    base_worker_core = {
        "schema": CLAIMANT.PREPARATION_SCHEMA,
        "worker_id": "arm254-space-nominal-route-physics-worker-001",
        "status": "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW",
        "required_authorization_statement": CLAIMANT.INTERNAL_WORKER_AUTHORIZATION,
        "proposed_output_directory": "C:/old/attempt",
        "attempt_ledger": {
            "maximum_attempt_count": 1,
            "attempts_consumed_by_preparation": 0,
            "automatic_retry": False,
        },
        "source_files_sha256": {"route_plan": "e" * 64},
        "runtime_bindings_sha256": {"robot_usd": "f" * 64},
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
    worker = _signed(CLAIMANT, base_worker_core, "worker_sha256")
    worker_path = tmp_path / "retained" / "worker.json"
    _write(worker_path, worker)
    kwargs = {
        "plan_file_sha256": CLAIMANT._file_sha(plan_path),
        "plan_review_file_sha256": CLAIMANT._file_sha(plan_review_path),
        "base_worker_file_sha256": CLAIMANT._file_sha(worker_path),
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
        plan, plan_review, worker, **kwargs
    )
    return {
        "plan": plan,
        "plan_path": plan_path,
        "plan_review": plan_review,
        "plan_review_path": plan_review_path,
        "worker": worker,
        "worker_path": worker_path,
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
        base_worker_file=data["worker_path"],
        claimant_review_source=REVIEW_SOURCE,
        eula_preflight_source=INTEGRATION / "nominal_route_isaac_eula_preflight.py",
        memory_preflight_source=INTEGRATION / "nominal_route_memory_preflight.py",
        worker_source=INTEGRATION / "nominal_route_physics_worker.py",
    )


def _passing_eula() -> dict[str, object]:
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


def _passing_memory() -> dict[str, object]:
    return {
        "status": "PASS_MEMORY_PREFLIGHT",
        "launch_admitted": True,
        "attempt_claimed": False,
        "isaac_started": False,
        "hardware_access": False,
        "physical_authority": False,
    }


def test_build_and_review_are_inert(tmp_path):
    data = _bundle(tmp_path)
    result = _review(data)
    assert data["definition"]["status"] == (
        "READY_FOR_INDEPENDENT_ARM300_CLAIMANT_REVIEW"
    )
    assert result["status"] == (
        "ACCEPTED_FOR_EXACT_ARM300_ONE_ATTEMPT_AUTHORIZATION"
    )
    assert result["both_receipts_precede_attempt_claim"] is True
    assert result["single_worker_delegation"] is True
    for key, value in CLAIMANT.ZERO_AUTHORITY.items():
        assert data["definition"][key] == value
        assert result[key] == value


def test_review_rejects_bound_source_drift(tmp_path):
    data = _bundle(tmp_path)
    data["worker_path"].write_text("{}\n", encoding="utf-8")
    with pytest.raises(REVIEW.Arm300ClaimantReviewError):
        _review(data)


def test_review_rejects_precreated_attempt_output(tmp_path):
    data = _bundle(tmp_path)
    data["attempt"].mkdir(parents=True)
    with pytest.raises(REVIEW.Arm300ClaimantReviewError, match="review boundary"):
        _review(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("required_authorization_statement", "old authorization"),
        ("authorization_reusable", True),
        ("hardware_access", True),
        ("automatic_retry", True),
    ],
)
def test_review_rejects_resigned_claimant_drift(tmp_path, field, value):
    data = _bundle(tmp_path)
    changed = copy.deepcopy(data["definition"])
    changed[field] = value
    changed.pop("claimant_sha256")
    changed["claimant_sha256"] = REVIEW._sha(changed)
    data["definition"] = changed
    with pytest.raises(REVIEW.Arm300ClaimantReviewError):
        _review(data)


def test_runtime_retains_gates_before_one_delegation(tmp_path):
    data = _bundle(tmp_path)
    events: list[str] = []

    def worker(preparation, **kwargs):
        events.append("worker")
        assert data["eula_receipt"].exists()
        assert data["memory_receipt"].exists()
        assert kwargs["authorization_statement"] == (
            CLAIMANT.INTERNAL_WORKER_AUTHORIZATION
        )
        assert preparation["proposed_output_directory"] == str(data["attempt"])
        return {"status": "delegated"}

    claimant = CLAIMANT.Arm300Claimant(
        data["definition"],
        _review(data),
        eula_collector=lambda: events.append("eula_collect") or {},
        eula_evaluator=lambda _: events.append("eula_evaluate") or _passing_eula(),
        memory_collector=lambda: events.append("memory_collect") or object(),
        memory_evaluator=lambda _: events.append("memory_evaluate")
        or _passing_memory(),
        worker_runner=worker,
    )
    result = claimant.run(
        authorization_statement=CLAIMANT.EXACT_FUTURE_AUTHORIZATION,
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
    with pytest.raises(CLAIMANT.Arm300ClaimantError):
        claimant.run(
            authorization_statement=CLAIMANT.EXACT_FUTURE_AUTHORIZATION,
            output_directory=data["attempt"],
            fresh_eula_receipt=data["eula_receipt"],
            fresh_memory_receipt=data["memory_receipt"],
            current_runtime_sources_sha256=data["plan"]["runtime_sources_sha256"],
            current_source_files_sha256={},
            current_runtime_bindings_sha256={},
            backend=lambda _: {},
        )


def test_runtime_rejects_wrong_authorization_before_gates(tmp_path):
    data = _bundle(tmp_path)
    events: list[str] = []
    claimant = CLAIMANT.Arm300Claimant(
        data["definition"],
        _review(data),
        eula_collector=lambda: events.append("gate") or {},
    )
    with pytest.raises(CLAIMANT.Arm300ClaimantError):
        claimant.run(
            authorization_statement="consumed ARM-298 statement",
            output_directory=data["attempt"],
            fresh_eula_receipt=data["eula_receipt"],
            fresh_memory_receipt=data["memory_receipt"],
            current_runtime_sources_sha256=data["plan"]["runtime_sources_sha256"],
            current_source_files_sha256={},
            current_runtime_bindings_sha256={},
            backend=lambda _: {},
        )
    assert events == []


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

    claimant = CLAIMANT.Arm300Claimant(
        data["definition"],
        _review(data),
        eula_evaluator=lambda _: _passing_eula(),
        memory_collector=lambda: object(),
        memory_evaluator=lambda _: _passing_memory(),
    )
    result = claimant.run(
        authorization_statement=CLAIMANT.EXACT_FUTURE_AUTHORIZATION,
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


def test_runtime_rejects_source_drift_before_gates(tmp_path):
    data = _bundle(tmp_path)
    events: list[str] = []
    claimant = CLAIMANT.Arm300Claimant(
        data["definition"],
        _review(data),
        eula_collector=lambda: events.append("gate") or {},
    )
    changed = dict(data["plan"]["runtime_sources_sha256"])
    changed["physics_backend"] = "0" * 64
    with pytest.raises(CLAIMANT.Arm300ClaimantError):
        claimant.run(
            authorization_statement=CLAIMANT.EXACT_FUTURE_AUTHORIZATION,
            output_directory=data["attempt"],
            fresh_eula_receipt=data["eula_receipt"],
            fresh_memory_receipt=data["memory_receipt"],
            current_runtime_sources_sha256=changed,
            current_source_files_sha256={},
            current_runtime_bindings_sha256={},
            backend=lambda _: {},
        )
    assert events == []


@pytest.mark.parametrize("failed_gate", ["eula", "memory"])
def test_runtime_refuses_failed_gate_without_worker(tmp_path, failed_gate):
    data = _bundle(tmp_path)
    events: list[str] = []
    eula = _passing_eula()
    memory = _passing_memory()
    if failed_gate == "eula":
        eula["status"] = "FAIL_EULA_PREFLIGHT"
    else:
        memory["status"] = "FAIL_MEMORY_PREFLIGHT"
    claimant = CLAIMANT.Arm300Claimant(
        data["definition"],
        _review(data),
        eula_evaluator=lambda _: eula,
        memory_collector=lambda: object(),
        memory_evaluator=lambda _: memory,
        worker_runner=lambda *args, **kwargs: events.append("worker"),
    )
    with pytest.raises(CLAIMANT.Arm300ClaimantError):
        claimant.run(
            authorization_statement=CLAIMANT.EXACT_FUTURE_AUTHORIZATION,
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


def test_claimant_has_no_direct_motion_or_transport_surface():
    text = SOURCE.read_text(encoding="utf-8")
    for token in (
        "set_dof_positions(",
        "set_dof_position_targets(",
        "set_joint_position_targets(",
        "serial.Serial(",
        "SimulationManager.step(",
    ):
        assert token not in text
