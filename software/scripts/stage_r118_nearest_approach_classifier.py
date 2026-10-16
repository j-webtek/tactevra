"""Classify adjacent keyboard approach endpoints by bounded nearest distance."""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r117_keyboard_field_approach_38 as r117


TARGET = "configured-diagnostic-candidate-r118"
APPROACH_TOLERANCE_COUNTS = 20
APPROACH_POSES = {
    "KEYBOARD_FIELD_APPROACH_10": (2174, 2271, 1825, 2362, 2277, 2040, 2047),
    "KEYBOARD_FIELD_APPROACH_20": (2174, 2293, 1803, 2383, 2234, 2040, 2047),
    "KEYBOARD_FIELD_APPROACH_25": (2174, 2305, 1791, 2393, 2213, 2040, 2047),
    "KEYBOARD_FIELD_APPROACH_28": (2174, 2312, 1784, 2399, 2200, 2040, 2047),
    "KEYBOARD_FIELD_APPROACH_38": (2174, 2337, 1759, 2416, 2158, 2040, 2047),
}


def classify_keyboard_approach(
    positions: tuple[int, ...], tolerance_counts: int = APPROACH_TOLERANCE_COUNTS
) -> str | None:
    """Return the unique closest endpoint inside the bounded max-joint tolerance."""
    candidates: list[tuple[int, str]] = []
    for name, expected in APPROACH_POSES.items():
        errors = tuple(abs(actual - target) for actual, target in zip(positions, expected))
        if max(errors) <= tolerance_counts:
            candidates.append((sum(errors), name))
    return min(candidates)[1] if candidates else None


def sources() -> dict[str, bytes]:
    files = dict(r117.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r117", b"r118")
    old = b"""  Pose classify(const int16_t* p){
    if(nearPose(p,kFoldedPositions))return FOLDED;
    if(nearPose(p,kUprightPositions))return UPRIGHT;
    if(nearPose(p,kAirHoverAPositions))return AIR_HOVER_A;
    if(nearPose(p,kKeyboardAHoverPositions))return KEYBOARD_A_HOVER;
    if(nearPose(p,kKeyboardALowAirPositions))return KEYBOARD_A_LOW_AIR;
    if(nearPose(p,kKeyboardForwardCal1Positions))return KEYBOARD_FORWARD_CAL_1;
    if(nearPose(p,kKeyboardDiagonalCal2Positions))return KEYBOARD_DIAGONAL_CAL_2;
    if(nearPose(p,kKeyboardFieldCal3Positions))return KEYBOARD_FIELD_CAL_3;
    if(nearPose(p,kKeyboardFieldApproach10Positions))return KEYBOARD_FIELD_APPROACH_10;
    if(nearPose(p,kKeyboardFieldApproach20Positions))return KEYBOARD_FIELD_APPROACH_20;
    if(nearPose(p,kKeyboardFieldApproach38Positions))return KEYBOARD_FIELD_APPROACH_38;
    if(nearPose(p,kKeyboardFieldApproach28Positions))return KEYBOARD_FIELD_APPROACH_28;
    if(nearPose(p,kKeyboardFieldApproach25Positions))return KEYBOARD_FIELD_APPROACH_25;
    return motion_active_?TRANSIT:UNKNOWN;
  }
"""
    new = b"""  int32_t boundedApproachError(const int16_t* p,const int16_t* expected){
    int16_t max_error=0;int32_t sum_error=0;
    for(size_t i=0;i<7;++i){
      const int16_t error=abs(p[i]-expected[i]);
      if(error>max_error)max_error=error;sum_error+=error;
    }
    return max_error<=20?sum_error:2147483647L;
  }
  Pose classifyKeyboardApproach(const int16_t* p){
    Pose best=UNKNOWN;int32_t best_error=2147483647L;int32_t error;
    error=boundedApproachError(p,kKeyboardFieldApproach10Positions);if(error<best_error){best=KEYBOARD_FIELD_APPROACH_10;best_error=error;}
    error=boundedApproachError(p,kKeyboardFieldApproach20Positions);if(error<best_error){best=KEYBOARD_FIELD_APPROACH_20;best_error=error;}
    error=boundedApproachError(p,kKeyboardFieldApproach25Positions);if(error<best_error){best=KEYBOARD_FIELD_APPROACH_25;best_error=error;}
    error=boundedApproachError(p,kKeyboardFieldApproach28Positions);if(error<best_error){best=KEYBOARD_FIELD_APPROACH_28;best_error=error;}
    error=boundedApproachError(p,kKeyboardFieldApproach38Positions);if(error<best_error){best=KEYBOARD_FIELD_APPROACH_38;best_error=error;}
    return best;
  }
  Pose classify(const int16_t* p){
    if(nearPose(p,kFoldedPositions))return FOLDED;
    if(nearPose(p,kUprightPositions))return UPRIGHT;
    if(nearPose(p,kAirHoverAPositions))return AIR_HOVER_A;
    if(nearPose(p,kKeyboardAHoverPositions))return KEYBOARD_A_HOVER;
    if(nearPose(p,kKeyboardALowAirPositions))return KEYBOARD_A_LOW_AIR;
    if(nearPose(p,kKeyboardForwardCal1Positions))return KEYBOARD_FORWARD_CAL_1;
    if(nearPose(p,kKeyboardDiagonalCal2Positions))return KEYBOARD_DIAGONAL_CAL_2;
    if(nearPose(p,kKeyboardFieldCal3Positions))return KEYBOARD_FIELD_CAL_3;
    const Pose approach=classifyKeyboardApproach(p);if(approach!=UNKNOWN)return approach;
    return motion_active_?TRANSIT:UNKNOWN;
  }
"""
    if old not in runtime:
        raise ValueError("r118 classifier marker missing")
    runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    required = (
        b"candidate\\\":\\\"r118",
        b"boundedApproachError",
        b"classifyKeyboardApproach",
        b"max_error<=20",
    )
    if any(token not in runtime for token in required) or b"r117" in runtime:
        raise ValueError("r118 transformation incomplete")
    return files


def stage(root: Path) -> dict:
    root = Path(root).resolve()
    files = sources()
    destination = root / ".firmware-tools" / TARGET / "RoArm-M3_example"
    existing = (
        {p.name: p.read_bytes() for p in destination.iterdir() if p.is_file()}
        if destination.exists()
        else {}
    )
    if existing and existing != files:
        raise ValueError("Existing r118 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r118 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "change": "BOUNDED_NEAREST_APPROACH_CLASSIFIER",
        "approach_tolerance_counts": APPROACH_TOLERANCE_COUNTS,
        "motion_commands_added": 0,
        "startup_motion_commands": 0,
        "contact_commands": 0,
        "hardware_access": False,
        "source_hashes": {
            name: hashlib.sha256(data).hexdigest()
            for name, data in sorted(files.items())
        },
    }


if __name__ == "__main__":
    import json

    print(json.dumps(stage(Path(__file__).resolve().parents[1]), indent=2))
