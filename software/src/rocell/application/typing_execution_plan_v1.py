"""Deterministic, zero-authority typing sequence optimization.

This module consumes an already admitted v2 model batch.  It amortizes static
batch work, preserves the exact semantic action order, and constructs direct
hover-to-hover transitions for offline comparison with a park-between-key
baseline.  It does not solve IK, create an execution envelope, encode controller
commands, access hardware, or grant physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from rocell.models import (
    Interaction,
    ModelMotionBatchV2,
    Point3Mm,
    ProposalDevice,
    ProposalFrame,
    SpeedClass,
)


SCHEMA = "rocell.typing_execution_plan.v1"
CONFIG_SCHEMA = "rocell.typing_execution_config.v1"
ACTION_SCHEMA = "rocell.typing_execution_action.v1"
METRICS_SCHEMA = "rocell.typing_execution_metrics.v1"
ACCEPTED_INGRESS_STATUS = "ACCEPTED_V2_FOR_FRESH_SEQUENTIAL_PLANNER_GATES"
MAX_ACTIONS = 64
MAX_PLAN_BYTES = 1_048_576
EVIDENCE_FLOAT_DECIMAL_PLACES = 9
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class TypingExecutionPlanV1Error(ValueError):
    """The optimized typing plan is malformed, inconsistent, or authoritative."""


class TransitionKindV1(str, Enum):
    START_REFERENCE_TO_HOVER = "START_REFERENCE_TO_HOVER"
    DIRECT_RETRACT_TO_HOVER = "DIRECT_RETRACT_TO_HOVER"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingExecutionPlanV1Error("value is not canonical JSON") from exc


def _strict(value: object, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingExecutionPlanV1Error(
            f"{label} must contain exactly {sorted(fields)}")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise TypingExecutionPlanV1Error(f"{label} must be a lowercase SHA-256 digest")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise TypingExecutionPlanV1Error(f"{label} must be a bounded identifier")
    return value


def _number(
    value: object,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    exclusive_minimum: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypingExecutionPlanV1Error(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise TypingExecutionPlanV1Error(f"{label} must be finite")
    if minimum is not None and (
        result < minimum or (exclusive_minimum and result == minimum)
    ):
        raise TypingExecutionPlanV1Error(f"{label} is below its minimum")
    if maximum is not None and result > maximum:
        raise TypingExecutionPlanV1Error(f"{label} exceeds its maximum")
    return result


def _positive_int(value: object, label: str, *, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise TypingExecutionPlanV1Error(
            f"{label} must be an integer in [1, {maximum}]")
    return value


def _point_dict(point: Point3Mm) -> dict[str, object]:
    return {
        "frame": point.frame,
        "x": float(point.x),
        "y": float(point.y),
        "z": float(point.z),
    }


def _point(value: object, label: str) -> Point3Mm:
    item = _strict(value, {"frame", "x", "y", "z"}, label)
    try:
        point = Point3Mm(str(item["frame"]), item["x"], item["y"], item["z"])
    except (TypeError, ValueError) as exc:
        raise TypingExecutionPlanV1Error(f"{label} is invalid") from exc
    if point.frame != ProposalFrame.BOARD.value:
        raise TypingExecutionPlanV1Error(f"{label} must use the board frame")
    return point


def _distance(left: Point3Mm, right: Point3Mm) -> float:
    if left.frame != right.frame:
        raise TypingExecutionPlanV1Error("transition points use different frames")
    return math.dist((left.x, left.y, left.z), (right.x, right.y, right.z))


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-9)


def _evidence_float(value: float) -> float:
    """Remove sub-nanometre runtime noise from retained aggregate evidence."""
    result = round(float(value), EVIDENCE_FLOAT_DECIMAL_PLACES)
    return 0.0 if result == 0.0 else result


@dataclass(frozen=True, slots=True)
class TypingExecutionConfigV1:
    config_id: str
    calibration_snapshot_sha256: str
    tool_profile_sha256: str
    dynamics_profile_sha256: str
    route_reference_point: Point3Mm
    hover_clearance_mm: float
    settle_position_tolerance_mm: float
    settle_velocity_tolerance_mm_s: float
    settle_hold_ms: int
    preview_horizon: int = 1
    speed_class: SpeedClass = SpeedClass.SLOW
    schema: str = CONFIG_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != CONFIG_SCHEMA:
            raise TypingExecutionPlanV1Error("unsupported typing execution config schema")
        _identifier(self.config_id, "config_id")
        for field in (
            "calibration_snapshot_sha256",
            "tool_profile_sha256",
            "dynamics_profile_sha256",
        ):
            _digest(getattr(self, field), field)
        if not isinstance(self.route_reference_point, Point3Mm) or (
            self.route_reference_point.frame != ProposalFrame.BOARD.value
        ):
            raise TypingExecutionPlanV1Error(
                "route_reference_point must be a board-frame point")
        object.__setattr__(self, "hover_clearance_mm", _number(
            self.hover_clearance_mm, "hover_clearance_mm", minimum=0.0,
            maximum=100.0, exclusive_minimum=True))
        object.__setattr__(self, "settle_position_tolerance_mm", _number(
            self.settle_position_tolerance_mm, "settle_position_tolerance_mm",
            minimum=0.0, maximum=10.0, exclusive_minimum=True))
        object.__setattr__(self, "settle_velocity_tolerance_mm_s", _number(
            self.settle_velocity_tolerance_mm_s,
            "settle_velocity_tolerance_mm_s", minimum=0.0, maximum=100.0,
            exclusive_minimum=True))
        object.__setattr__(self, "settle_hold_ms", _positive_int(
            self.settle_hold_ms, "settle_hold_ms", maximum=10_000))
        object.__setattr__(self, "preview_horizon", _positive_int(
            self.preview_horizon, "preview_horizon", maximum=2))
        try:
            object.__setattr__(self, "speed_class", SpeedClass(self.speed_class))
        except ValueError as exc:
            raise TypingExecutionPlanV1Error(str(exc)) from exc

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "config_id": self.config_id,
            "calibration_snapshot_sha256": self.calibration_snapshot_sha256,
            "tool_profile_sha256": self.tool_profile_sha256,
            "dynamics_profile_sha256": self.dynamics_profile_sha256,
            "route_reference_point": _point_dict(self.route_reference_point),
            "hover_clearance_mm": self.hover_clearance_mm,
            "settle_position_tolerance_mm": self.settle_position_tolerance_mm,
            "settle_velocity_tolerance_mm_s": self.settle_velocity_tolerance_mm_s,
            "settle_hold_ms": self.settle_hold_ms,
            "preview_horizon": self.preview_horizon,
            "speed_class": self.speed_class.value,
        }

    @property
    def config_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()

    @classmethod
    def from_mapping(cls, value: object) -> "TypingExecutionConfigV1":
        fields = {
            "schema", "config_id", "calibration_snapshot_sha256",
            "tool_profile_sha256", "dynamics_profile_sha256",
            "route_reference_point", "hover_clearance_mm",
            "settle_position_tolerance_mm", "settle_velocity_tolerance_mm_s",
            "settle_hold_ms", "preview_horizon", "speed_class",
        }
        item = _strict(value, fields, "typing execution config")
        return cls(
            schema=item["schema"], config_id=item["config_id"],
            calibration_snapshot_sha256=item["calibration_snapshot_sha256"],
            tool_profile_sha256=item["tool_profile_sha256"],
            dynamics_profile_sha256=item["dynamics_profile_sha256"],
            route_reference_point=_point(
                item["route_reference_point"], "route_reference_point"),
            hover_clearance_mm=item["hover_clearance_mm"],
            settle_position_tolerance_mm=item["settle_position_tolerance_mm"],
            settle_velocity_tolerance_mm_s=item[
                "settle_velocity_tolerance_mm_s"],
            settle_hold_ms=item["settle_hold_ms"],
            preview_horizon=item["preview_horizon"],
            speed_class=item["speed_class"],
        )


@dataclass(frozen=True, slots=True)
class TypingExecutionActionV1:
    action_index: int
    proposal_sha256: str
    target_id: str
    transition_kind: TransitionKindV1
    transition_source: Point3Mm
    hover_point: Point3Mm
    contact_point: Point3Mm
    retract_point: Point3Mm
    incoming_transition_distance_mm: float
    local_cycle_distance_mm: float
    schema: str = ACTION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != ACTION_SCHEMA:
            raise TypingExecutionPlanV1Error("unsupported typing action schema")
        if (
            isinstance(self.action_index, bool)
            or not isinstance(self.action_index, int)
            or not 0 <= self.action_index < MAX_ACTIONS
        ):
            raise TypingExecutionPlanV1Error("action_index is outside the bounded range")
        _digest(self.proposal_sha256, "proposal_sha256")
        _identifier(self.target_id, "target_id")
        try:
            object.__setattr__(self, "transition_kind", TransitionKindV1(
                self.transition_kind))
        except ValueError as exc:
            raise TypingExecutionPlanV1Error(str(exc)) from exc
        for field in (
            "transition_source", "hover_point", "contact_point", "retract_point"
        ):
            value = getattr(self, field)
            if not isinstance(value, Point3Mm) or value.frame != ProposalFrame.BOARD.value:
                raise TypingExecutionPlanV1Error(
                    f"{field} must be a board-frame point")
        incoming = _number(
            self.incoming_transition_distance_mm,
            "incoming_transition_distance_mm", minimum=0.0)
        local = _number(
            self.local_cycle_distance_mm, "local_cycle_distance_mm", minimum=0.0,
            exclusive_minimum=True)
        if not _close(incoming, _distance(self.transition_source, self.hover_point)):
            raise TypingExecutionPlanV1Error("incoming transition distance is inconsistent")
        expected_local = _distance(self.hover_point, self.contact_point) + _distance(
            self.contact_point, self.retract_point)
        if not _close(local, expected_local):
            raise TypingExecutionPlanV1Error("local cycle distance is inconsistent")
        if self.hover_point != self.retract_point:
            raise TypingExecutionPlanV1Error("v1 retract point must equal hover point")
        object.__setattr__(self, "incoming_transition_distance_mm", incoming)
        object.__setattr__(self, "local_cycle_distance_mm", local)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "action_index": self.action_index,
            "proposal_sha256": self.proposal_sha256,
            "target_id": self.target_id,
            "transition_kind": self.transition_kind.value,
            "transition_source": _point_dict(self.transition_source),
            "hover_point": _point_dict(self.hover_point),
            "contact_point": _point_dict(self.contact_point),
            "retract_point": _point_dict(self.retract_point),
            "incoming_transition_distance_mm": self.incoming_transition_distance_mm,
            "local_cycle_distance_mm": self.local_cycle_distance_mm,
        }

    @classmethod
    def from_mapping(cls, value: object) -> "TypingExecutionActionV1":
        fields = {
            "schema", "action_index", "proposal_sha256", "target_id",
            "transition_kind", "transition_source", "hover_point",
            "contact_point", "retract_point", "incoming_transition_distance_mm",
            "local_cycle_distance_mm",
        }
        item = _strict(value, fields, "typing execution action")
        return cls(
            schema=item["schema"], action_index=item["action_index"],
            proposal_sha256=item["proposal_sha256"], target_id=item["target_id"],
            transition_kind=item["transition_kind"],
            transition_source=_point(item["transition_source"], "transition_source"),
            hover_point=_point(item["hover_point"], "hover_point"),
            contact_point=_point(item["contact_point"], "contact_point"),
            retract_point=_point(item["retract_point"], "retract_point"),
            incoming_transition_distance_mm=item[
                "incoming_transition_distance_mm"],
            local_cycle_distance_mm=item["local_cycle_distance_mm"],
        )


@dataclass(frozen=True, slots=True)
class TypingExecutionMetricsV1:
    direct_transit_distance_mm: float
    park_transit_distance_mm: float
    local_cycle_distance_mm: float
    direct_total_distance_mm: float
    park_total_distance_mm: float
    distance_saved_mm: float
    distance_reduction_fraction: float
    schema: str = METRICS_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != METRICS_SCHEMA:
            raise TypingExecutionPlanV1Error("unsupported typing metrics schema")
        for field in (
            "direct_transit_distance_mm", "park_transit_distance_mm",
            "local_cycle_distance_mm", "direct_total_distance_mm",
            "park_total_distance_mm", "distance_saved_mm",
            "distance_reduction_fraction",
        ):
            maximum = 1.0 if field == "distance_reduction_fraction" else None
            object.__setattr__(self, field, _number(
                getattr(self, field), field, minimum=0.0, maximum=maximum))
        if not _close(
            self.direct_total_distance_mm,
            self.direct_transit_distance_mm + self.local_cycle_distance_mm,
        ):
            raise TypingExecutionPlanV1Error("direct distance metrics are inconsistent")
        if not _close(
            self.park_total_distance_mm,
            self.park_transit_distance_mm + self.local_cycle_distance_mm,
        ):
            raise TypingExecutionPlanV1Error("park distance metrics are inconsistent")
        if not _close(
            self.distance_saved_mm,
            self.park_total_distance_mm - self.direct_total_distance_mm,
        ):
            raise TypingExecutionPlanV1Error("distance savings are inconsistent")
        expected_fraction = (
            self.distance_saved_mm / self.park_total_distance_mm
            if self.park_total_distance_mm else 0.0
        )
        if not _close(self.distance_reduction_fraction, expected_fraction):
            raise TypingExecutionPlanV1Error("distance reduction is inconsistent")

    def to_dict(self) -> dict[str, object]:
        return {"schema": self.schema, **{
            field: getattr(self, field)
            for field in self.__dataclass_fields__ if field != "schema"
        }}

    @classmethod
    def from_mapping(cls, value: object) -> "TypingExecutionMetricsV1":
        fields = {
            "schema", "direct_transit_distance_mm", "park_transit_distance_mm",
            "local_cycle_distance_mm", "direct_total_distance_mm",
            "park_total_distance_mm", "distance_saved_mm",
            "distance_reduction_fraction",
        }
        item = _strict(value, fields, "typing execution metrics")
        return cls(**{field: item[field] for field in fields})


@dataclass(frozen=True, slots=True)
class TypingExecutionPlanV1:
    request_id: str
    intent_plan_sha256: str
    batch_sha256: str
    ingress_sha256: str
    config: TypingExecutionConfigV1
    actions: tuple[TypingExecutionActionV1, ...]
    metrics: TypingExecutionMetricsV1
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise TypingExecutionPlanV1Error("unsupported typing execution plan schema")
        _identifier(self.request_id, "request_id")
        for field in ("intent_plan_sha256", "batch_sha256", "ingress_sha256"):
            _digest(getattr(self, field), field)
        if not isinstance(self.config, TypingExecutionConfigV1):
            raise TypingExecutionPlanV1Error("config has the wrong type")
        actions = tuple(self.actions)
        if not 1 <= len(actions) <= MAX_ACTIONS or any(
            not isinstance(item, TypingExecutionActionV1) for item in actions
        ):
            raise TypingExecutionPlanV1Error("actions must contain 1 to 64 items")
        if tuple(item.action_index for item in actions) != tuple(range(len(actions))):
            raise TypingExecutionPlanV1Error("action indexes must be ordered and contiguous")
        if actions[0].transition_kind is not TransitionKindV1.START_REFERENCE_TO_HOVER:
            raise TypingExecutionPlanV1Error("first transition must start at the reference")
        if actions[0].transition_source != self.config.route_reference_point:
            raise TypingExecutionPlanV1Error("first action uses a different reference point")
        for previous, current in zip(actions, actions[1:]):
            if current.transition_kind is not TransitionKindV1.DIRECT_RETRACT_TO_HOVER:
                raise TypingExecutionPlanV1Error("later actions must use direct transitions")
            if current.transition_source != previous.retract_point:
                raise TypingExecutionPlanV1Error("direct transition chain is discontinuous")
        for action in actions:
            if not (
                _close(action.hover_point.x, action.contact_point.x)
                and _close(action.hover_point.y, action.contact_point.y)
                and _close(action.hover_point.z, (
                    action.contact_point.z + self.config.hover_clearance_mm))
            ):
                raise TypingExecutionPlanV1Error(
                    "hover point differs from configured target clearance")
        if not isinstance(self.metrics, TypingExecutionMetricsV1):
            raise TypingExecutionPlanV1Error("metrics have the wrong type")
        expected = _metrics(actions, self.config.route_reference_point)
        if self.metrics.to_dict() != expected.to_dict():
            raise TypingExecutionPlanV1Error("plan metrics do not match the action chain")
        object.__setattr__(self, "actions", actions)

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "request_id": self.request_id,
            "intent_plan_sha256": self.intent_plan_sha256,
            "batch_sha256": self.batch_sha256,
            "ingress_sha256": self.ingress_sha256,
            "config": self.config.to_dict(),
            "config_sha256": self.config.config_sha256,
            "actions": [item.to_dict() for item in self.actions],
            "metrics": self.metrics.to_dict(),
            "commit_horizon": 1,
            "preview_horizon": self.config.preview_horizon,
            "automatic_retry_allowed": False,
            "controller_commands": [],
            "hardware_commands_generated": 0,
            "hardware_access": False,
            "physical_authority": False,
        }

    @property
    def plan_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.unsigned_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "plan_sha256": self.plan_sha256}

    def to_bytes(self) -> bytes:
        return _canonical(self.to_dict())

    @classmethod
    def from_mapping(cls, value: object) -> "TypingExecutionPlanV1":
        fields = {
            "schema", "request_id", "intent_plan_sha256", "batch_sha256",
            "ingress_sha256", "config", "config_sha256", "actions", "metrics",
            "commit_horizon", "preview_horizon", "automatic_retry_allowed",
            "controller_commands", "hardware_commands_generated", "hardware_access",
            "physical_authority", "plan_sha256",
        }
        item = _strict(value, fields, "typing execution plan")
        if (
            item["commit_horizon"] != 1
            or item["automatic_retry_allowed"] is not False
            or item["controller_commands"] != []
            or item["hardware_commands_generated"] != 0
            or item["hardware_access"] is not False
            or item["physical_authority"] is not False
        ):
            raise TypingExecutionPlanV1Error("typing plan violates zero authority")
        config = TypingExecutionConfigV1.from_mapping(item["config"])
        if item["config_sha256"] != config.config_sha256:
            raise TypingExecutionPlanV1Error("config_sha256 does not match config")
        if item["preview_horizon"] != config.preview_horizon:
            raise TypingExecutionPlanV1Error("preview horizon differs from config")
        raw_actions = item["actions"]
        if not isinstance(raw_actions, Sequence) or isinstance(raw_actions, (str, bytes)):
            raise TypingExecutionPlanV1Error("actions must be an array")
        plan = cls(
            schema=item["schema"], request_id=item["request_id"],
            intent_plan_sha256=item["intent_plan_sha256"],
            batch_sha256=item["batch_sha256"], ingress_sha256=item["ingress_sha256"],
            config=config,
            actions=tuple(TypingExecutionActionV1.from_mapping(action)
                          for action in raw_actions),
            metrics=TypingExecutionMetricsV1.from_mapping(item["metrics"]),
        )
        if _digest(item["plan_sha256"], "plan_sha256") != plan.plan_sha256:
            raise TypingExecutionPlanV1Error("plan_sha256 does not match content")
        return plan

    @classmethod
    def from_bytes(cls, payload: bytes) -> "TypingExecutionPlanV1":
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        if not payload or len(payload) > MAX_PLAN_BYTES:
            raise TypingExecutionPlanV1Error("typing plan payload is empty or oversized")

        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, item in pairs:
                if key in result:
                    raise TypingExecutionPlanV1Error(
                        f"duplicate JSON field {key!r}")
                result[key] = item
            return result

        try:
            value = json.loads(
                payload.decode("utf-8"), object_pairs_hook=unique,
                parse_constant=lambda item: (_ for _ in ()).throw(
                    TypingExecutionPlanV1Error(
                        f"non-finite JSON constant {item!r}")),
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TypingExecutionPlanV1Error(
                "typing plan payload is not strict UTF-8 JSON") from exc
        if _canonical(value) != payload:
            raise TypingExecutionPlanV1Error("typing plan payload is not canonical JSON")
        return cls.from_mapping(value)


def _metrics(
    actions: tuple[TypingExecutionActionV1, ...], reference: Point3Mm,
) -> TypingExecutionMetricsV1:
    direct_transit = sum(item.incoming_transition_distance_mm for item in actions)
    direct_transit += _distance(actions[-1].retract_point, reference)
    park_transit = sum(
        _distance(reference, item.hover_point) + _distance(item.retract_point, reference)
        for item in actions
    )
    local = sum(item.local_cycle_distance_mm for item in actions)
    direct_total = direct_transit + local
    park_total = park_transit + local
    saved = max(0.0, park_total - direct_total)
    fraction = saved / park_total if park_total else 0.0
    return TypingExecutionMetricsV1(
        direct_transit_distance_mm=_evidence_float(direct_transit),
        park_transit_distance_mm=_evidence_float(park_transit),
        local_cycle_distance_mm=_evidence_float(local),
        direct_total_distance_mm=_evidence_float(direct_total),
        park_total_distance_mm=_evidence_float(park_total),
        distance_saved_mm=_evidence_float(saved),
        distance_reduction_fraction=_evidence_float(fraction),
    )


def _validated_ingress_sha256(
    batch: ModelMotionBatchV2, ingress_report: Mapping[str, Any],
) -> str:
    if not isinstance(ingress_report, Mapping):
        raise TypeError("ingress_report must be a mapping")
    claimed = ingress_report.get("ingress_sha256")
    unsigned = {
        key: value for key, value in ingress_report.items()
        if key != "ingress_sha256"
    }
    if not isinstance(claimed, str) or hashlib.sha256(
        _canonical(unsigned)).hexdigest() != claimed:
        raise TypingExecutionPlanV1Error("ingress report content hash is invalid")
    if ingress_report.get("status") != ACCEPTED_INGRESS_STATUS:
        raise TypingExecutionPlanV1Error("ingress report is not accepted")
    if (
        ingress_report.get("batch_sha256") != batch.batch_sha256
        or ingress_report.get("intent_plan_sha256") != batch.intent_plan_sha256
        or ingress_report.get("request_id") != batch.request_id
    ):
        raise TypingExecutionPlanV1Error("ingress report binds a different batch")
    if ingress_report.get("ordered_target_ids") != [
        proposal.target_id for proposal in batch.proposals
    ]:
        raise TypingExecutionPlanV1Error("ingress target order differs from the batch")
    if (
        ingress_report.get("controller_commands") != []
        or ingress_report.get("hardware_commands_generated") != 0
        or ingress_report.get("hardware_access") is not False
        or ingress_report.get("physical_authority") is not False
    ):
        raise TypingExecutionPlanV1Error("ingress report violates zero authority")
    return claimed


def compile_typing_execution_plan_v1(
    batch: ModelMotionBatchV2,
    ingress_report: Mapping[str, Any],
    *,
    config: TypingExecutionConfigV1,
) -> TypingExecutionPlanV1:
    """Compile one admitted keyboard batch into a zero-authority local route plan."""
    if not isinstance(batch, ModelMotionBatchV2):
        raise TypeError("batch must be a ModelMotionBatchV2")
    if not isinstance(config, TypingExecutionConfigV1):
        raise TypeError("config must be a TypingExecutionConfigV1")
    if batch.device is not ProposalDevice.KEYBOARD:
        raise TypingExecutionPlanV1Error("v1 typing execution accepts keyboard batches only")
    if any(proposal.interaction is not Interaction.CONTACT for proposal in batch.proposals):
        raise TypingExecutionPlanV1Error("typing execution requires CONTACT proposals")
    ingress_sha256 = _validated_ingress_sha256(batch, ingress_report)

    actions: list[TypingExecutionActionV1] = []
    source = config.route_reference_point
    for proposal in batch.proposals:
        target = proposal.target
        hover = Point3Mm(
            target.frame, target.x, target.y, target.z + config.hover_clearance_mm)
        kind = (
            TransitionKindV1.START_REFERENCE_TO_HOVER
            if proposal.action_index == 0
            else TransitionKindV1.DIRECT_RETRACT_TO_HOVER
        )
        action = TypingExecutionActionV1(
            action_index=proposal.action_index,
            proposal_sha256=proposal.proposal_sha256,
            target_id=proposal.target_id,
            transition_kind=kind,
            transition_source=source,
            hover_point=hover,
            contact_point=target,
            retract_point=hover,
            incoming_transition_distance_mm=_distance(source, hover),
            local_cycle_distance_mm=2.0 * config.hover_clearance_mm,
        )
        actions.append(action)
        source = action.retract_point
    frozen_actions = tuple(actions)
    return TypingExecutionPlanV1(
        request_id=batch.request_id,
        intent_plan_sha256=batch.intent_plan_sha256,
        batch_sha256=batch.batch_sha256,
        ingress_sha256=ingress_sha256,
        config=config,
        actions=frozen_actions,
        metrics=_metrics(frozen_actions, config.route_reference_point),
    )


__all__ = [
    "SCHEMA",
    "ACTION_SCHEMA",
    "CONFIG_SCHEMA",
    "METRICS_SCHEMA",
    "TransitionKindV1",
    "TypingExecutionActionV1",
    "TypingExecutionConfigV1",
    "TypingExecutionMetricsV1",
    "TypingExecutionPlanV1",
    "TypingExecutionPlanV1Error",
    "compile_typing_execution_plan_v1",
]
