from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from types import ModuleType
from typing import Any

import pytest


WORKSPACE = Path(__file__).resolve().parents[3]
TOOL_PATH = WORKSPACE / "software/tools/refreeze_build_alignment.py"


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "refreeze_build_alignment_test", TOOL_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("payload", (b"\xff", b'{"value": NaN}'))
def test_json_loader_rejects_invalid_encoding_and_nonfinite_values(
    tmp_path: Path,
    payload: bytes,
) -> None:
    tool = _load_tool()
    source = tmp_path / "invalid.json"
    source.write_bytes(payload)

    with pytest.raises(tool.RefreezeError, match="Cannot load"):
        tool._load_json(source)


def _synthetic_plan(module: ModuleType, workspace: Path) -> Any:
    config = workspace / "software/config"
    config.mkdir(parents=True)
    leaf = config / "camera_manifest.json"
    bundle = config / "simulation_bundle_lock.json"
    manifest = config / "system_manifest.json"
    model = workspace / "software/models/arm.urdf"
    model.parent.mkdir(parents=True)
    for path, payload in (
        (leaf, b"old-leaf\n"),
        (bundle, b"old-bundle\n"),
        (manifest, b"old-manifest\n"),
        (model, b"old-model\n"),
    ):
        path.write_bytes(payload)
    archive = workspace / "software/freezes/OLD/camera_manifest.json"
    documents = {
        manifest: b"new-manifest\n",
        bundle: b"new-bundle\n",
        leaf: b"new-leaf\n",
        archive: b"old-leaf\n",
    }
    inputs = {
        leaf: _sha(leaf.read_bytes()),
        bundle: _sha(bundle.read_bytes()),
        manifest: _sha(manifest.read_bytes()),
        model: _sha(model.read_bytes()),
    }
    plan_sha256 = module._set_digest(documents, workspace)
    return module.RefreezePlan(
        workspace=workspace,
        documents=documents,
        input_digests=inputs,
        summary={
            "plan_sha256": plan_sha256,
            "nested_evidence": {"output_names": [path.name for path in documents]},
        },
    )


def test_apply_requires_reviewed_hash_and_unchanged_inputs(tmp_path: Path) -> None:
    tool = _load_tool()
    plan = _synthetic_plan(tool, tmp_path)
    plan_sha256 = plan.summary["plan_sha256"]
    lock = tool.acquire_refreeze_lock(tmp_path, plan_sha256)
    try:
        with pytest.raises(tool.RefreezeError, match="reviewed plan hash"):
            tool.apply_refreeze_plan(
                plan,
                expected_plan_sha256="b" * 64,
                held_lock_path=lock,
            )
        (tmp_path / "software/models/arm.urdf").write_bytes(b"changed\n")
        with pytest.raises(tool.RefreezeError, match="input changed"):
            tool.apply_refreeze_plan(
                plan,
                expected_plan_sha256=plan_sha256,
                held_lock_path=lock,
            )
        assert (tmp_path / "software/config/system_manifest.json").read_bytes() == (
            b"old-manifest\n"
        )
    finally:
        tool.release_refreeze_lock(lock)


def test_apply_commits_archive_then_leaf_bundle_and_manifest_last(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _load_tool()
    plan = _synthetic_plan(tool, tmp_path)
    plan_sha256 = plan.summary["plan_sha256"]
    replaced: list[Path] = []
    real_replace = tool.os.replace

    def traced_replace(source: Path, destination: Path) -> None:
        replaced.append(Path(destination))
        real_replace(source, destination)

    monkeypatch.setattr(tool.os, "replace", traced_replace)
    lock = tool.acquire_refreeze_lock(tmp_path, plan_sha256)
    try:
        tool.apply_refreeze_plan(
            plan,
            expected_plan_sha256=plan_sha256,
            held_lock_path=lock,
        )
    finally:
        tool.release_refreeze_lock(lock)

    assert "freezes" in replaced[0].parts
    assert replaced[-2].name == "simulation_bundle_lock.json"
    assert replaced[-1].name == "system_manifest.json"
    assert (tmp_path / "software/config/system_manifest.json").read_bytes() == (
        b"new-manifest\n"
    )


def test_lock_contention_and_archive_collision_fail_closed(tmp_path: Path) -> None:
    tool = _load_tool()
    plan = _synthetic_plan(tool, tmp_path)
    plan_sha256 = plan.summary["plan_sha256"]
    archive = tmp_path / "software/freezes/OLD/camera_manifest.json"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"different\n")
    lock = tool.acquire_refreeze_lock(tmp_path, plan_sha256)
    try:
        with pytest.raises(tool.RefreezeError, match="lock exists"):
            tool.acquire_refreeze_lock(tmp_path, "f" * 64)
        with pytest.raises(tool.RefreezeError, match="immutable archive"):
            tool.apply_refreeze_plan(
                plan,
                expected_plan_sha256=plan_sha256,
                held_lock_path=lock,
            )
    finally:
        tool.release_refreeze_lock(lock)


