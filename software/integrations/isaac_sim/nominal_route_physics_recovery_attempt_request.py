"""Build a non-executing recovery request after the consumed ARM-253 attempt.

The request binds the retained native-abort receipt and a passing memory
preflight.  It does not start Isaac, claim an attempt directory, or reuse the
authorization that was consumed by ARM-253.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_recovery_request.v1"
SOURCE_REQUEST_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_attempt_request.v1"
MEMORY_SCHEMA = "tactevra.isaac_nominal_route_memory_preflight.v1"
SOURCE_REQUEST_ID = "arm253-space-nominal-route-physics-attempt-001"
SOURCE_AUTHORIZATION = (
    "I authorize exactly one ARM-253 nominal SPACE route-physics simulation "
    "attempt for episode-ef340d0ad2740c118d87, with no automatic retry, "
    "no trajectory playback, and no hardware or physical authority."
)
EXACT_AUTHORIZATION = (
    "I authorize exactly one ARM-280 recovered nominal SPACE route-physics "
    "simulation attempt for episode-ef340d0ad2740c118d87, with no automatic "
    "retry, no trajectory playback, and no hardware or physical authority."
)


class RecoveryAttemptRequestError(ValueError):
    """Raised when recovery evidence or its zero-authority boundary changed."""


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
        raise RecoveryAttemptRequestError("input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryAttemptRequestError(f"required JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise RecoveryAttemptRequestError(f"required JSON is not an object: {path}")
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise RecoveryAttemptRequestError(f"{label} hash is missing")
    core = dict(document)
    core.pop(key, None)
    if _sha(core) != claimed:
        raise RecoveryAttemptRequestError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("hardware_access") is False
        and document.get("physical_authority") is False
        and document.get("trajectory_playback") is False
        and document.get("joint_targets_submitted") is False
    )


def build_request(
    source_request: Mapping[str, Any],
    failure_status: Mapping[str, Any],
    memory_preflight: Mapping[str, Any],
    *,
    source_request_file_sha256: str,
    failure_status_file_sha256: str,
    memory_preflight_file_sha256: str,
    proposed_output_directory: str,
) -> dict[str, Any]:
    """Bind one failed attempt and one safe-memory observation into a request."""

    source_request_hash = _require_hash(
        source_request, "request_sha256", "ARM-253 request"
    )
    attempt = source_request.get("attempt_contract", {})
    checks = memory_preflight.get("checks", {})
    thresholds = memory_preflight.get("thresholds", {})
    hashes = (
        source_request_file_sha256,
        failure_status_file_sha256,
        memory_preflight_file_sha256,
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
        or failure_status.get("status") != "FAILED_RETAINED_NO_RETRY"
        or failure_status.get("attempt_count") != 1
        or failure_status.get("automatic_retry") is not False
        or failure_status.get("error_type") != "NativeIsaacRuntimeAbort"
        or "paging file is too small"
        not in str(failure_status.get("error_message", "")).lower()
        or not _zero_authority(failure_status)
        or memory_preflight.get("schema") != MEMORY_SCHEMA
        or memory_preflight.get("status") != "PASS_MEMORY_PREFLIGHT"
        or memory_preflight.get("launch_admitted") is not True
        or memory_preflight.get("attempt_claimed") is not False
        or memory_preflight.get("isaac_started") is not False
        or memory_preflight.get("automatic_retry") is not False
        or not _zero_authority(memory_preflight)
        or checks
        != {
            "available_commit": True,
            "available_physical": True,
            "commit_utilization": True,
        }
        or thresholds.get("minimum_available_commit_bytes") != 32 * 1024**3
        or thresholds.get("minimum_available_physical_bytes") != 16 * 1024**3
        or thresholds.get("maximum_commit_utilization") != 0.9
        or any(not isinstance(value, str) or len(value) != 64 for value in hashes)
        or not proposed_output_directory
        or not Path(proposed_output_directory).is_absolute()
    ):
        raise RecoveryAttemptRequestError("ARM-280 recovery boundary changed")

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "request_id": "arm280-space-nominal-route-physics-recovery-001",
        "status": "READY_FOR_INDEPENDENT_RECOVERY_CLAIMANT_REVIEW",
        "source_request_sha256": source_request_hash,
        "source_request_file_sha256": source_request_file_sha256,
        "source_failure_status_file_sha256": failure_status_file_sha256,
        "source_memory_preflight_file_sha256": memory_preflight_file_sha256,
        "failure_classification": "HOST_COMMIT_EXHAUSTION_BEFORE_PHYSICS",
        "memory_remediation": {
            "pagefile_configuration_changed": False,
            "concurrent_commit_pressure_released": True,
            "fresh_memory_preflight_required_at_launch": True,
            "minimum_available_commit_bytes": 32 * 1024**3,
            "minimum_available_physical_bytes": 16 * 1024**3,
            "maximum_commit_utilization": 0.9,
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
        "gpu_started": False,
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
        "next_required_stage": (
            "IMPLEMENT_AND_INDEPENDENTLY_REVIEW_ARM280_RECOVERY_CLAIMANT"
        ),
        "limitations": [
            "request_build_does_not_start_isaac_or_claim_an_attempt",
            "passing_memory_evidence_must_be_refreshed_at_launch",
            "the_consumed_arm253_authorization_cannot_be_reused",
            "simulation_result_cannot_authorize_hardware_or_physical_motion",
        ],
    }
    return {**core, "request_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-request", type=Path, required=True)
    parser.add_argument("--failure-status", type=Path, required=True)
    parser.add_argument("--memory-preflight", type=Path, required=True)
    parser.add_argument("--proposed-output-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_request_path = args.source_request.resolve(strict=True)
    failure_path = args.failure_status.resolve(strict=True)
    memory_path = args.memory_preflight.resolve(strict=True)
    proposed = args.proposed_output_directory.resolve()
    if proposed.exists():
        raise RecoveryAttemptRequestError(
            "proposed recovery output directory already exists"
        )
    result = build_request(
        _load(source_request_path),
        _load(failure_path),
        _load(memory_path),
        source_request_file_sha256=_file_sha(source_request_path),
        failure_status_file_sha256=_file_sha(failure_path),
        memory_preflight_file_sha256=_file_sha(memory_path),
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
