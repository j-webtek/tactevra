"""Strict C03 import boundary for measured moving-cable evidence.

The adapter binds one measured capsule chain to every bounded partition sample
and one independently conservative swept capsule chain to every partition-owned
adjacent segment.  It converts admitted rows into the generic collision types
used by the later partition evaluator, but performs no collision evaluation and
creates no command or physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from rocell.geometry import Vec3
from rocell.simulation.collision import (
    CapsuleMm,
    CollisionEvidenceState,
    SampledCollisionGeometry,
)

from .bounded_segment_collision_qualification import (
    MeasuredSegmentConfigurationSample,
)
from .c03_installed_collision_qualification_v1 import (
    READY_FOR_EVIDENCE_STATUS,
    SCHEMA as QUALIFICATION_SCHEMA,
)
from .c03_rigid_attachment_binding_v1 import (
    READY_STATUS as RIGID_READY_STATUS,
    REPORT_SCHEMA as RIGID_REPORT_SCHEMA,
)
from .conservative_segment_sweep_qualification import (
    MeasuredConfigurationSweepEnvelopeBinding,
)
from .fk_collision_pose_adapter import MeasuredConfigurationGeometryBinding


SCHEMA = "tactevra.c03_cable_envelope_manifest.v1"
REPORT_SCHEMA = "tactevra.c03_cable_envelope_intake_report.v1"
READY_STATUS = "READY_FOR_C03_PARTITION_COLLISION_EVALUATION"
MAX_BYTES = 64 * 1024 * 1024
MAX_ROWS = 4096
MAX_CAPSULES_PER_BODY = 64
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SAMPLE_METHOD = "DIRECT_CAPTURED_CAPSULE_CHAIN"
_SWEEP_METHODS = {
    "DIRECT_CAPTURED_CONSERVATIVE_ENVELOPE",
    "MULTI_POSE_CAPTURE_UNION_WITH_VALIDATED_BOUND",
}

_ROOT_FIELDS = {
    "schema", "cable_manifest_id", "captured_at_utc", "valid_until_utc",
    "c03_installed_collision_qualification_sha256",
    "c03_rigid_attachment_binding_report_sha256",
    "partitioned_typing_collision_intake_sha256",
    "collision_contract_sha256", "installed_collision_profile_content_sha256",
    "installed_collision_profile_file_sha256", "measurement_manifest_file_sha256",
    "measurement_manifest_content_sha256", "root_frame", "sources", "samples",
    "sweeps", "content_sha256",
}
_SOURCE_FIELDS = {"source_id", "sha256", "captured_at_utc", "method", "notes"}
_SAMPLE_FIELDS = {
    "partition_index", "sample_sequence", "sample_plan_sha256", "captured_at_utc",
    "method", "bodies",
}
_SWEEP_FIELDS = {
    "partition_index", "segment_sequence", "owned_segment_sequence",
    "start_sample_sha256", "end_sample_sha256", "captured_at_utc",
    "construction_method", "intermediate_observation_count", "bodies",
}
_BODY_FIELDS = {"body_id", "source_id", "capsules"}
_CAPSULE_FIELDS = {
    "start_mm", "end_mm", "measured_radius_mm", "capture_uncertainty_mm",
    "unobserved_deformation_mm",
}


class C03CableEnvelopeIntakeV1Error(ValueError):
    """Cable evidence is incomplete, stale, crossed, or nonconservative."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise C03CableEnvelopeIntakeV1Error(f"{label} is not a SHA-256 digest")
    return value


