import copy
import hashlib
import json
import math
from pathlib import Path

import pytest

from rocell.arm.position_vector_calibration import (
    convert_position_vector_feedback,
    load_position_vector_calibration,
)
from rocell.calibration.position_vector_campaign import (
    CANDIDATE_AUGMENTATION_SCHEMA,
    CANDIDATE_COVERAGE_SCHEMA,
    CANDIDATE_INVENTORY_ADMISSION_RECEIPT_SCHEMA,
    CANDIDATE_INVENTORY_SCHEMA,
    CANDIDATE_PREFLIGHT_SCHEMA,
    CANDIDATE_PROPOSAL_SCHEMA,
    CANDIDATE_QUALIFICATION_PLAN_SCHEMA,
    CANDIDATE_QUALIFICATION_ASSESSMENT_SCHEMA,
    CANDIDATE_QUALIFICATION_EVIDENCE_SCHEMA,
    CANDIDATE_QUALIFICATION_HANDOFF_SCHEMA,
    CANDIDATE_TRAINING_SPLIT_PLAN_SCHEMA,
    DATASET_SCHEMA,
    FIT_REPORT_SCHEMA,
    OBSERVATIONS_SCHEMA,
    PLAN_SCHEMA,
    PREPARATION_RECEIPT_SCHEMA,
    QUALIFIED_COLLECTION_PREPARATION_RECEIPT_SCHEMA,
    QUALIFIED_COLLECTION_READINESS_ASSESSMENT_SCHEMA,
    QUALIFIED_COLLECTION_READINESS_EVIDENCE_SCHEMA,
    QUALIFIED_COLLECTION_READINESS_HANDOFF_SCHEMA,
    QUALIFIED_COLLECTION_READINESS_PLAN_SCHEMA,
    QUALIFIED_DETERMINISTIC_FIT_ASSESSMENT_SCHEMA,
    QUALIFIED_INDEPENDENT_FIT_REVIEW_RECEIPT_SCHEMA,
    QUALIFIED_INDEPENDENT_FIT_REVIEW_SCHEMA,
    QUALIFIED_OBSERVATION_SET_COMPILATION_RECEIPT_SCHEMA,
    QUALIFIED_STATIONARY_OBSERVATION_EVIDENCE_SCHEMA,
    QUALIFIED_STATIONARY_OBSERVATION_INGESTION_RECEIPT_SCHEMA,
    READINESS_EVIDENCE_RECEIPT_SCHEMA,
    READINESS_EVIDENCE_SCHEMA,
    READINESS_SCHEMA,
    REVIEWED_COMPILATION_RECEIPT_SCHEMA,
    REVIEWED_PREPARATION_RECEIPT_SCHEMA,
    REVIEW_SCHEMA,
    CampaignPolicy,
    PositionVectorCampaignError,
    accept_qualified_independent_fit_review,
    audit_candidate_count_coverage,
    assess_candidate_qualification_evidence,
    assess_collection_readiness,
    assess_qualified_collection_readiness_evidence,
    assess_qualified_deterministic_fit,
    assess_reviewed_readiness_evidence,
    build_calibration_artifact,
    canonical_sha256,
    collection_observations_template,
    compile_planned_dataset,
    compile_qualified_observation_set,
    create_assessed_collection_package,
    create_candidate_qualification_handoff,
    create_candidate_qualification_plan,
    create_collection_plan,
    create_reviewed_collection_package,
    create_reviewed_dataset_package,
    create_qualified_candidate_inventory_package,
    create_qualified_candidate_collection_package,
    create_qualified_collection_readiness_plan,
    create_qualified_collection_readiness_handoff,
    evaluate_candidate_count_augmentation,
    fit_campaign_dataset,
    ingest_qualified_stationary_observation,
    load_campaign_dataset,
    load_collection_readiness,
    load_collection_plan,
    main,
    plan_candidate_count_augmentation,
    plan_qualified_candidate_training_split,
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


def plan():
    return create_collection_plan(
        dataset_id="installed-arm-count-campaign-01",
        producer_id="calibration-producer-01",
        controller_binding=CONTROLLER,
        attachment_profile="no_attachment",
        training_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5)],
        held_out_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5, 8)],
        truth_method="link_fiducial_pose",
    )


def observations(source_plan=None):
    source_plan = source_plan or plan()
    source = dataset(source_plan["attachment_profile"])
    return {
        "schema": OBSERVATIONS_SCHEMA,
        "plan_sha256": canonical_sha256(source_plan),
        "samples": [
            {
                **{
                    key: value
                    for key, value in sample.items()
                    if key not in {"sample_id", "split", "source_pose", "truth_method"}
                },
                "sample_id": source_plan["slots"][index]["sample_id"],
            }
            for index, sample in enumerate(source["samples"])
        ],
    }


def test_readiness_reports_retained_firmware_and_pose_blockers_without_authority():
    result = assess_collection_readiness(
        controller_identity={key: CONTROLLER[key] for key in ("vid", "pid", "unit_serial")},
        installed_firmware_sha256=None,
        attachment_profile="no_attachment",
        truth_method="link_fiducial_pose",
        retained_pose_labels=[
            "A_CLEAR", "A_HOVER", "A_DOWN", "B_CLEAR", "B_HOVER", "B_DOWN"
        ],
    )

    assert result["schema"] == READINESS_SCHEMA
    assert result["status"] == "BLOCKED"
    assert result["blockers"] == [
        "INSTALLED_FIRMWARE_SHA256_UNVERIFIED",
        "UNIQUE_SOURCE_POSE_COUNT_6_BELOW_8",
    ]
    assert result["installed_firmware_sha256"] is None
    assert not result["ready_to_prepare"]
    assert result["authority"] == {
        "controller_opened": False,
        "camera_opened": False,
        "commands_sent": 0,
        "motion_authorized": False,
        "physical_authority": False,
    }


def test_readiness_passes_only_with_exact_firmware_and_enough_unique_poses():
    result = assess_collection_readiness(
        controller_identity={key: CONTROLLER[key] for key in ("vid", "pid", "unit_serial")},
        installed_firmware_sha256=CONTROLLER["firmware_sha256"],
        attachment_profile="stylus_attachment",
        truth_method="mechanical_angle_fixture",
        retained_pose_labels=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(8)],
    )

    assert result["status"] == "READY_TO_PREPARE"
    assert result["blockers"] == []
    assert result["ready_to_prepare"]


def test_readiness_deduplicates_pose_inventory_and_reports_duplicates():
    result = assess_collection_readiness(
        controller_identity={key: CONTROLLER[key] for key in ("vid", "pid", "unit_serial")},
        installed_firmware_sha256=CONTROLLER["firmware_sha256"],
        attachment_profile="no_attachment",
        truth_method="link_fiducial_pose",
        retained_pose_labels=["A", "A", "B"],
    )

    assert result["retained_pose_labels"] == ["A", "B"]
    assert result["blockers"] == [
        "UNIQUE_SOURCE_POSE_COUNT_2_BELOW_8",
        "SOURCE_POSE_LABELS_NOT_UNIQUE",
    ]


def ready_assessment():
    return assess_collection_readiness(
        controller_identity={key: CONTROLLER[key] for key in ("vid", "pid", "unit_serial")},
        installed_firmware_sha256=CONTROLLER["firmware_sha256"],
        attachment_profile="no_attachment",
        truth_method="link_fiducial_pose",
        retained_pose_labels=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(8)],
    )


def reviewed_evidence():
    return {
        "schema": READINESS_EVIDENCE_SCHEMA,
        "campaign_id": "installed-arm-count-campaign-01",
        "producer_id": "calibration-producer-01",
        "controller_identity": {
            key: CONTROLLER[key] for key in ("vid", "pid", "unit_serial")
        },
        "installed_firmware_sha256": CONTROLLER["firmware_sha256"],
        "firmware_evidence_sha256": "b" * 64,
        "firmware_verifier_id": "firmware-reviewer-02",
        "attachment_profile": "no_attachment",
        "truth_method": "link_fiducial_pose",
        "poses": [
            {
                "label": f"CAL_POSE_{ordinal:02d}",
                "truth_procedure_sha256": hashlib.sha256(
                    f"procedure-{ordinal}".encode()
                ).hexdigest(),
                "reviewer_id": "pose-reviewer-03",
            }
            for ordinal in range(8)
        ],
    }


def candidate_inventory():
    counts = [
        [2047, 2136, 1960, 2549, 2224, 2040, 2047],
        [2105, 2180, 1916, 2473, 2257, 2040, 2047],
        [2174, 2250, 1846, 2340, 2320, 2040, 2047],
        [2174, 2271, 1825, 2362, 2277, 2040, 2047],
        [2174, 2293, 1803, 2383, 2234, 2040, 2047],
        [2174, 2305, 1791, 2393, 2213, 2040, 2047],
        [2174, 2312, 1784, 2399, 2200, 2040, 2047],
        [2174, 2337, 1759, 2416, 2158, 2040, 2047],
    ]
    return {
        "schema": CANDIDATE_INVENTORY_SCHEMA,
        "inventory_id": "bare-jaw-keyboard-chain-20261024",
        "controller_binding": dict(CONTROLLER),
        "attachment_profile": "no_attachment",
        "count_kind": "PLANNED_GOAL",
        "poses": [
            {
                "label": f"POSE_{index}",
                "raw_position_counts": row,
                "source_ref": f"source:{index}",
            }
            for index, row in enumerate(counts)
        ],
    }


def candidate_proposal(inventory=None, counts=None, attachment="no_attachment"):
    inventory = inventory or candidate_inventory()
    return {
        "schema": CANDIDATE_PROPOSAL_SCHEMA,
        "inventory_sha256": canonical_sha256(inventory),
        "label": "POSE_8",
        "attachment_profile": attachment,
        "raw_position_counts": counts
        or [2175, 2200, 1895, 2400, 2250, 2168, 2175],
        "source_ref": "offline:reviewed-proposal-8",
    }


def candidate_qualification_chain():
    inventory = candidate_inventory()
    proposal = candidate_proposal(inventory)
    preflight = evaluate_candidate_count_augmentation(inventory, proposal)
    qualification_plan = create_candidate_qualification_plan(
        inventory, proposal, preflight
    )
    return inventory, proposal, preflight, qualification_plan


def candidate_qualification_evidence(qualification_plan, requirements=None):
    requirements = requirements or [
        item["requirement"]
        for item in qualification_plan["qualification_requirements"]
    ]
    return {
        "schema": CANDIDATE_QUALIFICATION_EVIDENCE_SCHEMA,
        "qualification_plan_sha256": canonical_sha256(qualification_plan),
        "inventory_sha256": qualification_plan["inventory_sha256"],
        "candidate_sha256": qualification_plan["candidate_sha256"],
        "attachment_profile": qualification_plan["attachment_profile"],
        "producer_id": "qualification-producer-01",
        "evidence": [
            {
                "requirement": requirement,
                "evidence_sha256": hashlib.sha256(requirement.encode()).hexdigest(),
                "reviewer_id": "qualification-reviewer-02",
                "decision": "ACCEPT",
            }
            for requirement in requirements
        ],
    }


def qualified_candidate_inventory_package():
    inventory, proposal, preflight, qualification_plan = (
        candidate_qualification_chain()
    )
    evidence = candidate_qualification_evidence(qualification_plan)
    assessment = assess_candidate_qualification_evidence(
        inventory, proposal, preflight, qualification_plan, evidence
    )
    handoff = create_candidate_qualification_handoff(
        inventory,
        proposal,
        preflight,
        qualification_plan,
        evidence,
        assessment,
    )
    admitted, receipt = create_qualified_candidate_inventory_package(
        inventory,
        proposal,
        preflight,
        qualification_plan,
        evidence,
        assessment,
        handoff,
        "bare-jaw-keyboard-chain-qualified-20261024",
    )
    return admitted, receipt


def qualified_collection_readiness_chain():
    admitted, admission_receipt = qualified_candidate_inventory_package()
    split = plan_qualified_candidate_training_split(admitted, admission_receipt)
    plan, observations, preparation_receipt = (
        create_qualified_candidate_collection_package(
            inventory_document=admitted,
            admission_receipt_document=admission_receipt,
            training_split_document=split,
            dataset_id="bare-jaw-position-vector-campaign-01",
            producer_id="calibration-producer-01",
            truth_method="link_fiducial_pose",
        )
    )
    readiness_plan = create_qualified_collection_readiness_plan(
        inventory_document=admitted,
        admission_receipt_document=admission_receipt,
        training_split_document=split,
        collection_plan_document=plan,
        observations_document=observations,
        preparation_receipt_document=preparation_receipt,
    )
    return (
        admitted,
        admission_receipt,
        split,
        plan,
        observations,
        preparation_receipt,
        readiness_plan,
    )


def qualified_collection_readiness_evidence(readiness_plan, requirements=None):
    requirements = requirements or [
        item["requirement"] for item in readiness_plan["evidence_requirements"]
    ]
    return {
        "schema": QUALIFIED_COLLECTION_READINESS_EVIDENCE_SCHEMA,
        "readiness_plan_sha256": canonical_sha256(readiness_plan),
        "inventory_sha256": readiness_plan["inventory_sha256"],
        "collection_plan_sha256": readiness_plan["collection_plan_sha256"],
        "preparation_receipt_sha256": readiness_plan[
            "preparation_receipt_sha256"
        ],
        "attachment_profile": readiness_plan["attachment_profile"],
        "producer_id": "readiness-producer-01",
        "evidence": [
            {
                "requirement": requirement,
                "evidence_sha256": hashlib.sha256(requirement.encode()).hexdigest(),
                "reviewer_id": "readiness-reviewer-02",
                "decision": "ACCEPT",
            }
            for requirement in requirements
        ],
    }


def qualified_collection_readiness_handoff_chain():
    chain = qualified_collection_readiness_chain()
    evidence = qualified_collection_readiness_evidence(chain[-1])
    assessment = assess_qualified_collection_readiness_evidence(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=chain[4],
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        evidence_document=evidence,
    )
    handoff = create_qualified_collection_readiness_handoff(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=chain[4],
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        evidence_document=evidence,
        assessment_document=assessment,
    )
    return (*chain, evidence, assessment, handoff)


