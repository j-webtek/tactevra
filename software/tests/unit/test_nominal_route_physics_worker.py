from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE_HASHES = {
    "nominal_profile": "1" * 64,
    "route_plan": "2" * 64,
    "correction_plan": "3" * 64,
    "toolchain_lock": "4" * 64,
}
RUNTIME_HASHES = {
    "robot_usd": "a" * 64,
    "robot_import_receipt": "b" * 64,
    "virtual_profile": "c" * 64,
    "key_mechanics_profile": "d" * 64,
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _worker():
    return _load_module(
        "arm254_worker",
        ROOT / "software/integrations/isaac_sim/nominal_route_physics_worker.py",
    )


def _arm251_fixtures():
    return _load_module(
        "arm251_fixtures_for_arm254",
        ROOT / "software/tests/unit/test_nominal_route_physics_experiment.py",
    )


def _review_module():
    return _load_module(
        "arm252_for_arm254",
        ROOT / "software/integrations/isaac_sim/"
        "nominal_route_physics_experiment_review.py",
    )


def _request_module():
    return _load_module(
        "arm253_for_arm254",
        ROOT / "software/integrations/isaac_sim/"
        "nominal_route_physics_attempt_request.py",
    )


def _seal(module, value: dict, key: str) -> dict:
    value.pop(key, None)
    value[key] = module._sha(value)
    return value


def _bundle(tmp_path: Path):
    worker = _worker()
    fixtures = _arm251_fixtures()
    experiment_module = fixtures._module()
    sources = fixtures._inputs()
    route = sources["route_plan"]
    route["source_bindings"] = {
        "robot_usd_sha256": RUNTIME_HASHES["robot_usd"],
        "robot_import_receipt_sha256": RUNTIME_HASHES["robot_import_receipt"],
        "virtual_profile_sha256": RUNTIME_HASHES["virtual_profile"],
        "key_mechanics_profile_sha256": RUNTIME_HASHES["key_mechanics_profile"],
    }
    _seal(experiment_module, route, "plan_sha256")
    correction = sources["correction_plan"]
    correction["source_corrected_plan_sha256"] = route["plan_sha256"]
    _seal(experiment_module, correction, "plan_sha256")
    experiment = experiment_module.build_experiment(
        **sources,
        source_files_sha256=SOURCE_HASHES,
    )
    review = _review_module().build_review(
        experiment=experiment,
        **sources,
        source_files_sha256=SOURCE_HASHES,
        experiment_file_sha256="5" * 64,
    )
    request = _request_module().build_request(
        review,
        experiment,
        source_files_sha256=SOURCE_HASHES,
        review_file_sha256="6" * 64,
        experiment_file_sha256="5" * 64,
    )
    output_directory = tmp_path / "attempt-001"
    preparation = worker.build_preparation(
        request,
        review,
        experiment,
        route,
        source_files_sha256=SOURCE_HASHES,
        request_file_sha256="7" * 64,
        review_file_sha256="6" * 64,
        experiment_file_sha256="5" * 64,
        proposed_output_directory=str(output_directory),
    )
    return worker, preparation, request, review, experiment, route, output_directory


def _accepted_review(worker, preparation):
    core = {
        "schema": worker.WORKER_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ONE_SEPARATELY_AUTHORIZED_SIMULATION_ATTEMPT",
        "source_worker_sha256": preparation["worker_sha256"],
        "reviewed_backend_sha256": "e" * 64,
        "launch_admitted": True,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }
    return {**core, "worker_review_sha256": worker._sha(core)}


def test_arm254_builds_reviewable_nonexecuting_worker_envelope(tmp_path: Path) -> None:
    _, result, *_ = _bundle(tmp_path)

    assert result["status"] == "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW"
    assert result["attempt_ledger"] == {
        "maximum_attempt_count": 1,
        "attempts_consumed_by_preparation": 0,
        "automatic_retry": False,
        "output_directory_claim": "ATOMIC_CREATE_NEW_DIRECTORY",
        "existing_directory_disposition": "FAIL_BEFORE_ISAAC_IMPORT",
        "failure_disposition": "RETAIN_STATUS_AND_STOP",
    }
    assert result["backend_contract"]["regenerated_row_count"] == 287
    assert result["isaac_backend_implemented_by_this_envelope"] is False


def test_arm254_binds_all_runtime_models_from_route_lineage(tmp_path: Path) -> None:
    _, result, *_ = _bundle(tmp_path)

    assert result["runtime_bindings_sha256"] == RUNTIME_HASHES
    assert result["source_files_sha256"] == SOURCE_HASHES


def test_arm254_preserves_zero_authority_and_typing_boundary(tmp_path: Path) -> None:
    _, result, *_ = _bundle(tmp_path)

    assert result["isaac_execution_authorized"] is False
    assert result["isaac_started"] is False
    assert result["gpu_started"] is False
    assert result["joint_targets_materialized"] is False
    assert result["trajectory_playback_authorized"] is False
    assert result["native_replay_authorized"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False
    assert result["controller_commands"] == []
    assert result["wire_commands"] == []
    assert result["gate_promotions"] == []
    assert result["next_required_stage"] == (
        "IMPLEMENT_AND_INDEPENDENTLY_REVIEW_PINNED_ISAAC_PHYSICS_BACKEND"
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["attempt_contract"].update(maximum_attempt_count=2),
        lambda value: value["attempt_contract"].update(automatic_retry=True),
        lambda value: value.update(target_id="ENTER"),
        lambda value: value.update(isaac_execution_authorized=True),
    ],
)
def test_arm254_rejects_request_drift(tmp_path: Path, mutate) -> None:
    worker, _, request, review, experiment, route, output_directory = _bundle(tmp_path)
    changed = copy.deepcopy(request)
    mutate(changed)
    _seal(worker, changed, "request_sha256")

    with pytest.raises(worker.NominalRoutePhysicsWorkerError):
        worker.build_preparation(
            changed,
            review,
            experiment,
            route,
            source_files_sha256=SOURCE_HASHES,
            request_file_sha256="7" * 64,
            review_file_sha256="6" * 64,
            experiment_file_sha256="5" * 64,
            proposed_output_directory=str(output_directory),
        )


def test_arm254_refuses_unreviewed_or_drifted_attempt(tmp_path: Path) -> None:
    worker, preparation, *_, output_directory = _bundle(tmp_path)
    review = _accepted_review(worker, preparation)

    with pytest.raises(worker.NominalRoutePhysicsWorkerError):
        worker.run_one_attempt(
            preparation,
            worker_review={**review, "launch_admitted": False},
            authorization_statement=worker.EXACT_AUTHORIZATION,
            output_directory=output_directory,
            current_source_files_sha256=SOURCE_HASHES,
            current_runtime_bindings_sha256=RUNTIME_HASHES,
            backend=lambda _: {},
        )
    with pytest.raises(worker.NominalRoutePhysicsWorkerError):
        worker.run_one_attempt(
            preparation,
            worker_review=review,
            authorization_statement=worker.EXACT_AUTHORIZATION,
            output_directory=output_directory,
            current_source_files_sha256={**SOURCE_HASHES, "route_plan": "9" * 64},
            current_runtime_bindings_sha256=RUNTIME_HASHES,
            backend=lambda _: {},
        )
    assert not output_directory.exists()


def test_arm254_claims_exactly_once_and_retains_failure(tmp_path: Path) -> None:
    worker, preparation, *_, output_directory = _bundle(tmp_path)
    review = _accepted_review(worker, preparation)
    calls = 0

    def fail_once(_: Path):
        nonlocal calls
        calls += 1
        raise RuntimeError("synthetic backend failure")

    with pytest.raises(RuntimeError, match="synthetic backend failure"):
        worker.run_one_attempt(
            preparation,
            worker_review=review,
            authorization_statement=worker.EXACT_AUTHORIZATION,
            output_directory=output_directory,
            current_source_files_sha256=SOURCE_HASHES,
            current_runtime_bindings_sha256=RUNTIME_HASHES,
            backend=fail_once,
        )
    status = json.loads((output_directory / "status.json").read_bytes())
    assert calls == 1
    assert status["status"] == "FAILED_RETAINED_NO_RETRY"
    assert status["attempt_count"] == 1
    assert status["automatic_retry"] is False

    with pytest.raises(worker.NominalRoutePhysicsWorkerError):
        worker.run_one_attempt(
            preparation,
            worker_review=review,
            authorization_statement=worker.EXACT_AUTHORIZATION,
            output_directory=output_directory,
            current_source_files_sha256=SOURCE_HASHES,
            current_runtime_bindings_sha256=RUNTIME_HASHES,
            backend=fail_once,
        )
    assert calls == 1
