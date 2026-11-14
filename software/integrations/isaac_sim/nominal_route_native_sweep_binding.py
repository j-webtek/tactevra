"""Hash-pinned native Isaac binding for conservative route clearance.

The module is import-safe outside Isaac. It implements the ARM-257 runtime
protocol around objects supplied by an already admitted Isaac worker, but its
CLI only emits a reviewable definition and never imports or starts Isaac.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence
from xml.etree import ElementTree

from nominal_route_conservative_sweep_adapter import SphereIntervalBound


BINDING_SCHEMA = "tactevra.isaac_lm4_native_conservative_sweep_binding.v1"
BINDING_REVIEW_SCHEMA = (
    "tactevra.isaac_lm4_native_conservative_sweep_binding_review.v1"
)
READINESS_SCHEMA = "tactevra.isaac_lm4_native_sweep_binding_preflight.v2"
REVIEW_SCHEMA = "tactevra.isaac_lm4_native_sweep_proof_input_review.v1"
EXPECTED_READINESS_SHA256 = (
    "5f3153301e64d526bd837c7084e01fbbcc644491f03cdffef0f5e2a252c119a8"
)
EXPECTED_REVIEW_SHA256 = (
    "aff177aee0fa1bba98d607eddfb7aae90f9c65b515e91da6fec4714c9eddd4b5"
)
EXPECTED_PROFILE_SHA256 = (
    "6150688561f6069efcf26ba0b843f8cf04542af7cfd357f02c35b799bc7aed3e"
)
EXPECTED_POLICY_SHA256 = (
    "8bce70dd4498ca3da3687a4d43cfddac82422ec80ff68aa330496590ac71efc4"
)
EXPECTED_URDF_SHA256 = (
    "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
)
EXPECTED_READINESS_FILE_SHA256 = (
    "c60b211da9629e5975bb2e3922f85065e693d584a1fd87d050817e917dc40133"
)
EXPECTED_REVIEW_FILE_SHA256 = (
    "e395e84d4e0dc991025db73cf071ebaabc0e4bd73c461140bc7a1c12e0c5d97a"
)
EXPECTED_DOF_NAMES = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
    "link5_to_gripper_link",
)
PROFILE_TO_NATIVE_LINK = {
    "robot:base_link": "base_link",
    "robot:link1": "link1",
    "robot:link2": "link2",
    "robot:link3": "link3",
    "robot:link4": "link4",
    "robot:link5": "link5",
    "robot:gripper": "gripper_link",
}


class NativeSweepBindingError(ValueError):
    """Raised when the pinned binding or supplied native services drift."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(value: Mapping[str, Any], key: str, label: str) -> str:
    claimed = value.get(key)
    unsigned = dict(value)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeSweepBindingError(f"{label} hash mismatch")
    return claimed


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NativeSweepBindingError(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise NativeSweepBindingError(f"{label} is not finite")
    return result


def _vector3(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise NativeSweepBindingError(f"{label} must contain three values")
    return tuple(_finite(item, label) for item in value)  # type: ignore[return-value]


def _parse_xyz(value: str | None) -> tuple[float, float, float]:
    parts = (value or "0 0 0").split()
    if len(parts) != 3:
        raise NativeSweepBindingError("URDF joint origin is invalid")
    try:
        result = tuple(float(item) * 1000.0 for item in parts)
    except ValueError as exc:
        raise NativeSweepBindingError("URDF joint origin is invalid") from exc
    if not all(math.isfinite(item) for item in result):
        raise NativeSweepBindingError("URDF joint origin is invalid")
    return result  # type: ignore[return-value]


def _joint_chain(urdf_text: str) -> dict[str, dict[str, Any]]:
    try:
        root = ElementTree.fromstring(urdf_text)
    except ElementTree.ParseError as exc:
        raise NativeSweepBindingError("governed URDF is not valid XML") from exc
    by_child: dict[str, dict[str, Any]] = {}
    for joint in root.findall("joint"):
        parent = joint.find("parent")
        child = joint.find("child")
        origin = joint.find("origin")
        name = joint.get("name")
        kind = joint.get("type")
        if (
            not name
            or kind not in {"fixed", "revolute"}
            or parent is None
            or child is None
            or not parent.get("link")
            or not child.get("link")
            or child.get("link") in by_child
        ):
            raise NativeSweepBindingError("governed URDF joint graph is invalid")
        by_child[child.get("link", "")] = {
            "name": name,
            "type": kind,
            "parent": parent.get("link"),
            "origin_mm": _parse_xyz(origin.get("xyz") if origin is not None else None),
        }
    if set(EXPECTED_DOF_NAMES) != {
        row["name"] for row in by_child.values() if row["type"] == "revolute"
    }:
        raise NativeSweepBindingError("governed URDF movable joints changed")
    return by_child


def _path_lipschitz_coefficients(
    profile: Mapping[str, Any], urdf_text: str
) -> dict[str, dict[str, float]]:
    """Derive conservative millimetres-per-radian center-path bounds."""

    by_child = _joint_chain(urdf_text)
    rows = profile.get("link_spheres")
    if not isinstance(rows, list) or len(rows) != len(PROFILE_TO_NATIVE_LINK):
        raise NativeSweepBindingError("certified sphere inventory changed")
    result: dict[str, dict[str, float]] = {}
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or row.get("link_name") not in PROFILE_TO_NATIVE_LINK
        ):
            raise NativeSweepBindingError("certified sphere inventory changed")
        profile_name = row["link_name"]
        native_link = PROFILE_TO_NATIVE_LINK[profile_name]
        center = _vector3(row.get("local_center_mm"), f"{profile_name} center")
        reach_bound = math.sqrt(sum(item * item for item in center))
        coefficients: dict[str, float] = {}
        current = native_link
        visited: set[str] = set()
        while current in by_child:
            if current in visited:
                raise NativeSweepBindingError(
                    "governed URDF joint graph contains a cycle"
                )
            visited.add(current)
            joint = by_child[current]
            if joint["type"] == "revolute":
                coefficients[joint["name"]] = reach_bound
            origin = joint["origin_mm"]
            reach_bound += math.sqrt(sum(item * item for item in origin))
            current = joint["parent"]
        result[profile_name] = {
            name: coefficients[name]
            for name in EXPECTED_DOF_NAMES
            if name in coefficients
        }
    if set(result) != set(PROFILE_TO_NATIVE_LINK):
        raise NativeSweepBindingError("certified sphere inventory changed")
    return result


def build_binding_definition(
    readiness: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    readiness_file_sha256: str,
    review_file_sha256: str,
    urdf_file_sha256: str,
    binding_source_file_sha256: str,
    urdf_text: str,
) -> dict[str, Any]:
    """Build an offline, reviewable native-binding definition."""

    readiness_hash = _require_hash(
        readiness, "preflight_sha256", "ARM-261 readiness"
    )
    review_hash = _require_hash(review, "review_sha256", "ARM-260 review")
    profile = review.get("certified_sphere_profile")
    policy = review.get("accepted_pair_policy")
    if not isinstance(profile, Mapping) or not isinstance(policy, Mapping):
        raise NativeSweepBindingError("ARM-260 certified inputs are missing")
    profile_hash = _require_hash(
        profile, "profile_sha256", "certified sphere profile"
    )
    policy_hash = _require_hash(policy, "policy_sha256", "accepted pair policy")
    expected_inputs = readiness.get("certified_proof_inputs")
    if (
        readiness.get("schema") != READINESS_SCHEMA
        or readiness.get("status") != "READY_TO_IMPLEMENT_NATIVE_BINDING"
        or readiness.get("blockers") != []
        or readiness.get("launch_admitted") is not False
        or readiness.get("attempt_consumed") is not False
        or readiness_hash != EXPECTED_READINESS_SHA256
        or review.get("schema") != REVIEW_SCHEMA
        or review.get("status") != "ACCEPTED_FOR_NATIVE_BINDING_IMPLEMENTATION"
        or review.get("native_binding_admitted") is not False
        or review_hash != EXPECTED_REVIEW_SHA256
        or profile_hash != EXPECTED_PROFILE_SHA256
        or policy_hash != EXPECTED_POLICY_SHA256
        or expected_inputs
        != {
            "arm260_review_sha256": review_hash,
            "certified_sphere_profile_sha256": profile_hash,
            "accepted_pair_policy_sha256": policy_hash,
        }
        or urdf_file_sha256 != EXPECTED_URDF_SHA256
        or profile.get("source_urdf_sha256") != urdf_file_sha256
        or policy.get("source_urdf_sha256") != urdf_file_sha256
        or readiness_file_sha256 != EXPECTED_READINESS_FILE_SHA256
        or review_file_sha256 != EXPECTED_REVIEW_FILE_SHA256
    ):
        raise NativeSweepBindingError("native binding source contract changed")
    for digest, label in (
        (readiness_file_sha256, "readiness file"),
        (review_file_sha256, "review file"),
        (binding_source_file_sha256, "binding source file"),
    ):
        if not isinstance(digest, str) or len(digest) != 64:
            raise NativeSweepBindingError(f"{label} digest is invalid")
    exclusions = policy.get("accepted_exclusion_pairs")
    if not isinstance(exclusions, list) or len(exclusions) != 6:
        raise NativeSweepBindingError("accepted pair policy changed")
    core: dict[str, Any] = {
        "schema": BINDING_SCHEMA,
        "binding_id": "arm262-native-conservative-sweep-binding-001",
        "status": "READY_FOR_INDEPENDENT_NATIVE_BINDING_REVIEW",
        "source_readiness_sha256": readiness_hash,
        "source_review_sha256": review_hash,
        "source_profile_sha256": profile_hash,
        "source_policy_sha256": policy_hash,
        "source_files_sha256": {
            "arm261_readiness": readiness_file_sha256,
            "arm260_review": review_file_sha256,
            "governed_urdf": urdf_file_sha256,
            "binding_source": binding_source_file_sha256,
        },
        "dof_names": list(EXPECTED_DOF_NAMES),
        "profile_to_native_link": dict(PROFILE_TO_NATIVE_LINK),
        "link_spheres": profile["link_spheres"],
        "accepted_exclusion_pairs": exclusions,
        "path_lipschitz_mm_per_rad": _path_lipschitz_coefficients(
            profile, urdf_text
        ),
        "runtime_contract": {
            "articulation_link_transform_source": "articulation.get_link_transforms",
            "environment_queries": [
                "scene_query.overlap_sphere_any",
                "scene_query.sweep_sphere_any",
            ],
            "environment_scene_contains_robot_collision_shapes": False,
            "stage_units_in_meters": 1.0,
            "self_collision_method": (
                "RELATIVE_CENTER_SEGMENT_WITH_SUMMED_PATH_DEVIATION"
            ),
            "clearance_margin_mm": 0.5,
            "indeterminate_disposition": "FAIL_CLOSED",
        },
        "binding_implemented": True,
        "binding_review_admitted": False,
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
        "next_required_stage": "INDEPENDENTLY_REVIEW_NATIVE_BINDING",
        "limitations": [
            "definition_build_imports_no_isaac_module_and_starts_no_runtime",
            "single_link_spheres_are_conservative_and_can_false_positive",
            "environment_query_requires_robot_collision_shapes_to_be_absent",
            "installed_tool_clamp_cable_and_optional_camera_geometry_are_excluded",
            "binding_cannot_consume_the_governed_attempt_before_independent_review",
        ],
    }
    return {**core, "binding_sha256": _sha(core)}


def _tensor_list(value: Any, label: str) -> Any:
    try:
        if hasattr(value, "numpy"):
            value = value.numpy()
        if hasattr(value, "tolist"):
            value = value.tolist()
    except Exception as exc:  # pragma: no cover - native tensor boundary
        raise NativeSweepBindingError(f"{label} cannot be converted") from exc
    return value


def _rotate_xyzw(
    quaternion: Sequence[float], vector: Sequence[float]
) -> tuple[float, float, float]:
    if len(quaternion) != 4:
        raise NativeSweepBindingError(
            "native link quaternion must contain four values"
        )
    x, y, z, w = (_finite(item, "native link quaternion") for item in quaternion)
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm <= 0.0 or abs(norm - 1.0) > 1e-4:
        raise NativeSweepBindingError("native link quaternion is not normalized")
    vx, vy, vz = _vector3(vector, "local sphere center")
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


class NativeIsaacConservativeSweepBinding:
    """Concrete ARM-257 runtime over an admitted articulation and query."""

    def __init__(
        self,
        definition: Mapping[str, Any],
        *,
        binding_review: Mapping[str, Any],
        articulation: Any,
        scene_query: Any,
        environment_only_scene: bool,
        robot_collision_query_shapes_enabled: bool,
    ) -> None:
        binding_hash = _require_hash(definition, "binding_sha256", "ARM-262 binding")
        _require_hash(
            binding_review, "binding_review_sha256", "native binding review"
        )
        if (
            definition.get("schema") != BINDING_SCHEMA
            or definition.get("status")
            != "READY_FOR_INDEPENDENT_NATIVE_BINDING_REVIEW"
            or definition.get("binding_implemented") is not True
            or definition.get("binding_review_admitted") is not False
            or definition.get("launch_admitted") is not False
            or binding_review.get("schema") != BINDING_REVIEW_SCHEMA
            or binding_review.get("status")
            != "ACCEPTED_FOR_NATIVE_BINDING_INTEGRATION"
            or binding_review.get("source_binding_sha256") != binding_hash
            or binding_review.get("runtime_instantiation_admitted") is not True
            or binding_review.get("launch_admitted") is not False
            or binding_review.get("attempt_consumed") is not False
            or binding_review.get("hardware_access") is not False
            or binding_review.get("physical_authority") is not False
            or environment_only_scene is not True
            or robot_collision_query_shapes_enabled is not False
            or not callable(getattr(scene_query, "overlap_sphere_any", None))
            or not callable(getattr(scene_query, "sweep_sphere_any", None))
            or not callable(getattr(articulation, "get_link_transforms", None))
            or tuple(getattr(articulation, "dof_names", ())) != EXPECTED_DOF_NAMES
        ):
            raise NativeSweepBindingError("native runtime binding is not admissible")
        link_names = tuple(getattr(articulation, "link_names", ()))
        if not set(PROFILE_TO_NATIVE_LINK.values()).issubset(link_names):
            raise NativeSweepBindingError("native articulation link inventory changed")
        self._definition = definition
        self._articulation = articulation
        self._scene_query = scene_query
        self._link_names = link_names
        self._spheres = {
            row["link_name"]: row for row in definition["link_spheres"]
        }
        self._excluded_pairs = frozenset(
            tuple(sorted(pair)) for pair in definition["accepted_exclusion_pairs"]
        )

    def _world_centers(
        self, joints: Sequence[float]
    ) -> dict[str, tuple[float, float, float]]:
        if len(joints) != len(EXPECTED_DOF_NAMES):
            raise NativeSweepBindingError("joint target must contain six values")
        values = [_finite(item, "joint target") for item in joints]
        self._articulation.set_dof_positions([values])
        getter = getattr(self._articulation, "get_link_transforms", None)
        if not callable(getter):
            raise NativeSweepBindingError(
                "native articulation link-transform protocol is absent"
            )
        transforms = _tensor_list(getter(), "native link transforms")
        if (
            not isinstance(transforms, list)
            or len(transforms) != 1
            or not isinstance(transforms[0], list)
            or len(transforms[0]) != len(self._link_names)
        ):
            raise NativeSweepBindingError("native link transform shape changed")
        by_name = dict(zip(self._link_names, transforms[0]))
        result: dict[str, tuple[float, float, float]] = {}
        for profile_name, native_name in PROFILE_TO_NATIVE_LINK.items():
            transform = by_name[native_name]
            if not isinstance(transform, (list, tuple)) or len(transform) != 7:
                raise NativeSweepBindingError("native link transform row changed")
            position_m = _vector3(transform[:3], f"{native_name} position")
            rotated = _rotate_xyzw(
                transform[3:], self._spheres[profile_name]["local_center_mm"]
            )
            result[profile_name] = tuple(
                position_m[index] * 1000.0 + rotated[index] for index in range(3)
            )  # type: ignore[assignment]
        return result

    def bound_link_spheres(
        self,
        *,
        start_joint_targets_rad: Sequence[float],
        end_joint_targets_rad: Sequence[float],
    ) -> Sequence[SphereIntervalBound]:
        start = self._world_centers(start_joint_targets_rad)
        end = self._world_centers(end_joint_targets_rad)
        delta = [
            abs(float(right) - float(left))
            for left, right in zip(start_joint_targets_rad, end_joint_targets_rad)
        ]
        coefficients = self._definition["path_lipschitz_mm_per_rad"]
        bounds = []
        for profile_name in PROFILE_TO_NATIVE_LINK:
            deviation = sum(
                coefficients[profile_name].get(joint_name, 0.0) * delta[index]
                for index, joint_name in enumerate(EXPECTED_DOF_NAMES)
            )
            bounds.append(
                SphereIntervalBound(
                    link_name=profile_name,
                    start_center_mm=start[profile_name],
                    end_center_mm=end[profile_name],
                    radius_mm=float(self._spheres[profile_name]["radius_mm"]),
                    max_center_path_deviation_mm=deviation,
                )
            )
        return tuple(bounds)

    def sweep_sphere_any(
        self,
        *,
        start_center_mm: Sequence[float],
        end_center_mm: Sequence[float],
        radius_mm: float,
        moving_link: str,
    ) -> bool:
        if moving_link not in PROFILE_TO_NATIVE_LINK:
            raise NativeSweepBindingError("moving link is outside the certified profile")
        start = _vector3(start_center_mm, "sweep start")
        end = _vector3(end_center_mm, "sweep end")
        radius = _finite(radius_mm, "sweep radius")
        if radius <= 0.0:
            raise NativeSweepBindingError("sweep radius must be positive")
        delta = tuple(end[index] - start[index] for index in range(3))
        distance_mm = math.sqrt(sum(item * item for item in delta))
        direction = (
            (1.0, 0.0, 0.0)
            if distance_mm == 0.0
            else tuple(item / distance_mm for item in delta)
        )
        radius_m = radius / 1000.0
        start_m = tuple(item / 1000.0 for item in start)
        end_m = tuple(item / 1000.0 for item in end)
        start_overlap = self._scene_query.overlap_sphere_any(radius_m, start_m)
        if not isinstance(start_overlap, bool):
            raise NativeSweepBindingError("native start overlap did not return bool")
        if start_overlap:
            return True
        if distance_mm == 0.0:
            return False
        swept = self._scene_query.sweep_sphere_any(
            radius_m, start_m, direction, distance_mm / 1000.0, True
        )
        end_overlap = self._scene_query.overlap_sphere_any(radius_m, end_m)
        if not isinstance(swept, bool) or not isinstance(end_overlap, bool):
            raise NativeSweepBindingError("native sphere query did not return bool")
        return swept or end_overlap

    def moving_self_collision_any(
        self,
        *,
        bounds: Sequence[SphereIntervalBound],
        excluded_pairs: frozenset[tuple[str, str]],
    ) -> tuple[str, str] | None:
        if excluded_pairs != self._excluded_pairs:
            raise NativeSweepBindingError(
                "self-collision exclusions differ from the certified policy"
            )
        by_name = {bound.link_name: bound for bound in bounds}
        if set(by_name) != set(PROFILE_TO_NATIVE_LINK) or len(by_name) != len(bounds):
            raise NativeSweepBindingError("self-collision sphere inventory changed")
        names = tuple(PROFILE_TO_NATIVE_LINK)
        for index, left_name in enumerate(names):
            for right_name in names[index + 1 :]:
                pair = tuple(sorted((left_name, right_name)))
                if pair in excluded_pairs:
                    continue
                left, right = by_name[left_name], by_name[right_name]
                relative_start = tuple(
                    left.start_center_mm[axis] - right.start_center_mm[axis]
                    for axis in range(3)
                )
                relative_delta = tuple(
                    (left.end_center_mm[axis] - right.end_center_mm[axis])
                    - relative_start[axis]
                    for axis in range(3)
                )
                denominator = sum(item * item for item in relative_delta)
                t = (
                    0.0
                    if denominator == 0.0
                    else max(
                        0.0,
                        min(
                            1.0,
                            -sum(
                                relative_start[axis] * relative_delta[axis]
                                for axis in range(3)
                            )
                            / denominator,
                        ),
                    )
                )
                minimum = math.sqrt(
                    sum(
                        (relative_start[axis] + t * relative_delta[axis]) ** 2
                        for axis in range(3)
                    )
                )
                threshold = (
                    left.radius_mm
                    + right.radius_mm
                    + left.max_center_path_deviation_mm
                    + right.max_center_path_deviation_mm
                )
                if minimum <= threshold:
                    return pair
        return None


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeSweepBindingError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--proof-review", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--binding-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    urdf_bytes = args.urdf.read_bytes()
    result = build_binding_definition(
        _load(args.readiness),
        _load(args.proof_review),
        readiness_file_sha256=_file_sha(args.readiness),
        review_file_sha256=_file_sha(args.proof_review),
        urdf_file_sha256=hashlib.sha256(urdf_bytes).hexdigest(),
        binding_source_file_sha256=_file_sha(args.binding_source),
        urdf_text=urdf_bytes.decode("utf-8"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
