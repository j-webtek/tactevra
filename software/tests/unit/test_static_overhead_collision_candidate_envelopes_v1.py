from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell.application.static_overhead_collision_candidate_envelopes_v1 import (
    build_static_overhead_collision_candidate_envelopes_v1,
)


WORKSPACE = Path(__file__).resolve().parents[3]
WORK_ORDER = WORKSPACE / "software/ai/eval/static_overhead_collision_qualification_work_order_20261017.json"


def _work_order_sha256() -> str:
    return hashlib.sha256(WORK_ORDER.read_bytes()).hexdigest()


def test_candidate_envelopes_are_deterministic_complete_and_zero_authority() -> None:
    first = build_static_overhead_collision_candidate_envelopes_v1(WORKSPACE, WORK_ORDER, _work_order_sha256())
    second = build_static_overhead_collision_candidate_envelopes_v1(WORKSPACE, WORK_ORDER, _work_order_sha256())
    rows = {row["body_id"]: row for row in first["body_candidates"]}

    assert first == second
    assert first["required_body_count"] == 19
    assert len(rows) == 19
    assert first["candidate_envelope_body_count"] == 16
    assert first["candidate_board_or_link_frame_placement_body_count"] == 9
    assert first["accepted_uncertainty_body_count"] == 0
    assert first["bodies_without_candidate_envelope"] == [
        "installation:base_and_factory_clamp",
        "installation:static_camera_cable",
        "attachment:contact_tool",
    ]
    assert rows["workcell:board_solid"]["envelope"]["size_mm"] == [610.0, 457.0, 18.0]
    assert rows["workcell:keyboard"]["envelope"]["size_mm"] == [315.0, 147.0, 21.0]
    assert rows["workcell:phone"]["envelope"]["size_mm"] == [77.9, 164.4, 7.9]
    assert rows["workcell:station:keyboard_left"]["envelope"]["size_mm"] == [184.5, 192.0, 7.0]
    assert rows["workcell:station:phone_tcp"]["envelope"]["size_mm"] == [186.300003, 172.800003, 10.5]
    assert rows["installation:static_camera_support"]["envelope"]["size_mm"] == [850.0, 564.5, 1108.900024]
    assert rows["installation:static_camera_module"]["envelope"] == {
        "minimum_mm": [245.0, 180.5, 1000.0],
        "maximum_mm": [365.0, 335.5, 1074.0],
        "size_mm": [120.0, 155.0, 74.0],
    }
    assert rows["installation:static_camera_connector"]["envelope"] == {
        "minimum_mm": [245.0, 187.5, 1068.0],
        "maximum_mm": [365.0, 290.5, 1074.0],
        "size_mm": [120.0, 103.0, 6.0],
    }
    assert rows["attachment:contact_tool"]["attachment_profile"] == "BARE_JAW"
    assert first["repeat_dimension_measurement_body_ids"] == []
    assert first["installed_profile_eligible"] is False
    assert first["profile_generated"] is False
    assert first["collision_screening_executed"] is False
    assert first["controller_commands"] == []
    assert first["hardware_access"] is False
    assert first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_candidate_envelopes_bind_every_source_file() -> None:
    report = build_static_overhead_collision_candidate_envelopes_v1(WORKSPACE, WORK_ORDER, _work_order_sha256())
    assert len(report["source_bindings"]) == 13
    for source in report["source_bindings"]:
        path = WORKSPACE / source["path"]
        assert path.stat().st_size == source["byte_length"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]


def test_candidate_envelopes_reject_work_order_tampering(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="file hash mismatch"):
        build_static_overhead_collision_candidate_envelopes_v1(WORKSPACE, WORK_ORDER, "0" * 64)

    value = json.loads(WORK_ORDER.read_text(encoding="utf-8"))
    value["required_body_count"] = 18
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        build_static_overhead_collision_candidate_envelopes_v1(
            WORKSPACE,
            changed,
            hashlib.sha256(changed.read_bytes()).hexdigest(),
        )
