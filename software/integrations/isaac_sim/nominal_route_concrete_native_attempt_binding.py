"""Bind the proven concrete Isaac session to the governed one-attempt backend.

ARM-278 is deliberately a preflight.  It validates the retained ARM-277 settle
evidence and all reviewed runtime inputs, then constructs a deferred callable.
It does not create an Isaac session, claim the governed attempt, step physics,
or invoke the backend.  ARM-254 remains the only attempt claimant.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from nominal_route_concrete_native_session_smoke import SCHEMA as SETTLE_SCHEMA
from nominal_route_native_root_path_correction import (
    CorrectedRootRuntimeFactory,
    corrected_native_metadata,
)
from nominal_route_native_runtime_factory import construct_runtime
from nominal_route_native_runtime_worker_integration import OneAttemptNativeBackend
from nominal_route_native_session_smoke import IsaacInertSmokeDriver
from nominal_route_physics_backend import execute_backend
from nominal_route_physics_worker import EXACT_AUTHORIZATION


SCHEMA = "tactevra.isaac_lm4_concrete_native_attempt_binding.v1"
EXPECTED_SETTLE_RECEIPT_SHA256 = (
    "533b1b9afea6f641fb61aa34f7955af7b2af4c63ab061a4cfea4ca33d7f704af"
)
EXPECTED_ROBOT_USD_SHA256 = (
    "a0ec437fb4d647f354007dc352a3af8b13576eaf4931d69d60a510bf235ebea2"
)
EXPECTED_LAYOUT_SHA256 = (
    "6779213e832ab27eeda1e7fb245f57ff8cb0d56707b5aa73a8f31ec483a620f2"
)
EXPECTED_ROUTE_SHA256 = (
    "d22fffa61b4d481e8c90956828c3c2a58634e9408108f00a2521501e331c0449"
)
EXPECTED_MECHANICS_SHA256 = (
    "768829bc8c131efe41e8866b6a18900a24b3f77e2ef97b367b55cffbfcf9881a"
)
EXPECTED_DEPENDENCY_SHA256 = {
    "arm274-native-runtime-worker-integration-001/integration.json": "fb1c6de09b3c56dae645d8df57885b58776beced2ea233edd800c71aa185b882",
    "arm255-nominal-route-physics-backend-001/backend.json": "968140c9b075cc4f6a8d5599edc765cd1b6cde734e32e6632513bd2c94fb6228",
    "arm272-native-runtime-factory-001/factory.json": "6572a0a9166106c0321349ef4b8276154f06ab775ec478a941869e6b5c7ce854",
    "arm272-native-runtime-factory-review-001/review.json": "0418f5c0e6d4e9fe35de36be68a9f46a05dbccb2ba4ea0f15231a8828542aca0",
    "arm271-native-runtime-construction-plan-002/plan.json": "a912687cf0b2e1595d4c6de7b038ce5c17d11056a23f3648d1d3ae2ad8f56b25",
    "arm271-native-runtime-construction-plan-review-002/review.json": "f5b7bc5cdaf0e8728ee213415e614ea4fe176c8770a92a4e577607d5eb12ccce",
    "arm265-native-clearance-adapter-001/adapter.json": "b5e8891053531cd799e6367b4ff24140c268757e4a57a3a19691fc48d1e76df4",
    "arm265-native-clearance-adapter-review-001/review.json": "1ababaac40fc50840f31aa921e3d3b00514cb4416e6c92190bc51095b4381b13",
    "arm262-native-sweep-binding-003/binding.json": "e620ae81b082a6a1ce957af4b2419464a6d87f5c5c790cf99bc0f8987448c3da",
    "arm263-native-sweep-binding-review-001/review.json": "b13a1de38086c865040b81e49045ec3405b6d1b9c12876bec7a3fe45416d7620",
    "arm267-canonical-ik-row-adapter-001/adapter.json": "b3e799c4964bec898772730502f3c81cf22f9e0ded7447f76d21b6a284786f1a",
    "arm267-canonical-ik-row-adapter-review-001/review.json": "cb61e4005777e0f75556fb238b18608be029375da2b4b11a1be75b0da74fe42f",
    "arm268-tool-key-metrics-adapter-002/adapter.json": "e4b059e0fc78343eda7959c2e97ac66565db93fe859e8a0dc0e5591eee8e41da",
    "arm268-tool-key-metrics-adapter-review-002/review.json": "3077bc83c25f8cd491ace003469e6add6d275a8de79894a70f8344a2256167a7",
    "arm269-root-drift-adapter-001/adapter.json": "8c5ed1c2313c3dd5f906f35b1b1ba1028884eb8471c92cc8218fd647f509d25c",
    "arm269-root-drift-adapter-review-001/review.json": "8490cb9d97a2d13a38181e863d915373ee626bf5e0418212e1f314026e735480",
    "arm270-complete-runtime-composition-001/composition.json": "7d091f477dc1986b505693cbf8faed0d27cebd605860520f29e3535f6b15aa32",
    "arm270-complete-runtime-composition-review-001/review.json": "5657126f17c4415caed380e5aaf5194f985f8a93c1423764a3cfd471acb95645",
}


class ConcreteNativeAttemptBindingError(ValueError):
    """Raised when retained evidence or the deferred authority boundary changes."""


@dataclass(frozen=True)
class BindingPaths:
    artifact_root: Path
    repo_root: Path
    governed_attempt_directory: Path

    @property
    def robot_usd(self) -> Path:
        return (
            self.artifact_root
            / "wp1-import-003/roarm_m3_kinematic_40dbd84/roarm_m3_kinematic_40dbd84.usda"
        )

    @property
    def layout(self) -> Path:
        return self.repo_root / "software/config/nominal_target_profiles.json"

    @property
    def route(self) -> Path:
        return (
            self.artifact_root
            / "arm231-state-policy-fixed-fixture-correction-001/episode-ef340d0ad2740c118d87/native_mechanics_plan.json"
        )

    @property
    def mechanics(self) -> Path:
        return self.repo_root / "software/config/isaac_lm0b_geometry_prior_profile.json"


@dataclass(frozen=True)
class ConcreteNativeAttemptBinding:
    backend: OneAttemptNativeBackend
    receipt: Mapping[str, Any]


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ConcreteNativeAttemptBindingError(
            f"required input unavailable: {path}"
        ) from exc


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ConcreteNativeAttemptBindingError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise ConcreteNativeAttemptBindingError(
            f"required JSON is not an object: {path}"
        )
    return value


def _artifact(paths: BindingPaths, directory: str, filename: str) -> Path:
    return paths.artifact_root / directory / filename


def _load_runtime_documents(paths: BindingPaths) -> dict[str, dict[str, Any]]:
    locations = {
        "clearance_definition": ("arm265-native-clearance-adapter-001", "adapter.json"),
        "clearance_review": (
            "arm265-native-clearance-adapter-review-001",
            "review.json",
        ),
        "binding_definition": ("arm262-native-sweep-binding-003", "binding.json"),
        "binding_review": ("arm263-native-sweep-binding-review-001", "review.json"),
        "ik_definition": ("arm267-canonical-ik-row-adapter-001", "adapter.json"),
        "ik_review": ("arm267-canonical-ik-row-adapter-review-001", "review.json"),
        "metrics_definition": ("arm268-tool-key-metrics-adapter-002", "adapter.json"),
        "metrics_review": ("arm268-tool-key-metrics-adapter-review-002", "review.json"),
        "drift_definition": ("arm269-root-drift-adapter-001", "adapter.json"),
        "drift_review": ("arm269-root-drift-adapter-review-001", "review.json"),
        "composition_definition": (
            "arm270-complete-runtime-composition-001",
            "composition.json",
        ),
        "composition_review": (
            "arm270-complete-runtime-composition-review-001",
            "review.json",
        ),
    }
    return {
        name: _load(_artifact(paths, directory, filename))
        for name, (directory, filename) in locations.items()
    }


def build_concrete_native_attempt_binding(
    paths: BindingPaths,
    *,
    session_type: Callable[..., Any] = IsaacInertSmokeDriver,
    runtime_factory: Callable[..., Any] = construct_runtime,
    backend_executor: Callable[..., Mapping[str, Any]] = execute_backend,
) -> ConcreteNativeAttemptBinding:
    """Construct the deferred backend without creating a session or an attempt."""
    if paths.governed_attempt_directory.exists():
        raise ConcreteNativeAttemptBindingError(
            "governed attempt directory already exists; binding refused"
        )
    pinned = {
        paths.robot_usd: EXPECTED_ROBOT_USD_SHA256,
        paths.layout: EXPECTED_LAYOUT_SHA256,
        paths.route: EXPECTED_ROUTE_SHA256,
        paths.mechanics: EXPECTED_MECHANICS_SHA256,
    }
    for path, expected in pinned.items():
        if _file_sha(path) != expected:
            raise ConcreteNativeAttemptBindingError(f"pinned input changed: {path}")
    for relative, expected in EXPECTED_DEPENDENCY_SHA256.items():
        path = paths.artifact_root / relative
        if _file_sha(path) != expected:
            raise ConcreteNativeAttemptBindingError(
                f"reviewed dependency changed: {path}"
            )

    settle_path = _artifact(
        paths, "arm277-concrete-native-session-settle-001", "receipt.json"
    )
    settle = _load(settle_path)
    if (
        _file_sha(settle_path) != EXPECTED_SETTLE_RECEIPT_SHA256
        or settle.get("schema") != SETTLE_SCHEMA
        or settle.get("status") != "PASS_CONCRETE_NATIVE_SESSION_BOUNDED_SETTLE"
        or settle.get("physics_steps") != 30
        or settle.get("attempt_consumed") is not False
        or settle.get("trajectory_playback") is not False
        or settle.get("joint_targets_submitted") is not False
        or settle.get("hardware_access") is not False
        or settle.get("physical_authority") is not False
    ):
        raise ConcreteNativeAttemptBindingError("ARM-277 settle evidence changed")

    integration = _load(
        _artifact(
            paths, "arm274-native-runtime-worker-integration-001", "integration.json"
        )
    )
    backend_definition = _load(
        _artifact(paths, "arm255-nominal-route-physics-backend-001", "backend.json")
    )
    factory_definition = _load(
        _artifact(paths, "arm272-native-runtime-factory-001", "factory.json")
    )
    factory_review = _load(
        _artifact(paths, "arm272-native-runtime-factory-review-001", "review.json")
    )
    factory_plan = _load(
        _artifact(paths, "arm271-native-runtime-construction-plan-002", "plan.json")
    )
    factory_plan_review = _load(
        _artifact(
            paths, "arm271-native-runtime-construction-plan-review-002", "review.json"
        )
    )
    route = _load(paths.route)
    documents = _load_runtime_documents(paths)
    corrected_factory = CorrectedRootRuntimeFactory(runtime_factory)
    session_creations = 0

    def session_factory() -> Any:
        nonlocal session_creations
        session_creations += 1
        if session_creations != 1:
            raise ConcreteNativeAttemptBindingError("session factory retry refused")
        return session_type(
            paths.robot_usd,
            paths.layout,
            paths.route,
            mechanics_profile=paths.mechanics,
        )

    backend = OneAttemptNativeBackend(
        integration,
        session_factory=session_factory,
        construct_runtime_fn=corrected_factory,
        execute_backend_fn=backend_executor,
        backend_definition=backend_definition,
        route=route,
        factory_definition=factory_definition,
        factory_review=factory_review,
        factory_plan=factory_plan,
        factory_plan_review=factory_plan_review,
        documents=documents,
        solver_kwargs={},
        native_metadata=corrected_native_metadata(),
    )
    receipt = {
        "schema": SCHEMA,
        "status": "READY_FOR_EXACT_SEPARATELY_AUTHORIZED_ARM253_ATTEMPT",
        "binding_id": "arm278-concrete-native-attempt-binding-001",
        "source_settle_receipt_sha256": EXPECTED_SETTLE_RECEIPT_SHA256,
        "source_files_sha256": {
            "robot_usd": EXPECTED_ROBOT_USD_SHA256,
            "layout": EXPECTED_LAYOUT_SHA256,
            "route": EXPECTED_ROUTE_SHA256,
            "mechanics_profile": EXPECTED_MECHANICS_SHA256,
        },
        "reviewed_dependencies_sha256": dict(EXPECTED_DEPENDENCY_SHA256),
        "governed_attempt_directory": str(paths.governed_attempt_directory),
        "required_authorization_statement": EXACT_AUTHORIZATION,
        "worker_remains_sole_attempt_claimant": True,
        "backend_constructed": True,
        "session_factory_deferred": True,
        "session_creations": session_creations,
        "root_metadata_correction_bound": True,
        "attempt_consumed": False,
        "isaac_started": False,
        "scene_loaded": False,
        "physics_steps": 0,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "key_contact": False,
        "automatic_retry": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
    }
    return ConcreteNativeAttemptBinding(backend=backend, receipt=receipt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--governed-attempt-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    if args.output_directory.exists():
        raise ConcreteNativeAttemptBindingError("binding output exists; retry refused")
    binding = build_concrete_native_attempt_binding(
        BindingPaths(
            artifact_root=args.artifact_root,
            repo_root=args.repo_root,
            governed_attempt_directory=args.governed_attempt_directory,
        )
    )
    args.output_directory.mkdir(parents=True, exist_ok=False)
    receipt = dict(binding.receipt)
    receipt["binding_id"] = args.output_directory.name
    (args.output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
