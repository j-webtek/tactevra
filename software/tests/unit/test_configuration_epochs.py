from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from rocell.application.configuration_epochs import (
    ConfigurationEpochPolicyError,
    load_configuration_epoch_policy,
)
from rocell.application.physical_onboarding import PhysicalOnboardingStage


WORKSPACE = Path(__file__).resolve().parents[3]
POLICY_PATH = WORKSPACE / "software/config/configuration_epochs.json"


def _document() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _temporary_policy(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> Path:
    document = copy.deepcopy(_document())
    mutate(document)
    path = tmp_path / "configuration_epochs.json"
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def test_loads_configuration_epoch_policy_read_only() -> None:
    before = POLICY_PATH.read_bytes()

    policy = load_configuration_epoch_policy(WORKSPACE)

    assert POLICY_PATH.read_bytes() == before
    assert policy.zero_physical_authority
    assert len(policy.epochs) == 8
    assert policy.by_id["camera_support_optics"].invalidates_from_stage is (
        PhysicalOnboardingStage.CAMERA_RECEIPT
    )
    assert policy.by_id["board_tags_bench"].invalidates_from_stage is (
        PhysicalOnboardingStage.CAMERA_RECEIPT
    )
    assert policy.by_id["phone_station"].invalidates_from_stage is (
        PhysicalOnboardingStage.REFERENCE_FRAME_CALIBRATION
    )
    assert policy.physical_blockers


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("robot_power_authorized", True),
        ("motion_authorized", True),
        ("contact_authorized", True),
        ("physical_release_effect", "RELEASED"),
    ],
)
def test_rejects_authority_escalation(
    tmp_path: Path, field: str, value: object
) -> None:
    path = _temporary_policy(
        tmp_path,
        lambda document: document["authority"].update({field: value}),
    )

    with pytest.raises(ConfigurationEpochPolicyError, match="zero authority"):
        load_configuration_epoch_policy(tmp_path, path)


def test_rejects_unknown_epoch_stage(tmp_path: Path) -> None:
    path = _temporary_policy(
        tmp_path,
        lambda document: document["epochs"][0].update(
            {"invalidates_from_stage": "imaginary_stage"}
        ),
    )

    with pytest.raises(ConfigurationEpochPolicyError, match="unknown"):
        load_configuration_epoch_policy(tmp_path, path)


def test_rejects_late_board_or_bench_invalidation_boundary(tmp_path: Path) -> None:
    path = _temporary_policy(
        tmp_path,
        lambda document: document["epochs"][2].update(
            {"invalidates_from_stage": "static_registration"}
        ),
    )

    with pytest.raises(ConfigurationEpochPolicyError, match="boundary changed"):
        load_configuration_epoch_policy(tmp_path, path)


def test_rejects_missing_or_reordered_epoch(tmp_path: Path) -> None:
    path = _temporary_policy(tmp_path, lambda document: document["epochs"].pop())

    with pytest.raises(ConfigurationEpochPolicyError, match="order or membership"):
        load_configuration_epoch_policy(tmp_path, path)


def test_rejects_duplicate_change_trigger(tmp_path: Path) -> None:
    def mutate(document: dict[str, Any]) -> None:
        trigger = document["epochs"][0]["change_triggers"][0]
        document["epochs"][0]["change_triggers"].append(trigger)

    path = _temporary_policy(tmp_path, mutate)
    with pytest.raises(ConfigurationEpochPolicyError, match="duplicates"):
        load_configuration_epoch_policy(tmp_path, path)


def test_rejects_unknown_root_field(tmp_path: Path) -> None:
    path = _temporary_policy(
        tmp_path,
        lambda document: document.update({"unversioned_extension": True}),
    )

    with pytest.raises(ConfigurationEpochPolicyError, match="fields differ"):
        load_configuration_epoch_policy(tmp_path, path)


def test_rejects_duplicate_json_field(tmp_path: Path) -> None:
    original = POLICY_PATH.read_text(encoding="utf-8")
    duplicated = original.replace(
        '"runtime_activation": false,',
        '"runtime_activation": false,\n  "runtime_activation": false,',
        1,
    )
    path = tmp_path / "duplicate.json"
    path.write_text(duplicated, encoding="utf-8")

    with pytest.raises(ConfigurationEpochPolicyError, match="duplicate JSON field"):
        load_configuration_epoch_policy(tmp_path, path)


def test_rejects_float_anywhere(tmp_path: Path) -> None:
    original = POLICY_PATH.read_text(encoding="utf-8")
    path = tmp_path / "float.json"
    path.write_text(original.replace('"revision": 1,', '"revision": 1.0,'), encoding="utf-8")

    with pytest.raises(ConfigurationEpochPolicyError, match="must not use floats"):
        load_configuration_epoch_policy(tmp_path, path)


def test_rejects_policy_outside_workspace(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationEpochPolicyError, match="beneath the workspace"):
        load_configuration_epoch_policy(tmp_path, POLICY_PATH)


def test_rejects_oversized_policy_at_file_boundary(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * (256 * 1024 + 1))
    with pytest.raises(ConfigurationEpochPolicyError, match="could not read"):
        load_configuration_epoch_policy(tmp_path, path)
