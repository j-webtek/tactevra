#!/usr/bin/env python3
"""Reject deletion or rewriting of the repository evidence ledger."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Mapping


ROOT = Path(__file__).resolve().parents[2]
LEDGER = Path("software/ai/docs/EVIDENCE_LEDGER.md")
EVIDENCE_HEADING = re.compile(r"^### (E-[A-Za-z0-9-]+)(?:\s|$)")

# These duplicate pairs predate the uniqueness policy. The append-only rule
# forbids renaming either heading. Pinning the exact inherited counts preserves
# that evidence while ensuring another occurrence, or any new duplicate ID,
# fails CI.
HISTORICAL_DUPLICATE_ID_COUNTS = {
    "E-20260926-INT-001": 2,
    "E-20261003-AI-558": 2,
    "E-20261003-AI-561": 2,
    "E-20261003-AI-562": 2,
    "E-20261004-INT-656": 2,
    "E-20261004-INT-657": 2,
}


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


def check_unique_ids(
    ledger: bytes,
    allowed_duplicate_counts: Mapping[str, int] | None = None,
) -> int:
    """Reject repeated evidence-heading IDs outside the pinned historical set."""

    try:
        lines = ledger.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("current ledger is not valid UTF-8") from exc

    locations: dict[str, list[int]] = defaultdict(list)
    for line_number, line in enumerate(lines, start=1):
        match = EVIDENCE_HEADING.match(line)
        if match:
            locations[match.group(1)].append(line_number)

    counts = Counter({evidence_id: len(rows) for evidence_id, rows in locations.items()})
    allowed = dict(allowed_duplicate_counts or {})
    violations = []
    for evidence_id, count in sorted(counts.items()):
        if count <= 1:
            continue
        if allowed.get(evidence_id) == count:
            continue
        rows = ", ".join(str(row) for row in locations[evidence_id])
        allowance = allowed.get(evidence_id)
        suffix = f"; historical allowance is {allowance}" if allowance else ""
        violations.append(f"{evidence_id} occurs {count} times on lines {rows}{suffix}")

    if violations:
        raise ValueError("repeated evidence ID(s): " + "; ".join(violations))
    return len(locations)


def check_append_only(
    root: Path,
    base_ref: str,
    *,
    allowed_duplicate_counts: Mapping[str, int] | None = None,
) -> tuple[int, int]:
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
    check_unique_ids(current, allowed_duplicate_counts)
    return len(old), len(current)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", help="Git revision containing the ledger prefix")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        base = resolve_base(args.root, args.base_ref)
        old_size, current_size = check_append_only(
            args.root,
            base,
            allowed_duplicate_counts=HISTORICAL_DUPLICATE_ID_COUNTS,
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: evidence ledger append-only check: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS: evidence ledger preserves its exact existing prefix at "
        f"{base} ({old_size} -> {current_size} bytes); evidence IDs are unique "
        f"apart from {len(HISTORICAL_DUPLICATE_ID_COUNTS)} pinned historical pairs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
