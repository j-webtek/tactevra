"""Render blank, profile-separated evidence templates for collision partitions.

This boundary consumes the completed output of
``fixed_camera_keyboard_profiled_collision_partitions_v1``.  It verifies the
receipt, manifest, and both partition intakes byte-for-byte, then enumerates
every measured binding required by the existing collision evaluators.  The
result contains null measurement fields only.  It does not infer geometry,
evaluate collision, access hardware, or grant physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from .fixed_camera_keyboard_clearance_intake_v1 import SUPPORTED_PROFILES
from .fixed_camera_keyboard_profiled_collision_partitions_v1 import (
    MANIFEST_NAME as SOURCE_MANIFEST_NAME,
    PARTITION_NAMES as SOURCE_PARTITION_NAMES,
    RECEIPT_NAME as SOURCE_RECEIPT_NAME,
    RECEIPT_SCHEMA as SOURCE_RECEIPT_SCHEMA,
    RECEIPT_STATUS as SOURCE_RECEIPT_STATUS,
    SCHEMA as SOURCE_MANIFEST_SCHEMA,
    STATUS as SOURCE_STATUS,
    ZERO_AUTHORITY as SOURCE_ZERO_AUTHORITY,
)
from .partitioned_typing_collision_intake_v1 import (
    READY_STATUS as PARTITION_READY_STATUS,
    SCHEMA as PARTITION_SCHEMA,
)


SCHEMA = "rocell.fixed_camera_keyboard_profiled_collision_evidence_template_manifest.v1"
STATUS = "BLANK_PROFILED_COLLISION_EVIDENCE_TEMPLATE_READY"
RECEIPT_SCHEMA = (
    "rocell.fixed_camera_keyboard_profiled_collision_evidence_template_receipt.v1"
)
RECEIPT_STATUS = "PROFILED_COLLISION_EVIDENCE_TEMPLATE_ADMITTED"
TEMPLATE_SCHEMA = "rocell.profile_bound_partitioned_collision_evidence_template.v1"
TEMPLATE_STATUS = "BLANK_MEASURED_COLLISION_EVIDENCE_REQUIRED"
MANIFEST_NAME = "profiled-collision-evidence-template-manifest.json"
RECEIPT_NAME = "profiled-collision-evidence-template-receipt.json"
TEMPLATE_NAMES = {
    "no_attachment": "no-attachment-collision-evidence-template.json",
    "stylus_attachment": "stylus-attachment-collision-evidence-template.json",
}
MAX_JSON_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
ZERO_AUTHORITY: Mapping[str, object] = {
    "blank_template_rendered_offline": True,
    "measured_collision_evidence_supplied": False,
    "installed_geometry_collision_screening_executed": False,
    "continuous_collision_proven": False,
    "fresh_observed_start_state_present": False,
    "controller_commands": [],
    "hardware_commands_generated": 0,
    "hardware_access": False,
    "physical_authority": False,
    "physical_release_effect": "NONE",
}


class FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(ValueError):
    """The partition bundle cannot safely form blank evidence templates."""


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
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _reject_constant(value: str) -> None:
    raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
        f"collision partition input contains nonfinite constant {value!r}"
    )


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
                f"collision partition input contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _read_json(
    path: str | Path, *, expected_sha256: str, label: str
) -> tuple[Path, bytes, Mapping[str, Any]]:
    source = Path(path).expanduser()
    expected = _digest(expected_sha256, f"expected_{label}_file_sha256")
    if source.is_symlink():
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"{label} path must not be a symlink"
        )
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"cannot inspect {label} file: {exc}"
        ) from exc
    if not source.is_file() or size <= 0 or size > MAX_JSON_BYTES:
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"{label} file size is invalid"
        )
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"cannot read {label} file: {exc}"
        ) from exc
    if len(payload) != size or _sha_bytes(payload) != expected:
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"{label} bytes differ from expected file SHA-256"
        )
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"{label} must be a JSON object"
        )
    return source.resolve(), payload, value


def _profile_map(value: Mapping[str, Any], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != set(SUPPORTED_PROFILES):
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"{label} must contain the exact supported profile set"
        )


def _unique_text_list(value: object, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or len(set(value)) != len(value)
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"{label} must be a unique nonempty text array"
        )
    return list(value)


def _validate_partition_report(report: Mapping[str, Any], profile: str) -> None:
    unsigned = dict(report)
    claimed = unsigned.pop("partitioned_typing_collision_intake_sha256", None)
    if (
        report.get("schema") != PARTITION_SCHEMA
        or report.get("status") != PARTITION_READY_STATUS
        or claimed != _sha(unsigned)
        or report.get("installed_geometry_collision_screening_executed") is not False
        or report.get("continuous_collision_proven") is not False
        or report.get("installed_collision_gate_cleared") is not False
        or report.get("controller_commands") != []
        or report.get("hardware_commands_generated") != 0
        or report.get("hardware_access") is not False
        or report.get("physical_authority") is not False
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"partition intake is invalid or authority-bearing: {profile}"
        )
    _digest(report.get("installed_collision_profile_sha256"), "installed profile")
    _digest(report.get("collision_contract_sha256"), "collision contract")
    accepted = _unique_text_list(
        report.get("accepted_profile_source_sha256_values"),
        f"{profile} accepted source hashes",
    )
    for digest in accepted:
        _digest(digest, f"{profile} accepted source hash")
    rigid = _unique_text_list(
        report.get("required_rigid_attachment_frames"),
        f"{profile} rigid attachment frames",
    )
    bodies = _unique_text_list(
        report.get("required_configuration_body_ids"),
        f"{profile} configuration body ids",
    )
    partitions = report.get("partitions")
    boundaries = report.get("boundary_lineage")
    if (
        not isinstance(partitions, list)
        or not partitions
        or not isinstance(boundaries, list)
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"{profile} partition or boundary inventory is invalid"
        )
    sample_total = segment_total = geometry_total = sweep_total = 0
    for expected_index, partition in enumerate(partitions):
        if not isinstance(partition, Mapping):
            raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
                f"{profile} partition must be an object"
            )
        partition_unsigned = dict(partition)
        partition_claimed = partition_unsigned.pop("partition_intake_sha256", None)
        samples = partition.get("bounded_joint_sample_plan")
        slots = partition.get("required_evidence_slots")
        if (
            partition.get("partition_index") != expected_index
            or partition_claimed != _sha(partition_unsigned)
            or not isinstance(samples, list)
            or not samples
            or not isinstance(slots, Mapping)
            or partition.get("bounded_sample_count") != len(samples)
        ):
            raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
                f"{profile} partition lineage is invalid at {expected_index}"
            )
        hashes: list[str] = []
        for sequence, sample in enumerate(samples):
            if (
                not isinstance(sample, Mapping)
                or sample.get("sample_sequence") != sequence
            ):
                raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
                    f"{profile} sample sequence is invalid"
                )
            hashes.append(_sha(sample))
        adjacent = max(0, len(samples) - 1)
        expected_slots = {
            "configuration_sample_count": len(samples),
            "configuration_body_count_per_sample": len(bodies),
            "configuration_geometry_binding_count": len(samples) * len(bodies),
            "adjacent_sample_segment_count": adjacent,
            "configuration_sweep_envelope_count": adjacent * len(bodies),
        }
        if (
            dict(slots) != expected_slots
            or partition.get("first_sample_sha256") != hashes[0]
            or partition.get("terminal_sample_sha256") != hashes[-1]
        ):
            raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
                f"{profile} evidence slot inventory is invalid"
            )
        sample_total += len(samples)
        segment_total += adjacent
        geometry_total += len(samples) * len(bodies)
        sweep_total += adjacent * len(bodies)
    if len(boundaries) != len(partitions) - 1:
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"{profile} boundary lineage count is invalid"
        )
    for index, boundary in enumerate(boundaries):
        if not isinstance(boundary, Mapping):
            raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
                f"{profile} boundary lineage must be an object"
            )
        unsigned_boundary = dict(boundary)
        claimed_boundary = unsigned_boundary.pop("boundary_lineage_sha256", None)
        predecessor = partitions[index]
        successor = partitions[index + 1]
        if (
            claimed_boundary != _sha(unsigned_boundary)
            or boundary.get("predecessor_partition_index") != index
            or boundary.get("successor_partition_index") != index + 1
            or boundary.get("predecessor_terminal_sample_sha256")
            != predecessor.get("terminal_sample_sha256")
            or boundary.get("successor_boundary_recheck_sample_sha256")
            != successor.get("first_sample_sha256")
            or boundary.get("maximum_joint_difference_rad") != 0.0
            or boundary.get("boundary_recheck_required") is not True
            or boundary.get("extra_zero_length_sweep_envelope_required") is not False
        ):
            raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
                f"{profile} boundary lineage is invalid at {index}"
            )
    totals = report.get("required_evidence_slots")
    if not isinstance(totals, Mapping) or any(
        totals.get(key) != value
        for key, value in {
            "partition_count": len(partitions),
            "partition_sample_count_including_boundary_rechecks": sample_total,
            "conservative_boundary_recheck_count": len(boundaries),
            "partition_owned_adjacent_sample_segment_count": segment_total,
            "configuration_geometry_binding_count": geometry_total,
            "configuration_sweep_envelope_count": sweep_total,
        }.items()
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"{profile} total evidence slot inventory is invalid"
        )
    if not rigid and not bodies:
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"{profile} has no measured evidence requirements"
        )


def _validate_source(
    receipt_path: Path,
    receipt: Mapping[str, Any],
    manifest_path: Path,
    manifest_bytes: bytes,
    manifest: Mapping[str, Any],
    partition_sources: Mapping[str, tuple[Path, bytes, Mapping[str, Any]]],
) -> None:
    if (
        receipt_path.name != SOURCE_RECEIPT_NAME
        or manifest_path.name != SOURCE_MANIFEST_NAME
        or receipt_path.parent != manifest_path.parent
        or any(
            path.parent != receipt_path.parent
            for path, _, _ in partition_sources.values()
        )
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            "receipt, manifest, and partition intakes must be the named co-located bundle"
        )
    if (
        receipt.get("schema") != SOURCE_RECEIPT_SCHEMA
        or receipt.get("status") != SOURCE_RECEIPT_STATUS
        or receipt.get("profile_separation_preserved") is not True
        or receipt.get("authority") != SOURCE_ZERO_AUTHORITY
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            "collision partition receipt is invalid or authority-bearing"
        )
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            "collision partition receipt artifacts must be an object"
        )
    bound_manifest = artifacts.get("profiled_collision_partitions_manifest")
    if (
        not isinstance(bound_manifest, Mapping)
        or bound_manifest.get("name") != SOURCE_MANIFEST_NAME
        or bound_manifest.get("size_bytes") != len(manifest_bytes)
        or bound_manifest.get("file_sha256") != _sha_bytes(manifest_bytes)
        or bound_manifest.get("meaning_sha256") != _sha(manifest)
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            "collision partition manifest differs from its receipt"
        )
    unsigned = dict(manifest)
    claimed = unsigned.pop("profiled_collision_partitions_manifest_sha256", None)
    profiles = manifest.get("profiles")
    if (
        manifest.get("schema") != SOURCE_MANIFEST_SCHEMA
        or manifest.get("status") != SOURCE_STATUS
        or claimed != _sha(unsigned)
        or manifest.get("profile_separation_preserved") is not True
        or manifest.get("authority") != SOURCE_ZERO_AUTHORITY
        or not isinstance(profiles, Mapping)
        or set(profiles) != set(SUPPORTED_PROFILES)
    ):
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            "collision partition manifest is invalid or authority-bearing"
        )
    profile_hashes: set[str] = set()
    for profile in SUPPORTED_PROFILES:
        path, payload, report = partition_sources[profile]
        row = profiles[profile]
        bound = artifacts.get(f"{profile}_partitioned_collision_intake")
        if not isinstance(row, Mapping) or not isinstance(bound, Mapping):
            raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
                f"collision partition binding is missing: {profile}"
            )
        _validate_partition_report(report, profile)
        if (
            path.name != SOURCE_PARTITION_NAMES[profile]
            or bound.get("name") != path.name
            or bound.get("size_bytes") != len(payload)
            or bound.get("file_sha256") != _sha_bytes(payload)
            or bound.get("meaning_sha256")
            != report.get("partitioned_typing_collision_intake_sha256")
            or row.get("partitioned_typing_collision_intake_file_sha256")
            != _sha_bytes(payload)
            or row.get("partitioned_typing_collision_intake_sha256")
            != report.get("partitioned_typing_collision_intake_sha256")
            or row.get("installed_collision_profile_content_sha256")
            != report.get("installed_collision_profile_sha256")
            or row.get("collision_contract_sha256")
            != report.get("collision_contract_sha256")
            or row.get("required_evidence_slots")
            != report.get("required_evidence_slots")
            or row.get("boundary_lineage") != report.get("boundary_lineage")
        ):
            raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
                f"collision partition binding differs: {profile}"
            )
        profile_hashes.add(str(report["installed_collision_profile_sha256"]))
    if len(profile_hashes) != len(SUPPORTED_PROFILES):
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            "attachment states require distinct installed collision profiles"
        )


def _template(profile: str, report: Mapping[str, Any]) -> dict[str, Any]:
    bodies = list(report["required_configuration_body_ids"])
    rigid_rows = [
        {
            "parent_frame": frame,
            "anchor_link_frame": None,
            "anchor_t_parent": None,
            "source_sha256": None,
            "source_reference": None,
            "evidence_state": "REQUIRED_MEASURED_INPUT",
        }
        for frame in report["required_rigid_attachment_frames"]
    ]
    partition_rows: list[dict[str, Any]] = []
    for partition in report["partitions"]:
        samples = partition["bounded_joint_sample_plan"]
        configuration_rows = []
        for sample in samples:
            sample_sha = _sha(sample)
            configuration_rows.append(
                {
                    "sample_sequence": sample["sample_sequence"],
                    "sample_id": sample["sample_id"],
                    "sample_plan_sha256": sample_sha,
                    "geometry_by_body": [
                        {
                            "body_id": body,
                            "geometry_root_frame": None,
                            "source_sha256": None,
                            "evidence_state": "REQUIRED_MEASURED_INPUT",
                        }
                        for body in bodies
                    ],
                }
            )
        sweep_rows = []
        for segment_sequence, (start, end) in enumerate(
            zip(samples, samples[1:], strict=False)
        ):
            sweep_rows.append(
                {
                    "segment_sequence": segment_sequence,
                    "start_sample_sha256": _sha(start),
                    "end_sample_sha256": _sha(end),
                    "envelope_by_body": [
                        {
                            "body_id": body,
                            "geometry_root_frame": None,
                            "source_sha256": None,
                            "evidence_state": "REQUIRED_MEASURED_INPUT",
                        }
                        for body in bodies
                    ],
                }
            )
        partition_rows.append(
            {
                "partition_index": partition["partition_index"],
                "partition_sha256": partition["partition_sha256"],
                "partition_intake_sha256": partition["partition_intake_sha256"],
                "configuration_samples": configuration_rows,
                "configuration_sweep_envelopes": sweep_rows,
            }
        )
    core: dict[str, Any] = {
        "schema": TEMPLATE_SCHEMA,
        "status": TEMPLATE_STATUS,
        "profile": profile,
        "source_partitioned_typing_collision_intake_sha256": report[
            "partitioned_typing_collision_intake_sha256"
        ],
        "installed_collision_profile_sha256": report[
            "installed_collision_profile_sha256"
        ],
        "collision_contract_sha256": report["collision_contract_sha256"],
        "accepted_profile_source_sha256_values": report[
            "accepted_profile_source_sha256_values"
        ],
        "rigid_attachment_bindings": rigid_rows,
        "partitions": partition_rows,
        "boundary_lineage": report["boundary_lineage"],
        "required_evidence_slots": {
            **report["required_evidence_slots"],
            "rigid_attachment_binding_count": len(rigid_rows),
        },
        "completion_rule": (
            "Replace every null measurement field using independently reviewed "
            "evidence whose SHA-256 is accepted by this exact installed profile; "
            "a blank template is never collision evidence."
        ),
        "next_required_stage": "SUPPLY_AND_ADMIT_EXACT_MEASURED_COLLISION_EVIDENCE",
        "authority": dict(ZERO_AUTHORITY),
    }
    return {**core, "profiled_collision_evidence_template_sha256": _sha(core)}


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            f"cannot publish new evidence template file {path.name}: {exc}"
        ) from exc


@dataclass(frozen=True, slots=True)
class FixedCameraKeyboardProfiledCollisionEvidenceTemplateResultV1:
    output_directory: Path
    template_paths: Mapping[str, Path]
    manifest_path: Path
    receipt_path: Path
    templates: Mapping[str, Mapping[str, Any]]
    manifest: Mapping[str, Any]
    receipt: Mapping[str, Any]


def render_fixed_camera_keyboard_profiled_collision_evidence_templates_v1(
    collision_partitions_receipt_path: str | Path,
    *,
    expected_collision_partitions_receipt_file_sha256: str,
    collision_partitions_manifest_path: str | Path,
    expected_collision_partitions_manifest_file_sha256: str,
    partition_intake_paths: Mapping[str, str | Path],
    expected_partition_intake_file_sha256: Mapping[str, str],
    output_directory: str | Path,
) -> FixedCameraKeyboardProfiledCollisionEvidenceTemplateResultV1:
    """Verify a partition bundle and publish blank per-profile evidence slots."""

    _profile_map(partition_intake_paths, "partition_intake_paths")
    _profile_map(
        expected_partition_intake_file_sha256,
        "expected_partition_intake_file_sha256",
    )
    receipt_source, receipt_bytes, receipt = _read_json(
        collision_partitions_receipt_path,
        expected_sha256=expected_collision_partitions_receipt_file_sha256,
        label="collision partitions receipt",
    )
    manifest_source, manifest_bytes, source_manifest = _read_json(
        collision_partitions_manifest_path,
        expected_sha256=expected_collision_partitions_manifest_file_sha256,
        label="collision partitions manifest",
    )
    partition_sources = {
        profile: _read_json(
            partition_intake_paths[profile],
            expected_sha256=expected_partition_intake_file_sha256[profile],
            label=f"{profile} partition intake",
        )
        for profile in SUPPORTED_PROFILES
    }
    _validate_source(
        receipt_source,
        receipt,
        manifest_source,
        manifest_bytes,
        source_manifest,
        partition_sources,
    )

    templates = {
        profile: _template(profile, partition_sources[profile][2])
        for profile in SUPPORTED_PROFILES
    }
    template_payloads = {
        profile: _canonical(template, newline=True)
        for profile, template in templates.items()
    }
    profiles = {
        profile: {
            "profile": profile,
            "installed_collision_profile_sha256": template[
                "installed_collision_profile_sha256"
            ],
            "source_partitioned_typing_collision_intake_sha256": template[
                "source_partitioned_typing_collision_intake_sha256"
            ],
            "profiled_collision_evidence_template_sha256": template[
                "profiled_collision_evidence_template_sha256"
            ],
            "profiled_collision_evidence_template_file_sha256": _sha_bytes(
                template_payloads[profile]
            ),
            "required_evidence_slots": template["required_evidence_slots"],
        }
        for profile, template in templates.items()
    }
    manifest_core: Mapping[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "source_profiled_collision_partitions_manifest_sha256": source_manifest[
            "profiled_collision_partitions_manifest_sha256"
        ],
        "profiles": profiles,
        "profile_separation_preserved": True,
        "all_measurement_fields_blank": True,
        "next_required_stage": "SUPPLY_AND_ADMIT_EXACT_MEASURED_COLLISION_EVIDENCE",
        "authority": dict(ZERO_AUTHORITY),
    }
    manifest = {
        **manifest_core,
        "profiled_collision_evidence_template_manifest_sha256": _sha(manifest_core),
    }
    manifest_payload = _canonical(manifest, newline=True)
    receipt_out: Mapping[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "status": RECEIPT_STATUS,
        "sources": {
            "collision_partitions_receipt": {
                "name": receipt_source.name,
                "size_bytes": len(receipt_bytes),
                "file_sha256": _sha_bytes(receipt_bytes),
            },
            "collision_partitions_manifest": {
                "name": manifest_source.name,
                "size_bytes": len(manifest_bytes),
                "file_sha256": _sha_bytes(manifest_bytes),
            },
            **{
                f"{profile}_partitioned_collision_intake": {
                    "name": path.name,
                    "size_bytes": len(payload),
                    "file_sha256": _sha_bytes(payload),
                }
                for profile, (path, payload, _) in partition_sources.items()
            },
        },
        "artifacts": {
            **{
                f"{profile}_collision_evidence_template": {
                    "name": TEMPLATE_NAMES[profile],
                    "size_bytes": len(template_payloads[profile]),
                    "file_sha256": _sha_bytes(template_payloads[profile]),
                    "meaning_sha256": templates[profile][
                        "profiled_collision_evidence_template_sha256"
                    ],
                }
                for profile in SUPPORTED_PROFILES
            },
            "profiled_collision_evidence_template_manifest": {
                "name": MANIFEST_NAME,
                "size_bytes": len(manifest_payload),
                "file_sha256": _sha_bytes(manifest_payload),
                "meaning_sha256": _sha(manifest),
            },
            "completion_receipt": {"name": RECEIPT_NAME, "written_last": True},
        },
        "profile_separation_preserved": True,
        "all_measurement_fields_blank": True,
        "next_required_stage": "SUPPLY_AND_ADMIT_EXACT_MEASURED_COLLISION_EVIDENCE",
        "authority": dict(ZERO_AUTHORITY),
    }
    receipt_payload = _canonical(receipt_out, newline=True)

    requested = Path(output_directory).expanduser()
    if not requested.name or requested.name in (".", ".."):
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            "output_directory must name a new directory"
        )
    parent = requested.parent.resolve()
    if not parent.is_dir():
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            "output_directory parent must already exist"
        )
    destination = parent / requested.name
    if destination.exists() or destination.is_symlink():
        raise FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error(
            "output_directory already exists; refusing to overwrite"
        )
    try:
        destination.mkdir(mode=0o700, exist_ok=False)
        template_paths = {
            profile: destination / TEMPLATE_NAMES[profile]
            for profile in SUPPORTED_PROFILES
        }
        for profile in SUPPORTED_PROFILES:
            _write_new(template_paths[profile], template_payloads[profile])
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
    return FixedCameraKeyboardProfiledCollisionEvidenceTemplateResultV1(
        destination,
        template_paths,
        manifest_path,
        receipt_path,
        templates,
        manifest,
        receipt_out,
    )


__all__ = [
    "MANIFEST_NAME",
    "RECEIPT_NAME",
    "RECEIPT_STATUS",
    "STATUS",
    "TEMPLATE_NAMES",
    "TEMPLATE_SCHEMA",
    "TEMPLATE_STATUS",
    "ZERO_AUTHORITY",
    "FixedCameraKeyboardProfiledCollisionEvidenceTemplateResultV1",
    "FixedCameraKeyboardProfiledCollisionEvidenceTemplateV1Error",
    "render_fixed_camera_keyboard_profiled_collision_evidence_templates_v1",
]
