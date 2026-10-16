"""Explicit operator-history/vendor-protocol basis for a first feedback query.

Unmodified delivery is not an installed version or firmware binary hash. This
record associates the operator's original statement with the reviewed protocol;
it never authorizes native dispatch, energization, motion or calibration.
"""

import base64
import hashlib
import re

from .arm_bench_qualification_contract import _canonical
from .wizard_diagnostic_coordinator import decode_diagnostic_json

SCHEMA = "rocell.powered_feedback_firmware_review.v1"


def create_review(
    *,
    session_id,
    source_sha256,
    operator_id,
    history_original,
    protocol_review_original,
    installed_firmware_evidence_original=None,
):
    """Bind either delivery history or verified installed-firmware evidence."""
    for raw, maximum in ((history_original, 2048), (protocol_review_original, 65536)):
        if type(raw) is not bytes or not 0 < len(raw) <= maximum:
            raise ValueError("Bounded original evidence bytes required")
    if installed_firmware_evidence_original is not None:
        installed = decode_diagnostic_json(
            installed_firmware_evidence_original, maximum=8192)
        if (
            type(installed) is not dict
            or installed.get("schema") != "rocell.installed_r120_evidence.v1"
            or installed.get("candidate") != "r120"
            or type(installed.get("app_sha256")) is not str
            or re.fullmatch(r"[a-f0-9]{64}", installed["app_sha256"]) is None
            or installed.get("startup_motion_commands") != 0
            or installed.get("feedback_request") != {"T": 105}
            or installed.get("motion_authorized") is not False
            or installed.get("physical_authority") is not False
        ):
            raise ValueError("Verified installed r120 evidence required")
        history = "LOCALLY_BUILT_AND_FLASH_VERIFIED"
        basis = "RETAINED_DEPLOYMENT_SESSION_IMAGE_AND_SOURCE_VERIFICATION"
        installed_version = "r120"
        installed_binary_sha256 = installed["app_sha256"]
        installed_evidence_base64 = base64.b64encode(
            installed_firmware_evidence_original).decode("ascii")
        installed_evidence_sha256 = hashlib.sha256(
            installed_firmware_evidence_original).hexdigest()
    else:
        history = "UNCHANGED_SINCE_DELIVERY"
        basis = "OPERATOR_HISTORY_AND_VENDOR_PROTOCOL_NOT_BINARY_VERIFICATION"
        installed_version = installed_binary_sha256 = None
        installed_evidence_base64 = installed_evidence_sha256 = None
    body = {
        "schema": SCHEMA,
        "session_id": session_id,
        "source_sha256": source_sha256,
        "operator_id": operator_id,
        "reported_model": "RoArm-M3-Pro",
        "reported_firmware_history": history,
        "history_original_base64": base64.b64encode(history_original).decode("ascii"),
        "history_original_sha256": hashlib.sha256(history_original).hexdigest(),
        "protocol_review_sha256": hashlib.sha256(protocol_review_original).hexdigest(),
        "basis": basis,
        "installed_version": installed_version,
        "installed_binary_sha256": installed_binary_sha256,
        "installed_evidence_base64": installed_evidence_base64,
        "installed_evidence_sha256": installed_evidence_sha256,
        "command_type": 105,
        "response_type": 1051,
        "motion_authorized": False,
        "physical_authority": False,
    }
    raw = _canonical(body)
    validate_review(
        raw,
        session_id=session_id,
        source_sha256=source_sha256,
        protocol_review_original=protocol_review_original,
    )
    return raw


def validate_review(raw, *, session_id, source_sha256, protocol_review_original):
    """Validate recorded basis and byte associations, not operator authenticity."""
    if type(raw) is not bytes or type(protocol_review_original) is not bytes:
        raise ValueError("Immutable firmware/protocol review originals required")
    value = decode_diagnostic_json(raw, maximum=8192)
    installed_mode = value.get("reported_firmware_history") == "LOCALLY_BUILT_AND_FLASH_VERIFIED"
    fixed = {
        "schema": SCHEMA,
        "session_id": session_id,
        "source_sha256": source_sha256,
        "reported_model": "RoArm-M3-Pro",
        "reported_firmware_history": ("LOCALLY_BUILT_AND_FLASH_VERIFIED" if installed_mode
                                      else "UNCHANGED_SINCE_DELIVERY"),
        "protocol_review_sha256": hashlib.sha256(protocol_review_original).hexdigest(),
        "basis": ("RETAINED_DEPLOYMENT_SESSION_IMAGE_AND_SOURCE_VERIFICATION" if installed_mode
                  else "OPERATOR_HISTORY_AND_VENDOR_PROTOCOL_NOT_BINARY_VERIFICATION"),
        "installed_version": "r120" if installed_mode else None,
        "command_type": 105,
        "response_type": 1051,
        "motion_authorized": False,
        "physical_authority": False,
    }
    if (
        type(value) is not dict
        or set(value)
        != set(fixed)
        | {"operator_id", "history_original_base64", "history_original_sha256",
           "installed_binary_sha256", "installed_evidence_base64",
           "installed_evidence_sha256"}
        or _canonical(value) != raw
        or any(
            _canonical(value[key]) != _canonical(expected)
            for key, expected in fixed.items()
        )
    ):
        raise ValueError("Firmware review domain or context mismatch")
    for item, pattern in (
        (session_id, r"wizard-[a-f0-9]{32}"),
        (source_sha256, r"[a-f0-9]{64}"),
        (value["operator_id"], r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}"),
    ):
        if type(item) is not str or re.fullmatch(pattern, item) is None:
            raise ValueError("Exact review context/operator required")
    if type(value["history_original_base64"]) is not str:
        raise ValueError("Encoded operator original required")
    history = base64.b64decode(value["history_original_base64"], validate=True)
    if (
        not 0 < len(history) <= 2048
        or hashlib.sha256(history).hexdigest() != value["history_original_sha256"]
    ):
        raise ValueError("Firmware history original mismatch")
    if installed_mode:
        if (type(value["installed_evidence_base64"]) is not str
                or type(value["installed_evidence_sha256"]) is not str
                or type(value["installed_binary_sha256"]) is not str):
            raise ValueError("Installed firmware evidence binding required")
        evidence = base64.b64decode(value["installed_evidence_base64"], validate=True)
        installed = decode_diagnostic_json(evidence, maximum=8192)
        if (hashlib.sha256(evidence).hexdigest() != value["installed_evidence_sha256"]
                or type(installed) is not dict
                or installed.get("schema") != "rocell.installed_r120_evidence.v1"
                or installed.get("candidate") != "r120"
                or installed.get("app_sha256") != value["installed_binary_sha256"]
                or re.fullmatch(r"[a-f0-9]{64}", value["installed_binary_sha256"]) is None
                or installed.get("startup_motion_commands") != 0
                or installed.get("feedback_request") != {"T": 105}
                or installed.get("motion_authorized") is not False
                or installed.get("physical_authority") is not False):
            raise ValueError("Installed firmware evidence mismatch")
    elif any(value[name] is not None for name in (
        "installed_binary_sha256", "installed_evidence_base64",
        "installed_evidence_sha256")):
        raise ValueError("Unchanged-delivery review cannot claim installed evidence")
    return value
