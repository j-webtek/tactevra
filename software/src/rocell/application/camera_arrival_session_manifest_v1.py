"""Restart-safe manifest for one zero-authority camera-arrival session."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .camera_arrival_commissioning_orchestrator_v1 import (
    parse_camera_arrival_commissioning_orchestrator_v1,
    run_camera_arrival_commissioning_orchestrator_v1,
)
from .camera_arrival_kit_v1 import REQUIRED_SLOT_IDS


SCHEMA = "rocell.camera_arrival_session_manifest.v1"
COLLECTION_STATE = "COLLECTION_INCOMPLETE"
STRUCTURALLY_COMPLETE_STATE = "STRUCTURALLY_COMPLETE"
PENDING_STATE = "VALIDATION_PENDING"
BLOCKED_STATE = "VALIDATION_BLOCKED"
COMPLETE_HELD_STATE = "OFFLINE_REVIEW_COMPLETE_MEASURED_COMMISSIONING_HELD"
_HASH = re.compile(r"^[0-9a-f]{64}$")
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_FIELDS = {
    "schema", "session_id", "configuration_epoch_candidate",
    "camera_profile_id", "camera_profile_sha256", "tool_profile_id",
    "tool_profile_sha256", "state", "orchestrator_sha256", "orchestrator",
    "originals", "routes", "receipts", "restart_reconstruction_required",
    "measured_commissioning_held", "configuration_epoch_advanced",
    "deployment_registry_updated", "qualification_installed", "camera_opened",
    "transport_opened", "controller_started", "controller_commands",
    "hardware_writes", "physical_movements", "physical_authority",
    "manifest_sha256",
}


class CameraArrivalSessionManifestV1Error(ValueError):
    """The session metadata, lineage, or reconstruction is inconsistent."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CameraArrivalSessionManifestV1Error(
                "duplicate session manifest JSON field"
            )
        result[key] = value
    return result


def load_camera_arrival_session_manifest_v1(path: Path) -> dict[str, Any]:
    """Load one bounded regular manifest without following a final symlink."""

    try:
        if path.is_symlink() or not path.is_file():
            raise CameraArrivalSessionManifestV1Error(
                "session manifest must be a regular non-symlink file"
            )
        size = path.stat().st_size
        if not 0 < size <= MAX_MANIFEST_BYTES:
            raise CameraArrivalSessionManifestV1Error(
                "session manifest size is outside the allowed bound"
            )
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        try:
            payload = os.read(descriptor, MAX_MANIFEST_BYTES + 1)
        finally:
            os.close(descriptor)
        if len(payload) != size or len(payload) > MAX_MANIFEST_BYTES:
            raise CameraArrivalSessionManifestV1Error(
                "session manifest changed while being read"
            )
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_unique_object
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CameraArrivalSessionManifestV1Error(
            f"cannot load session manifest: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise CameraArrivalSessionManifestV1Error(
            "session manifest JSON root must be an object"
        )
    return dict(parse_camera_arrival_session_manifest_v1(value))


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str) or not 1 <= len(value) <= 128
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in value)
    ):
        raise CameraArrivalSessionManifestV1Error(f"{label} is not a safe identifier")
    return value


