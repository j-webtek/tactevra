"""Execute exactly one reviewed ARM-298 route-physics attempt.

Importing this module is inert.  The CLI validates the reviewed launch binding,
its independent review, this launcher's independent review, the qualified
Isaac interpreter, repository ancestry, all runtime/worker/binding inputs, and
the exact fresh authorization before constructing a deferred backend and
delegating once to :class:`Arm298Claimant`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Mapping


INTEGRATION_ROOT = Path(__file__).resolve().parent
SOFTWARE_SOURCE_ROOT = INTEGRATION_ROOT.parents[1] / "src"
if not (SOFTWARE_SOURCE_ROOT / "rocell/__init__.py").is_file():
    raise RuntimeError(f"RoCell source root unavailable: {SOFTWARE_SOURCE_ROOT}")
for source_root in (INTEGRATION_ROOT, SOFTWARE_SOURCE_ROOT):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from nominal_route_arm298_claimant import Arm298Claimant  # noqa: E402
from nominal_route_concrete_native_attempt_binding import (  # noqa: E402
    BindingPaths,
    ConcreteNativeAttemptBinding,
    build_concrete_native_attempt_binding,
)


class Arm298LaunchError(RuntimeError):
    """Raised before delegation when the reviewed launch boundary changed."""


BINDING_SCHEMA = "tactevra.isaac_lm4_arm298_route_physics_launch_binding.v1"
BINDING_REVIEW_SCHEMA = (
    "tactevra.isaac_lm4_arm298_route_physics_launch_binding_review.v1"
)
LAUNCHER_REVIEW_SCHEMA = "tactevra.isaac_lm4_arm298_route_physics_launcher_review.v1"
EXPECTED_BINDING_SHA256 = (
    "dceeb71e5c17def71a2744a91610961e3d676450c31544315402675c144567c5"
)
EXPECTED_BINDING_FILE_SHA256 = (
    "a91365ba0e877732822bd3e99fb05bbebb78bad85272f9b30460e2f59aa62424"
)
EXPECTED_BINDING_REVIEW_SHA256 = (
    "69e7f3f2368740462add44f3d0359cad729e2848379fa005d38858815a87445d"
)
EXPECTED_BINDING_REVIEW_FILE_SHA256 = (
    "4af40b4d2ca0b76ef2ed593536a814f1e0b83148c7407c0f6f504fea4a81cbc0"
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
        raise Arm298LaunchError("launch input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Arm298LaunchError(f"required input unavailable: {path}") from exc


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise Arm298LaunchError(f"required JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise Arm298LaunchError(f"required JSON is not an object: {path}")
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    core = dict(document)
    core.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise Arm298LaunchError(f"{label} hash changed")
    return claimed


def _validate_binding(
    binding: Mapping[str, Any],
    binding_review: Mapping[str, Any],
    *,
    binding_file_sha256: str,
    binding_review_file_sha256: str,
) -> None:
    binding_hash = _require_hash(binding, "launch_binding_sha256", "launch binding")
    review_hash = _require_hash(
        binding_review, "launch_binding_review_sha256", "launch binding review"
    )
    if (
        binding.get("schema") != BINDING_SCHEMA
        or binding.get("status") != "READY_FOR_INDEPENDENT_ARM298_LAUNCH_BINDING_REVIEW"
        or binding_hash != EXPECTED_BINDING_SHA256
        or binding_file_sha256 != EXPECTED_BINDING_FILE_SHA256
        or binding_review.get("schema") != BINDING_REVIEW_SCHEMA
        or binding_review.get("status") != "ACCEPTED_FOR_ARM298_LAUNCHER_IMPLEMENTATION"
        or review_hash != EXPECTED_BINDING_REVIEW_SHA256
        or binding_review_file_sha256 != EXPECTED_BINDING_REVIEW_FILE_SHA256
        or binding_review.get("source_launch_binding_sha256") != binding_hash
        or binding_review.get("source_launch_binding_file_sha256")
        != binding_file_sha256
        or binding.get("required_authorization_statement") != EXACT_AUTHORIZATION
        or binding_review.get("required_authorization_statement") != EXACT_AUTHORIZATION
        or any(binding.get(key) != value for key, value in ZERO_AUTHORITY.items())
        or binding.get("launch_admitted") is not False
        or any(
            binding_review.get(key) != value for key, value in ZERO_AUTHORITY.items()
        )
        or binding_review.get("launch_admitted") is not False
    ):
        raise Arm298LaunchError("reviewed ARM-298 launch binding changed")


def _validate_launcher_review(
    review: Mapping[str, Any],
    *,
    launcher_source_sha256: str,
    binding: Mapping[str, Any],
    binding_review: Mapping[str, Any],
) -> None:
    _require_hash(review, "launcher_review_sha256", "launcher review")
    if (
        review.get("schema") != LAUNCHER_REVIEW_SCHEMA
        or review.get("status") != "ACCEPTED_FOR_EXACT_ARM298_ONE_ATTEMPT_AUTHORIZATION"
        or review.get("source_launcher_file_sha256") != launcher_source_sha256
        or review.get("source_launch_binding_sha256")
        != binding.get("launch_binding_sha256")
        or review.get("source_launch_binding_review_sha256")
        != binding_review.get("launch_binding_review_sha256")
        or review.get("required_authorization_statement") != EXACT_AUTHORIZATION
        or review.get("single_claimant_delegation") is not True
        or review.get("fresh_gates_owned_by_claimant") is not True
        or review.get("terminalization_owned_by_worker") is not True
        or review.get("automatic_retry_refused") is not True
        or any(review.get(key) != value for key, value in ZERO_AUTHORITY.items())
        or review.get("launch_admitted") is not False
    ):
        raise Arm298LaunchError("independent ARM-298 launcher review changed")


def _validate_qualified_interpreter(
    binding: Mapping[str, Any], actual: Path | None = None
) -> None:
    expected = binding.get("qualified_interpreter")
    if not isinstance(expected, Mapping):
        raise Arm298LaunchError("qualified interpreter binding is absent")
    actual = Path(sys.executable) if actual is None else actual
    expected_path = Path(str(expected.get("path", "")))
    try:
        expected_resolved = expected_path.resolve(strict=True)
        actual_resolved = actual.resolve(strict=True)
    except OSError as exc:
        raise Arm298LaunchError(
            f"qualified Isaac Python unavailable: expected={expected_path}, actual={actual}"
        ) from exc
    if os.path.normcase(str(expected_resolved)) != os.path.normcase(
        str(actual_resolved)
    ) or _file_sha(actual_resolved) != expected.get("file_sha256"):
        raise Arm298LaunchError(
            "ARM-298 must run under the exact qualified Isaac Python"
        )


def _repository_contains_binding_commit(repo_root: Path, commit: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", commit, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _runtime_source_hashes(repo_root: Path) -> dict[str, str]:
    return {
        name: _file_sha(repo_root / filename)
        for name, filename in RUNTIME_SOURCE_FILES.items()
    }


def _worker_source_hashes(artifact_root: Path, repo_root: Path) -> dict[str, str]:
    return {
        "nominal_profile": _file_sha(
            artifact_root / "arm250-base-board-nominal-profile-001/profile.json"
        ),
        "route_plan": _file_sha(
            artifact_root
            / "arm231-state-policy-fixed-fixture-correction-001"
            / "episode-ef340d0ad2740c118d87"
            / "native_mechanics_plan.json"
        ),
        "correction_plan": _file_sha(
            artifact_root
            / "arm235-state-policy-transit-clearance-correction-plan-001/plan.json"
        ),
        "toolchain_lock": _file_sha(
            repo_root / "software/config/isaac_sim_toolchain_lock.json"
        ),
    }


def _canonical_document_hash(document: Mapping[str, Any], excluded: str) -> str:
    core = dict(document)
    core.pop(excluded, None)
    return _sha(core)


def _runtime_binding_hashes(artifact_root: Path, repo_root: Path) -> dict[str, str]:
    route = _load(
        artifact_root
        / "arm231-state-policy-fixed-fixture-correction-001"
        / "episode-ef340d0ad2740c118d87"
        / "native_mechanics_plan.json"
    )
    bindings = route.get("source_bindings")
    if not isinstance(bindings, Mapping):
        raise Arm298LaunchError("route source bindings changed")
    import_receipt = _load(
        repo_root
        / "software/integrations/isaac_sim/evidence/roarm_m3_urdf_import_20260929.json"
    )
    result = {
        "robot_usd": _file_sha(
            artifact_root
            / "wp1-import-003/roarm_m3_kinematic_40dbd84"
            / "roarm_m3_kinematic_40dbd84.usda"
        ),
        "robot_import_receipt": _canonical_document_hash(
            import_receipt, "receipt_sha256"
        ),
        "virtual_profile": _file_sha(
            repo_root / "software/config/virtual_commissioning_profile.json"
        ),
        "key_mechanics_profile": str(bindings.get("key_mechanics_profile_sha256", "")),
    }
    expected = {
        "robot_usd": bindings.get("robot_usd_sha256"),
        "robot_import_receipt": bindings.get("robot_import_receipt_sha256"),
        "virtual_profile": bindings.get("virtual_profile_sha256"),
        "key_mechanics_profile": bindings.get("key_mechanics_profile_sha256"),
    }
    if result != expected:
        raise Arm298LaunchError(
            "current runtime bindings do not match the retained route"
        )
    return result


CommitChecker = Callable[[Path, str], bool]
ClaimantType = Callable[..., Any]
BindingBuilder = Callable[[BindingPaths], ConcreteNativeAttemptBinding]


def run_authorized_attempt(
    *,
    authorization_statement: str,
    claimant_path: Path,
    claimant_review_path: Path,
    launch_binding_path: Path,
    launch_binding_review_path: Path,
    launcher_review_path: Path,
    launcher_source_path: Path,
    artifact_root: Path,
    repo_root: Path,
    actual_interpreter: Path | None = None,
    claimant_type: ClaimantType = Arm298Claimant,
    binding_builder: BindingBuilder = build_concrete_native_attempt_binding,
    commit_checker: CommitChecker = _repository_contains_binding_commit,
) -> Mapping[str, Any]:
    """Revalidate the full boundary and delegate once to the reviewed claimant."""

    if authorization_statement != EXACT_AUTHORIZATION:
        raise Arm298LaunchError("exact fresh ARM-298 authorization is absent")
    binding = _load(launch_binding_path)
    binding_review = _load(launch_binding_review_path)
    _validate_binding(
        binding,
        binding_review,
        binding_file_sha256=_file_sha(launch_binding_path),
        binding_review_file_sha256=_file_sha(launch_binding_review_path),
    )
    _validate_qualified_interpreter(binding, actual_interpreter)
    repository_commit = str(binding.get("repository_commit", ""))
    if not commit_checker(repo_root, repository_commit):
        raise Arm298LaunchError("bound repository commit is not current ancestry")
    claimant_definition = _load(claimant_path)
    claimant_review = _load(claimant_review_path)
    if (
        _file_sha(claimant_path) != binding.get("source_claimant_file_sha256")
        or _file_sha(claimant_review_path)
        != binding.get("source_claimant_review_file_sha256")
        or _runtime_source_hashes(repo_root) != binding.get("runtime_sources_sha256")
    ):
        raise Arm298LaunchError("ARM-298 claimant or runtime source changed")
    launcher_review = _load(launcher_review_path)
    _validate_launcher_review(
        launcher_review,
        launcher_source_sha256=_file_sha(launcher_source_path),
        binding=binding,
        binding_review=binding_review,
    )
    output_directory = Path(str(binding["proposed_output_directory"]))
    eula_receipt = Path(str(binding["fresh_eula_receipt"]))
    memory_receipt = Path(str(binding["fresh_memory_receipt"]))
    if (
        output_directory.exists()
        or eula_receipt.exists()
        or memory_receipt.exists()
        or eula_receipt.parent.exists()
        or memory_receipt.parent.exists()
    ):
        raise Arm298LaunchError("ARM-298 governed output is not fresh")
    concrete = binding_builder(
        BindingPaths(
            artifact_root=artifact_root,
            repo_root=repo_root,
            governed_attempt_directory=output_directory,
        )
    )
    return claimant_type(claimant_definition, claimant_review).run(
        authorization_statement=authorization_statement,
        output_directory=output_directory,
        fresh_eula_receipt=eula_receipt,
        fresh_memory_receipt=memory_receipt,
        current_runtime_sources_sha256=_runtime_source_hashes(repo_root),
        current_source_files_sha256=_worker_source_hashes(artifact_root, repo_root),
        current_runtime_bindings_sha256=_runtime_binding_hashes(
            artifact_root, repo_root
        ),
        backend=concrete.backend,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization-statement", required=True)
    parser.add_argument("--claimant", type=Path, required=True)
    parser.add_argument("--claimant-review", type=Path, required=True)
    parser.add_argument("--launch-binding", type=Path, required=True)
    parser.add_argument("--launch-binding-review", type=Path, required=True)
    parser.add_argument("--launcher-review", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()
    result = run_authorized_attempt(
        authorization_statement=args.authorization_statement,
        claimant_path=args.claimant.resolve(strict=True),
        claimant_review_path=args.claimant_review.resolve(strict=True),
        launch_binding_path=args.launch_binding.resolve(strict=True),
        launch_binding_review_path=args.launch_binding_review.resolve(strict=True),
        launcher_review_path=args.launcher_review.resolve(strict=True),
        launcher_source_path=Path(__file__).resolve(strict=True),
        artifact_root=args.artifact_root.resolve(strict=True),
        repo_root=args.repo_root.resolve(strict=True),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
