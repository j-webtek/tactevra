"""Independently review the ARM-299 fresh-gate claimant.

The reviewer starts no simulator and claims no output. It reopens the accepted
lineage, base worker, and executable sources, then proves the future ordering
of exact authorization, source checks, fresh gates, receipt retention,
single-use consumption, and one worker delegation.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


CLAIMANT_SCHEMA = "tactevra.isaac_lm4_arm299_route_physics_claimant.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_arm299_route_physics_claimant_review.v1"
PLAN_SCHEMA = "tactevra.isaac_lm4_arm299_route_physics_lineage_plan.v1"
PLAN_REVIEW_SCHEMA = (
    "tactevra.isaac_lm4_arm299_route_physics_lineage_plan_review.v1"
)
WORKER_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_worker.v1"
WORKER_REVIEW_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_worker_review.v1"
EXPECTED_AUTHORIZATION = (
    "I authorize exactly one ARM-299 recovered nominal SPACE route-physics "
    "simulation attempt for episode-ef340d0ad2740c118d87, with no automatic "
    "retry, no trajectory playback, and no hardware or physical authority."
)
INTERNAL_WORKER_AUTHORIZATION = (
    "I authorize exactly one ARM-253 nominal SPACE route-physics simulation "
    "attempt for episode-ef340d0ad2740c118d87, with no automatic retry, "
    "no trajectory playback, and no hardware or physical authority."
)
RUNTIME_SOURCE_KEYS = {
    "complete_runtime_composition",
    "concrete_native_attempt_binding",
    "native_runtime_factory",
    "native_runtime_worker_integration",
    "native_session_wrapper",
    "native_sweep_binding",
    "physics_backend",
    "physics_worker",
}
ZERO_AUTHORITY = {
    "authorization_observed": False,
    "attempt_claimed": False,
    "attempt_consumed": False,
    "worker_invoked": False,
    "backend_invoked": False,
    "isaac_imported": False,
    "isaac_started": False,
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
}
LINEAGE_ZERO_AUTHORITY = {
    "authorization_observed": False,
    "attempt_claimed": False,
    "attempt_consumed": False,
    "claimant_constructed": False,
    "launch_admitted": False,
    "worker_invoked": False,
    "backend_invoked": False,
    "isaac_imported": False,
    "isaac_started": False,
    "physics_steps": 0,
    "trajectory_playback": False,
    "joint_positions_submitted": False,
    "joint_targets_submitted": False,
    "key_contact": False,
    "automatic_retry": False,
    "hardware_access": False,
    "physical_authority": False,
}


class Arm299ClaimantReviewError(ValueError):
    """Raised when claimant lineage or ordered authority boundaries drift."""


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
        raise Arm299ClaimantReviewError("review input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Arm299ClaimantReviewError(
            f"required input unavailable: {path}"
        ) from exc


def _digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise Arm299ClaimantReviewError(f"{label} hash changed")
    return claimed


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise Arm299ClaimantReviewError(f"required JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise Arm299ClaimantReviewError(f"required JSON is not an object: {path}")
    return value


def _zero(document: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return all(document.get(key) == value for key, value in expected.items())


def _worker_is_inert(document: Mapping[str, Any]) -> bool:
    return all(
        (
            document.get("isaac_execution_authorized") is False,
            document.get("isaac_started") is False,
            document.get("gpu_started") is False,
            document.get("joint_targets_materialized") is False,
            document.get("trajectory_playback_authorized") is False,
            document.get("native_replay_authorized") is False,
            document.get("hardware_access") is False,
            document.get("hardware_writes") == 0,
            document.get("physical_authority") is False,
            document.get("physical_movements") == 0,
        )
    )


def _static_review(path: Path) -> dict[str, bool]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    if any(
        name.startswith(("isaac", "omni", "serial", "socket", "requests"))
        for name in imports
    ):
        raise Arm299ClaimantReviewError(
            "claimant imports simulator or transport authority"
        )
    forbidden = (
        "set_dof_positions(",
        "set_dof_position_targets(",
        "set_joint_position_targets(",
        "serial.Serial(",
        "SimulationManager.step(",
    )
    if any(token in text for token in forbidden):
        raise Arm299ClaimantReviewError(
            "claimant contains motion or transport command surface"
        )
    run_node = next(
        (
            member
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Arm299Claimant"
            for member in node.body
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            and member.name == "run"
        ),
        None,
    )
    if run_node is None or run_node.end_lineno is None:
        raise Arm299ClaimantReviewError("Arm299Claimant.run is unavailable")
    run_text = "\n".join(text.splitlines()[run_node.lineno - 1 : run_node.end_lineno])
    ordered = (
        "authorization_statement != EXACT_FUTURE_AUTHORIZATION",
        "current_runtime_sources_sha256.items()",
        "self._eula_evaluator(self._eula_collector())",
        "self._memory_evaluator(self._memory_collector())",
        'fresh_eula_receipt.open("x"',
        "fresh_memory_receipt.open(",
        "self._used = True",
        "return self._worker_runner(",
    )
    positions = [run_text.find(token) for token in ordered]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise Arm299ClaimantReviewError(
            "authorization, source, gate, receipt, and worker order changed"
        )
    if run_text.count("return self._worker_runner(") != 1:
        raise Arm299ClaimantReviewError("worker delegation count changed")
    return {
        "simulator_and_transport_imports_absent": True,
        "motion_and_transport_commands_absent": True,
        "exact_authorization_precedes_source_revalidation": True,
        "source_revalidation_precedes_eula_collection": True,
        "eula_pass_precedes_memory_collection": True,
        "memory_pass_precedes_receipt_retention": True,
        "both_receipts_precede_single_use_consumption": True,
        "single_use_consumption_precedes_worker_delegation": True,
    }


def review_claimant(
    definition: Mapping[str, Any],
    *,
    definition_file_sha256: str,
    claimant_source: Path,
    plan_file: Path,
    plan_review_file: Path,
    base_worker_file: Path,
    claimant_review_source: Path,
    eula_preflight_source: Path,
    memory_preflight_source: Path,
    worker_source: Path,
) -> dict[str, Any]:
    """Accept only the exact fresh-gate claimant and ordered implementation."""

    claimant_hash = _require_hash(definition, "claimant_sha256", "ARM-299 claimant")
    plan = _load(plan_file.resolve(strict=True))
    plan_review = _load(plan_review_file.resolve(strict=True))
    base_worker = _load(base_worker_file.resolve(strict=True))
    plan_hash = _require_hash(plan, "plan_sha256", "ARM-299 plan")
    plan_review_hash = _require_hash(
        plan_review, "review_sha256", "ARM-299 plan review"
    )
    base_worker_hash = _require_hash(base_worker, "worker_sha256", "base worker")
    worker = definition.get("worker_preparation")
    worker_review = definition.get("worker_review")
    if not isinstance(worker, Mapping) or not isinstance(worker_review, Mapping):
        raise Arm299ClaimantReviewError("worker evidence changed")
    worker_hash = _require_hash(worker, "worker_sha256", "ARM-299 worker")
    _require_hash(worker_review, "worker_review_sha256", "ARM-299 worker review")
    files = definition.get("source_files_sha256")
    runtime_sources = definition.get("runtime_sources_sha256")
    outputs = plan.get("proposed_outputs")
    if not isinstance(files, Mapping) or not isinstance(outputs, Mapping):
        raise Arm299ClaimantReviewError("claimant evidence inventory changed")
    expected_files = {
        "plan": _file_sha(plan_file),
        "plan_review": _file_sha(plan_review_file),
        "base_worker": _file_sha(base_worker_file),
        "claimant_source": _file_sha(claimant_source),
        "claimant_review_source": _file_sha(claimant_review_source),
        "eula_preflight_source": _file_sha(eula_preflight_source),
        "memory_preflight_source": _file_sha(memory_preflight_source),
        "worker_source": _file_sha(worker_source),
    }
    attempt = Path(str(definition.get("proposed_output_directory", "")))
    eula_receipt = Path(str(definition.get("fresh_eula_receipt", "")))
    memory_receipt = Path(str(definition.get("fresh_memory_receipt", "")))
    eula = definition.get("fresh_eula_preflight")
    memory = definition.get("fresh_memory_preflight")
    failure = definition.get("failure_terminalization")
    static = _static_review(claimant_source.resolve(strict=True))
    if (
        definition.get("schema") != CLAIMANT_SCHEMA
        or definition.get("status")
        != "READY_FOR_INDEPENDENT_ARM299_CLAIMANT_REVIEW"
        or definition.get("source_plan_sha256") != plan_hash
        or definition.get("source_plan_review_sha256") != plan_review_hash
        or definition.get("source_base_worker_sha256") != base_worker_hash
        or files != expected_files
        or not _digest(definition_file_sha256)
        or plan.get("schema") != PLAN_SCHEMA
        or plan.get("status") != "READY_FOR_INDEPENDENT_ARM299_LINEAGE_REVIEW"
        or plan.get("required_future_authorization_statement")
        != EXPECTED_AUTHORIZATION
        or not _zero(plan, LINEAGE_ZERO_AUTHORITY)
        or plan_review.get("schema") != PLAN_REVIEW_SCHEMA
        or plan_review.get("status")
        != "ACCEPTED_FOR_ARM299_CLAIMANT_CONSTRUCTION"
        or plan_review.get("source_plan_sha256") != plan_hash
        or plan_review.get("source_plan_file_sha256") != _file_sha(plan_file)
        or plan_review.get("fresh_outputs_verified_absent") is not True
        or not _zero(plan_review, LINEAGE_ZERO_AUTHORITY)
        or not isinstance(runtime_sources, Mapping)
        or set(runtime_sources) != RUNTIME_SOURCE_KEYS
        or runtime_sources != plan.get("runtime_sources_sha256")
        or definition.get("required_authorization_statement")
        != EXPECTED_AUTHORIZATION
        or definition.get("authorization_reusable") is not False
        or definition.get("worker_authorization_is_internal_compatibility_token")
        is not True
        or definition.get("callable_is_single_use_after_admission") is not True
        or not _zero(definition, ZERO_AUTHORITY)
        or worker.get("schema") != WORKER_SCHEMA
        or worker.get("worker_id") != "arm299-space-route-physics-worker-001"
        or worker.get("recovered_from_worker_sha256") != base_worker_hash
        or worker.get("external_authorization_statement") != EXPECTED_AUTHORIZATION
        or worker.get("required_authorization_statement")
        != INTERNAL_WORKER_AUTHORIZATION
        or worker.get("proposed_output_directory") != str(attempt)
        or not _worker_is_inert(worker)
        or worker_review.get("schema") != WORKER_REVIEW_SCHEMA
        or worker_review.get("source_worker_sha256") != worker_hash
        or worker_review.get("reviewed_backend_sha256")
        != runtime_sources.get("physics_backend")
        or worker_review.get("launch_admitted") is not True
        or worker_review.get("hardware_access") is not False
        or worker_review.get("physical_authority") is not False
        or not isinstance(eula, Mapping)
        or eula.get("required_before_attempt_claim") is not True
        or eula.get("acceptance_variable") != "OMNI_KIT_ACCEPT_EULA"
        or eula.get("required_acceptance_value") != "YES"
        or eula.get("receipt_must_be_retained_before_claim") is not True
        or not isinstance(memory, Mapping)
        or memory.get("required_before_attempt_claim") is not True
        or memory.get("minimum_available_commit_bytes") != 32 * 1024**3
        or memory.get("minimum_available_physical_bytes") != 16 * 1024**3
        or memory.get("maximum_commit_utilization") != 0.9
        or memory.get("receipt_must_be_retained_before_claim") is not True
        or not isinstance(failure, Mapping)
        or failure.get("required_before_simulator_shutdown") is not True
        or failure.get("failing_lifecycle_phase_retained") is not True
        or failure.get("exception_type_and_message_retained") is not True
        or str(attempt) != outputs.get("attempt_directory")
        or str(eula_receipt) != outputs.get("eula_receipt")
        or str(memory_receipt) != outputs.get("memory_receipt")
        or any(path.exists() for path in (attempt, eula_receipt, memory_receipt))
        or eula_receipt.parent.exists()
        or memory_receipt.parent.exists()
    ):
        raise Arm299ClaimantReviewError("ARM-299 claimant review boundary changed")

    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm299-route-physics-claimant-review-001",
        "status": "ACCEPTED_FOR_EXACT_ARM299_ONE_ATTEMPT_AUTHORIZATION",
        "source_claimant_sha256": claimant_hash,
        "source_claimant_file_sha256": definition_file_sha256,
        "source_claimant_source_sha256": _file_sha(claimant_source),
        "source_plan_sha256": plan_hash,
        "source_plan_review_sha256": plan_review_hash,
        "source_base_worker_sha256": base_worker_hash,
        "static_review": static,
        "fresh_gates_precede_attempt_claim": True,
        "both_receipts_precede_attempt_claim": True,
        "failure_terminalization_precedes_shutdown": True,
        "old_authorizations_rejected": True,
        "internal_worker_token_is_not_external_authority": True,
        "single_worker_delegation": True,
        "required_authorization_statement": EXPECTED_AUTHORIZATION,
        "launch_admitted": True,
        **ZERO_AUTHORITY,
        "next_required_stage": "BUILD_REPRODUCIBLE_ARM299_LAUNCH_BINDING",
    }
    return {**core, "claimant_review_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claimant", type=Path, required=True)
    parser.add_argument("--claimant-source", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-review", type=Path, required=True)
    parser.add_argument("--base-worker", type=Path, required=True)
    parser.add_argument("--claimant-review-source", type=Path, required=True)
    parser.add_argument("--eula-preflight-source", type=Path, required=True)
    parser.add_argument("--memory-preflight-source", type=Path, required=True)
    parser.add_argument("--worker-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise Arm299ClaimantReviewError("claimant review output already exists")
    result = review_claimant(
        _load(args.claimant),
        definition_file_sha256=_file_sha(args.claimant),
        claimant_source=args.claimant_source,
        plan_file=args.plan,
        plan_review_file=args.plan_review,
        base_worker_file=args.base_worker,
        claimant_review_source=args.claimant_review_source,
        eula_preflight_source=args.eula_preflight_source,
        memory_preflight_source=args.memory_preflight_source,
        worker_source=args.worker_source,
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
