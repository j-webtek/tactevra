"""Launch the reviewed ARM-295 claimant through one reproducible entry point.

This module adds no authority.  It revalidates every retained file used by the
claimant and worker, constructs the deferred concrete backend, and delegates to
the single-use claimant.  Importing this module or constructing its inputs does
not start Isaac, claim an attempt, step physics, or access hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping

from nominal_route_concrete_native_attempt_binding import (
    BindingPaths,
    ConcreteNativeAttemptBinding,
    build_concrete_native_attempt_binding,
)
from nominal_route_native_inventory_recovery_claimant import (
    NativeInventoryRecoveryClaimant,
)


class NativeInventoryRecoveryLaunchError(RuntimeError):
    """Raised before delegation when a retained ARM-295 binding changed."""


QUALIFIED_ISAAC_PYTHON = Path(r"C:\IsaacSim\env_6_1_0\Scripts\python.exe")


def _validate_qualified_interpreter(
    expected: Path = QUALIFIED_ISAAC_PYTHON,
    actual: Path | None = None,
) -> None:
    """Fail before claimant construction when the pinned Isaac host is not active."""

    actual = Path(sys.executable) if actual is None else actual
    try:
        expected_resolved = expected.resolve(strict=True)
        actual_resolved = actual.resolve(strict=True)
    except OSError as exc:
        raise NativeInventoryRecoveryLaunchError(
            f"qualified Isaac Python unavailable: expected={expected}, actual={actual}"
        ) from exc
    if os.path.normcase(str(expected_resolved)) != os.path.normcase(
        str(actual_resolved)
    ):
        raise NativeInventoryRecoveryLaunchError(
            "ARM-295 must run under the qualified Isaac Python: "
            f"expected={expected_resolved}, actual={actual_resolved}"
        )


RUNTIME_SOURCE_FILES = {
    "concrete_native_attempt_binding": "nominal_route_concrete_native_attempt_binding.py",
    "concrete_native_session": "nominal_route_concrete_native_session_smoke.py",
    "native_root_path_correction": "nominal_route_native_root_path_correction.py",
    "native_session": "nominal_route_native_session_smoke.py",
    "native_sweep_binding": "nominal_route_native_sweep_binding.py",
    "native_worker_integration": "nominal_route_native_runtime_worker_integration.py",
    "physics_backend": "nominal_route_physics_backend.py",
    "physics_worker": "nominal_route_physics_worker.py",
}


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise NativeInventoryRecoveryLaunchError(
            f"required input unavailable: {path}"
        ) from exc


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeInventoryRecoveryLaunchError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise NativeInventoryRecoveryLaunchError(
            f"required JSON is not an object: {path}"
        )
    return value


def _canonical_document_hash(document: Mapping[str, Any], excluded: str) -> str:
    core = dict(document)
    core.pop(excluded, None)
    encoded = json.dumps(
        core,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _runtime_source_hashes(integration_root: Path) -> dict[str, str]:
    return {
        name: _file_sha(integration_root / filename)
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


def _runtime_binding_hashes(artifact_root: Path, repo_root: Path) -> dict[str, str]:
    route = _load(
        artifact_root
        / "arm231-state-policy-fixed-fixture-correction-001"
        / "episode-ef340d0ad2740c118d87"
        / "native_mechanics_plan.json"
    )
    bindings = route.get("source_bindings")
    if not isinstance(bindings, Mapping):
        raise NativeInventoryRecoveryLaunchError("route source bindings changed")
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
    expected_route_bindings = {
        "robot_usd": bindings.get("robot_usd_sha256"),
        "robot_import_receipt": bindings.get("robot_import_receipt_sha256"),
        "virtual_profile": bindings.get("virtual_profile_sha256"),
        "key_mechanics_profile": bindings.get("key_mechanics_profile_sha256"),
    }
    if result != expected_route_bindings:
        raise NativeInventoryRecoveryLaunchError(
            "current runtime bindings do not match the retained route"
        )
    return result


def run_authorized_attempt(
    *,
    authorization_statement: str,
    claimant_path: Path,
    claimant_review_path: Path,
    artifact_root: Path,
    repo_root: Path,
    claimant_type: Callable[..., Any] = NativeInventoryRecoveryClaimant,
    binding_builder: Callable[
        [BindingPaths], ConcreteNativeAttemptBinding
    ] = build_concrete_native_attempt_binding,
) -> Mapping[str, Any]:
    """Revalidate current inputs and delegate once to the reviewed claimant."""

    claimant_definition = _load(claimant_path)
    claimant_review = _load(claimant_review_path)
    if _file_sha(claimant_path) != claimant_review.get("source_claimant_file_sha256"):
        raise NativeInventoryRecoveryLaunchError("claimant file changed")

    output_directory = Path(str(claimant_definition["proposed_output_directory"]))
    eula_receipt = Path(str(claimant_definition["fresh_eula_receipt"]))
    memory_receipt = Path(str(claimant_definition["fresh_memory_receipt"]))
    binding = binding_builder(
        BindingPaths(
            artifact_root=artifact_root,
            repo_root=repo_root,
            governed_attempt_directory=output_directory,
        )
    )
    integration_root = repo_root / "software/integrations/isaac_sim"
    return claimant_type(claimant_definition, claimant_review).run(
        authorization_statement=authorization_statement,
        output_directory=output_directory,
        fresh_eula_receipt=eula_receipt,
        fresh_memory_receipt=memory_receipt,
        current_runtime_sources_sha256=_runtime_source_hashes(integration_root),
        current_source_files_sha256=_worker_source_hashes(artifact_root, repo_root),
        current_runtime_bindings_sha256=_runtime_binding_hashes(
            artifact_root, repo_root
        ),
        backend=binding.backend,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization-statement", required=True)
    parser.add_argument("--claimant", type=Path, required=True)
    parser.add_argument("--claimant-review", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()
    _validate_qualified_interpreter()
    result = run_authorized_attempt(
        authorization_statement=args.authorization_statement,
        claimant_path=args.claimant.resolve(strict=True),
        claimant_review_path=args.claimant_review.resolve(strict=True),
        artifact_root=args.artifact_root.resolve(strict=True),
        repo_root=args.repo_root.resolve(strict=True),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
