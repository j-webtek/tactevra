from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from rocell.application.camera_arrival_consumer_handoff_v1 import (
    build_camera_arrival_consumer_handoff_v1,
)
from rocell.application.camera_arrival_kit_v1 import build_camera_arrival_kit_v1
from rocell.application.immutable_camera_replay_v1 import (
    ImmutableCameraReplayV1Error,
    build_immutable_camera_replay_manifest_v1,
    parse_immutable_camera_replay_manifest_v1,
    parse_immutable_camera_replay_report_v1,
    run_immutable_camera_replay_v1,
)


ROOT = Path(__file__).resolve().parents[3]
H = "a" * 64
MODEL = "b" * 64
WHEN = "2026-09-29T17:00:00Z"
SCRIPT = ROOT / "software/scripts/run_immutable_camera_replay_v1.py"
MANIFEST_VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/immutable_camera_replay_manifest_v1.schema.json"
).read_text(encoding="utf-8")), format_checker=FormatChecker())
REPORT_VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/immutable_camera_replay_report_v1.schema.json"
).read_text(encoding="utf-8")))


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _populate_arrival(root: Path) -> None:
    for slot in build_camera_arrival_kit_v1()["slots"]:
        relative = f"sources/{slot['artifact_id']}.bin"
        payload = slot["artifact_id"].encode()
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(payload)
        uncertainty = None if not slot["uncertainty_required"] else {
            "value": 0.1, "unit": slot["required_units"][0],
            "method": "synthetic replay fixture", "evidence_sha256": H,
        }
        sidecar = root / slot["destination_relative_to_external_evidence_root"]
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_bytes(_canonical({
            "schema": "rocell.camera_arrival_original.v1",
            "artifact_id": slot["artifact_id"],
            "artifact_class": slot["artifact_class"],
            "captured_at_utc": "2026-09-29T12:00:00Z",
            "source_relative_path": relative, "source_size_bytes": len(payload),
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "units": slot["required_units"], "uncertainty": uncertainty,
            "configuration_epoch_id": "camera-epoch-001",
            "review": {
                "reviewer_id": "synthetic-replay-review",
                "reviewed_at_utc": "2026-09-29T13:00:00Z",
                "disposition": "ACCEPTED", "review_sha256": H,
            },
        }))


def _fixture(root: Path, *, source_class: str = "SYNTHETIC_FIXTURE"):
    arrival = root / "arrival"
    replay = root / "replay"
    arrival.mkdir()
    replay.mkdir()
    _populate_arrival(arrival)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, arrival)
    (replay / "frame.bin").write_bytes(b"synthetic immutable camera frame")
    metadata_core = {
        "schema": "rocell.immutable_camera_capture_metadata.v1",
        "capture_id": "capture-001", "captured_at_utc": WHEN,
        "source_evidence_class": source_class,
        "camera_profile_sha256": "1" * 64,
        "support_profile_sha256": "2" * 64,
        "calibration_sha256": "3" * 64,
    }
    (replay / "metadata.json").write_bytes(_canonical({
        **metadata_core, "metadata_sha256": _hash(metadata_core),
    }))
    campaign_core = {
        "schema": "rocell.physical_camera_localization_campaign_preflight.v1",
        "status": "READY_FOR_OFFLINE_EVALUATION", "camera_opened": False,
        "model_loaded": False, "controller_started": False,
        "hardware_writes": 0, "physical_movements": 0,
        "qualification_installed": False,
    }
    (replay / "campaign.json").write_bytes(_canonical({
        **campaign_core, "receipt_sha256": _hash(campaign_core),
    }))
    localization_core = {
        "schema": "rocell.physical_camera_localization_evaluation_result.v1",
        "status": "QUALIFICATION_BLOCKED", "model_sha256": MODEL,
        "criteria": {
            "held_out_coverage_met": False,
            "unsafe_false_accepts_zero": True,
        },
        "qualification_installed": False,
        "physical_deployment_qualified": False,
        "model_motion_batch_emitted": False, "controller_started": False,
        "hardware_writes": 0, "physical_movements": 0,
    }
    (replay / "localization.json").write_bytes(_canonical({
        **localization_core, "result_sha256": _hash(localization_core),
    }))
    manifest = build_immutable_camera_replay_manifest_v1(
        handoff, replay_root=replay, replay_id="replay-001",
        source_evidence_class=source_class,
        camera_profile_sha256="1" * 64, support_profile_sha256="2" * 64,
        model_sha256=MODEL, calibration_sha256="3" * 64,
        validated_at_utc=WHEN,
        captures=({
            "capture_id": "capture-001", "image_relative_path": "frame.bin",
            "metadata_relative_path": "metadata.json",
        },),
        campaign_output_relative_path="campaign.json",
        localization_output_relative_path="localization.json",
    )
    return replay, handoff, manifest


