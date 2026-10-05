"""Launch the selected Isaac environment headlessly and retain a compact receipt.

This NVIDIA-dependent probe is intentionally outside the ``rocell`` package and
ordinary CI.  It creates no scene, controller command, or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
from typing import Any

def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def driver_inventory() -> dict[str, Any]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,driver_version,compute_cap",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    gpus = []
    drivers = set()
    for line in completed.stdout.splitlines():
        index, name, memory_mb, driver, capability = (
            part.strip() for part in line.split(",")
        )
        drivers.add(driver)
        gpus.append({
            "index": int(index),
            "name": name,
            "memory_total_mb": int(memory_mb),
            "compute_capability": capability,
        })
    if not gpus or len(drivers) != 1:
        raise RuntimeError("nvidia-smi returned an inconsistent GPU inventory")
    return {"driver_version": drivers.pop(), "gpus": gpus}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    parser.add_argument("--installation-sha256", required=True)
    parser.add_argument("--installer-sha256", required=True)
    args = parser.parse_args()
    for name in ("installation_sha256", "installer_sha256"):
        value = getattr(args, name)
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError(f"{name} must be a lowercase SHA-256 digest")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    from isaacsim import SimulationApp

    app = None
    try:
        launch_profile = {
            "headless": True,
            "multi_gpu": False,
            "physics_cuda_device": 0,
            "portable": True,
            "no_window": True,
        }
        app = SimulationApp({"headless": True, "multi_gpu": False})
        import omni.kit.app

        kit = omni.kit.app.get_app()
        manager = kit.get_extension_manager()
        raw = manager.get_extensions()
        items = list(raw.values()) if isinstance(raw, dict) else list(raw)
        extensions = []
        for item in items:
            if not isinstance(item, dict):
                continue
            extension_id = item.get("id") or item.get("name")
            if extension_id and manager.is_extension_enabled(extension_id):
                extensions.append({
                    "id": extension_id,
                    "name": item.get("name"),
                    "version": item.get("version"),
                })
        extensions.sort(key=lambda value: str(value.get("id")))
        nvidia = driver_inventory()
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_first_launch.v1",
            "evidence_class": "COMPATIBILITY_LAUNCH_ONLY",
            "isaacsim_distribution": importlib.metadata.version("isaacsim"),
            "kit_version": kit.get_app_version(),
            "installation_sha256": args.installation_sha256,
            "installer_sha256": args.installer_sha256,
            "enabled_extension_count": len(extensions),
            "enabled_extensions": extensions,
            "extension_lock_sha256": canonical_sha256(extensions),
            "launch_profile": launch_profile,
            "settings_profile_sha256": canonical_sha256(launch_profile),
            "nvidia": nvidia,
            "license_acceptance_status": "OWNER_AUTHORIZED_INTERNAL_USE",
            "hardware_access": False,
            "physical_authority": False,
            "wire_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "compatibility_startup_only",
                "no_usd_scene_loaded",
                "no_physics_or_render_acceptance",
                "no_physical_qualification",
            ],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        args.output.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        args.status_output.write_text(
            json.dumps({"status": "PASS", "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except BaseException as exc:
        args.status_output.write_text(
            json.dumps({"status": "ERROR", "type": type(exc).__name__, "message": str(exc)}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise
    finally:
        if app is not None:
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
