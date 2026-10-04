from __future__ import annotations

from dataclasses import replace
import math
from typing import Any

import pytest

from rocell.application.wizard_actions import (
    ACTIONS,
    ACTION_BY_ID,
    ActionDefinition,
    WizardError,
    validate_action_input,
)


def test_registry_is_unique_and_has_only_expected_semantic_actions() -> None:
    assert len(ACTIONS) == len(ACTION_BY_ID)
    assert "run_micro_commissioning" not in ACTION_BY_ID
    assert not any(name.startswith("run_wifi_roll_") for name in ACTION_BY_ID)
    assert set(ACTION_BY_ID) == {
        'run_held_pair',
        'review_observed_pair',
        'review_observed_hold',
        'review_collected_hold',
        'review_started_servo_run',
        'review_started_startup_run',
        'review_planned_servo_run',
        'review_startup_servo_run',
        'rehearse_static_task',
        'review_cartesian_export',
        'review_product_ghost_case',
        'review_input_capture',
        'rehearse_ghost_keyboard',
        'rehearse_ghost_endpoints',
        'review_tap_capture',
        'observe_arm_wifi_bounded',
        'observe_arm_wifi_feedback',
        'observe_arm_wifi_feedback_fast',
        'observe_arm_wifi_feedback_intermediate',
        'observe_arm_wifi_feedback_spaced',
        'read_arm_wifi_feedback',
        'sample_arm_wifi_feedback',
        'simulate_discrete_transaction',
        'simulate_servo_diagnostics',
        'simulate_micro_correction',
        'review_pose_policy',
        "record_observational_movement",
        "run_observational_movement",
        "setup_observational_movement",
        "positional_campaign_rehearse",
        "positional_campaign_boundary_tests",
        "run_positional_campaign",
        "wrist_correction_rehearse",
        "assess_saved_wrist_correction",
        "bind_saved_wrist_correction",
        "stage_wrist_correction",
        "run_wrist_correction",
        "use_current_arm_for_observational_test",
        "run_first_motion",
        "record_first_motion_engineering_review",
        "create_first_motion_draft",
        "review_retained_first_motion_draft",
        "attach_retained_first_motion",
        "record_first_motion_observation",
        "assess_first_motion_qualification",
        "review_first_motion_qualification",
        "record_endpoint_engineering_review",
        "review_endpoint_campaign",
        "run_endpoint_trial",
        "movement_campaign_preview",
        "movement_campaign_simulate",
        "movement_endpoint_rehearse",
        "first_motion_rehearse",
        "first_motion_review",
        "record_first_motion_measurements",
        "movement_endpoint_review",
        "bench_review_key_setup",
        "movement_saved_capture_review",
        "capture_powered_arm_telemetry",
        "physical_camera_mode_enter",
        "physical_camera_operating_proposal",
        "physical_camera_operating_submit",
        "physical_camera_operating_assessment",
        "physical_usb_complete_assess",
        "physical_usb_complete_review",
        "physical_usb_reconnect_begin",
        "physical_usb_reconnect_prepare",
        "physical_usb_reconnect_review",
        "physical_usb_reconnect_boot_collect",
        "physical_usb_reconnect_collect",
        "physical_usb_reboot_begin",
        "physical_usb_reboot_prepare",
        "physical_usb_reboot_review",
        "physical_usb_reboot_boot_collect",
        "physical_usb_reboot_collect",
        "physical_usb_absence_begin",
        "physical_usb_absence_boot_review",
        "physical_usb_absence_boot_collect",
        "physical_usb_absence_runtime_review",
        "physical_usb_absence_collect",
        "physical_usb_qualification_declare",
        "physical_usb_qualification_begin",
        "physical_usb_qualification_prepare",
        "physical_usb_qualification_review",
        "physical_usb_qualification_collect",
        "physical_usb_identity_inspect",
        "physical_usb_identity_review",
        "physical_usb_identity_collect",
        "physical_usb_identity_export",
        "physical_camera_identity_submit",
        "physical_camera_identity_review",
        "physical_camera_identity_export",
        "physical_received_camera_files_discover",
        "physical_received_camera_draft_start",
        "physical_received_camera_draft_record",
        "physical_received_camera_submit",
        "physical_received_camera_review",
        "physical_camera_identity_begin",
        "physical_received_camera_export",
        "physical_source_isolation_files_discover",
        "physical_source_qualify",
        "physical_source_qualification_review",
        "physical_static_contract_begin",
        "physical_static_contract_collect",
        "physical_static_contract_review",
        "physical_camera_receipt_begin",
        "physical_intake_start",
        "physical_intake_record",
        "physical_intake_files_discover",
        "physical_intake_submit",
        "physical_intake_review",
        "physical_intake_export_originals",
        "physical_source_preflight",
        "physical_camera_plan",
        "physical_camera_runtime_inspect",
        "physical_camera_runtime_review",
        "physical_camera_initialize",
        "physical_camera_refresh",
        "physical_camera_prerequisites",
        "physical_camera_assess_sources",
        "physical_camera_review_sources",
        "physical_camera_discover",
        "physical_camera_reopen",
        "physical_camera_probe",
        "physical_camera_probe_prepare",
        "physical_camera_probe_review",
        "physical_camera_probe_export",
        "physical_camera_probe_attempt_export",
        "physical_camera_configuration",
        "physical_camera_configuration_capture",
        "physical_camera_configuration_attempt_export",
        "physical_camera_capture",
        "rehearsal_initialize",
        "rehearsal_discover",
        "rehearsal_reopen",
        "rehearsal_record_operator",
        "rehearsal_collect",
        "rehearsal_camera_campaign",
        "rehearsal_owned_camera_campaign",
        "rehearsal_camera_settings",
        "rehearsal_camera_probe",
        "rehearsal_camera_configuration",
        "rehearsal_arm_feedback_campaign",
        "rehearsal_owned_arm_feedback_campaign",
        "rehearsal_assess",
        "rehearsal_review",
        "rehearsal_refresh",
        "run_baseline",
        "boundary_tests",
        "camera_profile",
        "camera_rehearsal",
        "board_preview",
        "camera_stack",
        "prebuild_vision_checks",
        "camera_connect",
        "arm_rehearsal",
        "rehearse_passive_arm_connection",
        "rehearse_powered_arm_feedback",
        "record_passive_arm_setup",
        "record_powered_arm_startup",
        "run_passive_arm_connection",
        "run_powered_arm_feedback",
        "inspect_passive_arm_history",
        "inspect_physical_passive_history",
        "inspect_powered_feedback_history",
        "arm_feedback_contract",
        "inventory_devices",
        "inspect_native_arm_metadata",
        "rehearse_native_arm_metadata",
        "rehearse_device_inventory",
        "review_camera_candidate",
        "review_arm_candidate",
        "native_camera_inventory",
        "native_camera_identity",
        "native_camera_review",
        "camera_helper_inspect",
        "camera_helper_review",
        "arm_connect",
        "calibration_rehearsal",
        "plan_task",
        "simulate_task",
        "execute_task",
        "verify_v2",
        "record_note",
        "export_logs",
        "stop_operation",
    }
    assert {action.section for action in ACTIONS} <= {
        "commissioning",
        "overview",
        "camera",
        "arm",
        "board",
        "tasks",
        "diagnostics",
    }
    forbidden_fields = {
        "path",
        "port",
        "camera_index",
        "module",
        "command",
        "argv",
        "authority",
        "destination",
        "directory",
        "raw_bytes",
        "t_code",
    }
    for action in ACTIONS:
        assert not forbidden_fields.intersection(
            field["name"] for field in action.fields
        )
        if action.action_id in {
            "physical_source_qualify",
            "physical_camera_probe",
            "physical_camera_configuration_capture",
            "physical_camera_operating_assessment",
        }:
            assert action.timeout_s == 300
        else:
            # Existing camera-original submission has a separate bounded 300s budget.
            assert 0 < action.timeout_s <= (300 if action.action_id == 'physical_camera_operating_submit' else 240)


