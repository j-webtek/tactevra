"""Typing-specific, transport-free Waveshare T=102 command preview.

The AI cannot supply controller JSON, joint order, firmware settings, ports,
retry policy, or authority through this boundary.  One PC3 current action is
selected from an arm-owned timed joint schedule and encoded with the pinned
RoArm protocol.  The resulting dispatch intent is reviewable evidence only.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from rocell.arm.all_joint_command import JOINT_FIELDS, all_joint_command
from rocell.arm.protocol import decode_line, encode_line
from rocell.kinematics import ARM_JOINT_NAMES

from .typing_joint_schedule_v1 import TypingJointScheduleV1
from .typing_rolling_horizon_v1 import parse_typing_rolling_horizon_v1
from .typing_trajectory_plan_v1 import TypingTrajectoryPlanV1


SCHEMA = "rocell.typing_controller_preview.v1"
PROFILE_SCHEMA = "rocell.typing_controller_encoding_profile.v1"
QUALIFICATION_SCHEMA = "rocell.typing_controller_action_qualification.v1"
STATUS = "ZERO_WRITE_T102_ACTION_PREVIEW"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_COMMAND_FIELDS = ("T", *JOINT_FIELDS, "spd", "acc")
MAX_PREVIEW_COMMANDS = 4095
MAX_COMMAND_PAYLOAD_BYTES = 1024


class TypingControllerBridgeV1Error(ValueError):
    """A typing action cannot be encoded at the zero-write boundary."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypingControllerBridgeV1Error("value is not canonical JSON") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise TypingControllerBridgeV1Error(f"{label} must be a SHA-256 digest")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise TypingControllerBridgeV1Error(f"{label} must be a bounded identifier")
    return value


def _positive_ns(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TypingControllerBridgeV1Error(f"{label} must be positive nanoseconds")
    return value


@dataclass(frozen=True, slots=True)
class TypingControllerEncodingProfileV1:
    profile_id: str
    vendor_source_sha256: str
    controller_joint_mapping_sha256: str
    controller_session_id: str
    configuration_epoch_sha256: str
    fixed_gripper_rad: float
    speed: int
    acceleration: int
    feedback_timeout_ns: int
    schema: str = PROFILE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != PROFILE_SCHEMA:
            raise TypingControllerBridgeV1Error("unsupported encoding profile schema")
        _identifier(self.profile_id, "profile_id")
        _identifier(self.controller_session_id, "controller_session_id")
        for field in (
            "vendor_source_sha256", "controller_joint_mapping_sha256",
            "configuration_epoch_sha256",
        ):
            _digest(getattr(self, field), field)
        _positive_ns(self.feedback_timeout_ns, "feedback_timeout_ns")
        # The pinned arm boundary owns numeric validation and firmware ranges.
        all_joint_command(
            [0.0] * len(ARM_JOINT_NAMES) + [self.fixed_gripper_rad],
            speed=self.speed, acceleration=self.acceleration,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "profile_id": self.profile_id,
            "vendor_source_sha256": self.vendor_source_sha256,
            "controller_joint_mapping_sha256": self.controller_joint_mapping_sha256,
            "controller_session_id": self.controller_session_id,
            "configuration_epoch_sha256": self.configuration_epoch_sha256,
            "fixed_gripper_rad": float(self.fixed_gripper_rad),
            "speed": self.speed,
            "acceleration": self.acceleration,
            "feedback_timeout_ns": self.feedback_timeout_ns,
            "joint_order": list(ARM_JOINT_NAMES),
            "controller_joint_fields": list(JOINT_FIELDS[:5]),
            "gripper_policy": "FIXED_ARM_OWNED_ABSOLUTE_RAD",
            "interpolation_policy": "HOST_TIMED_T102_WAYPOINTS_V1",
        }

    @property
    def profile_sha256(self) -> str:
        return _sha256(self.to_dict())


@dataclass(frozen=True, slots=True)
class TypingControllerActionQualificationV1:
    rolling_horizon_sha256: str
    collision_qualification_sha256: str
    execution_envelope_sha256: str
    execution_permit_sha256: str
    action_deadline_monotonic_ns: int
    schema: str = QUALIFICATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != QUALIFICATION_SCHEMA:
            raise TypingControllerBridgeV1Error("unsupported qualification schema")
        for field in (
            "rolling_horizon_sha256", "collision_qualification_sha256",
            "execution_envelope_sha256", "execution_permit_sha256",
        ):
            _digest(getattr(self, field), field)
        _positive_ns(self.action_deadline_monotonic_ns,
                     "action_deadline_monotonic_ns")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "rolling_horizon_sha256": self.rolling_horizon_sha256,
            "collision_qualification_sha256": self.collision_qualification_sha256,
            "execution_envelope_sha256": self.execution_envelope_sha256,
            "execution_permit_sha256": self.execution_permit_sha256,
            "action_deadline_monotonic_ns": self.action_deadline_monotonic_ns,
        }

    @property
    def qualification_sha256(self) -> str:
        return _sha256(self.to_dict())


