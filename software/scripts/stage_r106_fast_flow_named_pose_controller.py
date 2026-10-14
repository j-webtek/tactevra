"""Stage the faster measured-envelope revision of the r105 controller."""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r105_minimum_time_named_pose_controller as r105

TARGET = "configured-diagnostic-candidate-r106"


def sources() -> dict[str, bytes]:
    files = dict(r105.sources())
    runtime = files["smooth_named_pose_runtime.h"].replace(b"r105", b"r106")
    replacements = {
        b"{160,160,160,170,120,160,160}": b"{220,220,220,220,150,220,220}",
        b"{300,300,300,100,120,300,300}": b"{400,400,400,150,180,400,400}",
        b"{1200,1200,1200,400,500,1200,1200}": b"{1600,1600,1600,600,700,1600,1600}",
        b"kDurationMargin=1.08f": b"kDurationMargin=1.05f",
        b"speeds[7]={240,240,240,240,240,240,240}": b"speeds[7]={400,400,400,400,400,400,400}",
        b"accelerations[7]={20,20,20,20,20,20,20}": b"accelerations[7]={30,30,30,30,30,30,30}",
    }
    for old, new in replacements.items():
        if old not in runtime:
            raise ValueError(f"r106 transform marker missing: {old!r}")
        runtime = runtime.replace(old, new)
    files["smooth_named_pose_runtime.h"] = runtime
    if b"r105" in runtime or b"kDurationMargin=1.05f" not in runtime:
        raise ValueError("r106 transformation incomplete")
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
        raise ValueError("Existing r106 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r106 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "trajectory": "LIMIT_DERIVED_QUINTIC_40HZ",
        "duration_policy": "FAST_FLOW_MEASURED_ENVELOPE",
        "source_hashes": {
            n: hashlib.sha256(d).hexdigest() for n, d in sorted(files.items())
        },
        "startup_motion_commands": 0,
        "hardware_access": False,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(stage(Path(__file__).resolve().parents[1]), indent=2))
