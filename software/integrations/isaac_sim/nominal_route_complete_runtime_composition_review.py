"""Independently review the ARM-270 complete runtime composition."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping


REVIEW_SCHEMA = "tactevra.isaac_lm4_complete_runtime_composition_review.v1"
EXPECTED_COMPOSITION_SHA256 = (
    "05b0bc6e8c63022fcecde6fab02302de0abd63432084a6e84fe8e6c916ed2d19"
)
EXPECTED_COMPOSITION_FILE_SHA256 = (
    "7d091f477dc1986b505693cbf8faed0d27cebd605860520f29e3535f6b15aa32"
)
EXPECTED_COMPOSITION_SOURCE_SHA256 = (
    "a1d8813ae9bdb032eed21e399cab263effbcc32b8786d64836170cb562e95b4b"
)


class CompleteRuntimeCompositionReviewError(ValueError):
    """Raised when composition evidence or its reviewed surface changes."""


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
        raise CompleteRuntimeCompositionReviewError(
            "input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise CompleteRuntimeCompositionReviewError(f"{label} hash changed")
    return claimed


def _import_composition(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("arm270_reviewed_composition", path)
    if spec is None or spec.loader is None:
        raise CompleteRuntimeCompositionReviewError(
            "composition source cannot be imported"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _review_source(payload: bytes) -> dict[str, Any]:
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
        raise CompleteRuntimeCompositionReviewError("forbidden execution surface found")
    tree = ast.parse(text)
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    runtime = classes.get("CompleteRuntimeComposition")
    if runtime is None:
        raise CompleteRuntimeCompositionReviewError("composition class is absent")
    methods = {
        node.name: node for node in runtime.body if isinstance(node, ast.FunctionDef)
    }
    expected = {
        "regenerate_row": "self._ik.regenerate_row",
        "check_continuous_clearance": "self._clearance.check_continuous_clearance",
        "measure_tool_key": "self._metrics.measure_tool_key",
        "root_drift": "self._drift.root_drift",
    }
    observed: dict[str, str] = {}
    for method_name, call_name in expected.items():
        method = methods.get(method_name)
        if method is None:
            raise CompleteRuntimeCompositionReviewError(f"{method_name} is absent")
        calls = [
            ast.unparse(node.func)
            for node in ast.walk(method)
            if isinstance(node, ast.Call)
        ]
        if calls.count(call_name) != 1 or len(calls) != 1:
            raise CompleteRuntimeCompositionReviewError(
                f"{method_name} delegation changed"
            )
        observed[method_name] = call_name
    return {
        "forbidden_runtime_imports_absent": True,
        "backend_execution_call_absent": True,
        "joint_submission_calls_absent": True,
        "one_to_one_delegation": observed,
    }


class _Recorder:
    def __init__(self, result: Mapping[str, Any]) -> None:
        self.result = dict(result)
        self.calls: list[dict[str, Any]] = []

    def invoke(self, **kwargs: Any) -> Mapping[str, Any]:
        self.calls.append(kwargs)
        return dict(self.result)


def _component(class_name: str, method_name: str, recorder: _Recorder) -> Any:
    def delegated(self: Any, **kwargs: Any) -> Mapping[str, Any]:
        return self.recorder.invoke(**kwargs)

    component_type = type(class_name, (), {method_name: delegated})
    instance = component_type()
    instance.recorder = recorder
    return instance


def _accepted_review(composition: Any, definition: Mapping[str, Any]) -> dict[str, Any]:
    core = {
        "schema": composition.COMPOSITION_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_CONSTRUCTION",
        "source_composition_sha256": definition["composition_sha256"],
        "runtime_construction_admitted": True,
    }
    return {**core, "composition_review_sha256": composition._sha(core)}


def _exercise_composition(
    composition: Any, definition: Mapping[str, Any]
) -> dict[str, Any]:
    recorders = {
        "clearance": _Recorder({"continuous": True}),
        "ik": _Recorder({"accepted": True}),
        "metrics": _Recorder({"determinate": True}),
        "drift": _Recorder({"translation_mm": 0.0}),
    }
    components = {
        name: _component(spec["class"], spec["method"], recorders[name])
        for name, spec in composition.COMPONENTS.items()
    }
    runtime = composition.CompleteRuntimeComposition(
        definition,
        composition_review=_accepted_review(composition, definition),
        **components,
    )
    row = {"sequence": 654}
    previous = [0.0] * 6
    ik_result = runtime.regenerate_row(
        source_row=row, previous_joint_targets_rad=previous
    )
    clearance_result = runtime.check_continuous_clearance(
        start_sequence=653,
        end_sequence=654,
        start_joint_targets_rad=previous,
        end_joint_targets_rad=[0.01] * 6,
    )
    metrics_result = runtime.measure_tool_key(
        sequence=654, joint_targets_rad=[0.01] * 6, phase="TRANSIT"
    )
    drift_result = runtime.root_drift()
    if (
        ik_result != {"accepted": True}
        or clearance_result != {"continuous": True}
        or metrics_result != {"determinate": True}
        or drift_result != {"translation_mm": 0.0}
        or any(len(recorder.calls) != 1 for recorder in recorders.values())
        or recorders["ik"].calls[0]
        != {"source_row": row, "previous_joint_targets_rad": previous}
        or recorders["drift"].calls[0] != {}
    ):
        raise CompleteRuntimeCompositionReviewError("delegation evidence changed")
    return {
        "all_four_methods_delegated": True,
        "each_component_called_once": True,
        "arguments_preserved": True,
        "results_preserved": True,
    }


def review_composition(
    definition: Mapping[str, Any],
    backend: Mapping[str, Any],
    component_documents: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any]]],
    *,
    composition_file_sha256: str,
    composition_source_path: Path,
    backend_file_sha256: str,
    component_file_sha256: Mapping[str, Mapping[str, str]],
    component_source_sha256: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    composition_hash = _require_hash(
        definition, "composition_sha256", "ARM-270 composition"
    )
    source_sha = _file_sha(composition_source_path)
    if (
        composition_hash != EXPECTED_COMPOSITION_SHA256
        or composition_file_sha256 != EXPECTED_COMPOSITION_FILE_SHA256
        or source_sha != EXPECTED_COMPOSITION_SOURCE_SHA256
    ):
        raise CompleteRuntimeCompositionReviewError(
            "composition review boundary changed"
        )
    composition = _import_composition(composition_source_path)
    reproduced = composition.build_composition_definition(
        backend,
        component_documents,
        backend_file_sha256=backend_file_sha256,
        component_file_sha256=component_file_sha256,
        component_source_sha256=component_source_sha256,
        composition_source_file_sha256=source_sha,
    )
    if reproduced != definition:
        raise CompleteRuntimeCompositionReviewError("composition did not reproduce")
    source_review = _review_source(composition_source_path.read_bytes())
    delegation_evidence = _exercise_composition(composition, definition)
    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm270-complete-runtime-composition-review-001",
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_CONSTRUCTION",
        "source_composition_sha256": composition_hash,
        "source_composition_file_sha256": composition_file_sha256,
        "source_composition_source_sha256": source_sha,
        "definition_reproduced": True,
        "source_call_surface_reviewed": True,
        "complete_protocol_delegation_verified": True,
        "delegation_evidence": delegation_evidence,
        "source_review": source_review,
        "runtime_construction_admitted": True,
        "backend_execution_admitted": False,
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
        "next_required_stage": "PREPARE_AND_REVIEW_ZERO_AUTHORITY_NATIVE_RUNTIME_CONSTRUCTION",
        "limitations": [
            "review_uses_non_runtime_doubles_and_does_not_start_isaac",
            "acceptance_covers_delegation_and_lineage_not_native_object_construction",
            "backend_execution_and_any_simulation_attempt_remain_unadmitted",
        ],
    }
    return {**core, "composition_review_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise CompleteRuntimeCompositionReviewError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--composition", type=Path, required=True)
    parser.add_argument("--composition-source", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    names = ("clearance", "ik", "metrics", "drift")
    for name in names:
        parser.add_argument(f"--{name}-adapter", type=Path, required=True)
        parser.add_argument(f"--{name}-review", type=Path, required=True)
        parser.add_argument(f"--{name}-adapter-source", type=Path, required=True)
        parser.add_argument(f"--{name}-review-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    documents = {
        name: (
            _load(getattr(args, f"{name}_adapter")),
            _load(getattr(args, f"{name}_review")),
        )
        for name in names
    }
    files = {
        name: {
            "adapter": _file_sha(getattr(args, f"{name}_adapter")),
            "review": _file_sha(getattr(args, f"{name}_review")),
        }
        for name in names
    }
    sources = {
        name: {
            "adapter": _file_sha(getattr(args, f"{name}_adapter_source")),
            "review": _file_sha(getattr(args, f"{name}_review_source")),
        }
        for name in names
    }
    result = review_composition(
        _load(args.composition),
        _load(args.backend),
        documents,
        composition_file_sha256=_file_sha(args.composition),
        composition_source_path=args.composition_source,
        backend_file_sha256=_file_sha(args.backend),
        component_file_sha256=files,
        component_source_sha256=sources,
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
