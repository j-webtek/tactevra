"""Independently review one retained ARM-294 zero-motion receipt.

This reviewer never imports or starts Isaac.  It accepts only the exact
seven-link success receipt, rebinds it to the reviewed ARM-292/ARM-293
lineage, verifies that the future route-attempt directory is still absent,
and emits an inert review document.  Acceptance permits preparation of a new
route-physics lineage; it does not admit an attempt, motion, or hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


REQUEST_SCHEMA = "tactevra.isaac_lm4_native_link_inventory_request.v1"
REQUEST_STATUS = "READY_FOR_INDEPENDENT_NATIVE_LINK_INVENTORY_REVIEW"
ARM293_SCHEMA = "tactevra.isaac_lm4_native_link_inventory_review.v1"
ARM293_STATUS = "ACCEPTED_FOR_EXACT_ARM294_ZERO_MOTION_AUTHORIZATION"
RECEIPT_SCHEMA = "tactevra.isaac_lm4_native_link_inventory_receipt.v1"
RECEIPT_STATUS = "PASS_NATIVE_LINK_INVENTORY_ZERO_MOTION"
REVIEW_SCHEMA = "tactevra.isaac_lm4_native_link_inventory_receipt_review.v1"
EXPECTED_LINK_NAMES = (
    "base_link",
    "link1",
    "link2",
    "link3",
    "link4",
    "link5",
    "gripper_link",
)
ZERO_AUTHORITY = {
    "attempt_consumed": False,
    "worker_invoked": False,
    "backend_invoked": False,
    "timeline_played": False,
    "physics_steps": 0,
    "trajectory_playback": False,
    "joint_positions_submitted": False,
    "joint_targets_submitted": False,
    "key_contact": False,
    "automatic_retry": False,
    "hardware_access": False,
    "hardware_writes": 0,
    "physical_authority": False,
    "physical_movements": 0,
    "controller_commands": [],
    "wire_commands": [],
    "gate_promotions": [],
}
EXPECTED_RECEIPT_KEYS = {
    "schema",
    "status",
    "diagnostic_id",
    "source_request_sha256",
    "source_review_sha256",
    "source_files_sha256",
    "link_names",
    "link_count",
    "transform_batch_count",
    "transform_count",
    "governed_attempt_directory",
    "governed_attempt_directory_created",
    "isaac_started",
    *ZERO_AUTHORITY,
}


class NativeLinkInventoryReceiptReviewError(ValueError):
    """Raised when retained ARM-294 evidence is incomplete or has drifted."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NativeLinkInventoryReceiptReviewError(
            "review input is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeLinkInventoryReceiptReviewError(f"{label} hash changed")
    return claimed


def _digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _has_zero_authority(document: Mapping[str, Any]) -> bool:
    return all(document.get(key) == value for key, value in ZERO_AUTHORITY.items())


