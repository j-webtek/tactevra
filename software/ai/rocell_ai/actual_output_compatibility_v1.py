"""Reproduce actual AI outputs against the arm-owned zero-authority boundary.

This module is an offline compatibility gate.  It deliberately stops before
IK, controller serialization, transport selection, or any hardware access.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from rocell.application.context import load_simulation_context
from rocell.application.model_motion_ingress_v2 import (
    MeasuredTargetRegionV2,
    ModelMotionIngressV2Error,
    TrustedLocalizationQualificationV2,
)
from rocell.application.model_motion_registry_v2 import (
    TrustedMotionRegistryV2,
    ingest_with_trusted_registry_v2,
    revalidate_with_trusted_registry_v2,
)
from rocell.application.typing_execution_plan_v1 import (
    TypingExecutionConfigV1,
    compile_typing_execution_plan_v1,
)
from rocell.application.typing_trajectory_plan_v1 import (
    TypingTrajectoryPolicyV1,
    compile_typing_trajectory_plan_v1,
)
from rocell.models import (
    ActionPlan,
    Device,
    MAX_BATCH_BYTES_V2,
    MAX_BATCH_PROPOSALS_V2,
    ModelMotionBatchV2,
    ModelMotionBatchV2Error,
    MotionCapabilityV2,
    MotionEvidenceV2,
    MotionGeometryV2,
    MotionUncertaintyV2,
    Point3Mm,
    PressKey,
    SpeedClass,
    UncertaintyBoundType,
    VerifyPhoneState,
    decode_model_motion_batch_v2_json,
)

from .batch_emitter_v2 import TargetObservationV2, assemble


SCHEMA = "rocell.actual_ai_arm_compatibility_report.v1"
CORPUS_SCHEMA = "rocell.actual_ai_arm_compatibility_corpus.v1"
T0 = 1_800_000_000_000
H = {letter: letter * 64 for letter in "abcdef"}


class ActualOutputCompatibilityError(ValueError):
    """The corpus, retained output, or observed outcome differs."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _plan(text: str, targets: tuple[str, ...]) -> ActionPlan:
    return ActionPlan.from_text(
        device=Device.KEYBOARD,
        profile_id="keyboard-development-v1",
        text=text,
        actions=tuple(PressKey(target) for target in targets),
        required_calibrations=("keyboard_pose", "keyboard_tcp"),
    )


def _baseline_parts(context: Any, targets: tuple[str, ...]) -> dict[str, Any]:
    return {
        "capability": MotionCapabilityV2("keyboard-development-v1", H["e"]),
        "geometry": MotionGeometryV2(
            "board_mm_xy_plane_v2", "mm", H["d"], H["e"],
            context.targets.content_sha256,
        ),
        "evidence": MotionEvidenceV2(
            capture_id="capture-001", frame_id="frame-001",
            image_sha256=H["a"], camera_identity_sha256=H["b"],
            capture_clock_domain_id="capture-clock-001",
            model_id="keyboard-pose-net-robust-v0", model_sha256=H["c"],
            scene_observation_sha256=H["b"],
            precision_observation_sha256=H["c"],
            fusion_decision_sha256=H["d"], scene_lease_id="lease-001",
            scene_lease_issuer_id="capture-service-001",
            scene_lease_sha256=H["f"], captured_at_epoch_ms=T0,
            evaluated_at_epoch_ms=T0 + 2_000,
            expires_at_epoch_ms=T0 + 10_000,
        ),
        "uncertainty": MotionUncertaintyV2(
            UncertaintyBoundType.PLANAR_L2_DISK, 1.0, 0.99, H["f"], H["a"],
            "static-overhead-keyboard-v1", tuple(dict.fromkeys(targets)),
        ),
    }


def build_actual_emitter_hhi_payload(workspace: Path) -> bytes:
    """Run the real shared AI assembler and return its canonical H,H,I bytes."""
    return build_actual_emitter_payload(
        workspace, text="hhi", targets=("H", "H", "I"),
        batch_id="pc18-actual-emitter-hhi-v1",
        request_id="pc18-request-hhi-v1",
    )


