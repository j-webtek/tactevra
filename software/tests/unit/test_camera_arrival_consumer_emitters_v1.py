from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from rocell.application.camera_arrival_consumer_emitters_v1 import (
    CameraArrivalConsumerEmitterV1Error,
    emit_camera_campaign_consumer_receipt_v1,
    emit_camera_localization_consumer_receipt_v1,
    emit_camera_support_consumer_receipt_v1,
    emit_installed_collision_consumer_receipt_v1,
    emit_planner_snapshot_consumer_receipt_v1,
)
from rocell.application.camera_arrival_consumer_handoff_v1 import (
    build_camera_arrival_consumer_handoff_v1,
)
from rocell.application.camera_arrival_consumer_operator_v1 import (
    CameraArrivalConsumerOperatorV1Error,
    emit_camera_arrival_consumer_operator_receipt_v1,
    main as operator_main,
    write_camera_arrival_consumer_operator_receipt_v1,
)
from rocell.application.camera_arrival_consumer_validation_v1 import (
    assess_camera_arrival_consumer_validation_v1,
    parse_camera_arrival_consumer_validation_receipt_v1,
)
from rocell.application.camera_arrival_kit_v1 import build_camera_arrival_kit_v1
from rocell.application.collision_readiness import assess_current_collision_readiness
from rocell.application.context import load_simulation_context
from rocell.application.installed_collision_geometry import (
    InstalledCollisionGeometryProfile,
)
from rocell.application.installed_cable_envelope_intake_v1 import (
    InstalledCableEnvelopeIntakeV1,
    InstalledCableEnvelopeIntakeV1Error,
    build_synthetic_cable_envelope_intake_v1,
)
from rocell.calibration.planner_snapshot import PlannerCalibrationSnapshot
from rocell.geometry import RigidTransform, Rotation3, Vec3
from rocell.simulation.collision import (
    CollisionClearanceEvidenceState,
    CollisionClearancePolicy,
)


ROOT = Path(__file__).resolve().parents[3]
H = "a" * 64
WHEN = "2026-09-29T15:00:00Z"
CABLE_VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/installed_cable_envelope_intake_v1.schema.json"
).read_text(encoding="utf-8")))


def _hash(core: dict) -> str:
    raw = json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _populate(root: Path) -> None:
    for slot in build_camera_arrival_kit_v1()["slots"]:
        relative = f"sources/{slot['artifact_id']}.bin"
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        payload = slot["artifact_id"].encode()
        source.write_bytes(payload)
        uncertainty = None if not slot["uncertainty_required"] else {
            "value": 0.1, "unit": slot["required_units"][0],
            "method": "fixture bound", "evidence_sha256": H,
        }
        sidecar = root / slot["destination_relative_to_external_evidence_root"]
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps({
            "schema": "rocell.camera_arrival_original.v1",
            "artifact_id": slot["artifact_id"],
            "artifact_class": slot["artifact_class"],
            "captured_at_utc": "2026-09-29T12:00:00Z",
            "source_relative_path": relative, "source_size_bytes": len(payload),
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "units": slot["required_units"], "uncertainty": uncertainty,
            "configuration_epoch_id": "camera-epoch-001",
            "review": {
                "reviewer_id": "owner-ai-review",
                "reviewed_at_utc": "2026-09-29T13:00:00Z",
                "disposition": "ACCEPTED", "review_sha256": H,
            },
        }), encoding="utf-8")


def _support(*, blocked: str | None = None) -> dict:
    bindings = []
    for artifact_id in (
        "camera_receipt", "camera_identity", "camera_mode_controls", "support_witnesses"
    ):
        blockers = ["EVIDENCE_STALE"] if artifact_id == blocked else []
        bindings.append({
            "binding_id": artifact_id,
            "status": "BLOCKED" if blockers else "READY",
            "blockers": blockers,
        })
    core = {
        "schema": "rocell.camera_support_optics_epoch_assessment.v1",
        "status": "BLOCKED" if blocked else "READY_FOR_COMPONENT_ADMISSION",
        "binding_assessments": bindings,
        "component_admission_ready": blocked is None,
        "epoch_advanced": False, "hardware_access": False,
        "camera_open_authorized": False, "installation_authorized": False,
        "controller_start_authorized": False, "transport_authorized": False,
        "execution_authorized": False, "physical_authority": False,
    }
    return {**core, "assessment_sha256": _hash(core)}


