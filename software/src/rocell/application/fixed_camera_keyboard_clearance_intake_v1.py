"""Bind fixed-camera keyboard localization to installed-clearance evidence.

This boundary preserves the separate bare-jaw and stylus configurations.  It
accepts only reviewed bindings to exact measured installed collision profiles
and emits route-construction inputs for the existing typing collision intake.
It does not construct a trajectory, screen collision, or authorize motion.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .collision_readiness import assess_current_collision_readiness
from .context import SimulationContext, revalidate_simulation_context
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from rocell.simulation.collision import CollisionAttachmentProfile


SCHEMA = "rocell.fixed_camera_keyboard_clearance_intake.v1"
BINDING_SCHEMA = "rocell.keyboard_clearance_profile_bindings.v1"
LOCALIZATION_SCHEMA = "rocell.fixed_camera_keyboard_robot_localization.v1"
REVIEWED_STATUS = "REVIEWED_ATTACHMENT_PROFILE_BINDINGS"
READY_STATUS = "READY_FOR_PROFILE_SPECIFIC_ROUTE_CONSTRUCTION"
SUPPORTED_PROFILES = ("no_attachment", "stylus_attachment")
ATTACHMENT_STATES = {
    "no_attachment": "BARE_JAW",
    "stylus_attachment": "STYLUS_INSTALLED",
}


class FixedCameraKeyboardClearanceIntakeV1Error(ValueError):
    """Localization or attachment-profile evidence is not exact."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            "value is not canonical JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha(value: object, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            f"{label} must be a lowercase SHA-256 digest")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            f"{label} must be nonempty text")
    return value.strip()


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    actual = set(value)
    if actual != fields:
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            f"{label} fields differ: missing={sorted(fields - actual)}, "
            f"unexpected={sorted(actual - fields)}")


def _reviewed_at(value: object) -> str:
    text = _text(value, "review.reviewed_at")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            "review.reviewed_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            "review.reviewed_at must include a UTC offset")
    return text


def binding_template(robot_localization_sha256: str = "") -> dict[str, Any]:
    """Return a blank local review contract for the two attachment states."""
    if robot_localization_sha256:
        _sha(robot_localization_sha256, "robot_localization_sha256")
    return {
        "schema": BINDING_SCHEMA,
        "status": "DRAFT_UNREVIEWED",
        "robot_localization_sha256": robot_localization_sha256,
        "profiles": [
            {
                "profile": profile,
                "attachment_state": ATTACHMENT_STATES[profile],
                "installed_collision_profile_id": "",
                "installed_collision_profile_file_sha256": "",
                "measured_tcp_sha256": None,
            }
            for profile in SUPPORTED_PROFILES
        ],
        "review": {
            "reviewed": False,
            "reviewer": "",
            "reviewed_at": "",
            "notes": "",
        },
    }


def _validate_localization(value: Mapping[str, Any]) -> str:
    _exact(value, {
        "schema", "status", "measurement_sha256", "keyboard_package_sha256",
        "target_profile_sha256", "transform", "fit_residuals_mm",
        "holdout_residuals_mm", "board_to_robot_transform_verified",
        "profiles", "profile_separation_preserved", "motion_targets_emitted",
        "physical_clearance_verified", "motion_authorized",
        "contact_authorized", "limitations",
    }, "robot localization")
    if (value.get("schema") != LOCALIZATION_SCHEMA
            or value.get("status") != "ROBOT_FRAME_LOCALIZATION_CANDIDATES_READY"
            or value.get("board_to_robot_transform_verified") is not True
            or value.get("profile_separation_preserved") is not True
            or value.get("motion_targets_emitted") is not False
            or value.get("physical_clearance_verified") is not False
            or value.get("motion_authorized") is not False
            or value.get("contact_authorized") is not False):
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            "robot localization is not a ready zero-authority input")
    profiles = value.get("profiles")
    if not isinstance(profiles, Mapping) or set(profiles) != set(SUPPORTED_PROFILES):
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            "robot localization must contain exactly both attachment profiles")
    for profile in SUPPORTED_PROFILES:
        row = profiles[profile]
        if isinstance(row, Mapping):
            _exact(row, {
                "profile", "board_to_robot_transform_verified",
                "robot_frame_localization_candidates_emitted",
                "robot_frame_localization_candidates", "motion_targets_emitted",
                "physical_clearance_verified", "motion_authorized",
                "contact_authorized", "blockers",
            }, f"localization profile {profile}")
        if (not isinstance(row, Mapping) or row.get("profile") != profile
                or row.get("board_to_robot_transform_verified") is not True
                or row.get("robot_frame_localization_candidates_emitted") is not True
                or row.get("motion_targets_emitted") is not False
                or row.get("physical_clearance_verified") is not False
                or row.get("motion_authorized") is not False
                or row.get("contact_authorized") is not False):
            raise FixedCameraKeyboardClearanceIntakeV1Error(
                f"localization profile is invalid: {profile}")
        candidates = row.get("robot_frame_localization_candidates")
        if not isinstance(candidates, list) or len(candidates) != 46:
            raise FixedCameraKeyboardClearanceIntakeV1Error(
                f"localization candidate coverage is incomplete: {profile}")
        ids: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                raise FixedCameraKeyboardClearanceIntakeV1Error(
                    "localization candidate must be an object")
            _exact(candidate, {"key_id", "robot_xyz_mm"}, "localization candidate")
            key_id = _text(candidate.get("key_id"), "candidate key_id")
            xyz = candidate.get("robot_xyz_mm")
            if (key_id in ids or not isinstance(xyz, list) or len(xyz) != 3
                    or any(isinstance(item, bool) or not isinstance(item, (int, float))
                           or not math.isfinite(float(item)) for item in xyz)):
                raise FixedCameraKeyboardClearanceIntakeV1Error(
                    f"localization candidate is invalid: {profile}/{key_id}")
            ids.add(key_id)
    return _digest(value)


