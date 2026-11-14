"""Independently review the inert ARM-300 reproducible launch binding.

The reviewer reopens every bound byte, checks the qualified interpreter and
merged revision, and statically proves the binding builder has no simulator,
motion, or transport execution path.  Acceptance does not run the launcher or
grant attempt, hardware, or physical authority.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "tactevra.isaac_lm4_arm300_route_physics_launch_binding_review.v1"
BINDING_SCHEMA = "tactevra.isaac_lm4_arm300_route_physics_launch_binding.v1"
CLAIMANT_SCHEMA = "tactevra.isaac_lm4_arm300_route_physics_claimant.v1"
CLAIMANT_REVIEW_SCHEMA = "tactevra.isaac_lm4_arm300_route_physics_claimant_review.v1"
EXPECTED_REPOSITORY_COMMIT = "59f68b4406965c6cd0779d8ff45d80d99f5904c5"
EXPECTED_INTERPRETER_PATH = r"C:\IsaacSim\env_6_1_0\Scripts\python.exe"
EXPECTED_INTERPRETER_SHA256 = (
    "d55736b9f3d6b4ca7985b82db8ce11edfa09994cf93ce31c6b506543b74f32eb"
)
EXPECTED_AUTHORIZATION = (
    "I authorize exactly one ARM-300 recovered nominal SPACE route-physics "
    "simulation attempt for episode-ef340d0ad2740c118d87, with no automatic "
    "retry, no trajectory playback, and no hardware or physical authority."
)
EXPECTED_ORDER = [
    "verify_qualified_interpreter_identity",
    "verify_merged_repository_commit",
    "revalidate_binding_claimant_review_and_runtime_sources",
    "verify_exact_fresh_external_authorization",
    "evaluate_fresh_eula_preflight",
    "evaluate_fresh_memory_preflight",
    "retain_both_fresh_receipts",
    "delegate_exactly_once_to_reviewed_claimant",
    "retain_terminal_status_before_simulator_shutdown",
    "stop_without_retry",
]
RUNTIME_SOURCE_FILES = {
    "complete_runtime_composition": "software/integrations/isaac_sim/nominal_route_complete_runtime_composition.py",
    "concrete_native_attempt_binding": "software/integrations/isaac_sim/nominal_route_concrete_native_attempt_binding.py",
    "native_runtime_factory": "software/integrations/isaac_sim/nominal_route_native_runtime_factory.py",
    "native_runtime_worker_integration": "software/integrations/isaac_sim/nominal_route_native_runtime_worker_integration.py",
    "native_session_wrapper": "software/integrations/isaac_sim/nominal_route_native_session_smoke.py",
    "native_sweep_binding": "software/integrations/isaac_sim/nominal_route_native_sweep_binding.py",
    "physics_backend": "software/integrations/isaac_sim/nominal_route_physics_backend.py",
    "physics_worker": "software/integrations/isaac_sim/nominal_route_physics_worker.py",
}
ZERO_AUTHORITY = {
    "authorization_observed": False,
    "attempt_claimed": False,
    "attempt_consumed": False,
    "claimant_invoked": False,
    "backend_invoked": False,
    "isaac_imported": False,
    "isaac_started": False,
    "timeline_played": False,
    "physics_steps": 0,
    "trajectory_playback": False,
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


class Arm300LaunchBindingReviewError(ValueError):
    """Raised when the reproducible launch binding cannot be accepted."""


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
        raise Arm300LaunchBindingReviewError(
            "review input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Arm300LaunchBindingReviewError(
            f"required file unavailable: {path}"
        ) from exc


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    core = dict(document)
    core.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise Arm300LaunchBindingReviewError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return document.get("launch_admitted") is False and all(
        document.get(key) == value for key, value in ZERO_AUTHORITY.items()
    )


def _review_source(source_bytes: bytes) -> dict[str, bool]:
    try:
        tree = ast.parse(source_bytes.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise Arm300LaunchBindingReviewError(
            "binding source is not reviewable Python"
        ) from exc
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    forbidden_imports = {
        name
        for name in imports
        if name.startswith(("isaacsim", "omni", "serial", "rocell.providers"))
    }
    forbidden_calls = calls & {
        "run_one_attempt",
        "run_authorized_attempt",
        "play",
        "step",
        "set_joint_position_targets",
        "set_joint_positions",
        "send",
    }
    if forbidden_imports or forbidden_calls:
        raise Arm300LaunchBindingReviewError(
            "binding source contains simulator, motion, or transport execution"
        )
    return {
        "simulator_and_transport_imports_absent": True,
        "simulator_motion_and_transport_calls_absent": True,
        "builder_only_materialization": True,
    }


def review_launch_binding(
    binding: Mapping[str, Any],
    claimant: Mapping[str, Any],
    claimant_review: Mapping[str, Any],
    *,
    binding_file_sha256: str,
    claimant_file_sha256: str,
    claimant_review_file_sha256: str,
    binding_source_bytes: bytes,
    interpreter_file_sha256: str,
    repository_commit: str,
    runtime_source_files_sha256: Mapping[str, str],
) -> dict[str, Any]:
    """Return a zero-authority independent acceptance receipt."""

    binding_hash = _require_hash(binding, "launch_binding_sha256", "launch binding")
    claimant_hash = _require_hash(claimant, "claimant_sha256", "claimant")
    claimant_review_hash = _require_hash(
        claimant_review, "claimant_review_sha256", "claimant review"
    )
    source_sha = hashlib.sha256(binding_source_bytes).hexdigest()
    interpreter = binding.get("qualified_interpreter")
    gates = binding.get("fresh_gate_policy")
    terminal = binding.get("terminalization_policy")
    if (
        binding.get("schema") != BINDING_SCHEMA
        or binding.get("status") != "READY_FOR_INDEPENDENT_ARM300_LAUNCH_BINDING_REVIEW"
        or claimant.get("schema") != CLAIMANT_SCHEMA
        or claimant_review.get("schema") != CLAIMANT_REVIEW_SCHEMA
        or binding.get("source_claimant_sha256") != claimant_hash
        or binding.get("source_claimant_file_sha256") != claimant_file_sha256
        or binding.get("source_claimant_review_sha256") != claimant_review_hash
        or binding.get("source_claimant_review_file_sha256")
        != claimant_review_file_sha256
        or binding.get("source_binding_file_sha256") != source_sha
        or binding.get("repository_commit") != EXPECTED_REPOSITORY_COMMIT
        or repository_commit != EXPECTED_REPOSITORY_COMMIT
        or not isinstance(interpreter, Mapping)
        or interpreter.get("path") != EXPECTED_INTERPRETER_PATH
        or interpreter.get("file_sha256") != EXPECTED_INTERPRETER_SHA256
        or interpreter_file_sha256 != EXPECTED_INTERPRETER_SHA256
        or binding.get("runtime_sources_sha256")
        != dict(sorted(runtime_source_files_sha256.items()))
        or binding.get("runtime_sources_sha256")
        != claimant.get("runtime_sources_sha256")
        or binding.get("required_authorization_statement") != EXPECTED_AUTHORIZATION
        or binding.get("launch_order") != EXPECTED_ORDER
        or not isinstance(gates, Mapping)
        or set(gates.values()) != {True}
        or not isinstance(terminal, Mapping)
        or set(terminal.values()) != {True}
        or binding.get("proposed_output_directory")
        != claimant.get("proposed_output_directory")
        or binding.get("fresh_eula_receipt") != claimant.get("fresh_eula_receipt")
        or binding.get("fresh_memory_receipt") != claimant.get("fresh_memory_receipt")
        or not _zero_authority(binding)
    ):
        raise Arm300LaunchBindingReviewError("ARM-300 launch binding changed")
    static_review = _review_source(binding_source_bytes)
    core = {
        "schema": SCHEMA,
        "review_id": "arm300-route-physics-launch-binding-review-001",
        "status": "ACCEPTED_FOR_ARM300_LAUNCHER_IMPLEMENTATION",
        "source_launch_binding_sha256": binding_hash,
        "source_launch_binding_file_sha256": binding_file_sha256,
        "source_binding_source_sha256": source_sha,
        "source_claimant_sha256": claimant_hash,
        "source_claimant_review_sha256": claimant_review_hash,
        "repository_commit": repository_commit,
        "qualified_interpreter_file_sha256": interpreter_file_sha256,
        "required_authorization_statement": EXPECTED_AUTHORIZATION,
        "fresh_gates_precede_single_delegation": True,
        "terminal_status_precedes_shutdown": True,
        "automatic_retry_refused": True,
        "static_review": static_review,
        "next_required_stage": "IMPLEMENT_AND_REVIEW_ARM300_EXECUTABLE_LAUNCHER",
        **ZERO_AUTHORITY,
        "launch_admitted": False,
    }
    return {**core, "launch_binding_review_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise Arm300LaunchBindingReviewError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise Arm300LaunchBindingReviewError(f"required JSON is not an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--claimant", type=Path, required=True)
    parser.add_argument("--claimant-review", type=Path, required=True)
    parser.add_argument("--binding-source", type=Path, required=True)
    parser.add_argument("--interpreter", type=Path, required=True)
    parser.add_argument("--repository-commit", required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime_hashes = {
        key: _file_sha(args.repository_root / filename)
        for key, filename in RUNTIME_SOURCE_FILES.items()
    }
    result = review_launch_binding(
        _load(args.binding),
        _load(args.claimant),
        _load(args.claimant_review),
        binding_file_sha256=_file_sha(args.binding),
        claimant_file_sha256=_file_sha(args.claimant),
        claimant_review_file_sha256=_file_sha(args.claimant_review),
        binding_source_bytes=args.binding_source.read_bytes(),
        interpreter_file_sha256=_file_sha(args.interpreter),
        repository_commit=args.repository_commit,
        runtime_source_files_sha256=runtime_hashes,
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
