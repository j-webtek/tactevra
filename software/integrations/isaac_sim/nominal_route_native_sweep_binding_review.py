"""Independently review the ARM-262 native conservative-sweep binding.

ARM-263 reopens the exact ARM-262 artifact, implementation source, certified
inputs, and governed URDF.  It independently rederives the path bounds and
uses non-Isaac test doubles to exercise the native runtime contract.  An
accepted receipt admits construction of the reviewed binding inside a future,
separately admitted worker; it does not admit an Isaac launch or an attempt.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree


REVIEW_SCHEMA = "tactevra.isaac_lm4_native_conservative_sweep_binding_review.v1"
BINDING_SCHEMA = "tactevra.isaac_lm4_native_conservative_sweep_binding.v1"
EXPECTED_BINDING_SHA256 = (
    "3fc667eabeddee46833c3d181bca1d438a9eb874d51a72565a5b083d110495fc"
)
EXPECTED_BINDING_FILE_SHA256 = (
    "e620ae81b082a6a1ce957af4b2419464a6d87f5c5c790cf99bc0f8987448c3da"
)
EXPECTED_BINDING_SOURCE_SHA256 = (
    "a1c49cf0c982df91fe9d07dde7ee9bef3463ecbe4c58ce79d7eec91a66440ebe"
)
EXPECTED_READINESS_FILE_SHA256 = (
    "c60b211da9629e5975bb2e3922f85065e693d584a1fd87d050817e917dc40133"
)
EXPECTED_PROOF_REVIEW_FILE_SHA256 = (
    "e395e84d4e0dc991025db73cf071ebaabc0e4bd73c461140bc7a1c12e0c5d97a"
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
PROFILE_TO_NATIVE_LINK = {
    "robot:base_link": "base_link",
    "robot:link1": "link1",
    "robot:link2": "link2",
    "robot:link3": "link3",
    "robot:link4": "link4",
    "robot:link5": "link5",
    "robot:gripper": "gripper_link",
}


class NativeSweepBindingReviewError(ValueError):
    """Raised when ARM-262 cannot be independently accepted."""


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
        raise NativeSweepBindingReviewError("review input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeSweepBindingReviewError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("launch_admitted") is False
        and document.get("attempt_consumed") is False
        and document.get("isaac_started") is False
        and document.get("trajectory_playback") is False
        and document.get("hardware_access") is False
        and document.get("hardware_writes") == 0
        and document.get("physical_authority") is False
        and document.get("physical_movements") == 0
        and document.get("controller_commands") == []
        and document.get("wire_commands") == []
        and document.get("gate_promotions") == []
    )


def _parse_xyz(value: str | None) -> tuple[float, float, float]:
    parts = (value or "0 0 0").split()
    if len(parts) != 3:
        raise NativeSweepBindingReviewError("URDF joint origin changed")
    try:
        result = tuple(float(item) * 1000.0 for item in parts)
    except ValueError as exc:
        raise NativeSweepBindingReviewError("URDF joint origin changed") from exc
    if not all(math.isfinite(item) for item in result):
        raise NativeSweepBindingReviewError("URDF joint origin changed")
    return result  # type: ignore[return-value]


def _independent_path_coefficients(
    spheres: object, urdf_bytes: bytes
) -> dict[str, dict[str, float]]:
    """Rederive center-path coefficients without the ARM-262 helper."""

    try:
        root = ElementTree.fromstring(urdf_bytes)
    except ElementTree.ParseError as exc:
        raise NativeSweepBindingReviewError("governed URDF is not valid XML") from exc
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
            raise NativeSweepBindingReviewError("governed URDF graph changed")
        by_child[child.get("link", "")] = {
            "name": name,
            "kind": kind,
            "parent": parent.get("link"),
            "origin_mm": _parse_xyz(origin.get("xyz") if origin is not None else None),
        }
    if not isinstance(spheres, list) or len(spheres) != 7:
        raise NativeSweepBindingReviewError("binding sphere inventory changed")
    result: dict[str, dict[str, float]] = {}
    for row in spheres:
        if not isinstance(row, Mapping) or row.get("link_name") not in PROFILE_TO_NATIVE_LINK:
            raise NativeSweepBindingReviewError("binding sphere inventory changed")
        profile_name = row["link_name"]
        center = row.get("local_center_mm")
        if (
            not isinstance(center, list)
            or len(center) != 3
            or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in center)
        ):
            raise NativeSweepBindingReviewError("binding sphere center changed")
        reach = math.sqrt(sum(float(item) ** 2 for item in center))
        coefficients: dict[str, float] = {}
        current = PROFILE_TO_NATIVE_LINK[profile_name]
        visited: set[str] = set()
        while current in by_child:
            if current in visited:
                raise NativeSweepBindingReviewError("governed URDF graph contains a cycle")
            visited.add(current)
            joint = by_child[current]
            if joint["kind"] == "revolute":
                coefficients[joint["name"]] = reach
            reach += math.sqrt(sum(item * item for item in joint["origin_mm"]))
            current = joint["parent"]
        result[profile_name] = {
            name: coefficients[name] for name in EXPECTED_DOF_NAMES if name in coefficients
        }
    if set(result) != set(PROFILE_TO_NATIVE_LINK):
        raise NativeSweepBindingReviewError("binding sphere inventory changed")
    return result


def _review_source(source_bytes: bytes) -> None:
    try:
        tree = ast.parse(source_bytes.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise NativeSweepBindingReviewError("binding source is not reviewable Python") from exc
    imported: set[str] = set()
    classes: dict[str, set[str]] = {}
    attributes: set[str] = set()
    string_constants: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.ClassDef):
            classes[node.name] = {
                child.name for child in node.body if isinstance(child, ast.FunctionDef)
            }
        elif isinstance(node, ast.Attribute):
            attributes.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            string_constants.add(node.value)
    forbidden = {name for name in imported if name.startswith(("isaacsim", "serial"))}
    required_methods = {
        "__init__",
        "_world_centers",
        "bound_link_spheres",
        "sweep_sphere_any",
        "moving_self_collision_any",
    }
    if forbidden:
        raise NativeSweepBindingReviewError("binding source imports a forbidden runtime")
    if not required_methods.issubset(classes.get("NativeIsaacConservativeSweepBinding", set())):
        raise NativeSweepBindingReviewError("native binding method surface changed")
    if not {"get_link_transforms", "set_dof_positions", "overlap_sphere_any", "sweep_sphere_any"}.issubset(attributes | string_constants):
        raise NativeSweepBindingReviewError("native binding call surface changed")
    text = source_bytes.decode("utf-8")
    if "SimulationApp(" in text or "execute_backend(" in text:
        raise NativeSweepBindingReviewError("binding source contains launch authority")


class _Array:
    def __init__(self, value: object) -> None:
        self.value = value

    def numpy(self) -> "_Array":
        return self

    def tolist(self) -> object:
        return self.value


class _Articulation:
    dof_names = EXPECTED_DOF_NAMES
    link_names = tuple(PROFILE_TO_NATIVE_LINK.values())

    def __init__(self) -> None:
        self.positions: list[float] = []

    def get_link_transforms(self) -> _Array:
        offset = self.positions[0] if self.positions else 0.0
        rows = [
            [offset + index / 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
            for index, _name in enumerate(self.link_names)
        ]
        return _Array([rows])

    def set_dof_positions(self, rows: list[list[float]]) -> None:
        self.positions = list(rows[0])


class _Query:
    def __init__(self, *, swept: bool = False, overlaps: tuple[bool, ...] = ()) -> None:
        self.swept = swept
        self.overlaps = list(overlaps)
        self.calls: list[tuple[Any, ...]] = []

    def overlap_sphere_any(self, *args: Any) -> bool:
        self.calls.append(("overlap", *args))
        return self.overlaps.pop(0) if self.overlaps else False

    def sweep_sphere_any(self, *args: Any) -> bool:
        self.calls.append(("sweep", *args))
        return self.swept


def _provisional_review(binding_hash: str) -> dict[str, Any]:
    core = {
        "schema": REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_NATIVE_BINDING_INTEGRATION",
        "source_binding_sha256": binding_hash,
        "runtime_instantiation_admitted": True,
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "binding_review_sha256": _sha(core)}


def _runtime_conformance(module: Any, binding: Mapping[str, Any]) -> None:
    query = _Query(swept=True)
    runtime = module.NativeIsaacConservativeSweepBinding(
        binding,
        binding_review=_provisional_review(binding["binding_sha256"]),
        articulation=_Articulation(),
        scene_query=query,
        environment_only_scene=True,
        robot_collision_query_shapes_enabled=False,
    )
    bounds = runtime.bound_link_spheres(
        start_joint_targets_rad=[0.0] * 6,
        end_joint_targets_rad=[0.01] * 6,
    )
    if (
        len(bounds) != 7
        or bounds[0].link_name != "robot:base_link"
        or bounds[0].max_center_path_deviation_mm != 0.0
        or bounds[-1].max_center_path_deviation_mm <= 0.0
    ):
        raise NativeSweepBindingReviewError("native transform/path binding failed review")
    if runtime.sweep_sphere_any(
        start_center_mm=[100.0, 200.0, 300.0],
        end_center_mm=[100.0, 200.0, 400.0],
        radius_mm=25.0,
        moving_link="robot:link2",
    ) is not True:
        raise NativeSweepBindingReviewError("native environment sweep failed review")
    if query.calls != [
        ("overlap", 0.025, (0.1, 0.2, 0.3)),
        ("sweep", 0.025, (0.1, 0.2, 0.3), (0.0, 0.0, 1.0), 0.1, True),
        ("overlap", 0.025, (0.1, 0.2, 0.4)),
    ]:
        raise NativeSweepBindingReviewError("native query unit conversion failed review")
    far = [
        module.SphereIntervalBound(
            name,
            (10000.0 + index * 1000.0, 0.0, 0.0),
            (10000.0 + index * 1000.0, 0.0, 0.0),
            1.0,
            0.0,
        )
        for index, name in enumerate(PROFILE_TO_NATIVE_LINK)
    ]
    far[2] = module.SphereIntervalBound(
        "robot:link2", (10.0, -10.0, 0.0), (10.0, 10.0, 0.0), 2.0, 0.0
    )
    far[4] = module.SphereIntervalBound(
        "robot:link4", (0.0, 0.0, 0.0), (20.0, 0.0, 0.0), 2.0, 0.0
    )
    exclusions = frozenset(tuple(sorted(pair)) for pair in binding["accepted_exclusion_pairs"])
    if runtime.moving_self_collision_any(bounds=far, excluded_pairs=exclusions) != (
        "robot:link2",
        "robot:link4",
    ):
        raise NativeSweepBindingReviewError("moving self-collision failed review")
    try:
        runtime.moving_self_collision_any(
            bounds=far,
            excluded_pairs=frozenset(set(exclusions) | {("robot:link2", "robot:link4")}),
        )
    except module.NativeSweepBindingError:
        pass
    else:
        raise NativeSweepBindingReviewError("uncertified exclusion was accepted")
    try:
        module.NativeIsaacConservativeSweepBinding(
            binding,
            binding_review=_provisional_review(binding["binding_sha256"]),
            articulation=_Articulation(),
            scene_query=_Query(),
            environment_only_scene=False,
            robot_collision_query_shapes_enabled=True,
        )
    except module.NativeSweepBindingError:
        pass
    else:
        raise NativeSweepBindingReviewError("mixed robot/environment query scene was accepted")


def build_review(
    binding: Mapping[str, Any],
    readiness: Mapping[str, Any],
    proof_review: Mapping[str, Any],
    urdf_bytes: bytes,
    binding_source_bytes: bytes,
    *,
    binding_file_sha256: str,
    readiness_file_sha256: str,
    proof_review_file_sha256: str,
    urdf_file_sha256: str,
    binding_source_file_sha256: str,
    binding_module: Any,
) -> dict[str, Any]:
    """Review and admit only the exact ARM-262 runtime construction boundary."""

    binding_hash = _require_hash(binding, "binding_sha256", "ARM-262 binding")
    if (
        binding.get("schema") != BINDING_SCHEMA
        or binding.get("status") != "READY_FOR_INDEPENDENT_NATIVE_BINDING_REVIEW"
        or binding.get("binding_implemented") is not True
        or binding.get("binding_review_admitted") is not False
        or binding.get("next_required_stage") != "INDEPENDENTLY_REVIEW_NATIVE_BINDING"
        or binding_hash != EXPECTED_BINDING_SHA256
        or binding_file_sha256 != EXPECTED_BINDING_FILE_SHA256
        or binding_source_file_sha256 != EXPECTED_BINDING_SOURCE_SHA256
        or readiness_file_sha256 != EXPECTED_READINESS_FILE_SHA256
        or proof_review_file_sha256 != EXPECTED_PROOF_REVIEW_FILE_SHA256
        or urdf_file_sha256 != EXPECTED_URDF_SHA256
        or hashlib.sha256(urdf_bytes).hexdigest() != EXPECTED_URDF_SHA256
        or hashlib.sha256(binding_source_bytes).hexdigest() != EXPECTED_BINDING_SOURCE_SHA256
        or not _zero_authority(binding)
    ):
        raise NativeSweepBindingReviewError("ARM-262 binding identity or boundary changed")
    source_files = binding.get("source_files_sha256")
    if source_files != {
        "arm261_readiness": readiness_file_sha256,
        "arm260_review": proof_review_file_sha256,
        "governed_urdf": urdf_file_sha256,
        "binding_source": binding_source_file_sha256,
    }:
        raise NativeSweepBindingReviewError("ARM-262 source lineage changed")
    if (
        _require_hash(readiness, "preflight_sha256", "ARM-261 readiness")
        != binding.get("source_readiness_sha256")
        or _require_hash(proof_review, "review_sha256", "ARM-260 proof review")
        != binding.get("source_review_sha256")
    ):
        raise NativeSweepBindingReviewError("ARM-262 canonical lineage changed")
    profile = proof_review.get("certified_sphere_profile")
    policy = proof_review.get("accepted_pair_policy")
    if not isinstance(profile, Mapping) or not isinstance(policy, Mapping):
        raise NativeSweepBindingReviewError("certified proof inputs are absent")
    if (
        _require_hash(profile, "profile_sha256", "certified sphere profile")
        != binding.get("source_profile_sha256")
        or _require_hash(policy, "policy_sha256", "accepted pair policy")
        != binding.get("source_policy_sha256")
        or binding.get("link_spheres") != profile.get("link_spheres")
        or binding.get("accepted_exclusion_pairs") != policy.get("accepted_exclusion_pairs")
        or binding.get("dof_names") != list(EXPECTED_DOF_NAMES)
        or binding.get("profile_to_native_link") != PROFILE_TO_NATIVE_LINK
    ):
        raise NativeSweepBindingReviewError("certified binding inputs changed")
    if binding.get("path_lipschitz_mm_per_rad") != _independent_path_coefficients(
        binding.get("link_spheres"), urdf_bytes
    ):
        raise NativeSweepBindingReviewError("path-deviation coefficients failed review")
    expected_runtime_contract = {
        "articulation_link_transform_source": "articulation.get_link_transforms",
        "environment_queries": [
            "scene_query.overlap_sphere_any",
            "scene_query.sweep_sphere_any",
        ],
        "environment_scene_contains_robot_collision_shapes": False,
        "stage_units_in_meters": 1.0,
        "self_collision_method": "RELATIVE_CENTER_SEGMENT_WITH_SUMMED_PATH_DEVIATION",
        "clearance_margin_mm": 0.5,
        "indeterminate_disposition": "FAIL_CLOSED",
    }
    if binding.get("runtime_contract") != expected_runtime_contract:
        raise NativeSweepBindingReviewError("native runtime contract changed")
    _review_source(binding_source_bytes)
    reproduced = binding_module.build_binding_definition(
        readiness,
        proof_review,
        readiness_file_sha256=readiness_file_sha256,
        review_file_sha256=proof_review_file_sha256,
        urdf_file_sha256=urdf_file_sha256,
        binding_source_file_sha256=binding_source_file_sha256,
        urdf_text=urdf_bytes.decode("utf-8"),
    )
    if reproduced != binding:
        raise NativeSweepBindingReviewError("ARM-262 definition reproduction changed")
    _runtime_conformance(binding_module, binding)
    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm263-native-conservative-sweep-binding-review-001",
        "status": "ACCEPTED_FOR_NATIVE_BINDING_INTEGRATION",
        "source_binding_sha256": binding_hash,
        "source_files_sha256": {
            "arm262_binding": binding_file_sha256,
            "arm262_binding_source": binding_source_file_sha256,
            "arm261_readiness": readiness_file_sha256,
            "arm260_proof_review": proof_review_file_sha256,
            "governed_urdf": urdf_file_sha256,
        },
        "review_findings": {
            "exact_binding_and_source_identity_verified": True,
            "arm260_and_arm261_lineage_reopened": True,
            "definition_reproduced_byte_for_byte": True,
            "seven_sphere_native_link_mapping_verified": True,
            "path_deviation_coefficients_independently_rederived": True,
            "millimetre_to_metre_query_conversion_verified": True,
            "endpoint_overlap_and_continuous_sweep_verified": True,
            "moving_self_collision_and_exact_exclusions_verified": True,
            "environment_only_query_scene_enforced": True,
            "import_safe_zero_authority_boundary_verified": True,
        },
        "runtime_instantiation_admitted": True,
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
        "next_required_stage": "PREPARE_ZERO_AUTHORITY_NATIVE_BINDING_INTEGRATION_PREFLIGHT",
        "limitations": [
            "review_admits_runtime_construction_only_inside_a_future_separately_admitted_worker",
            "review_does_not_admit_or_start_isaac",
            "review_does_not_admit_trajectory_playback_joint_targets_or_key_contact",
            "single_link_spheres_remain_conservative_and_can_false_positive",
            "installed_tool_clamp_cable_and_optional_camera_geometry_remain_excluded",
            "review_does_not_consume_the_governed_attempt_or_grant_physical_authority",
        ],
    }
    return {**core, "binding_review_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeSweepBindingReviewError(f"{path} must contain a JSON object")
    return value


def _load_module(path: Path) -> Any:
    integration = str(path.parent)
    if integration not in sys.path:
        sys.path.insert(0, integration)
    name = "arm262_binding_under_arm263_review"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise NativeSweepBindingReviewError("binding source cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--proof-review", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--binding-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    urdf_bytes = args.urdf.read_bytes()
    source_bytes = args.binding_source.read_bytes()
    result = build_review(
        _load(args.binding),
        _load(args.readiness),
        _load(args.proof_review),
        urdf_bytes,
        source_bytes,
        binding_file_sha256=_file_sha(args.binding),
        readiness_file_sha256=_file_sha(args.readiness),
        proof_review_file_sha256=_file_sha(args.proof_review),
        urdf_file_sha256=hashlib.sha256(urdf_bytes).hexdigest(),
        binding_source_file_sha256=hashlib.sha256(source_bytes).hexdigest(),
        binding_module=_load_module(args.binding_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
