from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import sys

import jsonschema
import pytest


AI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI))

from eval.build_parked_pose_evidence_index import (  # noqa: E402
    DECLARATIONS_SCHEMA,
    build_index,
    canonical_hash,
    load_strict_json,
)
from eval.preflight_parked_pose_campaign import preflight  # noqa: E402
from test_parked_pose_preflight import _package, _write_json  # noqa: E402


def _declarations(root: Path, index: dict) -> Path:
    core = {
        "schema": "rocell.ai_parked_pose_custody_declarations.v1",
        "scope": "EXTERNAL_DECLARATIONS_REQUIRING_OWNER_AUTHENTICATION",
        "campaign_sha256": index["campaign_sha256"],
        "custody_review_sha256": index["custody_review_sha256"],
        "declarations": [
            {"sha256": entry["sha256"], "custody": entry["custody"]}
            for entry in index["entries"]
        ],
    }
    document = {**core, "declarations_sha256": canonical_hash(core)}
    return _write_json(root / "custody-declarations.json", document)


def _rehash_declarations(document: dict) -> None:
    document["declarations_sha256"] = canonical_hash(
        {key: value for key, value in document.items() if key != "declarations_sha256"}
    )


def test_schema_and_complete_inventory_are_deterministic_and_preflight_compatible(tmp_path):
    jsonschema.Draft202012Validator.check_schema(load_strict_json(DECLARATIONS_SCHEMA))
    campaign_path, _, evidence, _, expected = _package(tmp_path)
    declarations_path = _declarations(tmp_path, expected)
    first = build_index(campaign_path, declarations_path, evidence)
    second = build_index(campaign_path, declarations_path, evidence)
    assert first == second == expected
    index_path = _write_json(tmp_path / "built-index.json", first)
    receipt = preflight(campaign_path, index_path, evidence)
    assert receipt["status"] == "PASS_FILE_INTEGRITY_ONLY"
    assert receipt["verified_artifact_count"] == 270
    assert receipt["physical_deployment_qualified"] is False
    assert receipt["controller_authority"] is False


def test_missing_extra_empty_and_duplicate_retained_files_are_rejected(tmp_path):
    campaign_path, _, evidence, _, expected = _package(tmp_path)
    declarations_path = _declarations(tmp_path, expected)
    first = evidence / expected["entries"][0]["relative_path"]
    original = first.read_bytes()
    first.unlink()
    with pytest.raises(ValueError, match="retained file coverage mismatch"):
        build_index(campaign_path, declarations_path, evidence)

    first.write_bytes(original)
    (evidence / "extra.bin").write_bytes(b"extra")
    with pytest.raises(ValueError, match="retained file coverage mismatch"):
        build_index(campaign_path, declarations_path, evidence)

    (evidence / "extra.bin").write_bytes(b"")
    with pytest.raises(ValueError, match="cannot be empty"):
        build_index(campaign_path, declarations_path, evidence)

    (evidence / "extra.bin").write_bytes(original)
    with pytest.raises(ValueError, match="multiple paths"):
        build_index(campaign_path, declarations_path, evidence)


def test_declaration_hash_binding_coverage_and_custody_are_enforced(tmp_path):
    campaign_path, _, evidence, _, expected = _package(tmp_path)
    declarations_path = _declarations(tmp_path, expected)
    original = load_strict_json(declarations_path)

    document = deepcopy(original)
    document["declarations_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="custody declarations SHA-256 mismatch"):
        build_index(campaign_path, _write_json(tmp_path / "bad-hash.json", document), evidence)

    document = deepcopy(original)
    document["campaign_sha256"] = "0" * 64
    _rehash_declarations(document)
    with pytest.raises(ValueError, match="campaign identity mismatch"):
        build_index(campaign_path, _write_json(tmp_path / "bad-binding.json", document), evidence)

    document = deepcopy(original)
    document["declarations"].pop()
    _rehash_declarations(document)
    with pytest.raises(ValueError, match="declaration coverage mismatch"):
        build_index(campaign_path, _write_json(tmp_path / "missing.json", document), evidence)

    document = deepcopy(original)
    document["declarations"][0]["custody"] = "AUTHORIZATION_RECORD"
    _rehash_declarations(document)
    with pytest.raises(ValueError, match="artifact custody mismatch"):
        build_index(campaign_path, _write_json(tmp_path / "wrong-custody.json", document), evidence)


def test_duplicate_declarations_and_campaign_tampering_are_rejected(tmp_path):
    campaign_path, _, evidence, campaign, expected = _package(tmp_path)
    declarations_path = _declarations(tmp_path, expected)
    document = load_strict_json(declarations_path)
    document["declarations"].append(deepcopy(document["declarations"][0]))
    _rehash_declarations(document)
    with pytest.raises(ValueError, match="duplicate custody declaration"):
        build_index(campaign_path, _write_json(tmp_path / "duplicate.json", document), evidence)

    campaign["campaign_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="campaign SHA-256 mismatch"):
        build_index(
            _write_json(tmp_path / "tampered-campaign.json", campaign),
            declarations_path,
            evidence,
        )


def test_symlinked_content_and_inputs_are_rejected(tmp_path):
    campaign_path, _, evidence, _, expected = _package(tmp_path)
    declarations_path = _declarations(tmp_path, expected)
    target = evidence / expected["entries"][0]["relative_path"]
    link = evidence / "linked.bin"
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ValueError, match="cannot contain a symlink"):
        build_index(campaign_path, declarations_path, evidence)

    link.unlink()
    campaign_link = tmp_path / "campaign-link.json"
    os.symlink(campaign_path, campaign_link)
    with pytest.raises(ValueError, match="campaign cannot be a symlink"):
        build_index(campaign_link, declarations_path, evidence)


def test_cli_rejects_output_inside_evidence_root(tmp_path):
    campaign_path, _, evidence, _, expected = _package(tmp_path)
    declarations_path = _declarations(tmp_path, expected)
    from eval.build_parked_pose_evidence_index import main

    previous = sys.argv
    sys.argv = [
        "build_parked_pose_evidence_index.py",
        "--campaign", str(campaign_path),
        "--custody-declarations", str(declarations_path),
        "--evidence-root", str(evidence),
        "--output", str(evidence / "index.json"),
    ]
    try:
        with pytest.raises(SystemExit, match="2"):
            main()
    finally:
        sys.argv = previous
