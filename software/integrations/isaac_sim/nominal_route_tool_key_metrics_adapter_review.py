"""Independently review the ARM-268 tool/key metrics adapter.

The reviewer reproduces the definition, inspects the read-only operation
surface, and exercises the FK/native-key calculation with non-runtime doubles.
It imports no Isaac module, starts no simulator, and submits no joint target.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping


REVIEW_SCHEMA = "tactevra.isaac_lm4_tool_key_metrics_adapter_review.v1"
EXPECTED_ADAPTER_SHA256 = (
    "5b2327498efe78ced7d7c5ef88db170f0596d59b83a22a56df5e8b5f60493f19"
)
EXPECTED_ADAPTER_FILE_SHA256 = (
    "e4b059e0fc78343eda7959c2e97ac66565db93fe859e8a0dc0e5591eee8e41da"
)
EXPECTED_ADAPTER_SOURCE_SHA256 = (
    "b7555a1414b4431ad92ebefb9a6ffb8f18a3e6d763ce4e73e6f7747c4474be6b"
)


class ToolKeyMetricsAdapterReviewError(ValueError):
    """Raised when the adapter or review evidence changes."""


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
        raise ToolKeyMetricsAdapterReviewError("input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise ToolKeyMetricsAdapterReviewError(f"{label} hash changed")
    return claimed


def _import_adapter(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("arm268_reviewed_adapter", path)
    if spec is None or spec.loader is None:
        raise ToolKeyMetricsAdapterReviewError("adapter source cannot be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _review_source(payload: bytes) -> dict[str, bool]:
    text = payload.decode("utf-8")
    forbidden = (
        "import isaacsim",
        "from isaacsim",
        "SimulationApp(",
        "import serial",
        "set_dof_positions",
        "set_dof_position_targets",
        "execute_backend(",
    )
    if any(token in text for token in forbidden):
        raise ToolKeyMetricsAdapterReviewError("forbidden runtime surface found")
    tree = ast.parse(text)
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    runtime = classes.get("ToolKeyMetricsRuntimeAdapter")
    if runtime is None:
        raise ToolKeyMetricsAdapterReviewError("runtime adapter class is absent")
    methods = {
        node.name: node for node in runtime.body if isinstance(node, ast.FunctionDef)
    }
    method = methods.get("measure_tool_key")
    pose_method = methods.get("_observed_key_center_z_stage")
    if method is None or pose_method is None:
        raise ToolKeyMetricsAdapterReviewError("metric operation surface is absent")
    calls = {
        ast.unparse(node.func)
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
    }
    pose_calls = {
        ast.unparse(node.func)
        for node in ast.walk(pose_method)
        if isinstance(node, ast.Call)
    }
    if "self._solver.model.forward_kinematics" not in calls:
        raise ToolKeyMetricsAdapterReviewError("canonical FK call is absent")
    if "self._key_view.get_world_poses" not in pose_calls:
        raise ToolKeyMetricsAdapterReviewError("native key pose read is absent")
    return {
        "forbidden_runtime_imports_absent": True,
        "joint_submission_calls_absent": True,
        "canonical_fk_call_present": True,
        "native_key_pose_read_present": True,
        "backend_execution_call_absent": True,
    }


class _Joint:
    def __init__(self, value: float) -> None:
        self.value = float(value)

    @classmethod
    def radians(cls, value: float) -> "_Joint":
        return cls(value)


class _Vec:
    def __init__(self, x: float, y: float, z: float) -> None:
        self.x, self.y, self.z = x, y, z


class _Rotation:
    @staticmethod
    def identity() -> "_Rotation":
        return _Rotation()


class _Transform:
    def __init__(self, *args: Any, translation_mm: Any = None, **_kwargs: Any) -> None:
        self.parent_frame = args[0] if args else "world"
        if translation_mm is not None:
            self.translation_mm = translation_mm
        elif len(args) >= 4:
            self.translation_mm = args[3]
        else:
            self.translation_mm = _Vec(0.0, 0.0, 0.0)

    def compose(self, other: "_Transform") -> "_Transform":
        left, right = self.translation_mm, other.translation_mm
        return _Transform(
            self.parent_frame,
            translation_mm=_Vec(
                left.x + right.x,
                left.y + right.y,
                left.z + right.z,
            ),
        )


class _Model:
    def forward_kinematics(self, state: Mapping[str, _Joint]) -> dict[str, _Transform]:
        if len(state) != 6:
            raise AssertionError("review FK state did not contain six joints")
        return {"hand_tcp": _Transform("world", translation_mm=_Vec(10.0, 20.0, 15.0))}


class _Solver:
    def __init__(self) -> None:
        self.model = _Model()
        self.hand_tcp_to_tip_z_mm = -5.0
        self.fixed_gripper_position = _Joint(0.25)


class _Tensor:
    def __init__(self, value: Any) -> None:
        self._value = value

    def numpy(self) -> "_Tensor":
        return self

    def tolist(self) -> Any:
        return self._value


class _KeyView:
    def __init__(self, z_stage: float) -> None:
        self.z_stage = z_stage

    def get_world_poses(self) -> tuple[_Tensor, _Tensor]:
        return (
            _Tensor([[0.0, 0.0, self.z_stage]]),
            _Tensor([[1.0, 0.0, 0.0, 0.0]]),
        )


def _exercise_runtime(adapter: Any, definition: Mapping[str, Any]) -> dict[str, Any]:
    adapter._runtime_types = lambda: (
        _Joint,
        _Transform,
        _Rotation,
        _Vec,
        "hand_tcp",
        _Solver,
    )
    review_core = {
        "schema": adapter.ADAPTER_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "source_adapter_sha256": definition["adapter_sha256"],
        "runtime_integration_admitted": True,
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    review = {
        **review_core,
        "adapter_review_sha256": adapter._sha(review_core),
    }
    runtime = adapter.ToolKeyMetricsRuntimeAdapter(
        definition,
        adapter_review=review,
        solver=_Solver(),
        key_view=_KeyView(0.006),
        settled_key_center_z_stage=0.006,
    )
    result = runtime.measure_tool_key(
        sequence=654,
        joint_targets_rad=[0.0, 0.1, 0.2, 0.3, 0.4, 0.25],
        phase="TRANSIT",
    )
    if result != {
        "sequence": 654,
        "determinate": True,
        "tool_key_clearance_mm": 1.0,
        "key_displacement_mm": 0.0,
    }:
        raise ToolKeyMetricsAdapterReviewError("runtime metric evidence changed")
    return dict(result)


def review_adapter(
    definition: Mapping[str, Any],
    readiness: Mapping[str, Any],
    backend: Mapping[str, Any],
    route: Mapping[str, Any],
    ik_adapter: Mapping[str, Any],
    ik_review: Mapping[str, Any],
    *,
    adapter_file_sha256: str,
    adapter_source_path: Path,
    readiness_file_sha256: str,
    backend_file_sha256: str,
    route_file_sha256: str,
    ik_adapter_file_sha256: str,
    ik_review_file_sha256: str,
    ik_source_file_sha256: str,
    urdf_file_sha256: str,
    mechanics_source_file_sha256: str,
) -> dict[str, Any]:
    adapter_hash = _require_hash(definition, "adapter_sha256", "ARM-268 adapter")
    source_sha = _file_sha(adapter_source_path)
    if (
        adapter_hash != EXPECTED_ADAPTER_SHA256
        or adapter_file_sha256 != EXPECTED_ADAPTER_FILE_SHA256
        or source_sha != EXPECTED_ADAPTER_SOURCE_SHA256
    ):
        raise ToolKeyMetricsAdapterReviewError("adapter review boundary changed")
    adapter = _import_adapter(adapter_source_path)
    reproduced = adapter.build_adapter_definition(
        readiness,
        backend,
        route,
        ik_adapter,
        ik_review,
        readiness_file_sha256=readiness_file_sha256,
        backend_file_sha256=backend_file_sha256,
        route_file_sha256=route_file_sha256,
        ik_adapter_file_sha256=ik_adapter_file_sha256,
        ik_review_file_sha256=ik_review_file_sha256,
        ik_source_file_sha256=ik_source_file_sha256,
        urdf_file_sha256=urdf_file_sha256,
        mechanics_source_file_sha256=mechanics_source_file_sha256,
        adapter_source_file_sha256=source_sha,
    )
    if reproduced != definition:
        raise ToolKeyMetricsAdapterReviewError("adapter definition did not reproduce")
    source_review = _review_source(adapter_source_path.read_bytes())
    runtime_evidence = _exercise_runtime(adapter, definition)
    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm268-tool-key-metrics-adapter-review-001",
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "source_adapter_sha256": adapter_hash,
        "source_adapter_file_sha256": adapter_file_sha256,
        "source_adapter_source_sha256": source_sha,
        "definition_reproduced": True,
        "source_call_surface_reviewed": True,
        "offline_fk_native_key_composition_verified": True,
        "reviewed_runtime_evidence": runtime_evidence,
        "source_review": source_review,
        "runtime_integration_admitted": True,
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
        "next_required_stage": "IMPLEMENT_AND_REVIEW_ROOT_DRIFT_ADAPTER",
        "limitations": [
            "review_uses_non_runtime_doubles_and_does_not_start_isaac",
            "acceptance_covers_measure_tool_key_only",
            "native_tracking_root_drift_and_full_runtime_execution_remain_unadmitted",
        ],
    }
    return {**core, "adapter_review_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ToolKeyMetricsAdapterReviewError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--adapter-source", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--ik-adapter", type=Path, required=True)
    parser.add_argument("--ik-adapter-review", type=Path, required=True)
    parser.add_argument("--ik-source", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--mechanics-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review_adapter(
        _load(args.adapter),
        _load(args.readiness),
        _load(args.backend),
        _load(args.route),
        _load(args.ik_adapter),
        _load(args.ik_adapter_review),
        adapter_file_sha256=_file_sha(args.adapter),
        adapter_source_path=args.adapter_source,
        readiness_file_sha256=_file_sha(args.readiness),
        backend_file_sha256=_file_sha(args.backend),
        route_file_sha256=_file_sha(args.route),
        ik_adapter_file_sha256=_file_sha(args.ik_adapter),
        ik_review_file_sha256=_file_sha(args.ik_adapter_review),
        ik_source_file_sha256=_file_sha(args.ik_source),
        urdf_file_sha256=_file_sha(args.urdf),
        mechanics_source_file_sha256=_file_sha(args.mechanics_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
