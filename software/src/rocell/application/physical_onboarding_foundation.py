"""Strict aggregate for the pre-hardware physical-onboarding foundation.

The checked-in foundation is intentionally an index, not a second copy of the
stage, authority, hazard, epoch, interface, or accuracy contracts.  Loading it
validates the byte identity of each specialized source, delegates semantic
validation to that source's strict loader, and checks the small number of
cross-contract relationships that no individual loader can own.

This module imports no device adapter and exposes no provider, permit issuer,
power operation, motion command, calibration promotion, or release operation.
Successful validation therefore proves source coherence only; it grants zero
physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, cast

from rocell.application.configuration_epochs import (
    ConfigurationEpochPolicy,
    ConfigurationEpochPolicyError,
    load_configuration_epoch_policy,
)
from rocell.application.physical_onboarding_stage_catalog import (
    PhysicalOnboardingStageCatalog,
    PhysicalOnboardingStageCatalogError,
    load_physical_onboarding_stage_catalog,
)
from rocell.application.physical_onboarding_policy import (
    PhysicalOnboardingPolicyError,
    load_physical_onboarding_policy,
)
from rocell.calibration.accuracy_budget import (
    AccuracyBudgetPolicyError,
    TargetAccuracyBudgetPolicy,
    load_target_accuracy_budget_policy,
)
from rocell.safety.effects import (
    AuthorityEffectPolicy,
    AuthorityEffectPolicyError,
    load_authority_effect_policy,
)
from rocell.safety.onboarding_hazards import (
    PhysicalOnboardingHazardError,
    PhysicalOnboardingHazardRegister,
    load_physical_onboarding_hazards,
)
from rocell.workcell.interface_contract import (
    WorkcellInterfaceContract,
    WorkcellInterfaceContractError,
    WorkcellSourceBinding,
    load_workcell_interface_contract,
)
from rocell.workcell.static_camera_support import (
    StaticCameraSupportError,
    load_static_camera_support_design,
)
from rocell.vision.camera_profile import CameraProfileError, load_camera_profile


PHYSICAL_ONBOARDING_FOUNDATION_SCHEMA_V1 = "rocell.physical_onboarding_foundation.v1"
PHYSICAL_ONBOARDING_FOUNDATION_SCHEMA = "rocell.physical_onboarding_foundation.v2"
PHYSICAL_ONBOARDING_FOUNDATION_ID_V1 = "ROCELL-PHYSICAL-ONBOARDING-FOUNDATION-001"
PHYSICAL_ONBOARDING_FOUNDATION_ID = "ROCELL-PHYSICAL-ONBOARDING-FOUNDATION-TRIPOD-002"
DEFAULT_PHYSICAL_ONBOARDING_FOUNDATION = Path(
    "software/config/physical_onboarding_foundation_v2.json"
)
MAX_PHYSICAL_ONBOARDING_FOUNDATION_BYTES = 128 * 1024
MAX_REFERENCED_CONTRACT_BYTES = 512 * 1024

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GATE = re.compile(r"[A-Z][A-Z0-9_]{0,95}\Z")
_ROOT_FIELDS = frozenset(
    {
        "schema",
        "foundation_id",
        "revision",
        "revision_date",
        "status",
        "runtime_activation",
        "authority",
        "contracts",
        "concurrency_and_durability",
        "evidence_and_datasets",
        "calibration_assurance",
        "commissioning_bundle",
        "threat_model",
        "open_implementation_gates",
    }
)
_EXPECTED_AUTHORITY: dict[str, object] = {
    "planning_authority": True,
    "simulation_authority": True,
    "device_io_authorized": False,
    "robot_power_authorized": False,
    "motion_authorized": False,
    "descent_authorized": False,
    "contact_authorized": False,
    "calibration_promotion_authorized": False,
    "build_promotion_authorized": False,
    "physical_release_effect": "NONE",
}
_EXPECTED_CONTRACTS_V1 = (
    (
        "ROCELL-AUTHORITY-EFFECT-001",
        "software/config/authority_effect_policy.json",
    ),
    (
        "ROCELL-PHYSICAL-ONBOARDING-STAGES-001",
        "software/config/physical_onboarding_stage_catalog.json",
    ),
    (
        "ROCELL-CONFIGURATION-EPOCHS-001",
        "software/config/configuration_epochs.json",
    ),
    (
        "ROCELL-PHYSICAL-ONBOARDING-HAZARDS-001",
        "software/config/physical_onboarding_hazards.json",
    ),
    (
        "ROCELL-WORKCELL-ICD-001",
        "software/config/workcell_icd.json",
    ),
    (
        "ROCELL-TARGET-ACCURACY-BUDGET-001",
        "software/config/accuracy_budget_policy.json",
    ),
)
_EXPECTED_CONTRACTS = tuple(
    (
        "ROCELL-WORKCELL-ICD-TRIPOD-003",
        "software/config/workcell_icd_v3.json",
    )
    if contract_id == "ROCELL-WORKCELL-ICD-001"
    else (contract_id, path)
    for contract_id, path in _EXPECTED_CONTRACTS_V1
)
_EXPECTED_CONCURRENCY: dict[str, object] = {
    "lease_acquisition_order": ["CELL", "SESSION", "CAMERA", "ARM_CONTROLLER"],
    "one_mutable_physical_session_per_cell": True,
    "pid_only_stale_lock_break_allowed": False,
    "device_identity_recheck_after_lock": True,
    "attempt_intent_durable_before_external_effect": True,
    "camera_open_is_first_possible_effect": True,
    "serial_open_is_first_possible_effect": True,
    "manual_energization_instruction_requires_armed_attempt": True,
    "every_actuator_off_to_on_requires_unique_envelope": True,
    "stage_11_and_stage_12_envelopes_must_differ": True,
    "emergency_deenergization_requires_software_permit": False,
    "automatic_attempt_replay_allowed": False,
    "windows_effectful_durability_state": "UNQUALIFIED_BLOCKING",
    "windows_qualification_requires": [
        "LOCKFILEEX_EXCLUSIVE_LEASE",
        "WRITE_THROUGH_FILE_OPEN",
        "FLUSH_FILE_BUFFERS",
        "ATOMIC_REPLACE",
        "DIRECTORY_ENTRY_DURABILITY_TEST",
    ],
    "effectful_action_allowed_when_durability_unqualified": False,
    "torn_tail_policy": "READ_ONLY_RECONCILIATION_NO_REPLAY",
}
_EXPECTED_EVIDENCE: dict[str, object] = {
    "native_frame_width_px": 5472,
    "native_frame_height_px": 3648,
    "native_pixel_format": "YUY2",
    "native_aspect": "3:2",
    "native_pixel_count": 19961856,
    "legacy_detector_maximum_image_pixels": 12000000,
    "implicit_detector_resize_allowed": False,
    "detector_space_policy": ("EXPLICIT_NATIVE_OR_CALIBRATED_WORKING_SPACE_REQUIRED"),
    "minimum_packed_native_frame_bytes": 39923712,
    "thirty_two_minimum_native_frames_bytes": 1277558784,
    "legacy_single_item_limit_bytes": 33554432,
    "legacy_single_item_limit_is_sufficient": False,
    "storage_format": "CHUNKED_CONTENT_ADDRESSED_MANIFEST_LAST",
    "manifest_core_digest_excludes_own_digest_field": True,
    "dataset_types": ["NATIVE_CAPTURE_DATASET", "CALIBRATION_IMAGE_DATASET"],
    "calibration_partitions": [
        "DEVELOPMENT",
        "MODEL_SELECTION",
        "UNTOUCHED_ACCEPTANCE",
    ],
    "partition_assignment_is_immutable_before_capture": True,
    "partition_overlap_allowed": False,
    "untouched_acceptance_may_drive_model_selection": False,
    "status_verification_scope": "JOURNAL_HIGH_WATER_AND_MANIFESTS_ONLY",
    "full_verification_required_before": [
        "MUTATION",
        "REVIEW",
        "PROMOTION",
        "EXPORT",
    ],
    "identity_and_mode_authority_backend": "WINDOWS_UVC_NATIVE_ADAPTER",
    "decode_backend_is_identity_or_mode_authority": False,
    "raw_evidence_preview_requires_safe_reencode": True,
}
_EXPECTED_BOOTSTRAP: dict[str, object] = {
    "required_before_repeated_uncalibrated_motion": True,
    "external_runner_only": True,
    "empty_cell_required": True,
    "device_articles_removed": True,
    "contact_allowed": False,
    "conservative_surveyed_envelope_required": True,
    "reduced_limits_required": True,
    "independent_observer_required": True,
    "fresh_permit_per_effect_required": True,
    "actual_stop_gravity_and_power_loss_checks_required": True,
    "bootstrap_artifacts_are_final_calibration": False,
}
_EXPECTED_CALIBRATION: dict[str, object] = {
    "freshness_requires_visible_time_varying_stimulus": True,
    "distinct_frame_hashes_alone_prove_freshness": False,
    "partition_policy_source": "evidence_and_datasets.calibration_partitions",
    "development_data_may_be_reused_for_fit": True,
    "model_selection_data_may_be_used_for_final_acceptance": False,
    "untouched_acceptance_data_may_be_used_for_fit_or_selection": False,
    "disturbed_final_calibration_must_be_reacquired": True,
    "precalibration_motion_bootstrap": _EXPECTED_BOOTSTRAP,
}
_REQUIRED_BUNDLE_COMPONENTS = [
    "controlled_source_binding",
    "provider_implementation_hashes",
    "runner_implementation_hashes",
    "camera_receipt",
    "passive_workcell_receipt",
    "camera_identity",
    "camera_mode_controls",
    "camera_frame_freshness",
    "installed_camera_intrinsics",
    "measured_tag_map",
    "static_camera_to_board_transform",
    "installed_optical_stability",
    "passive_visibility_atlas",
    "dataset_partition_manifests",
    "exact_arm_physical_identity",
    "power_safety_review",
    "first_power_observation",
    "startup_sweep_evidence",
    "feedback_only_exchange",
    "qualified_controller_identity",
    "bootstrap_phase_receipt",
    "reference_characterization_phase_receipt",
    "arm_to_board_transform",
    "controller_model_correlation",
    "free_state_tool_tcp",
    "keyboard_target_map",
    "phone_target_map",
    "outcome_observer_candidates",
    "noncontact_qualification_phase_receipt",
    "untouched_final_acceptance_phase_receipt",
    "noncontact_acceptance_report",
    "arm_induced_visibility_atlas",
    "collision_configuration",
    "accuracy_budget_assessment",
    "configuration_epoch_vector",
    "global_attempt_ledger_head",
    "global_quarantine_ledger_head",
    "reviewer_decisions",
    "open_blockers",
]
_EXPECTED_COMMISSIONING_BUNDLE: dict[str, object] = {
    "schema_target": "rocell.installed_workcell_candidate.v1",
    "phase_order": [
        "BOOTSTRAP",
        "REFERENCE_CHARACTERIZATION",
        "NONCONTACT_QUALIFICATION",
        "UNTOUCHED_FINAL_ACCEPTANCE",
    ],
    "phase_predecessor_hash_required": True,
    "required_components": _REQUIRED_BUNDLE_COMPONENTS,
    "contract_hashes_and_epoch_vector_required": True,
    "missing_stale_or_unbounded_component_policy": "BLOCK",
    "physical_runtime_nominal_fallback_allowed": False,
    "stage_15_effect": "DIAGNOSTIC_CANDIDATE_ONLY",
    "separate_reviewed_promotion_required": True,
    "keyboard_and_phone_contact_release_are_independent": True,
}
_EXPECTED_THREAT_MODEL: dict[str, object] = {
    "in_scope": [
        "ACCIDENTAL_REPLAY",
        "STALE_OR_TAMPERED_EVIDENCE",
        "CONCURRENT_LOCAL_CLIENTS",
        "MALFORMED_INPUT",
        "CROSS_ORIGIN_BROWSER_REQUESTS",
        "PROCESS_CRASH",
    ],
    "trusted_local_administrator_out_of_scope": True,
    "cryptographic_physical_provenance_claim_allowed": False,
    "zero_authority_validation_is_physical_qualification": False,
}
_EXPECTED_OPEN_GATES = (
    "V2_SESSION_SCHEMA_AND_V1_READ_ONLY_LOADER",
    "ATTEMPT_LEDGER_AND_REVIEW_PENDING_STATE",
    "CELL_DEVICE_LEASES_AND_GLOBAL_QUARANTINE",
    "WINDOWS_DURABILITY_AND_TORN_TAIL_RECOVERY",
    "MANUAL_ENERGIZATION_PERMIT_AND_ROLE_ENFORCEMENT",
    "BOUNDED_PROVIDER_CAMPAIGNS_AND_PROCESS_CONTAINMENT",
    "CHUNKED_NATIVE_DATASET_AND_VERIFICATION_TIERS",
    "PRECALIBRATION_MOTION_BOOTSTRAP_CONTRACT",
    "COMMISSIONING_BUNDLE_AND_NO_NOMINAL_FALLBACK",
    "KEYBOARD_PHONE_ACCURACY_BUDGET_REVIEW",
)
_B0477_NATIVE_HOST_BUS = "USB_3_2_GEN_1"
_B0477_NATIVE_MAXIMUM_FPS = 9.0
_B0477_NATIVE_PIXEL_FORMAT = "YUY2"


class PhysicalOnboardingFoundationError(ValueError):
    """The aggregate is malformed, source-stale, or no longer fail-closed."""


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PhysicalOnboardingFoundationError(
                f"duplicate foundation JSON field {key!r}"
            )
        result[key] = value
    return result


def _reject_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise PhysicalOnboardingFoundationError(
            f"foundation contains nonfinite value {value!r}"
        )
    raise PhysicalOnboardingFoundationError(
        "foundation must not contain floating-point values"
    )


def _parse_integer(value: str) -> int:
    if len(value.lstrip("-")) > 16:
        raise PhysicalOnboardingFoundationError(
            "foundation integer exceeds the parsing bound"
        )
    return int(value)


def _reject_constant(value: str) -> None:
    raise PhysicalOnboardingFoundationError(
        f"foundation contains nonfinite constant {value!r}"
    )


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise PhysicalOnboardingFoundationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise PhysicalOnboardingFoundationError(
            f"{label} fields differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _typed_equal(actual: object, expected: object) -> bool:
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        actual_map = cast(dict[object, object], actual)
        expected_map = cast(dict[object, object], expected)
        return set(actual_map) == set(expected_map) and all(
            _typed_equal(actual_map[key], expected_map[key]) for key in expected_map
        )
    if type(expected) is list:
        actual_list = cast(list[object], actual)
        expected_list = cast(list[object], expected)
        return len(actual_list) == len(expected_list) and all(
            _typed_equal(actual_item, expected_item)
            for actual_item, expected_item in zip(actual_list, expected_list)
        )
    return actual == expected


def _require_exact(actual: object, expected: object, label: str) -> None:
    if not _typed_equal(actual, expected):
        raise PhysicalOnboardingFoundationError(
            f"{label} differs from the reviewed zero-authority contract"
        )


def _reject_symlink_chain(path: Path, label: str) -> None:
    cursor = Path(os.path.abspath(path))
    while True:
        try:
            if os.path.lexists(cursor) and cursor.is_symlink():
                raise PhysicalOnboardingFoundationError(f"{label} contains a symlink")
        except OSError as exc:
            raise PhysicalOnboardingFoundationError(f"{label} is unavailable") from exc
        if cursor.parent == cursor:
            return
        cursor = cursor.parent


def _workspace_root(workspace: Path) -> Path:
    if not isinstance(workspace, Path):
        raise TypeError("workspace must be pathlib.Path")
    _reject_symlink_chain(workspace, "workspace")
    try:
        root = workspace.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PhysicalOnboardingFoundationError("workspace is unavailable") from exc
    if not root.is_dir():
        raise PhysicalOnboardingFoundationError("workspace must be a directory")
    return root


def _contained_file(root: Path, requested: Path, label: str) -> Path:
    if not isinstance(requested, Path):
        raise TypeError(f"{label} path must be pathlib.Path")
    if not requested.is_absolute() and ".." in requested.parts:
        raise PhysicalOnboardingFoundationError(
            f"{label} path must not contain traversal"
        )
    candidate = requested if requested.is_absolute() else root / requested
    _reject_symlink_chain(candidate, label)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise PhysicalOnboardingFoundationError(
            f"{label} must be a file beneath the workspace"
        ) from exc
    if not resolved.is_file():
        raise PhysicalOnboardingFoundationError(f"{label} must be a regular file")
    return resolved


def _read_bounded(path: Path, *, maximum: int, label: str) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise PhysicalOnboardingFoundationError(f"could not read {label}") from exc
    if not payload or len(payload) > maximum:
        raise PhysicalOnboardingFoundationError(
            f"{label} size must be within 1..{maximum} bytes"
        )
    return payload


def _normalized_contract_path(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip() or "\\" in value:
        raise PhysicalOnboardingFoundationError(
            f"{label} must be a normalized workspace-relative POSIX path"
        )
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise PhysicalOnboardingFoundationError(
            f"{label} must be a normalized workspace-relative POSIX path"
        )
    if parsed.as_posix() != value:
        raise PhysicalOnboardingFoundationError(f"{label} is not normalized")
    return value


def _freeze(value: object) -> object:
    if type(value) is dict:
        mapping = cast(dict[str, object], value)
        return MappingProxyType({key: _freeze(item) for key, item in mapping.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in cast(list[object], value))
    return value


@dataclass(frozen=True, slots=True)
class FoundationContractBinding:
    """One verified specialized contract referenced by the foundation."""

    id: str
    path: str
    sha256: str
    resolved_path: Path


@dataclass(frozen=True, slots=True)
class PhysicalOnboardingFoundation:
    """Immutable result of aggregate source and semantic validation."""

    foundation_id: str
    source_path: Path
    source_sha256: str
    runtime_activation: bool
    contracts: tuple[FoundationContractBinding, ...]
    open_implementation_gates: tuple[str, ...]
    concurrency_and_durability: Mapping[str, object]
    evidence_and_datasets: Mapping[str, object]
    calibration_assurance: Mapping[str, object]
    commissioning_bundle: Mapping[str, object]
    threat_model: Mapping[str, object]
    authority_effect_policy: AuthorityEffectPolicy
    stage_catalog: PhysicalOnboardingStageCatalog
    configuration_epoch_policy: ConfigurationEpochPolicy
    hazard_register: PhysicalOnboardingHazardRegister
    workcell_interface_contract: WorkcellInterfaceContract
    accuracy_budget_policy: TargetAccuracyBudgetPolicy

    @property
    def contracts_by_id(self) -> Mapping[str, FoundationContractBinding]:
        return MappingProxyType({binding.id: binding for binding in self.contracts})

    @property
    def zero_physical_authority(self) -> bool:
        return (
            self.runtime_activation is False
            and self.authority_effect_policy.authority.is_zero_authority
            and self.stage_catalog.zero_physical_authority
            and self.configuration_epoch_policy.zero_physical_authority
            and self.hazard_register.zero_physical_authority
            and self.workcell_interface_contract.zero_physical_authority
            and self.accuracy_budget_policy.zero_physical_authority
        )


_SPECIALIZED_ERRORS = (
    AuthorityEffectPolicyError,
    PhysicalOnboardingStageCatalogError,
    ConfigurationEpochPolicyError,
    PhysicalOnboardingHazardError,
    WorkcellInterfaceContractError,
    AccuracyBudgetPolicyError,
)


def _load_specialized_contracts(
    root: Path,
    bindings: Mapping[str, FoundationContractBinding],
) -> tuple[
    AuthorityEffectPolicy,
    PhysicalOnboardingStageCatalog,
    ConfigurationEpochPolicy,
    PhysicalOnboardingHazardRegister,
    WorkcellInterfaceContract,
    TargetAccuracyBudgetPolicy,
]:
    try:
        authority = load_authority_effect_policy(
            root, bindings["ROCELL-AUTHORITY-EFFECT-001"].resolved_path
        )
        stages = load_physical_onboarding_stage_catalog(
            root,
            bindings["ROCELL-PHYSICAL-ONBOARDING-STAGES-001"].resolved_path,
        )
        epochs = load_configuration_epoch_policy(
            root, bindings["ROCELL-CONFIGURATION-EPOCHS-001"].resolved_path
        )
        hazards = load_physical_onboarding_hazards(
            root,
            bindings["ROCELL-PHYSICAL-ONBOARDING-HAZARDS-001"].resolved_path,
        )
        interface_binding = next(
            binding
            for contract_id, binding in bindings.items()
            if contract_id in {
                "ROCELL-WORKCELL-ICD-001",
                "ROCELL-WORKCELL-ICD-TRIPOD-003",
            }
        )
        interface = load_workcell_interface_contract(root, interface_binding.resolved_path)
        accuracy = load_target_accuracy_budget_policy(
            root,
            bindings["ROCELL-TARGET-ACCURACY-BUDGET-001"].resolved_path,
        )
    except _SPECIALIZED_ERRORS as exc:
        raise PhysicalOnboardingFoundationError(
            f"referenced specialized contract failed validation: {exc}"
        ) from exc
    return authority, stages, epochs, hazards, interface, accuracy


def _validate_specialized_hashes(
    root: Path,
    bindings: Mapping[str, FoundationContractBinding],
    authority: AuthorityEffectPolicy,
    stages: PhysicalOnboardingStageCatalog,
    epochs: ConfigurationEpochPolicy,
    hazards: PhysicalOnboardingHazardRegister,
    interface: WorkcellInterfaceContract,
    accuracy: TargetAccuracyBudgetPolicy,
) -> None:
    observed = {
        "ROCELL-AUTHORITY-EFFECT-001": (
            authority.policy_id,
            authority.source_sha256,
        ),
        "ROCELL-PHYSICAL-ONBOARDING-STAGES-001": (
            stages.catalog_id,
            stages.source_sha256,
        ),
        "ROCELL-CONFIGURATION-EPOCHS-001": (
            epochs.policy_id,
            epochs.source_sha256,
        ),
        "ROCELL-PHYSICAL-ONBOARDING-HAZARDS-001": (
            hazards.register_id,
            hazards.source_sha256,
        ),
        interface.contract_id: (
            interface.contract_id,
            interface.content_sha256,
        ),
        "ROCELL-TARGET-ACCURACY-BUDGET-001": (
            accuracy.policy_id,
            accuracy.source_sha256,
        ),
    }
    for contract_id, binding in bindings.items():
        observed_id, observed_sha256 = observed[contract_id]
        if observed_id != contract_id or observed_sha256 != binding.sha256:
            raise PhysicalOnboardingFoundationError(
                f"specialized loader identity mismatch for {contract_id}"
            )
        payload = _read_bounded(
            _contained_file(
                root,
                Path(binding.path),
                f"contract {contract_id}",
            ),
            maximum=MAX_REFERENCED_CONTRACT_BYTES,
            label=f"contract {contract_id}",
        )
        if hashlib.sha256(payload).hexdigest() != binding.sha256:
            raise PhysicalOnboardingFoundationError(
                f"contract {contract_id} changed while the foundation was loading"
            )


def _validate_commissioning_bundle_producers(
    stages: PhysicalOnboardingStageCatalog,
    commissioning_bundle: Mapping[str, Any],
) -> None:
    """Require a single stage producer for every candidate-bundle component."""

    raw_required = commissioning_bundle.get("required_components")
    if type(raw_required) is not list:
        raise PhysicalOnboardingFoundationError(
            "commissioning bundle required_components must be an array"
        )
    required = tuple(raw_required)
    produced = stages.produced_bundle_components
    if (
        len(required) != 39
        or len(required) != len(set(required))
        or len(produced) != 39
        or len(produced) != len(set(produced))
        or produced != required
    ):
        raise PhysicalOnboardingFoundationError(
            "commissioning bundle components must have exactly one stage producer"
        )


def _foundation_native_mode(
    evidence_and_datasets: Mapping[str, Any],
) -> tuple[int, int, float, str]:
    """Validate and return the aggregate's derived packed B0477 native mode."""

    width = evidence_and_datasets.get("native_frame_width_px")
    height = evidence_and_datasets.get("native_frame_height_px")
    pixel_format = evidence_and_datasets.get("native_pixel_format")
    pixel_count = evidence_and_datasets.get("native_pixel_count")
    minimum_frame_bytes = evidence_and_datasets.get("minimum_packed_native_frame_bytes")
    thirty_two_frame_bytes = evidence_and_datasets.get(
        "thirty_two_minimum_native_frames_bytes"
    )
    if (
        type(width) is not int
        or type(height) is not int
        or width <= 0
        or height <= 0
        or type(pixel_format) is not str
        or type(pixel_count) is not int
        or type(minimum_frame_bytes) is not int
        or type(thirty_two_frame_bytes) is not int
    ):
        raise PhysicalOnboardingFoundationError(
            "B0477 native evidence values must have exact positive integer/text types"
        )
    if width * 2 != height * 3 or evidence_and_datasets.get("native_aspect") != "3:2":
        raise PhysicalOnboardingFoundationError(
            "B0477 native evidence must retain its exact 3:2 aspect"
        )
    derived_pixel_count = width * height
    derived_minimum_frame_bytes = derived_pixel_count * 2
    if (
        pixel_count != derived_pixel_count
        or minimum_frame_bytes != derived_minimum_frame_bytes
        or thirty_two_frame_bytes != derived_minimum_frame_bytes * 32
    ):
        raise PhysicalOnboardingFoundationError(
            "B0477 pixel and packed YUY2 byte counts must be derived from its native dimensions"
        )
    if pixel_format != _B0477_NATIVE_PIXEL_FORMAT:
        raise PhysicalOnboardingFoundationError(
            "B0477 native evidence must use packed YUY2"
        )
    return width, height, _B0477_NATIVE_MAXIMUM_FPS, pixel_format


