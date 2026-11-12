"""Build the inert ARM-298 nominal route-physics lineage plan.

The plan binds the independently reproduced ARM-298 canonical-continuity
qualification, the merged corrected production sources, the qualified Isaac
interpreter, and fresh absent outputs.  It imports no Isaac or transport
module and grants no launch, attempt, motion, hardware, or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "tactevra.isaac_lm4_arm298_route_physics_lineage_plan.v1"
QUALIFICATION_SCHEMA = "tactevra.isaac_lm4_arm298_continuity_qualification.v1"
QUALIFICATION_REVIEW_SCHEMA = (
    "tactevra.isaac_lm4_arm298_continuity_qualification_review.v1"
)
EXPECTED_QUALIFICATION_SHA256 = (
    "69c03491946af02e566ee1eecf9549c8eb6afb948b130881e36a331bc5c79b01"
)
EXPECTED_QUALIFICATION_FILE_SHA256 = (
    "76daa618c1f992e869aad3a7c2a12908487481f8c10d2aa21d8314c3ba256a25"
)
EXPECTED_QUALIFICATION_REVIEW_SHA256 = (
    "7a81cf31171d15d19f03b65761eebae62773a26d94494836e65b8094e766c6b1"
)
EXPECTED_QUALIFICATION_REVIEW_FILE_SHA256 = (
    "c905e81dece8ffac144193e7c1764ba7c3ebc9c75fb729f84cdca13f2d5e16f9"
)
EXPECTED_CANONICAL_ROWS_SHA256 = (
    "7d5b329e0a29a308f5e4fa9e42a3d4f9173560a61b32fd8d09795102d946919c"
)
EXPECTED_REPOSITORY_COMMIT = "8541cef20a63967d44cad14885bdd01f927af8ab"
EXPECTED_INTERPRETER_PATH = Path("C:/IsaacSim/env_6_1_0/Scripts/python.exe")
EXPECTED_INTERPRETER_SHA256 = (
    "d55736b9f3d6b4ca7985b82db8ce11edfa09994cf93ce31c6b506543b74f32eb"
)
RUNTIME_SOURCE_KEYS = (
    "canonical_ik_adapter",
    "canonical_ik_solver",
    "complete_runtime_composition",
    "concrete_native_attempt_binding",
    "native_root_path_correction",
    "native_runtime_factory",
    "native_runtime_worker_integration",
    "native_sweep_binding",
    "physics_backend",
    "physics_worker",
    "pinned_model_loader",
    "simulation_context",
    "system_manifest",
)
QUALIFIED_SOURCE_KEYS = {
    "canonical_ik_adapter",
    "canonical_ik_solver",
    "physics_backend",
    "pinned_model_loader",
    "simulation_context",
    "system_manifest",
}
EXACT_AUTHORIZATION = (
    "I authorize exactly one ARM-298 recovered nominal SPACE route-physics "
    "simulation attempt for episode-ef340d0ad2740c118d87, with no automatic "
    "retry, no trajectory playback, and no hardware or physical authority."
)
ZERO_AUTHORITY = {
    "authorization_observed": False,
    "attempt_claimed": False,
    "attempt_consumed": False,
    "claimant_constructed": False,
    "launch_admitted": False,
    "worker_invoked": False,
    "backend_invoked": False,
    "isaac_imported": False,
    "isaac_started": False,
    "scene_loaded": False,
    "timeline_played": False,
    "physics_steps": 0,
    "runtime_methods_called": [],
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


class Arm298LineagePlanError(ValueError):
    """Raised when accepted evidence or the proposed lineage changes."""


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
        raise Arm298LineagePlanError("lineage input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Arm298LineagePlanError(f"required input unavailable: {path}") from exc


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
        raise Arm298LineagePlanError(f"{label} hash changed")
    return claimed


def _validate_evidence(
    qualification: Mapping[str, Any], review: Mapping[str, Any]
) -> tuple[str, str]:
    qualification_hash = _require_hash(
        qualification, "qualification_sha256", "ARM-298 qualification"
    )
    review_hash = _require_hash(
        review, "qualification_review_sha256", "ARM-298 qualification review"
    )
    evaluation = qualification.get("evaluation")
    if (
        qualification.get("schema") != QUALIFICATION_SCHEMA
        or qualification_hash != EXPECTED_QUALIFICATION_SHA256
        or qualification.get("status")
        != "PASS_ARM298_CANONICAL_CONTINUITY_QUALIFICATION"
        or qualification.get("episode_id") != "episode-ef340d0ad2740c118d87"
        or qualification.get("target_id") != "SPACE"
        or not isinstance(evaluation, Mapping)
        or evaluation.get("canonical_boundary_sequence") != 653
        or evaluation.get("first_sequence") != 654
        or evaluation.get("last_sequence") != 940
        or evaluation.get("governed_row_count") != 287
        or evaluation.get("continuity_limit_rad") != 0.05
        or evaluation.get("maximum_adjacent_joint_step_rad", 1.0) > 0.05
        or evaluation.get("canonical_rows_sha256") != EXPECTED_CANONICAL_ROWS_SHA256
        or qualification.get("arm297_replay_permitted") is not False
        or qualification.get("arm298_attempt_authorized") is not False
        or any(
            qualification.get(key) != value
            for key, value in ZERO_AUTHORITY.items()
            if key in qualification
        )
    ):
        raise Arm298LineagePlanError("ARM-298 qualification boundary changed")
    if (
        review.get("schema") != QUALIFICATION_REVIEW_SCHEMA
        or review_hash != EXPECTED_QUALIFICATION_REVIEW_SHA256
        or review.get("status")
        != "ACCEPTED_ARM298_CANONICAL_CONTINUITY_FOR_LINEAGE_PLANNING"
        or review.get("source_qualification_sha256") != qualification_hash
        or review.get("reproduced_evaluation") != evaluation
        or review.get("production_solver_reexecuted") is not True
        or review.get("all_287_governed_rows_reproduced") is not True
        or review.get("unchanged_continuity_limit_verified") is not True
        or review.get("arm297_replay_permitted") is not False
        or review.get("arm298_attempt_authorized") is not False
        or review.get("next_required_stage")
        != "BUILD_FRESH_ARM298_ROUTE_PHYSICS_LINEAGE_PLAN"
    ):
        raise Arm298LineagePlanError("ARM-298 qualification review changed")
    return qualification_hash, review_hash


def build_arm298_lineage_plan(
    qualification: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    qualification_file_sha256: str,
    review_file_sha256: str,
    plan_source_file_sha256: str,
    runtime_sources_sha256: Mapping[str, str],
    repository_commit: str,
    qualified_interpreter: Path,
    proposed_attempt_directory: Path,
    proposed_eula_receipt: Path,
    proposed_memory_receipt: Path,
) -> dict[str, Any]:
    """Freeze ARM-298 inputs and absent outputs without constructing a claimant."""

    qualification_hash, review_hash = _validate_evidence(qualification, review)
    if qualification_file_sha256 != EXPECTED_QUALIFICATION_FILE_SHA256:
        raise Arm298LineagePlanError("ARM-298 qualification file changed")
    if review_file_sha256 != EXPECTED_QUALIFICATION_REVIEW_FILE_SHA256:
        raise Arm298LineagePlanError("ARM-298 qualification review file changed")
    if repository_commit != EXPECTED_REPOSITORY_COMMIT:
        raise Arm298LineagePlanError("merged qualification commit changed")
    if set(runtime_sources_sha256) != set(RUNTIME_SOURCE_KEYS) or not all(
        _digest(value) for value in runtime_sources_sha256.values()
    ):
        raise Arm298LineagePlanError("runtime source inventory changed")
    qualified_hashes = qualification.get("qualified_source_files_sha256")
    if not isinstance(qualified_hashes, Mapping) or any(
        runtime_sources_sha256.get(key) != qualified_hashes.get(key)
        for key in QUALIFIED_SOURCE_KEYS
    ):
        raise Arm298LineagePlanError("qualified production source changed")
    if not _digest(plan_source_file_sha256):
        raise Arm298LineagePlanError("lineage source digest changed")
    interpreter = qualified_interpreter.resolve(strict=True)
    if (
        interpreter != EXPECTED_INTERPRETER_PATH.resolve(strict=True)
        or _file_sha(interpreter) != EXPECTED_INTERPRETER_SHA256
    ):
        raise Arm298LineagePlanError("qualified interpreter changed")

    paths = (
        proposed_attempt_directory,
        proposed_eula_receipt,
        proposed_memory_receipt,
    )
    if (
        not all(path.is_absolute() for path in paths)
        or len({str(path) for path in paths}) != len(paths)
        or proposed_attempt_directory.name != "arm298-nominal-route-physics-attempt-001"
        or proposed_eula_receipt.parent.name
        != "arm298-nominal-route-physics-eula-preflight-001"
        or proposed_memory_receipt.parent.name
        != "arm298-nominal-route-physics-memory-preflight-001"
        or proposed_eula_receipt.name != "receipt.json"
        or proposed_memory_receipt.name != "receipt.json"
        or any(path.exists() for path in paths)
        or proposed_eula_receipt.parent.exists()
        or proposed_memory_receipt.parent.exists()
    ):
        raise Arm298LineagePlanError("fresh ARM-298 output boundary changed")

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "plan_id": "arm298-recovered-nominal-route-physics-lineage-plan-001",
        "status": "READY_FOR_INDEPENDENT_ARM298_LINEAGE_PLAN_REVIEW",
        "case_id": "nominal-fixture-baseline",
        "episode_id": "episode-ef340d0ad2740c118d87",
        "target_id": "SPACE",
        "source_qualification_sha256": qualification_hash,
        "source_qualification_file_sha256": qualification_file_sha256,
        "source_qualification_review_sha256": review_hash,
        "source_qualification_review_file_sha256": review_file_sha256,
        "source_repository_commit": repository_commit,
        "plan_source_file_sha256": plan_source_file_sha256,
        "runtime_sources_sha256": dict(sorted(runtime_sources_sha256.items())),
        "qualified_interpreter": {
            "path": str(interpreter),
            "file_sha256": EXPECTED_INTERPRETER_SHA256,
        },
        "superseded_attempts": [
            "ARM-253",
            "ARM-280",
            "ARM-284",
            "ARM-289",
            "ARM-295",
            "ARM-297",
        ],
        "superseded_authorizations_reusable": False,
        "arm297_replay_permitted": False,
        "arm298_qualification_is_attempt_authority": False,
        "proposed_attempt_directory": str(proposed_attempt_directory),
        "proposed_eula_receipt": str(proposed_eula_receipt),
        "proposed_memory_receipt": str(proposed_memory_receipt),
        "fresh_eula_preflight_required": True,
        "fresh_memory_preflight_required": True,
        "preflights_must_precede_attempt_claim": True,
        "terminal_status_must_precede_simulator_shutdown": True,
        "claimant_review_required_before_authorization": True,
        "required_authorization_statement": EXACT_AUTHORIZATION,
        "authorization_reusable": False,
        **ZERO_AUTHORITY,
        "next_required_stage": "INDEPENDENT_ARM298_LINEAGE_PLAN_REVIEW",
        "limitations": [
            "plan_does_not_construct_a_claimant_or_collect_live_preflights",
            "plan_does_not_accept_or_reuse_authorization",
            "plan_does_not_create_any_governed_output_directory",
            "plan_does_not_start_isaac_or_invoke_runtime_or_backend",
            "simulation_cannot_authorize_hardware_or_physical_motion",
        ],
    }
    return {**core, "plan_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise Arm298LineagePlanError(f"required JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise Arm298LineagePlanError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--qualification-review", type=Path, required=True)
    parser.add_argument("--runtime-source", action="append", nargs=2, required=True)
    parser.add_argument("--repository-commit", required=True)
    parser.add_argument("--qualified-interpreter", type=Path, required=True)
    parser.add_argument("--proposed-attempt-directory", type=Path, required=True)
    parser.add_argument("--proposed-eula-receipt", type=Path, required=True)
    parser.add_argument("--proposed-memory-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime_sources = {key: Path(value) for key, value in args.runtime_source}
    if set(runtime_sources) != set(RUNTIME_SOURCE_KEYS):
        raise Arm298LineagePlanError("runtime source inventory changed")
    result = build_arm298_lineage_plan(
        _load(args.qualification),
        _load(args.qualification_review),
        qualification_file_sha256=_file_sha(args.qualification),
        review_file_sha256=_file_sha(args.qualification_review),
        plan_source_file_sha256=_file_sha(Path(__file__).resolve()),
        runtime_sources_sha256={
            key: _file_sha(path.resolve(strict=True))
            for key, path in runtime_sources.items()
        },
        repository_commit=args.repository_commit,
        qualified_interpreter=args.qualified_interpreter,
        proposed_attempt_directory=args.proposed_attempt_directory,
        proposed_eula_receipt=args.proposed_eula_receipt,
        proposed_memory_receipt=args.proposed_memory_receipt,
    )
    if args.output.exists():
        raise Arm298LineagePlanError("lineage output exists; overwrite refused")
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
