"""Domain-specific receipt emitters for existing offline camera consumers."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from rocell.calibration.planner_snapshot import PlannerCalibrationSnapshot

from .camera_arrival_consumer_handoff_v1 import (
    parse_camera_arrival_consumer_handoff_v1,
)
from .camera_arrival_consumer_validation_v1 import (
    RECEIPT_SCHEMA,
    CameraArrivalConsumerValidationV1Error,
    parse_camera_arrival_consumer_validation_receipt_v1,
)
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .installed_cable_envelope_intake_v1 import InstalledCableEnvelopeIntakeV1


_SUPPORT_SOURCE = (
    "software/src/rocell/application/camera_support_optics_epoch_intake_v1.py"
)
_CAMPAIGN_SOURCE = "software/ai/eval/preflight_physical_camera_campaign.py"
_EVALUATION_SOURCE = "software/ai/eval/evaluate_physical_camera_localization.py"
_PLANNER_SOURCE = "software/src/rocell/calibration/planner_snapshot.py"
_COLLISION_SOURCE = (
    "software/src/rocell/application/installed_collision_geometry.py"
)
_SUPPORT_IDS = {
    "camera_receipt", "camera_identity", "camera_mode_controls", "support_witnesses",
}
_CAMPAIGN_IDS = {"camera_intrinsics", "localization_campaign"}
_EVALUATION_IDS = {"camera_to_board_transform", "localization_evaluation"}
_PLANNER_IDS = {
    "board_to_robot_transform", "keyboard_to_board_transform",
    "tool_to_joint_transform", "keyboard_profile", "tool_profile",
}
_COLLISION_IDS = {"installed_geometry", "cable_envelope"}


class CameraArrivalConsumerEmitterV1Error(ValueError):
    """A native consumer output cannot issue a receipt for this route."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _verify_native_hash(output: Mapping[str, Any], field: str) -> str:
    digest = output.get(field)
    if not isinstance(digest, str) or len(digest) != 64:
        raise CameraArrivalConsumerEmitterV1Error(
            f"native consumer output lacks {field}"
        )
    unsigned = {key: value for key, value in output.items() if key != field}
    if _hash(unsigned) != digest:
        raise CameraArrivalConsumerEmitterV1Error(
            "native consumer output hash mismatch"
        )
    return digest


def _route(handoff: Mapping[str, Any], artifact_id: str) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    try:
        verified = parse_camera_arrival_consumer_handoff_v1(handoff)
    except ValueError as exc:
        raise CameraArrivalConsumerEmitterV1Error(str(exc)) from exc
    if not verified["ready_for_offline_consumer_validation"]:
        raise CameraArrivalConsumerEmitterV1Error(
            "handoff is not ready for offline consumer validation"
        )
    route = next(
        (row for row in verified["routes"] if row["artifact_id"] == artifact_id),
        None,
    )
    if route is None or not route["ready_for_offline_consumer_validation"]:
        raise CameraArrivalConsumerEmitterV1Error("artifact route is unavailable")
    return verified, route


def _receipt(
    handoff: Mapping[str, Any], route: Mapping[str, Any], *,
    validator_id: str, validated_at_utc: str, status: str,
    blockers: list[str], output_sha256: str,
) -> dict[str, Any]:
    core = {
        "schema": RECEIPT_SCHEMA,
        "artifact_id": route["artifact_id"],
        "handoff_sha256": handoff["handoff_sha256"],
        "preflight_sha256": handoff["preflight_sha256"],
        "consumer_map_sha256": handoff["consumer_map_sha256"],
        "sidecar_sha256": route["sidecar_sha256"],
        "source_sha256": route["source_sha256"],
        "consumer_source": route["consumer_source"],
        "consumer_source_sha256": route["consumer_source_sha256"],
        "downstream_schema": route["downstream_schema"],
        "downstream_schema_sha256": route["downstream_schema_sha256"],
        "consumer_binding": route["consumer_binding"],
        "validator_id": validator_id,
        "validator_version_sha256": route["consumer_source_sha256"],
        "validated_at_utc": validated_at_utc,
        "validation_status": status,
        "blockers": blockers,
        "output_sha256": output_sha256,
        "consumer_invoked": True,
        "camera_opened": False,
        "controller_started": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "qualification_installed": False,
        "physical_admission_ready": False,
        "physical_authority": False,
    }
    receipt = {**core, "receipt_sha256": _hash(core)}
    try:
        parse_camera_arrival_consumer_validation_receipt_v1(receipt)
    except CameraArrivalConsumerValidationV1Error as exc:
        raise CameraArrivalConsumerEmitterV1Error(str(exc)) from exc
    return receipt


