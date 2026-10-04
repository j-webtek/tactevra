from __future__ import annotations

from copy import deepcopy

import pytest

from rocell.application.camera_arrival_kit_v1 import (
    EVIDENCE_CLASS,
    REQUIRED_SLOT_IDS,
    STATUS,
    CameraArrivalKitV1Error,
    build_camera_arrival_kit_v1,
    validate_camera_arrival_kit_v1,
)


def test_arrival_kit_maps_every_original_and_remains_zero_authority():
    document = build_camera_arrival_kit_v1()
    assert document["status"] == STATUS
    assert document["evidence_class"] == EVIDENCE_CLASS
    assert tuple(slot["artifact_id"] for slot in document["slots"]) == (
        REQUIRED_SLOT_IDS
    )
    assert document["required_slot_count"] == 15
    assert document["measured_slot_count"] == 0
    for slot in document["slots"]:
        assert slot["destination_relative_to_external_evidence_root"]
        assert slot["schema"].endswith("camera_arrival_original_v1.schema.json")
        assert slot["review_fields"] == [
            "reviewer_id", "reviewed_at_utc", "disposition", "review_sha256",
        ]
        assert slot["downstream_consumers"]
        assert slot["physical_original_required"] is True
        assert slot["measured_evidence_sha256"] is None
        assert slot["review_disposition"] == "PENDING_PHYSICAL_ORIGINAL"
    assert document["synthetic_may_populate_measured_slots"] is False
    assert document["configuration_epoch_advanced"] is False
    assert document["deployment_registry_updated"] is False
    assert document["qualification_installed"] is False
    assert document["camera_opened"] is False
    assert document["controller_started"] is False
    assert document["hardware_writes"] == document["physical_movements"] == 0
    assert document["physical_authority"] is False
    assert validate_camera_arrival_kit_v1(document) == document


def test_arrival_kit_is_deterministic_and_hash_bound():
    assert build_camera_arrival_kit_v1() == build_camera_arrival_kit_v1()


@pytest.mark.parametrize(("mutation", "value"), (
    ("measured_slot_count", 1),
    ("configuration_epoch_advanced", True),
    ("deployment_registry_updated", True),
    ("qualification_installed", True),
    ("camera_opened", True),
    ("physical_authority", True),
))
def test_arrival_kit_rejects_synthetic_escalation(mutation: str, value: object):
    document = deepcopy(build_camera_arrival_kit_v1())
    document[mutation] = value
    with pytest.raises(CameraArrivalKitV1Error, match="differs"):
        validate_camera_arrival_kit_v1(document)


def test_arrival_kit_rejects_measured_hash_in_synthetic_slot():
    document = deepcopy(build_camera_arrival_kit_v1())
    document["slots"][0]["measured_evidence_sha256"] = "a" * 64
    with pytest.raises(CameraArrivalKitV1Error, match="differs"):
        validate_camera_arrival_kit_v1(document)
