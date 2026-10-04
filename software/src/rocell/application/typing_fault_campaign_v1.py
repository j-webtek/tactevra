"""Deterministic, zero-I/O PC5 typing fault-campaign receipt.

The campaign consumes observations produced by bounded offline tests.  It does
not execute callbacks, open transports, issue permits, or retry work.  Its job
is to make complete fault-family coverage and fail-closed invariants auditable
with one canonical, hash-bound report.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping


SCHEMA = "rocell.typing_fault_campaign.v1"
CACHE_SCHEMA = "rocell.typing_fault_observation_cache.v1"
STATUS = "PASS_ZERO_AUTHORITY_FAULT_CAMPAIGN"
MAX_CAMPAIGN_CASES = 64
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Z0-9][A-Z0-9_]{0,95}$")

REJECTED = "REJECTED_BEFORE_DISPATCH"
UNCERTAIN = "OUTCOME_UNCERTAIN_RETRY_FORBIDDEN"
_OBSERVATION_FIELDS = {
    "case_id", "family", "reason_code", "terminal_outcome",
    "boundary_sha256", "fault_observed", "exception_escaped",
    "automatic_retry_allowed", "order_preserved", "silent_fallback_used",
    "bounded_resources", "controller_commands", "hardware_access",
    "physical_authority",
}


class TypingFaultCampaignV1Error(ValueError):
    """A PC5 observation or campaign report is incomplete or unsafe."""


# case_id: (family, stable reason, required terminal outcome)
REQUIRED_CASES: Mapping[str, tuple[str, str, str]] = MappingProxyType({
    "INPUT_MALFORMED": ("MODEL_INPUT", "INPUT_MALFORMED", REJECTED),
    "INPUT_DUPLICATE_FIELD": ("MODEL_INPUT", "INPUT_DUPLICATE_FIELD", REJECTED),
    "INPUT_MISSING_FIELD": ("MODEL_INPUT", "INPUT_MISSING_FIELD", REJECTED),
    "INPUT_OVERSIZED": ("MODEL_INPUT", "INPUT_OVERSIZED", REJECTED),
    "INPUT_NAN": ("MODEL_INPUT", "INPUT_NONFINITE", REJECTED),
    "INPUT_INFINITY": ("MODEL_INPUT", "INPUT_NONFINITE", REJECTED),
    "INPUT_DEEPLY_NESTED": ("MODEL_INPUT", "INPUT_DEPTH_LIMIT", REJECTED),
    "EVIDENCE_STALE": ("IDENTITY_ORDER", "EVIDENCE_STALE", REJECTED),
    "IDENTITY_CROSSED": ("IDENTITY_ORDER", "IDENTITY_CROSSED", REJECTED),
    "ACTION_ORDER_INVALID": ("IDENTITY_ORDER", "ACTION_ORDER_INVALID", REJECTED),
    "IK_UNREACHABLE": ("PLANNING", "IK_UNREACHABLE", REJECTED),
    "JOINT_LIMIT_LOSS": ("PLANNING", "JOINT_LIMIT_REJECTED", REJECTED),
    "SINGULARITY": ("PLANNING", "SINGULARITY_REJECTED", REJECTED),
    "DISCONTINUITY": ("PLANNING", "DISCONTINUITY_REJECTED", REJECTED),
    "DYNAMICS_OVERFLOW": ("PLANNING", "DYNAMICS_OVERFLOW", REJECTED),
    "COLLISION_EVIDENCE_ABSENT": (
        "PLANNING", "COLLISION_EVIDENCE_MISSING", REJECTED),
    "CLEARANCE_LOSS": ("PLANNING", "CLEARANCE_LOSS", REJECTED),
    "ACK_LATE": ("TRANSPORT_FEEDBACK", "ACK_LATE", UNCERTAIN),
    "FEEDBACK_MISSING": ("TRANSPORT_FEEDBACK", "FEEDBACK_MISSING", UNCERTAIN),
    "FEEDBACK_MALFORMED": ("TRANSPORT_FEEDBACK", "FEEDBACK_MALFORMED", UNCERTAIN),
    "PARTIAL_WRITE": ("TRANSPORT_FEEDBACK", "PARTIAL_WRITE_UNCERTAIN", UNCERTAIN),
    "DISCONNECT": ("TRANSPORT_FEEDBACK", "DISCONNECTED_UNCERTAIN", UNCERTAIN),
    "CONTROLLER_RESTART": (
        "TRANSPORT_FEEDBACK", "CONTROLLER_RESTART_UNCERTAIN", UNCERTAIN),
    "SEQUENCE_MISMATCH": ("TRANSPORT_FEEDBACK", "SEQUENCE_MISMATCH", UNCERTAIN),
    "AMBIGUOUS_COMPLETION": (
        "TRANSPORT_FEEDBACK", "AMBIGUOUS_COMPLETION", UNCERTAIN),
    "CRASH_BEFORE_INTENT": ("PROCESS_CRASH", "CRASH_BEFORE_INTENT_SAFE", REJECTED),
    "CRASH_AFTER_DURABLE_INTENT": (
        "PROCESS_CRASH", "CRASH_AFTER_INTENT_UNCERTAIN", UNCERTAIN),
    "CRASH_DURING_DISPATCH": (
        "PROCESS_CRASH", "CRASH_DURING_DISPATCH_UNCERTAIN", UNCERTAIN),
    "CRASH_AFTER_POSSIBLE_CONTACT": (
        "PROCESS_CRASH", "CRASH_AFTER_CONTACT_UNCERTAIN", UNCERTAIN),
    "CRASH_BEFORE_EFFECT_VERIFICATION": (
        "PROCESS_CRASH", "CRASH_BEFORE_EFFECT_VERIFICATION_UNCERTAIN", UNCERTAIN),
    "CACHE_CORRUPTION": ("RUNTIME_RESOURCE", "CACHE_CORRUPT", REJECTED),
    "CACHE_IDENTITY_CROSSING": (
        "RUNTIME_RESOURCE", "CACHE_IDENTITY_CROSSED", REJECTED),
    "DEADLINE_EXPIRY": ("RUNTIME_RESOURCE", "DEADLINE_EXPIRED", REJECTED),
    "CANCELLATION": ("RUNTIME_RESOURCE", "CANCELLED", REJECTED),
    "RESOURCE_EXHAUSTION": (
        "RUNTIME_RESOURCE", "RESOURCE_LIMIT_EXCEEDED", REJECTED),
})


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingFaultCampaignV1Error("value is not canonical JSON") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise TypingFaultCampaignV1Error(f"{label} must be a SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True)
class TypingFaultObservationV1:
    case_id: str
    family: str
    reason_code: str
    terminal_outcome: str
    boundary_sha256: str
    fault_observed: bool = True
    exception_escaped: bool = False
    automatic_retry_allowed: bool = False
    order_preserved: bool = True
    silent_fallback_used: bool = False
    bounded_resources: bool = True
    controller_commands: tuple[object, ...] = ()
    hardware_access: bool = False
    physical_authority: bool = False

    def __post_init__(self) -> None:
        if self.case_id not in REQUIRED_CASES:
            raise TypingFaultCampaignV1Error("fault case is not in the PC5 basis")
        expected = REQUIRED_CASES[self.case_id]
        if (self.family, self.reason_code, self.terminal_outcome) != expected:
            raise TypingFaultCampaignV1Error("fault disposition differs from PC5 basis")
        _digest(self.boundary_sha256, "boundary_sha256")
        if (
            self.fault_observed is not True
            or self.exception_escaped is not False
            or self.automatic_retry_allowed is not False
            or self.order_preserved is not True
            or self.silent_fallback_used is not False
            or self.bounded_resources is not True
            or self.controller_commands != ()
            or self.hardware_access is not False
            or self.physical_authority is not False
        ):
            raise TypingFaultCampaignV1Error("fault observation violates PC5 invariants")

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "family": self.family,
            "reason_code": self.reason_code,
            "terminal_outcome": self.terminal_outcome,
            "boundary_sha256": self.boundary_sha256,
            "fault_observed": self.fault_observed,
            "exception_escaped": self.exception_escaped,
            "automatic_retry_allowed": self.automatic_retry_allowed,
            "order_preserved": self.order_preserved,
            "silent_fallback_used": self.silent_fallback_used,
            "bounded_resources": self.bounded_resources,
            "controller_commands": [],
            "hardware_access": self.hardware_access,
            "physical_authority": self.physical_authority,
        }


def build_typing_fault_campaign_v1(
    observations: Iterable[TypingFaultObservationV1],
    *,
    qualification_basis_sha256: str,
) -> dict[str, Any]:
    """Build a complete canonical PC5 report without performing any I/O."""

    basis = _digest(qualification_basis_sha256, "qualification_basis_sha256")
    items = tuple(observations)
    if not items or len(items) > MAX_CAMPAIGN_CASES:
        raise TypingFaultCampaignV1Error("campaign case count is outside bounds")
    if any(not isinstance(item, TypingFaultObservationV1) for item in items):
        raise TypeError("observations must contain TypingFaultObservationV1 values")
    by_id = {item.case_id: item for item in items}
    if len(by_id) != len(items):
        raise TypingFaultCampaignV1Error("campaign contains duplicate case ids")
    if set(by_id) != set(REQUIRED_CASES):
        raise TypingFaultCampaignV1Error("campaign does not cover the exact PC5 basis")
    ordered = [by_id[case_id].to_dict() for case_id in sorted(REQUIRED_CASES)]
    families = sorted({item[0] for item in REQUIRED_CASES.values()})
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "qualification_basis_sha256": basis,
        "environment": "SYNTHETIC_OFFLINE_ZERO_IO",
        "family_count": len(families),
        "families": families,
        "case_count": len(ordered),
        "cases": ordered,
        "invariants": {
            "uncaught_exceptions": 0,
            "authority_leaks": 0,
            "automatic_retries": 0,
            "reorders": 0,
            "silent_fallbacks": 0,
            "unbounded_allocations": 0,
            "inconsistent_terminal_outcomes": 0,
        },
        "controller_commands": [],
        "transport_opened": False,
        "transport_write_count": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**report, "typing_fault_campaign_sha256": _sha256(report)}


def parse_typing_fault_campaign_v1(document: Mapping[str, Any]) -> Mapping[str, Any]:
    """Strictly validate and freeze a complete PC5 campaign report."""

    fields = {
        "schema", "status", "qualification_basis_sha256", "environment",
        "family_count", "families", "case_count", "cases", "invariants",
        "controller_commands", "transport_opened", "transport_write_count",
        "hardware_access", "physical_authority", "typing_fault_campaign_sha256",
    }
    if not isinstance(document, Mapping) or set(document) != fields:
        raise TypingFaultCampaignV1Error("campaign fields are not exact")
    unsigned = dict(document)
    claimed = _digest(
        unsigned.pop("typing_fault_campaign_sha256"),
        "typing_fault_campaign_sha256",
    )
    if _sha256(unsigned) != claimed:
        raise TypingFaultCampaignV1Error("campaign hash is invalid")
    if document["schema"] != SCHEMA or document["status"] != STATUS:
        raise TypingFaultCampaignV1Error("campaign schema or status is invalid")
    if document["environment"] != "SYNTHETIC_OFFLINE_ZERO_IO":
        raise TypingFaultCampaignV1Error("campaign environment is invalid")
    _digest(document["qualification_basis_sha256"], "qualification_basis_sha256")
    cases = document["cases"]
    if not isinstance(cases, list) or len(cases) > MAX_CAMPAIGN_CASES:
        raise TypingFaultCampaignV1Error("campaign cases are not bounded")
    observations: list[TypingFaultObservationV1] = []
    case_fields = set(TypingFaultObservationV1(
        case_id="INPUT_MALFORMED", family="MODEL_INPUT",
        reason_code="INPUT_MALFORMED", terminal_outcome=REJECTED,
        boundary_sha256="0" * 64,
    ).to_dict())
    for item in cases:
        if not isinstance(item, Mapping) or set(item) != case_fields:
            raise TypingFaultCampaignV1Error("campaign case fields are not exact")
        observations.append(TypingFaultObservationV1(
            case_id=item["case_id"], family=item["family"],
            reason_code=item["reason_code"], terminal_outcome=item["terminal_outcome"],
            boundary_sha256=item["boundary_sha256"],
            fault_observed=item["fault_observed"],
            exception_escaped=item["exception_escaped"],
            automatic_retry_allowed=item["automatic_retry_allowed"],
            order_preserved=item["order_preserved"],
            silent_fallback_used=item["silent_fallback_used"],
            bounded_resources=item["bounded_resources"],
            controller_commands=tuple(item["controller_commands"])
            if isinstance(item["controller_commands"], list) else (object(),),
            hardware_access=item["hardware_access"],
            physical_authority=item["physical_authority"],
        ))
    rebuilt = build_typing_fault_campaign_v1(
        observations,
        qualification_basis_sha256=document["qualification_basis_sha256"],
    )
    if rebuilt != dict(document):
        raise TypingFaultCampaignV1Error("campaign summary is inconsistent")
    frozen = dict(document)
    frozen["families"] = tuple(document["families"])
    frozen["cases"] = tuple(MappingProxyType(dict(item)) for item in cases)
    frozen["invariants"] = MappingProxyType(dict(document["invariants"]))
    frozen["controller_commands"] = ()
    return MappingProxyType(frozen)


def build_typing_fault_observation_cache_v1(
    observations: Iterable[TypingFaultObservationV1],
    *,
    qualification_basis_sha256: str,
) -> dict[str, Any]:
    """Seal a bounded evidence cache; it cannot carry execution authority."""

    basis = _digest(qualification_basis_sha256, "qualification_basis_sha256")
    items = tuple(observations)
    if len(items) > MAX_CAMPAIGN_CASES:
        raise TypingFaultCampaignV1Error("fault cache exceeds bounded capacity")
    if any(not isinstance(item, TypingFaultObservationV1) for item in items):
        raise TypeError("observations must contain TypingFaultObservationV1 values")
    if len({item.case_id for item in items}) != len(items):
        raise TypingFaultCampaignV1Error("fault cache contains duplicate case ids")
    entries = []
    for item in sorted(items, key=lambda value: value.case_id):
        observation = item.to_dict()
        entries.append({
            "case_id": item.case_id,
            "observation": observation,
            "entry_sha256": _sha256(observation),
        })
    cache: dict[str, Any] = {
        "schema": CACHE_SCHEMA,
        "qualification_basis_sha256": basis,
        "entry_count": len(entries),
        "entries": entries,
        "controller_commands": [],
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**cache, "fault_cache_sha256": _sha256(cache)}


def parse_typing_fault_observation_cache_v1(
    document: Mapping[str, Any],
    *,
    expected_qualification_basis_sha256: str,
) -> Mapping[str, Any]:
    """Reject corrupt or identity-crossed cached campaign observations."""

    expected_basis = _digest(
        expected_qualification_basis_sha256,
        "expected_qualification_basis_sha256",
    )
    fields = {
        "schema", "qualification_basis_sha256", "entry_count", "entries",
        "controller_commands", "hardware_access", "physical_authority",
        "fault_cache_sha256",
    }
    if not isinstance(document, Mapping) or set(document) != fields:
        raise TypingFaultCampaignV1Error("fault cache fields are not exact")
    unsigned = dict(document)
    claimed = _digest(unsigned.pop("fault_cache_sha256"), "fault_cache_sha256")
    if _sha256(unsigned) != claimed:
        raise TypingFaultCampaignV1Error("fault cache hash is invalid")
    if document["schema"] != CACHE_SCHEMA:
        raise TypingFaultCampaignV1Error("fault cache schema is invalid")
    basis = _digest(document["qualification_basis_sha256"],
                    "qualification_basis_sha256")
    if basis != expected_basis:
        raise TypingFaultCampaignV1Error("fault cache qualification identity is crossed")
    entries = document["entries"]
    if (
        not isinstance(entries, list)
        or len(entries) > MAX_CAMPAIGN_CASES
        or not isinstance(document["entry_count"], int)
        or isinstance(document["entry_count"], bool)
        or document["entry_count"] != len(entries)
    ):
        raise TypingFaultCampaignV1Error("fault cache accounting is invalid")
    observations: list[TypingFaultObservationV1] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {
            "case_id", "observation", "entry_sha256"
        }:
            raise TypingFaultCampaignV1Error("fault cache entry fields are not exact")
        observation = entry["observation"]
        if (
            not isinstance(observation, Mapping)
            or set(observation) != _OBSERVATION_FIELDS
        ):
            raise TypingFaultCampaignV1Error(
                "fault cache observation fields are not exact")
        if _digest(entry["entry_sha256"], "entry_sha256") != _sha256(observation):
            raise TypingFaultCampaignV1Error("fault cache entry hash is invalid")
        if (
            not isinstance(entry["case_id"], str)
            or entry["case_id"] != observation.get("case_id")
            or entry["case_id"] in seen
        ):
            raise TypingFaultCampaignV1Error("fault cache case identity is invalid")
        seen.add(entry["case_id"])
        observations.append(TypingFaultObservationV1(
            case_id=observation["case_id"], family=observation["family"],
            reason_code=observation["reason_code"],
            terminal_outcome=observation["terminal_outcome"],
            boundary_sha256=observation["boundary_sha256"],
            fault_observed=observation["fault_observed"],
            exception_escaped=observation["exception_escaped"],
            automatic_retry_allowed=observation["automatic_retry_allowed"],
            order_preserved=observation["order_preserved"],
            silent_fallback_used=observation["silent_fallback_used"],
            bounded_resources=observation["bounded_resources"],
            controller_commands=tuple(observation["controller_commands"])
            if isinstance(observation["controller_commands"], list) else (object(),),
            hardware_access=observation["hardware_access"],
            physical_authority=observation["physical_authority"],
        ))
    if [item.case_id for item in observations] != sorted(seen):
        raise TypingFaultCampaignV1Error("fault cache entry order is invalid")
    if (
        document["controller_commands"] != []
        or document["hardware_access"] is not False
        or document["physical_authority"] is not False
    ):
        raise TypingFaultCampaignV1Error("fault cache violates zero authority")
    frozen = dict(document)
    frozen["entries"] = tuple(MappingProxyType({
        **dict(item),
        "observation": MappingProxyType(dict(item["observation"])),
    }) for item in entries)
    frozen["controller_commands"] = ()
    return MappingProxyType(frozen)


__all__ = [
    "CACHE_SCHEMA", "MAX_CAMPAIGN_CASES", "REJECTED", "REQUIRED_CASES",
    "SCHEMA", "STATUS",
    "UNCERTAIN", "TypingFaultCampaignV1Error", "TypingFaultObservationV1",
    "build_typing_fault_campaign_v1", "build_typing_fault_observation_cache_v1",
    "parse_typing_fault_campaign_v1", "parse_typing_fault_observation_cache_v1",
]
