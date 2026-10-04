"""Immutable, zero-authority replay into existing camera consumer boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .camera_arrival_consumer_emitters_v1 import (
    CameraArrivalConsumerEmitterV1Error,
    emit_camera_campaign_consumer_receipt_v1,
    emit_camera_localization_consumer_receipt_v1,
)
from .camera_arrival_consumer_handoff_v1 import (
    parse_camera_arrival_consumer_handoff_v1,
)


MANIFEST_SCHEMA = "rocell.immutable_camera_replay_manifest.v1"
REPORT_SCHEMA = "rocell.immutable_camera_replay_report.v1"
REPLAY_EVIDENCE_CLASS = "IMMUTABLE_REPLAY"
SOURCE_EVIDENCE_CLASSES = {"ORIGINAL_CAPTURE", "SYNTHETIC_FIXTURE"}
MAX_CAPTURES = 64
MAX_IMAGE_BYTES = 128 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
_HASH = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_FIELDS = {
    "schema", "replay_id", "replay_evidence_class", "source_evidence_class",
    "handoff_sha256", "camera_profile_sha256", "support_profile_sha256",
    "model_sha256", "calibration_sha256", "validated_at_utc", "captures",
    "campaign_output", "localization_output", "expected_receipt_sha256",
    "live_camera_allowed", "qualification_installed", "controller_started",
    "controller_commands", "hardware_writes", "physical_movements",
    "physical_authority", "manifest_sha256",
}
_CAPTURE_FIELDS = {"capture_id", "image", "metadata"}
_FILE_FIELDS = {"relative_path", "size_bytes", "sha256"}
_METADATA_FIELDS = {
    "schema", "capture_id", "captured_at_utc", "source_evidence_class",
    "camera_profile_sha256", "support_profile_sha256", "calibration_sha256",
    "metadata_sha256",
}
_REPORT_FIELDS = {
    "schema", "replay_id", "manifest_sha256", "replay_evidence_class",
    "source_evidence_class", "capture_count", "verified_file_count",
    "receipt_sha256", "decision_status", "identical_replay_confirmed",
    "live_camera_opened", "qualification_installed", "controller_started",
    "controller_commands", "hardware_writes", "physical_movements",
    "physical_authority", "report_sha256",
}


class ImmutableCameraReplayV1Error(ValueError):
    """Frozen replay bytes, identities, outputs, or decisions differ."""


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise ImmutableCameraReplayV1Error(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ImmutableCameraReplayV1Error(f"non-finite JSON number: {value}")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ImmutableCameraReplayV1Error(f"{label} is not a SHA-256 digest")
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str) or not value.strip() or len(value) > 192
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:@/-"
               for character in value)
    ):
        raise ImmutableCameraReplayV1Error(f"{label} is invalid")
    return value


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    if not raw or len(raw) > MAX_JSON_BYTES:
        raise ImmutableCameraReplayV1Error(f"{label} size is outside its bound")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImmutableCameraReplayV1Error(f"{label} is not strict JSON") from exc
    if not isinstance(value, dict):
        raise ImmutableCameraReplayV1Error(f"{label} must be a JSON object")
    return value


def _contained_file(root: Path, relative: object, label: str) -> Path:
    if not isinstance(relative, str):
        raise ImmutableCameraReplayV1Error(f"{label} path is invalid")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ImmutableCameraReplayV1Error(f"{label} path is not contained")
    try:
        resolved_root = root.resolve(strict=True)
        resolved = (resolved_root / candidate).resolve(strict=True)
    except OSError as exc:
        raise ImmutableCameraReplayV1Error(f"{label} file is unavailable") from exc
    if resolved_root not in resolved.parents or not resolved.is_file():
        raise ImmutableCameraReplayV1Error(f"{label} is not a contained regular file")
    return resolved


def _file_binding(root: Path, relative: str, label: str, *, limit: int) -> dict[str, Any]:
    path = _contained_file(root, relative, label)
    raw = path.read_bytes()
    if not raw or len(raw) > limit:
        raise ImmutableCameraReplayV1Error(f"{label} size is outside its bound")
    return {
        "relative_path": relative.replace("\\", "/"),
        "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _read_binding(
    root: Path, binding: object, label: str, *, limit: int,
) -> bytes:
    if not isinstance(binding, Mapping) or set(binding) != _FILE_FIELDS:
        raise ImmutableCameraReplayV1Error(f"{label} binding fields differ")
    path = _contained_file(root, binding.get("relative_path"), label)
    raw = path.read_bytes()
    if (
        not raw or len(raw) > limit or binding.get("size_bytes") != len(raw)
        or hashlib.sha256(raw).hexdigest() != binding.get("sha256")
    ):
        raise ImmutableCameraReplayV1Error(f"{label} bytes differ")
    return raw


def _metadata(
    raw: bytes, capture_id: str, source_class: str,
    camera_profile_sha256: str, support_profile_sha256: str,
    calibration_sha256: str,
) -> dict[str, Any]:
    value = _strict_json(raw, f"capture {capture_id} metadata")
    if set(value) != _METADATA_FIELDS:
        raise ImmutableCameraReplayV1Error("capture metadata fields differ")
    unsigned = dict(value)
    digest = unsigned.pop("metadata_sha256")
    if not isinstance(digest, str) or _sha(unsigned) != digest:
        raise ImmutableCameraReplayV1Error("capture metadata hash mismatch")
    if (
        value.get("schema") != "rocell.immutable_camera_capture_metadata.v1"
        or value.get("capture_id") != capture_id
        or value.get("source_evidence_class") != source_class
        or value.get("camera_profile_sha256") != camera_profile_sha256
        or value.get("support_profile_sha256") != support_profile_sha256
        or value.get("calibration_sha256") != calibration_sha256
        or not isinstance(value.get("captured_at_utc"), str)
        or not value["captured_at_utc"].endswith("Z")
    ):
        raise ImmutableCameraReplayV1Error("capture metadata identity differs")
    return value


def _outputs(
    replay_root: Path, manifest: Mapping[str, Any], handoff: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    campaign = _strict_json(_read_binding(
        replay_root, manifest["campaign_output"], "campaign output",
        limit=MAX_JSON_BYTES,
    ), "campaign output")
    localization = _strict_json(_read_binding(
        replay_root, manifest["localization_output"], "localization output",
        limit=MAX_JSON_BYTES,
    ), "localization output")
    if localization.get("model_sha256") != manifest["model_sha256"]:
        raise ImmutableCameraReplayV1Error("localization model identity differs")
    try:
        campaign_receipt = emit_camera_campaign_consumer_receipt_v1(
            handoff, "localization_campaign", campaign,
            validated_at_utc=manifest["validated_at_utc"],
        )
        localization_receipt = emit_camera_localization_consumer_receipt_v1(
            handoff, "localization_evaluation", localization,
            validated_at_utc=manifest["validated_at_utc"],
        )
    except CameraArrivalConsumerEmitterV1Error as exc:
        raise ImmutableCameraReplayV1Error(str(exc)) from exc
    return campaign_receipt, localization_receipt


def build_immutable_camera_replay_manifest_v1(
    handoff: Mapping[str, Any], *, replay_root: Path, replay_id: str,
    source_evidence_class: str, camera_profile_sha256: str,
    support_profile_sha256: str, model_sha256: str, calibration_sha256: str,
    validated_at_utc: str, captures: Sequence[Mapping[str, str]],
    campaign_output_relative_path: str,
    localization_output_relative_path: str,
) -> dict[str, Any]:
    """Bind frozen files and the decisions of the existing consumer emitters."""

    verified_handoff = dict(parse_camera_arrival_consumer_handoff_v1(handoff))
    if source_evidence_class not in SOURCE_EVIDENCE_CLASSES:
        raise ImmutableCameraReplayV1Error("source evidence class differs")
    if not 1 <= len(captures) <= MAX_CAPTURES:
        raise ImmutableCameraReplayV1Error("capture count is outside its bound")
    normalized = []
    seen: set[str] = set()
    for index, row in enumerate(captures):
        if not isinstance(row, Mapping) or set(row) != {
            "capture_id", "image_relative_path", "metadata_relative_path"
        }:
            raise ImmutableCameraReplayV1Error(f"capture {index} fields differ")
        capture_id = _identifier(row["capture_id"], f"capture {index} id")
        if capture_id in seen:
            raise ImmutableCameraReplayV1Error("capture ids are not unique")
        seen.add(capture_id)
        image = _file_binding(
            replay_root, row["image_relative_path"], f"capture {capture_id} image",
            limit=MAX_IMAGE_BYTES,
        )
        metadata = _file_binding(
            replay_root, row["metadata_relative_path"],
            f"capture {capture_id} metadata", limit=MAX_JSON_BYTES,
        )
        normalized.append({"capture_id": capture_id, "image": image, "metadata": metadata})
    core = {
        "schema": MANIFEST_SCHEMA, "replay_id": _identifier(replay_id, "replay_id"),
        "replay_evidence_class": REPLAY_EVIDENCE_CLASS,
        "source_evidence_class": source_evidence_class,
        "handoff_sha256": verified_handoff["handoff_sha256"],
        "camera_profile_sha256": _digest(camera_profile_sha256, "camera profile"),
        "support_profile_sha256": _digest(support_profile_sha256, "support profile"),
        "model_sha256": _digest(model_sha256, "model"),
        "calibration_sha256": _digest(calibration_sha256, "calibration"),
        "validated_at_utc": validated_at_utc,
        "captures": normalized,
        "campaign_output": _file_binding(
            replay_root, campaign_output_relative_path, "campaign output",
            limit=MAX_JSON_BYTES,
        ),
        "localization_output": _file_binding(
            replay_root, localization_output_relative_path, "localization output",
            limit=MAX_JSON_BYTES,
        ),
        "expected_receipt_sha256": {},
        "live_camera_allowed": False, "qualification_installed": False,
        "controller_started": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    provisional = {**core, "manifest_sha256": "0" * 64}
    for row in normalized:
        raw = _read_binding(
            replay_root, row["metadata"], f"capture {row['capture_id']} metadata",
            limit=MAX_JSON_BYTES,
        )
        _metadata(
            raw, row["capture_id"], source_evidence_class,
            core["camera_profile_sha256"], core["support_profile_sha256"],
            core["calibration_sha256"],
        )
    campaign_receipt, localization_receipt = _outputs(
        replay_root, provisional, verified_handoff
    )
    core["expected_receipt_sha256"] = {
        "localization_campaign": campaign_receipt["receipt_sha256"],
        "localization_evaluation": localization_receipt["receipt_sha256"],
    }
    return {**core, "manifest_sha256": _sha(core)}


def parse_immutable_camera_replay_manifest_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _MANIFEST_FIELDS:
        raise ImmutableCameraReplayV1Error("replay manifest fields differ")
    unsigned = dict(value)
    digest = unsigned.pop("manifest_sha256")
    if not isinstance(digest, str) or _sha(unsigned) != digest:
        raise ImmutableCameraReplayV1Error("replay manifest hash mismatch")
    captures = value.get("captures")
    expected = value.get("expected_receipt_sha256")
    if (
        value.get("schema") != MANIFEST_SCHEMA
        or value.get("replay_evidence_class") != REPLAY_EVIDENCE_CLASS
        or value.get("source_evidence_class") not in SOURCE_EVIDENCE_CLASSES
        or not isinstance(captures, list) or not 1 <= len(captures) <= MAX_CAPTURES
        or len({row.get("capture_id") for row in captures if isinstance(row, Mapping)})
        != len(captures)
        or not isinstance(expected, Mapping)
        or set(expected) != {"localization_campaign", "localization_evaluation"}
        or any(not _HASH.fullmatch(item) for item in expected.values()
               if isinstance(item, str))
        or len(expected) != sum(isinstance(item, str) for item in expected.values())
        or any(value.get(field) is not False for field in (
            "live_camera_allowed", "qualification_installed", "controller_started",
            "physical_authority",
        ))
        or value.get("controller_commands") != []
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
    ):
        raise ImmutableCameraReplayV1Error("replay manifest semantics differ")
    _identifier(value.get("replay_id"), "replay_id")
    for field in (
        "handoff_sha256", "camera_profile_sha256", "support_profile_sha256",
        "model_sha256", "calibration_sha256",
    ):
        _digest(value.get(field), field)
    if not isinstance(value.get("validated_at_utc"), str) or not value["validated_at_utc"].endswith("Z"):
        raise ImmutableCameraReplayV1Error("validated_at_utc is invalid")
    for index, row in enumerate(captures):
        if not isinstance(row, Mapping) or set(row) != _CAPTURE_FIELDS:
            raise ImmutableCameraReplayV1Error(f"capture {index} fields differ")
        _identifier(row.get("capture_id"), f"capture {index} id")
        for name in ("image", "metadata"):
            binding = row.get(name)
            if (
                not isinstance(binding, Mapping) or set(binding) != _FILE_FIELDS
                or not isinstance(binding.get("relative_path"), str)
                or not isinstance(binding.get("size_bytes"), int)
                or binding["size_bytes"] <= 0
            ):
                raise ImmutableCameraReplayV1Error(f"capture {index} {name} differs")
            _digest(binding.get("sha256"), f"capture {index} {name}")
    for name in ("campaign_output", "localization_output"):
        binding = value.get(name)
        if not isinstance(binding, Mapping) or set(binding) != _FILE_FIELDS:
            raise ImmutableCameraReplayV1Error(f"{name} binding differs")
        _digest(binding.get("sha256"), name)
    return MappingProxyType(dict(value))


def run_immutable_camera_replay_v1(
    manifest: Mapping[str, Any], *, replay_root: Path,
    handoff: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify frozen bytes and reproduce both existing consumer decisions."""

    verified = dict(parse_immutable_camera_replay_manifest_v1(manifest))
    verified_handoff = dict(parse_camera_arrival_consumer_handoff_v1(handoff))
    if verified_handoff["handoff_sha256"] != verified["handoff_sha256"]:
        raise ImmutableCameraReplayV1Error("replay handoff identity differs")
    resolved: set[Path] = set()
    for row in verified["captures"]:
        image_path = _contained_file(
            replay_root, row["image"]["relative_path"],
            f"capture {row['capture_id']} image",
        )
        metadata_path = _contained_file(
            replay_root, row["metadata"]["relative_path"],
            f"capture {row['capture_id']} metadata",
        )
        if image_path in resolved or metadata_path in resolved or image_path == metadata_path:
            raise ImmutableCameraReplayV1Error("replay files are not unique")
        resolved.update((image_path, metadata_path))
        _read_binding(
            replay_root, row["image"], f"capture {row['capture_id']} image",
            limit=MAX_IMAGE_BYTES,
        )
        metadata_raw = _read_binding(
            replay_root, row["metadata"], f"capture {row['capture_id']} metadata",
            limit=MAX_JSON_BYTES,
        )
        _metadata(
            metadata_raw, row["capture_id"], verified["source_evidence_class"],
            verified["camera_profile_sha256"], verified["support_profile_sha256"],
            verified["calibration_sha256"],
        )
    campaign_receipt, localization_receipt = _outputs(
        replay_root, verified, verified_handoff
    )
    receipts = {
        "localization_campaign": campaign_receipt["receipt_sha256"],
        "localization_evaluation": localization_receipt["receipt_sha256"],
    }
    if receipts != verified["expected_receipt_sha256"]:
        raise ImmutableCameraReplayV1Error("replayed consumer decision differs")
    core = {
        "schema": REPORT_SCHEMA, "replay_id": verified["replay_id"],
        "manifest_sha256": verified["manifest_sha256"],
        "replay_evidence_class": REPLAY_EVIDENCE_CLASS,
        "source_evidence_class": verified["source_evidence_class"],
        "capture_count": len(verified["captures"]),
        "verified_file_count": len(verified["captures"]) * 2 + 2,
        "receipt_sha256": receipts,
        "decision_status": {
            "localization_campaign": campaign_receipt["validation_status"],
            "localization_evaluation": localization_receipt["validation_status"],
        },
        "identical_replay_confirmed": True,
        "live_camera_opened": False, "qualification_installed": False,
        "controller_started": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "report_sha256": _sha(core)}


