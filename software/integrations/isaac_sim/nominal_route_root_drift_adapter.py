"""Provide ARM-255 ``root_drift`` through one terminal read-only pose sample.

ARM-269 compares a supplied native root view with the root pose captured after
scene setup and before governed motion.  It never commands an articulation,
starts Isaac, or authorizes execution.  The definition CLI is import-safe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


ADAPTER_SCHEMA = "tactevra.isaac_lm4_root_drift_adapter.v1"
ADAPTER_REVIEW_SCHEMA = "tactevra.isaac_lm4_root_drift_adapter_review.v1"
READINESS_SCHEMA = "tactevra.isaac_lm4_runtime_composition_readiness.v1"
BACKEND_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_backend.v1"
METRICS_ADAPTER_SCHEMA = "tactevra.isaac_lm4_tool_key_metrics_adapter.v1"
METRICS_REVIEW_SCHEMA = "tactevra.isaac_lm4_tool_key_metrics_adapter_review.v1"

EXPECTED_READINESS_SHA256 = (
    "7259e53c0e5522a090a0cdce9c36034fc793bcd093cdfdcce63bee9b99f14bab"
)
EXPECTED_BACKEND_SHA256 = (
    "132f1e028503a3a83af11f2a713f839e00e1fef49aa9cb3fbb0156f858245cde"
)
EXPECTED_METRICS_ADAPTER_SHA256 = (
    "5b2327498efe78ced7d7c5ef88db170f0596d59b83a22a56df5e8b5f60493f19"
)
EXPECTED_METRICS_REVIEW_SHA256 = (
    "53d25636a6a26778a51b57ae05468fe890f8eaec4f908b34101367972ce92517"
)
EXPECTED_READINESS_FILE_SHA256 = (
    "572f97eb6c4b52f77b823da767ec270fa9e4c78112e9de69c284133bb91f8b75"
)
EXPECTED_BACKEND_FILE_SHA256 = (
    "968140c9b075cc4f6a8d5599edc765cd1b6cde734e32e6632513bd2c94fb6228"
)
EXPECTED_METRICS_ADAPTER_FILE_SHA256 = (
    "e4b059e0fc78343eda7959c2e97ac66565db93fe859e8a0dc0e5591eee8e41da"
)
EXPECTED_METRICS_REVIEW_FILE_SHA256 = (
    "3077bc83c25f8cd491ace003469e6add6d275a8de79894a70f8344a2256167a7"
)
EXPECTED_MECHANICS_SOURCE_SHA256 = (
    "ba12db530d8ffb0a9b22068238a604a935f6adaff8ba6f3fa7364581ec18d9a3"
)

STAGE_UNITS_IN_METERS = 1.0
TRANSLATION_TOLERANCE_MM = 0.05
ORIENTATION_TOLERANCE_DEG = 0.1


class RootDriftAdapterError(ValueError):
    """Raised when lineage, pose observations, or the fixed root drift."""


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
        raise RootDriftAdapterError("input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise RootDriftAdapterError(f"{label} hash changed")
    return claimed


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RootDriftAdapterError(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise RootDriftAdapterError(f"{label} is not finite")
    return result


def _vector(value: Any, length: int, label: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise RootDriftAdapterError(f"{label} must contain {length} values")
    return [_finite(item, label) for item in value]


def _unit_quaternion(value: Any, label: str) -> list[float]:
    quaternion = _vector(value, 4, label)
    norm = math.sqrt(sum(item * item for item in quaternion))
    if norm <= 1e-12:
        raise RootDriftAdapterError(f"{label} has zero norm")
    return [item / norm for item in quaternion]


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


def build_adapter_definition(
    readiness: Mapping[str, Any],
    backend: Mapping[str, Any],
    metrics_adapter: Mapping[str, Any],
    metrics_review: Mapping[str, Any],
    *,
    readiness_file_sha256: str,
    backend_file_sha256: str,
    metrics_adapter_file_sha256: str,
    metrics_review_file_sha256: str,
    mechanics_source_file_sha256: str,
    adapter_source_file_sha256: str,
) -> dict[str, Any]:
    """Build the immutable review input without constructing a native view."""

    readiness_hash = _require_hash(readiness, "readiness_sha256", "ARM-266 readiness")
    backend_hash = _require_hash(backend, "backend_sha256", "ARM-255 backend")
    metrics_hash = _require_hash(metrics_adapter, "adapter_sha256", "ARM-268 adapter")
    review_hash = _require_hash(
        metrics_review, "adapter_review_sha256", "ARM-268 review"
    )
    if (
        readiness.get("schema") != READINESS_SCHEMA
        or readiness_hash != EXPECTED_READINESS_SHA256
        or backend.get("schema") != BACKEND_SCHEMA
        or backend_hash != EXPECTED_BACKEND_SHA256
        or backend.get("runtime_protocol", {}).get("root_drift")
        != "ONE_DETERMINATE_TERMINAL_OBSERVATION"
        or metrics_adapter.get("schema") != METRICS_ADAPTER_SCHEMA
        or metrics_hash != EXPECTED_METRICS_ADAPTER_SHA256
        or metrics_review.get("schema") != METRICS_REVIEW_SCHEMA
        or review_hash != EXPECTED_METRICS_REVIEW_SHA256
        or metrics_review.get("source_adapter_sha256") != metrics_hash
        or metrics_review.get("status")
        != "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
        or metrics_review.get("next_required_stage")
        != "IMPLEMENT_AND_REVIEW_ROOT_DRIFT_ADAPTER"
        or readiness_file_sha256 != EXPECTED_READINESS_FILE_SHA256
        or backend_file_sha256 != EXPECTED_BACKEND_FILE_SHA256
        or metrics_adapter_file_sha256 != EXPECTED_METRICS_ADAPTER_FILE_SHA256
        or metrics_review_file_sha256 != EXPECTED_METRICS_REVIEW_FILE_SHA256
        or mechanics_source_file_sha256 != EXPECTED_MECHANICS_SOURCE_SHA256
        or any(
            not isinstance(item, str) or len(item) != 64
            for item in (adapter_source_file_sha256,)
        )
        or not _zero_authority(readiness)
        or not _zero_authority(metrics_adapter)
        or not _zero_authority(metrics_review)
    ):
        raise RootDriftAdapterError("root drift adapter lineage or boundary changed")

    core: dict[str, Any] = {
        "schema": ADAPTER_SCHEMA,
        "adapter_id": "arm269-zero-authority-root-drift-adapter-001",
        "status": "READY_FOR_INDEPENDENT_ROOT_DRIFT_ADAPTER_REVIEW",
        "source_readiness_sha256": readiness_hash,
        "source_backend_sha256": backend_hash,
        "source_tool_key_metrics_adapter_sha256": metrics_hash,
        "source_tool_key_metrics_review_sha256": review_hash,
        "source_files_sha256": {
            "arm266_readiness": readiness_file_sha256,
            "arm255_backend": backend_file_sha256,
            "arm268_adapter": metrics_adapter_file_sha256,
            "arm268_adapter_review": metrics_review_file_sha256,
            "native_mechanics_source": mechanics_source_file_sha256,
            "arm269_adapter_source": adapter_source_file_sha256,
        },
        "backend_method": "root_drift",
        "pose_source": "NATIVE_RIGID_PRIM_GET_WORLD_POSES",
        "quaternion_order": "WXYZ",
        "stage_units_in_meters": STAGE_UNITS_IN_METERS,
        "translation_tolerance_mm": TRANSLATION_TOLERANCE_MM,
        "orientation_tolerance_deg": ORIENTATION_TOLERANCE_DEG,
        "sample_count": 1,
        "sample_timing": "TERMINAL_AFTER_ROUTE_BEFORE_BACKEND_ACCEPTANCE",
        "baseline_timing": "AFTER_SCENE_SETUP_BEFORE_GOVERNED_MOTION",
        "quaternion_sign_invariant": True,
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
        "next_required_stage": "INDEPENDENTLY_REVIEW_ROOT_DRIFT_ADAPTER",
        "limitations": [
            "definition_cli_does_not_import_isaac_or_construct_runtime_objects",
            "runtime_adapter_reads_only_the_supplied_root_pose_view",
            "adapter_rejects_drift_outside_the_pinned_fixed_base_tolerances",
            "adapter_cannot_submit_joint_targets_or_authorize_an_attempt",
        ],
    }
    return {**core, "adapter_sha256": _sha(core)}


def _tensor_list(value: Any, label: str) -> Any:
    try:
        if hasattr(value, "numpy"):
            value = value.numpy()
        if hasattr(value, "tolist"):
            value = value.tolist()
    except Exception as exc:  # pragma: no cover - native tensor boundary
        raise RootDriftAdapterError(f"{label} cannot be converted") from exc
    return value


class RootDriftRuntimeAdapter:
    """Read one terminal native root pose and reject fixed-base drift."""

    def __init__(
        self,
        definition: Mapping[str, Any],
        *,
        adapter_review: Mapping[str, Any],
        root_view: Any,
        expected_position_stage: Sequence[float],
        expected_quaternion_wxyz: Sequence[float],
    ) -> None:
        adapter_hash = _require_hash(definition, "adapter_sha256", "ARM-269 adapter")
        _require_hash(adapter_review, "adapter_review_sha256", "ARM-269 review")
        if (
            definition.get("schema") != ADAPTER_SCHEMA
            or definition.get("status")
            != "READY_FOR_INDEPENDENT_ROOT_DRIFT_ADAPTER_REVIEW"
            or definition.get("backend_method") != "root_drift"
            or adapter_review.get("schema") != ADAPTER_REVIEW_SCHEMA
            or adapter_review.get("status")
            != "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
            or adapter_review.get("source_adapter_sha256") != adapter_hash
            or adapter_review.get("runtime_integration_admitted") is not True
            or not callable(getattr(root_view, "get_world_poses", None))
        ):
            raise RootDriftAdapterError(
                "root drift runtime composition is not admissible"
            )
        self._definition = definition
        self._root_view = root_view
        self._expected_position = _vector(
            expected_position_stage, 3, "expected root position"
        )
        self._expected_quaternion = _unit_quaternion(
            expected_quaternion_wxyz, "expected root quaternion"
        )

    def root_drift(self) -> Mapping[str, Any]:
        poses = self._root_view.get_world_poses()
        if not isinstance(poses, (list, tuple)) or len(poses) < 2:
            raise RootDriftAdapterError("native root pose result changed")
        positions = _tensor_list(poses[0], "native root positions")
        orientations = _tensor_list(poses[1], "native root orientations")
        if (
            not isinstance(positions, list)
            or len(positions) != 1
            or not isinstance(positions[0], (list, tuple))
            or not isinstance(orientations, list)
            or len(orientations) != 1
            or not isinstance(orientations[0], (list, tuple))
        ):
            raise RootDriftAdapterError("native root pose shape changed")
        observed_position = _vector(positions[0], 3, "observed root position")
        observed_quaternion = _unit_quaternion(
            orientations[0], "observed root quaternion"
        )
        scale = (
            _finite(self._definition.get("stage_units_in_meters"), "stage units")
            * 1000.0
        )
        translation = scale * math.sqrt(
            sum(
                (a - b) ** 2 for a, b in zip(self._expected_position, observed_position)
            )
        )
        dot = abs(
            sum(a * b for a, b in zip(self._expected_quaternion, observed_quaternion))
        )
        rotation = math.degrees(2.0 * math.acos(min(1.0, dot)))
        if translation > _finite(
            self._definition.get("translation_tolerance_mm"), "translation tolerance"
        ) or rotation > _finite(
            self._definition.get("orientation_tolerance_deg"), "orientation tolerance"
        ):
            raise RootDriftAdapterError("fixed root drift exceeds reviewed tolerance")
        return {
            "determinate": True,
            "translation_mm": translation,
            "rotation_deg": rotation,
        }


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise RootDriftAdapterError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--metrics-adapter", type=Path, required=True)
    parser.add_argument("--metrics-review", type=Path, required=True)
    parser.add_argument("--mechanics-source", type=Path, required=True)
    parser.add_argument("--adapter-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_adapter_definition(
        _load(args.readiness),
        _load(args.backend),
        _load(args.metrics_adapter),
        _load(args.metrics_review),
        readiness_file_sha256=_file_sha(args.readiness),
        backend_file_sha256=_file_sha(args.backend),
        metrics_adapter_file_sha256=_file_sha(args.metrics_adapter),
        metrics_review_file_sha256=_file_sha(args.metrics_review),
        mechanics_source_file_sha256=_file_sha(args.mechanics_source),
        adapter_source_file_sha256=_file_sha(args.adapter_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
