"""Audit ARM-238 against existing metrology without promoting design priors.

ARM-239 answers a narrow question: which installed-collision manifest fields
are already supported by accepted physical measurements, and what is still
missing?  Nominal layout values, CAD/model geometry, frame conventions, and
reference photographs remain useful capture priors, but none is converted into
an ICQ-1 ``MEASURED`` row by this module.

This module starts no simulator or GPU, opens no device, emits no motion, and
grants no physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


ARM238_RECEIPT_SCHEMA = (
    "tactevra.isaac_lm4_state_policy_installed_collision_measurement_intake.v1"
)
ARM238_RECEIPT_STATUS = "BLOCKED_PENDING_ACCEPTED_INSTALLED_MEASUREMENTS"
MANIFEST_SCHEMA = "rocell.installed_collision_measurement_manifest.v1"
REPORT_SCHEMA = "tactevra.isaac_lm4_installed_measurement_gap_matrix.v1"
REPORT_STATUS = "BLOCKED_NO_ACCEPTED_MEASUREMENT_PROMOTIONS"


class InstalledMeasurementGapMatrixError(ValueError):
    """ARM-239 lineage, evidence, or fail-closed semantics changed."""


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
        raise InstalledMeasurementGapMatrixError(
            "ARM-239 document is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_arm238(
    manifest: Mapping[str, Any], receipt: Mapping[str, Any]
) -> str:
    receipt_unsigned = dict(receipt)
    claimed_receipt_hash = receipt_unsigned.pop("receipt_sha256", None)
    manifest_unsigned = dict(manifest)
    claimed_manifest_content_hash = manifest_unsigned.pop("content_sha256", None)
    manifest_file_hash = hashlib.sha256(_canonical(manifest)).hexdigest()
    bodies = manifest.get("body_measurements")
    if (
        receipt.get("schema") != ARM238_RECEIPT_SCHEMA
        or receipt.get("status") != ARM238_RECEIPT_STATUS
        or not isinstance(claimed_receipt_hash, str)
        or claimed_receipt_hash != _sha(receipt_unsigned)
        or manifest.get("schema") != MANIFEST_SCHEMA
        or not isinstance(claimed_manifest_content_hash, str)
        or claimed_manifest_content_hash != _sha(manifest_unsigned)
        or receipt.get("measurement_manifest_content_sha256")
        != claimed_manifest_content_hash
        or receipt.get("measurement_manifest_file_sha256") != manifest_file_hash
        or receipt.get("reference_evidence_promoted_to_measurement") is not False
        or receipt.get("physical_authority") is not False
        or not isinstance(bodies, list)
        or any(row.get("status") != "PENDING" for row in bodies)
    ):
        raise InstalledMeasurementGapMatrixError(
            "ARM-238 installed-measurement lineage changed"
        )
    body_ids = sorted(row.get("body_id") for row in bodies)
    if body_ids != sorted(receipt.get("pending_body_ids", [])):
        raise InstalledMeasurementGapMatrixError(
            "ARM-238 pending-body inventory changed"
        )
    return claimed_receipt_hash


_ROBOT_BODIES = {
    "robot:base_link",
    "robot:link1",
    "robot:link2",
    "robot:link3",
    "robot:link4",
    "robot:link5",
    "robot:gripper",
}
_CAMERA_BODIES = {
    "attachment:camera_connector",
    "attachment:camera_holder",
    "attachment:camera_module",
}
_STATION_BODIES = {
    "workcell:station:keyboard_left",
    "workcell:station:keyboard_right",
    "workcell:station:phone_tcp",
}


def _capture_gap(body_id: str) -> tuple[list[str], str, list[str]]:
    """Return missing fields, recommended method, and relevant prior IDs."""

    common = [
        "accepted_source_hash",
        "local_frame_envelope_primitives",
        "geometry_uncertainty_mm",
    ]
    if body_id in _ROBOT_BODIES:
        return common + ["physical_model_identity_verification"], (
            "CAD_DERIVED_AND_PHYSICALLY_VERIFIED"
        ), ["robot_model_geometry"]
    if body_id in _CAMERA_BODIES:
        return common + ["installed_attachment_pose_verification"], (
            "CAD_DERIVED_AND_PHYSICALLY_VERIFIED"
        ), ["robot_model_geometry", "frame_conventions"]
    if body_id in _STATION_BODIES:
        suffix = body_id.rsplit(":", 1)[-1]
        return common + ["installed_station_pose_and_height"], (
            "CALIPER_OR_FIXTURE_GAUGE"
        ), [f"layout_station_{suffix}"]
    if body_id == "workcell:board_solid":
        return common + ["installed_board_pose", "flatness_or_bow_bound"], (
            "TAPE_MEASURE_AND_FLATNESS_GAUGE"
        ), ["layout_board_nominal", "board_measurement_gate"]
    if body_id == "workcell:keyboard":
        return common + [
            "installed_keyboard_pose",
            "undeformed_space_key_volume",
            "depressed_space_key_envelope",
            "pose_uncertainty_mm",
        ], "CALIPER_AND_FIXTURE_GAUGE", [
            "layout_keyboard_nominal",
            "keyboard_measurement_gate",
            "arm237_space_surface_prior",
        ]
    if body_id == "workcell:phone":
        return common + ["installed_phone_pose", "case_and_cable_keepout"], (
            "CALIPER_AND_FIXTURE_GAUGE"
        ), ["layout_phone_configured", "phone_measurement_gate"]
    if body_id == "installation:base_and_factory_clamp":
        return common + ["installed_clamp_footprint", "board_to_base_transform"], (
            "TAPE_MEASURE_AND_FIXTURE_GAUGE"
        ), ["frame_conventions", "commissioning_gate"]
    if body_id == "attachment:contact_tool":
        return common + ["assembled_tool_tcp_transform", "stylus_projection_mm"], (
            "CALIPER_AND_TCP_FIXTURE_GAUGE"
        ), ["stylus_measurement_gate", "tool_assembly_gate"]
    if body_id == "attachment:moving_camera_cable":
        return [
            "accepted_source_hash",
            "configuration_sampled_swept_envelope",
            "geometry_uncertainty_mm",
            "sampled_configuration_coverage",
        ], "PHOTOGRAMMETRY_OR_REVIEWED_CONFIGURATION_SWEEP", [
            "camera_cable_reference_photos"
        ]
    raise InstalledMeasurementGapMatrixError(
        f"ARM-239 has no reviewed capture plan for {body_id!r}"
    )


def _gate_prior(
    measurement_record: Mapping[str, Any], gate_name: str
) -> dict[str, Any]:
    gates = measurement_record.get("gates")
    if not isinstance(gates, Mapping) or not isinstance(gates.get(gate_name), Mapping):
        raise InstalledMeasurementGapMatrixError(
            f"measurement gate {gate_name!r} is unavailable"
        )
    gate = gates[gate_name]
    recorded = gate.get("recorded_values")
    if not isinstance(recorded, Mapping):
        raise InstalledMeasurementGapMatrixError(
            f"measurement gate {gate_name!r} has no recorded-values object"
        )
    def has_recorded_leaf(value: object) -> bool:
        if isinstance(value, Mapping):
            return any(has_recorded_leaf(item) for item in value.values())
        if isinstance(value, list):
            return any(has_recorded_leaf(item) for item in value)
        return value is not None and value != ""

    populated = sorted(
        key for key, value in recorded.items() if has_recorded_leaf(value)
    )
    return {
        "gate_name": gate_name,
        "gate_status": gate.get("status"),
        "populated_recorded_fields": populated,
        "classification": "PHYSICAL_GATE_NOT_ACCEPTED_FOR_ICQ1",
    }


def _build_priors(
    measurement_record: Mapping[str, Any],
    layout: Mapping[str, Any],
    frame_contract: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> list[dict[str, Any]]:
    board = layout.get("board", {})
    devices = layout.get("devices", {})
    stations = layout.get("stations", {})
    if not all(isinstance(value, Mapping) for value in (board, devices, stations)):
        raise InstalledMeasurementGapMatrixError("workcell layout structure changed")
    priors: list[dict[str, Any]] = [
        {
            "prior_id": "layout_board_nominal",
            "classification": "NOMINAL_CONFIGURED_NOT_ACCEPTED_MEASUREMENT",
            "values": {
                "width_mm": board.get("width"),
                "depth_mm": board.get("depth"),
                "thickness_mm": board.get("thickness"),
            },
        },
        {
            "prior_id": "layout_keyboard_nominal",
            "classification": "NOMINAL_CONFIGURED_NOT_ACCEPTED_MEASUREMENT",
            "values": devices.get("keyboard"),
        },
        {
            "prior_id": "layout_phone_configured",
            "classification": "CONFIGURED_NOT_ACCEPTED_MEASUREMENT",
            "values": devices.get("phone"),
        },
        {
            "prior_id": "frame_conventions",
            "classification": "FRAME_CONVENTION_NOT_GEOMETRY_MEASUREMENT",
            "values": frame_contract,
        },
        {
            "prior_id": "robot_model_geometry",
            "classification": "MODEL_GEOMETRY_PENDING_PHYSICAL_VERIFICATION",
            "values": {"available": True},
        },
        {
            "prior_id": "arm237_space_surface_prior",
            "classification": "SYNTHETIC_BOUNDED_PRIOR_NOT_ACCEPTED_MEASUREMENT",
            "values": receipt.get("known_provisional_target_surface"),
        },
        {
            "prior_id": "camera_cable_reference_photos",
            "classification": "REFERENCE_ONLY_NOT_ACCEPTED_MEASUREMENT",
            "values": {
                "reference_count": len(receipt.get("reference_artifacts", []))
            },
        },
    ]
    for name, gate in (
        ("board_measurement_gate", "board_fabrication_pass"),
        ("keyboard_measurement_gate", "keyboard_dimensions_measured"),
        ("phone_measurement_gate", "phone_dimensions_measured"),
        ("stylus_measurement_gate", "stylus_diameter_measured"),
        ("tool_assembly_gate", "tool_assembled_motion_pass"),
        ("commissioning_gate", "workcell_commissioning_pass"),
    ):
        priors.append({"prior_id": name, **_gate_prior(measurement_record, gate)})
    for station_id in sorted(_STATION_BODIES):
        suffix = station_id.rsplit(":", 1)[-1]
        values = stations.get(suffix)
        if not isinstance(values, Mapping):
            raise InstalledMeasurementGapMatrixError(
                f"layout station {suffix!r} is unavailable"
            )
        priors.append({
            "prior_id": f"layout_station_{suffix}",
            "classification": "NOMINAL_CONFIGURED_NOT_ACCEPTED_MEASUREMENT",
            "values": values,
        })
    return sorted(priors, key=lambda row: row["prior_id"])


def build_measurement_gap_matrix(
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
    measurement_record: Mapping[str, Any],
    layout: Mapping[str, Any],
    frame_contract: Mapping[str, Any],
    *,
    source_files: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Build the deterministic, zero-promotion ARM-239 audit."""

    arm238_hash = _require_arm238(manifest, receipt)
    priors = _build_priors(measurement_record, layout, frame_contract, receipt)
    prior_ids = {row["prior_id"] for row in priors}
    rows = []
    for body in sorted(manifest["body_measurements"], key=lambda row: row["body_id"]):
        missing, method, relevant = _capture_gap(body["body_id"])
        if not set(relevant).issubset(prior_ids):
            raise InstalledMeasurementGapMatrixError(
                f"body {body['body_id']} references an unknown prior"
            )
        rows.append({
            "body_id": body["body_id"],
            "parent_frame": body["parent_frame"],
            "binding_mode": body["binding_mode"],
            "current_status": body["status"],
            "accepted_measurement_available": False,
            "relevant_prior_ids": relevant,
            "missing_acceptance_fields": missing,
            "recommended_measurement_method": method,
        })
    source_rows = sorted(
        [dict(row) for row in source_files], key=lambda row: row["source_id"]
    )
    core: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": REPORT_STATUS,
        "source_arm238_receipt_sha256": arm238_hash,
        "attachment_profile": receipt.get("attachment_profile"),
        "measurement_manifest_content_sha256": manifest["content_sha256"],
        "evidence_source_files": source_rows,
        "candidate_priors": priors,
        "body_gap_matrix": rows,
        "required_body_count": len(rows),
        "accepted_body_count": 0,
        "pending_body_count": len(rows),
        "clearance_measurement_available": False,
        "target_specific_gaps": list(receipt.get("target_specific_blockers", [])),
        "nominal_values_promoted_to_measurement": False,
        "reference_photos_promoted_to_measurement": False,
        "measurement_manifest_modified": False,
        "installed_collision_profile_generated": False,
        "collision_screening_executed": False,
        "corrected_cartesian_route_materialized": False,
        "corrected_joint_targets_materialized": False,
        "isaac_started": False,
        "gpu_started": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "next_required_stage": (
            "CAPTURE_REVIEWED_LOCAL_FRAME_GEOMETRY_AND_UNCERTAINTY"
        ),
    }
    return {**core, "report_sha256": _sha(core)}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise InstalledMeasurementGapMatrixError(f"{path} is not a JSON object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm238-manifest", type=Path, required=True)
    parser.add_argument("--arm238-receipt", type=Path, required=True)
    parser.add_argument("--measurement-record", type=Path, required=True)
    parser.add_argument("--workcell-layout", type=Path, required=True)
    parser.add_argument("--frame-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    inputs = {
        "arm238_manifest": args.arm238_manifest.resolve(strict=True),
        "arm238_receipt": args.arm238_receipt.resolve(strict=True),
        "measurement_record": args.measurement_record.resolve(strict=True),
        "workcell_layout": args.workcell_layout.resolve(strict=True),
        "frame_contract": args.frame_contract.resolve(strict=True),
    }
    report = build_measurement_gap_matrix(
        _load_json(inputs["arm238_manifest"]),
        _load_json(inputs["arm238_receipt"]),
        _load_json(inputs["measurement_record"]),
        _load_json(inputs["workcell_layout"]),
        _load_json(inputs["frame_contract"]),
        source_files=[
            {
                "source_id": name,
                "sha256": _file_sha(path),
                "classification": "AUDIT_INPUT_NOT_ACCEPTED_MEASUREMENT",
            }
            for name, path in inputs.items()
        ],
    )
    _write_json(args.output.resolve(), report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
