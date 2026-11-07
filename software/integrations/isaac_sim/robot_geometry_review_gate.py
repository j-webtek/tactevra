"""Build and assess the ARM-241 robot-geometry engineering review boundary.

ARM-240 packages model-derived collision candidates but deliberately leaves all
seven robot bodies pending.  This module turns that package into an exact,
content-addressed review request and can assess a separately authored review.
It never edits the ICQ-1 manifest or emits an installed collision profile.

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


ARM240_SCHEMA = "tactevra.isaac_lm4_robot_geometry_review_candidates.v1"
ARM240_STATUS = "BLOCKED_CANDIDATES_AWAIT_PHYSICAL_VERIFICATION"
REQUEST_SCHEMA = "tactevra.isaac_lm4_robot_geometry_review_request.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_robot_geometry_engineering_review.v1"
ASSESSMENT_SCHEMA = "tactevra.isaac_lm4_robot_geometry_review_assessment.v1"
BODY_IDS = (
    "robot:base_link",
    "robot:gripper",
    "robot:link1",
    "robot:link2",
    "robot:link3",
    "robot:link4",
    "robot:link5",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RobotGeometryReviewGateError(ValueError):
    """The candidate lineage or engineering-review contract is invalid."""


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
        raise RobotGeometryReviewGateError("document is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RobotGeometryReviewGateError(f"{label} must be a SHA-256 digest")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RobotGeometryReviewGateError(f"{label} must be nonempty text")
    return value.strip()


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RobotGeometryReviewGateError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise RobotGeometryReviewGateError(f"{label} must be finite and positive")
    return result


def _require_arm240(report: Mapping[str, Any]) -> tuple[str, list[Mapping[str, Any]]]:
    unsigned = dict(report)
    claimed = unsigned.pop("report_sha256", None)
    candidates = report.get("robot_body_candidates")
    if (
        report.get("schema") != ARM240_SCHEMA
        or report.get("status") != ARM240_STATUS
        or not isinstance(claimed, str)
        or claimed != _sha(unsigned)
        or report.get("candidate_body_count") != 7
        or report.get("candidate_primitive_count") != 14
        or report.get("accepted_body_count") != 0
        or report.get("pending_robot_body_count") != 7
        or report.get("remaining_nonrobot_pending_body_count") != 12
        or report.get("measurement_manifest_modified") is not False
        or report.get("candidate_geometry_promoted_to_measurement") is not False
        or report.get("physical_authority") is not False
        or not isinstance(candidates, list)
    ):
        raise RobotGeometryReviewGateError("ARM-240 candidate lineage changed")
    ids = tuple(sorted(row.get("body_id") for row in candidates))
    if ids != BODY_IDS:
        raise RobotGeometryReviewGateError("ARM-240 robot-body inventory changed")
    return claimed, candidates


def _candidate_sha(row: Mapping[str, Any]) -> str:
    return _sha(
        {
            "body_id": row.get("body_id"),
            "parent_frame": row.get("parent_frame"),
            "source_mesh_sha256": row.get("source_mesh_sha256"),
            "partition_mode": row.get("partition_mode"),
            "candidate_primitives": row.get("candidate_primitives"),
        }
    )


def build_review_request(
    arm240_report: Mapping[str, Any], *, arm240_file_sha256: str
) -> dict[str, Any]:
    """Create the exact seven-body review checklist without accepting a body."""

    report_hash, candidates = _require_arm240(arm240_report)
    rows = []
    for candidate in candidates:
        body_id = candidate["body_id"]
        requirements = [
            "EXACT_INSTALLED_MODEL_IDENTITY_ACCEPTED",
            "POSITIVE_GEOMETRY_UNCERTAINTY_BOUND_ACCEPTED",
            "CONSERVATIVE_CANDIDATE_QUALITY_ACCEPTED",
        ]
        if candidate.get("non_watertight_component_count", 0):
            requirements.append("NON_WATERTIGHT_SOURCE_RISK_ACCEPTED")
        if body_id == "robot:link5":
            requirements.extend(
                [
                    "WHOLE_LINK_FALLBACK_ACCEPTED",
                    "ARM196_NEGATIVE_ROUTE_RESULT_EXPLICITLY_ADDRESSED",
                ]
            )
        rows.append(
            {
                "body_id": body_id,
                "parent_frame": candidate["parent_frame"],
                "candidate_sha256": _candidate_sha(candidate),
                "source_mesh_sha256": candidate["source_mesh_sha256"],
                "required_acceptance_findings": requirements,
                "current_disposition": "PENDING_ENGINEERING_REVIEW",
            }
        )
    core: dict[str, Any] = {
        "schema": REQUEST_SCHEMA,
        "status": "BLOCKED_REVIEW_RECORD_REQUIRED",
        "source_arm240_report_sha256": report_hash,
        "source_arm240_report_file_sha256": _digest(
            arm240_file_sha256, "ARM-240 file hash"
        ),
        "attachment_profile": arm240_report.get("attachment_profile"),
        "review_rows": rows,
        "review_body_count": len(rows),
        "candidate_primitive_count": arm240_report["candidate_primitive_count"],
        "accepted_body_count": 0,
        "pending_robot_body_count": 7,
        "remaining_nonrobot_pending_body_count": 12,
        "arm196_link5_negative_result": {
            "classification": "RETAINED_NEGATIVE_RESULT_NOT_ACCEPTANCE",
            "refinement_receipt_sha256": (
                "b75da3fa395fd39fdf2cb026e3f4e54152ea33ccf66571f3916af37d44c9c95f"
            ),
            "native_receipt_sha256": (
                "e1a6ddc7c52ec5acda2eee9e0ae628d705a44d85ca4f9db009a67b80a6e8b7b"
            ),
            "finding": "LINK5_SUBDIVISION_DID_NOT_IMPROVE_BODY_LEVEL_ROUTE_CLASSIFICATION",
        },
        "measurement_manifest_modified": False,
        "installed_collision_profile_generated": False,
        "isaac_started": False,
        "gpu_started": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "next_required_stage": "AUTHOR_EXACT_ENGINEERING_REVIEW_RECORD",
    }
    return {**core, "request_sha256": _sha(core)}


def _accepted_finding(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "accepted",
        "evidence_sha256",
        "source_reference",
    }:
        raise RobotGeometryReviewGateError(f"{label} finding fields differ")
    if value["accepted"] is not True:
        raise RobotGeometryReviewGateError(f"{label} is not accepted")
    _digest(value["evidence_sha256"], f"{label} evidence hash")
    _text(value["source_reference"], f"{label} source reference")
    return value


def assess_review(
    request: Mapping[str, Any], review: Mapping[str, Any]
) -> dict[str, Any]:
    """Fail closed unless every exact candidate has complete accepted findings."""

    request_unsigned = dict(request)
    request_hash = request_unsigned.pop("request_sha256", None)
    rows = request.get("review_rows")
    if (
        request.get("schema") != REQUEST_SCHEMA
        or request.get("status") != "BLOCKED_REVIEW_RECORD_REQUIRED"
        or not isinstance(request_hash, str)
        or request_hash != _sha(request_unsigned)
        or not isinstance(rows, list)
        or len(rows) != 7
    ):
        raise RobotGeometryReviewGateError("ARM-241 review request changed")
    review_unsigned = dict(review)
    review_hash = review_unsigned.pop("review_sha256", None)
    decisions = review.get("decisions")
    if (
        review.get("schema") != REVIEW_SCHEMA
        or review.get("source_request_sha256") != request_hash
        or not isinstance(review_hash, str)
        or review_hash != _sha(review_unsigned)
        or not isinstance(decisions, Sequence)
        or isinstance(decisions, (str, bytes))
    ):
        raise RobotGeometryReviewGateError("engineering review lineage changed")
    decision_map: dict[str, Mapping[str, Any]] = {}
    for decision in decisions:
        if not isinstance(decision, Mapping):
            raise RobotGeometryReviewGateError("review decision must be an object")
        body_id = decision.get("body_id")
        if body_id in decision_map:
            raise RobotGeometryReviewGateError(f"duplicate decision for {body_id}")
        decision_map[body_id] = decision
    if set(decision_map) != set(BODY_IDS):
        raise RobotGeometryReviewGateError("review decision coverage is incomplete")

    accepted = []
    for row in rows:
        body_id = row["body_id"]
        decision = decision_map[body_id]
        if decision.get("candidate_sha256") != row["candidate_sha256"]:
            raise RobotGeometryReviewGateError(f"{body_id} candidate hash changed")
        if decision.get("disposition") != "ACCEPT_FOR_ICQ1_ROBOT_ROW":
            raise RobotGeometryReviewGateError(f"{body_id} is not accepted")
        _text(decision.get("reviewer"), f"{body_id} reviewer")
        _positive(
            decision.get("geometry_uncertainty_mm"),
            f"{body_id} geometry uncertainty",
        )
        findings = decision.get("findings")
        if not isinstance(findings, Mapping):
            raise RobotGeometryReviewGateError(f"{body_id} findings missing")
        expected = set(row["required_acceptance_findings"])
        if set(findings) != expected:
            raise RobotGeometryReviewGateError(f"{body_id} finding coverage differs")
        for finding_id in sorted(expected):
            _accepted_finding(findings[finding_id], f"{body_id}.{finding_id}")
        accepted.append(
            {
                "body_id": body_id,
                "candidate_sha256": row["candidate_sha256"],
                "geometry_uncertainty_mm": float(decision["geometry_uncertainty_mm"]),
                "reviewer": decision["reviewer"].strip(),
            }
        )

    core: dict[str, Any] = {
        "schema": ASSESSMENT_SCHEMA,
        "status": "ROBOT_ROWS_REVIEWED_ELIGIBLE_FOR_SEPARATE_ICQ1_BUILD",
        "source_request_sha256": request_hash,
        "source_review_sha256": review_hash,
        "accepted_robot_rows": accepted,
        "accepted_body_count": 7,
        "pending_robot_body_count": 0,
        "remaining_nonrobot_pending_body_count": 12,
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
        "next_required_stage": "BUILD_NEW_ICQ1_MANIFEST_FROM_REVIEWED_ROBOT_ROWS_ONLY",
    }
    return {**core, "assessment_sha256": _sha(core)}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise RobotGeometryReviewGateError(f"{path} is not a JSON object")
    return value


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm240-report", type=Path)
    parser.add_argument("--review-request", type=Path)
    parser.add_argument("--engineering-review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.arm240_report and not args.review_request and not args.engineering_review:
        path = args.arm240_report.resolve(strict=True)
        result = build_review_request(
            _load_json(path), arm240_file_sha256=_file_sha(path)
        )
    elif args.review_request and args.engineering_review and not args.arm240_report:
        result = assess_review(
            _load_json(args.review_request.resolve(strict=True)),
            _load_json(args.engineering_review.resolve(strict=True)),
        )
    else:
        parser.error(
            "use either --arm240-report or both --review-request and --engineering-review"
        )
    _write_json(args.output.resolve(), result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
