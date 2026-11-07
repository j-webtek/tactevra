"""Build the blocked, hash-bound ARM-238 installed-measurement intake.

The intake converts the ARM-237 request for installed geometry into the
existing ICQ-1 manifest format.  It inventories every body for one attachment
profile, but deliberately leaves geometry pending until a reviewed source can
provide local-frame primitives and uncertainty.  Reference photographs are
content-addressed lineage only; they are not promoted into measurements.

This module performs no collision screening, simulation, hardware access, or
motion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.application.collision_readiness import (
    CurrentCollisionReadinessReport,
    assess_current_collision_readiness,
)
from rocell.application.context import load_simulation_context
from rocell.application.installed_collision_measurement_manifest_v1 import (
    BLOCKED_STATUS,
    validate_installed_collision_measurement_manifest_v1,
)
from rocell.simulation.collision import CollisionAttachmentProfile


ARM237_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_lifted_route_geometry_intake_plan.v1"
)
MANIFEST_SCHEMA = "rocell.installed_collision_measurement_manifest.v1"
RECEIPT_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_installed_collision_measurement_intake.v1"
)
RECEIPT_STATUS = "BLOCKED_PENDING_ACCEPTED_INSTALLED_MEASUREMENTS"


class InstalledCollisionMeasurementIntakeError(ValueError):
    """ARM-238 input lineage or output semantics changed."""


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
        raise InstalledCollisionMeasurementIntakeError(
            "ARM-238 document is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_arm237(plan: Mapping[str, Any]) -> str:
    claimed = plan.get("plan_sha256")
    unsigned = dict(plan)
    unsigned.pop("plan_sha256", None)
    if (
        plan.get("schema") != ARM237_SCHEMA
        or plan.get("status") != "BLOCKED_PENDING_HASH_BOUND_INSTALLED_GEOMETRY"
        or plan.get("next_required_stage")
        != "BUILD_HASH_BOUND_INSTALLED_COLLISION_MEASUREMENT_MANIFEST"
        or plan.get("corrected_cartesian_route_materialized") is not False
        or plan.get("physical_authority") is not False
        or not isinstance(claimed, str)
        or claimed != _sha(unsigned)
    ):
        raise InstalledCollisionMeasurementIntakeError(
            "ARM-237 installed-geometry intake lineage changed"
        )
    return claimed


def hash_reference_artifacts(paths: Sequence[Path]) -> list[dict[str, Any]]:
    """Hash reference-only artifacts without interpreting their contents."""

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        resolved = Path(path).resolve(strict=True)
        payload = resolved.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        rows.append({
            "reference_id": f"{resolved.parent.name}/{resolved.name}",
            "sha256": digest,
            "byte_count": len(payload),
            "classification": "REFERENCE_ONLY_NOT_ACCEPTED_MEASUREMENT",
        })
    return sorted(rows, key=lambda row: (row["reference_id"], row["sha256"]))


def build_pending_measurement_manifest(
    plan: Mapping[str, Any],
    readiness: CurrentCollisionReadinessReport,
    *,
    attachment_profile: CollisionAttachmentProfile,
    captured_at_utc: str,
) -> dict[str, Any]:
    """Inventory the selected profile without inventing installed geometry."""

    arm237_hash = _require_arm237(plan)
    if readiness.attachment_profile is not attachment_profile:
        raise InstalledCollisionMeasurementIntakeError(
            "collision readiness attachment profile changed"
        )
    body_measurements = []
    for requirement in sorted(
        readiness.contract.requirements, key=lambda row: row.body_id
    ):
        body_measurements.append({
            "body_id": requirement.body_id,
            "parent_frame": requirement.parent_frame,
            "role": requirement.role.value,
            "binding_mode": requirement.binding_mode.value,
            "status": "PENDING",
            "source_ids": [],
            "coordinate_frame": requirement.parent_frame,
            "units": "mm",
            "geometry_uncertainty_mm": None,
            "envelope_primitives": [],
            "notes": (
                "ARM-238 inventory row. Existing reference evidence does not "
                "establish an accepted local-frame 3D envelope and uncertainty."
            ),
        })
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "measurement_manifest_id": (
            f"arm-238-{attachment_profile.value}-installed-measurements-v1"
        ),
        "captured_at_utc": captured_at_utc,
        "manifest_id": readiness.manifest_id,
        "manifest_sha256": readiness.manifest_sha256,
        "active_build_id": readiness.active_build_id,
        "build_snapshot_sha256": readiness.build_snapshot_hash,
        "robot_model_sha256": readiness.urdf_sha256,
        "base_contract_sha256": readiness.contract.content_hash,
        "root_frame": readiness.contract.root_frame,
        "sources": [],
        "body_measurements": body_measurements,
        "clearance_measurement": {
            "status": "PENDING",
            "source_ids": [],
            "minimum_separation_mm": None,
            "geometry_uncertainty_mm_per_body": None,
            "pose_uncertainty_mm_per_body": None,
            "notes": (
                "ARM-237's 0.5 mm noncontact route threshold is a planning "
                "constraint, not an accepted installed clearance measurement."
            ),
        },
    }
    manifest["content_sha256"] = _sha(manifest)
    # Keep the source binding visible without misusing the ICQ-1 source table.
    if arm237_hash != plan["plan_sha256"]:  # pragma: no cover - defensive
        raise InstalledCollisionMeasurementIntakeError("ARM-237 hash changed")
    return manifest


def build_intake_package(
    plan: Mapping[str, Any],
    readiness: CurrentCollisionReadinessReport,
    *,
    attachment_profile: CollisionAttachmentProfile,
    captured_at_utc: str,
    reference_artifacts: Sequence[Mapping[str, Any]] = (),
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build and validate the blocked manifest plus its zero-authority receipt."""

    arm237_hash = _require_arm237(plan)
    manifest = build_pending_measurement_manifest(
        plan,
        readiness,
        attachment_profile=attachment_profile,
        captured_at_utc=captured_at_utc,
    )
    manifest_bytes = _canonical(manifest)
    manifest_file_hash = hashlib.sha256(manifest_bytes).hexdigest()
    validation = validate_installed_collision_measurement_manifest_v1(
        manifest,
        contract=readiness.contract,
        expected_manifest_id=readiness.manifest_id,
        expected_manifest_sha256=readiness.manifest_sha256,
        expected_active_build_id=readiness.active_build_id,
        expected_build_snapshot_sha256=readiness.build_snapshot_hash,
        expected_robot_model_sha256=readiness.urdf_sha256,
        file_sha256=manifest_file_hash,
    )
    if (
        validation.get("status") != BLOCKED_STATUS
        or validation.get("measured_body_count") != 0
        or validation.get("required_body_count")
        != len(readiness.contract.requirements)
    ):
        raise InstalledCollisionMeasurementIntakeError(
            "ARM-238 pending manifest unexpectedly became measurement-ready"
        )
    references = [dict(row) for row in reference_artifacts]
    for row in references:
        if row.get("classification") != "REFERENCE_ONLY_NOT_ACCEPTED_MEASUREMENT":
            raise InstalledCollisionMeasurementIntakeError(
                "ARM-238 reference artifact classification changed"
            )
    core: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "status": RECEIPT_STATUS,
        "source_arm237_plan_sha256": arm237_hash,
        "target_id": plan.get("target_id"),
        "attachment_profile": attachment_profile.value,
        "measurement_manifest_content_sha256": manifest["content_sha256"],
        "measurement_manifest_file_sha256": manifest_file_hash,
        "validation_report_sha256": validation["validation_report_sha256"],
        "required_body_count": validation["required_body_count"],
        "pending_body_ids": validation["pending_body_ids"],
        "clearance_status": validation["clearance_status"],
        "reference_artifacts": references,
        "known_provisional_target_surface": plan[
            "known_provisional_target_surface"
        ],
        "target_specific_blockers": [
            "TARGET_KEYCAP_UNDEFORMED_VOLUME_UNMEASURED",
            "TARGET_KEYCAP_DEPRESSED_ENVELOPE_UNMEASURED",
            "TARGET_KEY_POSE_UNCERTAINTY_UNBOUND",
        ],
        "reference_evidence_promoted_to_measurement": False,
        "installed_collision_profile_generated": False,
        "collision_screening_executed": False,
        "corrected_cartesian_route_materialized": False,
        "corrected_joint_targets_materialized": False,
        "trajectory_playback_authorized": False,
        "native_replay_authorized": False,
        "isaac_started": False,
        "gpu_started": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "gate_promotions": [],
        "next_required_stage": (
            "POPULATE_ACCEPTED_INSTALLED_BODY_AND_SPACE_KEY_MEASUREMENTS"
        ),
        "limitations": [
            "ruler_photos_do_not_establish_local_frame_3d_envelopes",
            "provisional_space_footprint_is_not_accepted_measurement",
            "attachment_profiles_require_separate_manifests",
            "manifest_does_not_authorize_simulation_or_physical_motion",
        ],
    }
    receipt = {**core, "receipt_sha256": _sha(core)}
    return manifest, validation, receipt


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def _write_canonical_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(_canonical(value))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument(
        "--system-manifest",
        type=Path,
        default=Path("software/config/system_manifest.json"),
    )
    parser.add_argument("--arm237-plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--captured-at-utc", required=True)
    parser.add_argument(
        "--attachment-profile",
        choices=[profile.value for profile in CollisionAttachmentProfile],
        required=True,
    )
    parser.add_argument("--reference-artifact", type=Path, action="append", default=[])
    args = parser.parse_args()

    workspace = args.workspace.resolve(strict=True)
    system_manifest = (
        args.system_manifest
        if args.system_manifest.is_absolute()
        else workspace / args.system_manifest
    ).resolve(strict=True)
    plan = json.loads(args.arm237_plan.resolve(strict=True).read_bytes())
    profile = CollisionAttachmentProfile(args.attachment_profile)
    context = load_simulation_context(workspace, system_manifest)
    readiness = assess_current_collision_readiness(
        context, attachment_profile=profile
    )
    references = hash_reference_artifacts(args.reference_artifact)
    manifest, validation, receipt = build_intake_package(
        plan,
        readiness,
        attachment_profile=profile,
        captured_at_utc=args.captured_at_utc,
        reference_artifacts=references,
    )
    output_dir = args.output_dir.resolve()
    _write_canonical_json(output_dir / "measurement_manifest.json", manifest)
    _write_json(output_dir / "validation.json", validation)
    _write_json(output_dir / "receipt.json", receipt)
    _write_json(
        output_dir / "status.json",
        {
            "status": receipt["status"],
            "receipt_sha256": receipt["receipt_sha256"],
            "pending_body_count": len(receipt["pending_body_ids"]),
        },
    )
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
