"""Deterministic PC15 installed-geometry and cable intake rehearsal."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from rocell.geometry import Vec3
from rocell.simulation.collision import (
    CollisionBindingMode,
    CollisionBody,
    CollisionClearanceEvidenceState,
    CollisionClearancePolicy,
    CollisionEvidenceState,
    CollisionGeometryContract,
    SphereMm,
)

from .camera_arrival_consumer_emitters_v1 import (
    CameraArrivalConsumerEmitterV1Error,
    emit_installed_collision_consumer_receipt_v1,
)
from .camera_arrival_consumer_handoff_v1 import (
    build_camera_arrival_consumer_handoff_v1,
)
from .camera_arrival_kit_v1 import build_camera_arrival_kit_v1
from .collision_readiness import assess_current_collision_readiness
from .context import load_simulation_context
from .installed_cable_envelope_intake_v1 import (
    MAX_POSTURES,
    InstalledCableEnvelopeIntakeV1,
    InstalledCableEnvelopeIntakeV1Error,
    build_synthetic_cable_envelope_intake_v1,
)
from .installed_collision_geometry import InstalledCollisionGeometryProfile


SCHEMA = "rocell.installed_geometry_cable_rehearsal.v1"
EVIDENCE_CLASS = "SYNTHETIC_OFFLINE_ONLY"
WHEN = "2026-09-29T16:00:00Z"
_H = "a" * 64
CASE_EXPECTATIONS = MappingProxyType({
    "complete_templates": ("PASS", []),
    "missing_rigid_body": (
        "BLOCKED",
        ["GEOMETRY_REQUIRED_BODY_BINDING_MISSING:attachment:camera_holder"],
    ),
    "unknown_attachment_evidence": (
        "BLOCKED",
        ["GEOMETRY_REQUIRED_BODY_GEOMETRY_UNKNOWN:attachment:camera_holder"],
    ),
    "maximum_posture_boundary": ("PASS", [f"postures={MAX_POSTURES}"]),
    "missing_swept_segment": (
        "REJECTED",
        ["swept envelopes do not cover every adjacent posture pair"],
    ),
    "crossed_posture_lineage": (
        "REJECTED", ["sweep 0 lineage differs from adjacent postures"],
    ),
    "unknown_source_hash": (
        "REJECTED", ["cable source is absent from installed profile bindings"],
    ),
    "cable_used_as_rigid_geometry": (
        "REJECTED", ["cable intake can satisfy only the cable_envelope route"],
    ),
})
_REPORT_FIELDS = {
    "schema", "evidence_class", "case_count", "matched_count", "cases",
    "all_declared_cases_matched", "qualification_installed", "camera_opened",
    "transport_opened", "controller_started", "controller_commands",
    "hardware_writes", "physical_movements", "physical_authority",
    "report_sha256",
}
_CASE_FIELDS = {"case_id", "expected", "observed", "matched", "detail"}


class InstalledGeometryCableRehearsalV1Error(ValueError):
    """Retained PC15 campaign content or semantics differ."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_synthetic_installed_collision_profile_v1(
    workspace: Path, *, omit_body_id: str | None = None,
    diagnostic_body_id: str | None = None,
) -> InstalledCollisionGeometryProfile:
    """Build complete far-field fixture geometry against the real base contract."""

    context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json"
    )
    readiness = assess_current_collision_readiness(context)
    bodies = []
    for index, requirement in enumerate(readiness.contract.requirements):
        if requirement.body_id == omit_body_id:
            continue
        primitives = ()
        if requirement.binding_mode is not CollisionBindingMode.CONFIGURATION_SAMPLED:
            primitives = (SphereMm(Vec3(50000.0 + 100.0 * index, 0.0, 0.0), 1.0),)
        state = (
            CollisionEvidenceState.UNKNOWN
            if requirement.body_id == diagnostic_body_id
            else CollisionEvidenceState.ACCEPTED_MEASURED
        )
        bodies.append(CollisionBody(
            requirement.body_id, requirement.parent_frame, requirement.role,
            state, primitives, requirement.binding_mode,
            "synthetic PC15 metrology template",
        ))
    contract = CollisionGeometryContract(
        "pc15-synthetic-installed-contract", readiness.contract.root_frame,
        readiness.contract.requirements, tuple(bodies), (),
    )
    sources = {
        "synthetic_attachment_review": "1" * 64,
        "synthetic_cable_envelope": "2" * 64,
        "synthetic_rigid_geometry": "3" * 64,
        "synthetic_uncertainty_review": "4" * 64,
    }
    policy = CollisionClearancePolicy(
        2.0, 0.5, 0.5, CollisionClearanceEvidenceState.ACCEPTED_MEASURED,
        "synthetic PC15 uncertainty template",
    )
    content = _sha({
        "evidence_class": EVIDENCE_CLASS,
        "contract_sha256": contract.content_hash,
        "source_bindings": sources,
        "clearance_policy": policy.to_dict(),
    })
    return InstalledCollisionGeometryProfile(
        "pc15-synthetic-installed-profile", readiness.manifest_id,
        readiness.manifest_sha256, readiness.active_build_id,
        readiness.build_snapshot_hash, readiness.urdf_sha256,
        readiness.contract.content_hash, sources, contract, policy, content,
        _sha({"synthetic_profile": content}),
    )