def parse_immutable_camera_replay_report_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise ImmutableCameraReplayV1Error("replay report fields differ")
    unsigned = dict(value)
    digest = unsigned.pop("report_sha256")
    if not isinstance(digest, str) or _sha(unsigned) != digest:
        raise ImmutableCameraReplayV1Error("replay report hash mismatch")
    if (
        value.get("schema") != REPORT_SCHEMA
        or value.get("replay_evidence_class") != REPLAY_EVIDENCE_CLASS
        or value.get("source_evidence_class") not in SOURCE_EVIDENCE_CLASSES
        or not isinstance(value.get("capture_count"), int)
        or not 1 <= value["capture_count"] <= MAX_CAPTURES
        or value.get("verified_file_count") != value["capture_count"] * 2 + 2
        or value.get("identical_replay_confirmed") is not True
        or any(value.get(field) is not False for field in (
            "live_camera_opened", "qualification_installed", "controller_started",
            "physical_authority",
        ))
        or value.get("controller_commands") != []
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
    ):
        raise ImmutableCameraReplayV1Error("replay report semantics differ")
    _digest(value.get("manifest_sha256"), "manifest_sha256")
    for field in ("receipt_sha256", "decision_status"):
        record = value.get(field)
        if not isinstance(record, Mapping) or set(record) != {
            "localization_campaign", "localization_evaluation"
        }:
            raise ImmutableCameraReplayV1Error(f"{field} differs")
    for digest_value in value["receipt_sha256"].values():
        _digest(digest_value, "receipt_sha256")
    if any(status not in {"PASS", "BLOCKED"} for status in value["decision_status"].values()):
        raise ImmutableCameraReplayV1Error("decision status differs")
    return MappingProxyType(dict(value))


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
            raise ImmutableCameraReplayV1Error(f"{label} file is unavailable or oversized")
        return _strict_json(path.read_bytes(), label)
    except OSError as exc:
        raise ImmutableCameraReplayV1Error(f"{label} file is unavailable") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--replay-root", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_immutable_camera_replay_v1(
            _load(args.manifest, "manifest"), replay_root=args.replay_root,
            handoff=_load(args.handoff, "handoff"),
        )
        parse_immutable_camera_replay_report_v1(report)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


__all__ = [
    "MANIFEST_SCHEMA", "MAX_CAPTURES", "REPORT_SCHEMA",
    "REPLAY_EVIDENCE_CLASS", "SOURCE_EVIDENCE_CLASSES",
    "ImmutableCameraReplayV1Error", "build_immutable_camera_replay_manifest_v1",
    "parse_immutable_camera_replay_manifest_v1",
    "parse_immutable_camera_replay_report_v1", "run_immutable_camera_replay_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())