def emit_camera_support_consumer_receipt_v1(
    handoff: Mapping[str, Any], artifact_id: str,
    assessment: Mapping[str, Any], *, validated_at_utc: str,
) -> dict[str, Any]:
    """Translate one native camera-support binding assessment into a receipt."""

    if artifact_id not in _SUPPORT_IDS:
        raise CameraArrivalConsumerEmitterV1Error("artifact is not support-owned")
    verified, route = _route(handoff, artifact_id)
    if route["consumer_source"] != _SUPPORT_SOURCE:
        raise CameraArrivalConsumerEmitterV1Error("support consumer source differs")
    output_hash = _verify_native_hash(assessment, "assessment_sha256")
    bindings = assessment.get("binding_assessments")
    ready_count = sum(
        isinstance(row, Mapping) and row.get("status") == "READY"
        for row in bindings
    ) if isinstance(bindings, list) else 0
    aggregate_ready = ready_count == len(_SUPPORT_IDS)
    if (
        assessment.get("schema") != "rocell.camera_support_optics_epoch_assessment.v1"
        or not isinstance(bindings, list)
        or len(bindings) != len(_SUPPORT_IDS)
        or assessment.get("status")
        != ("READY_FOR_COMPONENT_ADMISSION" if aggregate_ready else "BLOCKED")
        or assessment.get("component_admission_ready") is not aggregate_ready
        or any(assessment.get(field) is not False for field in (
            "epoch_advanced", "hardware_access", "camera_open_authorized",
            "installation_authorized", "controller_start_authorized",
            "transport_authorized", "execution_authorized", "physical_authority",
        ))
    ):
        raise CameraArrivalConsumerEmitterV1Error(
            "camera-support assessment semantics differ"
        )
    binding = next(
        (row for row in bindings if row.get("binding_id") == artifact_id), None
    )
    if not isinstance(binding, Mapping) or binding.get("status") not in {
        "READY", "BLOCKED", "MISSING",
    }:
        raise CameraArrivalConsumerEmitterV1Error("support binding result is absent")
    passed = binding["status"] == "READY"
    blockers = list(binding.get("blockers", []))
    if passed != (not blockers):
        raise CameraArrivalConsumerEmitterV1Error("support binding result contradicts blockers")
    return _receipt(
        verified, route, validator_id="camera-support-optics-epoch-assessment-v1",
        validated_at_utc=validated_at_utc, status="PASS" if passed else "BLOCKED",
        blockers=blockers, output_sha256=output_hash,
    )


def emit_camera_campaign_consumer_receipt_v1(
    handoff: Mapping[str, Any], artifact_id: str,
    preflight_receipt: Mapping[str, Any], *, validated_at_utc: str,
) -> dict[str, Any]:
    """Translate the native physical-camera campaign preflight receipt."""

    if artifact_id not in _CAMPAIGN_IDS:
        raise CameraArrivalConsumerEmitterV1Error("artifact is not campaign-owned")
    verified, route = _route(handoff, artifact_id)
    if route["consumer_source"] != _CAMPAIGN_SOURCE:
        raise CameraArrivalConsumerEmitterV1Error("campaign consumer source differs")
    output_hash = _verify_native_hash(preflight_receipt, "receipt_sha256")
    if (
        preflight_receipt.get("schema")
        != "rocell.physical_camera_localization_campaign_preflight.v1"
        or preflight_receipt.get("status") != "READY_FOR_OFFLINE_EVALUATION"
        or any(preflight_receipt.get(field) is not False for field in (
            "camera_opened", "model_loaded", "controller_started",
            "qualification_installed",
        ))
        or preflight_receipt.get("hardware_writes") != 0
        or preflight_receipt.get("physical_movements") != 0
    ):
        raise CameraArrivalConsumerEmitterV1Error(
            "campaign preflight receipt does not permit a pass"
        )
    return _receipt(
        verified, route, validator_id="physical-camera-campaign-preflight-v1",
        validated_at_utc=validated_at_utc, status="PASS", blockers=[],
        output_sha256=output_hash,
    )


