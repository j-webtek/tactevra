"""Retain the repository-bound PC9 arrival-consumer dry run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / "software" / "src"))

from rocell.application.camera_arrival_consumer_map_v1 import (  # noqa: E402
    build_camera_arrival_consumer_map_v1,
)


DEFAULT_OUTPUT = Path(
    "software/ai/eval/camera_arrival_consumer_map_dry_run_v1.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    args = parser.parse_args()
    candidate = Path(args.output)
    if candidate.is_absolute():
        raise ValueError("output must be workspace-relative")
    output = (WORKSPACE / candidate).resolve()
    if WORKSPACE.resolve() not in output.parents:
        raise ValueError("output escapes workspace")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"refusing to overwrite {output}")
    document = build_camera_arrival_consumer_map_v1(WORKSPACE)
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
        "consumer_map_sha256": document["consumer_map_sha256"],
        "slot_count": document["slot_count"],
        "measured_originals_consumed": 0,
        "physical_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
