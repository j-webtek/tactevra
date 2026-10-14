"""Stage one reversible, high-clearance keyboard forward-calibration step.

The r108 keyboard pose was observed behind the keyboard.  This revision adds
only a 20 mm model-space forward correction at the same modeled TCP height.
It exposes a paired return command and no descent or contact command.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r108_keyboard_air_action_controller as r108

TARGET = "configured-diagnostic-candidate-r109"
KEYBOARD_FORWARD_CAL_1_POSITIONS = (2047, 2136, 1960, 2549, 2224, 2040, 2047)
KEYBOARD_FORWARD_CAL_1_GOALS = KEYBOARD_FORWARD_CAL_1_POSITIONS


def sources() -> dict[str, bytes]:
    files = dict(r108.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r108", b"r109")
    replacements = {
        b'\\"KEYBOARD_A_LOW_AIR\\"],\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408]': b'\\"KEYBOARD_A_LOW_AIR\\",\\"KEYBOARD_FORWARD_CAL_1\\"],'
        b'\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408,409,410]',
        b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,TRANSIT=6};": b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,KEYBOARD_FORWARD_CAL_1=6,TRANSIT=7};",
        b"static constexpr int16_t kKeyboardALowAirGoals[7]={2047,2105,2009,2630,2173,2040,2047};": b"static constexpr int16_t kKeyboardALowAirGoals[7]={2047,2105,2009,2630,2173,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardForwardCal1Positions[7]={2047,2136,1960,2549,2224,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardForwardCal1Goals[7]={2047,2136,1960,2549,2224,2040,2047};",
        b'if(strcmp(line_,"{\\"T\\":408}")==0){moveNamed(AIR_HOVER_A);return;}': b'if(strcmp(line_,"{\\"T\\":408}")==0){moveNamed(AIR_HOVER_A);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":409}")==0){moveNamed(KEYBOARD_FORWARD_CAL_1);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":410}")==0){moveNamed(KEYBOARD_A_HOVER);return;}',
        b"if(nearPose(p,kKeyboardALowAirPositions))return KEYBOARD_A_LOW_AIR;": b"if(nearPose(p,kKeyboardALowAirPositions))return KEYBOARD_A_LOW_AIR;\n"
        b"    if(nearPose(p,kKeyboardForwardCal1Positions))return KEYBOARD_FORWARD_CAL_1;",
        b'if(pose==KEYBOARD_A_LOW_AIR)return "KEYBOARD_A_LOW_AIR";': b'if(pose==KEYBOARD_A_LOW_AIR)return "KEYBOARD_A_LOW_AIR";\n'
        b'    if(pose==KEYBOARD_FORWARD_CAL_1)return "KEYBOARD_FORWARD_CAL_1";',
        b"(source==KEYBOARD_A_HOVER&&requested==AIR_HOVER_A))){": b"(source==KEYBOARD_A_HOVER&&requested==AIR_HOVER_A)||\n"
        b"        (source==KEYBOARD_A_HOVER&&requested==KEYBOARD_FORWARD_CAL_1)||\n"
        b"        (source==KEYBOARD_FORWARD_CAL_1&&requested==KEYBOARD_A_HOVER))){",
        b"(requested==KEYBOARD_A_LOW_AIR?kKeyboardALowAirGoals:kFoldedGoals)));": b"(requested==KEYBOARD_A_LOW_AIR?kKeyboardALowAirGoals:\n"
        b"        (requested==KEYBOARD_FORWARD_CAL_1?kKeyboardForwardCal1Goals:kFoldedGoals))));",
    }
    for old, new in replacements.items():
        if old not in runtime:
            raise ValueError(f"r109 transform marker missing: {old!r}")
        runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    required = (
        b"KEYBOARD_FORWARD_CAL_1",
        b'{\\"T\\":409}',
        b'{\\"T\\":410}',
        b"kKeyboardForwardCal1Goals",
    )
    if any(token not in runtime for token in required) or b"r108" in runtime:
        raise ValueError("r109 transformation incomplete")
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
        raise ValueError("Existing r109 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r109 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "trajectory": "LIMIT_DERIVED_QUINTIC_40HZ",
        "keyboard_forward_cal_1_goals": list(KEYBOARD_FORWARD_CAL_1_GOALS),
        "model_space_forward_delta_mm": 20,
        "model_space_vertical_delta_mm": 0,
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
