from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import rocell.application.fixed_camera_keyboard_clearance_admission_v1 as subject
from rocell.application.fixed_camera_keyboard_clearance_admission_v1 import (
    ADMITTED_STATUS,
    INTAKE_NAME,
    RECEIPT_NAME,
    FixedCameraKeyboardClearanceAdmissionError,
    admit_fixed_camera_keyboard_clearance_v1,
)
from rocell.calibration.fixed_camera_keyboard_localization_admission_v1 import (
    ADMITTED_STATUS as LOCALIZATION_ADMITTED_STATUS,
    LOCALIZATION_NAME,
    RECEIPT_NAME as LOCALIZATION_RECEIPT_NAME,
    ZERO_AUTHORITY as LOCALIZATION_ZERO_AUTHORITY,
)
from rocell.cli import build_parser, main
from rocell.application.context import load_simulation_context

from test_fixed_camera_keyboard_clearance_intake_v1 import _localization, _profiles


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "software/config/system_manifest.json"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _meaning(value: object) -> str:
    return _sha(_canonical(value).rstrip(b"\n"))


def _intake() -> dict:
    profiles = {}
    for index, name in enumerate(("no_attachment", "stylus_attachment")):
        profiles[name] = {
            "profile": name,
            "attachment_state": "BARE_JAW" if index == 0 else "STYLUS_INSTALLED",
            "candidate_count": 46,
        }
    return {
        "schema": "rocell.fixed_camera_keyboard_clearance_intake.v1",
        "status": "READY_FOR_PROFILE_SPECIFIC_ROUTE_CONSTRUCTION",
        "profiles": profiles,
        "profile_separation_preserved": True,
        "trajectory_generated": False,
        "collision_screening_executed": False,
        "continuous_clearance_verified": False,
        "controller_commands": [],
        "hardware_access": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "physical_authority": False,
    }


