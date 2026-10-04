from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
AI_ROOT = ROOT / "software/ai"
sys.path.insert(0, str(ROOT / "software/integrations/isaac_sim"))

from residual_obstruction_v5_4_isaac_probe import (  # noqa: E402
    admit_variant_measurement,
    load_fixture,
    obstruction_render_descriptor,
    project_capsule_mask,
    render,
)

FIXTURE = AI_ROOT / "sim/evidence/residual_obstruction_successor_v5_4.json"
REPORT = AI_ROOT / "eval/residual_obstruction_v5_4_renderer_smoke_v1.json"
SCHEMA = AI_ROOT / "schemas/residual_obstruction_v5_4_renderer_smoke_v1.schema.json"


def test_loader_binds_v5_4_and_inherited_v5_contract() -> None:
    fixture, raw = load_fixture(FIXTURE)
    assert raw == FIXTURE.read_bytes()
    assert fixture["schema"] == "tactevra.ai_residual_obstruction_successor_fixture.v5_4"
    assert len(fixture["base_scenes"]) == 24
    assert len(fixture["variants"]) == 12
    assert len(fixture["appearances"]) == 6
    assert fixture["render_contract"]["evaluation_images_generated"] == 0
    assert set(fixture["obstruction_assets"]["training"]).isdisjoint(
        fixture["obstruction_assets"]["development"]
    )


def test_evaluation_is_rejected_before_renderer_initialization(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="only training and development"):
        render(
            ROOT, FIXTURE, tmp_path / "pixels", tmp_path / "status.json",
            "evaluation", 0, 1, 0, 1,
        )
    assert not (tmp_path / "pixels").exists()


def test_coverage_admission_is_bound_to_frozen_variant() -> None:
    fixture, _ = load_fixture(FIXTURE)
    admit_variant_measurement(fixture, "dark_cable_30", 0.30, 0.0)
    with pytest.raises(RuntimeError, match="outside"):
        admit_variant_measurement(fixture, "dark_cable_30", 0.70, 0.0)
    with pytest.raises(RuntimeError, match="unexpectedly overlaps"):
        admit_variant_measurement(fixture, "clear", 0.01, 0.0)


def test_render_descriptor_binds_actual_geometry_material_and_texture() -> None:
    first = obstruction_render_descriptor("training_dark_cable_01", "dark_cable_30", 14.0, 14.0, 0.30)
    second = obstruction_render_descriptor("training_dark_cable_01", "dark_cable_60", 14.0, 14.0, 0.60)
    assert first["geometry"]["primitive"] == "UsdGeom.Cylinder"
    assert first["geometry"]["radius_mm"] != second["geometry"]["radius_mm"]
    assert first["material"]["display_color_rgb"] == [0.025, 0.025, 0.03]
    assert first["texture"]["kind"] == "NONE_PROCEDURAL_SOLID_DISPLAY_COLOR"


def test_analytic_arm_mask_uses_projected_capsules_without_semantic_truth() -> None:
    camera = {
        "camera_position_mm": [0.0, 0.0, 100.0],
        "camera_look_at_mm": [0.0, 0.0, 0.0],
        "camera_up_axis": [0.0, 1.0, 0.0],
    }
    payload, record = project_capsule_mask(camera, [{
        "link": "link2", "start_board_mm": [-10.0, 0.0, 0.0],
        "end_board_mm": [10.0, 0.0, 0.0], "radius_mm": 4.0,
    }], Image, ImageDraw)
    assert payload.startswith(b"\x89PNG")
    assert record["projection_model"] == "ANALYTIC_PINHOLE_FK_CAPSULES_NO_SIMULATOR_MASK"
    assert record["projected_segment_count"] == 1


def test_fixture_tampering_is_rejected(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "evidence"
    fixture_dir.mkdir()
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["hardware_writes"] = 1
    altered = fixture_dir / FIXTURE.name
    altered.write_text(json.dumps(payload), encoding="utf-8")
    (fixture_dir / "residual_obstruction_successor_v5.json").write_bytes(
        (FIXTURE.parent / "residual_obstruction_successor_v5.json").read_bytes()
    )
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        load_fixture(altered)


def test_retained_smoke_is_training_only_and_evaluation_blocked() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(report)
    assert report["metrics"]["observation_count"] == 144
    assert report["metrics"]["reference_count"] == 12
    assert report["campaign_render_authorized"] is True
    assert report["evaluation_render_authorized"] is False
    assert report["descriptor_and_projection_audit"]["render_descriptors_hash_bound"] is True
    assert report["descriptor_and_projection_audit"]["arm_projection_uses_simulator_truth"] is False
    assert report["hardware_writes"] == report["physical_movements"] == 0
