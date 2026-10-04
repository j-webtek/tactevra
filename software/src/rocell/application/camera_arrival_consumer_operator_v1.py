"""Uniform offline operator boundary for camera-arrival consumer receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.calibration.planner_snapshot import PlannerCalibrationSnapshot

from .camera_arrival_consumer_emitters_v1 import (
    CameraArrivalConsumerEmitterV1Error,
    emit_camera_campaign_consumer_receipt_v1,
    emit_camera_localization_consumer_receipt_v1,
    emit_camera_support_consumer_receipt_v1,
    emit_installed_collision_consumer_receipt_v1,
    emit_planner_snapshot_consumer_receipt_v1,
)
from .camera_arrival_consumer_validation_v1 import (
    parse_camera_arrival_consumer_validation_receipt_v1,
)
from .installed_collision_geometry import InstalledCollisionGeometryProfile
from .installed_cable_envelope_intake_v1 import InstalledCableEnvelopeIntakeV1


MAX_INPUT_BYTES = 2_097_152
SUPPORT_IDS = {
    "camera_receipt", "camera_identity", "camera_mode_controls", "support_witnesses",
}
CAMPAIGN_IDS = {"camera_intrinsics", "localization_campaign"}
LOCALIZATION_IDS = {"camera_to_board_transform", "localization_evaluation"}
PLANNER_IDS = {
    "board_to_robot_transform", "keyboard_to_board_transform",
    "tool_to_joint_transform", "keyboard_profile", "tool_profile",
}
COLLISION_IDS = {"installed_geometry", "cable_envelope"}


class CameraArrivalConsumerOperatorV1Error(ValueError):
    """The operator request, native output, or output root is unsafe."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CameraArrivalConsumerOperatorV1Error(
                f"duplicate JSON member: {key}"
            )
        value[key] = item
    return value