def test_plan_payloads_are_immutable_and_forged_summary_is_rejected(
    tmp_path: Path,
) -> None:
    tool = _load_tool()
    plan = _synthetic_plan(tool, tmp_path)
    manifest = tmp_path / "software/config/system_manifest.json"

    with pytest.raises(TypeError):
        plan.documents[manifest] = b"forged-manifest\n"
    with pytest.raises(TypeError):
        plan.summary["plan_sha256"] = "f" * 64
    with pytest.raises(TypeError):
        plan.summary["nested_evidence"]["output_names"] = ()

    forged_sha256 = "f" * 64
    forged = replace(plan, summary={"plan_sha256": forged_sha256})
    lock = tool.acquire_refreeze_lock(tmp_path, forged_sha256)
    try:
        with pytest.raises(tool.RefreezeError, match="reviewed plan hash"):
            tool.apply_refreeze_plan(
                forged,
                expected_plan_sha256=forged_sha256,
                held_lock_path=lock,
            )
    finally:
        tool.release_refreeze_lock(lock)
    assert manifest.read_bytes() == b"old-manifest\n"


def test_apply_rejects_lock_token_for_another_plan(tmp_path: Path) -> None:
    tool = _load_tool()
    plan = _synthetic_plan(tool, tmp_path)
    plan_sha256 = plan.summary["plan_sha256"]
    lock = tool.acquire_refreeze_lock(tmp_path, plan_sha256)
    try:
        lock.write_text("e" * 64 + "\n", encoding="ascii")
        with pytest.raises(tool.RefreezeError, match="lock token"):
            tool.apply_refreeze_plan(
                plan,
                expected_plan_sha256=plan_sha256,
                held_lock_path=lock,
            )
    finally:
        tool.release_refreeze_lock(lock)


def test_apply_rechecks_inputs_after_staging_before_first_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _load_tool()
    plan = _synthetic_plan(tool, tmp_path)
    plan_sha256 = plan.summary["plan_sha256"]
    model = tmp_path / "software/models/arm.urdf"
    manifest = tmp_path / "software/config/system_manifest.json"
    replacements: list[Path] = []
    real_fsync = tool.os.fsync
    real_replace = tool.os.replace
    changed = False

    def mutate_after_first_staged_fsync(descriptor: int) -> None:
        nonlocal changed
        real_fsync(descriptor)
        if not changed:
            changed = True
            model.write_bytes(b"changed-during-staging\n")

    def traced_replace(source: Path, destination: Path) -> None:
        replacements.append(Path(destination))
        real_replace(source, destination)

    lock = tool.acquire_refreeze_lock(tmp_path, plan_sha256)
    monkeypatch.setattr(tool.os, "fsync", mutate_after_first_staged_fsync)
    monkeypatch.setattr(tool.os, "replace", traced_replace)
    try:
        with pytest.raises(tool.RefreezeError, match="during output staging"):
            tool.apply_refreeze_plan(
                plan,
                expected_plan_sha256=plan_sha256,
                held_lock_path=lock,
            )
    finally:
        tool.release_refreeze_lock(lock)

    assert replacements == []
    assert manifest.read_bytes() == b"old-manifest\n"


