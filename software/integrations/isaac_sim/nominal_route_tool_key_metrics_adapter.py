"""Provide ARM-255 ``measure_tool_key`` without commanding an articulation.

ARM-268 evaluates the requested regenerated row through the same pinned forward
kinematics used by ARM-267 and reads only the target key's native world pose.
The canonical tool-tip point is the surface point used by IK, so its world Z
minus the observed key top is the tool/key clearance.  Key displacement is the
settled key-center Z minus the observed key-center Z.  The definition CLI is
import-safe and does not import or start Isaac.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


ADAPTER_SCHEMA = "tactevra.isaac_lm4_tool_key_metrics_adapter.v1"
ADAPTER_REVIEW_SCHEMA = "tactevra.isaac_lm4_tool_key_metrics_adapter_review.v1"
READINESS_SCHEMA = "tactevra.isaac_lm4_runtime_composition_readiness.v1"
BACKEND_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_backend.v1"
ROUTE_SCHEMA = "tactevra.isaac_lm4_state_policy_native_mechanics_replay_plan.v2"
IK_ADAPTER_SCHEMA = "tactevra.isaac_lm4_canonical_ik_row_adapter.v1"
IK_REVIEW_SCHEMA = "tactevra.isaac_lm4_canonical_ik_row_adapter_review.v1"

EXPECTED_READINESS_SHA256 = (
    "7259e53c0e5522a090a0cdce9c36034fc793bcd093cdfdcce63bee9b99f14bab"
)
EXPECTED_BACKEND_SHA256 = (
    "132f1e028503a3a83af11f2a713f839e00e1fef49aa9cb3fbb0156f858245cde"
)
EXPECTED_ROUTE_SHA256 = (
    "1076f9747429f77f2581fb3a13e7278385d583c9de6c439c76ff38b26b04b16b"
)
EXPECTED_IK_ADAPTER_SHA256 = (
    "0c6b35d2392604687bc52bf723b9422967cc9631c5e33557a56cf7f2c5e4829a"
)
EXPECTED_IK_REVIEW_SHA256 = (
    "45ab4fde0d228893b0adc3e2c25ccb7ac15939742f24712c0b31e358ca41592a"
)
EXPECTED_READINESS_FILE_SHA256 = (
    "572f97eb6c4b52f77b823da767ec270fa9e4c78112e9de69c284133bb91f8b75"
)
EXPECTED_BACKEND_FILE_SHA256 = (
    "968140c9b075cc4f6a8d5599edc765cd1b6cde734e32e6632513bd2c94fb6228"
)
EXPECTED_ROUTE_FILE_SHA256 = (
    "d22fffa61b4d481e8c90956828c3c2a58634e9408108f00a2521501e331c0449"
)
EXPECTED_IK_ADAPTER_FILE_SHA256 = (
    "b3e799c4964bec898772730502f3c81cf22f9e0ded7447f76d21b6a284786f1a"
)
EXPECTED_IK_REVIEW_FILE_SHA256 = (
    "cb61e4005777e0f75556fb238b18608be029375da2b4b11a1be75b0da74fe42f"
)
EXPECTED_IK_SOURCE_SHA256 = (
    "4feb5adb8c33d7b3017f29c17130dc934269ae159bed88b06d8aa63d8474569a"
)
EXPECTED_URDF_SHA256 = (
    "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
)
EXPECTED_MECHANICS_SOURCE_SHA256 = (
    "ba12db530d8ffb0a9b22068238a604a935f6adaff8ba6f3fa7364581ec18d9a3"
)

FIRST_SEQUENCE = 654
LAST_SEQUENCE = 940
KEY_HALF_HEIGHT_MM = 3.0
STAGE_UNITS_IN_METERS = 1.0
JOINT_ORDER = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
    "link5_to_gripper_link",
)


class ToolKeyMetricsAdapterError(ValueError):
    """Raised when lineage, geometry, or native observations drift."""


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
        raise ToolKeyMetricsAdapterError("input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise ToolKeyMetricsAdapterError(f"{label} hash changed")
    return claimed


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolKeyMetricsAdapterError(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ToolKeyMetricsAdapterError(f"{label} is not finite")
    return result


def _joints(value: Any, label: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != len(JOINT_ORDER):
        raise ToolKeyMetricsAdapterError(f"{label} must contain six joints")
    return [_finite(item, label) for item in value]


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("launch_admitted") is False
        and document.get("attempt_consumed") is False
        and document.get("hardware_access") is False
        and document.get("hardware_writes") == 0
        and document.get("physical_authority") is False
        and document.get("physical_movements") == 0
        and document.get("controller_commands") == []
        and document.get("wire_commands") == []
        and document.get("gate_promotions") == []
    )


def build_adapter_definition(
    readiness: Mapping[str, Any],
    backend: Mapping[str, Any],
    route: Mapping[str, Any],
    ik_adapter: Mapping[str, Any],
    ik_review: Mapping[str, Any],
    *,
    readiness_file_sha256: str,
    backend_file_sha256: str,
    route_file_sha256: str,
    ik_adapter_file_sha256: str,
    ik_review_file_sha256: str,
    ik_source_file_sha256: str,
    urdf_file_sha256: str,
    mechanics_source_file_sha256: str,
    adapter_source_file_sha256: str,
) -> dict[str, Any]:
    """Build a review input without constructing a solver or native key view."""

    readiness_hash = _require_hash(readiness, "readiness_sha256", "ARM-266 readiness")
    backend_hash = _require_hash(backend, "backend_sha256", "ARM-255 backend")
    route_hash = _require_hash(route, "plan_sha256", "ARM-231 route")
    ik_adapter_hash = _require_hash(ik_adapter, "adapter_sha256", "ARM-267 adapter")
    ik_review_hash = _require_hash(ik_review, "adapter_review_sha256", "ARM-267 review")
    rows = route.get("joint_targets")
    digests = (
        adapter_source_file_sha256,
        ik_source_file_sha256,
        urdf_file_sha256,
        mechanics_source_file_sha256,
    )
    if (
        readiness.get("schema") != READINESS_SCHEMA
        or readiness.get("status")
        != "READY_TO_IMPLEMENT_REMAINING_ZERO_AUTHORITY_RUNTIME_ADAPTERS"
        or readiness_hash != EXPECTED_READINESS_SHA256
        or readiness.get("source_backend_sha256") != backend_hash
        or readiness.get("reviewed_methods") != ["check_continuous_clearance"]
        or readiness.get("remaining_methods")
        != ["regenerate_row", "measure_tool_key", "root_drift"]
        or backend.get("schema") != BACKEND_SCHEMA
        or backend_hash != EXPECTED_BACKEND_SHA256
        or backend.get("source_route_plan_sha256") != route_hash
        or backend.get("runtime_protocol", {}).get("tool_key_metrics")
        != "ONE_DETERMINATE_RESULT_PER_REGENERATED_ROW"
        or backend.get("acceptance", {}).get("minimum_noncontact_tool_key_clearance_mm")
        != 0.5
        or route.get("schema") != ROUTE_SCHEMA
        or route_hash != EXPECTED_ROUTE_SHA256
        or route.get("joint_order") != list(JOINT_ORDER)
        or not isinstance(rows, list)
        or len(rows) != 1416
        or any(row.get("sequence") != index for index, row in enumerate(rows))
        or any(
            row.get("phase") not in {"TRANSIT", "HOVER"}
            for row in rows[FIRST_SEQUENCE : LAST_SEQUENCE + 1]
        )
        or ik_adapter.get("schema") != IK_ADAPTER_SCHEMA
        or ik_adapter_hash != EXPECTED_IK_ADAPTER_SHA256
        or ik_adapter.get("backend_method") != "regenerate_row"
        or ik_review.get("schema") != IK_REVIEW_SCHEMA
        or ik_review_hash != EXPECTED_IK_REVIEW_SHA256
        or ik_review.get("source_adapter_sha256") != ik_adapter_hash
        or ik_review.get("status") != "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
        or ik_review.get("runtime_integration_admitted") is not True
        or ik_review.get("next_required_stage")
        != "IMPLEMENT_AND_REVIEW_TOOL_KEY_METRICS_ADAPTER"
        or readiness_file_sha256 != EXPECTED_READINESS_FILE_SHA256
        or backend_file_sha256 != EXPECTED_BACKEND_FILE_SHA256
        or route_file_sha256 != EXPECTED_ROUTE_FILE_SHA256
        or ik_adapter_file_sha256 != EXPECTED_IK_ADAPTER_FILE_SHA256
        or ik_review_file_sha256 != EXPECTED_IK_REVIEW_FILE_SHA256
        or ik_source_file_sha256 != EXPECTED_IK_SOURCE_SHA256
        or urdf_file_sha256 != EXPECTED_URDF_SHA256
        or mechanics_source_file_sha256 != EXPECTED_MECHANICS_SOURCE_SHA256
        or any(not isinstance(item, str) or len(item) != 64 for item in digests)
        or not _zero_authority(readiness)
        or not _zero_authority(ik_adapter)
        or not _zero_authority(ik_review)
    ):
        raise ToolKeyMetricsAdapterError(
            "tool/key metrics adapter lineage or boundary changed"
        )
    for index in range(FIRST_SEQUENCE, LAST_SEQUENCE + 1):
        _joints(rows[index].get("joint_position_target_rad"), f"route row {index}")

    core: dict[str, Any] = {
        "schema": ADAPTER_SCHEMA,
        "adapter_id": "arm268-zero-authority-tool-key-metrics-adapter-001",
        "status": "READY_FOR_INDEPENDENT_TOOL_KEY_METRICS_ADAPTER_REVIEW",
        "source_readiness_sha256": readiness_hash,
        "source_backend_sha256": backend_hash,
        "source_route_plan_sha256": route_hash,
        "source_ik_adapter_sha256": ik_adapter_hash,
        "source_ik_adapter_review_sha256": ik_review_hash,
        "source_files_sha256": {
            "arm266_readiness": readiness_file_sha256,
            "arm255_backend": backend_file_sha256,
            "arm231_route": route_file_sha256,
            "arm267_adapter": ik_adapter_file_sha256,
            "arm267_adapter_review": ik_review_file_sha256,
            "canonical_ik_source": ik_source_file_sha256,
            "pinned_urdf": urdf_file_sha256,
            "native_mechanics_source": mechanics_source_file_sha256,
            "arm268_adapter_source": adapter_source_file_sha256,
        },
        "backend_method": "measure_tool_key",
        "row_range": {
            "first_sequence": FIRST_SEQUENCE,
            "last_sequence": LAST_SEQUENCE,
        },
        "joint_order": list(JOINT_ORDER),
        "accepted_phases": ["TRANSIT", "HOVER"],
        "tool_surface_point": "CANONICAL_IK_TOOL_TIP_ENDPOINT",
        "key_pose_source": "NATIVE_RIGID_PRIM_GET_WORLD_POSES",
        "key_half_height_mm": KEY_HALF_HEIGHT_MM,
        "stage_units_in_meters": STAGE_UNITS_IN_METERS,
        "clearance_equation": "tool_tip_world_z_mm-key_center_world_z_mm-3.0",
        "displacement_equation": "settled_key_center_z_mm-observed_key_center_z_mm",
        "minimum_noncontact_clearance_mm": 0.5,
        "maximum_absolute_key_displacement_mm": 0.05,
        "joint_submission_required": False,
        "adapter_implemented": True,
        "runtime_integration_admitted": False,
        "launch_admitted": False,
        "attempt_consumed": False,
        "isaac_started": False,
        "scene_loaded": False,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "key_contact": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": "INDEPENDENTLY_REVIEW_TOOL_KEY_METRICS_ADAPTER",
        "limitations": [
            "definition_cli_does_not_import_isaac_or_construct_runtime_objects",
            "runtime_adapter_reads_only_the_supplied_key_pose_view",
            "tool_pose_is_kinematic_and_does_not_prove_native_tracking",
            "adapter_does_not_check_continuous_clearance_or_root_drift",
            "adapter_cannot_submit_joint_targets_or_authorize_an_attempt",
        ],
    }
    return {**core, "adapter_sha256": _sha(core)}


def _runtime_types() -> tuple[Any, ...]:
    from rocell.geometry import JointPosition, RigidTransform, Rotation3, Vec3
    from rocell.kinematics.ik import HAND_TCP_LINK_NAME, RoArmM3NumericalIk

    return (
        JointPosition,
        RigidTransform,
        Rotation3,
        Vec3,
        HAND_TCP_LINK_NAME,
        RoArmM3NumericalIk,
    )


def _tensor_list(value: Any, label: str) -> Any:
    try:
        if hasattr(value, "numpy"):
            value = value.numpy()
        if hasattr(value, "tolist"):
            value = value.tolist()
    except Exception as exc:  # pragma: no cover - native tensor boundary
        raise ToolKeyMetricsAdapterError(f"{label} cannot be converted") from exc
    return value


class ToolKeyMetricsRuntimeAdapter:
    """Read-only native-key and canonical-FK implementation of ARM-255."""

    def __init__(
        self,
        definition: Mapping[str, Any],
        *,
        adapter_review: Mapping[str, Any],
        solver: Any,
        key_view: Any,
        settled_key_center_z_stage: float,
    ) -> None:
        adapter_hash = _require_hash(definition, "adapter_sha256", "ARM-268 adapter")
        _require_hash(adapter_review, "adapter_review_sha256", "ARM-268 review")
        *_, solver_type = _runtime_types()
        pose_reader = getattr(key_view, "get_world_poses", None)
        if (
            definition.get("schema") != ADAPTER_SCHEMA
            or definition.get("status")
            != "READY_FOR_INDEPENDENT_TOOL_KEY_METRICS_ADAPTER_REVIEW"
            or definition.get("backend_method") != "measure_tool_key"
            or definition.get("joint_submission_required") is not False
            or adapter_review.get("schema") != ADAPTER_REVIEW_SCHEMA
            or adapter_review.get("status")
            != "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
            or adapter_review.get("source_adapter_sha256") != adapter_hash
            or adapter_review.get("runtime_integration_admitted") is not True
            or adapter_review.get("launch_admitted") is not False
            or adapter_review.get("attempt_consumed") is not False
            or not isinstance(solver, solver_type)
            or not callable(pose_reader)
        ):
            raise ToolKeyMetricsAdapterError(
                "tool/key metrics runtime composition is not admissible"
            )
        self._definition = definition
        self._solver = solver
        self._key_view = key_view
        self._settled_key_z = _finite(
            settled_key_center_z_stage, "settled key center Z"
        )

    def _observed_key_center_z_stage(self) -> float:
        poses = self._key_view.get_world_poses()
        if not isinstance(poses, (list, tuple)) or not poses:
            raise ToolKeyMetricsAdapterError("native key pose result changed")
        positions = _tensor_list(poses[0], "native key positions")
        if (
            not isinstance(positions, list)
            or len(positions) != 1
            or not isinstance(positions[0], (list, tuple))
            or len(positions[0]) != 3
        ):
            raise ToolKeyMetricsAdapterError("native key position shape changed")
        return _finite(positions[0][2], "observed key center Z")

    def measure_tool_key(
        self,
        *,
        sequence: int,
        joint_targets_rad: Sequence[float],
        phase: str,
    ) -> Mapping[str, Any]:
        (
            JointPosition,
            RigidTransform,
            Rotation3,
            Vec3,
            hand_tcp_link_name,
            _solver_type,
        ) = _runtime_types()
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or not FIRST_SEQUENCE <= sequence <= LAST_SEQUENCE
            or phase not in {"TRANSIT", "HOVER"}
        ):
            raise ToolKeyMetricsAdapterError(
                "metric row is outside the reviewed window"
            )
        joints = _joints(joint_targets_rad, "metric row joints")
        fixed_gripper = _finite(
            self._solver.fixed_gripper_position.value, "fixed gripper"
        )
        if joints[-1] != fixed_gripper:
            raise ToolKeyMetricsAdapterError(
                "metric row gripper differs from fixed gripper"
            )
        state = {
            name: JointPosition.radians(value)
            for name, value in zip(JOINT_ORDER[:-1], joints[:-1])
        }
        state[JOINT_ORDER[-1]] = self._solver.fixed_gripper_position
        world_t_hand = self._solver.model.forward_kinematics(state)[hand_tcp_link_name]
        hand_t_tip = RigidTransform(
            hand_tcp_link_name,
            "tool_tip",
            Rotation3.identity(),
            Vec3(0.0, 0.0, self._solver.hand_tcp_to_tip_z_mm),
        )
        world_t_tip = world_t_hand.compose(hand_t_tip)
        tool_tip_z_mm = _finite(world_t_tip.translation_mm.z, "tool-tip world Z")
        observed_key_z_stage = self._observed_key_center_z_stage()
        millimeters_per_stage_unit = (
            _finite(
                self._definition.get("stage_units_in_meters"),
                "stage units in meters",
            )
            * 1000.0
        )
        observed_key_z_mm = observed_key_z_stage * millimeters_per_stage_unit
        settled_key_z_mm = self._settled_key_z * millimeters_per_stage_unit
        clearance = (
            tool_tip_z_mm
            - observed_key_z_mm
            - _finite(self._definition.get("key_half_height_mm"), "key half height")
        )
        displacement = settled_key_z_mm - observed_key_z_mm
        return {
            "sequence": sequence,
            "determinate": True,
            "tool_key_clearance_mm": clearance,
            "key_displacement_mm": displacement,
        }


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ToolKeyMetricsAdapterError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--ik-adapter", type=Path, required=True)
    parser.add_argument("--ik-adapter-review", type=Path, required=True)
    parser.add_argument("--ik-source", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--mechanics-source", type=Path, required=True)
    parser.add_argument("--adapter-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_adapter_definition(
        _load(args.readiness),
        _load(args.backend),
        _load(args.route),
        _load(args.ik_adapter),
        _load(args.ik_adapter_review),
        readiness_file_sha256=_file_sha(args.readiness),
        backend_file_sha256=_file_sha(args.backend),
        route_file_sha256=_file_sha(args.route),
        ik_adapter_file_sha256=_file_sha(args.ik_adapter),
        ik_review_file_sha256=_file_sha(args.ik_adapter_review),
        ik_source_file_sha256=_file_sha(args.ik_source),
        urdf_file_sha256=_file_sha(args.urdf),
        mechanics_source_file_sha256=_file_sha(args.mechanics_source),
        adapter_source_file_sha256=_file_sha(args.adapter_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