def _load_json(path: Path, *, label: str) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CameraArrivalConsumerOperatorV1Error(
            f"{label} must be a regular non-symlink file"
        )
    size = path.stat().st_size
    if not 1 <= size <= MAX_INPUT_BYTES:
        raise CameraArrivalConsumerOperatorV1Error(
            f"{label} size is outside the bounded contract"
        )
    try:
        value = json.loads(
            path.read_bytes().decode("utf-8"), object_pairs_hook=_unique_object
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CameraArrivalConsumerOperatorV1Error(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise CameraArrivalConsumerOperatorV1Error(f"{label} must be an object")
    return value


def _output_root(path: Path) -> Path:
    resolved = path.resolve()
    if path.is_symlink() or not resolved.is_dir():
        raise CameraArrivalConsumerOperatorV1Error(
            "output root must be an existing non-symlink directory"
        )
    return resolved


def emit_camera_arrival_consumer_operator_receipt_v1(
    handoff: Mapping[str, Any], artifact_id: str,
    native_output: Mapping[str, Any] | PlannerCalibrationSnapshot
    | InstalledCollisionGeometryProfile | InstalledCableEnvelopeIntakeV1,
    *, validated_at_utc: str,
) -> dict[str, Any]:
    """Dispatch one route to its existing typed emitter without changing semantics."""

    try:
        if artifact_id in SUPPORT_IDS:
            if not isinstance(native_output, Mapping):
                raise CameraArrivalConsumerOperatorV1Error(
                    "support native output must be a mapping"
                )
            receipt = emit_camera_support_consumer_receipt_v1(
                handoff, artifact_id, native_output,
                validated_at_utc=validated_at_utc,
            )
        elif artifact_id in CAMPAIGN_IDS:
            if not isinstance(native_output, Mapping):
                raise CameraArrivalConsumerOperatorV1Error(
                    "campaign native output must be a mapping"
                )
            receipt = emit_camera_campaign_consumer_receipt_v1(
                handoff, artifact_id, native_output,
                validated_at_utc=validated_at_utc,
            )
        elif artifact_id in LOCALIZATION_IDS:
            if not isinstance(native_output, Mapping):
                raise CameraArrivalConsumerOperatorV1Error(
                    "localization native output must be a mapping"
                )
            receipt = emit_camera_localization_consumer_receipt_v1(
                handoff, artifact_id, native_output,
                validated_at_utc=validated_at_utc,
            )
        elif artifact_id in PLANNER_IDS:
            if not isinstance(native_output, PlannerCalibrationSnapshot):
                raise CameraArrivalConsumerOperatorV1Error(
                    "planner native output must be a typed PlannerCalibrationSnapshot"
                )
            receipt = emit_planner_snapshot_consumer_receipt_v1(
                handoff, artifact_id, native_output,
                validated_at_utc=validated_at_utc,
            )
        elif artifact_id in COLLISION_IDS:
            if not isinstance(native_output, (
                InstalledCollisionGeometryProfile, InstalledCableEnvelopeIntakeV1,
            )):
                raise CameraArrivalConsumerOperatorV1Error(
                    "collision native output must be a typed installed profile or cable intake"
                )
            receipt = emit_installed_collision_consumer_receipt_v1(
                handoff, artifact_id, native_output,
                validated_at_utc=validated_at_utc,
            )
        else:
            raise CameraArrivalConsumerOperatorV1Error(
                f"unsupported arrival artifact: {artifact_id}"
            )
    except CameraArrivalConsumerEmitterV1Error as exc:
        raise CameraArrivalConsumerOperatorV1Error(str(exc)) from exc
    return dict(parse_camera_arrival_consumer_validation_receipt_v1(receipt))


def write_camera_arrival_consumer_operator_receipt_v1(
    handoff: Mapping[str, Any], artifact_id: str,
    native_output: Mapping[str, Any] | PlannerCalibrationSnapshot
    | InstalledCollisionGeometryProfile | InstalledCableEnvelopeIntakeV1,
    *, validated_at_utc: str, output_root: Path,
) -> tuple[dict[str, Any], Path]:
    """Emit and exclusively create one canonical `<artifact_id>.json` receipt."""

    root = _output_root(output_root)
    receipt = emit_camera_arrival_consumer_operator_receipt_v1(
        handoff, artifact_id, native_output, validated_at_utc=validated_at_utc
    )
    destination = root / f"{artifact_id}.json"
    try:
        with destination.open("xb") as stream:
            stream.write(_canonical(receipt))
    except FileExistsError as exc:
        raise CameraArrivalConsumerOperatorV1Error(
            f"receipt already exists and will not be overwritten: {artifact_id}"
        ) from exc
    return receipt, destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Emit one mapping-based camera-arrival consumer receipt. Typed "
            "planner/collision outputs use the same Python operator function."
        )
    )
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--native-output", type=Path, required=True)
    parser.add_argument("--validated-at-utc", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.artifact_id in PLANNER_IDS | COLLISION_IDS:
        parser.error(
            "typed planner/collision outputs must use the Python operator boundary"
        )
    try:
        handoff = _load_json(args.handoff, label="handoff")
        native = _load_json(args.native_output, label="native output")
        receipt, path = write_camera_arrival_consumer_operator_receipt_v1(
            handoff, args.artifact_id, native,
            validated_at_utc=args.validated_at_utc,
            output_root=args.output_root,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({
        "artifact_id": receipt["artifact_id"],
        "validation_status": receipt["validation_status"],
        "blockers": receipt["blockers"],
        "receipt_sha256": receipt["receipt_sha256"],
        "output_relative_path": path.name,
        "camera_opened": False, "transport_opened": False,
        "controller_started": False, "hardware_writes": 0,
        "physical_movements": 0, "physical_authority": False,
    }, indent=2, sort_keys=True))
    return 0 if receipt["validation_status"] == "PASS" else 2


__all__ = [
    "CameraArrivalConsumerOperatorV1Error",
    "emit_camera_arrival_consumer_operator_receipt_v1", "main",
    "write_camera_arrival_consumer_operator_receipt_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())
