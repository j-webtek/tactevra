from __future__ import annotations

import json
from pathlib import Path

import pytest

from rocell.application.model_motion_bridge import (
    ModelMotionBridgeError,
    compile_mapping,
    compile_model_motion_proposal,
    compile_retained_keyboard_hover_draft,
)
from rocell.models import Interaction, ModelMotionProposal, MotionProposalError, Point3Mm
from rocell.targets import load_nominal_target_catalog


@pytest.fixture
def workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def proposal(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "rocell.model_motion_proposal.v1",
        "proposal_id": "proposal-h-001",
        "device": "keyboard",
        "target_id": "H",
        "coordinate_frame": "keyboard_local",
        "target_mm": {"x": 131.55, "y": 69.0, "z": 0.0},
        "interaction": "HOVER",
        "approach_clearance_mm": 25.0,
        "speed_class": "SLOW",
        "confidence": 0.98,
        "source": {
            "model_id": "candidate-model-v1",
            "frame_id": "frame-001",
            "image_sha256": "a" * 64,
        },
    }
    value.update(overrides)
    return value


def test_keyboard_local_coordinate_compiles_to_nominal_board_candidate(
    workspace_root: Path,
) -> None:
    report = compile_mapping(proposal(), workspace=workspace_root)

    assert report["status"] == "ACCEPTED_OFFLINE_NOMINAL_REQUIRES_CALIBRATED_PLANNER"
    assert report["proposal_id"] == "proposal-h-001"
    assert report["proposed_surface_target_board_mm"] == {
        "frame": "board",
        "x": pytest.approx(216.55),
        "y": pytest.approx(154.0),
        "z": pytest.approx(21.0),
    }
    assert report["requested_waypoints"] == [
        {
            "phase": "HOVER_DESTINATION",
            "point_mm": {
                "frame": "board",
                "x": pytest.approx(216.55),
                "y": pytest.approx(154.0),
                "z": pytest.approx(46.0),
            },
        }
    ]
    assert report["controller_commands"] == []
    assert report["hardware_commands_generated"] == 0
    assert report["physical_authority"] is False


def test_contact_candidate_preserves_approach_contact_retract_order(
    workspace_root: Path,
) -> None:
    value = proposal(
        device="phone",
        target_id="key_h",
        coordinate_frame="phone_screen_local",
        target_mm={"x": 46.5, "y": 42.0, "z": 0.0},
        interaction="CONTACT",
    )
    report = compile_mapping(value, workspace=workspace_root)

    assert [row["phase"] for row in report["requested_waypoints"]] == [
        "APPROACH",
        "CONTACT_CANDIDATE",
        "RETRACT",
    ]
    assert report["proposed_surface_target_board_mm"]["x"] == pytest.approx(545.7)
    assert report["proposed_surface_target_board_mm"]["y"] == pytest.approx(126.2)
    assert report["proposed_surface_target_board_mm"]["z"] == pytest.approx(11.9)


def test_board_coordinate_is_accepted_when_inside_named_safe_region(
    workspace_root: Path,
) -> None:
    value = proposal(
        coordinate_frame="board",
        target_mm={"x": 217.0, "y": 154.5, "z": 21.0},
    )
    report = compile_mapping(value, workspace=workspace_root)
    assert report["nominal_delta_mm"] == {
        "x": pytest.approx(0.45),
        "y": pytest.approx(0.5),
        "z": pytest.approx(0.0),
    }


def test_coordinate_outside_named_region_is_rejected(workspace_root: Path) -> None:
    value = proposal(target_mm={"x": 160.0, "y": 69.0, "z": 0.0})
    with pytest.raises(ModelMotionBridgeError, match="outside"):
        compile_mapping(value, workspace=workspace_root)


def test_wrong_surface_plane_is_rejected(workspace_root: Path) -> None:
    value = proposal(target_mm={"x": 131.55, "y": 69.0, "z": 5.0})
    with pytest.raises(ModelMotionBridgeError, match="surface plane"):
        compile_mapping(value, workspace=workspace_root)


def test_low_confidence_is_rejected(workspace_root: Path) -> None:
    value = proposal(confidence=0.5)
    with pytest.raises(ModelMotionBridgeError, match="below"):
        compile_mapping(value, workspace=workspace_root)


