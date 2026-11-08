"""Prepare and govern the ARM-254 nominal route-physics worker envelope.

This module implements the fail-closed, one-attempt orchestration boundary.  Its
CLI only builds a reviewable preparation receipt; it does not import Isaac,
start a GPU, generate targets, or execute the worker.  A later reviewed Isaac
backend can be injected into :func:`run_one_attempt` after separate launch
authorization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping


PREPARATION_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_worker.v1"
WORKER_REVIEW_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_worker_review.v1"
REQUEST_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_attempt_request.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_experiment_review.v1"
EXPERIMENT_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_experiment.v1"
EXACT_AUTHORIZATION = (
    "I authorize exactly one ARM-253 nominal SPACE route-physics simulation "
    "attempt for episode-ef340d0ad2740c118d87, with no automatic retry, "
    "no trajectory playback, and no hardware or physical authority."
)
SOURCE_NAMES = {
    "nominal_profile",
    "route_plan",
    "correction_plan",
    "toolchain_lock",
}
RUNTIME_BINDING_NAMES = {
    "robot_usd": "robot_usd_sha256",
    "robot_import_receipt": "robot_import_receipt_sha256",
    "virtual_profile": "virtual_profile_sha256",
    "key_mechanics_profile": "key_mechanics_profile_sha256",
}


class NominalRoutePhysicsWorkerError(ValueError):
    """The worker input changed or crossed its one-attempt authority boundary."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NominalRoutePhysicsWorkerError(
            "worker input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NominalRoutePhysicsWorkerError(f"{path} is not a JSON object")
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise NominalRoutePhysicsWorkerError(f"{label} hash is missing")
    core = dict(document)
    core.pop(key, None)
    if _sha(core) != claimed:
        raise NominalRoutePhysicsWorkerError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("hardware_access") is False
        and document.get("hardware_writes", 0) == 0
        and document.get("physical_authority") is False
        and document.get("physical_movements", 0) == 0
        and document.get("controller_commands", []) == []
        and document.get("wire_commands", []) == []
        and document.get("gate_promotions", []) == []
    )


def _validate_lineage(
    request: Mapping[str, Any],
    review: Mapping[str, Any],
    experiment: Mapping[str, Any],
    route_plan: Mapping[str, Any],
    *,
    source_files_sha256: Mapping[str, str],
    request_file_sha256: str,
    review_file_sha256: str,
    experiment_file_sha256: str,
) -> tuple[str, dict[str, str]]:
    request_hash = _require_hash(request, "request_sha256", "ARM-253 request")
    review_hash = _require_hash(review, "review_sha256", "ARM-252 review")
    experiment_hash = _require_hash(
        experiment, "experiment_sha256", "ARM-251 experiment"
    )
    attempt = request.get("attempt_contract", {})
    acceptance = request.get("acceptance_contract", {})
    output = request.get("output_contract", {})
    route_bindings = route_plan.get("source_bindings", {})
    expected_outputs = {
        "result": "result.json",
        "status": "status.json",
        "regenerated_joint_targets": "regenerated_joint_targets.jsonl",
        "canonical_ik": "canonical_ik.jsonl",
        "continuous_clearance": "continuous_clearance.jsonl",
        "tool_key_metrics": "tool_key_metrics.jsonl",
        "write_outputs_before_simulator_shutdown": True,
        "existing_output_directory_must_be_absent": True,
    }
    if (
        request.get("schema") != REQUEST_SCHEMA
        or request.get("status")
        != "READY_FOR_EXPLICIT_ONE_ATTEMPT_SIMULATION_AUTHORIZATION"
        or request.get("request_id") != "arm253-space-nominal-route-physics-attempt-001"
        or request.get("source_review_sha256") != review_hash
        or request.get("source_review_file_sha256") != review_file_sha256
        or request.get("source_experiment_sha256") != experiment_hash
        or request.get("source_experiment_file_sha256") != experiment_file_sha256
        or request.get("source_files_sha256")
        != dict(sorted(source_files_sha256.items()))
        or set(source_files_sha256) != SOURCE_NAMES
        or review.get("schema") != REVIEW_SCHEMA
        or review.get("source_experiment_sha256") != experiment_hash
        or experiment.get("schema") != EXPERIMENT_SCHEMA
        or experiment.get("source_files_sha256")
        != dict(sorted(source_files_sha256.items()))
        or request.get("case_id") != "nominal-fixture-baseline"
        or request.get("episode_id") != "episode-ef340d0ad2740c118d87"
        or request.get("target_id") != "SPACE"
        or attempt.get("maximum_attempt_count") != 1
        or attempt.get("automatic_retry") is not False
        or attempt.get("fresh_review_and_source_revalidation_required_at_launch")
        is not True
        or attempt.get("generate_only_rows_654_through_940") is not True
        or attempt.get("trajectory_playback") is not False
        or attempt.get("native_replay") is not False
        or attempt.get("hardware_or_physical_authority") is not False
        or acceptance.get("minimum_noncontact_tool_key_clearance_mm") != 0.5
        or acceptance.get("maximum_noncontact_key_displacement_mm") != 0.05
        or acceptance.get("maximum_adjacent_joint_step_rad") != 0.05
        or acceptance.get("canonical_ik_required_for_every_regenerated_row") is not True
        or acceptance.get("continuous_clearance_required_for_every_adjacent_segment")
        is not True
        or output != expected_outputs
        or request.get("required_authorization_statement") != EXACT_AUTHORIZATION
        or request.get("next_required_stage")
        != "IMPLEMENT_AND_REVIEW_FAIL_CLOSED_ONE_ATTEMPT_SIMULATION_WORKER"
        or request.get("isaac_execution_authorized") is not False
        or request.get("isaac_started") is not False
        or request.get("gpu_started") is not False
        or request.get("joint_targets_materialized") is not False
        or request.get("trajectory_playback_authorized") is not False
        or request.get("native_replay_authorized") is not False
        or not _zero_authority(request)
        or not _zero_authority(review)
        or not _zero_authority(experiment)
        or any(
            not isinstance(value, str) or len(value) != 64
            for value in (
                request_file_sha256,
                review_file_sha256,
                experiment_file_sha256,
                *source_files_sha256.values(),
            )
        )
    ):
        raise NominalRoutePhysicsWorkerError("ARM-254 lineage boundary changed")

    runtime_bindings: dict[str, str] = {}
    for name, source_key in RUNTIME_BINDING_NAMES.items():
        value = route_bindings.get(source_key)
        if not isinstance(value, str) or len(value) != 64:
            raise NominalRoutePhysicsWorkerError(
                f"route omits required runtime binding {source_key}"
            )
        runtime_bindings[name] = value
    return request_hash, runtime_bindings


