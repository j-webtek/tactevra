"""Admit reviewed, profile-separated measured collision evidence.

The file boundary verifies the blank template bundle, a completed evidence file,
and a disjoint review file for each attachment profile.  It decodes only the
existing typed collision inputs.  It does not run an evaluator, access hardware,
or grant motion authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from rocell.geometry import RigidTransform, Rotation3, Vec3
from rocell.simulation.collision import (
    CapsuleMm,
    CollisionEvidenceState,
    OrientedBoxMm,
    SampledCollisionGeometry,
    SphereMm,
)

from .conservative_segment_sweep_qualification import (
    MeasuredConfigurationSweepEnvelopeBinding,
)
from .fixed_camera_keyboard_clearance_intake_v1 import SUPPORTED_PROFILES
from .fixed_camera_keyboard_profiled_collision_evidence_template_v1 import (
    MANIFEST_NAME as TEMPLATE_MANIFEST_NAME,
    RECEIPT_NAME as TEMPLATE_RECEIPT_NAME,
    RECEIPT_SCHEMA as TEMPLATE_RECEIPT_SCHEMA,
    RECEIPT_STATUS as TEMPLATE_RECEIPT_STATUS,
    SCHEMA as TEMPLATE_MANIFEST_SCHEMA,
    STATUS as TEMPLATE_MANIFEST_STATUS,
    TEMPLATE_NAMES,
    TEMPLATE_SCHEMA,
    TEMPLATE_STATUS,
    ZERO_AUTHORITY as TEMPLATE_ZERO_AUTHORITY,
)
from .fk_collision_pose_adapter import (
    MeasuredConfigurationGeometryBinding,
    MeasuredRigidAttachmentBinding,
)


SCHEMA = (
    "rocell.fixed_camera_keyboard_profiled_collision_evidence_admission_manifest.v1"
)
STATUS = "PROFILED_MEASURED_COLLISION_EVIDENCE_ADMITTED"
RECEIPT_SCHEMA = (
    "rocell.fixed_camera_keyboard_profiled_collision_evidence_admission_receipt.v1"
)
RECEIPT_STATUS = "PROFILED_MEASURED_COLLISION_EVIDENCE_ADMISSION_COMPLETE"
COMPLETION_SCHEMA = "rocell.profile_bound_partitioned_collision_evidence_completion.v1"
COMPLETION_STATUS = "COMPLETED_MEASURED_COLLISION_EVIDENCE"
REVIEW_SCHEMA = "rocell.profile_bound_collision_evidence_independent_review.v1"
REVIEW_STATUS = "INDEPENDENT_COLLISION_EVIDENCE_REVIEW_ACCEPTED"
MANIFEST_NAME = "profiled-collision-evidence-admission-manifest.json"
RECEIPT_NAME = "profiled-collision-evidence-admission-receipt.json"
COMPLETION_NAMES = {
    "no_attachment": "no-attachment-collision-evidence-completion.json",
    "stylus_attachment": "stylus-attachment-collision-evidence-completion.json",
}
REVIEW_NAMES = {
    "no_attachment": "no-attachment-collision-evidence-review.json",
    "stylus_attachment": "stylus-attachment-collision-evidence-review.json",
}
MAX_JSON_BYTES = 32 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
ZERO_AUTHORITY: Mapping[str, object] = {
    "measured_collision_evidence_admitted": True,
    "installed_geometry_collision_screening_executed": False,
    "continuous_collision_proven": False,
    "fresh_observed_start_state_present": False,
    "controller_commands": [],
    "hardware_commands_generated": 0,
    "hardware_access": False,
    "physical_authority": False,
    "physical_release_effect": "NONE",
}


class FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(ValueError):
    """Profiled collision evidence is incomplete, crossed, or unreviewed."""


def _canonical(value: object, *, newline: bool = False) -> bytes:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return payload + (b"\n" if newline else b"")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(value: object) -> str:
    return _sha_bytes(_canonical(value))


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} must be nonempty unpadded text"
        )
    return value


def _reject_constant(value: str) -> None:
    raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
        f"collision evidence contains nonfinite constant {value!r}"
    )


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                f"collision evidence contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _read_json(
    path: str | Path, *, expected_sha256: str, label: str
) -> tuple[Path, bytes, Mapping[str, Any]]:
    source = Path(path).expanduser()
    expected = _digest(expected_sha256, f"expected_{label}_file_sha256")
    if source.is_symlink():
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} path must not be a symlink"
        )
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"cannot inspect {label}: {exc}"
        ) from exc
    if not source.is_file() or size <= 0 or size > MAX_JSON_BYTES:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} file size is invalid"
        )
    payload = source.read_bytes()
    if len(payload) != size or _sha_bytes(payload) != expected:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} bytes differ from expected SHA-256"
        )
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} must be a JSON object"
        )
    return source.resolve(), payload, value


def _exact(value: object, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} fields differ from the closed schema"
        )
    return value


def _profile_map(value: Mapping[str, Any], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != set(SUPPORTED_PROFILES):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} must contain the exact supported profile set"
        )


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} must be a finite number"
        )
    result = float(value)
    if not (-float("inf") < result < float("inf")):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} must be finite"
        )
    return result


def _vec(value: object, label: str) -> Vec3:
    if not isinstance(value, list) or len(value) != 3:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} must contain exactly three numbers"
        )
    return Vec3(*(_number(item, label) for item in value))


def _transform(value: object, anchor: str, parent: str) -> RigidTransform:
    row = _exact(
        value,
        {"parent_frame", "child_frame", "rotation_row_major", "translation_mm"},
        "attachment transform",
    )
    if row["parent_frame"] != anchor or row["child_frame"] != parent:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            "attachment transform frame direction differs from its declaration"
        )
    rotation = row["rotation_row_major"]
    if not isinstance(rotation, list) or len(rotation) != 9:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            "attachment rotation must contain exactly nine numbers"
        )
    try:
        return RigidTransform(
            anchor,
            parent,
            Rotation3(tuple(_number(item, "attachment rotation") for item in rotation)),
            _vec(row["translation_mm"], "attachment translation_mm"),
        )
    except (TypeError, ValueError) as exc:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            "attachment transform is not rigid"
        ) from exc


def _primitive(value: object, label: str):
    if not isinstance(value, Mapping):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} must be an object"
        )
    try:
        if value.get("kind") == "sphere" and set(value) == {
            "kind",
            "center_mm",
            "radius_mm",
        }:
            return SphereMm(
                _vec(value["center_mm"], label), _number(value["radius_mm"], label)
            )
        if value.get("kind") == "capsule" and set(value) == {
            "kind",
            "start_mm",
            "end_mm",
            "radius_mm",
        }:
            return CapsuleMm(
                _vec(value["start_mm"], label),
                _vec(value["end_mm"], label),
                _number(value["radius_mm"], label),
            )
        if value.get("kind") == "oriented_box" and set(value) == {
            "kind",
            "center_mm",
            "half_extents_mm",
            "rotation_row_major",
        }:
            rotation = value["rotation_row_major"]
            if not isinstance(rotation, list) or len(rotation) != 9:
                raise ValueError
            return OrientedBoxMm(
                _vec(value["center_mm"], label),
                _vec(value["half_extents_mm"], label),
                Rotation3(tuple(_number(item, label) for item in rotation)),
            )
    except (TypeError, ValueError) as exc:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} is invalid"
        ) from exc
    raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
        f"{label} has an unsupported primitive schema"
    )


def _geometry(value: object, label: str) -> SampledCollisionGeometry:
    row = _exact(
        value,
        {"evidence_state", "source_reference", "primitives"},
        label,
    )
    if row["evidence_state"] != CollisionEvidenceState.ACCEPTED_MEASURED.value:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} must use accepted measured evidence"
        )
    raw = row["primitives"]
    if not isinstance(raw, list) or not raw:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} primitives must be a nonempty array"
        )
    try:
        return SampledCollisionGeometry(
            tuple(
                _primitive(item, f"{label} primitive {index}")
                for index, item in enumerate(raw)
            ),
            CollisionEvidenceState.ACCEPTED_MEASURED,
            _text(row["source_reference"], f"{label} source_reference"),
        )
    except (TypeError, ValueError) as exc:
        if isinstance(
            exc, FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error
        ):
            raise
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{label} geometry is invalid"
        ) from exc


@dataclass(frozen=True, slots=True)
class AdmittedProfileCollisionEvidenceV1:
    profile: str
    attachment_bindings: tuple[MeasuredRigidAttachmentBinding, ...]
    configuration_geometry_by_partition: tuple[
        tuple[Mapping[str, MeasuredConfigurationGeometryBinding], ...], ...
    ]
    sweep_envelopes_by_partition: tuple[
        tuple[Mapping[str, MeasuredConfigurationSweepEnvelopeBinding], ...], ...
    ]
    completion_sha256: str
    review_sha256: str


@dataclass(frozen=True, slots=True)
class FixedCameraKeyboardProfiledCollisionEvidenceAdmissionResultV1:
    output_directory: Path
    manifest_path: Path
    receipt_path: Path
    admitted_profiles: Mapping[str, AdmittedProfileCollisionEvidenceV1]
    manifest: Mapping[str, Any]
    receipt: Mapping[str, Any]


def _validate_template_bundle(
    receipt_path: Path,
    receipt: Mapping[str, Any],
    manifest_path: Path,
    manifest_bytes: bytes,
    manifest: Mapping[str, Any],
    templates: Mapping[str, tuple[Path, bytes, Mapping[str, Any]]],
) -> None:
    if (
        receipt_path.name != TEMPLATE_RECEIPT_NAME
        or manifest_path.name != TEMPLATE_MANIFEST_NAME
        or receipt_path.parent != manifest_path.parent
        or any(path.parent != receipt_path.parent for path, _, _ in templates.values())
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            "template receipt, manifest, and templates must be the named co-located bundle"
        )
    if (
        receipt.get("schema") != TEMPLATE_RECEIPT_SCHEMA
        or receipt.get("status") != TEMPLATE_RECEIPT_STATUS
        or receipt.get("profile_separation_preserved") is not True
        or receipt.get("all_measurement_fields_blank") is not True
        or receipt.get("authority") != TEMPLATE_ZERO_AUTHORITY
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            "template receipt is invalid or authority-bearing"
        )
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            "template receipt artifacts must be an object"
        )
    bound_manifest = artifacts.get("profiled_collision_evidence_template_manifest")
    unsigned_manifest = dict(manifest)
    claimed_manifest = unsigned_manifest.pop(
        "profiled_collision_evidence_template_manifest_sha256", None
    )
    profiles = manifest.get("profiles")
    if (
        not isinstance(bound_manifest, Mapping)
        or bound_manifest.get("name") != TEMPLATE_MANIFEST_NAME
        or bound_manifest.get("size_bytes") != len(manifest_bytes)
        or bound_manifest.get("file_sha256") != _sha_bytes(manifest_bytes)
        or bound_manifest.get("meaning_sha256") != _sha(manifest)
        or manifest.get("schema") != TEMPLATE_MANIFEST_SCHEMA
        or manifest.get("status") != TEMPLATE_MANIFEST_STATUS
        or claimed_manifest != _sha(unsigned_manifest)
        or manifest.get("profile_separation_preserved") is not True
        or manifest.get("all_measurement_fields_blank") is not True
        or manifest.get("authority") != TEMPLATE_ZERO_AUTHORITY
        or not isinstance(profiles, Mapping)
        or set(profiles) != set(SUPPORTED_PROFILES)
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            "template manifest is invalid or differs from its receipt"
        )
    installed_hashes: set[str] = set()
    for profile in SUPPORTED_PROFILES:
        path, payload, template = templates[profile]
        row = profiles[profile]
        bound = artifacts.get(f"{profile}_collision_evidence_template")
        unsigned_template = dict(template)
        claimed_template = unsigned_template.pop(
            "profiled_collision_evidence_template_sha256", None
        )
        if (
            path.name != TEMPLATE_NAMES[profile]
            or not isinstance(row, Mapping)
            or not isinstance(bound, Mapping)
            or bound.get("name") != path.name
            or bound.get("size_bytes") != len(payload)
            or bound.get("file_sha256") != _sha_bytes(payload)
            or bound.get("meaning_sha256") != claimed_template
            or template.get("schema") != TEMPLATE_SCHEMA
            or template.get("status") != TEMPLATE_STATUS
            or template.get("profile") != profile
            or claimed_template != _sha(unsigned_template)
            or template.get("authority") != TEMPLATE_ZERO_AUTHORITY
            or row.get("installed_collision_profile_sha256")
            != template.get("installed_collision_profile_sha256")
            or row.get("source_partitioned_typing_collision_intake_sha256")
            != template.get("source_partitioned_typing_collision_intake_sha256")
            or row.get("profiled_collision_evidence_template_sha256")
            != claimed_template
            or row.get("profiled_collision_evidence_template_file_sha256")
            != _sha_bytes(payload)
            or row.get("required_evidence_slots")
            != template.get("required_evidence_slots")
        ):
            raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                f"template binding differs: {profile}"
            )
        installed_hashes.add(
            _digest(
                template.get("installed_collision_profile_sha256"),
                f"{profile} installed profile",
            )
        )
    if len(installed_hashes) != len(SUPPORTED_PROFILES):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            "attachment profiles are not distinct"
        )


def _matching_fields(
    completion: Mapping[str, Any], template: Mapping[str, Any]
) -> None:
    for field in (
        "profile",
        "source_partitioned_typing_collision_intake_sha256",
        "installed_collision_profile_sha256",
        "collision_contract_sha256",
        "accepted_profile_source_sha256_values",
        "boundary_lineage",
        "required_evidence_slots",
    ):
        if completion.get(field) != template.get(field):
            raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                f"completed evidence differs from template field {field}"
            )


def _decode_completion(
    profile: str,
    completion: Mapping[str, Any],
    template: Mapping[str, Any],
) -> tuple[AdmittedProfileCollisionEvidenceV1, str]:
    expected_keys = set(template) - {
        "profiled_collision_evidence_template_sha256",
        "completion_rule",
        "next_required_stage",
    }
    expected_keys.update(
        {
            "source_profiled_collision_evidence_template_sha256",
            "measurement_producer_id",
            "completion_sha256",
        }
    )
    row = _exact(completion, expected_keys, f"{profile} completed evidence")
    if (
        row["schema"] != COMPLETION_SCHEMA
        or row["status"] != COMPLETION_STATUS
        or row["profile"] != profile
        or row["source_profiled_collision_evidence_template_sha256"]
        != template["profiled_collision_evidence_template_sha256"]
        or row["authority"] != ZERO_AUTHORITY
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{profile} completion is invalid or authority-bearing"
        )
    _matching_fields(row, template)
    producer = _text(row["measurement_producer_id"], f"{profile} producer")
    unsigned = dict(row)
    claimed = unsigned.pop("completion_sha256")
    if claimed != _sha(unsigned):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{profile} completion hash is invalid"
        )
    accepted = {
        _digest(item, f"{profile} accepted source")
        for item in row["accepted_profile_source_sha256_values"]
    }
    if len(accepted) != len(row["accepted_profile_source_sha256_values"]):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{profile} accepted sources contain duplicates"
        )

    template_rigid = template["rigid_attachment_bindings"]
    raw_rigid = row["rigid_attachment_bindings"]
    if not isinstance(raw_rigid, list) or len(raw_rigid) != len(template_rigid):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{profile} rigid attachment coverage differs"
        )
    bindings: list[MeasuredRigidAttachmentBinding] = []
    for index, (raw, slot) in enumerate(zip(raw_rigid, template_rigid, strict=True)):
        binding = _exact(
            raw,
            {
                "parent_frame",
                "anchor_link_frame",
                "anchor_t_parent",
                "source_sha256",
                "source_reference",
                "evidence_state",
            },
            f"{profile} rigid binding {index}",
        )
        if (
            binding["parent_frame"] != slot["parent_frame"]
            or binding["evidence_state"] != "ACCEPTED_MEASURED"
        ):
            raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                f"{profile} rigid binding {index} differs from its slot"
            )
        source = _digest(binding["source_sha256"], "rigid binding source")
        if source not in accepted:
            raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                f"{profile} rigid binding source is absent from installed profile"
            )
        parent = _text(binding["parent_frame"], "parent_frame")
        anchor = _text(binding["anchor_link_frame"], "anchor_link_frame")
        bindings.append(
            MeasuredRigidAttachmentBinding(
                parent,
                anchor,
                _transform(binding["anchor_t_parent"], anchor, parent),
                source,
                _text(binding["source_reference"], "source_reference"),
            )
        )

    raw_partitions = row["partitions"]
    template_partitions = template["partitions"]
    if not isinstance(raw_partitions, list) or len(raw_partitions) != len(
        template_partitions
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{profile} partition coverage differs"
        )
    geometry_partitions = []
    sweep_partitions = []
    for partition_index, (raw_partition, slot_partition) in enumerate(
        zip(raw_partitions, template_partitions, strict=True)
    ):
        part = _exact(
            raw_partition,
            {
                "partition_index",
                "partition_sha256",
                "partition_intake_sha256",
                "configuration_samples",
                "configuration_sweep_envelopes",
            },
            f"{profile} partition {partition_index}",
        )
        for field in ("partition_index", "partition_sha256", "partition_intake_sha256"):
            if part[field] != slot_partition[field]:
                raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                    f"{profile} partition lineage differs at {partition_index}"
                )
        raw_samples = part["configuration_samples"]
        slot_samples = slot_partition["configuration_samples"]
        if not isinstance(raw_samples, list) or len(raw_samples) != len(slot_samples):
            raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                f"{profile} sample coverage differs at partition {partition_index}"
            )
        decoded_samples = []
        for sample_index, (raw_sample, slot_sample) in enumerate(
            zip(raw_samples, slot_samples, strict=True)
        ):
            sample = _exact(
                raw_sample,
                {
                    "sample_sequence",
                    "sample_id",
                    "sample_plan_sha256",
                    "geometry_by_body",
                },
                f"{profile} sample {partition_index}:{sample_index}",
            )
            for field in ("sample_sequence", "sample_id", "sample_plan_sha256"):
                if sample[field] != slot_sample[field]:
                    raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                        f"{profile} sample lineage differs at {partition_index}:{sample_index}"
                    )
            raw_bodies = sample["geometry_by_body"]
            slot_bodies = slot_sample["geometry_by_body"]
            if not isinstance(raw_bodies, list) or len(raw_bodies) != len(slot_bodies):
                raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                    f"{profile} geometry coverage differs"
                )
            decoded: dict[str, MeasuredConfigurationGeometryBinding] = {}
            for body_index, (raw_body, slot_body) in enumerate(
                zip(raw_bodies, slot_bodies, strict=True)
            ):
                body = _exact(
                    raw_body,
                    {
                        "body_id",
                        "geometry_root_frame",
                        "source_sha256",
                        "evidence_state",
                    },
                    f"{profile} geometry body {body_index}",
                )
                body_id = _text(body["body_id"], "body_id")
                source = _digest(body["source_sha256"], "geometry source")
                if source not in accepted:
                    raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                        f"{profile} geometry source is absent from installed profile"
                    )
                if (
                    body_id != slot_body["body_id"]
                    or body["evidence_state"] != "ACCEPTED_MEASURED"
                    or body_id in decoded
                ):
                    raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                        f"{profile} geometry binding differs at {partition_index}:{sample_index}"
                    )
                decoded[body_id] = MeasuredConfigurationGeometryBinding(
                    body_id,
                    _geometry(body["geometry_root_frame"], "configuration geometry"),
                    source,
                )
            decoded_samples.append(decoded)
        geometry_partitions.append(tuple(decoded_samples))

        raw_segments = part["configuration_sweep_envelopes"]
        slot_segments = slot_partition["configuration_sweep_envelopes"]
        if not isinstance(raw_segments, list) or len(raw_segments) != len(
            slot_segments
        ):
            raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                f"{profile} sweep coverage differs at partition {partition_index}"
            )
        decoded_segments = []
        for segment_index, (raw_segment, slot_segment) in enumerate(
            zip(raw_segments, slot_segments, strict=True)
        ):
            segment = _exact(
                raw_segment,
                {
                    "segment_sequence",
                    "start_sample_sha256",
                    "end_sample_sha256",
                    "envelope_by_body",
                },
                f"{profile} segment {partition_index}:{segment_index}",
            )
            for field in (
                "segment_sequence",
                "start_sample_sha256",
                "end_sample_sha256",
            ):
                if segment[field] != slot_segment[field]:
                    raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                        f"{profile} segment lineage differs at {partition_index}:{segment_index}"
                    )
            raw_bodies = segment["envelope_by_body"]
            slot_bodies = slot_segment["envelope_by_body"]
            if not isinstance(raw_bodies, list) or len(raw_bodies) != len(slot_bodies):
                raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                    f"{profile} sweep body coverage differs"
                )
            decoded: dict[str, MeasuredConfigurationSweepEnvelopeBinding] = {}
            for body_index, (raw_body, slot_body) in enumerate(
                zip(raw_bodies, slot_bodies, strict=True)
            ):
                body = _exact(
                    raw_body,
                    {
                        "body_id",
                        "geometry_root_frame",
                        "source_sha256",
                        "evidence_state",
                    },
                    f"{profile} sweep body {body_index}",
                )
                body_id = _text(body["body_id"], "body_id")
                source = _digest(body["source_sha256"], "sweep source")
                if source not in accepted:
                    raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                        f"{profile} sweep source is absent from installed profile"
                    )
                if (
                    body_id != slot_body["body_id"]
                    or body["evidence_state"] != "ACCEPTED_MEASURED"
                    or body_id in decoded
                ):
                    raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
                        f"{profile} sweep binding differs at {partition_index}:{segment_index}"
                    )
                decoded[body_id] = MeasuredConfigurationSweepEnvelopeBinding(
                    segment["segment_sequence"],
                    segment["start_sample_sha256"],
                    segment["end_sample_sha256"],
                    body_id,
                    _geometry(body["geometry_root_frame"], "sweep geometry"),
                    source,
                )
            decoded_segments.append(decoded)
        sweep_partitions.append(tuple(decoded_segments))

    return (
        AdmittedProfileCollisionEvidenceV1(
            profile,
            tuple(bindings),
            tuple(geometry_partitions),
            tuple(sweep_partitions),
            claimed,
            "",
        ),
        producer,
    )


def _validate_review(
    profile: str,
    review: Mapping[str, Any],
    *,
    completion_sha256: str,
    completion_file_sha256: str,
    producer_id: str,
) -> str:
    row = _exact(
        review,
        {
            "schema",
            "status",
            "profile",
            "completion_sha256",
            "completion_file_sha256",
            "measurement_producer_id",
            "independent_reviewer_id",
            "review_decision",
            "review_source_sha256",
            "physical_authority",
            "review_sha256",
        },
        f"{profile} independent review",
    )
    reviewer = _text(row["independent_reviewer_id"], f"{profile} reviewer")
    if (
        row["schema"] != REVIEW_SCHEMA
        or row["status"] != REVIEW_STATUS
        or row["profile"] != profile
        or row["completion_sha256"] != completion_sha256
        or row["completion_file_sha256"] != completion_file_sha256
        or row["measurement_producer_id"] != producer_id
        or row["review_decision"] != "ACCEPT"
        or row["physical_authority"] is not False
        or reviewer == producer_id
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{profile} review is not an independent acceptance of the exact completion"
        )
    _digest(row["review_source_sha256"], f"{profile} review source")
    unsigned = dict(row)
    claimed = unsigned.pop("review_sha256")
    if claimed != _sha(unsigned):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"{profile} review hash is invalid"
        )
    return claimed


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            f"cannot publish {path.name}: {exc}"
        ) from exc


def admit_fixed_camera_keyboard_profiled_collision_evidence_v1(
    template_receipt_path: str | Path,
    *,
    expected_template_receipt_file_sha256: str,
    template_manifest_path: str | Path,
    expected_template_manifest_file_sha256: str,
    template_paths: Mapping[str, str | Path],
    expected_template_file_sha256: Mapping[str, str],
    completion_paths: Mapping[str, str | Path],
    expected_completion_file_sha256: Mapping[str, str],
    review_paths: Mapping[str, str | Path],
    expected_review_file_sha256: Mapping[str, str],
    output_directory: str | Path,
) -> FixedCameraKeyboardProfiledCollisionEvidenceAdmissionResultV1:
    """Verify and decode exact reviewed evidence for both attachment profiles."""

    for value, label in (
        (template_paths, "template_paths"),
        (expected_template_file_sha256, "expected_template_file_sha256"),
        (completion_paths, "completion_paths"),
        (expected_completion_file_sha256, "expected_completion_file_sha256"),
        (review_paths, "review_paths"),
        (expected_review_file_sha256, "expected_review_file_sha256"),
    ):
        _profile_map(value, label)
    receipt_source, receipt_bytes, receipt = _read_json(
        template_receipt_path,
        expected_sha256=expected_template_receipt_file_sha256,
        label="template receipt",
    )
    manifest_source, manifest_bytes, template_manifest = _read_json(
        template_manifest_path,
        expected_sha256=expected_template_manifest_file_sha256,
        label="template manifest",
    )
    templates = {
        profile: _read_json(
            template_paths[profile],
            expected_sha256=expected_template_file_sha256[profile],
            label=f"{profile} template",
        )
        for profile in SUPPORTED_PROFILES
    }
    _validate_template_bundle(
        receipt_source,
        receipt,
        manifest_source,
        manifest_bytes,
        template_manifest,
        templates,
    )
    completions = {
        profile: _read_json(
            completion_paths[profile],
            expected_sha256=expected_completion_file_sha256[profile],
            label=f"{profile} completion",
        )
        for profile in SUPPORTED_PROFILES
    }
    reviews = {
        profile: _read_json(
            review_paths[profile],
            expected_sha256=expected_review_file_sha256[profile],
            label=f"{profile} review",
        )
        for profile in SUPPORTED_PROFILES
    }
    if any(
        path.name != COMPLETION_NAMES[profile]
        for profile, (path, _, _) in completions.items()
    ) or any(
        path.name != REVIEW_NAMES[profile] for profile, (path, _, _) in reviews.items()
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            "completion or review file names differ from the closed profile mapping"
        )

    admitted: dict[str, AdmittedProfileCollisionEvidenceV1] = {}
    producer_ids: set[str] = set()
    reviewer_ids: set[str] = set()
    for profile in SUPPORTED_PROFILES:
        _, completion_bytes, completion = completions[profile]
        decoded, producer = _decode_completion(
            profile, completion, templates[profile][2]
        )
        review_hash = _validate_review(
            profile,
            reviews[profile][2],
            completion_sha256=decoded.completion_sha256,
            completion_file_sha256=_sha_bytes(completion_bytes),
            producer_id=producer,
        )
        reviewer = reviews[profile][2]["independent_reviewer_id"]
        producer_ids.add(producer)
        reviewer_ids.add(reviewer)
        admitted[profile] = AdmittedProfileCollisionEvidenceV1(
            profile,
            decoded.attachment_bindings,
            decoded.configuration_geometry_by_partition,
            decoded.sweep_envelopes_by_partition,
            decoded.completion_sha256,
            review_hash,
        )
    if producer_ids & reviewer_ids:
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            "a measurement producer cannot review either attachment profile"
        )

    profile_rows = {
        profile: {
            "profile": profile,
            "installed_collision_profile_sha256": templates[profile][2][
                "installed_collision_profile_sha256"
            ],
            "source_profiled_collision_evidence_template_sha256": templates[profile][2][
                "profiled_collision_evidence_template_sha256"
            ],
            "completion_sha256": admitted[profile].completion_sha256,
            "completion_file_sha256": _sha_bytes(completions[profile][1]),
            "review_sha256": admitted[profile].review_sha256,
            "review_file_sha256": _sha_bytes(reviews[profile][1]),
            "required_evidence_slots": templates[profile][2]["required_evidence_slots"],
        }
        for profile in SUPPORTED_PROFILES
    }
    manifest_core: Mapping[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "source_profiled_collision_evidence_template_manifest_sha256": template_manifest[
            "profiled_collision_evidence_template_manifest_sha256"
        ],
        "profiles": profile_rows,
        "profile_separation_preserved": True,
        "independent_reviews_verified": True,
        "typed_evaluator_inputs_decoded": True,
        "next_required_stage": "RUN_PROFILE_BOUND_PARTITION_COLLISION_EVALUATORS",
        "authority": dict(ZERO_AUTHORITY),
    }
    manifest = {
        **manifest_core,
        "profiled_collision_evidence_admission_manifest_sha256": _sha(manifest_core),
    }
    manifest_payload = _canonical(manifest, newline=True)
    receipt_out: Mapping[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "status": RECEIPT_STATUS,
        "sources": {
            "template_receipt": {
                "name": receipt_source.name,
                "size_bytes": len(receipt_bytes),
                "file_sha256": _sha_bytes(receipt_bytes),
            },
            "template_manifest": {
                "name": manifest_source.name,
                "size_bytes": len(manifest_bytes),
                "file_sha256": _sha_bytes(manifest_bytes),
            },
            **{
                f"{profile}_template": {
                    "name": templates[profile][0].name,
                    "size_bytes": len(templates[profile][1]),
                    "file_sha256": _sha_bytes(templates[profile][1]),
                }
                for profile in SUPPORTED_PROFILES
            },
            **{
                f"{profile}_completion": {
                    "name": completions[profile][0].name,
                    "size_bytes": len(completions[profile][1]),
                    "file_sha256": _sha_bytes(completions[profile][1]),
                }
                for profile in SUPPORTED_PROFILES
            },
            **{
                f"{profile}_review": {
                    "name": reviews[profile][0].name,
                    "size_bytes": len(reviews[profile][1]),
                    "file_sha256": _sha_bytes(reviews[profile][1]),
                }
                for profile in SUPPORTED_PROFILES
            },
        },
        "artifacts": {
            "profiled_collision_evidence_admission_manifest": {
                "name": MANIFEST_NAME,
                "size_bytes": len(manifest_payload),
                "file_sha256": _sha_bytes(manifest_payload),
                "meaning_sha256": _sha(manifest),
            },
            "completion_receipt": {"name": RECEIPT_NAME, "written_last": True},
        },
        "profile_separation_preserved": True,
        "independent_reviews_verified": True,
        "next_required_stage": "RUN_PROFILE_BOUND_PARTITION_COLLISION_EVALUATORS",
        "authority": dict(ZERO_AUTHORITY),
    }
    receipt_payload = _canonical(receipt_out, newline=True)

    requested = Path(output_directory).expanduser()
    if not requested.name or requested.name in (".", ".."):
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            "output_directory must name a new directory"
        )
    parent = requested.parent.resolve()
    if not parent.is_dir():
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            "output_directory parent must already exist"
        )
    destination = parent / requested.name
    if destination.exists() or destination.is_symlink():
        raise FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error(
            "output_directory already exists; refusing to overwrite"
        )
    try:
        destination.mkdir(mode=0o700, exist_ok=False)
        manifest_path = destination / MANIFEST_NAME
        receipt_path = destination / RECEIPT_NAME
        _write_new(manifest_path, manifest_payload)
        _write_new(receipt_path, receipt_payload)
    except Exception:
        if destination.exists():
            for child in destination.iterdir():
                child.unlink(missing_ok=True)
            destination.rmdir()
        raise
    return FixedCameraKeyboardProfiledCollisionEvidenceAdmissionResultV1(
        destination,
        manifest_path,
        receipt_path,
        admitted,
        manifest,
        receipt_out,
    )


__all__ = [
    "COMPLETION_NAMES",
    "COMPLETION_SCHEMA",
    "COMPLETION_STATUS",
    "MANIFEST_NAME",
    "RECEIPT_NAME",
    "RECEIPT_STATUS",
    "REVIEW_NAMES",
    "REVIEW_SCHEMA",
    "REVIEW_STATUS",
    "STATUS",
    "ZERO_AUTHORITY",
    "AdmittedProfileCollisionEvidenceV1",
    "FixedCameraKeyboardProfiledCollisionEvidenceAdmissionResultV1",
    "FixedCameraKeyboardProfiledCollisionEvidenceAdmissionV1Error",
    "admit_fixed_camera_keyboard_profiled_collision_evidence_v1",
]
