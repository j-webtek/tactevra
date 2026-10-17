"""Build a source-bound work order for static collision qualification.

The work order preserves retained dimensions and candidate CAD while separating
envelope derivation, installed placement, uncertainty, flexible geometry, and
attachment-profile review.  It never promotes a candidate into measured
collision geometry.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "rocell.static_overhead_collision_qualification_work_order.v1"
STATUS = "READY_FOR_REVIEWED_QUALIFICATION_ZERO_AUTHORITY"
SOURCE_SCHEMA = "rocell.static_overhead_collision_source_audit.v1"
SOURCE_STATUS = "BLOCKED_CANDIDATE_SOURCES_REQUIRE_QUALIFICATION"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_source_audit(path: Path, file_sha256: str) -> dict[str, Any]:
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != file_sha256:
        raise ValueError("source audit file hash mismatch")
    document = json.loads(payload)
    if document.get("schema") != SOURCE_SCHEMA or document.get("status") != SOURCE_STATUS:
        raise ValueError("source audit schema or status mismatch")
    report_sha256 = document.get("report_sha256")
    core = {key: value for key, value in document.items() if key != "report_sha256"}
    if report_sha256 != _sha(core):
        raise ValueError("source audit canonical hash mismatch")
    rows = document.get("body_source_coverage")
    if not isinstance(rows, list) or len(rows) != 19:
        raise ValueError("source audit must contain exactly 19 body rows")
    body_ids = [row.get("body_id") for row in rows]
    if len(set(body_ids)) != 19:
        raise ValueError("source audit body IDs must be unique")
    if document.get("accepted_measurement_body_count") != 0:
        raise ValueError("qualification work order requires the candidate-only audit")
    return document


def _classification(body_id: str) -> tuple[str, tuple[str, ...], bool]:
    if body_id.startswith("robot:"):
        return (
            "REVIEW_CONSERVATIVE_LINK_ENVELOPE",
            (
                "Review whole-link coverage and non-watertight components.",
                "Select conservative primitives and geometry uncertainty.",
                "Bind the reviewed envelope to the pinned robot frame.",
            ),
            False,
        )
    if body_id == "installation:base_and_factory_clamp":
        return (
            "QUALIFY_INSTALLED_BASE_AND_CLAMP",
            (
                "Record a conservative installed base-and-clamp envelope.",
                "Bind its board-frame placement and placement uncertainty.",
            ),
            False,
        )
    if body_id in {
        "installation:static_camera_support",
        "installation:static_camera_module",
        "installation:static_camera_connector",
    }:
        return (
            "DERIVE_CAD_ENVELOPE_AND_BIND_INSTALLED_PLACEMENT",
            (
                "Derive a conservative envelope from the pinned candidate CAD.",
                "Review the installed article, board-frame placement, and uncertainty.",
            ),
            False,
        )
    if body_id == "installation:static_camera_cable":
        return (
            "QUALIFY_FIXED_FLEXIBLE_ENVELOPE",
            (
                "Define the fixed camera cable's conservative occupied region.",
                "Record routing variability and envelope uncertainty.",
            ),
            False,
        )
    if body_id == "attachment:contact_tool":
        return (
            "REVIEW_BARE_JAW_ABSENCE_DECLARATION",
            (
                "Confirm the BARE_JAW profile has no contact-tool body.",
                "Keep any future stylus in a separate attachment profile.",
            ),
            False,
        )
    if body_id in {"workcell:board_solid", "workcell:keyboard", "workcell:phone"}:
        return (
            "REVIEW_RETAINED_DIMENSIONS_AND_BIND_PLACEMENT",
            (
                "Reuse the retained dimension record; do not request a repeat measurement.",
                "Review the conservative envelope, board-frame placement, and uncertainty.",
            ),
            True,
        )
    if body_id.startswith("workcell:station:"):
        return (
            "DERIVE_CAD_ENVELOPE_AND_BIND_INSTALLED_PLACEMENT",
            (
                "Derive a conservative envelope from the controlled station CAD.",
                "Review the installed article, board-frame placement, and uncertainty.",
            ),
            False,
        )
    raise ValueError(f"unclassified collision body: {body_id}")


def build_static_overhead_collision_qualification_work_order_v1(
    source_audit_path: Path,
    source_audit_file_sha256: str,
) -> dict[str, Any]:
    """Convert the candidate audit into a deterministic zero-authority work order."""

    source = _load_source_audit(source_audit_path, source_audit_file_sha256)
    rows = []
    class_counts: dict[str, int] = {}
    retained_dimension_ids = []
    for source_row in source["body_source_coverage"]:
        body_id = source_row["body_id"]
        action_class, actions, retained_dimensions = _classification(body_id)
        class_counts[action_class] = class_counts.get(action_class, 0) + 1
        if retained_dimensions:
            retained_dimension_ids.append(body_id)
        rows.append(
            {
                "body_id": body_id,
                "parent_frame": source_row["parent_frame"],
                "binding_mode": source_row["binding_mode"],
                "source_decision": source_row["decision"],
                "candidate_source_bindings": [
                    {
                        "path": item["path"],
                        "sha256": item["sha256"],
                        "evidence_class": item["evidence_class"],
                    }
                    for item in source_row["candidate_sources"]
                ],
                "qualification_action_class": action_class,
                "qualification_actions": list(actions),
                "retained_dimensions_reused": retained_dimensions,
                "repeat_dimension_measurement_requested": False,
                "measurement_status_after_work_order": "PENDING",
            }
        )

    core = {
        "schema": SCHEMA,
        "status": STATUS,
        "source_audit_file_sha256": source_audit_file_sha256,
        "source_audit_report_sha256": source["report_sha256"],
        "base_contract_sha256": source["base_contract_sha256"],
        "measurement_manifest_file_sha256": source["measurement_manifest_file_sha256"],
        "required_body_count": len(rows),
        "qualification_action_class_counts": dict(sorted(class_counts.items())),
        "retained_dimension_body_ids": sorted(retained_dimension_ids),
        "repeat_dimension_measurement_body_ids": [],
        "body_qualification_work": rows,
        "execution_order": [
            {
                "stage": 1,
                "name": "REFERENCE_AND_BASE",
                "body_ids": ["workcell:board_solid", "installation:base_and_factory_clamp"],
            },
            {
                "stage": 2,
                "name": "ROBOT_AND_ATTACHMENT_PROFILE",
                "body_ids": [
                    *(f"robot:{name}" for name in (
                        "base_link", "link1", "link2", "link3", "link4", "link5", "gripper"
                    )),
                    "attachment:contact_tool",
                ],
            },
            {
                "stage": 3,
                "name": "STATIC_CAMERA_INSTALLATION",
                "body_ids": [
                    "installation:static_camera_support",
                    "installation:static_camera_module",
                    "installation:static_camera_connector",
                    "installation:static_camera_cable",
                ],
            },
            {
                "stage": 4,
                "name": "WORKCELL_ARTICLES_AND_STATIONS",
                "body_ids": [
                    "workcell:keyboard",
                    "workcell:phone",
                    "workcell:station:keyboard_left",
                    "workcell:station:keyboard_right",
                    "workcell:station:phone_tcp",
                ],
            },
            {
                "stage": 5,
                "name": "GLOBAL_CLEARANCE_AND_UNCERTAINTY_REVIEW",
                "body_ids": [],
            },
        ],
        "next_required_stage": "EXECUTE_REVIEWED_QUALIFICATION_WORK_ORDER",
        "profile_generated": False,
        "collision_screening_executed": False,
        "controller_commands": [],
        "hardware_access": False,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "work_order_sha256": _sha(core)}


__all__ = [
    "SCHEMA",
    "STATUS",
    "build_static_overhead_collision_qualification_work_order_v1",
]
