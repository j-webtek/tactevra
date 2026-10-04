from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from rocell.application.camera_arrival_consumer_handoff_v1 import main


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "software/scripts/route_camera_arrival_consumers_v1.py"


def test_installed_module_exposes_application_entry_point():
    assert callable(main)


def test_cli_routes_empty_root_without_invoking_consumers(tmp_path: Path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(ROOT / "software/src"), str(ROOT / "software"))
    )
    result = subprocess.run(
        (
            sys.executable, str(SCRIPT), "--workspace", str(ROOT),
            "--evidence-root", str(tmp_path),
        ), capture_output=True, check=False, encoding="utf-8", env=environment,
        timeout=10,
    )
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "BLOCKED_ARRIVAL_PREFLIGHT_INCOMPLETE"
    assert report["slot_count"] == 15
    assert report["ready_slot_count"] == 0
    assert report["consumer_validation_completed"] is False
    assert report["camera_opened"] is report["controller_started"] is False
    assert report["hardware_writes"] == report["physical_movements"] == 0
    assert report["physical_authority"] is False
