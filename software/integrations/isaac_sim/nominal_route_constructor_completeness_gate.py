"""Prove the corrected nominal runtime crosses ARM-295's constructor boundary.

ARM-296 is an inert, zero-authority gate.  It loads the exact reviewed runtime
documents and canonical IK inputs, constructs the real solver and all four
runtime adapters around deliberately inert protocol sentinels, and stops.  It
does not import Isaac, create a simulator session, step physics, invoke a
runtime method, submit a joint target, play a trajectory, or access hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from nominal_route_complete_runtime_composition import CompleteRuntimeComposition
from nominal_route_concrete_native_attempt_binding import (
    BindingPaths,
    _build_solver_kwargs,
    _load_runtime_documents,
)
from nominal_route_native_root_path_correction import (
    ACTUAL_ROOT_PATH,
    CorrectedRootRuntimeFactory,
    corrected_native_metadata,
)
from nominal_route_native_runtime_factory import construct_runtime
from nominal_route_native_sweep_binding import (
    EXPECTED_DOF_NAMES,
    PROFILE_TO_NATIVE_LINK,
)


SCHEMA = "tactevra.isaac_lm4_constructor_completeness_gate.v1"
EXPECTED_ARM295_STATUS_SHA256 = (
    "7490b9e2bac3d3adf0146ca08e6a61a542bd4d8952329d68e8bfeb12970da1b8"
)
EXPECTED_CORRECTED_BINDING_SOURCE_SHA256 = (
    "2d93fe5647e3596fded4c3f8ba7e33f7c89a495f76fcf69620327588eb2d1fe7"
)


class ConstructorCompletenessGateError(ValueError):
    """Raised when retained evidence or the inert constructor boundary changes."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ConstructorCompletenessGateError(
            "gate output is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ConstructorCompletenessGateError(
            f"required input unavailable: {path}"
        ) from exc


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ConstructorCompletenessGateError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise ConstructorCompletenessGateError(f"{path} must contain an object")
    return value


class _InertArticulation:
    dof_names = EXPECTED_DOF_NAMES
    link_names = tuple(PROFILE_TO_NATIVE_LINK.values())

    def __init__(self) -> None:
        self.protocol_calls: list[str] = []

    def get_link_transforms(self, *args: Any, **kwargs: Any) -> None:
        self.protocol_calls.append("get_link_transforms")
        raise AssertionError("constructor gate must not read link transforms")

    def set_dof_positions(self, *args: Any, **kwargs: Any) -> None:
        self.protocol_calls.append("set_dof_positions")
        raise AssertionError("constructor gate must not submit joint positions")


class _InertSceneQuery:
    def __init__(self) -> None:
        self.protocol_calls: list[str] = []

    def overlap_sphere_any(self, *args: Any, **kwargs: Any) -> None:
        self.protocol_calls.append("overlap_sphere_any")
        raise AssertionError("constructor gate must not query scene overlap")

    def sweep_sphere_any(self, *args: Any, **kwargs: Any) -> None:
        self.protocol_calls.append("sweep_sphere_any")
        raise AssertionError("constructor gate must not query scene sweeps")


class _InertPoseView:
    def __init__(
        self,
        *,
        prim_path: str,
        position: tuple[float, float, float],
        quaternion_wxyz: tuple[float, float, float, float],
    ) -> None:
        self.prim_path = prim_path
        self._position = position
        self._quaternion = quaternion_wxyz
        self.reads = 0

    def get_world_poses(self) -> tuple[list[list[float]], list[list[float]]]:
        self.reads += 1
        if self.reads != 1:
            raise AssertionError("constructor gate permits one baseline read only")
        return ([list(self._position)], [list(self._quaternion)])


def _validate_arm295(status_path: Path) -> dict[str, Any]:
    status = _load(status_path)
    if _file_sha(status_path) != EXPECTED_ARM295_STATUS_SHA256 or status != {
        "attempt_count": 1,
        "automatic_retry": False,
        "error_message": (
            "RoArmM3NumericalIk.__init__() missing 4 required keyword-only "
            "arguments: 'model', 'board_T_world', 'hand_tcp_to_tip_z_mm', "
            "and 'fixed_gripper_position'"
        ),
        "error_stage": "construct_runtime",
        "error_type": "TypeError",
        "hardware_access": False,
        "physical_authority": False,
        "status": "FAILED_RETAINED_NO_RETRY",
    }:
        raise ConstructorCompletenessGateError("ARM-295 terminal evidence changed")
    return status


def _solver_summary(solver_kwargs: Mapping[str, Any]) -> dict[str, Any]:
    model = solver_kwargs["model"]
    board = solver_kwargs["board_T_world"]
    options = solver_kwargs["options"]
    fixed_gripper = solver_kwargs["fixed_gripper_position"]
    return {
        "input_names": sorted(solver_kwargs),
        "model_type": type(model).__name__,
        "model_root_link": model.root_link,
        "board_transform_frames": [board.parent_frame, board.child_frame],
        "hand_tcp_to_tip_z_mm": float(solver_kwargs["hand_tcp_to_tip_z_mm"]),
        "fixed_gripper_position_rad": float(fixed_gripper.value),
        "ready_joint_names": sorted(solver_kwargs["ready_arm_joint_positions"]),
        "joint_bound_names": sorted(solver_kwargs["joint_bounds_rad"]),
        "ik_max_attempts": int(options.max_attempts),
        "ik_max_iterations_per_attempt": int(options.max_iterations_per_attempt),
    }