@pytest.mark.parametrize("action_id", ["camera_connect", "arm_connect", "execute_task"])
@pytest.mark.parametrize("mode", ["rehearsal", "physical"])
def test_reserved_physical_actions_are_always_held(action_id: str, mode: str) -> None:
    action = ACTION_BY_ID[action_id]
    view = action.view(mode=mode, busy=False)
    assert action.worker == "unavailable"
    assert action.hold
    assert view["enabled"] is False
    assert view["blocked_reasons"]


def test_view_mutation_does_not_change_registered_selections() -> None:
    action = ACTION_BY_ID["plan_task"]
    initial = action.view(mode="rehearsal", busy=False)
    initial["fields"][0]["options"][0]["value"] = "arbitrary-device"
    initial["fields"][0]["options"].append({"value": "raw-device", "label": "bad"})
    later = action.view(mode="rehearsal", busy=False)
    assert later["fields"][0]["options"][0]["value"] == "keyboard"
    assert len(later["fields"][0]["options"]) == 2
    with pytest.raises(WizardError, match="Target device"):
        validate_action_input(action, {"device": "arbitrary-device", "text": "hi"})


def test_busy_view_keeps_stop_available_and_holds_other_actions() -> None:
    for action in ACTIONS:
        view = action.view(mode="rehearsal", busy=True)
        assert view["enabled"] is (action.action_id == "stop_operation")


def test_mode_view_never_promotes_rehearsals_to_physical_authority() -> None:
    assert (
        ACTION_BY_ID["camera_rehearsal"].view(mode="physical", busy=False)["enabled"]
        is False
    )
    assert (
        ACTION_BY_ID["inventory_devices"].view(mode="rehearsal", busy=False)["enabled"]
        is False
    )
    assert (
        ACTION_BY_ID["camera_rehearsal"].view(mode="rehearsal", busy=False)["enabled"]
        is True
    )