def test_input_inventory_includes_models_and_foundation_dependencies(
    tmp_path: Path,
) -> None:
    tool = _load_tool()
    model = tmp_path / "software/models/arm.urdf"
    model.parent.mkdir(parents=True)
    model.write_text("model", encoding="utf-8")
    (tmp_path / "software/config").mkdir(parents=True)
    camera_profile = (
        tmp_path / "software/config/camera_profiles/arducam_b0477_imx283_16mm.json"
    )
    camera_profile.parent.mkdir(parents=True)
    camera_profile.write_text("{}\n", encoding="utf-8")
    (tmp_path / "software/calibrations").mkdir(parents=True)
    (tmp_path / "software/calibrations/registry.json").write_text(
        "{}\n", encoding="utf-8"
    )
    (tmp_path / "software/tools").mkdir(parents=True)
    (tmp_path / "software/tools/validate_build_alignment.py").write_text(
        "# test\n", encoding="utf-8"
    )
    (tmp_path / "software/src/rocell").mkdir(parents=True)
    support_design = (
        tmp_path / "hardware/static_overhead_camera/config/support_design.json"
    )
    support_design.parent.mkdir(parents=True)
    support_design.write_text("{}\n", encoding="utf-8")
    tripod_candidate = (
        tmp_path
        / "hardware/static_overhead_camera/config/commercial_tripod_candidate.json"
    )
    tripod_candidate.write_text("{}\n", encoding="utf-8")
    intake_template = (
        tmp_path / "hardware/static_overhead_camera/hardware_intake_template.csv"
    )
    intake_template.write_text("record_id\n", encoding="utf-8")

    observed = tool._collect_input_digests(
        tmp_path,
        snapshot_paths=[],
        document_paths={},
    )
    assert model.resolve() in observed
    assert camera_profile.resolve() in observed
    assert support_design.resolve() in observed
    assert tripod_candidate.resolve() in observed
    assert intake_template.resolve() in observed


def _next_freeze_arguments() -> tuple[str, int, str]:
    manifest = json.loads(
        (WORKSPACE / "software/config/system_manifest.json").read_text(encoding="utf-8")
    )
    current = manifest["manifest_id"]
    match = re.search(r"([0-9]{3})$", current)
    assert match is not None
    return current, int(match.group(1)) + 1, manifest["freeze_date"]


def _run_dry_plan(*extra: str) -> subprocess.CompletedProcess[str]:
    current, next_number, freeze_date = _next_freeze_arguments()
    return subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--expected-current-freeze-id",
            current,
            "--new-freeze-number",
            str(next_number),
            "--date",
            freeze_date,
            "--reason",
            "Controlled unit-test dry-run only",
            "--approval-reference",
            "PYTEST-DRY-RUN",
            *extra,
        ],
        cwd=WORKSPACE,
        check=False,
        capture_output=True,
        text=True,
    )


def test_noop_requires_explicit_companion_reason_and_dry_run_never_writes() -> None:
    current, next_number, _ = _next_freeze_arguments()
    archive = WORKSPACE / "software/freezes" / current
    transaction = (
        WORKSPACE
        / "software/freezes/transactions"
        / f"{current}__ROCELL-PHASE0-RC03-INT-R1-FREEZE-{next_number:03d}.json"
    )
    assert not archive.exists()
    assert not transaction.exists()

    rejected = _run_dry_plan()
    assert rejected.returncode == 2
    assert "No RC03 source changed" in rejected.stdout

    accepted = _run_dry_plan(
        "--companion-change-reason",
        "Exercise explicit companion-only planning without applying it",
    )
    assert accepted.returncode == 0
    report = json.loads(accepted.stdout)
    assert report["applied"] is False
    assert report["prospective_validation_status"] == (
        "ALIGNED_CAMERA_HOLD_CONTACT_BLOCKED"
    )
    assert (
        "software/config/virtual_commissioning_profile.json" in report["output_files"]
    )
    assert (
        f"software/freezes/{current}/virtual_commissioning_profile.json"
        in report["output_files"]
    )
    assert not archive.exists()
    assert not transaction.exists()


def test_invalid_and_backdated_dates_are_rejected() -> None:
    current, next_number, _ = _next_freeze_arguments()
    common = [
        sys.executable,
        str(TOOL_PATH),
        "--expected-current-freeze-id",
        current,
        "--new-freeze-number",
        str(next_number),
        "--reason",
        "Controlled date validation test",
        "--approval-reference",
        "PYTEST-DATE",
    ]
    invalid = subprocess.run(
        [*common, "--date", "2026-99-99"],
        cwd=WORKSPACE,
        check=False,
        capture_output=True,
        text=True,
    )
    backdated = subprocess.run(
        [*common, "--date", "2026-08-31"],
        cwd=WORKSPACE,
        check=False,
        capture_output=True,
        text=True,
    )
    assert invalid.returncode == 2
    assert "valid YYYY-MM-DD" in invalid.stdout
    assert backdated.returncode == 2
    assert "cannot precede" in backdated.stdout
