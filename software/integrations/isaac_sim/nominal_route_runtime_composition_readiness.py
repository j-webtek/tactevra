"""Pin ARM-265 and expose the remaining nominal-route runtime dependencies.

ARM-266 is an import-safe, non-executing readiness gate.  It proves that the
reviewed native-clearance adapter satisfies exactly one ARM-255 runtime method
and orders the three methods that still need separately reviewed adapters.
It cannot import or start Isaac, construct runtime objects, or consume the
reserved route attempt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


READINESS_SCHEMA = "tactevra.isaac_lm4_runtime_composition_readiness.v1"
BACKEND_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_backend.v1"
ADAPTER_SCHEMA = "tactevra.isaac_lm4_native_clearance_adapter.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_native_clearance_adapter_review.v1"

EXPECTED_BACKEND_SHA256 = (
    "132f1e028503a3a83af11f2a713f839e00e1fef49aa9cb3fbb0156f858245cde"
)
EXPECTED_ADAPTER_SHA256 = (
    "e5fb18e441e4ac97ee571a2399a55d441fcb149c9e6d6c766cbc660988aa4634"
)
EXPECTED_REVIEW_SHA256 = (
    "f83cd6b50c6dc93ed37ea4743bc50174e97e1a498a71b8b08c98969011d44243"
)
EXPECTED_BACKEND_FILE_SHA256 = (
    "968140c9b075cc4f6a8d5599edc765cd1b6cde734e32e6632513bd2c94fb6228"
)
EXPECTED_ADAPTER_FILE_SHA256 = (
    "b5e8891053531cd799e6367b4ff24140c268757e4a57a3a19691fc48d1e76df4"
)
EXPECTED_REVIEW_FILE_SHA256 = (
    "1ababaac40fc50840f31aa921e3d3b00514cb4416e6c92190bc51095b4381b13"
)


class RuntimeCompositionReadinessError(ValueError):
    """Raised when the reviewed runtime-composition lineage changes."""


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
        raise RuntimeCompositionReadinessError("input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise RuntimeCompositionReadinessError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("hardware_access") is False
        and document.get("hardware_writes") == 0
        and document.get("physical_authority") is False
        and document.get("physical_movements") == 0
        and document.get("controller_commands") == []
        and document.get("wire_commands") == []
        and document.get("gate_promotions") == []
    )


def build_runtime_composition_readiness(
    backend: Mapping[str, Any],
    adapter: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    backend_file_sha256: str,
    adapter_file_sha256: str,
    review_file_sha256: str,
    backend_source_file_sha256: str,
    adapter_source_file_sha256: str,
    readiness_source_file_sha256: str,
) -> dict[str, Any]:
    """Build the zero-authority composition plan from reviewed evidence."""

    backend_hash = _require_hash(backend, "backend_sha256", "ARM-255 backend")
    adapter_hash = _require_hash(adapter, "adapter_sha256", "ARM-265 adapter")
    review_hash = _require_hash(review, "adapter_review_sha256", "ARM-265 review")
    protocol = backend.get("runtime_protocol", {})
    expected_protocol = {
        "canonical_ik": "ONE_ACCEPTED_DETERMINATE_RESULT_PER_REGENERATED_ROW",
        "continuous_clearance": "CONTINUOUS_QUERY_NOT_DISCRETE_SAMPLING",
        "tool_key_metrics": "ONE_DETERMINATE_RESULT_PER_REGENERATED_ROW",
        "root_drift": "ONE_DETERMINATE_TERMINAL_OBSERVATION",
        "all_outputs_before_shutdown": True,
    }
    digests = (
        backend_source_file_sha256,
        adapter_source_file_sha256,
        readiness_source_file_sha256,
    )
    if (
        backend.get("schema") != BACKEND_SCHEMA
        or backend.get("status")
        != "READY_FOR_INDEPENDENT_BACKEND_AND_RUNTIME_ADAPTER_REVIEW"
        or backend_hash != EXPECTED_BACKEND_SHA256
        or protocol != expected_protocol
        or backend.get("acceptance", {}).get(
            "minimum_noncontact_tool_key_clearance_mm"
        )
        != 0.5
        or backend.get("acceptance", {}).get("maximum_adjacent_joint_step_rad")
        != 0.05
        or adapter.get("schema") != ADAPTER_SCHEMA
        or adapter.get("status")
        != "READY_FOR_INDEPENDENT_NATIVE_CLEARANCE_ADAPTER_REVIEW"
        or adapter_hash != EXPECTED_ADAPTER_SHA256
        or adapter.get("backend_method") != "check_continuous_clearance"
        or adapter.get("clearance_margin_mm") != 0.5
        or adapter.get("maximum_subdivision_depth") != 12
        or adapter.get("environment_only_scene_required") is not True
        or adapter.get("robot_collision_query_shapes_enabled") is not False
        or review.get("schema") != REVIEW_SCHEMA
        or review.get("status")
        != "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
        or review_hash != EXPECTED_REVIEW_SHA256
        or review.get("source_adapter_sha256") != adapter_hash
        or review.get("runtime_integration_admitted") is not True
        or review.get("next_required_stage")
        != "PREPARE_ZERO_AUTHORITY_NOMINAL_ROUTE_RUNTIME_COMPOSITION"
        or backend_file_sha256 != EXPECTED_BACKEND_FILE_SHA256
        or adapter_file_sha256 != EXPECTED_ADAPTER_FILE_SHA256
        or review_file_sha256 != EXPECTED_REVIEW_FILE_SHA256
        or any(not isinstance(item, str) or len(item) != 64 for item in digests)
        or not _zero_authority(backend)
        or not _zero_authority(adapter)
        or not _zero_authority(review)
    ):
        raise RuntimeCompositionReadinessError(
            "nominal-route runtime composition lineage or boundary changed"
        )

    core: dict[str, Any] = {
        "schema": READINESS_SCHEMA,
        "readiness_id": "arm266-zero-authority-runtime-composition-readiness-001",
        "status": "READY_TO_IMPLEMENT_REMAINING_ZERO_AUTHORITY_RUNTIME_ADAPTERS",
        "source_backend_sha256": backend_hash,
        "source_clearance_adapter_sha256": adapter_hash,
        "source_clearance_adapter_review_sha256": review_hash,
        "source_files_sha256": {
            "arm255_backend": backend_file_sha256,
            "arm265_clearance_adapter": adapter_file_sha256,
            "arm265_clearance_adapter_review": review_file_sha256,
            "arm255_backend_source": backend_source_file_sha256,
            "arm265_clearance_adapter_source": adapter_source_file_sha256,
            "arm266_readiness_source": readiness_source_file_sha256,
        },
        "backend_runtime_methods": [
            "regenerate_row",
            "check_continuous_clearance",
            "measure_tool_key",
            "root_drift",
        ],
        "reviewed_methods": ["check_continuous_clearance"],
        "remaining_methods": ["regenerate_row", "measure_tool_key", "root_drift"],
        "ordered_implementation_stages": [
            {
                "method": "regenerate_row",
                "requirement": expected_protocol["canonical_ik"],
                "next_stage": "IMPLEMENT_AND_REVIEW_CANONICAL_IK_ROW_ADAPTER",
            },
            {
                "method": "measure_tool_key",
                "requirement": expected_protocol["tool_key_metrics"],
                "next_stage": "IMPLEMENT_AND_REVIEW_TOOL_KEY_METRICS_ADAPTER",
            },
            {
                "method": "root_drift",
                "requirement": expected_protocol["root_drift"],
                "next_stage": "IMPLEMENT_AND_REVIEW_ROOT_DRIFT_ADAPTER",
            },
        ],
        "composition_complete": False,
        "backend_review_admitted": False,
        "runtime_objects_constructed": False,
        "composition_execution_admitted": False,
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
        "next_required_stage": "IMPLEMENT_AND_REVIEW_CANONICAL_IK_ROW_ADAPTER",
        "limitations": [
            "readiness_cli_does_not_construct_runtime_objects_or_import_isaac",
            "clearance_is_the_only_reviewed_backend_runtime_method",
            "full_backend_execution_remains_fail_closed",
            "no_launch_attempt_hardware_or_physical_authority_is_granted",
        ],
    }
    return {**core, "readiness_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise RuntimeCompositionReadinessError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--adapter-review", type=Path, required=True)
    parser.add_argument("--backend-source", type=Path, required=True)
    parser.add_argument("--adapter-source", type=Path, required=True)
    parser.add_argument("--readiness-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_runtime_composition_readiness(
        _load(args.backend),
        _load(args.adapter),
        _load(args.adapter_review),
        backend_file_sha256=_file_sha(args.backend),
        adapter_file_sha256=_file_sha(args.adapter),
        review_file_sha256=_file_sha(args.adapter_review),
        backend_source_file_sha256=_file_sha(args.backend_source),
        adapter_source_file_sha256=_file_sha(args.adapter_source),
        readiness_source_file_sha256=_file_sha(args.readiness_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
