"""Capture the precommitted ChArUco dataset with no robot transport or motion."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXPORTS = ROOT / "software/runs/wizard-exports"


class CaptureGateError(ValueError):
    """Raised before camera access when physical or configuration evidence fails."""


def _load(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CaptureGateError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise CaptureGateError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_scale_evidence(
    target: dict[str, Any], evidence: dict[str, Any], *,
    target_sha256: str, pdf_sha256: str,
) -> dict[str, float]:
    if evidence.get("schema") != "rocell.charuco_print_scale_evidence.v1":
        raise CaptureGateError("print-scale evidence schema mismatch")
    if evidence.get("target_id") != target.get("target_id"):
        raise CaptureGateError("print-scale evidence target mismatch")
    if evidence.get("target_definition_sha256") != target_sha256:
        raise CaptureGateError("print-scale evidence does not bind this target definition")
    if evidence.get("printed_pdf_sha256") != pdf_sha256:
        raise CaptureGateError("print-scale evidence does not bind this printable PDF")
    for flag in (
        "rigid_backing_confirmed", "opposite_extents_measured", "distributed_across_board",
    ):
        if evidence.get(flag) is not True:
            raise CaptureGateError(f"required physical confirmation is false: {flag}")
    for field in ("instrument_id", "reviewed_by", "reviewed_utc"):
        value = evidence.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise CaptureGateError(f"missing or invalid evidence field: {field}")

    contract = target["print_contract"]
    tolerance = float(contract["maximum_axis_scale_error_fraction"])
    results: dict[str, float] = {}
    for field, minimum_key, expected in (
        ("horizontal_board_width_mm", "minimum_horizontal_measurements", target["board_width_mm"]),
        ("vertical_board_height_mm", "minimum_vertical_measurements", target["board_height_mm"]),
    ):
        values = evidence.get(field)
        minimum = int(contract[minimum_key])
        if not isinstance(values, list) or len(values) < minimum:
            raise CaptureGateError(f"{field} requires at least {minimum} measurements")
        measured: list[float] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise CaptureGateError(f"{field} contains a nonnumeric measurement")
            number = float(value)
            if not math.isfinite(number) or abs(number - expected) / expected > tolerance:
                raise CaptureGateError(f"{field} exceeds the {tolerance:.4%} scale tolerance")
            measured.append(number)
        results[f"{field}_mean"] = sum(measured) / len(measured)
    return results


def preflight(
    session_path: Path, target_path: Path, evidence_path: Path, pdf_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, float]]:
    session, target, evidence = _load(session_path), _load(target_path), _load(evidence_path)
    if target.get("schema") != "rocell.physical_charuco_target.v1":
        raise CaptureGateError("target definition schema mismatch")
    commitment = session.get("camera_baseline", {}).get("intrinsics_dataset_precommit", {})
    if commitment.get("status") != "AWAITING_SCALE_VERIFIED_TARGET_AND_CAPTURE":
        raise CaptureGateError("session is not awaiting the precommitted dataset")
    sequence = commitment.get("capture_sequence")
    if not isinstance(sequence, list) or len(sequence) != 26:
        raise CaptureGateError("capture sequence must contain exactly 26 precommitted views")
    if [row.get("sequence_ordinal") for row in sequence] != list(range(1, 27)):
        raise CaptureGateError("capture sequence ordinals are not exact")
    if [row.get("split") for row in sequence].count("FIT") != 20:
        raise CaptureGateError("capture sequence must contain exactly 20 fit views")
    if [row.get("split") for row in sequence].count("HOLDOUT") != 6:
        raise CaptureGateError("capture sequence must contain exactly 6 holdout views")
    committed_target = commitment.get("target", {})
    if committed_target.get("target_id") != target.get("target_id"):
        raise CaptureGateError("session target id differs from the supplied target")
    if committed_target.get("definition_sha256") != _sha256(target_path):
        raise CaptureGateError("session target-definition hash differs from the supplied target")
    if committed_target.get("printable_pdf_sha256") != _sha256(pdf_path):
        raise CaptureGateError("session printable-PDF hash differs from the supplied target")
    scope = target.get("profile_scope", {})
    mode = scope.get("operational_mode", {})
    camera = session.get("camera_baseline", {})
    negotiated = camera.get("negotiated_mode", {})
    for key in ("width_px", "height_px", "settings_sha256"):
        if mode.get(key) != negotiated.get(key):
            raise CaptureGateError(f"target operational profile differs from session: {key}")
    if mode.get("fourcc") != negotiated.get("fourcc"):
        raise CaptureGateError("target operational profile differs from session: fourcc")
    if abs(float(mode.get("fps", 0.0)) - float(negotiated.get("fps", 0.0))) > 0.01:
        raise CaptureGateError("target operational profile differs from session: fps")
    measurements = validate_scale_evidence(
        target, evidence, target_sha256=_sha256(target_path), pdf_sha256=_sha256(pdf_path),
    )
    return session, target, measurements


def assess_frame(jpeg: bytes, target: dict[str, Any]) -> dict[str, Any]:
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("captured JPEG cannot be decoded")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_1000)
    board = cv2.aruco.CharucoBoard(
        (target["squares_x"], target["squares_y"]),
        target["square_length_mm"] / 1000.0,
        target["marker_length_mm"] / 1000.0,
        dictionary,
    )
    marker_corners, marker_ids, rejected = cv2.aruco.ArucoDetector(dictionary).detectMarkers(gray)
    count = 0
    centroid = None
    charuco_corners = None
    if marker_ids is not None and hasattr(cv2.aruco, "CharucoDetector"):
        charuco_corners, charuco_ids, _corners, _ids = cv2.aruco.CharucoDetector(
            board
        ).detectBoard(gray, markerCorners=marker_corners, markerIds=marker_ids)
        count = 0 if charuco_ids is None else int(len(charuco_ids))
    elif marker_ids is not None:
        found, charuco_corners, _ids = cv2.aruco.interpolateCornersCharuco(
            marker_corners, marker_ids, gray, board,
        )
        count = int(found)
    if charuco_corners is not None and count:
        centroid = [float(v) for v in charuco_corners.reshape(-1, 2).mean(axis=0)]
    return {
        "detected_marker_count": 0 if marker_ids is None else int(len(marker_ids)),
        "detected_charuco_corner_count": count,
        "charuco_centroid_px": centroid,
        "rejected_quad_candidates": len(rejected),
        "accepted": count >= 30,
        "registration_authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--scale-evidence", type=Path, required=True)
    parser.add_argument("--printable-pdf", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--confirm-camera-only-capture", action="store_true")
    args = parser.parse_args()
    session, target, measurements = preflight(
        args.session.resolve(), args.target.resolve(), args.scale_evidence.resolve(),
        args.printable_pdf.resolve(),
    )
    if args.preflight_only:
        print(json.dumps({"ready": True, "measurements": measurements}, indent=2))
        return 0
    if not args.confirm_camera_only_capture:
        parser.error("explicit camera-only capture confirmation is required")
    output = args.output_directory.resolve()
    if output.parent != EXPORTS.resolve() or output.exists():
        parser.error("output must be a new direct child of wizard-exports")
    output.mkdir()

    sys.path.insert(0, str(ROOT / "software/src"))
    import cv2
    from rocell.vision.usb_opencv import UsbOpenCvCamera
    from live_camera_read_only_intake import observe_pnp

    camera_record = session["camera_baseline"]
    mode = target["profile_scope"]["operational_mode"]
    selector = camera_record["capture_selector"]["opencv_index"]
    identity = camera_record["persistent_device_identity"]
    name = camera_record["physical_identity"]["friendly_name"]
    manifest: dict[str, Any] = {
        "schema": "rocell.live_charuco_dataset_capture.v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "target_id": target["target_id"],
        "target_definition_sha256": _sha256(args.target.resolve()),
        "printable_pdf_sha256": _sha256(args.printable_pdf.resolve()),
        "scale_measurement_summary": measurements,
        "mode": mode,
        "views": [],
        "rejections": [],
        "authority": {"camera_capture": True, "intrinsics_valid": False,
                      "registration": False, "robot_transport_opened": False,
                      "robot_motion": False, "descent": False, "contact": False,
                      "autonomous_retry": False},
    }
    camera = UsbOpenCvCamera(
        selector, identity=identity, width_px=mode["width_px"],
        height_px=mode["height_px"], fps=mode["fps"], pixel_format=mode["fourcc"],
        backend=cv2.CAP_DSHOW, jpeg_quality=95, max_jpeg_bytes=32 * 1024 * 1024,
        observed_identity_provider=lambda selected: (
            observe_pnp(identity, name)["instance_id"] if selected == selector else None
        ), require_identity_match=True,
    )
    try:
        observe_pnp(identity, name)
        camera.open()
        status = camera.probe()
        if status.settings_hash != mode["settings_sha256"]:
            raise RuntimeError("camera settings hash differs from the precommitted profile")
        for row in camera_record["intrinsics_dataset_precommit"]["capture_sequence"]:
            answer = input(
                f"Place target for {row['image_id']} ({row['required_view']}); Enter=capture, q=stop: "
            ).strip().lower()
            if answer == "q":
                break
            frame = camera.capture()
            assessment = assess_frame(frame.jpeg_bytes, target)
            prefix = "accepted" if assessment["accepted"] else "rejected"
            name_part = f"{row['sequence_ordinal']:02d}-{row['image_id']}.jpg"
            filename = f"{prefix}-{name_part}"
            (output / filename).write_bytes(frame.jpeg_bytes)
            record = {
                **row, "file_name": filename,
                "sha256": hashlib.sha256(frame.jpeg_bytes).hexdigest(),
                "settings_sha256": frame.settings_hash,
                "assessment": assessment,
            }
            (manifest["views"] if assessment["accepted"] else manifest["rejections"]).append(record)
            if not assessment["accepted"]:
                print("Rejected: fewer than 30 ChArUco corners; restart a new declared dataset epoch.")
                break
    finally:
        camera.close()
        manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["accepted_view_count"] = len(manifest["views"])
        manifest["complete"] = len(manifest["views"]) == 26 and not manifest["rejections"]
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n",
        )
    print(json.dumps({"output": str(output), "complete": manifest["complete"]}, indent=2))
    return 0 if manifest["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
