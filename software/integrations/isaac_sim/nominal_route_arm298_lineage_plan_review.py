"""Independently review the inert ARM-298 route-physics lineage plan."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PLAN_SCHEMA = "tactevra.isaac_lm4_arm298_route_physics_lineage_plan.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_arm298_route_physics_lineage_plan_review.v1"
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
EXPECTED_AUTHORIZATION = (
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


class Arm298LineagePlanReviewError(ValueError):
    """Raised when the proposed lineage or any bound source changes."""


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
        raise Arm298LineagePlanReviewError(
            "review input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Arm298LineagePlanReviewError(
            f"required input unavailable: {path}"
        ) from exc


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise Arm298LineagePlanReviewError(f"{label} hash changed")
    return claimed


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise Arm298LineagePlanReviewError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise Arm298LineagePlanReviewError(f"{path} must contain an object")
    return value


def _static_review(plan_source: Path) -> dict[str, Any]:
    text = plan_source.read_text(encoding="utf-8")
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
        raise Arm298LineagePlanReviewError("runtime- or transport-capable import found")
    forbidden = (
        "SimulationApp(",
        "start_headless(",
        "initialize_physics(",
        "SimulationManager.step(",
        "set_dof_positions(",
        "set_dof_position_targets(",
        "set_joint_position_targets(",
        "construct_runtime(",
        "execute_backend(",
        "run_one_attempt(",
        "serial.Serial(",
    )
    if any(token in text for token in forbidden):
        raise Arm298LineagePlanReviewError(
            "runtime, motion, or transport call surface found"
        )
    build = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "build_arm298_lineage_plan"
        ),
        None,
    )
    if build is None:
        raise Arm298LineagePlanReviewError("lineage plan builder is absent")
    return {
        "runtime_and_transport_imports_absent": True,
        "runtime_motion_and_transport_calls_absent": True,
        "lineage_plan_builder_present": True,
    }


def review_arm298_lineage_plan(
    plan: Mapping[str, Any],
    *,
    plan_file_sha256: str,
    plan_source: Path,
    qualification_file: Path,
    qualification_review_file: Path,
    runtime_sources: Mapping[str, Path],
    qualified_interpreter: Path,
    review_source_file_sha256: str,
) -> dict[str, Any]:
    """Rebind every source and prove the proposed ARM-298 outputs stay absent."""

    plan_hash = _require_hash(plan, "plan_sha256", "ARM-298 lineage plan")
    qualification = _load(qualification_file)
    qualification_review = _load(qualification_review_file)
    qualification_hash = _require_hash(
        qualification, "qualification_sha256", "ARM-298 qualification"
    )
    qualification_review_hash = _require_hash(
        qualification_review,
        "qualification_review_sha256",
        "ARM-298 qualification review",
    )
    if (
        _file_sha(qualification_file) != EXPECTED_QUALIFICATION_FILE_SHA256
        or _file_sha(qualification_review_file)
        != EXPECTED_QUALIFICATION_REVIEW_FILE_SHA256
        or qualification.get("schema") != QUALIFICATION_SCHEMA
        or qualification_hash != EXPECTED_QUALIFICATION_SHA256
        or qualification.get("status")
        != "PASS_ARM298_CANONICAL_CONTINUITY_QUALIFICATION"
        or qualification_review.get("schema") != QUALIFICATION_REVIEW_SCHEMA
        or qualification_review_hash != EXPECTED_QUALIFICATION_REVIEW_SHA256
        or qualification_review.get("source_qualification_sha256") != qualification_hash
        or qualification_review.get("reproduced_evaluation")
        != qualification.get("evaluation")
        or qualification_review.get("status")
        != "ACCEPTED_ARM298_CANONICAL_CONTINUITY_FOR_LINEAGE_PLANNING"
    ):
        raise Arm298LineagePlanReviewError("ARM-298 qualification evidence changed")
    if set(runtime_sources) != set(RUNTIME_SOURCE_KEYS):
        raise Arm298LineagePlanReviewError("runtime source inventory changed")
    current_runtime_hashes = {
        key: _file_sha(path.resolve(strict=True))
        for key, path in runtime_sources.items()
    }
    interpreter = qualified_interpreter.resolve(strict=True)
    if (
        interpreter != EXPECTED_INTERPRETER_PATH.resolve(strict=True)
        or _file_sha(interpreter) != EXPECTED_INTERPRETER_SHA256
    ):
        raise Arm298LineagePlanReviewError("qualified interpreter changed")
    static_review = _static_review(plan_source)

    attempt = Path(str(plan.get("proposed_attempt_directory", "")))
    eula_receipt = Path(str(plan.get("proposed_eula_receipt", "")))
    memory_receipt = Path(str(plan.get("proposed_memory_receipt", "")))
    paths = (attempt, eula_receipt, memory_receipt)
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("plan_id")
        != "arm298-recovered-nominal-route-physics-lineage-plan-001"
        or plan.get("status") != "READY_FOR_INDEPENDENT_ARM298_LINEAGE_PLAN_REVIEW"
        or plan.get("case_id") != "nominal-fixture-baseline"
        or plan.get("episode_id") != "episode-ef340d0ad2740c118d87"
        or plan.get("target_id") != "SPACE"
        or plan.get("source_qualification_sha256") != qualification_hash
        or plan.get("source_qualification_file_sha256")
        != EXPECTED_QUALIFICATION_FILE_SHA256
        or plan.get("source_qualification_review_sha256") != qualification_review_hash
        or plan.get("source_qualification_review_file_sha256")
        != EXPECTED_QUALIFICATION_REVIEW_FILE_SHA256
        or plan.get("source_repository_commit") != EXPECTED_REPOSITORY_COMMIT
        or plan.get("superseded_attempts")
        != ["ARM-253", "ARM-280", "ARM-284", "ARM-289", "ARM-295", "ARM-297"]
        or plan.get("superseded_authorizations_reusable") is not False
        or plan.get("arm297_replay_permitted") is not False
        or plan.get("arm298_qualification_is_attempt_authority") is not False
        or plan.get("fresh_eula_preflight_required") is not True
        or plan.get("fresh_memory_preflight_required") is not True
        or plan.get("preflights_must_precede_attempt_claim") is not True
        or plan.get("terminal_status_must_precede_simulator_shutdown") is not True
        or plan.get("claimant_review_required_before_authorization") is not True
        or plan.get("required_authorization_statement") != EXPECTED_AUTHORIZATION
        or plan.get("authorization_reusable") is not False
        or any(plan.get(key) != value for key, value in ZERO_AUTHORITY.items())
        or plan.get("next_required_stage") != "INDEPENDENT_ARM298_LINEAGE_PLAN_REVIEW"
    ):
        raise Arm298LineagePlanReviewError("ARM-298 lineage boundary changed")
    if (
        plan.get("plan_source_file_sha256") != _file_sha(plan_source)
        or plan.get("runtime_sources_sha256")
        != dict(sorted(current_runtime_hashes.items()))
        or plan.get("qualified_interpreter")
        != {
            "path": str(interpreter),
            "file_sha256": EXPECTED_INTERPRETER_SHA256,
        }
    ):
        raise Arm298LineagePlanReviewError("ARM-298 source binding changed")
    if (
        not all(path.is_absolute() for path in paths)
        or len({str(path) for path in paths}) != len(paths)
        or attempt.name != "arm298-nominal-route-physics-attempt-001"
        or eula_receipt.parent.name != "arm298-nominal-route-physics-eula-preflight-001"
        or memory_receipt.parent.name
        != "arm298-nominal-route-physics-memory-preflight-001"
        or eula_receipt.name != "receipt.json"
        or memory_receipt.name != "receipt.json"
        or any(path.exists() for path in paths)
        or eula_receipt.parent.exists()
        or memory_receipt.parent.exists()
    ):
        raise Arm298LineagePlanReviewError("ARM-298 output boundary changed")

    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm298-route-physics-lineage-plan-review-001",
        "status": "ACCEPTED_ARM298_LINEAGE_FOR_CLAIMANT_CONSTRUCTION",
        "source_plan_sha256": plan_hash,
        "source_plan_file_sha256": plan_file_sha256,
        "source_plan_source_file_sha256": _file_sha(plan_source),
        "source_qualification_sha256": qualification_hash,
        "source_qualification_file_sha256": EXPECTED_QUALIFICATION_FILE_SHA256,
        "source_qualification_review_sha256": qualification_review_hash,
        "source_qualification_review_file_sha256": (
            EXPECTED_QUALIFICATION_REVIEW_FILE_SHA256
        ),
        "source_repository_commit": EXPECTED_REPOSITORY_COMMIT,
        "verified_runtime_sources_sha256": dict(sorted(current_runtime_hashes.items())),
        "qualified_interpreter": {
            "path": str(interpreter),
            "file_sha256": EXPECTED_INTERPRETER_SHA256,
        },
        "static_review": static_review,
        "proposed_attempt_directory": str(attempt),
        "proposed_attempt_directory_absent": True,
        "proposed_eula_receipt": str(eula_receipt),
        "proposed_eula_receipt_absent": True,
        "proposed_memory_receipt": str(memory_receipt),
        "proposed_memory_receipt_absent": True,
        "required_authorization_statement": EXPECTED_AUTHORIZATION,
        **ZERO_AUTHORITY,
        "next_required_stage": (
            "BUILD_SINGLE_USE_ARM298_CLAIMANT_AND_INDEPENDENT_REVIEW"
        ),
        "limitations": [
            "review_does_not_construct_a_claimant_or_collect_live_preflights",
            "review_does_not_accept_authorization_or_claim_an_attempt",
            "review_does_not_start_isaac_or_invoke_runtime_or_backend",
            "review_does_not_authorize_hardware_or_physical_motion",
        ],
        "review_source_file_sha256": review_source_file_sha256,
    }
    return {**core, "lineage_review_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-source", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--qualification-review", type=Path, required=True)
    parser.add_argument("--runtime-source", action="append", nargs=2, required=True)
    parser.add_argument("--qualified-interpreter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review_arm298_lineage_plan(
        _load(args.plan),
        plan_file_sha256=_file_sha(args.plan),
        plan_source=args.plan_source,
        qualification_file=args.qualification,
        qualification_review_file=args.qualification_review,
        runtime_sources={key: Path(value) for key, value in args.runtime_source},
        qualified_interpreter=args.qualified_interpreter,
        review_source_file_sha256=_file_sha(Path(__file__).resolve()),
    )
    if args.output.exists():
        raise Arm298LineagePlanReviewError("review output exists; overwrite refused")
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
