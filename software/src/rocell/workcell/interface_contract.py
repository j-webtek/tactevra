"""Strict loader for the additive, zero-authority workcell ICD.

The ICD is intentionally a thin compatibility boundary.  It names the owners
of board geometry, robot frames, connection settings, camera architecture,
support design, intake evidence, commissioning epochs, and onboarding
authority without copying their hardware values.  Loading it verifies the
actual bytes of every referenced source.  It does not open a device, promote
calibration evidence, advance an epoch, issue a permit, or authorize power,
motion, descent, or contact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence


WORKCELL_INTERFACE_CONTRACT_SCHEMA_V1 = "rocell.workcell_interface_contract.v1"
WORKCELL_INTERFACE_CONTRACT_SCHEMA = "rocell.workcell_interface_contract.v2"
DEFAULT_WORKCELL_INTERFACE_CONTRACT = Path("software/config/workcell_icd_v2.json")
MAX_WORKCELL_INTERFACE_CONTRACT_BYTES = 64 * 1024
MAX_WORKCELL_INTERFACE_SOURCE_BYTES = 2 * 1024 * 1024

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ROOT_FIELDS = frozenset(
    {
        "schema",
        "schema_version",
        "contract_id",
        "status",
        "authority",
        "source_bindings",
        "coordinate_conventions",
        "mechanical_interface",
        "electrical_power_interface",
        "uvc_interface",
        "serial_interface",
        "timing_and_freshness",
        "provider_roles",
        "provider_binding",
        "configuration_epochs",
    }
)

_EXPECTED_SOURCE_BINDINGS_V1: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "workcell_layout": (
            "active-project/RoCell_v0_3/config/workcell_layout.json",
            "e84db9aa7b88db442f042c6f546196e350c822a2e7609cb4b652b3da535df2e1",
        ),
        "arm_frame_contract": (
            "software/config/arm_frame_contract.json",
            "5e3d39388149bdd191855e0bdd8c5eb7387f0419da9bc31a15cf3d807f1b9d6d",
        ),
        "arm_connection": (
            "software/config/arm_connection.json",
            "8b71efc87f3700aaaa3456d5cdc530d963a8caafe89e90dbb12d8e8935151adf",
        ),
        "b0477_camera_profile": (
            "software/config/camera_profiles/arducam_b0477_imx283_16mm.json",
            "c15264f866d81b99cc1155171e21d3416d3a1fa7a244b5ae97642cc989f2e024",
        ),
        "camera_architecture_plan": (
            "software/config/camera_architecture_plan.json",
            "e5414dc7295ab8a4c9c1e7e813bedf38e336755b73b9fad9431572da6e1913bf",
        ),
        "static_camera_support_design": (
            "hardware/static_overhead_camera/config/support_design.json",
            "2392257405b54022039be1da96e005690fe74df32256607a61d374d7c1720d1b",
        ),
        "hardware_intake_template": (
            "hardware/static_overhead_camera/hardware_intake_template.csv",
            "b54e3abd3f8b2c84aaa66ab32606cb9cde7890cda6cc56fe26ffbb3101169215",
        ),
        "configuration_epoch_policy": (
            "software/config/configuration_epochs.json",
            "5e0af455425feae892791186c259cff0f124dad3259a37b4acd09598b71eefc7",
        ),
        "physical_onboarding_policy": (
            "software/config/physical_onboarding_policy.json",
            "30af2bdf05d239b0eefc2079a88fb1916ab9d09cc4a1cb1a8a40b77f97369ee9",
        ),
    }
)

_EXPECTED_SOURCE_BINDINGS_V2: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        **{
            key: value
            for key, value in _EXPECTED_SOURCE_BINDINGS_V1.items()
            if key not in {"camera_architecture_plan", "static_camera_support_design"}
        },
        "camera_architecture_plan": (
            "software/config/camera_architecture_plan_v2.json",
            "b296d0f1ccd53d82db31816164de1b33d42a6c348271e814060c4242f1ff733f",
        ),
        "commercial_tripod_candidate": (
            "hardware/static_overhead_camera/config/commercial_tripod_candidate.json",
            "3f132aee15b5a3b5c65e1c6dfc04523cf5ded61939088bc34e0ddcee9e28fbe9",
        ),
    }
)

_EXPECTED_AUTHORITY = {
    "interface_description_authority": True,
    "simulation_validation_authority": True,
    "hardware_presence_authority": False,
    "device_open_authority": False,
    "robot_power_authority": False,
    "motion_authority": False,
    "descent_authority": False,
    "contact_authority": False,
    "calibration_promotion_authority": False,
    "physical_release_effect": "NONE",
    "rule": (
        "Loading or satisfying this ICD only proves source-bound interface "
        "compatibility; it never grants device access, energization, calibration "
        "promotion, motion, descent, contact, or physical release."
    ),
}

_EXPECTED_COORDINATE_CONVENTIONS = {
    "layout_and_board_frame_source": "workcell_layout",
    "arm_frame_registry_source": "arm_frame_contract",
    "static_camera_frame_source": "camera_architecture_plan",
    "length_unit": "mm",
    "angle_unit": "rad",
    "elapsed_time_unit": "s",
    "monotonic_timestamp_unit": "ns",
    "image_coordinate_unit": "px",
    "voltage_unit": "V",
    "transform_notation": ("A_T_B maps coordinates expressed in frame B into frame A"),
    "frame_definitions_redeclared_here": False,
    "implicit_frame_aliases_allowed": False,
    "implicit_unit_conversion_allowed": False,
    "measured_transform_required_for_physical_use": True,
}

_EXPECTED_MECHANICAL_INTERFACE = {
    "canonical_layout_source": "workcell_layout",
    "canonical_arm_frame_source": "arm_frame_contract",
    "static_support_candidate_source": "static_camera_support_design",
    "receipt_and_fit_up_source": "hardware_intake_template",
    "nominal_or_screening_geometry_is_measurement": False,
    "unmeasured_geometry_may_authorize_motion": False,
    "installed_article_identity_and_uncertainty_required": True,
    "changed_installation_requires_epoch_transition": True,
    "rule": (
        "Consumers reference the bound layout, frame, support, and intake "
        "sources; this ICD does not restate dimensions, transforms, fasteners, "
        "clearances, or acceptance limits."
    ),
}

_EXPECTED_MECHANICAL_INTERFACE_V2 = {
    **_EXPECTED_MECHANICAL_INTERFACE,
    "static_support_candidate_source": "commercial_tripod_candidate",
    "rule": (
        "Consumers reference the bound layout, frame, tripod, and intake "
        "sources; this ICD does not restate dimensions, transforms, fasteners, "
        "clearances, or acceptance limits."
    ),
}

_EXPECTED_ELECTRICAL_POWER_INTERFACE = {
    "arm_connection_source": "arm_connection",
    "intake_source": "hardware_intake_template",
    "authority_policy_source": "physical_onboarding_policy",
    "power_domains": ["host", "camera_usb", "controller_usb", "arm_actuator"],
    "usb_data_attachment_implies_actuator_power_authority": False,
    "software_stop_is_independent_physical_cutoff": False,
    "provider_controlled_energization_allowed": False,
    "automatic_power_on_or_repower_allowed": False,
    "fresh_reviewed_permit_required_for_each_energization": True,
    "power_loss_discharge_and_gravity_behavior_require_observation": True,
}

_EXPECTED_UVC_INTERFACE = {
    "camera_profile_source": "b0477_camera_profile",
    "architecture_source": "camera_architecture_plan",
    "support_source": "static_camera_support_design",
    "identity_selection": "PERSISTENT_OS_AND_DEVICE_IDENTITY_ONLY",
    "numeric_camera_index_is_authoritative": False,
    "open_requires_separate_stage_permission": True,
    "exact_request_and_readback_required": True,
    "silent_mode_or_control_fallback_allowed": False,
    "bounded_buffer_flush_before_evidence_capture": True,
    "identity_mode_and_controls_revalidated_after_reopen": True,
    "automatic_open_initialize_or_retry_allowed": False,
}

_EXPECTED_UVC_INTERFACE_V2 = {
    **_EXPECTED_UVC_INTERFACE,
    "support_source": "commercial_tripod_candidate",
}

_EXPECTED_SERIAL_INTERFACE = {
    "connection_source": "arm_connection",
    "frame_source": "arm_frame_contract",
    "identity_selection": "PERSISTENT_CONTROLLER_IDENTITY_ONLY",
    "port_name_alone_is_authoritative": False,
    "exclusive_owner_required": True,
    "open_requires_separate_stage_permission": True,
    "open_is_potentially_side_effectful": True,
    "feedback_diagnostic_operation": "ONE_BOUND_T105_REQUEST_EXPECTING_T1051",
    "generic_write_or_motion_operation_exposed": False,
    "automatic_connect_initialize_or_retry_allowed": False,
    "ambiguous_exchange_close_or_cleanup_attempt_required_if_possible": True,
    "ambiguous_exchange_requires_global_quarantine": True,
    "ambiguous_exchange_requires_manual_reconciliation": True,
    "same_t105_exchange_may_be_repeated_automatically": False,
    "same_t105_exchange_may_be_repeated_as_new_reviewed_attempt": False,
}

_EXPECTED_TIMING_AND_FRESHNESS = {
    "ordering_and_deadline_clock": "HOST_MONOTONIC",
    "wall_clock_is_authoritative_for_ordering": False,
    "request_start_and_completion_brackets_required": True,
    "age_and_deadline_rechecked_at_effect_boundary": True,
    "device_sequence_timestamp_or_token_must_advance_when_available": True,
    "freshness_evidence_regression_disappearance_or_replay_allowed": False,
    "host_receipt_time_proves_device_exposure_time": False,
    "in_motion_visual_correction_requires_qualified_device_exposure_timing": True,
    "reconnect_begins_new_freshness_epoch_and_requires_revalidation": True,
    "freshness_history_and_buffer_operations_must_be_bounded": True,
    "ambiguous_physical_effect_may_be_automatically_retried": False,
}

_EXPECTED_PROVIDER_ROLES = {
    "host_inventory": {
        "responsibility": (
            "Observe host dependencies and enumerate device identities without "
            "opening a selected camera or serial session."
        ),
        "capability_ceiling": "READ_ONLY_INVENTORY",
    },
    "camera_diagnostic": {
        "responsibility": (
            "Perform only the stage-scoped identity-bound UVC lifecycle declared "
            "by this ICD and return evidence receipts."
        ),
        "capability_ceiling": "CAMERA_IO_NO_ROBOT_EFFECT",
    },
    "arm_identity": {
        "responsibility": (
            "Observe controller identity while actuator power remains off and "
            "without opening the serial port."
        ),
        "capability_ceiling": "READ_ONLY_INVENTORY",
    },
    "arm_feedback": {
        "responsibility": (
            "Perform at most the separately permitted feedback-only serial "
            "lifecycle; expose no generic write, motion, torque, descent, or "
            "contact operation."
        ),
        "capability_ceiling": "SINGLE_T105_NO_MOTION_COMMAND",
    },
    "safety_evidence": {
        "responsibility": (
            "Record operator, observer, reviewer, power-topology, cutoff, "
            "containment, and first-power observations without controlling "
            "energization."
        ),
        "capability_ceiling": "OBSERVATION_ONLY",
    },
    "clock": {
        "responsibility": (
            "Supply monotonic instants and explicit wall-clock evidence without "
            "inventing device exposure timestamps."
        ),
        "capability_ceiling": "TIME_OBSERVATION_ONLY",
    },
    "evidence_store": {
        "responsibility": (
            "Persist bounded content-addressed evidence with manifest-last "
            "semantics and no device access."
        ),
        "capability_ceiling": "EVIDENCE_ONLY",
    },
}

_EXPECTED_PROVIDER_BINDING = {
    "descriptor_and_implementation_hash_required": True,
    "role_binding_required_before_invocation": True,
    "one_owned_session_per_physical_device": True,
    "provider_receipt_must_bind_request_role_epoch_and_source_hashes": True,
    "unbound_or_substituted_provider_policy": "REJECT",
    "power_actuation_role_defined": False,
    "motion_execution_role_defined": False,
    "contact_execution_role_defined": False,
    "human_role_attestation_source": "physical_onboarding_policy",
    "rule": (
        "A provider capability ceiling is not invocation authority; the active "
        "stage, permit, identity, leases, epochs, and evidence gates remain "
        "independently required."
    ),
}

_EXPECTED_CONFIGURATION_EPOCHS = {
    "policy_source": "configuration_epoch_policy",
    "epoch_definitions_redeclared_here": False,
    "complete_epoch_vector_required_on_evidence": True,
    "changed_dependency_requires_new_append_only_epoch_record": True,
    "affected_descendants_invalidated_before_next_effect": True,
    "cross_epoch_reuse_requires_exact_dependency_hashes": True,
    "freeze_number_alone_is_epoch_identity": False,
    "this_contract_may_create_advance_or_promote_an_epoch": False,
}


class WorkcellInterfaceContractError(ValueError):
    """The workcell ICD is malformed, unsafe, or no longer source coherent."""


@dataclass(frozen=True, slots=True)
class WorkcellSourceBinding:
    """One verified canonical source referenced by the ICD."""

    source_id: str
    relative_path: str
    resolved_path: Path
    sha256: str


@dataclass(frozen=True, slots=True)
class WorkcellProviderRole:
    """One provider responsibility and its maximum interface capability."""

    role_id: str
    responsibility: str
    capability_ceiling: str


@dataclass(frozen=True, slots=True)
class WorkcellInterfaceContract:
    """Validated immutable view of the zero-authority interface contract."""

    path: Path
    content_sha256: str
    contract_id: str
    status: str
    source_bindings: Mapping[str, WorkcellSourceBinding]
    provider_roles: tuple[WorkcellProviderRole, ...]
    units: Mapping[str, str]
    power_domains: tuple[str, ...]
    interface_description_authority: bool = field(default=True, init=False)
    simulation_validation_authority: bool = field(default=True, init=False)
    hardware_presence_authority: bool = field(default=False, init=False)
    device_open_authority: bool = field(default=False, init=False)
    robot_power_authority: bool = field(default=False, init=False)
    motion_authority: bool = field(default=False, init=False)
    descent_authority: bool = field(default=False, init=False)
    contact_authority: bool = field(default=False, init=False)
    calibration_promotion_authority: bool = field(default=False, init=False)
    physical_release_effect: str = field(default="NONE", init=False)

    @property
    def source_sha256(self) -> Mapping[str, str]:
        """Return an immutable source-id to verified byte-digest projection."""

        return MappingProxyType(
            {
                source_id: binding.sha256
                for source_id, binding in self.source_bindings.items()
            }
        )

    @property
    def zero_physical_authority(self) -> bool:
        """The v1 ICD has no representation capable of conferring authority."""

        return True


def _reject_json_constant(value: str) -> None:
    raise WorkcellInterfaceContractError(
        f"workcell ICD contains nonfinite JSON constant {value!r}"
    )


def _parse_finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise WorkcellInterfaceContractError(
            f"workcell ICD contains nonfinite JSON number {value!r}"
        )
    return parsed


def _object_without_duplicate_keys(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WorkcellInterfaceContractError(
                f"workcell ICD contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise WorkcellInterfaceContractError(f"{label} must be an object")
    return value


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise WorkcellInterfaceContractError(
            f"{label} fields differ: missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _validate_exact(value: object, expected: object, label: str) -> None:
    """Recursively validate a versioned literal without bool/int aliasing."""

    if isinstance(expected, dict):
        observed = _mapping(value, label)
        _exact_fields(observed, frozenset(expected), label)
        for field, expected_value in expected.items():
            _validate_exact(observed[field], expected_value, f"{label}.{field}")
        return
    if isinstance(expected, list):
        if not isinstance(value, list) or len(value) != len(expected):
            raise WorkcellInterfaceContractError(
                f"{label} must be the exact {len(expected)}-item array"
            )
        for index, (observed_item, expected_item) in enumerate(zip(value, expected)):
            _validate_exact(observed_item, expected_item, f"{label}[{index}]")
        return
    if type(value) is not type(expected) or value != expected:
        raise WorkcellInterfaceContractError(f"{label} must equal {expected!r}")


def _clean_text(value: object, label: str, *, maximum: int = 2048) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise WorkcellInterfaceContractError(
            f"{label} must be non-empty, trimmed, bounded text"
        )
    return value


def _reject_symlink_chain(path: Path, label: str) -> None:
    """Reject a symlink in the selected path or any of its ancestors."""

    cursor = Path(os.path.abspath(path))
    while True:
        try:
            if cursor.is_symlink():
                raise WorkcellInterfaceContractError(
                    f"{label} contains a symlink: {cursor}"
                )
        except OSError as exc:
            raise WorkcellInterfaceContractError(
                f"cannot inspect {label} for symlinks"
            ) from exc
        if cursor.parent == cursor:
            return
        cursor = cursor.parent


def _workspace_root(workspace: Path) -> Path:
    requested = Path(workspace)
    _reject_symlink_chain(requested, "workspace")
    try:
        root = requested.resolve(strict=True)
    except OSError as exc:
        raise WorkcellInterfaceContractError("workspace is unavailable") from exc
    if not root.is_dir():
        raise WorkcellInterfaceContractError("workspace must be a directory")
    return root


def _contained_file(root: Path, requested: Path, label: str) -> Path:
    candidate = requested if requested.is_absolute() else root / requested
    _reject_symlink_chain(candidate, label)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise WorkcellInterfaceContractError(
            f"{label} must be a file beneath the workspace"
        ) from exc
    if not resolved.is_file():
        raise WorkcellInterfaceContractError(f"{label} must be a regular file")
    return resolved


def _read_bounded(path: Path, *, maximum: int, label: str) -> bytes:
    try:
        with path.open("rb") as stream:
            payload = stream.read(maximum + 1)
    except OSError as exc:
        raise WorkcellInterfaceContractError(f"cannot read {label}") from exc
    if not payload:
        raise WorkcellInterfaceContractError(f"{label} is empty")
    if len(payload) > maximum:
        raise WorkcellInterfaceContractError(
            f"{label} exceeds the {maximum}-byte limit"
        )
    return payload


def _normalized_relative_path(value: object, label: str) -> str:
    text = _clean_text(value, label, maximum=512)
    parsed = PurePosixPath(text)
    if (
        parsed.is_absolute()
        or text != parsed.as_posix()
        or parsed.as_posix() == "."
        or "." in parsed.parts
        or ".." in parsed.parts
        or "\\" in text
        or ":" in parsed.parts[0]
    ):
        raise WorkcellInterfaceContractError(
            f"{label} must be a normalized workspace-relative POSIX path"
        )
    return text


def _validate_source_bindings(
    root: Path,
    value: object,
    *,
    expected_bindings: Mapping[str, tuple[str, str]],
    schema_version: int,
) -> Mapping[str, WorkcellSourceBinding]:
    bindings = _mapping(value, "source_bindings")
    _exact_fields(bindings, frozenset(expected_bindings), "source_bindings")
    verified: dict[str, WorkcellSourceBinding] = {}
    for source_id, (
        expected_path,
        expected_sha256,
    ) in expected_bindings.items():
        binding = _mapping(bindings[source_id], f"source_bindings.{source_id}")
        _exact_fields(
            binding,
            frozenset({"path", "sha256"}),
            f"source_bindings.{source_id}",
        )
        relative_path = _normalized_relative_path(
            binding["path"], f"source_bindings.{source_id}.path"
        )
        if relative_path != expected_path:
            raise WorkcellInterfaceContractError(
                f"source_bindings.{source_id}.path must equal {expected_path!r}"
            )
        declared_sha256 = _clean_text(
            binding["sha256"], f"source_bindings.{source_id}.sha256", maximum=64
        )
        if _SHA256.fullmatch(declared_sha256) is None:
            raise WorkcellInterfaceContractError(
                f"source_bindings.{source_id}.sha256 must be a lowercase SHA-256 digest"
            )
        if declared_sha256 != expected_sha256:
            raise WorkcellInterfaceContractError(
                f"source_bindings.{source_id}.sha256 changed from the v{schema_version} binding"
            )
        resolved = _contained_file(
            root,
            Path(*PurePosixPath(relative_path).parts),
            f"source_bindings.{source_id} source",
        )
        payload = _read_bounded(
            resolved,
            maximum=MAX_WORKCELL_INTERFACE_SOURCE_BYTES,
            label=f"source_bindings.{source_id} source",
        )
        # Recheck the lexical chain after opening so a simple path substitution
        # cannot go unnoticed between resolution and hashing.
        _reject_symlink_chain(resolved, f"source_bindings.{source_id} source")
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if actual_sha256 != declared_sha256:
            raise WorkcellInterfaceContractError(
                f"actual source SHA-256 mismatch for {relative_path}: expected "
                f"{declared_sha256}, got {actual_sha256}"
            )
        verified[source_id] = WorkcellSourceBinding(
            source_id=source_id,
            relative_path=relative_path,
            resolved_path=resolved,
            sha256=actual_sha256,
        )
    return MappingProxyType(verified)


def _parse_document(payload: bytes) -> Mapping[str, Any]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkcellInterfaceContractError("workcell ICD must be UTF-8") from exc
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_float=_parse_finite_json_float,
            parse_constant=_reject_json_constant,
        )
    except WorkcellInterfaceContractError:
        raise
    except json.JSONDecodeError as exc:
        raise WorkcellInterfaceContractError(
            f"workcell ICD is not valid JSON: {exc.msg}"
        ) from exc
    return _mapping(parsed, "workcell ICD")


def load_workcell_interface_contract(
    workspace: Path,
    contract_path: Path | None = None,
) -> WorkcellInterfaceContract:
    """Load and validate the source-bound ICD without changing any state.

    The contract file and every referenced source must be regular, non-symlink
    files beneath ``workspace``.  Both the declared v1 digests and the actual
    source bytes are checked before an immutable view is returned.
    """

    root = _workspace_root(Path(workspace))
    requested = (
        DEFAULT_WORKCELL_INTERFACE_CONTRACT
        if contract_path is None
        else Path(contract_path)
    )
    selected = _contained_file(root, requested, "workcell ICD")
    payload = _read_bounded(
        selected,
        maximum=MAX_WORKCELL_INTERFACE_CONTRACT_BYTES,
        label="workcell ICD",
    )
    _reject_symlink_chain(selected, "workcell ICD")
    document = _parse_document(payload)
    _exact_fields(document, _ROOT_FIELDS, "workcell ICD")
    schema = document["schema"]
    schema_version = document["schema_version"]
    if (
        type(schema) is str
        and type(schema_version) is int
        and (schema, schema_version) == (WORKCELL_INTERFACE_CONTRACT_SCHEMA_V1, 1)
    ):
        contract_id = "ROCELL-WORKCELL-ICD-001"
        expected_bindings = _EXPECTED_SOURCE_BINDINGS_V1
        expected_mechanical = _EXPECTED_MECHANICAL_INTERFACE
        expected_uvc = _EXPECTED_UVC_INTERFACE
    elif (
        type(schema) is str
        and type(schema_version) is int
        and (schema, schema_version) == (WORKCELL_INTERFACE_CONTRACT_SCHEMA, 2)
    ):
        contract_id = "ROCELL-WORKCELL-ICD-TRIPOD-002"
        expected_bindings = _EXPECTED_SOURCE_BINDINGS_V2
        expected_mechanical = _EXPECTED_MECHANICAL_INTERFACE_V2
        expected_uvc = _EXPECTED_UVC_INTERFACE_V2
    else:
        raise WorkcellInterfaceContractError(
            "schema and schema_version must identify workcell ICD v1 or v2"
        )
    _validate_exact(document["contract_id"], contract_id, "contract_id")
    _validate_exact(document["status"], "ADDITIVE_ZERO_AUTHORITY", "status")
    _validate_exact(document["authority"], _EXPECTED_AUTHORITY, "authority")

    source_bindings = _validate_source_bindings(
        root,
        document["source_bindings"],
        expected_bindings=expected_bindings,
        schema_version=schema_version,
    )
    _validate_exact(
        document["coordinate_conventions"],
        _EXPECTED_COORDINATE_CONVENTIONS,
        "coordinate_conventions",
    )
    _validate_exact(
        document["mechanical_interface"],
        expected_mechanical,
        "mechanical_interface",
    )
    _validate_exact(
        document["electrical_power_interface"],
        _EXPECTED_ELECTRICAL_POWER_INTERFACE,
        "electrical_power_interface",
    )
    _validate_exact(document["uvc_interface"], expected_uvc, "uvc_interface")
    _validate_exact(
        document["serial_interface"],
        _EXPECTED_SERIAL_INTERFACE,
        "serial_interface",
    )
    _validate_exact(
        document["timing_and_freshness"],
        _EXPECTED_TIMING_AND_FRESHNESS,
        "timing_and_freshness",
    )
    _validate_exact(
        document["provider_roles"], _EXPECTED_PROVIDER_ROLES, "provider_roles"
    )
    _validate_exact(
        document["provider_binding"],
        _EXPECTED_PROVIDER_BINDING,
        "provider_binding",
    )
    _validate_exact(
        document["configuration_epochs"],
        _EXPECTED_CONFIGURATION_EPOCHS,
        "configuration_epochs",
    )

    coordinate_conventions = _mapping(
        document["coordinate_conventions"], "coordinate_conventions"
    )
    electrical = _mapping(
        document["electrical_power_interface"], "electrical_power_interface"
    )
    roles = _mapping(document["provider_roles"], "provider_roles")
    provider_roles = tuple(
        WorkcellProviderRole(
            role_id=role_id,
            responsibility=_clean_text(
                _mapping(role, f"provider_roles.{role_id}")["responsibility"],
                f"provider_roles.{role_id}.responsibility",
            ),
            capability_ceiling=_clean_text(
                _mapping(role, f"provider_roles.{role_id}")["capability_ceiling"],
                f"provider_roles.{role_id}.capability_ceiling",
            ),
        )
        for role_id, role in roles.items()
    )
    units = MappingProxyType(
        {
            "length": coordinate_conventions["length_unit"],
            "angle": coordinate_conventions["angle_unit"],
            "elapsed_time": coordinate_conventions["elapsed_time_unit"],
            "monotonic_timestamp": coordinate_conventions["monotonic_timestamp_unit"],
            "image_coordinate": coordinate_conventions["image_coordinate_unit"],
            "voltage": coordinate_conventions["voltage_unit"],
        }
    )
    domains = electrical["power_domains"]
    assert isinstance(domains, list)
    return WorkcellInterfaceContract(
        path=selected,
        content_sha256=hashlib.sha256(payload).hexdigest(),
        contract_id=contract_id,
        status="ADDITIVE_ZERO_AUTHORITY",
        source_bindings=source_bindings,
        provider_roles=provider_roles,
        units=units,
        power_domains=tuple(domains),
    )


__all__ = [
    "DEFAULT_WORKCELL_INTERFACE_CONTRACT",
    "MAX_WORKCELL_INTERFACE_CONTRACT_BYTES",
    "MAX_WORKCELL_INTERFACE_SOURCE_BYTES",
    "WORKCELL_INTERFACE_CONTRACT_SCHEMA",
    "WORKCELL_INTERFACE_CONTRACT_SCHEMA_V1",
    "WorkcellInterfaceContract",
    "WorkcellInterfaceContractError",
    "WorkcellProviderRole",
    "WorkcellSourceBinding",
    "load_workcell_interface_contract",
]
