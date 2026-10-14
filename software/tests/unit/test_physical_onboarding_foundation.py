from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Callable, cast

import pytest

import rocell.application.physical_onboarding_foundation as foundation_module
from rocell.application.physical_onboarding_foundation import (
    MAX_PHYSICAL_ONBOARDING_FOUNDATION_BYTES,
    PHYSICAL_ONBOARDING_FOUNDATION_ID,
    PhysicalOnboardingFoundationError,
    load_physical_onboarding_foundation,
)


WORKSPACE = Path(__file__).resolve().parents[3]
FOUNDATION_RELATIVE_PATH = Path("software/config/physical_onboarding_foundation_v2.json")
FOUNDATION_PATH = WORKSPACE / FOUNDATION_RELATIVE_PATH
CONTRACT_RELATIVE_PATHS = (
    Path("software/config/authority_effect_policy.json"),
    Path("software/config/physical_onboarding_stage_catalog.json"),
    Path("software/config/configuration_epochs.json"),
    Path("software/config/physical_onboarding_hazards.json"),
    Path("software/config/workcell_icd_v3.json"),
    Path("software/config/accuracy_budget_policy.json"),
)
CROSS_CONTRACT_RELATIVE_PATHS = (
    Path("active-project/RoCell_v0_3/config/workcell_layout.json"),
    Path("active-project/RoCell_v0_3/config/robot_reach_screening.json"),
    Path("software/config/arm_frame_contract.json"),
    Path("software/config/arm_connection.json"),
    Path("software/config/camera_architecture_plan_v2.json"),
    Path("software/config/camera_profiles/arducam_b0477_imx283_16mm.json"),
    Path("software/config/physical_onboarding_policy_v2.json"),
    Path("hardware/static_overhead_camera/config/commercial_tripod_candidate.json"),
    Path("hardware/static_overhead_camera/hardware_intake_template.csv"),
)


def _document() -> dict[str, Any]:
    result = json.loads(FOUNDATION_PATH.read_text(encoding="utf-8"))
    assert isinstance(result, dict)
    return result