def _campaign() -> dict:
    core = {
        "schema": "rocell.physical_camera_localization_campaign_preflight.v1",
        "status": "READY_FOR_OFFLINE_EVALUATION", "camera_opened": False,
        "model_loaded": False, "controller_started": False,
        "hardware_writes": 0, "physical_movements": 0,
        "qualification_installed": False,
    }
    return {**core, "receipt_sha256": _hash(core)}


def _evaluation(*, passed: bool = True) -> dict:
    criteria = {
        "held_out_coverage_met": passed,
        "unsafe_false_accepts_zero": True,
    }
    core = {
        "schema": "rocell.physical_camera_localization_evaluation_result.v1",
        "status": "QUALIFICATION_RECOMMENDED" if passed else "QUALIFICATION_BLOCKED",
        "criteria": criteria, "qualification_installed": False,
        "physical_deployment_qualified": False,
        "model_motion_batch_emitted": False, "controller_started": False,
        "hardware_writes": 0, "physical_movements": 0,
    }
    return {**core, "result_sha256": _hash(core)}


def _planner_snapshot() -> PlannerCalibrationSnapshot:
    return PlannerCalibrationSnapshot(
        device="keyboard", manifest_id="manifest", active_build_id="build",
        artifact_hashes={
            "robot_reference": "1" * 64, "arm_board": "2" * 64,
            "controller_correlation": "3" * 64, "keyboard_pose": "4" * 64,
            "keyboard_tcp": "5" * 64,
        },
        board_T_vendor_world=RigidTransform(
            "B", "Wv", Rotation3.identity(), Vec3.zero()
        ),
        board_T_device=RigidTransform(
            "B", "keyboard", Rotation3.identity(), Vec3.zero()
        ),
        hand_T_tool=RigidTransform(
            "G", "T", Rotation3.identity(), Vec3.zero()
        ),
        robot_reference_identity={
            "arm_identity_hash": "6" * 64,
            "controller_identity_hash": "7" * 64,
            "firmware_identity_hash": "8" * 64,
        },
        joint_zero_offsets_rad=(0.0,) * 6,
        joint_lower_rad=(-2.0,) * 6,
        joint_upper_rad=(2.0,) * 6,
        joint_signs=(1, -1, 1, 1, -1, 1),
        controller_correlation={"qualified": True},
        target_map_sha256="9" * 64,
    )


def _incomplete_collision_profile() -> InstalledCollisionGeometryProfile:
    context = load_simulation_context(ROOT, ROOT / "software/config/system_manifest.json")
    readiness = assess_current_collision_readiness(context)
    policy = CollisionClearancePolicy(
        minimum_separation_mm=2.0,
        geometry_uncertainty_mm_per_body=0.5,
        pose_uncertainty_mm_per_body=0.5,
        evidence_state=CollisionClearanceEvidenceState.ACCEPTED_MEASURED,
        source_reference="fixture",
    )
    return InstalledCollisionGeometryProfile(
        profile_id="fixture", manifest_id=readiness.manifest_id,
        manifest_sha256=readiness.manifest_sha256,
        active_build_id=readiness.active_build_id,
        build_snapshot_sha256=readiness.build_snapshot_hash,
        robot_model_sha256=readiness.urdf_sha256,
        base_contract_sha256=readiness.contract.content_hash,
        source_bindings={"fixture": H}, contract=readiness.contract,
        clearance_policy=policy, content_sha256=H, file_sha256=H,
    )