def qualified_stationary_observation_evidence(chain, observations, index=0):
    plan = chain[3]
    handoff = chain[9]
    slot = plan["slots"][index]
    return {
        "schema": QUALIFIED_STATIONARY_OBSERVATION_EVIDENCE_SCHEMA,
        "readiness_handoff_sha256": canonical_sha256(handoff),
        "current_observations_sha256": canonical_sha256(observations),
        "sample_id": slot["sample_id"],
        "source_pose": slot["source_pose"],
        "observation_producer_id": "observation-producer-01",
        "truth_reviewer_id": "joint-truth-reviewer-02",
        "raw_position_counts": [1800 + index] * 7,
        "canonical_joints_rad": {
            joint: 0.01 * (joint_index + index)
            for joint_index, joint in enumerate(JOINTS)
        },
        "controller_feedback_evidence_sha256": hashlib.sha256(
            f"feedback-{index}".encode()
        ).hexdigest(),
        "camera_observation_receipt_sha256": hashlib.sha256(
            f"camera-{index}".encode()
        ).hexdigest(),
        "truth_evidence_sha256": hashlib.sha256(
            f"joint-truth-{index}".encode()
        ).hexdigest(),
        "stationary": True,
        "motion_active": False,
        "trajectory_progress_permille": 1000,
    }


def completed_qualified_observation_set():
    chain = qualified_collection_readiness_handoff_chain()
    observations = chain[4]
    receipts = []
    for index in range(len(chain[3]["slots"])):
        evidence = qualified_stationary_observation_evidence(chain, observations, index)
        observations, receipt = ingest_qualified_stationary_observation(
            inventory_document=chain[0],
            admission_receipt_document=chain[1],
            training_split_document=chain[2],
            collection_plan_document=chain[3],
            observations_document=observations,
            preparation_receipt_document=chain[5],
            readiness_plan_document=chain[6],
            readiness_evidence_document=chain[7],
            readiness_assessment_document=chain[8],
            readiness_handoff_document=chain[9],
            observation_evidence_document=evidence,
        )
        receipts.append(receipt)
    return chain, observations, receipts


def qualified_compilation_package():
    chain, observations, receipts = completed_qualified_observation_set()
    compiled, compilation_receipt = compile_qualified_observation_set(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=observations,
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        readiness_evidence_document=chain[7],
        readiness_assessment_document=chain[8],
        readiness_handoff_document=chain[9],
        ingestion_receipt_documents=receipts,
    )
    return chain, observations, receipts, compiled, compilation_receipt


def qualified_fit_package():
    chain, observations, receipts, compiled, compilation_receipt = (
        qualified_compilation_package()
    )
    policy = CampaignPolicy(minimum_training_count_span=1)
    fit_report, fit_assessment = assess_qualified_deterministic_fit(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=observations,
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        readiness_evidence_document=chain[7],
        readiness_assessment_document=chain[8],
        readiness_handoff_document=chain[9],
        ingestion_receipt_documents=receipts,
        dataset_document=compiled,
        compilation_receipt_document=compilation_receipt,
        calibration_id="qualified-fit-01",
        policy=policy,
    )
    return (
        chain,
        observations,
        receipts,
        compiled,
        compilation_receipt,
        fit_report,
        fit_assessment,
    )


def qualified_fit_review(compiled, compilation_receipt, fit_report, fit_assessment):
    return {
        "schema": QUALIFIED_INDEPENDENT_FIT_REVIEW_SCHEMA,
        "dataset_sha256": canonical_sha256(compiled),
        "compilation_receipt_sha256": canonical_sha256(compilation_receipt),
        "fit_report_sha256": canonical_sha256(fit_report),
        "fit_assessment_sha256": canonical_sha256(fit_assessment),
        "producer_id": fit_report["producer_id"],
        "reviewer_id": "independent-fit-reviewer-03",
        "decision": "ACCEPT",
        "reviewed_at": "2026-10-24T14:00:00-04:00",
        "review_notes_sha256": "e" * 64,
    }


def accept_qualified_fit_review_package(package, review_document):
    (
        chain,
        observations,
        receipts,
        compiled,
        compilation_receipt,
        fit_report,
        fit_assessment,
    ) = package
    return accept_qualified_independent_fit_review(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=observations,
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        readiness_evidence_document=chain[7],
        readiness_assessment_document=chain[8],
        readiness_handoff_document=chain[9],
        ingestion_receipt_documents=receipts,
        dataset_document=compiled,
        compilation_receipt_document=compilation_receipt,
        fit_report_document=fit_report,
        fit_assessment_document=fit_assessment,
        review_document=review_document,
    )


def test_candidate_audit_catches_catalog_that_cannot_meet_training_span():
    report = audit_candidate_count_coverage(candidate_inventory())

    assert report["schema"] == CANDIDATE_COVERAGE_SCHEMA
    assert report["status"] == "CANDIDATE_COVERAGE_BLOCKED"
    assert report["pose_count"] == 8
    assert report["blockers"] == [
        "CANDIDATE_COUNT_SPAN_BASE_127_BELOW_128",
        "CANDIDATE_COUNT_SPAN_WRIST_ROLL_0_BELOW_128",
        "CANDIDATE_COUNT_SPAN_GRIPPER_0_BELOW_128",
    ]
    assert report["authority"]["commands_sent"] == 0
    assert report["authority"]["physical_authority"] is False


def test_candidate_audit_passes_only_when_every_primary_joint_has_span():
    inventory = candidate_inventory()
    inventory["poses"][0]["raw_position_counts"][0] = 1900
    inventory["poses"][0]["raw_position_counts"][5] = 1800
    inventory["poses"][0]["raw_position_counts"][6] = 1800

    report = audit_candidate_count_coverage(inventory)

    assert report["status"] == "CANDIDATE_COVERAGE_PASS"
    assert report["blockers"] == []


def test_candidate_audit_rejects_duplicate_labels():
    inventory = candidate_inventory()
    inventory["poses"][1]["label"] = inventory["poses"][0]["label"]

    with pytest.raises(PositionVectorCampaignError, match="pose labels must be unique"):
        audit_candidate_count_coverage(inventory)


def test_candidate_augmentation_derives_exact_gap_closing_ranges():
    report = plan_candidate_count_augmentation(candidate_inventory())

    assert report["schema"] == CANDIDATE_AUGMENTATION_SCHEMA
    assert report["status"] == "CANDIDATE_AUGMENTATION_REQUIRED"
    assert report["catalog_minimum_additional_pose_lower_bound"] == 1
    assert report["coverage_sha256"] == canonical_sha256(
        audit_candidate_count_coverage(candidate_inventory())
    )
    requirements = {row["joint"]: row for row in report["joint_requirements"]}
    assert requirements["base"]["additional_span_needed_counts"] == 1
    assert requirements["base"]["catalog_span_closing_count_ranges"] == [
        {"minimum_count": 0, "maximum_count": 2046},
        {"minimum_count": 2175, "maximum_count": 4095},
    ]
    assert requirements["wrist_roll"]["catalog_span_closing_count_ranges"] == [
        {"minimum_count": 0, "maximum_count": 1912},
        {"minimum_count": 2168, "maximum_count": 4095},
    ]
    assert requirements["gripper"]["catalog_span_closing_count_ranges"] == [
        {"minimum_count": 0, "maximum_count": 1919},
        {"minimum_count": 2175, "maximum_count": 4095},
    ]
    assert report["authority"]["commands_sent"] == 0
    assert report["authority"]["physical_authority"] is False


def test_candidate_augmentation_is_empty_for_passing_catalog():
    inventory = candidate_inventory()
    inventory["poses"][0]["raw_position_counts"][0] = 1900
    inventory["poses"][0]["raw_position_counts"][5] = 1800
    inventory["poses"][0]["raw_position_counts"][6] = 1800

    report = plan_candidate_count_augmentation(inventory)

    assert report["status"] == "NO_CANDIDATE_AUGMENTATION_REQUIRED"
    assert report["catalog_minimum_additional_pose_lower_bound"] == 0
    assert report["joint_requirements"] == []
    assert report["unresolved_blockers"] == []


def test_candidate_preflight_proves_only_catalog_count_gap_closure():
    inventory = candidate_inventory()
    report = evaluate_candidate_count_augmentation(
        inventory, candidate_proposal(inventory)
    )

    assert report["schema"] == CANDIDATE_PREFLIGHT_SCHEMA
    assert report["status"] == "COUNT_VECTOR_CLOSES_CATALOG_GAPS"
    assert report["closes_all_catalog_count_gaps"] is True
    assert report["remaining_blockers"] == []
    assert all(
        row["matches_catalog_span_closing_range"]
        for row in report["requirement_evaluations"]
    )
    assert report["authority"]["commands_sent"] == 0
    assert report["authority"]["physical_authority"] is False
    assert any("does not establish reachability" in item
               for item in report["limitations"])


def test_candidate_preflight_retains_unclosed_gaps():
    inventory = candidate_inventory()
    report = evaluate_candidate_count_augmentation(
        inventory,
        candidate_proposal(
            inventory, counts=[2174, 2200, 1895, 2400, 2250, 2040, 2047]
        ),
    )

    assert report["status"] == "COUNT_VECTOR_LEAVES_CATALOG_GAPS"
    assert report["closes_all_catalog_count_gaps"] is False
    assert report["remaining_blockers"] == [
        "CANDIDATE_COUNT_SPAN_BASE_127_BELOW_128",
        "CANDIDATE_COUNT_SPAN_WRIST_ROLL_0_BELOW_128",
        "CANDIDATE_COUNT_SPAN_GRIPPER_0_BELOW_128",
    ]
    assert not any(row["matches_catalog_span_closing_range"]
                   for row in report["requirement_evaluations"])


def test_candidate_qualification_plan_binds_passing_preflight_and_lists_gates():
    inventory = candidate_inventory()
    proposal = candidate_proposal(inventory)
    preflight = evaluate_candidate_count_augmentation(inventory, proposal)

    plan = create_candidate_qualification_plan(inventory, proposal, preflight)

    assert plan["schema"] == CANDIDATE_QUALIFICATION_PLAN_SCHEMA
    assert plan["status"] == "QUALIFICATION_EVIDENCE_REQUIRED"
    assert plan["candidate_sha256"] == preflight["candidate_sha256"]
    assert plan["candidate_preflight_sha256"] == canonical_sha256(preflight)
    assert len(plan["qualification_requirements"]) == 8
    assert all(
        item["status"] == "EVIDENCE_REQUIRED"
        and item["accepted_evidence_sha256"] is None
        for item in plan["qualification_requirements"]
    )
    assert "INSTALLED_COLLISION_GEOMETRY_EVIDENCE_REQUIRED" in plan["blockers"]
    assert "ATTACHMENT_TCP_GEOMETRY_EVIDENCE_REQUIRED" in plan["blockers"]
    assert "CONTINUOUS_SWEPT_PATH_SCREENING_EVIDENCE_REQUIRED" in plan["blockers"]
    assert plan["authority"]["commands_sent"] == 0
    assert plan["authority"]["physical_authority"] is False


def test_candidate_qualification_plan_rejects_stale_or_failing_preflight():
    inventory = candidate_inventory()
    proposal = candidate_proposal(inventory)
    preflight = evaluate_candidate_count_augmentation(inventory, proposal)
    stale = copy.deepcopy(preflight)
    stale["candidate"]["source_ref"] = "crossed-evidence"

    with pytest.raises(PositionVectorCampaignError, match="does not reproduce"):
        create_candidate_qualification_plan(inventory, proposal, stale)

    failing = candidate_proposal(
        inventory, counts=[2174, 2200, 1895, 2400, 2250, 2040, 2047]
    )
    failing_preflight = evaluate_candidate_count_augmentation(inventory, failing)
    with pytest.raises(PositionVectorCampaignError, match="does not close"):
        create_candidate_qualification_plan(inventory, failing, failing_preflight)


def test_candidate_qualification_assessment_accepts_complete_reviewed_chain():
    inventory, proposal, preflight, qualification_plan = (
        candidate_qualification_chain()
    )
    evidence = candidate_qualification_evidence(qualification_plan)

    report = assess_candidate_qualification_evidence(
        inventory, proposal, preflight, qualification_plan, evidence
    )

    assert report["schema"] == CANDIDATE_QUALIFICATION_ASSESSMENT_SCHEMA
    assert report["status"] == "EVIDENCE_CHAIN_COMPLETE"
    assert report["blockers"] == []
    assert all(
        item["status"] == "EVIDENCE_ACCEPTED"
        for item in report["requirement_assessments"]
    )
    assert report["qualification_plan_sha256"] == canonical_sha256(
        qualification_plan
    )
    assert report["authority"]["commands_sent"] == 0
    assert report["authority"]["physical_authority"] is False
    assert any(
        "does not itself establish physical correctness" in limitation
        for limitation in report["limitations"]
    )


def test_candidate_qualification_assessment_reports_missing_and_rejected_gates():
    inventory, proposal, preflight, qualification_plan = (
        candidate_qualification_chain()
    )
    required = [
        item["requirement"]
        for item in qualification_plan["qualification_requirements"]
    ]
    evidence = candidate_qualification_evidence(qualification_plan, required[:2])
    evidence["evidence"][1]["decision"] = "REJECT"

    report = assess_candidate_qualification_evidence(
        inventory, proposal, preflight, qualification_plan, evidence
    )

    assert report["status"] == "EVIDENCE_CHAIN_BLOCKED"
    assert report["blockers"][0] == f"{required[1]}_EVIDENCE_REJECTED"
    assert report["blockers"][1:] == [
        f"{requirement}_EVIDENCE_REQUIRED" for requirement in required[2:]
    ]


def test_candidate_qualification_handoff_binds_complete_chain_in_gate_order():
    inventory, proposal, preflight, qualification_plan = (
        candidate_qualification_chain()
    )
    evidence = candidate_qualification_evidence(qualification_plan)
    assessment = assess_candidate_qualification_evidence(
        inventory, proposal, preflight, qualification_plan, evidence
    )

    receipt = create_candidate_qualification_handoff(
        inventory,
        proposal,
        preflight,
        qualification_plan,
        evidence,
        assessment,
    )

    assert receipt["schema"] == CANDIDATE_QUALIFICATION_HANDOFF_SCHEMA
    assert receipt["status"] == "QUALIFICATION_HANDOFF_READY"
    assert receipt["candidate"] == qualification_plan["candidate"]
    assert receipt["qualification_assessment_sha256"] == canonical_sha256(
        assessment
    )
    assert [item["requirement"] for item in receipt["accepted_evidence"]] == [
        item["requirement"]
        for item in qualification_plan["qualification_requirements"]
    ]
    assert receipt["blockers"] == []
    assert receipt["authority"]["commands_sent"] == 0
    assert receipt["authority"]["physical_authority"] is False


