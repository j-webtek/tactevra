from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import rocell.application.fixed_camera_keyboard_profiled_collision_partitions_v1 as subject
import rocell.application.fixed_camera_keyboard_profiled_route_screen_v1 as route_subject
from rocell.application.bounded_segment_collision_qualification import (
    BoundedSegmentSamplingPolicy,
)
from rocell.application.fixed_camera_keyboard_profiled_collision_partitions_v1 import (
    MANIFEST_NAME,
    PARTITION_NAMES,
    RECEIPT_NAME,
    RECEIPT_STATUS,
    STATUS,
    FixedCameraKeyboardProfiledCollisionPartitionsV1Error,
    partition_fixed_camera_keyboard_profiled_collision_routes_v1,
)
from rocell.application.partitioned_typing_collision_intake_v1 import READY_STATUS
from rocell.application.typing_trajectory_ik_screen_v1 import (
    screen_typing_trajectory_ik_v1,
)

from test_fixed_camera_keyboard_profiled_route_screen_v1 import (
    PROFILES,
    _bundle as route_bundle,
    _call as route_call,
    _fake_collision,
)
from test_typing_trajectory_ik_screen_v1 import _seed, _trajectory


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _route_screen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bundle = route_bundle(tmp_path)
    context, snapshot, *_ = bundle
    execution, trajectory = _trajectory(context, snapshot)
    template = screen_typing_trajectory_ik_v1(
        execution,
        trajectory,
        context,
        snapshot,
        _seed(context, snapshot),
    )

    def valid_ik(source_plan, route, _context, supplied_snapshot, seed, **_kwargs):
        report = copy.deepcopy(template)
        report.pop("typing_trajectory_ik_screen_sha256")
        report["typing_execution_plan_sha256"] = source_plan.plan_sha256
        report["typing_trajectory_plan_sha256"] = route.trajectory_plan_sha256
        report["calibration_snapshot_sha256"] = supplied_snapshot.snapshot_sha256
        report["seed_sha256"] = seed.seed_sha256
        report["seed"] = {
            **report["seed"],
            "seed_id": seed.seed_id,
            "calibration_snapshot_sha256": supplied_snapshot.snapshot_sha256,
            "build_snapshot_sha256": _context.snapshot.snapshot_hash,
            "joint_positions_rad": dict(seed.joint_positions_rad),
        }
        report["typing_trajectory_ik_screen_sha256"] = hashlib.sha256(
            _canonical(report)
        ).hexdigest()
        return report

    monkeypatch.setattr(route_subject, "screen_typing_trajectory_ik_v1", valid_ik)
    monkeypatch.setattr(
        route_subject,
        "prepare_typing_collision_intake_v1",
        _fake_collision,
    )
    return bundle, route_call(tmp_path, bundle)


def _call(tmp_path: Path, bundle, route_screen):
    context, snapshot, _admitted, installed, _policies, _seeds = bundle
    return partition_fixed_camera_keyboard_profiled_collision_routes_v1(
        route_screen.receipt_path,
        expected_route_screen_receipt_file_sha256=_sha(
            route_screen.receipt_path.read_bytes()
        ),
        route_screen_manifest_path=route_screen.manifest_path,
        expected_route_screen_manifest_file_sha256=_sha(
            route_screen.manifest_path.read_bytes()
        ),
        ik_screen_paths=route_screen.ik_paths,
        expected_ik_screen_file_sha256={
            name: _sha(route_screen.ik_paths[name].read_bytes()) for name in PROFILES
        },
        context=context,
        calibration_snapshot=snapshot,
        installed_collision_profiles=installed,
        sampling_policies={
            name: BoundedSegmentSamplingPolicy(
                maximum_joint_step_rad=0.25,
                maximum_samples=4,
            )
            for name in PROFILES
        },
        output_directory=tmp_path / "profiled-collision-partitions",
    )


def test_profile_routes_publish_separate_partitioned_collision_intakes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, route_screen = _route_screen(tmp_path, monkeypatch)

    result = _call(tmp_path, bundle, route_screen)

    assert result.manifest["status"] == STATUS
    assert result.receipt["status"] == RECEIPT_STATUS
    assert result.manifest_path.name == MANIFEST_NAME
    assert result.receipt_path.name == RECEIPT_NAME
    assert result.receipt["artifacts"]["completion_receipt"]["written_last"] is True
    assert result.manifest["profile_separation_preserved"] is True
    assert result.manifest["authority"]["physical_authority"] is False
    rows = result.manifest["profiles"]
    assert (
        rows["no_attachment"]["installed_collision_profile_content_sha256"]
        != rows["stylus_attachment"]["installed_collision_profile_content_sha256"]
    )
    for name in PROFILES:
        assert result.partition_paths[name].name == PARTITION_NAMES[name]
        assert result.partition_paths[name].is_file()
        report = json.loads(result.partition_paths[name].read_bytes())
        assert report["status"] == READY_STATUS
        assert len(report["partitions"]) > 1
        assert len(report["boundary_lineage"]) == len(report["partitions"]) - 1
        assert report["installed_geometry_collision_screening_executed"] is False
        assert report["controller_commands"] == []
        assert report["hardware_access"] is report["physical_authority"] is False


def test_crossed_profile_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, route_screen = _route_screen(tmp_path, monkeypatch)
    context, snapshot, admitted, installed, policies, seeds = bundle
    crossed = {**installed, "no_attachment": installed["stylus_attachment"]}

    with pytest.raises(
        FixedCameraKeyboardProfiledCollisionPartitionsV1Error,
        match="distinct installed collision profiles|differs from route screen",
    ):
        _call(
            tmp_path,
            (context, snapshot, admitted, crossed, policies, seeds),
            route_screen,
        )
    assert not (tmp_path / "profiled-collision-partitions").exists()


def test_tampered_ik_binding_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, route_screen = _route_screen(tmp_path, monkeypatch)
    source = route_screen.ik_paths["no_attachment"]
    changed = json.loads(source.read_bytes())
    changed["sample_count"] += 1
    source.write_bytes(_canonical(changed) + b"\n")

    with pytest.raises(
        FixedCameraKeyboardProfiledCollisionPartitionsV1Error,
        match="IK binding differs",
    ):
        _call(tmp_path, bundle, route_screen)
    assert not (tmp_path / "profiled-collision-partitions").exists()


def test_blocked_partition_fails_closed_without_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, route_screen = _route_screen(tmp_path, monkeypatch)
    real = subject.prepare_partitioned_typing_collision_intake_v1
    calls = 0

    def block_second(*args, **kwargs):
        nonlocal calls
        report = real(*args, **kwargs)
        calls += 1
        if calls == 2:
            return {**report, "status": "BLOCKED_TEST_ONLY"}
        return report

    monkeypatch.setattr(
        subject,
        "prepare_partitioned_typing_collision_intake_v1",
        block_second,
    )
    with pytest.raises(
        FixedCameraKeyboardProfiledCollisionPartitionsV1Error,
        match="did not reach partitioned collision intake",
    ):
        _call(tmp_path, bundle, route_screen)
    assert not (tmp_path / "profiled-collision-partitions").exists()
