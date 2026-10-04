from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "software/integrations/isaac_sim/residual_obstruction_v4_2_isaac_probe.py"
SPEC = importlib.util.spec_from_file_location("v4_2_renderer", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
FIXTURE = ROOT / "software/ai/sim/evidence/residual_obstruction_successor_v4_2.json"


def test_v4_2_fixture_is_unconsumed_and_evaluation_absent() -> None:
    fixture, payload = MODULE.load_fixture(FIXTURE)
    assert payload
    assert fixture["schema"].endswith("v4_2")
    assert fixture["images_generated"] is False
    assert fixture["training_started"] is False
    assert fixture["evaluation_opened"] is False
    assert fixture["split_policy"]["evaluation_pairs_rendered"] == 0


def test_variant_overlap_admission_is_fail_closed() -> None:
    fixture, _ = MODULE.load_fixture(FIXTURE)
    MODULE.admit_variant_measurement(fixture, "cable_rubber", 0.55, 0.0)
    MODULE.admit_variant_measurement(fixture, "adjacent_left", 0.0, 0.0)
    with pytest.raises(RuntimeError, match="outside"):
        MODULE.admit_variant_measurement(fixture, "tool_matte_edge", 0.75, 0.0)
    with pytest.raises(RuntimeError, match="unexpectedly overlaps"):
        MODULE.admit_variant_measurement(fixture, "clear", 0.01, 0.0)
    with pytest.raises(RuntimeError, match="distractor overlaps"):
        MODULE.admit_variant_measurement(fixture, "adjacent_right", 0.0, 0.01)


def test_camera_contract_samples_every_declared_axis_deterministically() -> None:
    fixture, _ = MODULE.load_fixture(FIXTURE)
    scene = next(row for row in fixture["base_scenes"] if row["split"] == "training")

    class Center:
        x = 10.0
        y = 20.0
        z = 30.0

    class Target:
        center = Center()

    first = MODULE.sample_camera_contract(scene, Target(), 82.0, MODULE.random.Random(91))
    second = MODULE.sample_camera_contract(scene, Target(), 82.0, MODULE.random.Random(91))
    assert first == second
    assert any(value != 0.0 for value in first["camera_position_jitter_mm"])
    assert any(value != 0.0 for value in first["camera_rotation_jitter_deg"])
    assert all(
        abs(value) <= limit
        for value, limit in zip(
            first["camera_position_jitter_mm"], scene["camera_pose_jitter_mm"], strict=True
        )
    )
    assert all(
        abs(value) <= limit
        for value, limit in zip(
            first["camera_rotation_jitter_deg"], scene["camera_rotation_jitter_deg"], strict=True
        )
    )