def test_candidate_qualification_handoff_rejects_blocked_or_stale_assessment():
    inventory, proposal, preflight, qualification_plan = (
        candidate_qualification_chain()
    )
    requirements = [
        item["requirement"]
        for item in qualification_plan["qualification_requirements"]
    ]
    incomplete_evidence = candidate_qualification_evidence(
        qualification_plan, requirements[:1]
    )
    blocked = assess_candidate_qualification_evidence(
        inventory,
        proposal,
        preflight,
        qualification_plan,
        incomplete_evidence,
    )
    with pytest.raises(PositionVectorCampaignError, match="chain is not complete"):
        create_candidate_qualification_handoff(
            inventory,
            proposal,
            preflight,
            qualification_plan,
            incomplete_evidence,
            blocked,
        )

    evidence = candidate_qualification_evidence(qualification_plan)
    assessment = assess_candidate_qualification_evidence(
        inventory, proposal, preflight, qualification_plan, evidence
    )
    assessment["evidence_sha256"] = "0" * 64
    with pytest.raises(PositionVectorCampaignError, match="does not reproduce"):
        create_candidate_qualification_handoff(
            inventory,
            proposal,
            preflight,
            qualification_plan,
            evidence,
            assessment,
        )


def test_qualified_candidate_admission_creates_new_passing_inventory_and_receipt():
    inventory, proposal, preflight, qualification_plan = (
        candidate_qualification_chain()
    )
    evidence = candidate_qualification_evidence(qualification_plan)
    assessment = assess_candidate_qualification_evidence(
        inventory, proposal, preflight, qualification_plan, evidence
    )
    handoff = create_candidate_qualification_handoff(
        inventory,
        proposal,
        preflight,
        qualification_plan,
        evidence,
        assessment,
    )

    admitted, receipt = create_qualified_candidate_inventory_package(
        inventory,
        proposal,
        preflight,
        qualification_plan,
        evidence,
        assessment,
        handoff,
        "bare-jaw-keyboard-chain-qualified-20261024",
    )

    assert admitted["inventory_id"] == "bare-jaw-keyboard-chain-qualified-20261024"
    assert admitted["count_kind"] == "PLANNED_GOAL"
    assert admitted["poses"][-1] == {
        "label": proposal["label"],
        "raw_position_counts": proposal["raw_position_counts"],
        "source_ref": proposal["source_ref"],
    }
    assert audit_candidate_count_coverage(admitted)["status"] == (
        "CANDIDATE_COVERAGE_PASS"
    )
    assert receipt["schema"] == CANDIDATE_INVENTORY_ADMISSION_RECEIPT_SCHEMA
    assert receipt["status"] == "QUALIFIED_CANDIDATE_INVENTORY_READY"
    assert receipt["admitted_inventory_sha256"] == canonical_sha256(admitted)
    assert receipt["qualification_handoff_sha256"] == canonical_sha256(handoff)
    assert receipt["resulting_pose_count"] == 9
    assert receipt["authority"]["physical_authority"] is False


def test_qualified_candidate_admission_rejects_stale_handoff_or_reused_identity():
    inventory, proposal, preflight, qualification_plan = (
        candidate_qualification_chain()
    )
    evidence = candidate_qualification_evidence(qualification_plan)
    assessment = assess_candidate_qualification_evidence(
        inventory, proposal, preflight, qualification_plan, evidence
    )
    handoff = create_candidate_qualification_handoff(
        inventory,
        proposal,
        preflight,
        qualification_plan,
        evidence,
        assessment,
    )
    stale = copy.deepcopy(handoff)
    stale["candidate_sha256"] = "0" * 64
    with pytest.raises(PositionVectorCampaignError, match="does not reproduce"):
        create_qualified_candidate_inventory_package(
            inventory,
            proposal,
            preflight,
            qualification_plan,
            evidence,
            assessment,
            stale,
            "bare-jaw-keyboard-chain-qualified-20261024",
        )

    with pytest.raises(PositionVectorCampaignError, match="must differ"):
        create_qualified_candidate_inventory_package(
            inventory,
            proposal,
            preflight,
            qualification_plan,
            evidence,
            assessment,
            handoff,
            inventory["inventory_id"],
        )


def test_qualified_inventory_split_selects_smallest_feasible_training_partition():
    admitted, receipt = qualified_candidate_inventory_package()

    split = plan_qualified_candidate_training_split(admitted, receipt)

    assert split["schema"] == CANDIDATE_TRAINING_SPLIT_PLAN_SCHEMA
    assert split["status"] == "TRAINING_SPLIT_READY"
    assert len(split["training_pose_labels"]) == 5
    assert len(split["held_out_pose_labels"]) == 4
    assert set(split["training_pose_labels"]).isdisjoint(
        split["held_out_pose_labels"]
    )
    assert set(split["training_pose_labels"] + split["held_out_pose_labels"]) == {
        pose["label"] for pose in admitted["poses"]
    }
    assert all(row["meets_minimum"] for row in split["training_joint_coverage"])
    assert admitted["poses"][-1]["label"] in split["training_pose_labels"]
    assert split["authority"]["physical_authority"] is False


def test_qualified_inventory_split_reports_no_feasible_bounded_partition():
    admitted, receipt = qualified_candidate_inventory_package()
    constrained = copy.deepcopy(admitted)
    constrained["poses"] = constrained["poses"][:8]
    for pose in constrained["poses"]:
        pose["raw_position_counts"] = [0] * 7
    for pose_index, position_index in enumerate(INDEXES):
        constrained["poses"][pose_index]["raw_position_counts"][
            position_index
        ] = 128
    constrained_coverage = audit_candidate_count_coverage(constrained)
    assert constrained_coverage["status"] == "CANDIDATE_COVERAGE_PASS"
    bound_receipt = copy.deepcopy(receipt)
    bound_receipt["admitted_inventory_sha256"] = canonical_sha256(constrained)
    bound_receipt["resulting_coverage_sha256"] = canonical_sha256(
        constrained_coverage
    )
    bound_receipt["resulting_pose_count"] = len(constrained["poses"])

    split = plan_qualified_candidate_training_split(constrained, bound_receipt)

    assert split["status"] == "TRAINING_SPLIT_BLOCKED"
    assert split["training_pose_labels"] == []
    assert split["blockers"] == [
        "NO_TRAINING_SUBSET_MEETS_COUNT_SPAN_POLICY"
    ]


def test_qualified_inventory_split_rejects_crossed_admission_receipt():
    admitted, receipt = qualified_candidate_inventory_package()
    receipt["admitted_inventory_sha256"] = "0" * 64

    with pytest.raises(PositionVectorCampaignError, match="binding mismatch"):
        plan_qualified_candidate_training_split(admitted, receipt)


def test_qualified_collection_package_binds_exact_inventory_split_and_outputs():
    admitted, admission_receipt = qualified_candidate_inventory_package()
    split = plan_qualified_candidate_training_split(admitted, admission_receipt)

    plan, observations, receipt = create_qualified_candidate_collection_package(
        inventory_document=admitted,
        admission_receipt_document=admission_receipt,
        training_split_document=split,
        dataset_id="bare-jaw-position-vector-campaign-01",
        producer_id="calibration-producer-01",
        truth_method="link_fiducial_pose",
    )

    assert [slot["source_pose"] for slot in plan["slots"]] == (
        split["training_pose_labels"] + split["held_out_pose_labels"]
    )
    assert [slot["split"] for slot in plan["slots"]] == (
        ["TRAINING"] * 5 + ["HELD_OUT"] * 4
    )
    assert observations == collection_observations_template(plan)
    assert receipt["schema"] == QUALIFIED_COLLECTION_PREPARATION_RECEIPT_SCHEMA
    assert receipt["status"] == "QUALIFIED_COLLECTION_PACKAGE_PREPARED"
    assert receipt["inventory_sha256"] == canonical_sha256(admitted)
    assert receipt["training_split_sha256"] == canonical_sha256(split)
    assert receipt["plan_sha256"] == canonical_sha256(plan)
    assert receipt["observations_sha256"] == canonical_sha256(observations)
    assert (receipt["pose_count"], receipt["training_count"], receipt["held_out_count"]) == (
        9,
        5,
        4,
    )
    assert receipt["next_required_gate"] == "REVIEWED_COLLECTION_READINESS"
    assert receipt["authority"]["physical_authority"] is False


def test_qualified_collection_package_rejects_edited_or_blocked_split():
    admitted, admission_receipt = qualified_candidate_inventory_package()
    split = plan_qualified_candidate_training_split(admitted, admission_receipt)
    edited = copy.deepcopy(split)
    edited["training_pose_labels"].reverse()

    with pytest.raises(PositionVectorCampaignError, match="does not reproduce"):
        create_qualified_candidate_collection_package(
            inventory_document=admitted,
            admission_receipt_document=admission_receipt,
            training_split_document=edited,
            dataset_id="bare-jaw-position-vector-campaign-01",
            producer_id="calibration-producer-01",
            truth_method="link_fiducial_pose",
        )

    constrained = copy.deepcopy(admitted)
    constrained["poses"] = constrained["poses"][:8]
    for pose in constrained["poses"]:
        pose["raw_position_counts"] = [0] * 7
    for pose_index, position_index in enumerate(INDEXES):
        constrained["poses"][pose_index]["raw_position_counts"][position_index] = 128
    coverage = audit_candidate_count_coverage(constrained)
    bound_receipt = copy.deepcopy(admission_receipt)
    bound_receipt["admitted_inventory_sha256"] = canonical_sha256(constrained)
    bound_receipt["resulting_coverage_sha256"] = canonical_sha256(coverage)
    bound_receipt["resulting_pose_count"] = len(constrained["poses"])
    blocked = plan_qualified_candidate_training_split(constrained, bound_receipt)

    with pytest.raises(PositionVectorCampaignError, match="split is blocked"):
        create_qualified_candidate_collection_package(
            inventory_document=constrained,
            admission_receipt_document=bound_receipt,
            training_split_document=blocked,
            dataset_id="bare-jaw-position-vector-campaign-01",
            producer_id="calibration-producer-01",
            truth_method="link_fiducial_pose",
        )


def test_qualified_collection_readiness_plan_binds_package_and_lists_gates():
    admitted, admission_receipt = qualified_candidate_inventory_package()
    split = plan_qualified_candidate_training_split(admitted, admission_receipt)
    plan, observations, preparation_receipt = (
        create_qualified_candidate_collection_package(
            inventory_document=admitted,
            admission_receipt_document=admission_receipt,
            training_split_document=split,
            dataset_id="bare-jaw-position-vector-campaign-01",
            producer_id="calibration-producer-01",
            truth_method="link_fiducial_pose",
        )
    )

    readiness_plan = create_qualified_collection_readiness_plan(
        inventory_document=admitted,
        admission_receipt_document=admission_receipt,
        training_split_document=split,
        collection_plan_document=plan,
        observations_document=observations,
        preparation_receipt_document=preparation_receipt,
    )

    assert readiness_plan["schema"] == QUALIFIED_COLLECTION_READINESS_PLAN_SCHEMA
    assert readiness_plan["status"] == (
        "QUALIFIED_COLLECTION_READINESS_EVIDENCE_REQUIRED"
    )
    assert readiness_plan["pose_labels"] == [
        slot["source_pose"] for slot in plan["slots"]
    ]
    assert [item["requirement"] for item in readiness_plan["evidence_requirements"]] == [
        "INSTALLED_FIRMWARE_BINDING",
        "FIXED_CAMERA_INTRINSICS",
        "CAMERA_TO_BOARD_REGISTRATION",
        "BOARD_GEOMETRY",
        "ATTACHMENT_PROFILE_GEOMETRY",
        "COLLECTION_COLLISION_ENVELOPE",
        "INDEPENDENT_TRUTH_PROCEDURES",
        "COLLECTION_OPERATOR_REVIEW",
    ]
    assert len(readiness_plan["blockers"]) == 8
    assert readiness_plan["collection_plan_sha256"] == canonical_sha256(plan)
    assert readiness_plan["preparation_receipt_sha256"] == canonical_sha256(
        preparation_receipt
    )
    assert readiness_plan["authority"]["physical_authority"] is False


@pytest.mark.parametrize(
    "target,field,replacement,error",
    [
        (
            "plan",
            "attachment_profile",
            "stylus_attachment",
            "collection plan does not reproduce",
        ),
        ("observations", "plan_sha256", "0" * 64, "observations do not reproduce"),
        (
            "receipt",
            "plan_sha256",
            "0" * 64,
            "preparation receipt does not reproduce",
        ),
    ],
)
def test_qualified_collection_readiness_plan_rejects_crossed_package(
    target, field, replacement, error
):
    admitted, admission_receipt = qualified_candidate_inventory_package()
    split = plan_qualified_candidate_training_split(admitted, admission_receipt)
    plan, observations, preparation_receipt = (
        create_qualified_candidate_collection_package(
            inventory_document=admitted,
            admission_receipt_document=admission_receipt,
            training_split_document=split,
            dataset_id="bare-jaw-position-vector-campaign-01",
            producer_id="calibration-producer-01",
            truth_method="link_fiducial_pose",
        )
    )
    values = {
        "plan": copy.deepcopy(plan),
        "observations": copy.deepcopy(observations),
        "receipt": copy.deepcopy(preparation_receipt),
    }
    values[target][field] = replacement

    with pytest.raises(PositionVectorCampaignError, match=error):
        create_qualified_collection_readiness_plan(
            inventory_document=admitted,
            admission_receipt_document=admission_receipt,
            training_split_document=split,
            collection_plan_document=values["plan"],
            observations_document=values["observations"],
            preparation_receipt_document=values["receipt"],
        )


