"""Independently review the inert ARM-296 constructor-completeness receipt."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


REVIEW_SCHEMA = "tactevra.isaac_lm4_constructor_completeness_gate_review.v1"
GATE_SCHEMA = "tactevra.isaac_lm4_constructor_completeness_gate.v1"
EXPECTED_GATE_SOURCE_SHA256 = (
    "34475e61d669ac6764233311ba2ba11adaadd74bddd4ca320e5decd0935aa17d"
)
EXPECTED_ARM295_STATUS_SHA256 = (
    "7490b9e2bac3d3adf0146ca08e6a61a542bd4d8952329d68e8bfeb12970da1b8"
)
EXPECTED_CORRECTED_BINDING_SOURCE_SHA256 = (
    "2d93fe5647e3596fded4c3f8ba7e33f7c89a495f76fcf69620327588eb2d1fe7"
)


class ConstructorCompletenessGateReviewError(ValueError):
    """Raised when the ARM-296 gate source or receipt changes."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ConstructorCompletenessGateReviewError(
            "review input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ConstructorCompletenessGateReviewError(
            f"required input unavailable: {path}"
        ) from exc


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ConstructorCompletenessGateReviewError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise ConstructorCompletenessGateReviewError(f"{path} must contain an object")
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise ConstructorCompletenessGateReviewError(f"{label} hash changed")
    return claimed


def _static_review(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    forbidden = (
        "import isaacsim",
        "from isaacsim",
        "SimulationApp(",
        "import serial",
        "serial.Serial",
        "execute_backend(",
        "run_one_attempt(",
        ".step(",
    )
    if any(token in text for token in forbidden):
        raise ConstructorCompletenessGateReviewError(
            "gate source contains execution authority"
        )
    tree = ast.parse(text)
    gate = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "run_constructor_completeness_gate"
        ),
        None,
    )
    if gate is None:
        raise ConstructorCompletenessGateReviewError("gate function is absent")
    calls = {
        node.func.id
        for node in ast.walk(gate)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    required = {
        "_validate_arm295",
        "_build_solver_kwargs",
        "CorrectedRootRuntimeFactory",
    }
    if not required.issubset(calls):
        raise ConstructorCompletenessGateReviewError(
            "constructor-completeness call chain changed"
        )
    return {
        "forbidden_runtime_imports_absent": True,
        "backend_physics_and_hardware_calls_absent": True,
        "required_constructor_call_chain_present": sorted(required),
    }


def review_constructor_completeness_gate(
    receipt: Mapping[str, Any], *, gate_source: Path
) -> dict[str, Any]:
    """Validate source and receipt without reconstructing or executing runtime."""
    gate_hash = _require_hash(receipt, "gate_sha256", "ARM-296 gate")
    static_review = _static_review(gate_source)
    expected_components = {
        "clearance": "NativeClearanceRuntimeAdapter",
        "ik": "CanonicalIkRowRuntimeAdapter",
        "metrics": "ToolKeyMetricsRuntimeAdapter",
        "drift": "RootDriftRuntimeAdapter",
        "solver": "RoArmM3NumericalIk",
    }
    expected_inputs = [
        "board_T_world",
        "fixed_gripper_position",
        "gripper_bounds_rad",
        "hand_tcp_to_tip_z_mm",
        "joint_bounds_rad",
        "model",
        "options",
        "ready_arm_joint_positions",
    ]
    if (
        _file_sha(gate_source) != EXPECTED_GATE_SOURCE_SHA256
        or receipt.get("schema") != GATE_SCHEMA
        or receipt.get("status") != "PASS_CORRECTED_RUNTIME_CONSTRUCTOR_COMPLETENESS"
        or receipt.get("source_arm295_status_sha256") != EXPECTED_ARM295_STATUS_SHA256
        or receipt.get("source_corrected_binding_sha256")
        != EXPECTED_CORRECTED_BINDING_SOURCE_SHA256
        or receipt.get("former_failure_stage") != "construct_runtime"
        or receipt.get("former_failure_crossed") is not True
        or receipt.get("runtime_type") != "CompleteRuntimeComposition"
        or receipt.get("component_types") != expected_components
        or receipt.get("solver", {}).get("input_names") != expected_inputs
        or receipt.get("solver", {}).get("model_root_link") != "world"
        or receipt.get("solver", {}).get("board_transform_frames") != ["board", "world"]
        or receipt.get("shared_solver_identity_verified") is not True
        or receipt.get("baseline_reads") != {"key_view": 1, "root_view": 1}
        or receipt.get("protocol_calls") != {"articulation": [], "scene_query": []}
        or receipt.get("attempt_consumed") is not False
        or receipt.get("isaac_imported") is not False
        or receipt.get("isaac_started") is not False
        or receipt.get("scene_loaded") is not False
        or receipt.get("physics_steps") != 0
        or receipt.get("runtime_methods_called") != []
        or receipt.get("trajectory_playback") is not False
        or receipt.get("joint_targets_submitted") is not False
        or receipt.get("key_contact") is not False
        or receipt.get("automatic_retry") is not False
        or receipt.get("hardware_access") is not False
        or receipt.get("hardware_writes") != 0
        or receipt.get("physical_authority") is not False
        or receipt.get("physical_movements") != 0
    ):
        raise ConstructorCompletenessGateReviewError(
            "constructor-completeness receipt changed"
        )
    core = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm296-constructor-completeness-gate-review-001",
        "status": "ACCEPTED_CORRECTED_RUNTIME_CONSTRUCTOR_COMPLETENESS",
        "source_gate_sha256": gate_hash,
        "source_gate_source_sha256": EXPECTED_GATE_SOURCE_SHA256,
        "static_review": static_review,
        "former_arm295_constructor_failure_crossed": True,
        "production_solver_and_runtime_components_verified": True,
        "shared_solver_identity_verified": True,
        "attempt_consumed": False,
        "isaac_started": False,
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
        "next_required_stage": (
            "PLAN_NEW_SEPARATELY_AUTHORIZED_NOMINAL_ROUTE_SIMULATION_LINEAGE"
        ),
    }
    return {**core, "gate_review_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--gate-source", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    if args.output_directory.exists():
        raise ConstructorCompletenessGateReviewError(
            "review output exists; retry refused"
        )
    review = review_constructor_completeness_gate(
        _load(args.receipt), gate_source=args.gate_source
    )
    args.output_directory.mkdir(parents=True, exist_ok=False)
    (args.output_directory / "review.json").write_text(
        json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(review, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
