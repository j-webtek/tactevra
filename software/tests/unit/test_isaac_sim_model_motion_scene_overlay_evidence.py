from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = (
    ROOT
    / "software/integrations/isaac_sim/evidence/model_motion_scene_overlay_20260929.json"
)
STATUS = EVIDENCE.with_name("model_motion_scene_overlay_20260929.status.json")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def test_retained_overlay_is_hash_bound_and_zero_authority():
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    unsigned = dict(document)
    claimed = unsigned.pop("receipt_sha256")

    assert _digest(_canonical(unsigned)) == claimed
    assert status["receipt_sha256"] == claimed
    assert document["status"] == status["status"] == (
        "BLOCKED_UNCERTAINTY_CROSSES_INFERRED_SAFE_REGIONS"
    )
    assert document["assessment"]["ordered_target_ids"] == [
        "H", "H", "1", "PERIOD"
    ]
    assert document["assessment"]["adjacent_repeat_action_indexes"] == [1]
    assert document["assessment"][
        "all_proposal_centers_inside_inferred_placed_safe_regions"
    ] is True
    assert document["assessment"][
        "all_uncertainty_disks_fit_inferred_placed_safe_regions"
    ] is False
    assert document["articulation_positions_changed"] == 0
    assert document["physics_steps"] == 0
    assert document["controller_commands"] == document["wire_commands"] == []
    assert document["hardware_writes"] == document["physical_movements"] == 0
    assert document["hardware_access"] is document["physical_authority"] is False


def test_retained_overlay_binds_current_source_bytes():
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    bindings = document["source_bindings"]
    paths = {
        "batch_file_sha256": (
            ROOT / "software/ai/eval/precision_adapter_batch_v2_contract_fixture.json"
        ),
        "batch_metadata_sha256": (
            ROOT
            / "software/ai/eval/precision_adapter_batch_v2_contract_fixture_metadata.json"
        ),
        "scene_receipt_file_sha256": (
            ROOT
            / "software/integrations/isaac_sim/evidence/rc03_nominal_rigid_scene_20260929.json"
        ),
        "nominal_target_geometry_source_sha256": (
            ROOT / "software/config/nominal_target_profiles.json"
        ),
    }
    for key, path in paths.items():
        assert bindings[key] == _digest(path.read_bytes())
