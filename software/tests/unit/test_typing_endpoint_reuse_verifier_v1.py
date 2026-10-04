from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/tests/integration"))

import test_typing_shadow_pipeline_v1 as shadow_fixture  # noqa: E402
import rocell.application.typing_endpoint_reuse_verifier_v1 as module  # noqa: E402
from rocell.application.context import SimulationContextError  # noqa: E402
from rocell.application.context_lifecycle_v1 import (  # noqa: E402
    SimulationContextLifecycleV1,
)
from rocell.application.typing_endpoint_reuse_verifier_v1 import (  # noqa: E402
    TypingEndpointReuseVerifierV1,
    TypingEndpointReuseVerifierV1Error,
    parse_typing_endpoint_reuse_verifier_snapshot_v1,
)
from rocell.application.typing_planner_preparation_v1 import (  # noqa: E402
    prepare_typing_planner_v1,
)
from rocell.application.typing_shadow_pipeline_v1 import (  # noqa: E402
    run_typing_shadow_pipeline_v1,
)
from rocell.application.typing_trajectory_ik_screen_v1 import (  # noqa: E402
    TypingTrajectoryIkScreenV1Error,
)


VALIDATOR = Draft202012Validator(json.loads((
    ROOT / "software/ai/schemas/typing_endpoint_reuse_verifier_v1.schema.json"
).read_text(encoding="utf-8")))


def _resources(service: str = "endpoint-reuse-test"):
    lifecycle = SimulationContextLifecycleV1.start(
        shadow_fixture.ingress_fixture.WORKSPACE,
        shadow_fixture.ingress_fixture.MANIFEST,
        service_instance_id=service,
        issued_monotonic_ns=100,
    )
    context = lifecycle.binding().context
    prepared = prepare_typing_planner_v1(context, lifecycle)
    return lifecycle, context, prepared


def _run(
    targets: tuple[str, ...] = ("R", "O", "B", "O", "T"),
    text: str = "robot", *, maximum_entries: int = 256,
):
    lifecycle, context, prepared = _resources()
    inputs = shadow_fixture._inputs(targets, text, context=context)
    reference = run_typing_shadow_pipeline_v1(**inputs)
    verifier = TypingEndpointReuseVerifierV1.create(
        context, lifecycle, maximum_entries=maximum_entries,
    )
    common = {
        "context_lifecycle": lifecycle,
        "prepared_planner": prepared,
        "endpoint_reuse_verifier": verifier,
    }
    first = run_typing_shadow_pipeline_v1(**inputs, **common)
    second = run_typing_shadow_pipeline_v1(**inputs, **common)
    return reference, first, second, verifier, lifecycle, inputs, common


@pytest.fixture(scope="module")
def stable_run():
    return _run()


def _rehash(value: dict) -> None:
    unsigned = dict(value)
    unsigned.pop("verifier_snapshot_sha256", None)
    value["verifier_snapshot_sha256"] = module._sha(unsigned)


def test_reuse_candidates_match_reference_without_becoming_decisions(
    stable_run,
) -> None:
    reference, first, second, verifier, _, _, _ = stable_run
    snapshot = verifier.snapshot()
    VALIDATOR.validate(snapshot)
    assert parse_typing_endpoint_reuse_verifier_snapshot_v1(snapshot) == snapshot
    assert reference == first == second
    assert snapshot["entry_count"] > 0
    assert snapshot["hits"] == snapshot["canonical_matches"] > 0
    assert snapshot["canonical_conflicts"] == 0
    assert snapshot["candidate_used_for_decision"] is False
    assert snapshot["diagnostics_used_for_admission"] is False
    assert snapshot["warm_start_authorized"] is False
    assert snapshot["controller_commands"] == []
    assert snapshot["hardware_access"] is snapshot["physical_authority"] is False


def test_capacity_and_invalidation_remain_bounded_and_zero_authority() -> None:
    reference, first, second, verifier, _, _, _ = _run(
        ("H", "I"), "hi", maximum_entries=1,
    )
    assert reference == first == second
    snapshot = verifier.snapshot()
    assert snapshot["entry_count"] == 1
    assert snapshot["capacity_skips"] > 0
    parse_typing_endpoint_reuse_verifier_snapshot_v1(snapshot)
    verifier.invalidate()
    invalidated = verifier.snapshot()
    assert invalidated["active"] is False
    assert invalidated["entries"] == []
    parse_typing_endpoint_reuse_verifier_snapshot_v1(invalidated)

    lifecycle, context, prepared = _resources("sample-bound")
    bounded = TypingEndpointReuseVerifierV1.create(
        context, lifecycle, maximum_samples=1,
    )
    with pytest.raises(
        TypingEndpointReuseVerifierV1Error, match="observation bound"
    ):
        run_typing_shadow_pipeline_v1(
            **shadow_fixture._inputs(context=context),
            context_lifecycle=lifecycle,
            prepared_planner=prepared,
            endpoint_reuse_verifier=bounded,
        )


