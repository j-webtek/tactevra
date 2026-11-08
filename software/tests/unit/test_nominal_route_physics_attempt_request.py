from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE_HASHES = {
    "nominal_profile": "1" * 64,
    "route_plan": "2" * 64,
    "correction_plan": "3" * 64,
    "toolchain_lock": "4" * 64,
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module():
    return _load_module(
        "arm253_request",
        ROOT / "software/integrations/isaac_sim/"
        "nominal_route_physics_attempt_request.py",
    )


def _review_fixtures():
    return _load_module(
        "arm252_test_fixtures_for_arm253",
        ROOT / "software/tests/unit/test_nominal_route_physics_experiment_review.py",
    )


def _build():
    fixtures = _review_fixtures()
    experiment, sources = fixtures._bundle()
    review = fixtures._review_module().build_review(
        experiment=experiment,
        **sources,
        source_files_sha256=SOURCE_HASHES,
        experiment_file_sha256="5" * 64,
    )
    result = _module().build_request(
        review,
        experiment,
        source_files_sha256=SOURCE_HASHES,
        review_file_sha256="6" * 64,
        experiment_file_sha256="5" * 64,
    )
    return result, review, experiment


def test_arm253_builds_exact_one_attempt_request() -> None:
    result, _, _ = _build()

    assert result["status"] == (
        "READY_FOR_EXPLICIT_ONE_ATTEMPT_SIMULATION_AUTHORIZATION"
    )
    assert result["attempt_contract"] == {
        "maximum_attempt_count": 1,
        "automatic_retry": False,
        "fresh_review_and_source_revalidation_required_at_launch": True,
        "generate_only_rows_654_through_940": True,
        "trajectory_playback": False,
        "native_replay": False,
        "hardware_or_physical_authority": False,
        "stop_and_retain_receipt_on_first_failure": True,
    }


def test_arm253_freezes_exact_authorization_statement() -> None:
    result, _, _ = _build()

    assert result["required_authorization_statement"] == (
        "I authorize exactly one ARM-253 nominal SPACE route-physics simulation "
        "attempt for episode-ef340d0ad2740c118d87, with no automatic retry, "
        "no trajectory playback, and no hardware or physical authority."
    )


def test_arm253_preserves_automatic_typing_progression() -> None:
    result, _, _ = _build()

    assert result["automatic_typing_goal"]["current_stage"] == (
        "SINGLE_KEY_SPACE_NOMINAL_ROUTE_REGENERATION"
    )
    assert result["automatic_typing_goal"]["next_after_pass"] == (
        "EXPAND_THE_SAME_CONTRACT_TO_A_REPRESENTATIVE_MULTI_KEY_SET"
    )


def test_arm253_grants_no_execution_or_physical_authority() -> None:
    result, _, _ = _build()

    assert result["isaac_execution_authorized"] is False
    assert result["isaac_started"] is False
    assert result["gpu_started"] is False
    assert result["joint_targets_materialized"] is False
    assert result["trajectory_playback_authorized"] is False
    assert result["native_replay_authorized"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False
    assert result["controller_commands"] == []
    assert result["wire_commands"] == []
    assert result["gate_promotions"] == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["simulation_attempt_admission"].update(
            maximum_attempt_count=2
        ),
        lambda value: value["simulation_attempt_admission"].update(
            automatic_retry=True
        ),
        lambda value: value.update(isaac_execution_authorized=True),
        lambda value: value["automatic_typing_goal"].update(current_stage="MULTI_KEY"),
    ],
)
def test_arm253_rejects_review_drift(mutate) -> None:
    module = _module()
    _, review, experiment = _build()
    changed = copy.deepcopy(review)
    mutate(changed)
    changed.pop("review_sha256")
    changed["review_sha256"] = module._sha(changed)

    with pytest.raises(module.NominalRoutePhysicsAttemptRequestError):
        module.build_request(
            changed,
            experiment,
            source_files_sha256=SOURCE_HASHES,
            review_file_sha256="6" * 64,
            experiment_file_sha256="5" * 64,
        )


def test_arm253_rejects_experiment_or_file_drift() -> None:
    module = _module()
    _, review, experiment = _build()
    changed = copy.deepcopy(experiment)
    changed["acceptance_contract"]["maximum_adjacent_joint_step_rad"] = 0.5
    changed.pop("experiment_sha256")
    changed["experiment_sha256"] = module._sha(changed)

    with pytest.raises(module.NominalRoutePhysicsAttemptRequestError):
        module.build_request(
            review,
            changed,
            source_files_sha256=SOURCE_HASHES,
            review_file_sha256="6" * 64,
            experiment_file_sha256="5" * 64,
        )

    with pytest.raises(module.NominalRoutePhysicsAttemptRequestError):
        module.build_request(
            review,
            experiment,
            source_files_sha256={**SOURCE_HASHES, "route_plan": "9" * 64},
            review_file_sha256="6" * 64,
            experiment_file_sha256="5" * 64,
        )
