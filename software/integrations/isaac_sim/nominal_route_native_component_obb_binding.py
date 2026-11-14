"""Native transform binding for component-OBB continuous self-clearance.

The offline definition builder promotes only the geometric containment facts
from the retained triangle-partition receipt.  It does not promote the old
finite collision replay, pair exclusions, or physical authority.  The runtime
class consumes public articulation link transforms and emits the interval
bounds required by :mod:`nominal_route_component_obb_clearance`.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence
from xml.etree import ElementTree

from nominal_route_component_obb_clearance import OrientedBoxIntervalBound


DEFINITION_SCHEMA = "tactevra.isaac_lm4_native_component_obb_binding.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_native_component_obb_binding_review.v1"
EXPECTED_PARTITION_RECEIPT_SHA256 = (
    "cf887206e9afdadb46a20263db56406eabfe90a78c3f9d1e5ad0e8dc3fbc6469"
)
EXPECTED_PARTITION_FILE_SHA256 = (
    "d132616a1cc1afb2b05ab4dd1b22478087fa3e0d1eb150fa2711d58538b1cdef"
)
EXPECTED_URDF_SHA256 = (
    "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
)
EXPECTED_DOF_NAMES = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
    "link5_to_gripper_link",
)
NATIVE_LINKS = (
    "base_link",
    "link1",
    "link2",
    "link3",
    "link4",
    "link5",
    "gripper_link",
)
PROFILE_LINKS = tuple(f"robot:{name}" for name in NATIVE_LINKS[:-1]) + (
    "robot:gripper",
)
PROFILE_TO_NATIVE_LINK = dict(zip(PROFILE_LINKS, NATIVE_LINKS))


class NativeComponentObbBindingError(ValueError):
    """Raised when the reviewed component binding contract drifts."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NativeComponentObbBindingError(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise NativeComponentObbBindingError(f"{label} is not finite")
    return result