def _bound_payload(
    root: Path,
    binding: WorkcellSourceBinding,
    *,
    label: str,
) -> bytes:
    """Re-read one ICD-bound source and reject load-time source replacement."""

    resolved = _contained_file(root, binding.resolved_path, label)
    payload = _read_bounded(
        resolved,
        maximum=MAX_REFERENCED_CONTRACT_BYTES,
        label=label,
    )
    if hashlib.sha256(payload).hexdigest() != binding.sha256:
        raise PhysicalOnboardingFoundationError(
            f"{label} changed after workcell ICD validation"
        )
    return payload


def _physical_policy_native_mode(
    root: Path,
    binding: WorkcellSourceBinding,
) -> tuple[int, int, float, str]:
    """Read the camera tuple only after the complete policy validates strictly."""

    policy = load_physical_onboarding_policy(root, binding.resolved_path)
    if policy.policy_file_sha256 != binding.sha256:
        raise PhysicalOnboardingFoundationError(
            "workcell ICD and physical onboarding policy bytes differ"
        )
    payload = _bound_payload(
        root,
        binding,
        label="ICD-bound physical onboarding policy",
    )
    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_int=_parse_integer,
            parse_constant=_reject_constant,
        )
    except PhysicalOnboardingFoundationError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise PhysicalOnboardingFoundationError(
            "ICD-bound physical onboarding policy must remain strict UTF-8 JSON"
        ) from exc
    policy_document = _mapping(parsed, "ICD-bound physical onboarding policy")
    camera = _mapping(
        policy_document.get("camera_contract"),
        "ICD-bound physical onboarding policy camera_contract",
    )
    width = camera.get("width_px")
    height = camera.get("height_px")
    maximum_fps = camera.get("maximum_fps")
    pixel_format = camera.get("pixel_format")
    if (
        type(width) is not int
        or type(height) is not int
        or type(maximum_fps) is not int
        or type(pixel_format) is not str
    ):
        raise PhysicalOnboardingFoundationError(
            "physical onboarding policy has an invalid B0477 native mode"
        )
    return width, height, float(maximum_fps), pixel_format


