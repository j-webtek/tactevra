from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.application.camera_arrival_kit_v1 import (
    build_camera_arrival_kit_v1,
    validate_camera_arrival_kit_v1,
)


ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "software/ai/eval/camera_arrival_kit_dry_run_v1.json"
FILE_SHA256 = "2a3c71f578626e6e4c8e0f1b56e7004f64c99643ce734325545b7a4d043b5808"


def test_retained_camera_arrival_kit_is_exact_canonical_dry_run():
    raw = REPORT.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FILE_SHA256
    assert raw == raw.rstrip(b"\n") + b"\n"
    document = json.loads(raw)
    assert document == build_camera_arrival_kit_v1()
    assert validate_camera_arrival_kit_v1(document) == document
