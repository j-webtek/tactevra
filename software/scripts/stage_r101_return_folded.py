"""Stage the exact reverse of the r100 straight-up ladder.

Filesystem-only.  The generated controller has no startup motion and permits
only sixteen ordered, source-checked elbow/wrist writes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r100_straight_up as outward

TARGET = "configured-diagnostic-candidate-r101"
SOURCE_POSITIONS = (2104, 2078, 2036, 1059, 1932, 2041, 1900)
TARGETS = tuple(reversed(outward.TARGETS[:-1])) + ((2604, 2485),)


def _replace_once(data: bytes, old: bytes, new: bytes) -> bytes:
    if data.count(old) != 1:
        raise ValueError(f"Pinned r100 template token count differs: {old!r}")
    return data.replace(old, new)


def sources() -> dict[str, bytes]:
    base = outward.sources()
    sketch = base["RoArm-M3_example.ino"]
    runtime = base["straight_up_runtime.h"]
    sketch = _replace_once(
        sketch, b'"straight_up_runtime.h"', b'"return_folded_runtime.h"'
    )
    sketch = _replace_once(sketch, b"StraightUpRuntime", b"ReturnFoldedRuntime")
    runtime = _replace_once(
        runtime, b"class StraightUpRuntime", b"class ReturnFoldedRuntime"
    )
    runtime = _replace_once(
        runtime, b'\\"candidate\\":\\"r100\\"', b'\\"candidate\\":\\"r101\\"'
    )
    runtime = _replace_once(
        runtime,
        b"static constexpr int16_t kSourcePositions[7]={"
        + b",".join(str(v).encode() for v in outward.SOURCE_POSITIONS)
        + b"};",
        b"static constexpr int16_t kSourcePositions[7]={"
        + b",".join(str(v).encode() for v in SOURCE_POSITIONS)
        + b"};",
    )
    old_targets = b",".join(
        b"{" + str(e).encode() + b"," + str(w).encode() + b"}"
        for e, w in outward.TARGETS
    )
    new_targets = b",".join(
        b"{" + str(e).encode() + b"," + str(w).encode() + b"}" for e, w in TARGETS
    )
    runtime = _replace_once(runtime, old_targets, new_targets)
    combined = sketch + runtime
    if combined.count(b"SyncWritePosEx") != 1:
        raise ValueError("Exactly one bounded group-write call site required")
    return {"RoArm-M3_example.ino": sketch, "return_folded_runtime.h": runtime}


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
        raise ValueError("Existing r101 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r101 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "source_positions": list(SOURCE_POSITIONS),
        "targets": [list(x) for x in TARGETS],
        "source_hashes": {
            n: hashlib.sha256(d).hexdigest() for n, d in sorted(files.items())
        },
        "startup_motion_commands": 0,
        "maximum_motion_writes": 16,
        "hardware_access": False,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(stage(Path(__file__).resolve().parents[1]), indent=2))
