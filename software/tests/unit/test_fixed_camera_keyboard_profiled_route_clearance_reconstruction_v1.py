from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

import rocell.application.fixed_camera_keyboard_profiled_route_clearance_reconstruction_v1 as subject
from rocell.application.fixed_camera_keyboard_profiled_partition_collision_evaluator_v1 import (
    SCHEMA as EVALUATION_SCHEMA,
    STATUS_CLEAR as EVALUATION_CLEAR,
    STATUS_COLLISION as EVALUATION_COLLISION,
    STATUS_INCOMPLETE as EVALUATION_INCOMPLETE,
)
from rocell.application.partitioned_typing_collision_intake_v1 import (
    READY_STATUS,
    SCHEMA as PARTITION_SCHEMA,
)


PROFILES = ("no_attachment", "stylus_attachment")
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "ai/schemas/fixed_camera_keyboard_profiled_route_clearance_reconstruction_v1.schema.json"
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _sealed(core: dict, field: str) -> dict:
    return {**core, field: _sha(core)}


def _inputs(status: str = EVALUATION_CLEAR):
    documents = {}
    profile_reports = {}
    for profile_index, profile_name in enumerate(PROFILES):
        partition_documents = []
        partition_reports = []
        start = 0
        for partition_index, count in enumerate((255, 73)):
            plan = [
                {
                    "sample_sequence": local,
                    "source_segment_index": start + max(0, local - 1),
                    "owner": profile_name,
                    "joint_positions_rad": {
                        "joint": float(
                            start - 1
                            if partition_index > 0 and local == 0
                            else start + max(0, local - 1)
                        )
                    },
                }
                for local in range(count + 1)
            ]
            partition_core = {
                "partition_index": partition_index,
                "source_result_start_index": start,
                "source_result_end_index_exclusive": start + count,
                "source_result_count": count,
                "bounded_joint_sample_plan": plan,
            }
            partition = _sealed(partition_core, "partition_intake_sha256")
            partition_documents.append(partition)
            segment_reports = []
            for local, (first, second) in enumerate(
                zip(plan[:-1], plan[1:], strict=True)
            ):
                source = start + local
                clearance = (
                    1.25
                    if profile_name == "stylus_attachment" and source == 300
                    else 4.0 + profile_index
                )
                segment_reports.append(
                    {
                        "segment_sequence": local,
                        "start_sample_sha256": _sha(first),
                        "end_sample_sha256": _sha(second),
                        "clearance_lower_bound_status": "CLEAR",
                        "minimum_clearance_lower_bound_mm": clearance,
                        "clearance_limiting_body_pair": ["arm", "keyboard"],
                    }
                )
            minimum = min(
                item["minimum_clearance_lower_bound_mm"] for item in segment_reports
            )
            limiting = next(
                item
                for item in segment_reports
                if item["minimum_clearance_lower_bound_mm"] == minimum
            )
            sweep = {
                "status": "CONSERVATIVE_SEGMENT_SWEEPS_CLEAR_RELEASE_GATES_REMAIN",
                "segment_count": count,
                "segment_reports": segment_reports,
                "minimum_clearance_lower_bound_mm": minimum,
                "limiting_segment_sequence": limiting["segment_sequence"],
                "limiting_body_pair": limiting["clearance_limiting_body_pair"],
                "all_segment_clearance_bounds_determinate": True,
                "all_conservative_segment_sweeps_clear": True,
            }
            partition_reports.append(
                {
                    "partition_index": partition_index,
                    "partition_intake_sha256": partition["partition_intake_sha256"],
                    "sample_count": count + 1,
                    "segment_count": count,
                    "conservative_sweep_qualification": (
                        sweep if status == EVALUATION_CLEAR else None
                    ),
                }
            )
            start += count
        boundary_core = {
            "predecessor_partition_index": 0,
            "successor_partition_index": 1,
            "source_boundary_result_index": 254,
            "predecessor_terminal_sample_sha256": _sha(
                partition_documents[0]["bounded_joint_sample_plan"][-1]
            ),
            "successor_boundary_recheck_sample_sha256": _sha(
                partition_documents[1]["bounded_joint_sample_plan"][0]
            ),
            "maximum_joint_difference_rad": 0.0,
            "boundary_recheck_required": True,
            "extra_zero_length_sweep_envelope_required": False,
            "first_successor_route_segment_owned_by_partition": 1,
        }
        document_core = {
            "schema": PARTITION_SCHEMA,
            "status": READY_STATUS,
            "installed_collision_profile_sha256": str(profile_index + 1) * 64,
            "partitions": partition_documents,
            "boundary_lineage": [
                {**boundary_core, "boundary_lineage_sha256": _sha(boundary_core)}
            ],
            "required_evidence_slots": {"route_segment_count": 328},
        }
        document = _sealed(document_core, "partitioned_typing_collision_intake_sha256")
        documents[profile_name] = document
        profile_reports[profile_name] = {
            "profile": profile_name,
            "status": status,
            "installed_collision_profile_sha256": document[
                "installed_collision_profile_sha256"
            ],
            "source_partitioned_typing_collision_intake_sha256": document[
                "partitioned_typing_collision_intake_sha256"
            ],
            "partition_count": 2,
            "partitions": partition_reports,
        }
    evaluation_core = {
        "schema": EVALUATION_SCHEMA,
        "status": status,
        "calibration_snapshot_sha256": "a" * 64,
        "build_snapshot_sha256": "b" * 64,
        "kinematic_model_sha256": "c" * 64,
        "profiles": profile_reports,
    }
    return documents, _sealed(
        evaluation_core, "profiled_partition_collision_evaluation_sha256"
    )