def test_existing_explicit_consumers_emit_eight_exact_pass_receipts(tmp_path: Path):
    _populate(tmp_path)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    receipts = []
    support = _support()
    for artifact_id in (
        "camera_receipt", "camera_identity", "camera_mode_controls", "support_witnesses"
    ):
        receipts.append(emit_camera_support_consumer_receipt_v1(
            handoff, artifact_id, support, validated_at_utc=WHEN
        ))
    campaign = _campaign()
    for artifact_id in ("camera_intrinsics", "localization_campaign"):
        receipts.append(emit_camera_campaign_consumer_receipt_v1(
            handoff, artifact_id, campaign, validated_at_utc=WHEN
        ))
    evaluation = _evaluation()
    for artifact_id in ("camera_to_board_transform", "localization_evaluation"):
        receipts.append(emit_camera_localization_consumer_receipt_v1(
            handoff, artifact_id, evaluation, validated_at_utc=WHEN
        ))
    assert all(dict(parse_camera_arrival_consumer_validation_receipt_v1(row)) == row for row in receipts)
    assessment = assess_camera_arrival_consumer_validation_v1(handoff, receipts)
    assert assessment["pass_count"] == 8
    assert assessment["pending_count"] == 7
    assert assessment["complete_for_offline_review"] is False
    assert assessment["physical_authority"] is False


def test_native_blocker_is_retained_with_native_output_hash(tmp_path: Path):
    _populate(tmp_path)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    receipt = emit_camera_localization_consumer_receipt_v1(
        handoff, "localization_evaluation", _evaluation(passed=False),
        validated_at_utc=WHEN,
    )
    assert receipt["validation_status"] == "BLOCKED"
    assert receipt["blockers"] == ["CRITERION_HELD_OUT_COVERAGE_MET"]
    assert len(receipt["output_sha256"]) == 64


def test_support_emitter_preserves_route_local_blocker(tmp_path: Path):
    _populate(tmp_path)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    receipt = emit_camera_support_consumer_receipt_v1(
        handoff, "camera_identity", _support(blocked="camera_identity"),
        validated_at_utc=WHEN,
    )
    assert receipt["validation_status"] == "BLOCKED"
    assert receipt["blockers"] == ["EVIDENCE_STALE"]


def test_typed_planner_snapshot_emits_all_five_planner_receipts(tmp_path: Path):
    _populate(tmp_path)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    snapshot = _planner_snapshot()
    artifact_ids = (
        "board_to_robot_transform", "keyboard_to_board_transform",
        "tool_to_joint_transform", "keyboard_profile", "tool_profile",
    )
    receipts = [
        emit_planner_snapshot_consumer_receipt_v1(
            handoff, artifact_id, snapshot, validated_at_utc=WHEN
        )
        for artifact_id in artifact_ids
    ]
    assert [row["artifact_id"] for row in receipts] == list(artifact_ids)
    assert all(row["validation_status"] == "PASS" for row in receipts)
    assert len({row["output_sha256"] for row in receipts}) == 1


def test_typed_collision_profile_preserves_geometry_and_cable_gaps(tmp_path: Path):
    _populate(tmp_path)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    profile = _incomplete_collision_profile()
    geometry = emit_installed_collision_consumer_receipt_v1(
        handoff, "installed_geometry", profile, validated_at_utc=WHEN
    )
    cable = emit_installed_collision_consumer_receipt_v1(
        handoff, "cable_envelope", profile, validated_at_utc=WHEN
    )
    assert geometry["validation_status"] == "BLOCKED"
    assert any(item.startswith("GEOMETRY_") for item in geometry["blockers"])
    assert cable["validation_status"] == "BLOCKED"
    assert "CONFIGURATION_SAMPLED_BODY:attachment:moving_camera_cable" in cable["blockers"]
    assert geometry["output_sha256"] == cable["output_sha256"]


