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


def _review_module():
    return _load_module(
        "arm252_review",
        ROOT
        / "software/integrations/isaac_sim/"
        "nominal_route_physics_experiment_review.py",
    )


def _arm251_fixtures():
    return _load_module(
        "arm251_test_fixtures",
        ROOT / "software/tests/unit/test_nominal_route_physics_experiment.py",
    )


def _bundle():
    fixtures = _arm251_fixtures()
    producer = fixtures._module()
    sources = fixtures._inputs()
    experiment = producer.build_experiment(
        **sources,
        source_files_sha256=SOURCE_HASHES,
    )
    return experiment, sources


def _build():
    experiment, sources = _bundle()
    return _review_module().build_review(
        experiment=experiment,
        **sources,
        source_files_sha256=SOURCE_HASHES,
        experiment_file_sha256="5" * 64,
    )


def test_arm252_independently_accepts_exact_arm251_contract() -> None:
    result = _build()

    assert result["status"] == (
        "ACCEPTED_FOR_ONE_SEPARATELY_AUTHORIZED_NOMINAL_SIMULATION_ATTEMPT"
    )
    assert result["review_findings"] == {
        "source_identity_and_canonical_hashes_verified": True,
        "nominal_fixture_scope_verified": True,
        "single_space_route_scope_verified": True,
        "regeneration_window_654_through_940_verified": True,
        "clearance_displacement_ik_and_joint_step_limits_verified": True,
        "truth_isolation_verified": True,
        "zero_hardware_and_physical_authority_verified": True,
    }


def test_arm252_admits_only_one_later_space_simulation_attempt() -> None:
    admission = _build()["simulation_attempt_admission"]

    assert admission == {
        "case_id": "nominal-fixture-baseline",
        "episode_id": "episode-ef340d0ad2740c118d87",
        "target_id": "SPACE",
        "maximum_attempt_count": 1,
        "automatic_retry": False,
        "fresh_source_revalidation_required_at_launch": True,
        "launch_authorized_by_this_review": False,
        "hardware_or_physical_authority": False,
    }


def test_arm252_keeps_automatic_typing_goal_explicit() -> None:
    goal = _build()["automatic_typing_goal"]

    assert goal["current_stage"] == "SINGLE_KEY_SPACE_NOMINAL_ROUTE_REGENERATION"
    assert goal["next_after_pass"] == (
        "EXPAND_THE_SAME_CONTRACT_TO_A_REPRESENTATIVE_MULTI_KEY_SET"
    )
    assert goal["later_stage"] == (
        "VISION_CONDITIONED_KEY_LOCALIZATION_AND_ROLLING_HORIZON_TYPING"
    )
    assert goal["physical_typing_requires_separate_installed_qualification"] is True


def test_arm252_review_grants_no_execution_or_physical_authority() -> None:
    result = _build()

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
    ("source", "mutate"),
    [
        ("nominal_profile", lambda value: value["board"].update(maximum_B_mm=[])),
        ("route_plan", lambda value: value.update(target_id="ENTER")),
        (
            "correction_plan",
            lambda value: value["materialization_contract"].update(
                minimum_noncontact_tool_key_clearance_mm=0.0
            ),
        ),
        ("toolchain_lock", lambda value: value.update(selection_status="REJECTED")),
    ],
)
def test_arm252_rejects_source_drift(source: str, mutate) -> None:
    module = _review_module()
    experiment, sources = _bundle()
    changed = copy.deepcopy(sources)
    mutate(changed[source])

    with pytest.raises(module.NominalRoutePhysicsExperimentReviewError):
        module.build_review(
            experiment=experiment,
            **changed,
            source_files_sha256=SOURCE_HASHES,
            experiment_file_sha256="5" * 64,
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["experiment_matrix"][0].update(
            simulator_runs_requested=2
        ),
        lambda value: value["acceptance_contract"].update(
            maximum_noncontact_key_displacement_mm=1.0
        ),
        lambda value: value.update(isaac_execution_authorized=True),
        lambda value: value["truth_isolation"].update(
            simulator_truth_may_enter_model_input=True
        ),
    ],
)
def test_arm252_rejects_experiment_drift(mutate) -> None:
    module = _review_module()
    experiment, sources = _bundle()
    mutate(experiment)

    with pytest.raises(module.NominalRoutePhysicsExperimentReviewError):
        module.build_review(
            experiment=experiment,
            **sources,
            source_files_sha256=SOURCE_HASHES,
            experiment_file_sha256="5" * 64,
        )


def test_arm252_rejects_file_identity_mismatch() -> None:
    module = _review_module()
    experiment, sources = _bundle()
    changed_hashes = {**SOURCE_HASHES, "route_plan": "9" * 64}

    with pytest.raises(
        module.NominalRoutePhysicsExperimentReviewError,
        match="source file hashes",
    ):
        module.build_review(
            experiment=experiment,
            **sources,
            source_files_sha256=changed_hashes,
            experiment_file_sha256="5" * 64,
        )
