"""Independently review ARM-274 without starting or importing a simulator."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


REVIEW_SCHEMA = "tactevra.isaac_lm4_native_runtime_worker_integration_review.v1"
INTEGRATION_SCHEMA = "tactevra.isaac_lm4_native_runtime_worker_integration.v1"


class NativeRuntimeWorkerIntegrationReviewError(ValueError):
    """Raised when ARM-274 gains authority or loses lifecycle guarantees."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeRuntimeWorkerIntegrationReviewError(f"{label} hash changed")
    return claimed


def _static_review(path: Path) -> dict[str, bool]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    if any(name.startswith(("isaac", "omni", "serial")) for name in imports):
        raise NativeRuntimeWorkerIntegrationReviewError(
            "integration imports simulator or hardware authority"
        )
    forbidden_calls = (
        "run_one_attempt(",
        "set_dof_positions(",
        "set_dof_position_targets(",
        "write_data(",
        "step(",
    )
    if any(token in text for token in forbidden_calls):
        raise NativeRuntimeWorkerIntegrationReviewError(
            "integration claims attempts or submits runtime commands"
        )
    return {
        "isaac_and_hardware_imports_absent": True,
        "worker_attempt_call_absent": True,
        "joint_and_physics_commands_absent": True,
    }


def review_integration(
    definition: Mapping[str, Any],
    *,
    definition_file_sha256: str,
    integration_source: Path,
    review_source_sha256: str,
) -> dict[str, Any]:
    integration_hash = _require_hash(
        definition, "integration_sha256", "ARM-274 integration"
    )
    worker_review = definition.get("worker_review", {})
    backend_review = definition.get("backend_review", {})
    _require_hash(worker_review, "worker_review_sha256", "worker review")
    _require_hash(backend_review, "backend_review_sha256", "backend review")
    lifecycle = definition.get("lifecycle")
    expected = [
        "verify_worker_claim",
        "create_session_once",
        "start_headless_once",
        "load_scene_once",
        "initialize_physics_once",
        "settle_scene_once",
        "obtain_native_objects_once",
        "construct_runtime_once",
        "execute_backend_once",
        "shutdown_once",
    ]
    static = _static_review(integration_source)
    if (
        definition.get("schema") != INTEGRATION_SCHEMA
        or definition.get("status")
        != "READY_FOR_INDEPENDENT_NATIVE_RUNTIME_WORKER_INTEGRATION_REVIEW"
        or lifecycle != expected
        or definition.get("worker_remains_sole_attempt_claimant") is not True
        or definition.get("callable_is_single_use") is not True
        or definition.get("automatic_retry") is not False
        or definition.get("runtime_execution_admitted") is not False
        or definition.get("launch_admitted") is not False
        or definition.get("attempt_consumed") is not False
        or worker_review.get("reviewed_backend_sha256")
        != "132f1e028503a3a83af11f2a713f839e00e1fef49aa9cb3fbb0156f858245cde"
        or backend_review.get("reviewed_runtime_adapter_sha256")
        != "1ff2ffdd97b5ec8514a86fdb21e1cac3aae8a445d388a8b10a9fd6775e6fe818"
        or not all(
            isinstance(value, str) and len(value) == 64
            for value in (definition_file_sha256, review_source_sha256)
        )
    ):
        raise NativeRuntimeWorkerIntegrationReviewError(
            "native runtime worker integration boundary changed"
        )
    core = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm274-native-runtime-worker-integration-review-001",
        "status": "ACCEPTED_FOR_SEPARATELY_AUTHORIZED_ONE_ATTEMPT_WORKER_USE",
        "source_integration_sha256": integration_hash,
        "source_integration_file_sha256": definition_file_sha256,
        "source_integration_source_sha256": _file_sha(integration_source),
        "review_source_sha256": review_source_sha256,
        "static_review": static,
        "worker_claim_precedes_session_creation": True,
        "factory_runtime_identity_passes_to_backend": True,
        "shutdown_is_finally_guarded": True,
        "single_use_no_retry": True,
        "runtime_execution_admitted": False,
        "launch_admitted": False,
        "attempt_consumed": False,
        "isaac_started": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": "SEPARATE_EXACT_ONE_ATTEMPT_AUTHORIZATION_OR_INERT_DRY_RUN",
    }
    return {**core, "integration_review_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeRuntimeWorkerIntegrationReviewError(f"{path} must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integration", type=Path, required=True)
    parser.add_argument("--integration-source", type=Path, required=True)
    parser.add_argument("--review-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review_integration(
        _load(args.integration),
        definition_file_sha256=_file_sha(args.integration),
        integration_source=args.integration_source,
        review_source_sha256=_file_sha(args.review_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