def _validate_icd_bound_b0477_mode(
    root: Path,
    interface: WorkcellInterfaceContract,
    foundation_mode: tuple[int, int, float, str],
) -> None:
    """Cross-check all ICD-bound zero-authority descriptions of the camera mode."""

    try:
        profile_binding = interface.source_bindings["b0477_camera_profile"]
        policy_binding = interface.source_bindings["physical_onboarding_policy"]
    except KeyError as exc:
        raise PhysicalOnboardingFoundationError(
            "workcell ICD is missing a required B0477 source binding"
        ) from exc

    try:
        profile = load_camera_profile(profile_binding.resolved_path)
        policy_mode = _physical_policy_native_mode(root, policy_binding)
    except (
        CameraProfileError,
        PhysicalOnboardingPolicyError,
    ) as exc:
        raise PhysicalOnboardingFoundationError(
            f"ICD-bound B0477 source failed strict validation: {exc}"
        ) from exc

    if profile.source_file_sha256 != profile_binding.sha256:
        raise PhysicalOnboardingFoundationError(
            "workcell ICD and purchased B0477 profile bytes differ"
        )
    _bound_payload(
        root,
        profile_binding,
        label="ICD-bound purchased B0477 profile",
    )
    support_mode: tuple[int, int, float, str] | None = None
    if "static_camera_support_design" in interface.source_bindings:
        support_binding = interface.source_bindings["static_camera_support_design"]
        try:
            support = load_static_camera_support_design(root, support_binding.resolved_path)
        except StaticCameraSupportError as exc:
            raise PhysicalOnboardingFoundationError(
                f"ICD-bound B0477 source failed strict validation: {exc}"
            ) from exc
        if support.content_sha256 != support_binding.sha256:
            raise PhysicalOnboardingFoundationError(
                "workcell ICD and static camera support bytes differ"
            )
        if support.source_sha256.get("purchased_camera_profile") != profile_binding.sha256:
            raise PhysicalOnboardingFoundationError(
                "static support and workcell ICD bind different B0477 profile bytes"
            )
        _bound_payload(root, support_binding, label="ICD-bound static camera support")
        support_mode = support.native_mode
    else:
        candidate_binding = interface.source_bindings.get("commercial_tripod_candidate")
        if candidate_binding is None:
            raise PhysicalOnboardingFoundationError(
                "workcell ICD is missing a static camera support candidate"
            )
        _bound_payload(
            root,
            candidate_binding,
            label="ICD-bound commercial tripod candidate",
        )

    width, height, maximum_fps, pixel_format = foundation_mode
    profile_mode = profile.published_mode(_B0477_NATIVE_HOST_BUS, width, height)
    if profile_mode is None:
        raise PhysicalOnboardingFoundationError(
            "purchased B0477 profile does not publish the foundation native mode"
        )
    published_mode = (
        profile_mode.width_px,
        profile_mode.height_px,
        profile_mode.maximum_fps,
        profile_mode.pixel_format,
    )
    if (
        foundation_mode != published_mode
        or (support_mode is not None and foundation_mode != support_mode)
        or foundation_mode != policy_mode
    ):
        raise PhysicalOnboardingFoundationError(
            "foundation, purchased profile, support, and onboarding policy B0477 modes differ"
        )


