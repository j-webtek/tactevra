"""Stage guarded air-only motion over the last calibrated keyboard A region."""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r107_air_hover_named_pose_controller as r107

TARGET = "configured-diagnostic-candidate-r108"
KEYBOARD_A_HOVER_POSITIONS = (2047, 2093, 2021, 2618, 2197, 2040, 2047)
KEYBOARD_A_HOVER_GOALS = KEYBOARD_A_HOVER_POSITIONS
KEYBOARD_A_LOW_AIR_POSITIONS = (2047, 2105, 2009, 2630, 2173, 2040, 2047)
KEYBOARD_A_LOW_AIR_GOALS = KEYBOARD_A_LOW_AIR_POSITIONS


def sources() -> dict[str, bytes]:
    files = dict(r107.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r107", b"r108")
    replacements = {
        b'\\"AIR_HOVER_A\\"],\\"supported_commands\\":[105,400,401,402,403,404]': b'\\"AIR_HOVER_A\\",\\"KEYBOARD_A_HOVER\\",\\"KEYBOARD_A_LOW_AIR\\"],'
        b'\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408]',
        b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,TRANSIT=4};": b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,TRANSIT=6};",
        b"static constexpr int16_t kAirHoverAGoals[7]={2047,2075,2039,2600,2233,2040,2047};": b"static constexpr int16_t kAirHoverAGoals[7]={2047,2075,2039,2600,2233,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardAHoverPositions[7]={2047,2093,2021,2618,2197,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardAHoverGoals[7]={2047,2093,2021,2618,2197,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardALowAirPositions[7]={2047,2105,2009,2630,2173,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardALowAirGoals[7]={2047,2105,2009,2630,2173,2040,2047};",
        b'if(strcmp(line_,"{\\"T\\":404}")==0){moveNamed(FOLDED);return;}': b'if(strcmp(line_,"{\\"T\\":404}")==0){moveNamed(FOLDED);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":405}")==0){moveNamed(KEYBOARD_A_HOVER);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":406}")==0){moveNamed(KEYBOARD_A_LOW_AIR);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":407}")==0){moveNamed(KEYBOARD_A_HOVER);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":408}")==0){moveNamed(AIR_HOVER_A);return;}',
        b"if(nearPose(p,kAirHoverAPositions))return AIR_HOVER_A;": b"if(nearPose(p,kAirHoverAPositions))return AIR_HOVER_A;\n"
        b"    if(nearPose(p,kKeyboardAHoverPositions))return KEYBOARD_A_HOVER;\n"
        b"    if(nearPose(p,kKeyboardALowAirPositions))return KEYBOARD_A_LOW_AIR;",
        b'if(pose==AIR_HOVER_A)return "AIR_HOVER_A";': b'if(pose==AIR_HOVER_A)return "AIR_HOVER_A";\n'
        b'    if(pose==KEYBOARD_A_HOVER)return "KEYBOARD_A_HOVER";\n'
        b'    if(pose==KEYBOARD_A_LOW_AIR)return "KEYBOARD_A_LOW_AIR";',
        b"(source==FOLDED&&requested==AIR_HOVER_A)||(source==AIR_HOVER_A&&requested==FOLDED))){": b"(source==FOLDED&&requested==AIR_HOVER_A)||(source==AIR_HOVER_A&&requested==FOLDED)||\n"
        b"        (source==AIR_HOVER_A&&requested==KEYBOARD_A_HOVER)||\n"
        b"        (source==KEYBOARD_A_HOVER&&requested==KEYBOARD_A_LOW_AIR)||\n"
        b"        (source==KEYBOARD_A_LOW_AIR&&requested==KEYBOARD_A_HOVER)||\n"
        b"        (source==KEYBOARD_A_HOVER&&requested==AIR_HOVER_A))){",
        b"const int16_t* requested_target=requested==UPRIGHT?kUprightGoals:\n        (requested==AIR_HOVER_A?kAirHoverAGoals:kFoldedGoals);": b"const int16_t* requested_target=requested==UPRIGHT?kUprightGoals:\n"
        b"        (requested==AIR_HOVER_A?kAirHoverAGoals:\n"
        b"        (requested==KEYBOARD_A_HOVER?kKeyboardAHoverGoals:\n"
        b"        (requested==KEYBOARD_A_LOW_AIR?kKeyboardALowAirGoals:kFoldedGoals)));",
    }
    for old, new in replacements.items():
        if old not in runtime:
            raise ValueError(f"r108 transform marker missing: {old!r}")
        runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    required = (
        b"KEYBOARD_A_HOVER",
        b"KEYBOARD_A_LOW_AIR",
        b'{\\"T\\":405}',
        b'{\\"T\\":406}',
        b'{\\"T\\":407}',
        b'{\\"T\\":408}',
    )
    if any(token not in runtime for token in required) or b"r107" in runtime:
        raise ValueError("r108 transformation incomplete")
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
        raise ValueError("Existing r108 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r108 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "trajectory": "LIMIT_DERIVED_QUINTIC_40HZ",
        "keyboard_a_hover_goals": list(KEYBOARD_A_HOVER_GOALS),
        "keyboard_a_low_air_goals": list(KEYBOARD_A_LOW_AIR_GOALS),
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