def build_actual_emitter_payload(
    workspace: Path, *, text: str, targets: tuple[str, ...], batch_id: str,
    request_id: str,
) -> bytes:
    """Run the actual shared assembler for one bounded keyboard sequence."""
    context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json")
    parts = _baseline_parts(context, targets)
    observations = {
        target: TargetObservationV2(
            context.targets.resolve("keyboard", target).center, 0.93)
        for target in dict.fromkeys(targets)
    }
    payload = assemble(
        _plan(text, targets), batch_id=batch_id, request_id=request_id,
        observations=observations, **parts,
    )
    if payload is None:
        raise ActualOutputCompatibilityError("actual HHI emitter abstained")
    return payload


def _registry_for_batch(
    context: Any, batch: ModelMotionBatchV2, *,
    minimum_confidence: float = 0.9,
) -> TrustedMotionRegistryV2:
    target_ids = tuple(batch.uncertainty.covered_target_ids)
    qualification = TrustedLocalizationQualificationV2(
        qualification_sha256=batch.uncertainty.qualification_sha256,
        model_id=batch.evidence.model_id,
        model_sha256=batch.evidence.model_sha256,
        evidence_method_sha256=batch.uncertainty.evidence_method_sha256,
        domain_id=batch.uncertainty.domain_id,
        target_catalog_sha256=batch.geometry.target_catalog_sha256,
        bound_type=batch.uncertainty.bound_type,
        error_bound_mm=batch.uncertainty.error_bound_mm,
        coverage_probability=batch.uncertainty.coverage_probability,
        target_ids=target_ids,
    )
    regions = []
    for target_id in target_ids:
        target = context.targets.resolve("keyboard", target_id)
        left, front, right, rear = target.safe_rectangle_board_mm
        regions.append(MeasuredTargetRegionV2(
            target_id=target_id, coordinate_frame="board",
            coordinate_profile=batch.geometry.coordinate_profile,
            board_frame_definition_sha256=(
                batch.geometry.board_frame_definition_sha256),
            vertices_xy_mm=((left, front), (right, front), (right, rear),
                            (left, rear)),
            surface_z_mm=target.center.z,
            surface_normal_error_bound_mm=0.1,
            placement_error_bound_mm=0.25,
            placement_observation_sha256=(
                batch.geometry.placement_observation_sha256),
            target_catalog_sha256=batch.geometry.target_catalog_sha256,
        ))
    evidence = batch.evidence
    return TrustedMotionRegistryV2(
        capability_profile_id=batch.capability.profile_id,
        capability_profile_sha256=batch.capability.profile_sha256,
        capture_id=evidence.capture_id, frame_id=evidence.frame_id,
        image_sha256=evidence.image_sha256,
        capture_clock_domain_id=evidence.capture_clock_domain_id,
        camera_identity_sha256=evidence.camera_identity_sha256,
        scene_lease_id=evidence.scene_lease_id,
        scene_lease_issuer_id=evidence.scene_lease_issuer_id,
        scene_lease_sha256=evidence.scene_lease_sha256,
        scene_lease_expires_at_epoch_ms=evidence.expires_at_epoch_ms,
        scene_observation_sha256=evidence.scene_observation_sha256,
        precision_observation_sha256=evidence.precision_observation_sha256,
        fusion_decision_sha256=evidence.fusion_decision_sha256,
        placement_observation_sha256=(
            batch.geometry.placement_observation_sha256),
        board_frame_definition_sha256=(
            batch.geometry.board_frame_definition_sha256),
        target_catalog_sha256=batch.geometry.target_catalog_sha256,
        maximum_scene_age_ms=20_000,
        minimum_observation_confidence=minimum_confidence,
        maximum_surface_normal_error_mm=0.5,
        qualification=qualification, target_regions=tuple(regions),
    )