def test_qualified_collection_readiness_assessment_preserves_partial_blockers():
    chain = qualified_collection_readiness_chain()
    readiness_plan = chain[-1]
    requirements = [
        item["requirement"] for item in readiness_plan["evidence_requirements"]
    ]
    evidence = qualified_collection_readiness_evidence(
        readiness_plan, requirements[:2]
    )
    evidence["evidence"][1]["decision"] = "REJECT"

    result = assess_qualified_collection_readiness_evidence(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=chain[4],
        preparation_receipt_document=chain[5],
        readiness_plan_document=readiness_plan,
        evidence_document=evidence,
    )

    assert result["schema"] == QUALIFIED_COLLECTION_READINESS_ASSESSMENT_SCHEMA
    assert result["status"] == "QUALIFIED_COLLECTION_READINESS_BLOCKED"
    assert [item["status"] for item in result["requirement_assessments"]] == [
        "EVIDENCE_ACCEPTED",
        "EVIDENCE_REJECTED",
        *(["EVIDENCE_MISSING"] * 6),
    ]
    assert result["blockers"] == [
        f"{requirements[1]}_EVIDENCE_REJECTED",
        *[f"{requirement}_EVIDENCE_REQUIRED" for requirement in requirements[2:]],
    ]
    assert result["authority"]["commands_sent"] == 0
    assert result["authority"]["physical_authority"] is False


def test_qualified_collection_readiness_assessment_accepts_complete_chain():
    chain = qualified_collection_readiness_chain()
    evidence = qualified_collection_readiness_evidence(chain[-1])

    result = assess_qualified_collection_readiness_evidence(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=chain[4],
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        evidence_document=evidence,
    )

    assert result["status"] == "QUALIFIED_COLLECTION_READINESS_COMPLETE"
    assert result["blockers"] == []
    assert all(
        item["status"] == "EVIDENCE_ACCEPTED"
        for item in result["requirement_assessments"]
    )
    assert result["evidence_sha256"] == canonical_sha256(evidence)


@pytest.mark.parametrize(
    "mutate,match",
    [
        (
            lambda value: value.update(readiness_plan_sha256="0" * 64),
            "binding mismatch",
        ),
        (
            lambda value: value["evidence"][0].update(
                reviewer_id=value["producer_id"]
            ),
            "not independent",
        ),
        (
            lambda value: value["evidence"].append(
                copy.deepcopy(value["evidence"][0])
            ),
            "repeats a requirement",
        ),
        (
            lambda value: value["evidence"][0].update(requirement="UNKNOWN_GATE"),
            "requirement is unknown",
        ),
        (
            lambda value: value["evidence"][0].update(decision="PENDING"),
            "decision is invalid",
        ),
        (
            lambda value: value["evidence"][0].update(evidence_sha256="0" * 63),
            "lowercase SHA-256",
        ),
    ],
)
def test_qualified_collection_readiness_assessment_rejects_invalid_evidence(
    mutate, match
):
    chain = qualified_collection_readiness_chain()
    evidence = qualified_collection_readiness_evidence(chain[-1])
    mutate(evidence)

    with pytest.raises(PositionVectorCampaignError, match=match):
        assess_qualified_collection_readiness_evidence(
            inventory_document=chain[0],
            admission_receipt_document=chain[1],
            training_split_document=chain[2],
            collection_plan_document=chain[3],
            observations_document=chain[4],
            preparation_receipt_document=chain[5],
            readiness_plan_document=chain[6],
            evidence_document=evidence,
        )


def test_qualified_collection_readiness_handoff_binds_complete_chain():
    chain = qualified_collection_readiness_chain()
    evidence = qualified_collection_readiness_evidence(chain[-1])
    assessment = assess_qualified_collection_readiness_evidence(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=chain[4],
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        evidence_document=evidence,
    )

    handoff = create_qualified_collection_readiness_handoff(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=chain[4],
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        evidence_document=evidence,
        assessment_document=assessment,
    )

    assert handoff["schema"] == QUALIFIED_COLLECTION_READINESS_HANDOFF_SCHEMA
    assert handoff["status"] == "QUALIFIED_COLLECTION_READINESS_HANDOFF_READY"
    assert handoff["collection_plan_sha256"] == canonical_sha256(chain[3])
    assert handoff["observations_sha256"] == canonical_sha256(chain[4])
    assert handoff["readiness_assessment_sha256"] == canonical_sha256(assessment)
    assert handoff["pose_labels"] == [
        slot["source_pose"] for slot in chain[3]["slots"]
    ]
    assert len(handoff["accepted_evidence"]) == 8
    assert handoff["next_required_gate"] == (
        "RETAINED_STATIONARY_OBSERVATION_COLLECTION"
    )
    assert handoff["authority"]["commands_sent"] == 0
    assert handoff["authority"]["physical_authority"] is False


def test_qualified_collection_readiness_handoff_rejects_blocked_or_tampered_chain():
    chain = qualified_collection_readiness_chain()
    requirements = [
        item["requirement"] for item in chain[-1]["evidence_requirements"]
    ]
    partial_evidence = qualified_collection_readiness_evidence(
        chain[-1], requirements[:1]
    )
    blocked = assess_qualified_collection_readiness_evidence(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=chain[4],
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        evidence_document=partial_evidence,
    )
    with pytest.raises(PositionVectorCampaignError, match="is not complete"):
        create_qualified_collection_readiness_handoff(
            inventory_document=chain[0],
            admission_receipt_document=chain[1],
            training_split_document=chain[2],
            collection_plan_document=chain[3],
            observations_document=chain[4],
            preparation_receipt_document=chain[5],
            readiness_plan_document=chain[6],
            evidence_document=partial_evidence,
            assessment_document=blocked,
        )

    evidence = qualified_collection_readiness_evidence(chain[-1])
    complete = assess_qualified_collection_readiness_evidence(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=chain[4],
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        evidence_document=evidence,
    )
    tampered = copy.deepcopy(complete)
    tampered["evidence_sha256"] = "0" * 64
    with pytest.raises(PositionVectorCampaignError, match="does not reproduce"):
        create_qualified_collection_readiness_handoff(
            inventory_document=chain[0],
            admission_receipt_document=chain[1],
            training_split_document=chain[2],
            collection_plan_document=chain[3],
            observations_document=chain[4],
            preparation_receipt_document=chain[5],
            readiness_plan_document=chain[6],
            evidence_document=evidence,
            assessment_document=tampered,
        )


def test_qualified_stationary_observation_ingests_one_exact_slot():
    chain = qualified_collection_readiness_handoff_chain()
    evidence = qualified_stationary_observation_evidence(chain, chain[4])

    observations, receipt = ingest_qualified_stationary_observation(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=chain[4],
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        readiness_evidence_document=chain[7],
        readiness_assessment_document=chain[8],
        readiness_handoff_document=chain[9],
        observation_evidence_document=evidence,
    )

    assert observations["samples"][0] == {
        "sample_id": chain[3]["slots"][0]["sample_id"],
        "raw_position_counts": evidence["raw_position_counts"],
        "canonical_joints_rad": evidence["canonical_joints_rad"],
        "truth_evidence_sha256": evidence["truth_evidence_sha256"],
        "stationary": True,
        "motion_active": False,
        "trajectory_progress_permille": 1000,
    }
    assert all(
        item["truth_evidence_sha256"] is None
        for item in observations["samples"][1:]
    )
    assert receipt["schema"] == (
        QUALIFIED_STATIONARY_OBSERVATION_INGESTION_RECEIPT_SCHEMA
    )
    assert receipt["status"] == "QUALIFIED_STATIONARY_OBSERVATION_INGESTED"
    assert receipt["previous_observations_sha256"] == canonical_sha256(chain[4])
    assert receipt["resulting_observations_sha256"] == canonical_sha256(
        observations
    )
    assert (receipt["filled_sample_count"], receipt["remaining_sample_count"]) == (
        1,
        8,
    )
    assert receipt["next_required_gate"] == (
        "RETAINED_STATIONARY_OBSERVATION_COLLECTION"
    )
    assert receipt["authority"]["commands_sent"] == 0


def test_qualified_stationary_observation_supports_hash_chained_progress():
    chain = qualified_collection_readiness_handoff_chain()
    first_evidence = qualified_stationary_observation_evidence(chain, chain[4], 0)
    first, _ = ingest_qualified_stationary_observation(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=chain[4],
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        readiness_evidence_document=chain[7],
        readiness_assessment_document=chain[8],
        readiness_handoff_document=chain[9],
        observation_evidence_document=first_evidence,
    )
    second_evidence = qualified_stationary_observation_evidence(chain, first, 1)

    second, receipt = ingest_qualified_stationary_observation(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=first,
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        readiness_evidence_document=chain[7],
        readiness_assessment_document=chain[8],
        readiness_handoff_document=chain[9],
        observation_evidence_document=second_evidence,
    )

    assert second["samples"][0] == first["samples"][0]
    assert second["samples"][1]["sample_id"] == second_evidence["sample_id"]
    assert receipt["previous_observations_sha256"] == canonical_sha256(first)
    assert (receipt["filled_sample_count"], receipt["remaining_sample_count"]) == (
        2,
        7,
    )


def test_qualified_stationary_observation_completes_compilable_set():
    chain = qualified_collection_readiness_handoff_chain()
    observations = chain[4]
    receipt = None
    for index in range(len(chain[3]["slots"])):
        evidence = qualified_stationary_observation_evidence(
            chain, observations, index
        )
        observations, receipt = ingest_qualified_stationary_observation(
            inventory_document=chain[0],
            admission_receipt_document=chain[1],
            training_split_document=chain[2],
            collection_plan_document=chain[3],
            observations_document=observations,
            preparation_receipt_document=chain[5],
            readiness_plan_document=chain[6],
            readiness_evidence_document=chain[7],
            readiness_assessment_document=chain[8],
            readiness_handoff_document=chain[9],
            observation_evidence_document=evidence,
        )

    assert receipt is not None
    assert (receipt["filled_sample_count"], receipt["remaining_sample_count"]) == (
        9,
        0,
    )
    assert receipt["next_required_gate"] == (
        "QUALIFIED_OBSERVATION_SET_COMPILATION"
    )
    compiled = compile_planned_dataset(chain[3], observations)
    assert len(compiled["samples"]) == 9


@pytest.mark.parametrize(
    "mutate,match",
    [
        (
            lambda value: value.update(current_observations_sha256="0" * 64),
            "current-template binding mismatch",
        ),
        (
            lambda value: value.update(source_pose="OTHER_POSE"),
            "source pose mismatch",
        ),
        (
            lambda value: value.update(
                truth_reviewer_id=value["observation_producer_id"]
            ),
            "not independent",
        ),
        (
            lambda value: value.update(stationary=False),
            "not a stationary observation",
        ),
        (
            lambda value: value.update(
                camera_observation_receipt_sha256="0" * 63
            ),
            "lowercase SHA-256",
        ),
    ],
)
def test_qualified_stationary_observation_rejects_invalid_evidence(mutate, match):
    chain = qualified_collection_readiness_handoff_chain()
    evidence = qualified_stationary_observation_evidence(chain, chain[4])
    mutate(evidence)

    with pytest.raises(PositionVectorCampaignError, match=match):
        ingest_qualified_stationary_observation(
            inventory_document=chain[0],
            admission_receipt_document=chain[1],
            training_split_document=chain[2],
            collection_plan_document=chain[3],
            observations_document=chain[4],
            preparation_receipt_document=chain[5],
            readiness_plan_document=chain[6],
            readiness_evidence_document=chain[7],
            readiness_assessment_document=chain[8],
            readiness_handoff_document=chain[9],
            observation_evidence_document=evidence,
        )


def test_qualified_stationary_observation_rejects_refilling_slot():
    chain = qualified_collection_readiness_handoff_chain()
    evidence = qualified_stationary_observation_evidence(chain, chain[4])
    observations, _ = ingest_qualified_stationary_observation(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=chain[4],
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        readiness_evidence_document=chain[7],
        readiness_assessment_document=chain[8],
        readiness_handoff_document=chain[9],
        observation_evidence_document=evidence,
    )
    replacement = qualified_stationary_observation_evidence(chain, observations)

    with pytest.raises(PositionVectorCampaignError, match="already filled"):
        ingest_qualified_stationary_observation(
            inventory_document=chain[0],
            admission_receipt_document=chain[1],
            training_split_document=chain[2],
            collection_plan_document=chain[3],
            observations_document=observations,
            preparation_receipt_document=chain[5],
            readiness_plan_document=chain[6],
            readiness_evidence_document=chain[7],
            readiness_assessment_document=chain[8],
            readiness_handoff_document=chain[9],
            observation_evidence_document=replacement,
        )


def test_qualified_observation_set_compiles_complete_receipt_chain():
    chain, observations, receipts = completed_qualified_observation_set()

    dataset, receipt = compile_qualified_observation_set(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=observations,
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        readiness_evidence_document=chain[7],
        readiness_assessment_document=chain[8],
        readiness_handoff_document=chain[9],
        ingestion_receipt_documents=receipts,
    )

    assert dataset == compile_planned_dataset(chain[3], observations)
    assert receipt["schema"] == QUALIFIED_OBSERVATION_SET_COMPILATION_RECEIPT_SCHEMA
    assert receipt["status"] == "QUALIFIED_OBSERVATION_SET_COMPILED"
    assert receipt["dataset_sha256"] == canonical_sha256(dataset)
    assert receipt["initial_observations_sha256"] == canonical_sha256(chain[4])
    assert receipt["final_observations_sha256"] == canonical_sha256(observations)
    assert len(receipt["ingestion_receipts"]) == len(chain[3]["slots"])
    assert (receipt["training_sample_count"], receipt["held_out_sample_count"]) == (
        5,
        4,
    )
    assert receipt["next_required_gate"] == "DETERMINISTIC_CALIBRATION_FIT"
    assert receipt["authority"]["commands_sent"] == 0
    assert receipt["authority"]["camera_opened"] is False


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda receipts: receipts.pop(), "does not cover every planned slot"),
        (
            lambda receipts: receipts.reverse(),
            "observation hash chain is broken",
        ),
        (
            lambda receipts: receipts[1].update(previous_observations_sha256="0" * 64),
            "observation hash chain is broken",
        ),
        (
            lambda receipts: receipts[1].update(
                sample_id=receipts[0]["sample_id"],
                source_pose=receipts[0]["source_pose"],
                split=receipts[0]["split"],
            ),
            "repeat a sample",
        ),
        (
            lambda receipts: receipts[-1].update(
                resulting_observations_sha256="0" * 64
            ),
            "does not bind the supplied observations",
        ),
        (
            lambda receipts: receipts[2].update(filled_sample_count=1),
            "sample-count progression mismatch",
        ),
        (
            lambda receipts: receipts[2].update(
                truth_evidence_sha256=receipts[1]["truth_evidence_sha256"]
            ),
            "reuse per-sample evidence",
        ),
    ],
)
def test_qualified_observation_set_rejects_broken_receipt_chain(mutate, match):
    chain, observations, receipts = completed_qualified_observation_set()
    mutate(receipts)

    with pytest.raises(PositionVectorCampaignError, match=match):
        compile_qualified_observation_set(
            inventory_document=chain[0],
            admission_receipt_document=chain[1],
            training_split_document=chain[2],
            collection_plan_document=chain[3],
            observations_document=observations,
            preparation_receipt_document=chain[5],
            readiness_plan_document=chain[6],
            readiness_evidence_document=chain[7],
            readiness_assessment_document=chain[8],
            readiness_handoff_document=chain[9],
            ingestion_receipt_documents=receipts,
        )


