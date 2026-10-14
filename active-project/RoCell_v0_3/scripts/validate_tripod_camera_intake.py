#!/usr/bin/env python3
"""Validate the hash-bound, zero-authority tripod installation intake."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
DEFAULT_INTAKE = PROJECT_ROOT / "config" / "tripod_camera_installation_intake_v1.json"


class TripodIntakeError(ValueError):
    """Raised when the controlled tripod intake is malformed or stale."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_tripod_camera_intake(path: Path = DEFAULT_INTAKE) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "rocell.rc03.tripod_camera_installation_intake.v1":
        raise TripodIntakeError("unsupported tripod installation intake schema")

    bindings = document.get("source_bindings")
    if not isinstance(bindings, dict) or set(bindings) != {
        "commercial_tripod_candidate",
        "b0477_camera_profile",
        "workcell_layout",
    }:
        raise TripodIntakeError("tripod intake source bindings are incomplete")
    for name, binding in bindings.items():
        source = REPOSITORY_ROOT / str(binding.get("path", ""))
        if not source.is_file():
            raise TripodIntakeError(f"tripod intake source is missing: {name}")
        if binding.get("sha256") != _sha256(source):
            raise TripodIntakeError(f"tripod intake source hash changed: {name}")

    authority = document.get("authority")
    expected_authority = {
        "fabrication": False,
        "physical_installation": False,
        "robot_power": False,
        "motion": False,
        "contact": False,
        "physical_release_effect": "NONE",
    }
    if authority != expected_authority:
        raise TripodIntakeError("tripod intake must remain zero authority")

    required_sections = (
        "received_hardware",
        "measured_mount_interface",
        "measured_support_geometry",
        "installed_pose",
        "stability_results",
        "qualification_results",
    )
    if any(not isinstance(document.get(section), dict) for section in required_sections):
        raise TripodIntakeError("tripod intake measurement sections are incomplete")

    return document


def main() -> int:
    document = validate_tripod_camera_intake()
    print(
        json.dumps(
            {
                "status": "PASS",
                "record_id": document["record_id"],
                "intake_status": document["status"],
                "physical_release_effect": "NONE",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
