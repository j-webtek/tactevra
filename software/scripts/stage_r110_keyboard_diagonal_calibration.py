"""Add one reversible high-clearance diagonal keyboard calibration step."""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r109_keyboard_forward_calibration as r109

TARGET = "configured-diagnostic-candidate-r110"
KEYBOARD_DIAGONAL_CAL_2_POSITIONS = (2105, 2180, 1916, 2473, 2257, 2040, 2047)
KEYBOARD_DIAGONAL_CAL_2_GOALS = KEYBOARD_DIAGONAL_CAL_2_POSITIONS


def sources() -> dict[str, bytes]:
    files = dict(r109.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r109", b"r110")
    replacements = {
        b'\\"KEYBOARD_FORWARD_CAL_1\\"],\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408,409,410]': b'\\"KEYBOARD_FORWARD_CAL_1\\",\\"KEYBOARD_DIAGONAL_CAL_2\\"],'
        b'\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408,409,410,411,412]',
        b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,KEYBOARD_FORWARD_CAL_1=6,TRANSIT=7};": b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,KEYBOARD_FORWARD_CAL_1=6,KEYBOARD_DIAGONAL_CAL_2=7,TRANSIT=8};",
        b"static constexpr int16_t kKeyboardForwardCal1Goals[7]={2047,2136,1960,2549,2224,2040,2047};": b"static constexpr int16_t kKeyboardForwardCal1Goals[7]={2047,2136,1960,2549,2224,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardDiagonalCal2Positions[7]={2105,2180,1916,2473,2257,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardDiagonalCal2Goals[7]={2105,2180,1916,2473,2257,2040,2047};",
        b'if(strcmp(line_,"{\\"T\\":410}")==0){moveNamed(KEYBOARD_A_HOVER);return;}': b'if(strcmp(line_,"{\\"T\\":410}")==0){moveNamed(KEYBOARD_A_HOVER);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":411}")==0){moveNamed(KEYBOARD_DIAGONAL_CAL_2);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":412}")==0){moveNamed(KEYBOARD_FORWARD_CAL_1);return;}',
        b"if(nearPose(p,kKeyboardForwardCal1Positions))return KEYBOARD_FORWARD_CAL_1;": b"if(nearPose(p,kKeyboardForwardCal1Positions))return KEYBOARD_FORWARD_CAL_1;\n"
        b"    if(nearPose(p,kKeyboardDiagonalCal2Positions))return KEYBOARD_DIAGONAL_CAL_2;",
        b'if(pose==KEYBOARD_FORWARD_CAL_1)return "KEYBOARD_FORWARD_CAL_1";': b'if(pose==KEYBOARD_FORWARD_CAL_1)return "KEYBOARD_FORWARD_CAL_1";\n'
        b'    if(pose==KEYBOARD_DIAGONAL_CAL_2)return "KEYBOARD_DIAGONAL_CAL_2";',
        b"(source==KEYBOARD_FORWARD_CAL_1&&requested==KEYBOARD_A_HOVER))){": b"(source==KEYBOARD_FORWARD_CAL_1&&requested==KEYBOARD_A_HOVER)||\n"
        b"        (source==KEYBOARD_FORWARD_CAL_1&&requested==KEYBOARD_DIAGONAL_CAL_2)||\n"
        b"        (source==KEYBOARD_DIAGONAL_CAL_2&&requested==KEYBOARD_FORWARD_CAL_1))){",
        b"(requested==KEYBOARD_FORWARD_CAL_1?kKeyboardForwardCal1Goals:kFoldedGoals))));": b"(requested==KEYBOARD_FORWARD_CAL_1?kKeyboardForwardCal1Goals:\n"
        b"        (requested==KEYBOARD_DIAGONAL_CAL_2?kKeyboardDiagonalCal2Goals:kFoldedGoals)))));",
    }
    for old, new in replacements.items():
        if old not in runtime:
            raise ValueError(f"r110 transform marker missing: {old!r}")
        runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    required = (
        b"KEYBOARD_DIAGONAL_CAL_2",
        b'{\\"T\\":411}',
        b'{\\"T\\":412}',
        b"kKeyboardDiagonalCal2Goals",
    )
    if any(token not in runtime for token in required) or b"r109" in runtime:
        raise ValueError("r110 transformation incomplete")
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
        raise ValueError("Existing r110 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r110 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "trajectory": "LIMIT_DERIVED_QUINTIC_40HZ",
        "keyboard_diagonal_cal_2_goals": list(KEYBOARD_DIAGONAL_CAL_2_GOALS),
        "model_space_forward_delta_mm": 20,
        "model_space_lateral_delta_mm": -20,
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
