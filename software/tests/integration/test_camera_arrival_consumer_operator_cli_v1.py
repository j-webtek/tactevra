from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from rocell.application.camera_arrival_consumer_handoff_v1 import (
    build_camera_arrival_consumer_handoff_v1,
)
from rocell.application.camera_arrival_fault_campaign_v1 import _populate


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "software/scripts/emit_camera_arrival_consumer_receipt_v1.py"


def _campaign_output() -> dict:
    core = {
        "schema": "rocell.physical_camera_localization_campaign_preflight.v1",
        "status": "READY_FOR_OFFLINE_EVALUATION", "camera_opened": False,
        "model_loaded": False, "controller_started": False,
        "hardware_writes": 0, "physical_movements": 0,
        "qualification_installed": False,
    }
    raw = json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
    return {**core, "receipt_sha256": hashlib.sha256(raw).hexdigest()}


def test_source_wrapper_emits_one_canonical_zero_authority_receipt(tmp_path: Path):
    evidence = tmp_path / "evidence"
    outputs = tmp_path / "receipts"
    evidence.mkdir()
    outputs.mkdir()
    _populate(evidence)
    handoff = build_camera_arrival_consumer_handoff_v1(ROOT, evidence)
    handoff_path = tmp_path / "handoff.json"
    native_path = tmp_path / "native.json"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    native_path.write_text(json.dumps(_campaign_output()), encoding="utf-8")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(ROOT / "software/src"), str(ROOT / "software"))
    )
    result = subprocess.run(
        (
            sys.executable, str(SCRIPT), "--handoff", str(handoff_path),
            "--artifact-id", "camera_intrinsics", "--native-output",
            str(native_path), "--validated-at-utc", "2026-09-29T15:00:00Z",
            "--output-root", str(outputs),
        ), capture_output=True, check=False, encoding="utf-8", env=environment,
        timeout=20,
    )
    assert result.returncode == 0
    summary = json.loads(result.stdout)
    receipt = json.loads((outputs / "camera_intrinsics.json").read_text())
    assert summary["receipt_sha256"] == receipt["receipt_sha256"]
    assert summary["camera_opened"] is summary["transport_opened"] is False
    assert summary["hardware_writes"] == summary["physical_movements"] == 0
    assert summary["physical_authority"] is False