def _blocker_code(exc: Exception) -> str:
    message = str(exc)
    known = {
        "composed uncertainty leaves measured region": (
            "COMPOSED_UNCERTAINTY_OUTSIDE_REGION"),
        "future-dated or expired": "STALE_OR_EXPIRED_EVIDENCE",
        "differs from trusted evidence": "CROSSED_EVIDENCE_IDENTITY",
        "confidence is below policy": "CONFIDENCE_BELOW_POLICY",
    }
    for fragment, code in known.items():
        if fragment in message:
            return code
    raise ActualOutputCompatibilityError(
        f"unclassified arm blocker: {type(exc).__name__}: {message}") from exc


def _decoder_blocker_code(exc: Exception) -> str:
    message = str(exc)
    known = {
        "violates zero authority": "AUTHORITY_INJECTION",
        "duplicate JSON field": "DUPLICATE_JSON_FIELD",
        "non-finite JSON constant": "NONFINITE_NUMBER",
        "action indexes must be ordered and contiguous": "REORDERED_ACTIONS",
    }
    for fragment, code in known.items():
        if fragment in message:
            return code
    raise ActualOutputCompatibilityError(
        f"unclassified decoder blocker: {type(exc).__name__}: {message}") from exc


def _zero_authority(result: Mapping[str, Any]) -> None:
    if (result.get("controller_commands") != []
            or result.get("hardware_access") is not False
            or result.get("physical_authority") is not False):
        raise ActualOutputCompatibilityError("case crossed zero-authority boundary")


def _accepted_case(
    workspace: Path, retained: bytes, *, case_id: str, text: str,
    targets: tuple[str, ...], batch_id: str, request_id: str,
) -> dict[str, Any]:
    reproduced = build_actual_emitter_payload(
        workspace, text=text, targets=targets, batch_id=batch_id,
        request_id=request_id)
    if retained != reproduced + b"\n":
        raise ActualOutputCompatibilityError("retained HHI bytes do not reproduce")
    context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json")
    plan = _plan(text, targets)
    batch = decode_model_motion_batch_v2_json(retained)
    registry = _registry_for_batch(context, batch)
    ingress = ingest_with_trusted_registry_v2(
        batch, plan, context, registry=registry,
        current_time_epoch_ms=T0 + 3_000,
        current_monotonic_ns=9_000_000_000,
    )
    preplanner = revalidate_with_trusted_registry_v2(
        ingress, registry=registry, current_monotonic_ns=10_000_000_000)
    _zero_authority(ingress)
    _zero_authority(preplanner)
    execution = compile_typing_execution_plan_v1(
        batch, ingress,
        config=TypingExecutionConfigV1(
            config_id="pc18-offline-zero-authority-v1",
            calibration_snapshot_sha256="1" * 64,
            tool_profile_sha256="2" * 64,
            dynamics_profile_sha256="3" * 64,
            route_reference_point=Point3Mm("board", 0.0, 0.0, 50.0),
            hover_clearance_mm=25.0,
            settle_position_tolerance_mm=0.5,
            settle_velocity_tolerance_mm_s=1.0,
            settle_hold_ms=100, preview_horizon=1,
            speed_class=SpeedClass.SLOW,
        ),
    )
    trajectory = compile_typing_trajectory_plan_v1(
        execution,
        policy=TypingTrajectoryPolicyV1(
            policy_id="pc18-offline-quintic-v1",
            maximum_cartesian_step_mm=5.0,
            maximum_velocity_mm_s=80.0,
            maximum_acceleration_mm_s2=160.0,
            maximum_jerk_mm_s3=800.0,
            hover_settle_ms=100, contact_dwell_ms=60,
        ),
    )
    contact_order = [
        item.target_id for item in trajectory.phase_waypoints
        if item.phase.value == "CONTACT"
    ]
    result = {
        "case_id": case_id,
        "source_class": "ACTUAL_AI_BATCH_EMITTER",
        "disposition": "TRAJECTORY_COMPILED",
        "ordered_target_ids": list(targets),
        "contact_target_ids": contact_order,
        "batch_payload_sha256": _sha256(retained),
        "batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress["ingress_sha256"],
        "preplanner_gate_sha256": preplanner["preplanner_gate_sha256"],
        "execution_plan_sha256": execution.plan_sha256,
        "trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "controller_commands": [], "hardware_access": False,
        "physical_authority": False,
    }
    _zero_authority(result)
    return result