def _rehash_manifest(value: dict) -> None:
    core = {key: item for key, item in value.items() if key != "manifest_sha256"}
    value["manifest_sha256"] = _hash(core)


def test_identical_frozen_inputs_reproduce_existing_consumer_decisions(tmp_path: Path):
    replay, handoff, manifest = _fixture(tmp_path)
    first = run_immutable_camera_replay_v1(
        manifest, replay_root=replay, handoff=handoff
    )
    second = run_immutable_camera_replay_v1(
        manifest, replay_root=replay, handoff=handoff
    )
    assert first == second
    assert list(MANIFEST_VALIDATOR.iter_errors(manifest)) == []
    assert list(REPORT_VALIDATOR.iter_errors(first)) == []
    assert dict(parse_immutable_camera_replay_manifest_v1(manifest)) == manifest
    assert dict(parse_immutable_camera_replay_report_v1(first)) == first
    assert first["decision_status"] == {
        "localization_campaign": "PASS",
        "localization_evaluation": "BLOCKED",
    }
    assert first["source_evidence_class"] == "SYNTHETIC_FIXTURE"
    assert first["identical_replay_confirmed"] is True
    assert first["live_camera_opened"] is first["physical_authority"] is False
    assert first["controller_commands"] == []


@pytest.mark.parametrize("target", ("image", "metadata", "campaign", "localization"))
def test_changed_frozen_file_bytes_reject(tmp_path: Path, target: str):
    replay, handoff, manifest = _fixture(tmp_path)
    filename = {
        "image": "frame.bin", "metadata": "metadata.json",
        "campaign": "campaign.json", "localization": "localization.json",
    }[target]
    with (replay / filename).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ImmutableCameraReplayV1Error, match="bytes differ"):
        run_immutable_camera_replay_v1(manifest, replay_root=replay, handoff=handoff)


@pytest.mark.parametrize("mutation", ("model", "calibration", "receipt", "authority"))
def test_rehashed_identity_or_authority_mutations_reject(tmp_path: Path, mutation: str):
    replay, handoff, manifest = _fixture(tmp_path)
    value = json.loads(json.dumps(manifest))
    if mutation == "model":
        value["model_sha256"] = "4" * 64
    elif mutation == "calibration":
        value["calibration_sha256"] = "4" * 64
    elif mutation == "receipt":
        value["expected_receipt_sha256"]["localization_campaign"] = "4" * 64
    else:
        value["physical_authority"] = True
    _rehash_manifest(value)
    with pytest.raises(ImmutableCameraReplayV1Error):
        run_immutable_camera_replay_v1(value, replay_root=replay, handoff=handoff)


def test_original_capture_provenance_remains_replay_not_new_capture(tmp_path: Path):
    replay, handoff, manifest = _fixture(
        tmp_path, source_class="ORIGINAL_CAPTURE"
    )
    report = run_immutable_camera_replay_v1(
        manifest, replay_root=replay, handoff=handoff
    )
    assert report["source_evidence_class"] == "ORIGINAL_CAPTURE"
    assert report["replay_evidence_class"] == "IMMUTABLE_REPLAY"
    assert report["live_camera_opened"] is False


def test_cli_runs_same_manifest_without_camera_or_controller(tmp_path: Path):
    replay, handoff, manifest = _fixture(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    handoff_path = tmp_path / "handoff.json"
    manifest_path.write_bytes(_canonical(manifest))
    handoff_path.write_bytes(_canonical(handoff))
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(ROOT / "software/src"), str(ROOT / "software"))
    )
    result = subprocess.run(
        (
            sys.executable, str(SCRIPT), "--manifest", str(manifest_path),
            "--replay-root", str(replay), "--handoff", str(handoff_path),
        ),
        capture_output=True, check=False, encoding="utf-8", env=environment,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["identical_replay_confirmed"] is True
    assert report["live_camera_opened"] is False
    assert report["hardware_writes"] == report["physical_movements"] == 0
