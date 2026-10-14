"""Resolve immutable evidence inputs after an active config pointer advances."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ZERO_AUTHORITY_SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_hash_bound_source(
    workspace: Path,
    binding: Mapping[str, Any],
) -> Path:
    """Resolve exact bound bytes, falling back to a controlled config freeze."""

    declared = Path(str(binding["path"]))
    expected = str(binding["sha256"])
    source = declared if declared.is_absolute() else workspace / declared
    if source.is_file() and not source.is_symlink() and _sha256(source) == expected:
        return source

    if declared.is_absolute() or tuple(declared.parts[:2]) != ("software", "config"):
        raise ValueError(f"bound source changed: {binding['path']}")

    freeze_root = workspace / "software" / "freezes"
    matches = sorted(
        candidate
        for candidate in freeze_root.glob(f"*/{declared.name}")
        if candidate.is_file()
        and not candidate.is_symlink()
        and _sha256(candidate) == expected
    )
    if not matches:
        raise ValueError(f"bound source changed: {binding['path']}")
    return matches[0]


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def load_compatible_emulator_fixture(path: Path, *, workspace: Path) -> dict[str, Any]:
    """Load an immutable emulator fixture while resolving frozen config bytes."""

    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _canonical_sha256(value) != claimed:
        raise ValueError("controller-emulator fixture hash mismatch")
    value["fixture_sha256"] = claimed

    section = value["controller_emulator"]
    section_claimed = section.pop("section_sha256")
    if _canonical_sha256(section) != section_claimed:
        raise ValueError("controller-emulator section hash mismatch")
    section["section_sha256"] = section_claimed
    if value["scope"] != ZERO_AUTHORITY_SCOPE or any(value["counters"].values()):
        raise ValueError("controller-emulator fixture changed zero-authority scope")
    for binding in value["bindings"].values():
        resolve_hash_bound_source(workspace, binding)
    return value


def load_compatible_first_motion_fixture(
    path: Path, *, workspace: Path
) -> dict[str, Any]:
    """Load first-motion evidence while resolving exact frozen config inputs."""

    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _canonical_sha256(value) != claimed:
        raise ValueError("first-motion fixture hash mismatch")
    value["fixture_sha256"] = claimed
    for name in ("phase3", "phase4", "phase5"):
        section = value[name]
        section_claimed = section.pop("section_sha256")
        if _canonical_sha256(section) != section_claimed:
            raise ValueError(f"{name} section hash mismatch")
        section["section_sha256"] = section_claimed
    if value["scope"] != ZERO_AUTHORITY_SCOPE or any(value["counters"].values()):
        raise ValueError("first-motion fixture changed zero-authority scope")
    for binding in value["bindings"].values():
        resolve_hash_bound_source(workspace, binding)
    return value
