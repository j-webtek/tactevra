"""Build the non-executing ARM-253 nominal route-physics attempt request.

The request freezes one later simulation-only SPACE attempt.  It starts no
simulator, generates no targets, plays no trajectory, and grants no hardware
or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


REQUEST_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_attempt_request.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_experiment_review.v1"
EXPERIMENT_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_experiment.v1"


class NominalRoutePhysicsAttemptRequestError(ValueError):
    """The reviewed experiment changed or crossed its authority boundary."""


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
        raise NominalRoutePhysicsAttemptRequestError(
            "attempt request input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NominalRoutePhysicsAttemptRequestError(f"{path} is not a JSON object")
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise NominalRoutePhysicsAttemptRequestError(f"{label} hash is missing")
    core = dict(document)
    core.pop(key, None)
    if _sha(core) != claimed:
        raise NominalRoutePhysicsAttemptRequestError(f"{label} hash changed")
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


def build_request(
    review: Mapping[str, Any],
    experiment: Mapping[str, Any],
    *,
    source_files_sha256: Mapping[str, str],
    review_file_sha256: str,
    experiment_file_sha256: str,
) -> dict[str, Any]:
    """Bind the accepted review into one explicit, non-executing request."""

    review_hash = _require_hash(review, "review_sha256", "ARM-252 review")
    experiment_hash = _require_hash(
        experiment, "experiment_sha256", "ARM-251 experiment"
    )
    expected_source_names = {
        "nominal_profile",
        "route_plan",
        "correction_plan",
        "toolchain_lock",
    }
    admission = review.get("simulation_attempt_admission", {})
    goal = review.get("automatic_typing_goal", {})
    matrix = experiment.get("experiment_matrix")
    acceptance = experiment.get("acceptance_contract")
    if (
        review.get("schema") != REVIEW_SCHEMA
        or review.get("status")
        != "ACCEPTED_FOR_ONE_SEPARATELY_AUTHORIZED_NOMINAL_SIMULATION_ATTEMPT"
        or review.get("source_experiment_sha256") != experiment_hash
        or review.get("source_experiment_file_sha256") != experiment_file_sha256
        or review.get("reviewed_source_files_sha256")
        != dict(sorted(source_files_sha256.items()))
        or experiment.get("schema") != EXPERIMENT_SCHEMA
        or experiment.get("source_files_sha256")
        != dict(sorted(source_files_sha256.items()))
        or set(source_files_sha256) != expected_source_names
        or not isinstance(matrix, list)
        or len(matrix) != 1
        or matrix[0].get("case_id") != "nominal-fixture-baseline"
        or matrix[0].get("simulator_runs_requested") != 1
        or not isinstance(acceptance, dict)
        or acceptance.get("minimum_noncontact_tool_key_clearance_mm") != 0.5
        or acceptance.get("maximum_noncontact_key_displacement_mm") != 0.05
        or acceptance.get("maximum_adjacent_joint_step_rad") != 0.05
        or acceptance.get("continuous_clearance_required_for_every_adjacent_segment")
        is not True
        or admission.get("case_id") != "nominal-fixture-baseline"
        or admission.get("episode_id") != "episode-ef340d0ad2740c118d87"
        or admission.get("target_id") != "SPACE"
        or admission.get("maximum_attempt_count") != 1
        or admission.get("automatic_retry") is not False
        or admission.get("fresh_source_revalidation_required_at_launch") is not True
        or admission.get("launch_authorized_by_this_review") is not False
        or admission.get("hardware_or_physical_authority") is not False
        or goal.get("current_stage") != "SINGLE_KEY_SPACE_NOMINAL_ROUTE_REGENERATION"
        or goal.get("next_after_pass")
        != "EXPAND_THE_SAME_CONTRACT_TO_A_REPRESENTATIVE_MULTI_KEY_SET"
        or review.get("next_required_stage")
        != "ONE_NOMINAL_SIMULATION_ATTEMPT_AFTER_SEPARATE_LAUNCH_AUTHORIZATION"
        or review.get("isaac_execution_authorized") is not False
        or review.get("joint_targets_materialized") is not False
        or review.get("trajectory_playback_authorized") is not False
        or review.get("native_replay_authorized") is not False
        or not _zero_authority(review)
        or not _zero_authority(experiment)
        or not isinstance(review_file_sha256, str)
        or len(review_file_sha256) != 64
        or not isinstance(experiment_file_sha256, str)
        or len(experiment_file_sha256) != 64
    ):
        raise NominalRoutePhysicsAttemptRequestError(
            "ARM-253 reviewed experiment boundary changed"
        )

    authorization = (
        "I authorize exactly one ARM-253 nominal SPACE route-physics simulation "
        "attempt for episode-ef340d0ad2740c118d87, with no automatic retry, "
        "no trajectory playback, and no hardware or physical authority."
    )
    core: dict[str, Any] = {
        "schema": REQUEST_SCHEMA,
        "request_id": "arm253-space-nominal-route-physics-attempt-001",
        "status": "READY_FOR_EXPLICIT_ONE_ATTEMPT_SIMULATION_AUTHORIZATION",
        "source_review_sha256": review_hash,
        "source_review_file_sha256": review_file_sha256,
        "source_experiment_sha256": experiment_hash,
        "source_experiment_file_sha256": experiment_file_sha256,
        "source_files_sha256": dict(sorted(source_files_sha256.items())),
        "case_id": "nominal-fixture-baseline",
        "episode_id": "episode-ef340d0ad2740c118d87",
        "target_id": "SPACE",
        "attempt_contract": {
            "maximum_attempt_count": 1,
            "automatic_retry": False,
            "fresh_review_and_source_revalidation_required_at_launch": True,
            "generate_only_rows_654_through_940": True,
            "trajectory_playback": False,
            "native_replay": False,
            "hardware_or_physical_authority": False,
            "stop_and_retain_receipt_on_first_failure": True,
        },
        "acceptance_contract": dict(acceptance),
        "required_outputs": list(experiment["required_outputs"]),
        "output_contract": {
            "result": "result.json",
            "status": "status.json",
            "regenerated_joint_targets": "regenerated_joint_targets.jsonl",
            "canonical_ik": "canonical_ik.jsonl",
            "continuous_clearance": "continuous_clearance.jsonl",
            "tool_key_metrics": "tool_key_metrics.jsonl",
            "write_outputs_before_simulator_shutdown": True,
            "existing_output_directory_must_be_absent": True,
        },
        "required_authorization_statement": authorization,
        "automatic_typing_goal": dict(goal),
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
            "IMPLEMENT_AND_REVIEW_FAIL_CLOSED_ONE_ATTEMPT_SIMULATION_WORKER"
        ),
        "limitations": [
            "request_build_does_not_start_isaac_or_a_gpu",
            "request_build_does_not_generate_joint_targets",
            "request_does_not_authorize_trajectory_or_native_replay",
            "single_space_case_is_not_multi_key_automatic_typing",
            "simulation_result_cannot_authorize_hardware_or_physical_motion",
        ],
    }
    return {**core, "request_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--nominal-profile", type=Path, required=True)
    parser.add_argument("--route-plan", type=Path, required=True)
    parser.add_argument("--correction-plan", type=Path, required=True)
    parser.add_argument("--toolchain-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_paths = {
        "nominal_profile": args.nominal_profile.resolve(strict=True),
        "route_plan": args.route_plan.resolve(strict=True),
        "correction_plan": args.correction_plan.resolve(strict=True),
        "toolchain_lock": args.toolchain_lock.resolve(strict=True),
    }
    review_path = args.review.resolve(strict=True)
    experiment_path = args.experiment.resolve(strict=True)
    result = build_request(
        _load_object(review_path),
        _load_object(experiment_path),
        source_files_sha256={
            name: _file_sha(path) for name, path in source_paths.items()
        },
        review_file_sha256=_file_sha(review_path),
        experiment_file_sha256=_file_sha(experiment_path),
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
