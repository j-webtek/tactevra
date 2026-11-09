"""Independently review the ARM-267 canonical IK row adapter.

The reviewer reproduces the definition, inspects the exact source operation
surface, and exercises FK-to-IK row regeneration with non-runtime doubles.  It
does not import Isaac, construct the production solver, or consume an attempt.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


REVIEW_SCHEMA = "tactevra.isaac_lm4_canonical_ik_row_adapter_review.v1"
EXPECTED_ADAPTER_SHA256 = (
    "0c6b35d2392604687bc52bf723b9422967cc9631c5e33557a56cf7f2c5e4829a"
)
EXPECTED_ADAPTER_FILE_SHA256 = (
    "b3e799c4964bec898772730502f3c81cf22f9e0ded7447f76d21b6a284786f1a"
)
EXPECTED_ADAPTER_SOURCE_SHA256 = (
    "bc23965c0d7bfef801d7427bece37a72fb4daed0a9916338edc35008b4d1f9b1"
)


class CanonicalIkRowAdapterReviewError(ValueError):
    """Raised when the adapter or its review evidence changes."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanonicalIkRowAdapterReviewError("input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise CanonicalIkRowAdapterReviewError(f"{label} hash changed")
    return claimed


def _import_adapter(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("arm267_reviewed_adapter", path)
    if spec is None or spec.loader is None:
        raise CanonicalIkRowAdapterReviewError("adapter source cannot be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _review_source(payload: bytes) -> dict[str, bool]:
    text = payload.decode("utf-8")
    if any(
        token in text
        for token in (
            "import isaacsim", "from isaacsim", "SimulationApp(",
            "import serial", "execute_backend(",
        )
    ):
        raise CanonicalIkRowAdapterReviewError("forbidden runtime surface found")
    tree = ast.parse(text)
    classes = {
        node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
    }
    runtime = classes.get("CanonicalIkRowRuntimeAdapter")
    if runtime is None:
        raise CanonicalIkRowAdapterReviewError("runtime adapter class is absent")
    methods = {
        node.name: node for node in runtime.body if isinstance(node, ast.FunctionDef)
    }
    method = methods.get("regenerate_row")
    if method is None:
        raise CanonicalIkRowAdapterReviewError("regenerate_row is absent")
    calls = {
        ast.unparse(node.func)
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
    }
    required = {
        "self._solver.model.forward_kinematics",
        "self._solver.solve",
        "BoardToolTipTarget",
    }
    if not required.issubset(calls):
        raise CanonicalIkRowAdapterReviewError("FK-to-canonical-IK call surface changed")
    return {
        "forbidden_runtime_imports_absent": True,
        "source_fk_call_present": True,
        "canonical_solver_call_present": True,
        "backend_execution_call_absent": True,
    }


class _Joint:
    def __init__(self, value: float) -> None:
        self.value = float(value)

    @classmethod
    def radians(cls, value: float) -> "_Joint":
        return cls(value)


class _Point:
    def __init__(self, frame: str, x: float, y: float, z: float) -> None:
        self.frame, self.x, self.y, self.z = frame, x, y, z


class _Vec:
    def __init__(self, x: float, y: float, z: float) -> None:
        self.x, self.y, self.z = x, y, z


class _Rotation:
    @staticmethod
    def identity() -> "_Rotation":
        return _Rotation()


class _Transform:
    def __init__(self, *args: Any, translation_mm: Any = None, **_kwargs: Any) -> None:
        self.parent_frame = args[0] if args else "board"
        if translation_mm is not None:
            self.translation_mm = translation_mm
        elif len(args) >= 4:
            self.translation_mm = args[3]
        else:
            self.translation_mm = _Vec(0.0, 0.0, 0.0)

    def compose(self, other: "_Transform") -> "_Transform":
        left, right = self.translation_mm, other.translation_mm
        return _Transform(
            self.parent_frame, translation_mm=_Vec(
                left.x + right.x, left.y + right.y, left.z + right.z
            )
        )


class _Target:
    def __init__(self, position_mm: _Point) -> None:
        self.position_mm = position_mm


class _Model:
    def forward_kinematics(self, state: Mapping[str, _Joint]) -> dict[str, _Transform]:
        if len(state) != 6:
            raise AssertionError("review state did not contain six joints")
        return {"hand_tcp": _Transform("world", translation_mm=_Vec(10, 20, 30))}


class _Solver:
    def __init__(self) -> None:
        self.model = _Model()
        self.board_T_world = _Transform("board")
        self.hand_tcp_to_tip_z_mm = -5.0
        self.fixed_gripper_position = _Joint(0.25)

    def solve(self, target: _Target, *, seed_joint_positions: Any) -> Any:
        if (target.position_mm.x, target.position_mm.y, target.position_mm.z) != (10, 20, 25):
            raise AssertionError("review target did not preserve source FK pose")
        seed = seed_joint_positions[0]
        if [seed[name].value for name in (
            "base_link_to_link1", "link1_to_link2", "link2_to_link3",
            "link3_to_link4", "link4_to_link5",
        )] != [0.0, 0.1, 0.2, 0.3, 0.4]:
            raise AssertionError("previous row was not the first seed")
        names = (
            "base_link_to_link1", "link1_to_link2", "link2_to_link3",
            "link3_to_link4", "link4_to_link5",
        )
        return SimpleNamespace(
            converged=True,
            solution_arm_joint_positions=tuple(
                SimpleNamespace(name=name, position=_Joint(index / 10))
                for index, name in enumerate(names)
            ),
            residual=SimpleNamespace(position_error_mm=0.001),
        )


def _exercise_runtime(adapter: Any, definition: Mapping[str, Any]) -> dict[str, Any]:
    adapter._runtime_types = lambda: (
        _Joint, _Point, _Transform, _Rotation, _Vec, _Target, "hand_tcp", _Solver
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
    review = {**review_core, "adapter_review_sha256": adapter._sha(review_core)}
    runtime = adapter.CanonicalIkRowRuntimeAdapter(
        definition, adapter_review=review, solver=_Solver()
    )
    result = runtime.regenerate_row(
        source_row={
            "sequence": 654,
            "phase": "TRANSIT",
            "joint_position_target_rad": [0.5, 0.6, 0.7, 0.8, 0.9, 0.25],
        },
        previous_joint_targets_rad=[0.0, 0.1, 0.2, 0.3, 0.4, 0.25],
    )
    if result != {
        "sequence": 654,
        "accepted": True,
        "determinate": True,
        "joint_position_target_rad": [0.0, 0.1, 0.2, 0.3, 0.4, 0.25],
        "position_error_mm": 0.001,
    }:
        raise CanonicalIkRowAdapterReviewError("runtime row evidence changed")
    return result


def review_adapter(
    definition: Mapping[str, Any],
    readiness: Mapping[str, Any],
    backend: Mapping[str, Any],
    route: Mapping[str, Any],
    *,
    adapter_file_sha256: str,
    adapter_source_path: Path,
    readiness_file_sha256: str,
    backend_file_sha256: str,
    route_file_sha256: str,
    ik_source_file_sha256: str,
    urdf_file_sha256: str,
) -> dict[str, Any]:
    adapter_hash = _require_hash(definition, "adapter_sha256", "ARM-267 adapter")
    source_sha = _file_sha(adapter_source_path)
    if (
        adapter_hash != EXPECTED_ADAPTER_SHA256
        or adapter_file_sha256 != EXPECTED_ADAPTER_FILE_SHA256
        or source_sha != EXPECTED_ADAPTER_SOURCE_SHA256
    ):
        raise CanonicalIkRowAdapterReviewError("adapter review boundary changed")
    adapter = _import_adapter(adapter_source_path)
    reproduced = adapter.build_adapter_definition(
        readiness, backend, route,
        readiness_file_sha256=readiness_file_sha256,
        backend_file_sha256=backend_file_sha256,
        route_file_sha256=route_file_sha256,
        ik_source_file_sha256=ik_source_file_sha256,
        urdf_file_sha256=urdf_file_sha256,
        adapter_source_file_sha256=source_sha,
    )
    if reproduced != definition:
        raise CanonicalIkRowAdapterReviewError("adapter definition did not reproduce")
    source_review = _review_source(adapter_source_path.read_bytes())
    runtime_evidence = _exercise_runtime(adapter, definition)
    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm267-canonical-ik-row-adapter-review-001",
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "source_adapter_sha256": adapter_hash,
        "source_adapter_file_sha256": adapter_file_sha256,
        "source_adapter_source_sha256": source_sha,
        "definition_reproduced": True,
        "source_call_surface_reviewed": True,
        "offline_fk_to_ik_composition_verified": True,
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
        "next_required_stage": "IMPLEMENT_AND_REVIEW_TOOL_KEY_METRICS_ADAPTER",
        "limitations": [
            "review_uses_non_runtime_doubles_and_does_not_run_production_ik",
            "acceptance_covers_regenerate_row_only",
            "full_runtime_composition_and_backend_execution_remain_unadmitted",
        ],
    }
    return {**core, "adapter_review_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise CanonicalIkRowAdapterReviewError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--adapter-source", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--ik-source", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review_adapter(
        _load(args.adapter), _load(args.readiness), _load(args.backend),
        _load(args.route), adapter_file_sha256=_file_sha(args.adapter),
        adapter_source_path=args.adapter_source,
        readiness_file_sha256=_file_sha(args.readiness),
        backend_file_sha256=_file_sha(args.backend),
        route_file_sha256=_file_sha(args.route),
        ik_source_file_sha256=_file_sha(args.ik_source),
        urdf_file_sha256=_file_sha(args.urdf),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