def test_qualified_deterministic_fit_reproduces_chain_and_assesses_metrics():
    chain, observations, receipts, compiled, compilation_receipt = (
        qualified_compilation_package()
    )
    policy = CampaignPolicy(minimum_training_count_span=1)

    fit_report, assessment = assess_qualified_deterministic_fit(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=observations,
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        readiness_evidence_document=chain[7],
        readiness_assessment_document=chain[8],
        readiness_handoff_document=chain[9],
        ingestion_receipt_documents=receipts,
        dataset_document=compiled,
        compilation_receipt_document=compilation_receipt,
        calibration_id="qualified-fit-01",
        policy=policy,
    )

    assert fit_report == fit_campaign_dataset(
        compiled, calibration_id="qualified-fit-01", policy=policy
    )
    assert assessment["schema"] == QUALIFIED_DETERMINISTIC_FIT_ASSESSMENT_SCHEMA
    assert assessment["status"] == "QUALIFIED_DETERMINISTIC_FIT_PASS"
    assert assessment["compilation_receipt_sha256"] == canonical_sha256(
        compilation_receipt
    )
    assert assessment["dataset_sha256"] == canonical_sha256(compiled)
    assert assessment["fit_report_sha256"] == canonical_sha256(fit_report)
    assert len(assessment["joint_assessments"]) == len(JOINTS)
    assert assessment["next_required_gate"] == "INDEPENDENT_CALIBRATION_REVIEW"
    assert assessment["authority"]["commands_sent"] == 0
    assert assessment["calibration_activation_authorized"] is False


@pytest.mark.parametrize(
    "target,match",
    [
        ("dataset", "qualified dataset does not reproduce"),
        ("receipt", "qualified compilation receipt does not reproduce"),
    ],
)
def test_qualified_deterministic_fit_rejects_crossed_compilation(target, match):
    chain, observations, receipts, compiled, compilation_receipt = (
        qualified_compilation_package()
    )
    if target == "dataset":
        compiled = copy.deepcopy(compiled)
        compiled["dataset_id"] = "crossed-dataset"
    else:
        compilation_receipt = copy.deepcopy(compilation_receipt)
        compilation_receipt["dataset_sha256"] = "0" * 64

    with pytest.raises(PositionVectorCampaignError, match=match):
        assess_qualified_deterministic_fit(
            inventory_document=chain[0],
            admission_receipt_document=chain[1],
            training_split_document=chain[2],
            collection_plan_document=chain[3],
            observations_document=observations,
            preparation_receipt_document=chain[5],
            readiness_plan_document=chain[6],
            readiness_evidence_document=chain[7],
            readiness_assessment_document=chain[8],
            readiness_handoff_document=chain[9],
            ingestion_receipt_documents=receipts,
            dataset_document=compiled,
            compilation_receipt_document=compilation_receipt,
            calibration_id="qualified-fit-01",
            policy=CampaignPolicy(minimum_training_count_span=1),
        )


def test_qualified_deterministic_fit_does_not_emit_pass_for_failed_policy():
    chain, observations, receipts, compiled, compilation_receipt = (
        qualified_compilation_package()
    )

    with pytest.raises(PositionVectorCampaignError, match="training count span"):
        assess_qualified_deterministic_fit(
            inventory_document=chain[0],
            admission_receipt_document=chain[1],
            training_split_document=chain[2],
            collection_plan_document=chain[3],
            observations_document=observations,
            preparation_receipt_document=chain[5],
            readiness_plan_document=chain[6],
            readiness_evidence_document=chain[7],
            readiness_assessment_document=chain[8],
            readiness_handoff_document=chain[9],
            ingestion_receipt_documents=receipts,
            dataset_document=compiled,
            compilation_receipt_document=compilation_receipt,
            calibration_id="qualified-fit-01",
        )


def test_qualified_independent_fit_review_accepts_exact_reproduced_chain():
    package = qualified_fit_package()
    review_document = qualified_fit_review(*package[3:])

    receipt = accept_qualified_fit_review_package(package, review_document)

    assert receipt["schema"] == QUALIFIED_INDEPENDENT_FIT_REVIEW_RECEIPT_SCHEMA
    assert receipt["status"] == "QUALIFIED_INDEPENDENT_FIT_REVIEW_ACCEPTED"
    assert receipt["review_sha256"] == canonical_sha256(review_document)
    assert receipt["fit_assessment_sha256"] == canonical_sha256(package[6])
    assert receipt["reviewer_id"] == review_document["reviewer_id"]
    assert receipt["next_required_gate"] == "QUALIFIED_CALIBRATION_ARTIFACT_BUILD"
    assert receipt["authority"]["commands_sent"] == 0
    assert receipt["calibration_activation_authorized"] is False


@pytest.mark.parametrize(
    "updates,match",
    [
        ({"dataset_sha256": "0" * 64}, "dataset_sha256 mismatch"),
        (
            {"compilation_receipt_sha256": "1" * 64},
            "compilation_receipt_sha256 mismatch",
        ),
        ({"fit_report_sha256": "2" * 64}, "fit_report_sha256 mismatch"),
        ({"fit_assessment_sha256": "3" * 64}, "fit_assessment_sha256 mismatch"),
        ({"producer_id": "another-producer"}, "producer mismatch"),
        ({"reviewer_id": "calibration-producer-01"}, "independent"),
        ({"decision": "REJECT"}, "not ACCEPT"),
        ({"reviewed_at": "2026-10-24"}, "UTC offset"),
        ({"review_notes_sha256": "invalid"}, "review_notes_sha256"),
    ],
)
def test_qualified_independent_fit_review_rejects_invalid_review(updates, match):
    package = qualified_fit_package()
    review_document = qualified_fit_review(*package[3:])
    review_document.update(updates)

    with pytest.raises(PositionVectorCampaignError, match=match):
        accept_qualified_fit_review_package(package, review_document)


@pytest.mark.parametrize(
    "index,match",
    [
        (5, "qualified fit report does not reproduce"),
        (6, "qualified fit assessment does not reproduce"),
    ],
)
def test_qualified_independent_fit_review_rejects_tampered_fit_artifact(index, match):
    package = list(qualified_fit_package())
    review_document = qualified_fit_review(*package[3:])
    package[index] = copy.deepcopy(package[index])
    package[index]["status"] = "TAMPERED"

    with pytest.raises(PositionVectorCampaignError, match=match):
        accept_qualified_fit_review_package(tuple(package), review_document)


@pytest.mark.parametrize(
    "mutate,match",
    [
        (
            lambda value: value.update(qualification_plan_sha256="0" * 64),
            "binding mismatch",
        ),
        (
            lambda value: value["evidence"][0].update(
                reviewer_id=value["producer_id"]
            ),
            "not independent",
        ),
        (
            lambda value: value["evidence"].append(
                copy.deepcopy(value["evidence"][0])
            ),
            "repeats a requirement",
        ),
        (
            lambda value: value["evidence"][0].update(requirement="UNKNOWN_GATE"),
            "requirement is unknown",
        ),
        (
            lambda value: value["evidence"][0].update(decision="PENDING"),
            "decision is invalid",
        ),
        (
            lambda value: value["evidence"][0].update(evidence_sha256="0" * 63),
            "lowercase SHA-256",
        ),
    ],
)
def test_candidate_qualification_assessment_rejects_invalid_evidence(mutate, match):
    inventory, proposal, preflight, qualification_plan = (
        candidate_qualification_chain()
    )
    evidence = candidate_qualification_evidence(qualification_plan)
    mutate(evidence)

    with pytest.raises(PositionVectorCampaignError, match=match):
        assess_candidate_qualification_evidence(
            inventory, proposal, preflight, qualification_plan, evidence
        )


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda value: value.update(inventory_sha256="0" * 64), "does not bind"),
        (
            lambda value: value.update(attachment_profile="stylus_attachment"),
            "attachment profile",
        ),
        (lambda value: value.update(label="POSE_0"), "already exists"),
        (
            lambda value: value.update(raw_position_counts=[2048] * 6),
            "raw_position_counts",
        ),
    ],
)
def test_candidate_preflight_rejects_crossed_or_invalid_proposals(mutate, match):
    inventory = candidate_inventory()
    proposal = candidate_proposal(inventory)
    mutate(proposal)

    with pytest.raises(PositionVectorCampaignError, match=match):
        evaluate_candidate_count_augmentation(inventory, proposal)


def test_file_workflow_writes_candidate_preflight_without_hardware(tmp_path):
    inventory = candidate_inventory()
    inventory_path = tmp_path / "inventory.json"
    candidate_path = tmp_path / "candidate.json"
    output_path = tmp_path / "preflight.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    candidate_path.write_text(
        json.dumps(candidate_proposal(inventory)), encoding="utf-8"
    )

    assert main([
        "preflight-candidate-augmentation",
        "--inventory", str(inventory_path),
        "--candidate", str(candidate_path),
        "--output", str(output_path),
    ]) == 0
    assert json.loads(output_path.read_bytes())["status"] == (
        "COUNT_VECTOR_CLOSES_CATALOG_GAPS"
    )
    with pytest.raises(PositionVectorCampaignError, match="refusing to replace"):
        main([
            "preflight-candidate-augmentation",
            "--inventory", str(inventory_path),
            "--candidate", str(candidate_path),
            "--output", str(output_path),
        ])


def test_file_workflow_writes_candidate_qualification_plan_without_hardware(tmp_path):
    inventory = candidate_inventory()
    proposal = candidate_proposal(inventory)
    preflight = evaluate_candidate_count_augmentation(inventory, proposal)
    inventory_path = tmp_path / "inventory.json"
    candidate_path = tmp_path / "candidate.json"
    preflight_path = tmp_path / "preflight.json"
    output_path = tmp_path / "qualification-plan.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    candidate_path.write_text(json.dumps(proposal), encoding="utf-8")
    preflight_path.write_text(json.dumps(preflight), encoding="utf-8")

    args = [
        "prepare-candidate-qualification",
        "--inventory", str(inventory_path),
        "--candidate", str(candidate_path),
        "--preflight", str(preflight_path),
        "--output", str(output_path),
    ]
    assert main(args) == 0
    assert json.loads(output_path.read_bytes()) == create_candidate_qualification_plan(
        inventory, proposal, preflight
    )
    with pytest.raises(PositionVectorCampaignError, match="refusing to replace"):
        main(args)


def test_file_workflow_assesses_candidate_qualification_without_hardware(tmp_path):
    inventory, proposal, preflight, qualification_plan = (
        candidate_qualification_chain()
    )
    evidence = candidate_qualification_evidence(qualification_plan)
    documents = {
        "inventory": inventory,
        "candidate": proposal,
        "preflight": preflight,
        "plan": qualification_plan,
        "evidence": evidence,
    }
    paths = {}
    for name, document in documents.items():
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(document), encoding="utf-8")
    output_path = tmp_path / "assessment.json"
    args = [
        "assess-candidate-qualification",
        "--inventory", str(paths["inventory"]),
        "--candidate", str(paths["candidate"]),
        "--preflight", str(paths["preflight"]),
        "--plan", str(paths["plan"]),
        "--evidence", str(paths["evidence"]),
        "--output", str(output_path),
    ]

    assert main(args) == 0
    assert json.loads(output_path.read_bytes())["status"] == "EVIDENCE_CHAIN_COMPLETE"
    with pytest.raises(PositionVectorCampaignError, match="refusing to replace"):
        main(args)


def test_file_workflow_creates_candidate_qualification_handoff_without_hardware(
    tmp_path,
):
    inventory, proposal, preflight, qualification_plan = (
        candidate_qualification_chain()
    )
    evidence = candidate_qualification_evidence(qualification_plan)
    assessment = assess_candidate_qualification_evidence(
        inventory, proposal, preflight, qualification_plan, evidence
    )
    documents = {
        "inventory": inventory,
        "candidate": proposal,
        "preflight": preflight,
        "plan": qualification_plan,
        "evidence": evidence,
        "assessment": assessment,
    }
    paths = {}
    for name, document in documents.items():
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(document), encoding="utf-8")
    output_path = tmp_path / "qualification-handoff.json"
    args = [
        "create-candidate-qualification-handoff",
        "--inventory", str(paths["inventory"]),
        "--candidate", str(paths["candidate"]),
        "--preflight", str(paths["preflight"]),
        "--plan", str(paths["plan"]),
        "--evidence", str(paths["evidence"]),
        "--assessment", str(paths["assessment"]),
        "--output", str(output_path),
    ]

    assert main(args) == 0
    assert json.loads(output_path.read_bytes())["status"] == (
        "QUALIFICATION_HANDOFF_READY"
    )
    with pytest.raises(PositionVectorCampaignError, match="refusing to replace"):
        main(args)


