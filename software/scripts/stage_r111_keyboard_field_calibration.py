"""Add a reversible high-clearance step toward the keyboard letter field."""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r110_keyboard_diagonal_calibration as r110

TARGET = "configured-diagnostic-candidate-r111"
KEYBOARD_FIELD_CAL_3_POSITIONS = (2174, 2250, 1846, 2340, 2320, 2040, 2047)
KEYBOARD_FIELD_CAL_3_GOALS = KEYBOARD_FIELD_CAL_3_POSITIONS


def sources() -> dict[str, bytes]:
    files = dict(r110.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r110", b"r111")
    replacements = {
        b'\\"KEYBOARD_DIAGONAL_CAL_2\\"],\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408,409,410,411,412]': b'\\"KEYBOARD_DIAGONAL_CAL_2\\",\\"KEYBOARD_FIELD_CAL_3\\"],'
        b'\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408,409,410,411,412,413,414]',
        b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,KEYBOARD_FORWARD_CAL_1=6,KEYBOARD_DIAGONAL_CAL_2=7,TRANSIT=8};": b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,KEYBOARD_FORWARD_CAL_1=6,KEYBOARD_DIAGONAL_CAL_2=7,KEYBOARD_FIELD_CAL_3=8,TRANSIT=9};",
        b"static constexpr int16_t kKeyboardDiagonalCal2Goals[7]={2105,2180,1916,2473,2257,2040,2047};": b"static constexpr int16_t kKeyboardDiagonalCal2Goals[7]={2105,2180,1916,2473,2257,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardFieldCal3Positions[7]={2174,2250,1846,2340,2320,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardFieldCal3Goals[7]={2174,2250,1846,2340,2320,2040,2047};",
        b'if(strcmp(line_,"{\\"T\\":412}")==0){moveNamed(KEYBOARD_FORWARD_CAL_1);return;}': b'if(strcmp(line_,"{\\"T\\":412}")==0){moveNamed(KEYBOARD_FORWARD_CAL_1);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":413}")==0){moveNamed(KEYBOARD_FIELD_CAL_3);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":414}")==0){moveNamed(KEYBOARD_DIAGONAL_CAL_2);return;}',
        b"if(nearPose(p,kKeyboardDiagonalCal2Positions))return KEYBOARD_DIAGONAL_CAL_2;": b"if(nearPose(p,kKeyboardDiagonalCal2Positions))return KEYBOARD_DIAGONAL_CAL_2;\n"
        b"    if(nearPose(p,kKeyboardFieldCal3Positions))return KEYBOARD_FIELD_CAL_3;",
        b'if(pose==KEYBOARD_DIAGONAL_CAL_2)return "KEYBOARD_DIAGONAL_CAL_2";': b'if(pose==KEYBOARD_DIAGONAL_CAL_2)return "KEYBOARD_DIAGONAL_CAL_2";\n'
        b'    if(pose==KEYBOARD_FIELD_CAL_3)return "KEYBOARD_FIELD_CAL_3";',
        b"(source==KEYBOARD_DIAGONAL_CAL_2&&requested==KEYBOARD_FORWARD_CAL_1))){": b"(source==KEYBOARD_DIAGONAL_CAL_2&&requested==KEYBOARD_FORWARD_CAL_1)||\n"
        b"        (source==KEYBOARD_DIAGONAL_CAL_2&&requested==KEYBOARD_FIELD_CAL_3)||\n"
        b"        (source==KEYBOARD_FIELD_CAL_3&&requested==KEYBOARD_DIAGONAL_CAL_2))){",
        b"(requested==KEYBOARD_DIAGONAL_CAL_2?kKeyboardDiagonalCal2Goals:kFoldedGoals)))));": b"(requested==KEYBOARD_DIAGONAL_CAL_2?kKeyboardDiagonalCal2Goals:\n"
        b"        (requested==KEYBOARD_FIELD_CAL_3?kKeyboardFieldCal3Goals:kFoldedGoals))))));",
    }
    for old, new in replacements.items():
        if old not in runtime:
            raise ValueError(f"r111 transform marker missing: {old!r}")
        runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    required = (
        b"KEYBOARD_FIELD_CAL_3",
        b'{\\"T\\":413}',
        b'{\\"T\\":414}',
        b"kKeyboardFieldCal3Goals",
    )
    if any(token not in runtime for token in required) or b"r110" in runtime:
        raise ValueError("r111 transformation incomplete")
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
        raise ValueError("Existing r111 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r111 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "trajectory": "LIMIT_DERIVED_QUINTIC_40HZ",
        "keyboard_field_cal_3_goals": list(KEYBOARD_FIELD_CAL_3_GOALS),
        "model_space_forward_delta_mm": 30,
        "model_space_lateral_delta_mm": -30,
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
