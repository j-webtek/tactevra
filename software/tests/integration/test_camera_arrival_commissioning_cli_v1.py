from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from rocell.application.camera_arrival_commissioning_orchestrator_v1 import main


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "software/scripts/run_camera_arrival_commissioning_v1.py"


def test_installed_module_exposes_application_entry_point():
    assert callable(main)


def test_cli_reports_empty_root_as_zero_authority_blocker(tmp_path: Path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(ROOT / "software/src"), str(ROOT / "software"))
    )
    result = subprocess.run(
        (
            sys.executable, str(SCRIPT), "--workspace", str(ROOT),
            "--evidence-root", str(tmp_path),
        ), capture_output=True, check=False, encoding="utf-8", env=environment,
        timeout=15,
    )
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "BLOCKED_ARRIVAL_EVIDENCE_INCOMPLETE"
    assert report["assessment"]["blocked_count"] == 15
    assert report["camera_opened"] is report["transport_opened"] is False
    assert report["controller_commands"] == []
    assert report["hardware_writes"] == report["physical_movements"] == 0
    assert report["physical_authority"] is False
