from pathlib import Path
import json
import subprocess
import sys

import pytest
np = pytest.importorskip("numpy")
Rotation = pytest.importorskip("scipy.spatial.transform").Rotation

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/integrations/isaac_sim"))
sys.path.insert(0, str(ROOT / "software/src"))
from arm301_link_frame_parity import (build_snapshot_receipt, capture_and_compare,
    capture_link_snapshot, compare_link_frames, compare_stationary_session)
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


def test_capture_is_read_only_and_rejects_changes():
    urdf = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    class FakeArticulation(_OfflineArticulation):
        def __init__(self):
            super().__init__(urdf)
            self.positions = [0.0] * 6
            self.reads = 0
            self.changed = False
        def get_dof_positions(self):
            self.reads += 1
            return [[0.01 if self.changed and self.reads % 2 == 0 else 0.0] + [0.0] * 5]
        def set_dof_positions(self, rows):
            raise AssertionError("capture must not set joint state")
    articulation = FakeArticulation()
    snapshot = capture_link_snapshot(articulation)
    assert articulation.reads == 2
    assert compare_link_frames(urdf, **{k: snapshot[k] for k in
        ("link_names", "joint_names", "joint_positions_rad", "native_transforms")})["parity_pass"]
    assert capture_and_compare(articulation, urdf)["comparison"]["parity_pass"]
    receipt = build_snapshot_receipt(urdf, snapshot)
    assert receipt["comparison"]["parity_pass"]
    assert receipt["capture_provenance_verified"] is False
    assert len(receipt["receipt_sha256"]) == 64
    changed_snapshot = dict(snapshot)
    changed_snapshot["joint_positions_after_rad"] = [0.01] + [0.0] * 5
    with pytest.raises(ValueError, match="consistency"):
        build_snapshot_receipt(urdf, changed_snapshot)
    articulation.changed = True
    with pytest.raises(ValueError, match="changed during snapshot"):
        capture_link_snapshot(articulation)


def test_capture_rejects_changed_joint_state_with_reused_native_buffer():
    urdf = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    class ReusedBuffer(_OfflineArticulation):
        def __init__(self):
            super().__init__(urdf)
            self.positions = [0.0] * 6
            self.buffer = np.zeros((1, 6))
            self.reads = 0
        def get_dof_positions(self):
            self.reads += 1
            if self.reads == 2:
                self.buffer[0, 0] = 0.01
            return self.buffer
    with pytest.raises(ValueError, match="changed during snapshot"):
        capture_link_snapshot(ReusedBuffer())


def test_stationary_session_comparison_never_starts_or_steps():
    urdf = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    class ReadOnlyArticulation(_OfflineArticulation):
        def __init__(self):
            super().__init__(urdf)
            self.positions = [0.0] * 6
        def get_dof_positions(self):
            return [self.positions]
    class Session:
        physics_steps = 0
        def native_objects(self):
            return {"articulation": ReadOnlyArticulation()}
        def start_headless(self):
            raise AssertionError("comparison must not start Isaac")
        def settle_scene(self):
            raise AssertionError("comparison must not step physics")
    session = Session()
    receipt = compare_stationary_session(session, urdf)
    assert receipt["comparison"]["parity_pass"]
    assert receipt["capture_provenance_verified"] is False
    session.physics_steps = 1
    with pytest.raises(ValueError, match="zero physics steps"):
        compare_stationary_session(session, urdf)
    session.physics_steps = 0
    class AdvancingArticulation(ReadOnlyArticulation):
        def get_link_transforms(self):
            session.physics_steps = 1
            return super().get_link_transforms()
    session.native_objects = lambda: {"articulation": AdvancingArticulation()}
    with pytest.raises(ValueError, match="advanced during snapshot"):
        compare_stationary_session(session, urdf)


def test_snapshot_cli_retains_failed_comparison_and_refuses_overwrite(tmp_path):
    urdf = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    class ReadOnlyArticulation(_OfflineArticulation):
        def __init__(self):
            super().__init__(urdf)
            self.positions = [0.0] * 6
        def get_dof_positions(self):
            return [self.positions]
    snapshot = capture_link_snapshot(ReadOnlyArticulation())
    snapshot["native_transforms"][3][0] += 0.001
    source, output = tmp_path / "snapshot.json", tmp_path / "receipt.json"
    source.write_text(json.dumps(snapshot), encoding="utf-8")
    command = [sys.executable, str(ROOT / "software/integrations/isaac_sim/arm301_link_frame_parity.py"),
               "--snapshot", str(source), "--output", str(output)]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 2, first.stderr
    original = output.read_bytes()
    receipt = json.loads(original)
    assert receipt["comparison"]["parity_pass"] is False
    assert receipt["capture_provenance_verified"] is False
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert second.returncode != 0
    assert output.read_bytes() == original
