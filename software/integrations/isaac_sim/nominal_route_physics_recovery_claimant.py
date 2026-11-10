"""Bind the ARM-280 recovery request to the reviewed one-attempt worker.

The CLI only builds a reviewable claimant definition.  Runtime execution is
available through :class:`RecoveryClaimant` only after an independent review,
the exact new authorization, and a fresh passing memory preflight.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from nominal_route_memory_preflight import (
    MemorySnapshot,
    collect_windows_memory_snapshot,
    evaluate_memory_preflight,
)
from nominal_route_physics_recovery_attempt_request import (
    EXACT_AUTHORIZATION,
    SCHEMA as RECOVERY_REQUEST_SCHEMA,
)
from nominal_route_physics_worker import (
    EXACT_AUTHORIZATION as WORKER_AUTHORIZATION,
)
from nominal_route_physics_worker import run_one_attempt


SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_recovery_claimant.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_recovery_claimant_review.v1"
WORKER_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_worker.v1"
WORKER_REVIEW_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_worker_review.v1"
EXPECTED_BACKEND_SHA256 = (
    "132f1e028503a3a83af11f2a713f839e00e1fef49aa9cb3fbb0156f858245cde"
)


class RecoveryClaimantError(RuntimeError):
    """Raised when recovery admission or its one-use boundary changes."""


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
        raise RecoveryClaimantError("input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryClaimantError(f"required JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise RecoveryClaimantError(f"required JSON is not an object: {path}")
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    core = dict(document)
    core.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise RecoveryClaimantError(f"{label} hash changed")
    return claimed


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


def build_claimant_definition(
    recovery_request: Mapping[str, Any],
    worker_preparation: Mapping[str, Any],
    *,
    recovery_request_file_sha256: str,
    worker_preparation_file_sha256: str,
    claimant_source_sha256: str,
    memory_preflight_source_sha256: str,
    worker_source_sha256: str,
) -> dict[str, Any]:
    """Build an inert claimant definition without collecting memory or claiming."""

    recovery_hash = _require_hash(
        recovery_request, "request_sha256", "ARM-280 recovery request"
    )
    worker_hash = _require_hash(
        worker_preparation, "worker_sha256", "ARM-280 worker preparation"
    )
    attempt = recovery_request.get("attempt_contract", {})
    ledger = worker_preparation.get("attempt_ledger", {})
    hashes = (
        recovery_request_file_sha256,
        worker_preparation_file_sha256,
        claimant_source_sha256,
        memory_preflight_source_sha256,
        worker_source_sha256,
    )
    if (
        recovery_request.get("schema") != RECOVERY_REQUEST_SCHEMA
        or recovery_request.get("status")
        != "READY_FOR_INDEPENDENT_RECOVERY_CLAIMANT_REVIEW"
        or recovery_request.get("required_authorization_statement")
        != EXACT_AUTHORIZATION
        or recovery_request.get("old_authorization_reusable") is not False
        or recovery_request.get("attempt_claimed") is not False
        or recovery_request.get("isaac_started") is not False
        or attempt.get("maximum_attempt_count") != 1
        or attempt.get("automatic_retry") is not False
        or attempt.get("claim_only_after_fresh_memory_preflight") is not True
        or attempt.get("trajectory_playback") is not False
        or attempt.get("hardware_or_physical_authority") is not False
        or worker_preparation.get("schema") != WORKER_SCHEMA
        or worker_preparation.get("status")
        != "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW"
        or worker_preparation.get("source_request_sha256")
        != recovery_request.get("source_request_sha256")
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
        or any(not isinstance(value, str) or len(value) != 64 for value in hashes)
    ):
        raise RecoveryClaimantError("ARM-281 claimant boundary changed")

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
        "claimant_id": "arm281-space-recovery-claimant-001",
        "status": "READY_FOR_INDEPENDENT_RECOVERY_CLAIMANT_REVIEW",
        "source_recovery_request_sha256": recovery_hash,
        "source_worker_sha256": worker_hash,
        "source_files_sha256": {
            "recovery_request": recovery_request_file_sha256,
            "worker_preparation": worker_preparation_file_sha256,
            "claimant_source": claimant_source_sha256,
            "memory_preflight_source": memory_preflight_source_sha256,
            "worker_source": worker_source_sha256,
        },
        "worker_preparation": dict(worker_preparation),
        "worker_review": worker_review,
        "required_authorization_statement": EXACT_AUTHORIZATION,
        "worker_authorization_is_internal_compatibility_token": True,
        "fresh_memory_preflight": {
            "required_before_attempt_claim": True,
            "minimum_available_commit_bytes": 32 * 1024**3,
            "minimum_available_physical_bytes": 16 * 1024**3,
            "maximum_commit_utilization": 0.9,
            "receipt_must_be_retained_before_claim": True,
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
        "next_required_stage": "INDEPENDENTLY_REVIEW_ARM281_RECOVERY_CLAIMANT",
    }
    return {**core, "claimant_sha256": _sha(core)}


Backend = Callable[[Path], Mapping[str, Any]]
MemoryCollector = Callable[[], MemorySnapshot]
MemoryEvaluator = Callable[[MemorySnapshot], Mapping[str, Any]]
WorkerRunner = Callable[..., Mapping[str, Any]]


class RecoveryClaimant:
    """Single-use, memory-gated adapter around the unchanged ARM-254 worker."""

    def __init__(
        self,
        definition: Mapping[str, Any],
        claimant_review: Mapping[str, Any],
        *,
        memory_collector: MemoryCollector = collect_windows_memory_snapshot,
        memory_evaluator: MemoryEvaluator = evaluate_memory_preflight,
        worker_runner: WorkerRunner = run_one_attempt,
    ) -> None:
        claimant_hash = _require_hash(definition, "claimant_sha256", "ARM-281 claimant")
        _require_hash(
            claimant_review, "claimant_review_sha256", "ARM-282 claimant review"
        )
        if (
            definition.get("schema") != SCHEMA
            or definition.get("status")
            != "READY_FOR_INDEPENDENT_RECOVERY_CLAIMANT_REVIEW"
            or claimant_review.get("schema") != REVIEW_SCHEMA
            or claimant_review.get("status")
            != "ACCEPTED_FOR_EXACT_ARM280_ONE_ATTEMPT_AUTHORIZATION"
            or claimant_review.get("source_claimant_sha256") != claimant_hash
            or claimant_review.get("launch_admitted") is not True
            or definition.get("automatic_retry") is not False
            or definition.get("callable_is_single_use_after_admission") is not True
        ):
            raise RecoveryClaimantError("claimant review boundary changed")
        self._definition = definition
        self._memory_collector = memory_collector
        self._memory_evaluator = memory_evaluator
        self._worker_runner = worker_runner
        self._used = False

    def run(
        self,
        *,
        authorization_statement: str,
        output_directory: Path,
        fresh_preflight_receipt: Path,
        current_source_files_sha256: Mapping[str, str],
        current_runtime_bindings_sha256: Mapping[str, str],
        backend: Backend,
    ) -> Mapping[str, Any]:
        """Run at most one admitted attempt; memory failure occurs before claim."""

        preparation = self._definition["worker_preparation"]
        if (
            self._used
            or authorization_statement != EXACT_AUTHORIZATION
            or str(output_directory) != self._definition["proposed_output_directory"]
            or output_directory.exists()
            or fresh_preflight_receipt.exists()
        ):
            raise RecoveryClaimantError("recovery attempt is not admitted")
        memory = dict(self._memory_evaluator(self._memory_collector()))
        if (
            memory.get("status") != "PASS_MEMORY_PREFLIGHT"
            or memory.get("launch_admitted") is not True
            or memory.get("attempt_claimed") is not False
            or memory.get("isaac_started") is not False
            or memory.get("hardware_access") is not False
            or memory.get("physical_authority") is not False
        ):
            raise RecoveryClaimantError("fresh memory preflight refused launch")
        fresh_preflight_receipt.parent.mkdir(parents=True, exist_ok=True)
        with fresh_preflight_receipt.open(
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
    parser.add_argument("--claimant-source", type=Path, required=True)
    parser.add_argument("--memory-preflight-source", type=Path, required=True)
    parser.add_argument("--worker-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_claimant_definition(
        _load(args.recovery_request),
        _load(args.worker_preparation),
        recovery_request_file_sha256=_file_sha(args.recovery_request),
        worker_preparation_file_sha256=_file_sha(args.worker_preparation),
        claimant_source_sha256=_file_sha(args.claimant_source),
        memory_preflight_source_sha256=_file_sha(args.memory_preflight_source),
        worker_source_sha256=_file_sha(args.worker_source),
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=False)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
