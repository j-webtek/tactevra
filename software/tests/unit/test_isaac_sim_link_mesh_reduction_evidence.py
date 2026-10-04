from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.geometry import Rotation3, Vec3
from rocell.integrations.isaac_sim import canonical_sha256
from rocell.simulation.collision import OrientedBoxMm


WORKSPACE = Path(__file__).resolve().parents[3]
RECEIPT = (
    WORKSPACE / "software/integrations/isaac_sim/evidence"
    / "roarm_m3_link_mesh_reduction_20261004.json"
)


def _load() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_reduction_receipt_is_canonical_and_zero_authority() -> None:
    receipt = _load()
    claimed = receipt.pop("receipt_sha256")
    assert canonical_sha256(receipt) == claimed
    assert receipt["evidence_class"] == "CONSERVATIVE_BOX_CANDIDATES_ONLY"
    assert receipt["hardware_access"] is receipt["physical_authority"] is False
    assert receipt["wire_commands"] == []
    assert receipt["hardware_writes"] == receipt["physical_movements"] == 0


def test_reduction_binds_the_retained_mesh_receipt() -> None:
    receipt = _load()
    source = (
        WORKSPACE / "software/integrations/isaac_sim/evidence"
        / "roarm_m3_upstream_link_mesh_binding_20261004.json"
    )
    assert receipt["source_bindings"]["mesh_receipt_file_sha256"] == _digest(source)
    assert receipt["source_bindings"]["mesh_receipt_sha256"] == (
        "dbb8b56a602ac4c2b69073af23d61700aee12c0153080bdf58b7f5990b92646e"
    )


def test_candidate_boxes_are_runtime_primitive_compatible_and_containing() -> None:
    receipt = _load()
    primitives = []
    for link in receipt["links"]:
        assert link["component_count"] <= 64
        for component in link["components"]:
            item = component["candidate_primitive"]
            primitive = OrientedBoxMm(
                Vec3(*item["center_mm"]),
                Vec3(*item["half_extents_mm"]),
                Rotation3(tuple(item["rotation_row_major"])),
            )
            primitives.append(primitive)
            assert component["maximum_vertex_overflow_mm"] == 0.0
    assert len(primitives) == receipt["summary"]["candidate_primitive_count"] == 14
    assert receipt["summary"]["maximum_vertex_overflow_mm"] == 0.0


def test_fragmented_link_uses_declared_contract_limit_fallback() -> None:
    links = {item["link_name"]: item for item in _load()["links"]}
    assert links["link5"]["processed_connected_component_count"] == 114
    assert links["link5"]["partition_mode"] == (
        "WHOLE_LINK_ENVELOPE_COMPONENT_LIMIT_FALLBACK"
    )
    assert links["link5"]["component_count"] == 1
    assert all(
        item["partition_mode"] == "ONE_BOX_PER_PROCESSED_CONNECTED_COMPONENT"
        for name, item in links.items()
        if name != "link5"
    )


def test_candidates_remain_uninstalled_and_unqualified() -> None:
    receipt = _load()
    assert receipt["candidate_profile_installable"] is False
    assert receipt["raw_mesh_collision_admissible"] is False
    assert receipt["reduced_collision_geometry_admissible"] is False
    assert receipt["clearance_replay_admissible"] is False
    assert receipt["summary"]["maximum_watertight_volume_ratio"] == 21.140797
    assert receipt["summary"]["non_watertight_component_count"] == 2
    assert {
        "SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED",
        "BOX_INFLATION_FALSE_POSITIVE_RATE_NOT_QUALIFIED",
        "LINK5_FRAGMENTATION_REQUIRES_WHOLE_LINK_ENVELOPE",
    } <= set(receipt["blockers"])
