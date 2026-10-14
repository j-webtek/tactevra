"""Strict policy and source binding for physical onboarding.

The physical onboarding journal stores one digest rather than trusting whichever
configuration files happen to exist when a session is resumed.  This module
builds that digest from the verified build snapshot, the onboarding stage plan,
the policy itself, and every configuration, executable implementation, protocol
boundary, and operator procedure named by the policy.  It performs file reads
only: no camera or serial backend is imported.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from rocell.application.physical_onboarding import (
    MAX_EVIDENCE_BYTES,
    MAX_EVIDENCE_ITEMS,
    MAX_JOURNAL_EVENTS,
    MAX_TOTAL_EVIDENCE_BYTES,
    STAGE_ORDER,
    STAGE_PLAN_SHA256,
)
from rocell.rc03 import BuildSnapshot


PHYSICAL_ONBOARDING_POLICY_SCHEMA_V1 = "rocell.physical_onboarding_policy.v1"
PHYSICAL_ONBOARDING_POLICY_SCHEMA = "rocell.physical_onboarding_policy.v2"
PHYSICAL_ONBOARDING_SOURCE_BINDING_SCHEMA = (
    "rocell.physical_onboarding_source_binding.v1"
)
DEFAULT_PHYSICAL_ONBOARDING_POLICY = Path(
    "software/config/physical_onboarding_policy_v2.json"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_POLICY_BYTES = 256 * 1024
_MAX_SOURCE_BYTES = 32 * 1024 * 1024
_MAX_CONTROLLED_SOURCE_FILES = 2048
_EXPECTED_CONTROLLED_SOURCES_V1 = (
    "rocell.ps1",
    "setup-rocell.ps1",
    "start-rocell-onboarding.ps1",
    "software/pyproject.toml",
    "software/config/system_manifest.json",
    "software/config/runtime.json",
    "software/config/physical_onboarding_foundation.json",
    "software/config/authority_effect_policy.json",
    "software/config/physical_onboarding_stage_catalog.json",
    "software/config/configuration_epochs.json",
    "software/config/physical_onboarding_hazards.json",
    "software/config/workcell_icd.json",
    "software/config/accuracy_budget_policy.json",
    "software/config/arm_frame_contract.json",
    "active-project/RoCell_v0_3/config/workcell_layout.json",
    "active-project/RoCell_v0_3/config/robot_reach_screening.json",
    "software/config/camera_architecture_plan.json",
    "software/config/camera_profiles/arducam_b0477_imx283_16mm.json",
    "software/config/arm_connection.json",
    "software/docs/FIRST_POWER_ON_ONBOARDING.md",
    "software/docs/PHYSICAL_ONBOARDING_AUTOMATION.md",
    "software/docs/B0477_CAMERA_INTEGRATION.md",
    "hardware/static_overhead_camera/README.md",
    "hardware/static_overhead_camera/config/support_design.json",
    "hardware/static_overhead_camera/hardware_intake_template.csv",
)
_EXPECTED_CONTROLLED_SOURCES = tuple(
    {
        "software/config/physical_onboarding_foundation.json": "software/config/physical_onboarding_foundation_v2.json",
        "software/config/workcell_icd.json": "software/config/workcell_icd_v3.json",
        "software/config/camera_architecture_plan.json": "software/config/camera_architecture_plan_v2.json",
        "hardware/static_overhead_camera/config/support_design.json": "hardware/static_overhead_camera/config/commercial_tripod_candidate.json",
    }.get(path, path)
    for path in _EXPECTED_CONTROLLED_SOURCES_V1
)
_EXPECTED_CONTROLLED_SOURCE_ROOTS = ("software/src/rocell",)
_EXPECTED_HUMAN_REVIEW_STAGES = tuple(stage.value for stage in STAGE_ORDER[2:])
_EXPECTED_SIDE_EFFECT_STAGES = (
    "camera_mode_controls",
    "camera_frame_freshness",
    "optics_intrinsics",
    "static_registration",
    "power_safety",
    "power_on_observation",
    "feedback_only_connection",
    "reference_frame_calibration",
    "noncontact_acceptance",
)
_EXPECTED_ALLOWED_AUTOMATION = (
    "verify_controlled_source_integrity",
    "inspect_host_dependency_metadata_without_importing_device_backends",
    "validate_hardware_intake_copy_and_hash_evidence",
    "enumerate_device_identity_without_opening_the_arm_port",
    "validate_exact_camera_identity_and_native_mode_receipts",
    "capture_camera_diagnostics_after_an_explicit_operator_gate",
    "perform_one_feedback_only_exchange_after_all_build_and_operator_gates",
    "append_immutable_evidence_and_derive_one_next_action",
)
_EXPECTED_FORBIDDEN_AUTOMATION = (
    "automatically_apply_robot_power",
    "automatically_select_an_ambiguous_camera_or_serial_device",
    "fall_back_to_a_numeric_camera_index",
    "automatically_reconnect_or_reopen_a_device_after_failure",
    "automatically_initialize_home_or_park_the_arm",
    "automatically_send_motion_or_gripper_commands",
    "automatically_retry_a_serial_exchange_motion_or_contact",
    "automatically_repeat_an_uncertain_physical_effect",
    "grant_robot_power_motion_contact_or_physical_release_authority",
)


class PhysicalOnboardingPolicyError(ValueError):
    """A controlled onboarding policy or source tree is unsafe or malformed."""


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PhysicalOnboardingPolicyError(
            f"value is not canonical JSON: {exc}"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise PhysicalOnboardingPolicyError(f"duplicate policy field {key!r}")
        document[key] = value
    return document


def _reject_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise PhysicalOnboardingPolicyError(f"nonfinite policy value {value!r}")
    raise PhysicalOnboardingPolicyError("onboarding policy must not contain floats")


def _reject_constant(value: str) -> None:
    raise PhysicalOnboardingPolicyError(f"nonfinite policy constant {value!r}")


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PhysicalOnboardingPolicyError(f"{label} must be an object")
    return value


def _exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise PhysicalOnboardingPolicyError(
            f"{label} fields differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _exact_string_list(value: object, expected: tuple[str, ...], label: str) -> None:
    if not isinstance(value, list) or tuple(value) != expected:
        raise PhysicalOnboardingPolicyError(f"{label} differs from the locked policy")


def _reject_symlink_chain(path: Path, label: str) -> None:
    cursor = Path(os.path.abspath(path))
    while True:
        if os.path.lexists(cursor) and cursor.is_symlink():
            raise PhysicalOnboardingPolicyError(f"{label} contains a symlink")
        if cursor.parent == cursor:
            return
        cursor = cursor.parent


def _workspace_root(workspace: Path) -> Path:
    _reject_symlink_chain(workspace, "workspace")
    try:
        root = Path(workspace).resolve(strict=True)
    except OSError as exc:
        raise PhysicalOnboardingPolicyError("workspace is unavailable") from exc
    if not root.is_dir():
        raise PhysicalOnboardingPolicyError("workspace must be a directory")
    return root


def _contained_path(
    root: Path,
    requested: Path,
    *,
    label: str,
    must_exist: bool,
) -> Path:
    selected = requested if requested.is_absolute() else root / requested
    _reject_symlink_chain(selected, label)
    try:
        resolved = selected.resolve(strict=must_exist)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise PhysicalOnboardingPolicyError(
            f"{label} is unavailable or outside the workspace"
        ) from exc
    return resolved


def _read_strict_policy(path: Path) -> tuple[Mapping[str, Any], bytes]:
    if not path.is_file():
        raise PhysicalOnboardingPolicyError("policy must be a regular file")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise PhysicalOnboardingPolicyError("could not read onboarding policy") from exc
    if not payload or len(payload) > _MAX_POLICY_BYTES:
        raise PhysicalOnboardingPolicyError(
            f"policy size must be within 1..{_MAX_POLICY_BYTES} bytes"
        )
    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PhysicalOnboardingPolicyError(
            "onboarding policy must be strict UTF-8 JSON"
        ) from exc
    return _mapping(document, "policy"), payload


def _relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PhysicalOnboardingPolicyError(f"{label} must be non-empty text")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value.startswith(("/", "\\")):
        raise PhysicalOnboardingPolicyError(
            f"{label} must be a workspace-relative path without traversal"
        )
    return path.as_posix()


@dataclass(frozen=True, slots=True)
class PhysicalOnboardingPolicy:
    """Validated, fail-closed physical onboarding policy."""

    policy_id: str
    policy_relative_path: str
    policy_file_sha256: str
    session_root_relative: str
    controlled_sources: tuple[str, ...]
    controlled_source_roots: tuple[str, ...]
    possible_device_side_effect_stages: tuple[str, ...]
    require_workspace_venv_for_device_access: bool
    windows_venv_python: str
    linux_venv_python: str
    workspace_launcher: str
    bootstrap_script: str

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise PhysicalOnboardingPolicyError("policy_id must not be empty")
        if _SHA256_RE.fullmatch(self.policy_file_sha256) is None:
            raise PhysicalOnboardingPolicyError("policy hash is invalid")
        if self.controlled_sources not in (
            _EXPECTED_CONTROLLED_SOURCES_V1,
            _EXPECTED_CONTROLLED_SOURCES,
        ):
            raise PhysicalOnboardingPolicyError("controlled source order changed")
        if self.controlled_source_roots != _EXPECTED_CONTROLLED_SOURCE_ROOTS:
            raise PhysicalOnboardingPolicyError("controlled source-root order changed")
        if self.possible_device_side_effect_stages != _EXPECTED_SIDE_EFFECT_STAGES:
            raise PhysicalOnboardingPolicyError(
                "possible side-effect stage order changed"
            )
        if self.require_workspace_venv_for_device_access is not True:
            raise PhysicalOnboardingPolicyError(
                "device access must require the controlled workspace environment"
            )

    def session_root(self, workspace: Path) -> Path:
        """Resolve the configured session parent without creating it."""

        root = _workspace_root(workspace)
        return _contained_path(
            root,
            Path(self.session_root_relative),
            label="physical onboarding session root",
            must_exist=False,
        )


@dataclass(frozen=True, slots=True)
class ControlledSourceDigest:
    relative_path: str
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class PhysicalOnboardingSourceBinding:
    policy_id: str
    policy_file_sha256: str
    build_snapshot_sha256: str
    stage_plan_sha256: str
    sources: tuple[ControlledSourceDigest, ...]
    source_binding_sha256: str

    def core_dict(self) -> dict[str, object]:
        return {
            "schema": PHYSICAL_ONBOARDING_SOURCE_BINDING_SCHEMA,
            "policy_id": self.policy_id,
            "policy_file_sha256": self.policy_file_sha256,
            "build_snapshot_sha256": self.build_snapshot_sha256,
            "stage_plan_sha256": self.stage_plan_sha256,
            "sources": [source.to_dict() for source in self.sources],
            "authority": {
                "hardware_accessed": False,
                "robot_power_authorized": False,
                "motion_authorized": False,
                "contact_authorized": False,
                "physical_release_effect": "NONE",
            },
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.core_dict(), "source_binding_sha256": self.source_binding_sha256}


def load_physical_onboarding_policy(
    workspace: Path,
    policy_path: Path | None = None,
) -> PhysicalOnboardingPolicy:
    """Load and exhaustively validate the controlled onboarding policy."""

    root = _workspace_root(workspace)
    selected = (
        DEFAULT_PHYSICAL_ONBOARDING_POLICY if policy_path is None else policy_path
    )
    resolved = _contained_path(
        root,
        Path(selected),
        label="physical onboarding policy",
        must_exist=True,
    )
    document, payload = _read_strict_policy(resolved)
    _exact_fields(
        document,
        {
            "schema",
            "policy_id",
            "session_root",
            "controlled_environment",
            "controlled_sources",
            "controlled_source_roots",
            "camera_contract",
            "arm_contract",
            "workflow",
            "automation",
            "limits",
            "authority",
        },
        "policy",
    )
    schema = document["schema"]
    policy_id = document["policy_id"]
    if (schema, policy_id) == (
        PHYSICAL_ONBOARDING_POLICY_SCHEMA_V1,
        "ROCELL-PHYSICAL-ONBOARDING-001",
    ):
        expected_sources = _EXPECTED_CONTROLLED_SOURCES_V1
    elif (schema, policy_id) == (
        PHYSICAL_ONBOARDING_POLICY_SCHEMA,
        "ROCELL-PHYSICAL-ONBOARDING-TRIPOD-002",
    ):
        expected_sources = _EXPECTED_CONTROLLED_SOURCES
    else:
        raise PhysicalOnboardingPolicyError("unsupported onboarding policy schema")

    environment = _mapping(document["controlled_environment"], "controlled_environment")
    _exact_fields(
        environment,
        {
            "bootstrap_script",
            "linux_venv_python",
            "require_workspace_venv_for_device_access",
            "windows_venv_python",
            "workspace_launcher",
        },
        "controlled_environment",
    )
    expected_environment = {
        "bootstrap_script": "setup-rocell.ps1",
        "linux_venv_python": ".venv/bin/python",
        "require_workspace_venv_for_device_access": True,
        "windows_venv_python": ".venv/Scripts/python.exe",
        "workspace_launcher": "rocell.ps1",
    }
    if dict(environment) != expected_environment:
        raise PhysicalOnboardingPolicyError("controlled environment contract changed")

    _exact_string_list(
        document["controlled_sources"],
        expected_sources,
        "controlled_sources",
    )
    _exact_string_list(
        document["controlled_source_roots"],
        _EXPECTED_CONTROLLED_SOURCE_ROOTS,
        "controlled_source_roots",
    )
    camera = _mapping(document["camera_contract"], "camera_contract")
    expected_camera: Mapping[str, object] = {
        "automatic_backend_fallback": False,
        "expected_model": "Arducam B0477",
        "expected_sensor": "Sony IMX283",
        "height_px": 3648,
        "host_bus": "USB_3_2_GEN_1",
        "interface": "USB_UVC",
        "maximum_fps": 9,
        "mount": "rigid_static_overhead_eye_to_hand",
        "persistent_identity_required": True,
        "pixel_format": "YUY2",
        "width_px": 5472,
    }
    if camera != expected_camera:
        raise PhysicalOnboardingPolicyError("B0477 camera connection contract changed")

    arm = _mapping(document["arm_contract"], "arm_contract")
    expected_arm: Mapping[str, object] = {
        "automatic_connection": False,
        "automatic_initialization": False,
        "automatic_retry": False,
        "baudrate": 115200,
        "controller": "ESP32",
        "dtr": False,
        "feedback_request": "T=105",
        "feedback_response": "T=1051",
        "model": "Waveshare RoArm-M3 Pro",
        "power_application_is_possible_motion_event": True,
        "rts": False,
        "transport": "direct_host_usb_serial",
    }
    if arm != expected_arm:
        raise PhysicalOnboardingPolicyError("RoArm connection contract changed")

    workflow = _mapping(document["workflow"], "workflow")
    _exact_fields(
        workflow,
        {
            "ordered_stages",
            "human_review_required_stages",
            "possible_device_side_effect_stages",
        },
        "workflow",
    )
    _exact_string_list(
        workflow["ordered_stages"],
        tuple(stage.value for stage in STAGE_ORDER),
        "workflow.ordered_stages",
    )
    _exact_string_list(
        workflow["human_review_required_stages"],
        _EXPECTED_HUMAN_REVIEW_STAGES,
        "workflow.human_review_required_stages",
    )
    _exact_string_list(
        workflow["possible_device_side_effect_stages"],
        _EXPECTED_SIDE_EFFECT_STAGES,
        "workflow.possible_device_side_effect_stages",
    )

    automation = _mapping(document["automation"], "automation")
    _exact_fields(
        automation,
        {"allowed", "forbidden", "resume_replays_in_flight_actions"},
        "automation",
    )
    _exact_string_list(
        automation["allowed"], _EXPECTED_ALLOWED_AUTOMATION, "automation.allowed"
    )
    _exact_string_list(
        automation["forbidden"],
        _EXPECTED_FORBIDDEN_AUTOMATION,
        "automation.forbidden",
    )
    if automation["resume_replays_in_flight_actions"] is not False:
        raise PhysicalOnboardingPolicyError(
            "resume must never replay an in-flight action"
        )

    limits = _mapping(document["limits"], "limits")
    if limits != {
        "maximum_evidence_bytes": MAX_EVIDENCE_BYTES,
        "maximum_evidence_items": MAX_EVIDENCE_ITEMS,
        "maximum_journal_events": MAX_JOURNAL_EVENTS,
        "maximum_total_evidence_bytes": MAX_TOTAL_EVIDENCE_BYTES,
    }:
        raise PhysicalOnboardingPolicyError("policy limits differ from journal limits")
    authority = _mapping(document["authority"], "authority")
    if authority != {
        "contact_authority": False,
        "live_motion_authority": False,
        "physical_release_effect": "NONE",
        "robot_power_authority": False,
    }:
        raise PhysicalOnboardingPolicyError("policy exceeds zero physical authority")

    session_root_relative = _relative_path(document["session_root"], "session_root")
    if session_root_relative != "software/runs/physical-onboarding":
        raise PhysicalOnboardingPolicyError("session_root differs from the locked path")
    relative_policy = resolved.relative_to(root).as_posix()
    return PhysicalOnboardingPolicy(
        policy_id=document["policy_id"],
        policy_relative_path=relative_policy,
        policy_file_sha256=hashlib.sha256(payload).hexdigest(),
        session_root_relative=session_root_relative,
        controlled_sources=expected_sources,
        controlled_source_roots=_EXPECTED_CONTROLLED_SOURCE_ROOTS,
        possible_device_side_effect_stages=_EXPECTED_SIDE_EFFECT_STAGES,
        require_workspace_venv_for_device_access=True,
        windows_venv_python=environment["windows_venv_python"],
        linux_venv_python=environment["linux_venv_python"],
        workspace_launcher=environment["workspace_launcher"],
        bootstrap_script=environment["bootstrap_script"],
    )


def bind_physical_onboarding_sources(
    workspace: Path,
    snapshot: BuildSnapshot,
    policy_path: Path | None = None,
) -> tuple[PhysicalOnboardingPolicy, PhysicalOnboardingSourceBinding]:
    """Hash every source that a new physical onboarding session relies on."""

    if not isinstance(snapshot, BuildSnapshot):
        raise TypeError("snapshot must be BuildSnapshot")
    if _SHA256_RE.fullmatch(snapshot.snapshot_hash) is None:
        raise PhysicalOnboardingPolicyError("build snapshot hash is invalid")
    root = _workspace_root(workspace)
    policy = load_physical_onboarding_policy(root, policy_path)
    relative_paths = [policy.policy_relative_path, *policy.controlled_sources]
    for relative_root in policy.controlled_source_roots:
        source_root = _contained_path(
            root,
            Path(relative_root),
            label=f"controlled source root {relative_root}",
            must_exist=True,
        )
        if not source_root.is_dir():
            raise PhysicalOnboardingPolicyError(
                f"controlled source root is not a directory: {relative_root}"
            )
        discovered: list[str] = []
        for directory, directory_names, file_names in os.walk(
            source_root, followlinks=False
        ):
            directory_path = Path(directory)
            for name in tuple(directory_names):
                candidate = directory_path / name
                if candidate.is_symlink():
                    raise PhysicalOnboardingPolicyError(
                        f"controlled source root contains a directory symlink: {candidate}"
                    )
            directory_names[:] = sorted(
                name for name in directory_names if name != "__pycache__"
            )
            for name in sorted(file_names):
                candidate = directory_path / name
                if candidate.is_symlink():
                    raise PhysicalOnboardingPolicyError(
                        f"controlled source root contains a file symlink: {candidate}"
                    )
                if candidate.suffix == ".py":
                    discovered.append(candidate.relative_to(root).as_posix())
        if not discovered:
            raise PhysicalOnboardingPolicyError(
                f"controlled source root contains no Python sources: {relative_root}"
            )
        relative_paths.extend(sorted(discovered))
    if len(relative_paths) > _MAX_CONTROLLED_SOURCE_FILES:
        raise PhysicalOnboardingPolicyError("controlled source closure is too large")
    if len(relative_paths) != len(set(relative_paths)):
        raise PhysicalOnboardingPolicyError(
            "controlled source closure contains duplicates"
        )
    sources: list[ControlledSourceDigest] = []
    for relative in relative_paths:
        resolved = _contained_path(
            root,
            Path(relative),
            label=f"controlled source {relative}",
            must_exist=True,
        )
        if not resolved.is_file():
            raise PhysicalOnboardingPolicyError(
                f"controlled source is not a regular file: {relative}"
            )
        try:
            payload = resolved.read_bytes()
        except OSError as exc:
            raise PhysicalOnboardingPolicyError(
                f"could not read controlled source: {relative}"
            ) from exc
        if not payload or len(payload) > _MAX_SOURCE_BYTES:
            raise PhysicalOnboardingPolicyError(
                f"controlled source size is outside 1..{_MAX_SOURCE_BYTES}: {relative}"
            )
        sources.append(
            ControlledSourceDigest(
                relative_path=relative,
                size_bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
    provisional = PhysicalOnboardingSourceBinding(
        policy_id=policy.policy_id,
        policy_file_sha256=policy.policy_file_sha256,
        build_snapshot_sha256=snapshot.snapshot_hash,
        stage_plan_sha256=STAGE_PLAN_SHA256,
        sources=tuple(sources),
        source_binding_sha256="0" * 64,
    )
    binding = PhysicalOnboardingSourceBinding(
        policy_id=provisional.policy_id,
        policy_file_sha256=provisional.policy_file_sha256,
        build_snapshot_sha256=provisional.build_snapshot_sha256,
        stage_plan_sha256=provisional.stage_plan_sha256,
        sources=provisional.sources,
        source_binding_sha256=_canonical_sha256(provisional.core_dict()),
    )
    return policy, binding


__all__ = [
    "DEFAULT_PHYSICAL_ONBOARDING_POLICY",
    "PHYSICAL_ONBOARDING_POLICY_SCHEMA",
    "PHYSICAL_ONBOARDING_POLICY_SCHEMA_V1",
    "PHYSICAL_ONBOARDING_SOURCE_BINDING_SCHEMA",
    "ControlledSourceDigest",
    "PhysicalOnboardingPolicy",
    "PhysicalOnboardingPolicyError",
    "PhysicalOnboardingSourceBinding",
    "bind_physical_onboarding_sources",
    "load_physical_onboarding_policy",
]
