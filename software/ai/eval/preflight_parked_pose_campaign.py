"""Authenticate a retained parked-pose campaign package without using hardware."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.evaluate_parked_pose_qualification import (  # noqa: E402
    CAMPAIGN_SCHEMA,
    canonical_hash,
    load_strict_json,
)


INDEX_SCHEMA = AI_ROOT / "schemas" / "parked_pose_evidence_index_v1.schema.json"
RECEIPT_SCHEMA = AI_ROOT / "schemas" / "parked_pose_preflight_receipt_v1.schema.json"


TOP_LEVEL_TYPES = {
    "park_pose_identity_sha256": "PARK_POSE_IDENTITY",
    "camera_calibration_sha256": "CAMERA_CALIBRATION",
    "camera_to_board_sha256": "CAMERA_TO_BOARD",
    "robot_visual_mesh_sha256": "ROBOT_VISUAL_MESH",
    "target_catalog_sha256": "TARGET_CATALOG",
    "projection_qualification_sha256": "PROJECTION_QUALIFICATION",
    "residual_model_sha256": "RESIDUAL_MODEL",
    "fusion_policy_sha256": "FUSION_POLICY",
    "repeatability_qualification_sha256": "REPEATABILITY_QUALIFICATION",
    "charuco_drift_qualification_sha256": "CHARUCO_DRIFT_QUALIFICATION",
}
SYNTHETIC_TYPES = {
    "image_sha256": "SYNTHETIC_IMAGE",
    "runtime_like_projection_sha256": "RUNTIME_LIKE_PROJECTION",
    "truth_mask_label_sha256": "TRUTH_MASK_LABEL",
}
PHYSICAL_TYPES = {
    "image_sha256": "PHYSICAL_IMAGE",
    "exposure_binding_sha256": "EXPOSURE_BINDING",
    "measured_feedback_bracket_sha256": "MEASURED_FEEDBACK_BRACKET",
    "projection_evidence_sha256": "PROJECTION_EVIDENCE",
    "residual_observation_sha256": "RESIDUAL_OBSERVATION",
    "charuco_capture_sha256": "CHARUCO_CAPTURE",
    "park_repeatability_evidence_sha256": "PARK_REPEATABILITY_EVIDENCE",
    "charuco_drift_evidence_sha256": "CHARUCO_DRIFT_EVIDENCE",
}
TYPE_CUSTODY = {
    **{value: "REVIEWED_CONFIGURATION" for value in TOP_LEVEL_TYPES.values()},
    "RESIDUAL_MODEL": "REVIEWED_SOFTWARE_ARTIFACT",
    **{value: "SYNTHETIC_RETAINED" for value in SYNTHETIC_TYPES.values()},
    **{value: "PHYSICAL_RETAINED_ORIGINAL" for value in PHYSICAL_TYPES.values()},
    "COLLECTION_AUTHORIZATION": "AUTHORIZATION_RECORD",
    "CUSTODY_REVIEW": "AUTHORIZATION_RECORD",
}


def _validate(document: dict[str, Any], schema_path: Path, label: str) -> None:
    errors = sorted(
        Draft202012Validator(load_strict_json(schema_path)).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        where = ".".join(str(item) for item in first.absolute_path) or "$"
        raise ValueError(f"{label} schema validation failed at {where}: {first.message}")


def _add_required(result: dict[str, str], digest: str, artifact_type: str) -> None:
    previous = result.get(digest)
    if previous is not None and previous != artifact_type:
        raise ValueError(f"one digest is reused across artifact types: {previous}/{artifact_type}")
    result[digest] = artifact_type


def required_artifacts(campaign: dict[str, Any], custody_review_sha256: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for field, artifact_type in TOP_LEVEL_TYPES.items():
        _add_required(result, campaign[field], artifact_type)
    authorization = campaign["collection_effects"]["authorization_evidence_sha256"]
    if authorization is not None:
        _add_required(result, authorization, "COLLECTION_AUTHORIZATION")
    _add_required(result, custody_review_sha256, "CUSTODY_REVIEW")
    for row in campaign["synthetic_observations"]:
        for field, artifact_type in SYNTHETIC_TYPES.items():
            _add_required(result, row[field], artifact_type)
    for row in campaign["physical_cycles"]:
        for field, artifact_type in PHYSICAL_TYPES.items():
            _add_required(result, row[field], artifact_type)
    return result


def _resolve(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"evidence path must be relative and contained: {relative}")
    if root.is_symlink():
        raise ValueError("evidence root cannot be a symlink")
    root = root.resolve(strict=True)
    unresolved = root
    for part in candidate.parts:
        unresolved /= part
        if unresolved.is_symlink():
            raise ValueError(f"evidence path cannot contain a symlink: {relative}")
    resolved = unresolved.resolve(strict=True)
    if root not in resolved.parents or not resolved.is_file():
        raise ValueError(f"evidence path is not a contained regular file: {relative}")
    return resolved


def _sha256_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(stream.fileno())
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"artifact changed during hashing: {path.name}")
    return digest.hexdigest(), after.st_size


def pending_receipt() -> dict[str, Any]:
    core = {
        "schema": "rocell.ai_parked_pose_preflight_receipt.v1",
        "scope": "READ_ONLY_FILE_INTEGRITY_ONLY",
        "status": "BLOCKED",
        "campaign_sha256": None,
        "evidence_index_sha256": None,
        "custody_review_sha256": None,
        "verified_artifact_count": 0,
        "verified_byte_count": 0,
        "verified_physical_original_count": 0,
        "verified_synthetic_count": 0,
        "blockers": ["campaign_package_not_retained"],
        "physical_deployment_qualified": False,
        "controller_authority": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "No parked-pose campaign package was supplied.",
            "File integrity and declared custody never prove physical originality or measurement truth.",
        ],
    }
    receipt = {**core, "receipt_sha256": canonical_hash(core)}
    _validate(receipt, RECEIPT_SCHEMA, "receipt")
    return receipt


def preflight(campaign_path: Path, index_path: Path, evidence_root: Path) -> dict[str, Any]:
    if campaign_path.is_symlink() or index_path.is_symlink():
        raise ValueError("campaign and evidence index must be retained regular files, not symlinks")
    campaign = load_strict_json(campaign_path)
    index = load_strict_json(index_path)
    _validate(campaign, CAMPAIGN_SCHEMA, "campaign")
    _validate(index, INDEX_SCHEMA, "evidence index")
    if canonical_hash({key: value for key, value in campaign.items() if key != "campaign_sha256"}) != campaign["campaign_sha256"]:
        raise ValueError("campaign SHA-256 mismatch")
    if canonical_hash({key: value for key, value in index.items() if key != "index_sha256"}) != index["index_sha256"]:
        raise ValueError("evidence index SHA-256 mismatch")
    if index["campaign_sha256"] != campaign["campaign_sha256"]:
        raise ValueError("evidence index campaign identity mismatch")
    if campaign["physical_cycles"] and campaign["collection_effects"]["authorization_evidence_sha256"] is None:
        raise ValueError("physical campaign requires collection authorization evidence")
    required = required_artifacts(campaign, index["custody_review_sha256"])
    entries: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for entry in index["entries"]:
        digest = entry["sha256"]
        if digest in entries:
            raise ValueError(f"duplicate evidence digest: {digest}")
        if entry["relative_path"] in paths:
            raise ValueError(f"duplicate evidence path: {entry['relative_path']}")
        entries[digest] = entry
        paths.add(entry["relative_path"])
    missing = sorted(set(required) - set(entries))
    extra = sorted(set(entries) - set(required))
    if missing or extra:
        raise ValueError(f"evidence coverage mismatch; missing={missing}; extra={extra}")
    verified_bytes = 0
    custody_counts = {"PHYSICAL_RETAINED_ORIGINAL": 0, "SYNTHETIC_RETAINED": 0}
    for digest, artifact_type in required.items():
        entry = entries[digest]
        if entry["artifact_type"] != artifact_type:
            raise ValueError(f"artifact type mismatch: {digest}")
        expected_custody = TYPE_CUSTODY[artifact_type]
        if entry["custody"] != expected_custody:
            raise ValueError(f"artifact custody mismatch: {digest}")
        path = _resolve(evidence_root, entry["relative_path"])
        actual_digest, size = _sha256_and_size(path)
        if size != entry["size_bytes"]:
            raise ValueError(f"artifact size mismatch: {digest}")
        if actual_digest != digest:
            raise ValueError(f"artifact SHA-256 mismatch: {digest}")
        verified_bytes += size
        if expected_custody in custody_counts:
            custody_counts[expected_custody] += 1
    core = {
        "schema": "rocell.ai_parked_pose_preflight_receipt.v1",
        "scope": "READ_ONLY_FILE_INTEGRITY_ONLY",
        "status": "PASS_FILE_INTEGRITY_ONLY",
        "campaign_sha256": campaign["campaign_sha256"],
        "evidence_index_sha256": index["index_sha256"],
        "custody_review_sha256": index["custody_review_sha256"],
        "verified_artifact_count": len(entries),
        "verified_byte_count": verified_bytes,
        "verified_physical_original_count": custody_counts["PHYSICAL_RETAINED_ORIGINAL"],
        "verified_synthetic_count": custody_counts["SYNTHETIC_RETAINED"],
        "blockers": [],
        "physical_deployment_qualified": False,
        "controller_authority": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "PASS authenticates retained bytes and declared bindings only.",
            "Custody labels and review bytes require independent owner authentication.",
            "The receipt does not evaluate model behavior, measurement truth, deployment readiness, or physical safety.",
        ],
    }
    receipt = {**core, "receipt_sha256": canonical_hash(core)}
    _validate(receipt, RECEIPT_SCHEMA, "receipt")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    supplied = (args.campaign is not None, args.index is not None, args.evidence_root is not None)
    if any(supplied) and not all(supplied):
        parser.error("--campaign, --index, and --evidence-root must be supplied together")
    receipt = (
        preflight(args.campaign, args.index, args.evidence_root)
        if all(supplied) else pending_receipt()
    )
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(rendered.encode("utf-8"))
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
