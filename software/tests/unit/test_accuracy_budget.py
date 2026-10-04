from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from rocell.calibration.accuracy_budget import (
    AccuracyAssessmentContext,
    AccuracyBudgetDisposition,
    AccuracyBudgetObservation,
    AccuracyBudgetPolicyError,
    AccuracyBudgetTermDefinition,
    AccuracyDependencyHash,
    AccuracyEvidenceProvenance,
    AccuracyEvidenceState,
    AccuracyTermEvidenceBinding,
    TargetAccuracyBudgetPolicy,
    TargetBudgetAssessment,
    TargetGeometryEvidence,
    assess_target_accuracy_budget,
    load_target_accuracy_budget_policy,
)


WORKSPACE = Path(__file__).resolve().parents[3]
POLICY_PATH = WORKSPACE / "software/config/accuracy_budget_policy.json"
EVIDENCE_DIGEST = "a" * 64
EPOCH_DIGEST = "b" * 64
CLOCK_DIGEST = "c" * 64
GEOMETRY_DIGEST = "d" * 64
POLICY_DIGEST = "e" * 64
INPUT_MANIFEST_DIGEST = "f" * 64
AS_OF_UNIX_NS = 2_000_000_000
OPERATING_DOMAIN = "installed_workcell_configuration_epoch_1"
CONFIGURATION_EPOCH_ID = "workcell_epoch_1"


