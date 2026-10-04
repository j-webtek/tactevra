from __future__ import annotations

import copy
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/tests/integration"))

import test_typing_shadow_pipeline_v1 as shadow_fixture  # noqa: E402
from rocell.application.typing_endpoint_atlas_observer_v1 import (  # noqa: E402
    TypingEndpointAtlasObserverV1Error,
    TypingEndpointAtlasRecorderV1,
    parse_typing_endpoint_atlas_observation_v1,
)
from rocell.application.typing_shadow_pipeline_v1 import (  # noqa: E402
    run_typing_shadow_pipeline_v1,
)


def _observed(
    targets: tuple[str, ...] = ("R", "O", "B", "O", "T"),
    text: str = "robot",
):
    inputs = shadow_fixture._inputs(targets, text)
    reference = run_typing_shadow_pipeline_v1(**inputs)
    recorder = TypingEndpointAtlasRecorderV1("endpoint-atlas-test")
    observed = run_typing_shadow_pipeline_v1(
        **inputs, endpoint_atlas_recorder=recorder
    )
    report = recorder.build(
        typing_trajectory_plan_sha256=observed["stage_hashes"][
            "typing_trajectory_plan_sha256"
        ],
        typing_trajectory_ik_screen_sha256=observed["stage_hashes"][
            "typing_trajectory_ik_screen_sha256"
        ],
    )
    return reference, observed, report


def _rehash(report: dict) -> None:
    import rocell.application.typing_endpoint_atlas_observer_v1 as module

    core = {
        key: value for key, value in report.items()
        if key != "endpoint_atlas_observation_sha256"
    }
    report["endpoint_atlas_observation_sha256"] = module._sha(core)


@pytest.fixture(scope="module")
def mutation_report() -> dict:
    return _observed(("H", "H"), "hh")[2]


def test_endpoint_observation_is_decision_neutral_bounded_and_zero_authority():
    reference, observed, report = _observed()

    assert observed == reference
    assert dict(parse_typing_endpoint_atlas_observation_v1(report)) == report
    assert report["endpoint_observation_count"] == 17
    assert report["transition_observation_count"] == 16
    assert report["repeated_endpoint_observation_count"] >= 3
    assert report["unique_endpoint_count"] < report["endpoint_observation_count"]
    assert report["atlas_use_authorized"] is False
    assert report["decision_input"] is False
    assert report["controller_commands"] == []
    assert report["hardware_access"] is report["physical_authority"] is False


def test_repeated_target_endpoints_are_counted_without_authorizing_reuse():
    _, _, report = _observed(("H", "H", "1", "PERIOD"), "hh1.")
    repeated = [
        item for item in report["endpoint_atlas"]
        if item["observation_count"] > 1
    ]
    assert repeated
    assert {item["target_id"] for item in repeated} == {"H", None}
    assert {item["phase"] for item in repeated} == {
        "PARK", "HOVER", "CONTACT", "RETRACT"
    }
    assert report["atlas_use_authorized"] is False


def test_observer_sample_bound_fails_closed_without_changing_default_path():
    inputs = shadow_fixture._inputs()
    recorder = TypingEndpointAtlasRecorderV1(
        "endpoint-atlas-capacity", maximum_samples=1
    )
    with pytest.raises(
        TypingEndpointAtlasObserverV1Error, match="sample bound exceeded"
    ):
        run_typing_shadow_pipeline_v1(
            **inputs, endpoint_atlas_recorder=recorder
        )
    assert run_typing_shadow_pipeline_v1(**inputs)["physical_authority"] is False


@pytest.mark.parametrize("mutation,match", (
    ("hash", "hash differs"),
    ("endpoint", "identity differs"),
    ("atlas", "endpoint atlas differs"),
    ("transition", "transition atlas differs"),
    ("count", "aggregate counts differ"),
    ("authority", "zero authority"),
))
def test_endpoint_observation_mutations_fail_closed(
    mutation_report: dict, mutation: str, match: str,
):
    report = copy.deepcopy(mutation_report)
    if mutation == "hash":
        report["endpoint_atlas_observation_sha256"] = "f" * 64
    elif mutation == "endpoint":
        report["endpoint_observations"][0]["phase"] = "CONTACT"
        _rehash(report)
    elif mutation == "atlas":
        report["endpoint_atlas"][0]["observation_count"] += 1
        _rehash(report)
    elif mutation == "transition":
        report["transition_atlas"][0]["observation_count"] += 1
        _rehash(report)
    elif mutation == "count":
        report["unique_endpoint_count"] += 1
        _rehash(report)
    else:
        report["atlas_use_authorized"] = True
        _rehash(report)
    with pytest.raises(TypingEndpointAtlasObserverV1Error, match=match):
        parse_typing_endpoint_atlas_observation_v1(report)