def build_preparation(
    request: Mapping[str, Any],
    review: Mapping[str, Any],
    experiment: Mapping[str, Any],
    route_plan: Mapping[str, Any],
    *,
    source_files_sha256: Mapping[str, str],
    request_file_sha256: str,
    review_file_sha256: str,
    experiment_file_sha256: str,
    proposed_output_directory: str,
) -> dict[str, Any]:
    """Build the deterministic worker envelope without starting the worker."""

    request_hash, runtime_bindings = _validate_lineage(
        request,
        review,
        experiment,
        route_plan,
        source_files_sha256=source_files_sha256,
        request_file_sha256=request_file_sha256,
        review_file_sha256=review_file_sha256,
        experiment_file_sha256=experiment_file_sha256,
    )
    if (
        not proposed_output_directory
        or not Path(proposed_output_directory).is_absolute()
    ):
        raise NominalRoutePhysicsWorkerError(
            "proposed output directory must be an absolute path"
        )

    core: dict[str, Any] = {
        "schema": PREPARATION_SCHEMA,
        "worker_id": "arm254-space-nominal-route-physics-worker-001",
        "status": "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW",
        "source_request_sha256": request_hash,
        "source_request_file_sha256": request_file_sha256,
        "source_review_sha256": review["review_sha256"],
        "source_review_file_sha256": review_file_sha256,
        "source_experiment_sha256": experiment["experiment_sha256"],
        "source_experiment_file_sha256": experiment_file_sha256,
        "source_files_sha256": dict(sorted(source_files_sha256.items())),
        "runtime_bindings_sha256": dict(sorted(runtime_bindings.items())),
        "proposed_output_directory": proposed_output_directory,
        "attempt_ledger": {
            "maximum_attempt_count": 1,
            "attempts_consumed_by_preparation": 0,
            "automatic_retry": False,
            "output_directory_claim": "ATOMIC_CREATE_NEW_DIRECTORY",
            "existing_directory_disposition": "FAIL_BEFORE_ISAAC_IMPORT",
            "failure_disposition": "RETAIN_STATUS_AND_STOP",
        },
        "launch_order": [
            "revalidate_request_review_experiment_and_four_source_files",
            "revalidate_four_runtime_bindings",
            "verify_exact_authorization_statement",
            "verify_independently_accepted_worker_envelope",
            "atomically_claim_absent_output_directory",
            "write_claimed_status_before_isaac_import",
            "import_and_start_single_gpu_headless_isaac",
            "run_exactly_one_nominal_fixture_case",
            "write_all_outputs_before_simulator_shutdown",
            "shutdown_and_retain_terminal_status_without_retry",
        ],
        "backend_contract": {
            "regeneration_first_sequence": 654,
            "regeneration_last_sequence": 940,
            "regenerated_row_count": 287,
            "source_sample_count": 1416,
            "preserved_contact_endpoint_sequences": [1061, 1299],
            "required_output_files": list(request["output_contract"].values())[:6],
            "canonical_ik_for_every_regenerated_row": True,
            "continuous_clearance_for_every_adjacent_segment": True,
            "trajectory_playback": False,
            "native_replay": False,
        },
        "required_authorization_statement": EXACT_AUTHORIZATION,
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
        "next_required_stage": (
            "IMPLEMENT_AND_INDEPENDENTLY_REVIEW_PINNED_ISAAC_PHYSICS_BACKEND"
        ),
        "limitations": [
            "preparation_does_not_import_or_start_isaac_or_a_gpu",
            "worker_envelope_does_not_yet_implement_the_isaac_physics_backend",
            "no_joint_target_generation_or_trajectory_playback_occurs",
            "single_space_case_is_not_multi_key_automatic_typing",
            "simulation_result_cannot_authorize_hardware_or_physical_motion",
        ],
    }
    return {**core, "worker_sha256": _sha(core)}


