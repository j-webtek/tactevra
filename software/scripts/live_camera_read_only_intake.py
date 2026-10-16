"""Create a bounded camera-only intake receipt; never access the robot."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
EXPORTS = ROOT / "software" / "runs" / "wizard-exports"
PNP_PATTERN = re.compile(
    r"USB\\VID_[0-9A-F]{4}&PID_[0-9A-F]{4}(?:&MI_[0-9A-F]{2})?\\[^\x00\r\n]+"
)
REQUIRED_TAG_IDS = frozenset(range(6))


def _identity(value: str) -> str:
    result = value.strip().upper()
    if not PNP_PATTERN.fullmatch(result):
        raise ValueError("expected one exact USB PnP instance ID")
    return result


def _name(value: str) -> str:
    result = value.strip()
    if not result or len(result) > 256 or any(c in result for c in "\x00\r\n"):
        raise ValueError("friendly name must be bounded single-line text")
    return result


def observe_pnp(identity: str, name: str) -> dict[str, str]:
    """Observe one exact present Camera/Image entry without opening it."""

    identity, name = _identity(identity), _name(name)
    command = (
        "$id=$env:ROCELL_CAMERA_PNP_ID;$name=$env:ROCELL_CAMERA_FRIENDLY_NAME;"
        "$x=@(Get-PnpDevice -PresentOnly|?{$_.Class -in @('Camera','Image') "
        "-and $_.InstanceId -eq $id -and $_.FriendlyName -eq $name});"
        "$x|select Status,Class,FriendlyName,InstanceId|ConvertTo-Json -Compress"
    )
    environment = os.environ.copy()
    environment["ROCELL_CAMERA_PNP_ID"] = identity
    environment["ROCELL_CAMERA_FRIENDLY_NAME"] = name
    run = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env=environment,
    )
    if run.returncode:
        raise RuntimeError("Windows PnP inventory failed")
    text = run.stdout.decode("utf-8", errors="strict").strip()
    if not text:
        raise RuntimeError("exact present PnP camera was not observed")
    value = json.loads(text)
    rows = value if isinstance(value, list) else [value]
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise RuntimeError("exact PnP camera is missing or ambiguous")
    row = rows[0]
    observed = {
        "status": str(row.get("Status", "")),
        "class": str(row.get("Class", "")),
        "friendly_name": str(row.get("FriendlyName", "")),
        "instance_id": str(row.get("InstanceId", "")).upper(),
    }
    if observed != {
        "status": "OK", "class": "Camera", "friendly_name": name,
        "instance_id": identity,
    }:
        raise RuntimeError("PnP observation differs from requested camera")
    return observed


def assess_jpeg(payload: bytes, cv2: object) -> dict[str, object]:
    """Return diagnostic pixels/tag coverage with zero registration authority."""

    import numpy as np

    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("captured JPEG cannot be decoded")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    _corners, ids, rejected = detector.detectMarkers(gray)
    detected = sorted([] if ids is None else {int(item) for item in ids.flatten()})
    return {
        "mean_luma_8bit": float(gray.mean()),
        "fraction_luma_le_8": float((gray <= 8).mean()),
        "fraction_luma_ge_247": float((gray >= 247).mean()),
        "laplacian_variance": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "detected_tag36h11_ids": detected,
        "required_tag36h11_ids": sorted(REQUIRED_TAG_IDS),
        "all_required_tags_visible": REQUIRED_TAG_IDS.issubset(detected),
        "rejected_quad_candidates": len(rejected),
        "registration_authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pnp-instance-id", required=True)
    parser.add_argument("--friendly-name", required=True)
    parser.add_argument("--selector", required=True, type=int)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=float, default=60.0)
    parser.add_argument("--fourcc", default="YUY2")
    parser.add_argument("--reopen-count", type=int, default=2)
    parser.add_argument("--frames-per-open", type=int, default=2)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--confirm-camera-only-capture", action="store_true")
    args = parser.parse_args()
    if not args.confirm_camera_only_capture:
        parser.error("explicit camera-only capture confirmation is required")
    if args.selector < 0 or not 1 <= args.reopen_count <= 3:
        parser.error("selector/reopen-count is outside the bounded range")
    if not 1 <= args.frames_per_open <= 5:
        parser.error("frames-per-open must be 1..5")
    if args.width < 16 or args.height < 16 or args.fps <= 0:
        parser.error("capture mode is invalid")
    if not re.fullmatch(r"[A-Za-z0-9]{4}", args.fourcc):
        parser.error("fourcc must be four ASCII letters/digits")
    identity, name = _identity(args.pnp_instance_id), _name(args.friendly_name)
    output = args.output_directory.resolve()
    if output.parent != EXPORTS.resolve() or output.exists():
        parser.error("output must be a new direct child of wizard-exports")
    output.mkdir()

    sys.path.insert(0, str(ROOT / "software" / "src"))
    import cv2
    from rocell.vision.usb_opencv import UsbOpenCvCamera

    receipt = {
        "schema": "rocell.live_camera_read_only_intake.v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "friendly_name": name,
        "persistent_device_identity": identity,
        "opencv_selector": args.selector,
        "numeric_selector_is_identity": False,
        "requested_mode": {"width_px": args.width, "height_px": args.height,
                           "fps": args.fps, "fourcc": args.fourcc.upper(),
                           "backend": "CAP_DSHOW"},
        "reopen_cycles": [],
        "authority": {"camera_capture_performed": False, "registration": False,
                      "camera_guided_motion": False, "robot_transport_opened": False,
                      "robot_motion": False, "descent": False, "contact": False,
                      "autonomous_retry": False},
        "limitations": [
            "PnP presence does not independently prove OpenCV index mapping.",
            "Electronic camera controls were not read or changed.",
            "Host receipt times are not sensor exposure times.",
            "Tag visibility grants no registration or motion authority.",
        ],
    }
    camera = None
    code = 1
    try:
        for cycle_index in range(args.reopen_count):
            pnp = observe_pnp(identity, name)
            camera = UsbOpenCvCamera(
                args.selector, identity=identity, width_px=args.width,
                height_px=args.height, fps=args.fps, pixel_format=args.fourcc,
                backend=cv2.CAP_DSHOW, jpeg_quality=95,
                max_jpeg_bytes=32 * 1024 * 1024,
                observed_identity_provider=lambda selector: (
                    observe_pnp(identity, name)["instance_id"]
                    if selector == args.selector else None),
                require_identity_match=True,
            )
            camera.open()
            status = camera.probe()
            cycle = {
                "reopen_ordinal": cycle_index, "pnp_observation": pnp,
                "negotiated_mode": {"width_px": status.width_px,
                    "height_px": status.height_px, "fps": status.fps,
                    "identity": status.identity,
                    "persistent_identity": status.persistent_identity,
                    "settings_sha256": status.settings_hash,
                    "details": dict(status.details)},
                "frames": [],
            }
            for frame_index in range(args.frames_per_open):
                frame = camera.capture()
                file_name = f"reopen-{cycle_index:02d}-frame-{frame_index:02d}.jpg"
                (output / file_name).write_bytes(frame.jpeg_bytes)
                cycle["frames"].append({
                    "file_name": file_name, "byte_length": len(frame.jpeg_bytes),
                    "sha256": hashlib.sha256(frame.jpeg_bytes).hexdigest(),
                    "width_px": frame.width_px, "height_px": frame.height_px,
                    "capture_id": frame.capture_id,
                    "host_request_ns": frame.host_request_ns,
                    "host_first_byte_ns": frame.host_first_byte_ns,
                    "host_complete_ns": frame.host_complete_ns,
                    "settings_sha256": frame.settings_hash,
                    "timestamp_quality": frame.timestamp_quality.value,
                    "scene_assessment": assess_jpeg(frame.jpeg_bytes, cv2),
                })
            camera.close()
            camera = None
            cycle["camera_closed"] = True
            receipt["reopen_cycles"].append(cycle)
        frames = [f for c in receipt["reopen_cycles"] for f in c["frames"]]
        hashes = {f["sha256"] for f in frames}
        settings = {c["negotiated_mode"]["settings_sha256"]
                    for c in receipt["reopen_cycles"]}
        tags_ok = any(f["scene_assessment"]["all_required_tags_visible"]
                      for f in frames)
        receipt["summary"] = {"frame_count": len(frames),
            "unique_frame_hash_count": len(hashes),
            "all_frame_hashes_unique": len(hashes) == len(frames),
            "settings_stable_after_reopen": len(settings) == 1,
            "all_required_tags_visible_in_one_frame": tags_ok}
        receipt["authority"]["camera_capture_performed"] = True
        receipt["status"] = ("CAPTURED_REVIEW_REQUIRED" if tags_ok else
                             "CAPTURED_REGISTRATION_BLOCKED_TAG_COVERAGE")
        code = 0
    except Exception as exc:
        receipt["status"] = "FAILED_REVIEW_REQUIRED"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if camera is not None:
            camera.close()
        receipt["completed_utc"] = datetime.now(timezone.utc).isoformat()
        receipt["camera_closed"] = camera is None or not camera.is_open
        with (output / "receipt.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
    print(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
