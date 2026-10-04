from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "software/scripts/run_camera_arrival_fault_campaign_v1.py"


def test_fault_campaign_cli_reproduces_retained_report():
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(ROOT / "software/src"), str(ROOT / "software"))
    )
    result = subprocess.run(
        (sys.executable, str(SCRIPT), "--workspace", str(ROOT)),
        capture_output=True, check=False, encoding="utf-8", env=environment,
        timeout=30,
    )
    assert result.returncode == 0
    actual = json.loads(result.stdout)
    retained = json.loads((
        ROOT / "software/ai/eval/camera_arrival_fault_campaign_v1.json"
    ).read_text(encoding="utf-8"))
    assert actual == retained
