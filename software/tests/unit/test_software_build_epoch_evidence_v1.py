from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

from rocell.application.owner_governed_configuration_epoch_v1 import (
    assess_owner_governed_configuration_epoch_v1,
    build_owner_governed_configuration_epoch_draft_v1,
)
from rocell.application.r97_owner_ai_review_acceptance_v1 import (
    parse_r97_owner_ai_review_acceptance_v1,
)
from rocell.application.software_build_epoch_evidence_v1 import (
    TRACKED_SOURCES,
    SoftwareBuildEpochEvidenceError,
    build_software_build_epoch_evidence_v1,
    review_software_build_epoch_evidence_v1,
    software_build_epoch_component_v1,
)


ROOT = Path(__file__).resolve().parents[2]


def acceptance():
    return parse_r97_owner_ai_review_acceptance_v1(json.loads((
        ROOT / "ai/eval/arm067_r97_owner_ai_review_acceptance.json"
    ).read_text(encoding="utf-8")))


def test_evidence_is_deterministic_schema_valid_and_authority_free():
    first = build_software_build_epoch_evidence_v1(ROOT)
    second = build_software_build_epoch_evidence_v1(ROOT)
    assert first == second
    assert first.evidence_bundle_sha256 == second.evidence_bundle_sha256
    document = first.to_dict()
    schema = json.loads((
        ROOT / "ai/schemas/software_build_epoch_evidence_v1.schema.json"
    ).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(document)
    assert [item[0] for item in first.binding_hashes] == [
        "build_snapshot", "source_binding", "dependency_receipt",
        "provider_hashes",
    ]
    assert document["physical_measurement_claimed"] is False
    for field in (
        "hardware_access", "installation_authorized",
        "controller_start_authorized", "transport_authorized",
        "execution_authorized", "physical_authority",
    ):
        assert document[field] is False


def test_review_is_closed_schema_valid_and_cross_lineage_fails():
    evidence = build_software_build_epoch_evidence_v1(ROOT)
    review = review_software_build_epoch_evidence_v1(evidence)
    assert review.accepted is True
    schema = json.loads((
        ROOT / "ai/schemas/software_build_owner_ai_review_v1.schema.json"
    ).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(review.to_dict())
    crossed = replace(review, evidence_bundle_sha256="0" * 64)
    with pytest.raises(SoftwareBuildEpochEvidenceError,
                       match="crosses evidence lineage"):
        software_build_epoch_component_v1(
            evidence, crossed, measured_monotonic_ns=1,
            valid_until_monotonic_ns=100)


def test_provider_tamper_is_rejected_before_component_admission(tmp_path):
    for relative in TRACKED_SOURCES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    protocol = tmp_path / "src/rocell/arm/all_joint_command.py"
    protocol.write_bytes(protocol.read_bytes() + b"\n# tampered\n")
    with pytest.raises(SoftwareBuildEpochEvidenceError,
                       match="protocol provider differs"):
        build_software_build_epoch_evidence_v1(tmp_path)


def test_partial_epoch_advances_only_software_build():
    evidence = build_software_build_epoch_evidence_v1(ROOT)
    review = review_software_build_epoch_evidence_v1(evidence)
    component = software_build_epoch_component_v1(
        evidence, review, measured_monotonic_ns=1,
        valid_until_monotonic_ns=100)
    draft = build_owner_governed_configuration_epoch_draft_v1(
        epoch_id="arm-069-test", owner_acceptance=acceptance(),
        components=(component,))
    report = assess_owner_governed_configuration_epoch_v1(
        draft, evaluated_monotonic_ns=2, owner_acceptance=acceptance())
    document = report.to_dict()
    assert document["status"] == "BLOCKED"
    assert document["ready_component_ids"] == ["software_build"]
    assert len(document["missing_component_ids"]) == 7
    assert document["configuration_epoch_sha256"] is None
    assert document["epoch_bound_build_proposal_ready"] is False


def test_retained_arm069_artifacts_remain_historical_after_dependency_change(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "arm069_builder", ROOT / "scripts/build_arm069_software_build_epoch.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    summary = module.build(
        software_root=ROOT,
        acceptance_path=(
            ROOT / "ai/eval/arm067_r97_owner_ai_review_acceptance.json"),
        output_directory=tmp_path,
    )
    assert summary["ready_component_ids"] == ["software_build"]
    assert len(summary["missing_component_ids"]) == 7
    assert summary["configuration_epoch_sha256"] is None
    current = json.loads((
        tmp_path / "arm069_software_build_evidence.json").read_text())
    retained = json.loads((
        ROOT / "ai/eval/arm069_software_build_evidence.json").read_text())
    current_sources = {item["path"]: item["sha256"]
                       for item in current["source_files"]}
    retained_sources = {item["path"]: item["sha256"]
                        for item in retained["source_files"]}
    assert current_sources["pyproject.toml"] != retained_sources["pyproject.toml"]
    assert current["evidence_bundle_sha256"] != retained["evidence_bundle_sha256"]
    for file_name in (
        "arm069_software_build_evidence.json",
        "arm069_software_build_owner_ai_review.json",
        "arm069_owner_epoch_draft.json",
        "arm069_owner_epoch_partial_assessment.json",
    ):
        generated = json.loads((tmp_path / file_name).read_text())
        historical = json.loads((ROOT / "ai/eval" / file_name).read_text())
        assert generated["physical_authority"] is False
        assert historical["physical_authority"] is False
    schema_pairs = (
        ("arm069_software_build_evidence.json",
         "software_build_epoch_evidence_v1.schema.json"),
        ("arm069_software_build_owner_ai_review.json",
         "software_build_owner_ai_review_v1.schema.json"),
        ("arm069_owner_epoch_draft.json",
         "owner_governed_configuration_epoch_draft_v1.schema.json"),
        ("arm069_owner_epoch_partial_assessment.json",
         "owner_governed_configuration_epoch_assessment_v1.schema.json"),
    )
    for artifact, schema_name in schema_pairs:
        document = json.loads((ROOT / "ai/eval" / artifact).read_text())
        schema = json.loads((ROOT / "ai/schemas" / schema_name).read_text())
        jsonschema.Draft202012Validator(schema).validate(document)
