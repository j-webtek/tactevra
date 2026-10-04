"""Run the portable source-preview checks from an identity-bound clean checkout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CHECKS = (
    ("evidence_ledger_append_only", ("scripts/ci/check_evidence_ledger_append_only.py",)),
    ("maintained_docs", ("scripts/ci/check_docs.py",)),
    ("public_records", ("scripts/ci/check_public_records.py",)),
    ("evidence_scope", ("scripts/ci/check_evidence_scope.py",)),
    ("repository_health_policy", ("scripts/ci/check_repository_health.py", "--policy-only")),
    ("source_archive_footprint", ("scripts/ci/check_source_archive_footprint.py",)),
    ("snapshot_audit", ("scripts/audit_github_snapshot.py",)),
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def validate_identity(expected_sha: str | None) -> str:
    actual = git("rev-parse", "HEAD").lower()
    if not re.fullmatch(r"[0-9a-f]{40}", actual):
        raise ValueError("HEAD did not resolve to a full commit SHA")
    if expected_sha is not None:
        expected = expected_sha.lower()
        if not re.fullmatch(r"[0-9a-f]{40}", expected):
            raise ValueError("expected SHA must be 40 hexadecimal characters")
        if actual != expected:
            raise ValueError(f"checked out {actual}, expected {expected}")
    return actual


def require_clean_tracked_tree() -> None:
    for args, label in ((["diff", "--quiet"], "working tree"),
                        (["diff", "--cached", "--quiet"], "index")):
        result = subprocess.run(["git", *args], cwd=ROOT, check=False)
        if result.returncode != 0:
            raise ValueError(f"tracked {label} is not clean")


def run_check(name: str, arguments: tuple[str, ...]) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, *arguments], cwd=ROOT, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    output = result.stdout.strip()
    return {"name": name, "exit_code": result.returncode, "output": output[-2000:]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha")
    parser.add_argument("--mode", choices=("policy", "candidate"), default="policy")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    try:
        commit = validate_identity(args.expected_sha)
        require_clean_tracked_tree()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"clean-checkout precondition failed: {exc}") from exc

    checks = [run_check(name, arguments) for name, arguments in CHECKS]
    checks.append(run_check(
        "release_integrity",
        ("scripts/ci/check_release_integrity.py", "--mode", args.mode),
    ))
    receipt = {
        "schema": "tactevra.clean-checkout-receipt.v1",
        "commit": commit,
        "mode": args.mode,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "status": "pass" if all(item["exit_code"] == 0 for item in checks) else "fail",
        "checks": checks,
        "limitations": [
            "No external AI checkpoint is downloaded or verified by this command.",
            "GitHub issue, review, and approval state is not queried by this command.",
            "No hardware, controller transport, firmware, or release operation is performed.",
        ],
    }
    serialized = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
