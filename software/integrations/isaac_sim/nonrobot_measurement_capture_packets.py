"""Build ARM-242 capture packets for the twelve pending non-robot bodies.

The packets preserve the exact ARM-239 gaps and ARM-241 robot/non-robot split.
They group measurements that share a physical setup, while keeping the contact
tool exclusive to the stylus attachment profile.  They are capture requests,
not measurements or engineering acceptance.

No simulator, GPU, device, controller, or physical motion is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ARM239_SCHEMA = "tactevra.isaac_lm4_installed_measurement_gap_matrix.v1"
ARM239_STATUS = "BLOCKED_NO_ACCEPTED_MEASUREMENT_PROMOTIONS"
ARM241_SCHEMA = "tactevra.isaac_lm4_robot_geometry_review_request.v1"
ARM241_STATUS = "BLOCKED_REVIEW_RECORD_REQUIRED"
REPORT_SCHEMA = "tactevra.isaac_lm4_nonrobot_measurement_capture_packets.v1"
NONROBOT_IDS = {
    "attachment:camera_connector",
    "attachment:camera_holder",
    "attachment:camera_module",
    "attachment:contact_tool",
    "attachment:moving_camera_cable",
    "installation:base_and_factory_clamp",
    "workcell:board_solid",
    "workcell:keyboard",
    "workcell:phone",
    "workcell:station:keyboard_left",
    "workcell:station:keyboard_right",
    "workcell:station:phone_tcp",
}
PACKET_GROUPS = (
    (
        "camera_rigid_assembly",
        (
            "attachment:camera_connector",
            "attachment:camera_holder",
            "attachment:camera_module",
        ),
        "CAD_DERIVED_AND_PHYSICALLY_VERIFIED",
    ),
    (
        "contact_tool_tcp",
        ("attachment:contact_tool",),
        "CALIPER_AND_TCP_FIXTURE_GAUGE",
    ),
    (
        "moving_camera_cable_sweep",
        ("attachment:moving_camera_cable",),
        "PHOTOGRAMMETRY_OR_REVIEWED_CONFIGURATION_SWEEP",
    ),
    (
        "base_board_installation",
        ("installation:base_and_factory_clamp", "workcell:board_solid"),
        "TAPE_MEASURE_AND_FIXTURE_GAUGE",
    ),
    (
        "keyboard_and_stations",
        (
            "workcell:keyboard",
            "workcell:station:keyboard_left",
            "workcell:station:keyboard_right",
        ),
        "CALIPER_AND_FIXTURE_GAUGE",
    ),
    (
        "phone_and_station",
        ("workcell:phone", "workcell:station:phone_tcp"),
        "CALIPER_AND_FIXTURE_GAUGE",
    ),
)


class NonrobotCapturePacketError(ValueError):
    """Input lineage or capture-packet semantics changed."""


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
        raise NonrobotCapturePacketError("document is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_hash(document: Mapping[str, Any], field: str, label: str) -> str:
    unsigned = dict(document)
    claimed = unsigned.pop(field, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NonrobotCapturePacketError(f"{label} content hash changed")
    return claimed


def _require_arm239(report: Mapping[str, Any]) -> tuple[str, dict[str, Mapping[str, Any]]]:
    claimed = _require_hash(report, "report_sha256", "ARM-239")
    rows = report.get("body_gap_matrix")
    if (
        report.get("schema") != ARM239_SCHEMA
        or report.get("status") != ARM239_STATUS
        or report.get("required_body_count") != 19
        or report.get("accepted_body_count") != 0
        or report.get("pending_body_count") != 19
        or report.get("measurement_manifest_modified") is not False
        or report.get("physical_authority") is not False
        or not isinstance(rows, list)
    ):
        raise NonrobotCapturePacketError("ARM-239 gap-matrix lineage changed")
    selected = {
        row.get("body_id"): row
        for row in rows
        if isinstance(row, Mapping) and row.get("body_id") in NONROBOT_IDS
    }
    if set(selected) != NONROBOT_IDS:
        raise NonrobotCapturePacketError("ARM-239 non-robot coverage changed")
    if any(
        row.get("current_status") != "PENDING"
        or row.get("accepted_measurement_available") is not False
        or not isinstance(row.get("missing_acceptance_fields"), list)
        or not row["missing_acceptance_fields"]
        for row in selected.values()
    ):
        raise NonrobotCapturePacketError("ARM-239 non-robot row semantics changed")
    return claimed, selected


def _require_arm241(request: Mapping[str, Any]) -> str:
    claimed = _require_hash(request, "request_sha256", "ARM-241")
    if (
        request.get("schema") != ARM241_SCHEMA
        or request.get("status") != ARM241_STATUS
        or request.get("review_body_count") != 7
        or request.get("accepted_body_count") != 0
        or request.get("pending_robot_body_count") != 7
        or request.get("remaining_nonrobot_pending_body_count") != 12
        or request.get("measurement_manifest_modified") is not False
        or request.get("physical_authority") is not False
    ):
        raise NonrobotCapturePacketError("ARM-241 robot-review lineage changed")
    return claimed


def build_capture_packets(
    gap_report: Mapping[str, Any],
    robot_review_request: Mapping[str, Any],
    *,
    arm239_file_sha256: str,
    arm241_file_sha256: str,
) -> dict[str, Any]:
    """Return six setup-coherent requests covering all 12 non-robot bodies."""

    arm239_hash, rows = _require_arm239(gap_report)
    arm241_hash = _require_arm241(robot_review_request)
    packets = []
    covered: set[str] = set()
    for packet_id, body_ids, method in PACKET_GROUPS:
        if covered.intersection(body_ids):
            raise NonrobotCapturePacketError("capture packet body overlap")
        covered.update(body_ids)
        body_rows = []
        for body_id in body_ids:
            row = rows[body_id]
            body_rows.append(
                {
                    "body_id": body_id,
                    "parent_frame": row.get("parent_frame"),
                    "binding_mode": row.get("binding_mode"),
                    "required_acceptance_fields": sorted(
                        row["missing_acceptance_fields"]
                    ),
                    "relevant_prior_ids": sorted(row.get("relevant_prior_ids", [])),
                    "requested_method": row.get("recommended_measurement_method"),
                    "current_disposition": "PENDING_CAPTURE_AND_REVIEW",
                }
            )
        profile_scope = ["stylus_attachment"] if packet_id == "contact_tool_tcp" else [
            "no_attachment",
            "stylus_attachment",
        ]
        packets.append(
            {
                "packet_id": packet_id,
                "profile_scope": profile_scope,
                "setup_method": method,
                "body_rows": body_rows,
                "body_count": len(body_rows),
                "required_common_metadata": [
                    "source_file_sha256",
                    "instrument_identity",
                    "instrument_resolution_mm",
                    "coordinate_frame",
                    "units_mm",
                    "reviewer_decision",
                ],
                "capture_completed": False,
            }
        )
    if covered != NONROBOT_IDS:
        raise NonrobotCapturePacketError("capture packet coverage changed")
    core: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": "BLOCKED_SIX_CAPTURE_PACKETS_PENDING",
        "source_arm239_report_sha256": arm239_hash,
        "source_arm239_report_file_sha256": arm239_file_sha256,
        "source_arm241_request_sha256": arm241_hash,
        "source_arm241_request_file_sha256": arm241_file_sha256,
        "capture_packets": packets,
        "capture_packet_count": len(packets),
        "nonrobot_body_count": len(covered),
        "shared_profile_body_count": 11,
        "stylus_only_body_count": 1,
        "stylus_only_body_ids": ["attachment:contact_tool"],
        "accepted_body_count": 0,
        "pending_nonrobot_body_count": 12,
        "robot_review_state_modified": False,
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
        "next_required_stage": "CAPTURE_AND_REVIEW_PACKET_EVIDENCE",
    }
    return {**core, "report_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NonrobotCapturePacketError(f"{path} is not a JSON object")
    return value


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm239-report", type=Path, required=True)
    parser.add_argument("--arm241-request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    gap_path = args.arm239_report.resolve(strict=True)
    review_path = args.arm241_request.resolve(strict=True)
    result = build_capture_packets(
        _load(gap_path),
        _load(review_path),
        arm239_file_sha256=_file_sha(gap_path),
        arm241_file_sha256=_file_sha(review_path),
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
