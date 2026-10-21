from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _load(name: str):
    path = ROOT / f"software/integrations/isaac_sim/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


BUNDLE = _load("joint_schedule_replay_bundle")
REPLAY = _load("joint_schedule_isaac_replay_probe")
COMMIT = "5" * 40
JOINTS = {
    "base_link_to_link1": 0.1,
    "link1_to_link2": 0.2,
    "link2_to_link3": 0.3,
    "link3_to_link4": 0.4,
    "link4_to_link5": 0.5,
}


def _sha(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _ready_profiled_admission():
    lock = {
        "schema": "rocell.isaac_sim_toolchain_lock.v1",
        "selection_status": "SELECTED",
        "isaac_sim_version": "test-only",
        "installation_sha256": "1" * 64,
        "extension_lock_sha256": "2" * 64,
        "settings_profile_sha256": "3" * 64,
        "runner_platform": "offline-test",
        "launch_method": "test-only",
        "license_review_status": "REVIEWED_FOR_INTERNAL_INTEGRATION",
        "hardware_access": False,
        "physical_authority": False,
        "wire_commands": [],
    }
    samples = [{
        "route_sample_sequence": sequence,
        "source_segment_index": None if sequence == 0 else sequence - 1,
        "joint_positions_rad": dict(JOINTS),
        "source_sample_sha256": f"{sequence:064x}",
    } for sequence in range(329)]
    trajectory_core = {
        "sample_count": 329,
        "segment_count": 328,
        "samples": samples,
    }
    trajectory = {**trajectory_core, "trajectory_sha256": _sha(trajectory_core)}
    request_core = {
        "active_profile": "no_attachment",
        "qualification_sha256": "4" * 64,
        "partitioned_typing_collision_intake_sha256": "5" * 64,
        "trajectory_sha256": trajectory["trajectory_sha256"],
        "toolchain_lock_sha256": _sha(lock),
        "isaac_sim_version": lock["isaac_sim_version"],
        "installation_sha256": lock["installation_sha256"],
        "extension_lock_sha256": lock["extension_lock_sha256"],
        "settings_profile_sha256": lock["settings_profile_sha256"],
        "random_seed": 0,
        "replan_allowed": False,
    }
    request = {**request_core, "request_sha256": _sha(request_core)}
    handoff_core = {
        "schema": "rocell.profiled_entry_route_isaac_replay_handoff.v1",
        "status": "READY_FOR_NATIVE_ISAAC_REPLAY_ZERO_AUTHORITY",
        "active_profile": "no_attachment",
        "profile_separation_preserved": True,
        "profiled_entry_route_qualification_sha256": "4" * 64,
        "partitioned_typing_collision_intake_sha256": "5" * 64,
        "installed_collision_profile_sha256": "6" * 64,
        "calibration_snapshot_sha256": "7" * 64,
        "build_snapshot_sha256": "8" * 64,
        "trajectory": trajectory,
        "toolchain_lock_sha256": _sha(lock),
        "toolchain_selection_status": "SELECTED",
        "isaac_replay_request": request,
        "blockers": [],
        "next_required_stage": "RUN_EXACT_NATIVE_ISAAC_REPLAY_AND_RETAIN_RECEIPT",
        "authority": {
            "controller_commands": [],
            "hardware_commands_generated": 0,
            "hardware_access": False,
            "physical_movements": 0,
            "physical_authority": False,
        },
    }
    handoff = {
        **handoff_core,
        "isaac_replay_handoff_sha256": _sha(handoff_core),
    }
    route_bound_core = {
        "schema": "rocell.route_bound_entry_isaac_replay_handoff.v1",
        "status": "READY_ROUTE_BOUND_NATIVE_ISAAC_REPLAY_ZERO_AUTHORITY",
        "active_profile": "no_attachment",
        "route_bound_collision_qualification_sha256": "9" * 64,
        "route_bound_entry_qualification_sha256": "a" * 64,
        "route_envelope_binding_sha256": "b" * 64,
        "installed_collision_profile_sha256": "6" * 64,
        "profiled_entry_route_qualification_sha256": "4" * 64,
        "isaac_replay_handoff": handoff,
        "isaac_replay_handoff_sha256": handoff["isaac_replay_handoff_sha256"],
        "profile_separation_preserved": True,
        "exact_route_and_fresh_entry_verified_before_handoff": True,
        "blockers": [],
        "next_required_stage": "RUN_EXACT_NATIVE_ISAAC_REPLAY_AND_RETAIN_RECEIPT",
        "authority": {
            "exact_route_binding_verified": True,
            "fresh_entry_binding_verified": True,
            "replan_allowed": False,
            "controller_commands": [],
            "hardware_commands_generated": 0,
            "hardware_writes": 0,
            "hardware_access": False,
            "physical_movements": 0,
            "physical_authority": False,
        },
    }
    route_bound = {
        **route_bound_core,
        "route_bound_isaac_replay_handoff_sha256": _sha(route_bound_core),
    }
    usd = b"governed-test-usd"
    receipt_core = {
        "schema": "tactevra.isaac_sim_urdf_import.v1",
        "external_files": [{
            "path": "robot.usda",
            "sha256": hashlib.sha256(usd).hexdigest(),
            "size_bytes": len(usd),
        }],
        "articulation_root_normalization": {
            "expected_live_dof_order": list(REPLAY.EXPECTED_DOFS),
        },
        "hardware_access": False,
        "physical_authority": False,
        "wire_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
    }
    receipt = {**receipt_core, "receipt_sha256": _sha(receipt_core)}
    return route_bound, lock, receipt, usd


def _report():
    samples = []
    trajectory = []
    ik = []
    for index in range(2):
        samples.append({
            "sequence": index,
            "time_from_start_ns": index * 100,
            "phase": "CONTACT",
            "phase_endpoint": True,
            "action_index": index,
            "target_id": "H",
            "joint_positions_rad": JOINTS,
        })
        trajectory.append({
            "sequence": index,
            "phase": "CONTACT",
            "action_index": index,
            "target_id": "H",
            "point": {"frame": "board", "x": 1.0, "y": 2.0, "z": 3.0},
        })
        ik.append({
            "accepted": True,
            "hardware_commands_generated": 0,
            "position_error_mm": 0.01,
            "minimum_normalized_arm_joint_margin": 0.2,
        })
    return {
        "arm_source_commit": COMMIT,
        "geometry_variant": "UNMEASURED_SENSITIVITY_OVERLAY",
        "virtual_profile_sha256": "a" * 64,
        "ordered_target_ids": ["H", "H"],
        "batch": {"proposals": [{"target_id": "H"}, {"target_id": "H"}]},
        "trajectory": {"screening_samples": trajectory},
        "ik": {
            "status": "READY_FOR_INSTALLED_GEOMETRY_COLLISION_SCREENING",
            "joint_results": ik,
        },
        "schedule": {
            "schema": "rocell.typing_joint_schedule.v1",
            "status": "READY_FOR_INSTALLED_GEOMETRY_AND_FRESH_STATE_SCREENING",
            "hardware_access": False,
            "physical_authority": False,
            "hardware_commands_generated": 0,
            "controller_commands": [],
            "samples": samples,
            "source_trajectory_plan_sha256": "b" * 64,
            "source_ik_screen_sha256": "c" * 64,
            "profile_sha256": "d" * 64,
            "total_motion_and_dwell_time_ns": 100,
            "joint_dynamics_all_samples_accepted": True,
            "blockers": ["INSTALLED_GEOMETRY_COLLISION_SCREENING_REQUIRED"],
        },
    }


def _build(report):
    raw = json.dumps(report, sort_keys=True).encode()
    return BUNDLE.build_replay_bundle(report, raw, COMMIT)


def test_bundle_preserves_repeated_contact_order_and_zero_authority():
    bundle = _build(_report())
    assert bundle["ordered_target_ids"] == ["H", "H"]
    assert bundle["sample_count"] == 2
    assert bundle["controller_commands"] == []
    assert bundle["hardware_writes"] == 0
    assert bundle["physical_movements"] == 0
    REPLAY._validate_bundle(bundle)


@pytest.mark.parametrize("mutation", ["commit", "order", "authority", "sequence"])
def test_bundle_rejects_source_or_semantic_tampering(mutation):
    report = deepcopy(_report())
    if mutation == "commit":
        report["arm_source_commit"] = "6" * 40
    elif mutation == "order":
        report["batch"]["proposals"][1]["target_id"] = "1"
    elif mutation == "authority":
        report["schedule"]["controller_commands"] = [{"unsafe": True}]
    else:
        report["schedule"]["samples"][1]["sequence"] = 9
    with pytest.raises(ValueError):
        _build(report)


def test_isaac_intake_rejects_changed_bundle_digest():
    bundle = _build(_report())
    bundle["samples"][0]["target_id"] = "1"
    with pytest.raises(ValueError, match="digest"):
        REPLAY._validate_bundle(bundle)


def test_v2_bundle_binds_actual_emitter_payload_to_retained_batch():
    report = _report()
    report["actual_shared_emitter_used"] = True
    report["actual_emitter_input_sha256"] = "e" * 64
    report["actual_emitter_payload_sha256"] = BUNDLE._digest(
        BUNDLE._canonical(report["batch"])
    )
    raw = json.dumps(report, sort_keys=True).encode()
    bundle = BUNDLE.build_replay_bundle(
        report, raw, COMMIT, require_actual_emitter=True
    )
    assert bundle["schema"].endswith(".v2")
    assert bundle["producer"]["kind"] == "ACTUAL_SHARED_EMITTER"
    assert bundle["producer"]["payload_sha256"] == bundle["source"][
        "batch_sha256"
    ]
    assert bundle["producer"]["deployment_qualification_claimed"] is False
    REPLAY._validate_bundle(bundle)


def test_v2_bundle_rejects_unbound_actual_emitter_claim():
    report = _report()
    report["actual_shared_emitter_used"] = True
    report["actual_emitter_input_sha256"] = "e" * 64
    report["actual_emitter_payload_sha256"] = "f" * 64
    raw = json.dumps(report, sort_keys=True).encode()
    with pytest.raises(ValueError, match="payload"):
        BUNDLE.build_replay_bundle(
            report, raw, COMMIT, require_actual_emitter=True
        )


def test_route_bound_native_admission_binds_every_identity_before_isaac_import():
    handoff, lock, receipt, usd = _ready_profiled_admission()
    admission = REPLAY._validate_route_bound_native_admission(
        handoff,
        lock,
        receipt,
        usd_bytes=usd,
        import_receipt_file_sha256="9" * 64,
    )
    assert admission["status"] == "READY_FOR_NATIVE_ISAAC_START_ZERO_AUTHORITY"
    assert admission["active_profile"] == "no_attachment"
    assert admission["sample_count"] == 329
    assert admission["segment_count"] == 328
    assert admission["route_bound_collision_qualification_sha256"] == "9" * 64
    assert admission["route_bound_entry_qualification_sha256"] == "a" * 64
    assert admission["controller_commands"] == []
    assert admission["gate_promotions"] == []
    assert "isaacsim" not in sys.modules


@pytest.mark.parametrize("mutation", ["usd", "dof_order", "joint_order"])
def test_route_bound_native_admission_rejects_crossed_governed_inputs(mutation):
    handoff, lock, receipt, usd = _ready_profiled_admission()
    if mutation == "usd":
        usd += b"-changed"
    elif mutation == "dof_order":
        receipt["articulation_root_normalization"]["expected_live_dof_order"].reverse()
        core = dict(receipt)
        core.pop("receipt_sha256")
        receipt["receipt_sha256"] = _sha(core)
    else:
        nested = handoff["isaac_replay_handoff"]
        joints = nested["trajectory"]["samples"][0]["joint_positions_rad"]
        nested["trajectory"]["samples"][0]["joint_positions_rad"] = dict(
            reversed(list(joints.items()))
        )
        trajectory = nested["trajectory"]
        trajectory_core = dict(trajectory)
        trajectory_core.pop("trajectory_sha256")
        trajectory["trajectory_sha256"] = _sha(trajectory_core)
        nested["isaac_replay_request"]["trajectory_sha256"] = trajectory[
            "trajectory_sha256"
        ]
        request_core = dict(nested["isaac_replay_request"])
        request_core.pop("request_sha256")
        nested["isaac_replay_request"]["request_sha256"] = _sha(request_core)
        handoff_core = dict(nested)
        handoff_core.pop("isaac_replay_handoff_sha256")
        nested["isaac_replay_handoff_sha256"] = _sha(handoff_core)
    with pytest.raises(ValueError):
        REPLAY._validate_route_bound_native_admission(
            handoff,
            lock,
            receipt,
            usd_bytes=usd,
            import_receipt_file_sha256="9" * 64,
        )


def test_admission_only_cli_exits_before_native_runtime(monkeypatch, tmp_path):
    handoff, lock, receipt, usd = _ready_profiled_admission()
    paths = {
        "usd": tmp_path / "robot.usda",
        "receipt": tmp_path / "import.json",
        "handoff": tmp_path / "handoff.json",
        "lock": tmp_path / "lock.json",
        "output": tmp_path / "admission.json",
        "status": tmp_path / "admission.status.json",
    }
    paths["usd"].write_bytes(usd)
    for name, value in (
        ("receipt", receipt),
        ("handoff", handoff),
        ("lock", lock),
    ):
        paths[name].write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "joint_schedule_isaac_replay_probe.py",
        "--admission-only",
        "--usd", str(paths["usd"]),
        "--import-receipt", str(paths["receipt"]),
        "--route-bound-handoff", str(paths["handoff"]),
        "--toolchain-lock", str(paths["lock"]),
        "--output", str(paths["output"]),
        "--status-output", str(paths["status"]),
    ])
    assert REPLAY.main() == 0
    assert json.loads(paths["output"].read_text())["evidence_class"] == (
        "NATIVE_ISAAC_ADMISSION_ONLY"
    )
    assert json.loads(paths["status"].read_text())["status"] == (
        "READY_FOR_NATIVE_ISAAC_START_ZERO_AUTHORITY"
    )
    assert "isaacsim" not in sys.modules


def test_native_admission_rejects_legacy_inner_handoff() -> None:
    route_bound, lock, receipt, usd = _ready_profiled_admission()
    with pytest.raises(ValueError, match="fields differ"):
        REPLAY._validate_route_bound_native_admission(
            route_bound["isaac_replay_handoff"],
            lock,
            receipt,
            usd_bytes=usd,
            import_receipt_file_sha256="9" * 64,
        )