def test_complete_synthetic_cable_template_passes_only_cable_receipt(
    tmp_path: Path,
):
    _populate(tmp_path)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    profile = _incomplete_collision_profile()
    intake = build_synthetic_cable_envelope_intake_v1(profile)
    document = intake.to_dict()
    CABLE_VALIDATOR.validate(document)
    assert document["evidence_class"] == "SYNTHETIC_OFFLINE_ONLY"
    assert document["template_complete"] is True
    assert document["qualification_installed"] is False
    assert document["physical_authority"] is False
    cable = emit_installed_collision_consumer_receipt_v1(
        handoff, "cable_envelope", intake, validated_at_utc=WHEN
    )
    assert cable["validation_status"] == "PASS"
    with pytest.raises(CameraArrivalConsumerEmitterV1Error, match="only"):
        emit_installed_collision_consumer_receipt_v1(
            handoff, "installed_geometry", intake, validated_at_utc=WHEN
        )


@pytest.mark.parametrize("mutation", ("missing_sweep", "crossed", "source"))
def test_synthetic_cable_template_rejects_incomplete_or_crossed_lineage(
    mutation: str,
):
    profile = _incomplete_collision_profile()
    fixture = build_synthetic_cable_envelope_intake_v1(profile)
    postures = tuple(dict(row) for row in fixture.postures)
    sweeps = tuple(dict(row) for row in fixture.swept_envelopes)
    source = fixture.source_sha256
    if mutation == "missing_sweep":
        sweeps = sweeps[:-1]
    elif mutation == "crossed":
        sweeps[0]["end_posture_id"] = postures[-1]["posture_id"]
    else:
        source = "f" * 64
    with pytest.raises(InstalledCableEnvelopeIntakeV1Error):
        InstalledCableEnvelopeIntakeV1(
            profile, fixture.sampled_body_id, source,
            fixture.maximum_uncertainty_mm, postures, sweeps,
        )


def test_domain_emitters_account_for_all_fifteen_routes(tmp_path: Path):
    _populate(tmp_path)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    receipts = [
        emit_camera_support_consumer_receipt_v1(
            handoff, artifact_id, _support(), validated_at_utc=WHEN
        )
        for artifact_id in (
            "camera_receipt", "camera_identity", "camera_mode_controls",
            "support_witnesses",
        )
    ]
    receipts += [
        emit_camera_campaign_consumer_receipt_v1(
            handoff, artifact_id, _campaign(), validated_at_utc=WHEN
        )
        for artifact_id in ("camera_intrinsics", "localization_campaign")
    ]
    receipts += [
        emit_camera_localization_consumer_receipt_v1(
            handoff, artifact_id, _evaluation(), validated_at_utc=WHEN
        )
        for artifact_id in ("camera_to_board_transform", "localization_evaluation")
    ]
    receipts += [
        emit_planner_snapshot_consumer_receipt_v1(
            handoff, artifact_id, _planner_snapshot(), validated_at_utc=WHEN
        )
        for artifact_id in (
            "board_to_robot_transform", "keyboard_to_board_transform",
            "tool_to_joint_transform", "keyboard_profile", "tool_profile",
        )
    ]
    receipts += [
        emit_installed_collision_consumer_receipt_v1(
            handoff, artifact_id, _incomplete_collision_profile(),
            validated_at_utc=WHEN,
        )
        for artifact_id in ("installed_geometry", "cable_envelope")
    ]
    assert {row["artifact_id"] for row in receipts} == {
        row["artifact_id"] for row in handoff["routes"]
    }
    assessment = assess_camera_arrival_consumer_validation_v1(handoff, receipts)
    assert assessment["pass_count"] == 13
    assert assessment["blocked_count"] == 2
    assert assessment["pending_count"] == 0
    assert assessment["complete_for_offline_review"] is False


