from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.application.installed_base_transform_intake_v1 import (
    STATUS,
    build_installed_base_transform_intake_v1,
    validate_completed_installed_base_transform_intake_v1,
)


WORKSPACE = Path(__file__).resolve().parents[3]
WHEN = "2026-10-17T12:00:00Z"


def _report() -> dict[str, object]:
    return build_installed_base_transform_intake_v1(
        WORKSPACE,
        intake_id="installed-base-transform-20261017-v1",
        captured_at_utc=WHEN,
    )


def test_pending_intake_reuses_retained_context_without_promoting_assumptions() -> None:
    first = _report()
    second = _report()
    retained = first["retained_context"]
    exclusions = first["assumptions_excluded_from_physical_solution"]

    assert first == second
    assert first["status"] == STATUS
    assert retained["board_size_xy_mm"] == [610.0, 457.0]
    assert retained["neutral_observation_pose"] == "KEYBOARD_FORWARD_CAL_1"
    assert retained["neutral_observation_servo_positions"] == [
        2052,
        2149,
        1956,
        2550,
        2227,
        2041,
        2042,
    ]
    assert retained["detected_tag_ids"] == [0, 1, 2, 3, 4, 5]
    assert retained["installed_tag_centers_xy_mm"] == {
        "T0": [27.32, 33.31],
        "T1": [403.66, 38.45],
        "T2": [32.55, 429.5],
        "T3": [581.38, 431.47],
        "K0": [240.17, 265.84],
        "P0": [442.05, 270.39],
    }
    assert retained["board_to_arm_transform_status"] == "MISSING"
    assert len(retained["robot_local_envelopes"]) == 7
    assert len(exclusions) == 4
    assert exclusions[0]["value"]["board_frame_base_axis_xy_mm"] == [305.0, 457.0]
    assert exclusions[1]["value"]["assumed_base_axis_xy_mm"] == [305.0, 557.0]
    assert exclusions[2]["value"]["base_axis_x_board_mm"] == 385.0
    assert first["measurement_intake"]["board_T_robot_base"]["translation_mm"] is None
    assert first["profile_generated"] is False
    assert first["controller_commands"] == []
    assert first["hardware_access"] is False
    assert first["physical_movements"] == 0
    assert first["physical_authority"] is False


def test_source_bindings_are_exact() -> None:
    for source in _report()["source_bindings"]:
        payload = (WORKSPACE / source["path"]).read_bytes()
        assert len(payload) == source["byte_length"]
        assert hashlib.sha256(payload).hexdigest() == source["sha256"]


def test_pending_intake_fails_closed() -> None:
    validation = validate_completed_installed_base_transform_intake_v1(_report())
    assert validation["status"] == STATUS
    assert validation["complete"] is False
    assert "insufficient correspondences" in validation["errors"]
    assert validation["physical_authority"] is False


def test_completed_fixture_passes_structural_validation() -> None:
    report = _report()
    report["target_artifact"]["prerequisite_status"] = {
        prerequisite: "ACCEPTED_PHYSICAL_ARTIFACT"
        for prerequisite in report["target_artifact"]["prerequisites"]
    }
    intake = report["measurement_intake"]
    intake["installed_base_and_clamp"].update(
        status="MEASURED",
        arm_serial_or_unique_id="test-arm",
        controller_id="test-controller",
        factory_clamp_revision="test-clamp",
        installation_witness_ids=["test-witness"],
        clamp_edge_to_base_axis_offset_xyz_mm=[1.0, 2.0, 3.0],
        conservative_board_frame_envelope={"kind": "box", "size_mm": [1.0, 1.0, 1.0]},
        geometry_uncertainty_mm=0.5,
    )
    intake["board_T_robot_base"].update(
        status="MEASURED",
        translation_mm=[1.0, 2.0, 3.0],
        rotation_matrix_row_major=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        quaternion_xyzw=[0.0, 0.0, 0.0, 1.0],
        translation_uncertainty_mm=0.5,
        rotation_uncertainty_deg=0.2,
    )
    intake["correspondences"] = [{"id": f"test-{index}"} for index in range(6)]
    intake["observability"].update(
        status="ACCEPTED",
        position_diversity_count=3,
        orientation_diversity_count=2,
        design_matrix_rank=6,
        condition_number=4.0,
    )
    intake["held_out_validation"].update(
        status="ACCEPTED",
        sample_count=2,
        maximum_position_residual_mm=0.8,
        rms_position_residual_mm=0.4,
        maximum_orientation_residual_deg=0.3,
        rms_orientation_residual_deg=0.1,
    )
    intake["reseat_repeatability"].update(
        status="ACCEPTED",
        trial_count=2,
        maximum_translation_delta_mm=0.6,
        maximum_rotation_delta_deg=0.2,
    )
    intake["source_ids"] = ["test-source"]
    unsigned = {key: value for key, value in report.items() if key != "content_sha256"}
    report["content_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()

    validation = validate_completed_installed_base_transform_intake_v1(report)
    assert validation["complete"] is True
    assert validation["status"] == "COMPLETE_ZERO_AUTHORITY"
    assert validation["physical_authority"] is False