def _profile_matches_context(
    profile: InstalledCollisionGeometryProfile,
    context: SimulationContext,
    attachment_profile: CollisionAttachmentProfile,
) -> bool:
    readiness = assess_current_collision_readiness(
        context,
        attachment_profile=attachment_profile,
    )
    return (
        profile.manifest_id == context.snapshot.manifest_id
        and profile.manifest_sha256 == context.snapshot.manifest_sha256
        and profile.active_build_id == context.snapshot.active_build_id
        and profile.build_snapshot_sha256 == context.snapshot.snapshot_hash
        and profile.robot_model_sha256 == context.scenario.model_sha256
        and profile.base_contract_sha256 == readiness.contract.content_hash
    )


def _validate_bindings(
    value: Mapping[str, Any], localization_sha256: str,
) -> dict[str, Mapping[str, Any]]:
    _exact(value, {
        "schema", "status", "robot_localization_sha256", "profiles", "review",
    }, "clearance bindings")
    if (value.get("schema") != BINDING_SCHEMA
            or value.get("status") != REVIEWED_STATUS
            or _sha(value.get("robot_localization_sha256"),
                    "robot_localization_sha256") != localization_sha256):
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            "clearance bindings are unreviewed or bind different localization")
    review = value.get("review")
    if isinstance(review, Mapping):
        _exact(review, {"reviewed", "reviewer", "reviewed_at", "notes"},
               "binding review")
    if (not isinstance(review, Mapping) or review.get("reviewed") is not True
            or not isinstance(review.get("reviewer"), str)
            or not review["reviewer"].strip()):
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            "binding review metadata is incomplete")
    _reviewed_at(review.get("reviewed_at"))
    rows = value.get("profiles")
    if not isinstance(rows, list) or len(rows) != 2:
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            "bindings must contain exactly two profiles")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise FixedCameraKeyboardClearanceIntakeV1Error(
                "profile binding must be an object")
        _exact(row, {
            "profile", "attachment_state", "installed_collision_profile_id",
            "installed_collision_profile_file_sha256", "measured_tcp_sha256",
        }, "profile binding")
        profile = row.get("profile")
        if profile not in SUPPORTED_PROFILES or profile in result:
            raise FixedCameraKeyboardClearanceIntakeV1Error(
                "profile bindings must be unique and supported")
        if row.get("attachment_state") != ATTACHMENT_STATES[profile]:
            raise FixedCameraKeyboardClearanceIntakeV1Error(
                f"attachment state differs for {profile}")
        _text(row.get("installed_collision_profile_id"), "installed profile id")
        _sha(row.get("installed_collision_profile_file_sha256"),
             "installed profile file hash")
        tcp = row.get("measured_tcp_sha256")
        if profile == "no_attachment" and tcp is not None:
            raise FixedCameraKeyboardClearanceIntakeV1Error(
                "bare-jaw profile cannot bind a stylus TCP")
        if profile == "stylus_attachment":
            _sha(tcp, "stylus measured TCP hash")
        result[profile] = row
    if set(result) != set(SUPPORTED_PROFILES):
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            "both attachment profiles are required")
    if (result["no_attachment"]["installed_collision_profile_id"]
            == result["stylus_attachment"]["installed_collision_profile_id"]
            or result["no_attachment"]["installed_collision_profile_file_sha256"]
            == result["stylus_attachment"]["installed_collision_profile_file_sha256"]):
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            "bare-jaw and stylus installed profiles must be distinct")
    return result


