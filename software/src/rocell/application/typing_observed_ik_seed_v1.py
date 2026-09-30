"""Bind fresh physical feedback to one retained typing trajectory IK attempt.

This adapter is the narrow bridge between ARM-147 state qualification and a
future deterministic re-screen of the retained Cartesian typing trajectory.
It authenticates lineage and freshness, but deliberately performs no IK,
collision checking, controller access, or command generation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping

from rocell.calibration import PlannerCalibrationSnapshot
from rocell.kinematics import ARM_JOINT_NAMES

from .context import (
    SimulationContext,
    SimulationContextError,
    revalidate_simulation_context,
)
from .observed_planner_start_state import (
    ObservedPlannerStartState,
    ObservedPlannerStartStateError,
)
from .typing_shadow_materialization_v1 import (
    TypingShadowMaterializationV1Error,
    parse_typing_shadow_materialization_v1,
)
from .typing_state_prerequisite_binding_v1 import (
    TypingStatePrerequisiteBindingV1Error,
    parse_typing_state_prerequisite_binding_v1,
)


SCHEMA = "rocell.typing_observed_ik_seed.v1"
STATUS = "READY_FOR_DETERMINISTIC_OBSERVED_STATE_IK_SCREENING"
SOURCE_KIND = "PHYSICAL_OBSERVED_STATE"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "schema", "status", "source_kind", "request_id",
    "materialization_sha256", "state_binding_sha256",
    "observed_start_state_sha256", "calibration_snapshot_sha256",
    "build_snapshot_sha256", "controller_session_id",
    "available_monotonic_ns", "valid_until_monotonic_ns",
    "joint_positions_rad", "controller_feedback_claimed",
    "physical_measurement_claimed", "ik_screening_completed",
    "collision_qualification_completed", "permit_review_ready",
    "eligible_for_executor", "controller_commands", "wire_commands",
    "hardware_commands_generated", "hardware_access", "physical_authority",
    "observed_ik_seed_sha256",
}


class TypingObservedIkSeedV1Error(ValueError):
    """Observed state cannot seed this retained trajectory exactly."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingObservedIkSeedV1Error(
            "observed IK seed is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise TypingObservedIkSeedV1Error(f"{label} must be a SHA-256 digest")
    return value


