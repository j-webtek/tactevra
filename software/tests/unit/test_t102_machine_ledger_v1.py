"""Process and crash boundaries for one-use physical T102 authority."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

import rocell.application.t102_machine_ledger_v1 as ledger


REVIEW = "a" * 64
GOAL = "b" * 64
SIGNED = "c" * 64
CLAIM = "d" * 64
FIRST = "e" * 64
SECOND = "f" * 64
SOFTWARE = Path(__file__).resolve().parents[2]


def _spend_in_child(root: Path, consumption: str, *, crash_after_authority: bool):
    script = """
import os
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
import rocell.application.t102_machine_ledger_v1 as ledger
ledger.machine_root = lambda: Path(sys.argv[2])
if sys.argv[4] == 'crash':
    original = ledger._write_new
    def write_then_crash(path, value):
        original(path, value)
        if path.name.startswith('authority-'):
            os._exit(7)
    ledger._write_new = write_then_crash
ledger.spend_execution(sys.argv[3], 'a'*64, 'b'*64, 'authority-1',
                       'issuer-1', 'c'*64, 'd'*64)
"""
    return subprocess.run(
        [sys.executable, "-c", script, str(SOFTWARE / "src"), str(root),
         consumption, "crash" if crash_after_authority else "normal"],
        capture_output=True, text=True, timeout=15, check=False,
    )


def test_authority_spent_before_crash_rejects_alternate_receipt_in_new_process(
    tmp_path, monkeypatch,
):
    root = tmp_path / "machine-ledger"
    root.mkdir()
    monkeypatch.setattr(ledger, "machine_root", lambda: root)
    ledger.reserve_review(FIRST, REVIEW, GOAL)

    crashed = _spend_in_child(root, FIRST, crash_after_authority=True)
    assert crashed.returncode == 7
    assert len(tuple(root.glob("authority-*.json"))) == 1
    assert not tuple(root.glob("execution-*.json"))

    ledger.reserve_review(SECOND, REVIEW, GOAL)
    replay = _spend_in_child(root, SECOND, crash_after_authority=False)
    assert replay.returncode != 0
    assert "already spent" in replay.stderr
    assert not tuple(root.glob("execution-*.json"))


def test_completed_spend_rejects_reconstructed_process(tmp_path, monkeypatch):
    root = tmp_path / "machine-ledger"
    root.mkdir()
    monkeypatch.setattr(ledger, "machine_root", lambda: root)
    ledger.reserve_review(FIRST, REVIEW, GOAL)
    assert _spend_in_child(root, FIRST, crash_after_authority=False).returncode == 0
    with pytest.raises(ledger.T102MachineLedgerError, match="already spent"):
        ledger.spend_execution(FIRST, REVIEW, GOAL, "authority-1",
                               "issuer-1", SIGNED, CLAIM)
