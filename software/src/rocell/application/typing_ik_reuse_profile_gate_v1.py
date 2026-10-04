"""Frozen zero-authority eligibility gate for exact-input typing IK reuse."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Mapping

from .context import SimulationContext
from .context_lifecycle_v1 import SimulationContextLifecycleV1

SCHEMA = "rocell.typing_ik_reuse_profile_decision.v1"
ELIGIBLE = "EXACT_INPUT_REUSE_SHADOW_ELIGIBLE"
FULL_SOLVE_ONLY = "FULL_SOLVE_ONLY"
_HASH = re.compile(r"^[0-9a-f]{64}$")
QUALIFIED_EVIDENCE_SHA256 = {
    "typing_exact_ik_cache_benchmark_v1":
        "6ad55c649fc37a9215264e124b9d7f10edf2bc405de0d559b7290de7de1bd7cf",
    "typing_exact_ik_cache_owner_campaign_v1":
        "a644c5b46d6c15d70a3d9a207530620d3e89deb4058baa5937fc3672a016553a",
    "typing_exact_reuse_multisequence_campaign_v1":
        "692b621a6910928507cb5a5f5b3dcfae92d7279a66c7537d3fe0a10752746f22",
    "typing_shadow_service_reuse_campaign_v1":
        "da0277885671a24de19a94b6b627759c3ce80726cf4eb530a5718ce16597c4a0",
}


class TypingIkReuseProfileGateV1Error(ValueError):
    """The proposed reuse profile is structurally unsafe or stale."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingIkReuseProfileGateV1Error(f"{label} must be a SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True)
class FrozenTypingIkReuseProfileV1:
    """Exact identities under which shadow cache reuse was qualified."""

    profile_id: str
    context_epoch_sha256: str
    service_instance_id: str
    generation: int
    build_snapshot_sha256: str
    kinematic_model_sha256: str
    calibration_snapshot_sha256: str
    maximum_entries: int = 256

    @classmethod
    def from_active_context(
        cls, context: SimulationContext, lifecycle: SimulationContextLifecycleV1,
        *, calibration_snapshot_sha256: str,
        profile_id: str = "typing-exact-ik-reuse-v1",
    ) -> "FrozenTypingIkReuseProfileV1":
        with lifecycle.validation_scope(context) as binding:
            return cls(
                profile_id=profile_id,
                context_epoch_sha256=binding.context_epoch_sha256,
                service_instance_id=binding.service_instance_id,
                generation=binding.generation,
                build_snapshot_sha256=context.snapshot.snapshot_hash,
                kinematic_model_sha256=context.scenario.model_sha256,
                calibration_snapshot_sha256=_digest(
                    calibration_snapshot_sha256, "calibration snapshot"
                ),
            ).validated()

    def validated(self) -> "FrozenTypingIkReuseProfileV1":
        if not isinstance(self.profile_id, str) or not self.profile_id:
            raise TypingIkReuseProfileGateV1Error("profile id is invalid")
        for value, label in (
            (self.context_epoch_sha256, "context epoch"),
            (self.build_snapshot_sha256, "build snapshot"),
            (self.kinematic_model_sha256, "kinematic model"),
            (self.calibration_snapshot_sha256, "calibration snapshot"),
        ):
            _digest(value, label)
        if not isinstance(self.service_instance_id, str) or not self.service_instance_id:
            raise TypingIkReuseProfileGateV1Error("service instance id is invalid")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation < 0:
            raise TypingIkReuseProfileGateV1Error("generation is invalid")
        if self.maximum_entries != 256:
            raise TypingIkReuseProfileGateV1Error("maximum entries must equal qualified bound 256")
        return self

    @property
    def profile_sha256(self) -> str:
        return _sha({
            "schema": "rocell.frozen_typing_ik_reuse_profile.v1",
            "profile_id": self.profile_id,
            "context_epoch_sha256": self.context_epoch_sha256,
            "service_instance_id": self.service_instance_id,
            "generation": self.generation,
            "build_snapshot_sha256": self.build_snapshot_sha256,
            "kinematic_model_sha256": self.kinematic_model_sha256,
            "calibration_snapshot_sha256": self.calibration_snapshot_sha256,
            "maximum_entries": self.maximum_entries,
        })