def _document() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _temporary_policy(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> Path:
    document = copy.deepcopy(_document())
    mutate(document)
    path = tmp_path / "accuracy_budget_policy.json"
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def _term_binding(term_id: str) -> AccuracyTermEvidenceBinding:
    return AccuracyTermEvidenceBinding(
        term_id=term_id,
        frame="board_target_plane",
        operating_domain=OPERATING_DOMAIN,
        configuration_epoch_id=CONFIGURATION_EPOCH_ID,
        configuration_epoch_sha256=EPOCH_DIGEST,
        sample_basis=f"{term_id}_qualification_samples",
        bound_method="conservative_observed_maximum",
        coverage="full_declared_operating_domain",
        evidence_sha256=EVIDENCE_DIGEST,
        dependency_hashes=(
            AccuracyDependencyHash(
                dependency_id="configuration_epoch",
                sha256=EPOCH_DIGEST,
            ),
            AccuracyDependencyHash(
                dependency_id="term_evidence",
                sha256=EVIDENCE_DIGEST,
            ),
        ),
    )


def _assessment_context(
    *,
    as_of_unix_ns: int = AS_OF_UNIX_NS,
    operating_domain: str = OPERATING_DOMAIN,
    configuration_epoch_id: str = CONFIGURATION_EPOCH_ID,
    configuration_epoch_sha256: str = EPOCH_DIGEST,
) -> AccuracyAssessmentContext:
    return AccuracyAssessmentContext(
        as_of_unix_ns=as_of_unix_ns,
        operating_domain=operating_domain,
        configuration_epoch_id=configuration_epoch_id,
        configuration_epoch_sha256=configuration_epoch_sha256,
        clock_evidence_sha256=CLOCK_DIGEST,
        dependency_hashes=(
            AccuracyDependencyHash(
                dependency_id="assessment_clock",
                sha256=CLOCK_DIGEST,
            ),
            AccuracyDependencyHash(
                dependency_id="configuration_epoch",
                sha256=configuration_epoch_sha256,
            ),
        ),
    )


def _target_geometry(
    *,
    target_safe_radius_micrometers: int = 5000,
    tool_tip_radius_micrometers: int = 500,
    guard_micrometers: int = 500,
    operating_domain: str = OPERATING_DOMAIN,
    configuration_epoch_id: str = CONFIGURATION_EPOCH_ID,
    configuration_epoch_sha256: str = EPOCH_DIGEST,
    observed_at_unix_ns: int = AS_OF_UNIX_NS - 1_000,
    valid_until_unix_ns: int = AS_OF_UNIX_NS + 1_000,
) -> TargetGeometryEvidence:
    return TargetGeometryEvidence(
        target_id="keyboard_key_a",
        frame="board_target_plane",
        operating_domain=operating_domain,
        configuration_epoch_id=configuration_epoch_id,
        configuration_epoch_sha256=configuration_epoch_sha256,
        target_safe_radius_basis="CERTIFIED_TARGET_CENTERED_SAFE_POLYGON_INRADIUS",
        tool_tip_radius_basis="CERTIFIED_TOOL_FOOTPRINT_CIRCUMRADIUS",
        target_safe_radius_micrometers=target_safe_radius_micrometers,
        tool_tip_radius_micrometers=tool_tip_radius_micrometers,
        guard_micrometers=guard_micrometers,
        evidence_sha256=GEOMETRY_DIGEST,
        dependency_hashes=(
            AccuracyDependencyHash(
                dependency_id="configuration_epoch",
                sha256=configuration_epoch_sha256,
            ),
            AccuracyDependencyHash(
                dependency_id="target_geometry_bundle",
                sha256=GEOMETRY_DIGEST,
            ),
        ),
        observed_at_unix_ns=observed_at_unix_ns,
        valid_until_unix_ns=valid_until_unix_ns,
    )


def _term_bindings(
    policy: TargetAccuracyBudgetPolicy,
) -> tuple[AccuracyTermEvidenceBinding, ...]:
    return tuple(_term_binding(term.term_id) for term in policy.terms)


def _measured_observations(
    bound_micrometers: int,
) -> tuple[AccuracyBudgetObservation, ...]:
    policy = load_target_accuracy_budget_policy(WORKSPACE)
    return tuple(
        AccuracyBudgetObservation(
            term_id=term.term_id,
            evidence_state=AccuracyEvidenceState.MEASURED_IN_DOMAIN,
            bound_micrometers=bound_micrometers,
            evidence_sha256=EVIDENCE_DIGEST,
            provenance=AccuracyEvidenceProvenance(
                frame=binding.frame,
                operating_domain=binding.operating_domain,
                sample_basis=binding.sample_basis,
                bound_method=binding.bound_method,
                coverage=binding.coverage,
                dependency_hashes=binding.dependency_hashes,
                observed_at_unix_ns=AS_OF_UNIX_NS - 1_000,
                valid_until_unix_ns=AS_OF_UNIX_NS + 1_000,
            ),
        )
        for term, binding in (
            (term, _term_binding(term.term_id)) for term in policy.terms
        )
    )


def test_loads_accuracy_policy_without_granting_authority() -> None:
    before = POLICY_PATH.read_bytes()

    policy = load_target_accuracy_budget_policy(WORKSPACE)

    assert POLICY_PATH.read_bytes() == before
    assert policy.zero_physical_authority
    assert len(policy.terms) == 10
    assert policy.contact_addendum_terms
    assert policy.open_blockers


def test_missing_terms_are_unbounded_not_zero() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)

    result = assess_target_accuracy_budget(
        policy,
        (),
        term_bindings=_term_bindings(policy),
        assessment_context=_assessment_context(),
        target_geometry=_target_geometry(),
    )

    assert result.disposition is AccuracyBudgetDisposition.BLOCKED_UNBOUNDED
    assert result.conservative_error_micrometers is None
    assert result.remaining_margin_micrometers is None
    assert result.blocking_term_ids == tuple(term.term_id for term in policy.terms)
    assert not result.physical_authority


def test_conservative_linear_sum_can_fit_but_remains_zero_authority() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)

    result = assess_target_accuracy_budget(
        policy,
        _measured_observations(200),
        term_bindings=_term_bindings(policy),
        assessment_context=_assessment_context(),
        target_geometry=_target_geometry(tool_tip_radius_micrometers=1000),
    )

    assert (
        result.disposition is AccuracyBudgetDisposition.DIAGNOSTIC_FITS_ZERO_AUTHORITY
    )
    assert result.conservative_error_micrometers == 2000
    assert result.eroded_target_radius_micrometers == 3500
    assert result.remaining_margin_micrometers == 1500
    assert result.assessed_at_unix_ns == AS_OF_UNIX_NS
    assert result.evidence_valid_until_unix_ns == AS_OF_UNIX_NS + 1_000
    assert result.configuration_epoch_sha256 == EPOCH_DIGEST
    assert result.target_geometry_evidence_sha256 == GEOMETRY_DIGEST
    assert result.policy_sha256 == policy.source_sha256
    assert len(result.canonical_term_input_manifest_sha256) == 64
    assert not result.physical_authority


