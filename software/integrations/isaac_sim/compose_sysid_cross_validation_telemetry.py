"""Compose retained train and validation telemetry without touching hardware."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path


SCHEMA = "tactevra.isaac_lm0b_cross_excitation_telemetry.v1"
EXPECTED_COLUMNS = tuple(
    ["time"]
    + [f"q{index}" for index in range(1, 7)]
    + [f"dq{index}" for index in range(1, 7)]
    + [f"cmd{index}" for index in range(1, 7)]
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_csv(path: Path) -> tuple[bytes, list[dict[str, str]], float]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
        raise ValueError(f"unexpected SysID columns in {path}")
    rows = list(reader)
    if len(rows) < 2:
        raise ValueError(f"SysID telemetry is too short: {path}")
    times = [float(row["time"]) for row in rows]
    if not all(math.isfinite(value) for value in times):
        raise ValueError(f"nonfinite time in {path}")
    deltas = [right - left for left, right in zip(times, times[1:])]
    dt = deltas[0]
    if dt <= 0.0 or max(abs(delta - dt) for delta in deltas) > 1e-9:
        raise ValueError(f"nonuniform sample timing in {path}")
    for row in rows:
        if not all(math.isfinite(float(row[column])) for column in EXPECTED_COLUMNS):
            raise ValueError(f"nonfinite telemetry value in {path}")
    return raw, rows, dt


def compose(train_path: Path, validation_path: Path) -> tuple[bytes, dict[str, object]]:
    """Return deterministic CSV bytes and a source-bound composition receipt."""
    train_raw, train_rows, train_dt = _load_csv(train_path)
    validation_raw, validation_rows, validation_dt = _load_csv(validation_path)
    if abs(train_dt - validation_dt) > 1e-12:
        raise ValueError("train and validation sample periods differ")

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(EXPECTED_COLUMNS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(train_rows)
    train_end = float(train_rows[-1]["time"])
    for source in validation_rows:
        row = dict(source)
        row["time"] = format(train_end + float(source["time"]), ".17g")
        writer.writerow(row)
    output_raw = output.getvalue().encode("utf-8")

    receipt: dict[str, object] = {
        "schema": SCHEMA,
        "status": "PASS_CROSS_EXCITATION_TELEMETRY_COMPOSITION",
        "hardware_access": False,
        "physical_authority": False,
        "sample_period_seconds": train_dt,
        "train": {
            "excitation": "chirp",
            "sample_count": len(train_rows),
            "start_seconds": float(train_rows[0]["time"]),
            "end_seconds": train_end,
            "sha256": _digest(train_raw),
        },
        "validation": {
            "excitation": "sine",
            "sample_count": len(validation_rows),
            "source_start_seconds": float(validation_rows[0]["time"]),
            "source_end_seconds": float(validation_rows[-1]["time"]),
            "composed_start_seconds": train_end + float(validation_rows[0]["time"]),
            "composed_end_seconds": train_end + float(validation_rows[-1]["time"]),
            "sha256": _digest(validation_raw),
        },
        "output": {
            "sample_count": len(train_rows) + len(validation_rows),
            "sha256": _digest(output_raw),
        },
    }
    receipt["receipt_sha256"] = _digest(_canonical(receipt))
    return output_raw, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    output_raw, receipt = compose(args.train.resolve(strict=True), args.validation.resolve(strict=True))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output_raw)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
