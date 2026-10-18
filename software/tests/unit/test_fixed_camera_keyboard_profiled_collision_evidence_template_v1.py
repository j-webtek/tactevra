from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell.application.fixed_camera_keyboard_profiled_collision_evidence_template_v1 import (
    MANIFEST_NAME,
    RECEIPT_NAME,
    RECEIPT_STATUS,
    STATUS,
    TEMPLATE_NAMES,
    TEMPLATE_STATUS,
    FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error,
    render_fixed_camera_keyboard_profiled_collision_evidence_templates_v1,
)

from test_fixed_camera_keyboard_profiled_collision_partitions_v1 import (
    PROFILES,
    _call as partition_call,
    _route_screen,
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bundle, route_screen = _route_screen(tmp_path, monkeypatch)
    return partition_call(tmp_path, bundle, route_screen)


def _call(tmp_path: Path, source):
    return render_fixed_camera_keyboard_profiled_collision_evidence_templates_v1(
        source.receipt_path,
        expected_collision_partitions_receipt_file_sha256=_sha(
            source.receipt_path.read_bytes()
        ),
        collision_partitions_manifest_path=source.manifest_path,
        expected_collision_partitions_manifest_file_sha256=_sha(
            source.manifest_path.read_bytes()
        ),
        partition_intake_paths=source.partition_paths,
        expected_partition_intake_file_sha256={
            profile: _sha(source.partition_paths[profile].read_bytes())
            for profile in PROFILES
        },
        output_directory=tmp_path / "profiled-collision-evidence-template",
    )


def test_partition_bundle_renders_exact_separate_blank_evidence_templates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, monkeypatch)

    result = _call(tmp_path, source)

    assert result.manifest["status"] == STATUS
    assert result.receipt["status"] == RECEIPT_STATUS
    assert result.manifest_path.name == MANIFEST_NAME
    assert result.receipt_path.name == RECEIPT_NAME
    assert result.receipt["artifacts"]["completion_receipt"]["written_last"] is True
    assert result.manifest["all_measurement_fields_blank"] is True
    assert result.manifest["authority"]["physical_authority"] is False
    assert (
        result.templates["no_attachment"]["installed_collision_profile_sha256"]
        != result.templates["stylus_attachment"]["installed_collision_profile_sha256"]
    )
    for profile in PROFILES:
        template = result.templates[profile]
        source_report = json.loads(source.partition_paths[profile].read_bytes())
        assert result.template_paths[profile].name == TEMPLATE_NAMES[profile]
        assert template["status"] == TEMPLATE_STATUS
        assert (
            template["source_partitioned_typing_collision_intake_sha256"]
            == (source_report["partitioned_typing_collision_intake_sha256"])
        )
        assert template["authority"]["hardware_access"] is False
        assert (
            template["required_evidence_slots"]["configuration_geometry_binding_count"]
            == source_report["required_evidence_slots"][
                "configuration_geometry_binding_count"
            ]
        )
        assert (
            template["required_evidence_slots"]["configuration_sweep_envelope_count"]
            == source_report["required_evidence_slots"][
                "configuration_sweep_envelope_count"
            ]
        )
        assert all(
            row["anchor_t_parent"] is None
            and row["source_sha256"] is None
            and row["evidence_state"] == "REQUIRED_MEASURED_INPUT"
            for row in template["rigid_attachment_bindings"]
        )
        geometry_rows = [
            body
            for partition in template["partitions"]
            for sample in partition["configuration_samples"]
            for body in sample["geometry_by_body"]
        ]
        sweep_rows = [
            body
            for partition in template["partitions"]
            for segment in partition["configuration_sweep_envelopes"]
            for body in segment["envelope_by_body"]
        ]
        assert (
            len(geometry_rows)
            == template["required_evidence_slots"][
                "configuration_geometry_binding_count"
            ]
        )
        assert (
            len(sweep_rows)
            == template["required_evidence_slots"]["configuration_sweep_envelope_count"]
        )
        assert all(row["geometry_root_frame"] is None for row in geometry_rows)
        assert all(row["source_sha256"] is None for row in sweep_rows)


def test_tampered_partition_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, monkeypatch)
    path = source.partition_paths["no_attachment"]
    changed = json.loads(path.read_bytes())
    changed["required_evidence_slots"]["configuration_geometry_binding_count"] += 1
    path.write_text(json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n")

    with pytest.raises(
        FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error,
        match="differs|invalid",
    ):
        _call(tmp_path, source)
    assert not (tmp_path / "profiled-collision-evidence-template").exists()


def test_crossed_profile_partition_paths_fail_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, monkeypatch)
    crossed = {
        "no_attachment": source.partition_paths["stylus_attachment"],
        "stylus_attachment": source.partition_paths["no_attachment"],
    }

    with pytest.raises(
        FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error,
        match="named co-located bundle|binding differs",
    ):
        render_fixed_camera_keyboard_profiled_collision_evidence_templates_v1(
            source.receipt_path,
            expected_collision_partitions_receipt_file_sha256=_sha(
                source.receipt_path.read_bytes()
            ),
            collision_partitions_manifest_path=source.manifest_path,
            expected_collision_partitions_manifest_file_sha256=_sha(
                source.manifest_path.read_bytes()
            ),
            partition_intake_paths=crossed,
            expected_partition_intake_file_sha256={
                profile: _sha(crossed[profile].read_bytes()) for profile in PROFILES
            },
            output_directory=tmp_path / "profiled-collision-evidence-template",
        )
    assert not (tmp_path / "profiled-collision-evidence-template").exists()


def test_existing_destination_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, monkeypatch)
    destination = tmp_path / "profiled-collision-evidence-template"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep")

    with pytest.raises(
        FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error,
        match="already exists",
    ):
        _call(tmp_path, source)
    assert sentinel.read_text() == "keep"