def _populate_evidence(root: Path) -> None:
    for slot in build_camera_arrival_kit_v1()["slots"]:
        relative = f"sources/{slot['artifact_id']}.bin"
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        payload = slot["artifact_id"].encode("ascii")
        source.write_bytes(payload)
        uncertainty = None if not slot["uncertainty_required"] else {
            "value": 0.1, "unit": slot["required_units"][0],
            "method": "synthetic PC15 fixture", "evidence_sha256": _H,
        }
        sidecar = root / slot["destination_relative_to_external_evidence_root"]
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_bytes(_canonical({
            "schema": "rocell.camera_arrival_original.v1",
            "artifact_id": slot["artifact_id"],
            "artifact_class": slot["artifact_class"],
            "captured_at_utc": "2026-09-29T12:00:00Z",
            "source_relative_path": relative,
            "source_size_bytes": len(payload),
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "units": slot["required_units"], "uncertainty": uncertainty,
            "configuration_epoch_id": "camera-epoch-001",
            "review": {
                "reviewer_id": "synthetic-pc15-review",
                "reviewed_at_utc": "2026-09-29T13:00:00Z",
                "disposition": "ACCEPTED", "review_sha256": _H,
            },
        }))


def _case(case_id: str, expected: str, observed: str, detail: list[str]) -> dict[str, Any]:
    return {
        "case_id": case_id, "expected": expected, "observed": observed,
        "matched": expected == observed, "detail": detail,
    }


def _boundary_intake(
    fixture: InstalledCableEnvelopeIntakeV1,
) -> InstalledCableEnvelopeIntakeV1:
    names = tuple(f"boundary-{index:02d}" for index in range(MAX_POSTURES))
    postures = tuple({
        "sequence": index, "posture_id": name,
        "joint_state_sha256": hashlib.sha256(name.encode("ascii")).hexdigest(),
        "capsules": [{
            "kind": "capsule", "start_mm": [60000.0 + index, 0.0, 0.0],
            "end_mm": [60001.0 + index, 0.0, 0.0], "radius_mm": 0.1,
        }],
    } for index, name in enumerate(names))
    sweeps = tuple({
        "sequence": index, "start_posture_id": names[index],
        "end_posture_id": names[index + 1],
        "capsules": [{
            "kind": "capsule", "start_mm": [60000.0 + index, 0.0, 0.0],
            "end_mm": [60002.0 + index, 0.0, 0.0], "radius_mm": 0.2,
        }],
    } for index in range(MAX_POSTURES - 1))
    return InstalledCableEnvelopeIntakeV1(
        fixture.profile, fixture.sampled_body_id, fixture.source_sha256,
        fixture.maximum_uncertainty_mm, postures, sweeps,
    )