def test_device_frame_mismatch_is_rejected() -> None:
    value = proposal(device="phone")
    with pytest.raises(MotionProposalError, match="incompatible"):
        ModelMotionProposal.from_mapping(value)


def test_extra_wire_command_field_is_rejected() -> None:
    value = proposal(controller_command={"T": 102})
    with pytest.raises(MotionProposalError, match="exactly"):
        ModelMotionProposal.from_mapping(value)


def test_catalog_local_projection_is_explicitly_nominal(workspace_root: Path) -> None:
    catalog = load_nominal_target_catalog(workspace_root)
    board = catalog.local_to_board(
        Point3Mm("keyboard_local", 36.3, 69.0, 0.0),
        device="keyboard",
    )
    assert board == Point3Mm("board", 121.3, 154.0, 21.0)
    assert catalog.simulation_only is True


def test_candidate_hash_is_deterministic(workspace_root: Path) -> None:
    parsed = ModelMotionProposal.from_mapping(proposal())
    catalog = load_nominal_target_catalog(workspace_root)
    first = compile_model_motion_proposal(parsed, catalog)
    second = compile_model_motion_proposal(parsed, catalog)
    assert first == second
    assert len(first["candidate_sha256"]) == 64


def test_retained_keyboard_hover_draft_binds_reviewed_evidence_without_authority(
    workspace_root: Path,
) -> None:
    values = dict(
        expected_workcell_epoch_id="keyboard-bare-jaw-camera-intake-20261015",
        expected_overlay_sha256=(
            "157acbe5e81e784d1fdc3e6a32f092bf2b21a95a24b1b6d0bc2ce6351f8ce407"
        ),
        expected_reference_frame_sha256=(
            "50032404cd328c1e0d09fc09d1d4cd8adf83b4444276380f2726eadd74a80ab5"
        ),
    )
    first = compile_retained_keyboard_hover_draft(workspace_root, "H", **values)
    second = compile_retained_keyboard_hover_draft(workspace_root, "H", **values)
    session = json.loads((
        workspace_root / "software/config/live_camera_feedback_session_20261015.json"
    ).read_text(encoding="utf-8"))

    assert first == second
    assert first == session["retained_hover_draft"]
    assert first["status"] == (
        "UNSENT_RETAINED_EVIDENCE_HOVER_DRAFT_BLOCKED_FROM_INGRESS"
    )
    assert first["proposal"]["interaction"] == "HOVER"
    assert first["proposal"]["target_mm"] == {
        "x": pytest.approx(212.95070610888823),
        "y": pytest.approx(149.20958023724344),
        "z": pytest.approx(21.0),
    }
    assert first["requested_waypoints"][0]["point_mm"]["z"] == pytest.approx(48.7953)
    assert first["bindings"]["attachment_profile"] == "BARE_JAW"
    assert first["controller_commands"] == []
    assert first["transport_writes"] == 0
    assert first["hardware_access"] is first["physical_authority"] is False
    assert first["descent_authorized"] is first["contact_authorized"] is False
    assert len(first["draft_sha256"]) == 64


@pytest.mark.parametrize("changes,match", [
    ({"expected_workcell_epoch_id": "stale-epoch"}, "epoch"),
    ({"expected_overlay_sha256": "1" * 64}, "overlay hash"),
    ({"expected_reference_frame_sha256": "2" * 64}, "frame hash"),
    ({"expected_attachment_profile": "STYLUS"}, "attachment profile"),
    ({"interaction": Interaction.CONTACT}, "HOVER only"),
])
def test_retained_keyboard_hover_draft_rejects_stale_or_unsafe_bindings(
    workspace_root: Path, changes: dict[str, object], match: str,
) -> None:
    values: dict[str, object] = {
        "expected_workcell_epoch_id": "keyboard-bare-jaw-camera-intake-20261015"
    }
    values.update(changes)
    with pytest.raises(ModelMotionBridgeError, match=match):
        compile_retained_keyboard_hover_draft(workspace_root, "H", **values)


def test_retained_keyboard_hover_draft_requires_a_reviewed_target(
    workspace_root: Path,
) -> None:
    with pytest.raises(ModelMotionBridgeError, match="overlay target"):
        compile_retained_keyboard_hover_draft(
            workspace_root, "NOT_A_KEY",
            expected_workcell_epoch_id="keyboard-bare-jaw-camera-intake-20261015",
        )
