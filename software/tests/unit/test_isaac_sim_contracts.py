from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from rocell.integrations.isaac_sim import (
    FakeIsaacSimAdapter,
    IsaacSimContractError,
    IsaacSimRunReceipt,
    IsaacSimRunRequest,
    IsaacSimToolchainLock,
    canonical_sha256,
)

WORKSPACE = Path(__file__).resolve().parents[3]
FIXTURES = WORKSPACE / "software/tests/fixtures/isaac_sim"
SCHEMAS = WORKSPACE / "software/schemas"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _reseal(document: dict) -> dict:
    document = deepcopy(document)
    document.pop("request_sha256", None)
    document["trajectory"]["trajectory_sha256"] = canonical_sha256(
        document["trajectory"]["samples"])
    document["request_sha256"] = canonical_sha256(document)
    return document


def test_valid_fixture_matches_json_schema_and_runtime_contract() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    document = _load("valid_request_v1.json")
    schema = json.loads(
        (SCHEMAS / "isaac_sim_run_request_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(schema).validate(document)
    request = IsaacSimRunRequest.from_dict(document)
    assert request.to_dict() == document
    assert request.request_sha256 == document["request_sha256"]


def test_request_sealing_is_order_independent_and_hash_bound() -> None:
    document = _load("valid_request_v1.json")
    unsigned = {key: value for key, value in reversed(tuple(document.items())) if key != "request_sha256"}
    request = IsaacSimRunRequest.seal(unsigned)
    assert request.request_sha256 == document["request_sha256"]
    tampered = request.to_dict()
    tampered["scene"]["random_seed"] += 1
    with pytest.raises(IsaacSimContractError, match="does not match"):
        IsaacSimRunRequest.from_dict(tampered)


@pytest.mark.parametrize(
    "fixture_name",
    ["invalid_authority_v1.json", "invalid_unknown_field_v1.json"],
)
def test_mutation_fixtures_fail_closed(fixture_name: str) -> None:
    mutation = _load(fixture_name)
    document = _load(mutation["fixture"])
    document.update(mutation["mutation"])
    with pytest.raises(IsaacSimContractError, match=mutation["expected_error"]):
        IsaacSimRunRequest.from_dict(document)


def test_request_rejects_trajectory_and_articulation_inconsistency() -> None:
    document = _load("valid_request_v1.json")
    document["trajectory"]["samples"][1]["time_from_start_ns"] = 0
    document = _reseal(document)
    with pytest.raises(IsaacSimContractError, match="increase strictly"):
        IsaacSimRunRequest.from_dict(document)
    document = _load("valid_request_v1.json")
    document["articulation"]["joint_names"].append("joint_3")
    document = _reseal(document)
    with pytest.raises(IsaacSimContractError, match="initial_positions_rad"):
        IsaacSimRunRequest.from_dict(document)


def test_fake_adapter_produces_schema_valid_zero_authority_receipt() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    request = IsaacSimRunRequest.from_dict(_load("valid_request_v1.json"))
    receipt = FakeIsaacSimAdapter().run(request)
    document = receipt.to_dict()
    schema = json.loads(
        (SCHEMAS / "isaac_sim_run_receipt_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(schema).validate(document)
    assert document["status"] == "PASS"
    assert document["evidence_class"] == "CONTRACT_TEST_ONLY"
    assert document["toolchain"]["backend"] == "FAKE"
    assert document["wire_commands"] == document["gate_promotions"] == []
    assert document["hardware_access"] is document["physical_authority"] is False


def test_fake_adapter_cancellation_is_terminal_and_named() -> None:
    adapter = FakeIsaacSimAdapter()
    adapter.cancel()
    receipt = adapter.run(
        IsaacSimRunRequest.from_dict(_load("valid_request_v1.json"))
    ).to_dict()
    assert receipt["status"] == "REJECT"
    assert receipt["reason_codes"] == ["CANCELLED_BEFORE_START"]
    assert receipt["execution"]["step_count"] == 0


def test_receipt_tampering_and_gate_promotion_reject() -> None:
    request = IsaacSimRunRequest.from_dict(_load("valid_request_v1.json"))
    document = FakeIsaacSimAdapter().run(request).to_dict()
    document["execution"]["gpu"] = "invented"
    with pytest.raises(IsaacSimContractError, match="does not match"):
        IsaacSimRunReceipt.from_dict(document)
    document = FakeIsaacSimAdapter().run(request).to_dict()
    document["gate_promotions"] = ["safe_to_power_robot"]
    document.pop("receipt_sha256")
    document["receipt_sha256"] = canonical_sha256(document)
    with pytest.raises(IsaacSimContractError, match="gate_promotions"):
        IsaacSimRunReceipt.from_dict(document)


def test_repository_toolchain_lock_matches_reviewed_exact_runner() -> None:
    path = WORKSPACE / "software/config/isaac_sim_toolchain_lock.json"
    selected = IsaacSimToolchainLock.load(path)
    assert selected.isaac_sim_version == "6.1.0.0"
    assert selected.installation_sha256 == (
        "ccb196b9c987865ee86918301f00705b1dd5a42449c3119f2119aeb2adf51258"
    )
    assert selected.license_review_status == "REVIEWED_FOR_INTERNAL_INTEGRATION"


def test_repository_lock_matches_retained_owner_authorized_launch() -> None:
    evidence = (
        WORKSPACE
        / "software/integrations/isaac_sim/evidence"
        / "windows_dual_rtx3090_first_launch_20260929.json"
    )
    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == (
        "bc41e5070109de62a1a78388e9b46ebd8a0882cecc567141ad43ea9ba90b20ee"
    )
    launch = json.loads(evidence.read_text(encoding="utf-8"))
    lock = IsaacSimToolchainLock.load(
        WORKSPACE / "software/config/isaac_sim_toolchain_lock.json"
    )
    assert launch["license_acceptance_status"] == "OWNER_AUTHORIZED_INTERNAL_USE"
    assert launch["isaacsim_distribution"] == lock.isaac_sim_version
    assert launch["installation_sha256"] == lock.installation_sha256
    assert launch["extension_lock_sha256"] == lock.extension_lock_sha256
    assert launch["settings_profile_sha256"] == lock.settings_profile_sha256
    assert launch["hardware_access"] is launch["physical_authority"] is False
    assert launch["hardware_writes"] == launch["physical_movements"] == 0
    assert launch["wire_commands"] == []


def test_selected_toolchain_lock_requires_exact_digests_and_license_review() -> None:
    document = json.loads(
        (WORKSPACE / "software/config/isaac_sim_toolchain_lock.json").read_text(
            encoding="utf-8"
        )
    )
    document.update({
        "selection_status": "SELECTED",
        "isaac_sim_version": "6.1.0-test",
        "installation_sha256": "1" * 64,
        "extension_lock_sha256": "2" * 64,
        "settings_profile_sha256": "3" * 64,
        "launch_method": "container-digest",
        "license_review_status": "REVIEWED_FOR_INTERNAL_INTEGRATION",
    })
    selected = IsaacSimToolchainLock.from_dict(document)
    assert selected.runner_platform == (
        "windows-11-amd64-dual-rtx3090-driver-595.97-compatibility-qualified"
    )
    document["installation_sha256"] = "UNPINNED"
    with pytest.raises(IsaacSimContractError, match="installation_sha256"):
        IsaacSimToolchainLock.from_dict(document)


def test_unselected_toolchain_lock_still_fails_closed() -> None:
    document = json.loads(
        (WORKSPACE / "software/config/isaac_sim_toolchain_lock.json").read_text(
            encoding="utf-8"
        )
    )
    document["selection_status"] = "UNSELECTED"
    with pytest.raises(IsaacSimContractError, match="not selected"):
        IsaacSimToolchainLock.from_dict(document)