def preview_typing_controller_action_v1(
    schedule: TypingJointScheduleV1,
    trajectory_plan: TypingTrajectoryPlanV1,
    rolling_horizon: Mapping[str, Any],
    qualification: TypingControllerActionQualificationV1,
    profile: TypingControllerEncodingProfileV1,
    *,
    now_monotonic_ns: int,
) -> dict[str, Any]:
    """Encode exactly the current typing action without I/O or authority."""

    if not isinstance(schedule, TypingJointScheduleV1):
        raise TypeError("schedule must be a TypingJointScheduleV1")
    if not isinstance(trajectory_plan, TypingTrajectoryPlanV1):
        raise TypeError("trajectory_plan must be a TypingTrajectoryPlanV1")
    if not isinstance(qualification, TypingControllerActionQualificationV1):
        raise TypeError("qualification must be a TypingControllerActionQualificationV1")
    if not isinstance(profile, TypingControllerEncodingProfileV1):
        raise TypeError("profile must be a TypingControllerEncodingProfileV1")
    now = _positive_ns(now_monotonic_ns, "now_monotonic_ns")
    horizon = parse_typing_rolling_horizon_v1(rolling_horizon)
    if horizon["phase"] not in {"PRE_DISPATCH", "RECONSTRUCTED_PRE_DISPATCH"}:
        raise TypingControllerBridgeV1Error("current action is not pre-dispatch")
    if qualification.rolling_horizon_sha256 != horizon["rolling_horizon_sha256"]:
        raise TypingControllerBridgeV1Error("qualification binds a different horizon")
    if qualification.action_deadline_monotonic_ns != horizon["deadline_monotonic_ns"]:
        raise TypingControllerBridgeV1Error("qualification deadline differs from horizon")
    if now > qualification.action_deadline_monotonic_ns:
        raise TypingControllerBridgeV1Error("action deadline has expired")
    binding = horizon["binding"]
    if (
        profile.controller_session_id != binding["controller_session_id"]
        or profile.configuration_epoch_sha256
        != binding["configuration_epoch_sha256"]
    ):
        raise TypingControllerBridgeV1Error("controller session or epoch is crossed")
    if trajectory_plan.source_plan_sha256 != horizon["plan_sha256"]:
        raise TypingControllerBridgeV1Error("trajectory binds a different typing plan")
    if schedule.source_trajectory_plan_sha256 != trajectory_plan.trajectory_plan_sha256:
        raise TypingControllerBridgeV1Error("schedule binds a different trajectory")
    if schedule.profile.profile_sha256 != binding["dynamics_profile_sha256"]:
        raise TypingControllerBridgeV1Error("schedule dynamics profile is crossed")
    if len(schedule.samples) != len(trajectory_plan.screening_samples) or any(
        timed.sequence != geometric.sequence
        or timed.endpoint_sequence != geometric.endpoint_sequence
        or timed.phase != geometric.phase.value
        or timed.action_index != geometric.action_index
        or timed.target_id != geometric.target_id
        for timed, geometric in zip(
            schedule.samples, trajectory_plan.screening_samples, strict=True
        )
    ):
        raise TypingControllerBridgeV1Error(
            "schedule semantics differ from the bound trajectory"
        )

    current = horizon["current"]
    action_index = current["action_index"]
    target_id = current["target_id"]
    selected = tuple(
        sample for sample in schedule.samples if sample.action_index == action_index
    )
    if not selected or any(sample.target_id != target_id for sample in selected):
        raise TypingControllerBridgeV1Error("schedule lacks the exact current action")
    sequences = tuple(sample.sequence for sample in selected)
    if sequences != tuple(range(sequences[0], sequences[-1] + 1)):
        raise TypingControllerBridgeV1Error("current action samples are not contiguous")
    if sequences[0] == 0:
        raise TypingControllerBridgeV1Error("current action lacks an observed source")
    source = schedule.samples[sequences[0] - 1]
    action_start_ns = source.time_from_start_ns
    final_offset_ns = selected[-1].time_from_start_ns - action_start_ns
    feedback_deadline = now + final_offset_ns + profile.feedback_timeout_ns
    if feedback_deadline > qualification.action_deadline_monotonic_ns:
        raise TypingControllerBridgeV1Error("command or feedback window exceeds deadline")

    commands: list[dict[str, Any]] = []
    for ordinal, sample in enumerate(selected):
        joints = [sample.joint_positions_rad[name] for name in ARM_JOINT_NAMES]
        message = all_joint_command(
            [*joints, profile.fixed_gripper_rad],
            speed=profile.speed, acceleration=profile.acceleration,
        )
        wire = encode_line(message)
        offset = sample.time_from_start_ns - action_start_ns
        commands.append({
            "ordinal": ordinal,
            "sample_sequence": sample.sequence,
            "phase": sample.phase,
            "action_index": action_index,
            "target_id": target_id,
            "time_from_action_start_ns": offset,
            "scheduled_dispatch_monotonic_ns": now + offset,
            "message": message,
            "payload_utf8": wire.decode("utf-8"),
            "payload_bytes": len(wire),
            "payload_sha256": hashlib.sha256(wire).hexdigest(),
        })
    ordered_wire_sha256 = _sha256([item["payload_sha256"] for item in commands])
    bindings = {
        "rolling_horizon_sha256": horizon["rolling_horizon_sha256"],
        "current_action_sha256": current["action_sha256"],
        "schedule_sha256": schedule.schedule_sha256,
        "dynamics_profile_sha256": schedule.profile.profile_sha256,
        "configuration_epoch_sha256": binding["configuration_epoch_sha256"],
        "observed_start_state_sha256": binding["observed_start_state_sha256"],
        "controller_session_id": binding["controller_session_id"],
        "collision_qualification_sha256": qualification.collision_qualification_sha256,
        "execution_envelope_sha256": qualification.execution_envelope_sha256,
        "execution_permit_sha256": qualification.execution_permit_sha256,
        "encoding_profile_sha256": profile.profile_sha256,
    }
    dispatch_subject = {
        "action_index": action_index,
        "target_id": target_id,
        "bindings": bindings,
        "ordered_wire_sha256": ordered_wire_sha256,
        "action_deadline_monotonic_ns": qualification.action_deadline_monotonic_ns,
    }
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "request_id": horizon["request_id"],
        "action_index": action_index,
        "target_id": target_id,
        "bindings": bindings,
        "qualification_sha256": qualification.qualification_sha256,
        "source_sample_sha256": _sha256(source.to_dict()),
        "command_count": len(commands),
        "commands": commands,
        "ordered_wire_sha256": ordered_wire_sha256,
        "dispatch_intent_sha256": _sha256(dispatch_subject),
        "acknowledgement_requirements": {
            "t102_acknowledgement": "OPTIONAL_NOT_ASSUMED",
            "required_feedback_request_type": 105,
            "required_feedback_response_type": 1051,
            "feedback_required_after_final_waypoint": True,
            "feedback_deadline_monotonic_ns": feedback_deadline,
            "completion_requires_correlated_feedback": True,
        },
        "action_deadline_monotonic_ns": qualification.action_deadline_monotonic_ns,
        "permit_consumed": False,
        "transport_opened": False,
        "transport_write_count": 0,
        "submitted_bytes": [],
        "automatic_retry_allowed": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**report, "typing_controller_preview_sha256": _sha256(report)}


