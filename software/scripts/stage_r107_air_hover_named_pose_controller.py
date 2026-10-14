"""Stage the first guarded noncontact action pose on the r106 motion engine.

The added AIR_HOVER_A endpoint is retained from controller-feedback evidence.
Only FOLDED <-> AIR_HOVER_A is permitted for the new commands.  No approach or
contact command is exposed by this firmware revision.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r106_fast_flow_named_pose_controller as r106

TARGET = "configured-diagnostic-candidate-r107"
AIR_HOVER_A_POSITIONS = (2041, 2081, 2033, 2609, 2233, 2041, 2047)
AIR_HOVER_A_GOALS = (2047, 2075, 2039, 2600, 2233, 2040, 2047)


def sources() -> dict[str, bytes]:
    files = dict(r106.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r106", b"r107")
    replacements = {
        b'\\"named_poses\\":[\\"FOLDED\\",\\"UPRIGHT\\"],\\"supported_commands\\":[105,400,401,402]': b'\\"named_poses\\":[\\"FOLDED\\",\\"UPRIGHT\\",\\"AIR_HOVER_A\\"],\\"supported_commands\\":[105,400,401,402,403,404]',
        b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,TRANSIT=3};": b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,TRANSIT=4};",
        b"static constexpr int16_t kUprightGoals[7]={2107,2075,2039,1056,1933,2040,1897};": b"static constexpr int16_t kUprightGoals[7]={2107,2075,2039,1056,1933,2040,1897};\n"
        b"  static constexpr int16_t kAirHoverAPositions[7]={2041,2081,2033,2609,2233,2041,2047};\n"
        b"  static constexpr int16_t kAirHoverAGoals[7]={2047,2075,2039,2600,2233,2040,2047};",
        b'if(strcmp(line_,"{\\"T\\":402}")==0){abortToHold();return;}': b'if(strcmp(line_,"{\\"T\\":402}")==0){abortToHold();return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":403}")==0){moveNamed(AIR_HOVER_A);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":404}")==0){moveNamed(FOLDED);return;}',
        b"if(nearPose(p,kUprightPositions))return UPRIGHT;": b"if(nearPose(p,kUprightPositions))return UPRIGHT;\n"
        b"    if(nearPose(p,kAirHoverAPositions))return AIR_HOVER_A;",
        b'if(pose==FOLDED)return "FOLDED";if(pose==UPRIGHT)return "UPRIGHT";': b'if(pose==FOLDED)return "FOLDED";if(pose==UPRIGHT)return "UPRIGHT";\n'
        b'    if(pose==AIR_HOVER_A)return "AIR_HOVER_A";',
        b"if(motion_active_||!((source==FOLDED&&requested==UPRIGHT)||(source==UPRIGHT&&requested==FOLDED))){": b"if(motion_active_||!((source==FOLDED&&requested==UPRIGHT)||(source==UPRIGHT&&requested==FOLDED)||\n"
        b"        (source==FOLDED&&requested==AIR_HOVER_A)||(source==AIR_HOVER_A&&requested==FOLDED))){",
        b"const int16_t* requested_target=requested==UPRIGHT?kUprightGoals:kFoldedGoals;": b"const int16_t* requested_target=requested==UPRIGHT?kUprightGoals:\n"
        b"        (requested==AIR_HOVER_A?kAirHoverAGoals:kFoldedGoals);",
    }
    for old, new in replacements.items():
        if old not in runtime:
            raise ValueError(f"r107 transform marker missing: {old!r}")
        runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    required = (
        b"AIR_HOVER_A",
        b"kAirHoverAPositions",
        b"kAirHoverAGoals",
        b'{\\"T\\":403}',
        b'{\\"T\\":404}',
    )
    if any(token not in runtime for token in required) or b"r106" in runtime:
        raise ValueError("r107 transformation incomplete")
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
        raise ValueError("Existing r107 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r107 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "trajectory": "LIMIT_DERIVED_QUINTIC_40HZ",
        "air_hover_a_positions": list(AIR_HOVER_A_POSITIONS),
        "air_hover_a_goals": list(AIR_HOVER_A_GOALS),
        "source_hashes": {
            n: hashlib.sha256(d).hexdigest() for n, d in sorted(files.items())
        },
        "startup_motion_commands": 0,
        "contact_commands": 0,
        "hardware_access": False,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(stage(Path(__file__).resolve().parents[1]), indent=2))
