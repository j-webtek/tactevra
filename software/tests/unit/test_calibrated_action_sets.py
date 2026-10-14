import pytest

from rocell.application.calibrated_action_sets import (
    ActionSetError,
    AttachmentProfile,
    CalibratedPose,
    DEFAULT_CALIBRATED_ACTIONS,
)


BARE_JAW = AttachmentProfile.BARE_JAW


def test_registry_resolves_alias_and_enforces_precondition() -> None:
    action = DEFAULT_CALIBRATED_ACTIONS.resolve(
        "point up",
        observed_pose=CalibratedPose.FOLDED,
        active_attachment_profile=BARE_JAW,
    )
    assert action.action_id == "stand_upright"
    assert action.end_pose is CalibratedPose.UPRIGHT
    with pytest.raises(ActionSetError, match="requires FOLDED"):
        DEFAULT_CALIBRATED_ACTIONS.resolve(
            "point up",
            observed_pose=CalibratedPose.UPRIGHT,
            active_attachment_profile=BARE_JAW,
        )


def test_registry_composes_pose_consistent_actions() -> None:
    actions = DEFAULT_CALIBRATED_ACTIONS.compose(
        ("raise arm", "return down"),
        observed_pose=CalibratedPose.FOLDED,
        active_attachment_profile=BARE_JAW,
    )
    assert tuple(action.action_id for action in actions) == (
        "stand_upright",
        "fold_arm",
    )
    assert (
        DEFAULT_CALIBRATED_ACTIONS.resolve(
            "up and down",
            observed_pose=CalibratedPose.FOLDED,
            active_attachment_profile=BARE_JAW,
        ).end_pose
        is CalibratedPose.FOLDED
    )
    assert tuple(
        action.action_id
        for action in DEFAULT_CALIBRATED_ACTIONS.by_capability("posture")
    ) == ("stand_upright", "fold_arm", "exercise_upright_cycle")


def test_registry_compiles_intent_to_canonical_firmware_requests() -> None:
    commands = DEFAULT_CALIBRATED_ACTIONS.compile_controller_commands(
        ("point up", "lower arm"),
        observed_pose=CalibratedPose.FOLDED,
        active_attachment_profile=BARE_JAW,
    )
    assert tuple(command.target for command in commands) == (
        CalibratedPose.UPRIGHT,
        CalibratedPose.FOLDED,
    )
    assert tuple(command.canonical_line for command in commands) == (
        b'{"T":400}\n',
        b'{"T":401}\n',
    )


def test_registry_compiles_guarded_hover_and_retract_commands() -> None:
    commands = DEFAULT_CALIBRATED_ACTIONS.compile_controller_commands(
        ("hover", "retract"),
        observed_pose=CalibratedPose.FOLDED,
        active_attachment_profile=BARE_JAW,
    )
    assert tuple(command.target for command in commands) == (
        CalibratedPose.AIR_HOVER_A,
        CalibratedPose.FOLDED,
    )
    assert tuple(command.canonical_line for command in commands) == (
        b'{"T":403}\n',
        b'{"T":404}\n',
    )
    assert (
        DEFAULT_CALIBRATED_ACTIONS.resolve(
            "hover cycle",
            observed_pose=CalibratedPose.FOLDED,
            active_attachment_profile=BARE_JAW,
        ).end_pose
        is CalibratedPose.FOLDED
    )


def test_contact_and_approach_are_not_calibrated_actions() -> None:
    for intent in ("approach", "contact", "press key"):
        with pytest.raises(ActionSetError, match="no calibrated action"):
            DEFAULT_CALIBRATED_ACTIONS.resolve(
                intent,
                observed_pose=CalibratedPose.FOLDED,
                active_attachment_profile=BARE_JAW,
            )


def test_registry_compiles_full_air_keypress_rehearsal() -> None:
    commands = DEFAULT_CALIBRATED_ACTIONS.compile_controller_commands(
        ("ghost keypress",),
        observed_pose=CalibratedPose.FOLDED,
        active_attachment_profile=BARE_JAW,
    )
    assert tuple(command.command_id for command in commands) == (
        403,
        405,
        406,
        407,
        408,
        404,
    )
    assert commands[-1].target is CalibratedPose.FOLDED


def test_stylus_profile_cannot_reuse_bare_jaw_calibration() -> None:
    with pytest.raises(ActionSetError, match="requires attachment BARE_JAW"):
        DEFAULT_CALIBRATED_ACTIONS.resolve(
            "hover",
            observed_pose=CalibratedPose.FOLDED,
            active_attachment_profile=AttachmentProfile.STYLUS,
        )