def _accepted_hhi_case(workspace: Path, retained: bytes) -> dict[str, Any]:
    return _accepted_case(
        workspace, retained, case_id="actual-emitter-hhi-supported",
        text="hhi", targets=("H", "H", "I"),
        batch_id="pc18-actual-emitter-hhi-v1",
        request_id="pc18-request-hhi-v1",
    )


def _blocked_case(
    workspace: Path, *, case_id: str, payload: bytes, plan: ActionPlan,
    registry: TrustedMotionRegistryV2 | None = None,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json")
    batch = decode_model_motion_batch_v2_json(payload)
    active_registry = registry or _registry_for_batch(context, batch)
    try:
        ingest_with_trusted_registry_v2(
            batch, plan, context, registry=active_registry,
            current_time_epoch_ms=(now_epoch_ms if now_epoch_ms is not None
                                   else batch.evidence.evaluated_at_epoch_ms),
            current_monotonic_ns=9_000_000_000,
        )
    except ModelMotionIngressV2Error as exc:
        return {
            "case_id": case_id,
            "source_class": "ACTUAL_OR_DERIVED_AI_BATCH",
            "disposition": "ARM_INGRESS_BLOCKED",
            "blocker_code": _blocker_code(exc),
            "ordered_target_ids": [item.target_id for item in batch.proposals],
            "batch_payload_sha256": _sha256(payload),
            "batch_sha256": batch.batch_sha256,
            "controller_commands": [], "hardware_access": False,
            "physical_authority": False,
        }
    raise ActualOutputCompatibilityError(f"{case_id} unexpectedly passed ingress")


def _derived_payload(
    workspace: Path, *, confidence: float = 0.93,
    image_sha256: str | None = None,
) -> bytes:
    context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json")
    targets = ("H", "H", "I")
    parts = _baseline_parts(context, targets)
    if image_sha256 is not None:
        parts["evidence"] = replace(parts["evidence"], image_sha256=image_sha256)
    observations = {
        target: TargetObservationV2(
            context.targets.resolve("keyboard", target).center, confidence)
        for target in dict.fromkeys(targets)
    }
    payload = assemble(
        _plan("hhi", targets), batch_id="pc18-derived-hhi-v1",
        request_id="pc18-derived-request-v1", observations=observations,
        **parts,
    )
    if payload is None:
        raise ActualOutputCompatibilityError("derived emitter unexpectedly abstained")
    return payload


def _validate_abstention(payload: bytes) -> dict[str, Any]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ActualOutputCompatibilityError("abstention record is not JSON") from exc
    if (document.get("status") != "ABSTAINED" or document.get("batch") is not None
            or document.get("fusion", {}).get("reasons")
            != ["localization_uncalibrated"]
            or document.get("controller_commands") != []
            or document.get("hardware_writes") != 0
            or document.get("physical_execution_authorized") is not False):
        raise ActualOutputCompatibilityError("abstention record changed meaning")
    return {
        "case_id": "actual-localization-abstention",
        "source_class": "ACTUAL_AI_PRECISION_FUSION",
        "disposition": "PRODUCER_ABSTAINED",
        "blocker_code": "LOCALIZATION_UNCALIBRATED",
        "ordered_target_ids": document["fusion"]["required_targets"],
        "source_file_sha256": _sha256(payload),
        "controller_commands": [], "hardware_access": False,
        "physical_authority": False,
    }


def _unsupported_phone_case(workspace: Path) -> dict[str, Any]:
    context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json")
    parts = _baseline_parts(context, ("H", "I"))
    phone = ActionPlan.from_text(
        device=Device.PHONE, profile_id="phone-development-v1", text="open",
        actions=(VerifyPhoneState("home"),),
        required_calibrations=("phone_pose", "phone_tcp"),
    )
    try:
        assemble(phone, batch_id="pc18-phone", request_id="pc18-phone",
                 observations={}, **parts)
    except ValueError as exc:
        if "keyboard PressKey plans only" not in str(exc):
            raise ActualOutputCompatibilityError(
                "unsupported request failed for an unexpected reason") from exc
        return {
            "case_id": "unsupported-phone-request",
            "source_class": "ACTUAL_AI_BATCH_EMITTER",
            "disposition": "PRODUCER_REJECTED",
            "blocker_code": "UNSUPPORTED_PHONE_REQUEST",
            "ordered_target_ids": [],
            "controller_commands": [], "hardware_access": False,
            "physical_authority": False,
        }
    raise ActualOutputCompatibilityError("unsupported phone request was emitted")


def _decoder_blocked_case(
    *, case_id: str, retained: bytes, mutation: str,
) -> dict[str, Any]:
    document = json.loads(retained)
    targets = [item["target_id"] for item in document["proposals"]]
    if mutation == "authority":
        document["hardware_access"] = True
        payload = _canonical(document)
    elif mutation == "duplicate":
        text = retained.decode("utf-8")
        needle = f'"batch_id":"{document["batch_id"]}"'
        payload = text.replace(
            needle, needle + ',"batch_id":"other-batch"', 1).encode("utf-8")
    elif mutation == "nonfinite":
        document["proposals"][0]["target_mm"]["x"] = float("nan")
        payload = json.dumps(
            document, sort_keys=True, separators=(",", ":"), allow_nan=True,
        ).encode("utf-8")
    elif mutation == "reorder":
        document["proposals"] = list(reversed(document["proposals"]))
        targets = [item["target_id"] for item in document["proposals"]]
        payload = _canonical(document)
    else:
        raise ActualOutputCompatibilityError("unsupported decoder mutation")
    try:
        decode_model_motion_batch_v2_json(payload)
    except ModelMotionBatchV2Error as exc:
        return {
            "case_id": case_id,
            "source_class": "DERIVED_FROM_ACTUAL_AI_BATCH",
            "disposition": "STRICT_DECODER_BLOCKED",
            "blocker_code": _decoder_blocker_code(exc),
            "ordered_target_ids": targets,
            "source_file_sha256": _sha256(retained),
            "mutated_payload_sha256": _sha256(payload),
            "controller_commands": [], "hardware_access": False,
            "physical_authority": False,
        }
    raise ActualOutputCompatibilityError(f"{case_id} passed strict decoding")


def run_actual_output_compatibility_v1(
    workspace: Path, corpus_path: Path,
) -> dict[str, Any]:
    """Reproduce the retained corpus and return a content-addressed report."""
    workspace = workspace.resolve()
    corpus_bytes = corpus_path.read_bytes()
    corpus = json.loads(corpus_bytes)
    if corpus.get("schema") != CORPUS_SCHEMA:
        raise ActualOutputCompatibilityError("unsupported corpus schema")
    root = corpus_path.parent
    files = corpus.get("retained_files")
    if not isinstance(files, Mapping):
        raise ActualOutputCompatibilityError("corpus retained_files is missing")

    retained: dict[str, bytes] = {}
    for file_id, record in files.items():
        path = (root / record["relative_path"]).resolve()
        if root.resolve() not in path.parents:
            raise ActualOutputCompatibilityError("retained path escapes corpus root")
        payload = path.read_bytes()
        if _sha256(payload) != record["sha256"]:
            raise ActualOutputCompatibilityError(f"{file_id} hash differs")
        retained[file_id] = payload

    actual_hhi = retained["actual_emitter_hhi"]
    hhi_batch = decode_model_motion_batch_v2_json(actual_hhi)
    hhi_plan = _plan("hhi", ("H", "H", "I"))
    mixed_targets = (
        "R", "O", "B", "O", "T", "SPACE", "B", "O", "O", "K", "SPACE",
        "1", "0", "PERIOD", "ENTER")
    all46_targets = tuple(sorted(load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json"
    ).targets.keyboard_targets))
    context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json")
    baseline_registry = _registry_for_batch(context, hhi_batch)

    precision = retained["precision_adapter_hh1_period"]
    precision_plan = _plan("hh1.", ("H", "H", "1", "PERIOD"))
    precision_case = _blocked_case(
        workspace, case_id="actual-precision-hh1-period-uncertain",
        payload=precision, plan=precision_plan,
    )

    crossed = _derived_payload(workspace, image_sha256="1" * 64)
    low_confidence = _derived_payload(workspace, confidence=0.4)
    cases = [
        _accepted_hhi_case(workspace, actual_hhi),
        _accepted_case(
            workspace, retained["actual_emitter_mixed"],
            case_id="actual-emitter-mixed-supported",
            text="robot book 10.\n", targets=mixed_targets,
            batch_id="pc18-actual-emitter-mixed-v1",
            request_id="pc18-request-mixed-v1"),
        _accepted_case(
            workspace, retained["actual_emitter_all46"],
            case_id="actual-emitter-all46-supported",
            text="all-46-keyboard-targets-v1", targets=all46_targets,
            batch_id="pc18-actual-emitter-all46-v1",
            request_id="pc18-request-all46-v1"),
        precision_case,
        _validate_abstention(retained["localization_abstention"]),
        _unsupported_phone_case(workspace),
        _blocked_case(
            workspace, case_id="derived-stale-evidence", payload=actual_hhi,
            plan=hhi_plan, registry=baseline_registry,
            now_epoch_ms=hhi_batch.evidence.expires_at_epoch_ms,
        ),
        _blocked_case(
            workspace, case_id="derived-crossed-image-identity", payload=crossed,
            plan=hhi_plan, registry=baseline_registry,
        ),
        _blocked_case(
            workspace, case_id="derived-low-confidence", payload=low_confidence,
            plan=hhi_plan,
        ),
        _decoder_blocked_case(
            case_id="derived-authority-injection", retained=actual_hhi,
            mutation="authority"),
        _decoder_blocked_case(
            case_id="derived-duplicate-json", retained=actual_hhi,
            mutation="duplicate"),
        _decoder_blocked_case(
            case_id="derived-nonfinite-coordinate", retained=actual_hhi,
            mutation="nonfinite"),
        _decoder_blocked_case(
            case_id="derived-reordered-actions", retained=actual_hhi,
            mutation="reorder"),
    ]
    expected = corpus.get("expected_cases")
    observed = {
        case["case_id"]: {
            "disposition": case["disposition"],
            "blocker_code": case.get("blocker_code"),
            "ordered_target_ids": case["ordered_target_ids"],
        }
        for case in cases
    }
    if observed != expected:
        raise ActualOutputCompatibilityError("observed compatibility outcomes differ")
    for case in cases:
        _zero_authority(case)

    unsigned = {
        "schema": SCHEMA,
        "corpus_id": corpus["corpus_id"],
        "corpus_file_sha256": _sha256(corpus_bytes),
        "case_count": len(cases),
        "passed_case_count": len(cases),
        "cases": cases,
        "actual_sources": 5,
        "derived_adversarial_cases": 7,
        "maximum_batch_bytes": MAX_BATCH_BYTES_V2,
        "maximum_batch_proposals": MAX_BATCH_PROPOSALS_V2,
        "largest_retained_batch_bytes": max(
            len(actual_hhi), len(retained["actual_emitter_mixed"]),
            len(retained["actual_emitter_all46"]), len(precision)),
        "largest_retained_proposal_count": max(
            len(hhi_batch.proposals),
            len(decode_model_motion_batch_v2_json(
                retained["actual_emitter_mixed"]).proposals),
            len(decode_model_motion_batch_v2_json(
                retained["actual_emitter_all46"]).proposals),
            len(decode_model_motion_batch_v2_json(precision).proposals)),
        "production_dispatch_allowed": False,
        "installation_authorized": False,
        "controller_start_authorized": False,
        "execution_authorized": False,
        "automatic_retry": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**unsigned, "report_sha256": _sha256(_canonical(unsigned))}


__all__ = [
    "ActualOutputCompatibilityError", "CORPUS_SCHEMA", "SCHEMA",
    "build_actual_emitter_hhi_payload", "build_actual_emitter_payload",
    "run_actual_output_compatibility_v1",
]
