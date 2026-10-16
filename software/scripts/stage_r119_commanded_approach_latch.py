"""Latch a completed commanded approach endpoint inside its bounded tolerance."""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r118_nearest_approach_classifier as r118


TARGET = "configured-diagnostic-candidate-r119"


def sources() -> dict[str, bytes]:
    files = dict(r118.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r118", b"r119")
    replacements = {
        b"bool terminal_locked_=false;bool motion_active_=false;bool trajectory_done_=false;":
            b"bool terminal_locked_=false;bool motion_active_=false;bool trajectory_done_=false;Pose settled_approach_pose_=UNKNOWN;",
        b"  Pose classify(const int16_t* p){\n":
            b"  const int16_t* approachPositions(Pose pose){\n"
            b"    if(pose==KEYBOARD_FIELD_APPROACH_10)return kKeyboardFieldApproach10Positions;\n"
            b"    if(pose==KEYBOARD_FIELD_APPROACH_20)return kKeyboardFieldApproach20Positions;\n"
            b"    if(pose==KEYBOARD_FIELD_APPROACH_25)return kKeyboardFieldApproach25Positions;\n"
            b"    if(pose==KEYBOARD_FIELD_APPROACH_28)return kKeyboardFieldApproach28Positions;\n"
            b"    if(pose==KEYBOARD_FIELD_APPROACH_38)return kKeyboardFieldApproach38Positions;\n"
            b"    return nullptr;\n"
            b"  }\n"
            b"  bool withinApproachTolerance(const int16_t* p,Pose pose){\n"
            b"    const int16_t* expected=approachPositions(pose);\n"
            b"    return expected!=nullptr&&boundedApproachError(p,expected)<2147483647L;\n"
            b"  }\n"
            b"  Pose classify(const int16_t* p){\n"
            b"    if(settled_approach_pose_!=UNKNOWN&&withinApproachTolerance(p,settled_approach_pose_))return settled_approach_pose_;\n",
        b"duration_ms_=computeDurationMs(start_,target_);motion_active_=true;trajectory_done_=false;target_pose_=requested;progress_permille_=0;":
            b"duration_ms_=computeDurationMs(start_,target_);motion_active_=true;trajectory_done_=false;settled_approach_pose_=UNKNOWN;target_pose_=requested;progress_permille_=0;",
        b"if(motion_active_&&trajectory_done_&&observed==target_pose_){motion_active_=false;target_pose_=UNKNOWN;}":
            b"if(motion_active_&&trajectory_done_&&(observed==target_pose_||withinApproachTolerance(p,target_pose_))){\n"
            b"      if(withinApproachTolerance(p,target_pose_))settled_approach_pose_=target_pose_;\n"
            b"      motion_active_=false;target_pose_=UNKNOWN;\n"
            b"    }",
    }
    for old, new in replacements.items():
        if old not in runtime:
            raise ValueError(f"r119 transform marker missing: {old!r}")
        runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    required = (
        b"candidate\\\":\\\"r119",
        b"settled_approach_pose_",
        b"withinApproachTolerance(p,target_pose_)",
        b"settled_approach_pose_=target_pose_",
    )
    if any(token not in runtime for token in required) or b"r118" in runtime:
        raise ValueError("r119 transformation incomplete")
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
        raise ValueError("Existing r119 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r119 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "change": "BOUNDED_COMMANDED_APPROACH_LATCH",
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
