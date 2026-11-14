from pathlib import Path
import sys

import pytest
np = pytest.importorskip("numpy")
Rotation = pytest.importorskip("scipy.spatial.transform").Rotation

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/integrations/isaac_sim"))
sys.path.insert(0, str(ROOT / "software/src"))
from arm301_link_frame_parity import compare_link_frames
from arm301_source_route_obb_audit import _OfflineArticulation
from nominal_route_native_component_obb_binding import EXPECTED_DOF_NAMES, NATIVE_LINKS


def test_all_link_frames_are_compared_and_common_base_placement_is_removed():
    urdf = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    positions = [0.2, -0.3, 0.4, -0.5, 0.6, 0.1]
    articulation = _OfflineArticulation(urdf)
    articulation.set_dof_positions([positions])
    rows = np.asarray(articulation.get_link_transforms()[0])
    global_rotation = Rotation.from_euler("xyz", [0.3, -0.2, 0.4])
    rows[:, :3] = global_rotation.apply(rows[:, :3]) + [0.4, -0.1, 0.7]
    rows[:, 3:] = (global_rotation * Rotation.from_quat(rows[:, 3:])).as_quat()
    args = dict(link_names=NATIVE_LINKS, joint_names=EXPECTED_DOF_NAMES,
                joint_positions_rad=positions, native_transforms=rows)
    result = compare_link_frames(urdf, **args)
    assert result["parity_pass"] is True
    assert len(result["link_results"]) == 7
    rows[3, 0] += 0.001
    result = compare_link_frames(urdf, **args)
    assert result["parity_pass"] is False
    assert result["link_results"][3]["translation_error_mm"] == pytest.approx(1.0)
    rows[3, 0] -= 0.001
    rows[4, 3:] = (Rotation.from_rotvec([0.01, 0, 0]) * Rotation.from_quat(rows[4, 3:])).as_quat()
    result = compare_link_frames(urdf, **args)
    assert result["parity_pass"] is False
    assert result["link_results"][4]["rotation_error_deg"] == pytest.approx(0.01 * 180 / np.pi)
    rows[3, 3:] = [0, 0, 0, 0]
    with pytest.raises(ValueError, match="quaternion"):
        compare_link_frames(urdf, **args)


def test_wrong_link_order_is_rejected():
    urdf = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    with pytest.raises(ValueError, match="order"):
        compare_link_frames(urdf, link_names=NATIVE_LINKS[::-1], joint_names=EXPECTED_DOF_NAMES,
                            joint_positions_rad=[0] * 6, native_transforms=[[0] * 7] * 7)
