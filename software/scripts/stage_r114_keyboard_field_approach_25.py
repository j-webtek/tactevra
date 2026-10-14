"""Add a reversible 5 mm final visual approach above the keyboard field."""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r113_keyboard_field_approach_20 as r113

TARGET = "configured-diagnostic-candidate-r114"
KEYBOARD_FIELD_APPROACH_25_POSITIONS = (2174, 2305, 1791, 2393, 2213, 2040, 2047)
KEYBOARD_FIELD_APPROACH_25_GOALS = KEYBOARD_FIELD_APPROACH_25_POSITIONS


def sources() -> dict[str, bytes]:
    files = dict(r113.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r113", b"r114")
    replacements = {
        b'\\"KEYBOARD_FIELD_APPROACH_20\\"],\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408,409,410,411,412,413,414,415,416,417,418]': b'\\"KEYBOARD_FIELD_APPROACH_20\\",\\"KEYBOARD_FIELD_APPROACH_25\\"],'
        b'\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408,409,410,411,412,413,414,415,416,417,418,419,420]',
        b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,KEYBOARD_FORWARD_CAL_1=6,KEYBOARD_DIAGONAL_CAL_2=7,KEYBOARD_FIELD_CAL_3=8,KEYBOARD_FIELD_APPROACH_10=9,KEYBOARD_FIELD_APPROACH_20=10,TRANSIT=11};": b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,KEYBOARD_FORWARD_CAL_1=6,KEYBOARD_DIAGONAL_CAL_2=7,KEYBOARD_FIELD_CAL_3=8,KEYBOARD_FIELD_APPROACH_10=9,KEYBOARD_FIELD_APPROACH_20=10,KEYBOARD_FIELD_APPROACH_25=11,TRANSIT=12};",
        b"static constexpr int16_t kKeyboardFieldApproach20Goals[7]={2174,2293,1803,2383,2234,2040,2047};": b"static constexpr int16_t kKeyboardFieldApproach20Goals[7]={2174,2293,1803,2383,2234,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardFieldApproach25Positions[7]={2174,2305,1791,2393,2213,2040,2047};\n"
        b"  static constexpr int16_t kKeyboardFieldApproach25Goals[7]={2174,2305,1791,2393,2213,2040,2047};",
        b'if(strcmp(line_,"{\\"T\\":418}")==0){moveNamed(KEYBOARD_FIELD_APPROACH_10);return;}': b'if(strcmp(line_,"{\\"T\\":418}")==0){moveNamed(KEYBOARD_FIELD_APPROACH_10);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":419}")==0){moveNamed(KEYBOARD_FIELD_APPROACH_25);return;}\n'
        b'    if(strcmp(line_,"{\\"T\\":420}")==0){moveNamed(KEYBOARD_FIELD_APPROACH_20);return;}',
        b"if(nearPose(p,kKeyboardFieldApproach20Positions))return KEYBOARD_FIELD_APPROACH_20;": b"if(nearPose(p,kKeyboardFieldApproach20Positions))return KEYBOARD_FIELD_APPROACH_20;\n"
        b"    if(nearPose(p,kKeyboardFieldApproach25Positions))return KEYBOARD_FIELD_APPROACH_25;",
        b'if(pose==KEYBOARD_FIELD_APPROACH_20)return "KEYBOARD_FIELD_APPROACH_20";': b'if(pose==KEYBOARD_FIELD_APPROACH_20)return "KEYBOARD_FIELD_APPROACH_20";\n'
        b'    if(pose==KEYBOARD_FIELD_APPROACH_25)return "KEYBOARD_FIELD_APPROACH_25";',
        b"(source==KEYBOARD_FIELD_APPROACH_20&&requested==KEYBOARD_FIELD_APPROACH_10))){": b"(source==KEYBOARD_FIELD_APPROACH_20&&requested==KEYBOARD_FIELD_APPROACH_10)||\n"
        b"        (source==KEYBOARD_FIELD_APPROACH_20&&requested==KEYBOARD_FIELD_APPROACH_25)||\n"
        b"        (source==KEYBOARD_FIELD_APPROACH_25&&requested==KEYBOARD_FIELD_APPROACH_20))){",
        b"(requested==KEYBOARD_FIELD_APPROACH_20?kKeyboardFieldApproach20Goals:kFoldedGoals))))))));": b"(requested==KEYBOARD_FIELD_APPROACH_20?kKeyboardFieldApproach20Goals:\n"
        b"        (requested==KEYBOARD_FIELD_APPROACH_25?kKeyboardFieldApproach25Goals:kFoldedGoals)))))))));",
    }
    for old, new in replacements.items():
        if old not in runtime:
            raise ValueError(f"r114 transform marker missing: {old!r}")
        runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    required = (
        b"KEYBOARD_FIELD_APPROACH_25",
        b'{\\"T\\":419}',
        b'{\\"T\\":420}',
        b"kKeyboardFieldApproach25Goals",
    )
    if any(token not in runtime for token in required) or b"r113" in runtime:
        raise ValueError("r114 transformation incomplete")
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
        raise ValueError("Existing r114 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r114 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "trajectory": "LIMIT_DERIVED_QUINTIC_40HZ",
        "keyboard_field_approach_25_goals": list(KEYBOARD_FIELD_APPROACH_25_GOALS),
        "model_space_vertical_delta_mm": -5,
        "modeled_total_vertical_approach_mm": 25,
        "minimum_hand_tcp_world_z_mm": 51.9212,
        "minimum_nonadjacent_proxy_distance_mm": 55.7501,
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
