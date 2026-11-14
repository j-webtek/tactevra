"""Build the inert ARM-299 recovery lineage after retained ARM-298 failure."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "tactevra.isaac_lm4_arm299_route_physics_lineage_plan.v1"
EXPECTED_REPOSITORY_COMMIT = "f84c69dc99f1df546dd27aec9c757c0a54e6033b"
EXPECTED_ARM298_STATUS_SHA256 = (
    "959e0a7c840f1b742ea479abe7cc65944d0aaa630724b7346e13a3a21d240a2c"
)
EXPECTED_WRAPPER_SHA256 = (
    "8427f2426f91b74f0339f17879ed064bfa3dc086c4a2df9f049022d974b77fd4"
)
EXPECTED_INTERPRETER_PATH = Path("C:/IsaacSim/env_6_1_0/Scripts/python.exe")
EXPECTED_INTERPRETER_SHA256 = (
    "d55736b9f3d6b4ca7985b82db8ce11edfa09994cf93ce31c6b506543b74f32eb"
)
RUNTIME_SOURCE_KEYS = (
    "complete_runtime_composition",
    "concrete_native_attempt_binding",
    "native_runtime_factory",
    "native_runtime_worker_integration",
    "native_session_wrapper",
    "native_sweep_binding",
    "physics_backend",
    "physics_worker",
)
EXACT_FUTURE_AUTHORIZATION = (
    "I authorize exactly one ARM-299 recovered nominal SPACE route-physics "
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
    "physics_steps": 0,
    "trajectory_playback": False,
    "joint_positions_submitted": False,
    "joint_targets_submitted": False,
    "key_contact": False,
    "automatic_retry": False,
    "hardware_access": False,
    "physical_authority": False,
}


class Arm299LineagePlanError(ValueError):
    """Raised when retained evidence or a proposed output changes."""


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
        raise Arm299LineagePlanError("lineage input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Arm299LineagePlanError(f"required input unavailable: {path}") from exc


def _validate_terminal_status(status: Mapping[str, Any]) -> None:
    if status != {
        "attempt_count": 1,
        "automatic_retry": False,
        "error_message": (
            "'IsaacArticulationLinkView' object has no attribute "
            "'set_dof_positions'"
        ),
        "error_stage": "execute_backend",
        "error_type": "AttributeError",
        "hardware_access": False,
        "physical_authority": False,
        "status": "FAILED_RETAINED_NO_RETRY",
    }:
        raise Arm299LineagePlanError("ARM-298 terminal status changed")


def build_arm299_lineage_plan(
    arm298_status: Mapping[str, Any],
    *,
    arm298_status_file_sha256: str,
    plan_source_file_sha256: str,
    runtime_sources_sha256: Mapping[str, str],
    repository_commit: str,
    qualified_interpreter: Path,
    proposed_attempt_directory: Path,
    proposed_eula_receipt: Path,
    proposed_memory_receipt: Path,
) -> dict[str, Any]:
    """Bind the correction and fresh outputs without creating a claimant."""

    _validate_terminal_status(arm298_status)
    if arm298_status_file_sha256 != EXPECTED_ARM298_STATUS_SHA256:
        raise Arm299LineagePlanError("ARM-298 terminal file changed")
    if repository_commit != EXPECTED_REPOSITORY_COMMIT:
        raise Arm299LineagePlanError("merged correction commit changed")
    if set(runtime_sources_sha256) != set(RUNTIME_SOURCE_KEYS):
        raise Arm299LineagePlanError("runtime source inventory changed")
    if (
        runtime_sources_sha256.get("native_session_wrapper")
        != EXPECTED_WRAPPER_SHA256
    ):
        raise Arm299LineagePlanError("corrected articulation wrapper changed")
    if not all(
        isinstance(value, str) and len(value) == 64
        for value in runtime_sources_sha256.values()
    ):
        raise Arm299LineagePlanError("runtime source digest is invalid")
    try:
        interpreter = qualified_interpreter.resolve(strict=True)
    except OSError as exc:
        raise Arm299LineagePlanError("qualified interpreter is unavailable") from exc
    if (
        interpreter != EXPECTED_INTERPRETER_PATH.resolve(strict=True)
        or _file_sha(interpreter) != EXPECTED_INTERPRETER_SHA256
    ):
        raise Arm299LineagePlanError("qualified interpreter changed")
    proposed = {
        "attempt_directory": str(proposed_attempt_directory.resolve()),
        "eula_receipt": str(proposed_eula_receipt.resolve()),
        "memory_receipt": str(proposed_memory_receipt.resolve()),
    }
    if len(set(proposed.values())) != 3 or any(
        Path(path).exists() for path in proposed.values()
    ):
        raise Arm299LineagePlanError("ARM-299 outputs must be distinct and absent")
    core = {
        "schema": SCHEMA,
        "status": "READY_FOR_INDEPENDENT_ARM299_LINEAGE_REVIEW",
        "episode_id": "episode-ef340d0ad2740c118d87",
        "target_id": "SPACE",
        "source_arm298_terminal_sha256": arm298_status_file_sha256,
        "source_arm298_terminal_status": dict(arm298_status),
        "repository_commit": repository_commit,
        "plan_source_file_sha256": plan_source_file_sha256,
        "runtime_sources_sha256": dict(sorted(runtime_sources_sha256.items())),
        "qualified_interpreter": {
            "path": str(interpreter),
            "file_sha256": EXPECTED_INTERPRETER_SHA256,
        },
        "proposed_outputs": proposed,
        "required_future_authorization_statement": EXACT_FUTURE_AUTHORIZATION,
        "next_required_stage": "INDEPENDENT_ARM299_LINEAGE_REVIEW",
        **ZERO_AUTHORITY,
    }
    return {**core, "plan_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise Arm299LineagePlanError(f"required JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise Arm299LineagePlanError(f"{path} must contain an object")
    return value


def _parse_sources(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        key, separator, filename = value.partition("=")
        if not separator or key in result:
            raise Arm299LineagePlanError("runtime source must be unique KEY=PATH")
        result[key] = Path(filename)
    return result


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm298-status", type=Path, required=True)
    parser.add_argument("--runtime-source", action="append", default=[])
    parser.add_argument("--repository-commit", required=True)
    parser.add_argument("--qualified-interpreter", type=Path, required=True)
    parser.add_argument("--attempt-directory", type=Path, required=True)
    parser.add_argument("--eula-receipt", type=Path, required=True)
    parser.add_argument("--memory-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise Arm299LineagePlanError("lineage plan output already exists")
    sources = _parse_sources(args.runtime_source)
    plan = build_arm299_lineage_plan(
        _load(args.arm298_status),
        arm298_status_file_sha256=_file_sha(args.arm298_status),
        plan_source_file_sha256=_file_sha(Path(__file__)),
        runtime_sources_sha256={key: _file_sha(path) for key, path in sources.items()},
        repository_commit=args.repository_commit,
        qualified_interpreter=args.qualified_interpreter,
        proposed_attempt_directory=args.attempt_directory,
        proposed_eula_receipt=args.eula_receipt,
        proposed_memory_receipt=args.memory_receipt,
    )
    _write_new(args.output, plan)
    print(json.dumps(plan, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
