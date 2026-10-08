"""Compose the fail-closed physical evidence checklist for the exact C03 route.

This module reuses the reviewed ICQ-1 through ICQ-4 validators.  It exposes the
remaining capture population and lineage in one deterministic packet.  It does
not synthesize measurements, run collision evaluation, access hardware, or
grant execution authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .bounded_segment_collision_qualification import BoundedSegmentSamplingPolicy
from .c03_cable_envelope_intake_v1 import load_c03_cable_envelope_intake_v1
from .c03_installed_collision_qualification_v1 import (
    READY_FOR_EVIDENCE_STATUS,
    prepare_c03_installed_collision_qualification_v1,
)
from .c03_rigid_attachment_binding_v1 import (
    READY_STATUS as RIGID_READY_STATUS,
    load_c03_rigid_attachment_binding_v1,
)
from .collision_readiness import assess_current_collision_readiness
from .context import SimulationContext, load_simulation_context


SCHEMA = "tactevra.c03_physical_evidence_packet.v1"
BLOCKED_MEASUREMENTS = "BLOCKED_INSTALLED_MEASUREMENTS_REQUIRED"
BLOCKED_RIGID = "BLOCKED_RIGID_ATTACHMENT_BINDINGS_REQUIRED"
BLOCKED_CABLE = "BLOCKED_CABLE_SAMPLE_AND_SWEEP_EVIDENCE_REQUIRED"
READY_FOR_EVALUATION = "READY_FOR_ZERO_AUTHORITY_COLLISION_EVALUATION"
MAX_ROUTE_RESULT_BYTES = 32 * 1024 * 1024


class C03PhysicalEvidencePacketV1Error(ValueError):
    """Physical evidence inputs are incomplete, crossed, or ambiguous."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _atomic_path_hash(
    path: str | Path | None,
    digest: str | None,
    label: str,
) -> bool:
    supplied = path is not None
    if supplied != (digest is not None):
        raise C03PhysicalEvidencePacketV1Error(
            f"{label} path and SHA-256 must be supplied together"
        )
    return supplied


def load_c03_route_result_v1(
    path: str | Path,
    expected_file_sha256: str,
) -> dict[str, Any]:
    """Load bounded route-result bytes with exact hash and duplicate-key checks."""

    if (
        not isinstance(expected_file_sha256, str)
        or len(expected_file_sha256) != 64
        or any(char not in "0123456789abcdef" for char in expected_file_sha256)
    ):
        raise C03PhysicalEvidencePacketV1Error(
            "route result SHA-256 must be lowercase hexadecimal"
        )
    route_path = Path(path)
    try:
        payload = route_path.read_bytes()
    except OSError as exc:
        raise C03PhysicalEvidencePacketV1Error(
            "cannot read route result"
        ) from exc
    if not payload or len(payload) > MAX_ROUTE_RESULT_BYTES:
        raise C03PhysicalEvidencePacketV1Error(
            "route result must be nonempty and within the byte limit"
        )
    if hashlib.sha256(payload).hexdigest() != expected_file_sha256:
        raise C03PhysicalEvidencePacketV1Error("route result file hash mismatch")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise C03PhysicalEvidencePacketV1Error(
                    f"duplicate route result field {key!r}"
                )
            result[key] = value
        return result

    try:
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise C03PhysicalEvidencePacketV1Error(
            "route result is invalid UTF-8 JSON"
        ) from exc
    if not isinstance(document, dict):
        raise C03PhysicalEvidencePacketV1Error("route result root must be an object")
    return document


