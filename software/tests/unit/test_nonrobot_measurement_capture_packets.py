from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    path = ROOT / "software/integrations/isaac_sim/nonrobot_measurement_capture_packets.py"
    spec = importlib.util.spec_from_file_location("arm242_packets", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _inputs():
    module = _module()
    robot_ids = [f"robot:{name}" for name in ["base_link", "gripper", "link1", "link2", "link3", "link4", "link5"]]
    rows = [{"body_id": body_id} for body_id in robot_ids]
    for body_id in sorted(module.NONROBOT_IDS):
        rows.append(
            {
                "body_id": body_id,
                "parent_frame": "board",
                "binding_mode": "STATIC_ROOT",
                "current_status": "PENDING",
                "accepted_measurement_available": False,
                "relevant_prior_ids": ["prior"],
                "missing_acceptance_fields": ["accepted_source_hash", "geometry_uncertainty_mm"],
                "recommended_measurement_method": "FIXTURE_GAUGE",
            }
        )
    gap_core = {
        "schema": "tactevra.isaac_lm4_installed_measurement_gap_matrix.v1",
        "status": "BLOCKED_NO_ACCEPTED_MEASUREMENT_PROMOTIONS",
        "body_gap_matrix": rows,
        "required_body_count": 19,
        "accepted_body_count": 0,
        "pending_body_count": 19,
        "measurement_manifest_modified": False,
        "physical_authority": False,
    }
    review_core = {
        "schema": "tactevra.isaac_lm4_robot_geometry_review_request.v1",
        "status": "BLOCKED_REVIEW_RECORD_REQUIRED",
        "review_body_count": 7,
        "accepted_body_count": 0,
        "pending_robot_body_count": 7,
        "remaining_nonrobot_pending_body_count": 12,
        "measurement_manifest_modified": False,
        "physical_authority": False,
    }
    return (
        {**gap_core, "report_sha256": _sha(gap_core)},
        {**review_core, "request_sha256": _sha(review_core)},
    )


def _report():
    gap, review = _inputs()
    return _module().build_capture_packets(
        gap,
        review,
        arm239_file_sha256="a" * 64,
        arm241_file_sha256="b" * 64,
    )


def test_arm242_covers_twelve_nonrobot_bodies_once_in_six_packets() -> None:
    report = _report()
    body_ids = [
        row["body_id"]
        for packet in report["capture_packets"]
        for row in packet["body_rows"]
    ]

    assert report["status"] == "BLOCKED_SIX_CAPTURE_PACKETS_PENDING"
    assert report["capture_packet_count"] == 6
    assert report["nonrobot_body_count"] == 12
    assert len(body_ids) == len(set(body_ids)) == 12
    assert report["accepted_body_count"] == 0
    assert report["pending_nonrobot_body_count"] == 12


def test_arm242_preserves_exact_attachment_profile_separation() -> None:
    report = _report()
    packets = {packet["packet_id"]: packet for packet in report["capture_packets"]}

    assert packets["contact_tool_tcp"]["profile_scope"] == ["stylus_attachment"]
    assert all(
        packet["profile_scope"] == ["no_attachment", "stylus_attachment"]
        for packet_id, packet in packets.items()
        if packet_id != "contact_tool_tcp"
    )
    assert report["shared_profile_body_count"] == 11
    assert report["stylus_only_body_ids"] == ["attachment:contact_tool"]


def test_arm242_remains_zero_authority_and_nonpromoting() -> None:
    report = _report()

    assert report["robot_review_state_modified"] is False
    assert report["measurement_manifest_modified"] is False
    assert report["installed_collision_profile_generated"] is False
    assert report["collision_screening_executed"] is False
    assert report["isaac_started"] is False
    assert report["hardware_access"] is False
    assert report["physical_authority"] is False
    assert report["controller_commands"] == []


@pytest.mark.parametrize("source", ["gap", "review"])
def test_arm242_rejects_tampered_lineage(source: str) -> None:
    module = _module()
    gap, review = _inputs()
    target = gap if source == "gap" else review
    target["physical_authority"] = True

    with pytest.raises(module.NonrobotCapturePacketError):
        module.build_capture_packets(
            gap,
            review,
            arm239_file_sha256="a" * 64,
            arm241_file_sha256="b" * 64,
        )


def test_arm242_rejects_missing_nonrobot_body() -> None:
    module = _module()
    gap, review = _inputs()
    gap["body_gap_matrix"].pop()
    unsigned = copy.deepcopy(gap)
    unsigned.pop("report_sha256")
    gap["report_sha256"] = _sha(unsigned)

    with pytest.raises(module.NonrobotCapturePacketError):
        module.build_capture_packets(
            gap,
            review,
            arm239_file_sha256="a" * 64,
            arm241_file_sha256="b" * 64,
        )
