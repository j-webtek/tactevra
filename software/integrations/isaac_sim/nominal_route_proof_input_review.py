"""Independently review and certify ARM-259 native-sweep proof inputs.

ARM-260 reopens the pinned mesh receipt and governed URDF, independently
recomputes all sphere bounds and direct adjacency pairs, and rejects any drift.
Its accepted outputs are scoped only to the pinned simulation model.  The
review does not import or start Isaac and grants no attempt or physical access.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from decimal import Decimal, ROUND_CEILING, localcontext
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree


REVIEW_SCHEMA = "tactevra.isaac_lm4_native_sweep_proof_input_review.v1"
PROPOSAL_SCHEMA = "tactevra.isaac_lm4_native_sweep_proof_input_proposal.v1"
MESH_RECEIPT_SCHEMA = "tactevra.isaac_sim_upstream_link_mesh_binding.v1"
SPHERE_PROFILE_SCHEMA = "tactevra.isaac_lm4_link_sphere_profile.v1"
PAIR_POLICY_SCHEMA = "tactevra.isaac_lm4_continuous_clearance_pair_policy.v1"
EXPECTED_URDF_SHA256 = (
    "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
)
EXPECTED_MESH_RECEIPT_SHA256 = (
    "dbb8b56a602ac4c2b69073af23d61700aee12c0153080bdf58b7f5990b92646e"
)
PROPOSAL_STATUS = "PROPOSED_FOR_INDEPENDENT_SIMULATION_CONTINUOUS_CLEARANCE_REVIEW"
CERTIFIED_PROFILE_STATUS = "CERTIFIED_FOR_SIMULATION_CONTINUOUS_CLEARANCE"
ACCEPTED_POLICY_STATUS = "ACCEPTED_FOR_SIMULATION_CONTINUOUS_CLEARANCE"
SOURCE_TO_RUNTIME_LINK = {
    "base_link": "robot:base_link",
    "link1": "robot:link1",
    "link2": "robot:link2",
    "link3": "robot:link3",
    "link4": "robot:link4",
    "link5": "robot:link5",
    "gripper_link": "robot:gripper",
}


class ProofInputReviewError(ValueError):
    """Raised when a proposed proof input cannot be independently certified."""


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
        raise ProofInputReviewError("review input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise ProofInputReviewError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("hardware_access") is False
        and document.get("hardware_writes", 0) == 0
        and document.get("physical_authority") is False
        and document.get("physical_movements", 0) == 0
        and document.get("controller_commands", []) == []
        and document.get("wire_commands", []) == []
        and document.get("gate_promotions", []) == []
    )


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProofInputReviewError(f"{label} is not numeric")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ProofInputReviewError(f"{label} is not finite")
    return result


def _independent_sphere(bounds: object, label: str) -> tuple[list[float], float]:
    if (
        not isinstance(bounds, list)
        or len(bounds) != 2
        or not all(isinstance(row, list) and len(row) == 3 for row in bounds)
    ):
        raise ProofInputReviewError(f"{label} bounds changed")
    low = [_decimal(item, f"{label} lower") for item in bounds[0]]
    high = [_decimal(item, f"{label} upper") for item in bounds[1]]
    if any(left >= right for left, right in zip(low, high)):
        raise ProofInputReviewError(f"{label} bounds are empty")
    with localcontext() as context:
        context.prec = 50
        center = [(left + right) / 2 for left, right in zip(low, high)]
        half = [(right - left) / 2 for left, right in zip(low, high)]
        radius = sum(component**2 for component in half).sqrt()
        rounded = radius.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)
        for corner in itertools.product(*zip(low, high)):
            squared_distance = sum(
                (coordinate - origin) ** 2 for coordinate, origin in zip(corner, center)
            )
            if squared_distance > rounded**2:
                raise ProofInputReviewError(f"{label} corner is not contained")
    return [float(value) for value in center], float(rounded)


def _review_sources(
    proposal: Mapping[str, Any],
    mesh_receipt: Mapping[str, Any],
    urdf_bytes: bytes,
    *,
    proposal_file_sha256: str,
    mesh_receipt_file_sha256: str,
    urdf_file_sha256: str,
) -> tuple[str, list[dict[str, Any]], list[list[str]]]:
    proposal_hash = _require_hash(proposal, "proposal_sha256", "ARM-259 proposal")
    receipt_hash = _require_hash(
        mesh_receipt, "receipt_sha256", "upstream mesh receipt"
    )
    if (
        proposal.get("schema") != PROPOSAL_SCHEMA
        or proposal.get("status") != "READY_FOR_INDEPENDENT_PROOF_INPUT_REVIEW"
        or proposal.get("proposal_id") != "arm259-native-sweep-proof-input-proposal-001"
        or proposal.get("certified_inputs_emitted") is not False
        or proposal.get("native_binding_admitted") is not False
        or proposal.get("launch_admitted") is not False
        or proposal.get("attempt_consumed") is not False
        or proposal.get("isaac_started") is not False
        or proposal.get("trajectory_playback") is not False
        or not _zero_authority(proposal)
        or not isinstance(proposal_file_sha256, str)
        or len(proposal_file_sha256) != 64
    ):
        raise ProofInputReviewError("ARM-259 proposal boundary changed")
    if (
        urdf_file_sha256 != EXPECTED_URDF_SHA256
        or hashlib.sha256(urdf_bytes).hexdigest() != EXPECTED_URDF_SHA256
        or receipt_hash != EXPECTED_MESH_RECEIPT_SHA256
        or mesh_receipt.get("schema") != MESH_RECEIPT_SCHEMA
        or proposal.get("source_files_sha256")
        != {
            "governed_urdf": urdf_file_sha256,
            "upstream_mesh_receipt": mesh_receipt_file_sha256,
        }
    ):
        raise ProofInputReviewError("ARM-259 source identity changed")

    binding = mesh_receipt.get("xacro_binding")
    inventory = mesh_receipt.get("mesh_inventory")
    if (
        not isinstance(binding, Mapping)
        or binding.get("link_count") != 7
        or binding.get("mesh_origin_xyz") != [0.0, 0.0, 0.0]
        or binding.get("mesh_origin_rpy") != [0.0, 0.0, 0.0]
        or binding.get("mesh_scale") != [0.001, 0.001, 0.001]
        or binding.get("visual_and_collision_references_identical") is not True
        or not isinstance(inventory, list)
        or len(inventory) != 7
    ):
        raise ProofInputReviewError("mesh binding semantics changed")

    expected_spheres: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in inventory:
        if not isinstance(row, Mapping):
            raise ProofInputReviewError("mesh inventory row changed")
        source_link = row.get("link_name")
        mesh_hash = row.get("sha256")
        if (
            not isinstance(source_link, str)
            or source_link in seen
            or source_link not in SOURCE_TO_RUNTIME_LINK
            or not isinstance(mesh_hash, str)
            or len(mesh_hash) != 64
        ):
            raise ProofInputReviewError("mesh inventory identity changed")
        seen.add(source_link)
        center, radius = _independent_sphere(
            row.get("local_bounds_source_units"), source_link
        )
        expected_spheres.append(
            {
                "link_name": SOURCE_TO_RUNTIME_LINK[source_link],
                "source_link_name": source_link,
                "local_center_mm": center,
                "radius_mm": radius,
                "source_bounds_mm": row["local_bounds_source_units"],
                "source_mesh_sha256": mesh_hash,
                "source_processed_vertex_count": row.get("processed_vertex_count"),
                "source_watertight": row.get("watertight"),
                "containment_method": (
                    "AABB_CORNER_ENCLOSING_SPHERE_RADIUS_CEILED_TO_1E_6_MM"
                ),
            }
        )
    if seen != set(SOURCE_TO_RUNTIME_LINK):
        raise ProofInputReviewError("mesh inventory is incomplete")

    try:
        root = ElementTree.fromstring(urdf_bytes)
    except ElementTree.ParseError as exc:
        raise ProofInputReviewError("governed URDF XML changed") from exc
    if root.tag != "robot" or root.attrib.get("name") != "roarm_m3":
        raise ProofInputReviewError("governed URDF robot changed")
    pairs: set[tuple[str, str]] = set()
    for joint in root.findall("joint"):
        parent = joint.find("parent")
        child = joint.find("child")
        if parent is None or child is None:
            raise ProofInputReviewError("governed URDF joint changed")
        parent_name = parent.attrib.get("link")
        child_name = child.attrib.get("link")
        if (
            parent_name in SOURCE_TO_RUNTIME_LINK
            and child_name in SOURCE_TO_RUNTIME_LINK
        ):
            pairs.add(
                tuple(
                    sorted(
                        (
                            SOURCE_TO_RUNTIME_LINK[parent_name],
                            SOURCE_TO_RUNTIME_LINK[child_name],
                        )
                    )
                )
            )
    expected_pairs = [list(pair) for pair in sorted(pairs)]
    if len(expected_pairs) != 6:
        raise ProofInputReviewError("governed URDF adjacency changed")
    return proposal_hash, expected_spheres, expected_pairs


def _certify_profile(
    proposed: Mapping[str, Any],
    expected_spheres: list[dict[str, Any]],
    proposal_hash: str,
) -> dict[str, Any]:
    _require_hash(proposed, "profile_sha256", "ARM-259 sphere profile")
    if (
        proposed.get("schema") != SPHERE_PROFILE_SCHEMA
        or proposed.get("status") != PROPOSAL_STATUS
        or proposed.get("source_urdf_sha256") != EXPECTED_URDF_SHA256
        or proposed.get("geometry_scope") != "PINNED_UPSTREAM_SIMULATION_MODEL_ONLY"
        or proposed.get("link_spheres") != expected_spheres
        or proposed.get("installed_geometry_claimed") is not False
        or proposed.get("hardware_access") is not False
        or proposed.get("physical_authority") is not False
    ):
        raise ProofInputReviewError("sphere profile proposal failed independent review")
    core = dict(proposed)
    source_profile_hash = core.pop("profile_sha256")
    core["status"] = CERTIFIED_PROFILE_STATUS
    core["source_proposal_sha256"] = proposal_hash
    core["source_proposal_profile_sha256"] = source_profile_hash
    core["certification_scope"] = (
        "PINNED_UPSTREAM_SIMULATION_MODEL_VERTEX_CONTAINMENT_ONLY"
    )
    core["limitations"] = [
        "single_spheres_are_conservative_and_may_produce_false_positive_hits",
        "non_watertight_meshes_limit_solid_claims_but_not_retained_vertex_containment",
        "profile_excludes_installed_tool_clamp_cable_and_optional_arm_camera_geometry",
        "simulation_model_containment_does_not_qualify_installed_physical_clearance",
    ]
    return {**core, "profile_sha256": _sha(core)}


def _accept_policy(
    proposed: Mapping[str, Any],
    expected_pairs: list[list[str]],
    proposal_hash: str,
) -> dict[str, Any]:
    _require_hash(proposed, "policy_sha256", "ARM-259 pair policy")
    if (
        proposed.get("schema") != PAIR_POLICY_SCHEMA
        or proposed.get("status") != PROPOSAL_STATUS
        or proposed.get("source_urdf_sha256") != EXPECTED_URDF_SHA256
        or proposed.get("accepted_exclusion_pairs") != expected_pairs
        or proposed.get("exclusion_basis")
        != "DIRECT_PARENT_CHILD_RELATIONSHIP_IN_GOVERNED_URDF"
        or proposed.get("default_pair_disposition") != "CHECK_MOVING_SELF_COLLISION"
        or proposed.get("finite_sample_evidence_used_for_exclusion") is not False
        or proposed.get("installed_geometry_claimed") is not False
        or proposed.get("hardware_access") is not False
        or proposed.get("physical_authority") is not False
    ):
        raise ProofInputReviewError("pair policy proposal failed independent review")
    core = dict(proposed)
    source_policy_hash = core.pop("policy_sha256")
    core["status"] = ACCEPTED_POLICY_STATUS
    core["source_proposal_sha256"] = proposal_hash
    core["source_proposal_policy_sha256"] = source_policy_hash
    core["acceptance_scope"] = "PINNED_SIMULATION_MODEL_DIRECT_ADJACENCY_ONLY"
    core["limitations"] = [
        "only_directly_connected_required_robot_links_are_excluded",
        "no_srdf_never_pair_or_finite_sample_exclusion_is_promoted",
        "policy_scope_is_simulation_model_continuous_clearance_only",
        "policy_does_not_qualify_installed_physical_clearance",
    ]
    return {**core, "policy_sha256": _sha(core)}


def build_review(
    proposal: Mapping[str, Any],
    mesh_receipt: Mapping[str, Any],
    urdf_bytes: bytes,
    *,
    proposal_file_sha256: str,
    mesh_receipt_file_sha256: str,
    urdf_file_sha256: str,
) -> dict[str, Any]:
    """Independently certify the exact ARM-259 simulation-model proposals."""

    proposal_hash, expected_spheres, expected_pairs = _review_sources(
        proposal,
        mesh_receipt,
        urdf_bytes,
        proposal_file_sha256=proposal_file_sha256,
        mesh_receipt_file_sha256=mesh_receipt_file_sha256,
        urdf_file_sha256=urdf_file_sha256,
    )
    proposed_profile = proposal.get("sphere_profile_proposal")
    proposed_policy = proposal.get("pair_policy_proposal")
    if not isinstance(proposed_profile, Mapping) or not isinstance(
        proposed_policy, Mapping
    ):
        raise ProofInputReviewError("ARM-259 proof input inventory changed")
    profile = _certify_profile(proposed_profile, expected_spheres, proposal_hash)
    policy = _accept_policy(proposed_policy, expected_pairs, proposal_hash)
    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm260-native-sweep-proof-input-review-002",
        "status": "ACCEPTED_FOR_NATIVE_BINDING_IMPLEMENTATION",
        "source_proposal_sha256": proposal_hash,
        "source_files_sha256": {
            "arm259_proposal": proposal_file_sha256,
            "governed_urdf": urdf_file_sha256,
            "upstream_mesh_receipt": mesh_receipt_file_sha256,
        },
        "review_findings": {
            "all_seven_source_mesh_bounds_reopened": True,
            "all_seven_sphere_centers_and_upward_rounded_radii_recomputed": True,
            "all_fifty_six_aabb_corners_contained": True,
            "all_six_direct_urdf_adjacency_pairs_rederived": True,
            "no_srdf_never_or_sample_derived_exclusion_present": True,
            "simulation_model_only_scope_preserved": True,
            "zero_hardware_and_physical_authority_preserved": True,
        },
        "certified_sphere_profile": profile,
        "accepted_pair_policy": policy,
        "certified_inputs_emitted": True,
        "native_binding_admitted": False,
        "launch_admitted": False,
        "attempt_consumed": False,
        "isaac_started": False,
        "trajectory_playback": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": "RERUN_ARM258_AND_IMPLEMENT_HASH_PINNED_NATIVE_BINDING",
        "limitations": [
            "certification_covers_pinned_simulation_model_vertex_containment_only",
            "single_spheres_may_create_false_positive_collision_hits",
            "installed_tool_clamp_cable_and_camera_geometry_remain_out_of_scope",
            "review_does_not_start_isaac_or_consume_the_governed_attempt",
        ],
    }
    return {**core, "review_sha256": _sha(core)}


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ProofInputReviewError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--mesh-receipt", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_review(
        _load_object(args.proposal),
        _load_object(args.mesh_receipt),
        args.urdf.read_bytes(),
        proposal_file_sha256=_file_sha(args.proposal),
        mesh_receipt_file_sha256=_file_sha(args.mesh_receipt),
        urdf_file_sha256=_file_sha(args.urdf),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
