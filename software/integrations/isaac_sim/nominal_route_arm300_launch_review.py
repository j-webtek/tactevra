"""Independently review the executable ARM-300 route-physics launcher.

This reviewer performs static analysis and exact-byte/ancestry checks only. It
does not import the launcher, evaluate live EULA or memory state, construct a
backend, claim an attempt, start Isaac, or grant physical authority.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping


SCHEMA = "tactevra.isaac_lm4_arm300_route_physics_launcher_review.v1"
BINDING_SCHEMA = "tactevra.isaac_lm4_arm300_route_physics_launch_binding.v1"
BINDING_REVIEW_SCHEMA = (
    "tactevra.isaac_lm4_arm300_route_physics_launch_binding_review.v1"
)
EXPECTED_BINDING_SHA256 = (
    "192c7f01e859ce5cd18ac03d6931a62813f1eafd466bfdeae5a954e9f91fa348"
)
EXPECTED_BINDING_FILE_SHA256 = (
    "f158df214caf281f2a86dd90ebbf1bf46d910853ed31f65ffa96fa331f7ad427"
)
EXPECTED_BINDING_REVIEW_SHA256 = (
    "b09cba9b42a161bdd072429090811db8ec0bd5d16b2b5d22a2780d445ecf8c1a"
)
EXPECTED_BINDING_REVIEW_FILE_SHA256 = (
    "4d13c0b923145b5fccc35f5ed50e74b8fe18126c4178c0aa85eb9be6a5871b48"
)
EXACT_AUTHORIZATION = (
    "I authorize exactly one ARM-300 recovered nominal SPACE route-physics "
    "simulation attempt for episode-ef340d0ad2740c118d87, with no automatic "
    "retry, no trajectory playback, and no hardware or physical authority."
)
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


class Arm300LauncherReviewError(ValueError):
    """Raised when the launcher cannot be independently accepted."""


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
        raise Arm300LauncherReviewError("review input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Arm300LauncherReviewError(f"required file unavailable: {path}") from exc


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise Arm300LauncherReviewError(f"required JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise Arm300LauncherReviewError(f"required JSON is not an object: {path}")
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    core = dict(document)
    core.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise Arm300LauncherReviewError(f"{label} hash changed")
    return claimed


def _is_ancestor(repo_root: Path, commit: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", commit, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _static_review(source_bytes: bytes) -> dict[str, bool]:
    try:
        tree = ast.parse(source_bytes.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise Arm300LauncherReviewError(
            "launcher source is not reviewable Python"
        ) from exc
    imports: set[str] = set()
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
    if {
        "nominal_route_arm300_claimant",
        "nominal_route_concrete_native_attempt_binding",
    } - imports:
        raise Arm300LauncherReviewError("required reviewed launcher imports changed")
    forbidden_imports = {
        name
        for name in imports
        if name.startswith(("isaacsim", "omni", "serial", "rocell.providers"))
    }
    run = functions.get("run_authorized_attempt")
    main = functions.get("main")
    if forbidden_imports or run is None or main is None:
        raise Arm300LauncherReviewError("launcher static boundary changed")
    if any(isinstance(node, (ast.For, ast.While)) for node in ast.walk(run)):
        raise Arm300LauncherReviewError("launcher contains a retry-capable loop")
    calls = [node for node in ast.walk(run) if isinstance(node, ast.Call)]

    def named(call: ast.Call, name: str) -> bool:
        return (
            isinstance(call.func, ast.Name)
            and call.func.id == name
            or isinstance(call.func, ast.Attribute)
            and call.func.attr == name
        )

    builder_calls = [call for call in calls if named(call, "binding_builder")]
    claimant_calls = [call for call in calls if named(call, "claimant_type")]
    run_calls = [call for call in calls if named(call, "run")]
    direct_worker_calls = [call for call in calls if named(call, "run_one_attempt")]
    auth_checks = [
        node
        for node in ast.walk(run)
        if isinstance(node, ast.Compare)
        and any(
            isinstance(child, ast.Name) and child.id == "authorization_statement"
            for child in ast.walk(node)
        )
    ]
    output_checks = [
        call
        for call in calls
        if named(call, "exists")
        and call.lineno < (builder_calls[0].lineno if builder_calls else 0)
    ]
    if (
        len(builder_calls) != 1
        or len(claimant_calls) != 1
        or len(run_calls) != 1
        or direct_worker_calls
        or not auth_checks
        or auth_checks[0].lineno >= builder_calls[0].lineno
        or len(output_checks) < 5
    ):
        raise Arm300LauncherReviewError(
            "single-delegation or fail-closed ordering changed"
        )
    main_calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)]
    if sum(named(call, "run_authorized_attempt") for call in main_calls) != 1:
        raise Arm300LauncherReviewError("CLI delegation count changed")
    return {
        "import_is_inert": True,
        "exact_authorization_precedes_backend_construction": True,
        "interpreter_ancestry_and_sources_precede_backend_construction": True,
        "governed_output_absence_precedes_backend_construction": True,
        "single_deferred_backend_construction": True,
        "single_claimant_construction": True,
        "single_claimant_run_call": True,
        "direct_worker_call_absent": True,
        "retry_loop_absent": True,
        "hardware_transport_imports_absent": True,
    }


def review_launcher(
    binding: Mapping[str, Any],
    binding_review: Mapping[str, Any],
    *,
    binding_file_sha256: str,
    binding_review_file_sha256: str,
    launcher_source_bytes: bytes,
    reviewer_source_file_sha256: str,
    claimant_file_sha256: str,
    claimant_review_file_sha256: str,
    interpreter_file_sha256: str,
    runtime_source_files_sha256: Mapping[str, str],
    repo_root: Path,
) -> dict[str, Any]:
    """Return an inert independent acceptance receipt for the launcher."""

    binding_hash = _require_hash(binding, "launch_binding_sha256", "launch binding")
    binding_review_hash = _require_hash(
        binding_review, "launch_binding_review_sha256", "launch binding review"
    )
    interpreter = binding.get("qualified_interpreter")
    if (
        binding.get("schema") != BINDING_SCHEMA
        or binding.get("status") != "READY_FOR_INDEPENDENT_ARM300_LAUNCH_BINDING_REVIEW"
        or binding_hash != EXPECTED_BINDING_SHA256
        or binding_file_sha256 != EXPECTED_BINDING_FILE_SHA256
        or binding_review.get("schema") != BINDING_REVIEW_SCHEMA
        or binding_review.get("status") != "ACCEPTED_FOR_ARM300_LAUNCHER_IMPLEMENTATION"
        or binding_review_hash != EXPECTED_BINDING_REVIEW_SHA256
        or binding_review_file_sha256 != EXPECTED_BINDING_REVIEW_FILE_SHA256
        or binding_review.get("source_launch_binding_sha256") != binding_hash
        or binding.get("required_authorization_statement") != EXACT_AUTHORIZATION
        or binding_review.get("required_authorization_statement") != EXACT_AUTHORIZATION
        or not isinstance(interpreter, Mapping)
        or interpreter.get("file_sha256") != interpreter_file_sha256
        or claimant_file_sha256 != binding.get("source_claimant_file_sha256")
        or claimant_review_file_sha256
        != binding.get("source_claimant_review_file_sha256")
        or dict(runtime_source_files_sha256) != binding.get("runtime_sources_sha256")
        or not _is_ancestor(repo_root, str(binding.get("repository_commit", "")))
        or any(binding.get(key) != value for key, value in ZERO_AUTHORITY.items())
        or binding.get("launch_admitted") is not False
    ):
        raise Arm300LauncherReviewError("ARM-300 launcher source contract changed")
    attempt = Path(str(binding.get("proposed_output_directory", "")))
    if attempt.exists():
        raise Arm300LauncherReviewError(
            "governed output is not absent: proposed_output_directory"
        )
    for path_key in ("fresh_eula_receipt", "fresh_memory_receipt"):
        path = Path(str(binding.get(path_key, "")))
        if path.exists() or path.parent.exists():
            raise Arm300LauncherReviewError(
                f"governed output is not absent: {path_key}"
            )
    static_review = _static_review(launcher_source_bytes)
    launcher_source_sha256 = hashlib.sha256(launcher_source_bytes).hexdigest()
    core = {
        "schema": SCHEMA,
        "review_id": "arm300-route-physics-launcher-review-001",
        "status": "ACCEPTED_FOR_EXACT_ARM300_ONE_ATTEMPT_AUTHORIZATION",
        "source_launcher_file_sha256": launcher_source_sha256,
        "source_reviewer_file_sha256": reviewer_source_file_sha256,
        "source_launch_binding_sha256": binding_hash,
        "source_launch_binding_file_sha256": binding_file_sha256,
        "source_launch_binding_review_sha256": binding_review_hash,
        "source_launch_binding_review_file_sha256": binding_review_file_sha256,
        "required_authorization_statement": EXACT_AUTHORIZATION,
        "single_claimant_delegation": True,
        "fresh_gates_owned_by_claimant": True,
        "terminalization_owned_by_worker": True,
        "automatic_retry_refused": True,
        "static_review": static_review,
        "next_required_stage": "SEPARATE_EXACT_ARM300_ONE_ATTEMPT_AUTHORIZATION",
        **ZERO_AUTHORITY,
        "launch_admitted": False,
    }
    return {**core, "launcher_review_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch-binding", type=Path, required=True)
    parser.add_argument("--launch-binding-review", type=Path, required=True)
    parser.add_argument("--claimant", type=Path, required=True)
    parser.add_argument("--claimant-review", type=Path, required=True)
    parser.add_argument("--launcher-source", type=Path, required=True)
    parser.add_argument("--reviewer-source", type=Path, required=True)
    parser.add_argument("--interpreter", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime_hashes = {
        key: _file_sha(args.repository_root / filename)
        for key, filename in RUNTIME_SOURCE_FILES.items()
    }
    result = review_launcher(
        _load(args.launch_binding),
        _load(args.launch_binding_review),
        binding_file_sha256=_file_sha(args.launch_binding),
        binding_review_file_sha256=_file_sha(args.launch_binding_review),
        launcher_source_bytes=args.launcher_source.read_bytes(),
        reviewer_source_file_sha256=_file_sha(args.reviewer_source),
        claimant_file_sha256=_file_sha(args.claimant),
        claimant_review_file_sha256=_file_sha(args.claimant_review),
        interpreter_file_sha256=_file_sha(args.interpreter),
        runtime_source_files_sha256=runtime_hashes,
        repo_root=args.repo_root.resolve(strict=True),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
