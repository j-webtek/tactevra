"""Strict, zero-authority configuration-epoch planning contract.

An epoch is a dependency boundary, not a release label.  This module validates
the pre-hardware policy that says which physical or software changes make
commissioning evidence stale.  It deliberately does not create epoch records,
promote a build, issue a permit, or touch hardware; those runtime operations
remain blocked until the v2 persistence work is implemented and reviewed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from rocell.application.physical_onboarding_durability import (
    PhysicalOnboardingDurabilityError,
    read_bounded_regular_file,
)
from rocell.application.physical_onboarding import PhysicalOnboardingStage


CONFIGURATION_EPOCH_POLICY_SCHEMA = "rocell.configuration_epoch_policy.v1"
DEFAULT_CONFIGURATION_EPOCH_POLICY = Path("software/config/configuration_epochs.json")
MAX_CONFIGURATION_EPOCH_POLICY_BYTES = 256 * 1024

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_EXPECTED_EPOCH_IDS = (
    "software_build",
    "camera_support_optics",
    "board_tags_bench",
    "arm_controller_tool",
    "power_system",
    "keyboard_station",
    "phone_station",
    "empty_cell_safety",
)
_EXPECTED_INVALIDATES_FROM_STAGE = {
    "software_build": PhysicalOnboardingStage.WORKSPACE_SOURCES,
    "camera_support_optics": PhysicalOnboardingStage.CAMERA_RECEIPT,
    "board_tags_bench": PhysicalOnboardingStage.CAMERA_RECEIPT,
    "arm_controller_tool": PhysicalOnboardingStage.ARM_IDENTITY,
    "power_system": PhysicalOnboardingStage.POWER_SAFETY,
    "keyboard_station": PhysicalOnboardingStage.REFERENCE_FRAME_CALIBRATION,
    "phone_station": PhysicalOnboardingStage.REFERENCE_FRAME_CALIBRATION,
    "empty_cell_safety": PhysicalOnboardingStage.POWER_SAFETY,
}
_EXPECTED_ROOT_FIELDS = frozenset(
    {
        "schema",
        "policy_id",
        "revision",
        "status",
        "runtime_activation",
        "authority",
        "transition_policy",
        "epochs",
        "physical_blockers",
    }
)
_EXPECTED_AUTHORITY = {
    "planning_authority": True,
    "simulation_authority": True,
    "robot_power_authorized": False,
    "motion_authorized": False,
    "contact_authorized": False,
    "physical_release_effect": "NONE",
}
_EXPECTED_TRANSITION_POLICY = {
    "records_are_append_only": True,
    "predecessor_hash_required": True,
    "reason_code_required": True,
    "affected_artifacts_must_be_invalidated": True,
    "cross_epoch_artifact_reuse_requires_exact_dependency_hashes": True,
    "freeze_number_alone_identifies_epoch": False,
}


class ConfigurationEpochPolicyError(ValueError):
    """The epoch policy is malformed, unsafe, or outside the workspace."""


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationEpochPolicyError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _reject_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ConfigurationEpochPolicyError(f"nonfinite JSON value {value!r}")
    raise ConfigurationEpochPolicyError("configuration epoch policy must not use floats")


def _reject_constant(value: str) -> None:
    raise ConfigurationEpochPolicyError(f"nonfinite JSON constant {value!r}")


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationEpochPolicyError(f"{label} must be an object")
    return value


def _exact_fields(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise ConfigurationEpochPolicyError(
            f"{label} fields differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ConfigurationEpochPolicyError(f"{label} must be non-empty trimmed text")
    if len(value) > 512:
        raise ConfigurationEpochPolicyError(f"{label} is too long")
    return value


def _identifier(value: object, label: str) -> str:
    result = _text(value, label)
    if _IDENTIFIER.fullmatch(result) is None:
        raise ConfigurationEpochPolicyError(f"{label} is not a valid identifier")
    return result


def _unique_text_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigurationEpochPolicyError(f"{label} must be a non-empty list")
    result = tuple(_identifier(item, f"{label} item") for item in value)
    if len(result) != len(set(result)):
        raise ConfigurationEpochPolicyError(f"{label} contains duplicates")
    return result


def _reject_symlink_chain(path: Path, label: str) -> None:
    cursor = Path(os.path.abspath(path))
    while True:
        if os.path.lexists(cursor) and cursor.is_symlink():
            raise ConfigurationEpochPolicyError(f"{label} contains a symlink")
        if cursor.parent == cursor:
            return
        cursor = cursor.parent


def _resolve_policy(workspace: Path, selected: Path) -> Path:
    _reject_symlink_chain(workspace, "workspace")
    try:
        root = workspace.resolve(strict=True)
    except OSError as exc:
        raise ConfigurationEpochPolicyError("workspace is unavailable") from exc
    candidate = selected if selected.is_absolute() else root / selected
    _reject_symlink_chain(candidate, "configuration epoch policy")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ConfigurationEpochPolicyError(
            "configuration epoch policy must be a file beneath the workspace"
        ) from exc
    if not resolved.is_file():
        raise ConfigurationEpochPolicyError("configuration epoch policy must be a file")
    return resolved


@dataclass(frozen=True, slots=True)
class ConfigurationEpochDefinition:
    """One immutable class of changes and the earliest stage it invalidates."""

    epoch_id: str
    description: str
    change_triggers: tuple[str, ...]
    invalidates_from_stage: PhysicalOnboardingStage
    required_bindings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConfigurationEpochPolicy:
    """Validated planning contract; it always carries zero physical authority."""

    source_path: Path
    source_sha256: str
    policy_id: str
    revision: int
    epochs: tuple[ConfigurationEpochDefinition, ...]
    physical_blockers: tuple[str, ...]

    @property
    def by_id(self) -> Mapping[str, ConfigurationEpochDefinition]:
        return MappingProxyType({item.epoch_id: item for item in self.epochs})

    @property
    def zero_physical_authority(self) -> bool:
        return True


def load_configuration_epoch_policy(
    workspace: Path,
    policy_path: Path | None = None,
) -> ConfigurationEpochPolicy:
    """Load and exhaustively validate the additive epoch design policy."""

    selected = DEFAULT_CONFIGURATION_EPOCH_POLICY if policy_path is None else policy_path
    resolved = _resolve_policy(Path(workspace), Path(selected))
    try:
        payload = read_bounded_regular_file(
            resolved, maximum_bytes=MAX_CONFIGURATION_EPOCH_POLICY_BYTES,
            label="configuration epoch policy",
        )
    except (OSError, PhysicalOnboardingDurabilityError) as exc:
        raise ConfigurationEpochPolicyError("could not read configuration epoch policy") from exc
    if not payload or len(payload) > MAX_CONFIGURATION_EPOCH_POLICY_BYTES:
        raise ConfigurationEpochPolicyError("configuration epoch policy size is invalid")
    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationEpochPolicyError(
            "configuration epoch policy must be strict UTF-8 JSON"
        ) from exc
    root = _mapping(document, "configuration epoch policy")
    _exact_fields(root, _EXPECTED_ROOT_FIELDS, "configuration epoch policy")
    if root["schema"] != CONFIGURATION_EPOCH_POLICY_SCHEMA:
        raise ConfigurationEpochPolicyError("unsupported configuration epoch schema")
    if root["policy_id"] != "ROCELL-CONFIGURATION-EPOCHS-001":
        raise ConfigurationEpochPolicyError("unexpected configuration epoch policy ID")
    if type(root["revision"]) is not int or root["revision"] != 1:
        raise ConfigurationEpochPolicyError("configuration epoch revision must be 1")
    if root["status"] != "DESIGN_REVIEWED_RUNTIME_MIGRATION_PENDING":
        raise ConfigurationEpochPolicyError("configuration epoch status is not fail-closed")
    if root["runtime_activation"] is not False:
        raise ConfigurationEpochPolicyError("configuration epochs cannot be runtime-active yet")
    if dict(_mapping(root["authority"], "authority")) != _EXPECTED_AUTHORITY:
        raise ConfigurationEpochPolicyError("configuration epoch policy exceeds zero authority")
    if dict(_mapping(root["transition_policy"], "transition_policy")) != _EXPECTED_TRANSITION_POLICY:
        raise ConfigurationEpochPolicyError("configuration epoch transition policy changed")

    raw_epochs = root["epochs"]
    if not isinstance(raw_epochs, list):
        raise ConfigurationEpochPolicyError("epochs must be a list")
    epochs: list[ConfigurationEpochDefinition] = []
    for index, raw_epoch in enumerate(raw_epochs):
        entry = _mapping(raw_epoch, f"epochs[{index}]")
        _exact_fields(
            entry,
            frozenset(
                {
                    "id",
                    "description",
                    "change_triggers",
                    "invalidates_from_stage",
                    "required_bindings",
                }
            ),
            f"epochs[{index}]",
        )
        try:
            stage = PhysicalOnboardingStage(entry["invalidates_from_stage"])
        except (TypeError, ValueError) as exc:
            raise ConfigurationEpochPolicyError(
                f"epochs[{index}].invalidates_from_stage is unknown"
            ) from exc
        epochs.append(
            ConfigurationEpochDefinition(
                epoch_id=_identifier(entry["id"], f"epochs[{index}].id"),
                description=_text(entry["description"], f"epochs[{index}].description"),
                change_triggers=_unique_text_tuple(
                    entry["change_triggers"], f"epochs[{index}].change_triggers"
                ),
                invalidates_from_stage=stage,
                required_bindings=_unique_text_tuple(
                    entry["required_bindings"], f"epochs[{index}].required_bindings"
                ),
            )
        )
    if tuple(item.epoch_id for item in epochs) != _EXPECTED_EPOCH_IDS:
        raise ConfigurationEpochPolicyError("configuration epoch order or membership changed")
    if any(
        item.invalidates_from_stage
        is not _EXPECTED_INVALIDATES_FROM_STAGE[item.epoch_id]
        for item in epochs
    ):
        raise ConfigurationEpochPolicyError(
            "configuration epoch invalidation boundary changed"
        )
    blockers = _unique_text_tuple(root["physical_blockers"], "physical_blockers")
    if not all(item.startswith(("v2_", "no_")) for item in blockers):
        # Identifiers are normalized to lower case by the file format check below.
        raise ConfigurationEpochPolicyError("physical blockers must remain explicit")

    return ConfigurationEpochPolicy(
        source_path=resolved,
        source_sha256=hashlib.sha256(payload).hexdigest(),
        policy_id=root["policy_id"],
        revision=root["revision"],
        epochs=tuple(epochs),
        physical_blockers=blockers,
    )


__all__ = [
    "CONFIGURATION_EPOCH_POLICY_SCHEMA",
    "DEFAULT_CONFIGURATION_EPOCH_POLICY",
    "MAX_CONFIGURATION_EPOCH_POLICY_BYTES",
    "ConfigurationEpochDefinition",
    "ConfigurationEpochPolicy",
    "ConfigurationEpochPolicyError",
    "load_configuration_epoch_policy",
]
