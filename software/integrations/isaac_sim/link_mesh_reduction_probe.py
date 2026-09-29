"""Derive conservative candidate boxes from pinned official link meshes.

This offline probe converts every connected component of each governed upstream
link mesh into one deterministic link-local axis-aligned box.  The boxes match
the installed collision geometry primitive vocabulary, but this probe does not
install a profile, select self-collision exclusions, run clearance queries, or
grant simulation or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess


UPSTREAM_COMMIT = "40dbd84b553695212fab713e8465f817ba95454d"
MESH_DIRECTORY = "src/roarm_main/roarm_description/meshes/roarm_m3"
EXPECTED_MESH_RECEIPT_SHA256 = (
    "77b7c16e2d7c7a8ee0579b071d6a911516a8ba6d675188971e0c54e466b30954"
)
IDENTITY_ROTATION = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
CONTAINMENT_TOLERANCE_MM = 1e-9
MINIMUM_HALF_EXTENT_MM = 1e-6
MAX_PRIMITIVES_PER_BODY = 64


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    return digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    )


def _git_blob(repo: Path, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", f"{UPSTREAM_COMMIT}:{path}"],
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _round(values, digits: int = 6) -> list[float]:
    return [round(float(value), digits) for value in values]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--mesh-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        import numpy as np
        import trimesh

        upstream_repo = args.upstream_repo.resolve(strict=True)
        mesh_receipt_path = args.mesh_receipt.resolve(strict=True)
        mesh_receipt = json.loads(mesh_receipt_path.read_text(encoding="utf-8"))
        if mesh_receipt["receipt_sha256"] != EXPECTED_MESH_RECEIPT_SHA256:
            raise ValueError("upstream link-mesh receipt identity mismatch")

        link_rows = []
        all_ratios: list[float] = []
        total_components = 0
        total_source_vertices = 0
        maximum_overflow = 0.0
        for inventory in mesh_receipt["mesh_inventory"]:
            link_name = inventory["link_name"]
            git_path = inventory["git_path"]
            mesh_bytes = _git_blob(upstream_repo, git_path)
            if digest_bytes(mesh_bytes) != inventory["sha256"]:
                raise ValueError(f"{link_name} mesh hash mismatch")
            mesh = trimesh.load_mesh(io.BytesIO(mesh_bytes), file_type="stl", process=True)
            split_components = list(mesh.split(only_watertight=False))
            split_components.sort(
                key=lambda item: tuple(np.asarray(item.bounds).reshape(-1).tolist())
            )
            use_whole_link_envelope = len(split_components) > MAX_PRIMITIVES_PER_BODY
            components = [mesh] if use_whole_link_envelope else split_components
            component_rows = []
            link_ratios: list[float] = []
            for component_index, component in enumerate(components):
                vertices = np.asarray(component.vertices, dtype=float)
                minimum = vertices.min(axis=0)
                maximum = vertices.max(axis=0)
                center = (minimum + maximum) / 2.0
                raw_half_extents = (maximum - minimum) / 2.0
                half_extents = np.maximum(raw_half_extents, MINIMUM_HALF_EXTENT_MM)
                normalized = np.abs(vertices - center) - half_extents
                overflow = max(0.0, float(normalized.max()))
                maximum_overflow = max(maximum_overflow, overflow)
                if overflow > CONTAINMENT_TOLERANCE_MM:
                    raise RuntimeError(f"{link_name} component {component_index} escapes its box")
                box_volume = float(np.prod(2.0 * half_extents))
                watertight = bool(component.is_watertight)
                source_volume = abs(float(component.volume)) if watertight else None
                inflation = (
                    box_volume / source_volume
                    if source_volume is not None and source_volume > 0.0
                    else None
                )
                if inflation is not None:
                    link_ratios.append(inflation)
                    all_ratios.append(inflation)
                component_rows.append({
                    "component_index": component_index,
                    "source_vertex_count": int(len(component.vertices)),
                    "source_triangle_count": int(len(component.faces)),
                    "source_watertight": watertight,
                    "source_bounds_mm": [_round(minimum), _round(maximum)],
                    "minimum_half_extent_floor_applied": bool(
                        np.any(raw_half_extents < MINIMUM_HALF_EXTENT_MM)
                    ),
                    "source_absolute_volume_mm3": (
                        round(source_volume, 6) if source_volume is not None else None
                    ),
                    "candidate_primitive": {
                        "kind": "oriented_box",
                        "center_mm": _round(center),
                        "half_extents_mm": _round(half_extents),
                        "rotation_row_major": IDENTITY_ROTATION,
                    },
                    "candidate_box_volume_mm3": round(box_volume, 6),
                    "box_to_source_volume_ratio": (
                        round(inflation, 6) if inflation is not None else None
                    ),
                    "maximum_vertex_overflow_mm": round(overflow, 12),
                })
            total_components += len(component_rows)
            total_source_vertices += sum(row["source_vertex_count"] for row in component_rows)
            link_rows.append({
                "link_name": link_name,
                "mesh_sha256": inventory["sha256"],
                "processed_connected_component_count": len(split_components),
                "partition_mode": (
                    "WHOLE_LINK_ENVELOPE_COMPONENT_LIMIT_FALLBACK"
                    if use_whole_link_envelope
                    else "ONE_BOX_PER_PROCESSED_CONNECTED_COMPONENT"
                ),
                "component_count": len(component_rows),
                "watertight_component_count": sum(
                    bool(row["source_watertight"]) for row in component_rows
                ),
                "maximum_watertight_volume_ratio": (
                    round(max(link_ratios), 6) if link_ratios else None
                ),
                "components": component_rows,
            })

        blockers = [
            "SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED",
            "BOX_INFLATION_FALSE_POSITIVE_RATE_NOT_QUALIFIED",
            "NON_WATERTIGHT_SOURCE_COMPONENTS",
            "LINK5_FRAGMENTATION_REQUIRES_WHOLE_LINK_ENVELOPE",
            "TOOL_GEOMETRY_MISSING",
            "CAMERA_SUPPORT_GEOMETRY_MISSING",
            "ROBOT_PLACEMENT_NOMINAL_UNMEASURED",
            "ISAAC_TOOLCHAIN_LOCK_UNSELECTED",
        ]
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_link_mesh_reduction.v1",
            "evidence_class": "CONSERVATIVE_BOX_CANDIDATES_ONLY",
            "source_bindings": {
                "upstream_repository": "https://github.com/waveshareteam/roarm_ws",
                "upstream_commit": UPSTREAM_COMMIT,
                "mesh_receipt_file_sha256": digest_bytes(mesh_receipt_path.read_bytes()),
                "mesh_receipt_sha256": mesh_receipt["receipt_sha256"],
            },
            "method": {
                "primitive_kind": "oriented_box",
                "orientation": "LINK_LOCAL_IDENTITY",
                "partition": "ONE_BOX_PER_PROCESSED_CONNECTED_COMPONENT",
                "component_sort": "LEXICOGRAPHIC_PROCESSED_BOUNDS",
                "containment_tolerance_mm": CONTAINMENT_TOLERANCE_MM,
                "minimum_half_extent_mm": MINIMUM_HALF_EXTENT_MM,
                "maximum_primitives_per_body": MAX_PRIMITIVES_PER_BODY,
                "component_limit_fallback": "ONE_WHOLE_LINK_ENVELOPE",
                "volume_ratio_scope": "WATERTIGHT_COMPONENTS_ONLY",
            },
            "links": link_rows,
            "summary": {
                "link_count": len(link_rows),
                "candidate_primitive_count": total_components,
                "source_vertex_count": total_source_vertices,
                "watertight_component_count": len(all_ratios),
                "non_watertight_component_count": total_components - len(all_ratios),
                "maximum_vertex_overflow_mm": round(maximum_overflow, 12),
                "maximum_watertight_volume_ratio": round(max(all_ratios), 6),
                "median_watertight_volume_ratio": round(float(np.median(all_ratios)), 6),
            },
            "candidate_profile_installable": False,
            "raw_mesh_collision_admissible": False,
            "reduced_collision_geometry_admissible": False,
            "clearance_replay_admissible": False,
            "blockers": blockers,
            "hardware_access": False,
            "physical_authority": False,
            "wire_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "boxes_are_unqualified_candidates_and_may_create_false_positive_collisions",
                "volume_ratio_is_omitted_for_non_watertight_components",
                "vertex_containment_does_not_measure_clearance_or_collision_differential",
                "no_self_collision_exclusions_tool_camera_support_or_environment_geometry",
                "no_installed_profile_simulation_query_controller_or_physical_qualification",
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