def emit_camera_localization_consumer_receipt_v1(
    handoff: Mapping[str, Any], artifact_id: str,
    evaluation: Mapping[str, Any], *, validated_at_utc: str,
) -> dict[str, Any]:
    """Translate the native held-out localization evaluation result."""

    if artifact_id not in _EVALUATION_IDS:
        raise CameraArrivalConsumerEmitterV1Error("artifact is not evaluation-owned")
    verified, route = _route(handoff, artifact_id)
    if route["consumer_source"] != _EVALUATION_SOURCE:
        raise CameraArrivalConsumerEmitterV1Error("evaluation consumer source differs")
    output_hash = _verify_native_hash(evaluation, "result_sha256")
    criteria = evaluation.get("criteria")
    if (
        evaluation.get("schema")
        != "rocell.physical_camera_localization_evaluation_result.v1"
        or evaluation.get("status") not in {
            "QUALIFICATION_RECOMMENDED", "QUALIFICATION_BLOCKED",
        }
        or not isinstance(criteria, Mapping)
        or any(not isinstance(value, bool) for value in criteria.values())
        or evaluation.get("qualification_installed") is not False
        or evaluation.get("physical_deployment_qualified") is not False
        or evaluation.get("model_motion_batch_emitted") is not False
        or evaluation.get("controller_started") is not False
        or evaluation.get("hardware_writes") != 0
        or evaluation.get("physical_movements") != 0
    ):
        raise CameraArrivalConsumerEmitterV1Error(
            "localization evaluation semantics differ"
        )
    passed = all(criteria.values())
    if passed != (evaluation["status"] == "QUALIFICATION_RECOMMENDED"):
        raise CameraArrivalConsumerEmitterV1Error(
            "localization recommendation contradicts criteria"
        )
    blockers = [] if passed else [
        f"CRITERION_{name.upper()}" for name, value in sorted(criteria.items())
        if not value
    ]
    return _receipt(
        verified, route, validator_id="physical-camera-localization-evaluator-v1",
        validated_at_utc=validated_at_utc, status="PASS" if passed else "BLOCKED",
        blockers=blockers, output_sha256=output_hash,
    )


def emit_planner_snapshot_consumer_receipt_v1(
    handoff: Mapping[str, Any], artifact_id: str,
    snapshot: PlannerCalibrationSnapshot, *, validated_at_utc: str,
) -> dict[str, Any]:
    """Emit one route receipt from an already decoded typed planner snapshot."""

    if artifact_id not in _PLANNER_IDS:
        raise CameraArrivalConsumerEmitterV1Error("artifact is not planner-owned")
    if not isinstance(snapshot, PlannerCalibrationSnapshot):
        raise CameraArrivalConsumerEmitterV1Error(
            "planner output must be a typed PlannerCalibrationSnapshot"
        )
    verified, route = _route(handoff, artifact_id)
    if route["consumer_source"] != _PLANNER_SOURCE:
        raise CameraArrivalConsumerEmitterV1Error("planner consumer source differs")
    document = snapshot.to_dict()
    required_artifacts = {"arm_board", "keyboard_pose", "keyboard_tcp"}
    if (
        snapshot.device != "keyboard"
        or document.get("schema") != "rocell.planner_calibration_snapshot.v1"
        or document.get("physical_authority") is not False
        or not required_artifacts.issubset(snapshot.artifact_hashes)
        or route["consumer_binding"] not in {
            "arm_board:B_T_Wv", "keyboard_pose:B_T_keyboard",
            "keyboard_tcp:G_T_T", "target_map_sha256",
            "keyboard_tcp.tool_identity_hash",
        }
    ):
        raise CameraArrivalConsumerEmitterV1Error(
            "planner snapshot cannot satisfy the keyboard route"
        )
    return _receipt(
        verified, route, validator_id="planner-calibration-snapshot-v1",
        validated_at_utc=validated_at_utc, status="PASS", blockers=[],
        output_sha256=snapshot.snapshot_sha256,
    )


