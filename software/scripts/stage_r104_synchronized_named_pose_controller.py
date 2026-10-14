"""Stage the measured-rate revision of the r103 smooth named-pose controller."""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r103_smooth_named_pose_controller as r103

TARGET = "configured-diagnostic-candidate-r104"
FOLDED_POSITIONS = r103.FOLDED_POSITIONS
FOLDED_GOALS = r103.FOLDED_GOALS
UPRIGHT_POSITIONS = r103.UPRIGHT_POSITIONS
UPRIGHT_GOALS = r103.UPRIGHT_GOALS


def sources() -> dict[str, bytes]:
    """Use the proven runtime with a trajectory the measured elbow can track."""
    transformed: dict[str, bytes] = {}
    for name, data in r103.sources().items():
        new_name = name
        revised = data.replace(b"r103", b"r104").replace(b"20000", b"40000")
        transformed[new_name] = revised
    combined = b"\n".join(transformed.values())
    if (
        b"kTrajectoryDurationMs=40000" not in combined
        or b'duration_ms\\":40000' not in combined
    ):
        raise ValueError("r104 duration substitution failed")
    if b"20000" in combined or combined.count(b"SyncWritePosEx") != 1:
        raise ValueError("r104 retained an obsolete duration or write surface")
    return transformed


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
        raise ValueError("Existing r104 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r104 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "folded_positions": list(FOLDED_POSITIONS),
        "upright_positions": list(UPRIGHT_POSITIONS),
        "trajectory": "QUINTIC_SMOOTHSTEP_40HZ",
        "duration_ms": 40000,
        "duration_basis": "measured_elbow_tracking_rate",
        "source_hashes": {
            n: hashlib.sha256(d).hexdigest() for n, d in sorted(files.items())
        },
        "startup_motion_commands": 0,
        "named_moves_reusable": True,
        "hardware_access": False,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(stage(Path(__file__).resolve().parents[1]), indent=2))
