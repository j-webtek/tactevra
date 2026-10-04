"""Probe physical ChArUco readiness without opening a camera."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = AI_ROOT / "schemas" / "physical_charuco_probe_v1.schema.json"


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_hash(value: Any) -> str:
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return sha256_bytes(data)


def _device_count(output: str) -> int:
    if "No devices were found on the system." in output:
        return 0
    return output.count("Instance ID:")


def build_receipt(
    *, source_commit: str, camera_output: bytes, image_output: bytes,
    opencv: dict[str, Any], board_definition_path: Path, board_pdf_path: Path,
) -> dict[str, Any]:
    definition = load_json(board_definition_path)
    camera_count = _device_count(camera_output.decode("utf-8", errors="replace"))
    image_count = _device_count(image_output.decode("utf-8", errors="replace"))
    blocked = []
    if camera_count + image_count == 0:
        blocked.append("no_connected_windows_camera_or_image_device")
    blocked.extend([
        "production_charuco_target_not_retained_or_print_verified",
        "production_charuco_rigid_backing_not_verified",
    ])
    status = "BLOCKED" if blocked else "READY_FOR_MANUAL_CAPTURE"
    core = {
        "schema": "tactevra.ai_physical_charuco_probe.v1",
        "scope": "READ_ONLY_DEVICE_AND_TOOLING_PROBE_NO_CALIBRATION",
        "status": status,
        "source_commit": source_commit,
        "commands": [
            "pnputil /enum-devices /connected /class Camera",
            "pnputil /enum-devices /connected /class Image",
        ],
        "camera_class_device_count": camera_count,
        "image_class_device_count": image_count,
        "camera_command_output_sha256": sha256_bytes(camera_output),
        "image_command_output_sha256": sha256_bytes(image_output),
        "opencv": opencv,
        "tooling_smoke_board_definition": definition,
        "tooling_smoke_board_definition_sha256": sha256_bytes(board_definition_path.read_bytes()),
        "tooling_smoke_board_pdf_sha256": sha256_bytes(board_pdf_path.read_bytes()),
        "production_board_contract": {
            "camera_model": "Arducam B0477",
            "native_width_px": 5472,
            "native_height_px": 3648,
            "capture_fps": 4,
            "pixel_format": "YUY2",
            "dictionary": "DICT_5X5_1000",
            "squares_x": 12,
            "squares_y": 9,
            "square_length_mm": 30.0,
            "marker_length_mm": 22.0,
            "rigid_backing_required": True,
        },
        "production_board_asset_retained": False,
        "production_board_physical_print_scale_verified": False,
        "production_board_rigid_backing_verified": False,
        "capture_count": 0,
        "calibration_solved": False,
        "reprojection_error_px": None,
        "diagnostic_reprojection_target_px": 0.5,
        "diagnostic_target_is_qualification_threshold": False,
        "blocked_reasons": blocked,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "No camera was opened and no physical image was captured.",
            "The retained 5x7 generated board asset was detected only as an OpenCV tooling smoke; it does not satisfy the production 12x9 target contract.",
            "The production 12x9 target asset, physical print scale, and rigid backing are not retained or verified.",
            "A B0477 identity, exact 5472x3648 YUY2 4 fps runtime mode, broad frame coverage, and held-out reprojection evidence remain required.",
        ],
    }
    result = {**core, "report_sha256": canonical_hash(core)}
    schema = load_json(SCHEMA)
    errors = sorted(Draft202012Validator(schema).iter_errors(result), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        raise ValueError(f"schema validation failed at {list(first.path)}: {first.message}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--board-definition", type=Path, required=True)
    parser.add_argument("--board-pdf", type=Path, required=True)
    parser.add_argument("--vision-python", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    command_outputs = []
    for class_name in ("Camera", "Image"):
        completed = subprocess.run(
            ["pnputil", "/enum-devices", "/connected", "/class", class_name],
            check=False, capture_output=True,
        )
        raw = completed.stdout + completed.stderr
        (args.raw_dir / f"pnputil-{class_name.lower()}.txt").write_bytes(raw)
        command_outputs.append(raw)
    smoke_code = (
        "import cv2,numpy as np,json;"
        "d=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100);"
        "b=cv2.aruco.CharucoBoard((5,7),.025,.0175,d);"
        f"im=cv2.imread({str(args.board_pdf.with_name('charuco_5x7_square25_marker17_5.png'))!r});"
        "c,i,mc,mi=cv2.aruco.CharucoDetector(b).detectBoard(im);"
        "print(json.dumps({'opencv_version':cv2.__version__,'numpy_version':np.__version__,"
        "'aruco_available':hasattr(cv2,'aruco'),'generated_asset_charuco_corners':0 if i is None else len(i)}))"
    )
    completed = subprocess.run(
        [str(args.vision_python), "-c", smoke_code], check=True, capture_output=True, text=True,
    )
    opencv = json.loads(completed.stdout)
    result = build_receipt(
        source_commit=args.source_commit,
        camera_output=command_outputs[0], image_output=command_outputs[1], opencv=opencv,
        board_definition_path=args.board_definition, board_pdf_path=args.board_pdf,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "READY_FOR_MANUAL_CAPTURE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
