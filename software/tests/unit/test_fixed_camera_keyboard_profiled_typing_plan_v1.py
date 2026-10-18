from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

import rocell.application.fixed_camera_keyboard_profiled_typing_plan_v1 as subject
from rocell.application.context import load_simulation_context
from rocell.application.fixed_camera_keyboard_clearance_admission_v1 import (
    ADMITTED_STATUS as CLEARANCE_ADMITTED_STATUS,
    INTAKE_NAME as CLEARANCE_INTAKE_NAME,
    RECEIPT_NAME as CLEARANCE_RECEIPT_NAME,
    ZERO_AUTHORITY as CLEARANCE_ZERO_AUTHORITY,
)
from rocell.application.fixed_camera_keyboard_clearance_intake_v1 import (
    compile_clearance_intake,
)
from rocell.application.fixed_camera_keyboard_profiled_typing_plan_v1 import (
    ADMITTED_STATUS,
    MANIFEST_NAME,
    PLAN_NAMES,
    RECEIPT_NAME,
    FixedCameraKeyboardProfiledTypingPlanV1Error,
    admit_fixed_camera_keyboard_profiled_typing_plans_v1,
)
from rocell.application.typing_execution_plan_v1 import TypingExecutionPlanV1
from rocell.cli import build_parser, main

from test_fixed_camera_keyboard_clearance_intake_v1 import (
    _bindings,
    _localization,
    _profiles,
)
from test_typing_execution_plan_v1 import _batch, _config, _ingress


ROOT = Path(__file__).resolve().parents[3]
SYSTEM_MANIFEST = ROOT / "software/config/system_manifest.json"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _meaning(value: object) -> str:
    return _sha(_canonical(value).rstrip(b"\n"))