def _positive_ns(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TypingObservedIkSeedV1Error(f"{label} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class TypingObservedIkSeedV1:
    """Immutable, fresh-feedback seed with no execution authority."""

    request_id: str
    materialization_sha256: str
    state_binding_sha256: str
    observed_start_state_sha256: str
    calibration_snapshot_sha256: str
    build_snapshot_sha256: str
    controller_session_id: str
    available_monotonic_ns: int
    valid_until_monotonic_ns: int
    joint_positions_rad: Mapping[str, float]
    source_kind: str = SOURCE_KIND
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCHEMA or self.source_kind != SOURCE_KIND:
            raise TypingObservedIkSeedV1Error(
                "observed IK seed schema or source kind differs"
            )
        for name in ("request_id", "controller_session_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise TypingObservedIkSeedV1Error(
                    f"{name} must be nonempty unpadded text"
                )
        for name in (
            "materialization_sha256", "state_binding_sha256",
            "observed_start_state_sha256", "calibration_snapshot_sha256",
            "build_snapshot_sha256",
        ):
            _digest(getattr(self, name), name)
        available = _positive_ns(
            self.available_monotonic_ns, "available_monotonic_ns"
        )
        valid_until = _positive_ns(
            self.valid_until_monotonic_ns, "valid_until_monotonic_ns"
        )
        if available > valid_until:
            raise TypingObservedIkSeedV1Error(
                "observed IK seed availability exceeds expiry"
            )
        if not isinstance(self.joint_positions_rad, Mapping) or set(
            self.joint_positions_rad
        ) != set(ARM_JOINT_NAMES):
            raise TypingObservedIkSeedV1Error(
                "joint_positions_rad must use the exact canonical arm-joint set"
            )
        joints: dict[str, float] = {}
        for name in ARM_JOINT_NAMES:
            raw = self.joint_positions_rad[name]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise TypingObservedIkSeedV1Error(
                    f"joint_positions_rad.{name} must be numeric"
                )
            number = float(raw)
            if not math.isfinite(number):
                raise TypingObservedIkSeedV1Error(
                    f"joint_positions_rad.{name} must be finite"
                )
            joints[name] = number
        object.__setattr__(self, "joint_positions_rad", MappingProxyType(joints))

    def to_dict(self) -> dict[str, Any]:
        core: dict[str, Any] = {
            "schema": self.schema,
            "status": STATUS,
            "source_kind": self.source_kind,
            "request_id": self.request_id,
            "materialization_sha256": self.materialization_sha256,
            "state_binding_sha256": self.state_binding_sha256,
            "observed_start_state_sha256": self.observed_start_state_sha256,
            "calibration_snapshot_sha256": self.calibration_snapshot_sha256,
            "build_snapshot_sha256": self.build_snapshot_sha256,
            "controller_session_id": self.controller_session_id,
            "available_monotonic_ns": self.available_monotonic_ns,
            "valid_until_monotonic_ns": self.valid_until_monotonic_ns,
            "joint_positions_rad": dict(self.joint_positions_rad),
            "controller_feedback_claimed": True,
            "physical_measurement_claimed": True,
            "ik_screening_completed": False,
            "collision_qualification_completed": False,
            "permit_review_ready": False,
            "eligible_for_executor": False,
            "controller_commands": [],
            "wire_commands": [],
            "hardware_commands_generated": 0,
            "hardware_access": False,
            "physical_authority": False,
        }
        return {**core, "observed_ik_seed_sha256": _sha(core)}

    @property
    def observed_ik_seed_sha256(self) -> str:
        return self.to_dict()["observed_ik_seed_sha256"]

    @property
    def seed_sha256(self) -> str:
        """Canonical alias used by the shared deterministic IK screen."""

        return self.observed_ik_seed_sha256


def build_typing_observed_ik_seed_v1(
    materialization: Mapping[str, Any],
    state_binding: Mapping[str, Any],
    observed_start: ObservedPlannerStartState,
    context: SimulationContext,
    snapshot: PlannerCalibrationSnapshot,
    *,
    evaluated_monotonic_ns: int,
) -> TypingObservedIkSeedV1:
    """Create one content-bound seed after revalidating every source boundary."""

    if not isinstance(materialization, Mapping):
        raise TypeError("materialization must be a mapping")
    if not isinstance(state_binding, Mapping):
        raise TypeError("state_binding must be a mapping")
    if not isinstance(observed_start, ObservedPlannerStartState):
        raise TypeError("observed_start must be an ObservedPlannerStartState")
    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(snapshot, PlannerCalibrationSnapshot):
        raise TypeError("snapshot must be a PlannerCalibrationSnapshot")

    now = _positive_ns(evaluated_monotonic_ns, "evaluated_monotonic_ns")
    try:
        materialized = parse_typing_shadow_materialization_v1(materialization)
        bound = parse_typing_state_prerequisite_binding_v1(state_binding)
        revalidate_simulation_context(context)
    except (
        SimulationContextError,
        TypingShadowMaterializationV1Error,
        TypingStatePrerequisiteBindingV1Error,
    ) as exc:
        raise TypingObservedIkSeedV1Error(str(exc)) from exc

    ik = materialized["stage_artifacts"]["typing_trajectory_ik_screen"]
    if (
        bound["request_id"] != materialized["request_id"]
        or bound["materialization_sha256"]
        != materialized["materialization_sha256"]
    ):
        raise TypingObservedIkSeedV1Error(
            "state binding belongs to a different retained materialization"
        )
    if (
        bound["observed_start_state_sha256"]
        != observed_start.observed_start_state_sha256
        or bound["controller_session_id"] != observed_start.controller_session_id
    ):
        raise TypingObservedIkSeedV1Error(
            "state binding belongs to a different observed controller state"
        )
    if bound["evaluated_monotonic_ns"] > now:
        raise TypingObservedIkSeedV1Error(
            "IK seed evaluation predates state prerequisite binding"
        )
    if (
        ik["calibration_snapshot_sha256"] != snapshot.snapshot_sha256
        or bound["calibration_snapshot_sha256"] != snapshot.snapshot_sha256
        or observed_start.calibration_snapshot_sha256 != snapshot.snapshot_sha256
    ):
        raise TypingObservedIkSeedV1Error(
            "calibration lineage differs across retained plan and observed state"
        )
    if ik["build_snapshot_sha256"] != context.snapshot.snapshot_hash:
        raise TypingObservedIkSeedV1Error(
            "active build differs from the retained trajectory plan"
        )

    try:
        joints = observed_start.require_fresh_for(snapshot, now)
    except ObservedPlannerStartStateError as exc:
        raise TypingObservedIkSeedV1Error(str(exc)) from exc
    return TypingObservedIkSeedV1(
        request_id=materialized["request_id"],
        materialization_sha256=materialized["materialization_sha256"],
        state_binding_sha256=bound["state_binding_sha256"],
        observed_start_state_sha256=observed_start.observed_start_state_sha256,
        calibration_snapshot_sha256=snapshot.snapshot_sha256,
        build_snapshot_sha256=context.snapshot.snapshot_hash,
        controller_session_id=observed_start.controller_session_id,
        available_monotonic_ns=observed_start.available_monotonic_ns,
        valid_until_monotonic_ns=observed_start.valid_until_monotonic_ns,
        joint_positions_rad=joints,
    )


def parse_typing_observed_ik_seed_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a serialized observed seed and all zero-authority invariants."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingObservedIkSeedV1Error("observed IK seed fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("observed_ik_seed_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingObservedIkSeedV1Error("observed IK seed hash differs")
    seed = TypingObservedIkSeedV1(
        request_id=value["request_id"],
        materialization_sha256=value["materialization_sha256"],
        state_binding_sha256=value["state_binding_sha256"],
        observed_start_state_sha256=value["observed_start_state_sha256"],
        calibration_snapshot_sha256=value["calibration_snapshot_sha256"],
        build_snapshot_sha256=value["build_snapshot_sha256"],
        controller_session_id=value["controller_session_id"],
        available_monotonic_ns=value["available_monotonic_ns"],
        valid_until_monotonic_ns=value["valid_until_monotonic_ns"],
        joint_positions_rad=value["joint_positions_rad"],
        source_kind=value["source_kind"],
        schema=value["schema"],
    )
    expected = seed.to_dict()
    if expected != dict(value) or (
        value["status"] != STATUS
        or value["controller_feedback_claimed"] is not True
        or value["physical_measurement_claimed"] is not True
        or value["ik_screening_completed"] is not False
        or value["collision_qualification_completed"] is not False
        or value["permit_review_ready"] is not False
        or value["eligible_for_executor"] is not False
        or value["controller_commands"] != []
        or value["wire_commands"] != []
        or value["hardware_commands_generated"] != 0
        or value["hardware_access"] is not False
        or value["physical_authority"] is not False
    ):
        raise TypingObservedIkSeedV1Error(
            "observed IK seed status or authority differs"
        )
    return dict(value)


__all__ = [
    "SCHEMA", "SOURCE_KIND", "STATUS", "TypingObservedIkSeedV1",
    "TypingObservedIkSeedV1Error", "build_typing_observed_ik_seed_v1",
    "parse_typing_observed_ik_seed_v1",
]
