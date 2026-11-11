"""Independently review ARM-290 without starting Isaac or claiming an attempt."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


REVIEW_SCHEMA = (
    "tactevra.isaac_lm4_terminalized_route_physics_recovery_claimant_review.v1"
)
CLAIMANT_SCHEMA = (
    "tactevra.isaac_lm4_terminalized_route_physics_recovery_claimant.v1"
)
EXPECTED_AUTHORIZATION = (
    "I authorize exactly one ARM-289 terminalized recovered nominal SPACE "
    "route-physics simulation attempt for episode-ef340d0ad2740c118d87, "
    "with no automatic retry, no trajectory playback, and no hardware or "
    "physical authority."
)
EXPECTED_BACKEND_SHA256 = (
    "132f1e028503a3a83af11f2a713f839e00e1fef49aa9cb3fbb0156f858245cde"
)


class TerminalizationRecoveryClaimantReviewError(ValueError):
    """Raised when lineage or fail-before-claim ordering changes."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise TerminalizationRecoveryClaimantReviewError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise TerminalizationRecoveryClaimantReviewError(
            f"required JSON is not an object: {path}"
        )
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    core = dict(document)
    core.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise TerminalizationRecoveryClaimantReviewError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return all(
        (
            document.get("hardware_access") is False,
            document.get("hardware_writes") == 0,
            document.get("physical_authority") is False,
            document.get("physical_movements") == 0,
            document.get("controller_commands") == [],
            document.get("wire_commands") == [],
            document.get("gate_promotions") == [],
        )
    )


def _static_review(path: Path) -> dict[str, bool]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    run_node = next(
        (
            member
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "TerminalizationRecoveryClaimant"
            for member in node.body
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            and member.name == "run"
        ),
        None,
    )
    if run_node is None or run_node.end_lineno is None:
        raise TerminalizationRecoveryClaimantReviewError(
            "TerminalizationRecoveryClaimant.run is unavailable"
        )
    run_text = "\n".join(
        text.splitlines()[run_node.lineno - 1 : run_node.end_lineno]
    )
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    if any(name.startswith(("isaac", "omni", "serial")) for name in imports):
        raise TerminalizationRecoveryClaimantReviewError(
            "claimant imports simulator or hardware authority"
        )
    forbidden = (
        "set_dof_positions(",
        "set_dof_position_targets(",
        "write_data(",
        "serial.Serial(",
    )
    if any(token in text for token in forbidden):
        raise TerminalizationRecoveryClaimantReviewError(
            "claimant contains trajectory or hardware command surface"
        )
    ordered = (
        "authorization_statement != EXACT_AUTHORIZATION",
        "self._eula_evaluator(self._eula_collector())",
        "self._memory_evaluator(self._memory_collector())",
        'fresh_eula_receipt.open("x"',
        'fresh_memory_receipt.open(',
        "self._used = True",
        "return self._worker_runner(",
    )
    positions = [run_text.find(token) for token in ordered]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise TerminalizationRecoveryClaimantReviewError(
            "authorization, EULA, memory, retention, and worker order changed"
        )
    required_source_guards = (
        'claimant_review.get("failure_terminalization_precedes_shutdown")',
        "or not _has_zero_authority(definition)",
        "or not _has_zero_authority(claimant_review)",
    )
    if any(token not in text for token in required_source_guards):
        raise TerminalizationRecoveryClaimantReviewError(
            "terminalization or zero-authority guard changed"
        )
    return {
        "isaac_and_hardware_imports_absent": True,
        "trajectory_and_hardware_commands_absent": True,
        "exact_authorization_precedes_eula_collection": True,
        "eula_pass_precedes_memory_collection": True,
        "memory_pass_precedes_receipt_retention": True,
        "both_receipts_precede_single_use_consumption": True,
        "single_use_consumption_precedes_worker_delegation": True,
        "terminalization_review_guard_present": True,
        "definition_and_review_zero_authority_guards_present": True,
    }