def parse_typing_controller_preview_v1(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Strictly reconstruct exact T=102 bytes and zero-authority bindings."""

    fields = {
        "schema", "status", "request_id", "action_index", "target_id",
        "bindings", "qualification_sha256", "source_sample_sha256",
        "command_count", "commands", "ordered_wire_sha256",
        "dispatch_intent_sha256", "acknowledgement_requirements",
        "action_deadline_monotonic_ns", "permit_consumed", "transport_opened",
        "transport_write_count", "submitted_bytes", "automatic_retry_allowed",
        "hardware_access", "physical_authority", "typing_controller_preview_sha256",
    }
    if not isinstance(document, Mapping) or set(document) != fields:
        raise TypingControllerBridgeV1Error("preview fields are not exact")
    unsigned = dict(document)
    claimed = _digest(
        unsigned.pop("typing_controller_preview_sha256"),
        "typing_controller_preview_sha256",
    )
    if _sha256(unsigned) != claimed:
        raise TypingControllerBridgeV1Error("preview hash is invalid")
    if document["schema"] != SCHEMA or document["status"] != STATUS:
        raise TypingControllerBridgeV1Error("preview schema or status is invalid")
    bindings = document["bindings"]
    binding_fields = {
        "rolling_horizon_sha256", "current_action_sha256", "schedule_sha256",
        "dynamics_profile_sha256", "configuration_epoch_sha256",
        "observed_start_state_sha256", "controller_session_id",
        "collision_qualification_sha256", "execution_envelope_sha256",
        "execution_permit_sha256", "encoding_profile_sha256",
    }
    if not isinstance(bindings, Mapping) or set(bindings) != binding_fields:
        raise TypingControllerBridgeV1Error("preview bindings are not exact")
    for name in binding_fields - {"controller_session_id"}:
        _digest(bindings[name], f"bindings.{name}")
    _identifier(bindings["controller_session_id"], "controller_session_id")
    for name in (
        "qualification_sha256", "source_sample_sha256", "ordered_wire_sha256",
        "dispatch_intent_sha256",
    ):
        _digest(document[name], name)
    commands = document["commands"]
    if (
        not isinstance(commands, list)
        or not commands
        or len(commands) > MAX_PREVIEW_COMMANDS
        or document["command_count"] != len(commands)
    ):
        raise TypingControllerBridgeV1Error("command accounting is invalid")
    payload_hashes: list[str] = []
    for ordinal, command in enumerate(commands):
        expected = {
            "ordinal", "sample_sequence", "phase", "action_index", "target_id",
            "time_from_action_start_ns", "scheduled_dispatch_monotonic_ns",
            "message", "payload_utf8", "payload_bytes", "payload_sha256",
        }
        if not isinstance(command, Mapping) or set(command) != expected:
            raise TypingControllerBridgeV1Error("command fields are not exact")
        if command["ordinal"] != ordinal:
            raise TypingControllerBridgeV1Error("command order is not contiguous")
        message = command["message"]
        if not isinstance(message, Mapping) or tuple(message) != _COMMAND_FIELDS:
            raise TypingControllerBridgeV1Error("command message fields are not canonical")
        wire = command["payload_utf8"].encode("utf-8") if isinstance(
            command["payload_utf8"], str) else b""
        if not wire or len(wire) > MAX_COMMAND_PAYLOAD_BYTES:
            raise TypingControllerBridgeV1Error("command payload size is invalid")
        try:
            decoded = decode_line(wire)
            encoded = encode_line(message)
        except (TypeError, ValueError) as exc:
            raise TypingControllerBridgeV1Error(
                "encoded command does not reconstruct"
            ) from exc
        if (
            decoded != dict(message)
            or encoded != wire
            or command["payload_bytes"] != len(wire)
            or command["payload_sha256"] != hashlib.sha256(wire).hexdigest()
            or command["action_index"] != document["action_index"]
            or command["target_id"] != document["target_id"]
        ):
            raise TypingControllerBridgeV1Error("encoded command does not reconstruct")
        payload_hashes.append(command["payload_sha256"])
    if document["ordered_wire_sha256"] != _sha256(payload_hashes):
        raise TypingControllerBridgeV1Error("ordered wire hash is invalid")
    dispatch_subject = {
        "action_index": document["action_index"],
        "target_id": document["target_id"],
        "bindings": dict(bindings),
        "ordered_wire_sha256": document["ordered_wire_sha256"],
        "action_deadline_monotonic_ns": document["action_deadline_monotonic_ns"],
    }
    if document["dispatch_intent_sha256"] != _sha256(dispatch_subject):
        raise TypingControllerBridgeV1Error("dispatch intent binding is invalid")
    ack = document["acknowledgement_requirements"]
    if not isinstance(ack, Mapping) or dict(ack) != {
        "t102_acknowledgement": "OPTIONAL_NOT_ASSUMED",
        "required_feedback_request_type": 105,
        "required_feedback_response_type": 1051,
        "feedback_required_after_final_waypoint": True,
        "feedback_deadline_monotonic_ns": ack.get("feedback_deadline_monotonic_ns"),
        "completion_requires_correlated_feedback": True,
    }:
        raise TypingControllerBridgeV1Error("feedback requirements are invalid")
    _positive_ns(ack["feedback_deadline_monotonic_ns"],
                 "feedback_deadline_monotonic_ns")
    _positive_ns(document["action_deadline_monotonic_ns"],
                 "action_deadline_monotonic_ns")
    if ack["feedback_deadline_monotonic_ns"] > document["action_deadline_monotonic_ns"]:
        raise TypingControllerBridgeV1Error("feedback deadline exceeds action deadline")
    if (
        document["permit_consumed"] is not False
        or document["transport_opened"] is not False
        or document["transport_write_count"] != 0
        or document["submitted_bytes"] != []
        or document["automatic_retry_allowed"] is not False
        or document["hardware_access"] is not False
        or document["physical_authority"] is not False
    ):
        raise TypingControllerBridgeV1Error("preview violates zero authority")
    frozen = dict(document)
    frozen["bindings"] = MappingProxyType(dict(bindings))
    frozen["commands"] = tuple(MappingProxyType(dict(item)) for item in commands)
    frozen["acknowledgement_requirements"] = MappingProxyType(dict(ack))
    frozen["submitted_bytes"] = ()
    return MappingProxyType(frozen)


__all__ = [
    "MAX_COMMAND_PAYLOAD_BYTES", "MAX_PREVIEW_COMMANDS", "PROFILE_SCHEMA",
    "QUALIFICATION_SCHEMA", "SCHEMA", "STATUS",
    "TypingControllerActionQualificationV1", "TypingControllerBridgeV1Error",
    "TypingControllerEncodingProfileV1", "parse_typing_controller_preview_v1",
    "preview_typing_controller_action_v1",
]
