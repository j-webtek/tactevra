"""Build the zero-authority B0477 physical commissioning amendment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "software/ai/schemas/b0477_commissioning_amendment_v1.schema.json"


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: Any) -> str:
    rendered = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def build_amendment(*, source_commit: str, probe_path: Path) -> dict[str, Any]:
    probe = load_json(probe_path)
    if probe.get("schema") != "tactevra.ai_physical_charuco_probe.v1":
        raise ValueError("probe schema mismatch")
    bindings = []
    for relative in (
        "software/config/camera_profiles/arducam_b0477_imx283_16mm.json",
        "software/tests/fixtures/camera/b0477_nominal_uvc_inventory.json",
        "software/tests/fixtures/camera/b0477_synthetic_intrinsics_rehearsal.json",
    ):
        path = ROOT / relative
        bindings.append({"path": relative, "sha256": sha256_file(path)})
    core = {
        "schema": "tactevra.ai_b0477_commissioning_amendment.v1",
        "scope": "PRECAPTURE_CONTRACT_CORRECTION_NO_PHYSICAL_EVIDENCE",
        "source_commit": source_commit,
        "superseded_probe_binding": {
            "path": "software/ai/eval/physical_charuco_probe_blocked_v1.json",
            "file_sha256": sha256_file(probe_path),
            "report_sha256": probe["report_sha256"],
            "preserved_as_failed_evidence": True,
        },
        "authoritative_bindings": bindings,
        "mode_correction": {
            "incorrect_fps_in_preserved_probe": 4,
            "authoritative_maximum_fps": 9.0,
            "reason": "The purchased profile, nominal UVC inventory, and sealed intrinsics rehearsal agree on the native mode.",
        },
        "calibration_runtime_mode": {
            "width_px": 5472,
            "height_px": 3648,
            "fps": 9.0,
            "pixel_format": "YUY2",
            "sensor_transform": "FULL_NATIVE_MODE",
        },
        "alternate_mode_rule": "SEPARATE_CALIBRATION_REQUIRED_UNLESS_CROP_BIN_SCALE_TRANSFORM_IS_MEASURED_AND_REVIEWED",
        "optics_and_controls_gate": {
            "manual_focus_locked": True,
            "manual_aperture_locked": True,
            "autofocus_disabled": True,
            "auto_exposure_disabled": True,
            "auto_white_balance_disabled": True,
            "exposure_locked": True,
            "gain_locked": True,
            "white_balance_locked": True,
            "focus_and_aperture_witness_required": True,
            "controls_snapshot_required": True,
            "settings_hash_binding_required": True,
        },
        "print_scale_measurement_gate": {
            "instrument": "CALIBRATED_CALIPERS",
            "minimum_total_measurements": 8,
            "minimum_horizontal_measurements": 4,
            "minimum_vertical_measurements": 4,
            "distributed_across_board": True,
            "opposite_extents_required": True,
            "raw_measurements_and_instrument_identity_retained": True,
            "maximum_axis_scale_error_fraction": None,
            "tolerance_status": "UNSET_PENDING_PHYSICAL_MEASUREMENT_AND_REVIEW",
        },
        "capture_plan": {
            "training_views": 24,
            "held_out_views": 8,
            "corners_and_edges_required": True,
            "varied_positions_angles_and_distances_required": True,
            "training_and_held_out_reprojection_reported_separately": True,
            "diagnostic_reprojection_target_px": 0.5,
            "diagnostic_target_is_qualification_threshold": False,
        },
        "ready_for_capture": False,
        "camera_frames_requested": 0,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "No B0477 is connected and no focus, exposure, gain, white-balance, or print-scale value has been measured.",
            "The nine-fps value is repository-authoritative rehearsal and purchase-profile evidence pending received-unit verification.",
            "No print-scale tolerance is selected; physical measurements require review before admission.",
        ],
    }
    result = {**core, "report_sha256": canonical_hash(core)}
    errors = sorted(
        Draft202012Validator(load_json(SCHEMA)).iter_errors(result), key=lambda e: list(e.path),
    )
    if errors:
        first = errors[0]
        raise ValueError(f"schema validation failed at {list(first.path)}: {first.message}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_amendment(source_commit=args.source_commit, probe_path=args.probe)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
