"""Assess reviewed SRDF pair proposals on held-out joint-space replay.

This evidence-only counterfactual cannot install an exclusion or grant
collision-query, controller, hardware, or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from collision_differential_probe import canonical_sha256


EXPECTED_ROBOT_MODEL_SHA256 = (
    "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
)
EXPECTED_GEOMETRY_SHA256 = (
    "cf887206e9afdadb46a20263db56406eabfe90a78c3f9d1e5ad0e8dc3fbc6469"
)
EXPECTED_POLICY_REVIEW_SHA256 = (
    "f80f6ac8e72414686489eb3757acb3746f03ea34b1136f68edfddfb68f4451d4"
)
EXPECTED_NEVER_REVIEW_SHA256 = (
    "83eb284513215976364792a8859c1cacb8b4ad0dd15288e4a391071f717dade1"
)
OUTCOMES = (
    "AGREEMENT_COLLISION", "AGREEMENT_FREE",
    "CANDIDATE_FALSE_POSITIVE", "CANDIDATE_FALSE_NEGATIVE",
)


def _load_receipt(path: Path, expected: str | None = None) -> dict:
    payload = path.resolve(strict=True).read_bytes()
    receipt = json.loads(payload.decode("utf-8"))
    claimed = receipt.get("receipt_sha256")
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256", None)
    if claimed != canonical_sha256(unsigned):
        raise ValueError(f"receipt hash mismatch: {path.name}")
    if expected is not None and claimed != expected:
        raise ValueError(f"receipt identity mismatch: {path.name}")
    receipt["_file_sha256"] = hashlib.sha256(payload).hexdigest()
    return receipt


def _load_stress_replay(path: Path) -> dict:
    replay = _load_receipt(path)
    method = replay.get("method", {})
    if (
        method.get("halton_start_index") != 1001
        or method.get("halton_sample_count") != 256
        or method.get("anchors_included") is not False
        or method.get("pose_families") != ["HALTON_INTERIOR"]
        or replay.get("pose_count") != 256
    ):
        raise ValueError("stress replay is not the declared held-out corpus")
    bindings = replay.get("source_bindings", {})
    if bindings.get("governed_urdf_sha256") != EXPECTED_ROBOT_MODEL_SHA256:
        raise ValueError("stress replay robot model mismatch")
    if bindings.get("reduction_receipt_sha256") != EXPECTED_GEOMETRY_SHA256:
        raise ValueError("stress replay geometry mismatch")
    return replay


def _assess(proposals: list[dict], replay: dict) -> dict:
    rows = {tuple(sorted(row["body_pair"])): row for row in replay["pair_summary"]}
    proposed_pairs = {tuple(sorted(row["body_pair"])) for row in proposals}
    proposed_reviews = []
    for proposal in proposals:
        pair = tuple(sorted(proposal["body_pair"]))
        row = rows[pair]
        counts = {name: int(row["counts"][name]) for name in OUTCOMES}
        case_count = sum(counts.values())
        never_supported = None
        if proposal["reason"] == "Never":
            never_supported = (
                counts["AGREEMENT_FREE"] == case_count
                and all(counts[name] == 0 for name in OUTCOMES if name != "AGREEMENT_FREE")
                and row["minimum_raw_mesh_signed_distance_mm"] > 0.0
                and row["minimum_candidate_box_signed_distance_mm"] > 0.0
            )
        proposed_reviews.append({
            "body_pair": list(pair), "upstream_reason": proposal["reason"],
            "case_count": case_count, "counts": counts,
            "minimum_raw_mesh_signed_distance_mm": row[
                "minimum_raw_mesh_signed_distance_mm"],
            "minimum_candidate_box_signed_distance_mm": row[
                "minimum_candidate_box_signed_distance_mm"],
            "held_out_supports_never_reason": never_supported,
        })

    retained_counts = {name: 0 for name in OUTCOMES}
    retained_reviews = []
    for pair, row in rows.items():
        if pair in proposed_pairs:
            continue
        counts = {name: int(row["counts"][name]) for name in OUTCOMES}
        for name in OUTCOMES:
            retained_counts[name] += counts[name]
        if any(counts[name] for name in (
            "AGREEMENT_COLLISION", "CANDIDATE_FALSE_POSITIVE",
            "CANDIDATE_FALSE_NEGATIVE",
        )):
            retained_reviews.append({"body_pair": list(pair), "counts": counts})

    never = [row for row in proposed_reviews if row["upstream_reason"] == "Never"]
    adjacent = [row for row in proposed_reviews if row["upstream_reason"] == "Adjacent"]
    return {
        "proposed_pair_reviews": proposed_reviews,
        "retained_nonzero_pair_reviews": retained_reviews,
        "summary": {
            "stress_pose_count": replay["pose_count"],
            "stress_pair_case_count": replay["summary"]["PAIR_CASES"],
            "proposed_pair_count": len(proposed_reviews),
            "proposed_adjacent_pair_count": len(adjacent),
            "proposed_never_pair_count": len(never),
            "supported_never_pair_count": sum(
                row["held_out_supports_never_reason"] is True for row in never),
            "contradicted_never_pair_count": sum(
                row["held_out_supports_never_reason"] is False for row in never),
            "retained_pair_count": len(rows) - len(proposed_pairs),
            "retained_collision_pair_count": sum(
                row["counts"]["AGREEMENT_COLLISION"] > 0 for row in retained_reviews),
            "retained_false_positive_pair_count": sum(
                row["counts"]["CANDIDATE_FALSE_POSITIVE"] > 0
                for row in retained_reviews),
            "retained_false_negative_pair_count": sum(
                row["counts"]["CANDIDATE_FALSE_NEGATIVE"] > 0
                for row in retained_reviews),
            "retained_pair_counts": retained_counts,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-review", type=Path, required=True)
    parser.add_argument("--never-review", type=Path, required=True)
    parser.add_argument("--stress-replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        policy = _load_receipt(args.policy_review, EXPECTED_POLICY_REVIEW_SHA256)
        never = _load_receipt(args.never_review, EXPECTED_NEVER_REVIEW_SHA256)
        replay = _load_stress_replay(args.stress_replay)
        if never["source_bindings"]["policy_review_sha256"] != policy["receipt_sha256"]:
            raise ValueError("never-pair review is not bound to policy review")
        assessment = _assess(policy["srdf_exclusions"], replay)
        blockers = [
            "POLICY_COUNTERFACTUAL_ONLY_NOT_INSTALLED",
            "HELD_OUT_FINITE_CORPUS_IS_NOT_CONTINUOUS_WORKSPACE_PROOF",
            "INSTALLED_MEASURED_GEOMETRY_ABSENT",
            "ENGINEERING_ACCEPTANCE_ABSENT",
            "TOOL_CAMERA_SUPPORT_AND_ENVIRONMENT_GEOMETRY_MISSING",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_collision_policy_stress.v2",
            "evidence_class": "HELD_OUT_POLICY_COUNTERFACTUAL_STRESS_ONLY",
            "source_bindings": {
                "policy_review_file_sha256": policy["_file_sha256"],
                "policy_review_sha256": policy["receipt_sha256"],
                "never_review_file_sha256": never["_file_sha256"],
                "never_review_sha256": never["receipt_sha256"],
                "geometry_candidate_sha256": EXPECTED_GEOMETRY_SHA256,
                "stress_replay_file_sha256": replay["_file_sha256"],
                "stress_replay_sha256": replay["receipt_sha256"],
            },
            "method": {
                "pose_family": "HALTON_INTERIOR", "halton_start_index": 1001,
                "halton_sample_count": 256,
                "corpus_relation": "DISJOINT_FROM_ORIGINAL_HALTON_1_THROUGH_32",
                "continuous_workspace_claimed": False,
            },
            **assessment,
            "installation_state": "COUNTERFACTUAL_ONLY_UNINSTALLED",
            "effective_exclusions": [], "default_pair_disposition": "CHECK_COLLISION",
            "collision_query_admissible": False, "clearance_replay_admissible": False,
            "controller_authority": False, "execution_permit_authority": False,
            "transport_authority": False, "hardware_access": False,
            "physical_authority": False, "wire_commands": [], "hardware_writes": 0,
            "physical_movements": 0, "blockers": blockers,
            "limitations": [
                "held_out_finite_samples_do_not_cover_continuous_joint_space",
                "stress_support_does_not_install_or_promote_exclusions",
                "raw_non_watertight_meshes_are_not_repaired",
                "no_measured_installed_tool_camera_support_or_environment_geometry",
                "no_controller_hardware_or_physical_qualification",
            ],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        args.output.write_bytes(
            (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        args.status_output.write_bytes((json.dumps({
            "status": "PASS_WITH_BLOCKERS", "receipt_sha256": receipt["receipt_sha256"],
            **receipt["summary"], "effective_exclusion_count": 0,
            "hardware_writes": 0, "physical_movements": 0, "blockers": blockers,
        }, sort_keys=True) + "\n").encode("utf-8"))
    except BaseException as exc:
        args.status_output.write_bytes((json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
        }, sort_keys=True) + "\n").encode("utf-8"))
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