def build_c03_physical_evidence_packet_v1(
    result: Mapping[str, Any],
    context: SimulationContext,
    *,
    measurement_manifest_path: str | Path | None = None,
    expected_measurement_manifest_file_sha256: str | None = None,
    rigid_binding_manifest_path: str | Path | None = None,
    expected_rigid_binding_manifest_file_sha256: str | None = None,
    cable_manifest_path: str | Path | None = None,
    expected_cable_manifest_file_sha256: str | None = None,
    evaluated_at_utc: str | None = None,
    sampling_policy: BoundedSegmentSamplingPolicy | None = None,
    maximum_partitions: int = 64,
) -> dict[str, Any]:
    """Validate supplied evidence in dependency order and describe what remains."""

    measurement_supplied = _atomic_path_hash(
        measurement_manifest_path,
        expected_measurement_manifest_file_sha256,
        "measurement manifest",
    )
    rigid_supplied = _atomic_path_hash(
        rigid_binding_manifest_path,
        expected_rigid_binding_manifest_file_sha256,
        "rigid binding manifest",
    )
    cable_supplied = _atomic_path_hash(
        cable_manifest_path,
        expected_cable_manifest_file_sha256,
        "cable manifest",
    )
    if (rigid_supplied or cable_supplied) and evaluated_at_utc is None:
        raise C03PhysicalEvidencePacketV1Error(
            "evaluated_at_utc is required when rigid or cable evidence is supplied"
        )
    if rigid_supplied and not measurement_supplied:
        raise C03PhysicalEvidencePacketV1Error(
            "rigid binding evidence requires a supplied measurement manifest"
        )
    if cable_supplied and not rigid_supplied:
        raise C03PhysicalEvidencePacketV1Error(
            "cable evidence requires a supplied rigid binding manifest"
        )

    qualification = prepare_c03_installed_collision_qualification_v1(
        result,
        context,
        measurement_manifest_path=measurement_manifest_path,
        expected_measurement_manifest_file_sha256=(
            expected_measurement_manifest_file_sha256
        ),
        sampling_policy=sampling_policy,
        maximum_partitions=maximum_partitions,
    )
    intake = qualification["c03_collision_handoff"]["collision_intake"]
    rigid_report = None
    cable_result = None
    if rigid_supplied:
        if qualification["status"] != READY_FOR_EVIDENCE_STATUS:
            raise C03PhysicalEvidencePacketV1Error(
                "rigid binding evidence cannot precede complete installed measurements"
            )
        rigid_report = load_c03_rigid_attachment_binding_v1(
            rigid_binding_manifest_path,
            expected_rigid_binding_manifest_file_sha256,
            qualification,
            context=context,
            evaluated_at_utc=evaluated_at_utc,
        )
    if cable_supplied:
        if rigid_report is None or rigid_report["status"] != RIGID_READY_STATUS:
            raise C03PhysicalEvidencePacketV1Error(
                "cable evidence cannot precede ready rigid attachment evidence"
            )
        cable_result = load_c03_cable_envelope_intake_v1(
            cable_manifest_path,
            expected_cable_manifest_file_sha256,
            qualification,
            rigid_report,
            evaluated_at_utc=evaluated_at_utc,
        )

    if qualification["status"] != READY_FOR_EVIDENCE_STATUS:
        status = BLOCKED_MEASUREMENTS
        next_stage = "CAPTURE_COMPLETE_INSTALLED_COLLISION_MEASUREMENTS"
    elif rigid_report is None:
        status = BLOCKED_RIGID
        next_stage = "CAPTURE_HASH_BOUND_RIGID_ATTACHMENT_TRANSFORMS"
    elif cable_result is None:
        status = BLOCKED_CABLE
        next_stage = "CAPTURE_ALL_CONFIGURATION_CABLE_SAMPLES_AND_SWEEPS"
    else:
        status = READY_FOR_EVALUATION
        next_stage = "RUN_ICQ5_PARTITION_AND_ICQ6_CONTINUOUS_COLLISION_EVALUATION"

    contract = assess_current_collision_readiness(context).contract
    stages = [
        {
            "stage": "ICQ-1/2",
            "evidence": "installed collision measurements and derived profile",
            "status": (
                "READY"
                if qualification["status"] == READY_FOR_EVIDENCE_STATUS
                else "MISSING_OR_INCOMPLETE"
            ),
        },
        {
            "stage": "ICQ-3",
            "evidence": "root-frame rigid attachment transforms",
            "status": "READY" if rigid_report is not None else "MISSING",
        },
        {
            "stage": "ICQ-4",
            "evidence": "configuration cable samples and conservative sweeps",
            "status": "READY" if cable_result is not None else "MISSING",
        },
        {
            "stage": "ICQ-5/6",
            "evidence": "partition and continuous collision receipts",
            "status": "NOT_RUN",
        },
        {
            "stage": "ICQ-7/7.1",
            "evidence": "fresh observed entry state and numeric entry clearance",
            "status": "NOT_CAPTURED",
        },
        {
            "stage": "ICQ-8/9",
            "evidence": "aggregate PASS followed by physical execution review",
            "status": "BLOCKED",
        },
    ]
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "source_result_receipt_sha256": qualification["c03_collision_handoff"][
            "source_result_receipt_sha256"
        ],
        "source_route_receipt_sha256": qualification["c03_collision_handoff"][
            "source_route_receipt_sha256"
        ],
        "collision_contract_sha256": contract.content_hash,
        "ordered_targets": qualification["c03_collision_handoff"]["ordered_targets"],
        "measurement_manifest_file_sha256": qualification[
            "measurement_manifest_file_sha256"
        ],
        "installed_collision_profile_file_sha256": qualification[
            "profile_file_sha256"
        ],
        "rigid_binding_manifest_file_sha256": (
            None if rigid_report is None else rigid_report["binding_manifest_file_sha256"]
        ),
        "cable_manifest_file_sha256": (
            None if cable_result is None else cable_result.report["cable_manifest_file_sha256"]
        ),
        "installed_body_requirements": [
            requirement.to_dict() for requirement in contract.requirements
        ],
        "required_rigid_attachment_frames": intake[
            "required_rigid_attachment_frames"
        ],
        "required_configuration_body_ids": intake[
            "required_configuration_body_ids"
        ],
        "required_partitioned_evidence_slots": intake["required_evidence_slots"],
        "fresh_observed_entry_requirement": {
            "required": True,
            "source_kind": "OBSERVED_MEASURED",
            "must_postdate_state_changing_actions": True,
            "synthetic_or_nominal_start_is_execution_eligible": False,
        },
        "stages": stages,
        "blockers": [
            stage["evidence"]
            for stage in stages
            if stage["status"] not in {"READY"}
        ],
        "next_required_stage": next_stage,
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
    return {**core, "c03_physical_evidence_packet_sha256": _sha(core)}