@pytest.mark.parametrize("input", [[], None, "text", True, 1])
def test_input_must_be_exact_json_object(input: Any) -> None:
    with pytest.raises(WizardError) as caught:
        validate_action_input(ACTION_BY_ID["plan_task"], input)
    assert caught.value.code == "INVALID_INPUT"


@pytest.mark.parametrize(
    "key", ["path", "COM", "argv", "authority", "destination", "raw", "worker"]
)
def test_unknown_fields_fail_closed(key: str) -> None:
    with pytest.raises(WizardError) as caught:
        validate_action_input(ACTION_BY_ID["run_baseline"], {key: "untrusted"})
    assert caught.value.code == "UNKNOWN_INPUT_FIELD"


@pytest.mark.parametrize(
    "value", ["", "   ", "a" * 65, "a\x00", "a\x01", 12, None, True]
)
def test_typing_text_bounds_and_control_characters(value: Any) -> None:
    with pytest.raises(WizardError) as caught:
        validate_action_input(ACTION_BY_ID["plan_task"], {"text": value})
    assert caught.value.code == "INVALID_TEXT"


@pytest.mark.parametrize("value", ["hello", "a" * 64, "hello\nworld", "a\tb", "--help"])
def test_valid_text_is_preserved_exactly(value: str) -> None:
    assert validate_action_input(ACTION_BY_ID["plan_task"], {"text": value}) == {
        "text": value,
        "device": "keyboard",
    }


def test_simulated_task_has_smaller_budget_than_compile() -> None:
    assert (
        validate_action_input(ACTION_BY_ID["simulate_task"], {"text": "a" * 8})["text"]
        == "a" * 8
    )
    with pytest.raises(WizardError):
        validate_action_input(ACTION_BY_ID["simulate_task"], {"text": "a" * 9})


@pytest.mark.parametrize("value", ["COM3", "camera", "Keyboard", 0, True, None])
def test_device_selection_is_registered_semantic_enum(value: Any) -> None:
    with pytest.raises(WizardError) as caught:
        validate_action_input(ACTION_BY_ID["plan_task"], {"device": value})
    assert caught.value.code == "INVALID_SELECTION"


@pytest.mark.parametrize("value", [False, "true", 1, None])
def test_metadata_confirmation_is_explicit_boolean(value: Any) -> None:
    with pytest.raises(WizardError) as caught:
        validate_action_input(
            ACTION_BY_ID["inventory_devices"], {"power_disconnected": value}
        )
    assert caught.value.code == "CONFIRMATION_REQUIRED"


def test_metadata_confirmation_is_not_defaulted_to_true() -> None:
    with pytest.raises(WizardError):
        validate_action_input(ACTION_BY_ID["inventory_devices"], {})
    assert validate_action_input(
        ACTION_BY_ID["inventory_devices"], {"power_disconnected": True}
    ) == {"power_disconnected": True, "metadata_only": False}
    assert validate_action_input(
        ACTION_BY_ID["inventory_devices"], {"metadata_only": True}
    ) == {"power_disconnected": False, "metadata_only": True}
    with pytest.raises(WizardError):
        validate_action_input(ACTION_BY_ID["inventory_devices"],
                              {"power_disconnected": False, "metadata_only": False})


def test_issue_note_is_bounded_and_has_no_release_fields() -> None:
    action = ACTION_BY_ID["record_note"]
    assert validate_action_input(action, {"note": "n" * 2000}) == {"note": "n" * 2000}
    with pytest.raises(WizardError):
        validate_action_input(action, {"note": "n" * 2001})
    with pytest.raises(WizardError):
        validate_action_input(action, {"note": "resolved", "clear_hold": True})


def _numeric_action() -> ActionDefinition:
    return replace(
        ACTION_BY_ID["plan_task"],
        fields=(
            {
                "name": "sample_budget",
                "label": "Sample budget",
                "type": "number",
                "min": 1,
                "max": 10,
            },
        ),
    )


@pytest.mark.parametrize("value", [True, "5", math.nan, math.inf, -math.inf, 10**400])
def test_numeric_fields_reject_coercion_and_nonfinite_values(value: Any) -> None:
    with pytest.raises(WizardError) as caught:
        validate_action_input(_numeric_action(), {"sample_budget": value})
    assert caught.value.code == "INVALID_NUMBER"


@pytest.mark.parametrize("value", [0, -1, 10.1, 11])
def test_numeric_fields_respect_declared_bounds(value: Any) -> None:
    with pytest.raises(WizardError) as caught:
        validate_action_input(_numeric_action(), {"sample_budget": value})
    assert caught.value.code == "NUMBER_OUT_OF_RANGE"


def test_numeric_range_boundaries_are_inclusive() -> None:
    for value in (1, 5.5, 10):
        assert validate_action_input(_numeric_action(), {"sample_budget": value}) == {
            "sample_budget": value
        }


def test_error_transport_record_keeps_reason_code() -> None:
    assert WizardError("TEST_HOLD", "Review source").to_dict() == {
        "code": "TEST_HOLD",
        "message": "Review source",
    }
