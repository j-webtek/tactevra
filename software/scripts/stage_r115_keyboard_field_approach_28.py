"""Add a reversible 3 mm close visual approach above the keyboard field."""

from __future__ import annotations
import hashlib
from pathlib import Path
import stage_r114_keyboard_field_approach_25 as r114

TARGET = "configured-diagnostic-candidate-r115"
KEYBOARD_FIELD_APPROACH_28_POSITIONS = (2174, 2312, 1784, 2399, 2200, 2040, 2047)
KEYBOARD_FIELD_APPROACH_28_GOALS = KEYBOARD_FIELD_APPROACH_28_POSITIONS


def sources() -> dict[str, bytes]:
    files = dict(r114.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r114", b"r115")
    replacements = {
        b'\\"KEYBOARD_FIELD_APPROACH_25\\"],\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408,409,410,411,412,413,414,415,416,417,418,419,420]': b'\\"KEYBOARD_FIELD_APPROACH_25\\",\\"KEYBOARD_FIELD_APPROACH_28\\"],\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408,409,410,411,412,413,414,415,416,417,418,419,420,421,422]',
        b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,KEYBOARD_FORWARD_CAL_1=6,KEYBOARD_DIAGONAL_CAL_2=7,KEYBOARD_FIELD_CAL_3=8,KEYBOARD_FIELD_APPROACH_10=9,KEYBOARD_FIELD_APPROACH_20=10,KEYBOARD_FIELD_APPROACH_25=11,TRANSIT=12};": b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,KEYBOARD_FORWARD_CAL_1=6,KEYBOARD_DIAGONAL_CAL_2=7,KEYBOARD_FIELD_CAL_3=8,KEYBOARD_FIELD_APPROACH_10=9,KEYBOARD_FIELD_APPROACH_20=10,KEYBOARD_FIELD_APPROACH_25=11,KEYBOARD_FIELD_APPROACH_28=12,TRANSIT=13};",
        b"static constexpr int16_t kKeyboardFieldApproach25Goals[7]={2174,2305,1791,2393,2213,2040,2047};": b"static constexpr int16_t kKeyboardFieldApproach25Goals[7]={2174,2305,1791,2393,2213,2040,2047};\n  static constexpr int16_t kKeyboardFieldApproach28Positions[7]={2174,2312,1784,2399,2200,2040,2047};\n  static constexpr int16_t kKeyboardFieldApproach28Goals[7]={2174,2312,1784,2399,2200,2040,2047};",
        b'if(strcmp(line_,"{\\"T\\":420}")==0){moveNamed(KEYBOARD_FIELD_APPROACH_20);return;}': b'if(strcmp(line_,"{\\"T\\":420}")==0){moveNamed(KEYBOARD_FIELD_APPROACH_20);return;}\n    if(strcmp(line_,"{\\"T\\":421}")==0){moveNamed(KEYBOARD_FIELD_APPROACH_28);return;}\n    if(strcmp(line_,"{\\"T\\":422}")==0){moveNamed(KEYBOARD_FIELD_APPROACH_25);return;}',
        b"if(nearPose(p,kKeyboardFieldApproach25Positions))return KEYBOARD_FIELD_APPROACH_25;": b"if(nearPose(p,kKeyboardFieldApproach25Positions))return KEYBOARD_FIELD_APPROACH_25;\n    if(nearPose(p,kKeyboardFieldApproach28Positions))return KEYBOARD_FIELD_APPROACH_28;",
        b'if(pose==KEYBOARD_FIELD_APPROACH_25)return "KEYBOARD_FIELD_APPROACH_25";': b'if(pose==KEYBOARD_FIELD_APPROACH_25)return "KEYBOARD_FIELD_APPROACH_25";\n    if(pose==KEYBOARD_FIELD_APPROACH_28)return "KEYBOARD_FIELD_APPROACH_28";',
        b"(source==KEYBOARD_FIELD_APPROACH_25&&requested==KEYBOARD_FIELD_APPROACH_20))){": b"(source==KEYBOARD_FIELD_APPROACH_25&&requested==KEYBOARD_FIELD_APPROACH_20)||\n        (source==KEYBOARD_FIELD_APPROACH_25&&requested==KEYBOARD_FIELD_APPROACH_28)||\n        (source==KEYBOARD_FIELD_APPROACH_28&&requested==KEYBOARD_FIELD_APPROACH_25))){",
        b"(requested==KEYBOARD_FIELD_APPROACH_25?kKeyboardFieldApproach25Goals:kFoldedGoals)))))))));": b"(requested==KEYBOARD_FIELD_APPROACH_25?kKeyboardFieldApproach25Goals:\n        (requested==KEYBOARD_FIELD_APPROACH_28?kKeyboardFieldApproach28Goals:kFoldedGoals))))))))));",
    }
    for old, new in replacements.items():
        if old not in runtime:
            raise ValueError(f"r115 transform marker missing: {old!r}")
        runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    required = (
        b"KEYBOARD_FIELD_APPROACH_28",
        b'{\\"T\\":421}',
        b'{\\"T\\":422}',
        b"kKeyboardFieldApproach28Goals",
    )
    if any(t not in runtime for t in required) or b"r114" in runtime:
        raise ValueError("r115 transformation incomplete")
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
        raise ValueError("Existing r115 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r115 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "trajectory": "LIMIT_DERIVED_QUINTIC_40HZ",
        "keyboard_field_approach_28_goals": list(KEYBOARD_FIELD_APPROACH_28_GOALS),
        "model_space_vertical_delta_mm": -3,
        "modeled_total_vertical_approach_mm": 28,
        "minimum_hand_tcp_world_z_mm": 48.9193,
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
