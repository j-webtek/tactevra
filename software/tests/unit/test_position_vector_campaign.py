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
    CANDIDATE_INVENTORY_SCHEMA,
    CANDIDATE_PREFLIGHT_SCHEMA,
    CANDIDATE_PROPOSAL_SCHEMA,
    CANDIDATE_QUALIFICATION_PLAN_SCHEMA,
    CANDIDATE_QUALIFICATION_ASSESSMENT_SCHEMA,
    CANDIDATE_QUALIFICATION_EVIDENCE_SCHEMA,
    CANDIDATE_QUALIFICATION_HANDOFF_SCHEMA,
    DATASET_SCHEMA,
    FIT_REPORT_SCHEMA,
    OBSERVATIONS_SCHEMA,
    PLAN_SCHEMA,
    PREPARATION_RECEIPT_SCHEMA,
    READINESS_EVIDENCE_RECEIPT_SCHEMA,
    READINESS_EVIDENCE_SCHEMA,
    READINESS_SCHEMA,
    REVIEWED_COMPILATION_RECEIPT_SCHEMA,
    REVIEWED_PREPARATION_RECEIPT_SCHEMA,
    REVIEW_SCHEMA,
    CampaignPolicy,
    PositionVectorCampaignError,
    audit_candidate_count_coverage,
    assess_candidate_qualification_evidence,
    assess_collection_readiness,
    assess_reviewed_readiness_evidence,
    build_calibration_artifact,
    canonical_sha256,
    collection_observations_template,
    compile_planned_dataset,
    create_assessed_collection_package,
    create_candidate_qualification_handoff,
    create_candidate_qualification_plan,
    create_collection_plan,
    create_reviewed_collection_package,
    create_reviewed_dataset_package,
    evaluate_candidate_count_augmentation,
    fit_campaign_dataset,
    load_campaign_dataset,
    load_collection_readiness,
    load_collection_plan,
    main,
    plan_candidate_count_augmentation,
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
