"""Indexed semantic actions backed only by calibrated live motion primitives."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class CalibratedPose(str, Enum):
    FOLDED = "FOLDED"
    UPRIGHT = "UPRIGHT"
    AIR_HOVER_A = "AIR_HOVER_A"
    KEYBOARD_A_HOVER = "KEYBOARD_A_HOVER"
    KEYBOARD_A_LOW_AIR = "KEYBOARD_A_LOW_AIR"


class PrimitiveKind(str, Enum):
    MOVE_NAMED_POSE = "MOVE_NAMED_POSE"


class AttachmentProfile(str, Enum):
    """Physical end-effector configuration used to qualify an action."""

    BARE_JAW = "BARE_JAW"
    STYLUS = "STYLUS"


@dataclass(frozen=True, slots=True)
class CalibratedPrimitive:
    kind: PrimitiveKind
    target: CalibratedPose


@dataclass(frozen=True, slots=True)
class NamedPoseControllerCommand:
    """Canonical firmware request produced by a calibrated primitive."""

    target: CalibratedPose
    command_id: int

    @property
    def canonical_line(self) -> bytes:
        return ('{"T":' + str(self.command_id) + "}\n").encode("ascii")


@dataclass(frozen=True, slots=True)
class ActionSet:
    action_id: str
    aliases: tuple[str, ...]
    attachment_profile: AttachmentProfile
    start_pose: CalibratedPose
    end_pose: CalibratedPose
    primitives: tuple[CalibratedPrimitive, ...]
    capability_tags: tuple[str, ...]


class ActionSetError(ValueError):
    """An intent cannot be resolved through the calibrated action graph."""


class CalibratedActionRegistry:
    def __init__(self, actions: tuple[ActionSet, ...]) -> None:
        if not actions:
            raise ActionSetError("registry requires actions")
        index: dict[str, ActionSet] = {}
        for action in actions:
            pose = action.start_pose
            for primitive in action.primitives:
                if primitive.kind is not PrimitiveKind.MOVE_NAMED_POSE:
                    raise ActionSetError("action contains an unsupported primitive")
                if primitive.target is pose:
                    raise ActionSetError("action contains a zero-distance move")
                pose = primitive.target
            if not action.primitives or pose is not action.end_pose:
                raise ActionSetError(
                    "action endpoint differs from its primitive sequence"
                )
            for key in (action.action_id, *action.aliases):
                normalized = self._normalize(key)
                if normalized in index:
                    raise ActionSetError(f"duplicate action key: {normalized}")
                index[normalized] = action
        self._actions = actions
        self._index: Mapping[str, ActionSet] = MappingProxyType(index)

    @staticmethod
    def _normalize(intent: str) -> str:
        if type(intent) is not str or not intent.strip():
            raise ActionSetError("intent must be non-empty text")
        return "_".join(intent.strip().lower().replace("-", " ").split())

    def resolve(
        self,
        intent: str,
        *,
        observed_pose: CalibratedPose,
        active_attachment_profile: AttachmentProfile,
    ) -> ActionSet:
        action = self._index.get(self._normalize(intent))
        if action is None:
            raise ActionSetError("intent has no calibrated action")
        if active_attachment_profile is not action.attachment_profile:
            raise ActionSetError(
                f"{action.action_id} requires attachment {action.attachment_profile.value}, "
                f"observed {active_attachment_profile.value}"
            )
        if observed_pose is not action.start_pose:
            raise ActionSetError(
                f"{action.action_id} requires {action.start_pose.value}, observed {observed_pose.value}"
            )
        return action

    def compose(
        self,
        intents: tuple[str, ...],
        *,
        observed_pose: CalibratedPose,
        active_attachment_profile: AttachmentProfile,
    ) -> tuple[ActionSet, ...]:
        pose = observed_pose
        result: list[ActionSet] = []
        for intent in intents:
            action = self.resolve(
                intent,
                observed_pose=pose,
                active_attachment_profile=active_attachment_profile,
            )
            result.append(action)
            pose = action.end_pose
        return tuple(result)

    def by_capability(self, capability: str) -> tuple[ActionSet, ...]:
        key = self._normalize(capability)
        return tuple(
            action for action in self._actions if key in action.capability_tags
        )

    def compile_controller_commands(
        self,
        intents: tuple[str, ...],
        *,
        observed_pose: CalibratedPose,
        active_attachment_profile: AttachmentProfile,
    ) -> tuple[NamedPoseControllerCommand, ...]:
        actions = self.compose(
            intents,
            observed_pose=observed_pose,
            active_attachment_profile=active_attachment_profile,
        )
        command_by_transition = {
            (CalibratedPose.FOLDED, CalibratedPose.UPRIGHT): 400,
            (CalibratedPose.UPRIGHT, CalibratedPose.FOLDED): 401,
            (CalibratedPose.FOLDED, CalibratedPose.AIR_HOVER_A): 403,
            (CalibratedPose.AIR_HOVER_A, CalibratedPose.FOLDED): 404,
            (CalibratedPose.AIR_HOVER_A, CalibratedPose.KEYBOARD_A_HOVER): 405,
            (CalibratedPose.KEYBOARD_A_HOVER, CalibratedPose.KEYBOARD_A_LOW_AIR): 406,
            (CalibratedPose.KEYBOARD_A_LOW_AIR, CalibratedPose.KEYBOARD_A_HOVER): 407,
            (CalibratedPose.KEYBOARD_A_HOVER, CalibratedPose.AIR_HOVER_A): 408,
        }
        pose = observed_pose
        commands: list[NamedPoseControllerCommand] = []
        for action in actions:
            for primitive in action.primitives:
                transition = (pose, primitive.target)
                if transition not in command_by_transition:
                    raise ActionSetError(
                        "pose transition has no calibrated controller command"
                    )
                commands.append(
                    NamedPoseControllerCommand(
                        target=primitive.target,
                        command_id=command_by_transition[transition],
                    )
                )
                pose = primitive.target
        return tuple(commands)


DEFAULT_CALIBRATED_ACTIONS = CalibratedActionRegistry(
    (
        ActionSet(
            action_id="stand_upright",
            aliases=("upright", "raise arm", "point up"),
            attachment_profile=AttachmentProfile.BARE_JAW,
            start_pose=CalibratedPose.FOLDED,
            end_pose=CalibratedPose.UPRIGHT,
            primitives=(
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.UPRIGHT
                ),
            ),
            capability_tags=("posture", "raise", "transit"),
        ),
        ActionSet(
            action_id="fold_arm",
            aliases=("fold", "lower arm", "return down"),
            attachment_profile=AttachmentProfile.BARE_JAW,
            start_pose=CalibratedPose.UPRIGHT,
            end_pose=CalibratedPose.FOLDED,
            primitives=(
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.FOLDED
                ),
            ),
            capability_tags=("posture", "lower", "transit"),
        ),
        ActionSet(
            action_id="exercise_upright_cycle",
            aliases=("up and down", "upright cycle"),
            attachment_profile=AttachmentProfile.BARE_JAW,
            start_pose=CalibratedPose.FOLDED,
            end_pose=CalibratedPose.FOLDED,
            primitives=(
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.UPRIGHT
                ),
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.FOLDED
                ),
            ),
            capability_tags=("posture", "cycle", "validation"),
        ),
        ActionSet(
            action_id="enter_air_hover_a",
            aliases=("hover", "air hover", "hover a"),
            attachment_profile=AttachmentProfile.BARE_JAW,
            start_pose=CalibratedPose.FOLDED,
            end_pose=CalibratedPose.AIR_HOVER_A,
            primitives=(
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.AIR_HOVER_A
                ),
            ),
            capability_tags=("noncontact", "hover", "transit"),
        ),
        ActionSet(
            action_id="retract_air_hover_a",
            aliases=("retract", "leave hover", "return from hover"),
            attachment_profile=AttachmentProfile.BARE_JAW,
            start_pose=CalibratedPose.AIR_HOVER_A,
            end_pose=CalibratedPose.FOLDED,
            primitives=(
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.FOLDED
                ),
            ),
            capability_tags=("noncontact", "retract", "transit"),
        ),
        ActionSet(
            action_id="exercise_air_hover_cycle",
            aliases=("hover cycle", "air hover cycle"),
            attachment_profile=AttachmentProfile.BARE_JAW,
            start_pose=CalibratedPose.FOLDED,
            end_pose=CalibratedPose.FOLDED,
            primitives=(
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.AIR_HOVER_A
                ),
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.FOLDED
                ),
            ),
            capability_tags=("noncontact", "hover", "retract", "cycle", "validation"),
        ),
        ActionSet(
            action_id="rehearse_keyboard_action_a",
            aliases=("ghost keypress", "air keypress", "rehearse keypress"),
            attachment_profile=AttachmentProfile.BARE_JAW,
            start_pose=CalibratedPose.FOLDED,
            end_pose=CalibratedPose.FOLDED,
            primitives=(
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.AIR_HOVER_A
                ),
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.KEYBOARD_A_HOVER
                ),
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.KEYBOARD_A_LOW_AIR
                ),
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.KEYBOARD_A_HOVER
                ),
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.AIR_HOVER_A
                ),
                CalibratedPrimitive(
                    PrimitiveKind.MOVE_NAMED_POSE, CalibratedPose.FOLDED
                ),
            ),
            capability_tags=(
                "noncontact",
                "keyboard",
                "hover",
                "retract",
                "cycle",
                "validation",
            ),
        ),
    )
)


__all__ = [
    "ActionSet",
    "ActionSetError",
    "AttachmentProfile",
    "CalibratedActionRegistry",
    "CalibratedPose",
    "CalibratedPrimitive",
    "DEFAULT_CALIBRATED_ACTIONS",
    "NamedPoseControllerCommand",
    "PrimitiveKind",
]
