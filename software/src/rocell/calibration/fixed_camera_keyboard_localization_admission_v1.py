"""Publish reviewed fixed-camera keyboard localization from exact files.

This offline boundary joins the accepted campaign-review receipt to the exact
reviewed board-to-robot measurement it published, the exact keyboard-to-board
package, and the exact target profile.  It invokes the existing localization
compiler and publishes candidates only when the transform passes every fit and
held-out residual check.  The completion receipt is written last.  No camera,
robot, serial, trajectory, motion, contact, or freeze-release capability is
present.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from rocell.vision.fixed_camera_keyboard_robot_localization_v1 import (
    FixedCameraKeyboardRobotLocalizationError,
    compile_localization,
)

from .fixed_camera_campaign_review_admission_v1 import (
    RECEIPT_NAME as REVIEW_ADMISSION_RECEIPT_NAME,
    REVIEWED_MEASUREMENT_NAME,
    ZERO_AUTHORITY as REVIEW_ADMISSION_ZERO_AUTHORITY,
)
from .fixed_camera_campaign_review_intake_v1 import ACCEPTED_STATUS


MAX_JSON_BYTES = 4 * 1024 * 1024
LOCALIZATION_NAME = "keyboard-robot-localization.json"
RECEIPT_NAME = "localization-admission-receipt.json"
READY_STATUS = "ROBOT_FRAME_LOCALIZATION_CANDIDATES_READY"
ADMITTED_STATUS = "ROBOT_FRAME_LOCALIZATION_CANDIDATES_ADMITTED"
ZERO_AUTHORITY: Mapping[str, object] = {
    "camera_opened": False,
    "robot_provider_called": False,
    "controller_commands": [],
    "trajectory_generated": False,
    "motion_targets_emitted": False,
    "motion_authorized": False,
    "contact_authorized": False,
    "physical_release_effect": "NONE",
}


class FixedCameraKeyboardLocalizationAdmissionError(ValueError):
    """The retained localization inputs cannot be admitted or published."""


def _canonical(value: object, *, newline: bool = False) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            "localization value is not canonical JSON"
        ) from exc
    return encoded + (b"\n" if newline else b"")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest(value: object) -> str:
    return _sha256(_canonical(value))


def _expected_digest(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FixedCameraKeyboardLocalizationAdmissionError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _reject_constant(value: str) -> None:
    raise FixedCameraKeyboardLocalizationAdmissionError(
        f"localization input contains nonfinite constant {value!r}"
    )


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise FixedCameraKeyboardLocalizationAdmissionError(
                f"localization input contains duplicate key {key!r}"
            )
        value[key] = item
    return value


def _read_json_pinned(
    path: str | Path,
    *,
    expected_sha256: str,
    label: str,
) -> tuple[Path, bytes, Mapping[str, Any]]:
    source = Path(path).expanduser()
    expected = _expected_digest(expected_sha256, f"expected_{label}_file_sha256")
    if source.is_symlink():
        raise FixedCameraKeyboardLocalizationAdmissionError(
            f"{label} path must not be a symlink"
        )
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            f"cannot inspect {label} file: {exc}"
        ) from exc
    if not source.is_file() or size <= 0 or size > MAX_JSON_BYTES:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            f"{label} file size is invalid"
        )
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            f"cannot read {label} file: {exc}"
        ) from exc
    if len(payload) != size:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            f"{label} file changed while being read"
        )
    if _sha256(payload) != expected:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            f"{label} bytes differ from expected file SHA-256"
        )
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise FixedCameraKeyboardLocalizationAdmissionError(
            f"{label} must be a JSON object"
        )
    return source.resolve(), payload, value


def _require_exact_keys(
    value: Mapping[str, Any], required: set[str], label: str
) -> None:
    if set(value) != required:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            f"{label} fields are invalid"
        )


def _validate_review_admission_binding(
    receipt_path: Path,
    receipt: Mapping[str, Any],
    measurement_path: Path,
    measurement_bytes: bytes,
    measurement: Mapping[str, Any],
) -> None:
    if receipt_path.name != REVIEW_ADMISSION_RECEIPT_NAME:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            "review admission receipt has the wrong file name"
        )
    if measurement_path.name != REVIEWED_MEASUREMENT_NAME:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            "reviewed measurement has the wrong file name"
        )
    if receipt_path.parent != measurement_path.parent:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            "review admission receipt and measurement must share one directory"
        )
    if (
        receipt.get("schema")
        != "rocell.fixed_camera_campaign_review_admission_receipt.v1"
        or receipt.get("status") != ACCEPTED_STATUS
        or receipt.get("measurement_published") is not True
    ):
        raise FixedCameraKeyboardLocalizationAdmissionError(
            "review admission did not accept and publish a measurement"
        )
    artifacts = receipt.get("artifacts")
    authority = receipt.get("authority")
    if (
        not isinstance(artifacts, Mapping)
        or authority != REVIEW_ADMISSION_ZERO_AUTHORITY
    ):
        raise FixedCameraKeyboardLocalizationAdmissionError(
            "review admission receipt is incomplete or authority-bearing"
        )
    completion = artifacts.get("completion_receipt")
    artifact = artifacts.get("reviewed_measurement")
    if (
        not isinstance(completion, Mapping)
        or completion.get("name") != REVIEW_ADMISSION_RECEIPT_NAME
        or completion.get("written_last") is not True
        or not isinstance(artifact, Mapping)
    ):
        raise FixedCameraKeyboardLocalizationAdmissionError(
            "review admission completion or measurement artifact is invalid"
        )
    _require_exact_keys(
        artifact,
        {"name", "size_bytes", "file_sha256", "meaning_sha256"},
        "reviewed measurement artifact",
    )
    if (
        artifact.get("name") != REVIEWED_MEASUREMENT_NAME
        or artifact.get("size_bytes") != len(measurement_bytes)
        or artifact.get("file_sha256") != _sha256(measurement_bytes)
        or artifact.get("meaning_sha256") != _digest(measurement)
    ):
        raise FixedCameraKeyboardLocalizationAdmissionError(
            "reviewed measurement differs from the accepted review artifact"
        )


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            f"cannot publish new localization file {path.name}: {exc}"
        ) from exc


@dataclass(frozen=True, slots=True)
class FixedCameraKeyboardLocalizationAdmissionResultV1:
    """Paths and receipt for one completed localization admission."""

    output_directory: Path
    localization_path: Path
    receipt_path: Path
    localization: Mapping[str, Any]
    receipt: Mapping[str, Any]


def admit_fixed_camera_keyboard_localization_v1(
    review_admission_receipt_path: str | Path,
    *,
    expected_review_admission_receipt_file_sha256: str,
    reviewed_measurement_path: str | Path,
    expected_reviewed_measurement_file_sha256: str,
    keyboard_package_path: str | Path,
    expected_keyboard_package_file_sha256: str,
    target_profile_path: str | Path,
    expected_target_profile_file_sha256: str,
    output_directory: str | Path,
) -> FixedCameraKeyboardLocalizationAdmissionResultV1:
    """Validate exact reviewed inputs and publish zero-authority localization."""

    receipt_source, receipt_bytes, review_receipt = _read_json_pinned(
        review_admission_receipt_path,
        expected_sha256=expected_review_admission_receipt_file_sha256,
        label="review admission receipt",
    )
    measurement_source, measurement_bytes, measurement = _read_json_pinned(
        reviewed_measurement_path,
        expected_sha256=expected_reviewed_measurement_file_sha256,
        label="reviewed measurement",
    )
    _validate_review_admission_binding(
        receipt_source,
        review_receipt,
        measurement_source,
        measurement_bytes,
        measurement,
    )
    keyboard_source, keyboard_bytes, keyboard_package = _read_json_pinned(
        keyboard_package_path,
        expected_sha256=expected_keyboard_package_file_sha256,
        label="keyboard package",
    )
    target_source, target_bytes, target_profile = _read_json_pinned(
        target_profile_path,
        expected_sha256=expected_target_profile_file_sha256,
        label="target profile",
    )

    try:
        localization = compile_localization(
            measurement,
            keyboard_package,
            target_profile,
            target_profile_sha256=_sha256(target_bytes),
        )
    except FixedCameraKeyboardRobotLocalizationError as exc:
        raise FixedCameraKeyboardLocalizationAdmissionError(str(exc)) from exc
    if (
        localization.get("status") != READY_STATUS
        or localization.get("board_to_robot_transform_verified") is not True
    ):
        raise FixedCameraKeyboardLocalizationAdmissionError(
            "board-to-robot localization residual checks did not pass"
        )
    profiles = localization.get("profiles")
    if not isinstance(profiles, Mapping) or set(profiles) != {
        "no_attachment",
        "stylus_attachment",
    }:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            "localization did not preserve both attachment profiles"
        )
    for profile_name, profile in profiles.items():
        if (
            not isinstance(profile, Mapping)
            or profile.get("profile") != profile_name
            or profile.get("robot_frame_localization_candidates_emitted") is not True
            or not isinstance(profile.get("robot_frame_localization_candidates"), list)
            or len(profile["robot_frame_localization_candidates"]) != 46
        ):
            raise FixedCameraKeyboardLocalizationAdmissionError(
                f"localization candidate coverage is invalid: {profile_name}"
            )

    localization_bytes = _canonical(localization, newline=True)
    source_rows = {
        "review_admission_receipt": (
            receipt_source,
            receipt_bytes,
            _digest(review_receipt),
        ),
        "reviewed_measurement": (
            measurement_source,
            measurement_bytes,
            _digest(measurement),
        ),
        "keyboard_package": (
            keyboard_source,
            keyboard_bytes,
            _digest(keyboard_package),
        ),
        "target_profile": (
            target_source,
            target_bytes,
            _digest(target_profile),
        ),
    }
    sources = {
        label: {
            "name": source.name,
            "size_bytes": len(payload),
            "file_sha256": _sha256(payload),
            "meaning_sha256": meaning,
        }
        for label, (source, payload, meaning) in source_rows.items()
    }
    receipt: Mapping[str, object] = {
        "schema": "rocell.fixed_camera_keyboard_localization_admission_receipt.v1",
        "status": ADMITTED_STATUS,
        "sources": sources,
        "review_admission_status": review_receipt["status"],
        "artifacts": {
            "localization": {
                "name": LOCALIZATION_NAME,
                "size_bytes": len(localization_bytes),
                "file_sha256": _sha256(localization_bytes),
                "meaning_sha256": _digest(localization),
                "profile_candidate_counts": {
                    name: len(profile["robot_frame_localization_candidates"])
                    for name, profile in profiles.items()
                },
            },
            "completion_receipt": {
                "name": RECEIPT_NAME,
                "written_last": True,
            },
        },
        "profile_separation_preserved": True,
        "next_required_stage": "PROFILE_SPECIFIC_INSTALLED_CLEARANCE_INTAKE",
        "authority": dict(ZERO_AUTHORITY),
    }
    receipt_bytes_out = _canonical(receipt, newline=True)

    requested = Path(output_directory).expanduser()
    if not requested.name or requested.name in (".", ".."):
        raise FixedCameraKeyboardLocalizationAdmissionError(
            "output_directory must name a new directory"
        )
    parent = requested.parent.resolve()
    if not parent.is_dir():
        raise FixedCameraKeyboardLocalizationAdmissionError(
            "output_directory parent must already exist"
        )
    destination = parent / requested.name
    if destination.exists() or destination.is_symlink():
        raise FixedCameraKeyboardLocalizationAdmissionError(
            "output_directory already exists; refusing to overwrite"
        )
    try:
        destination.mkdir(mode=0o700, exist_ok=False)
    except OSError as exc:
        raise FixedCameraKeyboardLocalizationAdmissionError(
            f"cannot reserve output_directory: {exc}"
        ) from exc
    localization_path = destination / LOCALIZATION_NAME
    receipt_path = destination / RECEIPT_NAME
    try:
        _write_new(localization_path, localization_bytes)
        _write_new(receipt_path, receipt_bytes_out)
    except Exception:
        for path in (receipt_path, localization_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            destination.rmdir()
        except OSError:
            pass
        raise

    return FixedCameraKeyboardLocalizationAdmissionResultV1(
        output_directory=destination,
        localization_path=localization_path,
        receipt_path=receipt_path,
        localization=localization,
        receipt=receipt,
    )


__all__ = [
    "ADMITTED_STATUS",
    "LOCALIZATION_NAME",
    "RECEIPT_NAME",
    "FixedCameraKeyboardLocalizationAdmissionError",
    "FixedCameraKeyboardLocalizationAdmissionResultV1",
    "admit_fixed_camera_keyboard_localization_v1",
]
