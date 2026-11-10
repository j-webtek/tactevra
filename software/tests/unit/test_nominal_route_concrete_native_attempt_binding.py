from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
SOURCE = INTEGRATION / "nominal_route_concrete_native_attempt_binding.py"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))
SPEC = importlib.util.spec_from_file_location("arm278_binding", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

worker_integration = sys.modules["nominal_route_native_runtime_worker_integration"]


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(json.dumps(value), encoding="utf-8")


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _paths(tmp_path: Path, monkeypatch):
    artifact_root = tmp_path / "artifacts"
    repo_root = tmp_path / "repo"
    paths = MODULE.BindingPaths(
        artifact_root=artifact_root,
        repo_root=repo_root,
        governed_attempt_directory=tmp_path / "governed-attempt",
    )
    _write(paths.robot_usd, b"pinned robot")
    _write(paths.layout, {})
    _write(paths.route, {})
    _write(paths.mechanics, {})
    for name, path in (
        ("EXPECTED_ROBOT_USD_SHA256", paths.robot_usd),
        ("EXPECTED_LAYOUT_SHA256", paths.layout),
        ("EXPECTED_ROUTE_SHA256", paths.route),
        ("EXPECTED_MECHANICS_SHA256", paths.mechanics),
    ):
        monkeypatch.setattr(MODULE, name, _sha(path))

    settle_path = (
        artifact_root / "arm277-concrete-native-session-settle-001/receipt.json"
    )
    _write(
        settle_path,
        {
            "schema": MODULE.SETTLE_SCHEMA,
            "status": "PASS_CONCRETE_NATIVE_SESSION_BOUNDED_SETTLE",
            "physics_steps": 30,
            "attempt_consumed": False,
            "trajectory_playback": False,
            "joint_targets_submitted": False,
            "hardware_access": False,
            "physical_authority": False,
        },
    )
    monkeypatch.setattr(MODULE, "EXPECTED_SETTLE_RECEIPT_SHA256", _sha(settle_path))

    integration_core = {
        "schema": worker_integration.INTEGRATION_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_NATIVE_RUNTIME_WORKER_INTEGRATION_REVIEW",
        "worker_remains_sole_attempt_claimant": True,
        "callable_is_single_use": True,
        "automatic_retry": False,
        "runtime_execution_admitted": False,
        "launch_admitted": False,
        "backend_review": {},
    }
    integration = {
        **integration_core,
        "integration_sha256": worker_integration._sha(integration_core),
    }
    files = {
        "arm274-native-runtime-worker-integration-001/integration.json": integration,
        "arm255-nominal-route-physics-backend-001/backend.json": {},
        "arm272-native-runtime-factory-001/factory.json": {},
        "arm272-native-runtime-factory-review-001/review.json": {},
        "arm271-native-runtime-construction-plan-002/plan.json": {},
        "arm271-native-runtime-construction-plan-review-002/review.json": {},
        "arm265-native-clearance-adapter-001/adapter.json": {},
        "arm265-native-clearance-adapter-review-001/review.json": {},
        "arm262-native-sweep-binding-003/binding.json": {},
        "arm263-native-sweep-binding-review-001/review.json": {},
        "arm267-canonical-ik-row-adapter-001/adapter.json": {},
        "arm267-canonical-ik-row-adapter-review-001/review.json": {},
        "arm268-tool-key-metrics-adapter-002/adapter.json": {},
        "arm268-tool-key-metrics-adapter-review-002/review.json": {},
        "arm269-root-drift-adapter-001/adapter.json": {},
        "arm269-root-drift-adapter-review-001/review.json": {},
        "arm270-complete-runtime-composition-001/composition.json": {},
        "arm270-complete-runtime-composition-review-001/review.json": {},
    }
    for relative, value in files.items():
        _write(artifact_root / relative, value)
    monkeypatch.setattr(
        MODULE,
        "EXPECTED_DEPENDENCY_SHA256",
        {relative: _sha(artifact_root / relative) for relative in files},
    )
    return paths


def test_arm278_builds_deferred_single_attempt_binding_without_session(
    tmp_path, monkeypatch
):
    calls = []

    class Session:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

    binding = MODULE.build_concrete_native_attempt_binding(
        _paths(tmp_path, monkeypatch), session_type=Session
    )
    assert calls == []
    assert binding.receipt["backend_constructed"] is True
    assert binding.receipt["session_factory_deferred"] is True
    assert binding.receipt["session_creations"] == 0
    assert binding.receipt["attempt_consumed"] is False
    assert binding.receipt["physics_steps"] == 0
    assert binding.receipt["hardware_access"] is False
    assert binding.receipt["physical_authority"] is False
    assert (
        binding.receipt["required_authorization_statement"]
        == MODULE.EXACT_AUTHORIZATION
    )


def test_arm278_refuses_existing_governed_attempt(tmp_path, monkeypatch):
    paths = _paths(tmp_path, monkeypatch)
    paths.governed_attempt_directory.mkdir()
    with pytest.raises(
        MODULE.ConcreteNativeAttemptBindingError, match="already exists"
    ):
        MODULE.build_concrete_native_attempt_binding(paths)


def test_arm278_refuses_changed_pinned_input(tmp_path, monkeypatch):
    paths = _paths(tmp_path, monkeypatch)
    monkeypatch.setattr(MODULE, "EXPECTED_LAYOUT_SHA256", "0" * 64)
    with pytest.raises(MODULE.ConcreteNativeAttemptBindingError, match="pinned input"):
        MODULE.build_concrete_native_attempt_binding(paths)


def test_arm278_source_contains_no_execution_or_hardware_authority():
    source = SOURCE.read_text(encoding="utf-8")
    assert "run_one_attempt(" not in source
    assert ".set_joint_position" not in source
    assert ".set_joint_position_target" not in source
    assert "serial.Serial" not in source
    assert "\n    session_factory()" not in source
