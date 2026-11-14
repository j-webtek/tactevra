"""Independently check connected vendor mesh vertices against candidate boxes."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--mesh-dir", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo / "software/integrations/isaac_sim"))
from nominal_route_whole_component_candidate import build_candidate

meshdir = args.mesh_dir
reduction = json.loads((repo / "software/integrations/isaac_sim/evidence/roarm_m3_link_mesh_reduction_20261004.json").read_bytes())
definition = build_candidate(repo)
results = []
for link in reduction["links"]:
    name = link["link_name"]
    path = meshdir / f"{name}.stl"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != link["mesh_sha256"]:
        raise ValueError(f"mesh digest mismatch: {name}")
    mesh = trimesh.load_mesh(path, process=True)
    parts = list(mesh.split(only_watertight=False))
    if not parts or sum(len(part.faces) for part in parts) != len(mesh.faces):
        raise ValueError(f"connected-component face coverage mismatch: {name}")
    boxes = [p for p in definition["component_obbs"] if p["native_link_name"] == name]
    worst = -float("inf")
    for part in parts:
        vertices = np.asarray(part.vertices)
        overflows = []
        for box in boxes:
            center = np.asarray(box["local_center_mm"])
            extent = np.asarray(box["half_extents_mm"])
            overflows.append(float(np.max(np.abs(vertices - center) - extent)))
        best = min(overflows)
        if best > 1e-9:
            raise ValueError(f"component not contained: {name}: {best}")
        worst = max(worst, best)
    results.append({"link": name, "mesh_sha256": digest, "vertices": len(mesh.vertices),
                    "triangles": len(mesh.faces), "connected_components": len(parts),
                    "boxes": len(boxes), "worst_component_overflow_mm": worst})
out = {"scope": "vendor_mesh_connected_components_contained_by_candidate_boxes",
       "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
       "definition_sha256": definition["binding_sha256"], "trimesh_version": trimesh.__version__,
       "links": results, "isaac_started": False, "hardware_access": False,
       "limitations": ["mesh components only", "no omitted physical geometry or attachments",
                       "no imported Isaac transform validation", "no independent human review"]}
raw = json.dumps(out, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
out["receipt_sha256"] = hashlib.sha256(raw).hexdigest()
target = args.output
with target.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(out, stream, indent=2, sort_keys=True, allow_nan=False)
    stream.write("\n")
print(json.dumps(out))