Backend = Callable[[Path], Mapping[str, Any]]


def run_one_attempt(
    preparation: Mapping[str, Any],
    *,
    worker_review: Mapping[str, Any],
    authorization_statement: str,
    output_directory: Path,
    current_source_files_sha256: Mapping[str, str],
    current_runtime_bindings_sha256: Mapping[str, str],
    backend: Backend,
) -> Mapping[str, Any]:
    """Claim and run one injected backend attempt without retry.

    This testable envelope is intentionally not exposed by the CLI until a
    separately reviewed, hash-pinned Isaac backend exists.
    """

    worker_hash = _require_hash(
        preparation, "worker_sha256", "ARM-254 worker preparation"
    )
    review_hash = _require_hash(
        worker_review, "worker_review_sha256", "ARM-254 worker review"
    )
    if (
        preparation.get("schema") != PREPARATION_SCHEMA
        or preparation.get("status") != "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW"
        or preparation.get("isaac_backend_implemented_by_this_envelope") is not False
        or worker_review.get("schema") != WORKER_REVIEW_SCHEMA
        or worker_review.get("status")
        != "ACCEPTED_FOR_ONE_SEPARATELY_AUTHORIZED_SIMULATION_ATTEMPT"
        or worker_review.get("source_worker_sha256") != worker_hash
        or not isinstance(worker_review.get("reviewed_backend_sha256"), str)
        or len(worker_review["reviewed_backend_sha256"]) != 64
        or worker_review.get("launch_admitted") is not True
        or not isinstance(review_hash, str)
        or authorization_statement != EXACT_AUTHORIZATION
        or str(output_directory) != preparation.get("proposed_output_directory")
        or output_directory.exists()
        or dict(sorted(current_source_files_sha256.items()))
        != preparation.get("source_files_sha256")
        or dict(sorted(current_runtime_bindings_sha256.items()))
        != preparation.get("runtime_bindings_sha256")
        or not _zero_authority(preparation)
        or not _zero_authority(worker_review)
    ):
        raise NominalRoutePhysicsWorkerError(
            "worker attempt is not admitted by the reviewed envelope"
        )
    output_directory.mkdir(parents=False, exist_ok=False)
    status_path = output_directory / "status.json"
    status_path.write_text(
        json.dumps(
            {
                "status": "ATTEMPT_CLAIMED_BACKEND_PENDING",
                "attempt_count": 1,
                "automatic_retry": False,
                "hardware_access": False,
                "physical_authority": False,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        return backend(output_directory)
    except BaseException as exc:
        status_path.write_text(
            json.dumps(
                {
                    "status": "FAILED_RETAINED_NO_RETRY",
                    "attempt_count": 1,
                    "automatic_retry": False,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "hardware_access": False,
                    "physical_authority": False,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--nominal-profile", type=Path, required=True)
    parser.add_argument("--route-plan", type=Path, required=True)
    parser.add_argument("--correction-plan", type=Path, required=True)
    parser.add_argument("--toolchain-lock", type=Path, required=True)
    parser.add_argument("--proposed-output-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        "nominal_profile": args.nominal_profile.resolve(strict=True),
        "route_plan": args.route_plan.resolve(strict=True),
        "correction_plan": args.correction_plan.resolve(strict=True),
        "toolchain_lock": args.toolchain_lock.resolve(strict=True),
    }
    request_path = args.request.resolve(strict=True)
    review_path = args.review.resolve(strict=True)
    experiment_path = args.experiment.resolve(strict=True)
    proposed = args.proposed_output_directory.resolve()
    if proposed.exists():
        raise NominalRoutePhysicsWorkerError(
            "proposed attempt output directory already exists"
        )
    result = build_preparation(
        _load_object(request_path),
        _load_object(review_path),
        _load_object(experiment_path),
        _load_object(paths["route_plan"]),
        source_files_sha256={name: _file_sha(path) for name, path in paths.items()},
        request_file_sha256=_file_sha(request_path),
        review_file_sha256=_file_sha(review_path),
        experiment_file_sha256=_file_sha(experiment_path),
        proposed_output_directory=str(proposed),
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