def _inputs(tmp_path: Path) -> tuple[dict[str, Path], dict[str, str]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    context = load_simulation_context(ROOT, SYSTEM_MANIFEST)
    localization = _localization()
    installed = _profiles(context)
    intake = compile_clearance_intake(
        localization, _bindings(localization, installed), installed, context=context
    )

    clearance_dir = tmp_path / "clearance"
    clearance_dir.mkdir()
    intake_path = clearance_dir / CLEARANCE_INTAKE_NAME
    intake_bytes = _canonical(intake)
    intake_path.write_bytes(intake_bytes)
    localization_path = tmp_path / "keyboard-robot-localization.json"
    localization_bytes = _canonical(localization)
    localization_path.write_bytes(localization_bytes)
    receipt = {
        "schema": "rocell.fixed_camera_keyboard_clearance_admission_receipt.v1",
        "status": CLEARANCE_ADMITTED_STATUS,
        "sources": {
            "localization": {
                "name": localization_path.name,
                "size_bytes": len(localization_bytes),
                "file_sha256": _sha(localization_bytes),
                "meaning_sha256": _meaning(localization),
            }
        },
        "artifacts": {
            "clearance_intake": {
                "name": CLEARANCE_INTAKE_NAME,
                "size_bytes": len(intake_bytes),
                "file_sha256": _sha(intake_bytes),
                "meaning_sha256": _meaning(intake),
            },
            "completion_receipt": {
                "name": CLEARANCE_RECEIPT_NAME,
                "written_last": True,
            },
        },
        "profile_separation_preserved": True,
        "next_required_stage": (
            "BUILD_PROFILE_SPECIFIC_TYPING_EXECUTION_PLAN_THEN_USE_"
            "TYPING_COLLISION_INTAKE_V1"
        ),
        "authority": dict(CLEARANCE_ZERO_AUTHORITY),
    }
    receipt_path = clearance_dir / CLEARANCE_RECEIPT_NAME
    receipt_bytes = _canonical(receipt)
    receipt_path.write_bytes(receipt_bytes)

    original = _batch()
    proposals = tuple(
        replace(item, target_id=f"K{index:02d}")
        for index, item in enumerate(original.proposals)
    )
    batch = replace(
        original,
        proposals=proposals,
        uncertainty=replace(
            original.uncertainty,
            covered_target_ids=tuple(item.target_id for item in proposals),
        ),
    )
    batch_path = tmp_path / "model-motion-batch.json"
    batch_bytes = _canonical(batch.to_dict())
    batch_path.write_bytes(batch_bytes)
    ingress = _ingress(batch)
    ingress_path = tmp_path / "ingress.json"
    ingress_bytes = _canonical(ingress)
    ingress_path.write_bytes(ingress_bytes)

    bare_config = replace(
        _config(), config_id="fixed-camera-bare-jaw-v1", tool_profile_sha256="4" * 64
    )
    stylus_config = replace(
        _config(), config_id="fixed-camera-stylus-v1", tool_profile_sha256="5" * 64
    )
    bare_config_path = tmp_path / "bare-config.json"
    stylus_config_path = tmp_path / "stylus-config.json"
    bare_config_bytes = _canonical(bare_config.to_dict())
    stylus_config_bytes = _canonical(stylus_config.to_dict())
    bare_config_path.write_bytes(bare_config_bytes)
    stylus_config_path.write_bytes(stylus_config_bytes)

    paths = {
        "receipt": receipt_path,
        "intake": intake_path,
        "localization": localization_path,
        "batch": batch_path,
        "ingress": ingress_path,
        "bare_config": bare_config_path,
        "stylus_config": stylus_config_path,
    }
    payloads = {
        "receipt": receipt_bytes,
        "intake": intake_bytes,
        "localization": localization_bytes,
        "batch": batch_bytes,
        "ingress": ingress_bytes,
        "bare_config": bare_config_bytes,
        "stylus_config": stylus_config_bytes,
    }
    return paths, {name: _sha(payload) for name, payload in payloads.items()}


def _admit(tmp_path: Path, paths: dict[str, Path], hashes: dict[str, str]):
    return admit_fixed_camera_keyboard_profiled_typing_plans_v1(
        paths["receipt"],
        expected_clearance_admission_receipt_file_sha256=hashes["receipt"],
        clearance_intake_path=paths["intake"],
        expected_clearance_intake_file_sha256=hashes["intake"],
        localization_path=paths["localization"],
        expected_localization_file_sha256=hashes["localization"],
        model_motion_batch_path=paths["batch"],
        expected_model_motion_batch_file_sha256=hashes["batch"],
        ingress_report_path=paths["ingress"],
        expected_ingress_report_file_sha256=hashes["ingress"],
        no_attachment_config_path=paths["bare_config"],
        expected_no_attachment_config_file_sha256=hashes["bare_config"],
        stylus_attachment_config_path=paths["stylus_config"],
        expected_stylus_attachment_config_file_sha256=hashes["stylus_config"],
        output_directory=tmp_path / "profiled-plans",
    )


def test_exact_inputs_publish_distinct_plans_manifest_and_receipt_last(tmp_path: Path):
    paths, hashes = _inputs(tmp_path)
    result = _admit(tmp_path, paths, hashes)

    assert result.receipt["status"] == ADMITTED_STATUS
    assert result.manifest_path.name == MANIFEST_NAME
    assert result.receipt_path.name == RECEIPT_NAME
    assert result.receipt["artifacts"]["completion_receipt"]["written_last"] is True
    bare = TypingExecutionPlanV1.from_bytes(
        result.plan_paths["no_attachment"].read_bytes()
    )
    stylus = TypingExecutionPlanV1.from_bytes(
        result.plan_paths["stylus_attachment"].read_bytes()
    )
    assert bare.plan_sha256 != stylus.plan_sha256
    assert [item.target_id for item in bare.actions] == [
        "K00", "K01", "K02", "K03", "K04"
    ]
    assert result.manifest["profiles"]["no_attachment"][
        "typing_execution_plan_name"
    ] == PLAN_NAMES["no_attachment"]
    assert result.manifest["profile_separation_preserved"] is True
    assert result.manifest["physical_authority"] is False
    assert result.receipt["authority"]["trajectory_generated"] is False


def test_unknown_key_or_crossed_localization_fails_without_output(tmp_path: Path):
    paths, hashes = _inputs(tmp_path)
    batch = json.loads(paths["batch"].read_bytes())
    batch["proposals"][0]["target_id"] = "NOT_LOCALIZED"
    batch["uncertainty"]["covered_target_ids"][0] = "NOT_LOCALIZED"
    batch["batch_sha256"] = _meaning(
        {key: value for key, value in batch.items() if key != "batch_sha256"}
    )
    payload = _canonical(batch)
    paths["batch"].write_bytes(payload)
    hashes["batch"] = _sha(payload)
    with pytest.raises(
        FixedCameraKeyboardProfiledTypingPlanV1Error,
        match="outside localized uncertainty coverage",
    ):
        _admit(tmp_path, paths, hashes)
    assert not (tmp_path / "profiled-plans").exists()

    paths, hashes = _inputs(tmp_path / "crossed")
    changed = json.loads(paths["localization"].read_bytes())
    changed["profiles"]["stylus_attachment"][
        "robot_frame_localization_candidates"
    ][0]["key_id"] = "CHANGED"
    payload = _canonical(changed)
    paths["localization"].write_bytes(payload)
    hashes["localization"] = _sha(payload)
    with pytest.raises(
        FixedCameraKeyboardProfiledTypingPlanV1Error,
        match="clearance admission source|clearance intake",
    ):
        _admit(tmp_path / "crossed", paths, hashes)


def test_reused_attachment_config_and_existing_output_fail_closed(tmp_path: Path):
    paths, hashes = _inputs(tmp_path)
    payload = paths["bare_config"].read_bytes()
    paths["stylus_config"].write_bytes(payload)
    hashes["stylus_config"] = _sha(payload)
    with pytest.raises(
        FixedCameraKeyboardProfiledTypingPlanV1Error,
        match="must be distinct",
    ):
        _admit(tmp_path, paths, hashes)

    paths, hashes = _inputs(tmp_path / "existing")
    output = tmp_path / "existing" / "profiled-plans"
    output.mkdir()
    sentinel = output / "sentinel"
    sentinel.write_text("preserve", encoding="utf-8")
    with pytest.raises(
        FixedCameraKeyboardProfiledTypingPlanV1Error,
        match="refusing to overwrite",
    ):
        _admit(tmp_path / "existing", paths, hashes)
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_cli_registers_and_reports_profiled_plan_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "out"
    result = subject.FixedCameraKeyboardProfiledTypingPlanResultV1(
        output_directory=output,
        plan_paths={
            name: output / filename for name, filename in PLAN_NAMES.items()
        },
        manifest_path=output / MANIFEST_NAME,
        receipt_path=output / RECEIPT_NAME,
        manifest={},
        receipt={
            "schema": (
                "rocell.fixed_camera_keyboard_profiled_typing_plan_"
                "admission_receipt.v1"
            ),
            "status": ADMITTED_STATUS,
            "authority": {"physical_release_effect": "NONE"},
        },
    )
    monkeypatch.setattr(
        subject,
        "admit_fixed_camera_keyboard_profiled_typing_plans_v1",
        lambda *_args, **_kwargs: result,
    )
    command = "admit-fixed-camera-keyboard-profiled-typing-plans"
    parser = build_parser()
    assert command in parser._subparsers._group_actions[0].choices
    arguments: list[str] = [command]
    for name in (
        "clearance-admission-receipt",
        "clearance-intake",
        "localization",
        "model-motion-batch",
        "ingress-report",
        "no-attachment-config",
        "stylus-attachment-config",
    ):
        arguments.extend([f"--{name}", str(tmp_path / f"{name}.json")])
        arguments.extend([f"--{name}-sha256", "1" * 64])
    arguments.extend(["--output-directory", str(output), "--json"])

    assert main(arguments) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == ADMITTED_STATUS
    assert report["manifest_path"] == str(output / MANIFEST_NAME)
