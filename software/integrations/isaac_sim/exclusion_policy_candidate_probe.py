"""Build an inert exclusion-policy candidate from retained WP2 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


BASE_CONTRACT_SHA256 = "d3238c0c95a1d2e7ff74fcb8dccc3eb0aadb0f897b2ea041319bbcd6442af5c3"
ROBOT_MODEL_SHA256 = "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
GEOMETRY_CANDIDATE_SHA256 = "0568f7ba269cf190ca4b9d6bc41ac17c90c72c3489fad433bb064ca2239e5fc6"
REPLAY_SHA256 = "1cad314d6901c0f639c4771f7be79b235eeadf844eba600129d4f8bb45991b87"
POLICY_REVIEW_SHA256 = "c6c1df0b304f7f8b36bd6b8e1015244d1b5e427b24476a85f84b846de5001423"
NEVER_REVIEW_SHA256 = "a2210f019e0dae09274be1e30b36dbaf69ffe3064b54030bb699568c9230c0e8"
SRDF_SHA256 = "29f1daaeea91a490b85581a9a62dd07be9ab959d7817fad89836c466e8288499"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _load(path: Path, expected: str, label: str) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if value.get("receipt_sha256") != expected:
        raise ValueError(f"{label} identity mismatch")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--geometry-candidate", type=Path, required=True)
    parser.add_argument("--replay-summary", type=Path, required=True)
    parser.add_argument("--policy-review", type=Path, required=True)
    parser.add_argument("--never-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        workspace = args.workspace.resolve(strict=True)
        geometry = _load(args.geometry_candidate, GEOMETRY_CANDIDATE_SHA256, "geometry")
        replay = _load(args.replay_summary, REPLAY_SHA256, "replay")
        policy = _load(args.policy_review, POLICY_REVIEW_SHA256, "policy review")
        never = _load(args.never_review, NEVER_REVIEW_SHA256, "Never review")
        if policy["source_bindings"]["upstream_srdf_sha256"] != SRDF_SHA256:
            raise ValueError("policy review SRDF identity mismatch")

        sys.path.insert(0, str(workspace / "software/src"))
        from rocell.application.collision_readiness import assess_current_collision_readiness
        from rocell.application.context import load_simulation_context

        context = load_simulation_context(workspace, workspace / "software/config/system_manifest.json")
        readiness = assess_current_collision_readiness(context)
        if readiness.contract.content_hash != BASE_CONTRACT_SHA256:
            raise ValueError("base collision contract identity mismatch")
        if readiness.urdf_sha256 != ROBOT_MODEL_SHA256:
            raise ValueError("robot model identity mismatch")

        body_map = {
            "base_link": "robot:base_link",
            "link1": "robot:link1",
            "link2": "robot:link2",
            "link3": "robot:link3",
            "link4": "robot:link4",
            "link5": "robot:link5",
            "gripper_link": "robot:gripper",
        }
        proposals = []
        for row in policy["srdf_exclusions"]:
            reason = row["reason"]
            proposals.append({
                "body_pair": sorted(body_map[value] for value in row["body_pair"]),
                "upstream_reason": f"UPSTREAM_SRDF_{reason.upper()}",
                "supporting_evidence_sha256": (
                    policy["receipt_sha256"] if reason == "Adjacent" else never["receipt_sha256"]
                ),
            })
        proposals.sort(key=lambda row: tuple(row["body_pair"]))
        source_bindings = {
            "upstream_srdf": SRDF_SHA256,
            "selected_geometry_candidate": geometry["receipt_sha256"],
            "selected_replay": replay["receipt_sha256"],
            "adjacent_policy_review": policy["receipt_sha256"],
            "never_pair_review": never["receipt_sha256"],
        }
        document: dict[str, object] = {
            "schema": "rocell.collision_exclusion_policy_candidate.v1",
            "policy_id": "ROARM-M3-WP2-SRDF-CANDIDATE-20260929",
            "installation_state": "CANDIDATE_UNINSTALLED",
            "default_pair_disposition": "CHECK_COLLISION",
            "base_contract_sha256": readiness.contract.content_hash,
            "robot_model_sha256": readiness.urdf_sha256,
            "geometry_candidate_sha256": geometry["receipt_sha256"],
            "source_bindings": source_bindings,
            "proposed_exclusions": proposals,
            "effective_exclusions": [],
            "authority": {
                "collision_query": False,
                "clearance_replay": False,
                "controller": False,
                "execution_permit": False,
                "transport": False,
                "physical": False,
            },
        }
        document["content_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
        args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.status_output.write_text(json.dumps({
            "status": "PASS_WITH_BLOCKERS",
            "content_sha256": document["content_sha256"],
            "proposed_exclusion_count": len(proposals),
            "effective_exclusion_count": 0,
            "default_pair_disposition": "CHECK_COLLISION",
            "hardware_writes": 0,
            "physical_movements": 0,
            "blockers": [
                "CANDIDATE_UNINSTALLED",
                "EFFECTIVE_EXCLUSIONS_EMPTY",
                "INSTALLED_MEASURED_GEOMETRY_ABSENT",
                "ENGINEERING_ACCEPTANCE_ABSENT",
            ],
        }, sort_keys=True) + "\n", encoding="utf-8")
    except BaseException as exc:
        args.status_output.write_text(json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
        }, sort_keys=True) + "\n", encoding="utf-8")
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