def review_claimant(
    definition: Mapping[str, Any],
    *,
    definition_file_sha256: str,
    claimant_source: Path,
    review_source_sha256: str,
) -> dict[str, Any]:
    """Accept only the exact inert definition and gate-before-claim source."""

    claimant_hash = _require_hash(
        definition, "claimant_sha256", "ARM-290 claimant"
    )
    worker = definition.get("worker_preparation", {})
    worker_review = definition.get("worker_review", {})
    _require_hash(worker, "worker_sha256", "ARM-289 worker preparation")
    _require_hash(worker_review, "worker_review_sha256", "worker review")
    files = definition.get("source_files_sha256", {})
    eula = definition.get("fresh_eula_preflight", {})
    memory = definition.get("fresh_memory_preflight", {})
    failure = definition.get("failure_terminalization", {})
    static = _static_review(claimant_source)
    digests = (definition_file_sha256, review_source_sha256)
    if (
        definition.get("schema") != CLAIMANT_SCHEMA
        or definition.get("status")
        != "READY_FOR_INDEPENDENT_TERMINALIZED_RECOVERY_CLAIMANT_REVIEW"
        or definition.get("required_authorization_statement")
        != EXPECTED_AUTHORIZATION
        or definition.get("worker_authorization_is_internal_compatibility_token")
        is not True
        or definition.get("callable_is_single_use_after_admission") is not True
        or definition.get("automatic_retry") is not False
        or definition.get("runtime_execution_admitted") is not False
        or definition.get("launch_admitted") is not False
        or definition.get("attempt_claimed") is not False
        or definition.get("isaac_started") is not False
        or definition.get("trajectory_playback") is not False
        or definition.get("joint_targets_submitted") is not False
        or not _zero_authority(definition)
        or eula.get("required_before_attempt_claim") is not True
        or eula.get("acceptance_variable") != "OMNI_KIT_ACCEPT_EULA"
        or eula.get("required_acceptance_value") != "YES"
        or eula.get("receipt_must_be_retained_before_claim") is not True
        or memory.get("required_before_attempt_claim") is not True
        or memory.get("receipt_must_be_retained_before_claim") is not True
        or memory.get("minimum_available_commit_bytes") != 32 * 1024**3
        or memory.get("minimum_available_physical_bytes") != 16 * 1024**3
        or memory.get("maximum_commit_utilization") != 0.9
        or failure.get("required_before_simulator_shutdown") is not True
        or failure.get("failing_lifecycle_phase_retained") is not True
        or failure.get("exception_type_and_message_retained") is not True
        or files.get("claimant_source") != _file_sha(claimant_source)
        or worker_review.get("source_worker_sha256") != worker.get("worker_sha256")
        or worker_review.get("reviewed_backend_sha256")
        != EXPECTED_BACKEND_SHA256
        or worker_review.get("launch_admitted") is not True
        or not _zero_authority(worker_review)
        or any(
            not isinstance(value, str) or len(value) != 64 for value in digests
        )
    ):
        raise TerminalizationRecoveryClaimantReviewError(
            "ARM-291 review boundary changed"
        )

    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm291-terminalized-space-recovery-claimant-review-001",
        "status": "ACCEPTED_FOR_EXACT_ARM289_ONE_ATTEMPT_AUTHORIZATION",
        "source_claimant_sha256": claimant_hash,
        "source_claimant_file_sha256": definition_file_sha256,
        "source_claimant_source_sha256": _file_sha(claimant_source),
        "review_source_sha256": review_source_sha256,
        "static_review": static,
        "fresh_eula_gate_precedes_memory_and_attempt_claim": True,
        "fresh_memory_gate_precedes_attempt_claim": True,
        "both_receipts_precede_attempt_claim": True,
        "failure_terminalization_precedes_shutdown": True,
        "old_authorization_rejected": True,
        "single_worker_delegation": True,
        "automatic_retry": False,
        "launch_admitted": True,
        "attempt_consumed": False,
        "isaac_started": False,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": "SEPARATE_EXACT_ARM289_ONE_ATTEMPT_AUTHORIZATION",
    }
    return {**core, "claimant_review_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claimant", type=Path, required=True)
    parser.add_argument("--claimant-source", type=Path, required=True)
    parser.add_argument("--review-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review_claimant(
        _load(args.claimant),
        definition_file_sha256=_file_sha(args.claimant),
        claimant_source=args.claimant_source.resolve(strict=True),
        review_source_sha256=_file_sha(args.review_source),
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=False)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