def _hash(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise CameraArrivalSessionManifestV1Error(f"{label} is not a SHA-256 digest")
    return value


def _state(orchestrator: Mapping[str, Any]) -> str:
    if orchestrator["preflight"]["ready_for_offline_qualification_review"] is not True:
        return COLLECTION_STATE
    if orchestrator["assessment"]["complete_for_offline_review"] is True:
        return COMPLETE_HELD_STATE
    if orchestrator["assessment"]["blocked_count"]:
        return BLOCKED_STATE
    if orchestrator["receipt_root"] is None:
        return STRUCTURALLY_COMPLETE_STATE
    return PENDING_STATE


def _summaries(orchestrator: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    file_by_id = {
        row["artifact_id"]: row for row in orchestrator["receipt_files"]
    }
    originals = [{
        "artifact_id": row["artifact_id"], "status": row["status"],
        "sidecar_relative_path": row["sidecar_relative_path"],
        "sidecar_sha256": row["sidecar_sha256"],
        "source_relative_path": row["source_relative_path"],
        "source_sha256": row["source_sha256"],
        "configuration_epoch_id": row["configuration_epoch_id"],
    } for row in orchestrator["preflight"]["slots"]]
    routes = [{
        "artifact_id": row["artifact_id"],
        "consumer_source_sha256": row["consumer_source_sha256"],
        "downstream_schema_sha256": row["downstream_schema_sha256"],
        "consumer_binding": row["consumer_binding"],
        "ready": row["ready_for_offline_consumer_validation"],
    } for row in orchestrator["handoff"]["routes"]]
    receipts = []
    for row in orchestrator["assessment"]["route_results"]:
        file_row = file_by_id.get(row["artifact_id"])
        receipts.append({
            "artifact_id": row["artifact_id"], "status": row["status"],
            "relative_path": None if file_row is None else file_row["relative_path"],
            "file_sha256": None if file_row is None else file_row["file_sha256"],
            "receipt_sha256": row["receipt_sha256"],
            "output_sha256": row["output_sha256"],
            "blockers": list(row["blockers"]),
        })
    return originals, routes, receipts


def build_camera_arrival_session_manifest_v1(
    orchestrator: Mapping[str, Any], *, session_id: str,
    configuration_epoch_candidate: str, camera_profile_id: str,
    camera_profile_sha256: str, tool_profile_id: str,
    tool_profile_sha256: str,
) -> dict[str, Any]:
    """Bind a verified PC11 report and operator-selected immutable identities."""

    try:
        verified = dict(parse_camera_arrival_commissioning_orchestrator_v1(orchestrator))
    except ValueError as exc:
        raise CameraArrivalSessionManifestV1Error(str(exc)) from exc
    originals, routes, receipts = _summaries(verified)
    core = {
        "schema": SCHEMA,
        "session_id": _identifier(session_id, "session_id"),
        "configuration_epoch_candidate": _identifier(
            configuration_epoch_candidate, "configuration_epoch_candidate"
        ),
        "camera_profile_id": _identifier(camera_profile_id, "camera_profile_id"),
        "camera_profile_sha256": _hash(camera_profile_sha256, "camera_profile_sha256"),
        "tool_profile_id": _identifier(tool_profile_id, "tool_profile_id"),
        "tool_profile_sha256": _hash(tool_profile_sha256, "tool_profile_sha256"),
        "state": _state(verified),
        "orchestrator_sha256": verified["orchestrator_sha256"],
        "orchestrator": verified,
        "originals": originals, "routes": routes, "receipts": receipts,
        "restart_reconstruction_required": True,
        "measured_commissioning_held": True,
        "configuration_epoch_advanced": False,
        "deployment_registry_updated": False,
        "qualification_installed": False,
        "camera_opened": False, "transport_opened": False,
        "controller_started": False, "controller_commands": [],
        "hardware_writes": 0, "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "manifest_sha256": _digest(core)}


def parse_camera_arrival_session_manifest_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise CameraArrivalSessionManifestV1Error("session manifest fields differ")
    unsigned = dict(value)
    digest = unsigned.pop("manifest_sha256")
    if not isinstance(digest, str) or _digest(unsigned) != digest:
        raise CameraArrivalSessionManifestV1Error("session manifest hash mismatch")
    try:
        verified = dict(parse_camera_arrival_commissioning_orchestrator_v1(
            value["orchestrator"]
        ))
    except (KeyError, TypeError, ValueError) as exc:
        raise CameraArrivalSessionManifestV1Error(str(exc)) from exc
    originals, routes, receipts = _summaries(verified)
    expected_state = _state(verified)
    if (
        value.get("schema") != SCHEMA
        or value.get("orchestrator_sha256") != verified["orchestrator_sha256"]
        or value.get("state") != expected_state
        or value.get("originals") != originals or value.get("routes") != routes
        or value.get("receipts") != receipts
        or value.get("restart_reconstruction_required") is not True
        or value.get("measured_commissioning_held") is not True
        or any(value.get(field) is not False for field in (
            "configuration_epoch_advanced", "deployment_registry_updated",
            "qualification_installed", "camera_opened", "transport_opened",
            "controller_started", "physical_authority",
        ))
        or value.get("controller_commands") != []
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
    ):
        raise CameraArrivalSessionManifestV1Error("session manifest semantics differ")
    _identifier(value.get("session_id"), "session_id")
    _identifier(value.get("configuration_epoch_candidate"), "configuration_epoch_candidate")
    _identifier(value.get("camera_profile_id"), "camera_profile_id")
    _hash(value.get("camera_profile_sha256"), "camera_profile_sha256")
    _identifier(value.get("tool_profile_id"), "tool_profile_id")
    _hash(value.get("tool_profile_sha256"), "tool_profile_sha256")
    if tuple(row["artifact_id"] for row in originals) != REQUIRED_SLOT_IDS:
        raise CameraArrivalSessionManifestV1Error("session original order differs")
    return MappingProxyType(dict(value))


def reconstruct_camera_arrival_session_manifest_v1(
    existing: Mapping[str, Any], *, workspace: Path, evidence_root: Path,
    receipt_root: Path | None,
) -> dict[str, Any]:
    """Rerun PC11 and require byte-equivalent session state on restart."""

    prior = parse_camera_arrival_session_manifest_v1(existing)
    orchestrator = run_camera_arrival_commissioning_orchestrator_v1(
        workspace, evidence_root, receipt_root
    )
    rebuilt = build_camera_arrival_session_manifest_v1(
        orchestrator, session_id=prior["session_id"],
        configuration_epoch_candidate=prior["configuration_epoch_candidate"],
        camera_profile_id=prior["camera_profile_id"],
        camera_profile_sha256=prior["camera_profile_sha256"],
        tool_profile_id=prior["tool_profile_id"],
        tool_profile_sha256=prior["tool_profile_sha256"],
    )
    if rebuilt != dict(prior):
        raise CameraArrivalSessionManifestV1Error(
            "session reconstruction differs; dependent state is invalid"
        )
    return rebuilt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--receipt-root", type=Path)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--configuration-epoch-candidate", required=True)
    parser.add_argument("--camera-profile-id", required=True)
    parser.add_argument("--camera-profile-sha256", required=True)
    parser.add_argument("--tool-profile-id", required=True)
    parser.add_argument("--tool-profile-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        orchestrator = run_camera_arrival_commissioning_orchestrator_v1(
            args.workspace, args.evidence_root, args.receipt_root
        )
        manifest = build_camera_arrival_session_manifest_v1(
            orchestrator, session_id=args.session_id,
            configuration_epoch_candidate=args.configuration_epoch_candidate,
            camera_profile_id=args.camera_profile_id,
            camera_profile_sha256=args.camera_profile_sha256,
            tool_profile_id=args.tool_profile_id,
            tool_profile_sha256=args.tool_profile_sha256,
        )
        with args.output.open("xb") as stream:
            stream.write(_canonical(manifest))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["state"] == COMPLETE_HELD_STATE else 2


def verify_main(argv: Sequence[str] | None = None) -> int:
    """Verify that one retained manifest reconstructs exactly from disk."""

    parser = argparse.ArgumentParser(description=verify_main.__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--receipt-root", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        existing = load_camera_arrival_session_manifest_v1(args.manifest)
        rebuilt = reconstruct_camera_arrival_session_manifest_v1(
            existing, workspace=args.workspace, evidence_root=args.evidence_root,
            receipt_root=args.receipt_root,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(rebuilt, indent=2, sort_keys=True))
    return 0


__all__ = [
    "BLOCKED_STATE", "COLLECTION_STATE", "COMPLETE_HELD_STATE",
    "MAX_MANIFEST_BYTES", "PENDING_STATE", "SCHEMA",
    "STRUCTURALLY_COMPLETE_STATE",
    "CameraArrivalSessionManifestV1Error",
    "build_camera_arrival_session_manifest_v1", "main",
    "load_camera_arrival_session_manifest_v1",
    "parse_camera_arrival_session_manifest_v1",
    "reconstruct_camera_arrival_session_manifest_v1", "verify_main",
]


if __name__ == "__main__":
    raise SystemExit(main())