def _vector3(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise NativeComponentObbBindingError(f"{label} must contain three values")
    return tuple(_finite(item, label) for item in value)  # type: ignore[return-value]


def _matrix3(value: Any, label: str) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != 9:
        raise NativeComponentObbBindingError(f"{label} must contain nine values")
    return tuple(_finite(item, label) for item in value)


def _parse_xyz(value: str | None) -> tuple[float, float, float]:
    parts = (value or "0 0 0").split()
    if len(parts) != 3:
        raise NativeComponentObbBindingError("URDF joint origin is invalid")
    try:
        return tuple(float(item) * 1000.0 for item in parts)  # type: ignore[return-value]
    except ValueError as exc:
        raise NativeComponentObbBindingError("URDF joint origin is invalid") from exc


def _joint_chain(urdf_text: str) -> dict[str, dict[str, Any]]:
    try:
        root = ElementTree.fromstring(urdf_text)
    except ElementTree.ParseError as exc:
        raise NativeComponentObbBindingError("governed URDF is invalid") from exc
    result = {}
    for joint in root.findall("joint"):
        parent, child, origin = joint.find("parent"), joint.find("child"), joint.find("origin")
        if parent is None or child is None or not joint.get("name") or not joint.get("type"):
            raise NativeComponentObbBindingError("governed URDF joint is incomplete")
        child_name = child.get("link")
        if not child_name or child_name in result:
            raise NativeComponentObbBindingError("governed URDF joint graph changed")
        result[child_name] = {
            "name": joint.get("name"),
            "type": joint.get("type"),
            "parent": parent.get("link"),
            "origin_mm": _parse_xyz(origin.get("xyz") if origin is not None else None),
        }
    movable = tuple(
        row["name"] for row in result.values() if row["type"] == "revolute"
    )
    if movable != EXPECTED_DOF_NAMES:
        raise NativeComponentObbBindingError("governed URDF movable joints changed")
    return result


def _component_coefficients(
    link_name: str,
    center_mm: Sequence[float],
    half_extents_mm: Sequence[float],
    chain: Mapping[str, Mapping[str, Any]],
) -> dict[str, float]:
    # center norm + box circumradius bounds every component point's reach.
    reach = math.sqrt(sum(item * item for item in center_mm)) + math.sqrt(
        sum(item * item for item in half_extents_mm)
    )
    coefficients: dict[str, float] = {}
    current = link_name
    visited = set()
    while current in chain:
        if current in visited:
            raise NativeComponentObbBindingError("governed URDF contains a cycle")
        visited.add(current)
        joint = chain[current]
        if joint["type"] == "revolute":
            coefficients[str(joint["name"])] = reach
        reach += math.sqrt(sum(item * item for item in joint["origin_mm"]))
        current = str(joint["parent"])
    return {
        name: coefficients[name] for name in EXPECTED_DOF_NAMES if name in coefficients
    }


def build_definition(
    partition: Mapping[str, Any],
    *,
    partition_file_sha256: str,
    urdf_file_sha256: str,
    binding_source_file_sha256: str,
    urdf_text: str,
) -> dict[str, Any]:
    """Build a zero-authority component containment definition."""

    unsigned = dict(partition)
    claimed = unsigned.pop("receipt_sha256", None)
    links = partition.get("links")
    if (
        claimed != EXPECTED_PARTITION_RECEIPT_SHA256
        or claimed != _sha(unsigned)
        or partition_file_sha256 != EXPECTED_PARTITION_FILE_SHA256
        or urdf_file_sha256 != EXPECTED_URDF_SHA256
        or hashlib.sha256(urdf_text.encode("utf-8")).hexdigest() != urdf_file_sha256
        or partition.get("schema") != "tactevra.isaac_sim_triangle_partition_refinement.v1"
        or partition.get("target_metrics", {}).get("maximum_vertex_overflow_mm") != 0.0
        or partition.get("summary", {}).get("candidate_primitive_count") != 29
        or not isinstance(links, list)
        or [row.get("link_name") for row in links] != list(NATIVE_LINKS)
        or any(row.get("component_count", 65) > 64 for row in links)
        or any(
            component.get("maximum_vertex_overflow_mm") != 0.0
            for row in links
            for component in row.get("components", [])
        )
    ):
        raise NativeComponentObbBindingError("component containment source changed")
    for digest, label in (
        (binding_source_file_sha256, "binding source"),
        (partition_file_sha256, "partition file"),
        (urdf_file_sha256, "URDF file"),
    ):
        if not isinstance(digest, str) or len(digest) != 64:
            raise NativeComponentObbBindingError(f"{label} digest is invalid")
    chain = _joint_chain(urdf_text)
    components = []
    for row, profile_name in zip(links, PROFILE_LINKS):
        if len(row.get("components", [])) != row.get("component_count"):
            raise NativeComponentObbBindingError("component count changed")
        for component in row["components"]:
            primitive = component.get("candidate_primitive", {})
            if primitive.get("kind") != "oriented_box":
                raise NativeComponentObbBindingError("component primitive changed")
            center = _vector3(primitive.get("center_mm"), "component center")
            extents = _vector3(primitive.get("half_extents_mm"), "component extents")
            rotation = _matrix3(primitive.get("rotation_row_major"), "component rotation")
            if any(item <= 0.0 for item in extents):
                raise NativeComponentObbBindingError("component extent is invalid")
            components.append(
                {
                    "link_name": profile_name,
                    "native_link_name": row["link_name"],
                    "primitive_name": f"{profile_name}:{component['component_index']}",
                    "local_center_mm": list(center),
                    "local_rotation_row_major": list(rotation),
                    "half_extents_mm": list(extents),
                    "path_lipschitz_mm_per_rad": _component_coefficients(
                        row["link_name"], center, extents, chain
                    ),
                }
            )
    exclusions = [list(pair) for pair in zip(PROFILE_LINKS[:-1], PROFILE_LINKS[1:])]
    core: dict[str, Any] = {
        "schema": DEFINITION_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_COMPONENT_OBB_BINDING_REVIEW",
        "source_partition_receipt_sha256": claimed,
        "source_files_sha256": {
            "partition": partition_file_sha256,
            "governed_urdf": urdf_file_sha256,
            "binding_source": binding_source_file_sha256,
        },
        "dof_names": list(EXPECTED_DOF_NAMES),
        "profile_to_native_link": PROFILE_TO_NATIVE_LINK,
        "component_obbs": components,
        "accepted_exclusion_pairs": exclusions,
        "containment_contract": {
            "all_assigned_triangle_vertices_contained": True,
            "maximum_serialized_vertex_overflow_mm": 0.0,
            "continuous_method": "SAT_GAP_MINUS_EVERY_POINT_PATH_DEVIATION",
            "clearance_margin_mm": 0.5,
            "maximum_subdivision_depth": 12,
            "indeterminate_disposition": "FAIL_CLOSED",
        },
        "finite_replay_promoted": False,
        "srdf_never_exclusions_promoted": False,
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
        "next_required_stage": "INDEPENDENTLY_REVIEW_COMPONENT_OBB_BINDING",
    }
    return {**core, "binding_sha256": _sha(core)}


def _tensor_list(value: Any, label: str) -> Any:
    try:
        if hasattr(value, "numpy"):
            value = value.numpy()
        if hasattr(value, "tolist"):
            value = value.tolist()
    except Exception as exc:  # pragma: no cover - native tensor boundary
        raise NativeComponentObbBindingError(f"{label} cannot be converted") from exc
    return value


def _quaternion_matrix_xyzw(value: Sequence[float]) -> tuple[float, ...]:
    if len(value) != 4:
        raise NativeComponentObbBindingError("native quaternion shape changed")
    x, y, z, w = (_finite(item, "native quaternion") for item in value)
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if abs(norm - 1.0) > 1e-4:
        raise NativeComponentObbBindingError("native quaternion is not normalized")
    return (
        1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
        2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
        2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y),
    )