def _validate_cross_links(
    root: Path,
    evidence_and_datasets: Mapping[str, Any],
    commissioning_bundle: Mapping[str, Any],
    authority: AuthorityEffectPolicy,
    stages: PhysicalOnboardingStageCatalog,
    epochs: ConfigurationEpochPolicy,
    hazards: PhysicalOnboardingHazardRegister,
    interface: WorkcellInterfaceContract,
    accuracy: TargetAccuracyBudgetPolicy,
    bindings: Mapping[str, FoundationContractBinding],
) -> None:
    if not (
        authority.authority.is_zero_authority
        and stages.zero_physical_authority
        and epochs.zero_physical_authority
        and hazards.zero_physical_authority
        and interface.zero_physical_authority
        and accuracy.zero_physical_authority
    ):
        raise PhysicalOnboardingFoundationError(
            "a specialized contract exceeds zero physical authority"
        )

    _validate_commissioning_bundle_producers(stages, commissioning_bundle)
    foundation_mode = _foundation_native_mode(evidence_and_datasets)
    _validate_icd_bound_b0477_mode(root, interface, foundation_mode)

    effect_classes = {rule.effect_class for rule in authority.effect_classes}
    if any(
        required not in effect_classes
        for stage in stages.stages
        for required in stage.required_effect_classes
    ):
        raise PhysicalOnboardingFoundationError(
            "stage catalog references an undefined effect class"
        )

    stage_ids = {stage.stage for stage in stages.stages}
    banner_ids = {
        hazard_id for stage in stages.stages for hazard_id in stage.hazard_banner_ids
    }
    if banner_ids != set(hazards.by_id):
        raise PhysicalOnboardingFoundationError(
            "stage hazard banners do not cover the complete hazard register"
        )
    if any(
        evidence_stage not in stage_ids
        for hazard in hazards.hazards
        for evidence_stage in hazard.evidence_stages
    ):
        raise PhysicalOnboardingFoundationError(
            "hazard register references an undefined stage"
        )

    epoch_ids = set(epochs.by_id)
    hazard_epoch_ids = {
        epoch.value
        for hazard in hazards.hazards
        for epoch in hazard.invalidation_epochs
    }
    if hazard_epoch_ids != epoch_ids:
        raise PhysicalOnboardingFoundationError(
            "hazard invalidation references do not cover the epoch policy"
        )

    if any(term.owner_stage not in stage_ids for term in accuracy.terms):
        raise PhysicalOnboardingFoundationError(
            "accuracy policy references an undefined owner stage"
        )

    try:
        icd_epoch = interface.source_bindings["configuration_epoch_policy"]
    except KeyError as exc:
        raise PhysicalOnboardingFoundationError(
            "workcell ICD does not bind the configuration epoch policy"
        ) from exc
    epoch_binding = bindings["ROCELL-CONFIGURATION-EPOCHS-001"]
    if (
        icd_epoch.relative_path != epoch_binding.path
        or icd_epoch.sha256 != epoch_binding.sha256
    ):
        raise PhysicalOnboardingFoundationError(
            "workcell ICD and foundation bind different epoch policy bytes"
        )