def test_assessment_manifest_changes_when_a_term_input_changes() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)
    common = {
        "term_bindings": _term_bindings(policy),
        "assessment_context": _assessment_context(),
        "target_geometry": _target_geometry(),
    }

    first = assess_target_accuracy_budget(policy, _measured_observations(100), **common)
    second = assess_target_accuracy_budget(
        policy, _measured_observations(101), **common
    )

    assert (
        first.canonical_term_input_manifest_sha256
        != second.canonical_term_input_manifest_sha256
    )


def test_target_geometry_requires_conservative_radius_certificates() -> None:
    with pytest.raises(AccuracyBudgetPolicyError, match="geometry certificates"):
        replace(
            _target_geometry(),
            target_safe_radius_basis="CALLER_ASSERTED_RADIUS",
        )


def test_conservative_sum_blocks_when_eroded_target_is_too_small() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)

    result = assess_target_accuracy_budget(
        policy,
        _measured_observations(400),
        term_bindings=_term_bindings(policy),
        assessment_context=_assessment_context(),
        target_geometry=_target_geometry(
            target_safe_radius_micrometers=4500,
            tool_tip_radius_micrometers=1000,
        ),
    )

    assert result.disposition is AccuracyBudgetDisposition.BLOCKED_TARGET_MARGIN
    assert result.conservative_error_micrometers == 4000
    assert result.remaining_margin_micrometers == -1000


def test_stale_term_blocks_entire_budget() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)
    observations = list(_measured_observations(100))
    observations[3] = AccuracyBudgetObservation(
        term_id=observations[3].term_id,
        evidence_state=AccuracyEvidenceState.STALE,
        bound_micrometers=None,
        evidence_sha256=None,
    )

    result = assess_target_accuracy_budget(
        policy,
        observations,
        term_bindings=_term_bindings(policy),
        assessment_context=_assessment_context(),
        target_geometry=_target_geometry(),
    )

    assert result.disposition is AccuracyBudgetDisposition.BLOCKED_UNBOUNDED
    assert result.blocking_term_ids == ("static_support_drift",)


def test_missing_provenance_is_unbounded_even_when_state_claims_measured() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)
    observations = list(_measured_observations(100))
    observations[0] = replace(observations[0], provenance=None)

    result = assess_target_accuracy_budget(
        policy,
        observations,
        term_bindings=_term_bindings(policy),
        assessment_context=_assessment_context(),
        target_geometry=_target_geometry(),
    )

    assert result.disposition is AccuracyBudgetDisposition.BLOCKED_UNBOUNDED
    assert result.blocking_term_ids == ("board_pose",)


def test_expired_or_future_provenance_is_unbounded_at_explicit_as_of() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)
    observations = list(_measured_observations(100))
    expired = observations[1].provenance
    future = observations[2].provenance
    assert expired is not None
    assert future is not None
    observations[1] = replace(
        observations[1],
        provenance=replace(
            expired,
            observed_at_unix_ns=AS_OF_UNIX_NS - 100,
            valid_until_unix_ns=AS_OF_UNIX_NS - 1,
        ),
    )
    observations[2] = replace(
        observations[2],
        provenance=replace(
            future,
            observed_at_unix_ns=AS_OF_UNIX_NS + 1,
            valid_until_unix_ns=AS_OF_UNIX_NS + 100,
        ),
    )

    result = assess_target_accuracy_budget(
        policy,
        observations,
        term_bindings=_term_bindings(policy),
        assessment_context=_assessment_context(),
        target_geometry=_target_geometry(),
    )

    assert result.disposition is AccuracyBudgetDisposition.BLOCKED_UNBOUNDED
    assert result.blocking_term_ids == (
        "intrinsics_and_distortion",
        "camera_board_registration",
    )


