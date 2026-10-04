#!/usr/bin/env python3
"""One portable entry point for routine Tactevra repository maintenance."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

POLICY_CHECKS = [
    ["scripts/ci/check_evidence_ledger_append_only.py"],
    ["scripts/ci/check_docs.py"],
    ["scripts/ci/check_public_records.py"],
    ["scripts/ci/check_evidence_scope.py"],
    ["scripts/ci/check_repository_artifacts.py"],
    ["scripts/ci/check_repository_health.py", "--policy-only"],
    ["scripts/ci/check_source_archive_footprint.py"],
    ["scripts/ci/check_release_integrity.py", "--mode", "policy"],
    ["scripts/ci/check_release_readiness_sync.py"],
]


def run(command: list[str]) -> None:
    rendered = " ".join(command)
    print(f"\n==> {rendered}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def verify(full: bool) -> None:
    run([sys.executable, "-m", "compileall", "-q", "scripts/ci"])
    run([sys.executable, "-m", "unittest", "discover", "-s", "scripts/ci", "-p", "test_*.py"])
    for arguments in POLICY_CHECKS:
        run([sys.executable, *arguments])
    if full:
        run([sys.executable, "scripts/ci/offline_checks.py", "test"])
    print("\nRepository verification passed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify", help="run repository policy and CI-unit checks")
    verify_parser.add_argument("--full", action="store_true", help="also run the installed-package test suite")
    sync_parser = subparsers.add_parser("sync-readiness", help="refresh generated readiness surfaces")
    sync_parser.add_argument("--apply-github", action="store_true", help="also repair the live tracker and milestone")
    report_parser = subparsers.add_parser("report", help="build the weekly operations report")
    report_parser.add_argument("--output-dir", type=Path, default=ROOT / ".repository-operations")
    args = parser.parse_args()
    try:
        if args.command == "verify":
            verify(args.full)
        elif args.command == "sync-readiness":
            command = [sys.executable, "scripts/ci/check_release_readiness_sync.py", "--write-dashboard"]
            if args.apply_github:
                command.extend(["--apply-github", "--repository", "j-webtek/tactevra"])
            run(command)
        else:
            run([sys.executable, "scripts/ci/build_repository_operations_report.py", "--output-dir", str(args.output_dir)])
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
