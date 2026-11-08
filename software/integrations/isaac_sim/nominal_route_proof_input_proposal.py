"""Build review-only proof inputs for the ARM-257 native Isaac binding.

ARM-259 derives conservative model-link spheres from the pinned upstream mesh
bounds and derives self-collision exclusions only from direct parent/child
relationships in the governed URDF.  The outputs remain proposals until a
separate reviewer reopens their source evidence and promotes their statuses.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from decimal import Decimal, ROUND_CEILING, localcontext
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree


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
REVIEW_PENDING = "PROPOSED_FOR_INDEPENDENT_SIMULATION_CONTINUOUS_CLEARANCE_REVIEW"
SOURCE_TO_RUNTIME_LINK = {
    "base_link": "robot:base_link",
    "link1": "robot:link1",
    "link2": "robot:link2",
    "link3": "robot:link3",
    "link4": "robot:link4",
    "link5": "robot:link5",
    "gripper_link": "robot:gripper",
}


class ProofInputProposalError(ValueError):
    """Raised when source geometry or kinematic identity is not exact."""


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
        raise ProofInputProposalError("proposal input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_receipt_hash(receipt: Mapping[str, Any]) -> str:
    claimed = receipt.get("receipt_sha256")
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256", None)
    if claimed != EXPECTED_MESH_RECEIPT_SHA256 or claimed != _sha(unsigned):
        raise ProofInputProposalError("upstream mesh receipt hash changed")
    return claimed


def _finite_decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProofInputProposalError(f"{label} is not numeric")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ProofInputProposalError(f"{label} is not finite")
    return result


def _sphere_from_bounds(bounds: object, label: str) -> tuple[list[float], float]:
    if (
        not isinstance(bounds, list)
        or len(bounds) != 2
        or not all(isinstance(row, list) and len(row) == 3 for row in bounds)
    ):
        raise ProofInputProposalError(f"{label} bounds are invalid")
    minimum = [_finite_decimal(value, f"{label} minimum") for value in bounds[0]]
    maximum = [_finite_decimal(value, f"{label} maximum") for value in bounds[1]]
    if any(low >= high for low, high in zip(minimum, maximum)):
        raise ProofInputProposalError(f"{label} bounds are empty")
    with localcontext() as context:
        context.prec = 40
        center = [(low + high) / Decimal(2) for low, high in zip(minimum, maximum)]
        half = [(high - low) / Decimal(2) for low, high in zip(minimum, maximum)]
        radius = sum(value * value for value in half).sqrt()
        radius = radius.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)
    center_float = [float(value) for value in center]
    radius_float = float(radius)
    if not all(math.isfinite(value) for value in [*center_float, radius_float]):
        raise ProofInputProposalError(f"{label} sphere is not finite")
    return center_float, radius_float


def _runtime_link(source_link: str) -> str:
    try:
        return SOURCE_TO_RUNTIME_LINK[source_link]
    except KeyError as exc:
        raise ProofInputProposalError(
            f"unexpected source mesh link {source_link!r}"
        ) from exc


def _build_sphere_profile(
    mesh_receipt: Mapping[str, Any],
    *,
    mesh_receipt_file_sha256: str,
) -> dict[str, Any]:
    receipt_hash = _require_receipt_hash(mesh_receipt)
    binding = mesh_receipt.get("xacro_binding")
    inventory = mesh_receipt.get("mesh_inventory")
    if (
        mesh_receipt.get("schema") != MESH_RECEIPT_SCHEMA
        or not isinstance(binding, Mapping)
        or binding.get("link_count") != 7
        or binding.get("mesh_origin_xyz") != [0.0, 0.0, 0.0]
        or binding.get("mesh_origin_rpy") != [0.0, 0.0, 0.0]
        or binding.get("mesh_scale") != [0.001, 0.001, 0.001]
        or binding.get("visual_and_collision_references_identical") is not True
        or not isinstance(inventory, list)
        or len(inventory) != 7
    ):
        raise ProofInputProposalError("upstream mesh binding contract changed")

    seen: set[str] = set()
    spheres: list[dict[str, Any]] = []
    for row in inventory:
        if not isinstance(row, Mapping):
            raise ProofInputProposalError("mesh inventory row is invalid")
        source_link = row.get("link_name")
        if not isinstance(source_link, str) or source_link in seen:
            raise ProofInputProposalError("mesh link inventory is not unique")
        seen.add(source_link)
        mesh_sha = row.get("sha256")
        if not isinstance(mesh_sha, str) or len(mesh_sha) != 64:
            raise ProofInputProposalError(f"{source_link} mesh digest is invalid")
        center, radius = _sphere_from_bounds(
            row.get("local_bounds_source_units"), source_link
        )
        spheres.append(
            {
                "link_name": _runtime_link(source_link),
                "source_link_name": source_link,
                "local_center_mm": center,
                "radius_mm": radius,
                "source_bounds_mm": row["local_bounds_source_units"],
                "source_mesh_sha256": mesh_sha,
                "source_processed_vertex_count": row.get("processed_vertex_count"),
                "source_watertight": row.get("watertight"),
                "containment_method": (
                    "AABB_CORNER_ENCLOSING_SPHERE_RADIUS_CEILED_TO_1E_6_MM"
                ),
            }
        )
    if seen != set(SOURCE_TO_RUNTIME_LINK):
        raise ProofInputProposalError("mesh link inventory is incomplete")

    core: dict[str, Any] = {
        "schema": SPHERE_PROFILE_SCHEMA,
        "status": REVIEW_PENDING,
        "profile_id": "roarm-m3-upstream-mesh-aabb-spheres-001",
        "source_urdf_sha256": EXPECTED_URDF_SHA256,
        "source_mesh_receipt_sha256": receipt_hash,
        "source_mesh_receipt_file_sha256": mesh_receipt_file_sha256,
        "geometry_scope": "PINNED_UPSTREAM_SIMULATION_MODEL_ONLY",
        "link_spheres": spheres,
        "containment_claim": (
            "EACH_SPHERE_CONTAINS_THE_RETAINED_LOCAL_AABB_AND_THEREFORE_ALL_"
            "PROCESSED_SOURCE_MESH_VERTICES"
        ),
        "installed_geometry_claimed": False,
        "hardware_access": False,
        "physical_authority": False,
        "limitations": [
            "proposal_requires_independent_source_and_arithmetic_review",
            "single_spheres_are_conservative_and_may_produce_false_positive_hits",
            "non_watertight_meshes_do_not_invalidate_vertex_containment_but_limit_solid_claims",
            "profile_excludes_installed_tool_clamp_cable_and_optional_arm_camera_geometry",
            "simulation_model_containment_does_not_qualify_installed_physical_clearance",
        ],
    }
    return {**core, "profile_sha256": _sha(core)}


def _build_pair_policy(urdf_bytes: bytes) -> dict[str, Any]:
    try:
        root = ElementTree.fromstring(urdf_bytes)
    except ElementTree.ParseError as exc:
        raise ProofInputProposalError("governed URDF XML is invalid") from exc
    if root.tag != "robot" or root.attrib.get("name") != "roarm_m3":
        raise ProofInputProposalError("governed URDF robot identity changed")
    links = {node.attrib.get("name") for node in root.findall("link")}
    if not set(SOURCE_TO_RUNTIME_LINK).issubset(links):
        raise ProofInputProposalError("governed URDF link inventory changed")

    pairs: set[tuple[str, str]] = set()
    for joint in root.findall("joint"):
        parent = joint.find("parent")
        child = joint.find("child")
        if parent is None or child is None:
            raise ProofInputProposalError("governed URDF joint is incomplete")
        parent_name = parent.attrib.get("link")
        child_name = child.attrib.get("link")
        if (
            parent_name in SOURCE_TO_RUNTIME_LINK
            and child_name in SOURCE_TO_RUNTIME_LINK
        ):
            pairs.add(
                tuple(sorted((_runtime_link(parent_name), _runtime_link(child_name))))
            )
    expected_pair_count = len(SOURCE_TO_RUNTIME_LINK) - 1
    if len(pairs) != expected_pair_count:
        raise ProofInputProposalError("direct robot adjacency inventory changed")

    core: dict[str, Any] = {
        "schema": PAIR_POLICY_SCHEMA,
        "status": REVIEW_PENDING,
        "policy_id": "roarm-m3-direct-urdf-adjacency-001",
        "source_urdf_sha256": EXPECTED_URDF_SHA256,
        "accepted_exclusion_pairs": [list(pair) for pair in sorted(pairs)],
        "exclusion_basis": "DIRECT_PARENT_CHILD_RELATIONSHIP_IN_GOVERNED_URDF",
        "default_pair_disposition": "CHECK_MOVING_SELF_COLLISION",
        "finite_sample_evidence_used_for_exclusion": False,
        "installed_geometry_claimed": False,
        "hardware_access": False,
        "physical_authority": False,
        "limitations": [
            "proposal_requires_independent_urdf_adjacency_review",
            "only_directly_connected_required_robot_links_are_proposed_for_exclusion",
            "no_srdf_never_pair_or_finite_sample_exclusion_is_promoted",
            "policy_scope_is_simulation_model_continuous_clearance_only",
        ],
    }
    return {**core, "policy_sha256": _sha(core)}


def build_proposal(
    mesh_receipt: Mapping[str, Any],
    urdf_bytes: bytes,
    *,
    mesh_receipt_file_sha256: str,
    urdf_file_sha256: str,
) -> dict[str, Any]:
    """Build both proof-input proposals without importing or starting Isaac."""

    if urdf_file_sha256 != EXPECTED_URDF_SHA256:
        raise ProofInputProposalError("governed URDF file identity changed")
    if hashlib.sha256(urdf_bytes).hexdigest() != urdf_file_sha256:
        raise ProofInputProposalError("governed URDF bytes do not match file identity")
    if (
        not isinstance(mesh_receipt_file_sha256, str)
        or len(mesh_receipt_file_sha256) != 64
    ):
        raise ProofInputProposalError("mesh receipt file digest is invalid")

    sphere_profile = _build_sphere_profile(
        mesh_receipt,
        mesh_receipt_file_sha256=mesh_receipt_file_sha256,
    )
    pair_policy = _build_pair_policy(urdf_bytes)
    core: dict[str, Any] = {
        "schema": PROPOSAL_SCHEMA,
        "proposal_id": "arm259-native-sweep-proof-input-proposal-001",
        "status": "READY_FOR_INDEPENDENT_PROOF_INPUT_REVIEW",
        "source_files_sha256": {
            "governed_urdf": urdf_file_sha256,
            "upstream_mesh_receipt": mesh_receipt_file_sha256,
        },
        "sphere_profile_proposal": sphere_profile,
        "pair_policy_proposal": pair_policy,
        "review_requirements": [
            "recompute_all_seven_spheres_from_retained_mesh_bounds",
            "verify_each_retained_aabb_corner_is_contained",
            "rederive_all_six_direct_adjacency_pairs_from_the_governed_urdf",
            "verify_no_srdf_never_or_sample_derived_pair_is_present",
            "preserve_simulation_model_only_and_zero_authority_scope",
        ],
        "certified_inputs_emitted": False,
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
        "next_required_stage": "INDEPENDENTLY_REVIEW_ARM259_PROOF_INPUT_PROPOSALS",
    }
    return {**core, "proposal_sha256": _sha(core)}


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ProofInputProposalError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh-receipt", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_proposal(
        _load_object(args.mesh_receipt),
        args.urdf.read_bytes(),
        mesh_receipt_file_sha256=_file_sha(args.mesh_receipt),
        urdf_file_sha256=_file_sha(args.urdf),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