def test_wrong_domain_or_dependency_binding_is_unbounded() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)
    observations = list(_measured_observations(100))
    wrong_domain = observations[3].provenance
    wrong_dependency = observations[4].provenance
    assert wrong_domain is not None
    assert wrong_dependency is not None
    observations[3] = replace(
        observations[3],
        provenance=replace(wrong_domain, operating_domain="different_domain"),
    )
    observations[4] = replace(
        observations[4],
        provenance=replace(
            wrong_dependency,
            dependency_hashes=(
                AccuracyDependencyHash(
                    dependency_id="measurement_bundle",
                    sha256="f" * 64,
                ),
            ),
        ),
    )

    result = assess_target_accuracy_budget(
        policy,
        observations,
        term_bindings=_term_bindings(policy),
        assessment_context=_assessment_context(),
        target_geometry=_target_geometry(),
    )

    assert result.disposition is AccuracyBudgetDisposition.BLOCKED_UNBOUNDED
    assert result.blocking_term_ids == ("static_support_drift", "arm_board")


def test_missing_term_binding_is_unbounded() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)

    result = assess_target_accuracy_budget(
        policy,
        _measured_observations(100),
        term_bindings=_term_bindings(policy)[1:],
        assessment_context=_assessment_context(),
        target_geometry=_target_geometry(),
    )

    assert result.disposition is AccuracyBudgetDisposition.BLOCKED_UNBOUNDED
    assert result.blocking_term_ids == ("board_pose",)


@pytest.mark.parametrize(
    "term_variant", ["empty", "subset", "duplicate", "wrong_owner"]
)
def test_constructed_policy_cannot_remove_or_redefine_required_terms(
    term_variant: str,
) -> None:
    loaded = load_target_accuracy_budget_policy(WORKSPACE)
    terms: tuple[AccuracyBudgetTermDefinition, ...]
    if term_variant == "empty":
        terms = ()
    elif term_variant == "subset":
        terms = loaded.terms[:-1]
    elif term_variant == "duplicate":
        terms = (*loaded.terms[:-1], loaded.terms[-2])
    else:
        terms = (
            replace(
                loaded.terms[0],
                owner_stage=loaded.terms[-1].owner_stage,
            ),
            *loaded.terms[1:],
        )
    with pytest.raises(AccuracyBudgetPolicyError, match="term order|ownership"):
        TargetAccuracyBudgetPolicy(
            source_path=loaded.source_path,
            source_sha256=loaded.source_sha256,
            policy_id=loaded.policy_id,
            terms=terms,
            contact_addendum_terms=loaded.contact_addendum_terms,
            open_blockers=loaded.open_blockers,
        )


def test_assessor_revalidates_policy_after_low_level_mutation() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)
    object.__setattr__(policy, "terms", ())

    with pytest.raises(AccuracyBudgetPolicyError, match="term order"):
        assess_target_accuracy_budget(
            policy,
            (),
            term_bindings=(),
            assessment_context=_assessment_context(),
            target_geometry=_target_geometry(),
        )


def test_observation_digest_must_match_independent_term_binding() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)
    observations = list(_measured_observations(100))
    observations[0] = replace(observations[0], evidence_sha256="f" * 64)

    result = assess_target_accuracy_budget(
        policy,
        observations,
        term_bindings=_term_bindings(policy),
        assessment_context=_assessment_context(),
        target_geometry=_target_geometry(),
    )

    assert result.disposition is AccuracyBudgetDisposition.BLOCKED_UNBOUNDED
    assert result.blocking_term_ids == ("board_pose",)


def test_binding_digest_must_match_its_named_dependency() -> None:
    with pytest.raises(AccuracyBudgetPolicyError, match="evidence digest"):
        replace(_term_binding("board_pose"), evidence_sha256="f" * 64)


def test_context_clock_and_epoch_digests_must_match_named_dependencies() -> None:
    with pytest.raises(AccuracyBudgetPolicyError, match="clock digest"):
        replace(_assessment_context(), clock_evidence_sha256="f" * 64)
    with pytest.raises(AccuracyBudgetPolicyError, match="epoch digest"):
        replace(_assessment_context(), configuration_epoch_sha256="f" * 64)


def test_geometry_digest_and_epoch_must_match_named_dependencies() -> None:
    with pytest.raises(AccuracyBudgetPolicyError, match="evidence digest"):
        replace(_target_geometry(), evidence_sha256="f" * 64)
    with pytest.raises(AccuracyBudgetPolicyError, match="epoch digest"):
        replace(_target_geometry(), configuration_epoch_sha256="f" * 64)