def run_installed_geometry_cable_rehearsal_v1(workspace: Path) -> dict[str, Any]:
    """Run the frozen PC15 fixture matrix without opening any device."""

    with tempfile.TemporaryDirectory(prefix="rocell-pc15-") as temporary:
        evidence = Path(temporary) / "evidence"
        evidence.mkdir()
        _populate_evidence(evidence)
        handoff = build_camera_arrival_consumer_handoff_v1(workspace, evidence)
        complete = build_synthetic_installed_collision_profile_v1(workspace)
        cable = build_synthetic_cable_envelope_intake_v1(complete)
        geometry_receipt = emit_installed_collision_consumer_receipt_v1(
            handoff, "installed_geometry", complete, validated_at_utc=WHEN
        )
        cable_receipt = emit_installed_collision_consumer_receipt_v1(
            handoff, "cable_envelope", cable, validated_at_utc=WHEN
        )
        cases = [_case(
            "complete_templates", "PASS", (
                "PASS" if geometry_receipt["validation_status"] == "PASS"
                and cable_receipt["validation_status"] == "PASS" else "BLOCKED"
            ), [],
        )]

        missing = build_synthetic_installed_collision_profile_v1(
            workspace, omit_body_id="attachment:camera_holder"
        )
        missing_receipt = emit_installed_collision_consumer_receipt_v1(
            handoff, "installed_geometry", missing, validated_at_utc=WHEN
        )
        cases.append(_case(
            "missing_rigid_body", "BLOCKED", missing_receipt["validation_status"],
            list(missing_receipt["blockers"]),
        ))

        diagnostic = build_synthetic_installed_collision_profile_v1(
            workspace, diagnostic_body_id="attachment:camera_holder"
        )
        diagnostic_receipt = emit_installed_collision_consumer_receipt_v1(
            handoff, "installed_geometry", diagnostic, validated_at_utc=WHEN
        )
        cases.append(_case(
            "unknown_attachment_evidence", "BLOCKED",
            diagnostic_receipt["validation_status"],
            list(diagnostic_receipt["blockers"]),
        ))

        boundary = _boundary_intake(cable)
        boundary_receipt = emit_installed_collision_consumer_receipt_v1(
            handoff, "cable_envelope", boundary, validated_at_utc=WHEN
        )
        cases.append(_case(
            "maximum_posture_boundary", "PASS",
            boundary_receipt["validation_status"],
            [f"postures={len(boundary.postures)}"],
        ))

        mutations = {
            "missing_swept_segment": (cable.postures, cable.swept_envelopes[:-1], cable.source_sha256),
            "crossed_posture_lineage": (
                cable.postures,
                ({**cable.swept_envelopes[0], "end_posture_id": cable.postures[-1]["posture_id"]},)
                + cable.swept_envelopes[1:],
                cable.source_sha256,
            ),
            "unknown_source_hash": (cable.postures, cable.swept_envelopes, "f" * 64),
        }
        for case_id, (postures, sweeps, source) in mutations.items():
            try:
                InstalledCableEnvelopeIntakeV1(
                    complete, cable.sampled_body_id, source,
                    cable.maximum_uncertainty_mm, postures, sweeps,
                )
            except InstalledCableEnvelopeIntakeV1Error as exc:
                cases.append(_case(case_id, "REJECTED", "REJECTED", [str(exc)]))
            else:  # pragma: no cover - guarded by the retained campaign
                cases.append(_case(case_id, "REJECTED", "ACCEPTED", []))

        try:
            emit_installed_collision_consumer_receipt_v1(
                handoff, "installed_geometry", cable, validated_at_utc=WHEN
            )
        except CameraArrivalConsumerEmitterV1Error as exc:
            cases.append(_case(
                "cable_used_as_rigid_geometry", "REJECTED", "REJECTED", [str(exc)]
            ))
        else:  # pragma: no cover
            cases.append(_case(
                "cable_used_as_rigid_geometry", "REJECTED", "ACCEPTED", []
            ))

    core = {
        "schema": SCHEMA, "evidence_class": EVIDENCE_CLASS,
        "case_count": len(cases), "matched_count": sum(row["matched"] for row in cases),
        "cases": cases,
        "all_declared_cases_matched": all(row["matched"] for row in cases),
        "qualification_installed": False, "camera_opened": False,
        "transport_opened": False, "controller_started": False,
        "controller_commands": [], "hardware_writes": 0,
        "physical_movements": 0, "physical_authority": False,
    }
    return {**core, "report_sha256": _sha(core)}


def parse_installed_geometry_cable_rehearsal_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Verify exact campaign ordering, outcomes, authority, and content hash."""

    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise InstalledGeometryCableRehearsalV1Error("report fields differ")
    unsigned = dict(value)
    digest = unsigned.pop("report_sha256")
    if not isinstance(digest, str) or _sha(unsigned) != digest:
        raise InstalledGeometryCableRehearsalV1Error("report hash mismatch")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != len(CASE_EXPECTATIONS):
        raise InstalledGeometryCableRehearsalV1Error("report case count differs")
    for row, (case_id, (expected, detail)) in zip(
        cases, CASE_EXPECTATIONS.items()
    ):
        if (
            not isinstance(row, Mapping) or set(row) != _CASE_FIELDS
            or row.get("case_id") != case_id
            or row.get("expected") != expected
            or row.get("detail") != detail
            or row.get("matched") is not (row.get("observed") == expected)
        ):
            raise InstalledGeometryCableRehearsalV1Error(
                f"report case differs: {case_id}"
            )
    matched = sum(row["matched"] is True for row in cases)
    if (
        value.get("schema") != SCHEMA
        or value.get("evidence_class") != EVIDENCE_CLASS
        or value.get("case_count") != len(CASE_EXPECTATIONS)
        or value.get("matched_count") != matched
        or value.get("all_declared_cases_matched") is not (
            matched == len(CASE_EXPECTATIONS)
        )
        or any(value.get(field) is not False for field in (
            "qualification_installed", "camera_opened", "transport_opened",
            "controller_started", "physical_authority",
        ))
        or value.get("controller_commands") != []
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
    ):
        raise InstalledGeometryCableRehearsalV1Error("report semantics differ")
    return MappingProxyType(dict(value))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_installed_geometry_cable_rehearsal_v1(args.workspace)
        parse_installed_geometry_cable_rehearsal_v1(report)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_declared_cases_matched"] else 2


__all__ = [
    "CASE_EXPECTATIONS", "EVIDENCE_CLASS", "SCHEMA",
    "InstalledGeometryCableRehearsalV1Error",
    "build_synthetic_installed_collision_profile_v1", "main",
    "parse_installed_geometry_cable_rehearsal_v1",
    "run_installed_geometry_cable_rehearsal_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())
