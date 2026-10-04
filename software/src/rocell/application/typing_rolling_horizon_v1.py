"""One-action typing commit/preview state with fail-closed restart handling.

This module is an orchestration boundary only.  It never issues a permit,
encodes a controller command, opens a transport, or retries an action.  Its
durable documents make the distinction between safe pre-dispatch recovery and
an ambiguous post-intent restart explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from .typing_execution_plan_v1 import TypingExecutionPlanV1


SCHEMA = "rocell.typing_rolling_horizon.v1"
BINDING_SCHEMA = "rocell.typing_observed_execution_binding.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PHASES = {
    "PRE_DISPATCH",
    "RECONSTRUCTED_PRE_DISPATCH",
    "DISPATCH_INTENT_RETAINED",
    "COMPLETED",
    "INVALIDATED",
    "OUTCOME_UNCERTAIN",
}
_INVALIDATION_REASONS = {
    "OBSERVED_STATE_DRIFT",
    "CALIBRATION_CHANGED",
    "TOOL_PROFILE_CHANGED",
    "DYNAMICS_PROFILE_CHANGED",
    "CONFIGURATION_EPOCH_CHANGED",
    "EVIDENCE_STALE",
    "CONTROLLER_SESSION_CHANGED",
    "CANCELLED",
    "DEADLINE_EXPIRED",
}


class TypingRollingHorizonV1Error(ValueError):
    """A rolling-horizon document or transition is invalid."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingRollingHorizonV1Error("value is not canonical JSON") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise TypingRollingHorizonV1Error(f"{label} must be a SHA-256 digest")
    return value


