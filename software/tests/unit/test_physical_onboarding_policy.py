from __future__ import annotations

import json
from pathlib import Path
import re
import shutil

import pytest

from rocell.application.physical_onboarding import STAGE_PLAN_SHA256
from rocell.application.physical_onboarding_policy import (
    DEFAULT_PHYSICAL_ONBOARDING_POLICY,
    PHYSICAL_ONBOARDING_SOURCE_BINDING_SCHEMA,
    PhysicalOnboardingPolicyError,
    bind_physical_onboarding_sources,
    load_physical_onboarding_policy,
)
from rocell.rc03 import import_build_snapshot


WORKSPACE = Path(__file__).resolve().parents[3]
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _snapshot():
    return import_build_snapshot(
        WORKSPACE, WORKSPACE / "software/config/system_manifest.json"
    )


def _copy_policy_sources(destination: Path) -> None:
    policy = load_physical_onboarding_policy(WORKSPACE)
    for relative in (policy.policy_relative_path, *policy.controlled_sources):
        source = WORKSPACE / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative_root in policy.controlled_source_roots:
        for source in (WORKSPACE / relative_root).rglob("*.py"):
            target = destination / source.relative_to(WORKSPACE)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def test_default_policy_binds_every_source_and_never_confers_authority() -> None:
    policy, binding = bind_physical_onboarding_sources(WORKSPACE, _snapshot())
    document = binding.to_dict()

    assert policy.require_workspace_venv_for_device_access is True
    assert policy.session_root_relative == "software/runs/physical-onboarding"
    expected_python_sources = sum(
        1
        for relative_root in policy.controlled_source_roots
        for _path in (WORKSPACE / relative_root).rglob("*.py")
    )
    assert len(binding.sources) == (
        len(policy.controlled_sources) + expected_python_sources + 1
    )
    assert len({source.relative_path for source in binding.sources}) == len(
        binding.sources
    )
    assert (
        binding.sources[0].relative_path
        == DEFAULT_PHYSICAL_ONBOARDING_POLICY.as_posix()
    )
    assert binding.stage_plan_sha256 == STAGE_PLAN_SHA256
    assert document["schema"] == PHYSICAL_ONBOARDING_SOURCE_BINDING_SCHEMA
    assert document["authority"] == {
        "hardware_accessed": False,
        "robot_power_authorized": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "physical_release_effect": "NONE",
    }
    assert SHA256.fullmatch(binding.source_binding_sha256)


def test_explicit_historical_v1_policy_remains_readable() -> None:
    policy = load_physical_onboarding_policy(
        WORKSPACE, WORKSPACE / "software/config/physical_onboarding_policy.json"
    )

    assert policy.policy_id == "ROCELL-PHYSICAL-ONBOARDING-001"
    assert policy.policy_relative_path == "software/config/physical_onboarding_policy.json"


def test_default_policy_binds_the_executable_and_operator_procedure() -> None:
    """An old session must become stale when its code or runbook changes."""

    policy = load_physical_onboarding_policy(WORKSPACE)
    controlled = set(policy.controlled_sources)
    _, binding = bind_physical_onboarding_sources(WORKSPACE, _snapshot())
    bound_paths = {source.relative_path for source in binding.sources}

    assert {
        "active-project/RoCell_v0_3/config/workcell_layout.json",
        "active-project/RoCell_v0_3/config/robot_reach_screening.json",
        "start-rocell-onboarding.ps1",
        "software/pyproject.toml",
        "software/config/physical_onboarding_foundation_v2.json",
        "software/config/authority_effect_policy.json",
        "software/config/physical_onboarding_stage_catalog.json",
        "software/config/configuration_epochs.json",
        "software/config/physical_onboarding_hazards.json",
        "software/config/workcell_icd_v3.json",
        "software/config/accuracy_budget_policy.json",
        "software/config/arm_frame_contract.json",
        "software/docs/FIRST_POWER_ON_ONBOARDING.md",
        "software/docs/PHYSICAL_ONBOARDING_AUTOMATION.md",
    } <= controlled
    assert policy.controlled_source_roots == ("software/src/rocell",)
    assert "power_safety" in policy.possible_device_side_effect_stages
    assert {
        "software/src/rocell/__main__.py",
        "software/src/rocell/cli.py",
        "software/src/rocell/application/physical_onboarding.py",
        "software/src/rocell/application/physical_onboarding_controller.py",
        "software/src/rocell/application/physical_connection_rehearsal.py",
        "software/src/rocell/application/physical_onboarding_receipts.py",
        "software/src/rocell/rc03/importer.py",
        "software/src/rocell/arm/serial_transport.py",
        "software/src/rocell/vision/usb_opencv.py",
    } <= bound_paths


def test_source_binding_changes_when_a_controlled_source_changes(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _copy_policy_sources(workspace)

    _, before = bind_physical_onboarding_sources(workspace, _snapshot())
    arm_path = workspace / "software/config/arm_connection.json"
    arm_path.write_bytes(arm_path.read_bytes() + b"\n")
    _, after = bind_physical_onboarding_sources(workspace, _snapshot())

    assert after.source_binding_sha256 != before.source_binding_sha256
    before_arm = next(
        source
        for source in before.sources
        if source.relative_path.endswith("arm_connection.json")
    )
    after_arm = next(
        source
        for source in after.sources
        if source.relative_path.endswith("arm_connection.json")
    )
    assert after_arm.sha256 != before_arm.sha256


def test_policy_rejects_unknown_fields_and_unsafe_authority(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _copy_policy_sources(workspace)
    path = workspace / DEFAULT_PHYSICAL_ONBOARDING_POLICY
    document = json.loads(path.read_text(encoding="utf-8"))
    document["authority"]["live_motion_authority"] = True
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(PhysicalOnboardingPolicyError, match="zero physical authority"):
        load_physical_onboarding_policy(workspace)

    document["authority"]["live_motion_authority"] = False
    document["surprise"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(PhysicalOnboardingPolicyError, match="fields differ"):
        load_physical_onboarding_policy(workspace)


def test_policy_rejects_duplicate_fields(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    path = workspace / DEFAULT_PHYSICAL_ONBOARDING_POLICY
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"schema":"rocell.physical_onboarding_policy.v1",'
        '"schema":"rocell.physical_onboarding_policy.v1"}',
        encoding="utf-8",
    )

    with pytest.raises(PhysicalOnboardingPolicyError, match="duplicate policy field"):
        load_physical_onboarding_policy(workspace)


def test_policy_path_cannot_escape_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(PhysicalOnboardingPolicyError, match="outside the workspace"):
        load_physical_onboarding_policy(workspace, outside)
