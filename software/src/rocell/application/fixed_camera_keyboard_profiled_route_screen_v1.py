"""Offline profile-separated trajectory, IK, and collision-intake publication.

This boundary consumes the exact two-plan bundle admitted by
``fixed_camera_keyboard_profiled_typing_plan_v1``.  It replays each attachment
profile through the existing deterministic trajectory compiler, IK screen, and
installed-geometry collision intake without adding a controller or transport
dependency.

Successful publication means both profiles reached the offline collision
evidence boundary.  It does not prove continuous clearance, observe a fresh
start state, create controller commands, or grant physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from rocell.calibration import PlannerCalibrationSnapshot
from rocell.simulation.collision import CollisionAttachmentProfile

from .bounded_segment_collision_qualification import BoundedSegmentSamplingPolicy
from .context import SimulationContext
from .fixed_camera_keyboard_clearance_intake_v1 import SUPPORTED_PROFILES
from .fixed_camera_keyboard_profiled_typing_plan_v1 import (
    ADMITTED_STATUS as PLAN_ADMITTED_STATUS,
    MANIFEST_NAME as PLAN_MANIFEST_NAME,
    PLAN_NAMES,
    RECEIPT_NAME as PLAN_RECEIPT_NAME,
    ZERO_AUTHORITY as PLAN_ZERO_AUTHORITY,
)
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .typing_collision_intake_v1 import (
    READY_STATUS as COLLISION_READY_STATUS,
    prepare_typing_collision_intake_v1,
)
from .typing_execution_plan_v1 import TypingExecutionPlanV1
from .typing_trajectory_ik_screen_v1 import (
    READY_STATUS as IK_READY_STATUS,
    TypingTrajectoryIkSeedV1,
    screen_typing_trajectory_ik_v1,
)
from .typing_trajectory_plan_v1 import (
    TypingTrajectoryPolicyV1,
    compile_typing_trajectory_plan_v1,
)
from .trajectory_simulation import TrajectorySimulationPolicy


SCHEMA = "rocell.fixed_camera_keyboard_profiled_route_screen_manifest.v1"
STATUS = "READY_FOR_PROFILE_BOUND_COLLISION_EVIDENCE"
RECEIPT_SCHEMA = (
    "rocell.fixed_camera_keyboard_profiled_route_screen_admission_receipt.v1"
)
RECEIPT_STATUS = "PROFILED_ROUTE_SCREEN_BUNDLE_ADMITTED"
MANIFEST_NAME = "profiled-route-screen-manifest.json"
RECEIPT_NAME = "profiled-route-screen-admission-receipt.json"
TRAJECTORY_NAMES = {
    "no_attachment": "no-attachment-typing-trajectory-plan.json",
    "stylus_attachment": "stylus-attachment-typing-trajectory-plan.json",
}
IK_NAMES = {
    "no_attachment": "no-attachment-typing-ik-screen.json",
    "stylus_attachment": "stylus-attachment-typing-ik-screen.json",
}
COLLISION_NAMES = {
    "no_attachment": "no-attachment-typing-collision-intake.json",
    "stylus_attachment": "stylus-attachment-typing-collision-intake.json",
}
MAX_JSON_BYTES = 8 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
ZERO_AUTHORITY: Mapping[str, object] = {
    "trajectory_compiled_offline": True,
    "ik_screening_executed_offline": True,
    "collision_intake_prepared_offline": True,
    "installed_geometry_collision_screening_executed": False,
    "continuous_collision_proven": False,
    "fresh_observed_start_state_present": False,
    "controller_commands": [],
    "hardware_commands_generated": 0,
    "hardware_access": False,
    "physical_authority": False,
    "physical_release_effect": "NONE",
}


class FixedCameraKeyboardProfiledRouteScreenV1Error(ValueError):
    """The admitted plan bundle cannot reach both offline profile boundaries."""


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
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _reject_constant(value: str) -> None:
    raise FixedCameraKeyboardProfiledRouteScreenV1Error(
        f"profiled route input contains nonfinite constant {value!r}"
    )


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FixedCameraKeyboardProfiledRouteScreenV1Error(
                f"profiled route input contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _read_pinned(
    path: str | Path, *, expected_sha256: str, label: str
) -> tuple[Path, bytes]:
    source = Path(path).expanduser()
    expected = _digest(expected_sha256, f"expected_{label}_file_sha256")
    if source.is_symlink():
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            f"{label} path must not be a symlink"
        )
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            f"cannot inspect {label} file: {exc}"
        ) from exc
    if not source.is_file() or size <= 0 or size > MAX_JSON_BYTES:
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            f"{label} file size is invalid"
        )
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            f"cannot read {label} file: {exc}"
        ) from exc
    if len(payload) != size or _sha_bytes(payload) != expected:
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            f"{label} bytes differ from expected file SHA-256"
        )
    return source.resolve(), payload


def _read_json(
    path: str | Path, *, expected_sha256: str, label: str
) -> tuple[Path, bytes, Mapping[str, Any]]:
    source, payload = _read_pinned(
        path, expected_sha256=expected_sha256, label=label
    )
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            f"{label} must be a JSON object"
        )
    return source, payload, value


def _require_profile_map(value: Mapping[str, Any], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != set(SUPPORTED_PROFILES):
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            f"{label} must contain the exact supported profile set"
        )


def _validate_source_bundle(
    receipt_path: Path,
    receipt: Mapping[str, Any],
    manifest_path: Path,
    manifest_bytes: bytes,
    manifest: Mapping[str, Any],
    plan_sources: Mapping[str, tuple[Path, bytes]],
    plans: Mapping[str, TypingExecutionPlanV1],
) -> None:
    if (
        receipt_path.name != PLAN_RECEIPT_NAME
        or manifest_path.name != PLAN_MANIFEST_NAME
        or receipt_path.parent != manifest_path.parent
        or any(path.parent != receipt_path.parent for path, _ in plan_sources.values())
    ):
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            "plan receipt, manifest, and plans must be the named co-located bundle"
        )
    if (
        receipt.get("schema")
        != "rocell.fixed_camera_keyboard_profiled_typing_plan_admission_receipt.v1"
        or receipt.get("status") != PLAN_ADMITTED_STATUS
        or receipt.get("profile_separation_preserved") is not True
        or receipt.get("authority") != PLAN_ZERO_AUTHORITY
    ):
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            "profiled plan admission receipt is invalid or authority-bearing"
        )
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            "profiled plan receipt has no artifact bindings"
        )
    bound_manifest = artifacts.get("profiled_typing_plan_manifest")
    if (
        not isinstance(bound_manifest, Mapping)
        or bound_manifest.get("name") != PLAN_MANIFEST_NAME
        or bound_manifest.get("size_bytes") != len(manifest_bytes)
        or bound_manifest.get("file_sha256") != _sha_bytes(manifest_bytes)
        or bound_manifest.get("meaning_sha256") != _sha(manifest)
    ):
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            "profiled plan manifest differs from its admission receipt"
        )
    claimed = manifest.get("profiled_typing_plan_manifest_sha256")
    unsigned = dict(manifest)
    unsigned.pop("profiled_typing_plan_manifest_sha256", None)
    profiles = manifest.get("profiles")
    if (
        manifest.get("schema")
        != "rocell.fixed_camera_keyboard_profiled_typing_plan_manifest.v1"
        or manifest.get("status") != "READY_FOR_PROFILE_SPECIFIC_TRAJECTORY_AND_IK"
        or claimed != _sha(unsigned)
        or manifest.get("profile_separation_preserved") is not True
        or manifest.get("controller_commands") != []
        or manifest.get("hardware_commands_generated") != 0
        or manifest.get("hardware_access") is not False
        or manifest.get("physical_authority") is not False
        or not isinstance(profiles, Mapping)
        or set(profiles) != set(SUPPORTED_PROFILES)
    ):
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            "profiled plan manifest is invalid or authority-bearing"
        )
    for name in SUPPORTED_PROFILES:
        path, payload = plan_sources[name]
        plan = plans[name]
        row = profiles[name]
        bound = artifacts.get(f"{name}_typing_execution_plan")
        if (
            path.name != PLAN_NAMES[name]
            or not isinstance(bound, Mapping)
            or bound.get("name") != path.name
            or bound.get("size_bytes") != len(payload)
            or bound.get("file_sha256") != _sha_bytes(payload)
            or bound.get("plan_sha256") != plan.plan_sha256
            or not isinstance(row, Mapping)
            or row.get("profile") != name
            or row.get("typing_execution_plan_name") != path.name
            or row.get("typing_execution_plan_file_sha256") != _sha_bytes(payload)
            or row.get("typing_execution_plan_sha256") != plan.plan_sha256
            or row.get("typing_execution_config_sha256")
            != plan.config.config_sha256
            or row.get("tool_profile_sha256") != plan.config.tool_profile_sha256
            or row.get("action_count") != len(plan.actions)
            or row.get("ordered_target_ids")
            != [action.target_id for action in plan.actions]
        ):
            raise FixedCameraKeyboardProfiledRouteScreenV1Error(
                f"profiled plan bundle binding differs: {name}"
            )


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            f"cannot publish new profiled route file {path.name}: {exc}"
        ) from exc


@dataclass(frozen=True, slots=True)
class FixedCameraKeyboardProfiledRouteScreenResultV1:
    output_directory: Path
    trajectory_paths: Mapping[str, Path]
    ik_paths: Mapping[str, Path]
    collision_paths: Mapping[str, Path]
    manifest_path: Path
    receipt_path: Path
    manifest: Mapping[str, Any]
    receipt: Mapping[str, Any]


def screen_fixed_camera_keyboard_profiled_routes_v1(
    typing_plan_admission_receipt_path: str | Path,
    *,
    expected_typing_plan_admission_receipt_file_sha256: str,
    typing_plan_manifest_path: str | Path,
    expected_typing_plan_manifest_file_sha256: str,
    plan_paths: Mapping[str, str | Path],
    expected_plan_file_sha256: Mapping[str, str],
    context: SimulationContext,
    calibration_snapshot: PlannerCalibrationSnapshot,
    trajectory_policies: Mapping[str, TypingTrajectoryPolicyV1],
    ik_seeds: Mapping[str, TypingTrajectoryIkSeedV1],
    installed_collision_profiles: Mapping[str, InstalledCollisionGeometryProfile],
    output_directory: str | Path,
    ik_policies: Mapping[str, TrajectorySimulationPolicy | None] | None = None,
    collision_sampling_policies: Mapping[
        str, BoundedSegmentSamplingPolicy | None
    ] | None = None,
) -> FixedCameraKeyboardProfiledRouteScreenResultV1:
    """Run both admitted attachment profiles to the collision-intake boundary."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(calibration_snapshot, PlannerCalibrationSnapshot):
        raise TypeError("calibration_snapshot must be a PlannerCalibrationSnapshot")
    for value, label in (
        (plan_paths, "plan_paths"),
        (expected_plan_file_sha256, "expected_plan_file_sha256"),
        (trajectory_policies, "trajectory_policies"),
        (ik_seeds, "ik_seeds"),
        (installed_collision_profiles, "installed_collision_profiles"),
    ):
        _require_profile_map(value, label)
    if ik_policies is not None:
        _require_profile_map(ik_policies, "ik_policies")
    if collision_sampling_policies is not None:
        _require_profile_map(
            collision_sampling_policies, "collision_sampling_policies"
        )

    receipt_source, receipt_bytes, receipt = _read_json(
        typing_plan_admission_receipt_path,
        expected_sha256=expected_typing_plan_admission_receipt_file_sha256,
        label="typing plan admission receipt",
    )
    manifest_source, manifest_bytes, source_manifest = _read_json(
        typing_plan_manifest_path,
        expected_sha256=expected_typing_plan_manifest_file_sha256,
        label="typing plan manifest",
    )
    plans: dict[str, TypingExecutionPlanV1] = {}
    plan_sources: dict[str, tuple[Path, bytes]] = {}
    for name in SUPPORTED_PROFILES:
        path, payload = _read_pinned(
            plan_paths[name],
            expected_sha256=expected_plan_file_sha256[name],
            label=f"{name} typing execution plan",
        )
        try:
            plans[name] = TypingExecutionPlanV1.from_bytes(payload)
        except (TypeError, ValueError) as exc:
            raise FixedCameraKeyboardProfiledRouteScreenV1Error(str(exc)) from exc
        plan_sources[name] = (path, payload)
    _validate_source_bundle(
        receipt_source,
        receipt,
        manifest_source,
        manifest_bytes,
        source_manifest,
        plan_sources,
        plans,
    )

    if any(
        plan.config.calibration_snapshot_sha256
        != calibration_snapshot.snapshot_sha256
        for plan in plans.values()
    ):
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            "typing plans differ from the supplied calibration snapshot"
        )
    if (
        calibration_snapshot.manifest_id != context.snapshot.manifest_id
        or calibration_snapshot.active_build_id != context.snapshot.active_build_id
    ):
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            "calibration snapshot differs from the active context"
        )
    if any(
        not isinstance(trajectory_policies[name], TypingTrajectoryPolicyV1)
        or not isinstance(ik_seeds[name], TypingTrajectoryIkSeedV1)
        or not isinstance(
            installed_collision_profiles[name], InstalledCollisionGeometryProfile
        )
        for name in SUPPORTED_PROFILES
    ):
        raise TypeError("profile inputs have an unsupported type")
    if len({trajectory_policies[name].policy_sha256 for name in SUPPORTED_PROFILES}) != 2:
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            "attachment profiles require distinct trajectory policies"
        )
    if len({ik_seeds[name].seed_sha256 for name in SUPPORTED_PROFILES}) != 2:
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            "attachment profiles require separately identified IK seeds"
        )
    if len(
        {
            installed_collision_profiles[name].content_sha256
            for name in SUPPORTED_PROFILES
        }
    ) != 2:
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            "attachment profiles require distinct installed collision profiles"
        )

    trajectories = {}
    ik_reports: dict[str, Mapping[str, Any]] = {}
    collision_reports: dict[str, Mapping[str, Any]] = {}
    output_payloads: dict[str, dict[str, bytes]] = {
        "trajectory": {},
        "ik": {},
        "collision": {},
    }
    profile_rows: dict[str, Any] = {}
    source_profiles = source_manifest["profiles"]
    for name in SUPPORTED_PROFILES:
        profile = installed_collision_profiles[name]
        source_row = source_profiles[name]
        if (
            source_row.get("installed_collision_profile_id") != profile.profile_id
            or source_row.get("installed_collision_profile_content_sha256")
            != profile.content_sha256
            or source_row.get("collision_contract_sha256")
            != profile.contract.content_hash
        ):
            raise FixedCameraKeyboardProfiledRouteScreenV1Error(
                f"installed collision profile differs from admitted binding: {name}"
            )
        trajectories[name] = compile_typing_trajectory_plan_v1(
            plans[name], policy=trajectory_policies[name]
        )
        ik_reports[name] = screen_typing_trajectory_ik_v1(
            plans[name],
            trajectories[name],
            context,
            calibration_snapshot,
            ik_seeds[name],
            policy=None if ik_policies is None else ik_policies[name],
        )
        if ik_reports[name].get("status") != IK_READY_STATUS:
            raise FixedCameraKeyboardProfiledRouteScreenV1Error(
                f"profile did not pass deterministic IK screening: {name}"
            )
        collision_reports[name] = prepare_typing_collision_intake_v1(
            plans[name],
            trajectories[name],
            ik_reports[name],
            context,
            calibration_snapshot,
            profile,
            attachment_profile=CollisionAttachmentProfile(name),
            sampling_policy=(
                None
                if collision_sampling_policies is None
                else collision_sampling_policies[name]
            ),
        )
        if collision_reports[name].get("status") != COLLISION_READY_STATUS:
            raise FixedCameraKeyboardProfiledRouteScreenV1Error(
                f"profile did not reach installed-geometry collision intake: {name}"
            )
        trajectory_payload = trajectories[name].to_bytes()
        ik_payload = _canonical(ik_reports[name], newline=True)
        collision_payload = _canonical(collision_reports[name], newline=True)
        output_payloads["trajectory"][name] = trajectory_payload
        output_payloads["ik"][name] = ik_payload
        output_payloads["collision"][name] = collision_payload
        profile_rows[name] = {
            "profile": name,
            "attachment_state": source_row["attachment_state"],
            "typing_execution_plan_sha256": plans[name].plan_sha256,
            "typing_trajectory_policy_sha256": trajectory_policies[
                name
            ].policy_sha256,
            "typing_trajectory_plan_sha256": trajectories[
                name
            ].trajectory_plan_sha256,
            "typing_trajectory_plan_file_sha256": _sha_bytes(trajectory_payload),
            "typing_trajectory_ik_seed_sha256": ik_seeds[name].seed_sha256,
            "typing_trajectory_ik_screen_sha256": ik_reports[name][
                "typing_trajectory_ik_screen_sha256"
            ],
            "typing_trajectory_ik_screen_file_sha256": _sha_bytes(ik_payload),
            "installed_collision_profile_id": profile.profile_id,
            "installed_collision_profile_content_sha256": profile.content_sha256,
            "collision_contract_sha256": profile.contract.content_hash,
            "typing_collision_intake_sha256": collision_reports[name][
                "typing_collision_intake_sha256"
            ],
            "typing_collision_intake_file_sha256": _sha_bytes(collision_payload),
            "bounded_sample_count": collision_reports[name]["bounded_sample_count"],
            "required_evidence_slots": collision_reports[name][
                "required_evidence_slots"
            ],
            "blockers": collision_reports[name]["blockers"],
            "next_required_stage": collision_reports[name]["next_required_stage"],
        }

    manifest_core: Mapping[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "source_profiled_typing_plan_manifest_sha256": source_manifest[
            "profiled_typing_plan_manifest_sha256"
        ],
        "calibration_snapshot_sha256": calibration_snapshot.snapshot_sha256,
        "build_snapshot_sha256": context.snapshot.snapshot_hash,
        "kinematic_model_sha256": context.scenario.model_sha256,
        "profiles": profile_rows,
        "profile_separation_preserved": True,
        "next_required_stage": "SUPPLY_PROFILE_BOUND_COLLISION_EVIDENCE",
        "authority": dict(ZERO_AUTHORITY),
    }
    manifest = {**manifest_core, "profiled_route_screen_manifest_sha256": _sha(manifest_core)}
    result_manifest_bytes = _canonical(manifest, newline=True)

    source_rows = {
        "typing_plan_admission_receipt": (receipt_source, receipt_bytes),
        "typing_plan_manifest": (manifest_source, manifest_bytes),
        **{
            f"{name}_typing_execution_plan": plan_sources[name]
            for name in SUPPORTED_PROFILES
        },
    }
    artifact_rows: dict[str, Any] = {}
    for kind, names in (
        ("trajectory", TRAJECTORY_NAMES),
        ("ik", IK_NAMES),
        ("collision", COLLISION_NAMES),
    ):
        for name in SUPPORTED_PROFILES:
            payload = output_payloads[kind][name]
            artifact_rows[f"{name}_{kind}"] = {
                "name": names[name],
                "size_bytes": len(payload),
                "file_sha256": _sha_bytes(payload),
            }
    receipt_out: Mapping[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "status": RECEIPT_STATUS,
        "sources": {
            name: {
                "name": source.name,
                "size_bytes": len(payload),
                "file_sha256": _sha_bytes(payload),
            }
            for name, (source, payload) in source_rows.items()
        },
        "artifacts": {
            **artifact_rows,
            "profiled_route_screen_manifest": {
                "name": MANIFEST_NAME,
                "size_bytes": len(result_manifest_bytes),
                "file_sha256": _sha_bytes(result_manifest_bytes),
                "meaning_sha256": _sha(manifest),
            },
            "completion_receipt": {"name": RECEIPT_NAME, "written_last": True},
        },
        "profile_separation_preserved": True,
        "next_required_stage": "SUPPLY_PROFILE_BOUND_COLLISION_EVIDENCE",
        "authority": dict(ZERO_AUTHORITY),
    }
    receipt_out_bytes = _canonical(receipt_out, newline=True)

    requested = Path(output_directory).expanduser()
    if not requested.name or requested.name in (".", ".."):
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            "output_directory must name a new directory"
        )
    parent = requested.parent.resolve()
    if not parent.is_dir():
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            "output_directory parent must already exist"
        )
    destination = parent / requested.name
    if destination.exists() or destination.is_symlink():
        raise FixedCameraKeyboardProfiledRouteScreenV1Error(
            "output_directory already exists; refusing to overwrite"
        )
    try:
        destination.mkdir(mode=0o700, exist_ok=False)
        trajectory_paths = {
            name: destination / TRAJECTORY_NAMES[name] for name in SUPPORTED_PROFILES
        }
        ik_paths = {name: destination / IK_NAMES[name] for name in SUPPORTED_PROFILES}
        collision_paths = {
            name: destination / COLLISION_NAMES[name] for name in SUPPORTED_PROFILES
        }
        for name in SUPPORTED_PROFILES:
            _write_new(trajectory_paths[name], output_payloads["trajectory"][name])
            _write_new(ik_paths[name], output_payloads["ik"][name])
            _write_new(collision_paths[name], output_payloads["collision"][name])
        result_manifest_path = destination / MANIFEST_NAME
        result_receipt_path = destination / RECEIPT_NAME
        _write_new(result_manifest_path, result_manifest_bytes)
        _write_new(result_receipt_path, receipt_out_bytes)
    except Exception:
        if destination.exists():
            for child in destination.iterdir():
                child.unlink(missing_ok=True)
            destination.rmdir()
        raise
    return FixedCameraKeyboardProfiledRouteScreenResultV1(
        destination,
        trajectory_paths,
        ik_paths,
        collision_paths,
        result_manifest_path,
        result_receipt_path,
        manifest,
        receipt_out,
    )


__all__ = [
    "COLLISION_NAMES",
    "IK_NAMES",
    "MANIFEST_NAME",
    "RECEIPT_NAME",
    "RECEIPT_STATUS",
    "STATUS",
    "TRAJECTORY_NAMES",
    "ZERO_AUTHORITY",
    "FixedCameraKeyboardProfiledRouteScreenResultV1",
    "FixedCameraKeyboardProfiledRouteScreenV1Error",
    "screen_fixed_camera_keyboard_profiled_routes_v1",
]
