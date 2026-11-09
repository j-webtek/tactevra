"""Plan the ARM-273 native-runtime worker integration without executing it.

The plan connects the existing one-attempt worker, deterministic backend, and
reviewed ARM-272 factory at the contract level.  It imports no Isaac module,
constructs no runtime object, claims no output directory, and calls no worker,
backend, or runtime protocol method.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PLAN_SCHEMA = "tactevra.isaac_lm4_native_runtime_worker_integration_plan.v1"
PLAN_REVIEW_SCHEMA = (
    "tactevra.isaac_lm4_native_runtime_worker_integration_plan_review.v1"
)
WORKER_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_worker.v1"
BACKEND_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_backend.v1"
FACTORY_SCHEMA = "tactevra.isaac_lm4_native_runtime_factory.v1"
FACTORY_REVIEW_SCHEMA = "tactevra.isaac_lm4_native_runtime_factory_review.v1"

EXPECTED = {
    "worker": {
        "canonical": "f1fb3eaeb23f2dd70a6c29b2dd13e50b6390b9b0bbaadf64b5aaeff84ba142f7",
        "file": "8a8dcea01c68eb6e8e4af88e163c87f6b37943ab72c9abed1c7b171178a610d5",
        "source": "21b7010877ee363fc90e5bacf651ee2b9ee11a5524904b51aefcb11760767e2c",
    },
    "backend": {
        "canonical": "132f1e028503a3a83af11f2a713f839e00e1fef49aa9cb3fbb0156f858245cde",
        "file": "968140c9b075cc4f6a8d5599edc765cd1b6cde734e32e6632513bd2c94fb6228",
        "source": "b7fdcded95e1c2316506cbf9d1c3986e908e63c91e422dea0c90f0bc032862ae",
    },
    "factory": {
        "canonical": "1ff2ffdd97b5ec8514a86fdb21e1cac3aae8a445d388a8b10a9fd6775e6fe818",
        "file": "6572a0a9166106c0321349ef4b8276154f06ab775ec478a941869e6b5c7ce854",
        "source": "d23a94ee333456c3a0a9ca314b40d5c1568469847f0b9e882709e1fb45d72c44",
    },
    "factory_review": {
        "canonical": "5ec24c47b771d8ecb63b1db839562a62f973b5b2aa3a0ba7cb75d7da1d7bf6f7",
        "file": "0418f5c0e6d4e9fe35de36be68a9f46a05dbccb2ba4ea0f15231a8828542aca0",
        "source": "f19843cca23a8188fb40e9a4a7e2cc95007471220a821e1547c52e73100bbdbf",
    },
}


class NativeRuntimeWorkerIntegrationPlanError(ValueError):
    """Raised when the proposed integration lineage changes."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError) as exc:
        raise NativeRuntimeWorkerIntegrationPlanError(
            "input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeRuntimeWorkerIntegrationPlanError(f"{label} hash changed")
    return claimed


def build_worker_integration_plan(
    worker: Mapping[str, Any],
    backend: Mapping[str, Any],
    factory: Mapping[str, Any],
    factory_review: Mapping[str, Any],
    *,
    files_sha256: Mapping[str, str],
    sources_sha256: Mapping[str, str],
    plan_source_sha256: str,
) -> dict[str, Any]:
    """Build a reviewable integration plan without invoking any integration."""
    hashes = {
        "worker": _require_hash(worker, "worker_sha256", "ARM-254 worker"),
        "backend": _require_hash(backend, "backend_sha256", "ARM-255 backend"),
        "factory": _require_hash(factory, "factory_sha256", "ARM-272 factory"),
        "factory_review": _require_hash(
            factory_review, "factory_review_sha256", "ARM-272 factory review"
        ),
    }
    if (
        worker.get("schema") != WORKER_SCHEMA
        or worker.get("status") != "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW"
        or worker.get("attempt_ledger", {}).get("maximum_attempt_count") != 1
        or worker.get("attempt_ledger", {}).get("automatic_retry") is not False
        or worker.get("attempt_ledger", {}).get("attempts_consumed_by_preparation")
        != 0
        or worker.get("isaac_started") is not False
        or worker.get("hardware_access") is not False
        or worker.get("physical_authority") is not False
        or backend.get("schema") != BACKEND_SCHEMA
        or backend.get("status")
        != "READY_FOR_INDEPENDENT_BACKEND_AND_RUNTIME_ADAPTER_REVIEW"
        or backend.get("source_worker_sha256") != hashes["worker"]
        or backend.get("isaac_runtime_adapter_implemented_by_core") is not False
        or backend.get("isaac_execution_authorized") is not False
        or backend.get("hardware_access") is not False
        or backend.get("physical_authority") is not False
        or factory.get("schema") != FACTORY_SCHEMA
        or factory.get("status")
        != "READY_FOR_INDEPENDENT_NATIVE_RUNTIME_FACTORY_REVIEW"
        or factory.get("runtime_execution_admitted") is not False
        or factory.get("launch_admitted") is not False
        or factory_review.get("schema") != FACTORY_REVIEW_SCHEMA
        or factory_review.get("status")
        != "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_FACTORY_USE"
        or factory_review.get("source_factory_sha256") != hashes["factory"]
        or factory_review.get("runtime_construction_admitted") is not True
        or factory_review.get("backend_execution_admitted") is not False
        or factory_review.get("runtime_execution_admitted") is not False
        or factory_review.get("launch_admitted") is not False
        or any(
            document.get("controller_commands") != []
            or document.get("wire_commands") != []
            or document.get("gate_promotions") != []
            for document in (worker, backend, factory, factory_review)
        )
        or set(files_sha256) != set(EXPECTED)
        or set(sources_sha256) != set(EXPECTED)
        or any(hashes[name] != EXPECTED[name]["canonical"] for name in EXPECTED)
        or any(files_sha256[name] != EXPECTED[name]["file"] for name in EXPECTED)
        or any(
            sources_sha256[name] != EXPECTED[name]["source"] for name in EXPECTED
        )
        or not isinstance(plan_source_sha256, str)
        or len(plan_source_sha256) != 64
    ):
        raise NativeRuntimeWorkerIntegrationPlanError(
            "native runtime worker integration lineage changed"
        )

    core: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "plan_id": "arm273-native-runtime-worker-integration-plan-001",
        "status": "READY_FOR_INDEPENDENT_NATIVE_RUNTIME_WORKER_INTEGRATION_PLAN_REVIEW",
        "source_documents_sha256": dict(sorted(hashes.items())),
        "source_files_sha256": dict(sorted(files_sha256.items())),
        "source_code_sha256": dict(sorted(sources_sha256.items())),
        "plan_source_sha256": plan_source_sha256,
        "integration_boundary": {
            "worker_entrypoint": "nominal_route_physics_worker.run_one_attempt",
            "backend_entrypoint": "nominal_route_physics_backend.execute_backend",
            "runtime_factory_entrypoint": (
                "nominal_route_native_runtime_factory.construct_runtime"
            ),
            "worker_remains_sole_output_directory_claimant": True,
            "backend_callable_is_injected_without_side_effects": True,
            "factory_receives_only_already_initialized_supplied_objects": True,
            "factory_result_is_passed_as_backend_runtime": True,
            "backend_is_called_exactly_once_after_worker_claim": True,
            "automatic_retry": False,
        },
        "required_future_inputs": {
            "accepted_worker_review": {
                "schema": "tactevra.isaac_lm4_nominal_route_physics_worker_review.v1",
                "source_worker_sha256": hashes["worker"],
                "reviewed_backend_sha256": hashes["backend"],
                "launch_admitted_only_by_separate_attempt_authorization": True,
            },
            "accepted_backend_review": {
                "schema": "tactevra.isaac_lm4_nominal_route_physics_backend_review.v1",
                "source_backend_sha256": hashes["backend"],
                "reviewed_runtime_adapter_sha256": hashes["factory"],
                "continuous_clearance_protocol_accepted": True,
                "launch_admitted_only_by_separate_attempt_authorization": True,
            },
            "exact_worker_documents": [
                "route_plan",
                "factory_definition",
                "factory_review",
                "arm271_plan",
                "arm271_plan_review",
                "all_twelve_factory_component_documents",
            ],
            "already_initialized_native_objects": [
                "articulation",
                "environment_only_scene_query",
                "single_key_view",
                "single_root_view",
            ],
            "worker_pinned_values": [
                "target_key_prim_path",
                "solver_kwargs",
                "native_metadata",
            ],
        },
        "required_future_order": [
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
        ],
        "failure_policy": {
            "before_worker_claim": "FAIL_WITHOUT_CREATING_ATTEMPT_DIRECTORY",
            "after_worker_claim": "RETAIN_FAILED_STATUS_AND_STOP",
            "factory_or_backend_failure": "NO_RETRY",
            "indeterminate_native_query": "FAIL_CLOSED",
            "shutdown_failure": "RETAIN_TERMINAL_EVIDENCE_AND_STOP",
        },
        "review_requirements": [
            "verify_worker_claim_precedes_isaac_import_or_launch",
            "verify_factory_construction_follows_scene_settle",
            "verify_factory_runtime_identity_is_passed_to_backend",
            "verify_exactly_one_backend_call_and_zero_retry_paths",
            "verify_all_outputs_precede_shutdown",
            "verify_no_hardware_or_controller_imports",
        ],
        "worker_integration_implemented": False,
        "worker_review_materialized": False,
        "backend_review_materialized": False,
        "runtime_objects_constructed": False,
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
            "INDEPENDENTLY_REVIEW_NATIVE_RUNTIME_WORKER_INTEGRATION_PLAN"
        ),
        "limitations": [
            "plan_does_not_import_or_start_isaac_or_claim_an_attempt",
            "accepted_worker_and_backend_review_artifacts_remain_required",
            "implementation_requires_separate_review_before_any_attempt",
            "simulation_result_cannot_authorize_hardware_or_physical_motion",
        ],
    }
    return {**core, "integration_plan_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeRuntimeWorkerIntegrationPlanError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in EXPECTED:
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
        parser.add_argument(
            f"--{name.replace('_', '-')}-source", type=Path, required=True
        )
    parser.add_argument("--plan-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {name: getattr(args, name) for name in EXPECTED}
    sources = {name: getattr(args, f"{name}_source") for name in EXPECTED}
    result = build_worker_integration_plan(
        _load(paths["worker"]),
        _load(paths["backend"]),
        _load(paths["factory"]),
        _load(paths["factory_review"]),
        files_sha256={name: _file_sha(path) for name, path in paths.items()},
        sources_sha256={name: _file_sha(path) for name, path in sources.items()},
        plan_source_sha256=_file_sha(args.plan_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
