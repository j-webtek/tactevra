from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
LAUNCH_SOURCE = INTEGRATION / "nominal_route_arm297_launch.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_arm297_launch_review.py"


def _load(name: str, path: Path):
    if str(INTEGRATION) not in sys.path:
        sys.path.insert(0, str(INTEGRATION))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LAUNCH = _load("arm297_launch", LAUNCH_SOURCE)
REVIEW = _load("arm297_launch_review", REVIEW_SOURCE)


def _write_json(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return LAUNCH._file_sha(path)


def _fixture(tmp_path: Path, monkeypatch):
    interpreter = tmp_path / "qualified" / "python.exe"
    interpreter.parent.mkdir()
    interpreter.write_bytes(b"qualified interpreter")
    interpreter_sha = LAUNCH._file_sha(interpreter)
    governed = tmp_path / "governed"
    attempt = governed / "attempt"
    eula = tmp_path / "eula-output" / "receipt.json"
    memory = tmp_path / "memory-output" / "receipt.json"
    claimant_path = tmp_path / "inputs" / "claimant.json"
    claimant_review_path = tmp_path / "inputs" / "claimant-review.json"
    claimant_file_sha = _write_json(claimant_path, {"kind": "claimant"})
    claimant_review_file_sha = _write_json(
        claimant_review_path, {"kind": "claimant-review"}
    )
    runtime = {key: str(index).zfill(64) for index, key in enumerate(LAUNCH.RUNTIME_SOURCE_FILES, 1)}
    commit = "a" * 40
    binding_core = {
        "schema": LAUNCH.BINDING_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_ARM297_LAUNCH_BINDING_REVIEW",
        "required_authorization_statement": LAUNCH.EXACT_AUTHORIZATION,
        "qualified_interpreter": {
            "path": str(interpreter),
            "file_sha256": interpreter_sha,
        },
        "repository_commit": commit,
        "source_claimant_file_sha256": claimant_file_sha,
        "source_claimant_review_file_sha256": claimant_review_file_sha,
        "runtime_sources_sha256": runtime,
        "proposed_output_directory": str(attempt),
        "fresh_eula_receipt": str(eula),
        "fresh_memory_receipt": str(memory),
        **LAUNCH.ZERO_AUTHORITY,
        "launch_admitted": False,
    }
    binding = {
        **binding_core,
        "launch_binding_sha256": LAUNCH._sha(binding_core),
    }
    binding_path = tmp_path / "inputs" / "binding.json"
    binding_file_sha = _write_json(binding_path, binding)
    binding_review_core = {
        "schema": LAUNCH.BINDING_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ARM297_LAUNCHER_IMPLEMENTATION",
        "source_launch_binding_sha256": binding["launch_binding_sha256"],
        "source_launch_binding_file_sha256": binding_file_sha,
        "required_authorization_statement": LAUNCH.EXACT_AUTHORIZATION,
        **LAUNCH.ZERO_AUTHORITY,
        "launch_admitted": False,
    }
    binding_review = {
        **binding_review_core,
        "launch_binding_review_sha256": LAUNCH._sha(binding_review_core),
    }
    binding_review_path = tmp_path / "inputs" / "binding-review.json"
    binding_review_file_sha = _write_json(
        binding_review_path, binding_review
    )
    launcher_review_core = {
        "schema": LAUNCH.LAUNCHER_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_EXACT_ARM297_ONE_ATTEMPT_AUTHORIZATION",
        "source_launcher_file_sha256": LAUNCH._file_sha(LAUNCH_SOURCE),
        "source_launch_binding_sha256": binding["launch_binding_sha256"],
        "source_launch_binding_review_sha256": binding_review[
            "launch_binding_review_sha256"
        ],
        "required_authorization_statement": LAUNCH.EXACT_AUTHORIZATION,
        "single_claimant_delegation": True,
        "fresh_gates_owned_by_claimant": True,
        "terminalization_owned_by_worker": True,
        "automatic_retry_refused": True,
        **LAUNCH.ZERO_AUTHORITY,
        "launch_admitted": False,
    }
    launcher_review = {
        **launcher_review_core,
        "launcher_review_sha256": LAUNCH._sha(launcher_review_core),
    }
    launcher_review_path = tmp_path / "inputs" / "launcher-review.json"
    _write_json(launcher_review_path, launcher_review)
    monkeypatch.setattr(LAUNCH, "EXPECTED_BINDING_SHA256", binding["launch_binding_sha256"])
    monkeypatch.setattr(LAUNCH, "EXPECTED_BINDING_FILE_SHA256", binding_file_sha)
    monkeypatch.setattr(
        LAUNCH,
        "EXPECTED_BINDING_REVIEW_SHA256",
        binding_review["launch_binding_review_sha256"],
    )
    monkeypatch.setattr(
        LAUNCH, "EXPECTED_BINDING_REVIEW_FILE_SHA256", binding_review_file_sha
    )
    monkeypatch.setattr(LAUNCH, "_runtime_source_hashes", lambda _: runtime)
    monkeypatch.setattr(LAUNCH, "_worker_source_hashes", lambda *_: {"worker": "b" * 64})
    monkeypatch.setattr(LAUNCH, "_runtime_binding_hashes", lambda *_: {"binding": "c" * 64})
    return SimpleNamespace(
        interpreter=interpreter,
        interpreter_sha=interpreter_sha,
        commit=commit,
        governed=governed,
        attempt=attempt,
        eula=eula,
        memory=memory,
        claimant_path=claimant_path,
        claimant_review_path=claimant_review_path,
        claimant_file_sha=claimant_file_sha,
        claimant_review_file_sha=claimant_review_file_sha,
        binding=binding,
        binding_path=binding_path,
        binding_file_sha=binding_file_sha,
        binding_review=binding_review,
        binding_review_path=binding_review_path,
        binding_review_file_sha=binding_review_file_sha,
        launcher_review=launcher_review,
        launcher_review_path=launcher_review_path,
        runtime=runtime,
    )


def test_import_is_inert_and_standalone_source_root_is_bound():
    assert LAUNCH.RUNTIME_SOURCE_FILES["physics_worker"] == "nominal_route_physics_worker.py"
    probe = (
        "import importlib.util; "
        f"p=r'{LAUNCH_SOURCE}'; "
        "s=importlib.util.spec_from_file_location('arm297_standalone', p); "
        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        "import rocell; print(rocell.__file__)"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert str(ROOT / "software/src/rocell") in completed.stdout


def test_exact_entry_delegates_once_after_all_revalidation(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, monkeypatch)
    calls = []

    def build(paths):
        calls.append(("build", paths))
        return SimpleNamespace(backend="deferred-backend")

    class Claimant:
        def __init__(self, definition, review):
            calls.append(("construct", definition, review))

        def run(self, **kwargs):
            calls.append(("run", kwargs))
            return {"status": "terminal"}

    result = LAUNCH.run_authorized_attempt(
        authorization_statement=LAUNCH.EXACT_AUTHORIZATION,
        claimant_path=fixture.claimant_path,
        claimant_review_path=fixture.claimant_review_path,
        launch_binding_path=fixture.binding_path,
        launch_binding_review_path=fixture.binding_review_path,
        launcher_review_path=fixture.launcher_review_path,
        launcher_source_path=LAUNCH_SOURCE,
        artifact_root=tmp_path / "artifact-root",
        repo_root=tmp_path / "repo-root",
        actual_interpreter=fixture.interpreter,
        claimant_type=Claimant,
        binding_builder=build,
        commit_checker=lambda root, commit: commit == fixture.commit,
    )

    assert result == {"status": "terminal"}
    assert [row[0] for row in calls] == ["build", "construct", "run"]
    run = calls[-1][1]
    assert run["authorization_statement"] == LAUNCH.EXACT_AUTHORIZATION
    assert run["output_directory"] == fixture.attempt
    assert run["fresh_eula_receipt"] == fixture.eula
    assert run["fresh_memory_receipt"] == fixture.memory
    assert run["current_runtime_sources_sha256"] == fixture.runtime
    assert run["current_source_files_sha256"] == {"worker": "b" * 64}
    assert run["current_runtime_bindings_sha256"] == {"binding": "c" * 64}
    assert run["backend"] == "deferred-backend"


def test_wrong_authorization_stops_before_backend(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, monkeypatch)
    calls = []
    with pytest.raises(LAUNCH.Arm297LaunchError, match="exact fresh"):
        LAUNCH.run_authorized_attempt(
            authorization_statement="old ARM-295 authorization",
            claimant_path=fixture.claimant_path,
            claimant_review_path=fixture.claimant_review_path,
            launch_binding_path=fixture.binding_path,
            launch_binding_review_path=fixture.binding_review_path,
            launcher_review_path=fixture.launcher_review_path,
            launcher_source_path=LAUNCH_SOURCE,
            artifact_root=tmp_path,
            repo_root=tmp_path,
            actual_interpreter=fixture.interpreter,
            binding_builder=lambda paths: calls.append(paths),
        )
    assert calls == []


def test_interpreter_ancestry_and_existing_output_fail_before_backend(
    tmp_path, monkeypatch
):
    fixture = _fixture(tmp_path, monkeypatch)
    other = tmp_path / "other-python.exe"
    other.write_bytes(b"other")
    with pytest.raises(LAUNCH.Arm297LaunchError, match="exact qualified"):
        LAUNCH.run_authorized_attempt(
            authorization_statement=LAUNCH.EXACT_AUTHORIZATION,
            claimant_path=fixture.claimant_path,
            claimant_review_path=fixture.claimant_review_path,
            launch_binding_path=fixture.binding_path,
            launch_binding_review_path=fixture.binding_review_path,
            launcher_review_path=fixture.launcher_review_path,
            launcher_source_path=LAUNCH_SOURCE,
            artifact_root=tmp_path,
            repo_root=tmp_path,
            actual_interpreter=other,
        )
    with pytest.raises(LAUNCH.Arm297LaunchError, match="current ancestry"):
        LAUNCH.run_authorized_attempt(
            authorization_statement=LAUNCH.EXACT_AUTHORIZATION,
            claimant_path=fixture.claimant_path,
            claimant_review_path=fixture.claimant_review_path,
            launch_binding_path=fixture.binding_path,
            launch_binding_review_path=fixture.binding_review_path,
            launcher_review_path=fixture.launcher_review_path,
            launcher_source_path=LAUNCH_SOURCE,
            artifact_root=tmp_path,
            repo_root=tmp_path,
            actual_interpreter=fixture.interpreter,
            commit_checker=lambda *_: False,
        )
    fixture.attempt.mkdir(parents=True)
    calls = []
    with pytest.raises(LAUNCH.Arm297LaunchError, match="not fresh"):
        LAUNCH.run_authorized_attempt(
            authorization_statement=LAUNCH.EXACT_AUTHORIZATION,
            claimant_path=fixture.claimant_path,
            claimant_review_path=fixture.claimant_review_path,
            launch_binding_path=fixture.binding_path,
            launch_binding_review_path=fixture.binding_review_path,
            launcher_review_path=fixture.launcher_review_path,
            launcher_source_path=LAUNCH_SOURCE,
            artifact_root=tmp_path,
            repo_root=tmp_path,
            actual_interpreter=fixture.interpreter,
            commit_checker=lambda *_: True,
            binding_builder=lambda paths: calls.append(paths),
        )
    assert calls == []


def test_changed_launcher_review_fails_closed(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, monkeypatch)
    changed = dict(fixture.launcher_review)
    changed["single_claimant_delegation"] = False
    core = dict(changed)
    core.pop("launcher_review_sha256")
    changed["launcher_review_sha256"] = LAUNCH._sha(core)
    _write_json(fixture.launcher_review_path, changed)
    with pytest.raises(LAUNCH.Arm297LaunchError, match="launcher review"):
        LAUNCH.run_authorized_attempt(
            authorization_statement=LAUNCH.EXACT_AUTHORIZATION,
            claimant_path=fixture.claimant_path,
            claimant_review_path=fixture.claimant_review_path,
            launch_binding_path=fixture.binding_path,
            launch_binding_review_path=fixture.binding_review_path,
            launcher_review_path=fixture.launcher_review_path,
            launcher_source_path=LAUNCH_SOURCE,
            artifact_root=tmp_path,
            repo_root=tmp_path,
            actual_interpreter=fixture.interpreter,
            commit_checker=lambda *_: True,
        )


def test_independent_static_review_accepts_launcher_and_rejects_retry_loop():
    accepted = REVIEW._static_review(LAUNCH_SOURCE.read_bytes())
    assert accepted["single_claimant_run_call"] is True
    assert accepted["retry_loop_absent"] is True
    with pytest.raises(REVIEW.Arm297LauncherReviewError, match="retry-capable loop"):
        REVIEW._static_review(
            LAUNCH_SOURCE.read_bytes().replace(
                b"    if authorization_statement != EXACT_AUTHORIZATION:\n",
                b"    while False:\n        pass\n    if authorization_statement != EXACT_AUTHORIZATION:\n",
                1,
            )
        )


def test_independent_review_materializes_zero_authority_receipt(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, monkeypatch)
    fixture.attempt.parent.mkdir(parents=True)
    monkeypatch.setattr(
        REVIEW,
        "EXPECTED_BINDING_SHA256",
        fixture.binding["launch_binding_sha256"],
    )
    monkeypatch.setattr(REVIEW, "EXPECTED_BINDING_FILE_SHA256", fixture.binding_file_sha)
    monkeypatch.setattr(
        REVIEW,
        "EXPECTED_BINDING_REVIEW_SHA256",
        fixture.binding_review["launch_binding_review_sha256"],
    )
    monkeypatch.setattr(
        REVIEW,
        "EXPECTED_BINDING_REVIEW_FILE_SHA256",
        fixture.binding_review_file_sha,
    )
    monkeypatch.setattr(REVIEW, "_is_ancestor", lambda *_: True)
    receipt = REVIEW.review_launcher(
        fixture.binding,
        fixture.binding_review,
        binding_file_sha256=fixture.binding_file_sha,
        binding_review_file_sha256=fixture.binding_review_file_sha,
        launcher_source_bytes=LAUNCH_SOURCE.read_bytes(),
        reviewer_source_file_sha256=REVIEW._file_sha(REVIEW_SOURCE),
        claimant_file_sha256=fixture.claimant_file_sha,
        claimant_review_file_sha256=fixture.claimant_review_file_sha,
        interpreter_file_sha256=fixture.interpreter_sha,
        runtime_source_files_sha256=fixture.runtime,
        repo_root=tmp_path,
    )
    assert receipt["status"] == "ACCEPTED_FOR_EXACT_ARM297_ONE_ATTEMPT_AUTHORIZATION"
    assert receipt["attempt_claimed"] is False
    assert receipt["launch_admitted"] is False
    assert receipt["physics_steps"] == 0
