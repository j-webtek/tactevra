import copy
import hashlib
import json
import math

import pytest

from rocell.arm.position_vector_calibration import (
    convert_position_vector_feedback,
    load_position_vector_calibration,
)
from rocell.calibration.position_vector_campaign import (
    DATASET_SCHEMA,
    FIT_REPORT_SCHEMA,
    REVIEW_SCHEMA,
    CampaignPolicy,
    PositionVectorCampaignError,
    build_calibration_artifact,
    canonical_sha256,
    fit_campaign_dataset,
    load_campaign_dataset,
    main,
)


CONTROLLER = {
    "vid": "10c4",
    "pid": "ea60",
    "unit_serial": "52E4E1E8337FEF119E92181CEDD322A4",
    "firmware_sha256": "a" * 64,
}
JOINTS = ("base", "shoulder", "elbow", "wrist_pitch", "wrist_roll", "gripper")
INDEXES = (0, 1, 3, 4, 5, 6)
SCALES = (-0.0010, 0.0011, 0.0009, 0.0012, -0.0011, 0.0007)
ZEROS = (1800, 1900, 1700, 1750, 1850, 1600)


def dataset(attachment="no_attachment"):
    samples = []
    for ordinal in range(8):
        counts = [0] * 7
        primary = [1000 + 200 * ordinal + 11 * index for index in range(6)]
        for index, count in zip(INDEXES, primary, strict=True):
            counts[index] = count
        counts[2] = 4095 - counts[1]
        angles = {
            joint: (count - zero) * scale
            for joint, count, zero, scale in zip(
                JOINTS, primary, ZEROS, SCALES, strict=True
            )
        }
        samples.append(
            {
                "sample_id": f"sample-{ordinal:02d}",
                "split": "TRAINING" if ordinal < 5 else "HELD_OUT",
                "source_pose": f"CAL_POSE_{ordinal:02d}",
                "raw_position_counts": counts,
                "canonical_joints_rad": angles,
                "truth_method": "link_fiducial_pose",
                "truth_evidence_sha256": hashlib.sha256(
                    f"truth-{ordinal}".encode()
                ).hexdigest(),
                "stationary": True,
                "motion_active": False,
                "trajectory_progress_permille": 1000,
            }
        )
    return {
        "schema": DATASET_SCHEMA,
        "dataset_id": "installed-arm-count-campaign-01",
        "producer_id": "calibration-producer-01",
        "controller_binding": dict(CONTROLLER),
        "attachment_profile": attachment,
        "position_order_servo_ids": list(range(11, 18)),
        "joint_order": list(JOINTS),
        "samples": samples,
    }


def review(source, fit, **updates):
    value = {
        "schema": REVIEW_SCHEMA,
        "dataset_sha256": canonical_sha256(load_campaign_dataset(source)),
        "fit_report_sha256": canonical_sha256(fit),
        "producer_id": "calibration-producer-01",
        "reviewer_id": "calibration-reviewer-02",
        "decision": "ACCEPT",
        "reviewed_at": "2026-10-21T20:00:00Z",
        "review_notes_sha256": "f" * 64,
    }
    value.update(updates)
    return value


def test_campaign_builds_existing_strict_artifact_and_converts_feedback():
    source = dataset()
    fit = fit_campaign_dataset(source, calibration_id="installed-count-fit-01")
    artifact = build_calibration_artifact(source, fit, review(source, fit))

    assert fit["schema"] == FIT_REPORT_SCHEMA
    assert fit["attachment_profile"] == "no_attachment"
    assert fit["status"] == "PASS"
    assert not fit["motion_authorized"] and not fit["physical_authority"]
    assert load_position_vector_calibration(artifact).calibration_id == "installed-count-fit-01"
    assert len(set(artifact["evidence"].values())) == 3

    held_out = source["samples"][6]
    message = {
        "T": 1051,
        "p": held_out["raw_position_counts"],
        "pose": held_out["source_pose"],
        "motion_active": False,
        "trajectory_progress_permille": 1000,
    }
    converted = convert_position_vector_feedback(message, artifact, CONTROLLER)
    for joint in JOINTS:
        assert converted["canonical_joints_rad"][joint] == pytest.approx(
            held_out["canonical_joints_rad"][joint]
        )


