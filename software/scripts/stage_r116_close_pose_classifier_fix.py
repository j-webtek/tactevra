"""Prefer the closest keyboard approach pose when tolerance bands overlap."""

from __future__ import annotations
import hashlib
from pathlib import Path
import stage_r115_keyboard_field_approach_28 as r115

TARGET = "configured-diagnostic-candidate-r116"


def sources() -> dict[str, bytes]:
    files = dict(r115.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r115", b"r116")
    old = (
        b"if(nearPose(p,kKeyboardFieldApproach25Positions))return KEYBOARD_FIELD_APPROACH_25;\n"
        b"    if(nearPose(p,kKeyboardFieldApproach28Positions))return KEYBOARD_FIELD_APPROACH_28;"
    )
    new = (
        b"if(nearPose(p,kKeyboardFieldApproach28Positions))return KEYBOARD_FIELD_APPROACH_28;\n"
        b"    if(nearPose(p,kKeyboardFieldApproach25Positions))return KEYBOARD_FIELD_APPROACH_25;"
    )
    if old not in runtime:
        raise ValueError("r116 classifier marker missing")
    runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    if b"r115" in runtime or runtime.find(
        b"kKeyboardFieldApproach28Positions"
    ) > runtime.find(
        b"kKeyboardFieldApproach25Positions", runtime.find(b"Pose classify")
    ):
        raise ValueError("r116 classifier transformation incomplete")
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
        raise ValueError("Existing r116 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r116 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "change": "CLOSE_POSE_CLASSIFIER_PRECEDENCE_ONLY",
        "motion_commands_added": 0,
        "startup_motion_commands": 0,
        "contact_commands": 0,
        "hardware_access": False,
        "source_hashes": {
            n: hashlib.sha256(d).hexdigest() for n, d in sorted(files.items())
        },
    }


if __name__ == "__main__":
    import json

    print(json.dumps(stage(Path(__file__).resolve().parents[1]), indent=2))
