"""Add a reversible 10 mm high-clearance approach above the keyboard field."""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r111_keyboard_field_calibration as r111

TARGET = "configured-diagnostic-candidate-r112"
KEYBOARD_FIELD_APPROACH_10_POSITIONS = (2174, 2271, 1825, 2362, 2277, 2040, 2047)
KEYBOARD_FIELD_APPROACH_10_GOALS = KEYBOARD_FIELD_APPROACH_10_POSITIONS


def sources() -> dict[str, bytes]:
    files = dict(r111.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r111", b"r112")
    replacements = {
        b'\\"KEYBOARD_FIELD_CAL_3\\"],\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408,409,410,411,412,413,414]': b'\\"KEYBOARD_FIELD_CAL_3\\",\\"KEYBOARD_FIELD_APPROACH_10\\"],'
        b'\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408,409,410,411,412,413,414,415,416]',
        b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,KEYBOARD_FORWARD_CAL_1=6,KEYBOARD_DIAGONAL_CAL_2=7,KEYBOARD_FIELD_CAL_3=8,TRANSIT=9};": b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,KEYBOARD_FORWARD_CAL_1=6,KEYBOARD_DIAGONAL_CAL_2=7,KEYBOARD_FIELD_CAL_3=8,KEYBOARD_FIELD_APPROACH_10=9,TRANSIT=10};",
        b"static constexpr int16_t kKeyboardFieldCal3Goals[7]={2174,2250,1846,2340,2320,2040,2047};": b"static constexpr int16_t kKeyboardFieldCal3Goals[7]={2174,2250,1846,2340,2320,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardFieldApproach10Positions[7]={2174,2271,1825,2362,2277,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardFieldApproach10Goals[7]={2174,2271,1825,2362,2277,2040,2047};",
        b'if(strcmp(line_,"{\\"T\\":414}")==0){moveNamed(KEYBOARD_DIAGONAL_CAL_2);return;}': b'if(strcmp(line_,"{\\"T\\":414}")==0){moveNamed(KEYBOARD_DIAGONAL_CAL_2);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":415}")==0){moveNamed(KEYBOARD_FIELD_APPROACH_10);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":416}")==0){moveNamed(KEYBOARD_FIELD_CAL_3);return;}',
        b"if(nearPose(p,kKeyboardFieldCal3Positions))return KEYBOARD_FIELD_CAL_3;": b"if(nearPose(p,kKeyboardFieldCal3Positions))return KEYBOARD_FIELD_CAL_3;\n"
        b"    if(nearPose(p,kKeyboardFieldApproach10Positions))return KEYBOARD_FIELD_APPROACH_10;",
        b'if(pose==KEYBOARD_FIELD_CAL_3)return "KEYBOARD_FIELD_CAL_3";': b'if(pose==KEYBOARD_FIELD_CAL_3)return "KEYBOARD_FIELD_CAL_3";\n'
        b'    if(pose==KEYBOARD_FIELD_APPROACH_10)return "KEYBOARD_FIELD_APPROACH_10";',
        b"(source==KEYBOARD_FIELD_CAL_3&&requested==KEYBOARD_DIAGONAL_CAL_2))){": b"(source==KEYBOARD_FIELD_CAL_3&&requested==KEYBOARD_DIAGONAL_CAL_2)||\n"
        b"        (source==KEYBOARD_FIELD_CAL_3&&requested==KEYBOARD_FIELD_APPROACH_10)||\n"
        b"        (source==KEYBOARD_FIELD_APPROACH_10&&requested==KEYBOARD_FIELD_CAL_3))){",
        b"(requested==KEYBOARD_FIELD_CAL_3?kKeyboardFieldCal3Goals:kFoldedGoals))))));": b"(requested==KEYBOARD_FIELD_CAL_3?kKeyboardFieldCal3Goals:\n"
        b"        (requested==KEYBOARD_FIELD_APPROACH_10?kKeyboardFieldApproach10Goals:kFoldedGoals)))))));",
    }
    for old, new in replacements.items():
        if old not in runtime:
            raise ValueError(f"r112 transform marker missing: {old!r}")
        runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    required = (
        b"KEYBOARD_FIELD_APPROACH_10",
        b'{\\"T\\":415}',
        b'{\\"T\\":416}',
        b"kKeyboardFieldApproach10Goals",
    )
    if any(token not in runtime for token in required) or b"r111" in runtime:
        raise ValueError("r112 transformation incomplete")
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
        raise ValueError("Existing r112 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r112 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "trajectory": "LIMIT_DERIVED_QUINTIC_40HZ",
        "keyboard_field_approach_10_goals": list(KEYBOARD_FIELD_APPROACH_10_GOALS),
        "model_space_forward_delta_mm": 0,
        "model_space_lateral_delta_mm": 0,
        "model_space_vertical_delta_mm": -10,
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