def test_file_workflow_admits_qualified_candidate_without_hardware(tmp_path):
    inventory, proposal, preflight, qualification_plan = (
        candidate_qualification_chain()
    )
    evidence = candidate_qualification_evidence(qualification_plan)
    assessment = assess_candidate_qualification_evidence(
        inventory, proposal, preflight, qualification_plan, evidence
    )
    handoff = create_candidate_qualification_handoff(
        inventory,
        proposal,
        preflight,
        qualification_plan,
        evidence,
        assessment,
    )
    documents = {
        "inventory": inventory,
        "candidate": proposal,
        "preflight": preflight,
        "plan": qualification_plan,
        "evidence": evidence,
        "assessment": assessment,
        "handoff": handoff,
    }
    paths = {}
    for name, document in documents.items():
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(document), encoding="utf-8")
    inventory_output = tmp_path / "qualified-inventory.json"
    receipt_output = tmp_path / "admission-receipt.json"
    args = [
        "admit-qualified-candidate",
        "--inventory", str(paths["inventory"]),
        "--candidate", str(paths["candidate"]),
        "--preflight", str(paths["preflight"]),
        "--plan", str(paths["plan"]),
        "--evidence", str(paths["evidence"]),
        "--assessment", str(paths["assessment"]),
        "--handoff", str(paths["handoff"]),
        "--inventory-id", "bare-jaw-keyboard-chain-qualified-20261024",
        "--inventory-output", str(inventory_output),
        "--receipt-output", str(receipt_output),
    ]

    assert main(args) == 0
    admitted = json.loads(inventory_output.read_bytes())
    receipt = json.loads(receipt_output.read_bytes())
    assert admitted["poses"][-1]["label"] == proposal["label"]
    assert receipt["admitted_inventory_sha256"] == canonical_sha256(admitted)
    with pytest.raises(PositionVectorCampaignError, match="replace or alias"):
        main(args)


def test_file_workflow_plans_qualified_candidate_split_without_hardware(tmp_path):
    admitted, receipt = qualified_candidate_inventory_package()
    inventory_path = tmp_path / "qualified-inventory.json"
    receipt_path = tmp_path / "admission-receipt.json"
    output_path = tmp_path / "training-split.json"
    inventory_path.write_text(json.dumps(admitted), encoding="utf-8")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    args = [
        "plan-qualified-candidate-split",
        "--inventory", str(inventory_path),
        "--admission-receipt", str(receipt_path),
        "--output", str(output_path),
    ]

    assert main(args) == 0
    assert json.loads(output_path.read_bytes())["status"] == "TRAINING_SPLIT_READY"
    with pytest.raises(PositionVectorCampaignError, match="refusing to replace"):
        main(args)


def test_file_workflow_prepares_qualified_collection_without_hardware(tmp_path):
    admitted, admission_receipt = qualified_candidate_inventory_package()
    split = plan_qualified_candidate_training_split(admitted, admission_receipt)
    documents = {
        "inventory": admitted,
        "admission-receipt": admission_receipt,
        "training-split": split,
    }
    paths = {}
    for name, document in documents.items():
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(document), encoding="utf-8")
    plan_path = tmp_path / "collection-plan.json"
    observations_path = tmp_path / "observations.json"
    receipt_path = tmp_path / "preparation-receipt.json"
    args = [
        "prepare-qualified-candidate-collection",
        "--inventory", str(paths["inventory"]),
        "--admission-receipt", str(paths["admission-receipt"]),
        "--training-split", str(paths["training-split"]),
        "--dataset-id", "bare-jaw-position-vector-campaign-01",
        "--producer-id", "calibration-producer-01",
        "--truth-method", "link_fiducial_pose",
        "--plan-output", str(plan_path),
        "--observations-output", str(observations_path),
        "--receipt-output", str(receipt_path),
    ]

    assert main(args) == 0
    plan = json.loads(plan_path.read_bytes())
    observations = json.loads(observations_path.read_bytes())
    receipt = json.loads(receipt_path.read_bytes())
    assert len(plan["slots"]) == 9
    assert observations == collection_observations_template(plan)
    assert receipt["plan_sha256"] == canonical_sha256(plan)
    with pytest.raises(PositionVectorCampaignError, match="replace or alias"):
        main(args)


def test_file_workflow_plans_qualified_collection_readiness_without_hardware(tmp_path):
    admitted, admission_receipt = qualified_candidate_inventory_package()
    split = plan_qualified_candidate_training_split(admitted, admission_receipt)
    plan, observations, preparation_receipt = (
        create_qualified_candidate_collection_package(
            inventory_document=admitted,
            admission_receipt_document=admission_receipt,
            training_split_document=split,
            dataset_id="bare-jaw-position-vector-campaign-01",
            producer_id="calibration-producer-01",
            truth_method="link_fiducial_pose",
        )
    )
    documents = {
        "inventory": admitted,
        "admission-receipt": admission_receipt,
        "training-split": split,
        "collection-plan": plan,
        "observations": observations,
        "preparation-receipt": preparation_receipt,
    }
    paths = {}
    for name, document in documents.items():
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(document), encoding="utf-8")
    output_path = tmp_path / "collection-readiness-plan.json"
    args = [
        "plan-qualified-collection-readiness",
        "--inventory", str(paths["inventory"]),
        "--admission-receipt", str(paths["admission-receipt"]),
        "--training-split", str(paths["training-split"]),
        "--collection-plan", str(paths["collection-plan"]),
        "--observations", str(paths["observations"]),
        "--preparation-receipt", str(paths["preparation-receipt"]),
        "--output", str(output_path),
    ]

    assert main(args) == 0
    result = json.loads(output_path.read_bytes())
    assert result["status"] == "QUALIFIED_COLLECTION_READINESS_EVIDENCE_REQUIRED"
    assert len(result["evidence_requirements"]) == 8
    with pytest.raises(PositionVectorCampaignError, match="refusing to replace"):
        main(args)


def test_file_workflow_assesses_qualified_collection_readiness_without_hardware(
    tmp_path,
):
    chain = qualified_collection_readiness_chain()
    evidence = qualified_collection_readiness_evidence(chain[-1])
    names = (
        "inventory",
        "admission-receipt",
        "training-split",
        "collection-plan",
        "observations",
        "preparation-receipt",
        "readiness-plan",
    )
    paths = {}
    for name, document in zip(names, chain, strict=True):
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(document), encoding="utf-8")
    paths["evidence"] = tmp_path / "evidence.json"
    paths["evidence"].write_text(json.dumps(evidence), encoding="utf-8")
    output_path = tmp_path / "readiness-assessment.json"
    args = [
        "assess-qualified-collection-readiness",
        "--inventory", str(paths["inventory"]),
        "--admission-receipt", str(paths["admission-receipt"]),
        "--training-split", str(paths["training-split"]),
        "--collection-plan", str(paths["collection-plan"]),
        "--observations", str(paths["observations"]),
        "--preparation-receipt", str(paths["preparation-receipt"]),
        "--readiness-plan", str(paths["readiness-plan"]),
        "--evidence", str(paths["evidence"]),
        "--output", str(output_path),
    ]

    assert main(args) == 0
    assert json.loads(output_path.read_bytes())["status"] == (
        "QUALIFIED_COLLECTION_READINESS_COMPLETE"
    )
    with pytest.raises(PositionVectorCampaignError, match="refusing to replace"):
        main(args)


def test_file_workflow_creates_qualified_collection_readiness_handoff_without_hardware(
    tmp_path,
):
    chain = qualified_collection_readiness_chain()
    evidence = qualified_collection_readiness_evidence(chain[-1])
    assessment = assess_qualified_collection_readiness_evidence(
        inventory_document=chain[0],
        admission_receipt_document=chain[1],
        training_split_document=chain[2],
        collection_plan_document=chain[3],
        observations_document=chain[4],
        preparation_receipt_document=chain[5],
        readiness_plan_document=chain[6],
        evidence_document=evidence,
    )
    names = (
        "inventory",
        "admission-receipt",
        "training-split",
        "collection-plan",
        "observations",
        "preparation-receipt",
        "readiness-plan",
    )
    paths = {}
    for name, document in zip(names, chain, strict=True):
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(document), encoding="utf-8")
    paths["evidence"] = tmp_path / "evidence.json"
    paths["evidence"].write_text(json.dumps(evidence), encoding="utf-8")
    paths["assessment"] = tmp_path / "assessment.json"
    paths["assessment"].write_text(json.dumps(assessment), encoding="utf-8")
    output_path = tmp_path / "readiness-handoff.json"
    args = [
        "create-qualified-collection-readiness-handoff",
        "--inventory", str(paths["inventory"]),
        "--admission-receipt", str(paths["admission-receipt"]),
        "--training-split", str(paths["training-split"]),
        "--collection-plan", str(paths["collection-plan"]),
        "--observations", str(paths["observations"]),
        "--preparation-receipt", str(paths["preparation-receipt"]),
        "--readiness-plan", str(paths["readiness-plan"]),
        "--evidence", str(paths["evidence"]),
        "--assessment", str(paths["assessment"]),
        "--output", str(output_path),
    ]

    assert main(args) == 0
    assert json.loads(output_path.read_bytes())["status"] == (
        "QUALIFIED_COLLECTION_READINESS_HANDOFF_READY"
    )
    with pytest.raises(PositionVectorCampaignError, match="refusing to replace"):
        main(args)


def test_file_workflow_ingests_qualified_stationary_observation_without_hardware(
    tmp_path,
):
    chain = qualified_collection_readiness_handoff_chain()
    observation_evidence = qualified_stationary_observation_evidence(
        chain, chain[4]
    )
    names = (
        "inventory",
        "admission-receipt",
        "training-split",
        "collection-plan",
        "observations",
        "preparation-receipt",
        "readiness-plan",
        "readiness-evidence",
        "readiness-assessment",
        "readiness-handoff",
    )
    paths = {}
    for name, document in zip(names, chain, strict=True):
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(document), encoding="utf-8")
    paths["observation-evidence"] = tmp_path / "observation-evidence.json"
    paths["observation-evidence"].write_text(
        json.dumps(observation_evidence), encoding="utf-8"
    )
    observations_output = tmp_path / "updated-observations.json"
    receipt_output = tmp_path / "ingestion-receipt.json"
    args = [
        "ingest-qualified-stationary-observation",
        "--inventory", str(paths["inventory"]),
        "--admission-receipt", str(paths["admission-receipt"]),
        "--training-split", str(paths["training-split"]),
        "--collection-plan", str(paths["collection-plan"]),
        "--observations", str(paths["observations"]),
        "--preparation-receipt", str(paths["preparation-receipt"]),
        "--readiness-plan", str(paths["readiness-plan"]),
        "--readiness-evidence", str(paths["readiness-evidence"]),
        "--readiness-assessment", str(paths["readiness-assessment"]),
        "--readiness-handoff", str(paths["readiness-handoff"]),
        "--observation-evidence", str(paths["observation-evidence"]),
        "--observations-output", str(observations_output),
        "--receipt-output", str(receipt_output),
    ]

    assert main(args) == 0
    assert json.loads(observations_output.read_bytes())["samples"][0][
        "truth_evidence_sha256"
    ] == observation_evidence["truth_evidence_sha256"]
    assert json.loads(receipt_output.read_bytes())["status"] == (
        "QUALIFIED_STATIONARY_OBSERVATION_INGESTED"
    )
    with pytest.raises(PositionVectorCampaignError, match="replace or alias"):
        main(args)


def test_file_workflow_compiles_qualified_observation_set_without_hardware(tmp_path):
    chain, observations, receipts = completed_qualified_observation_set()
    names = (
        "inventory",
        "admission-receipt",
        "training-split",
        "collection-plan",
        "observations",
        "preparation-receipt",
        "readiness-plan",
        "readiness-evidence",
        "readiness-assessment",
        "readiness-handoff",
    )
    documents = (*chain[:4], observations, *chain[5:])
    paths = {}
    for name, document in zip(names, documents, strict=True):
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(document), encoding="utf-8")
    receipt_paths = []
    for index, receipt in enumerate(receipts):
        path = tmp_path / f"ingestion-receipt-{index:02d}.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        receipt_paths.append(path)
    dataset_output = tmp_path / "dataset.json"
    compilation_receipt_output = tmp_path / "compilation-receipt.json"
    args = [
        "compile-qualified-observation-set",
        "--inventory",
        str(paths["inventory"]),
        "--admission-receipt",
        str(paths["admission-receipt"]),
        "--training-split",
        str(paths["training-split"]),
        "--collection-plan",
        str(paths["collection-plan"]),
        "--observations",
        str(paths["observations"]),
        "--preparation-receipt",
        str(paths["preparation-receipt"]),
        "--readiness-plan",
        str(paths["readiness-plan"]),
        "--readiness-evidence",
        str(paths["readiness-evidence"]),
        "--readiness-assessment",
        str(paths["readiness-assessment"]),
        "--readiness-handoff",
        str(paths["readiness-handoff"]),
    ]
    for path in receipt_paths:
        args.extend(("--ingestion-receipt", str(path)))
    args.extend(
        (
            "--output",
            str(dataset_output),
            "--receipt-output",
            str(compilation_receipt_output),
        )
    )

    assert main(args) == 0
    assert json.loads(dataset_output.read_bytes()) == compile_planned_dataset(
        chain[3], observations
    )
    assert json.loads(compilation_receipt_output.read_bytes())["status"] == (
        "QUALIFIED_OBSERVATION_SET_COMPILED"
    )
    with pytest.raises(PositionVectorCampaignError, match="replace or alias"):
        main(args)


