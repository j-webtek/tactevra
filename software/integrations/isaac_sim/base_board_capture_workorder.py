"""Build the ARM-244 base/board measurement capture work order.

This offline boundary selects the fixed base/board packet from ARM-242 and
binds it to the exact blank ARM-243 submission template and maintained board
frame contract. It prepares measurement and review instructions but does not
claim that any observation has been made.

No simulator, GPU, device, controller, or physical motion is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


ARM242_SCHEMA = "tactevra.isaac_lm4_nonrobot_measurement_capture_packets.v1"
ARM242_STATUS = "BLOCKED_SIX_CAPTURE_PACKETS_PENDING"
ARM243_SCHEMA = "tactevra.isaac_lm4_capture_submission_templates.v1"
ARM243_STATUS = "BLOCKED_CAPTURE_SUBMISSIONS_REQUIRED"
SUBMISSION_SCHEMA = "tactevra.isaac_lm4_capture_packet_submission.v1"
WORKORDER_SCHEMA = "tactevra.isaac_lm4_base_board_capture_workorder.v1"
PACKET_ID = "base_board_installation"
FRAME_ID = "B"
FRAME_DEFINITION = (
    "RC03 board frame, origin at front-left finished top surface; "
    "+x right, +y rear, +z up"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BaseBoardCaptureWorkorderError(ValueError):
    """A source contract or selected packet is not the expected immutable input."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BaseBoardCaptureWorkorderError("document is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BaseBoardCaptureWorkorderError(f"{label} must be a SHA-256 digest")
    return value


