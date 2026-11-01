"""Author the governed geometry and drive prior into a derived SysID USD stage."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
from typing import Any


SCHEMA = "tactevra.isaac_lm0b_sysid_stage_prior.v1"
PROFILE_SCHEMA = "tactevra.isaac_lm0b_geometry_prior_profile.v1"
EXPECTED_DOFS = (
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
    "link5_to_gripper_link",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_profile(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    profile = json.loads(raw)
    if profile.get("schema") != PROFILE_SCHEMA:
        raise ValueError("SysID stage authoring requires the geometry-prior profile")
    if profile.get("simulation_only") is not True or profile.get("physical_authority") is not False:
        raise ValueError("geometry prior crossed its simulation-only authority boundary")
    if profile.get("status") != "PROVISIONAL_SIMULATION_ONLY":
        raise ValueError("geometry prior must remain provisional")
    properties = profile.get("rigid_body_properties")
    if not isinstance(properties, dict) or len(properties) != 7:
        raise ValueError("geometry prior must bind seven rigid bodies")
    dof = profile.get("dof")
    if not isinstance(dof, dict) or any(float(dof.get(name, 0.0)) <= 0.0 for name in ("stiffness", "damping", "maximum_effort")):
        raise ValueError("geometry prior requires positive drive stiffness, damping, and effort")
    return profile, raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-usd", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-usd", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        source = args.input_usd.resolve(strict=True)
        destination = args.output_usd.resolve()
        if source == destination:
            raise ValueError("derived SysID stage must not overwrite its source USD")
        destination.parent.mkdir(parents=True, exist_ok=True)
        profile, profile_raw = load_profile(args.profile.resolve(strict=True))
        source_raw = source.read_bytes()
        shutil.copyfile(source, destination)

        from pxr import Gf, Usd, UsdPhysics

        stage = Usd.Stage.Open(str(destination))
        if stage is None:
            raise RuntimeError("could not open copied SysID stage")
        for prim_path, row in profile["rigid_body_properties"].items():
            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                raise RuntimeError(f"missing rigid body {prim_path}")
            api = UsdPhysics.MassAPI.Apply(prim)
            api.CreateMassAttr().Set(row["mass_kg"])
            api.CreateCenterOfMassAttr().Set(Gf.Vec3f(*row["center_of_mass_m"]))
            api.CreateDiagonalInertiaAttr().Set(Gf.Vec3f(*row["diagonal_inertia_kg_m2"]))
            axes = row["principal_axes_wxyz"]
            api.CreatePrincipalAxesAttr().Set(Gf.Quatf(axes[0], axes[1], axes[2], axes[3]))

        dof = profile["dof"]
        for name in EXPECTED_DOFS:
            prim = stage.GetPrimAtPath(f"/roarm_m3/Physics/{name}")
            if not prim.IsValid() or not prim.IsA(UsdPhysics.RevoluteJoint):
                raise RuntimeError(f"missing governed revolute joint {name}")
            drive = UsdPhysics.DriveAPI.Apply(prim, "angular")
            drive.CreateTypeAttr().Set("force")
            drive.CreateStiffnessAttr().Set(dof["stiffness"])
            drive.CreateDampingAttr().Set(dof["damping"])
            drive.CreateMaxForceAttr().Set(dof["maximum_effort"])
        stage.GetRootLayer().customLayerData = {
            **dict(stage.GetRootLayer().customLayerData),
            "tactevra:sysidProfileSha256": _digest(profile_raw),
            "tactevra:sysidStageClass": "PROVISIONAL_SIMULATION_ONLY",
        }
        stage.GetRootLayer().Save()

        check = Usd.Stage.Open(str(destination))
        if check is None:
            raise RuntimeError("could not reopen derived SysID stage")
        for prim_path, row in profile["rigid_body_properties"].items():
            api = UsdPhysics.MassAPI(check.GetPrimAtPath(prim_path))
            if not math.isclose(float(api.GetMassAttr().Get()), float(row["mass_kg"]), rel_tol=0.0, abs_tol=1e-8):
                raise RuntimeError(f"mass readback mismatch at {prim_path}")
        for name in EXPECTED_DOFS:
            drive = UsdPhysics.DriveAPI.Get(check.GetPrimAtPath(f"/roarm_m3/Physics/{name}"), "angular")
            observed = (
                float(drive.GetStiffnessAttr().Get()),
                float(drive.GetDampingAttr().Get()),
                float(drive.GetMaxForceAttr().Get()),
            )
            expected = (float(dof["stiffness"]), float(dof["damping"]), float(dof["maximum_effort"]))
            if any(not math.isclose(observed[i], expected[i], rel_tol=0.0, abs_tol=1e-8) for i in range(3)):
                raise RuntimeError(f"drive readback mismatch at {name}: {observed}")

        result: dict[str, Any] = {
            "schema": SCHEMA,
            "status": "PASS_PROVISIONAL_SYSID_STAGE_PRIOR",
            "evidence_class": "PROVISIONAL_SIMULATION_ONLY",
            "source_bindings": {
                "source_usd_sha256": _digest(source_raw),
                "profile_file_sha256": _digest(profile_raw),
            },
            "output_usd_sha256": _digest(destination.read_bytes()),
            "rigid_body_property_count": 7,
            "drive_property_count": 6,
            "drive_prior": {
                "stiffness": dof["stiffness"],
                "damping": dof["damping"],
                "maximum_effort": dof["maximum_effort"],
                "type": "force",
            },
            "source_usd_modified": False,
            "hardware_access": False,
            "physical_authority": False,
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "geometry_derived_provisional_mass_properties",
                "provisional_mass_distribution_and_drive_parameters",
                "derived_stage_is_not_a_physical_fit",
                "no_collision_or_contact_geometry",
            ],
        }
        result["receipt_sha256"] = _digest(_canonical(result))
        args.receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.status_output.write_text(
            json.dumps({"status": result["status"], "receipt_sha256": result["receipt_sha256"]}, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return 0
    except BaseException as exc:
        args.status_output.write_text(
            json.dumps({"status": "ERROR", "type": type(exc).__name__, "message": str(exc)}, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
