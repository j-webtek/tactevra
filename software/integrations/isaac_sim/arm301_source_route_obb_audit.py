"""Audit the pinned SPACE source route with offline URDF kinematics, not Isaac."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import scipy
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/src"))

from nominal_route_component_obb_clearance import check_continuous_self_clearance
from nominal_route_native_component_obb_binding import (
    EXPECTED_DOF_NAMES,
    NATIVE_LINKS,
    NativeComponentObbRuntime,
    _sha,
    build_definition,
)
from rocell.geometry.urdf import JointPosition, UrdfModel

ROUTE_SHA256 = "d22fffa61b4d481e8c90956828c3c2a58634e9408108f00a2521501e331c0449"
EPISODE = "episode-ef340d0ad2740c118d87"


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _signed(core: dict, key: str) -> dict:
    data = json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {**core, key: hashlib.sha256(data).hexdigest()}


class _OfflineArticulation:
    """Implement the narrow link-view protocol using offline URDF FK."""

    dof_names = EXPECTED_DOF_NAMES
    link_names = NATIVE_LINKS

    def __init__(self, urdf: Path) -> None:
        self.model = UrdfModel.from_file(urdf)
        self.positions = None

    def set_dof_positions(self, rows):
        self.positions = rows[0]

    def get_link_transforms(self):
        transforms = self.model.forward_kinematics({
            name: JointPosition.radians(value)
            for name, value in zip(self.dof_names, self.positions)
        })
        result = []
        for name in self.link_names:
            transform = transforms[name]
            translation = transform.translation_mm
            matrix = transform.rotation.matrix
            quaternion = Rotation.from_matrix([matrix[i:i + 3] for i in (0, 3, 6)]).as_quat()
            result.append([translation.x / 1000, translation.y / 1000,
                           translation.z / 1000, *quaternion.tolist()])
        return [result]


def _verify_whole_component_inventory(definition: dict, reduction: dict) -> None:
    """Ensure every offline box is exactly the pinned whole-component box."""
    expected = {}
    for row in reduction["links"]:
        for component in row["components"]:
            box = component["candidate_primitive"]
            if box.get("kind") != "oriented_box" or component["maximum_vertex_overflow_mm"] != 0.0:
                raise ValueError("whole-component box containment changed")
            key = (row["link_name"], component["component_index"])
            if key in expected:
                raise ValueError("duplicate whole-component box")
            expected[key] = (box["center_mm"], box["rotation_row_major"], box["half_extents_mm"])
    actual = {}
    for component in definition["component_obbs"]:
        key = (component["native_link_name"], int(component["primitive_name"].rsplit(":", 1)[1]))
        if key in actual:
            raise ValueError("duplicate candidate box")
        actual[key] = (component["local_center_mm"], component["local_rotation_row_major"],
                       component["half_extents_mm"])
    if len(expected) != 14 or actual != expected:
        raise ValueError("whole-component box inventory differs from reduction")


def _regenerated_rows(route: dict, artifacts: Path) -> tuple[list, dict]:
    from nominal_route_arm298_continuity_qualification import (
        EXPECTED_ADAPTER_FILE_SHA256, EXPECTED_ADAPTER_REVIEW_FILE_SHA256,
        _production_runtime, evaluate_route_continuity,
    )

    definition = artifacts / "arm267-canonical-ik-row-adapter-001/adapter.json"
    review = artifacts / "arm267-canonical-ik-row-adapter-review-001/review.json"
    if (_file_sha(definition) != EXPECTED_ADAPTER_FILE_SHA256
            or _file_sha(review) != EXPECTED_ADAPTER_REVIEW_FILE_SHA256):
        raise ValueError("canonical IK adapter evidence changed")
    solver = _production_runtime(ROOT, json.loads(definition.read_bytes()), json.loads(review.read_bytes()))
    rows = list(route["joint_targets"])

    class RecordingSolver:
        def regenerate_row(self, **kwargs):
            result = solver.regenerate_row(**kwargs)
            rows[result["sequence"]] = dict(result)
            return result

    continuity = evaluate_route_continuity(route, RecordingSolver())
    expected = "7d5b329e0a29a308f5e4fa9e42a3d4f9173560a61b32fd8d09795102d946919c"
    if continuity["canonical_rows_sha256"] != expected:
        raise ValueError("canonical IK rows differ from retained ARM-298 qualification")
    return rows, continuity


def _workcell_boxes(route: dict, layout: dict, urdf: Path):
    """Express board-coordinate obstacles in the URDF world used by offline FK."""
    import numpy as np
    from nominal_route_component_obb_clearance import OrientedBoxIntervalBound

    board_from_base = np.array(route["robot_placement_matrix_row_major"]).reshape(4, 4)
    model = UrdfModel.from_file(urdf)
    base = model.forward_kinematics({name: JointPosition.radians(0.0) for name in EXPECTED_DOF_NAMES})["base_link"]
    world_from_base = np.eye(4)
    world_from_base[:3, :3] = np.array(base.rotation.matrix).reshape(3, 3)
    t = base.translation_mm
    world_from_base[:3, 3] = [t.x, t.y, t.z]
    world_from_board = world_from_base @ np.linalg.inv(board_from_base)

    def box(name, lower, size):
        half = np.array(size) / 2
        center = world_from_board @ np.append(np.array(lower) + half, 1.0)
        return OrientedBoxIntervalBound(name, name, tuple(center[:3]),
                                        tuple(world_from_board[:3, :3].flat), tuple(half), 0.0)

    board = layout["board"]
    keyboard = layout["devices"]["keyboard"]
    return (
        box("board", (0, 0, board["bottom_surface_z"]),
            (board["width"], board["depth"], board["thickness"])),
        box("keyboard_envelope", (*keyboard["nominal_origin_xy"], keyboard["support_plane_z"]),
            keyboard["nominal_size"]),
    )


def _screen_workcell(runtime, rows, obstacles):
    from nominal_route_component_obb_clearance import _separating_axis_gap_mm

    results = {box.link_name: {"segments_screened": 0, "segments_unresolved": 0} for box in obstacles}
    for sequence in range(653, 941):
        moving = runtime.bound_link_obbs(
            start_joint_targets_rad=rows[sequence]["joint_position_target_rad"],
            end_joint_targets_rad=rows[sequence + 1]["joint_position_target_rad"],
        )
        for obstacle in obstacles:
            residual, primitive = min(
                (_separating_axis_gap_mm(part, obstacle) - part.max_point_path_deviation_mm,
                 part.primitive_name) for part in moving
            )
            result = results[obstacle.link_name]
            result["segments_screened"] += 1
            result["segments_unresolved"] += int(residual <= 0.5)
            if residual < result.get("minimum_interval_bound_mm", float("inf")):
                result.update(minimum_interval_bound_mm=residual, limiting_primitive=primitive,
                              limiting_segment=[sequence, sequence + 1])
    return results


def audit(route: Path, *, whole_components: bool = False, ik_artifacts: Path | None = None, screen_workcell: bool = False) -> dict:
    integration = Path(__file__).resolve().parent
    urdf = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    partition = integration / "evidence/roarm_m3_triangle_partition_link2_20261005.json"
    binding = integration / "nominal_route_native_component_obb_binding.py"
    proof = integration / "nominal_route_component_obb_clearance.py"
    if _file_sha(route) != ROUTE_SHA256:
        raise ValueError("route file digest changed")
    data = json.loads(route.read_bytes())
    if data.get("episode_id") != EPISODE:
        raise ValueError("route episode changed")
    rows = data["joint_targets"]
    definition = build_definition(
        json.loads(partition.read_bytes()), partition_file_sha256=_file_sha(partition),
        urdf_file_sha256=_file_sha(urdf), binding_source_file_sha256=_file_sha(binding),
        urdf_text=urdf.read_text(encoding="utf-8"),
    )
    reduction = integration / "evidence/roarm_m3_link_mesh_reduction_20261004.json"
    if whole_components:
        from nominal_route_whole_component_candidate import build_candidate
        definition = build_candidate(ROOT)
        _verify_whole_component_inventory(definition, json.loads(reduction.read_bytes()))
    # This local record enables the offline mathematical audit only; it is not
    # an independent review or permission to construct a live Isaac runtime.
    review = _signed({
        "schema": "tactevra.isaac_lm4_native_component_obb_binding_review.v1",
        "status": "ACCEPTED_FOR_COMPONENT_OBB_RUNTIME_INTEGRATION",
        "source_binding_sha256": definition["binding_sha256"],
        "runtime_instantiation_admitted": True, "launch_admitted": False,
        "hardware_access": False, "physical_authority": False,
    }, "review_sha256")
    runtime = NativeComponentObbRuntime(
        definition, binding_review=review, articulation=_OfflineArticulation(urdf)
    )
    regenerated = {}
    if ik_artifacts is not None:
        if not whole_components:
            raise ValueError("regenerated route audit requires whole-component geometry")
        rows, continuity = _regenerated_rows(data, ik_artifacts)
        regenerated = {
            "route_input": "CANONICAL_IK_653_THROUGH_940_SOURCE_EXIT_941",
            "continuity": continuity,
            "screened_joint_rows_sha256": _sha([row["joint_position_target_rad"] for row in rows[653:942]]),
        }
    if screen_workcell:
        if not regenerated:
            raise ValueError("workcell screen requires regenerated whole-component geometry")
        layout = ROOT / "active-project/RoCell_v0_3/config/workcell_layout.json"
        obstacles = _workcell_boxes(data, json.loads(layout.read_bytes()), urdf)
        regenerated["nominal_workcell_screen"] = {
            "layout_file_sha256": _file_sha(layout),
            "geometry": "BOARD_AND_SOLID_NOMINAL_KEYBOARD_ENVELOPE",
            "obstacles": _screen_workcell(runtime, rows, obstacles),
        }
    outcomes = []
    for sequence in range(653, 941):
        left, right = rows[sequence], rows[sequence + 1]
        if left["sequence"] != sequence or right["sequence"] != sequence + 1:
            raise ValueError("route sequence changed")
        outcomes.append(check_continuous_self_clearance(
            runtime, start_sequence=sequence, end_sequence=sequence + 1,
            start_joint_targets_rad=left["joint_position_target_rad"],
            end_joint_targets_rad=right["joint_position_target_rad"],
            reviewed_excluded_pairs=tuple(runtime.excluded_pairs),
        ))
    return _signed({
        "schema": "tactevra.arm301.offline_source_route_obb_audit.v1",
        "source_files_sha256": {"route": _file_sha(route), "urdf": _file_sha(urdf),
            "partition": _file_sha(partition), "binding": _file_sha(binding),
            "proof": _file_sha(proof), "audit": _file_sha(Path(__file__)),
            **({"whole_component_reduction": _file_sha(reduction),
                "whole_component_builder": _file_sha(integration / "nominal_route_whole_component_candidate.py")}
               if whole_components else {})},
        "component_definition_sha256": definition["binding_sha256"],
        "geometry_candidate": "WHOLE_COMPONENT_BOXES" if whole_components else "TRIANGLE_PARTITION_BOXES",
        "component_count": len(definition["component_obbs"]), **regenerated,
        "episode_id": EPISODE, "first_sequence": 653, "last_sequence": 941,
        "segment_count": len(outcomes),
        "intervals_inspected": sum(row["intervals_inspected"] for row in outcomes),
        "terminal_proof_intervals": sum((row["intervals_inspected"] + 1) // 2 for row in outcomes),
        "subdivided_segments": sum(row["maximum_subdivision_depth"] > 0 for row in outcomes),
        "maximum_subdivision_depth": max(row["maximum_subdivision_depth"] for row in outcomes),
        "minimum_certified_residual_mm": min(row["minimum_clearance_mm"] for row in outcomes),
        "direct_joint_exclusions": [list(pair) for pair in sorted(runtime.excluded_pairs)],
        "clearance_margin_mm": 0.5, "python_version": sys.version.split()[0],
        "scipy_version": scipy.__version__, "isaac_started": False,
        "hardware_access": False, "physical_authority": False,
        "scope": ("REGENERATED_ROUTE_NONADJACENT_CONVEX_HULL_SURROGATE_CLEARANCE" if regenerated else "SOURCE_ROUTE_NONADJACENT_CONVEX_HULL_SURROGATE_CLEARANCE"
                  if whole_components else "SOURCE_ROUTE_NONADJACENT_MESH_SURFACE_CLEARANCE"),
        "modeled_solid_semantics": (
            "CONVEX_HULL_OF_EACH_SOURCE_COMPONENT_OR_WHOLE_LINK_FALLBACK"
            if whole_components else "SURFACE_ONLY"
        ),
        "limitations": ["offline URDF FK", *([] if regenerated else ["not regenerated IK"]), "no environment proof",
                        "no Isaac validation", "local review is not independent",
                        "mesh-to-robot frame alignment not established by this audit",
                        "physical robot, attachments and omitted geometry not bounded",
                        "link1 and link5 source meshes are non-watertight"]
        + ([] if whole_components else ["surface containment does not establish solid non-nesting"]),
    }, "receipt_sha256")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--whole-components", action="store_true", help="audit exploratory whole-component boxes")
    parser.add_argument("--ik-artifacts", type=Path, help="regenerate the governed IK window using retained adapter artifacts")
    parser.add_argument("--screen-workcell", action="store_true", help="screen the nominal board and keyboard envelope")
    args = parser.parse_args()
    result = audit(args.route, whole_components=args.whole_components, ik_artifacts=args.ik_artifacts,
                   screen_workcell=args.screen_workcell)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
