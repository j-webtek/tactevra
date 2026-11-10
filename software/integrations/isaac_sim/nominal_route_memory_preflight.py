"""Fail-closed host-memory preflight for governed Isaac attempts.

This module is deliberately separate from the one-attempt worker.  It can be
run immediately before entering ``run_one_attempt`` so insufficient host
memory is detected before the governed output directory is claimed.
"""

from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path
from typing import Any, Mapping, NamedTuple


SCHEMA = "tactevra.isaac_nominal_route_memory_preflight.v1"
GIB = 1024**3
DEFAULT_MINIMUM_AVAILABLE_COMMIT_BYTES = 32 * GIB
DEFAULT_MINIMUM_AVAILABLE_PHYSICAL_BYTES = 16 * GIB
DEFAULT_MAXIMUM_COMMIT_UTILIZATION = 0.90


class MemoryPreflightError(RuntimeError):
    """Raised when host-memory telemetry cannot be collected safely."""


class MemorySnapshot(NamedTuple):
    total_physical_bytes: int
    available_physical_bytes: int
    commit_limit_bytes: int
    available_commit_bytes: int

    @property
    def committed_bytes(self) -> int:
        return self.commit_limit_bytes - self.available_commit_bytes

    @property
    def commit_utilization(self) -> float:
        return self.committed_bytes / self.commit_limit_bytes


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def collect_windows_memory_snapshot() -> MemorySnapshot:
    """Read physical and system commit capacity from Windows."""

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError) as exc:
        raise MemoryPreflightError("Windows memory telemetry is unavailable") from exc
    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        error = ctypes.get_last_error()
        raise MemoryPreflightError(
            f"GlobalMemoryStatusEx failed with Windows error {error}"
        )
    snapshot = MemorySnapshot(
        total_physical_bytes=int(status.ullTotalPhys),
        available_physical_bytes=int(status.ullAvailPhys),
        commit_limit_bytes=int(status.ullTotalPageFile),
        available_commit_bytes=int(status.ullAvailPageFile),
    )
    if (
        snapshot.total_physical_bytes <= 0
        or snapshot.commit_limit_bytes <= 0
        or snapshot.available_physical_bytes < 0
        or snapshot.available_commit_bytes < 0
        or snapshot.available_physical_bytes > snapshot.total_physical_bytes
        or snapshot.available_commit_bytes > snapshot.commit_limit_bytes
    ):
        raise MemoryPreflightError("Windows returned invalid memory telemetry")
    return snapshot


def evaluate_memory_preflight(
    snapshot: MemorySnapshot,
    *,
    minimum_available_commit_bytes: int = DEFAULT_MINIMUM_AVAILABLE_COMMIT_BYTES,
    minimum_available_physical_bytes: int = DEFAULT_MINIMUM_AVAILABLE_PHYSICAL_BYTES,
    maximum_commit_utilization: float = DEFAULT_MAXIMUM_COMMIT_UTILIZATION,
) -> Mapping[str, Any]:
    """Return a deterministic admission receipt without changing system state."""

    if (
        minimum_available_commit_bytes <= 0
        or minimum_available_physical_bytes <= 0
        or not 0.0 < maximum_commit_utilization < 1.0
        or snapshot.commit_limit_bytes <= 0
    ):
        raise MemoryPreflightError("invalid memory-preflight threshold")
    checks = {
        "available_commit": (
            snapshot.available_commit_bytes >= minimum_available_commit_bytes
        ),
        "available_physical": (
            snapshot.available_physical_bytes >= minimum_available_physical_bytes
        ),
        "commit_utilization": (
            snapshot.commit_utilization <= maximum_commit_utilization
        ),
    }
    admitted = all(checks.values())
    return {
        "schema": SCHEMA,
        "status": "PASS_MEMORY_PREFLIGHT" if admitted else "FAIL_MEMORY_PREFLIGHT",
        "launch_admitted": admitted,
        "snapshot": {
            "total_physical_bytes": snapshot.total_physical_bytes,
            "available_physical_bytes": snapshot.available_physical_bytes,
            "commit_limit_bytes": snapshot.commit_limit_bytes,
            "committed_bytes": snapshot.committed_bytes,
            "available_commit_bytes": snapshot.available_commit_bytes,
            "commit_utilization": snapshot.commit_utilization,
        },
        "thresholds": {
            "minimum_available_commit_bytes": minimum_available_commit_bytes,
            "minimum_available_physical_bytes": minimum_available_physical_bytes,
            "maximum_commit_utilization": maximum_commit_utilization,
        },
        "checks": checks,
        "attempt_claimed": False,
        "isaac_started": False,
        "automatic_retry": False,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "hardware_access": False,
        "physical_authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = evaluate_memory_preflight(collect_windows_memory_snapshot())
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
    print(rendered, end="")
    return 0 if receipt["launch_admitted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
