"""Independently review the ARM-265 native-clearance composition adapter.

This review reopens the exact definition and sources, reproduces the definition,
inspects the Python call surface, and exercises the composition with non-Isaac
test doubles.  Acceptance admits later zero-authority runtime composition only;
it never admits an Isaac launch, governed attempt, or physical motion.
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


REVIEW_SCHEMA = "tactevra.isaac_lm4_native_clearance_adapter_review.v1"
ADAPTER_SCHEMA = "tactevra.isaac_lm4_native_clearance_adapter.v1"
EXPECTED_ADAPTER_SHA256 = (
    "e5fb18e441e4ac97ee571a2399a55d441fcb149c9e6d6c766cbc660988aa4634"
)
EXPECTED_ADAPTER_FILE_SHA256 = (
    "b5e8891053531cd799e6367b4ff24140c268757e4a57a3a19691fc48d1e76df4"
)
EXPECTED_ADAPTER_SOURCE_SHA256 = (
    "0c585fbfa28de5e91ea59bb1963338560a193b220ea3499db9abfac93f30dd19"
)


class NativeClearanceAdapterReviewError(ValueError):
    """Raised when the ARM-265 adapter cannot be independently accepted."""


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
        raise NativeClearanceAdapterReviewError("review input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeClearanceAdapterReviewError(f"{path} must contain an object")
    return value


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeClearanceAdapterReviewError(f"{label} hash changed")
    return claimed


def _review_source(source: bytes) -> None:
    try:
        tree = ast.parse(source.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise NativeClearanceAdapterReviewError("adapter source is not reviewable Python") from exc
    imports: set[str] = set()
    classes: dict[str, set[str]] = {}
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.ClassDef):
            classes[node.name] = {
                child.name for child in node.body if isinstance(child, ast.FunctionDef)
            }
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id)
    if any(name.startswith(("isaacsim", "serial")) for name in imports):
        raise NativeClearanceAdapterReviewError("adapter imports a forbidden runtime")
    if not {"__init__", "check_continuous_clearance"}.issubset(
        classes.get("NativeClearanceRuntimeAdapter", set())
    ):
        raise NativeClearanceAdapterReviewError("adapter method surface changed")
    if not {
        "NativeIsaacConservativeSweepBinding",
        "check_continuous_clearance",
    }.issubset(calls):
        raise NativeClearanceAdapterReviewError("adapter composition calls changed")
    text = source.decode("utf-8")
    if "SimulationApp(" in text or "execute_backend(" in text:
        raise NativeClearanceAdapterReviewError("adapter contains launch authority")


def _import_adapter(path: Path):
    integration = str(path.parent)
    if integration not in sys.path:
        sys.path.insert(0, integration)
    spec = importlib.util.spec_from_file_location("arm265_adapter_under_review", path)
    if spec is None or spec.loader is None:
        raise NativeClearanceAdapterReviewError("adapter source cannot be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Array:
    def __init__(self, value: object) -> None:
        self.value = value

    def numpy(self) -> "_Array":
        return self

    def tolist(self) -> object:
        return self.value


class _View:
    def __init__(self, articulation: "_Articulation") -> None:
        self.articulation = articulation

    def get_link_transforms(self) -> _Array:
        offset = self.articulation.positions[0] if self.articulation.positions else 0.0
        return _Array(
            [[
                [offset + index * 10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
                for index in range(7)
            ]]
        )


class _Articulation:
    dof_names = (
        "base_link_to_link1",
        "link1_to_link2",
        "link2_to_link3",
        "link3_to_link4",
        "link4_to_link5",
        "link5_to_gripper_link",
    )
    link_names = ("base_link", "link1", "link2", "link3", "link4", "link5", "gripper_link")

    def __init__(self) -> None:
        self.positions: list[float] = []
        self._physics_articulation_view = _View(self)

    def set_dof_positions(self, rows: list[list[float]]) -> None:
        self.positions = list(rows[0])


class _Query:
    def __init__(self, first_sweep_blocked: bool = False) -> None:
        self.first_sweep_blocked = first_sweep_blocked
        self.sweeps = 0

    def overlap_sphere_any(self, *args: object) -> bool:
        return False

    def sweep_sphere_any(self, *args: object) -> bool:
        self.sweeps += 1
        return self.first_sweep_blocked and self.sweeps == 1


def review_adapter(
    adapter: Mapping[str, Any],
    preflight: Mapping[str, Any],
    binding: Mapping[str, Any],
    binding_review: Mapping[str, Any],
    *,
    adapter_file_sha256: str,
    adapter_source_path: Path,
    preflight_file_sha256: str,
    binding_file_sha256: str,
    binding_review_file_sha256: str,
    proof_source_file_sha256: str,
    binding_source_file_sha256: str,
) -> dict[str, Any]:
    adapter_hash = _require_hash(adapter, "adapter_sha256", "ARM-265 adapter")
    if (
        adapter.get("schema") != ADAPTER_SCHEMA
        or adapter.get("status") != "READY_FOR_INDEPENDENT_NATIVE_CLEARANCE_ADAPTER_REVIEW"
        or adapter_hash != EXPECTED_ADAPTER_SHA256
        or adapter_file_sha256 != EXPECTED_ADAPTER_FILE_SHA256
        or _file_sha(adapter_source_path) != EXPECTED_ADAPTER_SOURCE_SHA256
        or adapter.get("adapter_implemented") is not True
        or adapter.get("adapter_review_admitted") is not False
        or adapter.get("integration_execution_admitted") is not False
        or adapter.get("launch_admitted") is not False
        or adapter.get("attempt_consumed") is not False
        or adapter.get("environment_only_scene_required") is not True
        or adapter.get("robot_collision_query_shapes_enabled") is not False
        or adapter.get("clearance_margin_mm") != 0.5
        or adapter.get("maximum_subdivision_depth") != 12
        or len(adapter.get("accepted_exclusion_pairs", [])) != 6
    ):
        raise NativeClearanceAdapterReviewError("adapter artifact boundary changed")
    _review_source(adapter_source_path.read_bytes())
    module = _import_adapter(adapter_source_path)
    reproduced = module.build_adapter_definition(
        preflight,
        binding,
        binding_review,
        preflight_file_sha256=preflight_file_sha256,
        binding_file_sha256=binding_file_sha256,
        binding_review_file_sha256=binding_review_file_sha256,
        proof_source_file_sha256=proof_source_file_sha256,
        binding_source_file_sha256=binding_source_file_sha256,
        adapter_source_file_sha256=EXPECTED_ADAPTER_SOURCE_SHA256,
    )
    if reproduced != adapter:
        raise NativeClearanceAdapterReviewError("adapter definition did not reproduce")
    provisional_core = {
        "schema": REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "source_adapter_sha256": adapter_hash,
        "runtime_integration_admitted": True,
        "launch_admitted": False,
        "attempt_consumed": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    provisional = {
        **provisional_core,
        "adapter_review_sha256": module._sha(provisional_core),
    }
    query = _Query(first_sweep_blocked=True)
    runtime = module.NativeClearanceRuntimeAdapter(
        adapter,
        adapter_review=provisional,
        binding_definition=binding,
        binding_review=binding_review,
        articulation=_Articulation(),
        scene_query=query,
        environment_only_scene=True,
        robot_collision_query_shapes_enabled=False,
    )
    evidence = runtime.check_continuous_clearance(
        start_sequence=20,
        end_sequence=21,
        start_joint_targets_rad=[0.0] * 6,
        end_joint_targets_rad=[0.001] * 6,
    )
    if (
        evidence.get("continuous") is not True
        or evidence.get("determinate") is not True
        or evidence.get("minimum_clearance_mm") != 0.5
        or evidence.get("intervals_inspected") != 3
        or query.sweeps < 3
    ):
        raise NativeClearanceAdapterReviewError("runtime composition evidence changed")
    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm265-native-clearance-adapter-review-001",
        "status": "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "source_adapter_sha256": adapter_hash,
        "source_files_sha256": {
            "arm265_adapter": adapter_file_sha256,
            "arm265_adapter_source": EXPECTED_ADAPTER_SOURCE_SHA256,
            "arm264_preflight": preflight_file_sha256,
            "arm262_binding": binding_file_sha256,
            "arm263_binding_review": binding_review_file_sha256,
            "arm257_proof_source": proof_source_file_sha256,
            "arm262_binding_source": binding_source_file_sha256,
        },
        "definition_reproduced": True,
        "source_call_surface_reviewed": True,
        "non_isaac_runtime_composition_verified": True,
        "recursive_refinement_verified": True,
        "environment_only_scene_enforced": True,
        "exact_exclusion_policy_enforced": True,
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
        "next_required_stage": "PREPARE_ZERO_AUTHORITY_NOMINAL_ROUTE_RUNTIME_COMPOSITION",
        "limitations": [
            "review_uses_non_isaac_test_doubles_only",
            "canonical_ik_tool_key_metrics_and_root_drift_remain_separate_dependencies",
            "no_launch_attempt_hardware_or_physical_authority_is_granted",
        ],
    }
    return {**core, "adapter_review_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--adapter-source", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--binding-review", type=Path, required=True)
    parser.add_argument("--proof-source", type=Path, required=True)
    parser.add_argument("--binding-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review_adapter(
        _load(args.adapter),
        _load(args.preflight),
        _load(args.binding),
        _load(args.binding_review),
        adapter_file_sha256=_file_sha(args.adapter),
        adapter_source_path=args.adapter_source,
        preflight_file_sha256=_file_sha(args.preflight),
        binding_file_sha256=_file_sha(args.binding),
        binding_review_file_sha256=_file_sha(args.binding_review),
        proof_source_file_sha256=_file_sha(args.proof_source),
        binding_source_file_sha256=_file_sha(args.binding_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
