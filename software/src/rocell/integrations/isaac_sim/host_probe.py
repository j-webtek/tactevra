"""Reproducible, zero-authority inventory for an Isaac Sim runner candidate.

The probe imports no Isaac or Torch modules.  It inspects installed distribution
metadata and ``nvidia-smi`` output, so collecting evidence cannot initialize a
simulator, open a controller transport, or move hardware.
"""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from typing import Callable, Iterable, Mapping, Sequence

from .contracts import canonical_sha256

PROBE_SCHEMA = "rocell.isaac_sim_host_probe.v1"
DEFAULT_TESTED_DRIVER = "595.97"
_ISAAC_PREFIX = "isaacsim"
_BOUND_PACKAGES = ("torch",)
_VERSION_PART = re.compile(r"\d+")


@dataclass(frozen=True, slots=True)
class DistributionRecord:
    name: str
    version: str
    metadata_sha256: str
    record_sha256: str

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "version": self.version,
            "metadata_sha256": self.metadata_sha256,
            "record_sha256": self.record_sha256,
        }


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _distribution_records(
    distributions: Iterable[metadata.Distribution] | None = None,
) -> list[DistributionRecord]:
    records: list[DistributionRecord] = []
    source = metadata.distributions() if distributions is None else distributions
    for distribution in source:
        name = (distribution.metadata.get("Name") or "").strip().lower()
        if not (name.startswith(_ISAAC_PREFIX) or name in _BOUND_PACKAGES):
            continue
        package_metadata = distribution.read_text("METADATA") or ""
        record = distribution.read_text("RECORD") or ""
        records.append(
            DistributionRecord(
                name=name,
                version=distribution.version,
                metadata_sha256=_sha256_text(package_metadata),
                record_sha256=_sha256_text(record),
            )
        )
    records.sort(key=lambda item: item.name)
    return records


def _parse_version(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in _VERSION_PART.findall(value))


def _driver_at_least(actual: str, expected: str) -> bool:
    left = _parse_version(actual)
    right = _parse_version(expected)
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) >= right + (0,) * (width - len(right))


def _query_nvidia(
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    query = (
        "index,name,memory.total,driver_version,compute_cap"
    )
    completed = run(
        ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    gpus: list[dict[str, object]] = []
    drivers: set[str] = set()
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 5:
            raise RuntimeError("unexpected nvidia-smi CSV shape")
        index, name, memory_mb, driver, capability = fields
        drivers.add(driver)
        gpus.append({
            "index": int(index),
            "name": name,
            "memory_total_mb": int(memory_mb),
            "compute_capability": capability,
        })
    if not gpus or len(drivers) != 1:
        raise RuntimeError("nvidia-smi did not report one consistent driver")
    gpus.sort(key=lambda item: int(item["index"]))
    return {"driver_version": drivers.pop(), "gpus": gpus}


def _physical_memory_bytes() -> int:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("GlobalMemoryStatusEx failed")
        return int(status.total_physical)
    page_size = os.sysconf("SC_PAGE_SIZE")
    page_count = os.sysconf("SC_PHYS_PAGES")
    return int(page_size * page_count)


def build_probe(
    *,
    captured_at: str,
    host: Mapping[str, object],
    nvidia: Mapping[str, object],
    python: Mapping[str, object],
    distributions: Sequence[DistributionRecord],
    tested_driver: str = DEFAULT_TESTED_DRIVER,
) -> dict[str, object]:
    """Build a canonical report from explicit inputs for deterministic tests."""
    packages = [record.as_dict() for record in sorted(distributions, key=lambda item: item.name)]
    isaac_packages = [item for item in packages if item["name"].startswith(_ISAAC_PREFIX)]
    primary = next((item for item in isaac_packages if item["name"] == "isaacsim"), None)
    if primary is None:
        raise RuntimeError("the isaacsim distribution is not installed")
    extension_packages = [
        item for item in isaac_packages if item["name"].startswith("isaacsim-extscache")
    ]
    if not extension_packages:
        raise RuntimeError("no Isaac Sim extension cache distributions are installed")
    installation_identity = {
        "python_version": python["version"],
        "packages": packages,
    }
    extension_identity = {
        "isaac_sim_version": primary["version"],
        "packages": extension_packages,
    }
    driver = str(nvidia["driver_version"])
    requirements = {
        "tested_driver_minimum": tested_driver,
        "driver_meets_tested_minimum": _driver_at_least(driver, tested_driver),
        "ram_at_least_32_gib": int(host["physical_memory_bytes"]) >= 32 * 1024**3,
        "each_gpu_at_least_16_gib": all(
            int(gpu["memory_total_mb"]) >= 16 * 1024
            for gpu in nvidia["gpus"]  # type: ignore[index]
        ),
        "gpu_model_in_documented_minimum_set": all(
            "RTX 4080" in str(gpu["name"]) or "RTX 4090" in str(gpu["name"])
            or "RTX 5080" in str(gpu["name"]) or "RTX 5090" in str(gpu["name"])
            or "RTX PRO" in str(gpu["name"])
            for gpu in nvidia["gpus"]  # type: ignore[index]
        ),
    }
    blockers = []
    if not requirements["driver_meets_tested_minimum"]:
        blockers.append("DRIVER_BELOW_TESTED_MINIMUM")
    if not requirements["ram_at_least_32_gib"]:
        blockers.append("RAM_BELOW_MINIMUM")
    if not requirements["each_gpu_at_least_16_gib"]:
        blockers.append("GPU_MEMORY_BELOW_MINIMUM")
    if not requirements["gpu_model_in_documented_minimum_set"]:
        blockers.append("GPU_MODEL_NOT_IN_DOCUMENTED_MINIMUM_SET")
    blockers.extend(["ISAAC_EULA_NOT_ACCEPTED_BY_AUTOMATION", "APPLICATION_NOT_LAUNCHED"])
    report: dict[str, object] = {
        "schema": PROBE_SCHEMA,
        "captured_at": captured_at,
        "host": dict(host),
        "nvidia": {"driver_version": driver, "gpus": list(nvidia["gpus"])},
        "python": dict(python),
        "packages": packages,
        "isaac_sim_version": primary["version"],
        "installation_sha256": canonical_sha256(installation_identity),
        "extension_lock_sha256": canonical_sha256(extension_identity),
        "requirements": requirements,
        "selection_status": "CANDIDATE_BLOCKED" if blockers else "CANDIDATE",
        "blockers": blockers,
        "license_review_status": "NOT_ACCEPTED_BY_AUTOMATION",
        "launch_status": "NOT_RUN",
        "settings_profile_sha256": None,
        "hardware_access": False,
        "physical_authority": False,
        "wire_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
    }
    report["probe_sha256"] = canonical_sha256(report)
    return report


def collect_probe(*, tested_driver: str = DEFAULT_TESTED_DRIVER) -> dict[str, object]:
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    disk = shutil.disk_usage(Path(sys.executable).anchor)
    host = {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "physical_memory_bytes": _physical_memory_bytes(),
        "installation_volume_free_bytes": disk.free,
    }
    python = {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": str(Path(sys.executable).resolve()),
    }
    return build_probe(
        captured_at=captured_at,
        host=host,
        nvidia=_query_nvidia(),
        python=python,
        distributions=_distribution_records(),
        tested_driver=tested_driver,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tested-driver", default=DEFAULT_TESTED_DRIVER)
    args = parser.parse_args(argv)
    report = collect_probe(tested_driver=args.tested_driver)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "probe_sha256": report["probe_sha256"],
        "selection_status": report["selection_status"],
        "blockers": report["blockers"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
