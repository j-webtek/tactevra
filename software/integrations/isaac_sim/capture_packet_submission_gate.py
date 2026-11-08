"""Materialize and assess ARM-243 non-robot capture submissions.

ARM-242 defines six capture packets. This boundary emits exact fillable
templates and validates one separately completed packet at a time. A passing
assessment is only eligibility for a later ICQ-1 manifest build; it neither
changes that manifest nor creates an installed collision profile.

No simulator, GPU, device, controller, or physical motion is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


ARM242_SCHEMA = "tactevra.isaac_lm4_nonrobot_measurement_capture_packets.v1"
ARM242_STATUS = "BLOCKED_SIX_CAPTURE_PACKETS_PENDING"
TEMPLATES_SCHEMA = "tactevra.isaac_lm4_capture_submission_templates.v1"
SUBMISSION_SCHEMA = "tactevra.isaac_lm4_capture_packet_submission.v1"
ASSESSMENT_SCHEMA = "tactevra.isaac_lm4_capture_packet_assessment.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CapturePacketSubmissionError(ValueError):
    """The packet lineage or submitted evidence is incomplete or invalid."""


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
        raise CapturePacketSubmissionError("document is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise CapturePacketSubmissionError(f"{label} must be a SHA-256 digest")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CapturePacketSubmissionError(f"{label} must be nonempty text")
    return value.strip()


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CapturePacketSubmissionError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise CapturePacketSubmissionError(f"{label} must be finite and positive")
    return result


def _require_arm242(report: Mapping[str, Any]) -> tuple[str, list[Mapping[str, Any]]]:
    unsigned = dict(report)
    claimed = unsigned.pop("report_sha256", None)
    packets = report.get("capture_packets")
    if (
        report.get("schema") != ARM242_SCHEMA
        or report.get("status") != ARM242_STATUS
        or not isinstance(claimed, str)
        or claimed != _sha(unsigned)
        or report.get("capture_packet_count") != 6
        or report.get("nonrobot_body_count") != 12
        or report.get("shared_profile_body_count") != 11
        or report.get("stylus_only_body_count") != 1
        or report.get("accepted_body_count") != 0
        or report.get("pending_nonrobot_body_count") != 12
        or report.get("measurement_manifest_modified") is not False
        or report.get("physical_authority") is not False
        or not isinstance(packets, list)
        or len(packets) != 6
    ):
        raise CapturePacketSubmissionError("ARM-242 packet lineage changed")
    ids = [packet.get("packet_id") for packet in packets]
    if len(ids) != len(set(ids)):
        raise CapturePacketSubmissionError("ARM-242 packet ids are not unique")
    body_ids = [
        row.get("body_id")
        for packet in packets
        for row in packet.get("body_rows", [])
        if isinstance(row, Mapping)
    ]
    if len(body_ids) != len(set(body_ids)) or len(body_ids) != 12:
        raise CapturePacketSubmissionError("ARM-242 body coverage changed")
    return claimed, packets


def _packet_hash(packet: Mapping[str, Any]) -> str:
    return _sha(packet)


def build_submission_templates(
    report: Mapping[str, Any], *, arm242_file_sha256: str
) -> dict[str, Any]:
    """Emit six exact, uncompleted templates bound to ARM-242."""

    report_hash, packets = _require_arm242(report)
    templates = []
    for packet in packets:
        body_submissions = []
        for row in packet["body_rows"]:
            body_submissions.append(
                {
                    "body_id": row["body_id"],
                    "parent_frame": row["parent_frame"],
                    "binding_mode": row["binding_mode"],
                    "acceptance_values": {
                        field: None for field in row["required_acceptance_fields"]
                    },
                }
            )
        templates.append(
            {
                "schema": SUBMISSION_SCHEMA,
                "source_arm242_report_sha256": report_hash,
                "packet_id": packet["packet_id"],
                "source_packet_sha256": _packet_hash(packet),
                "profile_scope": list(packet["profile_scope"]),
                "evidence_sources": [],
                "body_submissions": body_submissions,
                "instrument_identity": None,
                "instrument_resolution_mm": None,
                "coordinate_frame": None,
                "units": "mm",
                "reviewer": None,
                "reviewer_decision": "PENDING",
                "submission_sha256": None,
            }
        )
    core: dict[str, Any] = {
        "schema": TEMPLATES_SCHEMA,
        "status": "BLOCKED_CAPTURE_SUBMISSIONS_REQUIRED",
        "source_arm242_report_sha256": report_hash,
        "source_arm242_report_file_sha256": _digest(
            arm242_file_sha256, "ARM-242 file hash"
        ),
        "submission_templates": templates,
        "template_count": 6,
        "completed_submission_count": 0,
        "eligible_body_count": 0,
        "pending_nonrobot_body_count": 12,
        "measurement_manifest_modified": False,
        "installed_collision_profile_generated": False,
        "isaac_started": False,
        "gpu_started": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "next_required_stage": "COMPLETE_AND_REVIEW_ONE_CAPTURE_SUBMISSION",
    }
    return {**core, "templates_sha256": _sha(core)}


def _valid_primitive(value: object, label: str) -> None:
    if not isinstance(value, Mapping):
        raise CapturePacketSubmissionError(f"{label} must be an object")
    kind = value.get("kind")
    required = {
        "sphere": {"kind", "center_mm", "radius_mm"},
        "capsule": {"kind", "start_mm", "end_mm", "radius_mm"},
        "oriented_box": {
            "kind",
            "center_mm",
            "half_extents_mm",
            "rotation_row_major",
        },
    }
    if kind not in required or set(value) != required[kind]:
        raise CapturePacketSubmissionError(f"{label} primitive fields differ")
    vectors = [
        key
        for key in value
        if (key.endswith("_mm") and key != "radius_mm")
        or key == "rotation_row_major"
    ]
    for key in vectors:
        expected = 9 if key == "rotation_row_major" else 3
        vector = value[key]
        if (
            not isinstance(vector, Sequence)
            or isinstance(vector, (str, bytes))
            or len(vector) != expected
            or any(
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not math.isfinite(float(item))
                for item in vector
            )
        ):
            raise CapturePacketSubmissionError(f"{label}.{key} is invalid")
        if key == "half_extents_mm" and any(float(item) <= 0.0 for item in vector):
            raise CapturePacketSubmissionError(f"{label}.{key} must be positive")
    if "radius_mm" in value:
        _positive(value["radius_mm"], f"{label}.radius_mm")


def _require_value(field: str, value: object, label: str, source_hashes: set[str]) -> None:
    if field == "accepted_source_hash":
        if _digest(value, label) not in source_hashes:
            raise CapturePacketSubmissionError(f"{label} is not a submitted source")
    elif field in {"geometry_uncertainty_mm", "pose_uncertainty_mm", "stylus_projection_mm"}:
        _positive(value, label)
    elif field == "local_frame_envelope_primitives":
        if not isinstance(value, list) or not value:
            raise CapturePacketSubmissionError(f"{label} must be a nonempty array")
        for index, primitive in enumerate(value):
            _valid_primitive(primitive, f"{label}[{index}]")
    elif value is None or value == "" or value == [] or value == {}:
        raise CapturePacketSubmissionError(f"{label} is incomplete")


def assess_submission(
    report: Mapping[str, Any], submission: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate one completed packet and emit only later-build eligibility."""

    report_hash, packets = _require_arm242(report)
    packet_map = {packet["packet_id"]: packet for packet in packets}
    unsigned = dict(submission)
    claimed = unsigned.pop("submission_sha256", None)
    packet_id = submission.get("packet_id")
    if (
        submission.get("schema") != SUBMISSION_SCHEMA
        or submission.get("source_arm242_report_sha256") != report_hash
        or packet_id not in packet_map
        or not isinstance(claimed, str)
        or claimed != _sha(unsigned)
    ):
        raise CapturePacketSubmissionError("capture submission lineage changed")
    packet = packet_map[packet_id]
    if (
        submission.get("source_packet_sha256") != _packet_hash(packet)
        or submission.get("profile_scope") != packet["profile_scope"]
        or submission.get("units") != "mm"
        or submission.get("reviewer_decision") != "ACCEPTED_MEASURED"
    ):
        raise CapturePacketSubmissionError("capture submission scope is not accepted")
    _text(submission.get("instrument_identity"), "instrument identity")
    _positive(submission.get("instrument_resolution_mm"), "instrument resolution")
    _text(submission.get("coordinate_frame"), "coordinate frame")
    _text(submission.get("reviewer"), "reviewer")
    sources = submission.get("evidence_sources")
    if not isinstance(sources, list) or not sources:
        raise CapturePacketSubmissionError("evidence_sources must be nonempty")
    source_hashes = set()
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping) or set(source) != {
            "source_file_sha256",
            "source_reference",
        }:
            raise CapturePacketSubmissionError(f"source {index} fields differ")
        source_hashes.add(_digest(source["source_file_sha256"], f"source {index} hash"))
        _text(source["source_reference"], f"source {index} reference")
    submitted = submission.get("body_submissions")
    if not isinstance(submitted, list):
        raise CapturePacketSubmissionError("body_submissions must be an array")
    body_map = {
        row.get("body_id"): row for row in submitted if isinstance(row, Mapping)
    }
    expected = {row["body_id"]: row for row in packet["body_rows"]}
    if len(body_map) != len(submitted) or set(body_map) != set(expected):
        raise CapturePacketSubmissionError("body submission coverage differs")
    eligible = []
    for body_id, source_row in expected.items():
        row = body_map[body_id]
        if (
            row.get("parent_frame") != source_row["parent_frame"]
            or row.get("binding_mode") != source_row["binding_mode"]
        ):
            raise CapturePacketSubmissionError(f"{body_id} frame or binding changed")
        values = row.get("acceptance_values")
        required = set(source_row["required_acceptance_fields"])
        if not isinstance(values, Mapping) or set(values) != required:
            raise CapturePacketSubmissionError(f"{body_id} acceptance fields differ")
        for field in sorted(required):
            _require_value(field, values[field], f"{body_id}.{field}", source_hashes)
        eligible.append(
            {
                "body_id": body_id,
                "parent_frame": source_row["parent_frame"],
                "binding_mode": source_row["binding_mode"],
                "accepted_source_hash": values["accepted_source_hash"],
                "geometry_uncertainty_mm": float(values["geometry_uncertainty_mm"]),
            }
        )
    core: dict[str, Any] = {
        "schema": ASSESSMENT_SCHEMA,
        "status": "PACKET_ELIGIBLE_FOR_SEPARATE_ICQ1_FRAGMENT_BUILD",
        "source_arm242_report_sha256": report_hash,
        "source_submission_sha256": claimed,
        "packet_id": packet_id,
        "profile_scope": list(packet["profile_scope"]),
        "eligible_body_rows": eligible,
        "eligible_body_count": len(eligible),
        "remaining_packets_unassessed": 5,
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
        "next_required_stage": "BUILD_REVIEWED_PACKET_FRAGMENT_WITHOUT_MERGING_PROFILES",
    }
    return {**core, "assessment_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise CapturePacketSubmissionError(f"{path} is not a JSON object")
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
    parser.add_argument("--submission", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report_path = args.arm242_report.resolve(strict=True)
    report = _load(report_path)
    if args.submission:
        result = assess_submission(report, _load(args.submission.resolve(strict=True)))
    else:
        result = build_submission_templates(
            report, arm242_file_sha256=_file_sha(report_path)
        )
    _write(args.output.resolve(), result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
