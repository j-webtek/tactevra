"""Build the inert, reproducible ARM-298 route-physics launch binding.

The CLI hashes retained claimant evidence, the qualified Isaac interpreter,
the merged repository revision, and every runtime source.  It does not import
Isaac, evaluate live gates, claim an attempt, or invoke the claimant.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "tactevra.isaac_lm4_arm298_route_physics_launch_binding.v1"
CLAIMANT_SCHEMA = "tactevra.isaac_lm4_arm298_route_physics_claimant.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_arm298_route_physics_claimant_review.v1"
EXPECTED_CLAIMANT_SHA256 = (
    "a23ec05b51e3e14d3491be588ea3cb76fdf060f590c11adbd28315dcf1fbeaa4"
)
EXPECTED_CLAIMANT_FILE_SHA256 = (
    "0a6649d4eb98081f193f5ede79fde2b01ec05a5ae6c54ced56c6eceb9ed6760c"
)
EXPECTED_REVIEW_SHA256 = (
    "dc1501b904a984be6ac2dd097e4709bafddce6556f65d4d520df925c78431896"
)
EXPECTED_REVIEW_FILE_SHA256 = (
    "b8b4d40efe21ef98629444cc834e9f67cd9f96dcd3bf23739c88ee185e961547"
)
EXPECTED_REPOSITORY_COMMIT = "84bb099e13b19c389095552ad0b267494cdb38c1"
QUALIFIED_ISAAC_PYTHON = r"C:\IsaacSim\env_6_1_0\Scripts\python.exe"
EXPECTED_INTERPRETER_SHA256 = (
    "d55736b9f3d6b4ca7985b82db8ce11edfa09994cf93ce31c6b506543b74f32eb"
)
EXACT_AUTHORIZATION = (
    "I authorize exactly one ARM-298 recovered nominal SPACE route-physics "
    "simulation attempt for episode-ef340d0ad2740c118d87, with no automatic "
    "retry, no trajectory playback, and no hardware or physical authority."
)
RUNTIME_SOURCE_FILES = {
    "canonical_ik_adapter": "software/integrations/isaac_sim/nominal_route_canonical_ik_row_adapter.py",
    "canonical_ik_solver": "software/src/rocell/kinematics/ik.py",
    "complete_runtime_composition": "software/integrations/isaac_sim/nominal_route_complete_runtime_composition.py",
    "concrete_native_attempt_binding": "software/integrations/isaac_sim/nominal_route_concrete_native_attempt_binding.py",
    "native_root_path_correction": "software/integrations/isaac_sim/nominal_route_native_root_path_correction.py",
    "native_runtime_factory": "software/integrations/isaac_sim/nominal_route_native_runtime_factory.py",
    "native_runtime_worker_integration": "software/integrations/isaac_sim/nominal_route_native_runtime_worker_integration.py",
    "native_sweep_binding": "software/integrations/isaac_sim/nominal_route_native_sweep_binding.py",
    "physics_backend": "software/integrations/isaac_sim/nominal_route_physics_backend.py",
    "physics_worker": "software/integrations/isaac_sim/nominal_route_physics_worker.py",
    "pinned_model_loader": "software/src/rocell/application/_pinned_model.py",
    "simulation_context": "software/src/rocell/application/context.py",
    "system_manifest": "software/config/system_manifest.json",
}
ZERO_AUTHORITY = {
    "authorization_observed": False,
    "attempt_claimed": False,
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


class Arm298LaunchBindingError(ValueError):
    """Raised when retained evidence or launch inputs have drifted."""


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
        raise Arm298LaunchBindingError("binding input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Arm298LaunchBindingError(f"required file unavailable: {path}") from exc


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    core = dict(document)
    core.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise Arm298LaunchBindingError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any], *, launch_admitted: bool) -> bool:
    expected = dict(ZERO_AUTHORITY)
    expected["launch_admitted"] = launch_admitted
    return all(document.get(key) == value for key, value in expected.items())


def _claimant_zero_authority(
    document: Mapping[str, Any], *, launch_admitted: bool
) -> bool:
    expected = {
        "authorization_observed": False,
        "attempt_claimed": False,
        "worker_invoked": False,
        "backend_invoked": False,
        "isaac_started": False,
        "timeline_played": False,
        "physics_steps": 0,
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
        "launch_admitted": launch_admitted,
    }
    return all(document.get(key) == value for key, value in expected.items())


def build_launch_binding(
    claimant: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    claimant_file_sha256: str,
    review_file_sha256: str,
    interpreter_path: Path,
    interpreter_file_sha256: str,
    repository_commit: str,
    runtime_source_files_sha256: Mapping[str, str],
    binding_source_file_sha256: str,
) -> dict[str, Any]:
    """Return an offline binding that admits only a future reviewed launcher."""

    claimant_hash = _require_hash(claimant, "claimant_sha256", "claimant")
    review_hash = _require_hash(review, "claimant_review_sha256", "claimant review")
    if (
        claimant.get("schema") != CLAIMANT_SCHEMA
        or claimant.get("status") != "READY_FOR_INDEPENDENT_ARM298_CLAIMANT_REVIEW"
        or claimant_hash != EXPECTED_CLAIMANT_SHA256
        or claimant_file_sha256 != EXPECTED_CLAIMANT_FILE_SHA256
        or review.get("schema") != REVIEW_SCHEMA
        or review.get("status") != "ACCEPTED_FOR_EXACT_ARM298_ONE_ATTEMPT_AUTHORIZATION"
        or review_hash != EXPECTED_REVIEW_SHA256
        or review_file_sha256 != EXPECTED_REVIEW_FILE_SHA256
        or review.get("source_claimant_sha256") != claimant_hash
        or review.get("source_claimant_file_sha256") != claimant_file_sha256
        or claimant.get("required_authorization_statement") != EXACT_AUTHORIZATION
        or review.get("required_authorization_statement") != EXACT_AUTHORIZATION
        or repository_commit != EXPECTED_REPOSITORY_COMMIT
        or str(interpreter_path) != QUALIFIED_ISAAC_PYTHON
        or interpreter_file_sha256 != EXPECTED_INTERPRETER_SHA256
        or dict(runtime_source_files_sha256) != claimant.get("runtime_sources_sha256")
        or not _claimant_zero_authority(claimant, launch_admitted=False)
        or not _claimant_zero_authority(review, launch_admitted=True)
    ):
        raise Arm298LaunchBindingError("ARM-298 launch source contract changed")
    for digest, label in (
        (binding_source_file_sha256, "binding source"),
        (interpreter_file_sha256, "qualified interpreter"),
    ):
        if not isinstance(digest, str) or len(digest) != 64:
            raise Arm298LaunchBindingError(f"{label} digest is invalid")
    core = {
        "schema": SCHEMA,
        "binding_id": "arm298-route-physics-launch-binding-001",
        "status": "READY_FOR_INDEPENDENT_ARM298_LAUNCH_BINDING_REVIEW",
        "repository_commit": repository_commit,
        "qualified_interpreter": {
            "path": str(interpreter_path),
            "file_sha256": interpreter_file_sha256,
        },
        "source_claimant_sha256": claimant_hash,
        "source_claimant_file_sha256": claimant_file_sha256,
        "source_claimant_review_sha256": review_hash,
        "source_claimant_review_file_sha256": review_file_sha256,
        "source_binding_file_sha256": binding_source_file_sha256,
        "runtime_sources_sha256": dict(sorted(runtime_source_files_sha256.items())),
        "required_authorization_statement": EXACT_AUTHORIZATION,
        "proposed_output_directory": claimant["proposed_output_directory"],
        "fresh_eula_receipt": claimant["fresh_eula_receipt"],
        "fresh_memory_receipt": claimant["fresh_memory_receipt"],
        "fresh_gate_policy": {
            "eula_then_memory": True,
            "both_receipts_retained_before_attempt_claim": True,
            "receipts_must_not_preexist": True,
            "receipt_hashes_retained_in_terminal_status": True,
        },
        "terminalization_policy": {
            "terminal_status_before_shutdown": True,
            "exception_type_message_and_phase_retained": True,
            "all_required_outputs_before_shutdown_on_success": True,
            "no_automatic_retry": True,
        },
        "launch_order": [
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
        ],
        "next_required_stage": "INDEPENDENT_ARM298_LAUNCH_BINDING_REVIEW",
        **ZERO_AUTHORITY,
        "launch_admitted": False,
    }
    return {**core, "launch_binding_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise Arm298LaunchBindingError(f"required JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise Arm298LaunchBindingError(f"required JSON is not an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claimant", type=Path, required=True)
    parser.add_argument("--claimant-review", type=Path, required=True)
    parser.add_argument("--interpreter", type=Path, required=True)
    parser.add_argument("--repository-commit", required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--binding-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime_hashes = {
        key: _file_sha(args.repository_root / filename)
        for key, filename in RUNTIME_SOURCE_FILES.items()
    }
    result = build_launch_binding(
        _load(args.claimant),
        _load(args.claimant_review),
        claimant_file_sha256=_file_sha(args.claimant),
        review_file_sha256=_file_sha(args.claimant_review),
        interpreter_path=args.interpreter,
        interpreter_file_sha256=_file_sha(args.interpreter),
        repository_commit=args.repository_commit,
        runtime_source_files_sha256=runtime_hashes,
        binding_source_file_sha256=_file_sha(args.binding_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