def render_c03_physical_evidence_packet_markdown_v1(
    packet: Mapping[str, Any],
) -> str:
    """Render a compact operator checklist from a generated packet."""

    lines = [
        "# C03 physical evidence readiness packet",
        "",
        f"- Status: `{packet['status']}`",
        f"- Collision contract: `{packet['collision_contract_sha256']}`",
        f"- Next stage: `{packet['next_required_stage']}`",
        "- Authority: read only; zero commands, writes, or physical movement",
        "",
        "| Stage | Evidence | Status |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| {row['stage']} | {row['evidence']} | `{row['status']}` |"
        for row in packet["stages"]
    )
    slots = packet["required_partitioned_evidence_slots"]
    lines.extend([
        "",
        "## Exact capture population",
        "",
        f"- Installed bodies: {len(packet['installed_body_requirements'])}",
        f"- Rigid attachment frames: {len(packet['required_rigid_attachment_frames'])}",
        f"- Configuration bodies per sample: {len(packet['required_configuration_body_ids'])}",
        f"- Partitions: {slots['partition_count']}",
        f"- Configuration sample bindings: {slots['configuration_geometry_binding_count']}",
        f"- Conservative sweep bindings: {slots['configuration_sweep_envelope_count']}",
        "- Fresh observed entry state: required after state-changing actions",
        "",
        "This packet does not qualify measurements or authorize execution.",
    ])
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Generate one read-only readiness packet from caller hash-bound files."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--system-manifest", type=Path)
    parser.add_argument("--route-result", type=Path, required=True)
    parser.add_argument("--route-result-sha256", required=True)
    parser.add_argument("--measurement-manifest", type=Path)
    parser.add_argument("--measurement-manifest-sha256")
    parser.add_argument("--rigid-binding-manifest", type=Path)
    parser.add_argument("--rigid-binding-manifest-sha256")
    parser.add_argument("--cable-manifest", type=Path)
    parser.add_argument("--cable-manifest-sha256")
    parser.add_argument("--evaluated-at-utc")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    system_manifest = args.system_manifest or (
        args.workspace / "software/config/system_manifest.json"
    )
    try:
        context = load_simulation_context(args.workspace, system_manifest)
        route = load_c03_route_result_v1(
            args.route_result, args.route_result_sha256
        )
        packet = build_c03_physical_evidence_packet_v1(
            route,
            context,
            measurement_manifest_path=args.measurement_manifest,
            expected_measurement_manifest_file_sha256=(
                args.measurement_manifest_sha256
            ),
            rigid_binding_manifest_path=args.rigid_binding_manifest,
            expected_rigid_binding_manifest_file_sha256=(
                args.rigid_binding_manifest_sha256
            ),
            cable_manifest_path=args.cable_manifest,
            expected_cable_manifest_file_sha256=args.cable_manifest_sha256,
            evaluated_at_utc=args.evaluated_at_utc,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.format == "markdown":
        print(render_c03_physical_evidence_packet_markdown_v1(packet), end="")
    else:
        print(json.dumps(packet, indent=2, sort_keys=True))
    return 0 if packet["status"] == READY_FOR_EVALUATION else 2


__all__ = [
    "BLOCKED_CABLE",
    "BLOCKED_MEASUREMENTS",
    "BLOCKED_RIGID",
    "MAX_ROUTE_RESULT_BYTES",
    "READY_FOR_EVALUATION",
    "SCHEMA",
    "C03PhysicalEvidencePacketV1Error",
    "build_c03_physical_evidence_packet_v1",
    "load_c03_route_result_v1",
    "main",
    "render_c03_physical_evidence_packet_markdown_v1",
]
