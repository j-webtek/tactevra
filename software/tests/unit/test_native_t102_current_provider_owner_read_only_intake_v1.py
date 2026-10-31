from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.native_t102_current_provider_owner_ai_review_acceptance_v1 import (
    parse_current_provider_owner_ai_review_acceptance_v1,
)
from rocell.application.native_t102_current_provider_owner_read_only_intake_v1 import (
    OPERATIONS,
    NativeT102CurrentProviderOwnerReadOnlyIntakeError,
    build_native_t102_current_provider_owner_read_only_intake_v1,
    parse_native_t102_current_provider_owner_read_only_intake_v1,
)
from rocell.application.native_t102_production_transport_v1 import (
    PinnedNativeT102EndpointV1,
)


ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE_PATH = ROOT / "ai/eval/arm171_current_provider_owner_ai_review_acceptance.json"
CHECKPOINT_PATH = ROOT / "runs/operational-checkpoints/issue190-20261020.json"


def _load_builder():
    path = ROOT / "scripts/build_arm172_current_provider_owner_read_only_intake.py"
    spec = importlib.util.spec_from_file_location("arm172_intake_builder", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def acceptance():
    return parse_current_provider_owner_ai_review_acceptance_v1(
        json.loads(ACCEPTANCE_PATH.read_text(encoding="utf-8")))


def endpoint(**changes):
    values = {
        "port_name": "COM4", "usb_vid": "10C4", "usb_pid": "EA60",
        "usb_serial_number": "52E4E1E8337FEF119E92181CEDD322A4",
    }
    values.update(changes)
    return PinnedNativeT102EndpointV1(**values)


def intake(**changes):
    values = {
        "owner_acceptance": acceptance(), "endpoint": endpoint(),
        "intake_id": "arm-172-current-provider-owner-read-only-intake",
        "host_id": (
            "windows-host-sha256-"
            "e56132c821d6f85ebf7eb4b49584d5547d92765f96bfd7deb29796b3a1056e0b"),
        "created_utc": "2026-10-31T22:20:00Z",
        "operational_checkpoint_sha256": (
            "5ea16e80626a4daacdaffd30e13e4f0a5760d2d5b1b7c15488c1f7bb542d6ddf"),
        "controller_metadata_session_id": "wizard-3f8b857a3909442da32760881343b448",
        "controller_metadata_source_sha256": (
            "799c3243c1f4c1e420119b036bffd7983e11a01a3a184332aa261f65ed47a4a4"),
        "controller_metadata_log_head_sha256": (
            "2a8b8faf9108c2c7cd05ca75147c1c060d2b929e8aa62c738c30b64f97caa22f"),
    }
    values.update(changes)
    return build_native_t102_current_provider_owner_read_only_intake_v1(**values)


def test_intake_binds_owner_acceptance_retained_identity_and_zero_write_policy():
    document = intake().to_dict()
    assert document["owner_acceptance_sha256"] == acceptance().acceptance_sha256
    assert document["endpoint"] == endpoint().to_dict()
    assert document["operations"] == list(OPERATIONS)
    assert document["owner_governance_override"] is True
    assert document["human_review_claimed"] is False
    assert document["external_independence_claimed"] is False
    assert document["retained_identity_is_live_verification"] is False
    assert document["transport_write_count_limit"] == 0
    assert document["active_request_count_limit"] == 0
    assert document["movement_command_count_limit"] == 0
    for field in (
        "read_only_endpoint_authorized", "endpoint_open_authorized",
        "controller_start_authorized", "transport_write_authorized",
        "execution_authorized", "hardware_access", "physical_authority",
    ):
        assert document[field] is False


def test_schema_strict_round_trip_and_retained_record():
    schema = json.loads((ROOT / "ai/schemas" /
        "native_t102_current_provider_owner_read_only_intake_v1.schema.json"
    ).read_text(encoding="utf-8"))
    original = intake()
    jsonschema.Draft202012Validator(schema).validate(original.to_dict())
    assert parse_native_t102_current_provider_owner_read_only_intake_v1(
        original.to_dict()) == original
    retained = json.loads((ROOT / "ai/eval" /
        "arm172_current_provider_owner_read_only_intake.json"
    ).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(retained)
    assert parse_native_t102_current_provider_owner_read_only_intake_v1(
        retained).to_dict() == retained


@pytest.mark.parametrize("field,value", [
    ("owner_governance_override", False),
    ("external_independence_claimed", True),
    ("retained_identity_is_live_verification", True),
    ("transport_write_count_limit", 1),
    ("automatic_retry_allowed", True),
    ("endpoint_open_authorized", True),
    ("physical_authority", True),
])
def test_provenance_policy_or_authority_promotion_rejects(field, value):
    document = intake().to_dict()
    document[field] = value
    with pytest.raises(
        NativeT102CurrentProviderOwnerReadOnlyIntakeError,
        match="policy, subject, provenance, or authority",
    ):
        parse_native_t102_current_provider_owner_read_only_intake_v1(document)


def test_crossed_acceptance_endpoint_checkpoint_and_content_hash_reject():
    for field in (
        "owner_acceptance_sha256", "operational_checkpoint_sha256",
        "controller_metadata_source_sha256",
    ):
        document = intake().to_dict()
        document[field] = "0" * 64
        with pytest.raises(
            NativeT102CurrentProviderOwnerReadOnlyIntakeError,
            match="content hash",
        ):
            parse_native_t102_current_provider_owner_read_only_intake_v1(document)
    document = intake().to_dict()
    document["endpoint"]["usb_serial_number"] = "CROSSED"
    with pytest.raises(NativeT102CurrentProviderOwnerReadOnlyIntakeError):
        parse_native_t102_current_provider_owner_read_only_intake_v1(document)


def test_intake_cannot_predate_owner_acceptance():
    with pytest.raises(
        NativeT102CurrentProviderOwnerReadOnlyIntakeError,
        match="predate owner acceptance",
    ):
        intake(created_utc="2026-10-31T21:35:59Z")


def test_builder_matches_retained_record_and_refuses_overwrite(tmp_path):
    builder = _load_builder()
    output = tmp_path / "intake.json"
    result = builder.build(ACCEPTANCE_PATH, CHECKPOINT_PATH, output)
    retained = json.loads(output.read_text(encoding="utf-8"))
    expected = json.loads((ROOT / "ai/eval" /
        "arm172_current_provider_owner_read_only_intake.json"
    ).read_text(encoding="utf-8"))
    assert result == retained == expected
    with pytest.raises(FileExistsError):
        builder.build(ACCEPTANCE_PATH, CHECKPOINT_PATH, output)


def test_builder_rejects_checkpoint_tampering(tmp_path):
    builder = _load_builder()
    document = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    document["controller_metadata"]["port_name"] = "COM5"
    changed = tmp_path / "checkpoint.json"
    changed.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(
        NativeT102CurrentProviderOwnerReadOnlyIntakeError,
        match="checkpoint hash differs",
    ):
        builder.build(ACCEPTANCE_PATH, changed, tmp_path / "output.json")


def test_module_has_no_hardware_opener_enumerator_or_writer():
    path = (ROOT / "src/rocell/application" /
            "native_t102_current_provider_owner_read_only_intake_v1.py")
    source = path.read_text(encoding="utf-8")
    for prohibited in (
        "import serial", "serial.tools", ".open()", ".write(",
        "list_ports", "comports", "feedback_request(",
    ):
        assert prohibited not in source