def test_common_operator_writes_all_fifteen_canonical_receipts(tmp_path: Path):
    evidence = tmp_path / "evidence"
    outputs = tmp_path / "receipts"
    evidence.mkdir()
    outputs.mkdir()
    _populate(evidence)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, evidence)
    native_by_id = {
        **{artifact_id: _support() for artifact_id in (
            "camera_receipt", "camera_identity", "camera_mode_controls",
            "support_witnesses",
        )},
        **{artifact_id: _campaign() for artifact_id in (
            "camera_intrinsics", "localization_campaign",
        )},
        **{artifact_id: _evaluation() for artifact_id in (
            "camera_to_board_transform", "localization_evaluation",
        )},
        **{artifact_id: _planner_snapshot() for artifact_id in (
            "board_to_robot_transform", "keyboard_to_board_transform",
            "tool_to_joint_transform", "keyboard_profile", "tool_profile",
        )},
        **{artifact_id: _incomplete_collision_profile() for artifact_id in (
            "installed_geometry", "cable_envelope",
        )},
    }
    receipts = []
    for route in handoff["routes"]:
        receipt, destination = write_camera_arrival_consumer_operator_receipt_v1(
            handoff, route["artifact_id"], native_by_id[route["artifact_id"]],
            validated_at_utc=WHEN, output_root=outputs,
        )
        assert destination.name == f"{route['artifact_id']}.json"
        assert json.loads(destination.read_text(encoding="utf-8")) == receipt
        receipts.append(receipt)
    assessment = assess_camera_arrival_consumer_validation_v1(handoff, receipts)
    assert assessment["pass_count"] == 13
    assert assessment["blocked_count"] == 2
    assert assessment["pending_count"] == 0
    assert sorted(path.name for path in outputs.iterdir()) == sorted(
        f"{artifact_id}.json" for artifact_id in native_by_id
    )
    with pytest.raises(CameraArrivalConsumerOperatorV1Error, match="not be overwritten"):
        write_camera_arrival_consumer_operator_receipt_v1(
            handoff, "camera_receipt", _support(), validated_at_utc=WHEN,
            output_root=outputs,
        )


def test_operator_cli_supports_mapping_consumer_and_rejects_typed_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
):
    evidence = tmp_path / "evidence"
    outputs = tmp_path / "receipts"
    evidence.mkdir()
    outputs.mkdir()
    _populate(evidence)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, evidence)
    handoff_path = tmp_path / "handoff.json"
    native_path = tmp_path / "native.json"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    native_path.write_text(json.dumps(_campaign()), encoding="utf-8")
    result = operator_main([
        "--handoff", str(handoff_path), "--artifact-id", "camera_intrinsics",
        "--native-output", str(native_path), "--validated-at-utc", WHEN,
        "--output-root", str(outputs),
    ])
    assert result == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["validation_status"] == "PASS"
    assert summary["camera_opened"] is summary["transport_opened"] is False
    assert summary["hardware_writes"] == summary["physical_movements"] == 0
    assert summary["physical_authority"] is False
    with pytest.raises(SystemExit):
        operator_main([
            "--handoff", str(handoff_path), "--artifact-id", "keyboard_profile",
            "--native-output", str(native_path), "--validated-at-utc", WHEN,
            "--output-root", str(outputs),
        ])


def test_operator_dispatch_rejects_wrong_native_type(tmp_path: Path):
    _populate(tmp_path)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    with pytest.raises(CameraArrivalConsumerOperatorV1Error, match="typed"):
        emit_camera_arrival_consumer_operator_receipt_v1(
            handoff, "installed_geometry", _campaign(), validated_at_utc=WHEN
        )


@pytest.mark.parametrize("failure", ("wrong_route", "tampered", "blocked_handoff"))
def test_emitters_fail_closed(tmp_path: Path, failure: str):
    if failure != "blocked_handoff":
        _populate(tmp_path)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, tmp_path)
    output = _campaign()
    if failure == "wrong_route":
        with pytest.raises(CameraArrivalConsumerEmitterV1Error):
            emit_camera_campaign_consumer_receipt_v1(
                handoff, "camera_receipt", output, validated_at_utc=WHEN
            )
    elif failure == "tampered":
        output["camera_opened"] = True
        with pytest.raises(CameraArrivalConsumerEmitterV1Error):
            emit_camera_campaign_consumer_receipt_v1(
                handoff, "camera_intrinsics", output, validated_at_utc=WHEN
            )
    else:
        with pytest.raises(CameraArrivalConsumerEmitterV1Error):
            emit_camera_campaign_consumer_receipt_v1(
                handoff, "camera_intrinsics", output, validated_at_utc=WHEN
            )
