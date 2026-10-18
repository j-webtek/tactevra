from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import rocell.application.fixed_camera_keyboard_profiled_route_screen_v1 as subject
from rocell.application.context import load_simulation_context
from rocell.application.fixed_camera_keyboard_profiled_route_screen_v1 import (
    COLLISION_NAMES,
    IK_NAMES,
    MANIFEST_NAME,
    RECEIPT_NAME,
    RECEIPT_STATUS,
    STATUS,
    TRAJECTORY_NAMES,
    FixedCameraKeyboardProfiledRouteScreenV1Error,
    screen_fixed_camera_keyboard_profiled_routes_v1,
)
from rocell.application.typing_collision_intake_v1 import (
    READY_STATUS as COLLISION_READY_STATUS,
)
from rocell.application.typing_trajectory_ik_screen_v1 import (
    BLOCKED_STATUS as IK_BLOCKED_STATUS,
    READY_STATUS as IK_READY_STATUS,
    TypingTrajectoryIkSeedV1,
)
from rocell.application.typing_trajectory_plan_v1 import TypingTrajectoryPolicyV1

from test_fixed_camera_keyboard_clearance_intake_v1 import _profiles
from test_fixed_camera_keyboard_profiled_typing_plan_v1 import _admit, _inputs
from test_typing_trajectory_ik_screen_v1 import _ready_joint_values, _snapshot


