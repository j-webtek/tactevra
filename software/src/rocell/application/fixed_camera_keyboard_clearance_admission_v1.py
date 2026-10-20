"""Publish profile-specific keyboard clearance inputs from exact files.

This offline boundary joins an admitted fixed-camera localization package to
reviewed bare-jaw and stylus installed-collision profiles and the exact measured
stylus TCP artifact.  It invokes the existing clearance intake compiler and
writes its completion receipt last.  It cannot access hardware, construct a
trajectory, screen a route, or grant physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .context import SimulationContextError, load_simulation_context
from .fixed_camera_keyboard_clearance_intake_v1 import (
    READY_STATUS,
    FixedCameraKeyboardClearanceIntakeV1Error,
    compile_clearance_intake,
)
from .installed_collision_geometry import InstalledCollisionGeometryError
from .installed_collision_profile_builder_v1 import (
    InstalledCollisionProfileBuilderV1Error,
    load_installed_collision_geometry_profile_from_bytes_v1,
)
from rocell.calibration.fixed_camera_keyboard_localization_admission_v1 import (
    ADMITTED_STATUS as LOCALIZATION_ADMITTED_STATUS,
    LOCALIZATION_NAME,
    RECEIPT_NAME as LOCALIZATION_RECEIPT_NAME,
    ZERO_AUTHORITY as LOCALIZATION_ZERO_AUTHORITY,
)
from rocell.simulation.collision import CollisionAttachmentProfile


MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_TCP_BYTES = 4 * 1024 * 1024
INTAKE_NAME = "keyboard-clearance-intake.json"
RECEIPT_NAME = "clearance-admission-receipt.json"
ADMITTED_STATUS = "PROFILE_SPECIFIC_INSTALLED_CLEARANCE_ADMITTED"
SUPPORTED_PROFILES = ("no_attachment", "stylus_attachment")
ZERO_AUTHORITY: Mapping[str, object] = {
    "camera_opened": False,
    "robot_provider_called": False,
    "controller_commands": [],
    "trajectory_generated": False,
    "collision_screening_executed": False,
    "continuous_clearance_verified": False,
    "motion_authorized": False,
    "contact_authorized": False,
    "physical_release_effect": "NONE",
}


class FixedCameraKeyboardClearanceAdmissionError(ValueError):
    """The retained clearance inputs cannot be admitted or published."""


def _canonical(value: object, *, newline: bool = False) -> bytes:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FixedCameraKeyboardClearanceAdmissionError(
            "clearance value is not canonical JSON"
        ) from exc
    return payload + (b"\n" if newline else b"")


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
        raise FixedCameraKeyboardClearanceAdmissionError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _reject_constant(value: str) -> None:
    raise FixedCameraKeyboardClearanceAdmissionError(
        f"clearance input contains nonfinite constant {value!r}"
    )


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pairs:
        if key in result:
            raise FixedCameraKeyboardClearanceAdmissionError(
                f"clearance input contains duplicate key {key!r}"
            )
        result[key] = item
    return result


def _read_pinned_bytes(
    path: str | Path,
    *,
    expected_sha256: str,
    label: str,
    maximum_bytes: int,
) -> tuple[Path, bytes]:
    source = Path(path).expanduser()
    expected = _expected_digest(expected_sha256, f"expected_{label}_file_sha256")
    if source.is_symlink():
        raise FixedCameraKeyboardClearanceAdmissionError(
            f"{label} path must not be a symlink"
        )
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise FixedCameraKeyboardClearanceAdmissionError(
            f"cannot inspect {label} file: {exc}"
        ) from exc
    if not source.is_file() or size <= 0 or size > maximum_bytes:
        raise FixedCameraKeyboardClearanceAdmissionError(
            f"{label} file size is invalid"
        )
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise FixedCameraKeyboardClearanceAdmissionError(
            f"cannot read {label} file: {exc}"
        ) from exc
    if len(payload) != size:
        raise FixedCameraKeyboardClearanceAdmissionError(
            f"{label} file changed while being read"
        )
    if _sha256(payload) != expected:
        raise FixedCameraKeyboardClearanceAdmissionError(
            f"{label} bytes differ from expected file SHA-256"
        )
    return source.resolve(), payload


def _read_json_pinned(
    path: str | Path,
    *,
    expected_sha256: str,
    label: str,
) -> tuple[Path, bytes, Mapping[str, Any]]:
    source, payload = _read_pinned_bytes(
        path,
        expected_sha256=expected_sha256,
        label=label,
        maximum_bytes=MAX_JSON_BYTES,
    )
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixedCameraKeyboardClearanceAdmissionError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise FixedCameraKeyboardClearanceAdmissionError(
            f"{label} must be a JSON object"
        )
    return source, payload, value


def _validate_localization_admission(
    receipt_path: Path,
    receipt: Mapping[str, Any],
    localization_path: Path,
    localization_bytes: bytes,
    localization: Mapping[str, Any],
) -> None:
    if receipt_path.name != LOCALIZATION_RECEIPT_NAME:
        raise FixedCameraKeyboardClearanceAdmissionError(
            "localization admission receipt has the wrong file name"
        )
    if localization_path.name != LOCALIZATION_NAME:
        raise FixedCameraKeyboardClearanceAdmissionError(
            "localization artifact has the wrong file name"
        )
    if receipt_path.parent != localization_path.parent:
        raise FixedCameraKeyboardClearanceAdmissionError(
            "localization receipt and artifact must share one directory"
        )
    if (
        receipt.get("schema")
        != "rocell.fixed_camera_keyboard_localization_admission_receipt.v1"
        or receipt.get("status") != LOCALIZATION_ADMITTED_STATUS
        or receipt.get("profile_separation_preserved") is not True
        or receipt.get("authority") != LOCALIZATION_ZERO_AUTHORITY
    ):
        raise FixedCameraKeyboardClearanceAdmissionError(
            "localization admission receipt is invalid or authority-bearing"
        )
    artifacts = receipt.get("artifacts")
    artifact = artifacts.get("localization") if isinstance(artifacts, Mapping) else None
    completion = (
        artifacts.get("completion_receipt")
        if isinstance(artifacts, Mapping)
        else None
    )
    if (
        not isinstance(artifact, Mapping)
        or artifact.get("name") != LOCALIZATION_NAME
        or artifact.get("size_bytes") != len(localization_bytes)
        or artifact.get("file_sha256") != _sha256(localization_bytes)
        or artifact.get("meaning_sha256") != _digest(localization)
        or artifact.get("profile_candidate_counts")
        != {"no_attachment": 46, "stylus_attachment": 46}
        or not isinstance(completion, Mapping)
        or completion.get("name") != LOCALIZATION_RECEIPT_NAME
        or completion.get("written_last") is not True
    ):
        raise FixedCameraKeyboardClearanceAdmissionError(
            "localization differs from its admission receipt"
        )


def _profile_source_bindings(document: Mapping[str, Any], label: str) -> Mapping[str, str]:
    bindings = document.get("source_bindings")
    if not isinstance(bindings, Mapping) or not bindings:
        raise FixedCameraKeyboardClearanceAdmissionError(
            f"{label} source bindings are missing"
        )
    normalized: dict[str, str] = {}
    for key, value in bindings.items():
        if not isinstance(key, str) or not key.strip():
            raise FixedCameraKeyboardClearanceAdmissionError(
                f"{label} source binding name is invalid"
            )
        normalized[key] = _expected_digest(value, f"{label} source binding")
    return normalized


def _validate_stylus_tcp_binding(
    bindings: Mapping[str, Any], stylus_tcp_sha256: str
) -> None:
    rows = bindings.get("profiles")
    if not isinstance(rows, list):
        raise FixedCameraKeyboardClearanceAdmissionError(
            "clearance bindings profiles are invalid"
        )
    stylus_rows = [
        row
        for row in rows
        if isinstance(row, Mapping) and row.get("profile") == "stylus_attachment"
    ]
    if len(stylus_rows) != 1 or stylus_rows[0].get("measured_tcp_sha256") != stylus_tcp_sha256:
        raise FixedCameraKeyboardClearanceAdmissionError(
            "stylus TCP bytes differ from the reviewed binding"
        )


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise FixedCameraKeyboardClearanceAdmissionError(
            f"cannot publish new clearance file {path.name}: {exc}"
        ) from exc


@dataclass(frozen=True, slots=True)
class FixedCameraKeyboardClearanceAdmissionResultV1:
    """Paths and receipt for one completed clearance admission."""

    output_directory: Path
    intake_path: Path
    receipt_path: Path
    intake: Mapping[str, Any]
    receipt: Mapping[str, Any]


def admit_fixed_camera_keyboard_clearance_v1(
    localization_admission_receipt_path: str | Path,
    *,
    expected_localization_admission_receipt_file_sha256: str,
    localization_path: str | Path,
    expected_localization_file_sha256: str,
    profile_bindings_path: str | Path,
    expected_profile_bindings_file_sha256: str,
    bare_jaw_profile_path: str | Path,
    expected_bare_jaw_profile_file_sha256: str,
    stylus_profile_path: str | Path,
    expected_stylus_profile_file_sha256: str,
    stylus_tcp_path: str | Path,
    expected_stylus_tcp_file_sha256: str,
    workspace: str | Path,
    manifest_path: str | Path,
    expected_manifest_file_sha256: str,
    output_directory: str | Path,
) -> FixedCameraKeyboardClearanceAdmissionResultV1:
    """Validate exact profile evidence and publish a zero-authority handoff."""

    receipt_source, receipt_bytes, localization_receipt = _read_json_pinned(
        localization_admission_receipt_path,
        expected_sha256=expected_localization_admission_receipt_file_sha256,
        label="localization admission receipt",
    )
    localization_source, localization_bytes, localization = _read_json_pinned(
        localization_path,
        expected_sha256=expected_localization_file_sha256,
        label="localization",
    )
    _validate_localization_admission(
        receipt_source,
        localization_receipt,
        localization_source,
        localization_bytes,
        localization,
    )
    binding_source, binding_bytes, bindings = _read_json_pinned(
        profile_bindings_path,
        expected_sha256=expected_profile_bindings_file_sha256,
        label="profile bindings",
    )
    bare_source, bare_bytes, bare_document = _read_json_pinned(
        bare_jaw_profile_path,
        expected_sha256=expected_bare_jaw_profile_file_sha256,
        label="bare jaw installed profile",
    )
    stylus_source, stylus_bytes, stylus_document = _read_json_pinned(
        stylus_profile_path,
        expected_sha256=expected_stylus_profile_file_sha256,
        label="stylus installed profile",
    )
    tcp_source, tcp_bytes = _read_pinned_bytes(
        stylus_tcp_path,
        expected_sha256=expected_stylus_tcp_file_sha256,
        label="stylus TCP",
        maximum_bytes=MAX_TCP_BYTES,
    )
    tcp_sha256 = _sha256(tcp_bytes)
    _validate_stylus_tcp_binding(bindings, tcp_sha256)

    workspace_root = Path(workspace).expanduser().resolve()
    manifest_source, manifest_bytes, _manifest = _read_json_pinned(
        manifest_path,
        expected_sha256=expected_manifest_file_sha256,
        label="system manifest",
    )
    try:
        manifest_source.relative_to(workspace_root)
    except ValueError as exc:
        raise FixedCameraKeyboardClearanceAdmissionError(
            "system manifest must remain beneath the selected workspace"
        ) from exc
    try:
        context = load_simulation_context(workspace_root, manifest_source)
        profiles = {
            "no_attachment": load_installed_collision_geometry_profile_from_bytes_v1(
                bare_bytes,
                _sha256(bare_bytes),
                context=context,
                attachment_profile=CollisionAttachmentProfile.NO_ATTACHMENT,
                expected_source_bindings=_profile_source_bindings(
                    bare_document, "bare jaw installed profile"
                ),
            ),
            "stylus_attachment": load_installed_collision_geometry_profile_from_bytes_v1(
                stylus_bytes,
                _sha256(stylus_bytes),
                context=context,
                attachment_profile=CollisionAttachmentProfile.STYLUS_ATTACHMENT,
                expected_source_bindings=_profile_source_bindings(
                    stylus_document, "stylus installed profile"
                ),
            ),
        }
        intake = compile_clearance_intake(
            localization,
            bindings,
            profiles,
            context=context,
        )
    except (
        FixedCameraKeyboardClearanceIntakeV1Error,
        InstalledCollisionGeometryError,
        InstalledCollisionProfileBuilderV1Error,
        SimulationContextError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise FixedCameraKeyboardClearanceAdmissionError(str(exc)) from exc
    if (
        intake.get("status") != READY_STATUS
        or intake.get("profile_separation_preserved") is not True
        or intake.get("trajectory_generated") is not False
        or intake.get("collision_screening_executed") is not False
        or intake.get("physical_authority") is not False
    ):
        raise FixedCameraKeyboardClearanceAdmissionError(
            "clearance intake did not produce a separate zero-authority handoff"
        )

    intake_bytes = _canonical(intake, newline=True)
    source_rows = {
        "localization_admission_receipt": (
            receipt_source,
            receipt_bytes,
            _digest(localization_receipt),
        ),
        "localization": (
            localization_source,
            localization_bytes,
            _digest(localization),
        ),
        "profile_bindings": (binding_source, binding_bytes, _digest(bindings)),
        "bare_jaw_installed_profile": (
            bare_source,
            bare_bytes,
            _digest(bare_document),
        ),
        "stylus_installed_profile": (
            stylus_source,
            stylus_bytes,
            _digest(stylus_document),
        ),
        "stylus_tcp": (tcp_source, tcp_bytes, tcp_sha256),
        "system_manifest": (manifest_source, manifest_bytes, _digest(_manifest)),
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
        "schema": "rocell.fixed_camera_keyboard_clearance_admission_receipt.v1",
        "status": ADMITTED_STATUS,
        "sources": sources,
        "localization_admission_status": localization_receipt["status"],
        "artifacts": {
            "clearance_intake": {
                "name": INTAKE_NAME,
                "size_bytes": len(intake_bytes),
                "file_sha256": _sha256(intake_bytes),
                "meaning_sha256": _digest(intake),
                "profile_candidate_counts": {
                    name: profile["candidate_count"]
                    for name, profile in intake["profiles"].items()
                },
            },
            "completion_receipt": {
                "name": RECEIPT_NAME,
                "written_last": True,
            },
        },
        "profile_separation_preserved": True,
        "next_required_stage": (
            "BUILD_PROFILE_SPECIFIC_TYPING_EXECUTION_PLAN_THEN_USE_"
            "TYPING_COLLISION_INTAKE_V1"
        ),
        "authority": dict(ZERO_AUTHORITY),
    }
    receipt_bytes_out = _canonical(receipt, newline=True)

    requested = Path(output_directory).expanduser()
    if not requested.name or requested.name in (".", ".."):
        raise FixedCameraKeyboardClearanceAdmissionError(
            "output_directory must name a new directory"
        )
    parent = requested.parent.resolve()
    if not parent.is_dir():
        raise FixedCameraKeyboardClearanceAdmissionError(
            "output_directory parent must already exist"
        )
    destination = parent / requested.name
    if destination.exists() or destination.is_symlink():
        raise FixedCameraKeyboardClearanceAdmissionError(
            "output_directory already exists; refusing to overwrite"
        )
    try:
        destination.mkdir(mode=0o700, exist_ok=False)
    except OSError as exc:
        raise FixedCameraKeyboardClearanceAdmissionError(
            f"cannot reserve output_directory: {exc}"
        ) from exc
    intake_path = destination / INTAKE_NAME
    receipt_path = destination / RECEIPT_NAME
    try:
        _write_new(intake_path, intake_bytes)
        _write_new(receipt_path, receipt_bytes_out)
    except Exception:
        for path in (receipt_path, intake_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            destination.rmdir()
        except OSError:
            pass
        raise

    return FixedCameraKeyboardClearanceAdmissionResultV1(
        output_directory=destination,
        intake_path=intake_path,
        receipt_path=receipt_path,
        intake=intake,
        receipt=receipt,
    )


__all__ = [
    "ADMITTED_STATUS",
    "INTAKE_NAME",
    "RECEIPT_NAME",
    "FixedCameraKeyboardClearanceAdmissionError",
    "FixedCameraKeyboardClearanceAdmissionResultV1",
    "admit_fixed_camera_keyboard_clearance_v1",
]
