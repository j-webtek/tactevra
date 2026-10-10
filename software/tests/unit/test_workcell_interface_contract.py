from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Callable

import pytest

from rocell.workcell.interface_contract import (
    MAX_WORKCELL_INTERFACE_CONTRACT_BYTES,
    WorkcellInterfaceContractError,
    load_workcell_interface_contract,
)


WORKSPACE = Path(__file__).resolve().parents[3]
CONTRACT_RELATIVE_PATH = Path("software/config/workcell_icd_v2.json")
CONTRACT_PATH = WORKSPACE / CONTRACT_RELATIVE_PATH
HISTORICAL_CONTRACT_PATH = WORKSPACE / "software/config/workcell_icd.json"
SOURCE_RELATIVE_PATHS = (
    Path("active-project/RoCell_v0_3/config/workcell_layout.json"),
    Path("software/config/arm_frame_contract.json"),
    Path("software/config/arm_connection.json"),
    Path("software/config/camera_profiles/arducam_b0477_imx283_16mm.json"),
    Path("software/config/camera_architecture_plan_v2.json"),
    Path("hardware/static_overhead_camera/config/commercial_tripod_candidate.json"),
    Path("hardware/static_overhead_camera/hardware_intake_template.csv"),
    Path("software/config/configuration_epochs.json"),
    Path("software/config/physical_onboarding_policy.json"),
)


def _document() -> dict[str, Any]:
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sandbox(tmp_path: Path) -> Path:
    for relative_path in (*SOURCE_RELATIVE_PATHS, CONTRACT_RELATIVE_PATH):
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(WORKSPACE / relative_path, destination)
    return tmp_path / CONTRACT_RELATIVE_PATH


