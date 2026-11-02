"""Partition a governed link mesh into triangle-preserving box groups.

The probe assigns every source triangle to exactly one spatial group. Spatial
centroid partitions retain the original experiment, while whole-link scope can
merge disconnected source components by bounded box cost. Each candidate box
encloses every vertex used by its assigned triangles and may be axis-aligned or
oriented. The default invocation retains the original link2/component-0
experiment. It emits diagnostic collision geometry only; it does not install a
profile or grant query authority.
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


def build_refined_collision_candidate(
    template: dict[str, object],
    refinement: dict[str, object],
    *,
    target_link: str,
    target_mesh_sha256: str,
) -> dict[str, object]:
    """Bind a refinement receipt into a new unapplied collision candidate."""
    claimed_template_sha = template.get("candidate_sha256")
    unsigned_template = copy.deepcopy(template)
    unsigned_template.pop("candidate_sha256", None)
    if claimed_template_sha != canonical_sha256(unsigned_template):
        raise ValueError("collision candidate template hash mismatch")
    if (
        template.get("schema") != "tactevra.simulation_collision_candidate.v1"
        or template.get("installed") is not False
        or template.get("installed_profile_eligible") is not False
        or template.get("physical_authority") is not False
        or template.get("hardware_write_count") != 0
        or template.get("physical_movement_count") != 0
        or template.get("commands") != []
    ):
        raise ValueError("collision candidate template is not an unapplied candidate")
    claimed_refinement_sha = refinement.get("receipt_sha256")
    unsigned_refinement = copy.deepcopy(refinement)
    unsigned_refinement.pop("receipt_sha256", None)
    if claimed_refinement_sha != canonical_sha256(unsigned_refinement):
        raise ValueError("refinement receipt hash mismatch")
    if (
        refinement.get("candidate_profile_installable") is not False
        or refinement.get("physical_authority") is not False
        or refinement.get("hardware_writes") != 0
        or refinement.get("physical_movements") != 0
        or refinement.get("wire_commands") != []
    ):
        raise ValueError("refinement receipt unexpectedly permits installation")
    refinement_links = refinement.get("links")
    if not isinstance(refinement_links, list):
        raise ValueError("refinement receipt lacks link geometry")
    refined_link = next(
        (row for row in refinement_links if row.get("link_name") == target_link),
        None,
    )
    if not isinstance(refined_link, dict):
        raise ValueError("refinement receipt lacks the target link")
    components = refined_link.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("refinement target link has no primitives")
    if len(components) > MAX_PRIMITIVES_PER_BODY:
        raise ValueError("refinement exceeds the bounded primitive budget")

    candidate = copy.deepcopy(template)
    robot_bodies = candidate.get("robot_bodies")
    if not isinstance(robot_bodies, list):
        raise ValueError("collision candidate template lacks robot bodies")
    target_body_id = f"robot:{target_link}"
    target_body = next(
        (body for body in robot_bodies if body.get("body_id") == target_body_id),
        None,
    )
    if not isinstance(target_body, dict):
        raise ValueError("collision candidate template lacks the target body")
    if target_body.get("mesh_sha256") != target_mesh_sha256:
        raise ValueError("collision candidate target mesh identity differs")
    target_body["primitives"] = [
        copy.deepcopy(component["candidate_primitive"])
        for component in components
    ]
    candidate["geometry_refinement"] = {
        "source_candidate_sha256": claimed_template_sha,
        "refinement_receipt_sha256": refinement.get("receipt_sha256"),
        "target_body_id": target_body_id,
        "target_mesh_sha256": target_mesh_sha256,
        "replacement_primitive_count": len(components),
        "applied_to_installed_profile": False,
    }
    candidate.pop("candidate_sha256", None)
    candidate["candidate_sha256"] = canonical_sha256(candidate)
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--mesh-receipt", type=Path, required=True)
    parser.add_argument("--base-reduction", type=Path, required=True)
    parser.add_argument("--target-link", default=TARGET_LINK)
    parser.add_argument("--target-component-index", type=int, default=TARGET_COMPONENT_INDEX)
    parser.add_argument(
        "--source-scope",
        choices=("component", "whole-link"),
        default="component",
    )
    parser.add_argument("--band-count", type=int, required=True)
    parser.add_argument(
        "--primitive-fit",
        choices=("axis-aligned", "oriented"),
        default="axis-aligned",
    )
    parser.add_argument(
        "--strategy",
        choices=(
            "equal-width-axis",
            "recursive-longest-centroid-axis",
            "connected-component-merge-cost",
        ),
        default="equal-width-axis",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    parser.add_argument("--candidate-template", type=Path)
    parser.add_argument("--candidate-output", type=Path)
    args = parser.parse_args()
    if (args.candidate_template is None) != (args.candidate_output is None):
        parser.error("--candidate-template and --candidate-output must be used together")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    if args.candidate_output is not None:
        args.candidate_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        import numpy as np
        import trimesh

        if not 2 <= args.band_count <= MAX_PRIMITIVES_PER_BODY:
            raise ValueError(
                f"band-count must be between 2 and {MAX_PRIMITIVES_PER_BODY}"
            )
        upstream = args.upstream_repo.resolve(strict=True)
        mesh_path = args.mesh_receipt.resolve(strict=True)
        base_path = args.base_reduction.resolve(strict=True)
        mesh_receipt = json.loads(mesh_path.read_text(encoding="utf-8"))
        base = json.loads(base_path.read_text(encoding="utf-8"))
        if base["receipt_sha256"] != EXPECTED_BASE_REDUCTION_SHA256:
            raise ValueError("base reduction receipt identity mismatch")

        inventory = {row["link_name"]: row for row in mesh_receipt["mesh_inventory"]}
        target_link = args.target_link
        if target_link not in inventory:
            raise ValueError(f"unknown target link: {target_link}")
        source = inventory[target_link]
        payload = _blob(upstream, source["git_path"])
        if digest_bytes(payload) != source["sha256"]:
            raise ValueError(f"{target_link} mesh hash mismatch")
        mesh = trimesh.load_mesh(io.BytesIO(payload), file_type="stl", process=True)
        source_components = list(mesh.split(only_watertight=False))
        source_components.sort(key=lambda item: tuple(np.asarray(item.bounds).reshape(-1)))
        if args.source_scope == "whole-link":
            component = mesh
            source_component_reference: int | str = "ALL_PROCESSED_COMPONENTS"
        else:
            if not 0 <= args.target_component_index < len(source_components):
                raise ValueError("target-component-index is outside the processed mesh")
            component = source_components[args.target_component_index]
            source_component_reference = args.target_component_index
        vertices = np.asarray(component.vertices, dtype=float)
        faces = np.asarray(component.faces, dtype=int)
        axis = int(np.argmax(np.ptp(vertices, axis=0)))
        centroids = vertices[faces].mean(axis=1)[:, axis]
        component_group_counts: list[int] | None = None
        merge_cost_total = 0.0
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
        elif args.strategy == "recursive-longest-centroid-axis":
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
        else:
            if args.source_scope != "whole-link":
                raise ValueError(
                    "connected-component-merge-cost requires --source-scope whole-link"
                )
            groups = [
                np.asarray(group, dtype=int)
                for group in trimesh.graph.connected_components(
                    mesh.face_adjacency,
                    nodes=np.arange(len(faces), dtype=int),
                    min_len=1,
                )
            ]
            groups.sort(key=lambda group: int(group.min()))
            if len(groups) != len(source_components):
                raise RuntimeError(
                    "face adjacency and processed component counts differ"
                )
            component_group_counts = [1] * len(groups)

            def group_bounds(group):
                group_vertex_indices = np.unique(faces[group].reshape(-1))
                group_vertices = vertices[group_vertex_indices]
                return group_vertices.min(axis=0), group_vertices.max(axis=0)

            bounds = [group_bounds(group) for group in groups]
            while len(groups) > args.band_count:
                best = None
                for left_index in range(len(groups) - 1):
                    left_minimum, left_maximum = bounds[left_index]
                    left_volume = float(np.prod(left_maximum - left_minimum))
                    for right_index in range(left_index + 1, len(groups)):
                        right_minimum, right_maximum = bounds[right_index]
                        right_volume = float(np.prod(right_maximum - right_minimum))
                        merged_minimum = np.minimum(left_minimum, right_minimum)
                        merged_maximum = np.maximum(left_maximum, right_maximum)
                        merged_volume = float(
                            np.prod(merged_maximum - merged_minimum)
                        )
                        merge_cost = merged_volume - left_volume - right_volume
                        key = (
                            merge_cost,
                            merged_volume,
                            int(groups[left_index].min()),
                            int(groups[right_index].min()),
                            left_index,
                            right_index,
                        )
                        if best is None or key < best[0]:
                            best = (key, merged_minimum, merged_maximum)
                if best is None:
                    raise RuntimeError("no connected-component merge candidate")
                key, merged_minimum, merged_maximum = best
                left_index, right_index = key[-2:]
                merged_group = np.sort(
                    np.concatenate((groups[left_index], groups[right_index]))
                )
                merged_component_count = (
                    component_group_counts[left_index]
                    + component_group_counts[right_index]
                )
                merge_cost_total += float(key[0])
                for remove_index in (right_index, left_index):
                    groups.pop(remove_index)
                    bounds.pop(remove_index)
                    component_group_counts.pop(remove_index)
                groups.append(merged_group)
                bounds.append((merged_minimum, merged_maximum))
                component_group_counts.append(merged_component_count)
                order = np.argsort([int(group.min()) for group in groups])
                groups = [groups[int(index)] for index in order]
                bounds = [bounds[int(index)] for index in order]
                component_group_counts = [
                    component_group_counts[int(index)] for index in order
                ]

        partition_rows = []
        covered_faces: list[int] = []
        maximum_overflow = 0.0
        for band_index, face_indices in enumerate(groups):
            covered_faces.extend(int(index) for index in face_indices)
            vertex_indices = np.unique(faces[face_indices].reshape(-1))
            band_vertices = vertices[vertex_indices]
            minimum = band_vertices.min(axis=0)
            maximum = band_vertices.max(axis=0)
            if args.primitive_fit == "oriented":
                group_mesh = component.submesh(
                    [face_indices], append=True, repair=False
                )
                to_box, extents = trimesh.bounds.oriented_bounds(
                    group_mesh, angle_digits=1, ordered=True
                )
                box_to_link = np.linalg.inv(to_box)
                center = np.round(box_to_link[:3, 3], 9)
                rotation = np.round(box_to_link[:3, :3], 12)
                if np.linalg.det(rotation) < 0.0:
                    rotation[:, 2] *= -1.0
                half_extents = np.round(extents / 2.0 + PADDING_MM, 9)
                local_vertices = (band_vertices - center) @ rotation
            else:
                center = np.round((minimum + maximum) / 2.0, 6)
                rotation = np.eye(3)
                half_extents = np.round(
                    (maximum - minimum) / 2.0 + PADDING_MM, 6
                )
                local_vertices = band_vertices - center
            overflow = max(
                0.0,
                float((np.abs(local_vertices) - half_extents).max()),
            )
            if overflow > 1e-9:
                raise RuntimeError(f"serialized band {band_index} does not contain its vertices")
            maximum_overflow = max(maximum_overflow, overflow)
            partition_rows.append({
                "component_index": len(partition_rows),
                "source_component_index": source_component_reference,
                "partition_band_index": band_index,
                "source_vertex_count": int(len(vertex_indices)),
                "source_triangle_count": int(len(face_indices)),
                **(
                    {
                        "source_connected_component_count": (
                            component_group_counts[band_index]
                        )
                    }
                    if component_group_counts is not None
                    else {}
                ),
                "source_watertight": False,
                "source_bounds_mm": [_round(minimum), _round(maximum)],
                "minimum_half_extent_floor_applied": False,
                "source_absolute_volume_mm3": None,
                "candidate_primitive": {
                    "kind": "oriented_box",
                    "center_mm": _round(
                        center, 9 if args.primitive_fit == "oriented" else 6
                    ),
                    "half_extents_mm": _round(
                        half_extents,
                        9 if args.primitive_fit == "oriented" else 6,
                    ),
                    "rotation_row_major": _round(rotation.reshape(-1), 12),
                },
                "candidate_box_volume_mm3": round(float(np.prod(2.0 * half_extents)), 6),
                "box_to_source_volume_ratio": None,
                "maximum_vertex_overflow_mm": round(overflow, 12),
                "refinement": (
                    f"TRIANGLE_{args.strategy.upper().replace('-', '_')}_AABB"
                    if args.primitive_fit == "axis-aligned"
                    else (
                        "TRIANGLE_"
                        f"{args.strategy.upper().replace('-', '_')}_"
                        "TRIMESH_ORIENTED_BOUNDS"
                    )
                ),
            })
        if sorted(covered_faces) != list(range(len(faces))):
            raise RuntimeError("triangle partition is not exact")

        links = copy.deepcopy(base["links"])
        target_row = next(row for row in links if row["link_name"] == target_link)
        retained = (
            []
            if args.source_scope == "whole-link"
            else [
                row for row in target_row["components"]
                if row["component_index"] != args.target_component_index
            ]
        )
        replacement = partition_rows + retained
        for index, row in enumerate(replacement):
            row["component_index"] = index
        target_row["components"] = replacement
        target_row["component_count"] = len(replacement)
        partition_label = args.strategy.upper().replace("-", "_")
        target_row["partition_mode"] = (
            f"TRIANGLE_PARTITION_{partition_label}_FOR_WHOLE_LINK"
            if args.source_scope == "whole-link"
            else f"TRIANGLE_PARTITION_{partition_label}_FOR_COMPONENT_{args.target_component_index}"
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
        method: dict[str, object] = {
            "target_link": target_link,
            "target_component_index": args.target_component_index,
            "requested_band_count": args.band_count,
            "produced_band_count": len(partition_rows),
            "initial_longest_axis_index": axis,
            "initial_longest_axis_name": "xyz"[axis],
            "assignment": partition_label,
            "recursive_split_rule": (
                "SPLIT_GROUP_WITH_LARGEST_CENTROID_SPAN_AT_STABLE_MEDIAN"
                if args.strategy == "recursive-longest-centroid-axis" else None
            ),
            **(
                {
                    "component_merge_rule": (
                        "MINIMUM_AABB_VOLUME_INCREASE_WITH_STABLE_FACE_INDEX_TIES"
                    ),
                    "component_merge_cost_total_mm3": round(
                        merge_cost_total, 6
                    ),
                }
                if args.strategy == "connected-component-merge-cost"
                else {}
            ),
            "containment": "ALL_VERTICES_OF_EVERY_ASSIGNED_TRIANGLE",
            "serialization_containment_padding_mm": PADDING_MM,
            "maximum_primitives_per_body": MAX_PRIMITIVES_PER_BODY,
        }
        if args.primitive_fit != "axis-aligned":
            method.update({
                "primitive_fit": "TRIMESH_ORIENTED_BOUNDS",
                "oriented_bounds_angle_digits": 1,
                "serialized_center_digits": 9,
                "serialized_rotation_digits": 12,
            })
        if args.source_scope == "whole-link":
            method.update({
                "source_scope": "WHOLE_LINK",
                "processed_connected_component_count": len(source_components),
                "base_replacement_component_index": args.target_component_index,
            })
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
            "method": method,
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
        candidate = None
        if args.candidate_template is not None:
            candidate = build_refined_collision_candidate(
                json.loads(
                    args.candidate_template.resolve(strict=True).read_text(
                        encoding="utf-8"
                    )
                ),
                receipt,
                target_link=target_link,
                target_mesh_sha256=source["sha256"],
            )
            args.candidate_output.write_bytes(
                (json.dumps(candidate, indent=2, sort_keys=True) + "\n").encode("utf-8")
            )
        args.output.write_bytes((json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        args.status_output.write_bytes((json.dumps({
            "status": "PASS_WITH_BLOCKERS",
            "receipt_sha256": receipt["receipt_sha256"],
            "candidate_sha256": (
                candidate["candidate_sha256"] if candidate is not None else None
            ),
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
