from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    path = ROOT / "software/integrations/isaac_sim/capture_packet_submission_gate.py"
    spec = importlib.util.spec_from_file_location("arm243_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _packet_report():
    packets = []
    for index in range(6):
        body_count = 2
        body_rows = []
        for offset in range(body_count):
            body_rows.append(
                {
                    "body_id": f"body:{index}:{offset}",
                    "parent_frame": "board",
                    "binding_mode": "STATIC_ROOT",
                    "required_acceptance_fields": [
                        "accepted_source_hash",
                        "geometry_uncertainty_mm",
                        "local_frame_envelope_primitives",
                    ],
                    "relevant_prior_ids": [],
                    "requested_method": "FIXTURE_GAUGE",
                    "current_disposition": "PENDING_CAPTURE_AND_REVIEW",
                }
            )
        packets.append(
            {
                "packet_id": f"packet_{index}",
                "profile_scope": ["no_attachment", "stylus_attachment"],
                "setup_method": "FIXTURE_GAUGE",
                "body_rows": body_rows,
                "body_count": body_count,
                "required_common_metadata": [],
                "capture_completed": False,
            }
        )
    core = {
        "schema": "tactevra.isaac_lm4_nonrobot_measurement_capture_packets.v1",
        "status": "BLOCKED_SIX_CAPTURE_PACKETS_PENDING",
        "capture_packets": packets,
        "capture_packet_count": 6,
        "nonrobot_body_count": 12,
        "shared_profile_body_count": 11,
        "stylus_only_body_count": 1,
        "accepted_body_count": 0,
        "pending_nonrobot_body_count": 12,
        "measurement_manifest_modified": False,
        "physical_authority": False,
    }
    return {**core, "report_sha256": _sha(core)}


def _templates():
    return _module().build_submission_templates(
        _packet_report(), arm242_file_sha256="a" * 64
    )


def _submission():
    template = copy.deepcopy(_templates()["submission_templates"][0])
    template["evidence_sources"] = [
        {"source_file_sha256": "e" * 64, "source_reference": "metrology record"}
    ]
    template["instrument_identity"] = "unit-test caliper"
    template["instrument_resolution_mm"] = 0.1
    template["coordinate_frame"] = "board"
    template["reviewer"] = "unit-test reviewer"
    template["reviewer_decision"] = "ACCEPTED_MEASURED"
    for row in template["body_submissions"]:
        row["acceptance_values"] = {
            "accepted_source_hash": "e" * 64,
            "geometry_uncertainty_mm": 0.5,
            "local_frame_envelope_primitives": [
                {"kind": "sphere", "center_mm": [0.0, 0.0, 0.0], "radius_mm": 1.0}
            ],
        }
    unsigned = dict(template)
    unsigned.pop("submission_sha256")
    template["submission_sha256"] = _sha(unsigned)
    return template


def test_arm243_materializes_six_uncompleted_templates() -> None:
    result = _templates()

    assert result["status"] == "BLOCKED_CAPTURE_SUBMISSIONS_REQUIRED"
    assert result["template_count"] == 6
    assert result["completed_submission_count"] == 0
    assert result["eligible_body_count"] == 0
    assert result["pending_nonrobot_body_count"] == 12
    assert all(
        template["reviewer_decision"] == "PENDING"
        and template["submission_sha256"] is None
        for template in result["submission_templates"]
    )


def test_arm243_accepts_one_complete_packet_as_eligibility_only() -> None:
    assessment = _module().assess_submission(_packet_report(), _submission())

    assert assessment["eligible_body_count"] == 2
    assert assessment["remaining_packets_unassessed"] == 5
    assert assessment["measurement_manifest_modified"] is False
    assert assessment["installed_collision_profile_generated"] is False
    assert assessment["collision_screening_executed"] is False
    assert assessment["physical_authority"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "zero_uncertainty",
        "wrong_source",
        "missing_body",
        "pending_review",
        "invalid_box_rotation",
    ],
)
def test_arm243_rejects_incomplete_or_unaccepted_submission(mutation: str) -> None:
    module = _module()
    submission = _submission()
    if mutation == "zero_uncertainty":
        submission["body_submissions"][0]["acceptance_values"][
            "geometry_uncertainty_mm"
        ] = 0.0
    elif mutation == "wrong_source":
        submission["body_submissions"][0]["acceptance_values"][
            "accepted_source_hash"
        ] = "f" * 64
    elif mutation == "missing_body":
        submission["body_submissions"].pop()
    elif mutation == "pending_review":
        submission["reviewer_decision"] = "PENDING"
    else:
        submission["body_submissions"][0]["acceptance_values"][
            "local_frame_envelope_primitives"
        ] = [
            {
                "kind": "oriented_box",
                "center_mm": [0.0, 0.0, 0.0],
                "half_extents_mm": [1.0, 1.0, 1.0],
                "rotation_row_major": [1.0, 0.0, 0.0],
            }
        ]
    unsigned = dict(submission)
    unsigned.pop("submission_sha256")
    submission["submission_sha256"] = _sha(unsigned)

    with pytest.raises(module.CapturePacketSubmissionError):
        module.assess_submission(_packet_report(), submission)


def test_arm243_rejects_tampered_packet_report() -> None:
    module = _module()
    report = _packet_report()
    report["physical_authority"] = True

    with pytest.raises(module.CapturePacketSubmissionError):
        module.build_submission_templates(report, arm242_file_sha256="a" * 64)