def _retain_inputs(tmp_path: Path) -> tuple[dict[str, Path], dict[str, str]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    localization = _localization()
    admitted = tmp_path / "localization-admission"
    admitted.mkdir()
    localization_path = admitted / LOCALIZATION_NAME
    localization_bytes = _canonical(localization)
    localization_path.write_bytes(localization_bytes)
    receipt = {
        "schema": "rocell.fixed_camera_keyboard_localization_admission_receipt.v1",
        "status": LOCALIZATION_ADMITTED_STATUS,
        "sources": {},
        "review_admission_status": "ACCEPTED",
        "artifacts": {
            "localization": {
                "name": LOCALIZATION_NAME,
                "size_bytes": len(localization_bytes),
                "file_sha256": _sha(localization_bytes),
                "meaning_sha256": _meaning(localization),
                "profile_candidate_counts": {
                    "no_attachment": 46,
                    "stylus_attachment": 46,
                },
            },
            "completion_receipt": {
                "name": LOCALIZATION_RECEIPT_NAME,
                "written_last": True,
            },
        },
        "profile_separation_preserved": True,
        "next_required_stage": "PROFILE_SPECIFIC_INSTALLED_CLEARANCE_INTAKE",
        "authority": dict(LOCALIZATION_ZERO_AUTHORITY),
    }
    receipt_path = admitted / LOCALIZATION_RECEIPT_NAME
    receipt_bytes = _canonical(receipt)
    receipt_path.write_bytes(receipt_bytes)

    tcp_path = tmp_path / "measured-stylus-tcp.json"
    tcp_bytes = _canonical({"schema": "test.measured_tcp.v1", "z_mm": 52.0})
    tcp_path.write_bytes(tcp_bytes)
    bare_profile = {
        "schema": "rocell.installed_collision_geometry_profile.v1",
        "profile_id": "bare-jaw-installed",
        "source_bindings": {"measurement": "1" * 64},
    }
    stylus_profile = {
        "schema": "rocell.installed_collision_geometry_profile.v1",
        "profile_id": "stylus-installed",
        "source_bindings": {"measurement": "2" * 64},
    }
    bare_path = tmp_path / "bare-jaw-profile.json"
    stylus_path = tmp_path / "stylus-profile.json"
    bare_bytes = _canonical(bare_profile)
    stylus_bytes = _canonical(stylus_profile)
    bare_path.write_bytes(bare_bytes)
    stylus_path.write_bytes(stylus_bytes)

    bindings = {
        "schema": "rocell.keyboard_clearance_profile_bindings.v1",
        "status": "REVIEWED_ATTACHMENT_PROFILE_BINDINGS",
        "robot_localization_sha256": _meaning(localization),
        "profiles": [
            {
                "profile": "no_attachment",
                "attachment_state": "BARE_JAW",
                "installed_collision_profile_id": "bare-jaw-installed",
                "installed_collision_profile_file_sha256": _sha(bare_bytes),
                "measured_tcp_sha256": None,
            },
            {
                "profile": "stylus_attachment",
                "attachment_state": "STYLUS_INSTALLED",
                "installed_collision_profile_id": "stylus-installed",
                "installed_collision_profile_file_sha256": _sha(stylus_bytes),
                "measured_tcp_sha256": _sha(tcp_bytes),
            },
        ],
        "review": {
            "reviewed": True,
            "reviewer": "independent reviewer",
            "reviewed_at": "2026-10-18T09:00:00-04:00",
            "notes": "test",
        },
    }
    bindings_path = tmp_path / "profile-bindings.json"
    bindings_bytes = _canonical(bindings)
    bindings_path.write_bytes(bindings_bytes)

    paths = {
        "receipt": receipt_path,
        "localization": localization_path,
        "bindings": bindings_path,
        "bare": bare_path,
        "stylus": stylus_path,
        "tcp": tcp_path,
        "manifest": MANIFEST,
    }
    hashes = {
        "receipt": _sha(receipt_bytes),
        "localization": _sha(localization_bytes),
        "bindings": _sha(bindings_bytes),
        "bare": _sha(bare_bytes),
        "stylus": _sha(stylus_bytes),
        "tcp": _sha(tcp_bytes),
        "manifest": _sha(MANIFEST.read_bytes()),
    }
    return paths, hashes


def _profile_bytes(profile) -> bytes:
    policy = profile.clearance_policy
    value = {
        "schema": "rocell.installed_collision_geometry_profile.v1",
        "profile_id": profile.profile_id,
        "manifest_id": profile.manifest_id,
        "manifest_sha256": profile.manifest_sha256,
        "active_build_id": profile.active_build_id,
        "build_snapshot_sha256": profile.build_snapshot_sha256,
        "robot_model_sha256": profile.robot_model_sha256,
        "base_contract_sha256": profile.base_contract_sha256,
        "source_bindings": dict(profile.source_bindings),
        "bodies": [body.to_dict() for body in profile.contract.bodies],
        "pair_exclusions": [],
        "clearance_policy": {
            "minimum_separation_mm": policy.minimum_separation_mm,
            "geometry_uncertainty_mm_per_body": (
                policy.geometry_uncertainty_mm_per_body
            ),
            "pose_uncertainty_mm_per_body": policy.pose_uncertainty_mm_per_body,
            "evidence_state": policy.evidence_state.value,
            "source_reference": policy.source_reference,
        },
    }
    value["content_sha256"] = _meaning(value)
    return _canonical(value)


def _admit(tmp_path: Path, paths: dict[str, Path], hashes: dict[str, str]):
    return admit_fixed_camera_keyboard_clearance_v1(
        paths["receipt"],
        expected_localization_admission_receipt_file_sha256=hashes["receipt"],
        localization_path=paths["localization"],
        expected_localization_file_sha256=hashes["localization"],
        profile_bindings_path=paths["bindings"],
        expected_profile_bindings_file_sha256=hashes["bindings"],
        bare_jaw_profile_path=paths["bare"],
        expected_bare_jaw_profile_file_sha256=hashes["bare"],
        stylus_profile_path=paths["stylus"],
        expected_stylus_profile_file_sha256=hashes["stylus"],
        stylus_tcp_path=paths["tcp"],
        expected_stylus_tcp_file_sha256=hashes["tcp"],
        workspace=ROOT,
        manifest_path=paths["manifest"],
        expected_manifest_file_sha256=hashes["manifest"],
        output_directory=tmp_path / "clearance-admission",
    )


@pytest.fixture
def compiled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subject, "load_simulation_context", lambda *_args: object())
    monkeypatch.setattr(
        subject,
        "load_installed_collision_geometry_profile_from_bytes_v1",
        lambda payload, digest, **_kwargs: SimpleNamespace(
            payload=payload, file_sha256=digest
        ),
    )
    monkeypatch.setattr(
        subject,
        "compile_clearance_intake",
        lambda *_args, **_kwargs: _intake(),
    )


def test_exact_inputs_publish_profile_separated_receipt_last(
    tmp_path: Path, compiled: None
) -> None:
    paths, hashes = _retain_inputs(tmp_path)
    result = _admit(tmp_path, paths, hashes)

    assert result.intake_path == tmp_path / "clearance-admission" / INTAKE_NAME
    assert result.receipt_path == tmp_path / "clearance-admission" / RECEIPT_NAME
    assert json.loads(result.intake_path.read_bytes()) == result.intake
    receipt = json.loads(result.receipt_path.read_bytes())
    assert receipt == result.receipt
    assert receipt["status"] == ADMITTED_STATUS
    assert receipt["profile_separation_preserved"] is True
    assert receipt["artifacts"]["clearance_intake"][
        "profile_candidate_counts"
    ] == {"no_attachment": 46, "stylus_attachment": 46}
    assert receipt["artifacts"]["completion_receipt"]["written_last"] is True
    assert receipt["authority"]["collision_screening_executed"] is False
    assert receipt["authority"]["physical_release_effect"] == "NONE"


