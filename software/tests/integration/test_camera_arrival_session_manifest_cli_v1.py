from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "software/scripts/build_camera_arrival_session_manifest_v1.py"
VERIFY_SCRIPT = ROOT / "software/scripts/verify_camera_arrival_session_manifest_v1.py"


def test_cli_exclusively_writes_zero_authority_collection_manifest(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    output = tmp_path / "session.json"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(ROOT / "software/src"), str(ROOT / "software"))
    )
    command = (
        sys.executable, str(SCRIPT), "--workspace", str(ROOT),
        "--evidence-root", str(evidence), "--session-id", "session-001",
        "--configuration-epoch-candidate", "epoch-001",
        "--camera-profile-id", "camera-v1", "--camera-profile-sha256", "1" * 64,
        "--tool-profile-id", "tool-v1", "--tool-profile-sha256", "2" * 64,
        "--output", str(output),
    )
    first = subprocess.run(
        command, capture_output=True, check=False, encoding="utf-8",
        env=environment, timeout=20,
    )
    assert first.returncode == 2
    manifest = json.loads(first.stdout)
    assert json.loads(output.read_text()) == manifest
    assert manifest["state"] == "COLLECTION_INCOMPLETE"
    assert manifest["physical_authority"] is False
    second = subprocess.run(
        command, capture_output=True, check=False, encoding="utf-8",
        env=environment, timeout=20,
    )
    assert second.returncode == 2
    assert "File exists" in second.stderr or "exists" in second.stderr

    verify = subprocess.run(
        (
            sys.executable, str(VERIFY_SCRIPT), "--workspace", str(ROOT),
            "--evidence-root", str(evidence), "--manifest", str(output),
        ),
        capture_output=True, check=False, encoding="utf-8",
        env=environment, timeout=20,
    )
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout) == manifest
