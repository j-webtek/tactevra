from __future__ import annotations

import importlib.util
import json
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    WORKSPACE
    / "software"
    / "integrations"
    / "isaac_sim"
    / "fixed_fixture_practice_corpus.py"
)


def _module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("fixed_fixture_practice_corpus", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixed_fixture_corpus_is_deterministic_labeled_and_zero_authority(tmp_path) -> None:  # type: ignore[no-untyped-def]
    module = _module()
    first = module.generate(WORKSPACE, tmp_path / "first")
    second = module.generate(WORKSPACE, tmp_path / "second")

    assert first["corpus_sha256"] == second["corpus_sha256"]
    assert first["sample_count"] == len(module.POSES) * len(module.VARIANTS) == 16
    assert first["scope"] == "SYNTHETIC_FIXED_FIXTURE_PRACTICE_ONLY"
    assert first["synthetic_images"] is True
    assert first["physical_camera_images"] is False
    assert first["deployment_qualification_claimed"] is False
    assert first["authority"] == {
        "hardware_accessed": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "can_release_physical_gates": False,
    }

    first_samples = first["samples"]
    second_samples = second["samples"]
    assert [sample["image_sha256"] for sample in first_samples] == [
        sample["image_sha256"] for sample in second_samples
    ]
    assert len({sample["image_sha256"] for sample in first_samples}) == 16
    assert all(len(sample["targets"]) == 75 for sample in first_samples)
    assert all(
        {"device", "target_id", "center_board_mm", "safe_polygon_px", "in_frame"}
        <= set(target)
        for sample in first_samples
        for target in sample["targets"]
    )

    occluded = [
        sample for sample in first_samples
        if sample["pixel_transform"]["kind"] == "foreground_arm_tool_proxy"
    ]
    assert len(occluded) == 4
    assert all(sample["pixel_transform"]["occlusion_polygon_px"] for sample in occluded)
    assert any(
        target["synthetically_occluded"]
        for sample in occluded
        for target in sample["targets"]
    )

    disk_manifest = json.loads((tmp_path / "first" / "manifest.json").read_text())
    assert disk_manifest == first
    assert sorted(path.name for path in (tmp_path / "first").glob("*.jpg")) == sorted(
        sample["image_path"] for sample in first_samples
    )


def test_unknown_pixel_variant_fails_closed() -> None:
    module = _module()
    from PIL import Image

    image = Image.new("RGB", (64, 48), "white")
    try:
        module.apply_variant(image, "undeclared")
    except ValueError as exc:
        assert "unknown practice variant" in str(exc)
    else:
        raise AssertionError("undeclared transformation was accepted")
