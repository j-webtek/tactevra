"""Operator reports stay distinct from measured firmware identity and permission."""

import json

import pytest

from rocell.application.arm_bench_qualification_contract import _canonical
from rocell.application.powered_feedback_firmware_review import (
    create_review,
    validate_review,
)

CONTEXT = dict(
    session_id="wizard-" + "a" * 32,
    source_sha256="b" * 64,
    protocol_review_original=b"fixture vendor protocol review",
)


def original():
    return create_review(
        **CONTEXT,
        operator_id="fixture-operator",
        history_original=b"SYNTHETIC unchanged-delivery operator report"
    )


def test_history_is_not_installed_firmware_measurement():
    value = validate_review(original(), **CONTEXT)
    assert value["installed_version"] is value["installed_binary_sha256"] is None
    assert value["motion_authorized"] is value["physical_authority"] is False
    assert value["command_type"] == 105


def test_verified_r120_evidence_is_bound_as_installed_binary():
    evidence = _canonical({
        "schema": "rocell.installed_r120_evidence.v1",
        "candidate": "r120",
        "app_sha256": "c" * 64,
        "startup_motion_commands": 0,
        "feedback_request": {"T": 105},
        "motion_authorized": False,
        "physical_authority": False,
    })
    raw = create_review(
        **CONTEXT,
        operator_id="fixture-operator",
        history_original=b"SYNTHETIC locally installed r120 record",
        installed_firmware_evidence_original=evidence,
    )
    value = validate_review(raw, **CONTEXT)
    assert value["reported_firmware_history"] == "LOCALLY_BUILT_AND_FLASH_VERIFIED"
    assert value["installed_version"] == "r120"
    assert value["installed_binary_sha256"] == "c" * 64
    assert value["installed_evidence_sha256"]
    assert value["motion_authorized"] is value["physical_authority"] is False


def test_installed_r120_review_rejects_changed_embedded_evidence():
    evidence = _canonical({
        "schema": "rocell.installed_r120_evidence.v1", "candidate": "r120",
        "app_sha256": "c" * 64, "startup_motion_commands": 0,
        "feedback_request": {"T": 105}, "motion_authorized": False,
        "physical_authority": False,
    })
    body = json.loads(create_review(
        **CONTEXT, operator_id="fixture-operator",
        history_original=b"SYNTHETIC locally installed r120 record",
        installed_firmware_evidence_original=evidence))
    body["installed_binary_sha256"] = "d" * 64
    with pytest.raises(ValueError):
        validate_review(_canonical(body), **CONTEXT)


@pytest.mark.parametrize(
    "field,value",
    [
        ("reported_firmware_history", "UNKNOWN"),
        ("reported_firmware_history", "MODIFIED"),
        ("command_type", 100),
        ("installed_version", "invented"),
        ("physical_authority", True),
        ("motion_authorized", 0),
        ("history_original_sha256", "c" * 64),
        ("source_sha256", "d" * 64),
    ],
)
def test_wrong_or_invented_basis_rejected(field, value):
    body = json.loads(original())
    body[field] = value
    with pytest.raises(ValueError):
        validate_review(_canonical(body), **CONTEXT)


def test_protocol_original_must_be_the_reviewed_bytes():
    with pytest.raises(ValueError):
        validate_review(
            original(), **{**CONTEXT, "protocol_review_original": b"changed"}
        )
