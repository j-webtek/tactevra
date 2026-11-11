"""Bind ARM-289 to one worker behind fresh EULA and memory gates.

The CLI only builds an inert ARM-290 claimant definition. Runtime use requires
an independent ARM-291 review and the exact ARM-289 authorization. Neither
definition building nor admission grants hardware or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from nominal_route_isaac_eula_preflight import evaluate_eula_preflight
from nominal_route_memory_preflight import (
    MemorySnapshot,
    collect_windows_memory_snapshot,
    evaluate_memory_preflight,
)
from nominal_route_physics_terminalization_recovery_request import (
    EXACT_AUTHORIZATION,
    INTEGRATION_REVIEW_SCHEMA,
    INTEGRATION_SCHEMA,
    SCHEMA as RECOVERY_REQUEST_SCHEMA,
)
from nominal_route_physics_worker import (
    EXACT_AUTHORIZATION as WORKER_AUTHORIZATION,
)
from nominal_route_physics_worker import run_one_attempt


SCHEMA = "tactevra.isaac_lm4_terminalized_route_physics_recovery_claimant.v1"
REVIEW_SCHEMA = (
    "tactevra.isaac_lm4_terminalized_route_physics_recovery_claimant_review.v1"
)
WORKER_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_worker.v1"
WORKER_REVIEW_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_worker_review.v1"
EXPECTED_BACKEND_SHA256 = (
    "132f1e028503a3a83af11f2a713f839e00e1fef49aa9cb3fbb0156f858245cde"
)


class TerminalizationRecoveryClaimantError(RuntimeError):
    """Raised when admission evidence or the one-use boundary changes."""


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
        raise TerminalizationRecoveryClaimantError(
            "input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise TerminalizationRecoveryClaimantError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise TerminalizationRecoveryClaimantError(
            f"required JSON is not an object: {path}"
        )
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    core = dict(document)
    core.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise TerminalizationRecoveryClaimantError(f"{label} hash changed")
    return claimed


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value.lower()
    )


def _zero_authority() -> dict[str, Any]:
    return {
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }


def _has_zero_authority(document: Mapping[str, Any]) -> bool:
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


def build_claimant_definition(
    recovery_request: Mapping[str, Any],
    worker_preparation: Mapping[str, Any],
    integration: Mapping[str, Any],
    integration_review: Mapping[str, Any],
    *,
    recovery_request_file_sha256: str,
    worker_preparation_file_sha256: str,
    integration_file_sha256: str,
    integration_review_file_sha256: str,
    claimant_source_sha256: str,
    recovery_request_source_sha256: str,
    integration_source_sha256: str,
    integration_review_source_sha256: str,
    memory_preflight_source_sha256: str,
    eula_preflight_source_sha256: str,
    worker_source_sha256: str,
) -> dict[str, Any]:
    """Build an inert claimant without collecting gates or claiming an attempt."""

    recovery_hash = _require_hash(
        recovery_request, "request_sha256", "ARM-289 recovery request"
    )
    worker_hash = _require_hash(
        worker_preparation, "worker_sha256", "ARM-289 worker preparation"
    )
    integration_hash = _require_hash(
        integration, "integration_sha256", "ARM-287 integration"
    )
    review_hash = _require_hash(
        integration_review,
        "integration_review_sha256",
        "ARM-288 integration review",
    )
    attempt = recovery_request.get("attempt_contract", {})
    ledger = worker_preparation.get("attempt_ledger", {})
    integration_sources = integration.get("source_files_sha256", {})
    hashes = (
        recovery_request_file_sha256,
        worker_preparation_file_sha256,
        integration_file_sha256,
        integration_review_file_sha256,
        claimant_source_sha256,
        recovery_request_source_sha256,
        integration_source_sha256,
        integration_review_source_sha256,
        memory_preflight_source_sha256,
        eula_preflight_source_sha256,
        worker_source_sha256,
    )
    if (
        recovery_request.get("schema") != RECOVERY_REQUEST_SCHEMA
        or recovery_request.get("status")
        != "READY_FOR_INDEPENDENT_TERMINALIZED_RECOVERY_CLAIMANT_REVIEW"
        or recovery_request.get("required_authorization_statement")
        != EXACT_AUTHORIZATION
        or recovery_request.get("old_authorization_reusable") is not False
        or recovery_request.get("attempt_claimed") is not False
        or recovery_request.get("isaac_started") is not False
        or recovery_request.get("request_source_file_sha256")
        != recovery_request_source_sha256
        or attempt.get("maximum_attempt_count") != 1
        or attempt.get("automatic_retry") is not False
        or attempt.get("claim_only_after_fresh_memory_preflight") is not True
        or attempt.get("claim_only_after_fresh_eula_preflight") is not True
        or attempt.get("terminalize_before_simulator_shutdown") is not True
        or attempt.get("trajectory_playback") is not False
        or attempt.get("hardware_or_physical_authority") is not False
        or worker_preparation.get("schema") != WORKER_SCHEMA
        or worker_preparation.get("status")
        != "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW"
        or worker_preparation.get("source_request_sha256")
        != recovery_request.get("source_worker_request_sha256")
        or worker_preparation.get("proposed_output_directory")
        != recovery_request.get("proposed_output_directory")
        or worker_preparation.get("required_authorization_statement")
        != WORKER_AUTHORIZATION
        or ledger.get("maximum_attempt_count") != 1
        or ledger.get("attempts_consumed_by_preparation") != 0
        or ledger.get("automatic_retry") is not False
        or worker_preparation.get("isaac_execution_authorized") is not False
        or worker_preparation.get("isaac_started") is not False
        or worker_preparation.get("hardware_access") is not False
        or worker_preparation.get("physical_authority") is not False
        or integration.get("schema") != INTEGRATION_SCHEMA
        or integration.get("integration_id")
        != "arm287-terminalizing-native-runtime-worker-integration-001"
        or integration_hash != recovery_request.get("source_integration_sha256")
        or integration_file_sha256
        != recovery_request.get("source_integration_file_sha256")
        or integration_sources.get("arm274_integration_source")
        != integration_source_sha256
        or "terminalize_failure_before_shutdown"
        not in integration.get("lifecycle", [])
        or integration.get("launch_admitted") is not False
        or integration_review.get("schema") != INTEGRATION_REVIEW_SCHEMA
        or review_hash
        != recovery_request.get("source_integration_review_sha256")
        or integration_review_file_sha256
        != recovery_request.get("source_integration_review_file_sha256")
        or integration_review.get("source_integration_sha256") != integration_hash
        or integration_review.get("source_integration_source_sha256")
        != integration_source_sha256
        or integration_review.get("review_source_sha256")
        != integration_review_source_sha256
        or integration_review.get("failure_terminalization_precedes_shutdown")
        is not True
        or integration_review.get("launch_admitted") is not False
        or any(not _digest(value) for value in hashes)
    ):
        raise TerminalizationRecoveryClaimantError(
            "ARM-290 claimant boundary changed"
        )

    worker_review_core = {
        "schema": WORKER_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ONE_SEPARATELY_AUTHORIZED_SIMULATION_ATTEMPT",
        "source_worker_sha256": worker_hash,
        "reviewed_backend_sha256": EXPECTED_BACKEND_SHA256,
        "launch_admitted": True,
        **_zero_authority(),
    }
    worker_review = {
        **worker_review_core,
        "worker_review_sha256": _sha(worker_review_core),
    }
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "claimant_id": "arm290-terminalized-space-recovery-claimant-001",
        "status": "READY_FOR_INDEPENDENT_TERMINALIZED_RECOVERY_CLAIMANT_REVIEW",
        "source_recovery_request_sha256": recovery_hash,
        "source_worker_sha256": worker_hash,
        "source_integration_sha256": integration_hash,
        "source_integration_review_sha256": review_hash,
        "source_files_sha256": {
            "recovery_request": recovery_request_file_sha256,
            "worker_preparation": worker_preparation_file_sha256,
            "integration": integration_file_sha256,
            "integration_review": integration_review_file_sha256,
            "claimant_source": claimant_source_sha256,
            "recovery_request_source": recovery_request_source_sha256,
            "integration_source": integration_source_sha256,
            "integration_review_source": integration_review_source_sha256,
            "memory_preflight_source": memory_preflight_source_sha256,
            "eula_preflight_source": eula_preflight_source_sha256,
            "worker_source": worker_source_sha256,
        },
        "worker_preparation": dict(worker_preparation),
        "worker_review": worker_review,
        "required_authorization_statement": EXACT_AUTHORIZATION,
        "worker_authorization_is_internal_compatibility_token": True,
        "fresh_eula_preflight": {
            "required_before_attempt_claim": True,
            "acceptance_variable": "OMNI_KIT_ACCEPT_EULA",
            "required_acceptance_value": "YES",
            "receipt_must_be_retained_before_claim": True,
        },
        "fresh_memory_preflight": {
            "required_before_attempt_claim": True,
            "minimum_available_commit_bytes": 32 * 1024**3,
            "minimum_available_physical_bytes": 16 * 1024**3,
            "maximum_commit_utilization": 0.9,
            "receipt_must_be_retained_before_claim": True,
        },
        "failure_terminalization": {
            "required_before_simulator_shutdown": True,
            "failing_lifecycle_phase_retained": True,
            "exception_type_and_message_retained": True,
        },
        "proposed_output_directory": recovery_request["proposed_output_directory"],
        "callable_is_single_use_after_admission": True,
        "automatic_retry": False,
        "runtime_execution_admitted": False,
        "launch_admitted": False,
        "attempt_claimed": False,
        "isaac_started": False,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        **_zero_authority(),
        "next_required_stage": "INDEPENDENTLY_REVIEW_ARM290_RECOVERY_CLAIMANT",
    }
    return {**core, "claimant_sha256": _sha(core)}


Backend = Callable[[Path], Mapping[str, Any]]
EulaCollector = Callable[[], Mapping[str, str]]
EulaEvaluator = Callable[[Mapping[str, str]], Mapping[str, Any]]
MemoryCollector = Callable[[], MemorySnapshot]
MemoryEvaluator = Callable[[MemorySnapshot], Mapping[str, Any]]
WorkerRunner = Callable[..., Mapping[str, Any]]


class TerminalizationRecoveryClaimant:
    """Single-use adapter gated by independent review, EULA, and memory."""

    def __init__(
        self,
        definition: Mapping[str, Any],
        claimant_review: Mapping[str, Any],
        *,
        eula_collector: EulaCollector = lambda: os.environ,
        eula_evaluator: EulaEvaluator = evaluate_eula_preflight,
        memory_collector: MemoryCollector = collect_windows_memory_snapshot,
        memory_evaluator: MemoryEvaluator = evaluate_memory_preflight,
        worker_runner: WorkerRunner = run_one_attempt,
    ) -> None:
        claimant_hash = _require_hash(
            definition, "claimant_sha256", "ARM-290 claimant"
        )
        _require_hash(
            claimant_review, "claimant_review_sha256", "ARM-291 claimant review"
        )
        if (
            definition.get("schema") != SCHEMA
            or definition.get("status")
            != "READY_FOR_INDEPENDENT_TERMINALIZED_RECOVERY_CLAIMANT_REVIEW"
            or claimant_review.get("schema") != REVIEW_SCHEMA
            or claimant_review.get("status")
            != "ACCEPTED_FOR_EXACT_ARM289_ONE_ATTEMPT_AUTHORIZATION"
            or claimant_review.get("source_claimant_sha256") != claimant_hash
            or claimant_review.get("launch_admitted") is not True
            or claimant_review.get("failure_terminalization_precedes_shutdown")
            is not True
            or definition.get("runtime_execution_admitted") is not False
            or definition.get("launch_admitted") is not False
            or definition.get("attempt_claimed") is not False
            or definition.get("isaac_started") is not False
            or definition.get("trajectory_playback") is not False
            or definition.get("joint_targets_submitted") is not False
            or definition.get("automatic_retry") is not False
            or definition.get("callable_is_single_use_after_admission") is not True
            or not _has_zero_authority(definition)
            or not _has_zero_authority(claimant_review)
        ):
            raise TerminalizationRecoveryClaimantError(
                "claimant review boundary changed"
            )
        self._definition = definition
        self._eula_collector = eula_collector
        self._eula_evaluator = eula_evaluator
        self._memory_collector = memory_collector
        self._memory_evaluator = memory_evaluator
        self._worker_runner = worker_runner
        self._used = False

    def run(
        self,
        *,
        authorization_statement: str,
        output_directory: Path,
        fresh_eula_receipt: Path,
        fresh_memory_receipt: Path,
        current_source_files_sha256: Mapping[str, str],
        current_runtime_bindings_sha256: Mapping[str, str],
        backend: Backend,
    ) -> Mapping[str, Any]:
        """Delegate once only after retaining fresh passing gate receipts."""

        preparation = self._definition["worker_preparation"]
        if (
            self._used
            or authorization_statement != EXACT_AUTHORIZATION
            or str(output_directory) != self._definition["proposed_output_directory"]
            or output_directory.exists()
            or fresh_eula_receipt.exists()
            or fresh_memory_receipt.exists()
        ):
            raise TerminalizationRecoveryClaimantError(
                "recovery attempt is not admitted"
            )
        eula = dict(self._eula_evaluator(self._eula_collector()))
        if (
            eula.get("status") != "PASS_EULA_PREFLIGHT"
            or eula.get("launch_admitted") is not True
            or eula.get("acceptance_observed") is not True
            or eula.get("acceptance_performed_by_preflight") is not False
            or eula.get("attempt_claimed") is not False
            or eula.get("isaac_started") is not False
            or eula.get("hardware_access") is not False
            or eula.get("physical_authority") is not False
        ):
            raise TerminalizationRecoveryClaimantError(
                "fresh EULA preflight refused launch"
            )
        memory = dict(self._memory_evaluator(self._memory_collector()))
        if (
            memory.get("status") != "PASS_MEMORY_PREFLIGHT"
            or memory.get("launch_admitted") is not True
            or memory.get("attempt_claimed") is not False
            or memory.get("isaac_started") is not False
            or memory.get("hardware_access") is not False
            or memory.get("physical_authority") is not False
        ):
            raise TerminalizationRecoveryClaimantError(
                "fresh memory preflight refused launch"
            )
        fresh_eula_receipt.parent.mkdir(parents=True, exist_ok=True)
        with fresh_eula_receipt.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(eula, indent=2, sort_keys=True) + "\n")
        fresh_memory_receipt.parent.mkdir(parents=True, exist_ok=True)
        with fresh_memory_receipt.open(
            "x", encoding="utf-8", newline="\n"
        ) as stream:
            stream.write(json.dumps(memory, indent=2, sort_keys=True) + "\n")
        self._used = True
        return self._worker_runner(
            preparation,
            worker_review=self._definition["worker_review"],
            authorization_statement=WORKER_AUTHORIZATION,
            output_directory=output_directory,
            current_source_files_sha256=current_source_files_sha256,
            current_runtime_bindings_sha256=current_runtime_bindings_sha256,
            backend=backend,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recovery-request", type=Path, required=True)
    parser.add_argument("--worker-preparation", type=Path, required=True)
    parser.add_argument("--integration", type=Path, required=True)
    parser.add_argument("--integration-review", type=Path, required=True)
    parser.add_argument("--claimant-source", type=Path, required=True)
    parser.add_argument("--recovery-request-source", type=Path, required=True)
    parser.add_argument("--integration-source", type=Path, required=True)
    parser.add_argument("--integration-review-source", type=Path, required=True)
    parser.add_argument("--memory-preflight-source", type=Path, required=True)
    parser.add_argument("--eula-preflight-source", type=Path, required=True)
    parser.add_argument("--worker-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_claimant_definition(
        _load(args.recovery_request),
        _load(args.worker_preparation),
        _load(args.integration),
        _load(args.integration_review),
        recovery_request_file_sha256=_file_sha(args.recovery_request),
        worker_preparation_file_sha256=_file_sha(args.worker_preparation),
        integration_file_sha256=_file_sha(args.integration),
        integration_review_file_sha256=_file_sha(args.integration_review),
        claimant_source_sha256=_file_sha(args.claimant_source),
        recovery_request_source_sha256=_file_sha(args.recovery_request_source),
        integration_source_sha256=_file_sha(args.integration_source),
        integration_review_source_sha256=_file_sha(args.integration_review_source),
        memory_preflight_source_sha256=_file_sha(args.memory_preflight_source),
        eula_preflight_source_sha256=_file_sha(args.eula_preflight_source),
        worker_source_sha256=_file_sha(args.worker_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
