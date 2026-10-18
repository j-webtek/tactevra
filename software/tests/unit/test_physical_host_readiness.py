from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
from types import SimpleNamespace

import pytest

import rocell.application.physical_host_readiness as readiness_module
from rocell.application.physical_host_readiness import (
    PHYSICAL_HOST_READINESS_SCHEMA,
    PhysicalHostReadinessError,
    assess_physical_host_readiness,
)
from rocell.rc03 import import_build_snapshot


WORKSPACE = Path(__file__).resolve().parents[3]
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _snapshot():
    return import_build_snapshot(
        WORKSPACE, WORKSPACE / "software/config/system_manifest.json"
    )


_TEST_DEPENDENCY_VERSIONS = {
    "packaging": "26.0",
    "Pillow": "12.0.0",
    "numpy": "2.2.0",
    "opencv-contrib-python": "4.12.0.88",
    "pyserial": "3.5",
    "pytest": "9.1.1",
}


def _mock_controlled_windows_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    stale_cli: bool = False,
    prefix_matches: bool = True,
) -> Path:
    """Create path identities only; no executable or dependency is imported."""

    workspace = tmp_path / "workspace"
    config = workspace / "software/config"
    config.mkdir(parents=True)
    for name in ("runtime.json", "camera_architecture_plan.json"):
        shutil.copy2(WORKSPACE / "software/config" / name, config / name)
    (workspace / "rocell.ps1").write_text("# test launcher\n", encoding="utf-8")
    (workspace / "setup-rocell.ps1").write_text(
        "# test bootstrap\n", encoding="utf-8"
    )

    source_root = workspace / "software/src/rocell"
    runtime_origins: dict[str, Path] = {}
    for import_name, relative in (
        ("rocell", "__init__.py"),
        ("rocell.cli", "cli.py"),
        ("rocell.__main__", "__main__.py"),
    ):
        target = source_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {import_name}\n", encoding="utf-8")
        runtime_origins[import_name] = target

    venv = workspace / ".venv"
    interpreter = venv / "Scripts/python.exe"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"synthetic-python-launcher")
    (venv / "pyvenv.cfg").write_text(
        "home = C:\\Python312\ninclude-system-site-packages = false\n",
        encoding="utf-8",
    )
    package_root = venv / "Lib/site-packages"
    dependency_origins: dict[str, Path] = {}
    for import_name in ("packaging", "PIL", "numpy", "cv2", "serial", "pytest"):
        target = package_root / import_name / "__init__.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {import_name}\n", encoding="utf-8")
        dependency_origins[import_name] = target

    if stale_cli:
        stale = package_root / "rocell/cli.py"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text("# stale copied cli\n", encoding="utf-8")
        runtime_origins["rocell.cli"] = stale

    origins = {**runtime_origins, **dependency_origins}
    monkeypatch.setattr(
        readiness_module.util,
        "find_spec",
        lambda import_name: SimpleNamespace(origin=str(origins[import_name])),
    )
    monkeypatch.setattr(
        readiness_module.metadata,
        "version",
        lambda distribution_name: _TEST_DEPENDENCY_VERSIONS[distribution_name],
    )
    monkeypatch.setattr(readiness_module.sys, "executable", str(interpreter))
    monkeypatch.setattr(
        readiness_module.sys,
        "prefix",
        str(venv if prefix_matches else tmp_path / "copied-elsewhere"),
    )
    monkeypatch.setattr(readiness_module.sys, "base_prefix", str(tmp_path / "base"))
    return workspace


def test_host_readiness_is_side_effect_free_and_exposes_current_freeze_hold() -> None:
    report = assess_physical_host_readiness(
        WORKSPACE,
        _snapshot(),
        platform_system="Windows",
        platform_release="test",
    )

    document = report.to_dict()
    assert document["schema"] == PHYSICAL_HOST_READINESS_SCHEMA
    assert document["authority"] == {
        "hardware_accessed": False,
        "physical_authority": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "physical_release_effect": "NONE",
    }
    assert document["build"]["static_camera_plan_selected"] is True
    assert document["build"]["static_camera_freeze_promoted"] is False
    assert "SUPERSEDING_STATIC_CAMERA_FREEZE_NOT_PROMOTED" in document["blockers"]
    assert report.base_software_ready is True
    # This test is valid both under a developer's global interpreter and under
    # the checkout-controlled .venv created by setup-rocell.ps1. Readiness may
    # differ, but every positive result must be backed by the complete identity
    # and dependency chain rather than by the test runner's location alone.
    if report.device_access_environment_ready:
        assert report.workspace_venv_present is True
        assert report.running_from_workspace_venv is True
        assert report.workspace_venv_integrity_ready is True
        assert report.runtime_origins_match_workspace is True
        assert report.interpreter_identity_valid is True
        assert report.camera_diagnostics_dependencies_ready is True
        assert report.arm_diagnostics_dependencies_ready is True
    else:
        assert report.camera_diagnostics_dependencies_ready is False
        assert report.arm_diagnostics_dependencies_ready is False
    assert SHA256.fullmatch(document["report_sha256"])
    assert report.report_sha256 == document["report_sha256"]


def test_host_readiness_reports_unsupported_host_without_claiming_hardware() -> None:
    report = assess_physical_host_readiness(
        WORKSPACE,
        _snapshot(),
        platform_system="Plan9",
        platform_release="test",
    )

    assert report.base_software_ready is False
    assert "HOST_OS_NOT_SUPPORTED_BY_SELECTED_CAMERA_CONTRACT" in report.blockers
    assert report.hardware_accessed is False


