"""Generalize the bounded commanded-pose latch to every recorded named pose."""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r119_commanded_approach_latch as r119


TARGET = "configured-diagnostic-candidate-r120"


def sources() -> dict[str, bytes]:
    files = dict(r119.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r119", b"r120")
    replacements = {
        b"bool terminal_locked_=false;bool motion_active_=false;bool trajectory_done_=false;Pose settled_approach_pose_=UNKNOWN;":
            b"bool terminal_locked_=false;bool motion_active_=false;bool trajectory_done_=false;Pose settled_commanded_pose_=UNKNOWN;",
        b"for(size_t i=0;i<7;++i)if(abs(p[i]-expected[i])>16)return false;return true;":
            b"for(size_t i=0;i<7;++i)if(abs(p[i]-expected[i])>20)return false;return true;",
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
        b"  }":
            b"  const int16_t* posePositions(Pose pose){\n"
            b"    if(pose==FOLDED)return kFoldedPositions;\n"
            b"    if(pose==UPRIGHT)return kUprightPositions;\n"
            b"    if(pose==AIR_HOVER_A)return kAirHoverAPositions;\n"
            b"    if(pose==KEYBOARD_A_HOVER)return kKeyboardAHoverPositions;\n"
            b"    if(pose==KEYBOARD_A_LOW_AIR)return kKeyboardALowAirPositions;\n"
            b"    if(pose==KEYBOARD_FORWARD_CAL_1)return kKeyboardForwardCal1Positions;\n"
            b"    if(pose==KEYBOARD_DIAGONAL_CAL_2)return kKeyboardDiagonalCal2Positions;\n"
            b"    if(pose==KEYBOARD_FIELD_CAL_3)return kKeyboardFieldCal3Positions;\n"
            b"    if(pose==KEYBOARD_FIELD_APPROACH_10)return kKeyboardFieldApproach10Positions;\n"
            b"    if(pose==KEYBOARD_FIELD_APPROACH_20)return kKeyboardFieldApproach20Positions;\n"
            b"    if(pose==KEYBOARD_FIELD_APPROACH_25)return kKeyboardFieldApproach25Positions;\n"
            b"    if(pose==KEYBOARD_FIELD_APPROACH_28)return kKeyboardFieldApproach28Positions;\n"
            b"    if(pose==KEYBOARD_FIELD_APPROACH_38)return kKeyboardFieldApproach38Positions;\n"
            b"    return nullptr;\n"
            b"  }\n"
            b"  bool withinCommandedTolerance(const int16_t* p,Pose pose){\n"
            b"    const int16_t* expected=posePositions(pose);\n"
            b"    return expected!=nullptr&&boundedApproachError(p,expected)<2147483647L;\n"
            b"  }",
        b"if(settled_approach_pose_!=UNKNOWN&&withinApproachTolerance(p,settled_approach_pose_))return settled_approach_pose_;":
            b"if(settled_commanded_pose_!=UNKNOWN&&withinCommandedTolerance(p,settled_commanded_pose_))return settled_commanded_pose_;",
        b"settled_approach_pose_=UNKNOWN;target_pose_=requested":
            b"settled_commanded_pose_=UNKNOWN;target_pose_=requested",
        b"observed==target_pose_||withinApproachTolerance(p,target_pose_)":
            b"observed==target_pose_||withinCommandedTolerance(p,target_pose_)",
        b"if(withinApproachTolerance(p,target_pose_))settled_approach_pose_=target_pose_;":
            b"if(withinCommandedTolerance(p,target_pose_))settled_commanded_pose_=target_pose_;",
    }
    for old, new in replacements.items():
        if old not in runtime:
            raise ValueError(f"r120 transform marker missing: {old!r}")
        runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    required = (
        b"candidate\\\":\\\"r120",
        b"settled_commanded_pose_",
        b"withinCommandedTolerance(p,target_pose_)",
        b"if(abs(p[i]-expected[i])>20",
    )
    if any(token not in runtime for token in required) or b"r119" in runtime:
        raise ValueError("r120 transformation incomplete")
    return files


def stage(root: Path) -> dict:
    root = Path(root).resolve()
    files = sources()
    destination = root / ".firmware-tools" / TARGET / "RoArm-M3_example"
    existing = ({p.name: p.read_bytes() for p in destination.iterdir() if p.is_file()}
                if destination.exists() else {})
    if existing and existing != files:
        raise ValueError("Existing r120 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r120 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "change": "BOUNDED_COMMANDED_NAMED_POSE_LATCH",
        "motion_commands_added": 0,
        "startup_motion_commands": 0,
        "contact_commands": 0,
        "hardware_access": False,
        "source_hashes": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }


if __name__ == "__main__":
    import json
    print(json.dumps(stage(Path(__file__).resolve().parents[1]), indent=2))