def _temporary_foundation(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> Path:
    document = copy.deepcopy(_document())
    mutate(document)
    path = tmp_path / "physical_onboarding_foundation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def _contract_sandbox(tmp_path: Path) -> Path:
    for relative in (*CONTRACT_RELATIVE_PATHS, FOUNDATION_RELATIVE_PATH):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(WORKSPACE / relative, destination)
    return tmp_path / FOUNDATION_RELATIVE_PATH


def _cross_contract_sandbox(tmp_path: Path) -> Path:
    foundation_path = _contract_sandbox(tmp_path)
    for relative in CROSS_CONTRACT_RELATIVE_PATHS:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(WORKSPACE / relative, destination)
    return foundation_path


def _write_json(path: Path, document: object) -> None:
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def test_loads_hash_bound_zero_authority_foundation() -> None:
    before = FOUNDATION_PATH.read_bytes()

    foundation = load_physical_onboarding_foundation(WORKSPACE)

    assert FOUNDATION_PATH.read_bytes() == before
    assert foundation.foundation_id == PHYSICAL_ONBOARDING_FOUNDATION_ID
    assert foundation.source_path == FOUNDATION_PATH.resolve()
    assert foundation.source_sha256 == hashlib.sha256(before).hexdigest()
    assert foundation.runtime_activation is False
    assert foundation.zero_physical_authority
    assert len(foundation.contracts) == 6
    assert tuple(foundation.contracts_by_id) == tuple(
        binding.id for binding in foundation.contracts
    )
    assert len(foundation.open_implementation_gates) == 10
    assert "WINDOWS_DURABILITY_AND_TORN_TAIL_RECOVERY" in (
        foundation.open_implementation_gates
    )
    concurrency = foundation.concurrency_and_durability
    assert concurrency["camera_open_is_first_possible_effect"] is True
    assert concurrency["serial_open_is_first_possible_effect"] is True
    assert concurrency["every_actuator_off_to_on_requires_unique_envelope"] is True
    assert concurrency["stage_11_and_stage_12_envelopes_must_differ"] is True
    assert concurrency["emergency_deenergization_requires_software_permit"] is False
    datasets = foundation.evidence_and_datasets
    assert datasets["native_pixel_count"] == 19_961_856
    assert datasets["legacy_detector_maximum_image_pixels"] == 12_000_000
    assert datasets["implicit_detector_resize_allowed"] is False
    assert datasets["partition_assignment_is_immutable_before_capture"] is True
    assert foundation.commissioning_bundle["phase_order"] == (
        "BOOTSTRAP",
        "REFERENCE_CHARACTERIZATION",
        "NONCONTACT_QUALIFICATION",
        "UNTOUCHED_FINAL_ACCEPTANCE",
    )
    assert foundation.commissioning_bundle["phase_predecessor_hash_required"] is True
    required_components = cast(
        tuple[str, ...],
        foundation.commissioning_bundle["required_components"],
    )
    assert len(required_components) == 39
    assert "camera_frame_freshness" in required_components
    assert "accuracy_budget_assessment" in required_components
    assert "global_quarantine_ledger_head" in required_components
    assert foundation.stage_catalog.produced_bundle_components == required_components
    assert len(foundation.stage_catalog.bundle_component_producers) == 39
    assert (
        foundation.stage_catalog.bundle_component_producers[
            "accuracy_budget_assessment"
        ].value
        == "noncontact_acceptance"
    )


def test_explicit_historical_v1_foundation_remains_readable() -> None:
    foundation = load_physical_onboarding_foundation(
        WORKSPACE, WORKSPACE / "software/config/physical_onboarding_foundation.json"
    )

    assert foundation.foundation_id == "ROCELL-PHYSICAL-ONBOARDING-FOUNDATION-001"
    assert foundation.source_path == (
        WORKSPACE / "software/config/physical_onboarding_foundation.json"
    ).resolve()


def test_every_contract_binding_matches_verified_source_bytes() -> None:
    foundation = load_physical_onboarding_foundation(WORKSPACE)

    for binding in foundation.contracts:
        assert binding.path == binding.resolved_path.relative_to(WORKSPACE).as_posix()
        assert hashlib.sha256(binding.resolved_path.read_bytes()).hexdigest() == (
            binding.sha256
        )


def test_cross_contract_stage_hazard_epoch_and_accuracy_links_close() -> None:
    foundation = load_physical_onboarding_foundation(WORKSPACE)

    stages = foundation.stage_catalog
    stage_ids = {item.stage for item in stages.stages}
    banner_ids = {
        hazard_id for item in stages.stages for hazard_id in item.hazard_banner_ids
    }
    assert banner_ids == set(foundation.hazard_register.by_id)
    assert {
        epoch.value
        for hazard in foundation.hazard_register.hazards
        for epoch in hazard.invalidation_epochs
    } == set(foundation.configuration_epoch_policy.by_id)
    assert all(
        term.owner_stage in stage_ids
        for term in foundation.accuracy_budget_policy.terms
    )
    assert (
        foundation.workcell_interface_contract.source_bindings[
            "configuration_epoch_policy"
        ].sha256
        == foundation.contracts_by_id["ROCELL-CONFIGURATION-EPOCHS-001"].sha256
    )


def test_rejects_coordinated_bundle_requirement_without_stage_producer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Updating both the aggregate bytes and local expectation is insufficient."""

    foundation_path = _cross_contract_sandbox(tmp_path)
    document = json.loads(foundation_path.read_text(encoding="utf-8"))
    required = document["commissioning_bundle"]["required_components"]
    required[required.index("accuracy_budget_assessment")] = (
        "unproduced_accuracy_budget_assessment"
    )
    _write_json(foundation_path, document)

    expected_bundle = copy.deepcopy(foundation_module._EXPECTED_COMMISSIONING_BUNDLE)
    expected_bundle["required_components"] = list(required)
    monkeypatch.setattr(
        foundation_module,
        "_EXPECTED_COMMISSIONING_BUNDLE",
        expected_bundle,
    )

    with pytest.raises(
        PhysicalOnboardingFoundationError,
        match="exactly one stage producer",
    ):
        load_physical_onboarding_foundation(tmp_path, foundation_path)


def test_rejects_coordinated_self_consistent_native_mode_not_bound_by_icd_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mathematically valid aggregate mode must still match every bound source."""

    foundation_path = _cross_contract_sandbox(tmp_path)
    document = json.loads(foundation_path.read_text(encoding="utf-8"))
    evidence = document["evidence_and_datasets"]
    width = 6000
    height = 4000
    pixels = width * height
    evidence.update(
        {
            "native_frame_width_px": width,
            "native_frame_height_px": height,
            "native_pixel_count": pixels,
            "minimum_packed_native_frame_bytes": pixels * 2,
            "thirty_two_minimum_native_frames_bytes": pixels * 2 * 32,
        }
    )
    _write_json(foundation_path, document)

    expected_evidence = copy.deepcopy(foundation_module._EXPECTED_EVIDENCE)
    expected_evidence.update(evidence)
    monkeypatch.setattr(
        foundation_module,
        "_EXPECTED_EVIDENCE",
        expected_evidence,
    )

    with pytest.raises(
        PhysicalOnboardingFoundationError,
        match="does not publish the foundation native mode|B0477 modes differ",
    ):
        load_physical_onboarding_foundation(tmp_path, foundation_path)


def test_rejects_coordinated_packed_byte_counts_not_derived_from_dimensions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Consistent-looking byte fields cannot override the dimensional derivation."""

    foundation_path = _cross_contract_sandbox(tmp_path)
    document = json.loads(foundation_path.read_text(encoding="utf-8"))
    evidence = document["evidence_and_datasets"]
    claimed_pixels = evidence["native_pixel_count"] + 1
    evidence.update(
        {
            "native_pixel_count": claimed_pixels,
            "minimum_packed_native_frame_bytes": claimed_pixels * 2,
            "thirty_two_minimum_native_frames_bytes": claimed_pixels * 2 * 32,
        }
    )
    _write_json(foundation_path, document)

    expected_evidence = copy.deepcopy(foundation_module._EXPECTED_EVIDENCE)
    expected_evidence.update(evidence)
    monkeypatch.setattr(
        foundation_module,
        "_EXPECTED_EVIDENCE",
        expected_evidence,
    )

    with pytest.raises(
        PhysicalOnboardingFoundationError,
        match="pixel and packed YUY2 byte counts",
    ):
        load_physical_onboarding_foundation(tmp_path, foundation_path)


def test_cross_cutting_contract_is_deeply_immutable() -> None:
    foundation = load_physical_onboarding_foundation(WORKSPACE)

    with pytest.raises(TypeError):
        foundation.contracts_by_id["extra"] = foundation.contracts[0]  # type: ignore[index]
    with pytest.raises(TypeError):
        foundation.concurrency_and_durability["automatic_attempt_replay_allowed"] = True  # type: ignore[index]
    partitions = foundation.evidence_and_datasets["calibration_partitions"]
    assert isinstance(partitions, tuple)
    with pytest.raises(TypeError):
        partitions[0] = "FIT_AND_ACCEPT"  # type: ignore[index]
    bootstrap = foundation.calibration_assurance["precalibration_motion_bootstrap"]
    assert isinstance(bootstrap, dict) is False
    with pytest.raises(TypeError):
        bootstrap["contact_allowed"] = True  # type: ignore[index]


@pytest.mark.parametrize(
    ("section", "field", "unsafe_value"),
    [
        ("authority", "device_io_authorized", True),
        ("authority", "motion_authorized", True),
        (
            "concurrency_and_durability",
            "automatic_attempt_replay_allowed",
            True,
        ),
        (
            "concurrency_and_durability",
            "effectful_action_allowed_when_durability_unqualified",
            True,
        ),
        (
            "concurrency_and_durability",
            "emergency_deenergization_requires_software_permit",
            True,
        ),
        ("evidence_and_datasets", "partition_overlap_allowed", True),
        ("evidence_and_datasets", "implicit_detector_resize_allowed", True),
        (
            "evidence_and_datasets",
            "untouched_acceptance_may_drive_model_selection",
            True,
        ),
        (
            "commissioning_bundle",
            "physical_runtime_nominal_fallback_allowed",
            True,
        ),
        (
            "threat_model",
            "cryptographic_physical_provenance_claim_allowed",
            True,
        ),
    ],
)
def test_rejects_cross_cutting_safety_weakening(
    tmp_path: Path,
    section: str,
    field: str,
    unsafe_value: object,
) -> None:
    path = _temporary_foundation(
        tmp_path,
        lambda document: document[section].update({field: unsafe_value}),
    )
    with pytest.raises(PhysicalOnboardingFoundationError, match=section):
        load_physical_onboarding_foundation(tmp_path, path)


def test_rejects_runtime_activation(tmp_path: Path) -> None:
    path = _temporary_foundation(
        tmp_path, lambda document: document.update({"runtime_activation": True})
    )
    with pytest.raises(PhysicalOnboardingFoundationError, match="runtime_activation"):
        load_physical_onboarding_foundation(tmp_path, path)


def test_rejects_partition_commit_delayed_until_first_fit(tmp_path: Path) -> None:
    def weaken_partition_commit(document: dict[str, Any]) -> None:
        datasets = document["evidence_and_datasets"]
        datasets.pop("partition_assignment_is_immutable_before_capture")
        datasets["partition_assignment_is_immutable_before_first_fit"] = True

    path = _temporary_foundation(tmp_path, weaken_partition_commit)
    with pytest.raises(
        PhysicalOnboardingFoundationError,
        match="evidence_and_datasets",
    ):
        load_physical_onboarding_foundation(tmp_path, path)


def test_rejects_closed_or_missing_implementation_gate(tmp_path: Path) -> None:
    path = _temporary_foundation(
        tmp_path,
        lambda document: document["open_implementation_gates"].pop(),
    )
    with pytest.raises(PhysicalOnboardingFoundationError, match="implementation gates"):
        load_physical_onboarding_foundation(tmp_path, path)


def test_rejects_unknown_root_or_nested_field(tmp_path: Path) -> None:
    root_path = _temporary_foundation(
        tmp_path / "root",
        lambda document: document.update({"silent_extension": True}),
    )
    with pytest.raises(PhysicalOnboardingFoundationError, match="fields differ"):
        load_physical_onboarding_foundation(tmp_path / "root", root_path)

    nested_path = _temporary_foundation(
        tmp_path / "nested",
        lambda document: document["threat_model"].update({"silent_extension": True}),
    )
    with pytest.raises(PhysicalOnboardingFoundationError, match="threat_model"):
        load_physical_onboarding_foundation(tmp_path / "nested", nested_path)


def test_rejects_duplicate_json_field(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(
        FOUNDATION_PATH.read_text(encoding="utf-8").replace(
            '"runtime_activation": false,',
            '"runtime_activation": false,\n  "runtime_activation": false,',
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(PhysicalOnboardingFoundationError, match="duplicate"):
        load_physical_onboarding_foundation(tmp_path, path)


@pytest.mark.parametrize("number", ["1.0", "NaN", "Infinity", "1e9999"])
def test_rejects_float_or_nonfinite_number(tmp_path: Path, number: str) -> None:
    path = tmp_path / "number.json"
    path.write_text(
        FOUNDATION_PATH.read_text(encoding="utf-8").replace(
            '"revision": 2,', f'"revision": {number},', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        PhysicalOnboardingFoundationError,
        match="floating-point|nonfinite",
    ):
        load_physical_onboarding_foundation(tmp_path, path)


def test_rejects_bool_integer_alias(tmp_path: Path) -> None:
    path = _temporary_foundation(
        tmp_path, lambda document: document.update({"revision": True})
    )
    with pytest.raises(PhysicalOnboardingFoundationError, match="revision"):
        load_physical_onboarding_foundation(tmp_path, path)


def test_rejects_oversize_foundation_before_json_parse(tmp_path: Path) -> None:
    path = tmp_path / "oversize.json"
    path.write_bytes(b" " * (MAX_PHYSICAL_ONBOARDING_FOUNDATION_BYTES + 1))
    with pytest.raises(PhysicalOnboardingFoundationError, match="size"):
        load_physical_onboarding_foundation(tmp_path, path)


def test_rejects_foundation_outside_workspace(tmp_path: Path) -> None:
    with pytest.raises(PhysicalOnboardingFoundationError, match="beneath"):
        load_physical_onboarding_foundation(tmp_path, FOUNDATION_PATH)


def test_rejects_contract_path_traversal(tmp_path: Path) -> None:
    path = _temporary_foundation(
        tmp_path,
        lambda document: document["contracts"][0].update(
            {"path": "../authority_effect_policy.json"}
        ),
    )
    with pytest.raises(PhysicalOnboardingFoundationError, match="normalized"):
        load_physical_onboarding_foundation(tmp_path, path)


def test_rejects_referenced_contract_hash_drift(tmp_path: Path) -> None:
    foundation_path = _contract_sandbox(tmp_path)
    source = tmp_path / CONTRACT_RELATIVE_PATHS[0]
    source.write_bytes(source.read_bytes() + b"\n")

    with pytest.raises(PhysicalOnboardingFoundationError, match="SHA-256 mismatch"):
        load_physical_onboarding_foundation(tmp_path, foundation_path)


def test_rejects_unsafe_contract_even_if_aggregate_digest_is_updated(
    tmp_path: Path,
) -> None:
    foundation_path = _contract_sandbox(tmp_path)
    source = tmp_path / CONTRACT_RELATIVE_PATHS[0]
    document = json.loads(source.read_text(encoding="utf-8"))
    document["runtime_activation"] = True
    source.write_text(
        json.dumps(document, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    foundation = json.loads(foundation_path.read_text(encoding="utf-8"))
    foundation["contracts"][0]["sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    foundation_path.write_text(
        json.dumps(foundation, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        PhysicalOnboardingFoundationError,
        match="specialized contract failed validation",
    ):
        load_physical_onboarding_foundation(tmp_path, foundation_path)


def test_rejects_foundation_symlink(tmp_path: Path) -> None:
    target = tmp_path / "foundation.json"
    shutil.copy2(FOUNDATION_PATH, target)
    alias = tmp_path / "foundation-alias.json"
    try:
        os.symlink(target, alias)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(PhysicalOnboardingFoundationError, match="symlink"):
        load_physical_onboarding_foundation(tmp_path, alias)


def test_rejects_referenced_contract_symlink(tmp_path: Path) -> None:
    foundation_path = _contract_sandbox(tmp_path)
    source = tmp_path / CONTRACT_RELATIVE_PATHS[0]
    target = source.with_name("authority_effect_policy_real.json")
    source.replace(target)
    try:
        os.symlink(target, source)
    except (NotImplementedError, OSError) as exc:
        target.replace(source)
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(PhysicalOnboardingFoundationError, match="symlink"):
        load_physical_onboarding_foundation(tmp_path, foundation_path)
