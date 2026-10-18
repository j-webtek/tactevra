from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import rocell.calibration.fixed_camera_retained_campaign_manifest_v1 as subject
from rocell.calibration.fixed_camera_retained_campaign_manifest_v1 import (
    FixedCameraRetainedCampaignManifestError,
    compile_fixed_camera_retained_campaign_manifest_v1,
)

from test_fixed_camera_board_pose_extractor_v1 import _tag_map


ZERO_AUTHORITY = {
    "camera_opened": False,
    "robot_provider_called": False,
    "controller_commands": [],
    "motion_targets_emitted": False,
    "motion_authorized": False,
    "contact_authorized": False,
    "physical_release_effect": "NONE",
}


def write(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def pin(path: str, digest: str) -> dict[str, str]:
    return {"path": path, "expected_file_sha256": digest}


def fixture_manifest(root: Path) -> tuple[Path, dict]:
    tag_payload = json.dumps(_tag_map().to_dict(), sort_keys=True).encode()
    tag_hash = write(root / "geometry" / "tag-map.json", tag_payload)
    evidence_hash = write(root / "evidence" / "placeholder.bin", b"retained")
    captures = []
    for index, role in enumerate(("FIT", "FIT", "FIT", "HOLDOUT", "HOLDOUT")):
        capture = {"role": role}
        for name in (
            "bracket_record",
            "jpeg",
            "intrinsics_record",
            "tag_evidence",
            "bare_jaw_calibration",
            "bare_jaw_landmark_evidence",
        ):
            capture[name] = pin("evidence/placeholder.bin", evidence_hash)
        captures.append(capture)
    value = {
        "schema": subject.SCHEMA,
        "status": subject.STATUS,
        "producer_id": "calibration-producer-a",
        "tag_map": pin("geometry/tag-map.json", tag_hash),
        "captures": captures,
        "authority": ZERO_AUTHORITY,
    }
    path = root / "campaign.json"
    write(path, json.dumps(value, sort_keys=True).encode())
    return path, value


def test_compiles_relative_pinned_files_and_builds_review_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _ = fixture_manifest(tmp_path)
    observed: dict[str, object] = {}
    campaign = SimpleNamespace(sha256="a" * 64)
    packet = SimpleNamespace(packet_sha256="b" * 64)

    def compile_campaign(sources: list, *, tag_map: object) -> object:
        observed["sources"] = sources
        observed["tag_map"] = tag_map
        return campaign

    def build_packet(value: object, *, producer_id: str) -> object:
        assert value is campaign
        observed["producer_id"] = producer_id
        return packet

    monkeypatch.setattr(
        subject, "compile_retained_fixed_camera_calibration_campaign_v1", compile_campaign
    )
    monkeypatch.setattr(
        subject, "build_fixed_camera_campaign_review_packet_v1", build_packet
    )

    result = compile_fixed_camera_retained_campaign_manifest_v1(
        path, expected_file_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    )

    assert len(observed["sources"]) == 5  # type: ignore[arg-type]
    assert [source.role for source in observed["sources"]] == [  # type: ignore[union-attr]
        "FIT",
        "FIT",
        "FIT",
        "HOLDOUT",
        "HOLDOUT",
    ]
    assert observed["tag_map"].content_hash == _tag_map().content_hash  # type: ignore[union-attr]
    assert observed["producer_id"] == "calibration-producer-a"
    assert result.campaign is campaign
    assert result.review_packet is packet
    assert result.receipt()["authority"] == ZERO_AUTHORITY


def test_rejects_path_escape_before_compilation(tmp_path: Path) -> None:
    path, value = fixture_manifest(tmp_path)
    value["captures"][0]["jpeg"]["path"] = "../outside.jpg"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(
        FixedCameraRetainedCampaignManifestError,
        match="normalized relative POSIX path",
    ):
        compile_fixed_camera_retained_campaign_manifest_v1(
            path, expected_file_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        )


def test_rejects_tag_map_byte_substitution(tmp_path: Path) -> None:
    path, _ = fixture_manifest(tmp_path)
    (tmp_path / "geometry" / "tag-map.json").write_bytes(b"{}")

    with pytest.raises(
        FixedCameraRetainedCampaignManifestError,
        match="tag map bytes differ",
    ):
        compile_fixed_camera_retained_campaign_manifest_v1(
            path, expected_file_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        )


def test_rejects_nonzero_authority(tmp_path: Path) -> None:
    path, value = fixture_manifest(tmp_path)
    value["authority"]["motion_authorized"] = True
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(
        FixedCameraRetainedCampaignManifestError,
        match="authority must remain exactly zero",
    ):
        compile_fixed_camera_retained_campaign_manifest_v1(
            path, expected_file_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        )
