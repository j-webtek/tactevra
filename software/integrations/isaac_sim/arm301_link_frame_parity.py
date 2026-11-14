"""Compare a captured native link snapshot with governed URDF FK offline.

No Isaac session, articulation mutation, or hardware access is performed here.
The comparison factors out the observed base pose and therefore does not
qualify base-to-workcell placement.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Sequence

import numpy as np
from scipy.spatial.transform import Rotation

from nominal_route_native_component_obb_binding import EXPECTED_DOF_NAMES, NATIVE_LINKS, _file_sha, EXPECTED_URDF_SHA256
from rocell.geometry.urdf import JointPosition, UrdfModel


def _array(value: object) -> np.ndarray:
    if hasattr(value, "numpy"):
        value = value.numpy()
    # Native tensor views may reuse their backing buffer on the next read.
    # Preserve each observation before issuing another native call.
    return np.array(value, dtype=float, copy=True)


def capture_link_snapshot(articulation: object, *, maximum_joint_change_rad: float = 1e-7) -> dict:
    """Read one stable simulated state; never set positions or step physics.

    The caller must establish the session and ensure it remains stationary;
    bracketing joint reads detect state changes but do not make reads atomic.
    """
    if not math.isfinite(maximum_joint_change_rad) or maximum_joint_change_rad < 0:
        raise ValueError("joint change tolerance invalid")
    names = tuple(getattr(articulation, "link_names", ()))
    dofs = tuple(getattr(articulation, "dof_names", ()))
    if names != NATIVE_LINKS or dofs != EXPECTED_DOF_NAMES:
        raise ValueError("link or joint order changed")
    before = _array(articulation.get_dof_positions())
    transforms = _array(articulation.get_link_transforms())
    after = _array(articulation.get_dof_positions())
    if (before.shape != (1, 6) or after.shape != (1, 6) or transforms.shape != (1, 7, 7)
        or not np.isfinite(before).all() or not np.isfinite(after).all()
        or not np.isfinite(transforms).all()):
        raise ValueError("native snapshot shape or values invalid")
    if np.max(np.abs(before - after)) > maximum_joint_change_rad:
        raise ValueError("joint state changed during snapshot")
    return {"link_names": list(names), "joint_names": list(dofs),
            "joint_positions_rad": before[0].tolist(),
            "joint_positions_after_rad": after[0].tolist(),
            "native_transforms": transforms[0].tolist(),
            "maximum_joint_change_rad": maximum_joint_change_rad,
            "scope": "read-only non-atomic simulation snapshot"}


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


def capture_and_compare(articulation: object, urdf: Path) -> dict:
    """Capture and compare one state in an already-established stationary session.

    This helper never starts a session and does not itself authorize a capture.
    A caller must retain and review the result and establish its own provenance.
    """
    snapshot = capture_link_snapshot(articulation)
    comparison = compare_link_frames(urdf, **{key: snapshot[key] for key in
        ("link_names", "joint_names", "joint_positions_rad", "native_transforms")})
    return {"snapshot": snapshot, "comparison": comparison,
            "isaac_started_by_helper": False, "hardware_access_by_helper": False}


def build_snapshot_receipt(urdf: Path, snapshot: dict) -> dict:
    """Produce a hash-bound offline comparison without asserting capture provenance."""
    keys = {"link_names", "joint_names", "joint_positions_rad", "joint_positions_after_rad",
            "native_transforms", "maximum_joint_change_rad", "scope"}
    if set(snapshot) != keys or snapshot["scope"] != "read-only non-atomic simulation snapshot":
        raise ValueError("snapshot schema changed")
    before = np.asarray(snapshot["joint_positions_rad"], dtype=float)
    after = np.asarray(snapshot["joint_positions_after_rad"], dtype=float)
    limit = snapshot["maximum_joint_change_rad"]
    if (before.shape != (6,) or after.shape != (6,) or not np.isfinite(before).all()
        or not np.isfinite(after).all() or not isinstance(limit, (int, float))
        or isinstance(limit, bool) or not math.isfinite(limit) or limit < 0 or limit > 1e-7
        or np.max(np.abs(before - after)) > limit):
        raise ValueError("snapshot joint consistency invalid")
    comparison = compare_link_frames(urdf, **{key: snapshot[key] for key in
        ("link_names", "joint_names", "joint_positions_rad", "native_transforms")})
    receipt = {"schema": "tactevra.arm301.offline_link_frame_comparison.v1",
        "snapshot": snapshot, "comparison": comparison, "urdf_sha256": _file_sha(urdf),
        "comparator_sha256": _file_sha(Path(__file__)),
        "capture_provenance_verified": False, "isaac_started_by_helper": False,
        "hardware_access_by_helper": False}
    encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {**receipt, "receipt_sha256": hashlib.sha256(encoded).hexdigest()}


def compare_stationary_session(session: object, urdf: Path) -> dict:
    """Compare one already-initialized session without starting or stepping it.

    The caller owns session lifecycle and authorization. The returned receipt
    still does not independently verify the session's identity or provenance.
    """
    before_steps = session.physics_steps
    if type(before_steps) is not int or before_steps != 0:
        raise ValueError("session must report zero physics steps")
    native = session.native_objects()
    if not isinstance(native, dict) or "articulation" not in native:
        raise ValueError("session articulation unavailable")
    snapshot = capture_link_snapshot(native["articulation"])
    if session.physics_steps != before_steps:
        raise ValueError("session advanced during snapshot")
    return build_snapshot_receipt(urdf, snapshot)
