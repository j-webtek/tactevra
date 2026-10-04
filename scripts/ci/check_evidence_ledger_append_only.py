#!/usr/bin/env python3
"""Reject deletion or rewriting of the repository evidence ledger."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
LEDGER = Path("software/ai/docs/EVIDENCE_LEDGER.md")


def git(*arguments: str, root: Path = ROOT, text: bool = False) -> bytes | str:
    return subprocess.check_output(
        ["git", *arguments], cwd=root, text=text, stderr=subprocess.PIPE
    )


def resolve_base(root: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    configured = os.environ.get("EVIDENCE_LEDGER_BASE_REF")
    if configured:
        return configured
    github_base = os.environ.get("GITHUB_BASE_REF")
    if github_base:
        remote_ref = f"origin/{github_base}"
        try:
            return str(git("merge-base", "HEAD", remote_ref, root=root, text=True)).strip()
        except subprocess.CalledProcessError as exc:
            raise ValueError(
                f"cannot resolve merge base for {remote_ref}; CI checkout must fetch history"
            ) from exc
    dirty = subprocess.run(
        ["git", "diff", "--quiet", "--", str(LEDGER)], cwd=root, check=False
    ).returncode
    return "HEAD" if dirty else "HEAD^"


def check_append_only(root: Path, base_ref: str) -> tuple[int, int]:
    try:
        old = git("show", f"{base_ref}:{LEDGER.as_posix()}", root=root)
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"cannot read ledger at base ref {base_ref!r}") from exc
    current_path = root / LEDGER
    if not current_path.is_file():
        raise ValueError(f"current ledger is missing: {LEDGER}")
    current = current_path.read_bytes()
    if len(current) < len(old):
        raise ValueError(
            f"ledger shrank from {len(old)} to {len(current)} bytes relative to {base_ref}"
        )
    if current[: len(old)] != old:
        mismatch = next(
            (index for index, (before, after) in enumerate(zip(old, current)) if before != after),
            min(len(old), len(current)),
        )
        raise ValueError(
            "existing evidence-ledger bytes changed relative to "
            f"{base_ref}; first mismatch at byte {mismatch}"
        )
    return len(old), len(current)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", help="Git revision containing the ledger prefix")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        base = resolve_base(args.root, args.base_ref)
        old_size, current_size = check_append_only(args.root, base)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: evidence ledger append-only check: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS: evidence ledger preserves its exact existing prefix at "
        f"{base} ({old_size} -> {current_size} bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