def run_constructor_completeness_gate(
    *, artifact_root: Path, repo_root: Path
) -> dict[str, Any]:
    """Construct the production runtime around inert sentinels and stop."""
    status_path = artifact_root / "arm295-nominal-route-physics-attempt-001/status.json"
    _validate_arm295(status_path)
    binding_source = (
        repo_root
        / "software/integrations/isaac_sim/nominal_route_concrete_native_attempt_binding.py"
    )
    if _file_sha(binding_source) != EXPECTED_CORRECTED_BINDING_SOURCE_SHA256:
        raise ConstructorCompletenessGateError("corrected binding source changed")

    paths = BindingPaths(
        artifact_root=artifact_root,
        repo_root=repo_root,
        governed_attempt_directory=artifact_root / ".arm296-never-an-attempt",
    )
    definition = _load(artifact_root / "arm272-native-runtime-factory-001/factory.json")
    factory_review = _load(
        artifact_root / "arm272-native-runtime-factory-review-001/review.json"
    )
    plan = _load(
        artifact_root / "arm271-native-runtime-construction-plan-002/plan.json"
    )
    plan_review = _load(
        artifact_root / "arm271-native-runtime-construction-plan-review-002/review.json"
    )
    documents = _load_runtime_documents(paths)
    solver_kwargs = _build_solver_kwargs(paths)

    articulation = _InertArticulation()
    scene_query = _InertSceneQuery()
    key_view = _InertPoseView(
        prim_path="/World/Keyboard/SPACE",
        position=(0.0, 0.0, 0.02),
        quaternion_wxyz=(1.0, 0.0, 0.0, 0.0),
    )
    root_view = _InertPoseView(
        prim_path=ACTUAL_ROOT_PATH,
        position=(0.0, 0.0, 0.0),
        quaternion_wxyz=(1.0, 0.0, 0.0, 0.0),
    )
    corrected_factory = CorrectedRootRuntimeFactory(construct_runtime)
    runtime = corrected_factory(
        definition,
        factory_review=factory_review,
        plan=plan,
        plan_review=plan_review,
        documents=documents,
        articulation=articulation,
        scene_query=scene_query,
        key_view=key_view,
        root_view=root_view,
        solver_kwargs=solver_kwargs,
        native_metadata=corrected_native_metadata(),
    )

    if not isinstance(runtime, CompleteRuntimeComposition):
        raise ConstructorCompletenessGateError("runtime composition type changed")
    solver = runtime._ik._solver
    if (
        runtime._metrics._solver is not solver
        or key_view.reads != 1
        or root_view.reads != 1
        or corrected_factory.calls != 1
        or articulation.protocol_calls
        or scene_query.protocol_calls
    ):
        raise ConstructorCompletenessGateError(
            "inert runtime construction behavior changed"
        )

    core = {
        "schema": SCHEMA,
        "gate_id": "arm296-constructor-completeness-gate-001",
        "status": "PASS_CORRECTED_RUNTIME_CONSTRUCTOR_COMPLETENESS",
        "source_arm295_status_sha256": EXPECTED_ARM295_STATUS_SHA256,
        "source_corrected_binding_sha256": (EXPECTED_CORRECTED_BINDING_SOURCE_SHA256),
        "former_failure_stage": "construct_runtime",
        "former_failure_crossed": True,
        "runtime_type": type(runtime).__name__,
        "component_types": {
            "clearance": type(runtime._clearance).__name__,
            "ik": type(runtime._ik).__name__,
            "metrics": type(runtime._metrics).__name__,
            "drift": type(runtime._drift).__name__,
            "solver": type(solver).__name__,
        },
        "solver": _solver_summary(solver_kwargs),
        "shared_solver_identity_verified": True,
        "baseline_reads": {"key_view": key_view.reads, "root_view": root_view.reads},
        "protocol_calls": {
            "articulation": articulation.protocol_calls,
            "scene_query": scene_query.protocol_calls,
        },
        "attempt_consumed": False,
        "isaac_imported": False,
        "isaac_started": False,
        "scene_loaded": False,
        "physics_steps": 0,
        "runtime_methods_called": [],
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "key_contact": False,
        "automatic_retry": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "next_required_stage": "INDEPENDENTLY_REVIEW_ARM296_GATE_RECEIPT",
    }
    return {**core, "gate_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    if args.output_directory.exists():
        raise ConstructorCompletenessGateError("gate output exists; retry refused")
    receipt = run_constructor_completeness_gate(
        artifact_root=args.artifact_root, repo_root=args.repo_root
    )
    args.output_directory.mkdir(parents=True, exist_ok=False)
    (args.output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