def _exact(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise C03CableEnvelopeIntakeV1Error(f"{label} fields differ")
    return dict(value)


def _bounded_list(value: object, label: str, *, maximum: int = MAX_ROWS) -> list[Any]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise C03CableEnvelopeIntakeV1Error(f"{label} count is outside its bound")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise C03CableEnvelopeIntakeV1Error(f"{label} is invalid")
    return value


def _finite(
    value: object,
    label: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise C03CableEnvelopeIntakeV1Error(f"{label} is not numeric")
    result = float(value)
    if (
        not math.isfinite(result)
        or (positive and result <= 0.0)
        or (nonnegative and result < 0.0)
    ):
        raise C03CableEnvelopeIntakeV1Error(f"{label} is outside its bound")
    return result


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise C03CableEnvelopeIntakeV1Error(f"{label} must be UTC with Z suffix")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise C03CableEnvelopeIntakeV1Error(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise C03CableEnvelopeIntakeV1Error(f"{label} must be UTC")
    return parsed


def _validated_hash_report(
    value: object,
    *,
    schema: str,
    hash_field: str,
    status: str,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise C03CableEnvelopeIntakeV1Error(f"{label} must be an object")
    report = dict(value)
    digest = report.pop(hash_field, None)
    if (
        value.get("schema") != schema
        or value.get("status") != status
        or not isinstance(digest, str)
        or digest != _sha(report)
    ):
        raise C03CableEnvelopeIntakeV1Error(f"{label} is not exact and ready")
    return dict(value)


def _vector(value: object, label: str) -> Vec3:
    if not isinstance(value, list) or len(value) != 3:
        raise C03CableEnvelopeIntakeV1Error(f"{label} must have three coordinates")
    numbers = [_finite(item, label) for item in value]
    return Vec3(*numbers)


def _capsules(value: object, label: str) -> tuple[CapsuleMm, ...]:
    rows = _bounded_list(value, label, maximum=MAX_CAPSULES_PER_BODY)
    capsules: list[CapsuleMm] = []
    for index, raw in enumerate(rows):
        row = _exact(raw, _CAPSULE_FIELDS, f"{label}[{index}]")
        measured = _finite(
            row["measured_radius_mm"], f"{label}[{index}].measured_radius_mm",
            positive=True,
        )
        capture = _finite(
            row["capture_uncertainty_mm"],
            f"{label}[{index}].capture_uncertainty_mm",
            nonnegative=True,
        )
        deformation = _finite(
            row["unobserved_deformation_mm"],
            f"{label}[{index}].unobserved_deformation_mm",
            nonnegative=True,
        )
        capsules.append(
            CapsuleMm(
                _vector(row["start_mm"], f"{label}[{index}].start_mm"),
                _vector(row["end_mm"], f"{label}[{index}].end_mm"),
                measured + capture + deformation,
            )
        )
    return tuple(capsules)


def _geometry_by_body(
    value: object,
    *,
    required_body_ids: list[str],
    source_hashes: Mapping[str, str],
    label: str,
) -> tuple[dict[str, MeasuredConfigurationGeometryBinding], dict[str, Any]]:
    rows = _bounded_list(value, label, maximum=128)
    bindings: dict[str, MeasuredConfigurationGeometryBinding] = {}
    normalized: dict[str, Any] = {}
    for index, raw in enumerate(rows):
        row = _exact(raw, _BODY_FIELDS, f"{label}[{index}]")
        body_id = row["body_id"]
        source_id = row["source_id"]
        if (
            not isinstance(body_id, str) or body_id in bindings
            or not isinstance(source_id, str) or source_id not in source_hashes
        ):
            raise C03CableEnvelopeIntakeV1Error(f"{label} body/source identity is invalid")
        capsules = _capsules(row["capsules"], f"{label}[{index}].capsules")
        geometry = SampledCollisionGeometry(
            capsules,
            CollisionEvidenceState.ACCEPTED_MEASURED,
            f"C03 cable evidence source {source_id}:{source_hashes[source_id]}",
        )
        bindings[body_id] = MeasuredConfigurationGeometryBinding(
            body_id, geometry, source_hashes[source_id]
        )
        normalized[body_id] = {
            "source_sha256": source_hashes[source_id],
            "inflated_capsules": [item.to_dict() for item in capsules],
        }
    if sorted(bindings) != required_body_ids:
        raise C03CableEnvelopeIntakeV1Error(f"{label} body coverage differs")
    return bindings, normalized


@dataclass(frozen=True, slots=True)
class C03CableEnvelopeIntakeV1Result:
    """Typed evidence and zero-authority admission report for later ICQ stages."""

    report: Mapping[str, Any]
    configuration_samples_by_partition: tuple[
        tuple[MeasuredSegmentConfigurationSample, ...], ...
    ]
    sweep_envelopes_by_partition: tuple[
        tuple[Mapping[str, MeasuredConfigurationSweepEnvelopeBinding], ...], ...
    ]


def validate_c03_cable_envelope_intake_v1(
    document: Mapping[str, Any],
    qualification: Mapping[str, Any],
    rigid_binding_report: Mapping[str, Any],
    *,
    file_sha256: str,
    evaluated_at_utc: str,
) -> C03CableEnvelopeIntakeV1Result:
    """Validate a complete measured cable manifest against the exact C03 route."""

    qualified = _validated_hash_report(
        qualification,
        schema=QUALIFICATION_SCHEMA,
        hash_field="c03_installed_collision_qualification_sha256",
        status=READY_FOR_EVIDENCE_STATUS,
        label="installed collision qualification",
    )
    rigid = _validated_hash_report(
        rigid_binding_report,
        schema=RIGID_REPORT_SCHEMA,
        hash_field="c03_rigid_attachment_binding_report_sha256",
        status=RIGID_READY_STATUS,
        label="rigid attachment report",
    )
    root = _exact(document, _ROOT_FIELDS, "cable manifest")
    if root["schema"] != SCHEMA:
        raise C03CableEnvelopeIntakeV1Error("cable manifest schema mismatch")
    claimed_content = _digest(root["content_sha256"], "content_sha256")
    unsigned = {key: value for key, value in root.items() if key != "content_sha256"}
    if claimed_content != _sha(unsigned):
        raise C03CableEnvelopeIntakeV1Error("cable manifest content hash mismatch")
    if not isinstance(root["cable_manifest_id"], str) or not root["cable_manifest_id"]:
        raise C03CableEnvelopeIntakeV1Error("cable_manifest_id is invalid")

    intake = qualified["c03_collision_handoff"]["collision_intake"]
    expected = {
        "c03_installed_collision_qualification_sha256": qualified[
            "c03_installed_collision_qualification_sha256"
        ],
        "c03_rigid_attachment_binding_report_sha256": rigid[
            "c03_rigid_attachment_binding_report_sha256"
        ],
        "partitioned_typing_collision_intake_sha256": intake[
            "partitioned_typing_collision_intake_sha256"
        ],
        "collision_contract_sha256": intake["collision_contract_sha256"],
        "installed_collision_profile_content_sha256": intake[
            "installed_collision_profile_sha256"
        ],
        "installed_collision_profile_file_sha256": qualified["profile_file_sha256"],
        "measurement_manifest_file_sha256": qualified[
            "measurement_manifest_file_sha256"
        ],
        "measurement_manifest_content_sha256": qualified[
            "measurement_manifest_content_sha256"
        ],
        "root_frame": rigid["root_frame"],
    }
    if any(root[key] != value for key, value in expected.items()):
        raise C03CableEnvelopeIntakeV1Error("cable manifest lineage differs")
    if rigid["c03_installed_collision_qualification_sha256"] != expected[
        "c03_installed_collision_qualification_sha256"
    ]:
        raise C03CableEnvelopeIntakeV1Error("rigid report qualification lineage differs")

    captured = _timestamp(root["captured_at_utc"], "captured_at_utc")
    valid_until = _timestamp(root["valid_until_utc"], "valid_until_utc")
    evaluated = _timestamp(evaluated_at_utc, "evaluated_at_utc")
    if not captured <= evaluated <= valid_until:
        raise C03CableEnvelopeIntakeV1Error("cable manifest is stale or future dated")

    accepted_sources = set(intake["accepted_profile_source_sha256_values"])
    source_hashes: dict[str, str] = {}
    source_times: dict[str, datetime] = {}
    for index, raw in enumerate(_bounded_list(root["sources"], "sources", maximum=128)):
        row = _exact(raw, _SOURCE_FIELDS, f"sources[{index}]")
        source_id = row["source_id"]
        digest = _digest(row["sha256"], f"sources[{index}].sha256")
        if (
            not isinstance(source_id, str) or not source_id or source_id in source_hashes
            or digest not in accepted_sources
        ):
            raise C03CableEnvelopeIntakeV1Error("source identity is invalid or unbound")
        when = _timestamp(row["captured_at_utc"], f"sources[{index}].captured_at_utc")
        if when > captured or not isinstance(row["method"], str) or not row["method"]:
            raise C03CableEnvelopeIntakeV1Error("source chronology or method is invalid")
        if not isinstance(row["notes"], str):
            raise C03CableEnvelopeIntakeV1Error("source notes must be text")
        source_hashes[source_id] = digest
        source_times[source_id] = when

    partitions = intake["partitions"]
    required_body_ids = sorted(intake["required_configuration_body_ids"])
    expected_samples: dict[tuple[int, int], dict[str, Any]] = {}
    expected_sweeps: dict[tuple[int, int], dict[str, Any]] = {}
    owned_sequence = 0
    for partition in partitions:
        partition_index = partition["partition_index"]
        plan = partition["bounded_joint_sample_plan"]
        for sample_sequence, sample in enumerate(plan):
            expected_samples[(partition_index, sample_sequence)] = {
                "sample_plan_sha256": _sha(sample),
                "sample": sample,
            }
        for segment_sequence, (start, end) in enumerate(zip(plan, plan[1:])):
            expected_sweeps[(partition_index, segment_sequence)] = {
                "owned_segment_sequence": owned_sequence,
                "start_sample_sha256": _sha(start),
                "end_sample_sha256": _sha(end),
            }
            owned_sequence += 1

    sample_rows = _bounded_list(root["samples"], "samples")
    if len(sample_rows) != len(expected_samples):
        raise C03CableEnvelopeIntakeV1Error("sample evidence coverage differs")
    expected_sample_keys = list(expected_samples)
    samples_by_partition: list[list[MeasuredSegmentConfigurationSample]] = [
        [] for _ in partitions
    ]
    normalized_samples: dict[tuple[int, int], dict[str, Any]] = {}
    for index, raw in enumerate(sample_rows):
        row = _exact(raw, _SAMPLE_FIELDS, f"samples[{index}]")
        key = (
            _integer(row["partition_index"], "partition_index"),
            _integer(row["sample_sequence"], "sample_sequence"),
        )
        expected_sample = expected_samples.get(key)
        if (
            expected_sample is None
            or key in normalized_samples
            or key != expected_sample_keys[index]
        ):
            raise C03CableEnvelopeIntakeV1Error("sample identity is unexpected or duplicated")
        if (
            row["method"] != _SAMPLE_METHOD
            or _digest(row["sample_plan_sha256"], "sample_plan_sha256")
            != expected_sample["sample_plan_sha256"]
        ):
            raise C03CableEnvelopeIntakeV1Error("sample posture lineage differs")
        when = _timestamp(row["captured_at_utc"], "sample captured_at_utc")
        if when > captured:
            raise C03CableEnvelopeIntakeV1Error("sample is newer than its manifest")
        bindings, normalized = _geometry_by_body(
            row["bodies"], required_body_ids=required_body_ids,
            source_hashes=source_hashes, label=f"samples[{index}].bodies",
        )
        if any(source_times[next(
            source_id for source_id, digest in source_hashes.items()
            if digest == binding.source_sha256
        )] > when for binding in bindings.values()):
            raise C03CableEnvelopeIntakeV1Error("sample/source chronology is invalid")
        normalized_samples[key] = normalized
        samples_by_partition[key[0]].append(
            MeasuredSegmentConfigurationSample(key[1], row["sample_plan_sha256"], bindings)
        )

    for partition_index, rows in enumerate(samples_by_partition):
        if [row.sample_sequence for row in rows] != list(range(len(rows))):
            raise C03CableEnvelopeIntakeV1Error("sample rows are not canonically ordered")

    sweep_rows = _bounded_list(root["sweeps"], "sweeps")
    if len(sweep_rows) != len(expected_sweeps):
        raise C03CableEnvelopeIntakeV1Error("sweep evidence coverage differs")
    expected_sweep_keys = list(expected_sweeps)
    sweeps_by_partition: list[
        list[Mapping[str, MeasuredConfigurationSweepEnvelopeBinding]]
    ] = [[] for _ in partitions]
    seen_sweeps: set[tuple[int, int]] = set()
    normalized_sweeps: list[dict[str, Any]] = []
    for index, raw in enumerate(sweep_rows):
        row = _exact(raw, _SWEEP_FIELDS, f"sweeps[{index}]")
        key = (
            _integer(row["partition_index"], "partition_index"),
            _integer(row["segment_sequence"], "segment_sequence"),
        )
        expected_sweep = expected_sweeps.get(key)
        if (
            expected_sweep is None
            or key in seen_sweeps
            or key != expected_sweep_keys[index]
        ):
            raise C03CableEnvelopeIntakeV1Error("sweep identity is unexpected or duplicated")
        seen_sweeps.add(key)
        if (
            row["construction_method"] not in _SWEEP_METHODS
            or _integer(
                row["intermediate_observation_count"],
                "intermediate_observation_count", minimum=1,
            ) < 1
        ):
            raise C03CableEnvelopeIntakeV1Error(
                "endpoint-only sweep interpolation is insufficient"
            )
        for field in (
            "owned_segment_sequence", "start_sample_sha256", "end_sample_sha256"
        ):
            if row[field] != expected_sweep[field]:
                raise C03CableEnvelopeIntakeV1Error("sweep sample-pair lineage differs")
        when = _timestamp(row["captured_at_utc"], "sweep captured_at_utc")
        if when > captured:
            raise C03CableEnvelopeIntakeV1Error("sweep is newer than its manifest")
        bindings, normalized = _geometry_by_body(
            row["bodies"], required_body_ids=required_body_ids,
            source_hashes=source_hashes, label=f"sweeps[{index}].bodies",
        )
        converted: dict[str, MeasuredConfigurationSweepEnvelopeBinding] = {}
        for body_id, binding in bindings.items():
            converted[body_id] = MeasuredConfigurationSweepEnvelopeBinding(
                key[1], row["start_sample_sha256"], row["end_sample_sha256"],
                body_id, binding.geometry, binding.source_sha256,
            )
        sweeps_by_partition[key[0]].append(converted)
        normalized_sweeps.append({
            "partition_index": key[0], "segment_sequence": key[1],
            "owned_segment_sequence": row["owned_segment_sequence"],
            "inflated_geometry_by_body": normalized,
        })

    for partition_index, rows in enumerate(sweeps_by_partition):
        expected_count = len(partitions[partition_index]["bounded_joint_sample_plan"]) - 1
        if len(rows) != expected_count:
            raise C03CableEnvelopeIntakeV1Error("sweep rows are not canonically ordered")

    boundary_checks: list[dict[str, Any]] = []
    for boundary in intake["boundary_lineage"]:
        predecessor = boundary["predecessor_partition_index"]
        successor = boundary["successor_partition_index"]
        left_key = (predecessor, len(partitions[predecessor]["bounded_joint_sample_plan"]) - 1)
        right_key = (successor, 0)
        if normalized_samples[left_key] != normalized_samples[right_key]:
            raise C03CableEnvelopeIntakeV1Error(
                "shared-boundary cable geometry differs across partitions"
            )
        boundary_checks.append({
            "predecessor_partition_index": predecessor,
            "successor_partition_index": successor,
            "sample_sha256": boundary["predecessor_terminal_sample_sha256"],
            "inflated_geometry_sha256": _sha(normalized_samples[left_key]),
            "exact_match": True,
        })

    report_core: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": READY_STATUS,
        "cable_manifest_id": root["cable_manifest_id"],
        "cable_manifest_file_sha256": _digest(file_sha256, "file_sha256"),
        "cable_manifest_content_sha256": claimed_content,
        **expected,
        "required_configuration_body_ids": required_body_ids,
        "partition_count": len(partitions),
        "sample_count_including_boundary_rechecks": len(expected_samples),
        "owned_segment_count": len(expected_sweeps),
        "boundary_recheck_count": len(boundary_checks),
        "boundary_rechecks": boundary_checks,
        "inflation_method": (
            "measured_radius_plus_capture_uncertainty_plus_unobserved_deformation"
        ),
        "sweep_construction_methods": sorted({
            row["construction_method"] for row in sweep_rows
        }),
        "source_bindings": dict(sorted(source_hashes.items())),
        "configuration_sample_binding_sha256_by_partition": [
            [
                _sha({
                    "sample_sequence": item.sample_sequence,
                    "sample_plan_sha256": item.sample_plan_sha256,
                    "geometry_binding_sha256_by_body": {
                        body_id: item.geometry_by_body[body_id].content_sha256
                        for body_id in sorted(item.geometry_by_body)
                    },
                })
                for item in rows
            ]
            for rows in samples_by_partition
        ],
        "configuration_sweep_binding_sha256_by_partition": [
            [
                _sha({
                    "geometry_binding_sha256_by_body": {
                        body_id: item[body_id].content_sha256
                        for body_id in sorted(item)
                    },
                })
                for item in rows
            ]
            for rows in sweeps_by_partition
        ],
        "installed_geometry_collision_screening_executed": False,
        "continuous_collision_proven": False,
        "installed_collision_gate_cleared": False,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    report = {
        **report_core,
        "c03_cable_envelope_intake_report_sha256": _sha(report_core),
    }
    return C03CableEnvelopeIntakeV1Result(
        report,
        tuple(tuple(rows) for rows in samples_by_partition),
        tuple(tuple(rows) for rows in sweeps_by_partition),
    )


def load_c03_cable_envelope_intake_v1(
    path: str | Path,
    expected_file_sha256: str,
    qualification: Mapping[str, Any],
    rigid_binding_report: Mapping[str, Any],
    *,
    evaluated_at_utc: str,
) -> C03CableEnvelopeIntakeV1Result:
    """Load exact manifest bytes and validate the complete C03 cable evidence."""

    expected = _digest(expected_file_sha256, "expected_file_sha256")
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise C03CableEnvelopeIntakeV1Error("cable manifest file is missing")
    payload = manifest_path.read_bytes()
    if len(payload) > MAX_BYTES:
        raise C03CableEnvelopeIntakeV1Error("cable manifest exceeds byte limit")
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise C03CableEnvelopeIntakeV1Error("cable manifest file hash mismatch")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise C03CableEnvelopeIntakeV1Error(f"duplicate JSON field {key!r}")
            result[key] = value
        return result

    try:
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise C03CableEnvelopeIntakeV1Error("cable manifest is invalid JSON") from exc
    if not isinstance(document, dict):
        raise C03CableEnvelopeIntakeV1Error("cable manifest root must be an object")
    return validate_c03_cable_envelope_intake_v1(
        document, qualification, rigid_binding_report,
        file_sha256=actual, evaluated_at_utc=evaluated_at_utc,
    )


__all__ = [
    "MAX_BYTES", "READY_STATUS", "REPORT_SCHEMA", "SCHEMA",
    "C03CableEnvelopeIntakeV1Error", "C03CableEnvelopeIntakeV1Result",
    "load_c03_cable_envelope_intake_v1", "validate_c03_cable_envelope_intake_v1",
]