def _reseal_evaluation(evaluation: dict) -> None:
    core = dict(evaluation)
    core.pop("profiled_partition_collision_evaluation_sha256")
    evaluation["profiled_partition_collision_evaluation_sha256"] = _sha(core)


def _reseal_document(document: dict) -> None:
    core = dict(document)
    core.pop("partitioned_typing_collision_intake_sha256")
    document["partitioned_typing_collision_intake_sha256"] = _sha(core)


def test_reconstructs_two_profile_328_segment_route_and_global_minimum() -> None:
    documents, evaluation = _inputs()
    result = subject.reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1(
        documents, evaluation
    )

    assert result["status"] == subject.STATUS_READY
    assert result["disposition"] == "BLOCKED"
    assert result["minimum_clearance_lower_bound_mm_across_profiles"] == 1.25
    assert result["limiting_profile_route_segment"] == {
        "profile": "stylus_attachment",
        "partition_index": 1,
        "partition_segment_sequence": 45,
        "source_segment_index": 300,
        "body_pair": ["arm", "keyboard"],
    }
    assert all(
        item["route_segment_count"] == 328
        and item["all_route_segments_continuously_clear"]
        for item in result["profiles"].values()
    )
    assert result["authority"] == subject.ZERO_AUTHORITY
    jsonschema.Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    ).validate(result)


@pytest.mark.parametrize(
    ("evaluation_status", "expected_status", "disposition"),
    (
        (EVALUATION_COLLISION, subject.STATUS_REJECTED, "REJECT"),
        (EVALUATION_INCOMPLETE, subject.STATUS_BLOCKED, "BLOCKED"),
    ),
)
def test_preserves_collision_and_incomplete_dispositions(
    evaluation_status, expected_status, disposition
) -> None:
    documents, evaluation = _inputs(evaluation_status)
    result = subject.reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1(
        documents, evaluation
    )
    assert result["status"] == expected_status
    assert result["disposition"] == disposition
    assert result["minimum_clearance_lower_bound_mm_across_profiles"] is None


def test_rejects_gap_even_when_document_and_evaluation_are_rehashed() -> None:
    documents, evaluation = _inputs()
    document = documents["stylus_attachment"]
    document["partitions"][1]["source_result_start_index"] = 256
    partition = document["partitions"][1]
    core = dict(partition)
    core.pop("partition_intake_sha256")
    partition["partition_intake_sha256"] = _sha(core)
    _reseal_document(document)
    report = evaluation["profiles"]["stylus_attachment"]
    report["source_partitioned_typing_collision_intake_sha256"] = document[
        "partitioned_typing_collision_intake_sha256"
    ]
    report["partitions"][1]["partition_intake_sha256"] = partition[
        "partition_intake_sha256"
    ]
    _reseal_evaluation(evaluation)

    with pytest.raises(
        subject.FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error
    ):
        subject.reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1(
            documents, evaluation
        )


def test_rejects_changed_partition_minimum_after_whole_report_rehash() -> None:
    documents, evaluation = _inputs()
    changed = copy.deepcopy(evaluation)
    changed["profiles"]["no_attachment"]["partitions"][0][
        "conservative_sweep_qualification"
    ]["minimum_clearance_lower_bound_mm"] = 99.0
    _reseal_evaluation(changed)
    with pytest.raises(
        subject.FixedCameraKeyboardProfiledRouteClearanceReconstructionV1Error,
        match="aggregate differs",
    ):
        subject.reconstruct_fixed_camera_keyboard_profiled_route_clearance_v1(
            documents, changed
        )