def emit_installed_collision_consumer_receipt_v1(
    handoff: Mapping[str, Any], artifact_id: str,
    profile: InstalledCollisionGeometryProfile | InstalledCableEnvelopeIntakeV1,
    *, validated_at_utc: str,
) -> dict[str, Any]:
    """Emit installed-geometry or cable-envelope status from a typed profile."""

    if artifact_id not in _COLLISION_IDS:
        raise CameraArrivalConsumerEmitterV1Error("artifact is not collision-owned")
    cable_intake = (
        profile if isinstance(profile, InstalledCableEnvelopeIntakeV1) else None
    )
    installed_profile = cable_intake.profile if cable_intake else profile
    if not isinstance(installed_profile, InstalledCollisionGeometryProfile):
        raise CameraArrivalConsumerEmitterV1Error(
            "collision output must be a typed installed profile or cable intake"
        )
    if cable_intake is not None and artifact_id != "cable_envelope":
        raise CameraArrivalConsumerEmitterV1Error(
            "cable intake can satisfy only the cable_envelope route"
        )
    verified, route = _route(handoff, artifact_id)
    if route["consumer_source"] != _COLLISION_SOURCE:
        raise CameraArrivalConsumerEmitterV1Error("collision consumer source differs")
    document = installed_profile.to_dict()
    audit = document.get("geometry_audit")
    if (
        document.get("schema") != "rocell.installed_collision_geometry_profile.v1"
        or document.get("hardware_commands_generated") != 0
        or document.get("hardware_access") is not False
        or document.get("physical_authority") is not False
        or not isinstance(audit, Mapping)
    ):
        raise CameraArrivalConsumerEmitterV1Error(
            "installed collision profile semantics differ"
        )
    blockers = [
        f"GEOMETRY_{row['code']}:{row['body_id']}"
        for row in audit.get("diagnostic_blockers", [])
        if isinstance(row, Mapping) and row.get("code") and row.get("body_id")
    ]
    if artifact_id == "installed_geometry":
        passed = audit.get("diagnostic_ready") is True
        if not passed and not blockers:
            blockers = ["INSTALLED_GEOMETRY_NOT_DIAGNOSTIC_READY"]
    else:
        if cable_intake is not None:
            cable_document = cable_intake.to_dict()
            return _receipt(
                verified, route, validator_id="installed-cable-envelope-intake-v1",
                validated_at_utc=validated_at_utc, status="PASS", blockers=[],
                output_sha256=_hash(cable_document),
            )
        sampled = audit.get("configuration_sampled_body_ids")
        if not isinstance(sampled, list):
            raise CameraArrivalConsumerEmitterV1Error(
                "collision audit lacks sampled cable identities"
            )
        passed = audit.get("physical_geometry_complete") is True and not sampled
        if not passed:
            blockers.extend(f"CONFIGURATION_SAMPLED_BODY:{item}" for item in sampled)
            if not blockers:
                blockers = ["CABLE_ENVELOPE_NOT_PHYSICALLY_COMPLETE"]
    blockers = list(dict.fromkeys(blockers))
    return _receipt(
        verified, route, validator_id="installed-collision-geometry-v1",
        validated_at_utc=validated_at_utc, status="PASS" if passed else "BLOCKED",
        blockers=blockers, output_sha256=_hash(document),
    )


__all__ = [
    "CameraArrivalConsumerEmitterV1Error",
    "emit_camera_campaign_consumer_receipt_v1",
    "emit_camera_localization_consumer_receipt_v1",
    "emit_camera_support_consumer_receipt_v1",
    "emit_installed_collision_consumer_receipt_v1",
    "emit_planner_snapshot_consumer_receipt_v1",
]