def review_receipt(
    receipt: Mapping[str, Any],
    request: Mapping[str, Any],
    arm293_review: Mapping[str, Any],
    *,
    receipt_file_sha256: str,
    request_file_sha256: str,
    arm293_review_file_sha256: str,
    receipt_path: Path,
    governed_attempt_directory: Path,
    reviewer_source_sha256: str,
) -> dict[str, Any]:
    """Verify retained evidence without starting Isaac or claiming ARM-295."""

    request_hash = _require_hash(request, "request_sha256", "ARM-292 request")
    arm293_hash = _require_hash(arm293_review, "review_sha256", "ARM-293 review")
    digests = (
        receipt_file_sha256,
        request_file_sha256,
        arm293_review_file_sha256,
        reviewer_source_sha256,
    )
    if not all(_digest(value) for value in digests):
        raise NativeLinkInventoryReceiptReviewError("review source digest changed")

    proposed_output = Path(str(request.get("proposed_output_directory", "")))
    requested_sources = request.get("source_files_sha256")
    if (
        request.get("schema") != REQUEST_SCHEMA
        or request.get("request_id") != "arm292-native-link-inventory-request-001"
        or request.get("status") != REQUEST_STATUS
        or request.get("runtime_action_id") != "ARM-294"
        or request.get("expected_link_names") != list(EXPECTED_LINK_NAMES)
        or request.get("expected_transform_count") != len(EXPECTED_LINK_NAMES)
        or request.get("output_must_be_absent") is not True
        or request.get("single_use_by_output_exclusivity") is not True
        or request.get("failure_retained_before_shutdown") is not True
        or not isinstance(requested_sources, Mapping)
        or set(requested_sources) != {"diagnostic_source", "session_source"}
        or not all(_digest(value) for value in requested_sources.values())
        or not _has_zero_authority(request)
    ):
        raise NativeLinkInventoryReceiptReviewError("ARM-292 request boundary changed")
    if (
        arm293_review.get("schema") != ARM293_SCHEMA
        or arm293_review.get("status") != ARM293_STATUS
        or arm293_review.get("source_request_sha256") != request_hash
        or arm293_review.get("source_request_file_sha256") != request_file_sha256
        or arm293_review.get("source_diagnostic_source_sha256")
        != requested_sources.get("diagnostic_source")
        or arm293_review.get("launch_admitted") is not True
        or not _has_zero_authority(arm293_review)
    ):
        raise NativeLinkInventoryReceiptReviewError("ARM-293 review boundary changed")

    resolved_receipt = receipt_path.resolve(strict=True)
    if (
        resolved_receipt.name != "receipt.json"
        or resolved_receipt.parent != proposed_output
    ):
        raise NativeLinkInventoryReceiptReviewError("ARM-294 receipt path changed")
    if _file_sha(resolved_receipt) != receipt_file_sha256:
        raise NativeLinkInventoryReceiptReviewError("ARM-294 receipt file hash changed")
    if governed_attempt_directory != Path(
        str(receipt.get("governed_attempt_directory", ""))
    ):
        raise NativeLinkInventoryReceiptReviewError(
            "governed route-attempt identity changed"
        )
    if governed_attempt_directory.exists():
        raise NativeLinkInventoryReceiptReviewError(
            "governed route-attempt directory already exists"
        )
    if (
        set(receipt) != EXPECTED_RECEIPT_KEYS
        or receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("status") != RECEIPT_STATUS
        or receipt.get("diagnostic_id") != proposed_output.name
        or receipt.get("source_request_sha256") != request_hash
        or receipt.get("source_review_sha256") != arm293_hash
        or receipt.get("source_files_sha256") != dict(requested_sources)
        or receipt.get("link_names") != list(EXPECTED_LINK_NAMES)
        or receipt.get("link_count") != len(EXPECTED_LINK_NAMES)
        or receipt.get("transform_batch_count") != 1
        or receipt.get("transform_count") != len(EXPECTED_LINK_NAMES)
        or receipt.get("governed_attempt_directory_created") is not False
        or receipt.get("isaac_started") is not True
        or not _has_zero_authority(receipt)
    ):
        raise NativeLinkInventoryReceiptReviewError(
            "ARM-294 zero-motion receipt boundary changed"
        )

    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm294-native-link-inventory-receipt-review-001",
        "status": "ACCEPTED_NATIVE_LINK_INVENTORY_ZERO_MOTION_EVIDENCE",
        "source_receipt_file_sha256": receipt_file_sha256,
        "source_request_file_sha256": request_file_sha256,
        "source_request_sha256": request_hash,
        "source_arm293_review_file_sha256": arm293_review_file_sha256,
        "source_arm293_review_sha256": arm293_hash,
        "reviewer_source_sha256": reviewer_source_sha256,
        "verified_link_names": list(EXPECTED_LINK_NAMES),
        "verified_link_count": len(EXPECTED_LINK_NAMES),
        "verified_transform_batch_count": 1,
        "verified_transform_count": len(EXPECTED_LINK_NAMES),
        "source_isaac_started": True,
        "source_physics_steps": 0,
        "governed_attempt_directory": str(governed_attempt_directory),
        "governed_attempt_directory_absent": True,
        "route_attempt_admitted": False,
        "launch_admitted": False,
        "isaac_started": False,
        **ZERO_AUTHORITY,
        "next_required_stage": (
            "REBUILD_NEWLY_NUMBERED_ROUTE_PHYSICS_LINEAGE_WITH_FRESH_GATES"
        ),
    }
    return {**core, "receipt_review_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeLinkInventoryReceiptReviewError(
            f"JSON document is not an object: {path}"
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--arm293-review", type=Path, required=True)
    parser.add_argument("--governed-attempt-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve()
    result = review_receipt(
        _load(args.receipt),
        _load(args.request),
        _load(args.arm293_review),
        receipt_file_sha256=_file_sha(args.receipt),
        request_file_sha256=_file_sha(args.request),
        arm293_review_file_sha256=_file_sha(args.arm293_review),
        receipt_path=args.receipt,
        governed_attempt_directory=args.governed_attempt_directory,
        reviewer_source_sha256=_file_sha(source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
