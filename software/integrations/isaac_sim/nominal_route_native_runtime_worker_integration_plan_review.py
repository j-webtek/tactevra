"""Independently review the ARM-273 native-runtime worker integration plan."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping


REVIEW_SCHEMA = "tactevra.isaac_lm4_native_runtime_worker_integration_plan_review.v1"
EXPECTED_PLAN_SHA256 = (
    "aa779b19778ef40daacf8f5c0f62ca2aaccf2e27c1b3643d2a3a70d5f7981576"
)
EXPECTED_PLAN_FILE_SHA256 = (
    "945fa5bb7cdefd453a6cd880be7ac1aa995224769aeb3a31c0e158800ba45cfa"
)
EXPECTED_PLAN_SOURCE_SHA256 = (
    "85ef93b122f6517f10d21a02253dd5568b96cc656a3b3a56b2ee264eb6524b04"
)


class NativeRuntimeWorkerIntegrationPlanReviewError(ValueError):
    """Raised when the ARM-273 plan or reviewed call surfaces change."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeRuntimeWorkerIntegrationPlanReviewError(f"{label} hash changed")
    return claimed


def _import_plan(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("arm273_reviewed_plan", path)
    if spec is None or spec.loader is None:
        raise NativeRuntimeWorkerIntegrationPlanReviewError(
            "integration plan source cannot be imported"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _function_parameters(path: Path, name: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return [
                argument.arg
                for argument in (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                )
            ]
    raise NativeRuntimeWorkerIntegrationPlanReviewError(f"{name} is absent")


def _static_plan_review(path: Path) -> dict[str, bool]:
    text = path.read_text(encoding="utf-8")
    forbidden = (
        "import isaacsim",
        "from isaacsim",
        "SimulationApp(",
        "import serial",
        "run_one_attempt(",
        "execute_backend(",
        "construct_runtime(",
        "set_dof_positions",
        "set_dof_position_targets",
        "step(",
    )
    if any(token in text for token in forbidden):
        raise NativeRuntimeWorkerIntegrationPlanReviewError(
            "plan source contains runtime or attempt authority"
        )
    return {
        "isaac_import_and_launch_absent": True,
        "attempt_claim_absent": True,
        "worker_backend_and_factory_calls_absent": True,
        "joint_submission_and_physics_steps_absent": True,
    }


def _review_call_surfaces(source_paths: Mapping[str, Path]) -> dict[str, list[str]]:
    observed = {
        "run_one_attempt": _function_parameters(source_paths["worker"], "run_one_attempt"),
        "execute_backend": _function_parameters(source_paths["backend"], "execute_backend"),
        "construct_runtime": _function_parameters(
            source_paths["factory"], "construct_runtime"
        ),
    }
    expected = {
        "run_one_attempt": [
            "preparation",
            "worker_review",
            "authorization_statement",
            "output_directory",
            "current_source_files_sha256",
            "current_runtime_bindings_sha256",
            "backend",
        ],
        "execute_backend": [
            "definition",
            "route",
            "backend_review",
            "output_directory",
            "runtime",
        ],
        "construct_runtime": [
            "definition",
            "factory_review",
            "plan",
            "plan_review",
            "documents",
            "articulation",
            "scene_query",
            "key_view",
            "root_view",
            "solver_kwargs",
            "native_metadata",
        ],
    }
    if observed != expected:
        raise NativeRuntimeWorkerIntegrationPlanReviewError(
            "worker integration call surfaces changed"
        )
    return observed


def _review_order(plan: Mapping[str, Any]) -> dict[str, Any]:
    required = [
        "revalidate_arm254_arm255_arm271_arm272_and_all_source_hashes",
        "verify_exact_one_attempt_authorization_and_no_retry",
        "verify_governed_output_directory_is_absent",
        "create_side_effect_free_backend_callable_without_claiming_attempt",
        "enter_arm254_run_one_attempt_as_sole_directory_claimant",
        "after_claim_start_one_headless_isaac_runtime",
        "load_exact_pinned_scene_and_initialize_physics_once",
        "settle_scene_before_any_governed_route_operation",
        "construct_and_validate_supplied_native_objects_and_metadata",
        "invoke_arm272_factory_once_without_protocol_calls",
        "invoke_arm255_backend_once_with_factory_runtime",
        "write_all_outputs_before_simulator_shutdown",
        "shutdown_once_and_retain_terminal_status_without_retry",
    ]
    boundary = plan.get("integration_boundary", {})
    failure = plan.get("failure_policy", {})
    future = plan.get("required_future_inputs", {})
    if (
        plan.get("required_future_order") != required
        or boundary.get("worker_remains_sole_output_directory_claimant") is not True
        or boundary.get("backend_callable_is_injected_without_side_effects") is not True
        or boundary.get("factory_result_is_passed_as_backend_runtime") is not True
        or boundary.get("backend_is_called_exactly_once_after_worker_claim") is not True
        or boundary.get("automatic_retry") is not False
        or failure.get("after_worker_claim") != "RETAIN_FAILED_STATUS_AND_STOP"
        or failure.get("factory_or_backend_failure") != "NO_RETRY"
        or not isinstance(future.get("accepted_worker_review"), Mapping)
        or not isinstance(future.get("accepted_backend_review"), Mapping)
        or plan.get("worker_review_materialized") is not False
        or plan.get("backend_review_materialized") is not False
        or plan.get("worker_integration_implemented") is not False
        or plan.get("attempt_consumed") is not False
        or plan.get("physics_steps") != 0
        or plan.get("backend_execution_admitted") is not False
    ):
        raise NativeRuntimeWorkerIntegrationPlanReviewError(
            "worker integration order or authority boundary changed"
        )
    return {
        "ordered_step_count": len(required),
        "worker_claim_precedes_launch": True,
        "scene_settle_precedes_factory": True,
        "factory_precedes_backend": True,
        "outputs_precede_shutdown": True,
        "automatic_retry": False,
    }


def review_worker_integration_plan(
    plan: Mapping[str, Any],
    worker: Mapping[str, Any],
    backend: Mapping[str, Any],
    factory: Mapping[str, Any],
    factory_review: Mapping[str, Any],
    *,
    plan_file_sha256: str,
    plan_source_path: Path,
    source_paths: Mapping[str, Path],
    files_sha256: Mapping[str, str],
) -> dict[str, Any]:
    plan_hash = _require_hash(plan, "integration_plan_sha256", "ARM-273 plan")
    plan_source_sha = _file_sha(plan_source_path)
    if (
        plan_hash != EXPECTED_PLAN_SHA256
        or plan_file_sha256 != EXPECTED_PLAN_FILE_SHA256
        or plan_source_sha != EXPECTED_PLAN_SOURCE_SHA256
    ):
        raise NativeRuntimeWorkerIntegrationPlanReviewError(
            "integration plan review boundary changed"
        )
    module = _import_plan(plan_source_path)
    sources_sha256 = {
        name: _file_sha(source_paths[name]) for name in module.EXPECTED
    }
    reproduced = module.build_worker_integration_plan(
        worker,
        backend,
        factory,
        factory_review,
        files_sha256=files_sha256,
        sources_sha256=sources_sha256,
        plan_source_sha256=plan_source_sha,
    )
    if reproduced != plan:
        raise NativeRuntimeWorkerIntegrationPlanReviewError(
            "worker integration plan did not reproduce"
        )
    static = _static_plan_review(plan_source_path)
    surfaces = _review_call_surfaces(source_paths)
    order = _review_order(plan)
    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm273-native-runtime-worker-integration-plan-review-001",
        "status": (
            "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_WORKER_INTEGRATION_IMPLEMENTATION"
        ),
        "source_plan_sha256": plan_hash,
        "source_plan_file_sha256": plan_file_sha256,
        "source_plan_source_sha256": plan_source_sha,
        "definition_reproduced": True,
        "static_plan_review": static,
        "call_surfaces_verified": surfaces,
        "integration_order_verified": order,
        "worker_integration_implementation_admitted": True,
        "worker_review_materialization_required": True,
        "backend_review_materialization_required": True,
        "backend_execution_admitted": False,
        "runtime_execution_admitted": False,
        "launch_admitted": False,
        "attempt_consumed": False,
        "isaac_started": False,
        "scene_loaded": False,
        "physics_steps": 0,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "key_contact": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": (
            "IMPLEMENT_AND_REVIEW_ZERO_AUTHORITY_NATIVE_RUNTIME_WORKER_INTEGRATION"
        ),
        "limitations": [
            "review_is_static_and_executes_no_worker_backend_factory_or_runtime",
            "implementation_must_preserve_arm254_as_sole_attempt_claimant",
            "accepted_worker_and_backend_reviews_must_be_materialized_and_pinned",
            "any_simulation_attempt_requires_separate_exact_authorization",
        ],
    }
    return {**core, "integration_plan_review_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeRuntimeWorkerIntegrationPlanReviewError(
            f"{path} must contain an object"
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-source", type=Path, required=True)
    for name in ("worker", "backend", "factory", "factory-review"):
        parser.add_argument(f"--{name}", type=Path, required=True)
        parser.add_argument(f"--{name}-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document_paths = {
        "worker": args.worker,
        "backend": args.backend,
        "factory": args.factory,
        "factory_review": args.factory_review,
    }
    source_paths = {
        "worker": args.worker_source,
        "backend": args.backend_source,
        "factory": args.factory_source,
        "factory_review": args.factory_review_source,
    }
    result = review_worker_integration_plan(
        _load(args.plan),
        _load(args.worker),
        _load(args.backend),
        _load(args.factory),
        _load(args.factory_review),
        plan_file_sha256=_file_sha(args.plan),
        plan_source_path=args.plan_source,
        source_paths=source_paths,
        files_sha256={name: _file_sha(path) for name, path in document_paths.items()},
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
