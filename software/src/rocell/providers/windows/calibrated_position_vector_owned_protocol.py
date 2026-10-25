"""Closed wire protocol for one supervised calibrated position-vector query."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from rocell.application.physical_connection_contracts import (
    EvidenceOrigin,
    RoArmUsbSerialIdentity,
    UsbDriverIdentity,
)
from rocell.application.calibrated_position_vector_feedback_execution import (
    EXCHANGE_EVIDENCE_SCHEMA,
)
from rocell.arm.feedback_profile import (
    Feedback1051Profile,
    classify_feedback_1051_profile,
)
from rocell.arm.feedback_wire import validate_feedback_response_line

from .arm_feedback_worker import ReviewedControllerBinding
from .calibrated_position_vector_binding import CalibratedPositionVectorBinding
from .calibrated_position_vector_native_composition import EXPORT_SCHEMA
from .owned_worker_process import decode_owned_json


PAYLOAD_SCHEMA = "rocell.calibrated_position_vector_native_handoff.v1"
REQUEST_SCHEMA = "rocell.owned_calibrated_position_vector_request.v1"
RESULT_SCHEMA = "rocell.owned_calibrated_position_vector_result.v1"
WORKER_ID = "physical-calibrated-position-vector"
MAX_RESULT_BYTES = 256 * 1024


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def binding_document(binding: CalibratedPositionVectorBinding) -> dict[str, Any]:
    _require(type(binding) is CalibratedPositionVectorBinding, "exact binding required")
    binding.__post_init__()
    return {
        "reviewed_controller": binding.reviewed_controller.to_dict(),
        "fresh_identity": binding.fresh_identity.to_dict(),
        "request": dict(binding.request),
        "controller_binding": dict(binding.controller_binding),
        "installed_firmware_sha256": binding.installed_firmware_sha256,
        "runtime_sha256": binding.runtime_sha256,
        "expires_monotonic_ns": binding.expires_monotonic_ns,
        "binding_sha256": binding.binding_sha256,
    }


def _identity(value: object) -> RoArmUsbSerialIdentity:
    fields = {
        "manufacturer", "product", "controller", "vid", "pid", "unit_serial",
        "persistent_instance_id", "persistent_port_path", "port_name", "driver",
        "baudrate", "rts", "dtr", "flow_control",
    }
    _require(type(value) is dict and set(value) == fields, "exact USB identity required")
    driver = value["driver"]
    _require(
        type(driver) is dict
        and set(driver) == {"provider", "service", "version", "package_or_inf_path"},
        "exact USB driver identity required",
    )
    identity = RoArmUsbSerialIdentity(
        value["vid"], value["pid"], value["unit_serial"],
        value["persistent_instance_id"], value["persistent_port_path"],
        value["port_name"], UsbDriverIdentity(**driver),
    )
    _require(identity.to_dict() == value, "USB identity constants changed")
    return identity


def decode_binding(value: object) -> CalibratedPositionVectorBinding:
    fields = {
        "reviewed_controller", "fresh_identity", "request", "controller_binding",
        "installed_firmware_sha256", "runtime_sha256", "expires_monotonic_ns",
        "binding_sha256",
    }
    _require(type(value) is dict and set(value) == fields, "exact binding fields required")
    reviewed = value["reviewed_controller"]
    _require(type(reviewed) is dict, "reviewed controller object required")
    reviewed_fields = {
        "identity", "identity_receipt_sha256", "arm_model_receipt_sha256",
        "installed_firmware_evidence_sha256", "boot_policy_evidence_sha256",
        "serial_profile_sha256", "origin",
    }
    _require(set(reviewed) == reviewed_fields, "exact reviewed controller required")
    controller = ReviewedControllerBinding(
        _identity(reviewed["identity"]),
        reviewed["identity_receipt_sha256"],
        reviewed["arm_model_receipt_sha256"],
        reviewed["installed_firmware_evidence_sha256"],
        reviewed["boot_policy_evidence_sha256"],
        reviewed["serial_profile_sha256"],
        EvidenceOrigin(reviewed["origin"]),
    )
    binding = CalibratedPositionVectorBinding(
        controller,
        _identity(value["fresh_identity"]),
        value["request"],
        value["controller_binding"],
        value["installed_firmware_sha256"],
        value["runtime_sha256"],
        value["expires_monotonic_ns"],
    )
    _require(binding.binding_sha256 == value["binding_sha256"], "binding hash mismatch")
    return binding


def validate_payload(value: object) -> tuple[dict[str, Any], CalibratedPositionVectorBinding]:
    fields = {"schema", "root", "source_sha256", "binding", "registration"}
    _require(type(value) is dict and set(value) == fields, "exact handoff fields required")
    _require(value["schema"] == PAYLOAD_SCHEMA, "wrong handoff schema")
    root = Path(value["root"])
    from .owned_worker_process import _path, _hash
    _path(root)
    _hash(value["source_sha256"])
    _require(type(value["registration"]) is dict, "registration document required")
    binding = decode_binding(value["binding"])
    runtime = hashlib.sha256(canonical(value["registration"])).hexdigest()
    _require(binding.runtime_sha256 == runtime, "binding runtime hash mismatch")
    return value, binding


def decode_request(raw: bytes) -> dict[str, Any]:
    wire = decode_owned_json(raw, maximum=65536)
    fields = {
        "schema", "worker_id", "attempt_id", "session_id", "source_sha256",
        "operation_sha256", "selected_identity_sha256", "expires_at_monotonic_ns",
        "parent_deadline_monotonic_ns", "payload", "registration_sha256",
        "request_sha256",
    }
    _require(set(wire) == fields, "exact supervisor request fields required")
    _require(
        wire["schema"] == REQUEST_SCHEMA and wire["worker_id"] == WORKER_ID,
        "wrong supervisor request domain",
    )
    request_hash = hashlib.sha256(
        canonical({key: value for key, value in wire.items() if key != "request_sha256"})
    ).hexdigest()
    _require(wire["request_sha256"] == request_hash, "supervisor request hash mismatch")
    payload, binding = validate_payload(wire["payload"])
    request = binding.request
    _require(
        wire["attempt_id"] == request["attempt_id"]
        and wire["session_id"] == request["runtime_session_id"]
        and wire["source_sha256"] == payload["source_sha256"]
        and wire["operation_sha256"] == binding.binding_sha256
        and wire["selected_identity_sha256"] == binding.identity.identity_sha256
        and wire["registration_sha256"] == binding.runtime_sha256,
        "supervisor request association mismatch",
    )
    _require(
        wire["expires_at_monotonic_ns"] == binding.expires_monotonic_ns
        and wire["parent_deadline_monotonic_ns"] == binding.expires_monotonic_ns,
        "supervisor deadline mismatch",
    )
    return wire


def encode_result(child: Mapping[str, Any], *, wire: Mapping[str, Any]) -> bytes:
    value = {
        "schema": RESULT_SCHEMA,
        "attempt_id": wire["attempt_id"],
        "request_sha256": wire["request_sha256"],
        "child_result": dict(child),
        "physical_authority": False,
        "motion_authorized": False,
        "automatic_retry_allowed": False,
        "connected": False,
    }
    validate_result(value, wire=wire)
    return canonical(value)


def validate_result(value: object, *, wire: Mapping[str, Any]) -> dict[str, Any]:
    decoded = decode_request(canonical(dict(wire)))
    fields = {
        "schema", "attempt_id", "request_sha256", "child_result",
        "physical_authority", "motion_authorized", "automatic_retry_allowed", "connected",
    }
    _require(type(value) is dict and set(value) == fields, "exact result fields required")
    _require(len(canonical(value)) <= MAX_RESULT_BYTES, "result byte budget exceeded")
    _require(
        value["schema"] == RESULT_SCHEMA
        and value["attempt_id"] == decoded["attempt_id"]
        and value["request_sha256"] == decoded["request_sha256"]
        and all(value[name] is False for name in (
            "physical_authority", "motion_authorized", "automatic_retry_allowed", "connected"
        )),
        "result association or authority mismatch",
    )
    child = value["child_result"]
    child_fields = {
        "schema", "status", "error", "binding_sha256", "exchange_evidence", "journal_export",
        "physical_authority", "motion_authorized", "automatic_retry_allowed", "connected",
    }
    _require(type(child) is dict and set(child) == child_fields, "exact child result required")
    _, binding = validate_payload(decoded["payload"])
    _require(
        child["schema"] == "rocell.calibrated_position_vector_native_child_result.v1"
        and child["binding_sha256"] == binding.binding_sha256
        and all(child[name] is False for name in (
            "physical_authority", "motion_authorized", "automatic_retry_allowed", "connected"
        )),
        "child result association or authority mismatch",
    )
    evidence = child["exchange_evidence"]
    _require(
        child["status"] in {"SUCCEEDED", "FAILED_NO_RETRY"}
        and (
            (child["status"] == "SUCCEEDED" and child["error"] is None and type(evidence) is dict)
            or (
                child["status"] == "FAILED_NO_RETRY"
                and type(child["error"]) is str
                and 0 < len(child["error"]) <= 128
                and evidence is None
            )
        ),
        "child outcome is invalid",
    )
    if evidence is None:
        evidence_fields = None
    else:
        evidence_fields = {
            "schema", "attempt_id", "status", "request_line_utf8", "response_line_utf8",
            "request_count", "write_attempt_count", "confirmed_write_bytes",
            "automatic_retry_count", "response_count", "cleanup_confirmed",
            "motion_command_count", "started_at", "finished_at", "errors",
        }
    if evidence is not None:
        _require(
            set(evidence) == evidence_fields
            and evidence.get("schema") == EXCHANGE_EVIDENCE_SCHEMA
            and evidence.get("attempt_id") == decoded["attempt_id"]
            and evidence.get("status") == "RESPONSE_OBSERVED_CLOSED"
            and evidence.get("request_count") == 1
            and evidence.get("write_attempt_count") == 1
            and evidence.get("automatic_retry_count") == 0
            and evidence.get("motion_command_count") == 0
            and evidence.get("cleanup_confirmed") is True,
            "exchange evidence is not one closed feedback query",
        )
        contract = binding.request["request_contract"]
        _require(
            evidence["request_line_utf8"] == contract["request_line_utf8"]
            and evidence["confirmed_write_bytes"]
            == len(contract["request_line_utf8"].encode("utf-8"))
            and evidence["response_count"] == 1
            and evidence["errors"] == [],
            "exchange evidence byte accounting changed",
        )
        response = validate_feedback_response_line(
            evidence["response_line_utf8"],
            max_line_bytes=contract["maximum_response_line_bytes"],
        )
        _require(
            classify_feedback_1051_profile(response)
            is Feedback1051Profile.POSITION_VECTOR_NAMED_POSE,
            "exchange response profile changed",
        )
    exported = child["journal_export"]
    export_fields = {
        "schema", "attempt_directory_name", "recovery_disposition", "request_sha256",
        "event_count", "files", "automatic_retry_allowed", "motion_authorized",
        "physical_authority", "export_directory",
    }
    _require(
        type(exported) is dict and set(exported) == export_fields
        and exported.get("schema") == EXPORT_SCHEMA
        and exported.get("attempt_directory_name")
        == "position-vector-feedback-" + decoded["attempt_id"]
        and exported.get("recovery_disposition") == "TERMINAL_NO_REPLAY"
        and exported.get("request_sha256")
        == hashlib.sha256(canonical(binding.request)).hexdigest()
        and exported.get("automatic_retry_allowed") is False
        and exported.get("motion_authorized") is False
        and exported.get("physical_authority") is False,
        "journal export association mismatch",
    )
    return value


def verify_exported_journal(
    value: Mapping[str, Any], *, wire: Mapping[str, Any], working_directory: Path
) -> dict[str, Any]:
    validated = validate_result(dict(value), wire=wire)
    exported = validated["child_result"]["journal_export"]
    export_directory = Path(exported["export_directory"])
    expected_root = (Path(working_directory) / "exports").resolve()
    _require(
        export_directory.is_absolute()
        and export_directory.parent.resolve() == expected_root
        and not export_directory.is_symlink()
        and export_directory.is_dir(),
        "journal export escaped assigned directory",
    )
    manifest_path = export_directory / "manifest.json"
    _require(manifest_path.is_file() and not manifest_path.is_symlink(), "manifest unavailable")
    manifest = decode_owned_json(manifest_path.read_bytes(), maximum=65536)
    _require(
        manifest == {key: item for key, item in exported.items() if key != "export_directory"},
        "retained journal manifest differs from child result",
    )
    files = manifest.get("files")
    _require(
        type(files) is list
        and len(files) == 3
        and {item.get("name") for item in files if type(item) is dict}
        == {"header.json", "events.jsonl", "result.json"},
        "journal export file roster is not exact",
    )
    for item in files:
        _require(type(item) is dict and set(item) == {"name", "bytes", "sha256"}, "file receipt invalid")
        path = export_directory / item["name"]
        _require(
            path.parent.resolve() == export_directory.resolve()
            and path.is_file()
            and not path.is_symlink(),
            "journal export file escaped assigned directory",
        )
        raw = path.read_bytes()
        _require(
            type(item["bytes"]) is int and 0 <= item["bytes"] <= MAX_RESULT_BYTES
            and len(raw) == item["bytes"]
            and hashlib.sha256(raw).hexdigest() == item["sha256"],
            "exported journal file differs from manifest",
        )
    return validated


__all__ = [
    "PAYLOAD_SCHEMA", "REQUEST_SCHEMA", "RESULT_SCHEMA", "WORKER_ID",
    "binding_document", "canonical", "decode_binding", "decode_request",
    "encode_result", "validate_payload", "validate_result", "verify_exported_journal",
]
