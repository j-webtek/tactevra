"""Bind the reviewed worker, backend, and native runtime factory without launch.

ARM-274 is import-safe.  Building the definition and backend callable starts no
simulator and claims no attempt.  The returned callable is intended to be
injected into ARM-254, which remains the sole attempt-directory claimant.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


INTEGRATION_SCHEMA = "tactevra.isaac_lm4_native_runtime_worker_integration.v1"
PLAN_SCHEMA = "tactevra.isaac_lm4_native_runtime_worker_integration_plan.v1"
PLAN_REVIEW_SCHEMA = (
    "tactevra.isaac_lm4_native_runtime_worker_integration_plan_review.v1"
)
WORKER_REVIEW_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_worker_review.v1"
BACKEND_REVIEW_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_backend_review.v1"
EXPECTED_PLAN_SHA256 = (
    "aa779b19778ef40daacf8f5c0f62ca2aaccf2e27c1b3643d2a3a70d5f7981576"
)
EXPECTED_PLAN_REVIEW_SHA256 = (
    "6d7056068f822ffc4b0b9e8ca7ae85d24a789ca6a5c27ba43b63ceb4e4ebd5be"
)
EXPECTED_PLAN_FILE_SHA256 = (
    "945fa5bb7cdefd453a6cd880be7ac1aa995224769aeb3a31c0e158800ba45cfa"
)
EXPECTED_PLAN_REVIEW_FILE_SHA256 = (
    "e026d58361b84535c0c3553d6d5de824696aeda6e1670dd5d279297d19f8a3f2"
)
EXPECTED_PLAN_SOURCE_SHA256 = (
    "85ef93b122f6517f10d21a02253dd5568b96cc656a3b3a56b2ee264eb6524b04"
)
EXPECTED_PLAN_REVIEW_SOURCE_SHA256 = (
    "407642c5e2e6c2b5da355235b439f0cb14b8b2e5f038d3cefccd9e144e83928d"
)
EXPECTED_WORKER_SHA256 = (
    "f1fb3eaeb23f2dd70a6c29b2dd13e50b6390b9b0bbaadf64b5aaeff84ba142f7"
)
EXPECTED_BACKEND_SHA256 = (
    "132f1e028503a3a83af11f2a713f839e00e1fef49aa9cb3fbb0156f858245cde"
)
EXPECTED_FACTORY_SHA256 = (
    "1ff2ffdd97b5ec8514a86fdb21e1cac3aae8a445d388a8b10a9fd6775e6fe818"
)


class NativeRuntimeWorkerIntegrationError(ValueError):
    """Raised when lineage, claim state, or the one-use lifecycle changes."""


class NativeSession(Protocol):
    """Minimal lifecycle supplied later by the reviewed native launcher."""

    def start_headless(self) -> None: ...
    def load_scene(self) -> None: ...
    def initialize_physics(self) -> None: ...
    def settle_scene(self) -> None: ...
    def native_objects(self) -> Mapping[str, Any]: ...
    def shutdown(self) -> None: ...


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError) as exc:
        raise NativeRuntimeWorkerIntegrationError(
            "input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeRuntimeWorkerIntegrationError(f"{label} hash changed")
    return claimed


def _zero_authority() -> dict[str, Any]:
    return {
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }


def build_integration_definition(
    plan: Mapping[str, Any],
    plan_review: Mapping[str, Any],
    *,
    plan_file_sha256: str,
    plan_review_file_sha256: str,
    plan_source_sha256: str,
    plan_review_source_sha256: str,
    integration_source_sha256: str,
) -> dict[str, Any]:
    """Materialize reviewed worker/backend inputs without admitting execution."""
    plan_hash = _require_hash(plan, "integration_plan_sha256", "ARM-273 plan")
    review_hash = _require_hash(
        plan_review, "integration_plan_review_sha256", "ARM-273 review"
    )
    sources = plan.get("source_documents_sha256", {})
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan_hash != EXPECTED_PLAN_SHA256
        or plan.get("worker_integration_implemented") is not False
        or plan_review.get("schema") != PLAN_REVIEW_SCHEMA
        or review_hash != EXPECTED_PLAN_REVIEW_SHA256
        or plan_review.get("source_plan_sha256") != plan_hash
        or plan_review.get("status")
        != "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_WORKER_INTEGRATION_IMPLEMENTATION"
        or plan_review.get("worker_review_materialization_required") is not True
        or plan_review.get("backend_review_materialization_required") is not True
        or sources.get("worker") != EXPECTED_WORKER_SHA256
        or sources.get("backend") != EXPECTED_BACKEND_SHA256
        or sources.get("factory") != EXPECTED_FACTORY_SHA256
        or plan_file_sha256 != EXPECTED_PLAN_FILE_SHA256
        or plan_review_file_sha256 != EXPECTED_PLAN_REVIEW_FILE_SHA256
        or plan_source_sha256 != EXPECTED_PLAN_SOURCE_SHA256
        or plan_review_source_sha256 != EXPECTED_PLAN_REVIEW_SOURCE_SHA256
        or not isinstance(integration_source_sha256, str)
        or len(integration_source_sha256) != 64
    ):
        raise NativeRuntimeWorkerIntegrationError("ARM-274 lineage changed")

    worker_review_core = {
        "schema": WORKER_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ONE_SEPARATELY_AUTHORIZED_SIMULATION_ATTEMPT",
        "source_worker_sha256": EXPECTED_WORKER_SHA256,
        "reviewed_backend_sha256": EXPECTED_BACKEND_SHA256,
        "launch_admitted": True,
        **_zero_authority(),
    }
    backend_review_core = {
        "schema": BACKEND_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ONE_SEPARATELY_AUTHORIZED_SIMULATION_ATTEMPT",
        "source_backend_sha256": EXPECTED_BACKEND_SHA256,
        "reviewed_runtime_adapter_sha256": EXPECTED_FACTORY_SHA256,
        "continuous_clearance_protocol_accepted": True,
        "launch_admitted": True,
        **_zero_authority(),
    }
    worker_review = {
        **worker_review_core,
        "worker_review_sha256": _sha(worker_review_core),
    }
    backend_review = {
        **backend_review_core,
        "backend_review_sha256": _sha(backend_review_core),
    }
    core = {
        "schema": INTEGRATION_SCHEMA,
        "integration_id": "arm274-zero-authority-native-runtime-worker-integration-001",
        "status": "READY_FOR_INDEPENDENT_NATIVE_RUNTIME_WORKER_INTEGRATION_REVIEW",
        "source_plan_sha256": plan_hash,
        "source_plan_review_sha256": review_hash,
        "source_files_sha256": {
            "arm273_plan": plan_file_sha256,
            "arm273_plan_review": plan_review_file_sha256,
            "arm273_plan_source": plan_source_sha256,
            "arm273_plan_review_source": plan_review_source_sha256,
            "arm274_integration_source": integration_source_sha256,
        },
        "worker_review": worker_review,
        "backend_review": backend_review,
        "lifecycle": [
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
        ],
        "worker_remains_sole_attempt_claimant": True,
        "callable_is_single_use": True,
        "automatic_retry": False,
        "worker_integration_implemented": True,
        "runtime_execution_admitted": False,
        "launch_admitted": False,
        "attempt_consumed": False,
        "isaac_started": False,
        "scene_loaded": False,
        "physics_steps": 0,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "key_contact": False,
        **_zero_authority(),
        "next_required_stage": "INDEPENDENTLY_REVIEW_NATIVE_RUNTIME_WORKER_INTEGRATION",
    }
    return {**core, "integration_sha256": _sha(core)}


class OneAttemptNativeBackend:
    """Single-use backend invoked only after ARM-254 has claimed the attempt."""

    def __init__(
        self,
        definition: Mapping[str, Any],
        *,
        session_factory: Callable[[], NativeSession],
        construct_runtime_fn: Callable[..., Any],
        execute_backend_fn: Callable[..., Mapping[str, Any]],
        backend_definition: Mapping[str, Any],
        route: Mapping[str, Any],
        factory_definition: Mapping[str, Any],
        factory_review: Mapping[str, Any],
        factory_plan: Mapping[str, Any],
        factory_plan_review: Mapping[str, Any],
        documents: Mapping[str, Mapping[str, Any]],
        solver_kwargs: Mapping[str, Any],
        native_metadata: Mapping[str, Any],
    ) -> None:
        _require_hash(definition, "integration_sha256", "ARM-274 integration")
        if (
            definition.get("schema") != INTEGRATION_SCHEMA
            or definition.get("status")
            != "READY_FOR_INDEPENDENT_NATIVE_RUNTIME_WORKER_INTEGRATION_REVIEW"
            or definition.get("worker_remains_sole_attempt_claimant") is not True
            or definition.get("callable_is_single_use") is not True
            or definition.get("automatic_retry") is not False
            or definition.get("runtime_execution_admitted") is not False
            or definition.get("launch_admitted") is not False
        ):
            raise NativeRuntimeWorkerIntegrationError("integration boundary changed")
        self._definition = definition
        self._session_factory = session_factory
        self._construct_runtime = construct_runtime_fn
        self._execute_backend = execute_backend_fn
        self._backend_definition = backend_definition
        self._route = route
        self._factory_definition = factory_definition
        self._factory_review = factory_review
        self._factory_plan = factory_plan
        self._factory_plan_review = factory_plan_review
        self._documents = documents
        self._solver_kwargs = solver_kwargs
        self._native_metadata = native_metadata
        self._used = False

    def __call__(self, output_directory: Path) -> Mapping[str, Any]:
        if self._used:
            raise NativeRuntimeWorkerIntegrationError(
                "native backend callable is single-use; retry refused"
            )
        self._used = True
        status_path = output_directory / "status.json"
        try:
            claim = json.loads(status_path.read_bytes())
        except (OSError, json.JSONDecodeError) as exc:
            raise NativeRuntimeWorkerIntegrationError(
                "worker claim must exist before session creation"
            ) from exc
        if claim != {
            "status": "ATTEMPT_CLAIMED_BACKEND_PENDING",
            "attempt_count": 1,
            "automatic_retry": False,
            "hardware_access": False,
            "physical_authority": False,
        }:
            raise NativeRuntimeWorkerIntegrationError(
                "worker claim must exist before session creation"
            )

        session = self._session_factory()
        try:
            session.start_headless()
            session.load_scene()
            session.initialize_physics()
            session.settle_scene()
            native = dict(session.native_objects())
            if set(native) != {"articulation", "scene_query", "key_view", "root_view"}:
                raise NativeRuntimeWorkerIntegrationError(
                    "native session object set changed"
                )
            runtime = self._construct_runtime(
                self._factory_definition,
                factory_review=self._factory_review,
                plan=self._factory_plan,
                plan_review=self._factory_plan_review,
                documents=self._documents,
                articulation=native["articulation"],
                scene_query=native["scene_query"],
                key_view=native["key_view"],
                root_view=native["root_view"],
                solver_kwargs=self._solver_kwargs,
                native_metadata=self._native_metadata,
            )
            return self._execute_backend(
                self._backend_definition,
                self._route,
                backend_review=self._definition["backend_review"],
                output_directory=output_directory,
                runtime=runtime,
            )
        finally:
            session.shutdown()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeRuntimeWorkerIntegrationError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-review", type=Path, required=True)
    parser.add_argument("--plan-source", type=Path, required=True)
    parser.add_argument("--plan-review-source", type=Path, required=True)
    parser.add_argument("--integration-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_integration_definition(
        _load(args.plan),
        _load(args.plan_review),
        plan_file_sha256=_file_sha(args.plan),
        plan_review_file_sha256=_file_sha(args.plan_review),
        plan_source_sha256=_file_sha(args.plan_source),
        plan_review_source_sha256=_file_sha(args.plan_review_source),
        integration_source_sha256=_file_sha(args.integration_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