def test_corruption_conflict_context_and_lifecycle_changes_fail_closed() -> None:
    _, _, _, verifier, lifecycle, inputs, common = _run(("H", "H"), "hh")
    key = next(iter(verifier._entries))
    entry = verifier._entries[key]
    verifier._entries[key] = replace(entry, entry_sha256="f" * 64)
    with pytest.raises(TypingEndpointReuseVerifierV1Error, match="integrity"):
        run_typing_shadow_pipeline_v1(**inputs, **common)

    verifier._entries[key] = entry
    verifier._decision_context_sha256 = "f" * 64
    with pytest.raises(
        TypingEndpointReuseVerifierV1Error, match="decision context"
    ):
        run_typing_shadow_pipeline_v1(**inputs, **common)

    verifier._decision_context_sha256 = None
    lifecycle.reload_sources(issued_monotonic_ns=101)
    with pytest.raises(SimulationContextError):
        run_typing_shadow_pipeline_v1(**inputs, **common)

    other_lifecycle, other_context, other_prepared = _resources("other-context")
    other_inputs = shadow_fixture._inputs(context=other_context)
    with pytest.raises(SimulationContextError):
        run_typing_shadow_pipeline_v1(
            **other_inputs,
            context_lifecycle=other_lifecycle,
            prepared_planner=other_prepared,
            endpoint_reuse_verifier=verifier,
        )

    restart_lifecycle, restart_context, restart_prepared = _resources(
        "restart-old"
    )
    restart_verifier = TypingEndpointReuseVerifierV1.create(
        restart_context, restart_lifecycle
    )
    restart_inputs = shadow_fixture._inputs(context=restart_context)
    run_typing_shadow_pipeline_v1(
        **restart_inputs,
        context_lifecycle=restart_lifecycle,
        prepared_planner=restart_prepared,
        endpoint_reuse_verifier=restart_verifier,
    )
    replacement = restart_lifecycle.restart(
        service_instance_id="restart-new", issued_monotonic_ns=102,
    )
    replacement_context = replacement.binding().context
    with pytest.raises(SimulationContextError):
        run_typing_shadow_pipeline_v1(
            **shadow_fixture._inputs(context=replacement_context),
            context_lifecycle=replacement,
            prepared_planner=prepare_typing_planner_v1(
                replacement_context, replacement
            ),
            endpoint_reuse_verifier=restart_verifier,
        )


def test_conflicting_canonical_solution_fails_closed() -> None:
    _, _, _, verifier, _, inputs, common = _run(("H", "H"), "hh")
    key = next(iter(verifier._entries))
    entry = verifier._entries[key]
    changed = dict(entry.solution_joint_state)
    first_joint = next(iter(changed))
    changed[first_joint] += 0.01
    solution_sha = module._sha(changed)
    core = {
        "endpoint_sha256": entry.endpoint_sha256,
        "solution_joint_state": changed,
        "solution_joint_state_sha256": solution_sha,
    }
    verifier._entries[key] = replace(
        entry,
        solution_joint_state=changed,
        solution_joint_state_sha256=solution_sha,
        entry_sha256=module._sha(core),
    )
    with pytest.raises(
        TypingEndpointReuseVerifierV1Error, match="canonical solution"
    ):
        run_typing_shadow_pipeline_v1(**inputs, **common)
    assert verifier.snapshot()["canonical_conflicts"] == 1


def test_unmanaged_verifier_is_rejected_before_any_observation() -> None:
    lifecycle, context, _ = _resources("unmanaged-verifier")
    verifier = TypingEndpointReuseVerifierV1.create(context, lifecycle)
    with pytest.raises(TypingTrajectoryIkScreenV1Error, match="lifecycle"):
        run_typing_shadow_pipeline_v1(
            **shadow_fixture._inputs(context=context),
            endpoint_reuse_verifier=verifier,
        )
    assert verifier.snapshot()["observed_sample_count"] == 0


@pytest.mark.parametrize("mutation,match", (
    ("hash", "hash differs"),
    ("count", "derivation"),
    ("entry", "entry differs"),
    ("authority", "zero authority"),
))
def test_snapshot_mutations_fail_closed(stable_run, mutation: str, match: str):
    report = copy.deepcopy(stable_run[3].snapshot())
    if mutation == "hash":
        report["verifier_snapshot_sha256"] = "f" * 64
    elif mutation == "count":
        report["hits"] += 1
        _rehash(report)
    elif mutation == "entry":
        report["entries"][0]["observation_count"] = 0
        _rehash(report)
    else:
        report["warm_start_authorized"] = True
        _rehash(report)
    with pytest.raises(TypingEndpointReuseVerifierV1Error, match=match):
        parse_typing_endpoint_reuse_verifier_snapshot_v1(report)