def test_real_context_profile_loader_and_clearance_compiler_are_composed(
    tmp_path: Path,
) -> None:
    paths, hashes = _retain_inputs(tmp_path)
    context = load_simulation_context(ROOT, MANIFEST)
    profiles = _profiles(context)
    for name, key in (("no_attachment", "bare"), ("stylus_attachment", "stylus")):
        payload = _profile_bytes(profiles[name])
        paths[key].write_bytes(payload)
        hashes[key] = _sha(payload)
    bindings = json.loads(paths["bindings"].read_bytes())
    for row in bindings["profiles"]:
        profile = profiles[row["profile"]]
        key = "bare" if row["profile"] == "no_attachment" else "stylus"
        row["installed_collision_profile_id"] = profile.profile_id
        row["installed_collision_profile_file_sha256"] = hashes[key]
    binding_bytes = _canonical(bindings)
    paths["bindings"].write_bytes(binding_bytes)
    hashes["bindings"] = _sha(binding_bytes)

    result = _admit(tmp_path, paths, hashes)

    assert result.intake["status"] == (
        "READY_FOR_PROFILE_SPECIFIC_ROUTE_CONSTRUCTION"
    )
    assert result.intake["profiles"]["no_attachment"]["candidate_count"] == 46
    assert result.intake["profiles"]["stylus_attachment"]["candidate_count"] == 46
    assert result.intake["trajectory_generated"] is False
    assert result.intake["physical_authority"] is False


def test_crossed_localization_tcp_mismatch_and_existing_output_fail_closed(
    tmp_path: Path, compiled: None
) -> None:
    paths, hashes = _retain_inputs(tmp_path)
    crossed = tmp_path / "crossed"
    crossed.mkdir()
    crossed_localization = crossed / LOCALIZATION_NAME
    crossed_localization.write_bytes(paths["localization"].read_bytes())
    paths["localization"] = crossed_localization
    with pytest.raises(
        FixedCameraKeyboardClearanceAdmissionError,
        match="must share one directory",
    ):
        _admit(tmp_path, paths, hashes)

    paths, hashes = _retain_inputs(tmp_path / "tcp-case")
    bindings = json.loads(paths["bindings"].read_bytes())
    changed = copy.deepcopy(bindings)
    changed["profiles"][1]["measured_tcp_sha256"] = "f" * 64
    changed_bytes = _canonical(changed)
    paths["bindings"].write_bytes(changed_bytes)
    hashes["bindings"] = _sha(changed_bytes)
    with pytest.raises(
        FixedCameraKeyboardClearanceAdmissionError,
        match="stylus TCP bytes differ",
    ):
        _admit(tmp_path, paths, hashes)

    paths, hashes = _retain_inputs(tmp_path / "existing-case")
    output = tmp_path / "clearance-admission"
    output.mkdir()
    sentinel = output / "sentinel"
    sentinel.write_text("preserve", encoding="utf-8")
    with pytest.raises(
        FixedCameraKeyboardClearanceAdmissionError,
        match="refusing to overwrite",
    ):
        _admit(tmp_path, paths, hashes)
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_changed_profile_hash_publishes_nothing(
    tmp_path: Path, compiled: None
) -> None:
    paths, hashes = _retain_inputs(tmp_path)
    hashes["bare"] = "0" * 64
    with pytest.raises(
        FixedCameraKeyboardClearanceAdmissionError,
        match="differ from expected",
    ):
        _admit(tmp_path, paths, hashes)
    assert not (tmp_path / "clearance-admission").exists()


def test_cli_registers_and_reports_clearance_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "out"
    result = SimpleNamespace(
        receipt={
            "schema": "rocell.fixed_camera_keyboard_clearance_admission_receipt.v1",
            "status": ADMITTED_STATUS,
            "authority": {"physical_release_effect": "NONE"},
        },
        output_directory=output,
        intake_path=output / INTAKE_NAME,
        receipt_path=output / RECEIPT_NAME,
    )
    monkeypatch.setattr(
        subject,
        "admit_fixed_camera_keyboard_clearance_v1",
        lambda *_args, **_kwargs: result,
    )
    arguments = (
        "--workspace",
        str(ROOT),
        "admit-fixed-camera-keyboard-clearance",
        "--localization-admission-receipt",
        str(tmp_path / LOCALIZATION_RECEIPT_NAME),
        "--localization-admission-receipt-sha256",
        "a" * 64,
        "--localization",
        str(tmp_path / LOCALIZATION_NAME),
        "--localization-sha256",
        "b" * 64,
        "--profile-bindings",
        str(tmp_path / "bindings.json"),
        "--profile-bindings-sha256",
        "c" * 64,
        "--bare-jaw-profile",
        str(tmp_path / "bare.json"),
        "--bare-jaw-profile-sha256",
        "d" * 64,
        "--stylus-profile",
        str(tmp_path / "stylus.json"),
        "--stylus-profile-sha256",
        "e" * 64,
        "--stylus-tcp",
        str(tmp_path / "tcp.json"),
        "--stylus-tcp-sha256",
        "f" * 64,
        "--system-manifest-sha256",
        "1" * 64,
        "--output-directory",
        str(output),
        "--json",
    )
    parsed = build_parser().parse_args(arguments)
    assert parsed.handler.__name__ == (
        "_command_admit_fixed_camera_keyboard_clearance"
    )
    assert main(arguments) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == ADMITTED_STATUS
    assert report["clearance_intake_path"] == str(output / INTAKE_NAME)
