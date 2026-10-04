from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/tests/unit"))

import test_typing_trace_journal_v1 as trace_support  # noqa: E402
from test_cli import _run, _workspace  # noqa: E402

from rocell.application.typing_trace_journal_v1 import (  # noqa: E402
    build_typing_trace_journal_v1,
)
from rocell.application.typing_trace_package_v1 import (  # noqa: E402
    write_typing_trace_package_v1,
)


def test_cli_replays_contained_trace_without_hardware_imports(tmp_path: Path):
    workspace = _workspace(tmp_path)
    evidence_root = workspace / "software" / "runs" / "typing-traces"
    evidence_root.mkdir(parents=True)
    artifacts = trace_support._artifacts()
    journal = build_typing_trace_journal_v1(
        artifacts, correlation_id="trace-robot-001", request_id="request-robot",
        ordered_target_ids=("R", "O", "B", "O", "T"))
    package = write_typing_trace_package_v1(
        evidence_root, journal, artifacts,
        expected_correlation_id="trace-robot-001",
        expected_request_id="request-robot")

    completed = _run(
        workspace,
        "replay-typing-trace",
        "--evidence-root", str(evidence_root),
        "--package-id", package.name,
        "--expected-correlation-id", "trace-robot-001",
        "--expected-request-id", "request-robot",
        "--require-identical",
        "--json",
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "IDENTICAL"
    assert report["identical"] is True
    assert report["authority"] == {
        "simulation_only": True,
        "hardware_accessed": False,
        "hardware_commands_generated": 0,
        "execution_authorized": False,
        "live_motion_authorized": False,
        "physical_contact_authorized": False,
        "physical_release_effect": "NONE",
    }


def test_cli_rejects_escape_identifier_without_hardware(tmp_path: Path):
    workspace = _workspace(tmp_path)
    evidence_root = workspace / "software" / "runs" / "typing-traces"
    evidence_root.mkdir(parents=True)
    completed = _run(
        workspace,
        "replay-typing-trace",
        "--evidence-root", str(evidence_root),
        "--package-id", "../escape",
        "--expected-correlation-id", "trace-robot-001",
        "--expected-request-id", "request-robot",
        "--json",
    )
    assert completed.returncode != 0
    error = json.loads(completed.stderr)
    assert error["error"]["code"] == "TYPING_TRACE_REPLAY_FAILED"
    assert error["error"]["details"]["hardware_accessed"] is False