@pytest.mark.parametrize(
    ("observed_at", "valid_until"),
    [
        (AS_OF_UNIX_NS + 1, AS_OF_UNIX_NS + 100),
        (AS_OF_UNIX_NS - 100, AS_OF_UNIX_NS - 1),
    ],
)
def test_future_or_expired_target_geometry_rejects_assessment(
    observed_at: int,
    valid_until: int,
) -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)
    with pytest.raises(AccuracyBudgetPolicyError, match="future or expired"):
        assess_target_accuracy_budget(
            policy,
            _measured_observations(100),
            term_bindings=_term_bindings(policy),
            assessment_context=_assessment_context(),
            target_geometry=_target_geometry(
                observed_at_unix_ns=observed_at,
                valid_until_unix_ns=valid_until,
            ),
        )


def test_geometry_must_match_context_domain_and_epoch() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)
    with pytest.raises(AccuracyBudgetPolicyError, match="domain and epoch"):
        assess_target_accuracy_budget(
            policy,
            _measured_observations(100),
            term_bindings=_term_bindings(policy),
            assessment_context=_assessment_context(),
            target_geometry=_target_geometry(configuration_epoch_id="workcell_epoch_2"),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_safe_radius_micrometers", 0),
        ("tool_tip_radius_micrometers", 0),
        ("guard_micrometers", 0),
        ("guard_micrometers", True),
    ],
)
def test_geometry_rejects_zero_or_boolean_dimensions(
    field: str,
    value: int,
) -> None:
    with pytest.raises(AccuracyBudgetPolicyError, match="positive integer"):
        if field == "target_safe_radius_micrometers":
            replace(
                _target_geometry(),
                target_safe_radius_micrometers=value,
            )
        elif field == "tool_tip_radius_micrometers":
            replace(
                _target_geometry(),
                tool_tip_radius_micrometers=value,
            )
        else:
            replace(_target_geometry(), guard_micrometers=value)


def test_assessment_context_rejects_boolean_time() -> None:
    with pytest.raises(AccuracyBudgetPolicyError, match="Unix timestamp"):
        replace(_assessment_context(), as_of_unix_ns=True)


def test_term_binding_must_match_context_epoch_and_geometry_frame() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)
    bindings = list(_term_bindings(policy))
    bindings[0] = replace(bindings[0], configuration_epoch_id="workcell_epoch_2")
    bindings[1] = replace(bindings[1], frame="different_target_frame")

    result = assess_target_accuracy_budget(
        policy,
        _measured_observations(100),
        term_bindings=bindings,
        assessment_context=_assessment_context(),
        target_geometry=_target_geometry(),
    )

    assert result.disposition is AccuracyBudgetDisposition.BLOCKED_UNBOUNDED
    assert result.blocking_term_ids == (
        "board_pose",
        "intrinsics_and_distortion",
    )


def test_assessment_records_earliest_admissible_evidence_expiry() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)
    observations = list(_measured_observations(100))
    provenance = observations[4].provenance
    assert provenance is not None
    observations[4] = replace(
        observations[4],
        provenance=replace(
            provenance,
            valid_until_unix_ns=AS_OF_UNIX_NS + 25,
        ),
    )

    result = assess_target_accuracy_budget(
        policy,
        observations,
        term_bindings=_term_bindings(policy),
        assessment_context=_assessment_context(),
        target_geometry=_target_geometry(valid_until_unix_ns=AS_OF_UNIX_NS + 50),
    )

    assert result.evidence_valid_until_unix_ns == AS_OF_UNIX_NS + 25


def test_dependency_values_are_immutable_named_lowercase_sha256() -> None:
    with pytest.raises(AccuracyBudgetPolicyError, match="lowercase SHA-256"):
        AccuracyDependencyHash(
            dependency_id="measurement_bundle",
            sha256="A" * 64,
        )
    with pytest.raises(AccuracyBudgetPolicyError, match="non-empty immutable tuple"):
        replace(_term_binding("board_pose"), dependency_hashes=())