def load_physical_onboarding_foundation(
    workspace: Path,
    foundation_path: Path | None = None,
) -> PhysicalOnboardingFoundation:
    """Load the source-bound foundation without device I/O or runtime activation."""

    root = _workspace_root(workspace)
    requested = (
        DEFAULT_PHYSICAL_ONBOARDING_FOUNDATION
        if foundation_path is None
        else foundation_path
    )
    selected = _contained_file(root, requested, "physical onboarding foundation")
    payload = _read_bounded(
        selected,
        maximum=MAX_PHYSICAL_ONBOARDING_FOUNDATION_BYTES,
        label="physical onboarding foundation",
    )
    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_int=_parse_integer,
            parse_constant=_reject_constant,
        )
    except PhysicalOnboardingFoundationError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise PhysicalOnboardingFoundationError(
            "physical onboarding foundation must be strict UTF-8 JSON"
        ) from exc
    document = _mapping(parsed, "physical onboarding foundation")
    _exact_fields(document, _ROOT_FIELDS, "physical onboarding foundation")
    identity = (document["schema"], document["foundation_id"])
    if identity == (PHYSICAL_ONBOARDING_FOUNDATION_SCHEMA_V1, PHYSICAL_ONBOARDING_FOUNDATION_ID_V1):
        expected_contracts = _EXPECTED_CONTRACTS_V1
        expected_revision = 1
        expected_revision_date = "2026-09-06"
        expected_status = "FOUNDATION_IMPLEMENTED_RUNTIME_MIGRATION_PENDING_ZERO_AUTHORITY"
        foundation_id = PHYSICAL_ONBOARDING_FOUNDATION_ID_V1
    elif identity == (PHYSICAL_ONBOARDING_FOUNDATION_SCHEMA, PHYSICAL_ONBOARDING_FOUNDATION_ID):
        expected_contracts = _EXPECTED_CONTRACTS
        expected_revision = 2
        expected_revision_date = "2026-10-11"
        expected_status = "TRIPOD_CONTRACT_MIGRATED_ZERO_AUTHORITY"
        foundation_id = PHYSICAL_ONBOARDING_FOUNDATION_ID
    else:
        raise PhysicalOnboardingFoundationError("unsupported physical onboarding foundation schema")
    _require_exact(document["revision"], expected_revision, "revision")
    _require_exact(document["revision_date"], expected_revision_date, "revision_date")
    _require_exact(document["status"], expected_status, "status")
    _require_exact(document["runtime_activation"], False, "runtime_activation")
    _require_exact(document["authority"], _EXPECTED_AUTHORITY, "authority")
    _require_exact(
        document["concurrency_and_durability"],
        _EXPECTED_CONCURRENCY,
        "concurrency_and_durability",
    )
    _require_exact(
        document["evidence_and_datasets"],
        _EXPECTED_EVIDENCE,
        "evidence_and_datasets",
    )
    _require_exact(
        document["calibration_assurance"],
        _EXPECTED_CALIBRATION,
        "calibration_assurance",
    )
    _require_exact(
        document["commissioning_bundle"],
        _EXPECTED_COMMISSIONING_BUNDLE,
        "commissioning_bundle",
    )
    _require_exact(document["threat_model"], _EXPECTED_THREAT_MODEL, "threat_model")

    raw_gates = document["open_implementation_gates"]
    if type(raw_gates) is not list:
        raise PhysicalOnboardingFoundationError(
            "open_implementation_gates must be an array"
        )
    gates = tuple(raw_gates)
    if (
        gates != _EXPECTED_OPEN_GATES
        or len(gates) != len(set(gates))
        or any(type(gate) is not str or _GATE.fullmatch(gate) is None for gate in gates)
    ):
        raise PhysicalOnboardingFoundationError(
            "open implementation gates differ from the reviewed blocking set"
        )

    raw_contracts = document["contracts"]
    if type(raw_contracts) is not list or len(raw_contracts) != len(
        expected_contracts
    ):
        raise PhysicalOnboardingFoundationError(
            "contracts must contain the complete bounded contract set"
        )
    bindings: list[FoundationContractBinding] = []
    for index, raw_contract in enumerate(raw_contracts):
        entry = _mapping(raw_contract, f"contracts[{index}]")
        _exact_fields(entry, frozenset({"id", "path", "sha256"}), f"contracts[{index}]")
        expected_id, expected_path = expected_contracts[index]
        _require_exact(entry["id"], expected_id, f"contracts[{index}].id")
        path = _normalized_contract_path(entry["path"], f"contracts[{index}].path")
        _require_exact(path, expected_path, f"contracts[{index}].path")
        digest = entry["sha256"]
        if type(digest) is not str or _SHA256.fullmatch(digest) is None:
            raise PhysicalOnboardingFoundationError(
                f"contracts[{index}].sha256 must be a lowercase SHA-256 digest"
            )
        resolved = _contained_file(root, Path(path), f"contract {expected_id}")
        contract_payload = _read_bounded(
            resolved,
            maximum=MAX_REFERENCED_CONTRACT_BYTES,
            label=f"contract {expected_id}",
        )
        if hashlib.sha256(contract_payload).hexdigest() != digest:
            raise PhysicalOnboardingFoundationError(
                f"contract source SHA-256 mismatch for {expected_id}"
            )
        bindings.append(
            FoundationContractBinding(
                id=expected_id,
                path=path,
                sha256=digest,
                resolved_path=resolved,
            )
        )
    if (
        len({binding.id for binding in bindings}) != len(bindings)
        or len({binding.path for binding in bindings}) != len(bindings)
        or len({binding.resolved_path for binding in bindings}) != len(bindings)
    ):
        raise PhysicalOnboardingFoundationError(
            "foundation contract IDs and paths must be unique"
        )
    by_id: Mapping[str, FoundationContractBinding] = MappingProxyType(
        {binding.id: binding for binding in bindings}
    )

    authority, stages, epochs, hazards, interface, accuracy = (
        _load_specialized_contracts(root, by_id)
    )
    _validate_specialized_hashes(
        root, by_id, authority, stages, epochs, hazards, interface, accuracy
    )
    _validate_cross_links(
        root,
        _mapping(document["evidence_and_datasets"], "evidence_and_datasets"),
        _mapping(document["commissioning_bundle"], "commissioning_bundle"),
        authority,
        stages,
        epochs,
        hazards,
        interface,
        accuracy,
        by_id,
    )

    concurrency = _freeze(document["concurrency_and_durability"])
    evidence = _freeze(document["evidence_and_datasets"])
    calibration = _freeze(document["calibration_assurance"])
    bundle = _freeze(document["commissioning_bundle"])
    threat_model = _freeze(document["threat_model"])
    assert isinstance(concurrency, Mapping)
    assert isinstance(evidence, Mapping)
    assert isinstance(calibration, Mapping)
    assert isinstance(bundle, Mapping)
    assert isinstance(threat_model, Mapping)
    result = PhysicalOnboardingFoundation(
        foundation_id=foundation_id,
        source_path=selected,
        source_sha256=hashlib.sha256(payload).hexdigest(),
        runtime_activation=False,
        contracts=tuple(bindings),
        open_implementation_gates=gates,
        concurrency_and_durability=concurrency,
        evidence_and_datasets=evidence,
        calibration_assurance=calibration,
        commissioning_bundle=bundle,
        threat_model=threat_model,
        authority_effect_policy=authority,
        stage_catalog=stages,
        configuration_epoch_policy=epochs,
        hazard_register=hazards,
        workcell_interface_contract=interface,
        accuracy_budget_policy=accuracy,
    )
    if not result.zero_physical_authority:
        raise PhysicalOnboardingFoundationError(
            "foundation aggregate exceeds zero physical authority"
        )
    return result


__all__ = [
    "DEFAULT_PHYSICAL_ONBOARDING_FOUNDATION",
    "MAX_PHYSICAL_ONBOARDING_FOUNDATION_BYTES",
    "MAX_REFERENCED_CONTRACT_BYTES",
    "PHYSICAL_ONBOARDING_FOUNDATION_ID",
    "PHYSICAL_ONBOARDING_FOUNDATION_ID_V1",
    "PHYSICAL_ONBOARDING_FOUNDATION_SCHEMA",
    "PHYSICAL_ONBOARDING_FOUNDATION_SCHEMA_V1",
    "FoundationContractBinding",
    "PhysicalOnboardingFoundation",
    "PhysicalOnboardingFoundationError",
    "load_physical_onboarding_foundation",
]
