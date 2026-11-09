"""Independently review the ARM-269 read-only root drift adapter."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping


REVIEW_SCHEMA = "tactevra.isaac_lm4_root_drift_adapter_review.v1"
EXPECTED_ADAPTER_SHA256 = (
    "28c9fe7bf0b15d457d228281b6d9874499925214adf849d54d95b04c289fb499"
)
EXPECTED_ADAPTER_FILE_SHA256 = (
    "8c5ed1c2313c3dd5f906f35b1b1ba1028884eb8471c92cc8218fd647f509d25c"
)
EXPECTED_ADAPTER_SOURCE_SHA256 = (
    "2d0c94d74f1a9638bce5cb7de79c052323deed4314fbc5db8576cecb04f70434"
)


class RootDriftAdapterReviewError(ValueError):
    """Raised when the adapter or independent evidence changes."""


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
        raise RootDriftAdapterReviewError("input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise RootDriftAdapterReviewError(f"{label} hash changed")
    return claimed


def _import_adapter(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("arm269_reviewed_adapter", path)
    if spec is None or spec.loader is None:
        raise RootDriftAdapterReviewError("adapter source cannot be imported")
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
        raise RootDriftAdapterReviewError("forbidden runtime surface found")
    tree = ast.parse(text)
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    runtime = classes.get("RootDriftRuntimeAdapter")
    if runtime is None:
        raise RootDriftAdapterReviewError("runtime adapter class is absent")
    methods = {
        node.name: node for node in runtime.body if isinstance(node, ast.FunctionDef)
    }
    method = methods.get("root_drift")
    if method is None:
        raise RootDriftAdapterReviewError("root drift operation is absent")
    calls = {
        ast.unparse(node.func)
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
    }
    if "self._root_view.get_world_poses" not in calls:
        raise RootDriftAdapterReviewError("single native root pose read is absent")
    return {
        "forbidden_runtime_imports_absent": True,
        "joint_submission_calls_absent": True,
        "single_native_root_pose_read_present": True,
        "backend_execution_call_absent": True,
    }


class _Tensor:
    def __init__(self, value: Any) -> None:
        self._value = value

    def numpy(self) -> "_Tensor":
        return self

    def tolist(self) -> Any:
        return self._value


class _RootView:
    def __init__(self, position: list[float], orientation: list[float]) -> None:
        self.position = position
        self.orientation = orientation
        self.reads = 0

    def get_world_poses(self) -> tuple[_Tensor, _Tensor]:
        self.reads += 1
        return _Tensor([self.position]), _Tensor([self.orientation])


def _accepted_review(adapter: Any, definition: Mapping[str, Any]) -> dict[str, Any]:
    core = {
        "schema": adapter.ADAPTER_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "source_adapter_sha256": definition["adapter_sha256"],
        "runtime_integration_admitted": True,
    }
    return {**core, "adapter_review_sha256": adapter._sha(core)}


def _exercise_runtime(adapter: Any, definition: Mapping[str, Any]) -> dict[str, Any]:
    view = _RootView([0.00002, 0.0, 0.0], [-1.0, 0.0, 0.0, 0.0])
    runtime = adapter.RootDriftRuntimeAdapter(
        definition,
        adapter_review=_accepted_review(adapter, definition),
        root_view=view,
        expected_position_stage=[0.0, 0.0, 0.0],
        expected_quaternion_wxyz=[1.0, 0.0, 0.0, 0.0],
    )
    result = dict(runtime.root_drift())
    if (
        view.reads != 1
        or result.get("determinate") is not True
        or abs(result["translation_mm"] - 0.02) > 1e-12
        or result["rotation_deg"] != 0.0
    ):
        raise RootDriftAdapterReviewError("runtime root drift evidence changed")
    failing_view = _RootView([0.000051, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0])
    failing_runtime = adapter.RootDriftRuntimeAdapter(
        definition,
        adapter_review=_accepted_review(adapter, definition),
        root_view=failing_view,
        expected_position_stage=[0.0, 0.0, 0.0],
        expected_quaternion_wxyz=[1.0, 0.0, 0.0, 0.0],
    )
    try:
        failing_runtime.root_drift()
    except adapter.RootDriftAdapterError:
        pass
    else:
        raise RootDriftAdapterReviewError("out-of-tolerance drift did not fail closed")
    return result


def review_adapter(
    definition: Mapping[str, Any],
    readiness: Mapping[str, Any],
    backend: Mapping[str, Any],
    metrics_adapter: Mapping[str, Any],
    metrics_review: Mapping[str, Any],
    *,
    adapter_file_sha256: str,
    adapter_source_path: Path,
    readiness_file_sha256: str,
    backend_file_sha256: str,
    metrics_adapter_file_sha256: str,
    metrics_review_file_sha256: str,
    mechanics_source_file_sha256: str,
) -> dict[str, Any]:
    adapter_hash = _require_hash(definition, "adapter_sha256", "ARM-269 adapter")
    source_sha = _file_sha(adapter_source_path)
    if (
        adapter_hash != EXPECTED_ADAPTER_SHA256
        or adapter_file_sha256 != EXPECTED_ADAPTER_FILE_SHA256
        or source_sha != EXPECTED_ADAPTER_SOURCE_SHA256
    ):
        raise RootDriftAdapterReviewError("adapter review boundary changed")
    adapter = _import_adapter(adapter_source_path)
    reproduced = adapter.build_adapter_definition(
        readiness,
        backend,
        metrics_adapter,
        metrics_review,
        readiness_file_sha256=readiness_file_sha256,
        backend_file_sha256=backend_file_sha256,
        metrics_adapter_file_sha256=metrics_adapter_file_sha256,
        metrics_review_file_sha256=metrics_review_file_sha256,
        mechanics_source_file_sha256=mechanics_source_file_sha256,
        adapter_source_file_sha256=source_sha,
    )
    if reproduced != definition:
        raise RootDriftAdapterReviewError("adapter definition did not reproduce")
    source_review = _review_source(adapter_source_path.read_bytes())
    runtime_evidence = _exercise_runtime(adapter, definition)
    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm269-root-drift-adapter-review-001",
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "source_adapter_sha256": adapter_hash,
        "source_adapter_file_sha256": adapter_file_sha256,
        "source_adapter_source_sha256": source_sha,
        "definition_reproduced": True,
        "source_call_surface_reviewed": True,
        "offline_terminal_root_drift_verified": True,
        "out_of_tolerance_failure_verified": True,
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
        "next_required_stage": "PREPARE_AND_REVIEW_COMPLETE_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "limitations": [
            "review_uses_non_runtime_doubles_and_does_not_start_isaac",
            "acceptance_covers_root_drift_only",
            "complete_runtime_composition_and_execution_remain_unadmitted",
        ],
    }
    return {**core, "adapter_review_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise RootDriftAdapterReviewError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--adapter-source", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--metrics-adapter", type=Path, required=True)
    parser.add_argument("--metrics-review", type=Path, required=True)
    parser.add_argument("--mechanics-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review_adapter(
        _load(args.adapter),
        _load(args.readiness),
        _load(args.backend),
        _load(args.metrics_adapter),
        _load(args.metrics_review),
        adapter_file_sha256=_file_sha(args.adapter),
        adapter_source_path=args.adapter_source,
        readiness_file_sha256=_file_sha(args.readiness),
        backend_file_sha256=_file_sha(args.backend),
        metrics_adapter_file_sha256=_file_sha(args.metrics_adapter),
        metrics_review_file_sha256=_file_sha(args.metrics_review),
        mechanics_source_file_sha256=_file_sha(args.mechanics_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
