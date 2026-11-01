"""Derive provisional link mass properties from pinned official meshes."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
from typing import Any


MESH_RECEIPT_SCHEMA = "tactevra.isaac_sim_upstream_link_mesh_binding.v1"
MESH_RECEIPT_SHA256 = "dbb8b56a602ac4c2b69073af23d61700aee12c0153080bdf58b7f5990b92646e"
BASE_PROFILE_SCHEMA = "tactevra.isaac_lm0b_gravity_characterization_profile.v1"
PROFILE_SCHEMA = "tactevra.isaac_lm0b_geometry_prior_profile.v1"
RECEIPT_SCHEMA = "tactevra.isaac_lm0b_geometry_mass_prior.v1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git_blob(repo: Path, commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{path}"],
        check=True,
        capture_output=True,
    ).stdout


def _matrix_to_wxyz(matrix: Any) -> list[float]:
    """Convert a proper 3x3 rotation matrix to a normalized wxyz quaternion."""
    import numpy as np

    m = np.asarray(matrix, dtype=float)
    if m.shape != (3, 3) or not np.all(np.isfinite(m)):
        raise ValueError("principal-axis rotation must be a finite 3x3 matrix")
    trace = float(np.trace(m))
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    else:
        index = int(np.argmax(np.diag(m)))
        if index == 0:
            s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
            q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
        elif index == 1:
            s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
            q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
        else:
            s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
            q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    q = np.asarray(q, dtype=float)
    q /= np.linalg.norm(q)
    if q[0] < 0.0:
        q *= -1.0
    return [round(float(value), 12) for value in q]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--mesh-receipt", type=Path, required=True)
    parser.add_argument("--base-profile", type=Path, required=True)
    parser.add_argument("--profile-output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.profile_output, args.receipt_output, args.status_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import numpy as np
        import trimesh

        upstream = args.upstream_repo.resolve(strict=True)
        mesh_raw = args.mesh_receipt.resolve(strict=True).read_bytes()
        mesh_receipt = json.loads(mesh_raw)
        if mesh_receipt.get("schema") != MESH_RECEIPT_SCHEMA or mesh_receipt.get("receipt_sha256") != MESH_RECEIPT_SHA256:
            raise ValueError("unexpected upstream mesh-binding receipt")
        base_raw = args.base_profile.resolve(strict=True).read_bytes()
        base = json.loads(base_raw)
        if base.get("schema") != BASE_PROFILE_SCHEMA or base.get("physical_authority") is not False:
            raise ValueError("unexpected LM0B base profile")
        commit = mesh_receipt["source_bindings"]["upstream_commit"]
        mass_paths = {path.rsplit("/", 1)[-1]: (path, mass) for path, mass in base["rigid_body_mass_kg"].items()}
        properties: dict[str, Any] = {}
        rows = []
        for item in mesh_receipt["mesh_inventory"]:
            name = item["link_name"]
            if name not in mass_paths:
                raise ValueError(f"no provisional mass for {name}")
            prim_path, mass = mass_paths[name]
            raw = _git_blob(upstream, commit, item["git_path"])
            if _digest(raw) != item["sha256"]:
                raise ValueError(f"{name} source mesh hash mismatch")
            source = trimesh.load_mesh(io.BytesIO(raw), file_type="stl", process=True)
            method = "SOURCE_WATERTIGHT_VOLUME" if item["watertight"] else "CONVEX_HULL_CLOSURE"
            shape = source if item["watertight"] else source.convex_hull
            shape.apply_scale(0.001)
            mass_properties = shape.mass_properties
            if mass_properties["mass"] <= 0.0:
                raise ValueError(f"{name} has nonpositive geometric volume")
            inertia = np.asarray(mass_properties["inertia"], dtype=float) * (mass / mass_properties["mass"])
            eigenvalues, eigenvectors = np.linalg.eigh(inertia)
            if np.linalg.det(eigenvectors) < 0.0:
                eigenvectors[:, 0] *= -1.0
            if np.any(eigenvalues <= 0.0) or not np.all(np.isfinite(eigenvalues)):
                raise ValueError(f"{name} has invalid principal inertia")
            row = {
                "link_name": name,
                "prim_path": prim_path,
                "source_mesh_sha256": item["sha256"],
                "closure_method": method,
                "mass_kg": mass,
                "center_of_mass_m": [round(float(value), 12) for value in mass_properties["center_mass"]],
                "diagonal_inertia_kg_m2": [round(float(value), 12) for value in eigenvalues],
                "principal_axes_wxyz": _matrix_to_wxyz(eigenvectors),
            }
            properties[prim_path] = {key: value for key, value in row.items() if key not in {"link_name", "prim_path", "source_mesh_sha256", "closure_method"}}
            rows.append(row)
        if len(properties) != len(mass_paths):
            raise ValueError("mesh and provisional-mass link sets differ")

        profile = {
            "schema": PROFILE_SCHEMA,
            "status": "PROVISIONAL_SIMULATION_ONLY",
            "simulation_only": True,
            "physical_authority": False,
            "gravity_m_s2": base["gravity_m_s2"],
            "physics_dt_s": base["physics_dt_s"],
            "initial_settle_steps": base["initial_settle_steps"],
            "target_steps": base["target_steps"],
            "maximum_final_joint_error_rad": base["maximum_final_joint_error_rad"],
            "dof": base["dof"],
            "rigid_body_properties": properties,
            "source_bindings": {
                "mesh_receipt_sha256": MESH_RECEIPT_SHA256,
                "base_profile_file_sha256": _digest(base_raw),
                "upstream_commit": commit,
            },
            "provenance": {
                "mass_total_kg": base["provenance"]["mass_total_kg"],
                "mass_distribution": base["provenance"]["mass_distribution"],
                "center_of_mass_and_inertia": {
                    "class": "GEOMETRY_DERIVED_PROVISIONAL",
                    "watertight_mesh_count": sum(row["closure_method"] == "SOURCE_WATERTIGHT_VOLUME" for row in rows),
                    "convex_hull_closure_count": sum(row["closure_method"] == "CONVEX_HULL_CLOSURE" for row in rows),
                },
                "drive_gains": base["provenance"]["drive_gains"],
                "gravity": base["provenance"]["gravity"],
            },
        }
        profile_bytes = json.dumps(profile, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        args.profile_output.write_bytes(profile_bytes)
        receipt: dict[str, Any] = {
            "schema": RECEIPT_SCHEMA,
            "status": "PASS_PROVISIONAL_GEOMETRY_PRIOR",
            "evidence_class": "GEOMETRY_DERIVED_SIMULATION_PRIOR_ONLY",
            "source_bindings": {
                "mesh_receipt_file_sha256": _digest(mesh_raw),
                "mesh_receipt_sha256": MESH_RECEIPT_SHA256,
                "base_profile_file_sha256": _digest(base_raw),
                "upstream_commit": commit,
            },
            "profile_file_sha256": _digest(profile_bytes),
            "link_properties": rows,
            "total_mass_kg": sum(row["mass_kg"] for row in rows),
            "hardware_access": False,
            "physical_authority": False,
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "mesh_geometry_omits_internal_servo_electronics_and_fastener_mass_distribution",
                "link1_and_link5_use_convex_hull_closure",
                "link_masses_remain_provisional_allocations_of_published_total_mass",
                "not_physical_system_identification_torque_timing_contact_or_safety_evidence",
            ],
        }
        receipt["receipt_sha256"] = _digest(_canonical(receipt))
        args.receipt_output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.status_output.write_text(json.dumps({"status": receipt["status"], "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    except BaseException as exc:
        args.status_output.write_text(json.dumps({"status": "ERROR", "type": type(exc).__name__, "message": str(exc)}, sort_keys=True) + "\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
