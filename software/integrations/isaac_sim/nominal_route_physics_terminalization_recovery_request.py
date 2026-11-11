"""Build inert ARM-289 recovery after the consumed ARM-284 shutdown gap.

This module only binds retained evidence and the reviewed terminalization
correction.  It never imports Isaac, collects live gates, claims an output
directory, or grants hardware or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "tactevra.isaac_lm4_terminalized_route_physics_recovery_request.v1"
SOURCE_REQUEST_SCHEMA = (
    "tactevra.isaac_lm4_nominal_route_physics_eula_recovery_request.v1"
)
INTEGRATION_SCHEMA = "tactevra.isaac_lm4_native_runtime_worker_integration.v2"
INTEGRATION_REVIEW_SCHEMA = (
    "tactevra.isaac_lm4_native_runtime_worker_integration_review.v2"
)
EULA_SCHEMA = "tactevra.isaac_nominal_route_eula_preflight.v1"
MEMORY_SCHEMA = "tactevra.isaac_nominal_route_memory_preflight.v1"
SOURCE_REQUEST_ID = "arm284-space-nominal-route-physics-eula-recovery-001"
SOURCE_AUTHORIZATION = (
    "I authorize exactly one ARM-284 EULA-ready recovered nominal SPACE "
    "route-physics simulation attempt for episode-ef340d0ad2740c118d87, "
    "with no automatic retry, no trajectory playback, and no hardware or "
    "physical authority."
)
EXACT_AUTHORIZATION = (
    "I authorize exactly one ARM-289 terminalized recovered nominal SPACE "
    "route-physics simulation attempt for episode-ef340d0ad2740c118d87, "
    "with no automatic retry, no trajectory playback, and no hardware or "
    "physical authority."
)


class TerminalizationRecoveryRequestError(ValueError):
    """Raised when consumed evidence or corrected lineage changes."""


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
        raise TerminalizationRecoveryRequestError(
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
        raise TerminalizationRecoveryRequestError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise TerminalizationRecoveryRequestError(
            f"required JSON is not an object: {path}"
        )
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    core = dict(document)
    core.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise TerminalizationRecoveryRequestError(f"{label} hash changed")
    return claimed


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value.lower()
    )


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("hardware_access") is False
        and document.get("physical_authority") is False
        and document.get("trajectory_playback") is False
        and document.get("joint_targets_submitted") is False
        and document.get("automatic_retry") is False
    )


def build_request(
    source_request: Mapping[str, Any],
    consumed_status: Mapping[str, Any],
    eula_receipt: Mapping[str, Any],
    memory_receipt: Mapping[str, Any],
    integration: Mapping[str, Any],
    integration_review: Mapping[str, Any],
    *,
    source_request_file_sha256: str,
    consumed_status_file_sha256: str,
    eula_receipt_file_sha256: str,
    memory_receipt_file_sha256: str,
    postmortem_file_sha256: str,
    kit_log_file_sha256: str,
    integration_file_sha256: str,
    integration_review_file_sha256: str,
    request_source_file_sha256: str,
    proposed_output_directory: str,
) -> dict[str, Any]:
    """Bind ARM-284 evidence to the reviewed pre-shutdown correction."""

    source_hash = _require_hash(
        source_request, "request_sha256", "ARM-284 request"
    )
    integration_hash = _require_hash(
        integration, "integration_sha256", "ARM-287 integration"
    )
    review_hash = _require_hash(
        integration_review,
        "integration_review_sha256",
        "ARM-288 integration review",
    )
    attempt = source_request.get("attempt_contract", {})
    expected_status = {
        "status": "ATTEMPT_CLAIMED_BACKEND_PENDING",
        "attempt_count": 1,
        "automatic_retry": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    hashes = (
        source_request_file_sha256,
        consumed_status_file_sha256,
        eula_receipt_file_sha256,
        memory_receipt_file_sha256,
        postmortem_file_sha256,
        kit_log_file_sha256,
        integration_file_sha256,
        integration_review_file_sha256,
        request_source_file_sha256,
    )
    if (
        source_request.get("schema") != SOURCE_REQUEST_SCHEMA
        or source_request.get("request_id") != SOURCE_REQUEST_ID
        or source_request.get("required_authorization_statement")
        != SOURCE_AUTHORIZATION
        or source_request.get("episode_id") != "episode-ef340d0ad2740c118d87"
        or source_request.get("target_id") != "SPACE"
        or attempt.get("maximum_attempt_count") != 1
        or attempt.get("automatic_retry") is not False
        or attempt.get("trajectory_playback") is not False
        or attempt.get("hardware_or_physical_authority") is not False
        or dict(consumed_status) != expected_status
        or eula_receipt.get("schema") != EULA_SCHEMA
        or eula_receipt.get("status") != "PASS_EULA_PREFLIGHT"
        or eula_receipt.get("launch_admitted") is not True
        or eula_receipt.get("acceptance_observed") is not True
        or eula_receipt.get("acceptance_performed_by_preflight") is not False
        or eula_receipt.get("attempt_claimed") is not False
        or eula_receipt.get("isaac_started") is not False
        or not _zero_authority(eula_receipt)
        or memory_receipt.get("schema") != MEMORY_SCHEMA
        or memory_receipt.get("status") != "PASS_MEMORY_PREFLIGHT"
        or memory_receipt.get("launch_admitted") is not True
        or memory_receipt.get("attempt_claimed") is not False
        or memory_receipt.get("isaac_started") is not False
        or not _zero_authority(memory_receipt)
        or integration.get("schema") != INTEGRATION_SCHEMA
        or integration.get("integration_id")
        != "arm287-terminalizing-native-runtime-worker-integration-001"
        or integration.get("callable_is_single_use") is not True
        or integration.get("automatic_retry") is not False
        or integration.get("launch_admitted") is not False
        or integration.get("attempt_consumed") is not False
        or "terminalize_failure_before_shutdown"
        not in integration.get("lifecycle", [])
        or integration_review.get("schema") != INTEGRATION_REVIEW_SCHEMA
        or integration_review.get("review_id")
        != "arm288-terminalizing-native-runtime-worker-integration-review-001"
        or integration_review.get("status")
        != "ACCEPTED_FOR_SEPARATELY_AUTHORIZED_ONE_ATTEMPT_WORKER_USE"
        or integration_review.get("source_integration_sha256") != integration_hash
        or integration_review.get("failure_terminalization_precedes_shutdown")
        is not True
        or integration_review.get("launch_admitted") is not False
        or integration_review.get("attempt_consumed") is not False
        or not all(_digest(value) for value in hashes)
        or not proposed_output_directory
        or not Path(proposed_output_directory).is_absolute()
        or proposed_output_directory
        == source_request.get("proposed_output_directory")
    ):
        raise TerminalizationRecoveryRequestError(
            "ARM-289 recovery boundary changed"
        )

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "request_id": "arm289-terminalized-space-route-physics-recovery-001",
        "status": "READY_FOR_INDEPENDENT_TERMINALIZED_RECOVERY_CLAIMANT_REVIEW",
        "source_request_sha256": source_hash,
        "source_request_file_sha256": source_request_file_sha256,
        "source_consumed_status_file_sha256": consumed_status_file_sha256,
        "source_eula_receipt_file_sha256": eula_receipt_file_sha256,
        "source_memory_receipt_file_sha256": memory_receipt_file_sha256,
        "source_postmortem_file_sha256": postmortem_file_sha256,
        "source_kit_log_file_sha256": kit_log_file_sha256,
        "source_integration_sha256": integration_hash,
        "source_integration_file_sha256": integration_file_sha256,
        "source_integration_review_sha256": review_hash,
        "source_integration_review_file_sha256": integration_review_file_sha256,
        "request_source_file_sha256": request_source_file_sha256,
        "failure_classification": "FAST_SHUTDOWN_BEFORE_OUTER_TERMINALIZATION",
        "remediation": {
            "failure_terminalization_precedes_shutdown": True,
            "failing_lifecycle_phase_retained": True,
            "exception_type_and_message_retained": True,
            "fresh_eula_preflight_required_before_attempt_claim": True,
            "fresh_memory_preflight_required_before_attempt_claim": True,
        },
        "case_id": "nominal-fixture-baseline",
        "episode_id": "episode-ef340d0ad2740c118d87",
        "target_id": "SPACE",
        "proposed_output_directory": proposed_output_directory,
        "attempt_contract": {
            "maximum_attempt_count": 1,
            "automatic_retry": False,
            "existing_output_directory_must_be_absent": True,
            "claim_only_after_fresh_memory_preflight": True,
            "claim_only_after_fresh_eula_preflight": True,
            "terminalize_before_simulator_shutdown": True,
            "trajectory_playback": False,
            "native_replay": False,
            "hardware_or_physical_authority": False,
            "stop_and_retain_receipt_on_first_failure": True,
        },
        "required_authorization_statement": EXACT_AUTHORIZATION,
        "old_authorization_reusable": False,
        "attempt_claimed": False,
        "isaac_execution_authorized": False,
        "isaac_started": False,
        "automatic_retry": False,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": "IMPLEMENT_AND_REVIEW_ARM290_RECOVERY_CLAIMANT",
        "limitations": [
            "request_build_does_not_start_isaac_or_claim_an_attempt",
            "arm284_is_consumed_and_cannot_be_retried",
            "fresh_memory_and_eula_evidence_are_required_before_claim",
            "a_distinct_exact_authorization_is_required",
            "simulation_result_cannot_authorize_hardware_or_physical_motion",
        ],
    }
    return {**core, "request_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-request", type=Path, required=True)
    parser.add_argument("--consumed-status", type=Path, required=True)
    parser.add_argument("--eula-receipt", type=Path, required=True)
    parser.add_argument("--memory-receipt", type=Path, required=True)
    parser.add_argument("--postmortem", type=Path, required=True)
    parser.add_argument("--kit-log", type=Path, required=True)
    parser.add_argument("--integration", type=Path, required=True)
    parser.add_argument("--integration-review", type=Path, required=True)
    parser.add_argument("--request-source", type=Path, required=True)
    parser.add_argument("--proposed-output-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    paths = {
        "source_request": args.source_request.resolve(strict=True),
        "consumed_status": args.consumed_status.resolve(strict=True),
        "eula_receipt": args.eula_receipt.resolve(strict=True),
        "memory_receipt": args.memory_receipt.resolve(strict=True),
        "postmortem": args.postmortem.resolve(strict=True),
        "kit_log": args.kit_log.resolve(strict=True),
        "integration": args.integration.resolve(strict=True),
        "integration_review": args.integration_review.resolve(strict=True),
        "request_source": args.request_source.resolve(strict=True),
    }
    proposed = args.proposed_output_directory.resolve()
    if proposed.exists():
        raise TerminalizationRecoveryRequestError(
            "proposed recovery output already exists"
        )
    result = build_request(
        _load(paths["source_request"]),
        _load(paths["consumed_status"]),
        _load(paths["eula_receipt"]),
        _load(paths["memory_receipt"]),
        _load(paths["integration"]),
        _load(paths["integration_review"]),
        source_request_file_sha256=_file_sha(paths["source_request"]),
        consumed_status_file_sha256=_file_sha(paths["consumed_status"]),
        eula_receipt_file_sha256=_file_sha(paths["eula_receipt"]),
        memory_receipt_file_sha256=_file_sha(paths["memory_receipt"]),
        postmortem_file_sha256=_file_sha(paths["postmortem"]),
        kit_log_file_sha256=_file_sha(paths["kit_log"]),
        integration_file_sha256=_file_sha(paths["integration"]),
        integration_review_file_sha256=_file_sha(paths["integration_review"]),
        request_source_file_sha256=_file_sha(paths["request_source"]),
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
