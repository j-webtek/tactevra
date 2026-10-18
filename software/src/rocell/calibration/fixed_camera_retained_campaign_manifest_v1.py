"""Compile one retained fixed-camera campaign from an exact file manifest.

The manifest is an offline handoff boundary.  It resolves only bounded relative
paths below its own directory, verifies every retained file by SHA-256, rebuilds
the complete typed planar tag map, invokes the existing retained campaign
compiler, and produces the existing deterministic independent-review packet.
It has no camera, robot, serial, motion, contact, or release capability.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from rocell.geometry import Point3Mm
from rocell.vision.detections import TagReference
from rocell.vision.planar_pose_estimator import (
    TAG_MAP_CORNER_ORDER,
    PlanarBoardTag,
    PlanarBoardTagMap,
)

from .fixed_camera_campaign_review_packet_v1 import (
    FixedCameraCampaignReviewPacketResultV1,
    build_fixed_camera_campaign_review_packet_v1,
)
from .fixed_camera_retained_campaign_v1 import (
    RetainedFixedCameraCalibrationCampaignV1,
    RetainedFixedCameraObservationSourceV1,
    compile_retained_fixed_camera_calibration_campaign_v1,
)


SCHEMA = "rocell.fixed_camera_retained_campaign_manifest.v1"
STATUS = "RETAINED_CAMPAIGN_FILES_DECLARED"
MAX_MANIFEST_BYTES = 256 * 1024
MAX_TAG_MAP_BYTES = 256 * 1024
_ROOT_FIELDS = frozenset(
    {"schema", "status", "producer_id", "tag_map", "captures", "authority"}
)
_PIN_FIELDS = frozenset({"path", "expected_file_sha256"})
_CAPTURE_FIELDS = frozenset(
    {
        "role",
        "bracket_record",
        "jpeg",
        "intrinsics_record",
        "tag_evidence",
        "bare_jaw_calibration",
        "bare_jaw_landmark_evidence",
    }
)
_AUTHORITY_FIELDS = frozenset(
    {
        "camera_opened",
        "robot_provider_called",
        "controller_commands",
        "motion_targets_emitted",
        "motion_authorized",
        "contact_authorized",
        "physical_release_effect",
    }
)
_TAG_MAP_FIELDS = frozenset(
    {
        "schema",
        "map_id",
        "board_frame",
        "tag_plane_z_board_mm",
        "corner_order",
        "tags",
        "source_sha256",
        "physical_release_effect",
    }
)
_TAG_FIELDS = frozenset({"tag", "corner_order", "corners_board_mm"})
_REFERENCE_FIELDS = frozenset({"family", "id"})
_POINT_FIELDS = frozenset({"frame", "x", "y", "z"})


class FixedCameraRetainedCampaignManifestError(ValueError):
    """The retained campaign manifest or one of its file pins is invalid."""


def _pairs(items: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise FixedCameraRetainedCampaignManifestError(
                f"JSON contains duplicate field {key!r}"
            )
        result[key] = value
    return result


def _strict_json(payload: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                FixedCameraRetainedCampaignManifestError(
                    f"{label} contains non-finite value {item}"
                )
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FixedCameraRetainedCampaignManifestError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise FixedCameraRetainedCampaignManifestError(f"{label} must be an object")
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FixedCameraRetainedCampaignManifestError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != fields:
        raise FixedCameraRetainedCampaignManifestError(
            f"{label} fields differ; missing={sorted(fields - actual)}, "
            f"unknown={sorted(actual - fields)}"
        )


def _text(value: object, label: str, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise FixedCameraRetainedCampaignManifestError(
            f"{label} must be bounded, trimmed, non-empty text"
        )
    return value


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FixedCameraRetainedCampaignManifestError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _file_bytes(path: Path, expected: str, maximum: int, label: str) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise FixedCameraRetainedCampaignManifestError(
            f"cannot read {label}: {exc}"
        ) from exc
    if not payload or len(payload) > maximum:
        raise FixedCameraRetainedCampaignManifestError(
            f"{label} must be 1..{maximum} bytes"
        )
    if hashlib.sha256(payload).hexdigest() != expected:
        raise FixedCameraRetainedCampaignManifestError(
            f"{label} bytes differ from expected_file_sha256"
        )
    return payload


def _relative_file(root: Path, value: object, label: str) -> Path:
    text = _text(value, label, 1024)
    pure = PurePosixPath(text)
    if pure.is_absolute() or not pure.parts or any(part in ("", ".", "..") for part in pure.parts):
        raise FixedCameraRetainedCampaignManifestError(
            f"{label} must be a normalized relative POSIX path"
        )
    candidate = root.joinpath(*pure.parts).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise FixedCameraRetainedCampaignManifestError(
            f"{label} escapes the manifest directory"
        ) from exc
    if not candidate.is_file():
        raise FixedCameraRetainedCampaignManifestError(f"{label} is not a file")
    return candidate


def _pin(root: Path, value: object, label: str) -> tuple[Path, str]:
    record = _mapping(value, label)
    _exact(record, _PIN_FIELDS, label)
    return (
        _relative_file(root, record.get("path"), f"{label}.path"),
        _digest(record.get("expected_file_sha256"), f"{label}.expected_file_sha256"),
    )


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FixedCameraRetainedCampaignManifestError(f"{label} must be a number")
    result = float(value)
    if not (-1_000_000.0 <= result <= 1_000_000.0):
        raise FixedCameraRetainedCampaignManifestError(f"{label} is out of bounds")
    return result


def _tag_map(value: Mapping[str, Any]) -> PlanarBoardTagMap:
    _exact(value, _TAG_MAP_FIELDS, "tag map")
    if (
        value.get("schema") != "rocell.planar_apriltag_board_map.v1"
        or value.get("corner_order") != TAG_MAP_CORNER_ORDER
        or value.get("physical_release_effect") != "NONE"
    ):
        raise FixedCameraRetainedCampaignManifestError("tag map meaning differs")
    tags_value = value.get("tags")
    if not isinstance(tags_value, list) or not tags_value:
        raise FixedCameraRetainedCampaignManifestError("tag map tags must be non-empty")
    tags: list[PlanarBoardTag] = []
    for index, item in enumerate(tags_value):
        tag = _mapping(item, f"tag map tags[{index}]")
        _exact(tag, _TAG_FIELDS, f"tag map tags[{index}]")
        if tag.get("corner_order") != TAG_MAP_CORNER_ORDER:
            raise FixedCameraRetainedCampaignManifestError("tag corner order differs")
        reference = _mapping(tag.get("tag"), f"tag map tags[{index}].tag")
        _exact(reference, _REFERENCE_FIELDS, f"tag map tags[{index}].tag")
        points_value = tag.get("corners_board_mm")
        if not isinstance(points_value, list) or len(points_value) != 4:
            raise FixedCameraRetainedCampaignManifestError(
                "each tag must contain exactly four board corners"
            )
        points: list[Point3Mm] = []
        for point_index, point_value in enumerate(points_value):
            point = _mapping(
                point_value, f"tag map tags[{index}].corners[{point_index}]"
            )
            _exact(point, _POINT_FIELDS, "tag map point")
            points.append(
                Point3Mm(
                    _text(point.get("frame"), "tag map point.frame"),
                    _number(point.get("x"), "tag map point.x"),
                    _number(point.get("y"), "tag map point.y"),
                    _number(point.get("z"), "tag map point.z"),
                )
            )
        tag_id = reference.get("id")
        if isinstance(tag_id, bool) or not isinstance(tag_id, int):
            raise FixedCameraRetainedCampaignManifestError("tag_id must be an integer")
        tags.append(
            PlanarBoardTag(
                TagReference(_text(reference.get("family"), "tag family"), tag_id),
                tuple(points),  # type: ignore[arg-type]
            )
        )
    return PlanarBoardTagMap(
        map_id=_text(value.get("map_id"), "tag map map_id"),
        board_frame=_text(value.get("board_frame"), "tag map board_frame"),
        tag_plane_z_board_mm=_number(
            value.get("tag_plane_z_board_mm"), "tag map tag_plane_z_board_mm"
        ),
        tags=tuple(tags),
        source_sha256=_digest(value.get("source_sha256"), "tag map source_sha256"),
    )


@dataclass(frozen=True, slots=True)
class FixedCameraRetainedCampaignManifestResultV1:
    """Offline compiled campaign and deterministic review packet."""

    manifest_path: Path
    manifest_file_sha256: str
    tag_map_path: Path
    tag_map_file_sha256: str
    campaign: RetainedFixedCameraCalibrationCampaignV1
    review_packet: FixedCameraCampaignReviewPacketResultV1

    def receipt(self) -> dict[str, object]:
        return {
            "schema": "rocell.fixed_camera_retained_campaign_manifest_receipt.v1",
            "status": "RETAINED_CAMPAIGN_AND_REVIEW_PACKET_COMPILED",
            "manifest_file_sha256": self.manifest_file_sha256,
            "tag_map_file_sha256": self.tag_map_file_sha256,
            "campaign_receipt_sha256": self.campaign.sha256,
            "review_packet_sha256": self.review_packet.packet_sha256,
            "authority": {
                "camera_opened": False,
                "robot_provider_called": False,
                "controller_commands": [],
                "motion_targets_emitted": False,
                "motion_authorized": False,
                "contact_authorized": False,
                "physical_release_effect": "NONE",
            },
        }


def compile_fixed_camera_retained_campaign_manifest_v1(
    path: str | Path, *, expected_file_sha256: str
) -> FixedCameraRetainedCampaignManifestResultV1:
    """Compile exact retained files and create an independent-review packet."""

    expected = _digest(expected_file_sha256, "expected_file_sha256")
    manifest_path = Path(path).resolve()
    payload = _file_bytes(manifest_path, expected, MAX_MANIFEST_BYTES, "manifest")
    manifest = _strict_json(payload, "manifest")
    _exact(manifest, _ROOT_FIELDS, "manifest")
    if manifest.get("schema") != SCHEMA or manifest.get("status") != STATUS:
        raise FixedCameraRetainedCampaignManifestError("manifest meaning differs")
    producer_id = _text(manifest.get("producer_id"), "producer_id")

    authority = _mapping(manifest.get("authority"), "authority")
    _exact(authority, _AUTHORITY_FIELDS, "authority")
    if authority != {
        "camera_opened": False,
        "robot_provider_called": False,
        "controller_commands": [],
        "motion_targets_emitted": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "physical_release_effect": "NONE",
    }:
        raise FixedCameraRetainedCampaignManifestError(
            "manifest authority must remain exactly zero"
        )

    root = manifest_path.parent.resolve()
    tag_map_path, tag_map_hash = _pin(root, manifest.get("tag_map"), "tag_map")
    tag_map_payload = _file_bytes(
        tag_map_path, tag_map_hash, MAX_TAG_MAP_BYTES, "tag map"
    )
    typed_tag_map = _tag_map(_strict_json(tag_map_payload, "tag map"))

    captures = manifest.get("captures")
    if not isinstance(captures, list) or not 1 <= len(captures) <= 64:
        raise FixedCameraRetainedCampaignManifestError(
            "captures must contain 1 to 64 entries"
        )
    sources: list[RetainedFixedCameraObservationSourceV1] = []
    for index, item in enumerate(captures):
        capture = _mapping(item, f"captures[{index}]")
        _exact(capture, _CAPTURE_FIELDS, f"captures[{index}]")
        pins = {
            name: _pin(root, capture.get(name), f"captures[{index}].{name}")
            for name in _CAPTURE_FIELDS
            if name != "role"
        }
        sources.append(
            RetainedFixedCameraObservationSourceV1(
                bracket_record_path=pins["bracket_record"][0],
                jpeg_path=pins["jpeg"][0],
                intrinsics_record_path=pins["intrinsics_record"][0],
                tag_evidence_path=pins["tag_evidence"][0],
                bare_jaw_calibration_path=pins["bare_jaw_calibration"][0],
                bare_jaw_landmark_evidence_path=pins[
                    "bare_jaw_landmark_evidence"
                ][0],
                expected_bracket_record_file_sha256=pins["bracket_record"][1],
                expected_jpeg_file_sha256=pins["jpeg"][1],
                expected_intrinsics_file_sha256=pins["intrinsics_record"][1],
                expected_tag_evidence_file_sha256=pins["tag_evidence"][1],
                expected_bare_jaw_calibration_file_sha256=pins[
                    "bare_jaw_calibration"
                ][1],
                expected_bare_jaw_landmark_evidence_file_sha256=pins[
                    "bare_jaw_landmark_evidence"
                ][1],
                role=_text(capture.get("role"), f"captures[{index}].role"),
            )
        )
    campaign = compile_retained_fixed_camera_calibration_campaign_v1(
        sources, tag_map=typed_tag_map
    )
    packet = build_fixed_camera_campaign_review_packet_v1(
        campaign, producer_id=producer_id
    )
    return FixedCameraRetainedCampaignManifestResultV1(
        manifest_path=manifest_path,
        manifest_file_sha256=expected,
        tag_map_path=tag_map_path,
        tag_map_file_sha256=tag_map_hash,
        campaign=campaign,
        review_packet=packet,
    )


__all__ = [
    "MAX_MANIFEST_BYTES",
    "MAX_TAG_MAP_BYTES",
    "SCHEMA",
    "STATUS",
    "FixedCameraRetainedCampaignManifestError",
    "FixedCameraRetainedCampaignManifestResultV1",
    "compile_fixed_camera_retained_campaign_manifest_v1",
]
