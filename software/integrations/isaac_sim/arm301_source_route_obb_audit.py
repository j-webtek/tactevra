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
    _component_coefficients,
    _joint_chain,
    _sha,
    build_definition,
)
from rocell.geometry.urdf import JointPosition, UrdfModel

ROUTE_SHA256 = "d22fffa61b4d481e8c90956828c3c2a58634e9408108f00a2521501e331c0449"
EPISODE = "episode-ef340d0ad2740c118d87"
REDUCTION_FILE_SHA256 = "d9d49bbb97a207a56db2a15cb55b12dc63f6ce89e35998a139ccd112f2061714"
REDUCTION_RECEIPT_SHA256 = "ef8d011314df145afe5db43310457671082b276023191aea47287b3ef87a7178"


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


def audit(route: Path, *, whole_components: bool = False) -> dict:
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
        if _file_sha(reduction) != REDUCTION_FILE_SHA256:
            raise ValueError("whole-component reduction file changed")
        candidate = json.loads(reduction.read_bytes())
        unsigned = dict(candidate)
        claimed = unsigned.pop("receipt_sha256", None)
        if claimed != REDUCTION_RECEIPT_SHA256 or claimed != _sha(unsigned):
            raise ValueError("whole-component reduction receipt changed")
        parts = next(row for row in candidate["links"] if row["link_name"] == "link2")["components"]
        if len(parts) != 2 or any(part["maximum_vertex_overflow_mm"] != 0.0 for part in parts):
            raise ValueError("whole-component link2 containment changed")
        chain = _joint_chain(urdf.read_text(encoding="utf-8"))
        replacement = []
        for part in parts:
            box = part["candidate_primitive"]
            center, extents = box["center_mm"], box["half_extents_mm"]
            replacement.append({
                "link_name": "robot:link2", "native_link_name": "link2",
                "primitive_name": f"robot:link2:{part['component_index']}",
                "local_center_mm": center,
                "local_rotation_row_major": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "half_extents_mm": extents,
                "path_lipschitz_mm_per_rad": _component_coefficients("link2", center, extents, chain),
            })
        definition["component_obbs"] = [
            part for part in definition["component_obbs"] if part["native_link_name"] != "link2"
        ] + replacement
        definition["offline_whole_component_candidate"] = True
        definition.pop("binding_sha256")
        definition["binding_sha256"] = _sha(definition)
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
            **({"whole_component_reduction": _file_sha(reduction)} if whole_components else {})},
        "component_definition_sha256": definition["binding_sha256"],
        "geometry_candidate": "WHOLE_COMPONENT_BOXES" if whole_components else "TRIANGLE_PARTITION_BOXES",
        "component_count": len(definition["component_obbs"]),
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
        "scope": "SOURCE_ROUTE_MESH_SURFACE_SELF_CLEARANCE_ONLY",
        "limitations": ["offline URDF FK", "not regenerated IK", "no environment proof",
                        "no Isaac validation", "local review is not independent",
                        "surface containment does not establish solid non-nesting",
                        "link1 and link5 source meshes are non-watertight"],
    }, "receipt_sha256")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--whole-components", action="store_true", help="audit exploratory whole-component boxes")
    args = parser.parse_args()
    result = audit(args.route, whole_components=args.whole_components)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
