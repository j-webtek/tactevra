from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

import rocell.application.fixed_camera_keyboard_profiled_entry_route_qualification_v1 as subject
from rocell.application.fixed_camera_keyboard_profiled_partition_collision_evaluator_v1 import (
    STATUS_INCOMPLETE,
)

from test_fixed_camera_keyboard_profiled_route_clearance_reconstruction_v1 import (
    _inputs,
    _reseal_document,
    _reseal_evaluation,
    _sha,
)
from test_typing_observed_route_entry_coverage_v1 import _coverage
from test_typing_observed_route_entry_dynamics_v1 import _qualified
from test_typing_observed_route_entry_sweep_v1 import _reseal as _reseal_sweep


SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "ai/schemas/fixed_camera_keyboard_profiled_entry_route_qualification_v1.schema.json"
)


def _bundle(*, inactive_incomplete: bool = False):
    documents, evaluation = _inputs()
    context, entry, sweep, _profile, _dynamics = _qualified()
    _coverage_context, coverage_entry, _tracking, _policy, _samples, coverage = (
        _coverage()
    )
    assert (
        coverage_entry["observed_route_entry_sha256"]
        == entry["observed_route_entry_sha256"]
    )
    assert (
        coverage["observed_route_entry_tracking"]["observed_route_entry_dynamics"][
            "observed_route_entry_sweep_sha256"
        ]
        == sweep["observed_route_entry_sweep_sha256"]
    )

    profile = "no_attachment"
    document = documents[profile]
    partition = document["partitions"][0]
    first = partition["bounded_joint_sample_plan"][0]
    first["joint_positions_rad"] = copy.deepcopy(entry["entry_joint_positions_rad"])
    partition_core = dict(partition)
    partition_core.pop("partition_intake_sha256")
    partition["partition_intake_sha256"] = _sha(partition_core)
    document["installed_collision_profile_sha256"] = sweep[
        "installed_collision_profile_sha256"
    ]
    _reseal_document(document)

    report = evaluation["profiles"][profile]
    report["installed_collision_profile_sha256"] = document[
        "installed_collision_profile_sha256"
    ]
    report["source_partitioned_typing_collision_intake_sha256"] = document[
        "partitioned_typing_collision_intake_sha256"
    ]
    report["partitions"][0]["partition_intake_sha256"] = partition[
        "partition_intake_sha256"
    ]
    report["partitions"][0]["conservative_sweep_qualification"]["segment_reports"][0][
        "start_sample_sha256"
    ] = _sha(first)
    evaluation["calibration_snapshot_sha256"] = entry["calibration_snapshot_sha256"]
    evaluation["build_snapshot_sha256"] = context.snapshot.snapshot_hash

    if inactive_incomplete:
        inactive = evaluation["profiles"]["stylus_attachment"]
        inactive["status"] = STATUS_INCOMPLETE
        for partition_report in inactive["partitions"]:
            partition_report["conservative_sweep_qualification"] = None
        evaluation["status"] = STATUS_INCOMPLETE
    _reseal_evaluation(evaluation)
    return documents, evaluation, entry, sweep, coverage


def test_missing_fresh_entry_remains_blocked_and_zero_authority() -> None:
    documents, evaluation = _inputs()
    result = subject.qualify_fixed_camera_keyboard_profiled_entry_route_v1(
        documents, evaluation, "no_attachment"
    )
    assert result["status"] == subject.STATUS_BLOCKED
    assert result["disposition"] == "BLOCKED"
    assert result["blockers"] == [
        "FRESH_OBSERVED_START_AND_ENTRY_QUALIFICATION_REQUIRED"
    ]
    assert result["authority"] == subject.ZERO_AUTHORITY
    jsonschema.Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    ).validate(result)


def test_qualifies_exact_entry_and_selected_profile_route() -> None:
    documents, evaluation, entry, sweep, coverage = _bundle()
    result = subject.qualify_fixed_camera_keyboard_profiled_entry_route_v1(
        documents,
        evaluation,
        "no_attachment",
        entry,
        sweep,
        coverage,
    )
    assert result["status"] == subject.STATUS_PASS
    assert result["disposition"] == "PASS"
    assert result["route_segment_count"] == 328
    assert result["entry_route_joint_continuity_proven"] is True
    assert result["retained_entry_telemetry_coverage_qualified"] is True
    assert result["minimum_clearance_lower_bound_mm"] == min(
        result["route_minimum_clearance_lower_bound_mm"],
        result["entry_minimum_clearance_lower_bound_mm"],
    )
    assert result["blockers"] == []
    assert result["authority"] == subject.ZERO_AUTHORITY
    jsonschema.Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    ).validate(result)


def test_inactive_incomplete_profile_does_not_cross_selected_profile() -> None:
    documents, evaluation, entry, sweep, coverage = _bundle(inactive_incomplete=True)
    result = subject.qualify_fixed_camera_keyboard_profiled_entry_route_v1(
        documents,
        evaluation,
        "no_attachment",
        entry,
        sweep,
        coverage,
    )
    assert result["status"] == subject.STATUS_PASS
    assert result["profile_separation_preserved"] is True


def test_rejects_resealed_route_start_that_differs_from_observed_entry() -> None:
    documents, evaluation, entry, sweep, coverage = _bundle()
    changed = documents["no_attachment"]
    partition = changed["partitions"][0]
    first = partition["bounded_joint_sample_plan"][0]
    first["joint_positions_rad"][next(iter(first["joint_positions_rad"]))] += 0.01
    partition_core = dict(partition)
    partition_core.pop("partition_intake_sha256")
    partition["partition_intake_sha256"] = _sha(partition_core)
    _reseal_document(changed)
    report = evaluation["profiles"]["no_attachment"]
    report["source_partitioned_typing_collision_intake_sha256"] = changed[
        "partitioned_typing_collision_intake_sha256"
    ]
    report["partitions"][0]["partition_intake_sha256"] = partition[
        "partition_intake_sha256"
    ]
    report["partitions"][0]["conservative_sweep_qualification"]["segment_reports"][0][
        "start_sample_sha256"
    ] = _sha(first)
    _reseal_evaluation(evaluation)

    result = subject.qualify_fixed_camera_keyboard_profiled_entry_route_v1(
        documents,
        evaluation,
        "no_attachment",
        entry,
        sweep,
        coverage,
    )
    assert result["status"] == subject.STATUS_BLOCKED
    assert "OBSERVED_ENTRY_ROUTE_START_JOINT_MISMATCH" in result["blockers"]


def test_rejects_crossed_selected_collision_profile() -> None:
    documents, evaluation, entry, sweep, coverage = _bundle()
    crossed = copy.deepcopy(sweep)
    crossed["installed_collision_profile_sha256"] = "f" * 64
    _reseal_sweep(crossed)
    with pytest.raises(
        subject.FixedCameraKeyboardProfiledEntryRouteQualificationV1Error,
        match="lineage differs",
    ):
        subject.qualify_fixed_camera_keyboard_profiled_entry_route_v1(
            documents,
            evaluation,
            "no_attachment",
            entry,
            crossed,
            coverage,
        )
