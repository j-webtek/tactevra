"""Strict, read-only validation for synthetic self-occlusion projections.

The AI boundary consumes hashes and timing metadata from a projection producer.
It never receives joint values, creates geometry, installs calibration, or
authorizes motion.  A caller-provided registry is trust context; evidence cannot
self-install its qualification.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .scene_observation import SHA256_PATTERN, canonical_hash


EVIDENCE_SCHEMA = "rocell.ai_self_occlusion_projection_evidence.v1"
QUALIFICATION_SCHEMA = "rocell.ai_self_occlusion_projection_qualification.v1"
REPORT_SCHEMA = "rocell.ai_self_occlusion_projection_validation.v1"
SCOPE = "SYNTHETIC_OFFLINE_ONLY"
FEEDBACK_SOURCE = "MEASURED_SERVO_POSITION"
INTERPOLATION_POLICY = "LINEAR_MEASURED_POSITION_BRACKET_V1"
VISIBLE_OVERLAP_UPPER = 0.18
AMBIGUITY_OVERLAP_UPPER = 0.22

_IDENTITY_FIELDS = (
    "camera_calibration_sha256",
    "camera_to_board_sha256",
    "robot_visual_mesh_sha256",
    "target_catalog_sha256",
    "uncertainty_profile_sha256",
    "projection_implementation_sha256",
)
_ROOT_FIELDS = {
    "schema",
    "scope",
    "projection_id",
    "domain_id",
    "frame",
    "feedback_bracket",
    "projection_bindings",
    "dilation",
    "target_results",
    "hardware_writes",
    "physical_movements",
    "physical_authority",
    "limitations",
    "evidence_sha256",
}
_FRAME_FIELDS = {
    "frame_id",
    "image_sha256",
    "exposure_timestamp_ns",
    "exposure_start_ns",
    "exposure_end_ns",
    "clock_id",
}
_BRACKET_FIELDS = {
    "source",
    "feedback_source_sha256",
    "pre_sample_sha256",
    "pre_timestamp_ns",
    "post_sample_sha256",
    "post_timestamp_ns",
    "clock_id",
    "clock_correlation_sha256",
    "interpolation_policy_id",
    "interpolation_policy_sha256",
    "interpolated_measured_state_sha256",
}
_BINDING_FIELDS = set(_IDENTITY_FIELDS) | {"qualification_sha256"}
_DILATION_FIELDS = {"bound_px", "derivation_sha256"}
_TARGET_FIELDS = {
    "target_id",
    "center_covered",
    "safe_region_overlap_fraction",
    "dilated_safe_region_overlap_fraction",
    "decision",
}
_QUALIFICATION_FIELDS = {
    "schema",
    "scope",
    "domain_id",
    *_IDENTITY_FIELDS,
    "clock_id",
    "feedback_source",
    "feedback_source_sha256",
    "clock_correlation_sha256",
    "interpolation_policy_id",
    "interpolation_policy_sha256",
    "maximum_feedback_bracket_gap_ns",
    "maximum_evidence_age_ns",
    "dilation_bound_px",
    "dilation_derivation_sha256",
    "charuco_reprojection_evidence_sha256",
    "feedback_resolution_noise_evidence_sha256",
    "backlash_repeatability_evidence_sha256",
    "visible_overlap_upper",
    "ambiguity_overlap_upper",
    "physical_deployment_qualified",
    "hardware_writes",
    "physical_movements",
    "limitations",
    "qualification_sha256",
}


class ProjectionEvidenceError(ValueError):
    """Projection evidence or its trusted synthetic policy is malformed."""


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    actual = set(value)
    if actual != fields:
        raise ProjectionEvidenceError(
            f"{label} fields differ; missing={sorted(fields - actual)}, "
            f"extra={sorted(actual - fields)}"
        )


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ProjectionEvidenceError(f"{label} must be an object with string keys")
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or not value[0].isalnum()
        or any(not (item.isalnum() or item in "._:-") for item in value)
    ):
        raise ProjectionEvidenceError(f"{label} must be a bounded identifier")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ProjectionEvidenceError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _integer(value: object, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProjectionEvidenceError(f"{label} must be an integer")
    if value < (1 if positive else 0):
        raise ProjectionEvidenceError(f"{label} is below its minimum")
    return value


def _finite(value: object, label: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProjectionEvidenceError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ProjectionEvidenceError(f"{label} is outside [{minimum}, {maximum}]")
    return result


def _limitations(value: object, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ProjectionEvidenceError(f"{label} must contain nonempty strings")
    return tuple(value)


def _hash_without(document: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


@dataclass(frozen=True, slots=True)
class TrustedSyntheticProjectionQualificationV1:
    """Caller-authenticated synthetic policy; never deployment qualification."""

    document: Mapping[str, Any]

    def __post_init__(self) -> None:
        value = dict(_mapping(self.document, "qualification"))
        _exact(value, _QUALIFICATION_FIELDS, "qualification")
        if value["schema"] != QUALIFICATION_SCHEMA or value["scope"] != SCOPE:
            raise ProjectionEvidenceError("unsupported projection qualification")
        _identifier(value["domain_id"], "qualification.domain_id")
        for field in _IDENTITY_FIELDS:
            _digest(value[field], f"qualification.{field}")
        _identifier(value["clock_id"], "qualification.clock_id")
        if value["feedback_source"] != FEEDBACK_SOURCE:
            raise ProjectionEvidenceError("qualification requires measured servo feedback")
        if value["interpolation_policy_id"] != INTERPOLATION_POLICY:
            raise ProjectionEvidenceError("unsupported interpolation policy")
        for field in (
            "feedback_source_sha256",
            "clock_correlation_sha256",
            "interpolation_policy_sha256",
            "dilation_derivation_sha256",
            "charuco_reprojection_evidence_sha256",
            "feedback_resolution_noise_evidence_sha256",
            "backlash_repeatability_evidence_sha256",
        ):
            _digest(value[field], f"qualification.{field}")
        _integer(
            value["maximum_feedback_bracket_gap_ns"],
            "qualification.maximum_feedback_bracket_gap_ns",
            positive=True,
        )
        _integer(
            value["maximum_evidence_age_ns"],
            "qualification.maximum_evidence_age_ns",
            positive=True,
        )
        _finite(value["dilation_bound_px"], "qualification.dilation_bound_px", minimum=0, maximum=4096)
        if value["visible_overlap_upper"] != VISIBLE_OVERLAP_UPPER:
            raise ProjectionEvidenceError("visible overlap boundary is not frozen")
        if value["ambiguity_overlap_upper"] != AMBIGUITY_OVERLAP_UPPER:
            raise ProjectionEvidenceError("ambiguity overlap boundary is not frozen")
        if value["physical_deployment_qualified"] is not False:
            raise ProjectionEvidenceError("synthetic policy cannot qualify deployment")
        if value["hardware_writes"] != 0 or value["physical_movements"] != 0:
            raise ProjectionEvidenceError("qualification must have zero physical effects")
        _limitations(value["limitations"], "qualification.limitations")
        digest = _digest(value["qualification_sha256"], "qualification_sha256")
        if digest != _hash_without(value, "qualification_sha256"):
            raise ProjectionEvidenceError("qualification hash mismatch")
        object.__setattr__(self, "document", MappingProxyType(value))

    @property
    def sha256(self) -> str:
        return str(self.document["qualification_sha256"])


def validate_projection_evidence(document: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate exact structure, content hash, and deterministic decisions."""
    value = dict(_mapping(document, "projection evidence"))
    _exact(value, _ROOT_FIELDS, "projection evidence")
    if value["schema"] != EVIDENCE_SCHEMA or value["scope"] != SCOPE:
        raise ProjectionEvidenceError("unsupported projection evidence")
    _identifier(value["projection_id"], "projection_id")
    _identifier(value["domain_id"], "domain_id")

    frame = dict(_mapping(value["frame"], "frame"))
    _exact(frame, _FRAME_FIELDS, "frame")
    _identifier(frame["frame_id"], "frame.frame_id")
    _digest(frame["image_sha256"], "frame.image_sha256")
    for field in ("exposure_timestamp_ns", "exposure_start_ns", "exposure_end_ns"):
        _integer(frame[field], f"frame.{field}", positive=True)
    _identifier(frame["clock_id"], "frame.clock_id")
    if not frame["exposure_start_ns"] <= frame["exposure_timestamp_ns"] <= frame["exposure_end_ns"]:
        raise ProjectionEvidenceError("exposure timestamp is outside the exposure interval")

    bracket = dict(_mapping(value["feedback_bracket"], "feedback_bracket"))
    _exact(bracket, _BRACKET_FIELDS, "feedback_bracket")
    if bracket["source"] != FEEDBACK_SOURCE:
        raise ProjectionEvidenceError("commanded or unknown feedback source is prohibited")
    for field in (
        "feedback_source_sha256",
        "pre_sample_sha256",
        "post_sample_sha256",
        "clock_correlation_sha256",
        "interpolation_policy_sha256",
        "interpolated_measured_state_sha256",
    ):
        _digest(bracket[field], f"feedback_bracket.{field}")
    for field in ("pre_timestamp_ns", "post_timestamp_ns"):
        _integer(bracket[field], f"feedback_bracket.{field}", positive=True)
    _identifier(bracket["clock_id"], "feedback_bracket.clock_id")
    if bracket["interpolation_policy_id"] != INTERPOLATION_POLICY:
        raise ProjectionEvidenceError("unsupported interpolation policy")
    if bracket["clock_id"] != frame["clock_id"]:
        raise ProjectionEvidenceError("frame and measured-feedback clocks differ")
    if not (
        bracket["pre_timestamp_ns"] <= frame["exposure_start_ns"]
        <= frame["exposure_end_ns"] <= bracket["post_timestamp_ns"]
    ):
        raise ProjectionEvidenceError("measured feedback does not bracket exposure")

    bindings = dict(_mapping(value["projection_bindings"], "projection_bindings"))
    _exact(bindings, _BINDING_FIELDS, "projection_bindings")
    for field in _BINDING_FIELDS:
        _digest(bindings[field], f"projection_bindings.{field}")

    dilation = dict(_mapping(value["dilation"], "dilation"))
    _exact(dilation, _DILATION_FIELDS, "dilation")
    _finite(dilation["bound_px"], "dilation.bound_px", minimum=0, maximum=4096)
    _digest(dilation["derivation_sha256"], "dilation.derivation_sha256")

    results = value["target_results"]
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)) or not results:
        raise ProjectionEvidenceError("target_results must be a nonempty array")
    seen: set[str] = set()
    for index, item in enumerate(results):
        result = dict(_mapping(item, f"target_results[{index}]"))
        _exact(result, _TARGET_FIELDS, f"target_results[{index}]")
        target_id = _identifier(result["target_id"], f"target_results[{index}].target_id")
        if target_id in seen:
            raise ProjectionEvidenceError("target_results contains duplicate target ids")
        seen.add(target_id)
        if not isinstance(result["center_covered"], bool):
            raise ProjectionEvidenceError("center_covered must be boolean")
        raw = _finite(result["safe_region_overlap_fraction"], "safe_region_overlap_fraction", minimum=0, maximum=1)
        dilated = _finite(result["dilated_safe_region_overlap_fraction"], "dilated_safe_region_overlap_fraction", minimum=0, maximum=1)
        if dilated < raw:
            raise ProjectionEvidenceError("dilated overlap cannot be below raw overlap")
        expected = (
            "ABSTAIN_SELF_OCCLUDED"
            if result["center_covered"] or dilated > AMBIGUITY_OVERLAP_UPPER
            else "ABSTAIN_AMBIGUOUS"
            if dilated >= VISIBLE_OVERLAP_UPPER
            else "VISIBLE"
        )
        if result["decision"] != expected:
            raise ProjectionEvidenceError(f"target {target_id!r} decision is inconsistent")

    if value["hardware_writes"] != 0 or value["physical_movements"] != 0:
        raise ProjectionEvidenceError("projection evidence must have zero physical effects")
    if value["physical_authority"] is not False:
        raise ProjectionEvidenceError("projection evidence cannot claim physical authority")
    _limitations(value["limitations"], "limitations")
    digest = _digest(value["evidence_sha256"], "evidence_sha256")
    if digest != _hash_without(value, "evidence_sha256"):
        raise ProjectionEvidenceError("projection evidence hash mismatch")
    return MappingProxyType(value)


