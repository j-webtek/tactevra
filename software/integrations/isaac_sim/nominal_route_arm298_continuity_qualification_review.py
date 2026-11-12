"""Independently review the ARM-298 offline continuity qualification."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


INTEGRATION_ROOT = Path(__file__).resolve().parent
if str(INTEGRATION_ROOT) not in sys.path:
    sys.path.insert(0, str(INTEGRATION_ROOT))

from nominal_route_arm298_continuity_qualification import (  # noqa: E402
    EXPECTED_ADAPTER_FILE_SHA256,
    EXPECTED_ADAPTER_REVIEW_FILE_SHA256,
    EXPECTED_ARM297_STATUS_FILE_SHA256,
    EXPECTED_CURRENT_ADAPTER_SOURCE_SHA256,
    EXPECTED_CURRENT_BACKEND_SOURCE_SHA256,
    EXPECTED_ROUTE_FILE_SHA256,
    MAXIMUM_ADJACENT_JOINT_STEP_RAD,
    ZERO_AUTHORITY,
    build_qualification,
)


QUALIFICATION_SCHEMA = "tactevra.isaac_lm4_arm298_continuity_qualification.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_arm298_continuity_qualification_review.v1"


class Arm298ContinuityQualificationReviewError(ValueError):
    """Raised when retained qualification evidence cannot be reproduced."""


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
        raise Arm298ContinuityQualificationReviewError(
            "review input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Arm298ContinuityQualificationReviewError(
            f"required input unavailable: {path}"
        ) from exc


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise Arm298ContinuityQualificationReviewError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise Arm298ContinuityQualificationReviewError(f"{path} must contain an object")
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    core = dict(document)
    core.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise Arm298ContinuityQualificationReviewError(f"{label} hash changed")
    return claimed


def _static_review(path: Path) -> dict[str, Any]:
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
        raise Arm298ContinuityQualificationReviewError(
            "runtime- or transport-capable import found"
        )
    forbidden = (
        "SimulationApp(",
        "start_headless(",
        "initialize_physics(",
        "SimulationManager.step(",
        "set_dof_positions(",
        "set_dof_position_targets(",
        "set_joint_position_targets(",
        "execute_backend(",
        "run_one_attempt(",
        "serial.Serial(",
    )
    if any(token in text for token in forbidden):
        raise Arm298ContinuityQualificationReviewError(
            "simulator, motion, attempt, or transport surface found"
        )
    if "evaluate_route_continuity(" not in text or "_production_runtime(" not in text:
        raise Arm298ContinuityQualificationReviewError(
            "full-route production qualification surface missing"
        )
    return {
        "runtime_and_transport_imports_absent": True,
        "simulator_motion_attempt_and_transport_calls_absent": True,
        "full_route_evaluator_present": True,
        "production_kinematics_runtime_present": True,
    }


def review_qualification(
    qualification: Mapping[str, Any],
    *,
    qualification_file_sha256: str,
    qualification_source_path: Path,
    review_source_path: Path,
    arm297_status_path: Path,
    route_path: Path,
    adapter_definition_path: Path,
    adapter_review_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Re-hash every input and independently reproduce the 287-row result."""

    qualification_hash = _require_hash(
        qualification, "qualification_sha256", "ARM-298 qualification"
    )
    static_review = _static_review(qualification_source_path)
    reproduced = build_qualification(
        arm297_status_path=arm297_status_path,
        route_path=route_path,
        adapter_definition_path=adapter_definition_path,
        adapter_review_path=adapter_review_path,
        repo_root=repo_root,
        qualification_source_path=qualification_source_path,
    )
    evaluation = qualification.get("evaluation")
    if not isinstance(evaluation, Mapping):
        raise Arm298ContinuityQualificationReviewError(
            "qualification evaluation missing"
        )
    if (
        qualification != reproduced
        or qualification.get("schema") != QUALIFICATION_SCHEMA
        or qualification.get("status")
        != "PASS_ARM298_CANONICAL_CONTINUITY_QUALIFICATION"
        or qualification.get("source_arm297_status_file_sha256")
        != EXPECTED_ARM297_STATUS_FILE_SHA256
        or qualification.get("source_route_file_sha256") != EXPECTED_ROUTE_FILE_SHA256
        or qualification.get("source_adapter_file_sha256")
        != EXPECTED_ADAPTER_FILE_SHA256
        or qualification.get("source_adapter_review_file_sha256")
        != EXPECTED_ADAPTER_REVIEW_FILE_SHA256
        or qualification.get("qualified_source_files_sha256", {}).get(
            "canonical_ik_adapter"
        )
        != EXPECTED_CURRENT_ADAPTER_SOURCE_SHA256
        or qualification.get("qualified_source_files_sha256", {}).get("physics_backend")
        != EXPECTED_CURRENT_BACKEND_SOURCE_SHA256
        or evaluation.get("canonical_boundary_sequence") != 653
        or evaluation.get("first_sequence") != 654
        or evaluation.get("last_sequence") != 940
        or evaluation.get("governed_row_count") != 287
        or evaluation.get("continuity_limit_rad") != MAXIMUM_ADJACENT_JOINT_STEP_RAD
        or not isinstance(
            evaluation.get("maximum_adjacent_joint_step_rad"), (int, float)
        )
        or evaluation["maximum_adjacent_joint_step_rad"]
        > MAXIMUM_ADJACENT_JOINT_STEP_RAD
        or any(qualification.get(key) != value for key, value in ZERO_AUTHORITY.items())
        or qualification.get("arm297_replay_permitted") is not False
        or qualification.get("arm298_attempt_authorized") is not False
    ):
        raise Arm298ContinuityQualificationReviewError(
            "ARM-298 qualification boundary or reproduction changed"
        )

    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm298-canonical-continuity-qualification-review-001",
        "status": "ACCEPTED_ARM298_CANONICAL_CONTINUITY_FOR_LINEAGE_PLANNING",
        "source_qualification_sha256": qualification_hash,
        "source_qualification_file_sha256": qualification_file_sha256,
        "source_qualification_source_file_sha256": _file_sha(qualification_source_path),
        "review_source_file_sha256": _file_sha(review_source_path),
        "static_review": static_review,
        "reproduced_evaluation": dict(evaluation),
        "production_solver_reexecuted": True,
        "all_287_governed_rows_reproduced": True,
        "unchanged_continuity_limit_verified": True,
        "arm297_replay_permitted": False,
        "arm298_attempt_authorized": False,
        **ZERO_AUTHORITY,
        "next_required_stage": "BUILD_FRESH_ARM298_ROUTE_PHYSICS_LINEAGE_PLAN",
        "limitations": [
            "review_reexecutes_offline_kinematics_only",
            "review_does_not_start_isaac_or_step_physics",
            "review_does_not_check_clearance_tool_key_metrics_or_root_drift",
            "review_does_not_authorize_or_claim_an_attempt",
            "review_cannot_authorize_hardware_or_physical_motion",
        ],
    }
    return {**core, "qualification_review_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--qualification-source", type=Path, required=True)
    parser.add_argument("--arm297-status", type=Path, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--adapter-definition", type=Path, required=True)
    parser.add_argument("--adapter-review", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review_qualification(
        _load(args.qualification),
        qualification_file_sha256=_file_sha(args.qualification),
        qualification_source_path=args.qualification_source.resolve(strict=True),
        review_source_path=Path(__file__).resolve(),
        arm297_status_path=args.arm297_status,
        route_path=args.route,
        adapter_definition_path=args.adapter_definition,
        adapter_review_path=args.adapter_review,
        repo_root=args.repo_root.resolve(strict=True),
    )
    if args.output.exists():
        raise Arm298ContinuityQualificationReviewError(
            "review output exists; overwrite refused"
        )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
