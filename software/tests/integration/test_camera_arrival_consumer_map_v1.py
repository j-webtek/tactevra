from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.application.camera_arrival_consumer_map_v1 import (
    STATUS,
    build_camera_arrival_consumer_map_v1,
)
from rocell.application.camera_arrival_kit_v1 import REQUIRED_SLOT_IDS


ROOT = Path(__file__).resolve().parents[3]
RETAINED = ROOT / "software/ai/eval/camera_arrival_consumer_map_dry_run_v1.json"
RETAINED_FILE_SHA256 = (
    "d234aa3e54f33e840b90ea88922ea7a111728257b3bbff3a350a4db5a9e2ca6b"
)


def test_every_arrival_slot_resolves_to_hash_bound_existing_consumer():
    report = build_camera_arrival_consumer_map_v1(ROOT)
    assert report["status"] == STATUS
    assert tuple(row["artifact_id"] for row in report["mappings"]) == (
        REQUIRED_SLOT_IDS
    )
    assert report["slot_count"] == 15
    for row in report["mappings"]:
        assert len(row["consumer_source_sha256"]) == 64
        assert len(row["downstream_schema_sha256"]) == 64
        assert row["consumer_binding"]
        assert row["consumer_dependency_resolved"] is True
        assert row["physical_original_present"] is False
        assert row["physical_admission_ready"] is False
    assert report["measured_originals_consumed"] == 0
    assert report["configuration_epoch_advanced"] is False
    assert report["deployment_registry_updated"] is False
    assert report["hardware_access"] is False
    assert report["physical_authority"] is False


def test_consumer_map_is_byte_deterministic_for_same_checkout():
    first = build_camera_arrival_consumer_map_v1(ROOT)
    second = build_camera_arrival_consumer_map_v1(ROOT)
    assert first == second
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == (
        json.dumps(second, sort_keys=True, separators=(",", ":"))
    )


def test_retained_consumer_map_matches_current_checkout_exactly():
    raw = RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RETAINED_FILE_SHA256
    assert raw == raw.rstrip(b"\n") + b"\n"
    assert json.loads(raw) == build_camera_arrival_consumer_map_v1(ROOT)
