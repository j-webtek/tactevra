"""Independently review an inert ARM-300 recovery lineage plan."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PLAN_SCHEMA = "tactevra.isaac_lm4_arm300_route_physics_lineage_plan.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_arm300_route_physics_lineage_plan_review.v1"
EXPECTED_REPOSITORY_COMMIT = "50fd017ff89b1d4cb453f1abd93887e98237b10f"
EXPECTED_ARM299_STATUS_SHA256 = (
    "976c0883581e7dd54ba43ed6364d11e351ec5b8349ecf5ea5fd87d09cf0a6396"
)
EXPECTED_SWEEP_BINDING_SHA256 = (
    "d7062c6c5debebb3a8e74ab07c46fc4ae3ed86fe5ce087ed7be6a974c6ae561d"
)
EXPECTED_AUTHORIZATION = (
    "I authorize exactly one ARM-300 recovered nominal SPACE route-physics "
    "simulation attempt for episode-ef340d0ad2740c118d87, with no automatic "
    "retry, no trajectory playback, and no hardware or physical authority."
)
RUNTIME_SOURCE_KEYS = {
    "complete_runtime_composition",
    "concrete_native_attempt_binding",
    "native_runtime_factory",
    "native_runtime_worker_integration",
    "native_session_wrapper",
    "native_sweep_binding",
    "physics_backend",
    "physics_worker",
}
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
    "physics_steps": 0,
    "trajectory_playback": False,
    "joint_positions_submitted": False,
    "joint_targets_submitted": False,
    "key_contact": False,
    "automatic_retry": False,
    "hardware_access": False,
    "physical_authority": False,
}


class Arm300LineageReviewError(ValueError):
    """Raised when any reviewed input or authority boundary changes."""


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
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Arm300LineageReviewError(f"required input unavailable: {path}") from exc


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise Arm300LineageReviewError(f"required JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise Arm300LineageReviewError(f"{path} must contain an object")
    return value


def _static_review(path: Path) -> dict[str, bool]:
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
        raise Arm300LineageReviewError("runtime or transport import found")
    forbidden = (
        "SimulationApp(",
        "initialize_physics(",
        "set_dof_positions(",
        "set_dof_position_targets(",
        "execute_backend(",
        "run_one_attempt(",
        "serial.Serial(",
    )
    if any(token in text for token in forbidden):
        raise Arm300LineageReviewError("runtime, motion, or transport call found")
    return {
        "runtime_and_transport_imports_absent": True,
        "runtime_motion_and_transport_calls_absent": True,
    }


def review_arm300_lineage_plan(
    plan: Mapping[str, Any],
    *,
    plan_file_sha256: str,
    plan_source: Path,
    arm299_status_file: Path,
    runtime_sources: Mapping[str, Path],
    qualified_interpreter: Path,
    review_source_file_sha256: str,
) -> dict[str, Any]:
    claimed = plan.get("plan_sha256")
    unsigned = dict(plan)
    unsigned.pop("plan_sha256", None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise Arm300LineageReviewError("ARM-300 plan hash changed")
    if (
        len(plan_file_sha256) != 64
        or any(character not in "0123456789abcdef" for character in plan_file_sha256)
    ):
        raise Arm300LineageReviewError("ARM-300 plan file hash is invalid")
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("status") != "READY_FOR_INDEPENDENT_ARM300_LINEAGE_REVIEW"
        or plan.get("repository_commit") != EXPECTED_REPOSITORY_COMMIT
        or plan.get("required_future_authorization_statement")
        != EXPECTED_AUTHORIZATION
        or any(plan.get(key) != value for key, value in ZERO_AUTHORITY.items())
    ):
        raise Arm300LineageReviewError("ARM-300 plan boundary changed")
    if (
        _file_sha(arm299_status_file) != EXPECTED_ARM299_STATUS_SHA256
        or plan.get("source_arm299_terminal_sha256")
        != EXPECTED_ARM299_STATUS_SHA256
        or _load(arm299_status_file) != plan.get("source_arm299_terminal_status")
    ):
        raise Arm300LineageReviewError("ARM-299 terminal evidence changed")
    if set(runtime_sources) != RUNTIME_SOURCE_KEYS:
        raise Arm300LineageReviewError("runtime source inventory changed")
    observed_sources = {
        key: _file_sha(path) for key, path in sorted(runtime_sources.items())
    }
    if (
        observed_sources != plan.get("runtime_sources_sha256")
        or observed_sources.get("native_sweep_binding")
        != EXPECTED_SWEEP_BINDING_SHA256
        or _file_sha(plan_source) != plan.get("plan_source_file_sha256")
    ):
        raise Arm300LineageReviewError("corrected runtime source changed")
    interpreter = plan.get("qualified_interpreter")
    if not isinstance(interpreter, Mapping) or (
        str(qualified_interpreter.resolve(strict=True)) != interpreter.get("path")
        or _file_sha(qualified_interpreter) != interpreter.get("file_sha256")
    ):
        raise Arm300LineageReviewError("qualified interpreter changed")
    outputs = plan.get("proposed_outputs")
    if not isinstance(outputs, Mapping) or len(set(outputs.values())) != 3 or any(
        Path(str(path)).exists() for path in outputs.values()
    ):
        raise Arm300LineageReviewError("ARM-300 outputs are not fresh and absent")
    static = _static_review(plan_source)
    core = {
        "schema": REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ARM300_CLAIMANT_CONSTRUCTION",
        "source_plan_sha256": claimed,
        "source_plan_file_sha256": plan_file_sha256,
        "review_source_file_sha256": review_source_file_sha256,
        "recomputed_runtime_sources_sha256": observed_sources,
        "fresh_outputs_verified_absent": True,
        "required_future_authorization_statement": EXPECTED_AUTHORIZATION,
        "next_required_stage": "BUILD_AND_REVIEW_ARM300_SINGLE_USE_CLAIMANT",
        **static,
        **ZERO_AUTHORITY,
    }
    return {**core, "review_sha256": _sha(core)}


def _parse_sources(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        key, separator, filename = value.partition("=")
        if not separator or key in result:
            raise Arm300LineageReviewError("runtime source must be unique KEY=PATH")
        result[key] = Path(filename)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-source", type=Path, required=True)
    parser.add_argument("--arm299-status", type=Path, required=True)
    parser.add_argument("--runtime-source", action="append", default=[])
    parser.add_argument("--qualified-interpreter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise Arm300LineageReviewError("review output already exists")
    review = review_arm300_lineage_plan(
        _load(args.plan),
        plan_file_sha256=_file_sha(args.plan),
        plan_source=args.plan_source,
        arm299_status_file=args.arm299_status,
        runtime_sources=_parse_sources(args.runtime_source),
        qualified_interpreter=args.qualified_interpreter,
        review_source_file_sha256=_file_sha(Path(__file__)),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_text(
        json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(args.output)
    print(json.dumps(review, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