def test_file_workflow_assesses_qualified_deterministic_fit_without_hardware(
    tmp_path,
):
    chain, observations, receipts, compiled, compilation_receipt = (
        qualified_compilation_package()
    )
    names = (
        "inventory",
        "admission-receipt",
        "training-split",
        "collection-plan",
        "observations",
        "preparation-receipt",
        "readiness-plan",
        "readiness-evidence",
        "readiness-assessment",
        "readiness-handoff",
    )
    documents = (*chain[:4], observations, *chain[5:])
    paths = {}
    for name, document in zip(names, documents, strict=True):
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(document), encoding="utf-8")
    receipt_paths = []
    for index, receipt in enumerate(receipts):
        path = tmp_path / f"ingestion-receipt-{index:02d}.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        receipt_paths.append(path)
    paths["dataset"] = tmp_path / "dataset.json"
    paths["dataset"].write_text(json.dumps(compiled), encoding="utf-8")
    paths["compilation-receipt"] = tmp_path / "compilation-receipt.json"
    paths["compilation-receipt"].write_text(
        json.dumps(compilation_receipt), encoding="utf-8"
    )
    fit_output = tmp_path / "fit-report.json"
    assessment_output = tmp_path / "fit-assessment.json"
    args = ["assess-qualified-deterministic-fit"]
    for name in names:
        args.extend((f"--{name}", str(paths[name])))
    for path in receipt_paths:
        args.extend(("--ingestion-receipt", str(path)))
    args.extend(
        (
            "--dataset",
            str(paths["dataset"]),
            "--compilation-receipt",
            str(paths["compilation-receipt"]),
            "--calibration-id",
            "qualified-fit-01",
            "--minimum-training-count-span",
            "1",
            "--fit-report-output",
            str(fit_output),
            "--assessment-output",
            str(assessment_output),
        )
    )

    assert main(args) == 0
    fit_report = json.loads(fit_output.read_bytes())
    assessment = json.loads(assessment_output.read_bytes())
    assert fit_report["status"] == "PASS"
    assert assessment["fit_report_sha256"] == canonical_sha256(fit_report)
    assert assessment["status"] == "QUALIFIED_DETERMINISTIC_FIT_PASS"
    with pytest.raises(PositionVectorCampaignError, match="replace or alias"):
        main(args)


def test_file_workflow_accepts_qualified_independent_fit_review_without_hardware(
    tmp_path,
):
    package = qualified_fit_package()
    (
        chain,
        observations,
        receipts,
        compiled,
        compilation_receipt,
        fit_report,
        fit_assessment,
    ) = package
    review_document = qualified_fit_review(*package[3:])
    names = (
        "inventory",
        "admission-receipt",
        "training-split",
        "collection-plan",
        "observations",
        "preparation-receipt",
        "readiness-plan",
        "readiness-evidence",
        "readiness-assessment",
        "readiness-handoff",
    )
    documents = (*chain[:4], observations, *chain[5:])
    paths = {}
    for name, document in zip(names, documents, strict=True):
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(document), encoding="utf-8")
    receipt_paths = []
    for index, receipt in enumerate(receipts):
        path = tmp_path / f"ingestion-receipt-{index:02d}.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        receipt_paths.append(path)
    downstream_documents = {
        "dataset": compiled,
        "compilation-receipt": compilation_receipt,
        "fit-report": fit_report,
        "fit-assessment": fit_assessment,
        "review": review_document,
    }
    for name, document in downstream_documents.items():
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(document), encoding="utf-8")
    output = tmp_path / "independent-fit-review-receipt.json"
    args = ["accept-qualified-independent-fit-review"]
    for name in names:
        args.extend((f"--{name}", str(paths[name])))
    for path in receipt_paths:
        args.extend(("--ingestion-receipt", str(path)))
    for name in downstream_documents:
        args.extend((f"--{name}", str(paths[name])))
    args.extend(("--output", str(output)))

    assert main(args) == 0
    receipt = json.loads(output.read_bytes())
    assert receipt["status"] == "QUALIFIED_INDEPENDENT_FIT_REVIEW_ACCEPTED"
    assert receipt["review_sha256"] == canonical_sha256(review_document)
    with pytest.raises(PositionVectorCampaignError, match="refusing to replace"):
        main(args)


def test_retained_candidate_inventory_and_coverage_report_reproduce():
    software_root = Path(__file__).resolve().parents[2]
    inventory = json.loads(
        (software_root / "config/position_vector_candidate_pose_inventory_20261024.json")
        .read_text(encoding="utf-8")
    )
    retained_report = json.loads(
        (
            software_root
            / "config/calibration_candidates/position_vector_candidate_coverage_20261024.json"
        ).read_text(encoding="utf-8")
    )

    assert audit_candidate_count_coverage(inventory) == retained_report
    retained_augmentation = json.loads(
        (
            software_root
            / "config/calibration_candidates/position_vector_candidate_augmentation_20261024.json"
        ).read_text(encoding="utf-8")
    )
    assert plan_candidate_count_augmentation(inventory) == retained_augmentation


def test_file_workflow_writes_candidate_augmentation_without_hardware(tmp_path):
    inventory_path = tmp_path / "inventory.json"
    output_path = tmp_path / "augmentation.json"
    inventory_path.write_text(json.dumps(candidate_inventory()), encoding="utf-8")

    assert main([
        "plan-candidate-augmentation",
        "--inventory", str(inventory_path),
        "--output", str(output_path),
    ]) == 0
    assert json.loads(output_path.read_bytes()) == plan_candidate_count_augmentation(
        candidate_inventory()
    )
    with pytest.raises(PositionVectorCampaignError, match="refusing to replace"):
        main([
            "plan-candidate-augmentation",
            "--inventory", str(inventory_path),
            "--output", str(output_path),
        ])


def test_reviewed_evidence_derives_hash_bound_ready_assessment():
    readiness, receipt = assess_reviewed_readiness_evidence(reviewed_evidence())

    assert readiness == ready_assessment()
    assert receipt["schema"] == READINESS_EVIDENCE_RECEIPT_SCHEMA
    assert receipt["status"] == "READY_TO_PREPARE"
    assert receipt["evidence_sha256"] == canonical_sha256(reviewed_evidence())
    assert receipt["readiness_sha256"] == canonical_sha256(readiness)
    assert receipt["authority"]["commands_sent"] == 0


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda value: value.update(firmware_verifier_id=value["producer_id"]), "independent"),
        (
            lambda value: value["poses"][0].update(reviewer_id=value["producer_id"]),
            "independent",
        ),
        (
            lambda value: value["poses"][1].update(
                truth_procedure_sha256=value["poses"][0]["truth_procedure_sha256"]
            ),
            "procedure hashes",
        ),
    ],
)
def test_reviewed_evidence_rejects_nonindependent_or_reused_provenance(mutate, match):
    value = reviewed_evidence()
    mutate(value)
    with pytest.raises(PositionVectorCampaignError, match=match):
        assess_reviewed_readiness_evidence(value)


def test_assessed_preparation_binds_exact_readiness_and_all_outputs():
    readiness = ready_assessment()
    source_plan, source_observations, receipt = create_assessed_collection_package(
        readiness_document=readiness,
        dataset_id="installed-arm-count-campaign-01",
        producer_id="calibration-producer-01",
        training_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5)],
        held_out_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5, 8)],
    )

    assert source_plan == plan()
    assert source_observations == collection_observations_template(source_plan)
    assert receipt == {
        "schema": PREPARATION_RECEIPT_SCHEMA,
        "status": "PREPARED_FROM_ASSESSED_EVIDENCE",
        "dataset_id": source_plan["dataset_id"],
        "producer_id": source_plan["producer_id"],
        "readiness_sha256": canonical_sha256(readiness),
        "plan_sha256": canonical_sha256(source_plan),
        "observations_sha256": canonical_sha256(source_observations),
        "authority": source_plan["authority"],
    }


def test_assessed_preparation_rejects_blocked_tampered_or_crossed_readiness():
    blocked = assess_collection_readiness(
        controller_identity={key: CONTROLLER[key] for key in ("vid", "pid", "unit_serial")},
        installed_firmware_sha256=None,
        attachment_profile="no_attachment",
        truth_method="link_fiducial_pose",
        retained_pose_labels=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(8)],
    )
    with pytest.raises(PositionVectorCampaignError, match="readiness is blocked"):
        create_assessed_collection_package(
            readiness_document=blocked,
            dataset_id="campaign-01",
            producer_id="producer-01",
            training_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5)],
            held_out_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5, 8)],
        )

    tampered = ready_assessment()
    tampered["ready_to_prepare"] = False
    with pytest.raises(PositionVectorCampaignError, match="does not reproduce"):
        load_collection_readiness(tampered)

    with pytest.raises(PositionVectorCampaignError, match="do not match"):
        create_assessed_collection_package(
            readiness_document=ready_assessment(),
            dataset_id="campaign-01",
            producer_id="producer-01",
            training_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5)],
            held_out_poses=["CAL_POSE_05", "CAL_POSE_06", "UNREVIEWED_POSE"],
        )


def test_reviewed_preparation_binds_the_complete_provenance_chain():
    evidence = reviewed_evidence()
    readiness, readiness_receipt = assess_reviewed_readiness_evidence(evidence)
    source_plan, source_observations, receipt = create_reviewed_collection_package(
        evidence_document=evidence,
        readiness_document=readiness,
        readiness_receipt_document=readiness_receipt,
        training_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5)],
        held_out_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5, 8)],
    )

    _, _, assessed_receipt = create_assessed_collection_package(
        readiness_document=readiness,
        dataset_id=evidence["campaign_id"],
        producer_id=evidence["producer_id"],
        training_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5)],
        held_out_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5, 8)],
    )
    assert source_plan == plan()
    assert source_observations == collection_observations_template(source_plan)
    assert receipt == {
        "schema": REVIEWED_PREPARATION_RECEIPT_SCHEMA,
        "status": "PREPARED_FROM_REVIEWED_EVIDENCE",
        "campaign_id": evidence["campaign_id"],
        "producer_id": evidence["producer_id"],
        "evidence_sha256": readiness_receipt["evidence_sha256"],
        "readiness_evidence_receipt_sha256": canonical_sha256(readiness_receipt),
        "readiness_sha256": canonical_sha256(readiness),
        "assessed_preparation_receipt_sha256": canonical_sha256(assessed_receipt),
        "plan_sha256": canonical_sha256(source_plan),
        "observations_sha256": canonical_sha256(source_observations),
        "authority": source_plan["authority"],
    }


def test_reviewed_preparation_rejects_crossed_or_tampered_provenance():
    evidence = reviewed_evidence()
    readiness, readiness_receipt = assess_reviewed_readiness_evidence(evidence)

    mismatched_evidence = copy.deepcopy(evidence)
    mismatched_evidence["attachment_profile"] = "stylus_attachment"
    with pytest.raises(
        PositionVectorCampaignError,
        match="reviewed readiness does not match the retained evidence",
    ):
        create_reviewed_collection_package(
            evidence_document=mismatched_evidence,
            readiness_document=readiness,
            readiness_receipt_document=readiness_receipt,
            training_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5)],
            held_out_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5, 8)],
        )

    crossed_evidence = copy.deepcopy(evidence)
    crossed_evidence["campaign_id"] = "other-campaign"
    with pytest.raises(PositionVectorCampaignError, match="does not reproduce"):
        create_reviewed_collection_package(
            evidence_document=crossed_evidence,
            readiness_document=readiness,
            readiness_receipt_document=readiness_receipt,
            training_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5)],
            held_out_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5, 8)],
        )

    tampered_receipt = dict(readiness_receipt)
    tampered_receipt["evidence_sha256"] = "f" * 64
    with pytest.raises(PositionVectorCampaignError, match="does not reproduce"):
        create_reviewed_collection_package(
            evidence_document=evidence,
            readiness_document=readiness,
            readiness_receipt_document=tampered_receipt,
            training_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5)],
            held_out_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5, 8)],
        )


def reviewed_collection():
    evidence = reviewed_evidence()
    readiness, readiness_receipt = assess_reviewed_readiness_evidence(evidence)
    source_plan, _, preparation_receipt = create_reviewed_collection_package(
        evidence_document=evidence,
        readiness_document=readiness,
        readiness_receipt_document=readiness_receipt,
        training_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5)],
        held_out_poses=[f"CAL_POSE_{ordinal:02d}" for ordinal in range(5, 8)],
    )
    return (
        evidence,
        readiness,
        readiness_receipt,
        source_plan,
        observations(source_plan),
        preparation_receipt,
    )


def test_reviewed_compilation_binds_observations_and_dataset_to_preparation():
    (
        evidence,
        readiness,
        readiness_receipt,
        source_plan,
        source_observations,
        preparation_receipt,
    ) = reviewed_collection()
    source_dataset, receipt = create_reviewed_dataset_package(
        evidence_document=evidence,
        readiness_document=readiness,
        readiness_receipt_document=readiness_receipt,
        preparation_receipt_document=preparation_receipt,
        plan_document=source_plan,
        observations_document=source_observations,
    )

    assert source_dataset == compile_planned_dataset(source_plan, source_observations)
    assert receipt == {
        "schema": REVIEWED_COMPILATION_RECEIPT_SCHEMA,
        "status": "COMPILED_FROM_REVIEWED_COLLECTION",
        "campaign_id": evidence["campaign_id"],
        "producer_id": evidence["producer_id"],
        "evidence_sha256": preparation_receipt["evidence_sha256"],
        "readiness_evidence_receipt_sha256": preparation_receipt[
            "readiness_evidence_receipt_sha256"
        ],
        "readiness_sha256": canonical_sha256(readiness),
        "reviewed_preparation_receipt_sha256": canonical_sha256(
            preparation_receipt
        ),
        "plan_sha256": canonical_sha256(source_plan),
        "observations_sha256": canonical_sha256(source_observations),
        "dataset_sha256": canonical_sha256(source_dataset),
        "authority": source_plan["authority"],
    }


def test_reviewed_compilation_rejects_crossed_plan_or_preparation_receipt():
    (
        evidence,
        readiness,
        readiness_receipt,
        source_plan,
        source_observations,
        preparation_receipt,
    ) = reviewed_collection()
    crossed_plan = copy.deepcopy(source_plan)
    crossed_plan["attachment_profile"] = "stylus_attachment"
    crossed_observations = observations(crossed_plan)
    with pytest.raises(
        PositionVectorCampaignError,
        match="collection plan does not reproduce from reviewed preparation",
    ):
        create_reviewed_dataset_package(
            evidence_document=evidence,
            readiness_document=readiness,
            readiness_receipt_document=readiness_receipt,
            preparation_receipt_document=preparation_receipt,
            plan_document=crossed_plan,
            observations_document=crossed_observations,
        )

    tampered_receipt = copy.deepcopy(preparation_receipt)
    tampered_receipt["plan_sha256"] = "f" * 64
    with pytest.raises(
        PositionVectorCampaignError,
        match="reviewed preparation receipt does not reproduce",
    ):
        create_reviewed_dataset_package(
            evidence_document=evidence,
            readiness_document=readiness,
            readiness_receipt_document=readiness_receipt,
            preparation_receipt_document=tampered_receipt,
            plan_document=source_plan,
            observations_document=source_observations,
        )


