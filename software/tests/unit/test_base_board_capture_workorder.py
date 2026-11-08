from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _load_module(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _arm243_module():
    return _load_module(
        "arm243_gate", "software/integrations/isaac_sim/capture_packet_submission_gate.py"
    )


def _module():
    return _load_module(
        "arm244_workorder",
        "software/integrations/isaac_sim/base_board_capture_workorder.py",
    )


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _report():
    bodies = [
        (
            "installation:base_and_factory_clamp",
            "TAPE_MEASURE_AND_FIXTURE_GAUGE",
            [
                "accepted_source_hash",
                "board_to_base_transform",
                "geometry_uncertainty_mm",
                "installed_clamp_footprint",
                "local_frame_envelope_primitives",
            ],
        ),
        (
            "workcell:board_solid",
            "TAPE_MEASURE_AND_FLATNESS_GAUGE",
            [
                "accepted_source_hash",
                "flatness_or_bow_bound",
                "geometry_uncertainty_mm",
                "installed_board_pose",
                "local_frame_envelope_primitives",
            ],
        ),
    ]
    packets = []
    for index in range(6):
        if index == 3:
            rows = [
                {
                    "body_id": body_id,
                    "parent_frame": "board",
                    "binding_mode": "STATIC_ROOT",
                    "required_acceptance_fields": fields,
                    "relevant_prior_ids": [],
                    "requested_method": method,
                    "current_disposition": "PENDING_CAPTURE_AND_REVIEW",
                }
                for body_id, method, fields in bodies
            ]
            packet_id = "base_board_installation"
            method = "TAPE_MEASURE_AND_FIXTURE_GAUGE"
        else:
            rows = [
                {
                    "body_id": f"other:{index}:0",
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
            ]
            packet_id = f"packet_{index}"
            method = "FIXTURE_GAUGE"
        packets.append(
            {
                "packet_id": packet_id,
                "profile_scope": ["no_attachment", "stylus_attachment"],
                "setup_method": method,
                "body_rows": rows,
                "body_count": len(rows),
                "required_common_metadata": [],
                "capture_completed": False,
            }
        )
    # Add five more unique dummy rows so the ARM-242 total remains exactly 12.
    for index, packet in enumerate(packets):
        if index != 3:
            packet["body_rows"].append(
                {
                    **packet["body_rows"][0],
                    "body_id": f"other:{index}:1",
                }
            )
            packet["body_count"] = 2
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


def _templates(report):
    return _arm243_module().build_submission_templates(
        report, arm242_file_sha256="a" * 64
    )


def _frame_contract():
    return {
        "frames": {
            "B": (
                "RC03 board frame, origin at front-left finished top surface; "
                "+x right, +y rear, +z up"
            )
        }
    }


def _workorder():
    report = _report()
    return _module().build_workorder(
        report,
        _templates(report),
        _frame_contract(),
        arm242_file_sha256="a" * 64,
        arm243_file_sha256="b" * 64,
        frame_contract_file_sha256="c" * 64,
    )


def test_arm244_selects_foundational_static_packet_without_prefill() -> None:
    result = _workorder()

    assert result["status"] == "BLOCKED_OPERATOR_MEASUREMENTS_AND_REVIEW_REQUIRED"
    assert result["selected_packet_id"] == "base_board_installation"
    assert result["profile_scope"] == ["no_attachment", "stylus_attachment"]
    assert result["coordinate_frame_contract"]["frame_id"] == "B"
    assert result["unfilled_acceptance_field_count"] == 10
    assert result["submission_completed"] is False


def test_arm244_preserves_zero_authority_boundary() -> None:
    result = _workorder()

    assert result["measurement_manifest_modified"] is False
    assert result["installed_collision_profile_generated"] is False
    assert result["collision_screening_executed"] is False
    assert result["isaac_started"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False
    assert result["controller_commands"] == []


def test_arm244_covers_exact_packet_fields_and_methods() -> None:
    result = _workorder()

    fields = result["required_acceptance_fields_by_body"]
    assert set(fields) == {
        "installation:base_and_factory_clamp",
        "workcell:board_solid",
    }
    assert "flatness_or_bow_bound" in fields["workcell:board_solid"]
    assert "board_to_base_transform" in fields["installation:base_and_factory_clamp"]
    assert result["capture_sequence"][1]["method"] == "TAPE_MEASURE_AND_FLATNESS_GAUGE"
    assert result["capture_sequence"][2]["method"] == "TAPE_MEASURE_AND_FIXTURE_GAUGE"


@pytest.mark.parametrize("source", ["report", "templates", "frame"])
def test_arm244_rejects_source_contract_drift(source: str) -> None:
    module = _module()
    report = _report()
    templates = _templates(report)
    frame = _frame_contract()
    if source == "report":
        report["physical_authority"] = True
    elif source == "templates":
        templates["submission_templates"][3]["reviewer_decision"] = "ACCEPTED_MEASURED"
    else:
        frame["frames"]["B"] = "different"

    with pytest.raises(module.BaseBoardCaptureWorkorderError):
        module.build_workorder(
            report,
            templates,
            frame,
            arm242_file_sha256="a" * 64,
            arm243_file_sha256="b" * 64,
            frame_contract_file_sha256="c" * 64,
        )


def test_arm244_rejects_non_digest_lineage() -> None:
    module = _module()
    report = _report()
    with pytest.raises(module.BaseBoardCaptureWorkorderError):
        module.build_workorder(
            report,
            _templates(report),
            _frame_contract(),
            arm242_file_sha256="not-a-digest",
            arm243_file_sha256="b" * 64,
            frame_contract_file_sha256="c" * 64,
        )
