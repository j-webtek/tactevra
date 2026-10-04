"""Bind camera-arrival originals to repository consumers without invoking them."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .camera_arrival_consumer_map_v1 import build_camera_arrival_consumer_map_v1
from .camera_arrival_evidence_preflight_v1 import (
    inspect_camera_arrival_evidence_v1,
    parse_camera_arrival_evidence_preflight_v1,
)
from .camera_arrival_kit_v1 import REQUIRED_SLOT_IDS


SCHEMA = "rocell.camera_arrival_consumer_handoff.v1"
READY_STATUS = "READY_FOR_OFFLINE_CONSUMER_VALIDATION"
BLOCKED_STATUS = "BLOCKED_ARRIVAL_PREFLIGHT_INCOMPLETE"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_REPORT_FIELDS = {
    "schema", "status", "preflight_sha256", "consumer_map_sha256",
    "configuration_epoch_ids", "slot_count", "ready_slot_count", "routes",
    "ready_for_offline_consumer_validation", "consumer_validation_completed",
    "configuration_epoch_advanced", "deployment_registry_updated",
    "qualification_installed", "camera_opened", "controller_started",
    "hardware_writes", "physical_movements", "physical_authority",
    "handoff_sha256",
}
_ROUTE_FIELDS = {
    "artifact_id", "preflight_status", "preflight_blockers",
    "sidecar_sha256", "source_relative_path", "source_sha256",
    "configuration_epoch_id", "consumer_source", "consumer_source_sha256",
    "downstream_schema", "downstream_schema_sha256", "consumer_binding",
    "consumer_dependency_resolved", "ready_for_offline_consumer_validation",
    "consumer_validation_completed", "physical_admission_ready",
}


class CameraArrivalConsumerHandoffV1Error(ValueError):
    """The preflight/map binding or handoff report is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def compose_camera_arrival_consumer_handoff_v1(
    preflight: Mapping[str, Any], consumer_map: Mapping[str, Any]
) -> dict[str, Any]:
    """Compose a deterministic routing receipt from already-produced inputs."""

    try:
        verified = parse_camera_arrival_evidence_preflight_v1(preflight)
    except ValueError as exc:
        raise CameraArrivalConsumerHandoffV1Error(str(exc)) from exc
    mappings = consumer_map.get("mappings")
    if (
        consumer_map.get("schema") != "rocell.camera_arrival_consumer_map.v1"
        or not _is_hash(consumer_map.get("consumer_map_sha256"))
        or _digest({
            key: value for key, value in consumer_map.items()
            if key != "consumer_map_sha256"
        }) != consumer_map.get("consumer_map_sha256")
        or not isinstance(mappings, list)
        or tuple(
            row.get("artifact_id") if isinstance(row, Mapping) else None
            for row in mappings
        ) != REQUIRED_SLOT_IDS
    ):
        raise CameraArrivalConsumerHandoffV1Error(
            "consumer map is malformed or no longer hash-bound"
        )

    globally_ready = verified["ready_for_offline_qualification_review"] is True
    routes: list[dict[str, Any]] = []
    for slot, mapping in zip(verified["slots"], mappings):
        dependency_ready = mapping.get("consumer_dependency_resolved") is True
        ready = globally_ready and slot["status"] == "VALID" and dependency_ready
        routes.append({
            "artifact_id": slot["artifact_id"],
            "preflight_status": slot["status"],
            "preflight_blockers": list(slot["blockers"]),
            "sidecar_sha256": slot["sidecar_sha256"],
            "source_relative_path": slot["source_relative_path"],
            "source_sha256": slot["source_sha256"],
            "configuration_epoch_id": slot["configuration_epoch_id"],
            "consumer_source": mapping.get("consumer_source"),
            "consumer_source_sha256": mapping.get("consumer_source_sha256"),
            "downstream_schema": mapping.get("downstream_schema"),
            "downstream_schema_sha256": mapping.get("downstream_schema_sha256"),
            "consumer_binding": mapping.get("consumer_binding"),
            "consumer_dependency_resolved": dependency_ready,
            "ready_for_offline_consumer_validation": ready,
            "consumer_validation_completed": False,
            "physical_admission_ready": False,
        })
    ready_count = sum(
        route["ready_for_offline_consumer_validation"] for route in routes
    )
    ready = ready_count == len(REQUIRED_SLOT_IDS)
    core = {
        "schema": SCHEMA,
        "status": READY_STATUS if ready else BLOCKED_STATUS,
        "preflight_sha256": verified["preflight_sha256"],
        "consumer_map_sha256": consumer_map["consumer_map_sha256"],
        "configuration_epoch_ids": list(verified["configuration_epoch_ids"]),
        "slot_count": len(routes),
        "ready_slot_count": ready_count,
        "routes": routes,
        "ready_for_offline_consumer_validation": ready,
        "consumer_validation_completed": False,
        "configuration_epoch_advanced": False,
        "deployment_registry_updated": False,
        "qualification_installed": False,
        "camera_opened": False,
        "controller_started": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {**core, "handoff_sha256": _digest(core)}


def build_camera_arrival_consumer_handoff_v1(
    workspace: Path, evidence_root: Path
) -> dict[str, Any]:
    """Inspect originals and bind them to the current checkout's consumers."""

    preflight = inspect_camera_arrival_evidence_v1(workspace, evidence_root)
    consumer_map = build_camera_arrival_consumer_map_v1(workspace)
    return compose_camera_arrival_consumer_handoff_v1(preflight, consumer_map)


def parse_camera_arrival_consumer_handoff_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Fail closed on altered, incomplete, or authority-bearing receipts."""

    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise CameraArrivalConsumerHandoffV1Error(
            "handoff report fields differ from the v1 contract"
        )
    unsigned = dict(value)
    digest = unsigned.pop("handoff_sha256")
    if not _is_hash(digest) or _digest(unsigned) != digest:
        raise CameraArrivalConsumerHandoffV1Error("handoff hash mismatch")
    routes = value.get("routes")
    if not isinstance(routes, list) or len(routes) != len(REQUIRED_SLOT_IDS):
        raise CameraArrivalConsumerHandoffV1Error("handoff must contain 15 routes")
    if tuple(
        route.get("artifact_id") if isinstance(route, Mapping) else None
        for route in routes
    ) != REQUIRED_SLOT_IDS:
        raise CameraArrivalConsumerHandoffV1Error("handoff route identity differs")
    declared_ready = value.get("ready_for_offline_consumer_validation") is True
    all_routes_eligible = declared_ready and all(
        isinstance(route, Mapping)
        and route.get("preflight_status") == "VALID"
        and route.get("consumer_dependency_resolved") is True
        for route in routes
    )
    for route in routes:
        if not isinstance(route, Mapping) or set(route) != _ROUTE_FIELDS:
            raise CameraArrivalConsumerHandoffV1Error("handoff route fields differ")
        route_ready = route.get("ready_for_offline_consumer_validation") is True
        expected_ready = (
            all_routes_eligible
            and
            route.get("preflight_status") == "VALID"
            and route.get("consumer_dependency_resolved") is True
        )
        if (
            route.get("preflight_status") not in {"MISSING", "INVALID", "VALID"}
            or not isinstance(route.get("preflight_blockers"), list)
            or not _is_hash(route.get("consumer_source_sha256"))
            or not _is_hash(route.get("downstream_schema_sha256"))
            or not isinstance(route.get("consumer_source"), str)
            or not isinstance(route.get("downstream_schema"), str)
            or not isinstance(route.get("consumer_binding"), str)
            or route.get("consumer_validation_completed") is not False
            or route.get("physical_admission_ready") is not False
            or route_ready != expected_ready
        ):
            raise CameraArrivalConsumerHandoffV1Error(
                "handoff route semantics are inconsistent"
            )
    ready_count = sum(
        route["ready_for_offline_consumer_validation"] for route in routes
    )
    ready = declared_ready
    if (
        value.get("schema") != SCHEMA
        or not _is_hash(value.get("preflight_sha256"))
        or not _is_hash(value.get("consumer_map_sha256"))
        or value.get("slot_count") != 15
        or value.get("ready_slot_count") != ready_count
        or ready != (ready_count == 15)
        or value.get("status") != (READY_STATUS if ready else BLOCKED_STATUS)
        or value.get("consumer_validation_completed") is not False
        or any(value.get(field) is not False for field in (
            "configuration_epoch_advanced", "deployment_registry_updated",
            "qualification_installed", "camera_opened", "controller_started",
            "physical_authority",
        ))
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
    ):
        raise CameraArrivalConsumerHandoffV1Error(
            "handoff report semantics are inconsistent"
        )
    return MappingProxyType(dict(value))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bind arrival evidence to offline consumers without invoking them."
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = build_camera_arrival_consumer_handoff_v1(
            args.workspace, args.evidence_root
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready_for_offline_consumer_validation"] else 2


__all__ = [
    "BLOCKED_STATUS", "READY_STATUS", "SCHEMA",
    "CameraArrivalConsumerHandoffV1Error",
    "build_camera_arrival_consumer_handoff_v1",
    "compose_camera_arrival_consumer_handoff_v1", "main",
    "parse_camera_arrival_consumer_handoff_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())
