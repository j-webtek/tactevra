from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

import jsonschema
import pytest


AI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI))

from eval.preflight_parked_pose_campaign import (  # noqa: E402
    INDEX_SCHEMA,
    PHYSICAL_TYPES,
    RECEIPT_SCHEMA,
    SYNTHETIC_TYPES,
    TOP_LEVEL_TYPES,
    TYPE_CUSTODY,
    canonical_hash,
    load_strict_json,
    pending_receipt,
    preflight,
)
from test_parked_pose_qualification import _campaign  # noqa: E402


def _write_json(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _package(root: Path):
    evidence = root / "evidence"
    evidence.mkdir(parents=True)
    campaign = _campaign()
    records: dict[str, tuple[str, int, str]] = {}
    counter = 0

    def retain(artifact_type: str, context: str) -> str:
        nonlocal counter
        payload = f"retained:{artifact_type}:{context}".encode()
        digest = hashlib.sha256(payload).hexdigest()
        relative = f"artifacts/{counter:04d}.bin"
        path = evidence / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(payload)
        records[digest] = (relative, len(payload), artifact_type)
        counter += 1
        return digest

    for field, artifact_type in TOP_LEVEL_TYPES.items():
        campaign[field] = retain(artifact_type, field)
    campaign["collection_effects"]["authorization_evidence_sha256"] = retain(
        "COLLECTION_AUTHORIZATION", "authorization"
    )
    for row in campaign["synthetic_observations"]:
        for field, artifact_type in SYNTHETIC_TYPES.items():
            row[field] = retain(artifact_type, f"{row['observation_id']}:{field}")
    for row in campaign["physical_cycles"]:
        for field, artifact_type in PHYSICAL_TYPES.items():
            row[field] = retain(artifact_type, f"{row['observation_id']}:{field}")
    custody_review = retain("CUSTODY_REVIEW", "owner-review")
    campaign["campaign_sha256"] = canonical_hash(
        {key: value for key, value in campaign.items() if key != "campaign_sha256"}
    )
    entries = [
        {
            "sha256": digest, "relative_path": record[0], "size_bytes": record[1],
            "artifact_type": record[2], "custody": TYPE_CUSTODY[record[2]],
        }
        for digest, record in sorted(records.items())
    ]
    index_core = {
        "schema": "rocell.ai_parked_pose_evidence_index.v1",
        "scope": "READ_ONLY_RETAINED_EVIDENCE_INDEX",
        "campaign_sha256": campaign["campaign_sha256"],
        "custody_review_sha256": custody_review,
        "entries": entries,
    }
    index = {**index_core, "index_sha256": canonical_hash(index_core)}
    return (
        _write_json(root / "campaign.json", campaign),
        _write_json(root / "index.json", index), evidence, campaign, index,
    )


def _rehash_index(index: dict) -> None:
    index["index_sha256"] = canonical_hash(
        {key: value for key, value in index.items() if key != "index_sha256"}
    )


def test_schemas_and_pending_receipt_are_strict():
    for path in (INDEX_SCHEMA, RECEIPT_SCHEMA):
        jsonschema.Draft202012Validator.check_schema(load_strict_json(path))
    receipt = pending_receipt()
    assert receipt["status"] == "BLOCKED"
    assert receipt["blockers"] == ["campaign_package_not_retained"]
    assert receipt["campaign_sha256"] is None
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_complete_package_passes_file_integrity_only(tmp_path):
    campaign_path, index_path, evidence, _, _ = _package(tmp_path)
    receipt = preflight(campaign_path, index_path, evidence)
    assert receipt["status"] == "PASS_FILE_INTEGRITY_ONLY"
    assert receipt["verified_artifact_count"] == 270
    assert receipt["verified_physical_original_count"] == 240
    assert receipt["verified_synthetic_count"] == 18
    assert receipt["blockers"] == []
    assert receipt["physical_deployment_qualified"] is False
    assert receipt["controller_authority"] is False


def test_altered_missing_and_extra_artifacts_are_rejected(tmp_path):
    campaign_path, index_path, evidence, _, index = _package(tmp_path)
    first = index["entries"][0]
    path = evidence / first["relative_path"]
    original = path.read_bytes()
    path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    with pytest.raises(ValueError, match="artifact SHA-256 mismatch"):
        preflight(campaign_path, index_path, evidence)

    path.unlink()
    with pytest.raises(FileNotFoundError):
        preflight(campaign_path, index_path, evidence)

    campaign_path, _, evidence, _, index = _package(tmp_path / "extra")
    extra = evidence / "extra.bin"
    extra.write_bytes(b"extra")
    digest = hashlib.sha256(b"extra").hexdigest()
    index["entries"].append({
        "sha256": digest, "relative_path": "extra.bin", "size_bytes": 5,
        "artifact_type": "SYNTHETIC_IMAGE", "custody": "SYNTHETIC_RETAINED",
    })
    _rehash_index(index)
    with pytest.raises(ValueError, match="evidence coverage mismatch"):
        preflight(campaign_path, _write_json(tmp_path / "extra-index.json", index), evidence)


def test_duplicate_digest_path_and_wrong_metadata_are_rejected(tmp_path):
    campaign_path, _, evidence, _, original = _package(tmp_path)
    index = deepcopy(original)
    index["entries"].append(deepcopy(index["entries"][0]))
    _rehash_index(index)
    with pytest.raises(ValueError, match="duplicate evidence digest"):
        preflight(campaign_path, _write_json(tmp_path / "duplicate-digest.json", index), evidence)

    index = deepcopy(original)
    index["entries"][1]["relative_path"] = index["entries"][0]["relative_path"]
    _rehash_index(index)
    with pytest.raises(ValueError, match="duplicate evidence path"):
        preflight(campaign_path, _write_json(tmp_path / "duplicate-path.json", index), evidence)

    for field, value, message in (
        ("artifact_type", "SYNTHETIC_IMAGE", "artifact type mismatch"),
        ("custody", "AUTHORIZATION_RECORD", "artifact custody mismatch"),
    ):
        index = deepcopy(original)
        entry = next(item for item in index["entries"] if item[field] != value)
        entry[field] = value
        _rehash_index(index)
        with pytest.raises(ValueError, match=message):
            preflight(campaign_path, _write_json(tmp_path / f"wrong-{field}.json", index), evidence)


def test_traversal_symlink_and_index_tampering_are_rejected(tmp_path):
    campaign_path, _, evidence, _, original = _package(tmp_path)
    index = deepcopy(original)
    index["entries"][0]["relative_path"] = "../escape.bin"
    _rehash_index(index)
    with pytest.raises(ValueError, match="relative and contained"):
        preflight(campaign_path, _write_json(tmp_path / "traversal.json", index), evidence)

    index = deepcopy(original)
    index["index_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="evidence index SHA-256 mismatch"):
        preflight(campaign_path, _write_json(tmp_path / "tampered-index.json", index), evidence)

    index = deepcopy(original)
    entry = index["entries"][0]
    target = evidence / entry["relative_path"]
    link = evidence / "link.bin"
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    entry["relative_path"] = "link.bin"
    _rehash_index(index)
    with pytest.raises(ValueError, match="cannot contain a symlink"):
        preflight(campaign_path, _write_json(tmp_path / "symlink.json", index), evidence)


def test_campaign_identity_and_index_binding_are_enforced(tmp_path):
    campaign_path, index_path, evidence, campaign, _ = _package(tmp_path)
    campaign["campaign_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="campaign SHA-256 mismatch"):
        preflight(_write_json(tmp_path / "tampered-campaign.json", campaign), index_path, evidence)

    campaign_path, _, evidence, _, index = _package(tmp_path / "binding")
    index["campaign_sha256"] = "0" * 64
    _rehash_index(index)
    with pytest.raises(ValueError, match="campaign identity mismatch"):
        preflight(campaign_path, _write_json(tmp_path / "wrong-binding.json", index), evidence)