@pytest.mark.parametrize(
    ("tool_radius", "guard", "expected_eroded"),
    [(400, 100, 0), (500, 1, -1)],
)
def test_equal_or_oversized_tool_cannot_fit_target(
    tool_radius: int,
    guard: int,
    expected_eroded: int,
) -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)

    result = assess_target_accuracy_budget(
        policy,
        _measured_observations(0),
        term_bindings=_term_bindings(policy),
        assessment_context=_assessment_context(),
        target_geometry=_target_geometry(
            target_safe_radius_micrometers=500,
            tool_tip_radius_micrometers=tool_radius,
            guard_micrometers=guard,
        ),
    )

    assert result.disposition is AccuracyBudgetDisposition.BLOCKED_TARGET_MARGIN
    assert result.eroded_target_radius_micrometers == expected_eroded
    assert result.remaining_margin_micrometers == expected_eroded
    assert not result.physical_authority


def test_assessment_cannot_be_constructed_with_physical_authority() -> None:
    with pytest.raises(TypeError, match="physical_authority"):
        TargetBudgetAssessment(
            disposition=AccuracyBudgetDisposition.DIAGNOSTIC_FITS_ZERO_AUTHORITY,
            conservative_error_micrometers=0,
            eroded_target_radius_micrometers=1,
            remaining_margin_micrometers=1,
            blocking_term_ids=(),
            assessed_at_unix_ns=AS_OF_UNIX_NS,
            evidence_valid_until_unix_ns=AS_OF_UNIX_NS + 1,
            operating_domain=OPERATING_DOMAIN,
            configuration_epoch_id=CONFIGURATION_EPOCH_ID,
            configuration_epoch_sha256=EPOCH_DIGEST,
            clock_evidence_sha256=CLOCK_DIGEST,
            policy_sha256=POLICY_DIGEST,
            canonical_term_input_manifest_sha256=INPUT_MANIFEST_DIGEST,
            target_id="keyboard_key_a",
            target_geometry_evidence_sha256=GEOMETRY_DIGEST,
            physical_authority=True,  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    ("disposition", "error", "margin", "blockers", "valid_until"),
    [
        (
            AccuracyBudgetDisposition.DIAGNOSTIC_FITS_ZERO_AUTHORITY,
            None,
            None,
            (),
            AS_OF_UNIX_NS + 1,
        ),
        (
            AccuracyBudgetDisposition.DIAGNOSTIC_FITS_ZERO_AUTHORITY,
            0,
            -1,
            (),
            AS_OF_UNIX_NS + 1,
        ),
        (
            AccuracyBudgetDisposition.BLOCKED_UNBOUNDED,
            None,
            None,
            (),
            None,
        ),
    ],
)
def test_rejects_internally_inconsistent_constructed_assessment(
    disposition: AccuracyBudgetDisposition,
    error: int | None,
    margin: int | None,
    blockers: tuple[str, ...],
    valid_until: int | None,
) -> None:
    with pytest.raises(AccuracyBudgetPolicyError, match="assessment|unbounded"):
        TargetBudgetAssessment(
            disposition=disposition,
            conservative_error_micrometers=error,
            eroded_target_radius_micrometers=1,
            remaining_margin_micrometers=margin,
            blocking_term_ids=blockers,
            assessed_at_unix_ns=AS_OF_UNIX_NS,
            evidence_valid_until_unix_ns=valid_until,
            operating_domain=OPERATING_DOMAIN,
            configuration_epoch_id=CONFIGURATION_EPOCH_ID,
            configuration_epoch_sha256=EPOCH_DIGEST,
            clock_evidence_sha256=CLOCK_DIGEST,
            policy_sha256=POLICY_DIGEST,
            canonical_term_input_manifest_sha256=INPUT_MANIFEST_DIGEST,
            target_id="keyboard_key_a",
            target_geometry_evidence_sha256=GEOMETRY_DIGEST,
        )


