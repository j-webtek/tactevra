"""Add a reversible 10 mm visual approach above the keyboard field."""

from __future__ import annotations
import hashlib
from pathlib import Path
import stage_r116_close_pose_classifier_fix as r116

TARGET = "configured-diagnostic-candidate-r117"
KEYBOARD_FIELD_APPROACH_38_POSITIONS = (2174, 2337, 1759, 2416, 2158, 2040, 2047)
KEYBOARD_FIELD_APPROACH_38_GOALS = KEYBOARD_FIELD_APPROACH_38_POSITIONS


def sources() -> dict[str, bytes]:
    files = dict(r116.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r116", b"r117")
    replacements = {
        b'\\"KEYBOARD_FIELD_APPROACH_28\\"],\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408,409,410,411,412,413,414,415,416,417,418,419,420,421,422]': b'\\"KEYBOARD_FIELD_APPROACH_28\\",\\"KEYBOARD_FIELD_APPROACH_38\\"],\\"supported_commands\\":[105,400,401,402,403,404,405,406,407,408,409,410,411,412,413,414,415,416,417,418,419,420,421,422,423,424]',
        b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,KEYBOARD_FORWARD_CAL_1=6,KEYBOARD_DIAGONAL_CAL_2=7,KEYBOARD_FIELD_CAL_3=8,KEYBOARD_FIELD_APPROACH_10=9,KEYBOARD_FIELD_APPROACH_20=10,KEYBOARD_FIELD_APPROACH_25=11,KEYBOARD_FIELD_APPROACH_28=12,TRANSIT=13};": b"enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,AIR_HOVER_A=3,KEYBOARD_A_HOVER=4,KEYBOARD_A_LOW_AIR=5,KEYBOARD_FORWARD_CAL_1=6,KEYBOARD_DIAGONAL_CAL_2=7,KEYBOARD_FIELD_CAL_3=8,KEYBOARD_FIELD_APPROACH_10=9,KEYBOARD_FIELD_APPROACH_20=10,KEYBOARD_FIELD_APPROACH_25=11,KEYBOARD_FIELD_APPROACH_28=12,KEYBOARD_FIELD_APPROACH_38=13,TRANSIT=14};",
        b"static constexpr int16_t kKeyboardFieldApproach28Goals[7]={2174,2312,1784,2399,2200,2040,2047};": b"static constexpr int16_t kKeyboardFieldApproach28Goals[7]={2174,2312,1784,2399,2200,2040,2047};\n  static constexpr int16_t kKeyboardFieldApproach38Positions[7]={2174,2337,1759,2416,2158,2040,2047};\n  static constexpr int16_t kKeyboardFieldApproach38Goals[7]={2174,2337,1759,2416,2158,2040,2047};",
        b'if(strcmp(line_,"{\\"T\\":422}")==0){moveNamed(KEYBOARD_FIELD_APPROACH_25);return;}': b'if(strcmp(line_,"{\\"T\\":422}")==0){moveNamed(KEYBOARD_FIELD_APPROACH_25);return;}\n    if(strcmp(line_,"{\\"T\\":423}")==0){moveNamed(KEYBOARD_FIELD_APPROACH_38);return;}\n    if(strcmp(line_,"{\\"T\\":424}")==0){moveNamed(KEYBOARD_FIELD_APPROACH_28);return;}',
        b"if(nearPose(p,kKeyboardFieldApproach28Positions))return KEYBOARD_FIELD_APPROACH_28;": b"if(nearPose(p,kKeyboardFieldApproach38Positions))return KEYBOARD_FIELD_APPROACH_38;\n    if(nearPose(p,kKeyboardFieldApproach28Positions))return KEYBOARD_FIELD_APPROACH_28;",
        b'if(pose==KEYBOARD_FIELD_APPROACH_28)return "KEYBOARD_FIELD_APPROACH_28";': b'if(pose==KEYBOARD_FIELD_APPROACH_28)return "KEYBOARD_FIELD_APPROACH_28";\n    if(pose==KEYBOARD_FIELD_APPROACH_38)return "KEYBOARD_FIELD_APPROACH_38";',
        b"(source==KEYBOARD_FIELD_APPROACH_28&&requested==KEYBOARD_FIELD_APPROACH_25))){": b"(source==KEYBOARD_FIELD_APPROACH_28&&requested==KEYBOARD_FIELD_APPROACH_25)||\n        (source==KEYBOARD_FIELD_APPROACH_28&&requested==KEYBOARD_FIELD_APPROACH_38)||\n        (source==KEYBOARD_FIELD_APPROACH_38&&requested==KEYBOARD_FIELD_APPROACH_28))){",
        b"(requested==KEYBOARD_FIELD_APPROACH_28?kKeyboardFieldApproach28Goals:kFoldedGoals))))))))));": b"(requested==KEYBOARD_FIELD_APPROACH_28?kKeyboardFieldApproach28Goals:\n        (requested==KEYBOARD_FIELD_APPROACH_38?kKeyboardFieldApproach38Goals:kFoldedGoals)))))))))));",
    }
    for old, new in replacements.items():
        if old not in runtime:
            raise ValueError(f"r117 transform marker missing: {old!r}")
        runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    required = (
        b"KEYBOARD_FIELD_APPROACH_38",
        b'{\\"T\\":423}',
        b'{\\"T\\":424}',
        b"kKeyboardFieldApproach38Goals",
    )
    start = runtime.find(b"Pose classify")
    if (
        any(t not in runtime for t in required)
        or b"r116" in runtime
        or runtime.find(b"kKeyboardFieldApproach38Positions", start)
        > runtime.find(b"kKeyboardFieldApproach28Positions", start)
    ):
        raise ValueError("r117 transformation incomplete")
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
        raise ValueError("Existing r117 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r117 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "trajectory": "LIMIT_DERIVED_QUINTIC_40HZ",
        "keyboard_field_approach_38_goals": list(KEYBOARD_FIELD_APPROACH_38_GOALS),
        "model_space_vertical_delta_mm": -10,
        "modeled_total_vertical_approach_mm": 38,
        "minimum_hand_tcp_world_z_mm": 38.91168,
        "minimum_nonadjacent_proxy_distance_mm": 55.75012,
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
