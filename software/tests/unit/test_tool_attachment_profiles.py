import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_attachment_profiles_separate_bare_jaw_and_stylus_authority() -> None:
    document = json.loads(
        (ROOT / "config" / "tool_attachment_profiles.json").read_text()
    )
    assert document["schema"] == "rocell.tool_attachment_profiles.v1"
    profiles = {row["attachment_profile"]: row for row in document["profiles"]}
    assert set(profiles) == {"BARE_JAW", "STYLUS"}
    assert profiles["BARE_JAW"]["qualified_named_pose_maximum"] == (
        "KEYBOARD_FIELD_APPROACH_38"
    )
    assert profiles["STYLUS"]["tcp_definition"] is None
    assert profiles["STYLUS"]["qualified_named_pose_maximum"] is None
    assert all(not row["contact_authorized"] for row in profiles.values())


def test_attachment_change_invalidates_trajectory_and_epoch() -> None:
    document = json.loads(
        (ROOT / "config" / "tool_attachment_profiles.json").read_text()
    )
    policy = document["switching_policy"]
    assert policy == {
        "explicit_profile_required": True,
        "invalidate_precomputed_trajectory_on_change": True,
        "require_new_configuration_epoch_on_change": True,
        "allow_pose_inheritance_between_profiles": False,
        "allow_contact_authority_inheritance": False,
    }
