"""Conservative target-accuracy budget primitives and strict design policy.

The evaluator is intentionally useful before hardware: tests and synthetic
studies can exercise the same missing/stale/out-of-domain behavior that later
measurements will use.  A mathematical fit is still diagnostic because the
checked-in policy is not runtime-active and grants no motion or contact
authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from rocell.application.physical_onboarding import PhysicalOnboardingStage


TARGET_ACCURACY_BUDGET_POLICY_SCHEMA = "rocell.target_accuracy_budget_policy.v3"
DEFAULT_TARGET_ACCURACY_BUDGET_POLICY = Path(
    "software/config/accuracy_budget_policy.json"
)
MAX_TARGET_ACCURACY_BUDGET_POLICY_BYTES = 256 * 1024

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_EXPECTED_TERM_IDS = (
    "board_pose",
    "intrinsics_and_distortion",
    "camera_board_registration",
    "static_support_drift",
    "arm_board",
    "controller_correlation",
    "free_tcp",
    "device_pose",
    "motion_repeatability",
    "timing_and_settling",
)
_EXPECTED_CONTACT_TERMS = (
    "contact_tip_footprint",
    "loaded_tool_compliance",
    "descent_depth_and_surface_height",
    "device_actuation_variability",
    "contact_outcome_observation",
)
_EXPECTED_OPEN_BLOCKERS = (
    "NO_PHYSICAL_TERM_MEASUREMENTS",
    "PASSIVE_STYLUS_GEOMETRY_NOT_SELECTED",
    "KEYBOARD_SAFE_REGIONS_NOT_MEASURED",
    "PHONE_UI_SAFE_REGIONS_NOT_MEASURED",
    "CONTACT_ADDENDUM_NOT_QUALIFIED",
)
_REQUIRED_METADATA = (
    "frame",
    "operating_domain",
    "sample_basis",
    "bound_method",
    "coverage",
    "dependency_hashes",
)
_EXPECTED_TERM_OWNERS = (
    ("board_pose", PhysicalOnboardingStage.STATIC_REGISTRATION),
    ("intrinsics_and_distortion", PhysicalOnboardingStage.STATIC_REGISTRATION),
    ("camera_board_registration", PhysicalOnboardingStage.STATIC_REGISTRATION),
    ("static_support_drift", PhysicalOnboardingStage.STATIC_REGISTRATION),
    ("arm_board", PhysicalOnboardingStage.REFERENCE_FRAME_CALIBRATION),
    ("controller_correlation", PhysicalOnboardingStage.REFERENCE_FRAME_CALIBRATION),
    ("free_tcp", PhysicalOnboardingStage.REFERENCE_FRAME_CALIBRATION),
    ("device_pose", PhysicalOnboardingStage.REFERENCE_FRAME_CALIBRATION),
    ("motion_repeatability", PhysicalOnboardingStage.NONCONTACT_ACCEPTANCE),
    ("timing_and_settling", PhysicalOnboardingStage.NONCONTACT_ACCEPTANCE),
)

_ASSESSMENT_CLOCK_DEPENDENCY_ID = "assessment_clock"
_CONFIGURATION_EPOCH_DEPENDENCY_ID = "configuration_epoch"
_TARGET_GEOMETRY_DEPENDENCY_ID = "target_geometry_bundle"
_TERM_EVIDENCE_DEPENDENCY_ID = "term_evidence"


class AccuracyBudgetPolicyError(ValueError):
    """The target-accuracy policy or an assessment request is unsafe."""


class AccuracyEvidenceState(str, Enum):
    """Whether a conservative term is usable in its requested domain."""

    MEASURED_IN_DOMAIN = "MEASURED_IN_DOMAIN"
    UNMEASURED = "UNMEASURED"
    STALE = "STALE"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"


class AccuracyBudgetDisposition(str, Enum):
    """A diagnostic result; no value in this enum carries physical authority."""

    BLOCKED_UNBOUNDED = "BLOCKED_UNBOUNDED"
    BLOCKED_TARGET_MARGIN = "BLOCKED_TARGET_MARGIN"
    DIAGNOSTIC_FITS_ZERO_AUTHORITY = "DIAGNOSTIC_FITS_ZERO_AUTHORITY"


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AccuracyBudgetPolicyError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _reject_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise AccuracyBudgetPolicyError(f"nonfinite JSON value {value!r}")
    raise AccuracyBudgetPolicyError("accuracy policy must not contain floats")


def _reject_constant(value: str) -> None:
    raise AccuracyBudgetPolicyError(f"nonfinite JSON constant {value!r}")


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise AccuracyBudgetPolicyError(f"{label} must be an object")
    return value


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise AccuracyBudgetPolicyError(
            f"{label} fields differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AccuracyBudgetPolicyError(f"{label} must be non-empty trimmed text")
    if len(value) > 256:
        raise AccuracyBudgetPolicyError(f"{label} is too long")
    return value


def _identifier(value: object, label: str) -> str:
    result = _text(value, label)
    if _IDENTIFIER.fullmatch(result) is None:
        raise AccuracyBudgetPolicyError(f"{label} is not a valid identifier")
    return result


def _unique_identifiers(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise AccuracyBudgetPolicyError(f"{label} must be a non-empty list")
    result = tuple(_identifier(item, f"{label} item") for item in value)
    if len(result) != len(set(result)):
        raise AccuracyBudgetPolicyError(f"{label} contains duplicates")
    return result


def _unix_nanoseconds(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise AccuracyBudgetPolicyError(
            f"{label} must be a non-negative integer Unix timestamp in nanoseconds"
        )
    return value


def _sha256_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise AccuracyBudgetPolicyError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _canonical_sha256(value: object) -> str:
    """Hash a bounded evidence description with one cross-platform encoding."""

    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AccuracyBudgetPolicyError(
            "accuracy assessment input manifest is not canonical JSON"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _resolve_policy(workspace: Path, selected: Path) -> Path:
    root = Path(os.path.abspath(workspace))
    candidate = selected if selected.is_absolute() else root / selected
    for label, path in (("workspace", root), ("accuracy policy", candidate)):
        cursor = path
        while True:
            if os.path.lexists(cursor) and cursor.is_symlink():
                raise AccuracyBudgetPolicyError(f"{label} contains a symlink")
            if cursor.parent == cursor:
                break
            cursor = cursor.parent
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise AccuracyBudgetPolicyError(
            "accuracy policy must be a file beneath the workspace"
        ) from exc
    if not resolved.is_file():
        raise AccuracyBudgetPolicyError("accuracy policy must be a regular file")
    return resolved


@dataclass(frozen=True, slots=True)
class AccuracyBudgetTermDefinition:
    term_id: str
    owner_stage: PhysicalOnboardingStage
    required_metadata: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.term_id, "term_id")
        if not isinstance(self.owner_stage, PhysicalOnboardingStage):
            raise AccuracyBudgetPolicyError("term owner_stage is invalid")
        if type(self.required_metadata) is not tuple:
            raise AccuracyBudgetPolicyError(
                "term required_metadata must be an immutable tuple"
            )
        if self.required_metadata != _REQUIRED_METADATA:
            raise AccuracyBudgetPolicyError("accuracy term metadata contract changed")


@dataclass(frozen=True, slots=True)
class TargetAccuracyBudgetPolicy:
    source_path: Path
    source_sha256: str
    policy_id: str
    terms: tuple[AccuracyBudgetTermDefinition, ...]
    contact_addendum_terms: tuple[str, ...]
    open_blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_target_accuracy_budget_policy(self)

    @property
    def zero_physical_authority(self) -> bool:
        return True


def _validate_target_accuracy_budget_policy(
    policy: TargetAccuracyBudgetPolicy,
) -> None:
    """Revalidate even frozen policies at every assessment boundary.

    This closes the empty/subset-policy shortcut and also detects a policy that
    was altered through low-level Python mutation after construction. Trust in
    the source bytes remains an external commissioning concern; this type only
    enforces the complete diagnostic arithmetic contract.
    """

    if not isinstance(policy.source_path, Path) or not policy.source_path.is_absolute():
        raise AccuracyBudgetPolicyError("policy source_path must be an absolute Path")
    _sha256_digest(policy.source_sha256, "policy source_sha256")
    if policy.policy_id != "ROCELL-TARGET-ACCURACY-BUDGET-001":
        raise AccuracyBudgetPolicyError("unexpected accuracy policy ID")
    if type(policy.terms) is not tuple:
        raise AccuracyBudgetPolicyError("policy terms must be an immutable tuple")
    if any(not isinstance(term, AccuracyBudgetTermDefinition) for term in policy.terms):
        raise AccuracyBudgetPolicyError("policy terms contain an invalid item")
    actual_contract = tuple(
        (term.term_id, term.owner_stage, term.required_metadata)
        for term in policy.terms
    )
    expected_contract = tuple(
        (term_id, owner, _REQUIRED_METADATA) for term_id, owner in _EXPECTED_TERM_OWNERS
    )
    if actual_contract != expected_contract:
        raise AccuracyBudgetPolicyError(
            "accuracy policy term order, ownership, or metadata changed"
        )
    if type(policy.contact_addendum_terms) is not tuple or (
        policy.contact_addendum_terms != _EXPECTED_CONTACT_TERMS
    ):
        raise AccuracyBudgetPolicyError("contact addendum term contract changed")
    if type(policy.open_blockers) is not tuple or (
        policy.open_blockers != _EXPECTED_OPEN_BLOCKERS
    ):
        raise AccuracyBudgetPolicyError("accuracy policy open blockers changed")


@dataclass(frozen=True, slots=True)
class AccuracyDependencyHash:
    """A named immutable source digest used by an accuracy observation."""

    dependency_id: str
    sha256: str

    def __post_init__(self) -> None:
        _identifier(self.dependency_id, "dependency_id")
        _sha256_digest(self.sha256, "dependency sha256")


def _validate_dependency_hashes(
    value: object,
    label: str,
) -> tuple[AccuracyDependencyHash, ...]:
    if type(value) is not tuple or not value:
        raise AccuracyBudgetPolicyError(f"{label} must be a non-empty immutable tuple")
    if any(not isinstance(item, AccuracyDependencyHash) for item in value):
        raise AccuracyBudgetPolicyError(
            f"{label} must contain only AccuracyDependencyHash values"
        )
    result = tuple(value)
    dependency_ids = tuple(item.dependency_id for item in result)
    if len(dependency_ids) != len(set(dependency_ids)):
        raise AccuracyBudgetPolicyError(f"{label} contains duplicate dependency IDs")
    if dependency_ids != tuple(sorted(dependency_ids)):
        raise AccuracyBudgetPolicyError(f"{label} must be ordered by dependency_id")
    return result


def _dependency_digest(
    dependencies: tuple[AccuracyDependencyHash, ...],
    dependency_id: str,
    *,
    label: str,
) -> str:
    for dependency in dependencies:
        if dependency.dependency_id == dependency_id:
            return dependency.sha256
    raise AccuracyBudgetPolicyError(
        f"{label} must bind the {dependency_id!r} dependency"
    )


@dataclass(frozen=True, slots=True)
class AccuracyAssessmentContext:
    """Explicit assessment clock and configuration-epoch evidence.

    The digests make the inputs internally source-bound. Whether those sources
    are trusted enough for a future physical promotion is deliberately outside
    this zero-authority arithmetic module.
    """

    as_of_unix_ns: int
    operating_domain: str
    configuration_epoch_id: str
    configuration_epoch_sha256: str
    clock_evidence_sha256: str
    dependency_hashes: tuple[AccuracyDependencyHash, ...]

    def __post_init__(self) -> None:
        _unix_nanoseconds(self.as_of_unix_ns, "as_of_unix_ns")
        _text(self.operating_domain, "operating_domain")
        _identifier(self.configuration_epoch_id, "configuration_epoch_id")
        epoch_digest = _sha256_digest(
            self.configuration_epoch_sha256,
            "configuration_epoch_sha256",
        )
        clock_digest = _sha256_digest(
            self.clock_evidence_sha256,
            "clock_evidence_sha256",
        )
        dependencies = _validate_dependency_hashes(
            self.dependency_hashes,
            "assessment context dependency_hashes",
        )
        if (
            _dependency_digest(
                dependencies,
                _ASSESSMENT_CLOCK_DEPENDENCY_ID,
                label="assessment context",
            )
            != clock_digest
        ):
            raise AccuracyBudgetPolicyError(
                "assessment clock digest does not match its named dependency"
            )
        if (
            _dependency_digest(
                dependencies,
                _CONFIGURATION_EPOCH_DEPENDENCY_ID,
                label="assessment context",
            )
            != epoch_digest
        ):
            raise AccuracyBudgetPolicyError(
                "configuration epoch digest does not match its named dependency"
            )


@dataclass(frozen=True, slots=True)
class TargetGeometryEvidence:
    """Source-bound conservative radial certificate for target/tool geometry.

    The target radius is the certified inradius about the planned target point,
    and the tool radius is a certified circumradius around the complete passive
    footprint. Their scalar difference is therefore a conservative substitute
    for direct polygon erosion, not an assertion that either article is round.
    """

    target_id: str
    frame: str
    operating_domain: str
    configuration_epoch_id: str
    configuration_epoch_sha256: str
    target_safe_radius_basis: str
    tool_tip_radius_basis: str
    target_safe_radius_micrometers: int
    tool_tip_radius_micrometers: int
    guard_micrometers: int
    evidence_sha256: str
    dependency_hashes: tuple[AccuracyDependencyHash, ...]
    observed_at_unix_ns: int
    valid_until_unix_ns: int

    def __post_init__(self) -> None:
        _identifier(self.target_id, "target_id")
        _text(self.frame, "frame")
        _text(self.operating_domain, "operating_domain")
        _identifier(self.configuration_epoch_id, "configuration_epoch_id")
        epoch_digest = _sha256_digest(
            self.configuration_epoch_sha256,
            "configuration_epoch_sha256",
        )
        evidence_digest = _sha256_digest(
            self.evidence_sha256,
            "target geometry evidence_sha256",
        )
        if (
            self.target_safe_radius_basis
            != "CERTIFIED_TARGET_CENTERED_SAFE_POLYGON_INRADIUS"
            or self.tool_tip_radius_basis != "CERTIFIED_TOOL_FOOTPRINT_CIRCUMRADIUS"
        ):
            raise AccuracyBudgetPolicyError(
                "target/tool radius bases must be conservative geometry certificates"
            )
        for label, value in (
            ("target_safe_radius_micrometers", self.target_safe_radius_micrometers),
            ("tool_tip_radius_micrometers", self.tool_tip_radius_micrometers),
            ("guard_micrometers", self.guard_micrometers),
        ):
            if type(value) is not int or value <= 0:
                raise AccuracyBudgetPolicyError(f"{label} must be a positive integer")
        observed_at = _unix_nanoseconds(
            self.observed_at_unix_ns,
            "target geometry observed_at_unix_ns",
        )
        valid_until = _unix_nanoseconds(
            self.valid_until_unix_ns,
            "target geometry valid_until_unix_ns",
        )
        if valid_until < observed_at:
            raise AccuracyBudgetPolicyError(
                "target geometry validity cannot precede observation"
            )
        dependencies = _validate_dependency_hashes(
            self.dependency_hashes,
            "target geometry dependency_hashes",
        )
        if (
            _dependency_digest(
                dependencies,
                _CONFIGURATION_EPOCH_DEPENDENCY_ID,
                label="target geometry",
            )
            != epoch_digest
        ):
            raise AccuracyBudgetPolicyError(
                "target geometry configuration epoch digest does not match dependency"
            )
        if (
            _dependency_digest(
                dependencies,
                _TARGET_GEOMETRY_DEPENDENCY_ID,
                label="target geometry",
            )
            != evidence_digest
        ):
            raise AccuracyBudgetPolicyError(
                "target geometry evidence digest does not match dependency"
            )


@dataclass(frozen=True, slots=True)
class AccuracyEvidenceProvenance:
    """Complete provenance and validity interval for a measured bound.

    Text fields name immutable, reviewed concepts; dependency hashes bind their
    concrete artifacts.  The evaluator still requires an independently supplied
    term binding, so an observation cannot make its own provenance admissible.
    """

    frame: str
    operating_domain: str
    sample_basis: str
    bound_method: str
    coverage: str
    dependency_hashes: tuple[AccuracyDependencyHash, ...]
    observed_at_unix_ns: int
    valid_until_unix_ns: int

    def __post_init__(self) -> None:
        for field_name in (
            "frame",
            "operating_domain",
            "sample_basis",
            "bound_method",
            "coverage",
        ):
            _text(getattr(self, field_name), field_name)
        _validate_dependency_hashes(self.dependency_hashes, "dependency_hashes")
        observed_at = _unix_nanoseconds(self.observed_at_unix_ns, "observed_at_unix_ns")
        valid_until = _unix_nanoseconds(self.valid_until_unix_ns, "valid_until_unix_ns")
        if valid_until < observed_at:
            raise AccuracyBudgetPolicyError(
                "valid_until_unix_ns cannot precede observed_at_unix_ns"
            )


@dataclass(frozen=True, slots=True)
class AccuracyTermEvidenceBinding:
    """The independently selected provenance expected for one budget term."""

    term_id: str
    frame: str
    operating_domain: str
    configuration_epoch_id: str
    configuration_epoch_sha256: str
    sample_basis: str
    bound_method: str
    coverage: str
    evidence_sha256: str
    dependency_hashes: tuple[AccuracyDependencyHash, ...]

    def __post_init__(self) -> None:
        _identifier(self.term_id, "term_id")
        for field_name in (
            "frame",
            "operating_domain",
            "sample_basis",
            "bound_method",
            "coverage",
        ):
            _text(getattr(self, field_name), field_name)
        _identifier(self.configuration_epoch_id, "configuration_epoch_id")
        epoch_digest = _sha256_digest(
            self.configuration_epoch_sha256,
            "configuration_epoch_sha256",
        )
        evidence_digest = _sha256_digest(
            self.evidence_sha256,
            "term evidence_sha256",
        )
        dependencies = _validate_dependency_hashes(
            self.dependency_hashes,
            "dependency_hashes",
        )
        if (
            _dependency_digest(
                dependencies,
                _CONFIGURATION_EPOCH_DEPENDENCY_ID,
                label="term evidence binding",
            )
            != epoch_digest
        ):
            raise AccuracyBudgetPolicyError(
                "term binding configuration epoch digest does not match dependency"
            )
        if (
            _dependency_digest(
                dependencies,
                _TERM_EVIDENCE_DEPENDENCY_ID,
                label="term evidence binding",
            )
            != evidence_digest
        ):
            raise AccuracyBudgetPolicyError(
                "term evidence digest does not match its named dependency"
            )


@dataclass(frozen=True, slots=True)
class AccuracyBudgetObservation:
    """One measured conservative bound, expressed at the target plane."""

    term_id: str
    evidence_state: AccuracyEvidenceState
    bound_micrometers: int | None
    evidence_sha256: str | None
    provenance: AccuracyEvidenceProvenance | None = None

    def __post_init__(self) -> None:
        _identifier(self.term_id, "term_id")
        if not isinstance(self.evidence_state, AccuracyEvidenceState):
            raise AccuracyBudgetPolicyError("evidence_state is invalid")
        if self.evidence_state is AccuracyEvidenceState.MEASURED_IN_DOMAIN:
            if type(self.bound_micrometers) is not int or self.bound_micrometers < 0:
                raise AccuracyBudgetPolicyError(
                    "measured in-domain terms require a non-negative integer bound"
                )
            if (
                not isinstance(self.evidence_sha256, str)
                or _SHA256.fullmatch(self.evidence_sha256) is None
            ):
                raise AccuracyBudgetPolicyError(
                    "measured in-domain terms require an evidence digest"
                )
            if self.provenance is not None and not isinstance(
                self.provenance, AccuracyEvidenceProvenance
            ):
                raise AccuracyBudgetPolicyError("provenance has an invalid type")
        elif (
            self.bound_micrometers is not None
            or self.evidence_sha256 is not None
            or self.provenance is not None
        ):
            raise AccuracyBudgetPolicyError(
                "unmeasured, stale, or out-of-domain terms must remain unbounded "
                "and cannot carry admissible provenance"
            )


def _dependency_document(
    dependencies: tuple[AccuracyDependencyHash, ...],
) -> list[dict[str, str]]:
    return [
        {"dependency_id": item.dependency_id, "sha256": item.sha256}
        for item in dependencies
    ]


def _provenance_document(
    provenance: AccuracyEvidenceProvenance | None,
) -> dict[str, object] | None:
    if provenance is None:
        return None
    return {
        "frame": provenance.frame,
        "operating_domain": provenance.operating_domain,
        "sample_basis": provenance.sample_basis,
        "bound_method": provenance.bound_method,
        "coverage": provenance.coverage,
        "dependency_hashes": _dependency_document(provenance.dependency_hashes),
        "observed_at_unix_ns": provenance.observed_at_unix_ns,
        "valid_until_unix_ns": provenance.valid_until_unix_ns,
    }


def _observation_document(
    observation: AccuracyBudgetObservation | None,
) -> dict[str, object] | None:
    if observation is None:
        return None
    return {
        "term_id": observation.term_id,
        "evidence_state": observation.evidence_state.value,
        "bound_micrometers": observation.bound_micrometers,
        "evidence_sha256": observation.evidence_sha256,
        "provenance": _provenance_document(observation.provenance),
    }


def _binding_document(
    binding: AccuracyTermEvidenceBinding | None,
) -> dict[str, object] | None:
    if binding is None:
        return None
    return {
        "term_id": binding.term_id,
        "frame": binding.frame,
        "operating_domain": binding.operating_domain,
        "configuration_epoch_id": binding.configuration_epoch_id,
        "configuration_epoch_sha256": binding.configuration_epoch_sha256,
        "sample_basis": binding.sample_basis,
        "bound_method": binding.bound_method,
        "coverage": binding.coverage,
        "evidence_sha256": binding.evidence_sha256,
        "dependency_hashes": _dependency_document(binding.dependency_hashes),
    }


def _assessment_input_manifest_sha256(
    policy: TargetAccuracyBudgetPolicy,
    observed: Mapping[str, AccuracyBudgetObservation],
    bindings: Mapping[str, AccuracyTermEvidenceBinding],
    assessment_context: AccuracyAssessmentContext,
    target_geometry: TargetGeometryEvidence,
) -> str:
    """Bind every policy, term, context, and geometry input to the result."""

    document = {
        "schema": "rocell.target_accuracy_budget_input_manifest.v1",
        "policy": {
            "policy_id": policy.policy_id,
            "source_sha256": policy.source_sha256,
            "terms": [
                {
                    "term_id": term.term_id,
                    "owner_stage": term.owner_stage.value,
                    "required_metadata": list(term.required_metadata),
                    "observation": _observation_document(observed.get(term.term_id)),
                    "binding": _binding_document(bindings.get(term.term_id)),
                }
                for term in policy.terms
            ],
        },
        "assessment_context": {
            "as_of_unix_ns": assessment_context.as_of_unix_ns,
            "operating_domain": assessment_context.operating_domain,
            "configuration_epoch_id": assessment_context.configuration_epoch_id,
            "configuration_epoch_sha256": (
                assessment_context.configuration_epoch_sha256
            ),
            "clock_evidence_sha256": assessment_context.clock_evidence_sha256,
            "dependency_hashes": _dependency_document(
                assessment_context.dependency_hashes
            ),
        },
        "target_geometry": {
            "target_id": target_geometry.target_id,
            "frame": target_geometry.frame,
            "operating_domain": target_geometry.operating_domain,
            "configuration_epoch_id": target_geometry.configuration_epoch_id,
            "configuration_epoch_sha256": (target_geometry.configuration_epoch_sha256),
            "target_safe_radius_basis": target_geometry.target_safe_radius_basis,
            "tool_tip_radius_basis": target_geometry.tool_tip_radius_basis,
            "target_safe_radius_micrometers": (
                target_geometry.target_safe_radius_micrometers
            ),
            "tool_tip_radius_micrometers": (
                target_geometry.tool_tip_radius_micrometers
            ),
            "guard_micrometers": target_geometry.guard_micrometers,
            "evidence_sha256": target_geometry.evidence_sha256,
            "dependency_hashes": _dependency_document(
                target_geometry.dependency_hashes
            ),
            "observed_at_unix_ns": target_geometry.observed_at_unix_ns,
            "valid_until_unix_ns": target_geometry.valid_until_unix_ns,
        },
    }
    return _canonical_sha256(document)


@dataclass(frozen=True, slots=True)
class TargetBudgetAssessment:
    disposition: AccuracyBudgetDisposition
    conservative_error_micrometers: int | None
    eroded_target_radius_micrometers: int
    remaining_margin_micrometers: int | None
    blocking_term_ids: tuple[str, ...]
    assessed_at_unix_ns: int
    evidence_valid_until_unix_ns: int | None
    operating_domain: str
    configuration_epoch_id: str
    configuration_epoch_sha256: str
    clock_evidence_sha256: str
    policy_sha256: str
    canonical_term_input_manifest_sha256: str
    target_id: str
    target_geometry_evidence_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, AccuracyBudgetDisposition):
            raise AccuracyBudgetPolicyError("assessment disposition is invalid")
        if type(self.eroded_target_radius_micrometers) is not int:
            raise AccuracyBudgetPolicyError(
                "eroded_target_radius_micrometers must be an integer"
            )
        _unix_nanoseconds(self.assessed_at_unix_ns, "assessed_at_unix_ns")
        _text(self.operating_domain, "operating_domain")
        _identifier(self.configuration_epoch_id, "configuration_epoch_id")
        _sha256_digest(
            self.configuration_epoch_sha256,
            "configuration_epoch_sha256",
        )
        _sha256_digest(self.clock_evidence_sha256, "clock_evidence_sha256")
        _sha256_digest(self.policy_sha256, "policy_sha256")
        _sha256_digest(
            self.canonical_term_input_manifest_sha256,
            "canonical_term_input_manifest_sha256",
        )
        _identifier(self.target_id, "target_id")
        _sha256_digest(
            self.target_geometry_evidence_sha256,
            "target_geometry_evidence_sha256",
        )
        if type(self.blocking_term_ids) is not tuple:
            raise AccuracyBudgetPolicyError(
                "blocking_term_ids must be an immutable tuple"
            )
        for term_id in self.blocking_term_ids:
            _identifier(term_id, "blocking term ID")
        if len(self.blocking_term_ids) != len(set(self.blocking_term_ids)):
            raise AccuracyBudgetPolicyError("blocking_term_ids contains duplicates")
        if not set(self.blocking_term_ids).issubset(_EXPECTED_TERM_IDS):
            raise AccuracyBudgetPolicyError(
                "blocking_term_ids contains an unknown accuracy term"
            )

        if self.disposition is AccuracyBudgetDisposition.BLOCKED_UNBOUNDED:
            if (
                self.conservative_error_micrometers is not None
                or self.remaining_margin_micrometers is not None
                or self.evidence_valid_until_unix_ns is not None
                or not self.blocking_term_ids
            ):
                raise AccuracyBudgetPolicyError(
                    "unbounded assessment fields are inconsistent"
                )
            return

        if self.blocking_term_ids:
            raise AccuracyBudgetPolicyError(
                "bounded assessment cannot contain blocking terms"
            )
        if (
            type(self.conservative_error_micrometers) is not int
            or self.conservative_error_micrometers < 0
            or type(self.remaining_margin_micrometers) is not int
        ):
            raise AccuracyBudgetPolicyError(
                "bounded assessment requires integer error and margin"
            )
        valid_until = _unix_nanoseconds(
            self.evidence_valid_until_unix_ns,
            "evidence_valid_until_unix_ns",
        )
        if valid_until < self.assessed_at_unix_ns:
            raise AccuracyBudgetPolicyError("assessment evidence is already expired")
        if self.remaining_margin_micrometers != (
            self.eroded_target_radius_micrometers - self.conservative_error_micrometers
        ):
            raise AccuracyBudgetPolicyError(
                "assessment margin does not match erosion minus conservative error"
            )
        fits = (
            self.eroded_target_radius_micrometers > 0
            and self.remaining_margin_micrometers >= 0
        )
        if (
            self.disposition is AccuracyBudgetDisposition.DIAGNOSTIC_FITS_ZERO_AUTHORITY
        ) != fits:
            raise AccuracyBudgetPolicyError(
                "assessment disposition does not match its signed margin"
            )

    @property
    def physical_authority(self) -> bool:
        """Accuracy arithmetic never grants physical targeting or motion."""

        return False


def load_target_accuracy_budget_policy(
    workspace: Path,
    policy_path: Path | None = None,
) -> TargetAccuracyBudgetPolicy:
    """Load the exact additive policy without importing a device backend."""

    from rocell.application.physical_onboarding_durability import (
        PhysicalOnboardingDurabilityError,
        read_bounded_regular_file,
    )

    selected = (
        DEFAULT_TARGET_ACCURACY_BUDGET_POLICY if policy_path is None else policy_path
    )
    resolved = _resolve_policy(Path(workspace), Path(selected))
    try:
        payload = read_bounded_regular_file(
            resolved, maximum_bytes=MAX_TARGET_ACCURACY_BUDGET_POLICY_BYTES,
            label="accuracy policy",
        )
    except (OSError, PhysicalOnboardingDurabilityError) as exc:
        raise AccuracyBudgetPolicyError("could not read accuracy policy") from exc
    if not payload or len(payload) > MAX_TARGET_ACCURACY_BUDGET_POLICY_BYTES:
        raise AccuracyBudgetPolicyError("accuracy policy size is invalid")
    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AccuracyBudgetPolicyError(
            "accuracy policy must be strict UTF-8 JSON"
        ) from exc
    root = _mapping(parsed, "accuracy policy")
    _exact_fields(
        root,
        frozenset(
            {
                "schema",
                "policy_id",
                "revision",
                "status",
                "runtime_activation",
                "authority",
                "combination_policy",
                "evidence_admissibility",
                "noncontact_terms",
                "contact_addendum_terms",
                "current_sensitivity_reference",
                "stock_android_qwerty_requires_closed_budget",
                "fallback_order",
                "open_blockers",
            }
        ),
        "accuracy policy",
    )
    if root["schema"] != TARGET_ACCURACY_BUDGET_POLICY_SCHEMA:
        raise AccuracyBudgetPolicyError("unsupported accuracy policy schema")
    if root["policy_id"] != "ROCELL-TARGET-ACCURACY-BUDGET-001":
        raise AccuracyBudgetPolicyError("unexpected accuracy policy ID")
    if type(root["revision"]) is not int or root["revision"] != 4:
        raise AccuracyBudgetPolicyError("accuracy policy revision must be 4")
    if root["status"] != "OPEN_REQUIRES_PHYSICAL_MEASUREMENT":
        raise AccuracyBudgetPolicyError("accuracy policy must remain physically open")
    if root["runtime_activation"] is not False:
        raise AccuracyBudgetPolicyError("accuracy policy cannot be runtime-active")
    authority = _mapping(root["authority"], "authority")
    if dict(authority) != {
        "planning_authority": True,
        "simulation_authority": True,
        "physical_targeting_authorized": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "physical_release_effect": "NONE",
    }:
        raise AccuracyBudgetPolicyError(
            "accuracy policy exceeds zero physical authority"
        )
    combination = _mapping(root["combination_policy"], "combination_policy")
    if dict(combination) != {
        "release_method": "CONSERVATIVE_LINEAR_SUM",
        "rss_or_covariance_use": "DIAGNOSTIC_ONLY_UNLESS_INDEPENDENCE_IS_PROVEN",
        "missing_stale_or_out_of_domain_term": "UNBOUNDED_AND_BLOCKING",
        "angular_terms_project_to_target_plane": True,
        "target_safe_region_is_eroded_by_tool_and_guard": True,
        "scalar_erosion_requires_certified_polygon_inradius_and_tool_circumradius": True,
    }:
        raise AccuracyBudgetPolicyError("accuracy combination policy changed")
    admissibility = _mapping(root["evidence_admissibility"], "evidence_admissibility")
    if dict(admissibility) != {
        "assessment_as_of_unix_ns_required": True,
        "term_source_binding_required": True,
        "all_required_metadata_must_exactly_match_binding": True,
        "dependency_hashes_are_named_sha256": True,
        "dependency_hash_set_must_exactly_match_binding": True,
        "term_evidence_digest_must_match_binding": True,
        "configuration_epoch_binding_required": True,
        "target_geometry_evidence_required": True,
        "assessment_clock_evidence_required": True,
        "observation_time_must_not_follow_as_of": True,
        "valid_until_must_not_precede_as_of": True,
        "assessment_records_earliest_evidence_expiry": True,
        "assessment_binds_policy_and_canonical_term_input_manifest": True,
        "live_trust_promotion_is_external": True,
        "missing_or_nonadmissible_evidence_is_unbounded": True,
    }:
        raise AccuracyBudgetPolicyError(
            "accuracy evidence-admissibility policy changed"
        )

    raw_terms = root["noncontact_terms"]
    if not isinstance(raw_terms, list):
        raise AccuracyBudgetPolicyError("noncontact_terms must be a list")
    terms: list[AccuracyBudgetTermDefinition] = []
    for index, raw_term in enumerate(raw_terms):
        term = _mapping(raw_term, f"noncontact_terms[{index}]")
        _exact_fields(
            term,
            frozenset({"id", "owner_stage", "unit", "required_metadata"}),
            f"noncontact_terms[{index}]",
        )
        if term["unit"] != "MICROMETERS_AT_TARGET_PLANE":
            raise AccuracyBudgetPolicyError(
                "all accuracy terms must share target-plane units"
            )
        try:
            owner = PhysicalOnboardingStage(term["owner_stage"])
        except (TypeError, ValueError) as exc:
            raise AccuracyBudgetPolicyError(
                "accuracy term owner stage is unknown"
            ) from exc
        metadata = _unique_identifiers(
            term["required_metadata"], f"noncontact_terms[{index}].required_metadata"
        )
        if metadata != _REQUIRED_METADATA:
            raise AccuracyBudgetPolicyError("accuracy term metadata contract changed")
        terms.append(
            AccuracyBudgetTermDefinition(
                term_id=_identifier(term["id"], f"noncontact_terms[{index}].id"),
                owner_stage=owner,
                required_metadata=metadata,
            )
        )
    if tuple(item.term_id for item in terms) != _EXPECTED_TERM_IDS:
        raise AccuracyBudgetPolicyError("accuracy term order or membership changed")

    contact_terms = _unique_identifiers(
        root["contact_addendum_terms"], "contact_addendum_terms"
    )
    if contact_terms != _EXPECTED_CONTACT_TERMS:
        raise AccuracyBudgetPolicyError("contact addendum term contract changed")
    sensitivity = _mapping(
        root["current_sensitivity_reference"], "current_sensitivity_reference"
    )
    _exact_fields(
        sensitivity,
        frozenset(
            {
                "classification",
                "keyboard_targets_with_sampled_gap",
                "keyboard_target_count",
                "phone_targets_with_sampled_gap",
                "phone_target_count",
                "worst_phone_margin_micrometers",
            }
        ),
        "current_sensitivity_reference",
    )
    if dict(sensitivity) != {
        "classification": "ILLUSTRATIVE_UNMEASURED_NOT_ACCEPTANCE",
        "keyboard_targets_with_sampled_gap": 0,
        "keyboard_target_count": 46,
        "phone_targets_with_sampled_gap": 27,
        "phone_target_count": 29,
        "worst_phone_margin_micrometers": -756,
    }:
        raise AccuracyBudgetPolicyError("illustrative sensitivity reference changed")
    if root["stock_android_qwerty_requires_closed_budget"] is not True:
        raise AccuracyBudgetPolicyError(
            "stock Android QWERTY must require a closed budget"
        )
    fallbacks = root["fallback_order"]
    if not isinstance(fallbacks, list) or tuple(fallbacks) != (
        "SMALLER_CHARACTERIZED_PASSIVE_STYLUS",
        "LARGER_PURPOSE_BUILT_ANDROID_UI",
        "LOCAL_VISUAL_REFINEMENT",
        "MECHANICAL_PRECISION_IMPROVEMENT_OR_DIFFERENT_ARM",
    ):
        raise AccuracyBudgetPolicyError("accuracy fallback order changed")
    blockers = root["open_blockers"]
    if (
        not isinstance(blockers, list)
        or not blockers
        or len(blockers) != len(set(blockers))
    ):
        raise AccuracyBudgetPolicyError(
            "accuracy policy must retain unique open blockers"
        )
    if any(
        not isinstance(item, str)
        or not item.startswith(("NO_", "PASSIVE_", "KEYBOARD_", "PHONE_", "CONTACT_"))
        for item in blockers
    ):
        raise AccuracyBudgetPolicyError("accuracy policy blocker is invalid")

    return TargetAccuracyBudgetPolicy(
        source_path=resolved,
        source_sha256=hashlib.sha256(payload).hexdigest(),
        policy_id=root["policy_id"],
        terms=tuple(terms),
        contact_addendum_terms=contact_terms,
        open_blockers=tuple(blockers),
    )


def assess_target_accuracy_budget(
    policy: TargetAccuracyBudgetPolicy,
    observations: Sequence[AccuracyBudgetObservation],
    *,
    term_bindings: Sequence[AccuracyTermEvidenceBinding],
    assessment_context: AccuracyAssessmentContext,
    target_geometry: TargetGeometryEvidence,
) -> TargetBudgetAssessment:
    """Apply the conservative linear sum and target-erosion rule.

    The function never returns physical authority.  Every measured term must
    exactly match an independently supplied source binding and be valid at the
    source-bound assessment time and configuration epoch. Target, passive-tool,
    and guard dimensions also arrive as source-bound evidence rather than bare
    arithmetic inputs. Missing, stale, future, mismatched, or out-of-domain
    term evidence remains unbounded rather than being treated as zero error.

    Digest equality establishes internal evidence-graph consistency, not trust.
    Promotion of any digest, clock, or epoch source remains an external
    commissioning decision, and this result always has zero physical authority.
    """

    if not isinstance(policy, TargetAccuracyBudgetPolicy):
        raise TypeError("policy must be TargetAccuracyBudgetPolicy")
    _validate_target_accuracy_budget_policy(policy)
    if not isinstance(assessment_context, AccuracyAssessmentContext):
        raise AccuracyBudgetPolicyError("assessment_context has an invalid type")
    if not isinstance(target_geometry, TargetGeometryEvidence):
        raise AccuracyBudgetPolicyError("target_geometry has an invalid type")
    # Recheck at the use boundary to catch low-level mutation of frozen values.
    assessment_context.__post_init__()
    target_geometry.__post_init__()
    as_of = assessment_context.as_of_unix_ns
    if (
        target_geometry.operating_domain != assessment_context.operating_domain
        or target_geometry.configuration_epoch_id
        != assessment_context.configuration_epoch_id
        or target_geometry.configuration_epoch_sha256
        != assessment_context.configuration_epoch_sha256
    ):
        raise AccuracyBudgetPolicyError(
            "target geometry does not match the assessment domain and epoch"
        )
    if not (
        target_geometry.observed_at_unix_ns
        <= as_of
        <= target_geometry.valid_until_unix_ns
    ):
        raise AccuracyBudgetPolicyError(
            "target geometry is future or expired at assessment time"
        )

    observed: dict[str, AccuracyBudgetObservation] = {}
    for observation in observations:
        if not isinstance(observation, AccuracyBudgetObservation):
            raise AccuracyBudgetPolicyError("observations contain an invalid item")
        observation.__post_init__()
        if observation.provenance is not None:
            observation.provenance.__post_init__()
        if observation.term_id in observed:
            raise AccuracyBudgetPolicyError("observations contain a duplicate term")
        observed[observation.term_id] = observation
    expected = tuple(term.term_id for term in policy.terms)
    unknown = sorted(set(observed) - set(expected))
    if unknown:
        raise AccuracyBudgetPolicyError(
            f"observations contain unknown terms: {unknown}"
        )

    bindings: dict[str, AccuracyTermEvidenceBinding] = {}
    for binding in term_bindings:
        if not isinstance(binding, AccuracyTermEvidenceBinding):
            raise AccuracyBudgetPolicyError("term_bindings contain an invalid item")
        binding.__post_init__()
        if binding.term_id in bindings:
            raise AccuracyBudgetPolicyError("term_bindings contain a duplicate term")
        bindings[binding.term_id] = binding
    unknown_bindings = sorted(set(bindings) - set(expected))
    if unknown_bindings:
        raise AccuracyBudgetPolicyError(
            f"term_bindings contain unknown terms: {unknown_bindings}"
        )
    term_input_manifest_sha256 = _assessment_input_manifest_sha256(
        policy,
        observed,
        bindings,
        assessment_context,
        target_geometry,
    )

    def is_admissible(term_id: str) -> bool:
        observation = observed.get(term_id)
        binding = bindings.get(term_id)
        if (
            observation is None
            or binding is None
            or observation.evidence_state
            is not AccuracyEvidenceState.MEASURED_IN_DOMAIN
            or observation.provenance is None
        ):
            return False
        provenance = observation.provenance
        metadata_matches = (
            provenance.frame == binding.frame
            and binding.frame == target_geometry.frame
            and provenance.operating_domain == binding.operating_domain
            and binding.operating_domain == assessment_context.operating_domain
            and binding.configuration_epoch_id
            == assessment_context.configuration_epoch_id
            and binding.configuration_epoch_sha256
            == assessment_context.configuration_epoch_sha256
            and provenance.sample_basis == binding.sample_basis
            and provenance.bound_method == binding.bound_method
            and provenance.coverage == binding.coverage
            and provenance.dependency_hashes == binding.dependency_hashes
            and observation.evidence_sha256 == binding.evidence_sha256
        )
        is_fresh_at_assessment = (
            provenance.observed_at_unix_ns <= as_of
            and provenance.valid_until_unix_ns >= as_of
        )
        return metadata_matches and is_fresh_at_assessment

    blocking = tuple(term_id for term_id in expected if not is_admissible(term_id))
    # Preserve signed clearance.  Clamping to zero would erase the distinction
    # between an exact-radius tool and one that is physically larger than the
    # target.  Strictly positive geometric clearance is required even if all
    # measured error bounds happen to be zero.
    eroded = (
        target_geometry.target_safe_radius_micrometers
        - target_geometry.tool_tip_radius_micrometers
        - target_geometry.guard_micrometers
    )
    if blocking:
        return TargetBudgetAssessment(
            disposition=AccuracyBudgetDisposition.BLOCKED_UNBOUNDED,
            conservative_error_micrometers=None,
            eroded_target_radius_micrometers=eroded,
            remaining_margin_micrometers=None,
            blocking_term_ids=blocking,
            assessed_at_unix_ns=as_of,
            evidence_valid_until_unix_ns=None,
            operating_domain=assessment_context.operating_domain,
            configuration_epoch_id=assessment_context.configuration_epoch_id,
            configuration_epoch_sha256=(assessment_context.configuration_epoch_sha256),
            clock_evidence_sha256=assessment_context.clock_evidence_sha256,
            policy_sha256=policy.source_sha256,
            canonical_term_input_manifest_sha256=term_input_manifest_sha256,
            target_id=target_geometry.target_id,
            target_geometry_evidence_sha256=target_geometry.evidence_sha256,
        )
    total = sum(observed[term_id].bound_micrometers or 0 for term_id in expected)
    margin = eroded - total
    provenance_expiries = tuple(
        observed[term_id].provenance.valid_until_unix_ns  # type: ignore[union-attr]
        for term_id in expected
    )
    evidence_valid_until = min(
        target_geometry.valid_until_unix_ns,
        *provenance_expiries,
    )
    return TargetBudgetAssessment(
        disposition=(
            AccuracyBudgetDisposition.DIAGNOSTIC_FITS_ZERO_AUTHORITY
            if eroded > 0 and margin >= 0
            else AccuracyBudgetDisposition.BLOCKED_TARGET_MARGIN
        ),
        conservative_error_micrometers=total,
        eroded_target_radius_micrometers=eroded,
        remaining_margin_micrometers=margin,
        blocking_term_ids=(),
        assessed_at_unix_ns=as_of,
        evidence_valid_until_unix_ns=evidence_valid_until,
        operating_domain=assessment_context.operating_domain,
        configuration_epoch_id=assessment_context.configuration_epoch_id,
        configuration_epoch_sha256=assessment_context.configuration_epoch_sha256,
        clock_evidence_sha256=assessment_context.clock_evidence_sha256,
        policy_sha256=policy.source_sha256,
        canonical_term_input_manifest_sha256=term_input_manifest_sha256,
        target_id=target_geometry.target_id,
        target_geometry_evidence_sha256=target_geometry.evidence_sha256,
    )


__all__ = [
    "TARGET_ACCURACY_BUDGET_POLICY_SCHEMA",
    "DEFAULT_TARGET_ACCURACY_BUDGET_POLICY",
    "MAX_TARGET_ACCURACY_BUDGET_POLICY_BYTES",
    "AccuracyAssessmentContext",
    "AccuracyBudgetDisposition",
    "AccuracyDependencyHash",
    "AccuracyEvidenceProvenance",
    "AccuracyBudgetObservation",
    "AccuracyBudgetPolicyError",
    "AccuracyBudgetTermDefinition",
    "AccuracyEvidenceState",
    "AccuracyTermEvidenceBinding",
    "TargetGeometryEvidence",
    "TargetAccuracyBudgetPolicy",
    "TargetBudgetAssessment",
    "assess_target_accuracy_budget",
    "load_target_accuracy_budget_policy",
]
