from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.collision_readiness import assess_current_collision_readiness
from rocell.application.context import load_simulation_context
from rocell.application.fixed_camera_keyboard_clearance_intake_v1 import (
    FixedCameraKeyboardClearanceIntakeV1Error,
    binding_template,
    compile_clearance_intake,
    main,
)
from rocell.application.installed_collision_geometry import (
    InstalledCollisionGeometryProfile,
)
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


ROOT = Path(__file__).resolve().parents[3]
BINDING_SCHEMA = ROOT / (
    "software/ai/schemas/keyboard_clearance_profile_bindings_v1.schema.json")
RESULT_SCHEMA = ROOT / (
    "software/ai/schemas/fixed_camera_keyboard_clearance_intake_v1.schema.json")
MANIFEST = ROOT / "software/config/system_manifest.json"


@pytest.fixture(scope="module")
def context():
    return load_simulation_context(ROOT, MANIFEST)


def _localization() -> dict:
    profiles = {}
    for profile in ("no_attachment", "stylus_attachment"):
        blockers = ["PHYSICAL_CLEARANCE_UNVERIFIED"]
        if profile == "stylus_attachment":
            blockers.extend(["STYLUS_TCP_UNVERIFIED", "STYLUS_TRAJECTORY_UNVERIFIED"])
        profiles[profile] = {
            "profile": profile,
            "board_to_robot_transform_verified": True,
            "robot_frame_localization_candidates_emitted": True,
            "robot_frame_localization_candidates": [
                {"key_id": f"K{index:02d}", "robot_xyz_mm": [index, index + 1, 91.0]}
                for index in range(46)
            ],
            "motion_targets_emitted": False,
            "physical_clearance_verified": False,
            "motion_authorized": False,
            "contact_authorized": False,
            "blockers": blockers,
        }
    return {
        "schema": "rocell.fixed_camera_keyboard_robot_localization.v1",
        "status": "ROBOT_FRAME_LOCALIZATION_CANDIDATES_READY",
        "measurement_sha256": "1" * 64,
        "keyboard_package_sha256": "2" * 64,
        "target_profile_sha256": "3" * 64,
        "transform": {},
        "fit_residuals_mm": {},
        "holdout_residuals_mm": {},
        "board_to_robot_transform_verified": True,
        "profiles": profiles,
        "profile_separation_preserved": True,
        "motion_targets_emitted": False,
        "physical_clearance_verified": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "limitations": [],
    }


def _profiles(context) -> dict[str, InstalledCollisionGeometryProfile]:
    readiness = assess_current_collision_readiness(context)
    bodies = tuple(
        CollisionBody(
            requirement.body_id,
            requirement.parent_frame,
            requirement.role,
            CollisionEvidenceState.ACCEPTED_MEASURED,
            (() if requirement.binding_mode is CollisionBindingMode.CONFIGURATION_SAMPLED
             else (SphereMm(Vec3(50_000.0 + index, 0.0, 0.0), 0.1),)),
            requirement.binding_mode,
            "unit-test measured geometry",
        )
        for index, requirement in enumerate(readiness.contract.requirements)
    )
    contract = CollisionGeometryContract(
        "keyboard-clearance-intake-test",
        readiness.contract.root_frame,
        readiness.contract.requirements,
        bodies,
        readiness.contract.pair_exclusions,
    )
    policy = CollisionClearancePolicy(
        0.1,
        0.05,
        0.05,
        CollisionClearanceEvidenceState.ACCEPTED_MEASURED,
        "unit-test measured clearance",
    )
    return {
        profile: InstalledCollisionGeometryProfile(
            f"{profile}-installed-profile",
            readiness.manifest_id,
            readiness.manifest_sha256,
            readiness.active_build_id,
            readiness.build_snapshot_hash,
            readiness.urdf_sha256,
            readiness.contract.content_hash,
            {"metrology": str(index + 4) * 64},
            contract,
            policy,
            str(index + 6) * 64,
            str(index + 8) * 64,
        )
        for index, profile in enumerate(("no_attachment", "stylus_attachment"))
    }


