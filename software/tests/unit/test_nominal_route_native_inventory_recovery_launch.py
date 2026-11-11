from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = (
    ROOT
    / "software/integrations/isaac_sim"
    / "nominal_route_native_inventory_recovery_launch.py"
)


def _load_module():
    integration = str(SOURCE.parent)
    if integration not in sys.path:
        sys.path.insert(0, integration)
    spec = importlib.util.spec_from_file_location("arm295_launch", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


def test_import_is_inert():
    assert MODULE.RUNTIME_SOURCE_FILES["physics_worker"] == (
        "nominal_route_physics_worker.py"
    )


def test_standalone_import_binds_software_source_root():
    probe = (
        "import importlib.util; "
        f"p=r'{SOURCE}'; "
        "s=importlib.util.spec_from_file_location('arm295_standalone', p); "
        "m=importlib.util.module_from_spec(s); "
        "s.loader.exec_module(m); "
        "import rocell; "
        "print(rocell.__file__)"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert str(ROOT / "software/src/rocell") in completed.stdout


def test_qualified_interpreter_accepts_same_executable(tmp_path):
    executable = tmp_path / "python.exe"
    executable.write_bytes(b"pinned")

    MODULE._validate_qualified_interpreter(executable, executable)


def test_qualified_interpreter_rejects_other_executable(tmp_path):
    expected = tmp_path / "qualified" / "python.exe"
    actual = tmp_path / "other" / "python.exe"
    expected.parent.mkdir()
    actual.parent.mkdir()
    expected.write_bytes(b"qualified")
    actual.write_bytes(b"other")

    with pytest.raises(
        MODULE.NativeInventoryRecoveryLaunchError,
        match="must run under the qualified Isaac Python",
    ):
        MODULE._validate_qualified_interpreter(expected, actual)


def test_runtime_binding_hashes_revalidate_raw_and_canonical_inputs(tmp_path):
    artifact = tmp_path / "artifacts"
    repo = tmp_path / "repo"
    route = (
        artifact
        / "arm231-state-policy-fixed-fixture-correction-001"
        / "episode-ef340d0ad2740c118d87"
        / "native_mechanics_plan.json"
    )
    usd = (
        artifact
        / "wp1-import-003/roarm_m3_kinematic_40dbd84"
        / "roarm_m3_kinematic_40dbd84.usda"
    )
    virtual = repo / "software/config/virtual_commissioning_profile.json"
    receipt = (
        repo
        / "software/integrations/isaac_sim/evidence"
        / "roarm_m3_urdf_import_20260929.json"
    )
    for path in (route, usd, virtual, receipt):
        path.parent.mkdir(parents=True, exist_ok=True)
    usd.write_bytes(b"usd")
    virtual.write_bytes(b"virtual")
    receipt_core = {"schema": "receipt", "value": 1}
    receipt_hash = MODULE._canonical_document_hash(receipt_core, "receipt_sha256")
    receipt.write_text(
        json.dumps({**receipt_core, "receipt_sha256": receipt_hash}),
        encoding="utf-8",
    )
    route.write_text(
        json.dumps(
            {
                "source_bindings": {
                    "robot_usd_sha256": MODULE._file_sha(usd),
                    "robot_import_receipt_sha256": receipt_hash,
                    "virtual_profile_sha256": MODULE._file_sha(virtual),
                    "key_mechanics_profile_sha256": "a" * 64,
                }
            }
        ),
        encoding="utf-8",
    )
    assert MODULE._runtime_binding_hashes(artifact, repo) == {
        "robot_usd": MODULE._file_sha(usd),
        "robot_import_receipt": receipt_hash,
        "virtual_profile": MODULE._file_sha(virtual),
        "key_mechanics_profile": "a" * 64,
    }


def test_runtime_binding_hashes_fail_closed_on_changed_input(tmp_path):
    artifact = tmp_path / "artifacts"
    repo = tmp_path / "repo"
    route = (
        artifact
        / "arm231-state-policy-fixed-fixture-correction-001"
        / "episode-ef340d0ad2740c118d87"
        / "native_mechanics_plan.json"
    )
    usd = (
        artifact
        / "wp1-import-003/roarm_m3_kinematic_40dbd84"
        / "roarm_m3_kinematic_40dbd84.usda"
    )
    virtual = repo / "software/config/virtual_commissioning_profile.json"
    receipt = (
        repo
        / "software/integrations/isaac_sim/evidence"
        / "roarm_m3_urdf_import_20260929.json"
    )
    for path in (route, usd, virtual, receipt):
        path.parent.mkdir(parents=True, exist_ok=True)
    usd.write_bytes(b"changed")
    virtual.write_bytes(b"virtual")
    receipt.write_text(json.dumps({"receipt_sha256": "b" * 64}), encoding="utf-8")
    route.write_text(
        json.dumps(
            {
                "source_bindings": {
                    "robot_usd_sha256": "c" * 64,
                    "robot_import_receipt_sha256": "b" * 64,
                    "virtual_profile_sha256": MODULE._file_sha(virtual),
                    "key_mechanics_profile_sha256": "a" * 64,
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        MODULE.NativeInventoryRecoveryLaunchError,
        match="current runtime bindings",
    ):
        MODULE._runtime_binding_hashes(artifact, repo)


def test_authorized_entry_point_delegates_once_with_revalidated_maps(
    tmp_path, monkeypatch
):
    artifact = tmp_path / "artifacts"
    repo = tmp_path / "repo"
    attempt = artifact / "arm295-attempt"
    eula = artifact / "arm295-eula" / "receipt.json"
    memory = artifact / "arm295-memory" / "receipt.json"
    claimant_path = artifact / "claimant.json"
    review_path = artifact / "review.json"
    claimant_path.parent.mkdir(parents=True)
    claimant_path.write_text(
        json.dumps(
            {
                "proposed_output_directory": str(attempt),
                "fresh_eula_receipt": str(eula),
                "fresh_memory_receipt": str(memory),
            }
        ),
        encoding="utf-8",
    )
    review_path.write_text(
        json.dumps({"source_claimant_file_sha256": MODULE._file_sha(claimant_path)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(MODULE, "_runtime_source_hashes", lambda _: {"r": "1"})
    monkeypatch.setattr(MODULE, "_worker_source_hashes", lambda *_: {"source": "2"})
    monkeypatch.setattr(MODULE, "_runtime_binding_hashes", lambda *_: {"binding": "3"})
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

    result = MODULE.run_authorized_attempt(
        authorization_statement="exact statement",
        claimant_path=claimant_path,
        claimant_review_path=review_path,
        artifact_root=artifact,
        repo_root=repo,
        claimant_type=Claimant,
        binding_builder=build,
    )
    assert result == {"status": "terminal"}
    assert [call[0] for call in calls] == ["build", "construct", "run"]
    run = calls[-1][1]
    assert run["authorization_statement"] == "exact statement"
    assert run["output_directory"] == attempt
    assert run["fresh_eula_receipt"] == eula
    assert run["fresh_memory_receipt"] == memory
    assert run["current_runtime_sources_sha256"] == {"r": "1"}
    assert run["current_source_files_sha256"] == {"source": "2"}
    assert run["current_runtime_bindings_sha256"] == {"binding": "3"}
    assert run["backend"] == "deferred-backend"
