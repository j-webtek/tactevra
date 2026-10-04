from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from PIL import Image


WORKSPACE = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    WORKSPACE / "software" / "integrations" / "isaac_sim"
    / "fixed_overview_segmentation_corpus.py"
)


def _module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("fixed_overview_segmentation_corpus", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixed_overview_corpus_is_deterministic_pose_bound_and_zero_authority(tmp_path) -> None:  # type: ignore[no-untyped-def]
    module = _module()
    first = module.generate(WORKSPACE, tmp_path / "first")
    second = module.generate(WORKSPACE, tmp_path / "second")

    assert first["corpus_sha256"] == second["corpus_sha256"]
    assert first["sample_count"] == len(module.POSES) * len(module.VARIANTS) == 15
    assert first["camera_fixed_across_samples"] is True
    assert first["board_fixed_across_samples"] is True
    assert first["robot_obstruction_pose_bound_to_urdf_fk"] is True
    assert first["robot_geometry"] == "PROJECTED_LINK_CAPSULE_PROXY_NOT_CAD_MESH"
    assert first["deployment_qualification_claimed"] is False
    assert first["authority"] == {
        "hardware_accessed": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "can_release_physical_gates": False,
    }

    assert [sample["crop_jpeg_sha256"] for sample in first["samples"]] == [
        sample["crop_jpeg_sha256"] for sample in second["samples"]
    ]
    assert len({sample["crop_jpeg_sha256"] for sample in first["samples"]}) == 15
    assert len({sample["image_atlas_sha256"] for sample in first["samples"]}) == 3
    layers = first["pose_layers"]
    assert len(layers) == 3
    assert len({layer["robot_label_sha256"] for layer in layers}) == 3
    assert len({layer["robot_depth_sha256"] for layer in layers}) == 3
    assert all(len(layer["targets"]) == 75 for layer in layers)
    assert all(len(layer["segments"]) == 8 for layer in layers)
    assert all(
        any(target["safe_region_robot_overlap_fraction"] > 0.0 for target in layer["targets"])
        for layer in layers
    )

    for layer in layers:
        label = Image.open(tmp_path / "first" / layer["robot_label_path"])
        depth = Image.open(tmp_path / "first" / layer["robot_depth_path"])
        assert label.mode == "L"
        assert depth.mode in {"I;16", "I"}
        assert label.getbbox() is not None
        assert depth.getbbox() is not None
        assert max(label.getdata()) == max(layer["link_label_id_by_name"].values())
        assert min(value for value in depth.getdata() if value) > 0

    for pose_id in module.POSES:
        pose_samples = [sample for sample in first["samples"] if sample["pose_id"] == pose_id]
        assert len({sample["image_atlas_path"] for sample in pose_samples}) == 1
        atlas = Image.open(tmp_path / "first" / pose_samples[0]["image_atlas_path"])
        assert atlas.size == (1920 * 3, 1080 * 2)
        for sample in pose_samples:
            assert atlas.crop(sample["atlas_crop_box_px"]).size == (1920, 1080)

    disk = json.loads((tmp_path / "first" / "manifest.json").read_text())
    assert disk == first


def test_unknown_lighting_variant_fails_closed() -> None:
    module = _module()
    image = Image.new("RGB", (64, 48), "white")
    try:
        module.apply_lighting(image, "undeclared")
    except ValueError as exc:
        assert "unknown lighting variant" in str(exc)
    else:
        raise AssertionError("undeclared lighting transformation was accepted")
