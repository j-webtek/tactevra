from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from rocell.application.pre_camera_typing_qualification_basis_v1 import (
    DEFAULT_BASIS,
    EXPECTED_FIXTURES,
    PreCameraTypingQualificationBasisV1Error,
    load_pre_camera_typing_qualification_basis_v1,
    parse_pre_camera_typing_qualification_basis_v1,
    verify_pre_camera_typing_pins_v1,
)


WORKSPACE = Path(__file__).resolve().parents[3]


def _document() -> dict:
    return json.loads((WORKSPACE / DEFAULT_BASIS).read_text(encoding="utf-8"))


def test_retained_pc0_basis_and_pins_are_reproducible() -> None:
    first = load_pre_camera_typing_qualification_basis_v1(WORKSPACE)
    second = load_pre_camera_typing_qualification_basis_v1(WORKSPACE)

    assert first.basis_sha256 == second.basis_sha256
    assert tuple(item.fixture_id for item in first.fixtures) == EXPECTED_FIXTURES
    assert dict(first.document["authority"]) == {
        "controller_startup": False,
        "transport_open": False,
        "controller_write": False,
        "movement": False,
        "torque_change": False,
        "firmware_installation": False,
    }


def test_pc0_fixture_sequences_preserve_order_and_repetition() -> None:
    basis = load_pre_camera_typing_qualification_basis_v1(WORKSPACE)
    fixtures = {item.fixture_id: item for item in basis.fixtures}

    assert fixtures["type-robot"].expected_target_ids == ("R", "O", "B", "O", "T")
    assert fixtures["type-book"].expected_target_ids == ("B", "O", "O", "K")
    assert fixtures["repeat-punctuation"].expected_target_ids == (
        "H",
        "H",
        "1",
        "PERIOD",
    )
    assert fixtures["same-key-repeat"].expected_target_ids == ("A", "A", "A")


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value["authority"].__setitem__("movement", True),
        lambda value: value.__setitem__("evidence_class", "MEASURED"),
        lambda value: value["canonical_fixtures"].reverse(),
        lambda value: value["outcome_codes"].remove(
            "OUTCOME_UNCERTAIN_RETRY_FORBIDDEN"
        ),
        lambda value: value["synthetic_joint_dynamics_profile"].__setitem__(
            "physical_tracking_qualification", True
        ),
        lambda value: value["zero_write_controller_profile"].__setitem__(
            "transport_enabled", True
        ),
    ],
)
def test_pc0_basis_fails_closed_on_authority_or_contract_mutation(mutator) -> None:
    document = deepcopy(_document())
    mutator(document)

    with pytest.raises(PreCameraTypingQualificationBasisV1Error):
        parse_pre_camera_typing_qualification_basis_v1(document)


def test_pc0_basis_rejects_crossed_source_pin() -> None:
    document = deepcopy(_document())
    document["pinned_sources"][0]["sha256"] = "0" * 64
    basis = parse_pre_camera_typing_qualification_basis_v1(document)

    with pytest.raises(
        PreCameraTypingQualificationBasisV1Error,
        match="source hash differs",
    ):
        verify_pre_camera_typing_pins_v1(basis, WORKSPACE)


def test_pc0_fixture_identity_hashes_bind_their_ids() -> None:
    document = deepcopy(_document())
    document["fixture_identities"]["joint_dynamics_profile_id"] += "-crossed"

    with pytest.raises(
        PreCameraTypingQualificationBasisV1Error,
        match="does not bind",
    ):
        parse_pre_camera_typing_qualification_basis_v1(document)