def planned_dataset(source_plan=None):
    source_plan = source_plan or plan()
    value = dataset(source_plan["attachment_profile"])
    for sample, slot in zip(value["samples"], source_plan["slots"], strict=True):
        sample["sample_id"] = slot["sample_id"]
    return value


def test_collection_plan_freezes_profile_split_and_empty_evidence_slots():
    first = plan()
    second = plan()
    template = collection_observations_template(first)

    assert first == second == load_collection_plan(first)
    assert first["schema"] == PLAN_SCHEMA
    assert first["attachment_profile"] == "no_attachment"
    assert [slot["split"] for slot in first["slots"]] == [
        *("TRAINING" for _ in range(5)),
        *("HELD_OUT" for _ in range(3)),
    ]
    assert first["authority"] == {
        "controller_opened": False,
        "camera_opened": False,
        "commands_sent": 0,
        "motion_authorized": False,
        "physical_authority": False,
    }
    assert template["plan_sha256"] == canonical_sha256(first)
    assert all(sample["raw_position_counts"] is None for sample in template["samples"])


def test_planned_observations_compile_into_existing_strict_dataset_and_fit():
    source_plan = plan()
    compiled = compile_planned_dataset(source_plan, observations(source_plan))

    assert compiled == load_campaign_dataset(planned_dataset(source_plan))
    assert fit_campaign_dataset(compiled, calibration_id="fit-01")["status"] == "PASS"


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda value: value.update(plan_sha256="0" * 64), "plan hash"),
        (
            lambda value: value["samples"].__setitem__(
                0, {**value["samples"][0], "sample_id": "wrong-slot"}
            ),
            "sample order",
        ),
        (lambda value: value["samples"].pop(), "every planned slot"),
        (
            lambda value: value["samples"][0].update(raw_position_counts=None),
            "raw_position_counts",
        ),
    ],
)
def test_planned_observations_reject_incomplete_or_crossed_evidence(mutate, match):
    source_plan = plan()
    value = observations(source_plan)
    mutate(value)
    with pytest.raises(PositionVectorCampaignError, match=match):
        compile_planned_dataset(source_plan, value)


def test_collection_plan_rejects_profile_crossing_duplicate_poses_and_short_split():
    with pytest.raises(PositionVectorCampaignError, match="attachment profile"):
        create_collection_plan(
            dataset_id="campaign-01", producer_id="producer-01",
            controller_binding=CONTROLLER, attachment_profile="unknown",
            training_poses=[f"p-{i}" for i in range(5)],
            held_out_poses=[f"h-{i}" for i in range(3)],
            truth_method="link_fiducial_pose",
        )
    with pytest.raises(PositionVectorCampaignError, match="unique"):
        create_collection_plan(
            dataset_id="campaign-01", producer_id="producer-01",
            controller_binding=CONTROLLER, attachment_profile="no_attachment",
            training_poses=["same", "p-1", "p-2", "p-3", "p-4"],
            held_out_poses=["same", "h-1", "h-2"],
            truth_method="link_fiducial_pose",
        )
    with pytest.raises(PositionVectorCampaignError, match="held-out slots"):
        create_collection_plan(
            dataset_id="campaign-01", producer_id="producer-01",
            controller_binding=CONTROLLER, attachment_profile="no_attachment",
            training_poses=[f"p-{i}" for i in range(5)], held_out_poses=["h-0"],
            truth_method="link_fiducial_pose",
        )


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


def test_file_workflow_prepares_and_compiles_frozen_collection(tmp_path):
    plan_path = tmp_path / "plan.json"
    observations_path = tmp_path / "observations.json"
    dataset_path = tmp_path / "dataset.json"
    pose_args = []
    for ordinal in range(5):
        pose_args.extend(["--training-pose", f"CAL_POSE_{ordinal:02d}"])
    for ordinal in range(5, 8):
        pose_args.extend(["--held-out-pose", f"CAL_POSE_{ordinal:02d}"])

    assert main([
        "prepare",
        "--dataset-id", "installed-arm-count-campaign-01",
        "--producer-id", "calibration-producer-01",
        "--vid", CONTROLLER["vid"],
        "--pid", CONTROLLER["pid"],
        "--unit-serial", CONTROLLER["unit_serial"],
        "--firmware-sha256", CONTROLLER["firmware_sha256"],
        "--attachment-profile", "no_attachment",
        "--truth-method", "link_fiducial_pose",
        *pose_args,
        "--plan-output", str(plan_path),
        "--observations-output", str(observations_path),
    ]) == 0
    prepared_plan = json.loads(plan_path.read_bytes())
    assert prepared_plan == plan()
    observations_path.write_text(
        json.dumps(observations(prepared_plan)), encoding="utf-8"
    )
    assert main([
        "compile", "--plan", str(plan_path),
        "--observations", str(observations_path), "--output", str(dataset_path),
    ]) == 0
    assert load_campaign_dataset(json.loads(dataset_path.read_bytes())) == load_campaign_dataset(
        planned_dataset(prepared_plan)
    )

    with pytest.raises(PositionVectorCampaignError, match="preparation output"):
        main([
            "prepare",
            "--dataset-id", "installed-arm-count-campaign-01",
            "--producer-id", "calibration-producer-01",
            "--vid", CONTROLLER["vid"], "--pid", CONTROLLER["pid"],
            "--unit-serial", CONTROLLER["unit_serial"],
            "--firmware-sha256", CONTROLLER["firmware_sha256"],
            "--attachment-profile", "no_attachment",
            "--truth-method", "link_fiducial_pose", *pose_args,
            "--plan-output", str(plan_path),
            "--observations-output", str(tmp_path / "another.json"),
        ])


def test_file_workflow_prepares_from_exact_assessment_with_receipt(tmp_path):
    readiness_path = tmp_path / "readiness.json"
    plan_path = tmp_path / "plan.json"
    observations_path = tmp_path / "observations.json"
    receipt_path = tmp_path / "preparation-receipt.json"
    readiness_path.write_text(json.dumps(ready_assessment()), encoding="utf-8")
    pose_args = []
    for ordinal in range(5):
        pose_args.extend(["--training-pose", f"CAL_POSE_{ordinal:02d}"])
    for ordinal in range(5, 8):
        pose_args.extend(["--held-out-pose", f"CAL_POSE_{ordinal:02d}"])

    assert main([
        "prepare-assessed",
        "--readiness", str(readiness_path),
        "--dataset-id", "installed-arm-count-campaign-01",
        "--producer-id", "calibration-producer-01",
        *pose_args,
        "--plan-output", str(plan_path),
        "--observations-output", str(observations_path),
        "--receipt-output", str(receipt_path),
    ]) == 0

    prepared_plan = json.loads(plan_path.read_bytes())
    prepared_observations = json.loads(observations_path.read_bytes())
    receipt = json.loads(receipt_path.read_bytes())
    assert receipt["readiness_sha256"] == canonical_sha256(ready_assessment())
    assert receipt["plan_sha256"] == canonical_sha256(prepared_plan)
    assert receipt["observations_sha256"] == canonical_sha256(prepared_observations)
    assert receipt["authority"]["commands_sent"] == 0

    with pytest.raises(PositionVectorCampaignError, match="replace or alias"):
        main([
            "prepare-assessed",
            "--readiness", str(readiness_path),
            "--dataset-id", "installed-arm-count-campaign-01",
            "--producer-id", "calibration-producer-01",
            *pose_args,
            "--plan-output", str(plan_path),
            "--observations-output", str(tmp_path / "other-observations.json"),
            "--receipt-output", str(tmp_path / "other-receipt.json"),
        ])


def test_file_workflow_prepares_from_reviewed_evidence_chain(tmp_path):
    evidence = reviewed_evidence()
    readiness, readiness_receipt = assess_reviewed_readiness_evidence(evidence)
    evidence_path = tmp_path / "evidence.json"
    readiness_path = tmp_path / "readiness.json"
    readiness_receipt_path = tmp_path / "readiness-receipt.json"
    plan_path = tmp_path / "plan.json"
    observations_path = tmp_path / "observations.json"
    receipt_path = tmp_path / "reviewed-preparation-receipt.json"
    for path, value in (
        (evidence_path, evidence),
        (readiness_path, readiness),
        (readiness_receipt_path, readiness_receipt),
    ):
        path.write_text(json.dumps(value), encoding="utf-8")
    pose_args = []
    for ordinal in range(5):
        pose_args.extend(["--training-pose", f"CAL_POSE_{ordinal:02d}"])
    for ordinal in range(5, 8):
        pose_args.extend(["--held-out-pose", f"CAL_POSE_{ordinal:02d}"])

    assert main([
        "prepare-reviewed",
        "--evidence", str(evidence_path),
        "--readiness", str(readiness_path),
        "--readiness-receipt", str(readiness_receipt_path),
        *pose_args,
        "--plan-output", str(plan_path),
        "--observations-output", str(observations_path),
        "--receipt-output", str(receipt_path),
    ]) == 0

    prepared_plan = json.loads(plan_path.read_bytes())
    prepared_observations = json.loads(observations_path.read_bytes())
    receipt = json.loads(receipt_path.read_bytes())
    assert prepared_plan["dataset_id"] == evidence["campaign_id"]
    assert prepared_plan["producer_id"] == evidence["producer_id"]
    assert receipt["schema"] == REVIEWED_PREPARATION_RECEIPT_SCHEMA
    assert receipt["plan_sha256"] == canonical_sha256(prepared_plan)
    assert receipt["observations_sha256"] == canonical_sha256(prepared_observations)


def test_file_workflow_compiles_from_reviewed_preparation_chain(tmp_path):
    (
        evidence,
        readiness,
        readiness_receipt,
        source_plan,
        source_observations,
        preparation_receipt,
    ) = reviewed_collection()
    input_documents = {
        "evidence.json": evidence,
        "readiness.json": readiness,
        "readiness-receipt.json": readiness_receipt,
        "preparation-receipt.json": preparation_receipt,
        "plan.json": source_plan,
        "observations.json": source_observations,
    }
    for name, value in input_documents.items():
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    dataset_path = tmp_path / "dataset.json"
    receipt_path = tmp_path / "compilation-receipt.json"

    assert main([
        "compile-reviewed",
        "--evidence", str(tmp_path / "evidence.json"),
        "--readiness", str(tmp_path / "readiness.json"),
        "--readiness-receipt", str(tmp_path / "readiness-receipt.json"),
        "--preparation-receipt", str(tmp_path / "preparation-receipt.json"),
        "--plan", str(tmp_path / "plan.json"),
        "--observations", str(tmp_path / "observations.json"),
        "--output", str(dataset_path),
        "--receipt-output", str(receipt_path),
    ]) == 0

    compiled = json.loads(dataset_path.read_bytes())
    receipt = json.loads(receipt_path.read_bytes())
    assert compiled == compile_planned_dataset(source_plan, source_observations)
    assert receipt["schema"] == REVIEWED_COMPILATION_RECEIPT_SCHEMA
    assert receipt["reviewed_preparation_receipt_sha256"] == canonical_sha256(
        preparation_receipt
    )
    assert receipt["dataset_sha256"] == canonical_sha256(compiled)
    assert receipt["authority"]["commands_sent"] == 0

    with pytest.raises(PositionVectorCampaignError, match="replace or alias"):
        main([
            "compile-reviewed",
            "--evidence", str(tmp_path / "evidence.json"),
            "--readiness", str(tmp_path / "readiness.json"),
            "--readiness-receipt", str(tmp_path / "readiness-receipt.json"),
            "--preparation-receipt", str(tmp_path / "preparation-receipt.json"),
            "--plan", str(tmp_path / "plan.json"),
            "--observations", str(tmp_path / "observations.json"),
            "--output", str(dataset_path),
            "--receipt-output", str(tmp_path / "other-receipt.json"),
        ])


def test_file_workflow_writes_blocked_readiness_report_without_hardware(tmp_path):
    output = tmp_path / "readiness.json"
    pose_args = []
    for name in ("A_CLEAR", "A_HOVER", "A_DOWN", "B_CLEAR", "B_HOVER", "B_DOWN"):
        pose_args.extend(["--retained-pose", name])

    assert main([
        "assess",
        "--vid", CONTROLLER["vid"],
        "--pid", CONTROLLER["pid"],
        "--unit-serial", CONTROLLER["unit_serial"],
        "--attachment-profile", "no_attachment",
        "--truth-method", "link_fiducial_pose",
        *pose_args,
        "--output", str(output),
    ]) == 0
    report = json.loads(output.read_bytes())
    assert report["status"] == "BLOCKED"
    assert report["blockers"] == [
        "INSTALLED_FIRMWARE_SHA256_UNVERIFIED",
        "UNIQUE_SOURCE_POSE_COUNT_6_BELOW_8",
    ]
    with pytest.raises(PositionVectorCampaignError, match="refusing to replace"):
        main([
            "assess", "--vid", CONTROLLER["vid"], "--pid", CONTROLLER["pid"],
            "--unit-serial", CONTROLLER["unit_serial"],
            "--attachment-profile", "no_attachment",
            "--truth-method", "link_fiducial_pose", *pose_args,
            "--output", str(output),
        ])


def test_file_workflow_assesses_reviewed_evidence_without_hardware(tmp_path):
    evidence_path = tmp_path / "reviewed-evidence.json"
    readiness_path = tmp_path / "readiness.json"
    receipt_path = tmp_path / "readiness-receipt.json"
    evidence_path.write_text(json.dumps(reviewed_evidence()), encoding="utf-8")

    assert main([
        "assess-reviewed",
        "--evidence", str(evidence_path),
        "--readiness-output", str(readiness_path),
        "--receipt-output", str(receipt_path),
    ]) == 0
    readiness = json.loads(readiness_path.read_bytes())
    receipt = json.loads(receipt_path.read_bytes())
    assert readiness["status"] == "READY_TO_PREPARE"
    assert receipt["readiness_sha256"] == canonical_sha256(readiness)
