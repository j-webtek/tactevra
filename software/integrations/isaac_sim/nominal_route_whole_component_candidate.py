"""Reconstruct the pinned whole-component convex-hull surrogate offline.

This creates a review candidate, not a live-runtime certification.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nominal_route_native_component_obb_binding import (
    PROFILE_TO_NATIVE_LINK, _component_coefficients, _joint_chain, _sha, build_definition,
)

REDUCTION_FILE_SHA256 = "d9d49bbb97a207a56db2a15cb55b12dc63f6ce89e35998a139ccd112f2061714"
REDUCTION_RECEIPT_SHA256 = "ef8d011314df145afe5db43310457671082b276023191aea47287b3ef87a7178"


def build_candidate(root: Path) -> dict:
    """Build exactly the retained 14 boxes; no launch or review is granted."""
    integration = root / "software/integrations/isaac_sim"
    urdf = root / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    partition = integration / "evidence/roarm_m3_triangle_partition_link2_20261005.json"
    reduction = integration / "evidence/roarm_m3_link_mesh_reduction_20261004.json"
    binding = integration / "nominal_route_native_component_obb_binding.py"
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    if digest(reduction) != REDUCTION_FILE_SHA256:
        raise ValueError("whole-component reduction file changed")
    candidate = json.loads(reduction.read_bytes())
    unsigned = dict(candidate)
    claimed = unsigned.pop("receipt_sha256", None)
    if claimed != REDUCTION_RECEIPT_SHA256 or claimed != _sha(unsigned):
        raise ValueError("whole-component reduction receipt changed")
    text = urdf.read_text(encoding="utf-8")
    definition = build_definition(
        json.loads(partition.read_bytes()), partition_file_sha256=digest(partition),
        urdf_file_sha256=digest(urdf), binding_source_file_sha256=digest(binding), urdf_text=text,
    )
    chain = _joint_chain(text)
    native_to_profile = {native: profile for profile, native in PROFILE_TO_NATIVE_LINK.items()}
    boxes = []
    keys = set()
    for row in candidate["links"]:
        native = row["link_name"]
        for component in row["components"]:
            primitive = component["candidate_primitive"]
            key = (native, component["component_index"])
            if (native not in native_to_profile or key in keys
                or component["maximum_vertex_overflow_mm"] != 0.0
                or primitive["kind"] != "oriented_box"
                or primitive["rotation_row_major"] != [1, 0, 0, 0, 1, 0, 0, 0, 1]):
                raise ValueError("whole-component geometry changed")
            keys.add(key)
            center, extents = primitive["center_mm"], primitive["half_extents_mm"]
            profile = native_to_profile[native]
            boxes.append({"link_name": profile, "native_link_name": native,
                "primitive_name": f"{profile}:{component['component_index']}",
                "local_center_mm": center, "local_rotation_row_major": primitive["rotation_row_major"],
                "half_extents_mm": extents,
                "path_lipschitz_mm_per_rad": _component_coefficients(native, center, extents, chain)})
    if len(boxes) != 14 or {key[0] for key in keys} != set(native_to_profile):
        raise ValueError("whole-component box inventory changed")
    definition["component_obbs"] = boxes
    definition["offline_whole_component_candidate"] = True
    definition["source_files_sha256"]["whole_component_reduction"] = REDUCTION_FILE_SHA256
    definition["source_files_sha256"]["whole_component_builder"] = digest(Path(__file__))
    definition["containment_contract"]["whole_component_convex_hull_surrogate"] = True
    definition.pop("binding_sha256")
    definition["binding_sha256"] = _sha(definition)
    return definition
