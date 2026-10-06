"""Partition one link2 mesh component into triangle-preserving box groups.

The probe assigns every source triangle to exactly one spatial group by its
centroid.  Each candidate box encloses every vertex used by its assigned
triangles.  It emits diagnostic collision geometry only; it does not install
a profile or grant query authority.
"""

from __future__ import annotations

import argparse
import copy
import io
import json
from pathlib import Path

from collision_differential_probe import UPSTREAM_COMMIT, _blob, canonical_sha256, digest_bytes


EXPECTED_BASE_REDUCTION_SHA256 = (
    "ef8d011314df145afe5db43310457671082b276023191aea47287b3ef87a7178"
)
TARGET_LINK = "link2"
TARGET_COMPONENT_INDEX = 0
PADDING_MM = 2e-6
MAX_PRIMITIVES_PER_BODY = 64


def _round(values, digits: int = 6) -> list[float]:
    return [round(float(value), digits) for value in values]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--mesh-receipt", type=Path, required=True)
    parser.add_argument("--base-reduction", type=Path, required=True)
    parser.add_argument("--band-count", type=int, required=True)
    parser.add_argument(
        "--strategy",
        choices=("equal-width-axis", "recursive-longest-centroid-axis"),
        default="equal-width-axis",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        import numpy as np
        import trimesh

        if not 2 <= args.band_count <= 32:
            raise ValueError("band-count must be between 2 and 32")
        upstream = args.upstream_repo.resolve(strict=True)
        mesh_path = args.mesh_receipt.resolve(strict=True)
        base_path = args.base_reduction.resolve(strict=True)
        mesh_receipt = json.loads(mesh_path.read_text(encoding="utf-8"))
        base = json.loads(base_path.read_text(encoding="utf-8"))
        if base["receipt_sha256"] != EXPECTED_BASE_REDUCTION_SHA256:
            raise ValueError("base reduction receipt identity mismatch")

        inventory = {row["link_name"]: row for row in mesh_receipt["mesh_inventory"]}
        source = inventory[TARGET_LINK]
        payload = _blob(upstream, source["git_path"])
        if digest_bytes(payload) != source["sha256"]:
            raise ValueError("link2 mesh hash mismatch")
        mesh = trimesh.load_mesh(io.BytesIO(payload), file_type="stl", process=True)
        source_components = list(mesh.split(only_watertight=False))
        source_components.sort(key=lambda item: tuple(np.asarray(item.bounds).reshape(-1)))
        component = source_components[TARGET_COMPONENT_INDEX]
        vertices = np.asarray(component.vertices, dtype=float)
        faces = np.asarray(component.faces, dtype=int)
        axis = int(np.argmax(np.ptp(vertices, axis=0)))
        centroids = vertices[faces].mean(axis=1)[:, axis]
        if args.strategy == "equal-width-axis":
            edges = np.linspace(
                float(centroids.min()), float(centroids.max()), args.band_count + 1
            )
            groups = [
                np.flatnonzero(
                    np.searchsorted(edges[1:-1], centroids, side="right") == index
                )
                for index in range(args.band_count)
            ]
            groups = [group for group in groups if len(group)]
        else:
            face_centroids = vertices[faces].mean(axis=1)
            groups = [np.arange(len(faces), dtype=int)]
            while len(groups) < args.band_count:
                candidates = []
                for group_index, group in enumerate(groups):
                    spans = np.ptp(face_centroids[group], axis=0)
                    candidates.append((float(spans.max()), len(group), -group_index, group_index))
                _, count, _, group_index = max(candidates)
                if count < 2:
                    break
                group = groups.pop(group_index)
                split_axis = int(np.argmax(np.ptp(face_centroids[group], axis=0)))
                order = np.lexsort((group, face_centroids[group, split_axis]))
                midpoint = len(group) // 2
                groups.extend((group[order[:midpoint]], group[order[midpoint:]]))

        partition_rows = []
        covered_faces: list[int] = []
        maximum_overflow = 0.0
        for band_index, face_indices in enumerate(groups):
            covered_faces.extend(int(index) for index in face_indices)
            vertex_indices = np.unique(faces[face_indices].reshape(-1))
            band_vertices = vertices[vertex_indices]
            minimum = band_vertices.min(axis=0)
            maximum = band_vertices.max(axis=0)
            center = np.round((minimum + maximum) / 2.0, 6)
            half_extents = np.round((maximum - minimum) / 2.0 + PADDING_MM, 6)
            overflow = max(
                0.0,
                float((np.abs(band_vertices - center) - half_extents).max()),
            )
            if overflow > 1e-9:
                raise RuntimeError(f"serialized band {band_index} does not contain its vertices")
            maximum_overflow = max(maximum_overflow, overflow)
            partition_rows.append({
                "component_index": len(partition_rows),
                "source_component_index": TARGET_COMPONENT_INDEX,
                "partition_band_index": band_index,
                "source_vertex_count": int(len(vertex_indices)),
                "source_triangle_count": int(len(face_indices)),
                "source_watertight": False,
                "source_bounds_mm": [_round(minimum), _round(maximum)],
                "minimum_half_extent_floor_applied": False,
                "source_absolute_volume_mm3": None,
                "candidate_primitive": {
                    "kind": "oriented_box",
                    "center_mm": _round(center),
                    "half_extents_mm": _round(half_extents),
                    "rotation_row_major": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
                },
                "candidate_box_volume_mm3": round(float(np.prod(2.0 * half_extents)), 6),
                "box_to_source_volume_ratio": None,
                "maximum_vertex_overflow_mm": round(overflow, 12),
                "refinement": (
                    f"TRIANGLE_{args.strategy.upper().replace('-', '_')}_AABB"
                ),
            })
        if sorted(covered_faces) != list(range(len(faces))):
            raise RuntimeError("triangle partition is not exact")

        links = copy.deepcopy(base["links"])
        target_row = next(row for row in links if row["link_name"] == TARGET_LINK)
        retained = [
            row for row in target_row["components"]
            if row["component_index"] != TARGET_COMPONENT_INDEX
        ]
        replacement = partition_rows + retained
        for index, row in enumerate(replacement):
            row["component_index"] = index
        target_row["components"] = replacement
        target_row["component_count"] = len(replacement)
        target_row["partition_mode"] = (
            f"TRIANGLE_PARTITION_{args.strategy.upper().replace('-', '_')}_FOR_COMPONENT_0"
        )
        total_primitives = sum(len(row["components"]) for row in links)
        if len(replacement) > MAX_PRIMITIVES_PER_BODY:
            raise RuntimeError("partition exceeds the bounded primitive budget")
        existing_ratios = [
            component_row["box_to_source_volume_ratio"]
            for link in links for component_row in link["components"]
            if component_row["box_to_source_volume_ratio"] is not None
        ]
        blockers = [
            "JOINT_SPACE_REPLAY_REQUIRED",
            "SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED",
            "NON_WATERTIGHT_PARTITION_BANDS",
            "TOOL_CAMERA_SUPPORT_AND_ENVIRONMENT_GEOMETRY_MISSING",
            "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_triangle_partition_refinement.v1",
            "evidence_class": "TRIANGLE_PRESERVING_PARTITION_CANDIDATE_ONLY",
            "source_bindings": {
                "upstream_commit": UPSTREAM_COMMIT,
                "mesh_receipt_file_sha256": digest_bytes(mesh_path.read_bytes()),
                "mesh_receipt_sha256": mesh_receipt["receipt_sha256"],
                "base_reduction_file_sha256": digest_bytes(base_path.read_bytes()),
                "base_reduction_sha256": base["receipt_sha256"],
                "target_mesh_sha256": source["sha256"],
                "trimesh_version": trimesh.__version__,
            },
            "method": {
                "target_link": TARGET_LINK,
                "target_component_index": TARGET_COMPONENT_INDEX,
                "requested_band_count": args.band_count,
                "produced_band_count": len(partition_rows),
                "initial_longest_axis_index": axis,
                "initial_longest_axis_name": "xyz"[axis],
                "assignment": args.strategy.upper().replace("-", "_"),
                "recursive_split_rule": (
                    "SPLIT_GROUP_WITH_LARGEST_CENTROID_SPAN_AT_STABLE_MEDIAN"
                    if args.strategy == "recursive-longest-centroid-axis" else None
                ),
                "containment": "ALL_VERTICES_OF_EVERY_ASSIGNED_TRIANGLE",
                "serialization_containment_padding_mm": PADDING_MM,
                "maximum_primitives_per_body": MAX_PRIMITIVES_PER_BODY,
            },
            "target_metrics": {
                "source_triangle_count": int(len(faces)),
                "assigned_triangle_count": len(covered_faces),
                "unique_assigned_triangle_count": len(set(covered_faces)),
                "maximum_vertex_overflow_mm": round(maximum_overflow, 12),
            },
            "links": links,
            "summary": {
                "link_count": len(links),
                "candidate_primitive_count": total_primitives,
                "partition_primitive_count": len(partition_rows),
                "maximum_vertex_overflow_mm": round(maximum_overflow, 12),
                "maximum_watertight_volume_ratio": round(max(existing_ratios), 6),
                "median_watertight_volume_ratio": round(float(np.median(existing_ratios)), 6),
            },
            "candidate_profile_installable": False,
            "collision_query_admissible": False,
            "clearance_replay_admissible": False,
            "blockers": blockers,
            "hardware_access": False,
            "physical_authority": False,
            "wire_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "triangle_preservation_does_not_prove_collision_equivalence",
                "partition_bands_are_open_surface_groups_without_volume_ratios",
                "finite_replay_does_not_cover_continuous_joint_space",
                "no_pair_exclusions_profile_installation_or_collision_authority",
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
