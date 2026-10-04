"""Repository-bound PC9 map from arrival originals to existing consumers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .camera_arrival_kit_v1 import REQUIRED_SLOT_IDS


SCHEMA = "rocell.camera_arrival_consumer_map.v1"
STATUS = "BLOCKED_SYNTHETIC_DRY_RUN_ONLY"

_SUPPORT = "software/src/rocell/application/camera_support_optics_epoch_intake_v1.py"
_PLANNER = "software/src/rocell/calibration/planner_snapshot.py"
_COLLISION = "software/src/rocell/application/installed_collision_geometry.py"
_PREFLIGHT = "software/ai/eval/preflight_physical_camera_campaign.py"
_EVALUATOR = "software/ai/eval/evaluate_physical_camera_localization.py"
_SIDECAR = "software/ai/schemas/camera_arrival_original_v1.schema.json"
_PLANNER_SCHEMA = "software/ai/schemas/planner_calibration_snapshot_v1.schema.json"
_COLLISION_SCHEMA = (
    "software/ai/schemas/installed_collision_geometry_profile_v1.schema.json"
)
_CAMPAIGN_SCHEMA = (
    "software/ai/schemas/physical_camera_localization_campaign_v1.schema.json"
)
_EVALUATION_SCHEMA = (
    "software/ai/schemas/physical_camera_localization_evaluation_result_v1.schema.json"
)

_ROWS = (
    ("camera_receipt", _SUPPORT, _SIDECAR, "camera_receipt"),
    ("camera_identity", _SUPPORT, _SIDECAR, "camera_identity"),
    ("camera_mode_controls", _SUPPORT, _SIDECAR, "camera_mode_controls"),
    ("support_witnesses", _SUPPORT, _SIDECAR, "support_witnesses"),
    ("camera_intrinsics", _PREFLIGHT, _CAMPAIGN_SCHEMA,
     "camera_intrinsics_sha256"),
    ("camera_to_board_transform", _EVALUATOR, _EVALUATION_SCHEMA,
     "uncertainty_components.camera_to_board"),
    ("board_to_robot_transform", _PLANNER, _PLANNER_SCHEMA,
     "arm_board:B_T_Wv"),
    ("keyboard_to_board_transform", _PLANNER, _PLANNER_SCHEMA,
     "keyboard_pose:B_T_keyboard"),
    ("tool_to_joint_transform", _PLANNER, _PLANNER_SCHEMA,
     "keyboard_tcp:G_T_T"),
    ("installed_geometry", _COLLISION, _COLLISION_SCHEMA,
     "installed_collision_geometry_profile"),
    ("cable_envelope", _COLLISION, _COLLISION_SCHEMA,
     "attachment:moving_camera_cable"),
    ("keyboard_profile", _PLANNER, _PLANNER_SCHEMA,
     "target_map_sha256"),
    ("tool_profile", _PLANNER, _PLANNER_SCHEMA,
     "keyboard_tcp.tool_identity_hash"),
    ("localization_campaign", _PREFLIGHT, _CAMPAIGN_SCHEMA,
     "physical_camera_localization_campaign"),
    ("localization_evaluation", _EVALUATOR, _EVALUATION_SCHEMA,
     "physical_camera_localization_evaluation_result"),
)


class CameraArrivalConsumerMapV1Error(ValueError):
    """Consumer mapping is incomplete or no longer repository-resolvable."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _resolve(workspace: Path, relative: str) -> Path:
    root = workspace.resolve()
    path = (root / relative).resolve()
    if root not in path.parents or not path.is_file() or path.is_symlink():
        raise CameraArrivalConsumerMapV1Error(
            f"consumer dependency is unavailable: {relative}")
    return path


def build_camera_arrival_consumer_map_v1(workspace: Path) -> dict[str, Any]:
    if tuple(row[0] for row in _ROWS) != REQUIRED_SLOT_IDS:
        raise CameraArrivalConsumerMapV1Error("arrival slot coverage differs")
    dependencies: dict[str, str] = {}
    mappings = []
    for slot_id, consumer, downstream_schema, binding in _ROWS:
        for relative in (consumer, downstream_schema):
            dependencies.setdefault(
                relative, _hash_bytes(_resolve(workspace, relative).read_bytes()))
        mappings.append({
            "artifact_id": slot_id,
            "consumer_source": consumer,
            "consumer_source_sha256": dependencies[consumer],
            "downstream_schema": downstream_schema,
            "downstream_schema_sha256": dependencies[downstream_schema],
            "consumer_binding": binding,
            "consumer_dependency_resolved": True,
            "physical_original_present": False,
            "physical_admission_ready": False,
        })
    core = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_class": "SYNTHETIC_DRY_RUN_ONLY",
        "slot_count": len(mappings),
        "mappings": mappings,
        "dependency_hashes": [
            {"path": path, "sha256": digest}
            for path, digest in sorted(dependencies.items())
        ],
        "measured_originals_consumed": 0,
        "configuration_epoch_advanced": False,
        "deployment_registry_updated": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {
        **core,
        "consumer_map_sha256": _hash_bytes(_canonical(core)),
    }


__all__ = [
    "SCHEMA", "STATUS", "CameraArrivalConsumerMapV1Error",
    "build_camera_arrival_consumer_map_v1",
]
