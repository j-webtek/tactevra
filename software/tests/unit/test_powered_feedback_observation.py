"""Powered feedback lifecycle on sealed memory I/O, never the connected arm."""

import base64
import hashlib
from threading import Event
import time

import pytest

from rocell.application.arm_bench_qualification_contract import _canonical
from rocell.application.passive_arm_identity import PassiveControllerSelection
from rocell.application.powered_arm_feedback_contract import PoweredFeedbackIntent
from rocell.application import wizard_native_arm_metadata as metadata
from rocell.application.wizard_device_selection import WizardDeviceSelection
from rocell.application.wizard_inventory_fixture import rehearsal_device_inventory
from rocell.providers.windows.powered_feedback_binding import PoweredFeedbackBinding
from rocell.providers.windows.powered_feedback_observation import observe_rehearsal
from rocell.providers.windows.nonpurging_serial_api import (
    IncapableWin32SerialApi,
    IncapableWin32Scenario,
    NativeSerialError,
)
from rocell.providers.windows.nonpurging_serial_backend import (
    NonPurgingSerialConnection,
)
from test_wizard_native_arm_metadata import snapshot, no_host_access
from test_powered_arm_feedback_contract import document

REPLY = b'{"T":1051,"x":300,"y":0,"z":200,"tit":0,"b":0,"s":0,"e":1.5,"t":0,"r":0,"g":3,"v":1200}\n'
POSITION_VECTOR_REPLY = (
    b'{"T":1051,"p":[2050,2147,1958,2550,2227,2041,2042],'
    b'"pose":"KEYBOARD_FORWARD_CAL_1","motion_active":false,'
    b'"trajectory_progress_permille":1000}\n'
)


def binding():
    body = document()
    body["mode"] = "rehearsal"
    now = time.monotonic_ns()
    body["startup_recorded_monotonic_ns"] = now
    body["parent_deadline_monotonic_ns"] = now + 20_000_000_000
    selection = WizardDeviceSelection(
        "rehearsal", body["session_id"], body["references"]["source_sha256"]
    )
    selection.ingest(
        rehearsal_device_inventory("nominal"), operation_id="operation-generic"
    )
    review = selection.review(
        selection.choices("SERIAL")[0]["value"], "SERIAL", "fixture-reviewer"
    )
    report = metadata.correlate_native_arm_metadata(
        snapshot(),
        review,
        mode="rehearsal",
        session_id=body["session_id"],
        source_sha256=body["references"]["source_sha256"],
        operation_id="operation-" + "c" * 32,
    )
    raw = _canonical(report)
    body["references"]["native_identity_original_sha256"] = hashlib.sha256(
        raw
    ).hexdigest()
    return PoweredFeedbackBinding(
        PassiveControllerSelection(raw), PoweredFeedbackIntent(_canonical(body))
    )


def run(**changes):
    api = IncapableWin32SerialApi(
        IncapableWin32Scenario(response_bytes=REPLY, **changes)
    )
    return observe_rehearsal(binding(), api, Event())


def test_nominal_and_fragmented_reply_single_write_then_close():
    result = run(read_fragment_bytes=7)
    assert result["status"] == "FEEDBACK_OBSERVED_CLOSED", result
    assert result["feedback"]["v"] == 1200
    assert result["lifecycle"]["confirmed_write_bytes"] == 10
    assert (
        result["lifecycle"]["api_calls"]["submit_io"]
        == result["lifecycle"]["api_calls"]["read_admissions"] + 1
    )
    assert result["lifecycle"]["cleanup_confirmed"] is True
    assert base64.b64decode(result["response"]["base64"]) == REPLY
    assert result["physical_authority"] is False


def test_startup_is_retained_and_never_satisfies_new_query():
    result = run(startup_bytes=REPLY)
    assert result["status"] == "FAILED"
    assert result["lifecycle"]["confirmed_write_bytes"] == 0
    assert base64.b64decode(result["startup"]["base64"]) == REPLY


@pytest.mark.parametrize(
    "response", [b'{"T":1051}\n', REPLY + REPLY, b'{"T":104,"x":1}\n', b"not json\n"]
)
def test_incomplete_ambiguous_or_wrong_response_rejected(response):
    api = IncapableWin32SerialApi(IncapableWin32Scenario(response_bytes=response))
    result = observe_rehearsal(binding(), api, Event())
    assert result["status"] == "FAILED"
    assert result["feedback"] is None
    assert result["lifecycle"]["write_consumed"] is True


def test_installed_position_vector_profile_is_named_and_remains_rejected():
    api = IncapableWin32SerialApi(
        IncapableWin32Scenario(response_bytes=POSITION_VECTOR_REPLY)
    )
    result = observe_rehearsal(binding(), api, Event())
    assert result["status"] == "FAILED"
    assert result["feedback"] is None
    assert result["errors"] == ["INSTALLED_POSITION_VECTOR_FEEDBACK_PROFILE"]
    assert base64.b64decode(result["response"]["base64"]) == POSITION_VECTOR_REPLY
    assert result["lifecycle"]["confirmed_write_bytes"] == 10
    assert result["lifecycle"]["cleanup_confirmed"] is True
    assert result["motion_authorized"] is False


def test_short_write_not_retried():
    result = run(short_write=2)
    assert result["status"] == "FAILED"
    assert result["lifecycle"]["confirmed_write_bytes"] == 2
    assert "SHORT_WRITE_NO_RETRY" in result["errors"]


def test_cleanup_failure_not_success():
    result = run(fail_operations=("close_port",))
    assert result["status"] == "FAILED"
    assert "CLEANUP_UNKNOWN" in result["errors"]


def test_cancel_before_open_and_no_native_fallback():
    selected = binding()
    cancel = Event()
    cancel.set()
    result = observe_rehearsal(selected, IncapableWin32SerialApi(), cancel)
    assert result["status"] == "FAILED"
    assert result["lifecycle"]["resource_counts"]["acquired"] == 0
    with pytest.raises(NativeSerialError, match="POWERED_FEEDBACK_PHYSICAL_HELD"):
        NonPurgingSerialConnection(selected)
