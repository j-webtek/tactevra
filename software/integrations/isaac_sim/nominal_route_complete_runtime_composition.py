"""Compose all four reviewed ARM-255 runtime methods without executing them.

ARM-270 binds the accepted clearance, IK, tool/key, and root-drift adapters
behind the exact protocol consumed by the deterministic backend.  The module
does not import Isaac, start a simulator, construct native objects, or call the
backend.  Runtime components must be constructed separately from their own
accepted definitions and reviews.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


COMPOSITION_SCHEMA = "tactevra.isaac_lm4_complete_runtime_composition.v1"
COMPOSITION_REVIEW_SCHEMA = "tactevra.isaac_lm4_complete_runtime_composition_review.v1"
BACKEND_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_backend.v1"

COMPONENTS = {
    "clearance": {
        "adapter_schema": "tactevra.isaac_lm4_native_clearance_adapter.v1",
        "review_schema": "tactevra.isaac_lm4_native_clearance_adapter_review.v1",
        "method": "check_continuous_clearance",
        "class": "NativeClearanceRuntimeAdapter",
        "adapter_hash": "e5fb18e441e4ac97ee571a2399a55d441fcb149c9e6d6c766cbc660988aa4634",
        "review_hash": "f83cd6b50c6dc93ed37ea4743bc50174e97e1a498a71b8b08c98969011d44243",
        "adapter_file": "b5e8891053531cd799e6367b4ff24140c268757e4a57a3a19691fc48d1e76df4",
        "review_file": "1ababaac40fc50840f31aa921e3d3b00514cb4416e6c92190bc51095b4381b13",
        "adapter_source": "0c585fbfa28de5e91ea59bb1963338560a193b220ea3499db9abfac93f30dd19",
        "review_source": "7ed79804f6ef29c288a78bfab8eaedbfac026006795814bc68edcc2f2984b979",
    },
    "ik": {
        "adapter_schema": "tactevra.isaac_lm4_canonical_ik_row_adapter.v1",
        "review_schema": "tactevra.isaac_lm4_canonical_ik_row_adapter_review.v1",
        "method": "regenerate_row",
        "class": "CanonicalIkRowRuntimeAdapter",
        "adapter_hash": "0c6b35d2392604687bc52bf723b9422967cc9631c5e33557a56cf7f2c5e4829a",
        "review_hash": "45ab4fde0d228893b0adc3e2c25ccb7ac15939742f24712c0b31e358ca41592a",
        "adapter_file": "b3e799c4964bec898772730502f3c81cf22f9e0ded7447f76d21b6a284786f1a",
        "review_file": "cb61e4005777e0f75556fb238b18608be029375da2b4b11a1be75b0da74fe42f",
        "adapter_source": "bc23965c0d7bfef801d7427bece37a72fb4daed0a9916338edc35008b4d1f9b1",
        "review_source": "eed3d2e873eae658f2b2a1dbec7f98fc5469eb224969fe35e57891a3963df120",
    },
    "metrics": {
        "adapter_schema": "tactevra.isaac_lm4_tool_key_metrics_adapter.v1",
        "review_schema": "tactevra.isaac_lm4_tool_key_metrics_adapter_review.v1",
        "method": "measure_tool_key",
        "class": "ToolKeyMetricsRuntimeAdapter",
        "adapter_hash": "5b2327498efe78ced7d7c5ef88db170f0596d59b83a22a56df5e8b5f60493f19",
        "review_hash": "53d25636a6a26778a51b57ae05468fe890f8eaec4f908b34101367972ce92517",
        "adapter_file": "e4b059e0fc78343eda7959c2e97ac66565db93fe859e8a0dc0e5591eee8e41da",
        "review_file": "3077bc83c25f8cd491ace003469e6add6d275a8de79894a70f8344a2256167a7",
        "adapter_source": "b7555a1414b4431ad92ebefb9a6ffb8f18a3e6d763ce4e73e6f7747c4474be6b",
        "review_source": "f32d1d5606329067561fd1cf7c17a8a96d6d06429f773deb80c8f5ba7e70b2c1",
    },
    "drift": {
        "adapter_schema": "tactevra.isaac_lm4_root_drift_adapter.v1",
        "review_schema": "tactevra.isaac_lm4_root_drift_adapter_review.v1",
        "method": "root_drift",
        "class": "RootDriftRuntimeAdapter",
        "adapter_hash": "28c9fe7bf0b15d457d228281b6d9874499925214adf849d54d95b04c289fb499",
        "review_hash": "073a708c257604d8e80589303a658a83370e3fb045b7016dd23f8a1b93d63864",
        "adapter_file": "8c5ed1c2313c3dd5f906f35b1b1ba1028884eb8471c92cc8218fd647f509d25c",
        "review_file": "8490cb9d97a2d13a38181e863d915373ee626bf5e0418212e1f314026e735480",
        "adapter_source": "2d0c94d74f1a9638bce5cb7de79c052323deed4314fbc5db8576cecb04f70434",
        "review_source": "1866f7d88d6de80c1e467307656cd5531c53d268eaaed55dea40791ddbb63ec4",
    },
}

EXPECTED_BACKEND_SHA256 = (
    "132f1e028503a3a83af11f2a713f839e00e1fef49aa9cb3fbb0156f858245cde"
)
EXPECTED_BACKEND_FILE_SHA256 = (
    "968140c9b075cc4f6a8d5599edc765cd1b6cde734e32e6632513bd2c94fb6228"
)


class CompleteRuntimeCompositionError(ValueError):
    """Raised when component lineage or delegation changes."""


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
        raise CompleteRuntimeCompositionError("input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise CompleteRuntimeCompositionError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("launch_admitted") is False
        and document.get("attempt_consumed") is False
        and document.get("hardware_access") is False
        and document.get("physical_authority") is False
        and document.get("controller_commands") == []
        and document.get("wire_commands") == []
        and document.get("gate_promotions") == []
    )


def _backend_zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("isaac_execution_authorized") is False
        and document.get("trajectory_playback_authorized") is False
        and document.get("native_replay_authorized") is False
        and document.get("hardware_access") is False
        and document.get("physical_authority") is False
        and document.get("controller_commands") == []
        and document.get("wire_commands") == []
        and document.get("gate_promotions") == []
    )


def build_composition_definition(
    backend: Mapping[str, Any],
    component_documents: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any]]],
    *,
    backend_file_sha256: str,
    component_file_sha256: Mapping[str, Mapping[str, str]],
    component_source_sha256: Mapping[str, Mapping[str, str]],
    composition_source_file_sha256: str,
) -> dict[str, Any]:
    """Build a complete reviewed-method binding without runtime construction."""

    backend_hash = _require_hash(backend, "backend_sha256", "ARM-255 backend")
    if (
        backend.get("schema") != BACKEND_SCHEMA
        or backend_hash != EXPECTED_BACKEND_SHA256
        or backend_file_sha256 != EXPECTED_BACKEND_FILE_SHA256
        or backend.get("runtime_protocol")
        != {
            "canonical_ik": "ONE_ACCEPTED_DETERMINATE_RESULT_PER_REGENERATED_ROW",
            "continuous_clearance": "CONTINUOUS_QUERY_NOT_DISCRETE_SAMPLING",
            "tool_key_metrics": "ONE_DETERMINATE_RESULT_PER_REGENERATED_ROW",
            "root_drift": "ONE_DETERMINATE_TERMINAL_OBSERVATION",
            "all_outputs_before_shutdown": True,
        }
        or set(component_documents) != set(COMPONENTS)
        or set(component_file_sha256) != set(COMPONENTS)
        or set(component_source_sha256) != set(COMPONENTS)
        or not isinstance(composition_source_file_sha256, str)
        or len(composition_source_file_sha256) != 64
        or not _backend_zero_authority(backend)
    ):
        raise CompleteRuntimeCompositionError("backend composition boundary changed")

    lineage: dict[str, Any] = {}
    for name, expected in COMPONENTS.items():
        adapter, review = component_documents[name]
        adapter_hash = _require_hash(adapter, "adapter_sha256", f"{name} adapter")
        review_hash = _require_hash(review, "adapter_review_sha256", f"{name} review")
        files = component_file_sha256[name]
        sources = component_source_sha256[name]
        if (
            adapter.get("schema") != expected["adapter_schema"]
            or review.get("schema") != expected["review_schema"]
            or adapter_hash != expected["adapter_hash"]
            or review_hash != expected["review_hash"]
            or review.get("source_adapter_sha256") != adapter_hash
            or review.get("status") != "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
            or review.get("runtime_integration_admitted") is not True
            or files
            != {"adapter": expected["adapter_file"], "review": expected["review_file"]}
            or sources
            != {
                "adapter": expected["adapter_source"],
                "review": expected["review_source"],
            }
            or not _zero_authority(adapter)
            or not _zero_authority(review)
        ):
            raise CompleteRuntimeCompositionError(f"{name} component lineage changed")
        lineage[name] = {
            "backend_method": expected["method"],
            "runtime_class": expected["class"],
            "adapter_sha256": adapter_hash,
            "review_sha256": review_hash,
            "adapter_file_sha256": files["adapter"],
            "review_file_sha256": files["review"],
            "adapter_source_sha256": sources["adapter"],
            "review_source_sha256": sources["review"],
        }

    core: dict[str, Any] = {
        "schema": COMPOSITION_SCHEMA,
        "composition_id": "arm270-complete-zero-authority-runtime-composition-001",
        "status": "READY_FOR_INDEPENDENT_COMPLETE_RUNTIME_COMPOSITION_REVIEW",
        "source_backend_sha256": backend_hash,
        "source_backend_file_sha256": backend_file_sha256,
        "source_components": lineage,
        "composition_source_file_sha256": composition_source_file_sha256,
        "bound_methods": [
            "regenerate_row",
            "check_continuous_clearance",
            "measure_tool_key",
            "root_drift",
        ],
        "delegation_only": True,
        "backend_execution_called": False,
        "runtime_objects_constructed_by_definition": False,
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
        "next_required_stage": "INDEPENDENTLY_REVIEW_COMPLETE_ZERO_AUTHORITY_RUNTIME_COMPOSITION",
        "limitations": [
            "definition_cli_does_not_import_isaac_or_construct_runtime_objects",
            "composition_delegates_only_to_separately_constructed_reviewed_components",
            "composition_does_not_call_the_backend_or_authorize_execution",
            "native_object_construction_and_execution_require_separate_gates",
        ],
    }
    return {**core, "composition_sha256": _sha(core)}


class CompleteRuntimeComposition:
    """Delegate the ARM-255 protocol to four separately reviewed components."""

    def __init__(
        self,
        definition: Mapping[str, Any],
        *,
        composition_review: Mapping[str, Any],
        clearance: Any,
        ik: Any,
        metrics: Any,
        drift: Any,
    ) -> None:
        composition_hash = _require_hash(
            definition, "composition_sha256", "ARM-270 composition"
        )
        _require_hash(composition_review, "composition_review_sha256", "ARM-270 review")
        supplied = {
            "clearance": clearance,
            "ik": ik,
            "metrics": metrics,
            "drift": drift,
        }
        if (
            definition.get("schema") != COMPOSITION_SCHEMA
            or definition.get("status")
            != "READY_FOR_INDEPENDENT_COMPLETE_RUNTIME_COMPOSITION_REVIEW"
            or composition_review.get("schema") != COMPOSITION_REVIEW_SCHEMA
            or composition_review.get("status")
            != "ACCEPTED_FOR_ZERO_AUTHORITY_NATIVE_RUNTIME_CONSTRUCTION"
            or composition_review.get("source_composition_sha256") != composition_hash
            or composition_review.get("runtime_construction_admitted") is not True
        ):
            raise CompleteRuntimeCompositionError(
                "complete runtime composition is not admissible"
            )
        for name, component in supplied.items():
            expected = COMPONENTS[name]
            method = getattr(component, expected["method"], None)
            if type(component).__name__ != expected["class"] or not callable(method):
                raise CompleteRuntimeCompositionError(
                    f"{name} runtime component changed"
                )
        self._clearance = clearance
        self._ik = ik
        self._metrics = metrics
        self._drift = drift

    def regenerate_row(
        self,
        *,
        source_row: Mapping[str, Any],
        previous_joint_targets_rad: Sequence[float],
    ) -> Mapping[str, Any]:
        return self._ik.regenerate_row(
            source_row=source_row, previous_joint_targets_rad=previous_joint_targets_rad
        )

    def check_continuous_clearance(
        self,
        *,
        start_sequence: int,
        end_sequence: int,
        start_joint_targets_rad: Sequence[float],
        end_joint_targets_rad: Sequence[float],
    ) -> Mapping[str, Any]:
        return self._clearance.check_continuous_clearance(
            start_sequence=start_sequence,
            end_sequence=end_sequence,
            start_joint_targets_rad=start_joint_targets_rad,
            end_joint_targets_rad=end_joint_targets_rad,
        )

    def measure_tool_key(
        self, *, sequence: int, joint_targets_rad: Sequence[float], phase: str
    ) -> Mapping[str, Any]:
        return self._metrics.measure_tool_key(
            sequence=sequence, joint_targets_rad=joint_targets_rad, phase=phase
        )

    def root_drift(self) -> Mapping[str, Any]:
        return self._drift.root_drift()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise CompleteRuntimeCompositionError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, required=True)
    for name in COMPONENTS:
        parser.add_argument(f"--{name}-adapter", type=Path, required=True)
        parser.add_argument(f"--{name}-review", type=Path, required=True)
        parser.add_argument(f"--{name}-adapter-source", type=Path, required=True)
        parser.add_argument(f"--{name}-review-source", type=Path, required=True)
    parser.add_argument("--composition-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    documents = {
        name: (
            _load(getattr(args, f"{name}_adapter")),
            _load(getattr(args, f"{name}_review")),
        )
        for name in COMPONENTS
    }
    files = {
        name: {
            "adapter": _file_sha(getattr(args, f"{name}_adapter")),
            "review": _file_sha(getattr(args, f"{name}_review")),
        }
        for name in COMPONENTS
    }
    sources = {
        name: {
            "adapter": _file_sha(getattr(args, f"{name}_adapter_source")),
            "review": _file_sha(getattr(args, f"{name}_review_source")),
        }
        for name in COMPONENTS
    }
    result = build_composition_definition(
        _load(args.backend),
        documents,
        backend_file_sha256=_file_sha(args.backend),
        component_file_sha256=files,
        component_source_sha256=sources,
        composition_source_file_sha256=_file_sha(args.composition_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
