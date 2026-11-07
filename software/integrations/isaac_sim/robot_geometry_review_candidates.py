"""Package existing robot-link mesh reductions as ARM-240 review candidates.

The retained mesh-reduction evidence already contains conservative link-local
boxes for the seven robot bodies required by ICQ-1.  This module binds those
boxes to ARM-239's gap matrix so they can be reviewed without re-entering
geometry.  It deliberately does not mark any body measured: physical model
identity, geometry uncertainty, and candidate quality remain open.

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
MESH_SCHEMA = "tactevra.isaac_sim_link_mesh_reduction.v1"
MESH_EVIDENCE_CLASS = "CONSERVATIVE_BOX_CANDIDATES_ONLY"
REPORT_SCHEMA = "tactevra.isaac_lm4_robot_geometry_review_candidates.v1"
REPORT_STATUS = "BLOCKED_CANDIDATES_AWAIT_PHYSICAL_VERIFICATION"

LINK_TO_BODY = {
    "base_link": "robot:base_link",
    "link1": "robot:link1",
    "link2": "robot:link2",
    "link3": "robot:link3",
    "link4": "robot:link4",
    "link5": "robot:link5",
    "gripper_link": "robot:gripper",
}


class RobotGeometryReviewCandidateError(ValueError):
    """ARM-240 input lineage or candidate semantics changed."""


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
        raise RobotGeometryReviewCandidateError(
            "ARM-240 document is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_arm239(report: Mapping[str, Any]) -> str:
    unsigned = dict(report)
    claimed = unsigned.pop("report_sha256", None)
    body_rows = report.get("body_gap_matrix")
    if (
        report.get("schema") != ARM239_SCHEMA
        or report.get("status") != ARM239_STATUS
        or not isinstance(claimed, str)
        or claimed != _sha(unsigned)
        or report.get("required_body_count") != 19
        or report.get("accepted_body_count") != 0
        or report.get("pending_body_count") != 19
        or report.get("nominal_values_promoted_to_measurement") is not False
        or report.get("measurement_manifest_modified") is not False
        or report.get("physical_authority") is not False
        or not isinstance(body_rows, list)
    ):
        raise RobotGeometryReviewCandidateError("ARM-239 gap-matrix lineage changed")
    body_ids = {row.get("body_id") for row in body_rows}
    missing = sorted(set(LINK_TO_BODY.values()) - body_ids)
    if missing:
        raise RobotGeometryReviewCandidateError(
            f"ARM-239 gap matrix lacks robot bodies {missing}"
        )
    return claimed


def _require_mesh_reduction(evidence: Mapping[str, Any]) -> str:
    unsigned = dict(evidence)
    claimed = unsigned.pop("receipt_sha256", None)
    links = evidence.get("links")
    method = evidence.get("method")
    if (
        evidence.get("schema") != MESH_SCHEMA
        or evidence.get("evidence_class") != MESH_EVIDENCE_CLASS
        or evidence.get("candidate_profile_installable") is not False
        or evidence.get("reduced_collision_geometry_admissible") is not False
        or evidence.get("physical_authority") is not False
        or not isinstance(claimed, str)
        or claimed != _sha(unsigned)
        or not isinstance(links, list)
        or not isinstance(method, Mapping)
        or method.get("primitive_kind") != "oriented_box"
        or method.get("orientation") != "LINK_LOCAL_IDENTITY"
    ):
        raise RobotGeometryReviewCandidateError(
            "mesh-reduction candidate lineage changed"
        )
    names = [row.get("link_name") for row in links]
    if len(names) != len(set(names)) or set(names) != set(LINK_TO_BODY):
        raise RobotGeometryReviewCandidateError(
            "mesh-reduction link inventory changed"
        )
    return claimed


def _candidate_row(link: Mapping[str, Any]) -> dict[str, Any]:
    link_name = link.get("link_name")
    if link_name not in LINK_TO_BODY:
        raise RobotGeometryReviewCandidateError(
            f"unreviewed mesh-reduction link {link_name!r}"
        )
    components = link.get("components")
    if not isinstance(components, list) or not components:
        raise RobotGeometryReviewCandidateError(
            f"link {link_name} has no candidate components"
        )
    primitives = []
    non_watertight = 0
    for index, component in enumerate(components):
        if not isinstance(component, Mapping):
            raise RobotGeometryReviewCandidateError(
                f"link {link_name} component {index} is not an object"
            )
        primitive = component.get("candidate_primitive")
        if (
            not isinstance(primitive, Mapping)
            or primitive.get("kind") != "oriented_box"
            or component.get("maximum_vertex_overflow_mm") != 0.0
        ):
            raise RobotGeometryReviewCandidateError(
                f"link {link_name} candidate containment changed"
            )
        if component.get("source_watertight") is not True:
            non_watertight += 1
        primitives.append(dict(primitive))
    blockers = [
        "PHYSICAL_MODEL_IDENTITY_UNVERIFIED",
        "GEOMETRY_UNCERTAINTY_UNBOUND",
        "CONSERVATIVE_BOX_FALSE_POSITIVE_RATE_UNQUALIFIED",
    ]
    if non_watertight:
        blockers.append("NON_WATERTIGHT_SOURCE_COMPONENT_PRESENT")
    if link_name == "link5":
        blockers.append("LINK5_WHOLE_LINK_ENVELOPE_REVIEW_REQUIRED")
    return {
        "body_id": LINK_TO_BODY[link_name],
        "parent_frame": link_name,
        "candidate_classification": "MODEL_DERIVED_REVIEW_CANDIDATE_NOT_MEASUREMENT",
        "source_mesh_sha256": link.get("mesh_sha256"),
        "partition_mode": link.get("partition_mode"),
        "candidate_primitives": primitives,
        "candidate_primitive_count": len(primitives),
        "source_component_count": len(components),
        "non_watertight_component_count": non_watertight,
        "maximum_watertight_volume_ratio": link.get(
            "maximum_watertight_volume_ratio"
        ),
        "physical_model_identity_verified": False,
        "geometry_uncertainty_mm": None,
        "icq1_status_after_packaging": "PENDING",
        "review_blockers": blockers,
    }


def build_robot_geometry_review_candidates(
    gap_report: Mapping[str, Any],
    mesh_reduction: Mapping[str, Any],
    *,
    gap_report_file_sha256: str,
    mesh_reduction_file_sha256: str,
) -> dict[str, Any]:
    """Return seven hash-bound candidates without changing ICQ-1 status."""

    arm239_hash = _require_arm239(gap_report)
    mesh_receipt_hash = _require_mesh_reduction(mesh_reduction)
    candidates = sorted(
        (_candidate_row(row) for row in mesh_reduction["links"]),
        key=lambda row: row["body_id"],
    )
    primitive_count = sum(row["candidate_primitive_count"] for row in candidates)
    if primitive_count != mesh_reduction.get("summary", {}).get(
        "candidate_primitive_count"
    ):
        raise RobotGeometryReviewCandidateError(
            "mesh-reduction primitive denominator changed"
        )
    core: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": REPORT_STATUS,
        "source_arm239_report_sha256": arm239_hash,
        "source_arm239_report_file_sha256": gap_report_file_sha256,
        "source_mesh_reduction_receipt_sha256": mesh_receipt_hash,
        "source_mesh_reduction_file_sha256": mesh_reduction_file_sha256,
        "source_upstream_commit": mesh_reduction.get("source_bindings", {}).get(
            "upstream_commit"
        ),
        "attachment_profile": gap_report.get("attachment_profile"),
        "robot_body_candidates": candidates,
        "candidate_body_count": len(candidates),
        "candidate_primitive_count": primitive_count,
        "accepted_body_count": 0,
        "pending_robot_body_count": len(candidates),
        "remaining_nonrobot_pending_body_count": (
            gap_report["pending_body_count"] - len(candidates)
        ),
        "source_mesh_blockers": list(mesh_reduction.get("blockers", [])),
        "measurement_manifest_modified": False,
        "candidate_geometry_promoted_to_measurement": False,
        "installed_collision_profile_generated": False,
        "collision_screening_executed": False,
        "corrected_cartesian_route_materialized": False,
        "corrected_joint_targets_materialized": False,
        "isaac_started": False,
        "gpu_started": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "next_required_stage": (
            "REVIEW_ROBOT_CANDIDATES_AND_BIND_PHYSICAL_IDENTITY_UNCERTAINTY"
        ),
    }
    return {**core, "report_sha256": _sha(core)}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise RobotGeometryReviewCandidateError(f"{path} is not a JSON object")
    return value


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm239-report", type=Path, required=True)
    parser.add_argument("--mesh-reduction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    gap_path = args.arm239_report.resolve(strict=True)
    mesh_path = args.mesh_reduction.resolve(strict=True)
    report = build_robot_geometry_review_candidates(
        _load_json(gap_path),
        _load_json(mesh_path),
        gap_report_file_sha256=_file_sha(gap_path),
        mesh_reduction_file_sha256=_file_sha(mesh_path),
    )
    _write_json(args.output.resolve(), report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
