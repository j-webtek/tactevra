"""Build and govern the fresh-gate ARM-295 route-physics claimant.

The CLI emits only an inert claimant definition.  Runtime use additionally
requires an independent claimant review, the exact one-use ARM-295
authorization, fresh passing EULA and memory receipts, unchanged runtime
sources, and absent governed outputs.  The claimant delegates once to the
already reviewed fail-closed worker; it never grants hardware or physical
authority.
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
from nominal_route_native_inventory_recovery_plan import (
    EXACT_AUTHORIZATION,
    RUNTIME_SOURCE_KEYS,
    SCHEMA as PLAN_SCHEMA,
)
from nominal_route_native_inventory_recovery_plan_review import (
    REVIEW_SCHEMA as PLAN_REVIEW_SCHEMA,
)
from nominal_route_physics_worker import (
    EXACT_AUTHORIZATION as INTERNAL_WORKER_AUTHORIZATION,
)
from nominal_route_physics_worker import (
    PREPARATION_SCHEMA,
    WORKER_REVIEW_SCHEMA,
    run_one_attempt,
)


SCHEMA = "tactevra.isaac_lm4_native_inventory_recovery_claimant.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_native_inventory_recovery_claimant_review.v1"
EXPECTED_BACKEND_SHA256 = (
    "132f1e028503a3a83af11f2a713f839e00e1fef49aa9cb3fbb0156f858245cde"
)
ZERO_AUTHORITY = {
    "authorization_observed": False,
    "attempt_claimed": False,
    "worker_invoked": False,
    "backend_invoked": False,
    "launch_admitted": False,
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


class NativeInventoryRecoveryClaimantError(RuntimeError):
    """Raised when claimant evidence or the one-use boundary changes."""


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
        raise NativeInventoryRecoveryClaimantError(
            "claimant input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise NativeInventoryRecoveryClaimantError(
            f"required input unavailable: {path}"
        ) from exc


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value.lower()
    )


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    core = dict(document)
    core.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise NativeInventoryRecoveryClaimantError(f"{label} hash changed")
    return claimed


def _worker_zero_authority(document: Mapping[str, Any]) -> bool:
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
            document.get("controller_commands") == [],
            document.get("wire_commands") == [],
            document.get("gate_promotions") == [],
        )
    )


def _claimant_zero_authority(
    document: Mapping[str, Any], *, launch_admitted: bool = False
) -> bool:
    expected = {**ZERO_AUTHORITY, "launch_admitted": launch_admitted}
    return all(document.get(key) == value for key, value in expected.items())


def build_claimant_definition(
    plan: Mapping[str, Any],
    plan_review: Mapping[str, Any],
    base_worker: Mapping[str, Any],
    *,
    plan_file_sha256: str,
    plan_review_file_sha256: str,
    base_worker_file_sha256: str,
    claimant_source_sha256: str,
    claimant_review_source_sha256: str,
    eula_preflight_source_sha256: str,
    memory_preflight_source_sha256: str,
    worker_source_sha256: str,
) -> dict[str, Any]:
    """Create an inert claimant and fresh worker clone from reviewed evidence."""

    plan_hash = _require_hash(plan, "plan_sha256", "ARM-295 lineage plan")
    review_hash = _require_hash(
        plan_review, "review_sha256", "ARM-295 lineage plan review"
    )
    base_worker_hash = _require_hash(
        base_worker, "worker_sha256", "base route-physics worker"
    )
    source_hashes = (
        plan_file_sha256,
        plan_review_file_sha256,
        base_worker_file_sha256,
        claimant_source_sha256,
        claimant_review_source_sha256,
        eula_preflight_source_sha256,
        memory_preflight_source_sha256,
        worker_source_sha256,
    )
    runtime_sources = plan.get("runtime_sources_sha256", {})
    attempt = Path(str(plan.get("proposed_attempt_directory", "")))
    eula_receipt = Path(str(plan.get("proposed_eula_receipt", "")))
    memory_receipt = Path(str(plan.get("proposed_memory_receipt", "")))
    ledger = base_worker.get("attempt_ledger", {})
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("status")
        != "READY_FOR_INDEPENDENT_ARM295_LINEAGE_PLAN_REVIEW"
        or plan.get("required_authorization_statement") != EXACT_AUTHORIZATION
        or plan.get("superseded_authorizations_reusable") is not False
        or plan.get("fresh_eula_preflight_required") is not True
        or plan.get("fresh_memory_preflight_required") is not True
        or plan.get("preflights_must_precede_attempt_claim") is not True
        or plan.get("terminal_status_must_precede_simulator_shutdown") is not True
        or not _claimant_zero_authority(plan)
        or not isinstance(runtime_sources, Mapping)
        or set(runtime_sources) != set(RUNTIME_SOURCE_KEYS)
        or not all(_digest(value) for value in runtime_sources.values())
        or plan_review.get("schema") != PLAN_REVIEW_SCHEMA
        or plan_review.get("status")
        != "ACCEPTED_FOR_FRESH_PREFLIGHT_AND_CLAIMANT_CONSTRUCTION"
        or plan_review.get("source_plan_sha256") != plan_hash
        or plan_review.get("source_plan_file_sha256") != plan_file_sha256
        or plan_review.get("proposed_attempt_directory") != str(attempt)
        or plan_review.get("proposed_attempt_directory_absent") is not True
        or plan_review.get("proposed_eula_receipt") != str(eula_receipt)
        or plan_review.get("proposed_eula_receipt_absent") is not True
        or plan_review.get("proposed_memory_receipt") != str(memory_receipt)
        or plan_review.get("proposed_memory_receipt_absent") is not True
        or plan_review.get("required_authorization_statement")
        != EXACT_AUTHORIZATION
        or not _claimant_zero_authority(plan_review)
        or base_worker.get("schema") != PREPARATION_SCHEMA
        or base_worker.get("status")
        != "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW"
        or base_worker.get("required_authorization_statement")
        != INTERNAL_WORKER_AUTHORIZATION
        or ledger.get("maximum_attempt_count") != 1
        or ledger.get("attempts_consumed_by_preparation") != 0
        or ledger.get("automatic_retry") is not False
        or base_worker.get("isaac_backend_implemented_by_this_envelope") is not False
        or not _worker_zero_authority(base_worker)
        or str(attempt) == base_worker.get("proposed_output_directory")
        or not all(path.is_absolute() for path in (attempt, eula_receipt, memory_receipt))
        or any(path.exists() for path in (attempt, eula_receipt, memory_receipt))
        or eula_receipt.parent.exists()
        or memory_receipt.parent.exists()
        or not all(_digest(value) for value in source_hashes)
    ):
        raise NativeInventoryRecoveryClaimantError(
            "ARM-295 claimant definition boundary changed"
        )

    worker_core = dict(base_worker)
    worker_core.pop("worker_sha256")
    worker_core.update(
        {
            "worker_id": "arm295-space-route-physics-worker-001",
            "proposed_output_directory": str(attempt),
            "recovered_from_worker_sha256": base_worker_hash,
            "external_authorization_statement": EXACT_AUTHORIZATION,
            "required_authorization_statement": INTERNAL_WORKER_AUTHORIZATION,
        }
    )
    worker_preparation = {
        **worker_core,
        "worker_sha256": _sha(worker_core),
    }
    worker_review_core = {
        "schema": WORKER_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ONE_SEPARATELY_AUTHORIZED_SIMULATION_ATTEMPT",
        "source_worker_sha256": worker_preparation["worker_sha256"],
        "reviewed_backend_sha256": EXPECTED_BACKEND_SHA256,
        "launch_admitted": True,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }
    worker_review = {
        **worker_review_core,
        "worker_review_sha256": _sha(worker_review_core),
    }
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "claimant_id": "arm295-native-inventory-recovery-claimant-001",
        "status": "READY_FOR_INDEPENDENT_ARM295_CLAIMANT_REVIEW",
        "source_plan_sha256": plan_hash,
        "source_plan_review_sha256": review_hash,
        "source_base_worker_sha256": base_worker_hash,
        "source_files_sha256": {
            "plan": plan_file_sha256,
            "plan_review": plan_review_file_sha256,
            "base_worker": base_worker_file_sha256,
            "claimant_source": claimant_source_sha256,
            "claimant_review_source": claimant_review_source_sha256,
            "eula_preflight_source": eula_preflight_source_sha256,
            "memory_preflight_source": memory_preflight_source_sha256,
            "worker_source": worker_source_sha256,
        },
        "runtime_sources_sha256": dict(sorted(runtime_sources.items())),
        "worker_preparation": worker_preparation,
        "worker_review": worker_review,
        "worker_authorization_is_internal_compatibility_token": True,
        "required_authorization_statement": EXACT_AUTHORIZATION,
        "authorization_reusable": False,
        "proposed_output_directory": str(attempt),
        "fresh_eula_receipt": str(eula_receipt),
        "fresh_memory_receipt": str(memory_receipt),
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
        "callable_is_single_use_after_admission": True,
        **ZERO_AUTHORITY,
        "next_required_stage": "INDEPENDENT_ARM295_CLAIMANT_REVIEW",
    }
    return {**core, "claimant_sha256": _sha(core)}


Backend = Callable[[Path], Mapping[str, Any]]
EulaCollector = Callable[[], Mapping[str, str]]
EulaEvaluator = Callable[[Mapping[str, str]], Mapping[str, Any]]
MemoryCollector = Callable[[], MemorySnapshot]
MemoryEvaluator = Callable[[MemorySnapshot], Mapping[str, Any]]
WorkerRunner = Callable[..., Mapping[str, Any]]


class NativeInventoryRecoveryClaimant:
    """Single-use ARM-295 adapter behind new authorization and fresh gates."""

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
            definition, "claimant_sha256", "ARM-295 claimant"
        )
        _require_hash(
            claimant_review, "claimant_review_sha256", "ARM-295 claimant review"
        )
        if (
            definition.get("schema") != SCHEMA
            or definition.get("status")
            != "READY_FOR_INDEPENDENT_ARM295_CLAIMANT_REVIEW"
            or claimant_review.get("schema") != REVIEW_SCHEMA
            or claimant_review.get("status")
            != "ACCEPTED_FOR_EXACT_ARM295_ONE_ATTEMPT_AUTHORIZATION"
            or claimant_review.get("source_claimant_sha256") != claimant_hash
            or definition.get("required_authorization_statement")
            != EXACT_AUTHORIZATION
            or definition.get("authorization_reusable") is not False
            or definition.get(
                "worker_authorization_is_internal_compatibility_token"
            )
            is not True
            or claimant_review.get("required_authorization_statement")
            != EXACT_AUTHORIZATION
            or claimant_review.get("old_authorizations_rejected") is not True
            or claimant_review.get(
                "internal_worker_token_is_not_external_authority"
            )
            is not True
            or claimant_review.get("single_worker_delegation") is not True
            or claimant_review.get("launch_admitted") is not True
            or claimant_review.get("fresh_gates_precede_attempt_claim") is not True
            or claimant_review.get("both_receipts_precede_attempt_claim") is not True
            or claimant_review.get("failure_terminalization_precedes_shutdown")
            is not True
            or definition.get("callable_is_single_use_after_admission") is not True
            or not _claimant_zero_authority(definition)
            or not _claimant_zero_authority(
                claimant_review, launch_admitted=True
            )
        ):
            raise NativeInventoryRecoveryClaimantError(
                "ARM-295 claimant review boundary changed"
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
        current_runtime_sources_sha256: Mapping[str, str],
        current_source_files_sha256: Mapping[str, str],
        current_runtime_bindings_sha256: Mapping[str, str],
        backend: Backend,
    ) -> Mapping[str, Any]:
        """Retain fresh gates, then delegate exactly once to the worker."""

        if (
            self._used
            or authorization_statement != EXACT_AUTHORIZATION
            or str(output_directory) != self._definition["proposed_output_directory"]
            or str(fresh_eula_receipt) != self._definition["fresh_eula_receipt"]
            or str(fresh_memory_receipt) != self._definition["fresh_memory_receipt"]
            or dict(sorted(current_runtime_sources_sha256.items()))
            != self._definition["runtime_sources_sha256"]
            or output_directory.exists()
            or fresh_eula_receipt.exists()
            or fresh_memory_receipt.exists()
            or fresh_eula_receipt.parent.exists()
            or fresh_memory_receipt.parent.exists()
        ):
            raise NativeInventoryRecoveryClaimantError(
                "ARM-295 attempt is not admitted"
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
            raise NativeInventoryRecoveryClaimantError(
                "fresh EULA preflight refused ARM-295 launch"
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
            raise NativeInventoryRecoveryClaimantError(
                "fresh memory preflight refused ARM-295 launch"
            )
        fresh_eula_receipt.parent.mkdir(parents=True, exist_ok=False)
        with fresh_eula_receipt.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(eula, indent=2, sort_keys=True) + "\n")
        fresh_memory_receipt.parent.mkdir(parents=True, exist_ok=False)
        with fresh_memory_receipt.open(
            "x", encoding="utf-8", newline="\n"
        ) as stream:
            stream.write(json.dumps(memory, indent=2, sort_keys=True) + "\n")
        self._used = True
        return self._worker_runner(
            self._definition["worker_preparation"],
            worker_review=self._definition["worker_review"],
            authorization_statement=INTERNAL_WORKER_AUTHORIZATION,
            output_directory=output_directory,
            current_source_files_sha256=current_source_files_sha256,
            current_runtime_bindings_sha256=current_runtime_bindings_sha256,
            backend=backend,
        )


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeInventoryRecoveryClaimantError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise NativeInventoryRecoveryClaimantError(
            f"required JSON is not an object: {path}"
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-review", type=Path, required=True)
    parser.add_argument("--base-worker", type=Path, required=True)
    parser.add_argument("--claimant-source", type=Path, required=True)
    parser.add_argument("--claimant-review-source", type=Path, required=True)
    parser.add_argument("--eula-preflight-source", type=Path, required=True)
    parser.add_argument("--memory-preflight-source", type=Path, required=True)
    parser.add_argument("--worker-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_claimant_definition(
        _load(args.plan),
        _load(args.plan_review),
        _load(args.base_worker),
        plan_file_sha256=_file_sha(args.plan),
        plan_review_file_sha256=_file_sha(args.plan_review),
        base_worker_file_sha256=_file_sha(args.base_worker),
        claimant_source_sha256=_file_sha(args.claimant_source),
        claimant_review_source_sha256=_file_sha(args.claimant_review_source),
        eula_preflight_source_sha256=_file_sha(args.eula_preflight_source),
        memory_preflight_source_sha256=_file_sha(args.memory_preflight_source),
        worker_source_sha256=_file_sha(args.worker_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