def compile_clearance_intake(
    robot_localization: Mapping[str, Any],
    profile_bindings: Mapping[str, Any],
    installed_profiles: Mapping[str, InstalledCollisionGeometryProfile],
    *,
    context: SimulationContext,
) -> dict[str, Any]:
    """Prepare exact profile-specific inputs for route construction."""
    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    revalidate_simulation_context(context)
    localization_sha = _validate_localization(robot_localization)
    bindings = _validate_bindings(profile_bindings, localization_sha)
    if set(installed_profiles) != set(SUPPORTED_PROFILES):
        raise FixedCameraKeyboardClearanceIntakeV1Error(
            "installed_profiles must contain exactly both attachment profiles")

    output_profiles: dict[str, Any] = {}
    installed_ids: set[str] = set()
    installed_hashes: set[str] = set()
    for profile_name in SUPPORTED_PROFILES:
        installed = installed_profiles[profile_name]
        if not isinstance(installed, InstalledCollisionGeometryProfile):
            raise TypeError(
                f"installed profile must be typed: {profile_name}")
        binding = bindings[profile_name]
        if (installed.profile_id != binding["installed_collision_profile_id"]
                or installed.file_sha256
                != binding["installed_collision_profile_file_sha256"]):
            raise FixedCameraKeyboardClearanceIntakeV1Error(
                f"installed profile differs from reviewed binding: {profile_name}")
        attachment_profile = CollisionAttachmentProfile(profile_name)
        if not _profile_matches_context(installed, context, attachment_profile):
            raise FixedCameraKeyboardClearanceIntakeV1Error(
                f"installed profile differs from active context: {profile_name}")
        if (installed.profile_id in installed_ids
                or installed.file_sha256 in installed_hashes):
            raise FixedCameraKeyboardClearanceIntakeV1Error(
                "installed attachment profiles are not distinct")
        installed_ids.add(installed.profile_id)
        installed_hashes.add(installed.file_sha256)
        candidates = robot_localization["profiles"][profile_name][
            "robot_frame_localization_candidates"]
        output_profiles[profile_name] = {
            "profile": profile_name,
            "attachment_state": ATTACHMENT_STATES[profile_name],
            "robot_frame_localization_candidates_sha256": _digest(candidates),
            "candidate_count": 46,
            "installed_collision_profile_id": installed.profile_id,
            "installed_collision_profile_content_sha256": installed.content_sha256,
            "installed_collision_profile_file_sha256": installed.file_sha256,
            "collision_contract_sha256": installed.contract.content_hash,
            "clearance_policy_sha256": hashlib.sha256(
                _canonical(installed.clearance_policy.to_dict())).hexdigest(),
            "measured_tcp_sha256": binding["measured_tcp_sha256"],
            "route_construction_ready": True,
            "collision_screening_executed": False,
            "continuous_clearance_verified": False,
            "next_required_stage": (
                "BUILD_PROFILE_SPECIFIC_TYPING_EXECUTION_PLAN_THEN_USE_"
                "TYPING_COLLISION_INTAKE_V1"),
            "blockers": [
                "PROFILE_SPECIFIC_TRAJECTORY_REQUIRED",
                "CONTINUOUS_COLLISION_SCREENING_REQUIRED",
                "FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION",
            ],
        }

    core = {
        "schema": SCHEMA,
        "status": READY_STATUS,
        "robot_localization_sha256": localization_sha,
        "profile_bindings_sha256": _digest(profile_bindings),
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "kinematic_model_sha256": context.scenario.model_sha256,
        "profiles": output_profiles,
        "profile_separation_preserved": True,
        "trajectory_generated": False,
        "collision_screening_executed": False,
        "continuous_clearance_verified": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "physical_authority": False,
    }
    return {**core, "clearance_intake_sha256": _digest(core)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a local attachment-profile binding draft")
    parser.add_argument("--write-template", type=Path, required=True)
    parser.add_argument("--robot-localization", type=Path)
    args = parser.parse_args(argv)
    localization_sha = ""
    if args.robot_localization is not None:
        try:
            document = json.loads(args.robot_localization.read_bytes())
        except (OSError, json.JSONDecodeError) as exc:
            raise FixedCameraKeyboardClearanceIntakeV1Error(
                "robot localization could not be read as JSON") from exc
        if not isinstance(document, Mapping):
            raise FixedCameraKeyboardClearanceIntakeV1Error(
                "robot localization must be an object")
        localization_sha = _validate_localization(document)
    args.write_template.write_text(
        json.dumps(binding_template(localization_sha), indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


__all__ = [
    "BINDING_SCHEMA", "READY_STATUS", "REVIEWED_STATUS", "SCHEMA",
    "FixedCameraKeyboardClearanceIntakeV1Error", "binding_template",
    "compile_clearance_intake", "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