def test_constructed_assessment_rejects_unknown_blocking_term() -> None:
    with pytest.raises(AccuracyBudgetPolicyError, match="unknown accuracy term"):
        TargetBudgetAssessment(
            disposition=AccuracyBudgetDisposition.BLOCKED_UNBOUNDED,
            conservative_error_micrometers=None,
            eroded_target_radius_micrometers=1,
            remaining_margin_micrometers=None,
            blocking_term_ids=("invented_term",),
            assessed_at_unix_ns=AS_OF_UNIX_NS,
            evidence_valid_until_unix_ns=None,
            operating_domain=OPERATING_DOMAIN,
            configuration_epoch_id=CONFIGURATION_EPOCH_ID,
            configuration_epoch_sha256=EPOCH_DIGEST,
            clock_evidence_sha256=CLOCK_DIGEST,
            policy_sha256=POLICY_DIGEST,
            canonical_term_input_manifest_sha256=INPUT_MANIFEST_DIGEST,
            target_id="keyboard_key_a",
            target_geometry_evidence_sha256=GEOMETRY_DIGEST,
        )


def test_rejects_duplicate_or_unknown_observation() -> None:
    policy = load_target_accuracy_budget_policy(WORKSPACE)
    observation = _measured_observations(100)[0]
    with pytest.raises(AccuracyBudgetPolicyError, match="duplicate"):
        assess_target_accuracy_budget(
            policy,
            (observation, observation),
            term_bindings=_term_bindings(policy),
            assessment_context=_assessment_context(),
            target_geometry=_target_geometry(),
        )
    unknown = AccuracyBudgetObservation(
        term_id="unknown_term",
        evidence_state=AccuracyEvidenceState.MEASURED_IN_DOMAIN,
        bound_micrometers=1,
        evidence_sha256=EVIDENCE_DIGEST,
    )
    with pytest.raises(AccuracyBudgetPolicyError, match="unknown terms"):
        assess_target_accuracy_budget(
            policy,
            (unknown,),
            term_bindings=_term_bindings(policy),
            assessment_context=_assessment_context(),
            target_geometry=_target_geometry(),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("physical_targeting_authorized", True),
        ("motion_authorized", True),
        ("contact_authorized", True),
        ("physical_release_effect", "CONTACT_RELEASED"),
    ],
)
def test_rejects_authority_escalation(
    tmp_path: Path, field: str, value: object
) -> None:
    path = _temporary_policy(
        tmp_path,
        lambda document: document["authority"].update({field: value}),
    )
    with pytest.raises(AccuracyBudgetPolicyError, match="zero physical authority"):
        load_target_accuracy_budget_policy(tmp_path, path)


def test_rejects_unknown_policy_field(tmp_path: Path) -> None:
    path = _temporary_policy(
        tmp_path,
        lambda document: document.update({"unversioned_extension": True}),
    )
    with pytest.raises(AccuracyBudgetPolicyError, match="fields differ"):
        load_target_accuracy_budget_policy(tmp_path, path)


def test_rejects_relaxed_evidence_admissibility(tmp_path: Path) -> None:
    path = _temporary_policy(
        tmp_path,
        lambda document: document["evidence_admissibility"].update(
            {"term_source_binding_required": False}
        ),
    )
    with pytest.raises(AccuracyBudgetPolicyError, match="evidence-admissibility"):
        load_target_accuracy_budget_policy(tmp_path, path)


def test_rejects_duplicate_json_field(tmp_path: Path) -> None:
    original = POLICY_PATH.read_text(encoding="utf-8")
    path = tmp_path / "duplicate.json"
    path.write_text(
        original.replace(
            '"runtime_activation": false,',
            '"runtime_activation": false,\n  "runtime_activation": false,',
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(AccuracyBudgetPolicyError, match="duplicate JSON field"):
        load_target_accuracy_budget_policy(tmp_path, path)


def test_rejects_float_anywhere(tmp_path: Path) -> None:
    path = tmp_path / "float.json"
    path.write_text(
        POLICY_PATH.read_text(encoding="utf-8").replace(
            '"revision": 4,', '"revision": 4.0,', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(AccuracyBudgetPolicyError, match="must not contain floats"):
        load_target_accuracy_budget_policy(tmp_path, path)


def test_rejects_policy_outside_workspace(tmp_path: Path) -> None:
    with pytest.raises(AccuracyBudgetPolicyError, match="beneath the workspace"):
        load_target_accuracy_budget_policy(tmp_path, POLICY_PATH)


def test_rejects_oversized_policy_at_file_boundary(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * (256 * 1024 + 1))
    with pytest.raises(AccuracyBudgetPolicyError, match="could not read"):
        load_target_accuracy_budget_policy(tmp_path, path)
