"""Expand raw-mesh versus box collision evidence across governed joint limits."""

from __future__ import annotations

import argparse
from collections import defaultdict
import io
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from collision_differential_probe import (
    EXPECTED_FCL_VERSION,
    EXPECTED_FCL_WHEEL_SHA256,
    EXPECTED_MESH_RECEIPT_SHA256,
    EXPECTED_REDUCTION_RECEIPT_SHA256,
    JOINT_ORDER,
    POSES,
    UPSTREAM_COMMIT,
    _blob,
    _matrix,
    canonical_sha256,
    digest_bytes,
)


HALTON_BASES = (2, 3, 5, 7, 11, 13)
HALTON_SAMPLE_COUNT = 32
MAX_HALTON_SAMPLE_COUNT = 1024
EXPECTED_URDF_SHA256 = "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
OUTCOMES = (
    "AGREEMENT_COLLISION", "AGREEMENT_FREE",
    "CANDIDATE_FALSE_POSITIVE", "CANDIDATE_FALSE_NEGATIVE",
)


def _halton(index: int, base: int) -> float:
    fraction = 1.0
    result = 0.0
    while index:
        fraction /= base
        result += fraction * (index % base)
        index //= base
    return result


def _pose_corpus(
    urdf_path: Path,
    *,
    halton_start: int = 1,
    halton_count: int = HALTON_SAMPLE_COUNT,
    include_anchors: bool = True,
) -> tuple[list[dict], list[dict]]:
    if halton_start < 1:
        raise ValueError("halton_start must be positive")
    if not 1 <= halton_count <= MAX_HALTON_SAMPLE_COUNT:
        raise ValueError(
            f"halton_count must be between 1 and {MAX_HALTON_SAMPLE_COUNT}"
        )
    root = ET.fromstring(urdf_path.read_bytes())
    limits = []
    for name in JOINT_ORDER:
        joint = root.find(f"./joint[@name='{name}']")
        if joint is None or joint.find("limit") is None:
            raise ValueError(f"governed URDF lacks limits for {name}")
        limit = joint.find("limit")
        limits.append((float(limit.attrib["lower"]), float(limit.attrib["upper"])))
    rows: list[dict] = []
    seen: set[tuple[float, ...]] = set()

    def add(name: str, values, family: str) -> None:
        key = tuple(round(float(value), 12) for value in values)
        if key not in seen:
            seen.add(key)
            rows.append({"pose_name": name, "family": family, "joint_positions_rad": list(key)})

    if include_anchors:
        for name, values in POSES.items():
            add(name, values, "GOVERNED_ANCHOR")
        add("all_lower", [item[0] for item in limits], "LIMIT_ANCHOR")
        add("all_upper", [item[1] for item in limits], "LIMIT_ANCHOR")
        add("all_midpoint", [(item[0] + item[1]) / 2.0 for item in limits], "LIMIT_ANCHOR")
        for index, (lower, upper) in enumerate(limits):
            lower_values = [0.0] * len(limits)
            upper_values = [0.0] * len(limits)
            lower_values[index] = lower
            upper_values[index] = upper
            add(f"joint_{index + 1}_lower", lower_values, "SINGLE_JOINT_LIMIT")
            add(f"joint_{index + 1}_upper", upper_values, "SINGLE_JOINT_LIMIT")
    for sample in range(halton_start, halton_start + halton_count):
        values = [
            lower + _halton(sample, base) * (upper - lower)
            for base, (lower, upper) in zip(HALTON_BASES, limits)
        ]
        add(f"halton_{sample:03d}", values, "HALTON_INTERIOR")
    limit_rows = [
        {"joint_name": name, "lower_rad": lower, "upper_rad": upper}
        for name, (lower, upper) in zip(JOINT_ORDER, limits)
    ]
    return rows, limit_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--mesh-receipt", type=Path, required=True)
    parser.add_argument("--reduction-receipt", type=Path, required=True)
    parser.add_argument(
        "--expected-reduction-sha256",
        default=EXPECTED_REDUCTION_RECEIPT_SHA256,
    )
    parser.add_argument("--halton-start", type=int, default=1)
    parser.add_argument("--halton-count", type=int, default=HALTON_SAMPLE_COUNT)
    parser.add_argument("--halton-only", action="store_true")
    parser.add_argument("--fcl-wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.summary_output, args.status_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcl
        import numpy as np
        import trimesh

        workspace = args.workspace.resolve(strict=True)
        upstream = args.upstream_repo.resolve(strict=True)
        mesh_path = args.mesh_receipt.resolve(strict=True)
        reduction_path = args.reduction_receipt.resolve(strict=True)
        wheel_path = args.fcl_wheel.resolve(strict=True)
        if fcl.__version__ != EXPECTED_FCL_VERSION:
            raise ValueError("python-fcl version mismatch")
        if digest_bytes(wheel_path.read_bytes()) != EXPECTED_FCL_WHEEL_SHA256:
            raise ValueError("python-fcl wheel hash mismatch")
        mesh_receipt = json.loads(mesh_path.read_text(encoding="utf-8"))
        reduction = json.loads(reduction_path.read_text(encoding="utf-8"))
        if mesh_receipt["receipt_sha256"] != EXPECTED_MESH_RECEIPT_SHA256:
            raise ValueError("mesh receipt identity mismatch")
        if reduction["receipt_sha256"] != args.expected_reduction_sha256:
            raise ValueError("reduction receipt identity mismatch")
        urdf_path = workspace / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
        if digest_bytes(urdf_path.read_bytes()) != EXPECTED_URDF_SHA256:
            raise ValueError("governed URDF hash mismatch")
        corpus, limits = _pose_corpus(
            urdf_path,
            halton_start=args.halton_start,
            halton_count=args.halton_count,
            include_anchors=not args.halton_only,
        )

        sys.path.insert(0, str(workspace / "software/src"))
        from rocell.geometry.urdf import JointPosition, UrdfModel

        model = UrdfModel.from_file(urdf_path)
        link_order = [item["link_name"] for item in mesh_receipt["mesh_inventory"]]
        adjacent = {tuple(sorted(pair)) for pair in zip(link_order[:-1], link_order[1:])}
        local_meshes = {}
        for item in mesh_receipt["mesh_inventory"]:
            payload = _blob(upstream, item["git_path"])
            if digest_bytes(payload) != item["sha256"]:
                raise ValueError(f"{item['link_name']} mesh hash mismatch")
            local_meshes[item["link_name"]] = trimesh.load_mesh(
                io.BytesIO(payload), file_type="stl", process=True
            )
        box_rows = {item["link_name"]: item["components"] for item in reduction["links"]}
        totals = defaultdict(int)
        for outcome in OUTCOMES:
            totals[outcome] = 0
        pair_totals = defaultdict(lambda: defaultdict(int))
        pair_minima = defaultdict(lambda: {"raw": float("inf"), "box": float("inf")})
        detailed_poses = []
        compact_poses = []
        for pose in corpus:
            transforms = model.forward_kinematics({
                name: JointPosition.radians(value)
                for name, value in zip(JOINT_ORDER, pose["joint_positions_rad"])
            })
            raw_managers = {}
            box_managers = {}
            for link_name in link_order:
                world = _matrix(transforms[link_name], np)
                raw = local_meshes[link_name].copy()
                raw.apply_transform(world)
                raw_manager = trimesh.collision.CollisionManager()
                raw_manager.add_object(link_name, raw)
                raw_managers[link_name] = raw_manager
                box_manager = trimesh.collision.CollisionManager()
                for index, component in enumerate(box_rows[link_name]):
                    primitive = component["candidate_primitive"]
                    local = np.eye(4)
                    local[:3, :3] = np.asarray(
                        primitive["rotation_row_major"], dtype=float
                    ).reshape(3, 3)
                    local[:3, 3] = primitive["center_mm"]
                    box = trimesh.creation.box(
                        extents=2.0 * np.asarray(primitive["half_extents_mm"]),
                        transform=world @ local,
                    )
                    box_manager.add_object(f"{link_name}:{index}", box)
                box_managers[link_name] = box_manager
            pose_counts = defaultdict(int)
            for outcome in OUTCOMES:
                pose_counts[outcome] = 0
            pairs = []
            for first_index, first in enumerate(link_order):
                for second in link_order[first_index + 1:]:
                    pair_key = f"{first}/{second}"
                    raw_collision = bool(raw_managers[first].in_collision_other(raw_managers[second]))
                    box_collision = bool(box_managers[first].in_collision_other(box_managers[second]))
                    if raw_collision and box_collision:
                        outcome = "AGREEMENT_COLLISION"
                    elif not raw_collision and not box_collision:
                        outcome = "AGREEMENT_FREE"
                    elif box_collision:
                        outcome = "CANDIDATE_FALSE_POSITIVE"
                    else:
                        outcome = "CANDIDATE_FALSE_NEGATIVE"
                    raw_distance = float(raw_managers[first].min_distance_other(raw_managers[second]))
                    box_distance = float(box_managers[first].min_distance_other(box_managers[second]))
                    pose_counts[outcome] += 1
                    totals[outcome] += 1
                    totals["PAIR_CASES"] += 1
                    pair_totals[pair_key][outcome] += 1
                    pair_minima[pair_key]["raw"] = min(pair_minima[pair_key]["raw"], raw_distance)
                    pair_minima[pair_key]["box"] = min(pair_minima[pair_key]["box"], box_distance)
                    pairs.append({
                        "body_pair": [first, second],
                        "kinematically_adjacent": tuple(sorted((first, second))) in adjacent,
                        "raw_mesh_collision": raw_collision,
                        "candidate_box_collision": box_collision,
                        "raw_mesh_minimum_signed_distance_mm": round(raw_distance, 6),
                        "candidate_box_minimum_signed_distance_mm": round(box_distance, 6),
                        "outcome": outcome,
                    })
            counts = dict(sorted(pose_counts.items()))
            detailed_poses.append({**pose, "counts": counts, "pairs": pairs})
            compact_poses.append({**pose, "counts": counts})
        pair_summary = []
        for first_index, first in enumerate(link_order):
            for second in link_order[first_index + 1:]:
                key = f"{first}/{second}"
                pair_summary.append({
                    "body_pair": [first, second],
                    "kinematically_adjacent": tuple(sorted((first, second))) in adjacent,
                    "counts": {
                        outcome: pair_totals[key][outcome] for outcome in OUTCOMES
                    },
                    "minimum_raw_mesh_signed_distance_mm": round(pair_minima[key]["raw"], 6),
                    "minimum_candidate_box_signed_distance_mm": round(pair_minima[key]["box"], 6),
                })
        scope_summary = {
            scope: {outcome: 0 for outcome in OUTCOMES}
            for scope in ("ADJACENT", "NONADJACENT")
        }
        for row in pair_summary:
            scope = "ADJACENT" if row["kinematically_adjacent"] else "NONADJACENT"
            for outcome in OUTCOMES:
                scope_summary[scope][outcome] += row["counts"][outcome]
        source_bindings = {
            "upstream_commit": UPSTREAM_COMMIT,
            "governed_urdf_sha256": EXPECTED_URDF_SHA256,
            "mesh_receipt_sha256": mesh_receipt["receipt_sha256"],
            "reduction_receipt_sha256": reduction["receipt_sha256"],
            "python_fcl_version": fcl.__version__,
            "python_fcl_wheel_sha256": digest_bytes(wheel_path.read_bytes()),
            "trimesh_version": trimesh.__version__,
        }
        method = {
            "collision_backend": "python-fcl via trimesh CollisionManager",
            "joint_limits": limits,
            "pose_families": ["GOVERNED_ANCHOR", "LIMIT_ANCHOR", "SINGLE_JOINT_LIMIT", "HALTON_INTERIOR"],
            "halton_bases": list(HALTON_BASES),
            "halton_sample_count": HALTON_SAMPLE_COUNT,
            "adjacent_pairs_are_measured_not_excluded": True,
        }
        if (
            args.halton_start != 1
            or args.halton_count != HALTON_SAMPLE_COUNT
            or args.halton_only
        ):
            method["halton_start_index"] = args.halton_start
            method["halton_sample_count"] = args.halton_count
            method["anchors_included"] = not args.halton_only
            method["pose_families"] = (
                ["HALTON_INTERIOR"]
                if args.halton_only
                else method["pose_families"]
            )
        detailed: dict[str, object] = {
            "schema": "tactevra.isaac_sim_collision_joint_space_detailed.v1",
            "source_bindings": source_bindings,
            "method": method,
            "poses": detailed_poses,
            "summary": dict(sorted(totals.items())),
        }
        detailed["receipt_sha256"] = canonical_sha256(detailed)
        detailed_bytes = (json.dumps(detailed, indent=2, sort_keys=True) + "\n").encode("utf-8")
        args.output.write_bytes(detailed_bytes)
        blockers = []
        if totals["CANDIDATE_FALSE_POSITIVE"]:
            blockers.append("CANDIDATE_FALSE_POSITIVE_COLLISIONS_OBSERVED")
        if scope_summary["NONADJACENT"]["CANDIDATE_FALSE_POSITIVE"]:
            blockers.append("NONADJACENT_FALSE_POSITIVE_OBSERVED")
        blockers.extend([
            "FINITE_CORPUS_IS_NOT_CONTINUOUS_WORKSPACE_COVERAGE",
            "SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED",
            "NON_WATERTIGHT_RAW_MESHES",
            "TOOL_CAMERA_SUPPORT_AND_ENVIRONMENT_GEOMETRY_MISSING",
            "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
        ])
        summary: dict[str, object] = {
            "schema": "tactevra.isaac_sim_collision_joint_space_summary.v1",
            "evidence_class": "OFFLINE_GOVERNED_LIMIT_COLLISION_DIFFERENTIAL_ONLY",
            "source_bindings": {
                **source_bindings,
                "detailed_receipt_file_sha256": digest_bytes(detailed_bytes),
                "detailed_receipt_sha256": detailed["receipt_sha256"],
            },
            "method": method,
            "pose_count": len(corpus),
            "pose_results": compact_poses,
            "pair_summary": pair_summary,
            "adjacency_scope_summary": scope_summary,
            "summary": dict(sorted(totals.items())),
            "candidate_profile_installable": False,
            "collision_query_admissible": False,
            "pair_exclusions_admissible": False,
            "clearance_replay_admissible": False,
            "blockers": blockers,
            "hardware_access": False,
            "physical_authority": False,
            "wire_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "finite_deterministic_samples_do_not_cover_continuous_joint_space",
                "adjacent_contacts_are_reported_without_policy_exclusion",
                "raw_non_watertight_meshes_are_supported_by_fcl_but_not_repaired",
                "no_tool_camera_support_environment_clearance_or_contact_dynamics",
                "no_installed_profile_controller_hardware_or_physical_qualification",
            ],
        }
        summary["receipt_sha256"] = canonical_sha256(summary)
        args.summary_output.write_bytes((json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        args.status_output.write_bytes((json.dumps({
            "status": "PASS_WITH_BLOCKERS",
            "receipt_sha256": summary["receipt_sha256"],
            "pose_count": len(corpus),
            **dict(sorted(totals.items())),
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
