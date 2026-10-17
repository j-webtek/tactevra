"""Reconcile retained board measurements with physical-intrinsics target needs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "rocell.static_intrinsics_target_reconciliation.v1"
STATUS = "FIXED_BOARD_RECONCILED_MOVABLE_TARGET_REQUIRED"

_BOARD = Path("software/ai/eval/physical_installed_apriltag_xy_working_v1.json")
_REGISTRATION = Path("software/ai/eval/b0477_fixed_board_registration_20261016.json")
_CONTRACT = Path("software/ai/eval/static_intrinsics_multiview_capture_contract_20261016.json")
_LEGACY_PROBE = Path("software/ai/eval/physical_charuco_probe_blocked_v1.json")


class StaticIntrinsicsTargetReconciliationError(ValueError):
    """A retained target or board source is missing, malformed, or inconsistent."""


def _without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StaticIntrinsicsTargetReconciliationError(
                f"duplicate JSON field {key!r}"
            )
        result[key] = value
    return result


def _read(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(
            path.read_bytes(),
            object_pairs_hook=_without_duplicates,
            parse_constant=lambda item: (_ for _ in ()).throw(
                StaticIntrinsicsTargetReconciliationError(
                    f"nonfinite JSON constant {item!r}"
                )
            ),
        )
    except OSError as exc:
        raise StaticIntrinsicsTargetReconciliationError(
            f"target reconciliation source is unavailable: {path}"
        ) from exc
    if not isinstance(value, Mapping):
        raise StaticIntrinsicsTargetReconciliationError(
            f"target reconciliation source must be an object: {path}"
        )
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StaticIntrinsicsTargetReconciliationError(f"{label} must be an object")
    return value


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
        raise StaticIntrinsicsTargetReconciliationError(
            "target reconciliation cannot be canonicalized"
        ) from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reconcile_static_intrinsics_target(workspace: Path) -> dict[str, Any]:
    """Preserve completed board metrology and identify the remaining target need."""

    root = Path(workspace)
    board_path = root / _BOARD
    registration_path = root / _REGISTRATION
    contract_path = root / _CONTRACT
    legacy_path = root / _LEGACY_PROBE
    board = _read(board_path)
    registration = _read(registration_path)
    contract = _read(contract_path)
    legacy = _read(legacy_path)

    if (
        board.get("schema") != "rocell.working_installed_apriltag_xy.v1"
        or registration.get("schema")
        != "rocell.fixed_apriltag_board_registration.v1"
        or contract.get("schema")
        != "rocell.static_intrinsics_multiview_capture_contract.v1"
    ):
        raise StaticIntrinsicsTargetReconciliationError(
            "retained board or capture contract schema differs"
        )
    if registration.get("status") != "MEASURED_FIXED_EPOCH_PLANAR_MAPPING":
        raise StaticIntrinsicsTargetReconciliationError(
            "fixed-board planar mapping is not retained"
        )
    if contract.get("capture_ready") is not False:
        raise StaticIntrinsicsTargetReconciliationError(
            "capture contract unexpectedly claims readiness"
        )

    installed = _mapping(board.get("installed_tag_geometry"), "installed tag geometry")
    board_shape = _mapping(board.get("board"), "board")
    tags = _mapping(board.get("tags"), "tags")
    tag_centers = {
        name: _mapping(value, f"tags.{name}").get("working_detection_center_xy_mm")
        for name, value in tags.items()
    }
    validation = _mapping(registration.get("validation"), "registration validation")
    production = _mapping(legacy.get("production_board_contract"), "legacy production target")

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "source_bindings": {
            "installed_apriltag_xy": {
                "path": _BOARD.as_posix(),
                "sha256": _sha256(board_path),
            },
            "fixed_board_registration": {
                "path": _REGISTRATION.as_posix(),
                "sha256": _sha256(registration_path),
            },
            "multiview_capture_contract": {
                "path": _CONTRACT.as_posix(),
                "sha256": _sha256(contract_path),
                "contract_sha256": contract.get("contract_sha256"),
            },
            "legacy_charuco_probe": {
                "path": _LEGACY_PROBE.as_posix(),
                "sha256": _sha256(legacy_path),
            },
        },
        "completed_fixed_board_evidence": {
            "board_size_xy_mm": board_shape.get("size_xy_mm"),
            "tag_family": installed.get("family"),
            "tag_detection_edge_mm": installed.get("detection_edge_mm"),
            "tag_tile_edge_mm": installed.get("tile_edge_mm"),
            "tag_centers_xy_mm": tag_centers,
            "tag_ids": sorted(
                int(_mapping(value, f"tags.{name}").get("id"))
                for name, value in tags.items()
            ),
            "repeat_board_or_tag_measurements_required": False,
            "eligible_for_fixed_epoch_planar_mapping": True,
            "source_frame_count": validation.get("source_frame_count"),
            "fit_eligible_frame_count": validation.get("fit_eligible_frame_count"),
        },
        "intrinsics_observability_decision": {
            "fixed_camera": True,
            "fixed_board": True,
            "distinct_plane_poses_in_retained_board_frames": 1,
            "fixed_board_eligible_as_multiview_intrinsics_dataset": False,
            "reason": (
                "One fixed planar pose supports the retained image-to-board "
                "homography but cannot independently constrain focal length and "
                "lens distortion for the commissioned camera."
            ),
            "existing_board_measurements_are_rejected": False,
        },
        "legacy_target_record": {
            "definition": dict(production),
            "physical_asset_retained": legacy.get("production_board_asset_retained"),
            "physical_scale_verified": legacy.get(
                "production_board_physical_print_scale_verified"
            ),
            "rigid_backing_verified": legacy.get(
                "production_board_rigid_backing_verified"
            ),
            "eligible_for_capture": False,
            "reason": "The definition exists, but no matching physical target was retained.",
        },
        "accepted_existing_target_classes": [
            {
                "target_class": "CHARUCO",
                "required_identity": [
                    "dictionary",
                    "squares_x",
                    "squares_y",
                    "square_length_mm",
                    "marker_length_mm",
                ],
            },
            {
                "target_class": "APRILTAG_GRID",
                "required_identity": [
                    "dictionary",
                    "ordered_tag_ids",
                    "metric_corner_coordinates_xy_mm",
                ],
            },
        ],
        "existing_target_binding_requirements": [
            "immutable target identity and feature definition",
            "metric scale provenance across both target axes",
            "at least 30 detectable non-collinear feature corners per accepted view",
            "rigid flat backing witness",
            "one unchanged physical target through all precommitted slots",
        ],
        "collection_policy": {
            "new_target_print_requested": False,
            "move_existing_target_only": True,
            "camera_and_installed_board_remain_fixed": True,
            "arm_motion_required": False,
            "robot_transport_opened": False,
            "robot_commands_sent": 0,
        },
        "next_action": "BIND_EXISTING_MOVABLE_PLANAR_TARGET_THEN_CAPTURE_SLOT_01",
        "capture_ready": False,
        "authority": {
            "camera_opened": False,
            "camera_frames_requested": 0,
            "robot_transport_opened": False,
            "robot_commands_sent": 0,
            "physical_authority": False,
        },
    }
    return {
        **report,
        "reconciliation_sha256": hashlib.sha256(_canonical(report)).hexdigest(),
    }


__all__ = [
    "SCHEMA",
    "STATUS",
    "StaticIntrinsicsTargetReconciliationError",
    "reconcile_static_intrinsics_target",
]
