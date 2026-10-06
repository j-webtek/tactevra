"""Review pinned RoArm-M3 SRDF exclusions against retained collision evidence.

This probe binds semantic collision policy evidence and computes counterfactual
summary counts.  It never installs exclusions or grants collision-query,
controller, hardware, or physical authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from collision_differential_probe import UPSTREAM_COMMIT, _blob, canonical_sha256, digest_bytes


SRDF_PATH = "src/roarm_main/roarm_moveit/config/roarm_m3/roarm_m3.srdf"
EXPECTED_SRDF_SHA256 = "29f1daaeea91a490b85581a9a62dd07be9ab959d7817fad89836c466e8288499"
EXPECTED_REPLAY_SHA256 = "f511d844f2b66c4cd6054c5c1c73425108f15815eeca6c2726bd819896fd3ee5"
OUTCOMES = (
    "AGREEMENT_COLLISION",
    "AGREEMENT_FREE",
    "CANDIDATE_FALSE_POSITIVE",
    "CANDIDATE_FALSE_NEGATIVE",
)


def _pair(first: str, second: str) -> tuple[str, str]:
    return tuple(sorted((first, second)))


def _counterfactual(pair_rows: list[dict], excluded: set[tuple[str, str]]) -> dict:
    retained = {name: 0 for name in OUTCOMES}
    removed = {name: 0 for name in OUTCOMES}
    retained_cases = 0
    removed_cases = 0
    for row in pair_rows:
        counts = row["counts"]
        target = removed if _pair(*row["body_pair"]) in excluded else retained
        for outcome in OUTCOMES:
            target[outcome] += counts[outcome]
        count = sum(counts.values())
        if target is removed:
            removed_cases += count
        else:
            retained_cases += count
    return {
        "excluded_pair_count": len(excluded),
        "excluded_case_count": removed_cases,
        "retained_case_count": retained_cases,
        "retained_counts": retained,
        "excluded_counts": removed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--replay-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        workspace = args.workspace.resolve(strict=True)
        upstream = args.upstream_repo.resolve(strict=True)
        replay_path = args.replay_summary.resolve(strict=True)
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        if replay["receipt_sha256"] != EXPECTED_REPLAY_SHA256:
            raise ValueError("triangle-partition replay identity mismatch")

        srdf_bytes = _blob(upstream, SRDF_PATH)
        if digest_bytes(srdf_bytes) != EXPECTED_SRDF_SHA256:
            raise ValueError("RoArm-M3 SRDF identity mismatch")
        srdf_root = ET.fromstring(srdf_bytes)
        if srdf_root.attrib.get("name") != "roarm_m3":
            raise ValueError("unexpected SRDF robot name")
        exclusions = []
        seen_pairs: set[tuple[str, str]] = set()
        for element in srdf_root.findall("disable_collisions"):
            pair = _pair(element.attrib["link1"], element.attrib["link2"])
            if pair in seen_pairs:
                raise ValueError(f"duplicate SRDF exclusion: {pair}")
            seen_pairs.add(pair)
            exclusions.append({
                "body_pair": list(pair),
                "reason": element.attrib["reason"],
            })
        exclusions.sort(key=lambda row: tuple(row["body_pair"]))

        urdf_path = workspace / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
        urdf_bytes = urdf_path.read_bytes()
        urdf_root = ET.fromstring(urdf_bytes)
        if urdf_root.attrib.get("name") != "roarm_m3":
            raise ValueError("unexpected governed URDF robot name")
        mesh_links = {link for row in replay["pair_summary"] for link in row["body_pair"]}
        direct_joint_pairs = set()
        for joint in urdf_root.findall("joint"):
            parent = joint.find("parent").attrib["link"]
            child = joint.find("child").attrib["link"]
            if parent in mesh_links and child in mesh_links:
                direct_joint_pairs.add(_pair(parent, child))

        adjacent_exclusions = {
            tuple(row["body_pair"]) for row in exclusions if row["reason"] == "Adjacent"
        }
        never_exclusions = {
            tuple(row["body_pair"]) for row in exclusions if row["reason"] == "Never"
        }
        if adjacent_exclusions != direct_joint_pairs:
            raise ValueError("SRDF Adjacent exclusions do not match governed direct joints")
        if adjacent_exclusions & never_exclusions:
            raise ValueError("SRDF exclusion reasons overlap")

        false_positive_pairs = []
        unsupported_false_positive_pairs = []
        for row in replay["pair_summary"]:
            count = row["counts"]["CANDIDATE_FALSE_POSITIVE"]
            if not count:
                continue
            pair = _pair(*row["body_pair"])
            supported = pair in adjacent_exclusions and row["kinematically_adjacent"]
            record = {
                "body_pair": list(pair),
                "false_positive_count": count,
                "governed_direct_joint_pair": pair in direct_joint_pairs,
                "srdf_reason": next(
                    (item["reason"] for item in exclusions if tuple(item["body_pair"]) == pair),
                    None,
                ),
                "supported_by_adjacent_policy_evidence": supported,
            }
            false_positive_pairs.append(record)
            if not supported:
                unsupported_false_positive_pairs.append(record)

        adjacent_counterfactual = _counterfactual(replay["pair_summary"], adjacent_exclusions)
        full_counterfactual = _counterfactual(
            replay["pair_summary"], adjacent_exclusions | never_exclusions
        )
        blockers = [
            "COUNTERFACTUAL_ONLY_NOT_INSTALLED",
            "RUNTIME_POLICY_CONTRACT_NOT_SELECTED",
            "FINITE_CORPUS_IS_NOT_CONTINUOUS_WORKSPACE_COVERAGE",
            "NON_WATERTIGHT_RAW_MESHES",
            "TOOL_CAMERA_SUPPORT_AND_ENVIRONMENT_GEOMETRY_MISSING",
            "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_self_collision_policy_review.v1",
            "evidence_class": "PINNED_UPSTREAM_POLICY_COUNTERFACTUAL_ONLY",
            "source_bindings": {
                "upstream_commit": UPSTREAM_COMMIT,
                "upstream_srdf_path": SRDF_PATH,
                "upstream_srdf_sha256": EXPECTED_SRDF_SHA256,
                "governed_urdf_file_sha256": digest_bytes(urdf_bytes),
                "replay_summary_file_sha256": digest_bytes(replay_path.read_bytes()),
                "replay_summary_sha256": replay["receipt_sha256"],
            },
            "method": {
                "srdf_robot_name": srdf_root.attrib["name"],
                "urdf_robot_name": urdf_root.attrib["name"],
                "pair_normalization": "LEXICOGRAPHIC_LINK_NAMES",
                "adjacent_support_rule": (
                    "SRDF_REASON_ADJACENT_AND_GOVERNED_DIRECT_JOINT_PAIR"
                ),
                "counterfactual_scope": "PAIR_SUMMARY_COUNTS_ONLY",
            },
            "srdf_exclusions": exclusions,
            "summary": {
                "srdf_exclusion_count": len(exclusions),
                "srdf_adjacent_exclusion_count": len(adjacent_exclusions),
                "srdf_never_exclusion_count": len(never_exclusions),
                "governed_direct_joint_pair_count": len(direct_joint_pairs),
                "false_positive_pair_count": len(false_positive_pairs),
                "false_positive_case_count": sum(
                    row["false_positive_count"] for row in false_positive_pairs
                ),
                "unsupported_false_positive_pair_count": len(unsupported_false_positive_pairs),
            },
            "false_positive_pair_review": false_positive_pairs,
            "unsupported_false_positive_pairs": unsupported_false_positive_pairs,
            "adjacent_only_counterfactual": adjacent_counterfactual,
            "full_srdf_counterfactual": full_counterfactual,
            "exclusion_profile_installable": False,
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
                "upstream_srdf_semantics_do_not_install_a_local_runtime_policy",
                "counterfactual_removes_entire_pair_cases_without_requerying_geometry",
                "finite_replay_does_not_cover_continuous_joint_space",
                "never_reason_pairs_require_separate_review_before_any_policy_selection",
                "no_controller_hardware_or_physical_qualification",
            ],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        args.output.write_bytes((json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        args.status_output.write_bytes((json.dumps({
            "status": "PASS_WITH_BLOCKERS",
            "receipt_sha256": receipt["receipt_sha256"],
            **receipt["summary"],
            "blockers": blockers,
        }, sort_keys=True) + "\n").encode("utf-8"))
    except BaseException as exc:
        args.status_output.write_bytes((json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
        }, sort_keys=True) + "\n").encode("utf-8"))
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