def test_host_readiness_rejects_duplicate_runtime_fields(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "software/config").mkdir(parents=True)
    runtime = (WORKSPACE / "software/config/runtime.json").read_text(encoding="utf-8")
    # Inserting a duplicate at the start preserves valid JSON while exercising
    # the strict object-pairs loader.
    (workspace / "software/config/runtime.json").write_text(
        runtime.replace("{", '{"schema_version": 1,', 1),
        encoding="utf-8",
    )
    (workspace / "software/config/camera_architecture_plan.json").write_text(
        (WORKSPACE / "software/config/camera_architecture_plan.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    with pytest.raises(PhysicalHostReadinessError, match="duplicate"):
        assess_physical_host_readiness(
            workspace,
            _snapshot(),
            platform_system="Windows",
            platform_release="test",
        )


def test_host_readiness_report_hash_covers_blockers() -> None:
    report = assess_physical_host_readiness(
        WORKSPACE,
        _snapshot(),
        platform_system="Windows",
        platform_release="test",
    )
    document = report.to_dict()
    changed = dict(document)
    changed["blockers"] = []
    changed.pop("report_sha256")
    changed_sha256 = __import__("hashlib").sha256(
        json.dumps(
            changed,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert changed_sha256 != report.report_sha256


def test_controlled_environment_binds_versions_runtime_and_venv_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _mock_controlled_windows_environment(tmp_path, monkeypatch)

    report = assess_physical_host_readiness(
        workspace,
        _snapshot(),
        platform_system="Windows",
        platform_release="test",
    )

    assert report.runtime_origins_match_workspace is True
    assert report.workspace_venv_integrity_ready is True
    assert report.python_prefix_matches_workspace_venv is True
    assert report.python_base_prefix_distinct is True
    assert report.interpreter_identity_valid is True
    assert report.running_from_workspace_venv is True
    assert report.device_access_environment_ready is True
    assert report.camera_diagnostics_dependencies_ready is True
    assert report.arm_diagnostics_dependencies_ready is True
    assert report.development_dependencies_ready is True
    assert SHA256.fullmatch(report.workspace_venv_pyvenv_cfg_sha256 or "")
    assert SHA256.fullmatch(report.workspace_interpreter_sha256 or "")
    assert all(item.version_policy_satisfied for item in report.dependencies)
    assert not any("DEPENDENCY_VERSION" in item for item in report.blockers)


def test_stale_copied_cli_origin_blocks_device_access_even_inside_valid_venv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _mock_controlled_windows_environment(
        tmp_path,
        monkeypatch,
        stale_cli=True,
    )

    report = assess_physical_host_readiness(
        workspace,
        _snapshot(),
        platform_system="Windows",
        platform_release="test",
    )

    assert report.workspace_venv_integrity_ready is True
    assert report.running_from_workspace_venv is True
    assert report.runtime_origins_match_workspace is False
    assert report.device_access_environment_ready is False
    assert report.base_software_ready is False
    assert "RUNTIME_MODULE_ORIGIN_MISMATCH:rocell.cli" in report.blockers


def test_mismatched_python_prefix_blocks_copied_venv_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _mock_controlled_windows_environment(
        tmp_path,
        monkeypatch,
        prefix_matches=False,
    )

    report = assess_physical_host_readiness(
        workspace,
        _snapshot(),
        platform_system="Windows",
        platform_release="test",
    )

    assert report.workspace_venv_integrity_ready is True
    assert report.python_prefix_matches_workspace_venv is False
    assert report.interpreter_identity_valid is False
    assert report.running_from_workspace_venv is False
    assert report.device_access_environment_ready is False
    assert "PYTHON_PREFIX_OUTSIDE_WORKSPACE_VIRTUAL_ENVIRONMENT" in report.blockers


def test_dependency_outside_approved_version_is_explicitly_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _mock_controlled_windows_environment(tmp_path, monkeypatch)
    monkeypatch.setattr(
        readiness_module.metadata,
        "version",
        lambda distribution_name: (
            "4.11.0.86"
            if distribution_name == "opencv-contrib-python"
            else _TEST_DEPENDENCY_VERSIONS[distribution_name]
        ),
    )

    report = assess_physical_host_readiness(
        workspace,
        _snapshot(),
        platform_system="Windows",
        platform_release="test",
    )

    opencv = next(item for item in report.dependencies if item.import_name == "cv2")
    assert opencv.version_specifier == ">=4.12,<5"
    assert opencv.version_policy_satisfied is False
    assert report.device_access_environment_ready is False
    assert report.camera_diagnostics_dependencies_ready is False
    assert (
        "DEPENDENCY_VERSION_OUTSIDE_APPROVED_RANGE:"
        "opencv-contrib-python:>=4.12,<5"
    ) in report.blockers


def test_windows_venv_reparse_boundary_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _mock_controlled_windows_environment(tmp_path, monkeypatch)
    venv = workspace / ".venv"
    original = readiness_module._is_link_or_reparse
    monkeypatch.setattr(
        readiness_module,
        "_is_link_or_reparse",
        lambda path: Path(path) == venv or original(Path(path)),
    )

    report = assess_physical_host_readiness(
        workspace,
        _snapshot(),
        platform_system="Windows",
        platform_release="test",
    )

    assert report.workspace_venv_integrity_ready is False
    assert report.running_from_workspace_venv is False
    assert report.device_access_environment_ready is False
    assert "WORKSPACE_VIRTUAL_ENVIRONMENT_LINK_OR_REPARSE_POINT" in report.blockers