def _mat_vec(matrix: Sequence[float], vector: Sequence[float]) -> tuple[float, float, float]:
    return tuple(
        sum(matrix[row * 3 + column] * vector[column] for column in range(3))
        for row in range(3)
    )  # type: ignore[return-value]


def _mat_mul(left: Sequence[float], right: Sequence[float]) -> tuple[float, ...]:
    return tuple(
        sum(left[row * 3 + k] * right[k * 3 + column] for k in range(3))
        for row in range(3)
        for column in range(3)
    )


class NativeComponentObbRuntime:
    """Public-articulation transform source for reviewed component OBBs."""

    def __init__(
        self,
        definition: Mapping[str, Any],
        *,
        binding_review: Mapping[str, Any],
        articulation: Any,
    ) -> None:
        binding_hash = definition.get("binding_sha256")
        unsigned_review = dict(binding_review)
        review_hash = unsigned_review.pop("review_sha256", None)
        if (
            definition.get("schema") != DEFINITION_SCHEMA
            or definition.get("status") != "READY_FOR_INDEPENDENT_COMPONENT_OBB_BINDING_REVIEW"
            or binding_hash != _sha({k: v for k, v in definition.items() if k != "binding_sha256"})
            or binding_review.get("schema") != REVIEW_SCHEMA
            or binding_review.get("status") != "ACCEPTED_FOR_COMPONENT_OBB_RUNTIME_INTEGRATION"
            or binding_review.get("source_binding_sha256") != binding_hash
            or binding_review.get("runtime_instantiation_admitted") is not True
            or binding_review.get("launch_admitted") is not False
            or binding_review.get("hardware_access") is not False
            or binding_review.get("physical_authority") is not False
            or review_hash != _sha(unsigned_review)
            or tuple(getattr(articulation, "dof_names", ())) != EXPECTED_DOF_NAMES
            or not set(NATIVE_LINKS).issubset(tuple(getattr(articulation, "link_names", ())))
            or not callable(getattr(articulation, "set_dof_positions", None))
            or not callable(getattr(articulation, "get_link_transforms", None))
        ):
            raise NativeComponentObbBindingError("component OBB runtime is not admitted")
        self._definition = definition
        self._articulation = articulation
        self._link_names = tuple(articulation.link_names)

    @property
    def excluded_pairs(self) -> frozenset[tuple[str, str]]:
        return frozenset(
            tuple(sorted(pair)) for pair in self._definition["accepted_exclusion_pairs"]
        )

    def _world_transforms(self, joints: Sequence[float]) -> dict[str, Sequence[float]]:
        if len(joints) != 6:
            raise NativeComponentObbBindingError("joint target must contain six values")
        self._articulation.set_dof_positions([[_finite(item, "joint target") for item in joints]])
        transforms = _tensor_list(
            self._articulation.get_link_transforms(), "native link transforms"
        )
        if (
            not isinstance(transforms, list)
            or len(transforms) != 1
            or not isinstance(transforms[0], list)
            or len(transforms[0]) != len(self._link_names)
        ):
            raise NativeComponentObbBindingError("native link transform shape changed")
        return dict(zip(self._link_names, transforms[0]))

    def bound_link_obbs(
        self,
        *,
        start_joint_targets_rad: Sequence[float],
        end_joint_targets_rad: Sequence[float],
    ) -> Sequence[OrientedBoxIntervalBound]:
        transforms = self._world_transforms(start_joint_targets_rad)
        delta = [
            abs(float(right) - float(left))
            for left, right in zip(start_joint_targets_rad, end_joint_targets_rad)
        ]
        result = []
        for component in self._definition["component_obbs"]:
            transform = transforms[component["native_link_name"]]
            if not isinstance(transform, (list, tuple)) or len(transform) != 7:
                raise NativeComponentObbBindingError("native link transform row changed")
            position_m = _vector3(transform[:3], "native link position")
            world_rotation = _quaternion_matrix_xyzw(transform[3:])
            rotated_center = _mat_vec(world_rotation, component["local_center_mm"])
            center = tuple(
                position_m[index] * 1000.0 + rotated_center[index] for index in range(3)
            )
            axes = _mat_mul(world_rotation, component["local_rotation_row_major"])
            coefficients = component["path_lipschitz_mm_per_rad"]
            deviation = sum(
                coefficients.get(name, 0.0) * delta[index]
                for index, name in enumerate(EXPECTED_DOF_NAMES)
            )
            result.append(
                OrientedBoxIntervalBound(
                    component["link_name"],
                    component["primitive_name"],
                    center,
                    axes,
                    tuple(component["half_extents_mm"]),
                    deviation,
                )
            )
        return tuple(result)