def _mutated_contract(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> Path:
    path = _sandbox(tmp_path)
    document = copy.deepcopy(_document())
    mutate(document)
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def test_loads_read_only_source_bound_zero_authority_contract() -> None:
    before = CONTRACT_PATH.read_bytes()

    contract = load_workcell_interface_contract(WORKSPACE)

    assert CONTRACT_PATH.read_bytes() == before
    assert contract.path == CONTRACT_PATH.resolve()
    assert contract.content_sha256 == hashlib.sha256(before).hexdigest()
    assert contract.contract_id == "ROCELL-WORKCELL-ICD-TRIPOD-002"
    assert contract.status == "ADDITIVE_ZERO_AUTHORITY"
    assert contract.zero_physical_authority
    assert contract.interface_description_authority
    assert contract.simulation_validation_authority
    assert not any(
        (
            contract.hardware_presence_authority,
            contract.device_open_authority,
            contract.robot_power_authority,
            contract.motion_authority,
            contract.descent_authority,
            contract.contact_authority,
            contract.calibration_promotion_authority,
        )
    )
    assert contract.physical_release_effect == "NONE"
    assert tuple(contract.source_bindings) == (
        "workcell_layout",
        "arm_frame_contract",
        "arm_connection",
        "b0477_camera_profile",
        "hardware_intake_template",
        "configuration_epoch_policy",
        "physical_onboarding_policy",
        "camera_architecture_plan",
        "commercial_tripod_candidate",
    )
    for source_id, binding in contract.source_bindings.items():
        assert binding.source_id == source_id
        assert binding.resolved_path.read_bytes()
        assert hashlib.sha256(binding.resolved_path.read_bytes()).hexdigest() == (
            binding.sha256
        )
    assert contract.units == {
        "length": "mm",
        "angle": "rad",
        "elapsed_time": "s",
        "monotonic_timestamp": "ns",
        "image_coordinate": "px",
        "voltage": "V",
    }
    assert contract.power_domains == (
        "host",
        "camera_usb",
        "controller_usb",
        "arm_actuator",
    )
    assert tuple(role.role_id for role in contract.provider_roles) == (
        "host_inventory",
        "camera_diagnostic",
        "arm_identity",
        "arm_feedback",
        "safety_evidence",
        "clock",
        "evidence_store",
    )
    assert {role.capability_ceiling for role in contract.provider_roles}.isdisjoint(
        {"POWER", "MOTION", "DESCENT", "CONTACT"}
    )
    assert {
        role.role_id: role.capability_ceiling for role in contract.provider_roles
    }["arm_feedback"] == "SINGLE_T105_NO_MOTION_COMMAND"


def test_icd_references_canonical_values_instead_of_copying_them() -> None:
    document = _document()

    assert document["coordinate_conventions"]["frame_definitions_redeclared_here"] is False
    assert document["mechanical_interface"]["canonical_layout_source"] == (
        "workcell_layout"
    )
    assert document["mechanical_interface"]["canonical_arm_frame_source"] == (
        "arm_frame_contract"
    )
    assert document["uvc_interface"]["camera_profile_source"] == (
        "b0477_camera_profile"
    )
    assert document["serial_interface"]["connection_source"] == "arm_connection"
    assert document["serial_interface"][
        "ambiguous_exchange_close_or_cleanup_attempt_required_if_possible"
    ] is True
    assert document["serial_interface"][
        "ambiguous_exchange_requires_global_quarantine"
    ] is True
    assert document["serial_interface"][
        "ambiguous_exchange_requires_manual_reconciliation"
    ] is True
    assert document["serial_interface"][
        "same_t105_exchange_may_be_repeated_automatically"
    ] is False
    assert document["serial_interface"][
        "same_t105_exchange_may_be_repeated_as_new_reviewed_attempt"
    ] is False
    assert (
        "ambiguous_exchange_requires_close_and_new_reviewed_attempt"
        not in document["serial_interface"]
    )
    assert document["configuration_epochs"]["policy_source"] == (
        "configuration_epoch_policy"
    )
    assert document["configuration_epochs"]["epoch_definitions_redeclared_here"] is False
    assert "board" not in document
    assert "camera_mode" not in document
    assert "baud" not in document["serial_interface"]


def test_explicit_historical_v1_icd_remains_readable() -> None:
    before = HISTORICAL_CONTRACT_PATH.read_bytes()

    contract = load_workcell_interface_contract(WORKSPACE, HISTORICAL_CONTRACT_PATH)

    assert HISTORICAL_CONTRACT_PATH.read_bytes() == before
    assert contract.contract_id == "ROCELL-WORKCELL-ICD-001"
    assert contract.content_sha256 == hashlib.sha256(before).hexdigest()
    assert contract.zero_physical_authority


@pytest.mark.parametrize("change", ["missing", "unknown"])
def test_rejects_root_schema_drift(tmp_path: Path, change: str) -> None:
    def mutate(document: dict[str, Any]) -> None:
        if change == "missing":
            del document["timing_and_freshness"]
        else:
            document["silent_extension"] = True

    path = _mutated_contract(tmp_path, mutate)
    with pytest.raises(WorkcellInterfaceContractError, match="fields differ"):
        load_workcell_interface_contract(tmp_path, path)


def test_rejects_unknown_nested_field(tmp_path: Path) -> None:
    path = _mutated_contract(
        tmp_path,
        lambda document: document["uvc_interface"].update(
            {"unbounded_backend_escape": True}
        ),
    )
    with pytest.raises(WorkcellInterfaceContractError, match="unknown"):
        load_workcell_interface_contract(tmp_path, path)


def test_rejects_duplicate_json_key(tmp_path: Path) -> None:
    path = _sandbox(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        '"schema_version": 2,',
        '"schema_version": 2,\n  "schema_version": 2,',
        1,
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(WorkcellInterfaceContractError, match="duplicate key"):
        load_workcell_interface_contract(tmp_path, path)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity", "1e9999"])
def test_rejects_nonfinite_json_number(tmp_path: Path, constant: str) -> None:
    path = _sandbox(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        '"schema_version": 2', f'"schema_version": {constant}', 1
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(WorkcellInterfaceContractError, match="nonfinite"):
        load_workcell_interface_contract(tmp_path, path)


def test_rejects_bool_integer_alias_or_finite_float(tmp_path: Path) -> None:
    path = _mutated_contract(
        tmp_path, lambda document: document.update({"schema_version": 2.0})
    )
    with pytest.raises(WorkcellInterfaceContractError, match="schema_version"):
        load_workcell_interface_contract(tmp_path, path)


def test_rejects_oversize_contract_before_json_parse(tmp_path: Path) -> None:
    path = tmp_path / "oversize.json"
    path.write_bytes(b" " * (MAX_WORKCELL_INTERFACE_CONTRACT_BYTES + 1))

    with pytest.raises(WorkcellInterfaceContractError, match="byte limit"):
        load_workcell_interface_contract(tmp_path, path)


def test_rejects_contract_outside_workspace(tmp_path: Path) -> None:
    with pytest.raises(WorkcellInterfaceContractError, match="beneath the workspace"):
        load_workcell_interface_contract(tmp_path, CONTRACT_PATH)


def test_rejects_contract_symlink_even_when_target_is_contained(tmp_path: Path) -> None:
    target = _sandbox(tmp_path)
    alias = target.with_name("workcell_icd_alias.json")
    try:
        os.symlink(target, alias)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(WorkcellInterfaceContractError, match="symlink"):
        load_workcell_interface_contract(tmp_path, alias)


@pytest.mark.parametrize("mutation", ["path", "declared_digest", "actual_bytes"])
def test_rejects_source_path_declared_digest_or_actual_byte_drift(
    tmp_path: Path, mutation: str
) -> None:
    path = _sandbox(tmp_path)
    document = copy.deepcopy(_document())
    binding = document["source_bindings"]["arm_connection"]
    if mutation == "path":
        binding["path"] = "../outside.json"
    elif mutation == "declared_digest":
        binding["sha256"] = "0" * 64
    else:
        source = tmp_path / "software/config/arm_connection.json"
        source.write_bytes(source.read_bytes() + b"\n")
    path.write_text(
        json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )

    with pytest.raises(
        WorkcellInterfaceContractError,
        match="normalized|changed from|actual source SHA-256 mismatch",
    ):
        load_workcell_interface_contract(tmp_path, path)


def test_rejects_source_change_even_if_declared_digest_changes_with_it(
    tmp_path: Path,
) -> None:
    path = _sandbox(tmp_path)
    source = tmp_path / "software/config/arm_connection.json"
    source.write_bytes(source.read_bytes() + b"\n")
    document = copy.deepcopy(_document())
    document["source_bindings"]["arm_connection"]["sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    path.write_text(
        json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )

    with pytest.raises(WorkcellInterfaceContractError, match="changed from"):
        load_workcell_interface_contract(tmp_path, path)


def test_rejects_symlinked_referenced_source(tmp_path: Path) -> None:
    contract = _sandbox(tmp_path)
    source = tmp_path / "software/config/arm_connection.json"
    real_source = source.with_name("arm_connection_real.json")
    source.replace(real_source)
    try:
        os.symlink(real_source, source)
    except (NotImplementedError, OSError) as exc:
        real_source.replace(source)
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(WorkcellInterfaceContractError, match="symlink"):
        load_workcell_interface_contract(tmp_path, contract)


@pytest.mark.parametrize(
    "field",
    [
        "hardware_presence_authority",
        "device_open_authority",
        "robot_power_authority",
        "motion_authority",
        "descent_authority",
        "contact_authority",
        "calibration_promotion_authority",
    ],
)
def test_rejects_authority_escalation(tmp_path: Path, field: str) -> None:
    path = _mutated_contract(
        tmp_path, lambda document: document["authority"].update({field: True})
    )
    with pytest.raises(WorkcellInterfaceContractError, match=field):
        load_workcell_interface_contract(tmp_path, path)


@pytest.mark.parametrize(
    ("section", "field", "unsafe_value"),
    [
        (
            "coordinate_conventions",
            "implicit_frame_aliases_allowed",
            True,
        ),
        (
            "mechanical_interface",
            "unmeasured_geometry_may_authorize_motion",
            True,
        ),
        (
            "electrical_power_interface",
            "provider_controlled_energization_allowed",
            True,
        ),
        (
            "uvc_interface",
            "silent_mode_or_control_fallback_allowed",
            True,
        ),
        (
            "serial_interface",
            "generic_write_or_motion_operation_exposed",
            True,
        ),
        (
            "serial_interface",
            "ambiguous_exchange_close_or_cleanup_attempt_required_if_possible",
            False,
        ),
        (
            "serial_interface",
            "ambiguous_exchange_requires_global_quarantine",
            False,
        ),
        (
            "serial_interface",
            "ambiguous_exchange_requires_manual_reconciliation",
            False,
        ),
        (
            "serial_interface",
            "same_t105_exchange_may_be_repeated_automatically",
            True,
        ),
        (
            "serial_interface",
            "same_t105_exchange_may_be_repeated_as_new_reviewed_attempt",
            True,
        ),
        (
            "timing_and_freshness",
            "host_receipt_time_proves_device_exposure_time",
            True,
        ),
        (
            "provider_binding",
            "motion_execution_role_defined",
            True,
        ),
        (
            "configuration_epochs",
            "this_contract_may_create_advance_or_promote_an_epoch",
            True,
        ),
    ],
)
def test_rejects_interface_boundary_weakening(
    tmp_path: Path,
    section: str,
    field: str,
    unsafe_value: object,
) -> None:
    path = _mutated_contract(
        tmp_path,
        lambda document: document[section].update({field: unsafe_value}),
    )
    with pytest.raises(WorkcellInterfaceContractError, match=field):
        load_workcell_interface_contract(tmp_path, path)


def test_rejects_provider_role_removal_or_capability_escalation(
    tmp_path: Path,
) -> None:
    missing = _mutated_contract(
        tmp_path / "missing",
        lambda document: document["provider_roles"].pop("safety_evidence"),
    )
    with pytest.raises(WorkcellInterfaceContractError, match="fields differ"):
        load_workcell_interface_contract(tmp_path / "missing", missing)

    escalated = _mutated_contract(
        tmp_path / "escalated",
        lambda document: document["provider_roles"]["arm_feedback"].update(
            {"capability_ceiling": "GENERIC_SERIAL_WRITE_AND_MOTION"}
        ),
    )
    with pytest.raises(WorkcellInterfaceContractError, match="capability_ceiling"):
        load_workcell_interface_contract(tmp_path / "escalated", escalated)


def test_returned_mappings_are_immutable() -> None:
    contract = load_workcell_interface_contract(WORKSPACE)

    with pytest.raises(TypeError):
        contract.source_bindings["extra"] = contract.source_bindings[  # type: ignore[index]
            "workcell_layout"
        ]
    with pytest.raises(TypeError):
        contract.source_sha256["workcell_layout"] = "0" * 64  # type: ignore[index]
    with pytest.raises(TypeError):
        contract.units["length"] = "inch"  # type: ignore[index]
