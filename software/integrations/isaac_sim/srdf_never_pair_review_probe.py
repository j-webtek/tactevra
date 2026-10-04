"""Review pinned SRDF ``Never`` pairs against the selected replay summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from collision_differential_probe import canonical_sha256, digest_bytes


EXPECTED_POLICY_REVIEW_SHA256 = (
    "c6c1df0b304f7f8b36bd6b8e1015244d1b5e427b24476a85f84b846de5001423"
)
EXPECTED_REPLAY_SHA256 = "1cad314d6901c0f639c4771f7be79b235eeadf844eba600129d4f8bb45991b87"


def _pair(first: str, second: str) -> tuple[str, str]:
    return tuple(sorted((first, second)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-review", type=Path, required=True)
    parser.add_argument("--replay-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        policy_path = args.policy_review.resolve(strict=True)
        replay_path = args.replay_summary.resolve(strict=True)
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        if policy["receipt_sha256"] != EXPECTED_POLICY_REVIEW_SHA256:
            raise ValueError("self-collision policy review identity mismatch")
        if replay["receipt_sha256"] != EXPECTED_REPLAY_SHA256:
            raise ValueError("triangle-partition replay identity mismatch")

        never_pairs = {
            tuple(row["body_pair"])
            for row in policy["srdf_exclusions"]
            if row["reason"] == "Never"
        }
        pair_rows = {
            _pair(*row["body_pair"]): row for row in replay["pair_summary"]
        }
        reviews = []
        total_cases = 0
        all_free = True
        for pair in sorted(never_pairs):
            row = pair_rows[pair]
            counts = row["counts"]
            case_count = sum(counts.values())
            total_cases += case_count
            supported = (
                counts["AGREEMENT_FREE"] == case_count
                and counts["AGREEMENT_COLLISION"] == 0
                and counts["CANDIDATE_FALSE_POSITIVE"] == 0
                and counts["CANDIDATE_FALSE_NEGATIVE"] == 0
                and row["minimum_raw_mesh_signed_distance_mm"] > 0.0
                and row["minimum_candidate_box_signed_distance_mm"] > 0.0
            )
            all_free = all_free and supported
            reviews.append({
                "body_pair": list(pair),
                "case_count": case_count,
                "counts": counts,
                "minimum_raw_mesh_signed_distance_mm": (
                    row["minimum_raw_mesh_signed_distance_mm"]
                ),
                "minimum_candidate_box_signed_distance_mm": (
                    row["minimum_candidate_box_signed_distance_mm"]
                ),
                "finite_replay_supports_never_reason": supported,
            })

        excluded = {
            tuple(row["body_pair"]) for row in policy["srdf_exclusions"]
        }
        retained_nonadjacent_collisions = []
        for pair, row in sorted(pair_rows.items()):
            collision_count = row["counts"]["AGREEMENT_COLLISION"]
            if row["kinematically_adjacent"] or pair in excluded or not collision_count:
                continue
            retained_nonadjacent_collisions.append({
                "body_pair": list(pair),
                "agreement_collision_count": collision_count,
                "minimum_raw_mesh_signed_distance_mm": (
                    row["minimum_raw_mesh_signed_distance_mm"]
                ),
                "minimum_candidate_box_signed_distance_mm": (
                    row["minimum_candidate_box_signed_distance_mm"]
                ),
            })

        blockers = [
            "FINITE_CORPUS_DOES_NOT_PROVE_NEVER_COLLISION",
            "RUNTIME_POLICY_CONTRACT_NOT_SELECTED",
            "EXCLUSION_PROFILE_NOT_INSTALLED",
            "TOOL_CAMERA_SUPPORT_AND_ENVIRONMENT_GEOMETRY_MISSING",
            "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_srdf_never_pair_review.v1",
            "evidence_class": "FINITE_REPLAY_SRDF_NEVER_REVIEW_ONLY",
            "source_bindings": {
                "policy_review_file_sha256": digest_bytes(policy_path.read_bytes()),
                "policy_review_sha256": policy["receipt_sha256"],
                "upstream_commit": policy["source_bindings"]["upstream_commit"],
                "upstream_srdf_sha256": policy["source_bindings"]["upstream_srdf_sha256"],
                "replay_summary_file_sha256": digest_bytes(replay_path.read_bytes()),
                "replay_summary_sha256": replay["receipt_sha256"],
            },
            "method": {
                "support_rule": (
                    "ALL_PAIR_CASES_AGREEMENT_FREE_AND_POSITIVE_RECORDED_MINIMA"
                ),
                "scope": "COMMITTED_49_POSE_PAIR_SUMMARY",
                "continuous_workspace_claimed": False,
            },
            "never_pair_reviews": reviews,
            "retained_nonexcluded_nonadjacent_collisions": retained_nonadjacent_collisions,
            "summary": {
                "never_pair_count": len(reviews),
                "never_pair_case_count": total_cases,
                "supported_never_pair_count": sum(
                    row["finite_replay_supports_never_reason"] for row in reviews
                ),
                "contradicted_never_pair_count": sum(
                    not row["finite_replay_supports_never_reason"] for row in reviews
                ),
                "all_never_pair_cases_agreement_free": all_free,
                "retained_nonexcluded_nonadjacent_collision_pair_count": len(
                    retained_nonadjacent_collisions
                ),
                "retained_nonexcluded_nonadjacent_collision_case_count": sum(
                    row["agreement_collision_count"]
                    for row in retained_nonadjacent_collisions
                ),
            },
            "never_exclusions_installable": False,
            "pair_exclusions_admissible": False,
            "collision_query_admissible": False,
            "clearance_replay_admissible": False,
            "blockers": blockers,
            "hardware_access": False,
            "physical_authority": False,
            "wire_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "finite_samples_support_but_do_not_prove_never_collision_semantics",
                "pair_summary_minima_do_not_establish_continuous_clearance",
                "no_runtime_exclusion_contract_or_profile_installation",
                "no_controller_hardware_or_physical_qualification",
            ],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.status_output.write_text(json.dumps({
            "status": "PASS_WITH_BLOCKERS",
            "receipt_sha256": receipt["receipt_sha256"],
            **receipt["summary"],
            "blockers": blockers,
        }, sort_keys=True) + "\n", encoding="utf-8")
    except BaseException as exc:
        args.status_output.write_text(json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
        }, sort_keys=True) + "\n", encoding="utf-8")
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