def test_fit_is_deterministic_and_preserves_disjoint_counts():
    first = fit_campaign_dataset(dataset(), calibration_id="fit-01")
    second = fit_campaign_dataset(copy.deepcopy(dataset()), calibration_id="fit-01")
    assert first == second
    assert all(row["training_sample_count"] == 5 for row in first["joints"])
    assert all(row["held_out_sample_count"] == 3 for row in first["joints"])
    assert all(row["held_out_max_abs_error_rad"] < 1e-12 for row in first["joints"])
    assert first["shoulder_pair"]["training_max_abs_residual_counts"] == 0
    assert first["shoulder_pair"]["held_out_max_abs_residual_counts"] == 0


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda value: value.update(attachment_profile="unknown"), "attachment profile"),
        (lambda value: value["samples"][0].update(stationary=False), "stationary"),
        (lambda value: value["samples"][0].update(motion_active=True), "stationary"),
        (lambda value: value["samples"][0].update(split="VALIDATION"), "split"),
        (
            lambda value: value["samples"][1].update(
                truth_evidence_sha256=value["samples"][0]["truth_evidence_sha256"]
            ),
            "truth evidence hashes",
        ),
        (lambda value: value.update(position_order_servo_ids=list(range(10, 17))), "servo order"),
    ],
)
def test_dataset_rejects_ambiguous_or_crossed_observations(mutate, match):
    value = dataset()
    mutate(value)
    with pytest.raises(PositionVectorCampaignError, match=match):
        load_campaign_dataset(value)


def test_policy_rejects_inadequate_coverage_and_held_out_error():
    source = dataset()
    narrow = copy.deepcopy(source)
    for sample in narrow["samples"][:5]:
        sample["raw_position_counts"][0] = 1000
    with pytest.raises(PositionVectorCampaignError, match="base training count span"):
        fit_campaign_dataset(narrow, calibration_id="fit-01")

    noisy = copy.deepcopy(source)
    noisy["samples"][-1]["canonical_joints_rad"]["elbow"] += 0.1
    with pytest.raises(PositionVectorCampaignError, match="elbow held-out error"):
        fit_campaign_dataset(noisy, calibration_id="fit-01")

    with pytest.raises(PositionVectorCampaignError, match="insufficient training"):
        fit_campaign_dataset(
            source,
            calibration_id="fit-01",
            policy=CampaignPolicy(minimum_training_samples=6),
        )


def test_fit_tampering_and_attachment_crossing_fail_reproduction():
    source = dataset()
    fit = fit_campaign_dataset(source, calibration_id="fit-01")
    tampered = copy.deepcopy(fit)
    tampered["joints"][0]["radians_per_count"] *= 1.01
    with pytest.raises(PositionVectorCampaignError, match="does not reproduce"):
        build_calibration_artifact(source, tampered, review(source, tampered))

    crossed = dataset("stylus_attachment")
    with pytest.raises(PositionVectorCampaignError, match="does not reproduce"):
        build_calibration_artifact(crossed, fit, review(crossed, fit))


@pytest.mark.parametrize(
    "updates,match",
    [
        ({"reviewer_id": "calibration-producer-01"}, "independent"),
        ({"decision": "REJECT"}, "not ACCEPT"),
        ({"dataset_sha256": "0" * 64}, "dataset hash"),
        ({"fit_report_sha256": "1" * 64}, "fit report hash"),
        ({"reviewed_at": "2026-10-21"}, "UTC offset"),
        ({"review_notes_sha256": "not-a-digest"}, "review_notes_sha256"),
    ],
)
def test_review_must_accept_exact_inputs_independently(updates, match):
    source = dataset()
    fit = fit_campaign_dataset(source, calibration_id="fit-01")
    with pytest.raises(PositionVectorCampaignError, match=match):
        build_calibration_artifact(source, fit, review(source, fit, **updates))


def test_default_policy_is_stricter_than_artifact_minimums():
    policy = CampaignPolicy()
    assert policy.minimum_training_samples == 5
    assert policy.minimum_held_out_samples == 3
    assert policy.minimum_training_count_span == 128
    assert policy.accepted_max_abs_error_rad < math.radians(3)


def test_file_workflow_creates_new_fit_and_artifact_without_overwrite(tmp_path):
    source = dataset()
    dataset_path = tmp_path / "dataset.json"
    fit_path = tmp_path / "fit.json"
    review_path = tmp_path / "review.json"
    artifact_path = tmp_path / "calibration.json"
    dataset_path.write_text(json.dumps(source), encoding="utf-8")

    assert main([
        "fit", "--dataset", str(dataset_path), "--calibration-id", "fit-01",
        "--output", str(fit_path),
    ]) == 0
    fit = json.loads(fit_path.read_bytes())
    review_path.write_text(json.dumps(review(source, fit)), encoding="utf-8")
    assert main([
        "build", "--dataset", str(dataset_path), "--fit-report", str(fit_path),
        "--review", str(review_path), "--output", str(artifact_path),
    ]) == 0
    assert load_position_vector_calibration(
        json.loads(artifact_path.read_bytes())
    ).calibration_id == "fit-01"
    with pytest.raises(PositionVectorCampaignError, match="refusing to replace"):
        main([
            "fit", "--dataset", str(dataset_path), "--calibration-id", "fit-01",
            "--output", str(fit_path),
        ])
