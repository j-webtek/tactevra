"""Verify and bind the locally built, flash-verified r120 controller app."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .arm_bench_qualification_contract import _canonical


R120_APP_SHA256 = "1b0589fa323a2714777f5c70453eeec6daa94bd8c92a481701689da82ce93fdc"
R120_SOURCE = Path("software/.firmware-tools/configured-diagnostic-candidate-r120/RoArm-M3_example")
R120_IMAGE = Path("software/.firmware-tools/build-configured-diagnostic-candidate-r120--default-4mb-no-psram/RoArm-M3_example.ino.bin")
R120_SESSION = Path("software/config/live_camera_feedback_session_20261015.json")
R120_JOURNAL = Path("software/runs/live-controller/app-r120-deployment-events.jsonl")


def verified_installed_r120_evidence(workspace: Path) -> bytes:
    """Return canonical evidence only when every retained r120 binding agrees."""
    workspace = Path(workspace).resolve()
    session_raw = (workspace / R120_SESSION).read_bytes()
    session = json.loads(session_raw)
    installed = session["arm_baseline"]["installed_firmware"]
    if (
        installed.get("candidate"),
        installed.get("app_sha256"),
        installed.get("startup_motion_commands"),
    ) != ("r120", R120_APP_SHA256, 0):
        raise RuntimeError("Installed r120 session evidence differs")

    journal_raw = (workspace / R120_JOURNAL).read_bytes()
    events = [json.loads(line) for line in journal_raw.splitlines() if line.strip()]
    verified = [event for event in events if event.get("stage") == "FLASH_VERIFIED"]
    if (
        len(verified) != 1
        or verified[0].get("app_sha256") != R120_APP_SHA256
        or verified[0].get("protected_regions_unchanged") is not True
    ):
        raise RuntimeError("Installed r120 deployment evidence differs")

    image = (workspace / R120_IMAGE).read_bytes()
    if hashlib.sha256(image).hexdigest() != R120_APP_SHA256:
        raise RuntimeError("Pinned r120 application image differs")
    source_paths = sorted((workspace / R120_SOURCE).glob("*"))
    sources = b"\n".join(path.read_bytes() for path in source_paths if path.is_file())
    required = (
        b"Serial.begin(115200)",
        b"Serial1.begin(1000000",
        b'if(strcmp(line_,"{\\"T\\":105}")==0){emitFeedback();return;}',
    )
    network_tokens = (b"#include <WiFi", b"WiFi.", b"WebServer", b"softAP", b"HTTPServer")
    if any(token not in sources for token in required) or any(
        token in sources for token in network_tokens
    ):
        raise RuntimeError("Pinned r120 source is not the reviewed serial-only application")
    return _canonical(
        {
            "schema": "rocell.installed_r120_evidence.v1",
            "candidate": "r120",
            "app_sha256": R120_APP_SHA256,
            "deployment_journal_sha256": hashlib.sha256(journal_raw).hexdigest(),
            "session_record_sha256": hashlib.sha256(session_raw).hexdigest(),
            "network_transport": "NOT_IMPLEMENTED_IN_APPLICATION",
            "startup_motion_commands": 0,
            "feedback_request": {"T": 105},
            "motion_authorized": False,
            "physical_authority": False,
        }
    )


__all__ = [
    "R120_APP_SHA256",
    "R120_IMAGE",
    "R120_JOURNAL",
    "R120_SESSION",
    "R120_SOURCE",
    "verified_installed_r120_evidence",
]