def _bindings(localization: dict, profiles: dict) -> dict:
    import hashlib

    raw = json.dumps(
        localization, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()
    value = binding_template(hashlib.sha256(raw).hexdigest())
    value["status"] = "REVIEWED_ATTACHMENT_PROFILE_BINDINGS"
    value["review"] = {
        "reviewed": True,
        "reviewer": "test reviewer",
        "reviewed_at": "2026-10-17T18:00:00-04:00",
        "notes": "synthetic unit-test bindings",
    }
    for row in value["profiles"]:
        installed = profiles[row["profile"]]
        row["installed_collision_profile_id"] = installed.profile_id
        row["installed_collision_profile_file_sha256"] = installed.file_sha256
        if row["profile"] == "stylus_attachment":
            row["measured_tcp_sha256"] = "a" * 64
    return value


def test_template_is_schema_valid_and_zero_claim():
    value = binding_template()
    jsonschema.Draft202012Validator(
        json.loads(BINDING_SCHEMA.read_text())).validate(value)
    assert value["status"] == "DRAFT_UNREVIEWED"
    assert value["review"]["reviewed"] is False


def test_cli_writes_blank_local_template(tmp_path):
    destination = tmp_path / "bindings.json"
    assert main(["--write-template", str(destination)]) == 0
    value = json.loads(destination.read_text())
    assert value == binding_template()


def test_exact_profiles_prepare_separate_zero_authority_handoff(context):
    localization = _localization()
    profiles = _profiles(context)
    bindings = _bindings(localization, profiles)
    result = compile_clearance_intake(
        localization, bindings, profiles, context=context)
    jsonschema.Draft202012Validator(
        json.loads(RESULT_SCHEMA.read_text())).validate(result)

    assert result["status"] == "READY_FOR_PROFILE_SPECIFIC_ROUTE_CONSTRUCTION"
    assert result["profiles"]["no_attachment"]["candidate_count"] == 46
    assert result["profiles"]["stylus_attachment"]["measured_tcp_sha256"] == "a" * 64
    assert (result["profiles"]["no_attachment"]["installed_collision_profile_id"]
            != result["profiles"]["stylus_attachment"]["installed_collision_profile_id"])
    assert result["trajectory_generated"] is False
    assert result["collision_screening_executed"] is False
    assert result["continuous_clearance_verified"] is False
    assert result["controller_commands"] == []
    assert result["physical_authority"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda bindings, profiles: bindings.update({"status": "DRAFT_UNREVIEWED"}),
         "unreviewed"),
        (lambda bindings, profiles: bindings["profiles"][1].update(
            {"measured_tcp_sha256": None}), "stylus measured TCP"),
        (lambda bindings, profiles: bindings["profiles"][1].update(
            {"installed_collision_profile_file_sha256":
             bindings["profiles"][0]["installed_collision_profile_file_sha256"]}),
         "must be distinct"),
        (lambda bindings, profiles: profiles.update(
            {"stylus_attachment": profiles["no_attachment"]}),
         "differs from reviewed binding"),
    ],
)
def test_crossed_or_unreviewed_profile_evidence_is_rejected(
    context, mutation, message,
):
    localization = _localization()
    profiles = _profiles(context)
    bindings = _bindings(localization, profiles)
    mutation(bindings, profiles)
    with pytest.raises(FixedCameraKeyboardClearanceIntakeV1Error, match=message):
        compile_clearance_intake(localization, bindings, profiles, context=context)


def test_changed_localization_or_incomplete_candidate_set_is_rejected(context):
    localization = _localization()
    profiles = _profiles(context)
    bindings = _bindings(localization, profiles)
    changed = copy.deepcopy(localization)
    changed["profiles"]["no_attachment"][
        "robot_frame_localization_candidates"].pop()
    with pytest.raises(
        FixedCameraKeyboardClearanceIntakeV1Error,
        match="candidate coverage is incomplete",
    ):
        compile_clearance_intake(changed, bindings, profiles, context=context)