def _validated_report(report: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    unsigned = dict(report)
    claimed = unsigned.pop("report_sha256", None)
    packets = report.get("capture_packets")
    if (
        report.get("schema") != ARM242_SCHEMA
        or report.get("status") != ARM242_STATUS
        or not isinstance(claimed, str)
        or claimed != _sha(unsigned)
        or not isinstance(packets, list)
        or len(packets) != 6
        or report.get("capture_packet_count") != 6
        or report.get("nonrobot_body_count") != 12
        or report.get("accepted_body_count") != 0
        or report.get("measurement_manifest_modified") is not False
        or report.get("physical_authority") is not False
    ):
        raise BaseBoardCaptureWorkorderError("ARM-242 packet report changed")
    matches = [packet for packet in packets if packet.get("packet_id") == PACKET_ID]
    if len(matches) != 1:
        raise BaseBoardCaptureWorkorderError("base/board packet coverage changed")
    packet = matches[0]
    expected_bodies = {
        "installation:base_and_factory_clamp",
        "workcell:board_solid",
    }
    rows = packet.get("body_rows")
    if (
        packet.get("profile_scope") != ["no_attachment", "stylus_attachment"]
        or packet.get("setup_method") != "TAPE_MEASURE_AND_FIXTURE_GAUGE"
        or not isinstance(rows, list)
        or {row.get("body_id") for row in rows} != expected_bodies
        or packet.get("capture_completed") is not False
    ):
        raise BaseBoardCaptureWorkorderError("base/board packet contract changed")
    return claimed, packet


def _validated_template_set(
    templates: Mapping[str, Any], report_hash: str, packet: Mapping[str, Any]
) -> tuple[str, Mapping[str, Any]]:
    unsigned = dict(templates)
    claimed = unsigned.pop("templates_sha256", None)
    entries = templates.get("submission_templates")
    if (
        templates.get("schema") != ARM243_SCHEMA
        or templates.get("status") != ARM243_STATUS
        or templates.get("source_arm242_report_sha256") != report_hash
        or not isinstance(claimed, str)
        or claimed != _sha(unsigned)
        or templates.get("template_count") != 6
        or templates.get("completed_submission_count") != 0
        or templates.get("eligible_body_count") != 0
        or templates.get("measurement_manifest_modified") is not False
        or templates.get("physical_authority") is not False
        or not isinstance(entries, list)
        or len(entries) != 6
    ):
        raise BaseBoardCaptureWorkorderError("ARM-243 template set changed")
    matches = [entry for entry in entries if entry.get("packet_id") == PACKET_ID]
    if len(matches) != 1:
        raise BaseBoardCaptureWorkorderError("base/board template coverage changed")
    template = matches[0]
    expected_fields = {
        row["body_id"]: set(row["required_acceptance_fields"])
        for row in packet["body_rows"]
    }
    submitted = template.get("body_submissions")
    if not isinstance(submitted, list):
        raise BaseBoardCaptureWorkorderError("base/board template bodies changed")
    actual_fields = {
        row.get("body_id"): set(row.get("acceptance_values", {}))
        for row in submitted
        if isinstance(row, Mapping)
    }
    all_values = [
        value
        for row in submitted
        for value in row.get("acceptance_values", {}).values()
    ]
    if (
        template.get("schema") != SUBMISSION_SCHEMA
        or template.get("source_packet_sha256") != _sha(packet)
        or template.get("profile_scope") != packet["profile_scope"]
        or template.get("evidence_sources") != []
        or template.get("reviewer_decision") != "PENDING"
        or template.get("submission_sha256") is not None
        or actual_fields != expected_fields
        or any(value is not None for value in all_values)
    ):
        raise BaseBoardCaptureWorkorderError("base/board template is not blank")
    return claimed, template


def _validated_frame_contract(contract: Mapping[str, Any]) -> None:
    frames = contract.get("frames")
    if not isinstance(frames, Mapping) or frames.get(FRAME_ID) != FRAME_DEFINITION:
        raise BaseBoardCaptureWorkorderError("board frame contract changed")


def build_workorder(
    report: Mapping[str, Any],
    templates: Mapping[str, Any],
    frame_contract: Mapping[str, Any],
    *,
    arm242_file_sha256: str,
    arm243_file_sha256: str,
    frame_contract_file_sha256: str,
) -> dict[str, Any]:
    """Build an unexecuted work order for the foundational fixed packet."""

    report_hash, packet = _validated_report(report)
    templates_hash, template = _validated_template_set(templates, report_hash, packet)
    _validated_frame_contract(frame_contract)
    required_by_body = {
        row["body_id"]: list(row["required_acceptance_fields"])
        for row in packet["body_rows"]
    }
    core: dict[str, Any] = {
        "schema": WORKORDER_SCHEMA,
        "status": "BLOCKED_OPERATOR_MEASUREMENTS_AND_REVIEW_REQUIRED",
        "selected_packet_id": PACKET_ID,
        "selection_reason": (
            "Foundational static board frame and base installation used by both "
            "attachment profiles; capture requires no commanded arm motion."
        ),
        "source_arm242_report_sha256": report_hash,
        "source_arm242_report_file_sha256": _digest(
            arm242_file_sha256, "ARM-242 file hash"
        ),
        "source_arm243_templates_sha256": templates_hash,
        "source_arm243_templates_file_sha256": _digest(
            arm243_file_sha256, "ARM-243 file hash"
        ),
        "source_packet_sha256": template["source_packet_sha256"],
        "source_submission_template_sha256": _sha(template),
        "profile_scope": list(packet["profile_scope"]),
        "coordinate_frame_contract": {
            "frame_id": FRAME_ID,
            "definition": FRAME_DEFINITION,
            "units": "mm",
            "source_file_sha256": _digest(
                frame_contract_file_sha256, "frame contract file hash"
            ),
        },
        "existing_photo_disposition": (
            "SETUP_CONTEXT_ONLY_UNLESS_RETAINED_WITH_HASH_AND_METRIC_METHOD; "
            "photos alone do not establish flatness, uncertainty, transforms, "
            "footprints, or three-dimensional envelope primitives"
        ),
        "preconditions": [
            "arm remains secured and stationary; no commanded trajectory or joint target",
            "board, base, and factory clamp remain in the installed configuration",
            "measurement instruments are identified and their resolution recorded",
            "all evidence files are retained before their SHA-256 values are entered",
        ],
        "capture_sequence": [
            {
                "step": 1,
                "action": "RECORD_COMMON_PROVENANCE",
                "required_outputs": [
                    "evidence_sources",
                    "instrument_identity",
                    "instrument_resolution_mm",
                    "coordinate_frame=B",
                    "units=mm",
                ],
            },
            {
                "step": 2,
                "action": "MEASURE_BOARD_SOLID",
                "required_outputs": required_by_body["workcell:board_solid"],
                "method": "TAPE_MEASURE_AND_FLATNESS_GAUGE",
                "notes": (
                    "Measure installed board extents/thickness and a reviewed top-surface "
                    "flatness or bow bound in B; encode a conservative local envelope."
                ),
            },
            {
                "step": 3,
                "action": "MEASURE_BASE_AND_FACTORY_CLAMP",
                "required_outputs": required_by_body[
                    "installation:base_and_factory_clamp"
                ],
                "method": "TAPE_MEASURE_AND_FIXTURE_GAUGE",
                "notes": (
                    "Measure the installed board-to-base transform, full clamp footprint, "
                    "and conservative local envelope in B without moving the arm."
                ),
            },
            {
                "step": 4,
                "action": "INDEPENDENT_REVIEW_AND_HASH",
                "required_outputs": [
                    "reviewer",
                    "reviewer_decision=ACCEPTED_MEASURED",
                    "submission_sha256",
                ],
            },
        ],
        "required_acceptance_fields_by_body": required_by_body,
        "unfilled_acceptance_field_count": sum(
            len(fields) for fields in required_by_body.values()
        ),
        "completion_command": (
            "python software/integrations/isaac_sim/capture_packet_submission_gate.py "
            "--arm242-report <report.json> --submission <completed-base-board.json> "
            "--output <assessment.json>"
        ),
        "stop_conditions": [
            "installed configuration changes during capture",
            "frame B cannot be reproduced from its maintained definition",
            "instrument identity or resolution is unknown",
            "an evidence file is missing or its SHA-256 cannot be reproduced",
            "any acceptance value would depend only on an unscaled photograph or nominal prior",
            "independent measured review is unavailable or rejects the capture",
        ],
        "submission_completed": False,
        "measurement_manifest_modified": False,
        "installed_collision_profile_generated": False,
        "collision_screening_executed": False,
        "isaac_started": False,
        "gpu_started": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "next_required_stage": "EXECUTE_BASE_BOARD_METROLOGY_AND_COMPLETE_ARM243_TEMPLATE",
    }
    return {**core, "workorder_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise BaseBoardCaptureWorkorderError(f"{path} is not a JSON object")
    return value


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm242-report", type=Path, required=True)
    parser.add_argument("--arm243-templates", type=Path, required=True)
    parser.add_argument("--frame-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report_path = args.arm242_report.resolve(strict=True)
    templates_path = args.arm243_templates.resolve(strict=True)
    frame_path = args.frame_contract.resolve(strict=True)
    result = build_workorder(
        _load(report_path),
        _load(templates_path),
        _load(frame_path),
        arm242_file_sha256=_file_sha(report_path),
        arm243_file_sha256=_file_sha(templates_path),
        frame_contract_file_sha256=_file_sha(frame_path),
    )
    _write(args.output.resolve(), result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
