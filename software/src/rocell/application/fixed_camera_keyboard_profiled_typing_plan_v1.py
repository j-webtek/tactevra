"""Publish attachment-separated typing plans from admitted camera clearance.

This offline boundary binds one admitted keyboard batch to both reviewed
attachment profiles.  It compiles the existing deterministic typing plan once
per profile and publishes an explicit manifest that prevents a bare-jaw plan,
stylus plan, collision profile, or localization candidate set from being
crossed later.  It never opens hardware, solves IK, constructs a trajectory,
screens collision, or grants physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from rocell.models import ModelMotionBatchV2Error, decode_model_motion_batch_v2_json

from .fixed_camera_keyboard_clearance_admission_v1 import (
    ADMITTED_STATUS as CLEARANCE_ADMITTED_STATUS,
    INTAKE_NAME as CLEARANCE_INTAKE_NAME,
    RECEIPT_NAME as CLEARANCE_RECEIPT_NAME,
    ZERO_AUTHORITY as CLEARANCE_ZERO_AUTHORITY,
)
from .fixed_camera_keyboard_clearance_intake_v1 import (
    READY_STATUS as CLEARANCE_READY_STATUS,
    SCHEMA as CLEARANCE_SCHEMA,
    SUPPORTED_PROFILES,
)
from .typing_execution_plan_v1 import (
    TypingExecutionConfigV1,
    TypingExecutionPlanV1Error,
    compile_typing_execution_plan_v1,
)


MAX_JSON_BYTES = 4 * 1024 * 1024
PLAN_NAMES = {
    "no_attachment": "no-attachment-typing-execution-plan.json",
    "stylus_attachment": "stylus-attachment-typing-execution-plan.json",
}
MANIFEST_NAME = "profiled-typing-plan-manifest.json"
RECEIPT_NAME = "profiled-typing-plan-admission-receipt.json"
ADMITTED_STATUS = "PROFILE_SPECIFIC_TYPING_PLANS_ADMITTED"
ZERO_AUTHORITY: Mapping[str, object] = {
    "camera_opened": False,
    "robot_provider_called": False,
    "controller_commands": [],
    "trajectory_generated": False,
    "ik_screening_executed": False,
    "collision_screening_executed": False,
    "continuous_clearance_verified": False,
    "motion_authorized": False,
    "contact_authorized": False,
    "physical_release_effect": "NONE",
}


class FixedCameraKeyboardProfiledTypingPlanV1Error(ValueError):
    """Profiled typing inputs cannot be admitted or published."""


def _canonical(value: object, *, newline: bool = False) -> bytes:
    try:
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "profiled typing value is not canonical JSON"
        ) from exc
    return payload + (b"\n" if newline else b"")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest(value: object) -> str:
    return _sha256(_canonical(value))


def _expected_digest(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _reject_constant(value: str) -> None:
    raise FixedCameraKeyboardProfiledTypingPlanV1Error(
        f"profiled typing input contains nonfinite constant {value!r}"
    )


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FixedCameraKeyboardProfiledTypingPlanV1Error(
                f"profiled typing input contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _read_pinned(
    path: str | Path, *, expected_sha256: str, label: str,
) -> tuple[Path, bytes]:
    source = Path(path).expanduser()
    expected = _expected_digest(expected_sha256, f"expected_{label}_file_sha256")
    if source.is_symlink():
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            f"{label} path must not be a symlink"
        )
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            f"cannot inspect {label} file: {exc}"
        ) from exc
    if not source.is_file() or size <= 0 or size > MAX_JSON_BYTES:
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            f"{label} file size is invalid"
        )
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            f"cannot read {label} file: {exc}"
        ) from exc
    if len(payload) != size or _sha256(payload) != expected:
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            f"{label} bytes differ from expected file SHA-256"
        )
    return source.resolve(), payload


def _read_json(
    path: str | Path, *, expected_sha256: str, label: str,
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
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            f"{label} must be a JSON object"
        )
    return source, payload, value


def _validate_clearance(
    receipt_path: Path,
    receipt: Mapping[str, Any],
    intake_path: Path,
    intake_bytes: bytes,
    intake: Mapping[str, Any],
) -> None:
    if (
        receipt_path.name != CLEARANCE_RECEIPT_NAME
        or intake_path.name != CLEARANCE_INTAKE_NAME
        or receipt_path.parent != intake_path.parent
    ):
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "clearance receipt and intake must be the named co-located pair"
        )
    if (
        receipt.get("schema")
        != "rocell.fixed_camera_keyboard_clearance_admission_receipt.v1"
        or receipt.get("status") != CLEARANCE_ADMITTED_STATUS
        or receipt.get("profile_separation_preserved") is not True
        or receipt.get("authority") != CLEARANCE_ZERO_AUTHORITY
    ):
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "clearance admission receipt is invalid or authority-bearing"
        )
    artifacts = receipt.get("artifacts")
    bound = artifacts.get("clearance_intake") if isinstance(artifacts, Mapping) else None
    if (
        not isinstance(bound, Mapping)
        or bound.get("name") != CLEARANCE_INTAKE_NAME
        or bound.get("size_bytes") != len(intake_bytes)
        or bound.get("file_sha256") != _sha256(intake_bytes)
        or bound.get("meaning_sha256") != _digest(intake)
    ):
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "clearance intake differs from its admission receipt"
        )
    unsigned = dict(intake)
    claimed = unsigned.pop("clearance_intake_sha256", None)
    if (
        intake.get("schema") != CLEARANCE_SCHEMA
        or intake.get("status") != CLEARANCE_READY_STATUS
        or claimed != _digest(unsigned)
        or intake.get("profile_separation_preserved") is not True
        or intake.get("trajectory_generated") is not False
        or intake.get("collision_screening_executed") is not False
        or intake.get("hardware_access") is not False
        or intake.get("physical_authority") is not False
    ):
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "clearance intake is invalid or authority-bearing"
        )


def _candidate_sets(
    localization: Mapping[str, Any], intake: Mapping[str, Any]
) -> dict[str, set[str]]:
    profiles = localization.get("profiles")
    intake_profiles = intake.get("profiles")
    if (
        localization.get("schema")
        != "rocell.fixed_camera_keyboard_robot_localization.v1"
        or localization.get("status")
        != "ROBOT_FRAME_LOCALIZATION_CANDIDATES_READY"
        or not isinstance(profiles, Mapping)
        or not isinstance(intake_profiles, Mapping)
        or set(profiles) != set(SUPPORTED_PROFILES)
        or set(intake_profiles) != set(SUPPORTED_PROFILES)
    ):
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "localization does not contain both admitted profiles"
        )
    result: dict[str, set[str]] = {}
    for name in SUPPORTED_PROFILES:
        row = profiles[name]
        intake_row = intake_profiles[name]
        candidates = (
            row.get("robot_frame_localization_candidates")
            if isinstance(row, Mapping) else None
        )
        if (
            not isinstance(candidates, list)
            or len(candidates) != 46
            or not isinstance(intake_row, Mapping)
            or intake_row.get("profile") != name
            or intake_row.get("candidate_count") != 46
            or intake_row.get("robot_frame_localization_candidates_sha256")
            != _digest(candidates)
            or intake_row.get("route_construction_ready") is not True
        ):
            raise FixedCameraKeyboardProfiledTypingPlanV1Error(
                f"localized candidates differ from clearance intake: {name}"
            )
        ids = {
            item.get("key_id") for item in candidates if isinstance(item, Mapping)
        }
        if len(ids) != 46 or any(not isinstance(item, str) or not item for item in ids):
            raise FixedCameraKeyboardProfiledTypingPlanV1Error(
                f"localized candidate identities are invalid: {name}"
            )
        result[name] = ids
    if result["no_attachment"] != result["stylus_attachment"]:
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "attachment profiles expose different key identities"
        )
    return result


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            f"cannot publish new profiled typing file {path.name}: {exc}"
        ) from exc


@dataclass(frozen=True, slots=True)
class FixedCameraKeyboardProfiledTypingPlanResultV1:
    output_directory: Path
    plan_paths: Mapping[str, Path]
    manifest_path: Path
    receipt_path: Path
    manifest: Mapping[str, Any]
    receipt: Mapping[str, Any]


def admit_fixed_camera_keyboard_profiled_typing_plans_v1(
    clearance_admission_receipt_path: str | Path,
    *,
    expected_clearance_admission_receipt_file_sha256: str,
    clearance_intake_path: str | Path,
    expected_clearance_intake_file_sha256: str,
    localization_path: str | Path,
    expected_localization_file_sha256: str,
    model_motion_batch_path: str | Path,
    expected_model_motion_batch_file_sha256: str,
    ingress_report_path: str | Path,
    expected_ingress_report_file_sha256: str,
    no_attachment_config_path: str | Path,
    expected_no_attachment_config_file_sha256: str,
    stylus_attachment_config_path: str | Path,
    expected_stylus_attachment_config_file_sha256: str,
    output_directory: str | Path,
) -> FixedCameraKeyboardProfiledTypingPlanResultV1:
    """Compile and publish exact, independently bound attachment plans."""
    receipt_source, receipt_bytes, clearance_receipt = _read_json(
        clearance_admission_receipt_path,
        expected_sha256=expected_clearance_admission_receipt_file_sha256,
        label="clearance admission receipt",
    )
    intake_source, intake_bytes, intake = _read_json(
        clearance_intake_path,
        expected_sha256=expected_clearance_intake_file_sha256,
        label="clearance intake",
    )
    _validate_clearance(
        receipt_source, clearance_receipt, intake_source, intake_bytes, intake
    )
    localization_source, localization_bytes, localization = _read_json(
        localization_path,
        expected_sha256=expected_localization_file_sha256,
        label="localization",
    )
    sources = clearance_receipt.get("sources")
    bound_localization = sources.get("localization") if isinstance(sources, Mapping) else None
    if (
        not isinstance(bound_localization, Mapping)
        or bound_localization.get("file_sha256") != _sha256(localization_bytes)
        or bound_localization.get("meaning_sha256") != _digest(localization)
    ):
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "localization differs from the clearance admission source"
        )
    candidates = _candidate_sets(localization, intake)

    batch_source, batch_bytes = _read_pinned(
        model_motion_batch_path,
        expected_sha256=expected_model_motion_batch_file_sha256,
        label="model motion batch",
    )
    try:
        batch = decode_model_motion_batch_v2_json(batch_bytes)
    except ModelMotionBatchV2Error as exc:
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(str(exc)) from exc
    requested_ids = [proposal.target_id for proposal in batch.proposals]
    if (
        not set(requested_ids).issubset(candidates["no_attachment"])
        or not set(requested_ids).issubset(set(batch.uncertainty.covered_target_ids))
    ):
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "typing batch requests keys outside localized uncertainty coverage"
        )
    ingress_source, ingress_bytes, ingress = _read_json(
        ingress_report_path,
        expected_sha256=expected_ingress_report_file_sha256,
        label="ingress report",
    )
    config_inputs = {
        "no_attachment": (
            no_attachment_config_path,
            expected_no_attachment_config_file_sha256,
        ),
        "stylus_attachment": (
            stylus_attachment_config_path,
            expected_stylus_attachment_config_file_sha256,
        ),
    }
    configs: dict[str, TypingExecutionConfigV1] = {}
    config_sources: dict[str, tuple[Path, bytes]] = {}
    for name, (path, digest) in config_inputs.items():
        source, payload, document = _read_json(
            path, expected_sha256=digest, label=f"{name} typing config"
        )
        try:
            configs[name] = TypingExecutionConfigV1.from_mapping(document)
        except (TypingExecutionPlanV1Error, TypeError, ValueError) as exc:
            raise FixedCameraKeyboardProfiledTypingPlanV1Error(str(exc)) from exc
        config_sources[name] = (source, payload)
    if (
        configs["no_attachment"].config_sha256
        == configs["stylus_attachment"].config_sha256
        or configs["no_attachment"].tool_profile_sha256
        == configs["stylus_attachment"].tool_profile_sha256
    ):
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "bare-jaw and stylus typing configs and tool profiles must be distinct"
        )
    if (
        configs["no_attachment"].calibration_snapshot_sha256
        != configs["stylus_attachment"].calibration_snapshot_sha256
    ):
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "attachment typing configs must share one calibration snapshot"
        )

    plans = {}
    try:
        for name in SUPPORTED_PROFILES:
            plans[name] = compile_typing_execution_plan_v1(
                batch, ingress, config=configs[name]
            )
    except (TypingExecutionPlanV1Error, TypeError, ValueError) as exc:
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(str(exc)) from exc
    if plans["no_attachment"].plan_sha256 == plans["stylus_attachment"].plan_sha256:
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "profile-specific typing plans are not distinct"
        )

    profile_rows: dict[str, Any] = {}
    plan_bytes: dict[str, bytes] = {}
    for name in SUPPORTED_PROFILES:
        clearance_profile = intake["profiles"][name]
        payload = plans[name].to_bytes()
        plan_bytes[name] = payload
        profile_rows[name] = {
            "profile": name,
            "attachment_state": clearance_profile["attachment_state"],
            "typing_execution_config_sha256": configs[name].config_sha256,
            "tool_profile_sha256": configs[name].tool_profile_sha256,
            "typing_execution_plan_sha256": plans[name].plan_sha256,
            "typing_execution_plan_file_sha256": _sha256(payload),
            "typing_execution_plan_name": PLAN_NAMES[name],
            "installed_collision_profile_id": clearance_profile[
                "installed_collision_profile_id"
            ],
            "installed_collision_profile_content_sha256": clearance_profile[
                "installed_collision_profile_content_sha256"
            ],
            "installed_collision_profile_file_sha256": clearance_profile[
                "installed_collision_profile_file_sha256"
            ],
            "collision_contract_sha256": clearance_profile[
                "collision_contract_sha256"
            ],
            "clearance_policy_sha256": clearance_profile[
                "clearance_policy_sha256"
            ],
            "measured_tcp_sha256": clearance_profile["measured_tcp_sha256"],
            "robot_frame_localization_candidates_sha256": clearance_profile[
                "robot_frame_localization_candidates_sha256"
            ],
            "ordered_target_ids": requested_ids,
            "action_count": len(requested_ids),
            "trajectory_generated": False,
            "next_required_stage": (
                "COMPILE_PROFILE_SPECIFIC_TRAJECTORY_AND_IK_THEN_USE_"
                "TYPING_COLLISION_INTAKE_V1"
            ),
        }
    manifest_core: Mapping[str, Any] = {
        "schema": "rocell.fixed_camera_keyboard_profiled_typing_plan_manifest.v1",
        "status": "READY_FOR_PROFILE_SPECIFIC_TRAJECTORY_AND_IK",
        "clearance_intake_sha256": intake["clearance_intake_sha256"],
        "robot_localization_sha256": intake["robot_localization_sha256"],
        "model_motion_batch_sha256": batch.batch_sha256,
        "ingress_sha256": ingress.get("ingress_sha256"),
        "profiles": profile_rows,
        "profile_separation_preserved": True,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    manifest = {**manifest_core, "profiled_typing_plan_manifest_sha256": _digest(manifest_core)}
    manifest_bytes = _canonical(manifest, newline=True)

    source_rows = {
        "clearance_admission_receipt": (receipt_source, receipt_bytes),
        "clearance_intake": (intake_source, intake_bytes),
        "localization": (localization_source, localization_bytes),
        "model_motion_batch": (batch_source, batch_bytes),
        "ingress_report": (ingress_source, ingress_bytes),
        "no_attachment_config": config_sources["no_attachment"],
        "stylus_attachment_config": config_sources["stylus_attachment"],
    }
    receipt: Mapping[str, Any] = {
        "schema": "rocell.fixed_camera_keyboard_profiled_typing_plan_admission_receipt.v1",
        "status": ADMITTED_STATUS,
        "sources": {
            name: {
                "name": source.name,
                "size_bytes": len(payload),
                "file_sha256": _sha256(payload),
            }
            for name, (source, payload) in source_rows.items()
        },
        "artifacts": {
            **{
                f"{name}_typing_execution_plan": {
                    "name": PLAN_NAMES[name],
                    "size_bytes": len(plan_bytes[name]),
                    "file_sha256": _sha256(plan_bytes[name]),
                    "plan_sha256": plans[name].plan_sha256,
                }
                for name in SUPPORTED_PROFILES
            },
            "profiled_typing_plan_manifest": {
                "name": MANIFEST_NAME,
                "size_bytes": len(manifest_bytes),
                "file_sha256": _sha256(manifest_bytes),
                "meaning_sha256": _digest(manifest),
            },
            "completion_receipt": {"name": RECEIPT_NAME, "written_last": True},
        },
        "profile_separation_preserved": True,
        "next_required_stage": (
            "COMPILE_PROFILE_SPECIFIC_TRAJECTORY_AND_IK_THEN_USE_"
            "TYPING_COLLISION_INTAKE_V1"
        ),
        "authority": dict(ZERO_AUTHORITY),
    }
    receipt_bytes_out = _canonical(receipt, newline=True)

    requested = Path(output_directory).expanduser()
    if not requested.name or requested.name in (".", ".."):
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "output_directory must name a new directory"
        )
    parent = requested.parent.resolve()
    if not parent.is_dir():
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "output_directory parent must already exist"
        )
    destination = parent / requested.name
    if destination.exists() or destination.is_symlink():
        raise FixedCameraKeyboardProfiledTypingPlanV1Error(
            "output_directory already exists; refusing to overwrite"
        )
    try:
        destination.mkdir(mode=0o700, exist_ok=False)
        paths = {name: destination / PLAN_NAMES[name] for name in SUPPORTED_PROFILES}
        for name in SUPPORTED_PROFILES:
            _write_new(paths[name], plan_bytes[name])
        manifest_path = destination / MANIFEST_NAME
        receipt_path = destination / RECEIPT_NAME
        _write_new(manifest_path, manifest_bytes)
        _write_new(receipt_path, receipt_bytes_out)
    except Exception:
        if destination.exists():
            for child in destination.iterdir():
                child.unlink(missing_ok=True)
            destination.rmdir()
        raise
    return FixedCameraKeyboardProfiledTypingPlanResultV1(
        destination, paths, manifest_path, receipt_path, manifest, receipt
    )


__all__ = [
    "ADMITTED_STATUS",
    "MANIFEST_NAME",
    "PLAN_NAMES",
    "RECEIPT_NAME",
    "ZERO_AUTHORITY",
    "FixedCameraKeyboardProfiledTypingPlanResultV1",
    "FixedCameraKeyboardProfiledTypingPlanV1Error",
    "admit_fixed_camera_keyboard_profiled_typing_plans_v1",
]