def evaluate_typing_ik_reuse_profile_v1(
    profile: FrozenTypingIkReuseProfileV1,
    context: SimulationContext,
    lifecycle: SimulationContextLifecycleV1,
    *, calibration_snapshot_sha256: str,
    evidence_sha256: Mapping[str, str],
    requested_maximum_entries: int = 256,
    complete_solve_fallback_required: bool = True,
    automatic_retry_allowed: bool = False,
) -> dict[str, object]:
    """Evaluate shadow eligibility without opening hardware or admitting motion."""

    if not isinstance(profile, FrozenTypingIkReuseProfileV1):
        raise TypingIkReuseProfileGateV1Error("profile has the wrong type")
    profile.validated()
    if requested_maximum_entries != 256:
        raise TypingIkReuseProfileGateV1Error("requested cache capacity is not qualified")
    if complete_solve_fallback_required is not True:
        raise TypingIkReuseProfileGateV1Error("complete-solve fallback is required")
    if automatic_retry_allowed is not False:
        raise TypingIkReuseProfileGateV1Error("automatic retry is prohibited")
    if not isinstance(evidence_sha256, Mapping):
        raise TypingIkReuseProfileGateV1Error("evidence bundle is invalid")
    evidence = dict(evidence_sha256)
    for name, digest in evidence.items():
        if not isinstance(name, str) or not name:
            raise TypingIkReuseProfileGateV1Error("evidence name is invalid")
        _digest(digest, f"evidence {name}")
    calibration = _digest(calibration_snapshot_sha256, "active calibration snapshot")

    with lifecycle.validation_scope(context) as binding:
        active = {
            "context_epoch_sha256": binding.context_epoch_sha256,
            "service_instance_id": binding.service_instance_id,
            "generation": binding.generation,
            "build_snapshot_sha256": context.snapshot.snapshot_hash,
            "kinematic_model_sha256": context.scenario.model_sha256,
            "calibration_snapshot_sha256": calibration,
        }
        expected = {
            "context_epoch_sha256": profile.context_epoch_sha256,
            "service_instance_id": profile.service_instance_id,
            "generation": profile.generation,
            "build_snapshot_sha256": profile.build_snapshot_sha256,
            "kinematic_model_sha256": profile.kinematic_model_sha256,
            "calibration_snapshot_sha256": profile.calibration_snapshot_sha256,
        }
        blockers = [f"{name.upper()}_MISMATCH" for name in expected
                    if expected[name] != active[name]]
        if evidence != QUALIFIED_EVIDENCE_SHA256:
            blockers.append("QUALIFIED_EVIDENCE_MISMATCH")
        decision = FULL_SOLVE_ONLY if blockers else ELIGIBLE
        core = {
            "schema": SCHEMA,
            "decision": decision,
            "blockers": blockers,
            "profile_id": profile.profile_id,
            "profile_sha256": profile.profile_sha256,
            "active_identities": active,
            "evidence_sha256": evidence,
            "requested_maximum_entries": requested_maximum_entries,
            "exact_solver_input_only": True,
            "endpoint_only_substitution_authorized": False,
            "complete_solve_fallback_required": True,
            "automatic_retry_allowed": False,
            "candidate_used_for_admission": False,
            "controller_opened": False,
            "transport_opened": False,
            "controller_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "physical_authority": False,
        }
        return {**core, "decision_sha256": _sha(core)}


__all__ = [
    "ELIGIBLE", "FULL_SOLVE_ONLY", "QUALIFIED_EVIDENCE_SHA256", "SCHEMA",
    "FrozenTypingIkReuseProfileV1", "TypingIkReuseProfileGateV1Error",
    "evaluate_typing_ik_reuse_profile_v1",
]