ROOT = Path(__file__).resolve().parents[3]
SYSTEM_MANIFEST = ROOT / "software/config/system_manifest.json"
PROFILES = ("no_attachment", "stylus_attachment")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _bundle(tmp_path: Path):
    context = load_simulation_context(ROOT, SYSTEM_MANIFEST)
    snapshot = _snapshot(context)
    paths, hashes = _inputs(tmp_path)
    for key in ("bare_config", "stylus_config"):
        config = json.loads(paths[key].read_bytes())
        config["calibration_snapshot_sha256"] = snapshot.snapshot_sha256
        payload = (
            json.dumps(
                config,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        paths[key].write_bytes(payload)
        hashes[key] = _sha(payload)
    admitted = _admit(tmp_path, paths, hashes)
    installed = _profiles(context)
    policies = {
        "no_attachment": TypingTrajectoryPolicyV1("bare-route-v1"),
        "stylus_attachment": TypingTrajectoryPolicyV1(
            "stylus-route-v1", maximum_cartesian_step_mm=4.0
        ),
    }
    seeds = {
        name: TypingTrajectoryIkSeedV1(
            f"{name}-offline-seed",
            snapshot.snapshot_sha256,
            context.snapshot.snapshot_hash,
            _ready_joint_values(context),
        )
        for name in PROFILES
    }
    return context, snapshot, admitted, installed, policies, seeds


def _call(tmp_path: Path, bundle):
    context, snapshot, admitted, installed, policies, seeds = bundle
    return screen_fixed_camera_keyboard_profiled_routes_v1(
        admitted.receipt_path,
        expected_typing_plan_admission_receipt_file_sha256=_sha(
            admitted.receipt_path.read_bytes()
        ),
        typing_plan_manifest_path=admitted.manifest_path,
        expected_typing_plan_manifest_file_sha256=_sha(
            admitted.manifest_path.read_bytes()
        ),
        plan_paths=admitted.plan_paths,
        expected_plan_file_sha256={
            name: _sha(admitted.plan_paths[name].read_bytes()) for name in PROFILES
        },
        context=context,
        calibration_snapshot=snapshot,
        trajectory_policies=policies,
        ik_seeds=seeds,
        installed_collision_profiles=installed,
        output_directory=tmp_path / "profiled-route-screen",
    )


def _fake_ik(source_plan, trajectory, _context, snapshot, seed, **_kwargs):
    core = {
        "schema": "rocell.typing_trajectory_ik_screen.v1",
        "status": IK_READY_STATUS,
        "typing_execution_plan_sha256": source_plan.plan_sha256,
        "typing_trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "calibration_snapshot_sha256": snapshot.snapshot_sha256,
        "seed_sha256": seed.seed_sha256,
        "ik_all_samples_accepted": True,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {
        **core,
        "typing_trajectory_ik_screen_sha256": hashlib.sha256(
            json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _fake_collision(source_plan, trajectory, ik, _context, _snapshot, profile, **_kwargs):
    core = {
        "schema": "rocell.typing_collision_intake.v1",
        "status": COLLISION_READY_STATUS,
        "typing_execution_plan_sha256": source_plan.plan_sha256,
        "typing_trajectory_plan_sha256": trajectory.trajectory_plan_sha256,
        "typing_trajectory_ik_screen_sha256": ik[
            "typing_trajectory_ik_screen_sha256"
        ],
        "installed_collision_profile_sha256": profile.content_sha256,
        "bounded_sample_count": len(trajectory.screening_samples),
        "required_evidence_slots": {
            "configuration_sample_count": len(trajectory.screening_samples)
        },
        "blockers": [
            "MEASURED_RIGID_ATTACHMENT_BINDINGS_REQUIRED",
            "CONFIGURATION_GEOMETRY_REQUIRED_FOR_EVERY_BOUNDED_SAMPLE",
            "CONFIGURATION_SWEEP_ENVELOPES_REQUIRED_FOR_EVERY_ADJACENT_SAMPLE",
            "FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION",
        ],
        "next_required_stage": "SUPPLY_PROFILE_BOUND_COLLISION_EVIDENCE",
        "hardware_access": False,
        "physical_authority": False,
    }
    return {
        **core,
        "typing_collision_intake_sha256": hashlib.sha256(
            json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def test_exact_plan_bundle_publishes_separate_profile_route_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(tmp_path)
    monkeypatch.setattr(subject, "screen_typing_trajectory_ik_v1", _fake_ik)
    monkeypatch.setattr(subject, "prepare_typing_collision_intake_v1", _fake_collision)

    result = _call(tmp_path, bundle)

    assert result.manifest["status"] == STATUS
    assert result.receipt["status"] == RECEIPT_STATUS
    assert result.receipt["artifacts"]["completion_receipt"]["written_last"] is True
    assert result.manifest["profile_separation_preserved"] is True
    assert result.manifest["authority"]["physical_authority"] is False
    for name in PROFILES:
        assert result.trajectory_paths[name].name == TRAJECTORY_NAMES[name]
        assert result.ik_paths[name].name == IK_NAMES[name]
        assert result.collision_paths[name].name == COLLISION_NAMES[name]
        assert result.trajectory_paths[name].is_file()
        assert result.ik_paths[name].is_file()
        assert result.collision_paths[name].is_file()
    assert result.manifest_path.name == MANIFEST_NAME
    assert result.receipt_path.name == RECEIPT_NAME
    rows = result.manifest["profiles"]
    assert rows["no_attachment"]["typing_trajectory_plan_sha256"] != rows[
        "stylus_attachment"
    ]["typing_trajectory_plan_sha256"]
    assert rows["no_attachment"]["typing_trajectory_ik_seed_sha256"] != rows[
        "stylus_attachment"
    ]["typing_trajectory_ik_seed_sha256"]


def test_crossed_profile_or_reused_policy_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(tmp_path)
    monkeypatch.setattr(subject, "screen_typing_trajectory_ik_v1", _fake_ik)
    monkeypatch.setattr(subject, "prepare_typing_collision_intake_v1", _fake_collision)
    context, snapshot, admitted, installed, policies, seeds = bundle
    crossed = {**installed, "no_attachment": installed["stylus_attachment"]}
    with pytest.raises(
        FixedCameraKeyboardProfiledRouteScreenV1Error,
        match="distinct installed collision profiles|admitted binding",
    ):
        _call(tmp_path, (context, snapshot, admitted, crossed, policies, seeds))
    assert not (tmp_path / "profiled-route-screen").exists()

    same = {name: policies["no_attachment"] for name in PROFILES}
    with pytest.raises(
        FixedCameraKeyboardProfiledRouteScreenV1Error,
        match="distinct trajectory policies",
    ):
        _call(tmp_path, (context, snapshot, admitted, installed, same, seeds))


def test_blocked_ik_fails_closed_without_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(tmp_path)

    def blocked(*args, **kwargs):
        report = _fake_ik(*args, **kwargs)
        return {**report, "status": IK_BLOCKED_STATUS}

    monkeypatch.setattr(subject, "screen_typing_trajectory_ik_v1", blocked)
    monkeypatch.setattr(subject, "prepare_typing_collision_intake_v1", _fake_collision)
    with pytest.raises(
        FixedCameraKeyboardProfiledRouteScreenV1Error,
        match="did not pass deterministic IK screening",
    ):
        _call(tmp_path, bundle)
    assert not (tmp_path / "profiled-route-screen").exists()
