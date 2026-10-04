"""Assess an inert exclusion candidate against held-out joint-space replay.

This probe reports contradictions and retained-pair behavior. It cannot install
an exclusion or grant collision-query, controller, hardware, or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from collision_differential_probe import canonical_sha256, digest_bytes


EXPECTED_BASE_CONTRACT_SHA256 = (
    "d3238c0c95a1d2e7ff74fcb8dccc3eb0aadb0f897b2ea041319bbcd6442af5c3"
)
EXPECTED_ROBOT_MODEL_SHA256 = (
    "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
)
EXPECTED_GEOMETRY_SHA256 = (
    "0568f7ba269cf190ca4b9d6bc41ac17c90c72c3489fad433bb064ca2239e5fc6"
)
EXPECTED_CANDIDATE_FILE_SHA256 = (
    "88e31c4b525ded8ca48d4bae7cf70faff396e2d9f92249296f2b2f3a9c1d3c3f"
)
EXPECTED_SOURCE_BINDINGS = {
    "upstream_srdf": "29f1daaeea91a490b85581a9a62dd07be9ab959d7817fad89836c466e8288499",
    "selected_geometry_candidate": EXPECTED_GEOMETRY_SHA256,
    "selected_replay": "1cad314d6901c0f639c4771f7be79b235eeadf844eba600129d4f8bb45991b87",
    "adjacent_policy_review": "c6c1df0b304f7f8b36bd6b8e1015244d1b5e427b24476a85f84b846de5001423",
    "never_pair_review": "a2210f019e0dae09274be1e30b36dbaf69ffe3064b54030bb699568c9230c0e8",
}
KNOWN_BODY_IDS = (
    "robot:base_link", "robot:link1", "robot:link2", "robot:link3",
    "robot:link4", "robot:link5", "robot:gripper",
)
BODY_TO_REPLAY = {
    "robot:base_link": "base_link",
    "robot:link1": "link1",
    "robot:link2": "link2",
    "robot:link3": "link3",
    "robot:link4": "link4",
    "robot:link5": "link5",
    "robot:gripper": "gripper_link",
}
OUTCOMES = (
    "AGREEMENT_COLLISION", "AGREEMENT_FREE",
    "CANDIDATE_FALSE_POSITIVE", "CANDIDATE_FALSE_NEGATIVE",
)


def _load_replay(path: Path) -> dict:
    payload = path.resolve(strict=True).read_bytes()
    replay = json.loads(payload.decode("utf-8"))
    claimed = replay.get("receipt_sha256")
    unsigned = dict(replay)
    unsigned.pop("receipt_sha256", None)
    if claimed != canonical_sha256(unsigned):
        raise ValueError("stress replay receipt hash mismatch")
    method = replay.get("method", {})
    if (
        method.get("halton_start_index") != 1001
        or method.get("halton_sample_count") != 256
        or method.get("anchors_included") is not False
        or method.get("pose_families") != ["HALTON_INTERIOR"]
        or replay.get("pose_count") != 256
    ):
        raise ValueError("stress replay is not the declared held-out corpus")
    if replay.get("source_bindings", {}).get("governed_urdf_sha256") != EXPECTED_ROBOT_MODEL_SHA256:
        raise ValueError("stress replay robot model mismatch")
    if replay.get("source_bindings", {}).get("reduction_receipt_sha256") != EXPECTED_GEOMETRY_SHA256:
        raise ValueError("stress replay geometry mismatch")
    replay["_file_sha256"] = hashlib.sha256(payload).hexdigest()
    return replay


def _assess(candidate, replay: dict) -> dict:
    rows = {
        tuple(sorted(row["body_pair"])): row for row in replay["pair_summary"]
    }
    proposed_pairs: set[tuple[str, str]] = set()
    proposed_reviews = []
    for proposal in candidate.proposed_exclusions:
        replay_pair = tuple(sorted(BODY_TO_REPLAY[value] for value in proposal.body_pair))
        proposed_pairs.add(replay_pair)
        row = rows[replay_pair]
        counts = {name: int(row["counts"][name]) for name in OUTCOMES}
        case_count = sum(counts.values())
        never_supported = None
        if proposal.upstream_reason == "UPSTREAM_SRDF_NEVER":
            never_supported = (
                counts == {
                    "AGREEMENT_COLLISION": 0,
                    "AGREEMENT_FREE": case_count,
                    "CANDIDATE_FALSE_POSITIVE": 0,
                    "CANDIDATE_FALSE_NEGATIVE": 0,
                }
                and row["minimum_raw_mesh_signed_distance_mm"] > 0.0
                and row["minimum_candidate_box_signed_distance_mm"] > 0.0
            )
        proposed_reviews.append({
            "body_pair": list(proposal.body_pair),
            "replay_body_pair": list(replay_pair),
            "upstream_reason": proposal.upstream_reason,
            "case_count": case_count,
            "counts": counts,
            "minimum_raw_mesh_signed_distance_mm": row["minimum_raw_mesh_signed_distance_mm"],
            "minimum_candidate_box_signed_distance_mm": row["minimum_candidate_box_signed_distance_mm"],
            "held_out_supports_never_reason": never_supported,
        })

    retained_counts = {name: 0 for name in OUTCOMES}
    retained_pair_count = 0
    retained_pair_reviews = []
    for pair, row in rows.items():
        if pair in proposed_pairs:
            continue
        retained_pair_count += 1
        counts = {name: int(row["counts"][name]) for name in OUTCOMES}
        for outcome in OUTCOMES:
            retained_counts[outcome] += counts[outcome]
        if (
            counts["AGREEMENT_COLLISION"]
            or counts["CANDIDATE_FALSE_POSITIVE"]
            or counts["CANDIDATE_FALSE_NEGATIVE"]
        ):
            retained_pair_reviews.append({
                "body_pair": list(pair),
                "counts": counts,
                "minimum_raw_mesh_signed_distance_mm": (
                    row["minimum_raw_mesh_signed_distance_mm"]
                ),
                "minimum_candidate_box_signed_distance_mm": (
                    row["minimum_candidate_box_signed_distance_mm"]
                ),
            })

    never_reviews = [
        row for row in proposed_reviews
        if row["upstream_reason"] == "UPSTREAM_SRDF_NEVER"
    ]
    adjacent_reviews = [
        row for row in proposed_reviews
        if row["upstream_reason"] == "UPSTREAM_SRDF_ADJACENT"
    ]
    return {
        "proposed_pair_reviews": proposed_reviews,
        "retained_nonzero_pair_reviews": retained_pair_reviews,
        "summary": {
            "stress_pose_count": replay["pose_count"],
            "stress_pair_case_count": replay["summary"]["PAIR_CASES"],
            "proposed_pair_count": len(proposed_reviews),
            "proposed_adjacent_pair_count": len(adjacent_reviews),
            "proposed_never_pair_count": len(never_reviews),
            "supported_never_pair_count": sum(
                row["held_out_supports_never_reason"] is True for row in never_reviews
            ),
            "contradicted_never_pair_count": sum(
                row["held_out_supports_never_reason"] is False for row in never_reviews
            ),
            "retained_pair_count": retained_pair_count,
            "retained_collision_pair_count": sum(
                row["counts"]["AGREEMENT_COLLISION"] > 0
                for row in retained_pair_reviews
            ),
            "retained_false_positive_pair_count": sum(
                row["counts"]["CANDIDATE_FALSE_POSITIVE"] > 0
                for row in retained_pair_reviews
            ),
            "retained_false_negative_pair_count": sum(
                row["counts"]["CANDIDATE_FALSE_NEGATIVE"] > 0
                for row in retained_pair_reviews
            ),
            "retained_pair_counts": retained_counts,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--stress-replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        workspace = args.workspace.resolve(strict=True)
        sys.path.insert(0, str(workspace / "software/src"))
        from rocell.simulation.exclusion_policy import (
            load_collision_exclusion_policy_candidate,
        )

        candidate = load_collision_exclusion_policy_candidate(
            args.candidate,
            EXPECTED_CANDIDATE_FILE_SHA256,
            expected_base_contract_sha256=EXPECTED_BASE_CONTRACT_SHA256,
            expected_robot_model_sha256=EXPECTED_ROBOT_MODEL_SHA256,
            expected_geometry_candidate_sha256=EXPECTED_GEOMETRY_SHA256,
            expected_source_bindings=EXPECTED_SOURCE_BINDINGS,
            known_body_ids=KNOWN_BODY_IDS,
        )
        replay_path = args.stress_replay.resolve(strict=True)
        replay = _load_replay(replay_path)
        assessment = _assess(candidate, replay)
        blockers = [
            "CANDIDATE_UNINSTALLED",
            "EFFECTIVE_EXCLUSIONS_EMPTY",
            "HELD_OUT_FINITE_CORPUS_IS_NOT_CONTINUOUS_WORKSPACE_PROOF",
            "INSTALLED_MEASURED_GEOMETRY_ABSENT",
            "ENGINEERING_ACCEPTANCE_ABSENT",
            "TOOL_CAMERA_SUPPORT_AND_ENVIRONMENT_GEOMETRY_MISSING",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_collision_policy_stress.v1",
            "evidence_class": "HELD_OUT_POLICY_CANDIDATE_STRESS_ONLY",
            "source_bindings": {
                "candidate_file_sha256": candidate.file_sha256,
                "candidate_content_sha256": candidate.content_sha256,
                "base_contract_sha256": candidate.base_contract_sha256,
                "robot_model_sha256": candidate.robot_model_sha256,
                "geometry_candidate_sha256": candidate.geometry_candidate_sha256,
                "stress_replay_file_sha256": replay["_file_sha256"],
                "stress_replay_sha256": replay["receipt_sha256"],
            },
            "method": {
                "pose_family": "HALTON_INTERIOR",
                "halton_start_index": 1001,
                "halton_sample_count": 256,
                "corpus_relation": "DISJOINT_FROM_ORIGINAL_HALTON_1_THROUGH_32",
                "never_support_rule": "ALL_CASES_FREE_WITH_POSITIVE_RECORDED_MINIMA",
                "continuous_workspace_claimed": False,
            },
            **assessment,
            "installation_state": "CANDIDATE_UNINSTALLED",
            "effective_exclusions": [],
            "default_pair_disposition": "CHECK_COLLISION",
            "collision_query_admissible": False,
            "clearance_replay_admissible": False,
            "controller_authority": False,
            "execution_permit_authority": False,
            "transport_authority": False,
            "hardware_access": False,
            "physical_authority": False,
            "wire_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "blockers": blockers,
            "limitations": [
                "held_out_finite_samples_do_not_cover_continuous_joint_space",
                "stress_support_does_not_install_or_promote_exclusions",
                "raw_non_watertight_meshes_are_not_repaired",
                "no_measured_installed_tool_camera_support_or_environment_geometry",
                "no_controller_hardware_or_physical_qualification",
            ],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        args.output.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        args.status_output.write_text(json.dumps({
            "status": "PASS_WITH_BLOCKERS",
            "receipt_sha256": receipt["receipt_sha256"],
            **receipt["summary"],
            "effective_exclusion_count": 0,
            "hardware_writes": 0,
            "physical_movements": 0,
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
