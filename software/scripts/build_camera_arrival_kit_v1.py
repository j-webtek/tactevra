"""Generate the canonical zero-I/O PC9 camera-arrival kit dry run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / "software" / "src"))

from rocell.application.camera_arrival_kit_v1 import (  # noqa: E402
    build_camera_arrival_kit_v1,
    validate_camera_arrival_kit_v1,
)


DEFAULT_OUTPUT = Path("software/ai/eval/camera_arrival_kit_dry_run_v1.json")


def _resolve_output(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError("output must be workspace-relative")
    resolved = (WORKSPACE / candidate).resolve()
    if WORKSPACE not in resolved.parents:
        raise ValueError("output escapes workspace")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    args = parser.parse_args()
    output = _resolve_output(args.output)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"refusing to overwrite {output}")
    document = build_camera_arrival_kit_v1()
    validate_camera_arrival_kit_v1(document)
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(payload)
        stream.flush()
    print(json.dumps({
        "output": output.relative_to(WORKSPACE).as_posix(),
        "arrival_kit_sha256": document["arrival_kit_sha256"],
        "measured_slot_count": 0,
        "camera_opened": False,
        "physical_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
