from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell.application.collision_readiness import assess_current_collision_readiness
from rocell.application.context import load_simulation_context
from rocell.simulation.collision import CollisionAttachmentProfile


ROOT = Path(__file__).resolve().parents[3]
SYSTEM_MANIFEST = ROOT / "software/config/system_manifest.json"


def _module():
    import importlib.util

    path = (
        ROOT
        / "software/integrations/isaac_sim/installed_collision_measurement_intake.py"
    )
    spec = importlib.util.spec_from_file_location("arm238_intake", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _plan() -> dict[str, object]:
    core: dict[str, object] = {
        "schema": (
            "tactevra.isaac_lm4_state_policy_lifted_route_geometry_intake_plan.v1"
        ),
        "status": "BLOCKED_PENDING_HASH_BOUND_INSTALLED_GEOMETRY",
        "target_id": "SPACE",
        "known_provisional_target_surface": {
            "coordinate_frame": "board",
            "center_board_xy_mm": [224.0, 112.0],
            "half_extent_xy_mm": [48.0, 7.0],
            "target_plane_z_board_mm": 21.0,
            "volume_complete": False,
            "accepted_measured": False,
            "source_state": "SYNTHETIC_BOUNDED_PRIOR_NOT_PRODUCT_SPECIFICATION",
        },
        "corrected_cartesian_route_materialized": False,
        "physical_authority": False,
        "next_required_stage": (
            "BUILD_HASH_BOUND_INSTALLED_COLLISION_MEASUREMENT_MANIFEST"
        ),
    }
    return {**core, "plan_sha256": _sha(core)}


def _readiness(profile: CollisionAttachmentProfile):
    context = load_simulation_context(ROOT, SYSTEM_MANIFEST)
    return assess_current_collision_readiness(context, attachment_profile=profile)


def test_arm238_inventory_is_hash_bound_blocked_and_zero_authority() -> None:
    module = _module()
    profile = CollisionAttachmentProfile.STYLUS_ATTACHMENT
    manifest, validation, receipt = module.build_intake_package(
        _plan(),
        _readiness(profile),
        attachment_profile=profile,
        captured_at_utc="2026-11-07T21:10:00Z",
        reference_artifacts=[{
            "reference_id": "ruler/one.jpg",
            "sha256": "a" * 64,
            "byte_count": 10,
            "classification": "REFERENCE_ONLY_NOT_ACCEPTED_MEASUREMENT",
        }],
    )

    assert manifest["sources"] == []
    assert len(manifest["body_measurements"]) == 19
    assert {row["status"] for row in manifest["body_measurements"]} == {"PENDING"}
    assert validation["status"] == "BLOCKED_INCOMPLETE_INSTALLED_MEASUREMENTS"
    assert validation["measured_body_count"] == 0
    assert len(validation["pending_body_ids"]) == 19
    assert receipt["status"] == (
        "BLOCKED_PENDING_ACCEPTED_INSTALLED_MEASUREMENTS"
    )
    assert receipt["source_arm237_plan_sha256"] == _plan()["plan_sha256"]
    assert receipt["reference_evidence_promoted_to_measurement"] is False
    assert receipt["installed_collision_profile_generated"] is False
    assert receipt["collision_screening_executed"] is False
    assert receipt["controller_commands"] == []
    assert receipt["hardware_access"] is False
    assert receipt["physical_authority"] is False


def test_arm238_preserves_attachment_profile_separation() -> None:
    module = _module()
    no_attachment = CollisionAttachmentProfile.NO_ATTACHMENT
    stylus = CollisionAttachmentProfile.STYLUS_ATTACHMENT
    no_manifest, no_validation, no_receipt = module.build_intake_package(
        _plan(),
        _readiness(no_attachment),
        attachment_profile=no_attachment,
        captured_at_utc="2026-11-07T21:10:00Z",
    )
    stylus_manifest, stylus_validation, stylus_receipt = module.build_intake_package(
        _plan(),
        _readiness(stylus),
        attachment_profile=stylus,
        captured_at_utc="2026-11-07T21:10:00Z",
    )

    assert no_validation["required_body_count"] == 18
    assert stylus_validation["required_body_count"] == 19
    assert no_manifest["base_contract_sha256"] != stylus_manifest[
        "base_contract_sha256"
    ]
    assert no_receipt["receipt_sha256"] != stylus_receipt["receipt_sha256"]
    assert "attachment:contact_tool" not in no_validation["pending_body_ids"]
    assert "attachment:contact_tool" in stylus_validation["pending_body_ids"]


def test_arm238_hashes_and_deduplicates_reference_photos(tmp_path: Path) -> None:
    module = _module()
    first = tmp_path / "one.jpg"
    duplicate = tmp_path / "two.jpg"
    first.write_bytes(b"same-photo")
    duplicate.write_bytes(b"same-photo")

    rows = module.hash_reference_artifacts([first, duplicate])

    assert len(rows) == 1
    assert rows[0]["sha256"] == hashlib.sha256(b"same-photo").hexdigest()
    assert rows[0]["classification"] == (
        "REFERENCE_ONLY_NOT_ACCEPTED_MEASUREMENT"
    )


def test_arm238_retained_manifest_file_matches_validated_file_hash(
    tmp_path: Path,
) -> None:
    module = _module()
    profile = CollisionAttachmentProfile.STYLUS_ATTACHMENT
    manifest, validation, _ = module.build_intake_package(
        _plan(),
        _readiness(profile),
        attachment_profile=profile,
        captured_at_utc="2026-11-07T21:10:00Z",
    )
    path = tmp_path / "measurement_manifest.json"

    module._write_canonical_json(path, manifest)

    assert hashlib.sha256(path.read_bytes()).hexdigest() == validation[
        "measurement_manifest_file_sha256"
    ]


def test_arm238_rejects_tampered_plan_and_promoted_reference() -> None:
    module = _module()
    profile = CollisionAttachmentProfile.STYLUS_ATTACHMENT
    tampered = _plan()
    tampered["target_id"] = "ENTER"
    with pytest.raises(module.InstalledCollisionMeasurementIntakeError):
        module.build_intake_package(
            tampered,
            _readiness(profile),
            attachment_profile=profile,
            captured_at_utc="2026-11-07T21:10:00Z",
        )

    with pytest.raises(
        module.InstalledCollisionMeasurementIntakeError,
        match="classification changed",
    ):
        module.build_intake_package(
            _plan(),
            _readiness(profile),
            attachment_profile=profile,
            captured_at_utc="2026-11-07T21:10:00Z",
            reference_artifacts=[{
                "reference_id": "ruler/one.jpg",
                "sha256": "a" * 64,
                "byte_count": 10,
                "classification": "ACCEPTED_MEASURED",
            }],
        )
