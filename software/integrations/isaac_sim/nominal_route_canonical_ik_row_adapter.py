"""Provide the ARM-255 ``regenerate_row`` method with canonical offline IK.

ARM-267 preserves each source row's Cartesian tool-tip pose by recomputing it
with the pinned kinematic model, then solves that pose with the canonical
RoArm-M3 IK implementation and the previously accepted row as the first seed.
The definition CLI is import-safe and non-executing.  The runtime class performs
kinematic math only; it has no Isaac, controller, serial, or hardware surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


ADAPTER_SCHEMA = "tactevra.isaac_lm4_canonical_ik_row_adapter.v1"
ADAPTER_REVIEW_SCHEMA = "tactevra.isaac_lm4_canonical_ik_row_adapter_review.v1"
READINESS_SCHEMA = "tactevra.isaac_lm4_runtime_composition_readiness.v1"
BACKEND_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_backend.v1"
ROUTE_SCHEMA = "tactevra.isaac_lm4_state_policy_native_mechanics_replay_plan.v2"

EXPECTED_READINESS_SHA256 = (
    "7259e53c0e5522a090a0cdce9c36034fc793bcd093cdfdcce63bee9b99f14bab"
)
EXPECTED_BACKEND_SHA256 = (
    "132f1e028503a3a83af11f2a713f839e00e1fef49aa9cb3fbb0156f858245cde"
)
EXPECTED_ROUTE_SHA256 = (
    "1076f9747429f77f2581fb3a13e7278385d583c9de6c439c76ff38b26b04b16b"
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
EXPECTED_IK_SOURCE_SHA256 = (
    "4feb5adb8c33d7b3017f29c17130dc934269ae159bed88b06d8aa63d8474569a"
)
EXPECTED_URDF_SHA256 = (
    "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
)

FIRST_SEQUENCE = 654
LAST_SEQUENCE = 940
JOINT_ORDER = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
    "link5_to_gripper_link",
)
ARM_JOINT_ORDER = JOINT_ORDER[:-1]


class CanonicalIkRowAdapterError(ValueError):
    """Raised when lineage or deterministic IK evidence fails closed."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanonicalIkRowAdapterError("input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise CanonicalIkRowAdapterError(f"{label} hash changed")
    return claimed


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CanonicalIkRowAdapterError(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise CanonicalIkRowAdapterError(f"{label} is not finite")
    return result


def _joints(value: Any, label: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != len(JOINT_ORDER):
        raise CanonicalIkRowAdapterError(f"{label} must contain six joints")
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
    *,
    readiness_file_sha256: str,
    backend_file_sha256: str,
    route_file_sha256: str,
    ik_source_file_sha256: str,
    urdf_file_sha256: str,
    adapter_source_file_sha256: str,
) -> dict[str, Any]:
    """Build a review input without constructing or running the IK solver."""

    readiness_hash = _require_hash(
        readiness, "readiness_sha256", "ARM-266 readiness"
    )
    backend_hash = _require_hash(backend, "backend_sha256", "ARM-255 backend")
    route_hash = _require_hash(route, "plan_sha256", "ARM-231 route")
    rows = route.get("joint_targets")
    if (
        readiness.get("schema") != READINESS_SCHEMA
        or readiness.get("status")
        != "READY_TO_IMPLEMENT_REMAINING_ZERO_AUTHORITY_RUNTIME_ADAPTERS"
        or readiness_hash != EXPECTED_READINESS_SHA256
        or readiness.get("source_backend_sha256") != backend_hash
        or readiness.get("reviewed_methods") != ["check_continuous_clearance"]
        or readiness.get("remaining_methods")
        != ["regenerate_row", "measure_tool_key", "root_drift"]
        or readiness.get("next_required_stage")
        != "IMPLEMENT_AND_REVIEW_CANONICAL_IK_ROW_ADAPTER"
        or backend.get("schema") != BACKEND_SCHEMA
        or backend_hash != EXPECTED_BACKEND_SHA256
        or backend.get("source_route_plan_sha256") != route_hash
        or backend.get("runtime_protocol", {}).get("canonical_ik")
        != "ONE_ACCEPTED_DETERMINATE_RESULT_PER_REGENERATED_ROW"
        or route_hash != EXPECTED_ROUTE_SHA256
        or route.get("schema") != ROUTE_SCHEMA
        or route.get("joint_order") != list(JOINT_ORDER)
        or not isinstance(rows, list)
        or len(rows) != 1416
        or any(row.get("sequence") != index for index, row in enumerate(rows))
        or any(
            row.get("phase") not in {"TRANSIT", "HOVER"}
            for row in rows[FIRST_SEQUENCE : LAST_SEQUENCE + 1]
        )
        or readiness_file_sha256 != EXPECTED_READINESS_FILE_SHA256
        or backend_file_sha256 != EXPECTED_BACKEND_FILE_SHA256
        or route_file_sha256 != EXPECTED_ROUTE_FILE_SHA256
        or ik_source_file_sha256 != EXPECTED_IK_SOURCE_SHA256
        or urdf_file_sha256 != EXPECTED_URDF_SHA256
        or not isinstance(adapter_source_file_sha256, str)
        or len(adapter_source_file_sha256) != 64
        or not _zero_authority(readiness)
    ):
        raise CanonicalIkRowAdapterError(
            "canonical IK row adapter lineage or boundary changed"
        )
    for index in range(FIRST_SEQUENCE - 1, LAST_SEQUENCE + 1):
        _joints(rows[index].get("joint_position_target_rad"), f"route row {index}")

    core: dict[str, Any] = {
        "schema": ADAPTER_SCHEMA,
        "adapter_id": "arm267-zero-authority-canonical-ik-row-adapter-001",
        "status": "READY_FOR_INDEPENDENT_CANONICAL_IK_ROW_ADAPTER_REVIEW",
        "source_readiness_sha256": readiness_hash,
        "source_backend_sha256": backend_hash,
        "source_route_plan_sha256": route_hash,
        "source_files_sha256": {
            "arm266_readiness": readiness_file_sha256,
            "arm255_backend": backend_file_sha256,
            "arm231_route": route_file_sha256,
            "canonical_ik_source": ik_source_file_sha256,
            "pinned_urdf": urdf_file_sha256,
            "arm267_adapter_source": adapter_source_file_sha256,
        },
        "backend_method": "regenerate_row",
        "row_range": {"first_sequence": FIRST_SEQUENCE, "last_sequence": LAST_SEQUENCE},
        "joint_order": list(JOINT_ORDER),
        "target_derivation": "SOURCE_ROW_FORWARD_KINEMATICS_TOOL_TIP_POSE",
        "solver": "rocell.kinematics.ik.RoArmM3NumericalIk",
        "continuity_seed": "PREVIOUS_ACCEPTED_ROW_FIRST_SEED",
        "source_gripper_must_equal_fixed_gripper": True,
        "accepted_result": "ONE_CONVERGED_DETERMINATE_RESULT_PER_ROW",
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
        "next_required_stage": "INDEPENDENTLY_REVIEW_CANONICAL_IK_ROW_ADAPTER",
        "limitations": [
            "definition_cli_does_not_import_or_run_the_canonical_solver",
            "runtime_adapter_performs_kinematic_math_only",
            "adapter_does_not_check_collision_tool_key_metrics_or_root_drift",
            "adapter_cannot_submit_joint_targets_or_authorize_an_attempt",
        ],
    }
    return {**core, "adapter_sha256": _sha(core)}


def _runtime_types() -> tuple[Any, ...]:
    from rocell.geometry import JointPosition, Point3Mm, RigidTransform, Rotation3, Vec3
    from rocell.kinematics import BoardToolTipTarget
    from rocell.kinematics.ik import HAND_TCP_LINK_NAME, RoArmM3NumericalIk

    return (
        JointPosition, Point3Mm, RigidTransform, Rotation3, Vec3,
        BoardToolTipTarget, HAND_TCP_LINK_NAME, RoArmM3NumericalIk,
    )


class CanonicalIkRowRuntimeAdapter:
    """Offline canonical-IK implementation of the ARM-255 row boundary."""

    def __init__(
        self,
        definition: Mapping[str, Any],
        *,
        adapter_review: Mapping[str, Any],
        solver: Any,
    ) -> None:
        adapter_hash = _require_hash(definition, "adapter_sha256", "ARM-267 adapter")
        _require_hash(adapter_review, "adapter_review_sha256", "ARM-267 review")
        *_, solver_type = _runtime_types()
        if (
            definition.get("schema") != ADAPTER_SCHEMA
            or definition.get("status")
            != "READY_FOR_INDEPENDENT_CANONICAL_IK_ROW_ADAPTER_REVIEW"
            or definition.get("backend_method") != "regenerate_row"
            or adapter_review.get("schema") != ADAPTER_REVIEW_SCHEMA
            or adapter_review.get("status")
            != "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
            or adapter_review.get("source_adapter_sha256") != adapter_hash
            or adapter_review.get("runtime_integration_admitted") is not True
            or adapter_review.get("launch_admitted") is not False
            or adapter_review.get("attempt_consumed") is not False
            or not isinstance(solver, solver_type)
        ):
            raise CanonicalIkRowAdapterError(
                "canonical IK row runtime composition is not admissible"
            )
        self._solver = solver

    def regenerate_row(
        self,
        *,
        source_row: Mapping[str, Any],
        previous_joint_targets_rad: Sequence[float],
    ) -> Mapping[str, Any]:
        (
            JointPosition, Point3Mm, RigidTransform, Rotation3, Vec3,
            BoardToolTipTarget, hand_tcp_link_name, _solver_type,
        ) = _runtime_types()
        sequence = source_row.get("sequence")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or not FIRST_SEQUENCE <= sequence <= LAST_SEQUENCE
            or source_row.get("phase") not in {"TRANSIT", "HOVER"}
        ):
            raise CanonicalIkRowAdapterError("source row is outside the reviewed window")
        source = _joints(source_row.get("joint_position_target_rad"), "source row")
        previous = _joints(previous_joint_targets_rad, "previous row")
        fixed_gripper = _finite(
            self._solver.fixed_gripper_position.value, "fixed gripper"
        )
        if source[-1] != fixed_gripper or previous[-1] != fixed_gripper:
            raise CanonicalIkRowAdapterError("route gripper differs from fixed gripper")

        source_state = {
            name: JointPosition.radians(value)
            for name, value in zip(ARM_JOINT_ORDER, source[:-1])
        }
        source_state[JOINT_ORDER[-1]] = self._solver.fixed_gripper_position
        world_t_hand = self._solver.model.forward_kinematics(source_state)[
            hand_tcp_link_name
        ]
        hand_t_tip = RigidTransform(
            hand_tcp_link_name,
            "tool_tip",
            Rotation3.identity(),
            Vec3(0.0, 0.0, self._solver.hand_tcp_to_tip_z_mm),
        )
        board_t_tip = self._solver.board_T_world.compose(world_t_hand).compose(
            hand_t_tip
        )
        tip = board_t_tip.translation_mm
        target = BoardToolTipTarget(
            Point3Mm(self._solver.board_T_world.parent_frame, tip.x, tip.y, tip.z)
        )
        seed = {
            name: JointPosition.radians(value)
            for name, value in zip(ARM_JOINT_ORDER, previous[:-1])
        }
        solved = self._solver.solve(target, seed_joint_positions=(seed,))
        if solved.converged is not True:
            raise CanonicalIkRowAdapterError(f"canonical IK row {sequence} did not converge")
        names = tuple(item.name for item in solved.solution_arm_joint_positions)
        if names != ARM_JOINT_ORDER:
            raise CanonicalIkRowAdapterError("canonical IK joint order changed")
        joints = [
            _finite(item.position.value, "canonical IK solution")
            for item in solved.solution_arm_joint_positions
        ]
        joints.append(fixed_gripper)
        residual = _finite(solved.residual.position_error_mm, "position error")
        return {
            "sequence": sequence,
            "accepted": True,
            "determinate": True,
            "joint_position_target_rad": joints,
            "position_error_mm": residual,
        }


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise CanonicalIkRowAdapterError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--ik-source", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--adapter-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_adapter_definition(
        _load(args.readiness), _load(args.backend), _load(args.route),
        readiness_file_sha256=_file_sha(args.readiness),
        backend_file_sha256=_file_sha(args.backend),
        route_file_sha256=_file_sha(args.route),
        ik_source_file_sha256=_file_sha(args.ik_source),
        urdf_file_sha256=_file_sha(args.urdf),
        adapter_source_file_sha256=_file_sha(args.adapter_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
