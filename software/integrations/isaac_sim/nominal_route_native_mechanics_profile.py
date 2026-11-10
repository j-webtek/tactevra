"""Validate and bind the pinned provisional mechanics profile to native Isaac objects.

This module is import-safe.  Loading and validation perform file reads only;
binding mutates an in-memory USD stage and articulation but never starts Isaac,
steps physics, submits targets, or accesses hardware.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping


PROFILE_SCHEMA = "tactevra.isaac_lm0b_geometry_prior_profile.v1"
PROFILE_SHA256 = "768829bc8c131efe41e8866b6a18900a24b3f77e2ef97b367b55cffbfcf9881a"
EXPECTED_TOTAL_MASS_KG = 1.021
EXPECTED_DOF_COUNT = 6
EXPECTED_BODY_COUNT = 7


class NativeMechanicsProfileError(ValueError):
    """Raised when profile identity, data, or native binding changes."""


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite_vector(value: Any, size: int, label: str) -> list[float]:
    if (
        not isinstance(value, list)
        or len(value) != size
        or not all(isinstance(item, (int, float)) for item in value)
    ):
        raise NativeMechanicsProfileError(f"{label} shape changed")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise NativeMechanicsProfileError(f"{label} must be finite")
    return result


def load_pinned_profile(path: Path) -> dict[str, Any]:
    """Load the exact simulation-only profile and validate its physical values."""
    resolved = path.resolve(strict=True)
    if _file_sha(resolved) != PROFILE_SHA256:
        raise NativeMechanicsProfileError("mechanics profile hash changed")
    profile = json.loads(resolved.read_bytes())
    if not isinstance(profile, dict):
        raise NativeMechanicsProfileError("mechanics profile must contain an object")
    properties = profile.get("rigid_body_properties")
    dof = profile.get("dof")
    if (
        profile.get("schema") != PROFILE_SCHEMA
        or profile.get("status") != "PROVISIONAL_SIMULATION_ONLY"
        or profile.get("simulation_only") is not True
        or profile.get("physical_authority") is not False
        or not isinstance(properties, dict)
        or len(properties) != EXPECTED_BODY_COUNT
        or not isinstance(dof, dict)
        or set(dof)
        != {"damping", "maximum_effort", "maximum_velocity_rad_s", "stiffness"}
    ):
        raise NativeMechanicsProfileError("mechanics profile boundary changed")
    masses = []
    expected_row = {
        "mass_kg",
        "center_of_mass_m",
        "diagonal_inertia_kg_m2",
        "principal_axes_wxyz",
    }
    for prim_path, row in properties.items():
        if not isinstance(prim_path, str) or not isinstance(row, dict) or set(row) != expected_row:
            raise NativeMechanicsProfileError("rigid-body property shape changed")
        mass = row["mass_kg"]
        if not isinstance(mass, (int, float)) or not math.isfinite(mass) or mass <= 0:
            raise NativeMechanicsProfileError(f"{prim_path} mass is invalid")
        center = _finite_vector(row["center_of_mass_m"], 3, f"{prim_path} center")
        inertia = _finite_vector(
            row["diagonal_inertia_kg_m2"], 3, f"{prim_path} inertia"
        )
        axes = _finite_vector(row["principal_axes_wxyz"], 4, f"{prim_path} axes")
        if not all(item > 0 for item in inertia):
            raise NativeMechanicsProfileError(f"{prim_path} inertia is nonpositive")
        if not math.isclose(sum(item * item for item in axes), 1.0, abs_tol=1e-9):
            raise NativeMechanicsProfileError(f"{prim_path} axes are not unit length")
        if not all(math.isfinite(item) for item in center):  # defensive clarity
            raise NativeMechanicsProfileError(f"{prim_path} center is invalid")
        masses.append(float(mass))
    if not math.isclose(sum(masses), EXPECTED_TOTAL_MASS_KG, abs_tol=1e-12):
        raise NativeMechanicsProfileError("mechanics profile total mass changed")
    for name, value in dof.items():
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise NativeMechanicsProfileError(f"DOF {name} is invalid")
    for name in ("gravity_m_s2", "physics_dt_s"):
        value = profile.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise NativeMechanicsProfileError(f"{name} is invalid")
    return profile


def bind_mass_properties(
    stage: Any,
    profile: Mapping[str, Any],
    *,
    mass_api_factory: Callable[[Any], Any] | None = None,
    vec3_factory: Callable[..., Any] | None = None,
    quaternion_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Apply and read back all pinned rigid-body mass properties."""
    if mass_api_factory is None or vec3_factory is None or quaternion_factory is None:
        from pxr import Gf, UsdPhysics

        mass_api_factory = mass_api_factory or UsdPhysics.MassAPI.Apply
        vec3_factory = vec3_factory or Gf.Vec3f
        quaternion_factory = quaternion_factory or Gf.Quatf
    properties = profile["rigid_body_properties"]
    bound_paths = []

    def vector_values(value: Any) -> list[float]:
        return [float(item) for item in value]

    def quaternion_values(value: Any) -> list[float]:
        if hasattr(value, "GetReal") and hasattr(value, "GetImaginary"):
            imaginary = value.GetImaginary()
            return [float(value.GetReal()), *vector_values(imaginary)]
        return vector_values(value)

    def close(actual: list[float], expected: list[float], tolerance: float) -> bool:
        return len(actual) == len(expected) and max(
            abs(left - right) for left, right in zip(actual, expected, strict=True)
        ) <= tolerance

    for prim_path, row in properties.items():
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise NativeMechanicsProfileError(f"missing rigid body {prim_path}")
        api = mass_api_factory(prim)
        api.CreateMassAttr().Set(float(row["mass_kg"]))
        api.CreateCenterOfMassAttr().Set(vec3_factory(*row["center_of_mass_m"]))
        api.CreateDiagonalInertiaAttr().Set(
            vec3_factory(*row["diagonal_inertia_kg_m2"])
        )
        axes = row["principal_axes_wxyz"]
        api.CreatePrincipalAxesAttr().Set(quaternion_factory(*axes))
        if not math.isclose(
            float(api.GetMassAttr().Get()), row["mass_kg"], abs_tol=1e-6
        ):
            raise NativeMechanicsProfileError(f"{prim_path} mass readback changed")
        if not close(
            vector_values(api.GetCenterOfMassAttr().Get()),
            row["center_of_mass_m"],
            1e-7,
        ):
            raise NativeMechanicsProfileError(f"{prim_path} center readback changed")
        if not close(
            vector_values(api.GetDiagonalInertiaAttr().Get()),
            row["diagonal_inertia_kg_m2"],
            1e-9,
        ):
            raise NativeMechanicsProfileError(f"{prim_path} inertia readback changed")
        if not close(
            quaternion_values(api.GetPrincipalAxesAttr().Get()),
            row["principal_axes_wxyz"],
            1e-6,
        ):
            raise NativeMechanicsProfileError(f"{prim_path} axes readback changed")
        bound_paths.append(prim_path)
    return {
        "profile_sha256": PROFILE_SHA256,
        "rigid_body_count": len(bound_paths),
        "rigid_body_paths": bound_paths,
        "total_mass_kg": sum(
            float(row["mass_kg"]) for row in properties.values()
        ),
    }


def bind_drive_properties(articulation: Any, profile: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the pinned provisional gains without setting positions or targets."""
    required = {
        "set_dof_gains",
        "set_dof_max_efforts",
        "set_dof_max_velocities",
    }
    if any(not callable(getattr(articulation, name, None)) for name in required):
        raise NativeMechanicsProfileError("native articulation drive API changed")
    dof_names = list(articulation.dof_names)
    if len(dof_names) != EXPECTED_DOF_COUNT:
        raise NativeMechanicsProfileError("native articulation DOF count changed")
    dof = profile["dof"]
    articulation.set_dof_gains(
        [[float(dof["stiffness"])] * EXPECTED_DOF_COUNT],
        [[float(dof["damping"])] * EXPECTED_DOF_COUNT],
    )
    articulation.set_dof_max_efforts(
        [[float(dof["maximum_effort"])] * EXPECTED_DOF_COUNT]
    )
    articulation.set_dof_max_velocities(
        [[float(dof["maximum_velocity_rad_s"])] * EXPECTED_DOF_COUNT]
    )
    return {
        "dof_count": EXPECTED_DOF_COUNT,
        "dof_names": dof_names,
        "dof_parameters": {name: float(value) for name, value in dof.items()},
    }