def _positive_ns(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TypingRollingHorizonV1Error(f"{label} must be positive nanoseconds")
    return value


@dataclass(frozen=True, slots=True)
class TypingObservedExecutionBindingV1:
    observed_start_state_sha256: str
    feedback_receipt_sha256: str
    configuration_epoch_sha256: str
    calibration_snapshot_sha256: str
    tool_profile_sha256: str
    dynamics_profile_sha256: str
    controller_session_id: str
    valid_until_monotonic_ns: int
    schema: str = BINDING_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != BINDING_SCHEMA:
            raise TypingRollingHorizonV1Error("unsupported binding schema")
        for field in (
            "observed_start_state_sha256", "feedback_receipt_sha256",
            "configuration_epoch_sha256", "calibration_snapshot_sha256",
            "tool_profile_sha256", "dynamics_profile_sha256",
        ):
            _digest(getattr(self, field), field)
        if (
            not isinstance(self.controller_session_id, str)
            or not self.controller_session_id.strip()
            or len(self.controller_session_id) > 128
        ):
            raise TypingRollingHorizonV1Error("controller_session_id is invalid")
        _positive_ns(self.valid_until_monotonic_ns, "valid_until_monotonic_ns")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "observed_start_state_sha256": self.observed_start_state_sha256,
            "feedback_receipt_sha256": self.feedback_receipt_sha256,
            "configuration_epoch_sha256": self.configuration_epoch_sha256,
            "calibration_snapshot_sha256": self.calibration_snapshot_sha256,
            "tool_profile_sha256": self.tool_profile_sha256,
            "dynamics_profile_sha256": self.dynamics_profile_sha256,
            "controller_session_id": self.controller_session_id,
            "valid_until_monotonic_ns": self.valid_until_monotonic_ns,
        }

    @property
    def binding_sha256(self) -> str:
        return _sha256(self.to_dict())

    @classmethod
    def from_mapping(cls, value: object) -> "TypingObservedExecutionBindingV1":
        fields = {
            "schema", "observed_start_state_sha256", "feedback_receipt_sha256",
            "configuration_epoch_sha256", "calibration_snapshot_sha256",
            "tool_profile_sha256", "dynamics_profile_sha256",
            "controller_session_id", "valid_until_monotonic_ns",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            raise TypingRollingHorizonV1Error("binding fields are not exact")
        return cls(**{name: value[name] for name in fields})


def _slot(plan: TypingExecutionPlanV1, index: int, *, preview: bool) -> dict[str, object]:
    action = plan.actions[index]
    action_document = action.to_dict()
    return {
        "action_index": index,
        "target_id": action.target_id,
        "action_sha256": _sha256(action_document),
        "proposal_sha256": action.proposal_sha256,
        "role": "PREVIEW" if preview else "CURRENT",
        "permit_id": None,
        "permit_issued": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    document = dict(unsigned)
    document["rolling_horizon_sha256"] = _sha256(unsigned)
    return document


def _base(
    plan: TypingExecutionPlanV1,
    binding: TypingObservedExecutionBindingV1,
    *,
    action_index: int,
    phase: str,
    deadline_monotonic_ns: int,
    current: Mapping[str, Any] | None,
    preview: Mapping[str, Any] | None,
    dispatch_intent_sha256: str | None = None,
    completion_receipt_sha256: str | None = None,
    invalidation_reason: str | None = None,
    restart_reconciliation: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "phase": phase,
        "request_id": plan.request_id,
        "plan_sha256": plan.plan_sha256,
        "configuration_epoch_sha256": binding.configuration_epoch_sha256,
        "binding": binding.to_dict(),
        "binding_sha256": binding.binding_sha256,
        "action_count": len(plan.actions),
        "action_index": action_index,
        "current": None if current is None else dict(current),
        "preview": None if preview is None else dict(preview),
        "deadline_monotonic_ns": deadline_monotonic_ns,
        "dispatch_intent_sha256": dispatch_intent_sha256,
        "completion_receipt_sha256": completion_receipt_sha256,
        "invalidation_reason": invalidation_reason,
        "restart_reconciliation": restart_reconciliation,
        "commit_horizon": 1,
        "preview_horizon": 1,
        "automatic_retry_allowed": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }


def prepare_typing_rolling_horizon_v1(
    plan: TypingExecutionPlanV1,
    binding: TypingObservedExecutionBindingV1,
    *,
    action_index: int,
    now_monotonic_ns: int,
    deadline_monotonic_ns: int,
) -> dict[str, Any]:
    """Prepare one current action and at most one zero-authority preview."""

    if not isinstance(plan, TypingExecutionPlanV1):
        raise TypeError("plan must be a TypingExecutionPlanV1")
    if not isinstance(binding, TypingObservedExecutionBindingV1):
        raise TypeError("binding must be a TypingObservedExecutionBindingV1")
    now = _positive_ns(now_monotonic_ns, "now_monotonic_ns")
    deadline = _positive_ns(deadline_monotonic_ns, "deadline_monotonic_ns")
    if isinstance(action_index, bool) or not isinstance(action_index, int) or not (
        0 <= action_index < len(plan.actions)
    ):
        raise TypingRollingHorizonV1Error("action_index is outside the plan")
    if binding.calibration_snapshot_sha256 != plan.config.calibration_snapshot_sha256:
        raise TypingRollingHorizonV1Error("binding calibration differs from plan")
    if binding.tool_profile_sha256 != plan.config.tool_profile_sha256:
        raise TypingRollingHorizonV1Error("binding tool profile differs from plan")
    if binding.dynamics_profile_sha256 != plan.config.dynamics_profile_sha256:
        raise TypingRollingHorizonV1Error("binding dynamics profile differs from plan")
    if now > binding.valid_until_monotonic_ns:
        raise TypingRollingHorizonV1Error("observed evidence is stale")
    if now > deadline:
        raise TypingRollingHorizonV1Error("action deadline has expired")
    current = _slot(plan, action_index, preview=False)
    preview = (
        _slot(plan, action_index + 1, preview=True)
        if action_index + 1 < len(plan.actions)
        else None
    )
    return _seal(_base(
        plan, binding, action_index=action_index, phase="PRE_DISPATCH",
        deadline_monotonic_ns=deadline, current=current, preview=preview,
    ))


def parse_typing_rolling_horizon_v1(document: Mapping[str, Any]) -> Mapping[str, Any]:
    """Strictly validate and freeze one durable rolling-horizon document."""

    fields = {
        "schema", "phase", "request_id", "plan_sha256",
        "configuration_epoch_sha256", "binding", "binding_sha256",
        "action_count", "action_index", "current", "preview",
        "deadline_monotonic_ns", "dispatch_intent_sha256",
        "completion_receipt_sha256", "invalidation_reason",
        "restart_reconciliation", "commit_horizon", "preview_horizon",
        "automatic_retry_allowed", "controller_commands",
        "hardware_commands_generated", "hardware_access", "physical_authority",
        "rolling_horizon_sha256",
    }
    if not isinstance(document, Mapping) or set(document) != fields:
        raise TypingRollingHorizonV1Error("rolling-horizon fields are not exact")
    unsigned = dict(document)
    claimed = _digest(unsigned.pop("rolling_horizon_sha256"), "rolling_horizon_sha256")
    if _sha256(unsigned) != claimed:
        raise TypingRollingHorizonV1Error("rolling-horizon hash is invalid")
    if document["schema"] != SCHEMA or document["phase"] not in _PHASES:
        raise TypingRollingHorizonV1Error("schema or phase is invalid")
    binding = TypingObservedExecutionBindingV1.from_mapping(document["binding"])
    if document["binding_sha256"] != binding.binding_sha256:
        raise TypingRollingHorizonV1Error("binding hash is invalid")
    if document["configuration_epoch_sha256"] != binding.configuration_epoch_sha256:
        raise TypingRollingHorizonV1Error("configuration epoch is crossed")
    _digest(document["plan_sha256"], "plan_sha256")
    _positive_ns(document["deadline_monotonic_ns"], "deadline_monotonic_ns")
    if (
        isinstance(document["action_count"], bool)
        or not isinstance(document["action_count"], int)
        or not 1 <= document["action_count"] <= 64
        or isinstance(document["action_index"], bool)
        or not isinstance(document["action_index"], int)
        or not 0 <= document["action_index"] < document["action_count"]
    ):
        raise TypingRollingHorizonV1Error("action accounting is invalid")
    for name in ("current", "preview"):
        slot = document[name]
        if slot is not None:
            expected = {
                "action_index", "target_id", "action_sha256", "proposal_sha256",
                "role", "permit_id", "permit_issued", "controller_commands",
                "hardware_commands_generated", "hardware_access", "physical_authority",
            }
            if not isinstance(slot, Mapping) or set(slot) != expected:
                raise TypingRollingHorizonV1Error(f"{name} slot fields are not exact")
            _digest(slot["action_sha256"], f"{name}.action_sha256")
            _digest(slot["proposal_sha256"], f"{name}.proposal_sha256")
            if (
                slot["role"] != ("CURRENT" if name == "current" else "PREVIEW")
                or slot["permit_id"] is not None
                or slot["permit_issued"] is not False
                or slot["controller_commands"] != []
                or slot["hardware_commands_generated"] != 0
                or slot["hardware_access"] is not False
                or slot["physical_authority"] is not False
            ):
                raise TypingRollingHorizonV1Error(f"{name} slot grants authority")
    current = document["current"]
    preview = document["preview"]
    if current is not None and current["action_index"] != document["action_index"]:
        raise TypingRollingHorizonV1Error("current slot index is crossed")
    if preview is not None and (
        preview["action_index"] != document["action_index"] + 1
        or preview["action_index"] >= document["action_count"]
    ):
        raise TypingRollingHorizonV1Error("preview slot index is crossed")
    phase = document["phase"]
    if phase in {"PRE_DISPATCH", "RECONSTRUCTED_PRE_DISPATCH"}:
        if document["current"] is None or document["dispatch_intent_sha256"] is not None:
            raise TypingRollingHorizonV1Error("pre-dispatch state is inconsistent")
    if phase == "DISPATCH_INTENT_RETAINED":
        _digest(document["dispatch_intent_sha256"], "dispatch_intent_sha256")
        if document["current"] is None or document["preview"] is not None:
            raise TypingRollingHorizonV1Error("dispatch-intent state is inconsistent")
    if phase == "COMPLETED":
        _digest(document["completion_receipt_sha256"], "completion_receipt_sha256")
    if phase in {"INVALIDATED", "OUTCOME_UNCERTAIN", "COMPLETED"} and document["preview"] is not None:
        raise TypingRollingHorizonV1Error("terminal state retains a preview")
    if phase == "INVALIDATED" and document["invalidation_reason"] not in _INVALIDATION_REASONS:
        raise TypingRollingHorizonV1Error("invalidation reason is invalid")
    if phase == "OUTCOME_UNCERTAIN" and document["restart_reconciliation"] != "POST_DISPATCH_OR_AMBIGUOUS_RESTART_RETRY_FORBIDDEN":
        raise TypingRollingHorizonV1Error("uncertain restart disposition is invalid")
    if (
        document["commit_horizon"] != 1
        or document["preview_horizon"] != 1
        or document["automatic_retry_allowed"] is not False
        or document["controller_commands"] != []
        or document["hardware_commands_generated"] != 0
        or document["hardware_access"] is not False
        or document["physical_authority"] is not False
    ):
        raise TypingRollingHorizonV1Error("rolling horizon violates zero authority")
    frozen = dict(document)
    frozen["binding"] = MappingProxyType(dict(document["binding"]))
    frozen["current"] = None if document["current"] is None else MappingProxyType(dict(document["current"]))
    frozen["preview"] = None if document["preview"] is None else MappingProxyType(dict(document["preview"]))
    frozen["controller_commands"] = ()
    return MappingProxyType(frozen)


def revalidate_typing_rolling_horizon_v1(
    document: Mapping[str, Any],
    binding: TypingObservedExecutionBindingV1,
    *,
    now_monotonic_ns: int,
) -> dict[str, Any]:
    """Revalidate exact live lineage or emit one deterministic invalidation.

    A changed binding never silently replaces the binding beneath an already
    prepared current action.  The caller must create a fresh horizon after the
    invalidation is durably recorded.
    """

    state = parse_typing_rolling_horizon_v1(document)
    if not isinstance(binding, TypingObservedExecutionBindingV1):
        raise TypeError("binding must be a TypingObservedExecutionBindingV1")
    if state["phase"] not in {"PRE_DISPATCH", "RECONSTRUCTED_PRE_DISPATCH"}:
        raise TypingRollingHorizonV1Error("only pre-dispatch state may be revalidated")
    now = _positive_ns(now_monotonic_ns, "now_monotonic_ns")
    old = state["binding"]
    comparisons = (
        ("controller_session_id", "CONTROLLER_SESSION_CHANGED"),
        ("configuration_epoch_sha256", "CONFIGURATION_EPOCH_CHANGED"),
        ("calibration_snapshot_sha256", "CALIBRATION_CHANGED"),
        ("tool_profile_sha256", "TOOL_PROFILE_CHANGED"),
        ("dynamics_profile_sha256", "DYNAMICS_PROFILE_CHANGED"),
        ("observed_start_state_sha256", "OBSERVED_STATE_DRIFT"),
        ("feedback_receipt_sha256", "OBSERVED_STATE_DRIFT"),
    )
    for field, reason in comparisons:
        if old[field] != getattr(binding, field):
            return invalidate_typing_rolling_horizon_v1(document, reason=reason)
    if now > old["valid_until_monotonic_ns"] or now > binding.valid_until_monotonic_ns:
        return invalidate_typing_rolling_horizon_v1(document, reason="EVIDENCE_STALE")
    if now > state["deadline_monotonic_ns"]:
        return invalidate_typing_rolling_horizon_v1(document, reason="DEADLINE_EXPIRED")
    return dict(document)


def invalidate_typing_rolling_horizon_v1(
    document: Mapping[str, Any], *, reason: str,
) -> dict[str, Any]:
    state = parse_typing_rolling_horizon_v1(document)
    if reason not in _INVALIDATION_REASONS:
        raise TypingRollingHorizonV1Error("invalidation reason is invalid")
    if state["phase"] not in {"PRE_DISPATCH", "RECONSTRUCTED_PRE_DISPATCH"}:
        raise TypingRollingHorizonV1Error("only pre-dispatch state may be invalidated")
    unsigned = {key: (list(value) if key == "controller_commands" else value)
                for key, value in state.items() if key != "rolling_horizon_sha256"}
    unsigned["binding"] = dict(state["binding"])
    unsigned["current"] = None
    unsigned["preview"] = None
    unsigned["phase"] = "INVALIDATED"
    unsigned["invalidation_reason"] = reason
    return _seal(unsigned)


def retain_typing_dispatch_intent_v1(
    document: Mapping[str, Any], *, dispatch_intent_sha256: str,
) -> dict[str, Any]:
    state = parse_typing_rolling_horizon_v1(document)
    intent = _digest(dispatch_intent_sha256, "dispatch_intent_sha256")
    if state["phase"] not in {"PRE_DISPATCH", "RECONSTRUCTED_PRE_DISPATCH"}:
        raise TypingRollingHorizonV1Error("dispatch intent requires pre-dispatch state")
    unsigned = {key: (list(value) if key == "controller_commands" else value)
                for key, value in state.items() if key != "rolling_horizon_sha256"}
    unsigned["binding"] = dict(state["binding"])
    unsigned["current"] = dict(state["current"])
    unsigned["preview"] = None
    unsigned["phase"] = "DISPATCH_INTENT_RETAINED"
    unsigned["dispatch_intent_sha256"] = intent
    return _seal(unsigned)


def complete_typing_current_action_v1(
    document: Mapping[str, Any], *, completion_receipt_sha256: str,
) -> dict[str, Any]:
    state = parse_typing_rolling_horizon_v1(document)
    completion = _digest(completion_receipt_sha256, "completion_receipt_sha256")
    if state["phase"] != "DISPATCH_INTENT_RETAINED":
        raise TypingRollingHorizonV1Error("completion requires retained dispatch intent")
    unsigned = {key: (list(value) if key == "controller_commands" else value)
                for key, value in state.items() if key != "rolling_horizon_sha256"}
    unsigned["binding"] = dict(state["binding"])
    unsigned["current"] = dict(state["current"])
    unsigned["phase"] = "COMPLETED"
    unsigned["completion_receipt_sha256"] = completion
    return _seal(unsigned)


def reconcile_typing_restart_v1(document: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct only pre-dispatch intent; never replay possible dispatch."""

    state = parse_typing_rolling_horizon_v1(document)
    phase = state["phase"]
    if phase in {"PRE_DISPATCH", "RECONSTRUCTED_PRE_DISPATCH"}:
        target_phase = "RECONSTRUCTED_PRE_DISPATCH"
        disposition = "PRE_DISPATCH_INTENT_RECONSTRUCTED_NO_REPLAY"
    elif phase == "DISPATCH_INTENT_RETAINED":
        target_phase = "OUTCOME_UNCERTAIN"
        disposition = "POST_DISPATCH_OR_AMBIGUOUS_RESTART_RETRY_FORBIDDEN"
    else:
        raise TypingRollingHorizonV1Error("terminal state cannot be restart-reconciled")
    unsigned = {key: (list(value) if key == "controller_commands" else value)
                for key, value in state.items() if key != "rolling_horizon_sha256"}
    unsigned["binding"] = dict(state["binding"])
    unsigned["current"] = None if state["current"] is None else dict(state["current"])
    unsigned["preview"] = (
        None if target_phase == "OUTCOME_UNCERTAIN" or state["preview"] is None
        else dict(state["preview"])
    )
    unsigned["phase"] = target_phase
    unsigned["restart_reconciliation"] = disposition
    return _seal(unsigned)


__all__ = [
    "BINDING_SCHEMA", "SCHEMA", "TypingObservedExecutionBindingV1",
    "TypingRollingHorizonV1Error", "complete_typing_current_action_v1",
    "invalidate_typing_rolling_horizon_v1", "parse_typing_rolling_horizon_v1",
    "prepare_typing_rolling_horizon_v1", "reconcile_typing_restart_v1",
    "retain_typing_dispatch_intent_v1", "revalidate_typing_rolling_horizon_v1",
]