def assess_projection_evidence(
    document: Mapping[str, Any],
    *,
    trusted_synthetic_qualifications: Mapping[
        str, TrustedSyntheticProjectionQualificationV1
    ] | None,
    expected_domain_id: str,
    now_timestamp_ns: int,
    now_clock_id: str,
) -> Mapping[str, Any]:
    """Apply caller trust, identity, timing, and age checks without I/O."""
    evidence = validate_projection_evidence(document)
    _identifier(expected_domain_id, "expected_domain_id")
    _identifier(now_clock_id, "now_clock_id")
    _integer(now_timestamp_ns, "now_timestamp_ns", positive=True)
    reasons: list[str] = []
    qualification_sha256 = str(evidence["projection_bindings"]["qualification_sha256"])
    registry = trusted_synthetic_qualifications or {}
    qualification = registry.get(qualification_sha256)
    if qualification is None:
        reasons.append("projection_qualification_not_installed")
    elif not isinstance(qualification, TrustedSyntheticProjectionQualificationV1):
        raise ProjectionEvidenceError("qualification registry contains an invalid value")
    elif qualification.sha256 != qualification_sha256:
        raise ProjectionEvidenceError("qualification registry key mismatch")
    else:
        policy = qualification.document
        if evidence["domain_id"] != expected_domain_id or policy["domain_id"] != expected_domain_id:
            reasons.append("projection_domain_unverified")
        for field in _IDENTITY_FIELDS:
            if evidence["projection_bindings"][field] != policy[field]:
                reasons.append(f"projection_{field.removesuffix('_sha256')}_mismatch")
        frame = evidence["frame"]
        bracket = evidence["feedback_bracket"]
        if frame["clock_id"] != policy["clock_id"] or now_clock_id != policy["clock_id"]:
            reasons.append("projection_clock_unverified")
        if bracket["source"] != policy["feedback_source"]:
            reasons.append("projection_feedback_source_unverified")
        if bracket["feedback_source_sha256"] != policy["feedback_source_sha256"]:
            reasons.append("projection_measured_feedback_source_unverified")
        if bracket["clock_correlation_sha256"] != policy["clock_correlation_sha256"]:
            reasons.append("projection_clock_correlation_unverified")
        if (
            bracket["interpolation_policy_id"] != policy["interpolation_policy_id"]
            or bracket["interpolation_policy_sha256"] != policy["interpolation_policy_sha256"]
        ):
            reasons.append("projection_interpolation_unverified")
        gap = bracket["post_timestamp_ns"] - bracket["pre_timestamp_ns"]
        if gap > policy["maximum_feedback_bracket_gap_ns"]:
            reasons.append("projection_feedback_bracket_too_wide")
        age = now_timestamp_ns - frame["exposure_end_ns"]
        if age < 0 or age > policy["maximum_evidence_age_ns"]:
            reasons.append("projection_evidence_stale")
        if (
            evidence["dilation"]["bound_px"] != policy["dilation_bound_px"]
            or evidence["dilation"]["derivation_sha256"]
            != policy["dilation_derivation_sha256"]
        ):
            reasons.append("projection_dilation_unverified")

    accepted = not reasons
    core = {
        "schema": REPORT_SCHEMA,
        "scope": SCOPE,
        "projection_evidence_sha256": evidence["evidence_sha256"],
        "qualification_sha256": qualification_sha256,
        "decision": "ACCEPTED_SYNTHETIC_OFFLINE_ONLY" if accepted else "ABSTAIN",
        "reasons": reasons,
        "target_decisions": [
            {"target_id": item["target_id"], "decision": item["decision"]}
            for item in evidence["target_results"]
        ],
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "Synthetic trust context does not qualify deployment",
            "This validator does not render geometry or inspect joint values",
            "Projection visibility is not collision, reachability, or execution evidence",
        ],
    }
    return MappingProxyType({**core, "report_sha256": canonical_hash(core)})


__all__ = [
    "AMBIGUITY_OVERLAP_UPPER",
    "EVIDENCE_SCHEMA",
    "FEEDBACK_SOURCE",
    "INTERPOLATION_POLICY",
    "ProjectionEvidenceError",
    "QUALIFICATION_SCHEMA",
    "SCOPE",
    "TrustedSyntheticProjectionQualificationV1",
    "VISIBLE_OVERLAP_UPPER",
    "assess_projection_evidence",
    "validate_projection_evidence",
]
