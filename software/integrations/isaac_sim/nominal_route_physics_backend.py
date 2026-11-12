"""Fail-closed core for the governed nominal SPACE route physics backend.

This module deliberately separates deterministic contract enforcement from the
Isaac runtime adapter.  Importing it cannot import or start Isaac.  A reviewed
adapter must supply canonical IK, continuous (not sampled) clearance, tool/key
metrics, and root-drift observations before :func:`execute_backend` can emit a
passing receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


BACKEND_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_backend.v1"
BACKEND_REVIEW_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_backend_review.v1"
PREPARATION_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_worker.v1"
FIRST_SEQUENCE = 654
LAST_SEQUENCE = 940
BOUNDARY_SEQUENCE = FIRST_SEQUENCE - 1
SOURCE_SAMPLE_COUNT = 1416
CONTACT_ENDPOINTS = [1061, 1299]
REQUIRED_FILES = [
    "result.json",
    "status.json",
    "regenerated_joint_targets.jsonl",
    "canonical_ik.jsonl",
    "continuous_clearance.jsonl",
    "tool_key_metrics.jsonl",
]


class NominalRoutePhysicsBackendError(ValueError):
    """Raised when backend inputs or runtime evidence fail closed."""


class NominalRoutePhysicsRuntime(Protocol):
    """Reviewed runtime boundary required by the deterministic backend core."""

    def regenerate_row(
        self,
        *,
        source_row: Mapping[str, Any],
        previous_joint_targets_rad: Sequence[float],
    ) -> Mapping[str, Any]: ...

    def check_continuous_clearance(
        self,
        *,
        start_sequence: int,
        end_sequence: int,
        start_joint_targets_rad: Sequence[float],
        end_joint_targets_rad: Sequence[float],
    ) -> Mapping[str, Any]: ...

    def measure_tool_key(
        self,
        *,
        sequence: int,
        joint_targets_rad: Sequence[float],
        phase: str,
    ) -> Mapping[str, Any]: ...

    def root_drift(self) -> Mapping[str, Any]: ...


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_hash(value: Mapping[str, Any], key: str, label: str) -> str:
    claimed = value.get(key)
    unsigned = dict(value)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NominalRoutePhysicsBackendError(f"{label} hash mismatch")
    return claimed


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NominalRoutePhysicsBackendError(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise NominalRoutePhysicsBackendError(f"{label} is not finite")
    return result


def _joints(value: Any, label: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 6:
        raise NominalRoutePhysicsBackendError(f"{label} must contain six joints")
    return [_finite(item, label) for item in value]


def _zero_authority(value: Mapping[str, Any]) -> bool:
    return (
        value.get("hardware_access") is False
        and value.get("hardware_writes") == 0
        and value.get("physical_authority") is False
        and value.get("physical_movements") == 0
        and value.get("controller_commands") == []
        and value.get("wire_commands") == []
        and value.get("gate_promotions") == []
    )


def _validate_route(route: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = route.get("joint_targets")
    if (
        route.get("sample_count") != SOURCE_SAMPLE_COUNT
        or route.get("contact_endpoint_sequences") != CONTACT_ENDPOINTS
        or not isinstance(rows, list)
        or len(rows) != SOURCE_SAMPLE_COUNT
    ):
        raise NominalRoutePhysicsBackendError("source route shape changed")
    for sequence, row in enumerate(rows):
        if not isinstance(row, Mapping) or row.get("sequence") != sequence:
            raise NominalRoutePhysicsBackendError("source route is not contiguous")
        _joints(row.get("joint_position_target_rad"), f"source row {sequence}")
    return rows


def build_backend_definition(
    preparation: Mapping[str, Any],
    route: Mapping[str, Any],
    correction: Mapping[str, Any],
    *,
    source_files_sha256: Mapping[str, str],
    runtime_bindings_sha256: Mapping[str, str],
    backend_source_file_sha256: str,
) -> dict[str, Any]:
    """Build a reviewable backend definition without importing Isaac."""

    worker_hash = _require_hash(preparation, "worker_sha256", "ARM-254 worker")
    _require_hash(route, "plan_sha256", "route plan")
    _require_hash(correction, "plan_sha256", "correction plan")
    rows = _validate_route(route)
    window = correction.get("correction_window", {})
    contract = correction.get("materialization_contract", {})
    backend_contract = preparation.get("backend_contract", {})
    if (
        preparation.get("schema") != PREPARATION_SCHEMA
        or preparation.get("status") != "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW"
        or preparation.get("isaac_backend_implemented_by_this_envelope") is not False
        or dict(sorted(source_files_sha256.items()))
        != preparation.get("source_files_sha256")
        or dict(sorted(runtime_bindings_sha256.items()))
        != preparation.get("runtime_bindings_sha256")
        or backend_contract.get("regeneration_first_sequence") != FIRST_SEQUENCE
        or backend_contract.get("regeneration_last_sequence") != LAST_SEQUENCE
        or backend_contract.get("regenerated_row_count") != 287
        or backend_contract.get("source_sample_count") != SOURCE_SAMPLE_COUNT
        or backend_contract.get("preserved_contact_endpoint_sequences")
        != CONTACT_ENDPOINTS
        or backend_contract.get("required_output_files") != REQUIRED_FILES
        or backend_contract.get("canonical_ik_for_every_regenerated_row") is not True
        or backend_contract.get("continuous_clearance_for_every_adjacent_segment")
        is not True
        or backend_contract.get("trajectory_playback") is not False
        or backend_contract.get("native_replay") is not False
        or window.get("first_sequence_to_regenerate") != FIRST_SEQUENCE
        or window.get("last_sequence_to_regenerate") != LAST_SEQUENCE
        or window.get("allowed_source_phases") != ["TRANSIT", "HOVER"]
        or correction.get("source_corrected_plan_sha256") != route["plan_sha256"]
        or contract.get("method")
        != "DETERMINISTIC_IK_REGENERATION_WITH_CONTINUOUS_CLEARANCE_SCREEN"
        or contract.get("minimum_noncontact_tool_key_clearance_mm") != 0.5
        or contract.get("maximum_noncontact_key_displacement_mm") != 0.05
        or contract.get("maximum_adjacent_joint_step_rad") != 0.05
        or not isinstance(backend_source_file_sha256, str)
        or len(backend_source_file_sha256) != 64
        or any(row.get("phase") not in {"TRANSIT", "HOVER"} for row in rows[654:941])
        or not _zero_authority(preparation)
    ):
        raise NominalRoutePhysicsBackendError("backend definition contract changed")

    core: dict[str, Any] = {
        "schema": BACKEND_SCHEMA,
        "backend_id": "arm255-space-nominal-route-physics-backend-core-001",
        "status": "READY_FOR_INDEPENDENT_BACKEND_AND_RUNTIME_ADAPTER_REVIEW",
        "source_worker_sha256": worker_hash,
        "source_route_plan_sha256": route["plan_sha256"],
        "source_correction_plan_sha256": correction["plan_sha256"],
        "source_files_sha256": dict(sorted(source_files_sha256.items())),
        "runtime_bindings_sha256": dict(sorted(runtime_bindings_sha256.items())),
        "backend_source_file_sha256": backend_source_file_sha256,
        "regeneration_window": {
            "first_sequence": FIRST_SEQUENCE,
            "last_sequence": LAST_SEQUENCE,
            "row_count": 287,
            "canonical_boundary_sequence": BOUNDARY_SEQUENCE,
            "boundary_inclusive_clearance_segment_count": 288,
        },
        "acceptance": {
            "minimum_noncontact_tool_key_clearance_mm": 0.5,
            "maximum_noncontact_key_displacement_mm": 0.05,
            "maximum_adjacent_joint_step_rad": 0.05,
            "canonical_ik_required_for_start_boundary": True,
            "canonical_ik_required_for_every_regenerated_row": True,
            "continuous_clearance_required_for_boundary_and_internal_segments": True,
            "indeterminate_result_disposition": "FAIL_CLOSED",
        },
        "required_output_files": REQUIRED_FILES,
        "runtime_protocol": {
            "canonical_boundary": (
                "ONE_ACCEPTED_DETERMINATE_INITIALIZATION_RESULT_WITHOUT_"
                "SOURCE_ADJACENCY_ACCEPTANCE"
            ),
            "canonical_ik": "ONE_ACCEPTED_DETERMINATE_RESULT_PER_REGENERATED_ROW",
            "continuous_clearance": "CONTINUOUS_QUERY_NOT_DISCRETE_SAMPLING",
            "tool_key_metrics": "ONE_DETERMINATE_RESULT_PER_REGENERATED_ROW",
            "root_drift": "ONE_DETERMINATE_TERMINAL_OBSERVATION",
            "all_outputs_before_shutdown": True,
        },
        "isaac_runtime_adapter_implemented_by_core": False,
        "isaac_execution_authorized": False,
        "isaac_started": False,
        "gpu_started": False,
        "trajectory_playback_authorized": False,
        "native_replay_authorized": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": "INDEPENDENTLY_REVIEW_BACKEND_AND_PINNED_ISAAC_RUNTIME_ADAPTER",
        "limitations": [
            "definition_build_does_not_import_or_start_isaac_or_a_gpu",
            "core_requires_a_separately_reviewed_continuous_clearance_runtime_adapter",
            "discrete_overlap_sampling_cannot_satisfy_the_runtime_protocol",
            "simulation_result_cannot_authorize_hardware_or_physical_motion",
        ],
    }
    return {**core, "backend_sha256": _sha(core)}


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def execute_backend(
    definition: Mapping[str, Any],
    route: Mapping[str, Any],
    *,
    backend_review: Mapping[str, Any],
    output_directory: Path,
    runtime: NominalRoutePhysicsRuntime,
) -> Mapping[str, Any]:
    """Execute the deterministic core through an independently reviewed adapter.

    The worker must already have atomically claimed ``output_directory``.  This
    function performs no retry and contains no controller or hardware API.
    """

    backend_hash = _require_hash(definition, "backend_sha256", "ARM-255 backend")
    review_hash = _require_hash(
        backend_review, "backend_review_sha256", "ARM-255 backend review"
    )
    status_path = output_directory / REQUIRED_FILES[1]
    try:
        claim = json.loads(status_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise NominalRoutePhysicsBackendError(
            "worker claim receipt is unavailable"
        ) from exc
    if (
        definition.get("schema") != BACKEND_SCHEMA
        or definition.get("status")
        != "READY_FOR_INDEPENDENT_BACKEND_AND_RUNTIME_ADAPTER_REVIEW"
        or backend_review.get("schema") != BACKEND_REVIEW_SCHEMA
        or backend_review.get("status")
        != "ACCEPTED_FOR_ONE_SEPARATELY_AUTHORIZED_SIMULATION_ATTEMPT"
        or backend_review.get("source_backend_sha256") != backend_hash
        or not isinstance(backend_review.get("reviewed_runtime_adapter_sha256"), str)
        or len(backend_review["reviewed_runtime_adapter_sha256"]) != 64
        or backend_review.get("continuous_clearance_protocol_accepted") is not True
        or backend_review.get("launch_admitted") is not True
        or not isinstance(review_hash, str)
        or not output_directory.is_dir()
        or not _zero_authority(definition)
        or not _zero_authority(backend_review)
        or claim
        != {
            "status": "ATTEMPT_CLAIMED_BACKEND_PENDING",
            "attempt_count": 1,
            "automatic_retry": False,
            "hardware_access": False,
            "physical_authority": False,
        }
    ):
        raise NominalRoutePhysicsBackendError("backend execution is not admitted")
    rows = _validate_route(route)
    generated: list[dict[str, Any]] = []
    ik_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    boundary_evidence = dict(
        runtime.regenerate_row(
            source_row=rows[BOUNDARY_SEQUENCE],
            previous_joint_targets_rad=rows[BOUNDARY_SEQUENCE - 1][
                "joint_position_target_rad"
            ],
        )
    )
    canonical_boundary_joints = _joints(
        boundary_evidence.get("joint_position_target_rad"),
        "canonical boundary",
    )
    boundary_residual = _finite(
        boundary_evidence.get("position_error_mm"),
        "canonical boundary IK",
    )
    if (
        boundary_evidence.get("sequence") != BOUNDARY_SEQUENCE
        or boundary_evidence.get("accepted") is not True
        or boundary_evidence.get("determinate") is not True
    ):
        raise NominalRoutePhysicsBackendError("canonical IK boundary failed")
    previous = canonical_boundary_joints

    for sequence in range(FIRST_SEQUENCE, LAST_SEQUENCE + 1):
        source = rows[sequence]
        evidence = dict(
            runtime.regenerate_row(
                source_row=source, previous_joint_targets_rad=previous
            )
        )
        joints = _joints(evidence.get("joint_position_target_rad"), f"row {sequence}")
        maximum_step = max(abs(a - b) for a, b in zip(joints, previous))
        residual = _finite(evidence.get("position_error_mm"), f"IK row {sequence}")
        if (
            evidence.get("sequence") != sequence
            or evidence.get("accepted") is not True
            or evidence.get("determinate") is not True
            or maximum_step > 0.05
        ):
            raise NominalRoutePhysicsBackendError(f"canonical IK row {sequence} failed")
        generated.append(
            {
                "sequence": sequence,
                "time_from_start_ns": source["time_from_start_ns"],
                "phase": source["phase"],
                "phase_endpoint": source["phase_endpoint"],
                "action_index": source["action_index"],
                "target_id": source["target_id"],
                "joint_position_target_rad": joints,
            }
        )
        ik_rows.append(
            {
                "sequence": sequence,
                "accepted": True,
                "determinate": True,
                "position_error_mm": residual,
                "maximum_adjacent_joint_step_rad": maximum_step,
            }
        )
        metric = dict(
            runtime.measure_tool_key(
                sequence=sequence,
                joint_targets_rad=joints,
                phase=str(source["phase"]),
            )
        )
        clearance = _finite(metric.get("tool_key_clearance_mm"), f"metric {sequence}")
        displacement = _finite(metric.get("key_displacement_mm"), f"metric {sequence}")
        if (
            metric.get("sequence") != sequence
            or metric.get("determinate") is not True
            or clearance < 0.5
            or abs(displacement) > 0.05
        ):
            raise NominalRoutePhysicsBackendError(f"tool/key row {sequence} failed")
        metric_rows.append(
            {
                "sequence": sequence,
                "determinate": True,
                "tool_key_clearance_mm": clearance,
                "key_displacement_mm": displacement,
            }
        )
        previous = joints

    clearance_rows: list[dict[str, Any]] = []
    joint_by_sequence = {
        BOUNDARY_SEQUENCE: canonical_boundary_joints,
        **{row["sequence"]: row["joint_position_target_rad"] for row in generated},
        LAST_SEQUENCE + 1: _joints(
            rows[LAST_SEQUENCE + 1]["joint_position_target_rad"], "end boundary"
        ),
    }
    for start in range(FIRST_SEQUENCE - 1, LAST_SEQUENCE + 1):
        end = start + 1
        evidence = dict(
            runtime.check_continuous_clearance(
                start_sequence=start,
                end_sequence=end,
                start_joint_targets_rad=joint_by_sequence[start],
                end_joint_targets_rad=joint_by_sequence[end],
            )
        )
        minimum = _finite(
            evidence.get("minimum_clearance_mm"), f"segment {start}:{end}"
        )
        if (
            evidence.get("start_sequence") != start
            or evidence.get("end_sequence") != end
            or evidence.get("continuous") is not True
            or evidence.get("determinate") is not True
            or evidence.get("colliding_body_pair") is not None
            or minimum < 0.5
        ):
            raise NominalRoutePhysicsBackendError(
                f"continuous clearance segment {start}:{end} failed"
            )
        clearance_rows.append(
            {
                "start_sequence": start,
                "end_sequence": end,
                "continuous": True,
                "determinate": True,
                "minimum_clearance_mm": minimum,
                "colliding_body_pair": None,
            }
        )

    drift = dict(runtime.root_drift())
    translation = _finite(drift.get("translation_mm"), "root translation drift")
    rotation = _finite(drift.get("rotation_deg"), "root rotation drift")
    if drift.get("determinate") is not True:
        raise NominalRoutePhysicsBackendError("root drift is indeterminate")

    _write_jsonl(output_directory / REQUIRED_FILES[2], generated)
    _write_jsonl(output_directory / REQUIRED_FILES[3], ik_rows)
    _write_jsonl(output_directory / REQUIRED_FILES[4], clearance_rows)
    _write_jsonl(output_directory / REQUIRED_FILES[5], metric_rows)
    output_hashes = {
        name: hashlib.sha256((output_directory / name).read_bytes()).hexdigest()
        for name in REQUIRED_FILES[2:]
    }
    result_core: dict[str, Any] = {
        "schema": "tactevra.isaac_lm4_nominal_route_physics_result.v1",
        "status": "PASS_NOMINAL_SIMULATION_ONLY",
        "source_backend_sha256": backend_hash,
        "canonical_boundary_sequence": BOUNDARY_SEQUENCE,
        "canonical_boundary_position_error_mm": boundary_residual,
        "regenerated_row_count": len(generated),
        "canonical_ik_row_count": len(ik_rows),
        "continuous_clearance_segment_count": len(clearance_rows),
        "tool_key_metric_row_count": len(metric_rows),
        "root_translation_drift_mm": translation,
        "root_rotation_drift_deg": rotation,
        "output_file_sha256": output_hashes,
        "trajectory_playback": False,
        "native_replay": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": "INDEPENDENT_RESULT_REVIEW_BEFORE_MULTI_KEY_EXPANSION",
    }
    result = {**result_core, "result_sha256": _sha(result_core)}
    result_path = output_directory / REQUIRED_FILES[0]
    temporary = result_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(result_path)
    status = {
        "status": "PASS_RETAINED_NO_RETRY",
        "attempt_count": 1,
        "automatic_retry": False,
        "result_sha256": result["result_sha256"],
        "hardware_access": False,
        "physical_authority": False,
    }
    temporary = status_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(status, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(status_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--route-plan", type=Path, required=True)
    parser.add_argument("--correction-plan", type=Path, required=True)
    parser.add_argument("--backend-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    worker_path = args.worker.resolve(strict=True)
    route_path = args.route_plan.resolve(strict=True)
    correction_path = args.correction_plan.resolve(strict=True)
    source_path = args.backend_source.resolve(strict=True)
    preparation = json.loads(worker_path.read_bytes())
    route = json.loads(route_path.read_bytes())
    correction = json.loads(correction_path.read_bytes())
    source_hashes = preparation.get("source_files_sha256")
    runtime_hashes = preparation.get("runtime_bindings_sha256")
    if not isinstance(source_hashes, Mapping) or not isinstance(
        runtime_hashes, Mapping
    ):
        raise NominalRoutePhysicsBackendError("worker does not carry pinned bindings")
    if hashlib.sha256(route_path.read_bytes()).hexdigest() != source_hashes.get(
        "route_plan"
    ) or hashlib.sha256(correction_path.read_bytes()).hexdigest() != source_hashes.get(
        "correction_plan"
    ):
        raise NominalRoutePhysicsBackendError("route or correction file hash changed")
    result = build_backend_definition(
        preparation,
        route,
        correction,
        source_files_sha256=source_hashes,
        runtime_bindings_sha256=runtime_hashes,
        backend_source_file_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
