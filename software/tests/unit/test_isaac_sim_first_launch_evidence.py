from __future__ import annotations

import json
from pathlib import Path

from rocell.integrations.isaac_sim import canonical_sha256


WORKSPACE = Path(__file__).resolve().parents[3]
RECEIPT = (
    WORKSPACE
    / "software/integrations/isaac_sim/evidence"
    / "windows_dual_rtx3090_first_launch_20260929.json"
)


def _load() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_first_launch_receipt_is_hash_bound_and_zero_authority() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    assert receipt["evidence_class"] == "COMPATIBILITY_LAUNCH_ONLY"
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_first_launch_receipt_binds_live_toolchain_and_unique_extensions() -> None:
    receipt = _load()
    assert receipt["isaacsim_distribution"] == "6.1.0.0"
    assert receipt["kit_version"] == "6.1.0"
    assert receipt["nvidia"]["driver_version"] == "595.97"
    assert len(receipt["nvidia"]["gpus"]) == 2
    extensions = receipt["enabled_extensions"]
    assert len(extensions) == receipt["enabled_extension_count"] == 303
    identities = [extension["id"] for extension in extensions]
    assert len(set(identities)) == len(identities)
    assert canonical_sha256(extensions) == receipt["extension_lock_sha256"]
    assert canonical_sha256(receipt["launch_profile"]) == receipt["settings_profile_sha256"]


def test_first_launch_scope_excludes_scene_and_physical_claims() -> None:
    receipt = _load()
    assert set(receipt["limitations"]) == {
        "compatibility_startup_only",
        "no_usd_scene_loaded",
        "no_physics_or_render_acceptance",
        "no_physical_qualification",
    }
