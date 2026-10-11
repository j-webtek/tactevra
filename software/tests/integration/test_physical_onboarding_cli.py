from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

import pytest


SOFTWARE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = SOFTWARE_ROOT.parent


def _copy_arrival_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "arrival-workspace"
    policy_source = (
        REPOSITORY_ROOT / "software/config/physical_onboarding_policy_v2.json"
    )
    policy = json.loads(policy_source.read_text(encoding="utf-8"))
    controlled = (
        "software/config/physical_onboarding_policy_v2.json",
        *policy["controlled_sources"],
    )
    for relative in controlled:
        source = REPOSITORY_ROOT / relative
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative_root in policy["controlled_source_roots"]:
        for source in (REPOSITORY_ROOT / relative_root).rglob("*.py"):
            target = workspace / source.relative_to(REPOSITORY_ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    manifest = json.loads(
        (workspace / "software/config/system_manifest.json").read_text(encoding="utf-8")
    )
    rc03_root = Path(manifest["rc03"]["root"])
    for entry in manifest["rc03"]["source_snapshot"]:
        relative = rc03_root / entry["path"]
        source = REPOSITORY_ROOT / relative
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return workspace


def _run(
    workspace: Path, *arguments: str
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    sentinels = workspace / "sentinels"
    sentinels.mkdir(exist_ok=True)
    serial_marker = workspace / "serial-imported.txt"
    cv2_marker = workspace / "cv2-imported.txt"
    (sentinels / "serial.py").write_text(
        "import os\nfrom pathlib import Path\n"
        "Path(os.environ['ROCELL_SERIAL_IMPORT_MARKER']).write_text('imported')\n"
        "raise RuntimeError('serial must not be imported')\n",
        encoding="utf-8",
    )
    (sentinels / "cv2.py").write_text(
        "import os\nfrom pathlib import Path\n"
        "Path(os.environ['ROCELL_CV2_IMPORT_MARKER']).write_text('imported')\n"
        "raise RuntimeError('cv2 must not be imported')\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["ROCELL_SERIAL_IMPORT_MARKER"] = str(serial_marker)
    environment["ROCELL_CV2_IMPORT_MARKER"] = str(cv2_marker)
    # Execute the exact source copy whose physical-onboarding binding is under
    # test. Host readiness deliberately rejects a CLI imported from a different
    # checkout, even when both trees currently contain identical bytes.
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(sentinels), str(workspace / "software/src"))
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "rocell",
            "--workspace",
            str(workspace),
            *arguments,
        ],
        cwd=workspace,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, serial_marker, cv2_marker


def _json_result(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert completed.returncode == 0, completed.stderr
    value = json.loads(completed.stdout)
    assert isinstance(value, dict)
    return value


def _new_prepared(
    workspace: Path, session_id: str = "cli-arrival-001"
) -> dict[str, Any]:
    completed, serial_marker, cv2_marker = _run(
        workspace,
        "physical-onboard",
        "new",
        "--cell-id",
        "cell-a",
        "--session-id",
        session_id,
        "--prepare-safe",
        "--json",
    )
    result = _json_result(completed)
    assert not serial_marker.exists()
    assert not cv2_marker.exists()
    return result


def test_foundation_validation_is_zero_io_and_reports_open_gates(
    tmp_path: Path,
) -> None:
    workspace = _copy_arrival_workspace(tmp_path)

    completed, serial_marker, cv2_marker = _run(
        workspace,
        "physical-onboard",
        "verify-foundation",
        "--json",
    )
    document = _json_result(completed)
    result = document["result"]

    assert document["operation"] == "verify-foundation"
    assert result["result"] == "VALID_ZERO_AUTHORITY_FOUNDATION"
    assert result["validated_contract_count"] == 6
    assert result["runtime_activation"] is False
    assert result["zero_physical_authority"] is True
    assert len(result["open_implementation_gates"]) == 10
    assert document["operation_effect"]["device_opens"] == 0
    assert document["authority"]["physical_release_effect"] == "NONE"
    assert not serial_marker.exists()
    assert not cv2_marker.exists()


@pytest.mark.skipif(
    os.name != "nt", reason="qualified M1 physical storage is Windows NTFS only"
)
def test_m1_cli_initializes_creates_and_verifies_without_device_imports(
    tmp_path: Path,
) -> None:
    workspace = _copy_arrival_workspace(tmp_path)

    initialized, serial_marker, cv2_marker = _run(
        workspace,
        "physical-onboard",
        "init-v2-storage",
        "--cell-id",
        "cell-a",
        "--json",
    )
    initialized_document = _json_result(initialized)
    assert initialized_document["operation"] == "init-v2-storage"
    assert initialized_document["result"]["qualified_storage_ready"] is True
    assert initialized_document["result"]["session_created"] is False
    assert initialized_document["status"]["runtime_activation"] is False
    assert initialized_document["status"]["effect_methods_exposed"] is False
    assert initialized_document["operation_effect"]["device_opens"] == 0
    assert initialized_document["authority"]["physical_release_effect"] == "NONE"
    assert not serial_marker.exists()
    assert not cv2_marker.exists()

    created, serial_marker, cv2_marker = _run(
        workspace,
        "physical-onboard",
        "new-v2",
        "--cell-id",
        "cell-a",
        "--session-id",
        "cli-v2-arrival-001",
        "--json",
    )
    created_document = _json_result(created)
    assert created_document["operation"] == "new-v2"
    assert created_document["result"]["session_published"] is True
    assert created_document["result"]["stage_advanced"] is False
    assert created_document["status"]["session"]["session_id"] == ("cli-v2-arrival-001")
    assert created_document["status"]["operation_effect"]["robot_commands_sent"] == 0
    assert not serial_marker.exists()
    assert not cv2_marker.exists()

    verified, serial_marker, cv2_marker = _run(
        workspace,
        "physical-onboard",
        "verify-v2-runtime",
        "--cell-id",
        "cell-a",
        "--session-id",
        "cli-v2-arrival-001",
        "--json",
    )
    verified_document = _json_result(verified)
    assert verified_document["operation"] == "verify-v2-runtime"
    assert verified_document["result"]["integrity_verified"] is True
    assert verified_document["result"]["physical_authority_granted"] is False
    assert verified_document["status"]["session"]["reconciliation_required"] is False
    assert verified_document["status"]["authority"]["motion_authorized"] is False
    assert not serial_marker.exists()
    assert not cv2_marker.exists()


@pytest.mark.skipif(
    os.name != "nt", reason="qualified M1 physical storage is Windows NTFS only"
)
def test_m1_cli_requires_explicit_storage_initialization(tmp_path: Path) -> None:
    workspace = _copy_arrival_workspace(tmp_path)

    completed, serial_marker, cv2_marker = _run(
        workspace,
        "physical-onboard",
        "new-v2",
        "--cell-id",
        "cell-a",
        "--session-id",
        "must-not-publish",
        "--json",
    )

    assert completed.returncode == 3
    error = json.loads(completed.stderr)
    assert error["error"]["code"] == "PHYSICAL_ONBOARDING_M1_STORAGE_INVALID"
    assert error["error"]["details"]["hardware_access_attempted"] is False
    assert not (
        workspace / "software/runs/physical-onboarding/onboarding-must-not-publish"
    ).exists()
    assert not serial_marker.exists()
    assert not cv2_marker.exists()


def test_connection_rehearsal_is_fake_only_and_faults_fail_closed(
    tmp_path: Path,
) -> None:
    workspace = _copy_arrival_workspace(tmp_path)

    nominal, serial_marker, cv2_marker = _run(
        workspace,
        "rehearse-physical-connections",
        "--require-expected",
        "--json",
    )
    nominal_result = _json_result(nominal)
    assert nominal_result["rehearsal_passed"] is True
    assert nominal_result["expected_outcome_observed"] is True
    assert nominal_result["hardware_accessed"] is False
    assert nominal_result["physical_effects"]["camera_open_count"] == 0
    assert nominal_result["physical_effects"]["serial_write_count"] == 0
    assert not serial_marker.exists()
    assert not cv2_marker.exists()

    faulted, serial_marker, cv2_marker = _run(
        workspace,
        "rehearse-physical-connections",
        "--fault",
        "dirty-arm-buffer",
        "--require-expected",
        "--json",
    )
    fault_result = _json_result(faulted)
    assert fault_result["expected_fault_blocked"] is True
    assert fault_result["expected_outcome_observed"] is True
    assert fault_result["steps"][-1]["step_id"] == "arm_single_t105"
    assert fault_result["simulated_effects"]["t105_wire_attempts"] == 1
    assert fault_result["simulated_effects"]["retry_writes"] == 0
    assert not serial_marker.exists()
    assert not cv2_marker.exists()


def test_new_prepare_safe_reaches_first_operator_stage_without_device_imports(
    tmp_path: Path,
) -> None:
    workspace = _copy_arrival_workspace(tmp_path)
    result = _new_prepared(workspace)

    assert result["operation"] == "new"
    assert len(result["result"]["safe_zero_io_executions"]) == 2
    status = result["status"]
    assert status["journal"]["event_count"] == 4
    assert status["next_action"]["stage"] == "camera_receipt"
    assert status["next_action"]["stage_state"] == "PENDING"
    assert status["physical_effect_counters"]["device_opens"] == 0
    assert result["authority"]["motion_authorized"] is False


def test_next_uses_exact_stage_head_and_challenge_then_only_waits_for_operator(
    tmp_path: Path,
) -> None:
    workspace = _copy_arrival_workspace(tmp_path)
    _new_prepared(workspace)
    preview_completed, _, _ = _run(
        workspace,
        "physical-onboard",
        "next",
        "--session-id",
        "cli-arrival-001",
        "--json",
    )
    preview_result = _json_result(preview_completed)
    preview = preview_result["result"]["preview"]
    challenge = preview["challenge"]

    executed, serial_marker, cv2_marker = _run(
        workspace,
        "physical-onboard",
        "next",
        "--session-id",
        "cli-arrival-001",
        "--execute",
        "--expected-stage",
        "camera_receipt",
        "--expected-head-sha256",
        challenge["journal_head_sha256"],
        "--expected-challenge-sha256",
        challenge["challenge_sha256"],
        "--json",
    )
    result = _json_result(executed)
    assert result["status"]["next_action"]["stage_state"] == "WAITING_OPERATOR"
    assert result["result"]["execution"]["evidence_id"] is None
    assert not serial_marker.exists()
    assert not cv2_marker.exists()

    stale, _, _ = _run(
        workspace,
        "physical-onboard",
        "next",
        "--session-id",
        "cli-arrival-001",
        "--execute",
        "--expected-stage",
        "camera_receipt",
        "--expected-head-sha256",
        challenge["journal_head_sha256"],
        "--expected-challenge-sha256",
        challenge["challenge_sha256"],
        "--json",
    )
    assert stale.returncode == 3
    assert "PHYSICAL_ONBOARDING_HEAD_STALE" in stale.stderr


def test_record_archives_exact_file_but_cannot_pass_the_stage(tmp_path: Path) -> None:
    workspace = _copy_arrival_workspace(tmp_path)
    _new_prepared(workspace)
    preview, _, _ = _run(
        workspace,
        "physical-onboard",
        "next",
        "--session-id",
        "cli-arrival-001",
        "--json",
    )
    challenge = _json_result(preview)["result"]["preview"]["challenge"]
    _json_result(
        _run(
            workspace,
            "physical-onboard",
            "next",
            "--session-id",
            "cli-arrival-001",
            "--execute",
            "--expected-stage",
            "camera_receipt",
            "--expected-head-sha256",
            challenge["journal_head_sha256"],
            "--expected-challenge-sha256",
            challenge["challenge_sha256"],
            "--json",
        )[0]
    )
    waiting, _, _ = _run(
        workspace,
        "physical-onboard",
        "next",
        "--session-id",
        "cli-arrival-001",
        "--json",
    )
    waiting_challenge = _json_result(waiting)["result"]["preview"]["challenge"]
    evidence = workspace / "incoming/camera-receipt.txt"
    evidence.parent.mkdir()
    payload = b"received Arducam B0477 receipt observation\n"
    evidence.write_bytes(payload)
    captured_at_ns = time.time_ns()

    recorded, serial_marker, cv2_marker = _run(
        workspace,
        "physical-onboard",
        "record",
        "--session-id",
        "cli-arrival-001",
        "--stage",
        "camera_receipt",
        "--file",
        str(evidence.relative_to(workspace)),
        "--file-sha256",
        hashlib.sha256(payload).hexdigest(),
        "--captured-at-ns",
        str(captured_at_ns),
        "--label",
        "camera receipt",
        "--media-type",
        "text/plain",
        "--expected-challenge-sha256",
        waiting_challenge["challenge_sha256"],
        "--json",
    )
    result = _json_result(recorded)
    assert result["result"]["stage_passed"] is False
    assert result["status"]["next_action"]["stage_state"] == "WAITING_OPERATOR"
    assert not serial_marker.exists()
    assert not cv2_marker.exists()


def test_intake_validation_and_inventory_environment_gate_do_not_import_devices(
    tmp_path: Path,
) -> None:
    workspace = _copy_arrival_workspace(tmp_path)
    _new_prepared(workspace)
    intake, serial_marker, cv2_marker = _run(
        workspace,
        "physical-onboard",
        "intake",
        "--file",
        "hardware/static_overhead_camera/hardware_intake_template.csv",
        "--json",
    )
    intake_result = _json_result(intake)
    assert intake_result["result"]["assessment"]["record_count"] == 55
    assert intake_result["result"]["assessment"]["ready_for_human_review"] is False
    assert not serial_marker.exists()
    assert not cv2_marker.exists()

    inventory, serial_marker, cv2_marker = _run(
        workspace,
        "physical-onboard",
        "inventory",
        "--session-id",
        "cli-arrival-001",
        "--json",
    )
    assert inventory.returncode == 4
    assert "CAPABILITY_DENIED" in inventory.stderr
    assert not serial_marker.exists()
    assert not cv2_marker.exists()


def test_host_doctor_reports_environment_without_importing_device_backends(
    tmp_path: Path,
) -> None:
    workspace = _copy_arrival_workspace(tmp_path)
    runtime, serial_marker, cv2_marker = _run(
        workspace,
        "host-doctor",
        "--profile",
        "runtime",
        "--require-pass",
        "--json",
    )
    result = _json_result(runtime)
    assert result["profile_ready"] is True
    assert result["authority"]["hardware_accessed"] is False
    assert not serial_marker.exists()
    assert not cv2_marker.exists()

    hardware, serial_marker, cv2_marker = _run(
        workspace,
        "host-doctor",
        "--profile",
        "hardware",
        "--require-pass",
        "--json",
    )
    assert hardware.returncode == 4
    assert "WORKSPACE_VIRTUAL_ENVIRONMENT_MISSING" in hardware.stderr
    assert not serial_marker.exists()
    assert not cv2_marker.exists()
