from __future__ import annotations

from copy import deepcopy

from rocell.integrations.isaac_sim.host_probe import (
    DistributionRecord,
    build_probe,
)


def _record(name: str, version: str, marker: str) -> DistributionRecord:
    return DistributionRecord(name, version, marker * 64, marker * 64)


def _inputs() -> dict:
    return {
        "captured_at": "2026-09-29T12:00:00Z",
        "host": {
            "os": "Windows",
            "os_release": "11",
            "os_version": "test",
            "architecture": "AMD64",
            "processor": "test-cpu",
            "physical_memory_bytes": 128 * 1024**3,
            "installation_volume_free_bytes": 120 * 1024**3,
        },
        "nvidia": {
            "driver_version": "591.86",
            "gpus": [
                {
                    "index": 0,
                    "name": "NVIDIA GeForce RTX 3090",
                    "memory_total_mb": 24576,
                    "compute_capability": "8.6",
                },
                {
                    "index": 1,
                    "name": "NVIDIA GeForce RTX 3090",
                    "memory_total_mb": 24576,
                    "compute_capability": "8.6",
                },
            ],
        },
        "python": {
            "version": "3.12.0",
            "implementation": "CPython",
            "executable": "C:\\IsaacSim\\env_6_1_0\\Scripts\\python.exe",
        },
        "distributions": [
            _record("torch", "2.11.0+cu130", "1"),
            _record("isaacsim-extscache-kit-sdk", "6.1.0.0", "4"),
            _record("isaacsim", "6.1.0.0", "2"),
            _record("isaacsim-extscache-kit", "6.1.0.0", "3"),
            _record("isaacsim-extscache-physics", "6.1.0.0", "5"),
        ],
    }


def test_probe_is_deterministic_and_package_order_independent() -> None:
    inputs = _inputs()
    first = build_probe(**inputs)
    inputs["distributions"] = list(reversed(inputs["distributions"]))
    second = build_probe(**inputs)
    assert first == second
    assert first["isaac_sim_version"] == "6.1.0.0"
    assert len(first["installation_sha256"]) == 64
    assert len(first["extension_lock_sha256"]) == 64


def test_candidate_fails_closed_before_license_launch_and_driver_update() -> None:
    report = build_probe(**_inputs())
    assert report["selection_status"] == "CANDIDATE_BLOCKED"
    assert report["license_review_status"] == "NOT_ACCEPTED_BY_AUTOMATION"
    assert report["launch_status"] == "NOT_RUN"
    assert report["settings_profile_sha256"] is None
    assert "DRIVER_BELOW_TESTED_MINIMUM" in report["blockers"]
    assert "GPU_MODEL_NOT_IN_DOCUMENTED_MINIMUM_SET" in report["blockers"]
    assert report["hardware_access"] is report["physical_authority"] is False
    assert report["wire_commands"] == []
    assert report["hardware_writes"] == report["physical_movements"] == 0


def test_installation_and_extension_hashes_bind_different_inputs() -> None:
    inputs = _inputs()
    original = build_probe(**inputs)
    changed = deepcopy(inputs)
    changed["distributions"] = list(changed["distributions"])
    changed["distributions"][0] = _record("torch", "2.11.1+cu130", "1")
    torch_changed = build_probe(**changed)
    assert torch_changed["installation_sha256"] != original["installation_sha256"]
    assert torch_changed["extension_lock_sha256"] == original["extension_lock_sha256"]

    changed = deepcopy(inputs)
    changed["distributions"] = list(changed["distributions"])
    changed["distributions"][1] = _record("isaacsim-extscache-kit-sdk", "6.1.0.1", "4")
    extension_changed = build_probe(**changed)
    assert extension_changed["installation_sha256"] != original["installation_sha256"]
    assert extension_changed["extension_lock_sha256"] != original["extension_lock_sha256"]


def test_report_hash_binds_requirements_and_host_evidence() -> None:
    original = build_probe(**_inputs())
    inputs = _inputs()
    inputs["nvidia"] = dict(inputs["nvidia"])
    inputs["nvidia"]["driver_version"] = "595.97"
    updated = build_probe(**inputs)
    assert updated["probe_sha256"] != original["probe_sha256"]
    assert updated["requirements"]["driver_meets_tested_minimum"] is True
    assert "DRIVER_BELOW_TESTED_MINIMUM" not in updated["blockers"]
