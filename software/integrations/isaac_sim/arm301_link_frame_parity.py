"""Compare a captured native link snapshot with governed URDF FK offline.

No Isaac session, articulation mutation, or hardware access is performed here.
The comparison factors out the observed base pose and therefore does not
qualify base-to-workcell placement.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import numpy as np
from scipy.spatial.transform import Rotation

from nominal_route_native_component_obb_binding import EXPECTED_DOF_NAMES, NATIVE_LINKS, _file_sha, EXPECTED_URDF_SHA256
from rocell.geometry.urdf import JointPosition, UrdfModel


def compare_link_frames(urdf: Path, *, link_names: Sequence[str],
                        joint_names: Sequence[str], joint_positions_rad: Sequence[float],
                        native_transforms: Sequence[Sequence[float]],
                        translation_tolerance_mm: float = 0.1,
                        rotation_tolerance_deg: float = 0.05) -> dict:
    """Compare seven native [metres, xyzw] rows at one observed joint state."""
    if _file_sha(urdf) != EXPECTED_URDF_SHA256:
        raise ValueError("governed URDF digest changed")
    if tuple(link_names) != NATIVE_LINKS or tuple(joint_names) != EXPECTED_DOF_NAMES:
        raise ValueError("link or joint order changed")
    joints = np.asarray(joint_positions_rad, dtype=float)
    rows = np.asarray(native_transforms, dtype=float)
    if (joints.shape != (6,) or rows.shape != (7, 7)
        or not np.isfinite(joints).all() or not np.isfinite(rows).all()
        or not math.isfinite(translation_tolerance_mm) or translation_tolerance_mm <= 0
        or not math.isfinite(rotation_tolerance_deg) or rotation_tolerance_deg <= 0):
        raise ValueError("snapshot or tolerances invalid")
    norms = np.linalg.norm(rows[:, 3:], axis=1)
    if np.any(np.abs(norms - 1.0) > 1e-4):
        raise ValueError("native quaternion is not normalized")
    fk = UrdfModel.from_file(urdf).forward_kinematics({
        name: JointPosition.radians(float(value)) for name, value in zip(joint_names, joints)
    })
    base = fk["base_link"].inverse()
    observed_rotations = Rotation.from_quat(rows[:, 3:])
    observed_base_inverse = observed_rotations[0].inv()
    results = []
    for index, name in enumerate(link_names):
        expected = base.compose(fk[name])
        expected_position = np.array([expected.translation_mm.x, expected.translation_mm.y,
                                      expected.translation_mm.z])
        matrix = expected.rotation.matrix
        expected_rotation = Rotation.from_matrix([matrix[i:i+3] for i in (0, 3, 6)])
        observed_position = observed_base_inverse.apply((rows[index, :3] - rows[0, :3]) * 1000)
        observed_rotation = observed_base_inverse * observed_rotations[index]
        position_error = float(np.linalg.norm(observed_position - expected_position))
        angle_error = float((expected_rotation.inv() * observed_rotation).magnitude() * 180 / math.pi)
        results.append({"link": name, "translation_error_mm": position_error,
                        "rotation_error_deg": angle_error,
                        "pass": position_error <= translation_tolerance_mm and angle_error <= rotation_tolerance_deg})
    return {"link_results": results, "parity_pass": all(row["pass"] for row in results),
            "translation_tolerance_mm": translation_tolerance_mm,
            "rotation_tolerance_deg": rotation_tolerance_deg,
            "scope": "single snapshot relative to observed base; not workcell placement or dynamics"}
