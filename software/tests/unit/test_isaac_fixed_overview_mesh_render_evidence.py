from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw


WORKSPACE = Path(__file__).resolve().parents[3]
EVIDENCE = (
    WORKSPACE / "software" / "integrations" / "isaac_sim" / "evidence"
    / "fixed_overview_official_mesh_v1"
)
BUILDER_PATH = (
    WORKSPACE / "software" / "ai" / "train" / "build_official_mesh_occlusion_data.py"
)
RENDERER_PATH = (
    WORKSPACE / "software" / "integrations" / "isaac_sim"
    / "isaac_fixed_overview_mesh_render_probe.py"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _builder():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("build_official_mesh_occlusion_data", BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _renderer():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("isaac_fixed_overview_mesh_render_probe", RENDERER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_official_mesh_render_receipt_is_bound_and_zero_authority() -> None:
    manifest_path = EVIDENCE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    claimed_receipt_sha = manifest.pop("receipt_sha256")
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    assert _sha256(canonical) == claimed_receipt_sha
    assert manifest["schema"] == "tactevra.isaac_fixed_overview_mesh_render.v1"
    assert manifest["evidence_class"] == "OFFICIAL_VISUAL_MESH_PERCEPTION_COMPARISON_ONLY"
    assert manifest["visual_meshes_used_for_collision"] is False
    assert manifest["physics_steps"] == 0
    assert manifest["hardware_access"] is False
    assert manifest["hardware_writes"] == 0
    assert manifest["physical_movements"] == 0
    assert manifest["physical_authority"] is False
    assert manifest["result_status"] == "PASS_WITH_BLOCKERS"
    assert manifest["result_summary"]["minimum_mask_iou"] == min(
        row["mask_iou"] for row in manifest["pose_results"]
    )

    arrays = {}
    for name, artifact in manifest["artifact_atlases"].items():
        path = EVIDENCE / artifact["path"]
        assert _sha256(path.read_bytes()) == artifact["sha256"]
        dtype = np.uint16 if name == "robot_depth_mm" else None
        arrays[name] = np.asarray(Image.open(path), dtype=dtype)
        assert arrays[name].shape[:2] == (3240, 1920)

    results = manifest["pose_results"]
    assert [row["pose_id"] for row in results] == ["ready", "hover_t", "hover_e"]
    assert len({row["robot_mask_crop_pixel_sha256"] for row in results}) == 3
    expected_occlusion_counts = {
        "ready": (1, 5),
        "hover_t": (14, 17),
        "hover_e": (14, 18),
    }
    target_order = None
    for row in results:
        left, top, right, bottom = row["atlas_crop_px"]
        assert [left, right - left, bottom - top] == [0, 1920, 1080]
        slices = {
            "rgb": arrays["rgb"][top:bottom, left:right],
            "robot_mask": arrays["robot_mask"][top:bottom, left:right],
            "robot_depth": arrays["robot_depth_mm"][top:bottom, left:right],
        }
        assert _sha256(slices["rgb"].tobytes()) == row["rgb_crop_pixel_sha256"]
        assert _sha256(slices["robot_mask"].tobytes()) == row["robot_mask_crop_pixel_sha256"]
        assert _sha256(slices["robot_depth"].tobytes()) == row["robot_depth_crop_pixel_sha256"]
        assert 0.0 < row["mask_iou"] < 1.0
        assert row["official_mesh_outside_capsule_pixels"] > 0
        assert row["capsule_outside_official_mesh_pixels"] > 0
        targets = row["targets"]
        assert len(targets) == 75
        current_order = [(target["device"], target["target_id"]) for target in targets]
        target_order = current_order if target_order is None else target_order
        assert current_order == target_order
        assert all(target["in_frame"] is True for target in targets)
        center_count = sum(target["center_occluded_by_official_mesh"] for target in targets)
        overlap_count = sum(
            target["safe_region_official_mesh_overlap_fraction"] > 0.0
            for target in targets
        )
        assert (center_count, overlap_count) == expected_occlusion_counts[row["pose_id"]]


def test_target_occlusion_diagnostic_detects_overlap_and_reports_clearance() -> None:
    renderer = _renderer()
    target = {
        "center_px": [105.0, 105.0],
        "safe_polygon_px": [
            [100.0, 100.0], [110.0, 100.0],
            [110.0, 110.0], [100.0, 110.0],
        ],
    }
    clear_mask = np.zeros((1080, 1920), dtype=bool)
    clear_mask[100:111, 120] = True
    clear = renderer._target_occlusion_diagnostic(
        target, clear_mask, Image, ImageDraw, np,
    )
    assert clear["center_occluded"] is False
    assert clear["safe_region_overlap_px"] == 0
    assert clear["safe_region_overlap_fraction"] == 0.0
    assert clear["nominal_clearance_px"] == 10.0

    positive_control = clear_mask.copy()
    positive_control[100:111, 100:111] = True
    blocked = renderer._target_occlusion_diagnostic(
        target, positive_control, Image, ImageDraw, np,
    )
    assert blocked["center_occluded"] is True
    assert blocked["safe_region_overlap_fraction"] == 1.0
    assert blocked["nominal_clearance_px"] == 0.0


def test_candidate_search_projection_and_capsule_clearance_are_deterministic() -> None:
    renderer = _renderer()
    center = renderer._project_board_point(
        (0.0, 0.0, 0.0), (0.0, 0.0, 500.0),
        (0.0, 0.0, 0.0), (0.0, 1.0, 0.0),
    )
    assert center == pytest.approx((960.0, 540.0, 500.0))
    polygon = [[100.0, 100.0], [110.0, 100.0],
               [110.0, 110.0], [100.0, 110.0]]
    assert renderer._capsule_polygon_clearance_px(
        (80.0, 105.0), (90.0, 105.0), 2.0, polygon,
    ) == pytest.approx(8.0)
    assert renderer._capsule_polygon_clearance_px(
        (90.0, 105.0), (120.0, 105.0), 2.0, polygon,
    ) == pytest.approx(-2.0)


def test_native_nadir_height_projection_and_physical_resolution_are_explicit() -> None:
    renderer = _renderer()
    intrinsics = renderer._native_sensor_intrinsics(5472, 3648, 2.4, 16.0)
    assert intrinsics == pytest.approx({
        "fx_px": 6666.666666666667,
        "fy_px": 6666.666666666667,
        "cx_px": 2736.0,
        "cy_px": 1824.0,
        "sensor_mode_width_mm": 13.1328,
        "sensor_mode_height_mm": 8.7552,
    })
    center = renderer._project_nadir_board_point(
        (305.0, 228.5, 0.0), (305.0, 228.5), 800.0, intrinsics,
    )
    assert center == pytest.approx((2736.0, 1824.0, 800.0))
    right = renderer._project_nadir_board_point(
        (385.0, 228.5, 0.0), (305.0, 228.5), 800.0, intrinsics,
    )
    assert right == pytest.approx((3402.666666666667, 1824.0, 800.0))
    assert renderer._ground_sample_distance_mm_per_px(800.0, 2.4, 16.0) \
        == pytest.approx(0.12)


def test_nadir_projection_applies_brown_conrady_and_thin_lens_is_bounded() -> None:
    renderer = _renderer()
    intrinsics = renderer._native_sensor_intrinsics(5472, 3648, 2.4, 16.0)
    ideal = renderer._project_nadir_board_point(
        (505.0, 328.5, 21.0), (305.0, 228.5), 800.0, intrinsics,
    )
    stressed = renderer._project_nadir_board_point(
        (505.0, 328.5, 21.0), (305.0, 228.5), 800.0, intrinsics,
        {"k1": -0.04, "k2": 0.006, "p1": 0.0003,
         "p2": -0.0002, "k3": -0.0005},
    )
    assert ideal is not None and stressed is not None
    assert stressed[:2] != pytest.approx(ideal[:2])
    phone_blur = renderer._thin_lens_blur_diameter_px(
        800.0 - 11.9, 800.0 - 21.0, 16.0, 4.0, 2.4,
    )
    assert phone_blur > 0.0
    assert renderer._thin_lens_blur_diameter_px(
        779.0, 779.0, 16.0, 4.0, 2.4,
    ) == pytest.approx(0.0)


def test_fixed_physical_crop_preserves_extent_and_reports_height_support() -> None:
    renderer = _renderer()
    intrinsics = renderer._native_sensor_intrinsics(5472, 3648, 2.4, 16.0)
    near = renderer._fixed_physical_crop_box(
        (305.0, 228.5, 21.0), (48.0, 48.0), (305.0, 228.5),
        700.0, intrinsics,
    )
    far = renderer._fixed_physical_crop_box(
        (305.0, 228.5, 21.0), (48.0, 48.0), (305.0, 228.5),
        1000.0, intrinsics,
    )
    assert near["in_frame"] is far["in_frame"] is True
    assert near["physical_extent_xy_mm"] == far["physical_extent_xy_mm"] == [48.0, 48.0]
    assert near["native_support_width_px"] == pytest.approx(471.281296023564)
    assert far["native_support_width_px"] == pytest.approx(326.864147769153)
    assert near["native_support_width_px"] > far["native_support_width_px"]

    source = Image.fromarray(np.tile(np.arange(256, dtype=np.uint8), (256, 1)))
    synthetic_crop = {
        "in_frame": True,
        "native_box_ltrb_px": [32.5, 40.5, 224.5, 232.5],
    }
    resized = renderer._resample_fixed_physical_crop(
        source, synthetic_crop, (96, 96), Image,
    )
    assert resized.size == (96, 96)


def test_fixed_physical_crop_rejects_invalid_or_clipped_requests() -> None:
    renderer = _renderer()
    intrinsics = renderer._native_sensor_intrinsics(5472, 3648, 2.4, 16.0)
    with pytest.raises(ValueError, match="extents"):
        renderer._fixed_physical_crop_box(
            (305.0, 228.5, 21.0), (0.0, 48.0), (305.0, 228.5),
            700.0, intrinsics,
        )
    clipped = renderer._fixed_physical_crop_box(
        (0.0, 0.0, 21.0), (200.0, 200.0), (305.0, 228.5),
        700.0, intrinsics,
    )
    assert clipped["in_frame"] is False
    with pytest.raises(ValueError, match="not fully in frame"):
        renderer._resample_fixed_physical_crop(
            Image.new("RGB", (5472, 3648)), clipped, (96, 96), Image,
        )


def test_nadir_projection_explicitly_binds_isaac_vertical_orientation() -> None:
    renderer = _renderer()
    intrinsics = renderer._native_sensor_intrinsics(5472, 3648, 2.4, 16.0)
    analytic = renderer._project_nadir_board_point(
        (305.0, 248.5, 0.0), (305.0, 228.5), 800.0, intrinsics,
    )
    isaac = renderer._project_nadir_board_point(
        (305.0, 248.5, 0.0), (305.0, 228.5), 800.0, intrinsics,
        board_y_to_image_v_sign=-1,
    )
    assert analytic is not None and isaac is not None
    assert analytic[0] == pytest.approx(isaac[0])
    assert analytic[1] > intrinsics["cy_px"]
    assert isaac[1] < intrinsics["cy_px"]
    with pytest.raises(ValueError, match="sign"):
        renderer._project_nadir_board_point(
            (305.0, 248.5, 0.0), (305.0, 228.5), 800.0, intrinsics,
            board_y_to_image_v_sign=0,
        )


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ((0, 3648, 2.4, 16.0), "dimensions"),
        ((5472, 3648, 0.0, 16.0), "pixel pitch"),
    ],
)
def test_native_nadir_helpers_reject_invalid_geometry(
    arguments: tuple[int, int, float, float], message: str,
) -> None:
    renderer = _renderer()
    with pytest.raises(ValueError, match=message):
        renderer._native_sensor_intrinsics(*arguments)


def test_official_mesh_occlusion_builder_has_disjoint_groups_and_zero_authority(
    tmp_path: Path,
) -> None:
    module = _builder()
    first = module.build(EVIDENCE / "manifest.json", tmp_path / "first")
    second = module.build(EVIDENCE / "manifest.json", tmp_path / "second")

    assert first == second
    assert first["scope"] == "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION"
    assert first["pose_groups_disjoint"] is True
    assert first["lighting_groups_disjoint"] is True
    assert first["splits"]["train"] == {
        "path": "train.jsonl",
        "sha256": "140636df91e1884ca28d5f8cb9fb3662946a0ab8633f452098de4e87c3f8f107",
        "count": 450,
        "abstain_count": 51,
        "visible_count": 399,
    }
    assert first["splits"]["evaluation"] == {
        "path": "evaluation.jsonl",
        "sha256": "c00b3c3ded761af0c57e4211441d253bfa9848623b658be02dd114a2b40d70ca",
        "count": 225,
        "abstain_count": 45,
        "visible_count": 180,
    }
    assert first["authority"] == {
        "hardware_accessed": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "can_release_physical_gates": False,
    }
    assert len(first["images"]) == 9
    assert len({record["sha256"] for record in first["images"]}) == 9
    assert all(
        (tmp_path / "first" / record["path"]).is_file()
        for record in first["images"]
    )
    first_score = module.train_baseline(tmp_path / "first", tmp_path / "run-first")
    second_score = module.train_baseline(tmp_path / "second", tmp_path / "run-second")
    assert first_score == second_score
    assert first_score["promotion_status"] == "BLOCKED_SYNTHETIC_ONLY"
    assert first_score["train"]["confusion"] == {
        "true_abstain": 49,
        "true_visible": 398,
        "false_abstain": 1,
        "missed_abstain": 2,
    }
    assert first_score["evaluation"]["confusion"] == {
        "true_abstain": 32,
        "true_visible": 118,
        "false_abstain": 62,
        "missed_abstain": 13,
    }
    assert first_score["evaluation"]["balanced_accuracy"] < 0.70
    assert first_score["evaluation"]["expected_calibration_error_10_bin"] > 0.30
    assert first_score["hardware_writes"] == 0
    assert first_score["physical_movements"] == 0


def test_official_mesh_occlusion_builder_rejects_altered_source(tmp_path: Path) -> None:
    module = _builder()
    altered_dir = tmp_path / "altered"
    altered_dir.mkdir()
    source = json.loads((EVIDENCE / "manifest.json").read_text(encoding="utf-8"))
    source["target_catalog_sha256"] = "0" * 64
    (altered_dir / "manifest.json").write_text(json.dumps(source), encoding="utf-8")
    try:
        module.build(altered_dir / "manifest.json", tmp_path / "output")
    except ValueError as exc:
        assert "receipt hash mismatch" in str(exc)
    else:
        raise AssertionError("altered source was accepted")


def test_expanded_occlusion_policy_preserves_reserved_evaluation_groups() -> None:
    module = _builder()
    pose_groups = {
        "training": ["ready", "hover_t", "hover_e"],
        "development": ["hover_h", "contact_h"],
        "evaluation": ["hover_1", "contact_1", "hover_period", "contact_period"],
    }
    source = {
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v2",
        "pose_groups": pose_groups,
        "pose_results": [
            {"pose_id": pose_id, "pose_group": group}
            for group, pose_ids in pose_groups.items()
            for pose_id in pose_ids
        ],
    }

    schema, policy = module._split_policy(source)

    assert schema == "rocell.ai_official_mesh_occlusion_data.v2"
    assert policy == {
        "train": {
            "poses": ("ready", "hover_t", "hover_e"),
            "lighting": ("nominal", "dim", "bright"),
        },
        "development": {
            "poses": ("hover_h", "contact_h"),
            "lighting": ("warm", "glare", "blur"),
        },
        "evaluation": {
            "poses": ("hover_1", "contact_1", "hover_period", "contact_period"),
            "lighting": ("cool", "side_shadow", "defocus"),
        },
    }
    assert not (set(policy["train"]["poses"]) & set(policy["development"]["poses"]))
    assert not (set(policy["train"]["lighting"]) & set(policy["evaluation"]["lighting"]))


def test_expanded_lighting_families_are_deterministic_and_distinct() -> None:
    module = _builder()
    pixels = np.arange(32 * 32 * 3, dtype=np.uint8).reshape(32, 32, 3)
    source = Image.fromarray(pixels, mode="RGB")

    first = [np.asarray(module._lighting(source, name)) for name in module.EXPANDED_LIGHTING["evaluation"]]
    second = [np.asarray(module._lighting(source, name)) for name in module.EXPANDED_LIGHTING["evaluation"]]

    assert all(np.array_equal(left, right) for left, right in zip(first, second, strict=True))
    assert len({_sha256(value.tobytes()) for value in first}) == 3


def test_candidate_threshold_selection_prioritizes_missed_abstention_bound() -> None:
    module = _builder()
    labels = np.asarray([1.0] * 20 + [0.0] * 20)
    probabilities = np.asarray(
        [0.90] * 18 + [0.20, 0.10] + [0.40] * 5 + [0.15] * 15
    )

    threshold = module._select_threshold(labels, probabilities)

    predicted = probabilities >= threshold
    missed = int(np.count_nonzero(~predicted & labels.astype(bool)))
    assert threshold == 0.2
    assert missed / int(labels.sum()) <= 0.05


def test_chromatic_edge_features_are_deterministic_and_brightness_stable(tmp_path: Path) -> None:
    module = _builder()
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    base = np.tile(np.arange(64, 192, 8, dtype=np.uint8), (16, 1))
    rgb = np.stack((base, np.flip(base, axis=1), base), axis=2)
    bright = np.clip(rgb.astype(np.int16) + 40, 0, 255).astype(np.uint8)
    Image.fromarray(rgb).save(image_dir / "base.png")
    Image.fromarray(bright).save(image_dir / "bright.png")
    rows = [
        {
            "image_path": f"images/{name}.png",
            "image_sha256": _sha256((image_dir / f"{name}.png").read_bytes()),
            "safe_polygon_px": [[0, 0], [15, 0], [15, 15], [0, 15]],
            "decision": "target_visible",
        }
        for name in ("base", "bright")
    ]

    first, _ = module._features(tmp_path, rows, "chromatic_gray_edges")
    second, _ = module._features(tmp_path, rows, "chromatic_gray_edges")

    assert np.array_equal(first, second)
    assert first.shape == (2, 1536)
    assert np.mean(np.abs(first[0] - first[1])) < 0.08


def test_transit_pose_groups_are_predeclared_disjoint_and_schedule_bound() -> None:
    module = _renderer()
    groups = module.POSE_GROUPS
    flattened = [pose for poses in groups.values() for pose in poses]

    assert set(groups) == {"training", "development", "evaluation"}
    assert len(flattened) == len(set(flattened)) == 45
    assert set(module.REFERENCE_POSES) == {"ready", "hover_t", "hover_e"}
    assert set(module.SCHEDULE_POSE_SEQUENCES) == set(flattened) - set(module.REFERENCE_POSES)
    assert set(module.SCHEDULE_POSE_SEQUENCES.values()) == {
        2, 4, 6, 8, 10, 13, 17, 20, 26, 34, 35, 44, 52, 60, 63, 64, 72,
        11, 15, 19, 23, 27, 31, 84, 96, 103, 104, 112, 113, 114, 115,
        117, 118, 119, 120, 121, 122, 123, 124, 126, 128, 130,
    }
    assert set(groups["development"]) == {
        "targetaware_dev_outbound_11", "targetaware_dev_outbound_15",
        "targetaware_dev_outbound_19", "targetaware_dev_return_113",
        "targetaware_dev_return_117", "targetaware_dev_return_121",
    }
    assert set(groups["evaluation"]) == {
        "targetaware_eval_outbound_23", "targetaware_eval_outbound_27",
        "targetaware_eval_outbound_31", "targetaware_eval_return_115",
        "targetaware_eval_return_119", "targetaware_eval_return_123",
    }
    assert not (set(groups["development"]) & set(groups["evaluation"]))


def test_mask_perturbation_poses_are_fresh_development_only() -> None:
    module = _renderer()
    groups = module.PERTURBATION_POSE_GROUPS
    sequences = module.PERTURBATION_SCHEDULE_POSE_SEQUENCES

    assert set(groups) == {"training", "development", "evaluation"}
    assert groups["training"] == groups["evaluation"] == ()
    assert set(groups["development"]) == set(sequences)
    assert len(sequences) == len(set(sequences.values())) == 6
    assert not (set(sequences.values()) & set(module.SCHEDULE_POSE_SEQUENCES.values()))


def test_policy_evaluation_poses_are_fresh_evaluation_only() -> None:
    module = _renderer()
    groups = module.POLICY_EVALUATION_POSE_GROUPS
    sequences = module.POLICY_EVALUATION_SCHEDULE_POSE_SEQUENCES

    assert set(groups) == {"training", "development", "evaluation"}
    assert groups["training"] == groups["development"] == ()
    assert groups["evaluation"] == tuple(sequences)
    assert set(sequences.values()) == {40, 48, 56, 76, 88, 100}
    prior = set(module.SCHEDULE_POSE_SEQUENCES.values()) | set(
        module.PERTURBATION_SCHEDULE_POSE_SEQUENCES.values()
    )
    assert not (set(sequences.values()) & prior)


def test_hard_negative_poses_are_fresh_development_only() -> None:
    module = _renderer()
    groups = module.HARD_NEGATIVE_POSE_GROUPS
    sequences = module.HARD_NEGATIVE_SCHEDULE_POSE_SEQUENCES

    assert set(groups) == {"training", "development", "evaluation"}
    assert groups["training"] == groups["evaluation"] == ()
    assert groups["development"] == tuple(sequences)
    assert set(sequences.values()) == {42, 50, 58, 78, 90, 98}
    prior = (
        set(module.SCHEDULE_POSE_SEQUENCES.values())
        | set(module.PERTURBATION_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.POLICY_EVALUATION_SCHEDULE_POSE_SEQUENCES.values())
    )
    assert not (set(sequences.values()) & prior)


def test_target_identity_training_poses_are_fresh_training_only() -> None:
    module = _renderer()
    groups = module.TARGET_IDENTITY_TRAINING_POSE_GROUPS
    sequences = module.TARGET_IDENTITY_TRAINING_SCHEDULE_POSE_SEQUENCES

    assert set(groups) == {"training", "development", "evaluation"}
    assert groups["development"] == groups["evaluation"] == ()
    assert groups["training"] == tuple(sequences)
    assert set(sequences.values()) == {
        41, 43, 45, 47, 49, 51, 77, 79, 81, 83, 85, 87,
    }
    prior = (
        set(module.SCHEDULE_POSE_SEQUENCES.values())
        | set(module.PERTURBATION_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.POLICY_EVALUATION_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.HARD_NEGATIVE_SCHEDULE_POSE_SEQUENCES.values())
    )
    assert not (set(sequences.values()) & prior)


def test_fusion_evaluation_poses_are_fresh_evaluation_only() -> None:
    module = _renderer()
    groups = module.FUSION_EVALUATION_POSE_GROUPS
    sequences = module.FUSION_EVALUATION_SCHEDULE_POSE_SEQUENCES

    assert set(groups) == {"training", "development", "evaluation"}
    assert groups["training"] == groups["development"] == ()
    assert groups["evaluation"] == tuple(sequences)
    assert set(sequences.values()) == {46, 54, 62, 80, 92, 102}
    prior = (
        set(module.SCHEDULE_POSE_SEQUENCES.values())
        | set(module.PERTURBATION_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.POLICY_EVALUATION_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.HARD_NEGATIVE_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.TARGET_IDENTITY_TRAINING_SCHEDULE_POSE_SEQUENCES.values())
    )
    assert not (set(sequences.values()) & prior)


def test_occlusion_recall_poses_are_fresh_train_and_development_only() -> None:
    module = _renderer()
    groups = module.OCCLUSION_RECALL_POSE_GROUPS
    sequences = module.OCCLUSION_RECALL_SCHEDULE_POSE_SEQUENCES

    assert set(groups) == {"training", "development", "evaluation"}
    assert groups["evaluation"] == ()
    assert len(groups["training"]) == 12
    assert len(groups["development"]) == 6
    assert set(groups["training"]).isdisjoint(groups["development"])
    assert set(sequences.values()) == {
        30, 32, 36, 38, 53, 55, 57, 59, 61,
        66, 67, 68, 69, 70, 71, 106, 107, 108,
    }
    prior = (
        set(module.SCHEDULE_POSE_SEQUENCES.values())
        | set(module.PERTURBATION_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.POLICY_EVALUATION_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.HARD_NEGATIVE_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.TARGET_IDENTITY_TRAINING_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.FUSION_EVALUATION_SCHEDULE_POSE_SEQUENCES.values())
    )
    assert not (set(sequences.values()) & prior)


def test_recall_evaluation_poses_are_fresh_evaluation_only() -> None:
    module = _renderer()
    groups = module.RECALL_EVALUATION_POSE_GROUPS
    sequences = module.RECALL_EVALUATION_SCHEDULE_POSE_SEQUENCES

    assert groups["training"] == groups["development"] == ()
    assert len(groups["evaluation"]) == 6
    assert set(sequences.values()) == {73, 82, 91, 99, 105, 110}
    prior = (
        set(module.SCHEDULE_POSE_SEQUENCES.values())
        | set(module.PERTURBATION_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.POLICY_EVALUATION_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.HARD_NEGATIVE_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.TARGET_IDENTITY_TRAINING_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.FUSION_EVALUATION_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.OCCLUSION_RECALL_SCHEDULE_POSE_SEQUENCES.values())
    )
    assert not (set(sequences.values()) & prior)


def test_specificity_rebalance_poses_are_fresh_train_and_development_only() -> None:
    module = _renderer()
    groups = module.SPECIFICITY_REBALANCE_POSE_GROUPS
    sequences = module.SPECIFICITY_REBALANCE_SCHEDULE_POSE_SEQUENCES

    assert groups["evaluation"] == ()
    assert len(groups["training"]) == 8
    assert len(groups["development"]) == 5
    assert set(groups["training"]).isdisjoint(groups["development"])
    assert set(sequences.values()) == {
        33, 65, 74, 75, 86, 89, 93, 94, 95, 97, 101, 109, 111,
    }
    prior = (
        set(module.SCHEDULE_POSE_SEQUENCES.values())
        | set(module.PERTURBATION_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.POLICY_EVALUATION_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.HARD_NEGATIVE_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.TARGET_IDENTITY_TRAINING_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.FUSION_EVALUATION_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.OCCLUSION_RECALL_SCHEDULE_POSE_SEQUENCES.values())
        | set(module.RECALL_EVALUATION_SCHEDULE_POSE_SEQUENCES.values())
    )
    assert not (set(sequences.values()) & prior)


def test_rebalance_evaluation_poses_are_static_fresh_and_evaluation_only() -> None:
    module = _renderer()
    groups = module.REBALANCE_EVALUATION_POSE_GROUPS
    sequences = module.REBALANCE_EVALUATION_SCHEDULE_POSE_SEQUENCES

    assert groups["training"] == groups["development"] == ()
    assert tuple(sequences) == groups["evaluation"]
    assert set(sequences.values()) == {1001, 1002, 1003, 1004, 1005, 1006}
    assert min(sequences.values()) > 132
    assert module.EXPECTED_STATIC_EVALUATION_POSE_FILE_SHA256 == (
        "638e17a18feb79aa15864078ff80df37e69ebe6889710de08d98ed709013fb69"
    )


def test_rebalance_evaluation_policy_and_lighting_are_fresh() -> None:
    builder = _builder()
    renderer = _renderer()
    source = {
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v14",
        "pose_groups": {
            name: list(poses)
            for name, poses in renderer.REBALANCE_EVALUATION_POSE_GROUPS.items()
        },
        "pose_results": [
            {"pose_id": pose_id, "pose_group": group}
            for group, pose_ids in renderer.REBALANCE_EVALUATION_POSE_GROUPS.items()
            for pose_id in pose_ids
        ],
    }

    schema, policy = builder._split_policy(source)
    assert schema == "rocell.ai_official_mesh_occlusion_data.v14"


    assert policy["train"]["poses"] == policy["development"]["poses"] == ()
    assert policy["evaluation"]["poses"] == tuple(
        renderer.REBALANCE_EVALUATION_POSE_GROUPS["evaluation"]
    )
    assert policy["evaluation"]["lighting"] == (
        "neutral_edge_soft", "amber_lower_falloff", "cross_smear_cool",
    )
    all_prior = {
        name
        for value in vars(builder).values()
        if isinstance(value, dict) and value is not builder.REBALANCE_EVALUATION_LIGHTING
        for split in value.values()
        if isinstance(split, tuple)
        for name in split
    }
    assert not (set(policy["evaluation"]["lighting"]) & all_prior)

    pixels = np.arange(48 * 48 * 3, dtype=np.uint8).reshape(48, 48, 3)
    image = Image.fromarray(pixels, mode="RGB")
    first = [
        np.asarray(builder._lighting(image, name))
        for name in policy["evaluation"]["lighting"]
    ]
    second = [
        np.asarray(builder._lighting(image, name))
        for name in policy["evaluation"]["lighting"]
    ]
    assert all(
        np.array_equal(left, right)
        for left, right in zip(first, second, strict=True)
    )
    assert len({_sha256(value.tobytes()) for value in first}) == 3


def test_pose_diverse_campaign_is_frozen_train_development_only() -> None:
    module = _renderer()
    fixture_path = (
        WORKSPACE / "software" / "ai" / "sim" / "evidence"
        / "pose_diverse_training_development_v1.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert _sha256(fixture_path.read_bytes()) \
        == module.EXPECTED_POSE_DIVERSE_TRAINING_FILE_SHA256
    assert fixture["schema"] == "tactevra.ai_pose_diverse_training_fixture.v1"
    assert fixture["sample_count"] == 96
    assert fixture["split_counts"] == {"training": 72, "development": 24}
    assert fixture["controller_commands"] == []
    assert fixture["hardware_writes"] == fixture["physical_movements"] == 0
    assert fixture["physical_authority"] is False
    assert len({row["pose_id"] for row in fixture["samples"]}) == 96
    assert {row["split"] for row in fixture["samples"]} == {
        "training", "development",
    }
    source = RENDERER_PATH.read_text(encoding="utf-8")
    assert '"pose-diverse-training-v15"' in source
    assert '"tactevra.isaac_fixed_overview_mesh_render.v15"' in source


def test_grouped_neighborhood_campaign_is_frozen_train_development_only() -> None:
    module = _renderer()
    fixture_path = (
        WORKSPACE / "software" / "ai" / "sim" / "evidence"
        / "grouped_neighborhood_training_development_v1.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert _sha256(fixture_path.read_bytes()) \
        == module.EXPECTED_GROUPED_NEIGHBORHOOD_TRAINING_FILE_SHA256
    assert fixture["sample_count"] == 320
    assert fixture["split_counts"] == {"training": 256, "development": 64}
    assert fixture["controller_commands"] == []
    assert fixture["hardware_writes"] == fixture["physical_movements"] == 0
    source = RENDERER_PATH.read_text(encoding="utf-8")
    assert '"grouped-neighborhood-training-v16"' in source
    assert '"tactevra.isaac_fixed_overview_mesh_render.v16"' in source


def test_large_render_campaign_uses_bounded_tiled_atlas() -> None:
    module = _renderer()
    columns, rows, boxes = module._atlas_layout(module.ATLAS_CHUNK_SIZE)
    assert (columns, rows) == (1, 16)
    assert len(boxes) == 16
    assert boxes[0] == (0, 0, module.WIDTH, module.HEIGHT)
    assert boxes[1] == (0, module.HEIGHT, module.WIDTH, 2 * module.HEIGHT)
    assert columns * module.WIDTH <= module.MAX_IMAGE_DIMENSION
    assert rows * module.HEIGHT <= module.MAX_IMAGE_DIMENSION
    assert module._atlas_layout(3)[:2] == (1, 3)
    with pytest.raises(ValueError, match="at least one"):
        module._atlas_layout(0)


def test_pose_diverse_split_lighting_and_cluster_bootstrap_are_deterministic() -> None:
    module = _builder()
    source = {
        "schema": module.SOURCE_SCHEMA_V15,
        "pose_groups": {
            "training": ["train-a"],
            "development": ["dev-a"],
            "evaluation": [],
        },
        "pose_results": [
            {"pose_id": "train-a", "pose_group": "training"},
            {"pose_id": "dev-a", "pose_group": "development"},
        ],
    }
    schema, policy = module._split_policy(source)
    assert schema == module.SCHEMA_V15
    assert policy["train"]["lighting"] == module.POSE_DIVERSE_LIGHTING["train"]
    assert policy["development"]["lighting"] \
        == module.POSE_DIVERSE_LIGHTING["development"]
    assert set(policy["train"]["lighting"]).isdisjoint(
        module.REBALANCE_EVALUATION_LIGHTING["evaluation"]
    )
    image = Image.new("RGB", (64, 48), (120, 100, 80))
    transformed = [
        module._lighting(image, variant)
        for variants in module.POSE_DIVERSE_LIGHTING.values()
        for variant in variants
    ]
    assert all(value.size == image.size for value in transformed)

    rows = [
        {"pose_id": f"pose-{pose}", "id": f"{pose}-{index}"}
        for pose in range(4) for index in range(4)
    ]
    labels = np.asarray([0.0, 0.0, 1.0, 1.0] * 4)
    probabilities = np.asarray([0.1, 0.2, 0.8, 0.9] * 4)
    offsets = [
        ({"x_mm": 0.0, "y_mm": 0.0, "x_px": 0.0, "y_px": 0.0}, probabilities),
    ]
    first = module._pose_cluster_bootstrap_bounds(
        rows, labels, offsets, threshold=0.5, bound_mm=0.0,
    )
    second = module._pose_cluster_bootstrap_bounds(
        rows, labels, offsets, threshold=0.5, bound_mm=0.0,
    )
    assert first == second
    assert first["pose_count"] == 4
    assert first["maximum_missed_abstain_upper_95"] == 0.0
    assert first["maximum_visible_false_abstain_upper_95"] == 0.0


def test_grouped_neighborhood_split_and_lighting_are_fresh_and_deterministic() -> None:
    module = _builder()
    source = {
        "schema": module.SOURCE_SCHEMA_V16,
        "pose_groups": {
            "training": ["train-a"], "development": ["dev-a"], "evaluation": [],
        },
        "pose_results": [
            {"pose_id": "train-a", "pose_group": "training"},
            {"pose_id": "dev-a", "pose_group": "development"},
        ],
    }
    schema, policy = module._split_policy(source)
    assert schema == module.SCHEMA_V16
    assert policy["train"]["lighting"] == module.GROUPED_NEIGHBORHOOD_LIGHTING["train"]
    assert policy["development"]["lighting"] \
        == module.GROUPED_NEIGHBORHOOD_LIGHTING["development"]
    assert not set(sum(module.GROUPED_NEIGHBORHOOD_LIGHTING.values(), ())).intersection(
        sum(module.POSE_DIVERSE_LIGHTING.values(), ())
    )
    image = Image.new("RGB", (64, 48), (120, 100, 80))
    first = [module._lighting(image, name) for name in sum(
        module.GROUPED_NEIGHBORHOOD_LIGHTING.values(), ()
    )]
    second = [module._lighting(image, name) for name in sum(
        module.GROUPED_NEIGHBORHOOD_LIGHTING.values(), ()
    )]
    assert all(np.array_equal(np.asarray(a), np.asarray(b)) for a, b in zip(first, second))
    assert module.GROUPED_NEIGHBORHOOD_EPOCHS == 12
    assert module.GROUPED_NEIGHBORHOOD_LEARNING_RATE == 0.00015
    assert module.GROUPED_NEIGHBORHOOD_POSITIVE_WEIGHT == 1.75
    assert module.GROUPED_NEIGHBORHOOD_TARGET_EMPHASIS == 2.0
    assert module.GROUPED_NEIGHBORHOOD_BOOTSTRAP_SEED == 19016
    assert set(module.GROUPED_NEIGHBORHOOD_EMPHASIZED_TARGETS) == {
        "MINUS", "U", "7", "1", "0", "PERIOD", "6",
    }
    source_text = (WORKSPACE / "software/ai/train/build_official_mesh_occlusion_data.py").read_text()
    assert "--train-grouped-neighborhood-successor" in source_text
    assert '"trained_parameters": "conv2_conditioner_classifier"' in source_text


def test_transit_dataset_policy_uses_fresh_disjoint_lighting() -> None:
    builder = _builder()
    renderer = _renderer()
    source = {
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v3",
        "pose_groups": {name: list(poses) for name, poses in renderer.POSE_GROUPS.items()},
        "pose_results": [
            {"pose_id": pose_id, "pose_group": group}
            for group, pose_ids in renderer.POSE_GROUPS.items()
            for pose_id in pose_ids
        ],
    }

    schema, policy = builder._split_policy(source)

    assert schema == "rocell.ai_official_mesh_occlusion_data.v3"
    assert policy["train"]["lighting"] == (
        "nominal", "dim", "bright", "warm", "glare", "blur",
        "cool", "side_shadow", "defocus",
    )
    assert policy["development"]["lighting"] == (
        "desaturated", "gamma_dark", "vignette",
    )
    assert policy["evaluation"]["lighting"] == (
        "low_contrast", "right_shadow", "motion_blur",
    )
    lighting = [set(split["lighting"]) for split in policy.values()]
    assert all(
        not (left & right)
        for index, left in enumerate(lighting)
        for right in lighting[index + 1:]
    )


def test_transit_lighting_families_are_deterministic_and_distinct() -> None:
    module = _builder()
    pixels = np.arange(48 * 48 * 3, dtype=np.uint8).reshape(48, 48, 3)
    source = Image.fromarray(pixels, mode="RGB")
    variants = (*module.TRANSIT_LIGHTING["development"], *module.TRANSIT_LIGHTING["evaluation"])

    first = [np.asarray(module._lighting(source, name)) for name in variants]
    second = [np.asarray(module._lighting(source, name)) for name in variants]

    assert all(np.array_equal(left, right) for left, right in zip(first, second, strict=True))
    assert len({_sha256(value.tobytes()) for value in first}) == len(variants)


def test_specificity_dataset_policy_uses_fresh_disjoint_lighting() -> None:
    builder = _builder()
    renderer = _renderer()
    source = {
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v4",
        "pose_groups": {name: list(poses) for name, poses in renderer.POSE_GROUPS.items()},
        "pose_results": [
            {"pose_id": pose_id, "pose_group": group}
            for group, pose_ids in renderer.POSE_GROUPS.items()
            for pose_id in pose_ids
        ],
    }

    schema, policy = builder._split_policy(source)

    assert schema == "rocell.ai_official_mesh_occlusion_data.v4"
    assert policy["development"]["lighting"] == (
        "soft_neutral", "gamma_mid", "left_shadow",
    )
    assert policy["evaluation"]["lighting"] == (
        "cool_flat", "top_shadow", "vertical_motion_blur",
    )
    pose_groups = [set(split["poses"]) for split in policy.values()]
    lighting_groups = [set(split["lighting"]) for split in policy.values()]
    assert all(
        not (left & right)
        for groups in (pose_groups, lighting_groups)
        for index, left in enumerate(groups)
        for right in groups[index + 1:]
    )


def test_specificity_lighting_families_are_deterministic_and_distinct() -> None:
    module = _builder()
    pixels = np.arange(48 * 48 * 3, dtype=np.uint8).reshape(48, 48, 3)
    source = Image.fromarray(pixels, mode="RGB")
    variants = (
        *module.SPECIFICITY_LIGHTING["development"],
        *module.SPECIFICITY_LIGHTING["evaluation"],
    )

    first = [np.asarray(module._lighting(source, name)) for name in variants]
    second = [np.asarray(module._lighting(source, name)) for name in variants]

    assert all(np.array_equal(left, right) for left, right in zip(first, second, strict=True))
    assert len({_sha256(value.tobytes()) for value in first}) == len(variants)


def test_target_aware_dataset_policy_uses_fresh_disjoint_lighting() -> None:
    builder = _builder()
    renderer = _renderer()
    source = {
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v5",
        "pose_groups": {name: list(poses) for name, poses in renderer.POSE_GROUPS.items()},
        "pose_results": [
            {"pose_id": pose_id, "pose_group": group}
            for group, pose_ids in renderer.POSE_GROUPS.items()
            for pose_id in pose_ids
        ],
    }

    schema, policy = builder._split_policy(source)

    assert schema == "rocell.ai_official_mesh_occlusion_data.v5"
    assert policy["development"]["lighting"] == (
        "neutral_low", "bottom_shadow", "diagonal_motion_blur",
    )
    assert policy["evaluation"]["lighting"] == (
        "green_cast", "corner_glare", "horizontal_motion_blur",
    )
    assert set(builder.SPECIFICITY_LIGHTING["development"]) <= set(
        policy["train"]["lighting"]
    )
    assert set(builder.SPECIFICITY_LIGHTING["evaluation"]) <= set(
        policy["train"]["lighting"]
    )
    groups = [set(split["lighting"]) for split in policy.values()]
    assert all(
        not (left & right)
        for index, left in enumerate(groups)
        for right in groups[index + 1:]
    )


def test_mask_perturbation_policy_has_no_evaluation_group() -> None:
    builder = _builder()
    renderer = _renderer()
    source = {
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v6",
        "pose_groups": {
            name: list(poses)
            for name, poses in renderer.PERTURBATION_POSE_GROUPS.items()
        },
        "pose_results": [
            {"pose_id": pose_id, "pose_group": group}
            for group, pose_ids in renderer.PERTURBATION_POSE_GROUPS.items()
            for pose_id in pose_ids
        ],
    }

    schema, policy = builder._split_policy(source)

    assert schema == "rocell.ai_official_mesh_occlusion_data.v6"
    assert policy["train"]["poses"] == policy["evaluation"]["poses"] == ()
    assert policy["development"]["poses"] == tuple(
        renderer.PERTURBATION_POSE_GROUPS["development"]
    )
    assert policy["development"]["lighting"] == (
        "neutral_low", "bottom_shadow", "diagonal_motion_blur",
    )


def test_policy_evaluation_dataset_policy_is_evaluation_only() -> None:
    builder = _builder()
    renderer = _renderer()
    source = {
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v7",
        "pose_groups": {
            name: list(poses)
            for name, poses in renderer.POLICY_EVALUATION_POSE_GROUPS.items()
        },
        "pose_results": [
            {"pose_id": pose_id, "pose_group": group}
            for group, pose_ids in renderer.POLICY_EVALUATION_POSE_GROUPS.items()
            for pose_id in pose_ids
        ],
    }

    schema, policy = builder._split_policy(source)

    assert schema == "rocell.ai_official_mesh_occlusion_data.v7"
    assert policy["train"]["poses"] == policy["development"]["poses"] == ()
    assert policy["evaluation"]["poses"] == tuple(
        renderer.POLICY_EVALUATION_POSE_GROUPS["evaluation"]
    )
    assert policy["evaluation"]["lighting"] == (
        "amber_cast", "center_glare", "anti_diagonal_motion_blur",
    )


def test_policy_evaluation_lighting_is_deterministic_and_fresh() -> None:
    module = _builder()
    pixels = np.arange(48 * 48 * 3, dtype=np.uint8).reshape(48, 48, 3)
    source = Image.fromarray(pixels, mode="RGB")
    variants = module.POLICY_EVALUATION_LIGHTING["evaluation"]

    first = [np.asarray(module._lighting(source, name)) for name in variants]
    second = [np.asarray(module._lighting(source, name)) for name in variants]

    assert all(np.array_equal(left, right) for left, right in zip(first, second, strict=True))
    assert len({_sha256(value.tobytes()) for value in first}) == len(variants)
    prior = {
        name
        for policy in (
            module.LEGACY_SPLITS, module.EXPANDED_LIGHTING, module.TRANSIT_LIGHTING,
            module.SPECIFICITY_LIGHTING, module.TARGET_AWARE_LIGHTING,
            module.PERTURBATION_LIGHTING,
        )
        for split in policy.values()
        for name in (split["lighting"] if isinstance(split, dict) else split)
    }
    assert not (set(variants) & prior)


def test_hard_negative_dataset_policy_is_development_only() -> None:
    builder = _builder()
    renderer = _renderer()
    source = {
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v8",
        "pose_groups": {
            name: list(poses)
            for name, poses in renderer.HARD_NEGATIVE_POSE_GROUPS.items()
        },
        "pose_results": [
            {"pose_id": pose_id, "pose_group": group}
            for group, pose_ids in renderer.HARD_NEGATIVE_POSE_GROUPS.items()
            for pose_id in pose_ids
        ],
    }

    schema, policy = builder._split_policy(source)

    assert schema == "rocell.ai_official_mesh_occlusion_data.v8"
    assert policy["train"]["poses"] == policy["evaluation"]["poses"] == ()
    assert policy["development"]["poses"] == tuple(
        renderer.HARD_NEGATIVE_POSE_GROUPS["development"]
    )
    assert policy["development"]["lighting"] == (
        "amber_low_contrast", "right_center_glare", "offset_anti_diagonal_blur",
    )


def test_hard_negative_lighting_is_deterministic_and_distinct() -> None:
    module = _builder()
    pixels = np.arange(48 * 48 * 3, dtype=np.uint8).reshape(48, 48, 3)
    source = Image.fromarray(pixels, mode="RGB")
    variants = module.HARD_NEGATIVE_LIGHTING["development"]

    first = [np.asarray(module._lighting(source, name)) for name in variants]
    second = [np.asarray(module._lighting(source, name)) for name in variants]

    assert all(np.array_equal(left, right) for left, right in zip(first, second, strict=True))
    assert len({_sha256(value.tobytes()) for value in first}) == len(variants)
    prior = {
        name
        for policy in (
            module.LEGACY_SPLITS, module.EXPANDED_LIGHTING, module.TRANSIT_LIGHTING,
            module.SPECIFICITY_LIGHTING, module.TARGET_AWARE_LIGHTING,
            module.PERTURBATION_LIGHTING, module.POLICY_EVALUATION_LIGHTING,
        )
        for split in policy.values()
        for name in (split["lighting"] if isinstance(split, dict) else split)
    }
    assert not (set(variants) & prior)


def test_target_identity_training_policy_has_no_selection_or_evaluation_group() -> None:
    builder = _builder()
    renderer = _renderer()
    source = {
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v9",
        "pose_groups": {
            name: list(poses)
            for name, poses in renderer.TARGET_IDENTITY_TRAINING_POSE_GROUPS.items()
        },
        "pose_results": [
            {"pose_id": pose_id, "pose_group": group}
            for group, pose_ids in renderer.TARGET_IDENTITY_TRAINING_POSE_GROUPS.items()
            for pose_id in pose_ids
        ],
    }

    schema, policy = builder._split_policy(source)

    assert schema == "rocell.ai_official_mesh_occlusion_data.v9"
    assert policy["development"]["poses"] == policy["evaluation"]["poses"] == ()
    assert policy["train"]["poses"] == tuple(
        renderer.TARGET_IDENTITY_TRAINING_POSE_GROUPS["training"]
    )
    assert policy["train"]["lighting"] == (
        "amber_edge_boost", "right_glare_dim", "anti_diagonal_blur_contrast",
    )


def test_target_identity_training_lighting_is_deterministic_and_fresh() -> None:
    module = _builder()
    pixels = np.arange(48 * 48 * 3, dtype=np.uint8).reshape(48, 48, 3)
    source = Image.fromarray(pixels, mode="RGB")
    variants = module.TARGET_IDENTITY_TRAINING_LIGHTING["train"]

    first = [np.asarray(module._lighting(source, name)) for name in variants]
    second = [np.asarray(module._lighting(source, name)) for name in variants]

    assert all(np.array_equal(left, right) for left, right in zip(first, second, strict=True))
    assert len({_sha256(value.tobytes()) for value in first}) == len(variants)
    prior = {
        name
        for policy in (
            module.LEGACY_SPLITS, module.EXPANDED_LIGHTING, module.TRANSIT_LIGHTING,
            module.SPECIFICITY_LIGHTING, module.TARGET_AWARE_LIGHTING,
            module.PERTURBATION_LIGHTING, module.POLICY_EVALUATION_LIGHTING,
            module.HARD_NEGATIVE_LIGHTING,
        )
        for split in policy.values()
        for name in (split["lighting"] if isinstance(split, dict) else split)
    }
    assert not (set(variants) & prior)


def test_fusion_evaluation_policy_and_lighting_are_fresh() -> None:
    builder = _builder()
    renderer = _renderer()
    source = {
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v10",
        "pose_groups": {
            name: list(poses)
            for name, poses in renderer.FUSION_EVALUATION_POSE_GROUPS.items()
        },
        "pose_results": [
            {"pose_id": pose_id, "pose_group": group}
            for group, pose_ids in renderer.FUSION_EVALUATION_POSE_GROUPS.items()
            for pose_id in pose_ids
        ],
    }

    schema, policy = builder._split_policy(source)
    variants = builder.FUSION_EVALUATION_LIGHTING["evaluation"]
    pixels = np.arange(48 * 48 * 3, dtype=np.uint8).reshape(48, 48, 3)
    image = Image.fromarray(pixels, mode="RGB")
    first = [np.asarray(builder._lighting(image, name)) for name in variants]
    second = [np.asarray(builder._lighting(image, name)) for name in variants]
    prior = {
        name
        for lighting in (
            builder.LEGACY_SPLITS, builder.EXPANDED_LIGHTING,
            builder.TRANSIT_LIGHTING, builder.SPECIFICITY_LIGHTING,
            builder.TARGET_AWARE_LIGHTING, builder.PERTURBATION_LIGHTING,
            builder.POLICY_EVALUATION_LIGHTING, builder.HARD_NEGATIVE_LIGHTING,
            builder.TARGET_IDENTITY_TRAINING_LIGHTING,
        )
        for split in lighting.values()
        for name in (split["lighting"] if isinstance(split, dict) else split)
    }

    assert schema == "rocell.ai_official_mesh_occlusion_data.v10"
    assert policy["train"]["poses"] == policy["development"]["poses"] == ()
    assert policy["evaluation"]["poses"] == tuple(
        renderer.FUSION_EVALUATION_POSE_GROUPS["evaluation"]
    )
    assert policy["evaluation"]["lighting"] == variants
    assert all(
        np.array_equal(left, right)
        for left, right in zip(first, second, strict=True)
    )
    assert len({_sha256(value.tobytes()) for value in first}) == len(variants)
    assert not (set(variants) & prior)


def test_occlusion_recall_policy_and_lighting_are_fresh_and_disjoint() -> None:
    builder = _builder()
    renderer = _renderer()
    source = {
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v11",
        "pose_groups": {
            name: list(poses)
            for name, poses in renderer.OCCLUSION_RECALL_POSE_GROUPS.items()
        },
        "pose_results": [
            {"pose_id": pose_id, "pose_group": group}
            for group, pose_ids in renderer.OCCLUSION_RECALL_POSE_GROUPS.items()
            for pose_id in pose_ids
        ],
    }

    schema, policy = builder._split_policy(source)
    train_variants = builder.OCCLUSION_RECALL_LIGHTING["train"]
    development_variants = builder.OCCLUSION_RECALL_LIGHTING["development"]
    variants = (*train_variants, *development_variants)
    pixels = np.arange(48 * 48 * 3, dtype=np.uint8).reshape(48, 48, 3)
    image = Image.fromarray(pixels, mode="RGB")
    first = [np.asarray(builder._lighting(image, name)) for name in variants]
    second = [np.asarray(builder._lighting(image, name)) for name in variants]
    prior = {
        name
        for lighting in (
            builder.LEGACY_SPLITS, builder.EXPANDED_LIGHTING,
            builder.TRANSIT_LIGHTING, builder.SPECIFICITY_LIGHTING,
            builder.TARGET_AWARE_LIGHTING, builder.PERTURBATION_LIGHTING,
            builder.POLICY_EVALUATION_LIGHTING, builder.HARD_NEGATIVE_LIGHTING,
            builder.TARGET_IDENTITY_TRAINING_LIGHTING,
            builder.FUSION_EVALUATION_LIGHTING,
        )
        for split in lighting.values()
        for name in (split["lighting"] if isinstance(split, dict) else split)
    }

    assert schema == "rocell.ai_official_mesh_occlusion_data.v11"
    assert policy["evaluation"]["poses"] == policy["evaluation"]["lighting"] == ()
    assert policy["train"]["lighting"] == train_variants
    assert policy["development"]["lighting"] == development_variants
    assert set(train_variants).isdisjoint(development_variants)
    assert not (set(variants) & prior)
    assert all(
        np.array_equal(left, right)
        for left, right in zip(first, second, strict=True)
    )
    assert len({_sha256(value.tobytes()) for value in first}) == len(variants)


def test_recall_evaluation_policy_and_lighting_are_fresh() -> None:
    builder = _builder()
    renderer = _renderer()
    source = {
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v12",
        "pose_groups": {
            name: list(poses)
            for name, poses in renderer.RECALL_EVALUATION_POSE_GROUPS.items()
        },
        "pose_results": [
            {"pose_id": pose_id, "pose_group": group}
            for group, pose_ids in renderer.RECALL_EVALUATION_POSE_GROUPS.items()
            for pose_id in pose_ids
        ],
    }

    schema, policy = builder._split_policy(source)
    variants = builder.RECALL_EVALUATION_LIGHTING["evaluation"]
    pixels = np.arange(48 * 48 * 3, dtype=np.uint8).reshape(48, 48, 3)
    image = Image.fromarray(pixels, mode="RGB")
    first = [np.asarray(builder._lighting(image, name)) for name in variants]
    second = [np.asarray(builder._lighting(image, name)) for name in variants]
    prior = {
        name
        for lighting in (
            builder.LEGACY_SPLITS, builder.EXPANDED_LIGHTING,
            builder.TRANSIT_LIGHTING, builder.SPECIFICITY_LIGHTING,
            builder.TARGET_AWARE_LIGHTING, builder.PERTURBATION_LIGHTING,
            builder.POLICY_EVALUATION_LIGHTING, builder.HARD_NEGATIVE_LIGHTING,
            builder.TARGET_IDENTITY_TRAINING_LIGHTING,
            builder.FUSION_EVALUATION_LIGHTING,
            builder.OCCLUSION_RECALL_LIGHTING,
        )
        for split in lighting.values()
        for name in (split["lighting"] if isinstance(split, dict) else split)
    }

    assert schema == "rocell.ai_official_mesh_occlusion_data.v12"
    assert policy["train"]["poses"] == policy["train"]["lighting"] == ()
    assert policy["development"]["poses"] \
        == policy["development"]["lighting"] == ()
    assert policy["evaluation"]["lighting"] == variants
    assert not (set(variants) & prior)
    assert all(
        np.array_equal(left, right)
        for left, right in zip(first, second, strict=True)
    )
    assert len({_sha256(value.tobytes()) for value in first}) == len(variants)


def test_specificity_rebalance_policy_and_lighting_are_fresh() -> None:
    builder = _builder()
    renderer = _renderer()
    source = {
        "schema": "tactevra.isaac_fixed_overview_mesh_render.v13",
        "pose_groups": {
            name: list(poses)
            for name, poses in renderer.SPECIFICITY_REBALANCE_POSE_GROUPS.items()
        },
        "pose_results": [
            {"pose_id": pose_id, "pose_group": group}
            for group, pose_ids in renderer.SPECIFICITY_REBALANCE_POSE_GROUPS.items()
            for pose_id in pose_ids
        ],
    }

    schema, policy = builder._split_policy(source)
    train_variants = builder.SPECIFICITY_REBALANCE_LIGHTING["train"]
    development_variants = builder.SPECIFICITY_REBALANCE_LIGHTING["development"]
    variants = (*train_variants, *development_variants)
    pixels = np.arange(48 * 48 * 3, dtype=np.uint8).reshape(48, 48, 3)
    image = Image.fromarray(pixels, mode="RGB")
    first = [np.asarray(builder._lighting(image, name)) for name in variants]
    second = [np.asarray(builder._lighting(image, name)) for name in variants]
    prior = {
        name
        for lighting in (
            builder.LEGACY_SPLITS, builder.EXPANDED_LIGHTING,
            builder.TRANSIT_LIGHTING, builder.SPECIFICITY_LIGHTING,
            builder.TARGET_AWARE_LIGHTING, builder.PERTURBATION_LIGHTING,
            builder.POLICY_EVALUATION_LIGHTING, builder.HARD_NEGATIVE_LIGHTING,
            builder.TARGET_IDENTITY_TRAINING_LIGHTING,
            builder.FUSION_EVALUATION_LIGHTING,
            builder.OCCLUSION_RECALL_LIGHTING,
            builder.RECALL_EVALUATION_LIGHTING,
        )
        for split in lighting.values()
        for name in (split["lighting"] if isinstance(split, dict) else split)
    }

    assert schema == "rocell.ai_official_mesh_occlusion_data.v13"
    assert policy["evaluation"]["poses"] == policy["evaluation"]["lighting"] == ()
    assert policy["train"]["lighting"] == train_variants
    assert policy["development"]["lighting"] == development_variants
    assert set(train_variants).isdisjoint(development_variants)
    assert not (set(variants) & prior)
    assert all(
        np.array_equal(left, right)
        for left, right in zip(first, second, strict=True)
    )
    assert len({_sha256(value.tobytes()) for value in first}) == len(variants)


def test_target_aware_lighting_families_are_deterministic_and_distinct() -> None:
    module = _builder()
    pixels = np.arange(48 * 48 * 3, dtype=np.uint8).reshape(48, 48, 3)
    source = Image.fromarray(pixels, mode="RGB")
    variants = (
        *module.TARGET_AWARE_LIGHTING["development"],
        *module.TARGET_AWARE_LIGHTING["evaluation"],
    )

    first = [np.asarray(module._lighting(source, name)) for name in variants]
    second = [np.asarray(module._lighting(source, name)) for name in variants]

    assert all(np.array_equal(left, right) for left, right in zip(first, second, strict=True))
    assert len({_sha256(value.tobytes()) for value in first}) == len(variants)


def test_progression_video_encoder_is_deterministic(tmp_path: Path) -> None:
    pytest.importorskip("av")
    module = _builder()
    first_path = tmp_path / "first.mp4"
    second_path = tmp_path / "second.mp4"
    frames = [
        Image.new("RGB", (960, 540), color=(index * 40, 20, 80))
        for index in range(3)
    ]

    module._encode_mp4(first_path, frames)
    module._encode_mp4(second_path, frames)

    assert first_path.read_bytes() == second_path.read_bytes()
    assert first_path.stat().st_size > 0


def test_spatial_crops_are_deterministic_channel_first_and_labeled(tmp_path: Path) -> None:
    module = _builder()
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    pixels = np.arange(64 * 64 * 3, dtype=np.uint8).reshape(64, 64, 3)
    image_path = image_dir / "sample.png"
    Image.fromarray(pixels, mode="RGB").save(image_path)
    row = {
        "image_path": "images/sample.png",
        "image_sha256": _sha256(image_path.read_bytes()),
        "safe_polygon_px": [[20, 20], [44, 20], [44, 44], [20, 44]],
        "decision": "abstain",
    }

    first_x, first_y = module._spatial_crops(tmp_path, [row])
    second_x, second_y = module._spatial_crops(tmp_path, [row])

    assert first_x.shape == (1, 3, 32, 32)
    assert first_x.dtype == np.float32
    assert np.array_equal(first_x, second_x)
    assert np.array_equal(first_y, second_y)
    assert first_y.tolist() == [1.0]
    assert 0.0 <= float(first_x.min()) <= float(first_x.max()) <= 1.0


def test_target_aware_crops_add_only_known_safe_region_mask(tmp_path: Path) -> None:
    module = _builder()
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    pixels = np.arange(64 * 64 * 3, dtype=np.uint8).reshape(64, 64, 3)
    image_path = image_dir / "sample.png"
    Image.fromarray(pixels, mode="RGB").save(image_path)
    row = {
        "image_path": "images/sample.png",
        "image_sha256": _sha256(image_path.read_bytes()),
        "safe_polygon_px": [[24, 26], [40, 26], [40, 38], [24, 38]],
        "decision": "abstain",
    }

    spatial, labels = module._spatial_crops(tmp_path, [row])
    first, first_labels = module._target_aware_crops(tmp_path, [row])
    second, second_labels = module._target_aware_crops(tmp_path, [row])

    assert first.shape == (1, 4, 32, 32)
    assert np.array_equal(first[:, :3], spatial)
    assert set(np.unique(first[:, 3])).issubset({0.0, 1.0})
    assert 0 < int(first[:, 3].sum()) < 32 * 32
    assert np.array_equal(first, second)
    assert np.array_equal(labels, first_labels)
    assert np.array_equal(first_labels, second_labels)


def test_target_aware_crops_translate_rgb_and_mask_together(tmp_path: Path) -> None:
    module = _builder()
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    x = np.arange(128, dtype=np.uint8)[None, :]
    pixels = np.repeat(x, 128, axis=0)
    rgb = np.stack((pixels, np.flip(pixels, axis=1), pixels), axis=2)
    image_path = image_dir / "gradient.png"
    Image.fromarray(rgb, mode="RGB").save(image_path)
    row = {
        "image_path": "images/gradient.png",
        "image_sha256": _sha256(image_path.read_bytes()),
        "safe_polygon_px": [[56, 58], [72, 58], [72, 70], [56, 70]],
        "decision": "abstain",
    }

    nominal, labels = module._target_aware_crops(tmp_path, [row])
    shifted, shifted_labels = module._target_aware_crops(tmp_path, [row], (8.0, -4.0))
    repeated, _ = module._target_aware_crops(tmp_path, [row], (8.0, -4.0))

    assert nominal.shape == shifted.shape == (1, 4, 32, 32)
    assert not np.array_equal(nominal[:, :3], shifted[:, :3])
    assert np.array_equal(nominal[:, 3], shifted[:, 3])
    assert np.array_equal(shifted, repeated)
    assert np.array_equal(labels, shifted_labels)
    assert len(module._declared_mask_offsets()) == 33
    assert len(module._training_augmentation_offsets()) == 17


def test_target_identity_descriptor_binds_identity_and_nominal_geometry(
    tmp_path: Path,
) -> None:
    module = _builder()
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    image_path = image_dir / "sample.png"
    Image.new("RGB", (100, 50), (200, 200, 200)).save(image_path)
    rows = [
        {
            "device": "keyboard", "target_id": target,
            "image_path": "images/sample.png", "center_px": [50, 25],
            "safe_polygon_px": [[40, 20], [60, 20], [60, 30], [40, 30]],
        }
        for target in ("ENTER", "EQUAL")
    ]
    catalog = module._target_identity_catalog(rows)

    first = module._target_identity_descriptors(tmp_path, rows, catalog)
    second = module._target_identity_descriptors(tmp_path, rows, catalog)

    assert catalog == ("keyboard:ENTER", "keyboard:EQUAL")
    assert first.shape == (2, 6)
    assert np.array_equal(first, second)
    assert first[0, :2].tolist() == [1.0, 0.0]
    assert first[1, :2].tolist() == [0.0, 1.0]
    assert np.allclose(first[:, 2:], [[0.5, 0.5, 0.2, 0.2]] * 2)


def test_localization_policy_selects_largest_supported_development_bound() -> None:
    module = _builder()
    rows = [
        {"id": "visible"},
        {"id": "blocked"},
    ]
    labels = np.asarray([0.0, 1.0])
    probabilities = np.asarray([0.01, 0.99])
    by_offset = [
        (offset, probabilities.copy())
        for offset in module._declared_mask_offsets()
    ]

    threshold, bound, gate_met, measurements = module._select_localization_policy(
        rows, labels, by_offset,
    )

    assert threshold == 0.05
    assert bound == 4.0
    assert gate_met is True
    assert len(measurements) == 33
    assert all(
        item["metrics"]["confusion"] == {
            "true_abstain": 1,
            "true_visible": 1,
            "false_abstain": 0,
            "missed_abstain": 0,
        }
        for item in measurements
    )


def test_localization_policy_resolves_feasible_sub_centithreshold_interval() -> None:
    module = _builder()
    rows = [{"id": f"row-{index}"} for index in range(40)]
    labels = np.asarray([0.0] * 20 + [1.0] * 20)
    probabilities = np.asarray(
        [0.01] * 18 + [0.0945, 0.0945] + [0.094, 0.096] + [0.99] * 18,
        dtype=np.float64,
    )
    by_offset = [
        (offset, probabilities.copy())
        for offset in module._declared_mask_offsets()
    ]

    threshold, bound, gate_met, measurements = module._select_localization_policy(
        rows, labels, by_offset,
    )

    assert threshold == 0.095
    assert bound == 4.0
    assert gate_met is True
    assert len(measurements) == 33
    assert all(
        item["metrics"]["confusion"]["missed_abstain"] == 1
        and item["metrics"]["confusion"]["false_abstain"] == 0
        for item in measurements
    )


def test_target_aware_candidate_is_deterministic_and_has_no_robot_mask_input(
    tmp_path: Path,
) -> None:
    module = _builder()
    dataset = tmp_path / "dataset"
    image_dir = dataset / "images"
    image_dir.mkdir(parents=True)
    splits = {}
    for split_index, split in enumerate(("train", "development", "evaluation")):
        rows = []
        for index in range(8):
            expected_abstain = index % 2 == 0
            image = Image.new("RGB", (64, 64), (205, 205, 205))
            draw = ImageDraw.Draw(image)
            if expected_abstain:
                draw.rectangle((26, 20, 38, 44), fill=(20, 20, 20))
            else:
                draw.rectangle((4, 4, 14, 14), fill=(20, 20, 20))
            image_path = image_dir / f"{split}-{index}.png"
            image.save(image_path)
            rows.append({
                "id": f"{split}-{index}",
                "image_path": f"images/{image_path.name}",
                "image_sha256": _sha256(image_path.read_bytes()),
                "pose_id": f"pose-{split_index}-{index}",
                "lighting_variant": f"light-{split_index}",
                "device": "keyboard",
                "target_id": "H",
                "center_px": [32, 32],
                "safe_polygon_px": [[24, 24], [40, 24], [40, 40], [24, 40]],
                "center_occluded": expected_abstain,
                "safe_region_overlap_fraction": 0.5 if expected_abstain else 0.0,
                "decision": "abstain" if expected_abstain else "target_visible",
                "reason": "robot_occlusion" if expected_abstain else None,
                "synthetic_only": True,
            })
        payload = b"".join(module._canonical(row) + b"\n" for row in rows)
        path = dataset / f"{split}.jsonl"
        path.write_bytes(payload)
        splits[split] = {
            "path": path.name,
            "sha256": _sha256(payload),
            "count": len(rows),
            "abstain_count": 4,
            "visible_count": 4,
        }
    manifest = {
        "schema": "rocell.ai_official_mesh_occlusion_data.v5",
        "scope": "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION",
        "splits": splits,
        "limitations": ["unit-test synthetic fixture"],
    }
    manifest["dataset_sha256"] = _sha256(module._canonical(manifest))
    (dataset / "manifest.json").write_bytes(module._canonical(manifest) + b"\n")

    first = module.train_target_aware_candidate(dataset, tmp_path / "first")
    second = module.train_target_aware_candidate(dataset, tmp_path / "second")
    checkpoint = json.loads((tmp_path / "first" / "model.json").read_text())

    assert first == second
    assert (tmp_path / "first" / "model.json").read_bytes() == (
        tmp_path / "second" / "model.json"
    ).read_bytes()
    assert checkpoint["architecture"]["input"] == [4, 32, 32]
    assert checkpoint["architecture"]["simulator_robot_mask_input"] is False
    assert checkpoint["architecture"]["parameter_count"] == 1721
    loaded_checkpoint, loaded_model = module._load_spatial_checkpoint(tmp_path / "first")
    crops, _ = module._target_aware_crops(dataset, [
        json.loads((dataset / "evaluation.jsonl").read_text().splitlines()[0])
    ])
    torch = pytest.importorskip("torch")
    with torch.no_grad():
        probability = torch.sigmoid(loaded_model(torch.from_numpy(crops))).item()
    assert loaded_checkpoint["schema"] == "rocell.ai_target_crop_safe_region_spatial.v1"
    assert loaded_model.features[0].in_channels == 4
    assert 0.0 <= probability <= 1.0
    assert first["promotion_status"] == "BLOCKED_SYNTHETIC_ONLY"
    assert first["hardware_writes"] == 0
    assert first["physical_movements"] == 0


def test_target_identity_candidate_is_deterministic_and_keeps_evaluation_closed(
    tmp_path: Path,
) -> None:
    module = _builder()

    def make_dataset(name: str, schema: str, populated_split: str) -> Path:
        dataset = tmp_path / name
        image_dir = dataset / "images"
        image_dir.mkdir(parents=True)
        rows = []
        for index in range(16):
            expected_abstain = index % 2 == 0
            target_id = "ENTER" if index % 4 < 2 else "EQUAL"
            image = Image.new("RGB", (64, 64), (205, 205, 205))
            draw = ImageDraw.Draw(image)
            if expected_abstain:
                draw.rectangle((26, 20, 38, 44), fill=(20, 20, 20))
            else:
                draw.rectangle((4, 4, 14, 14), fill=(20, 20, 20))
            image_path = image_dir / f"{populated_split}-{index}.png"
            image.save(image_path)
            rows.append({
                "id": f"{populated_split}-{index}",
                "image_path": f"images/{image_path.name}",
                "image_sha256": _sha256(image_path.read_bytes()),
                "pose_id": f"pose-{index}",
                "lighting_variant": "unit-light",
                "device": "keyboard",
                "target_id": target_id,
                "center_px": [32, 32],
                "safe_polygon_px": [[24, 24], [40, 24], [40, 40], [24, 40]],
                "center_occluded": expected_abstain,
                "safe_region_overlap_fraction": 0.5 if expected_abstain else 0.0,
                "decision": "abstain" if expected_abstain else "target_visible",
                "reason": "robot_occlusion" if expected_abstain else None,
                "synthetic_only": True,
            })
        splits = {}
        for split in ("train", "development", "evaluation"):
            split_rows = rows if split == populated_split else []
            payload = b"".join(module._canonical(row) + b"\n" for row in split_rows)
            path = dataset / f"{split}.jsonl"
            path.write_bytes(payload)
            splits[split] = {
                "path": path.name,
                "sha256": _sha256(payload),
                "count": len(split_rows),
                "abstain_count": sum(row["decision"] == "abstain" for row in split_rows),
                "visible_count": sum(
                    row["decision"] == "target_visible" for row in split_rows
                ),
            }
        manifest = {
            "schema": schema,
            "scope": "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION",
            "target_catalog_sha256": "a" * 64,
            "splits": splits,
            "limitations": ["unit-test synthetic fixture"],
        }
        manifest["dataset_sha256"] = _sha256(module._canonical(manifest))
        (dataset / "manifest.json").write_bytes(module._canonical(manifest) + b"\n")
        return dataset

    training = make_dataset(
        "training", "rocell.ai_official_mesh_occlusion_data.v9", "train",
    )
    development = make_dataset(
        "development", "rocell.ai_official_mesh_occlusion_data.v8", "development",
    )

    first = module.train_target_identity_candidate(training, development, tmp_path / "first")
    second = module.train_target_identity_candidate(training, development, tmp_path / "second")
    checkpoint = json.loads((tmp_path / "first" / "model.json").read_text())

    assert first == second
    assert (tmp_path / "first" / "model.json").read_bytes() == (
        tmp_path / "second" / "model.json"
    ).read_bytes()
    assert checkpoint["schema"] == "rocell.ai_target_identity_geometry_spatial.v1"
    assert checkpoint["architecture"]["target_catalog"] == [
        "keyboard:ENTER", "keyboard:EQUAL",
    ]
    assert checkpoint["architecture"]["descriptor_size"] == 6
    assert checkpoint["evaluation_opened"] is False
    assert first["evaluation_group_present"] is False
    assert first["hardware_writes"] == 0
    assert first["physical_movements"] == 0
    assert first["physical_authority"] is False



def test_target_conditioned_fusion_is_deterministic_and_freezes_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _builder()
    torch = pytest.importorskip("torch")

    def make_dataset(name: str, schema: str, populated_split: str) -> Path:
        dataset = tmp_path / name
        image_dir = dataset / "images"
        image_dir.mkdir(parents=True)
        rows = []
        for index in range(12):
            expected_abstain = index % 3 == 0
            target_id = "ENTER" if index % 2 == 0 else "EQUAL"
            image = Image.new("RGB", (64, 64), (205, 205, 205))
            draw = ImageDraw.Draw(image)
            if expected_abstain:
                draw.rectangle((26, 20, 38, 44), fill=(20, 20, 20))
            else:
                draw.rectangle((4, 4, 14, 14), fill=(20, 20, 20))
            image_path = image_dir / f"{populated_split}-{index}.png"
            image.save(image_path)
            rows.append({
                "id": f"{populated_split}-{index}",
                "image_path": f"images/{image_path.name}",
                "image_sha256": _sha256(image_path.read_bytes()),
                "pose_id": f"pose-{index}",
                "lighting_variant": "unit-light",
                "device": "keyboard",
                "target_id": target_id,
                "center_px": [32, 32],
                "safe_polygon_px": [[24, 24], [40, 24], [40, 40], [24, 40]],
                "center_occluded": expected_abstain,
                "safe_region_overlap_fraction": 0.5 if expected_abstain else 0.0,
                "decision": "abstain" if expected_abstain else "target_visible",
                "reason": "robot_occlusion" if expected_abstain else None,
                "synthetic_only": True,
            })
        splits = {}
        for split in ("train", "development", "evaluation"):
            split_rows = rows if split == populated_split else []
            payload = b"".join(module._canonical(row) + b"\n" for row in split_rows)
            path = dataset / f"{split}.jsonl"
            path.write_bytes(payload)
            splits[split] = {
                "path": path.name, "sha256": _sha256(payload),
                "count": len(split_rows),
                "abstain_count": sum(row["decision"] == "abstain" for row in split_rows),
                "visible_count": sum(
                    row["decision"] == "target_visible" for row in split_rows
                ),
            }
        manifest = {
            "schema": schema,
            "scope": "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION",
            "target_catalog_sha256": "a" * 64,
            "splits": splits,
            "limitations": ["unit-test synthetic fixture"],
        }
        manifest["dataset_sha256"] = _sha256(module._canonical(manifest))
        (dataset / "manifest.json").write_bytes(module._canonical(manifest) + b"\n")
        return dataset

    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    generator = torch.Generator().manual_seed(190)
    shapes = {
        "features.0.weight": (8, 4, 3, 3), "features.0.bias": (8,),
        "features.3.weight": (16, 8, 3, 3), "features.3.bias": (16,),
        "classifier.weight": (1, 256), "classifier.bias": (1,),
    }
    state = {
        name: {
            "shape": list(shape),
            "values": (
                torch.randn(shape, generator=generator) * 0.02
            ).reshape(-1).tolist(),
        }
        for name, shape in shapes.items()
    }
    seed_checkpoint = {
        "schema": "rocell.ai_target_crop_localization_robust_spatial.v1",
        "architecture": {"input": [4, 32, 32]},
        "threshold": 0.1,
        "localization_uncertainty_policy": {
            "maximum_supported_planar_error_mm": 1.0,
            "development_gate_met": True,
        },
        "evaluation_opened": False,
        "state_dict": state,
    }
    seed_model_path = seed_dir / "model.json"
    seed_model_path.write_bytes(module._canonical(seed_checkpoint) + b"\n")
    seed_scorecard = {
        "schema": "rocell.ai_localization_policy_refreeze.v1",
        "model_sha256": _sha256(seed_model_path.read_bytes()),
        "maximum_supported_planar_error_mm": 1.0,
        "development_gate_met": True,
        "hardware_writes": 0,
        "physical_movements": 0,
    }
    seed_scorecard["scorecard_sha256"] = _sha256(module._canonical(seed_scorecard))
    (seed_dir / "scorecard.json").write_bytes(module._canonical(seed_scorecard) + b"\n")
    training = make_dataset(
        "fusion-training", "rocell.ai_official_mesh_occlusion_data.v9", "train",
    )
    development = make_dataset(
        "fusion-development", "rocell.ai_official_mesh_occlusion_data.v8", "development",
    )

    first = module.train_target_conditioned_fusion_candidate(
        training, development, seed_dir, tmp_path / "fusion-first",
    )
    second = module.train_target_conditioned_fusion_candidate(
        training, development, seed_dir, tmp_path / "fusion-second",
    )
    checkpoint = json.loads((tmp_path / "fusion-first" / "model.json").read_text())

    assert first == second
    assert (tmp_path / "fusion-first" / "model.json").read_bytes() == (
        tmp_path / "fusion-second" / "model.json"
    ).read_bytes()
    assert checkpoint["schema"] == "rocell.ai_target_conditioned_spatial_fusion.v1"
    assert checkpoint["architecture"]["fusion"].endswith("before_spatial_pooling")
    assert checkpoint["architecture"]["frozen_visual_backbone"] is True
    assert checkpoint["architecture"]["frozen_classifier"] is True
    assert checkpoint["architecture"]["trainable_parameter_count"] == 224
    assert checkpoint["state_dict"]["conv1.weight"] == state["features.0.weight"]
    assert checkpoint["state_dict"]["conv2.weight"] == state["features.3.weight"]
    assert checkpoint["state_dict"]["classifier.weight"] == state["classifier.weight"]
    assert checkpoint["evaluation_opened"] is False
    assert first["evaluation_group_present"] is False
    assert first["hardware_writes"] == 0
    assert first["physical_movements"] == 0
    assert first["physical_authority"] is False

    evaluation = make_dataset(
        "fusion-evaluation", "rocell.ai_official_mesh_occlusion_data.v10", "evaluation",
    )
    candidate_dir = tmp_path / "fusion-first"
    checkpoint["localization_uncertainty_policy"].update({
        "maximum_supported_planar_error_mm": 1.0,
        "development_gate_met": True,
        "above_bound_decision": "abstain_localization_uncertain",
    })
    model_path = candidate_dir / "model.json"
    model_path.write_bytes(module._canonical(checkpoint) + b"\n")
    scorecard_path = candidate_dir / "scorecard.json"
    scorecard = json.loads(scorecard_path.read_text())
    scorecard.pop("scorecard_sha256")
    scorecard.update({
        "model_sha256": _sha256(model_path.read_bytes()),
        "maximum_supported_planar_error_mm": 1.0,
        "development_gate_met": True,
        "evaluation_group_present": False,
    })
    scorecard["scorecard_sha256"] = _sha256(module._canonical(scorecard))
    scorecard_path.write_bytes(module._canonical(scorecard) + b"\n")

    recall = make_dataset(
        "occlusion-recall", "rocell.ai_official_mesh_occlusion_data.v11", "train",
    )
    recall_development = make_dataset(
        "occlusion-recall-development",
        "rocell.ai_official_mesh_occlusion_data.v11",
        "development",
    )
    recall_manifest_path = recall / "manifest.json"
    recall_manifest = json.loads(recall_manifest_path.read_text())
    recall_development_manifest = json.loads(
        (recall_development / "manifest.json").read_text()
    )
    for image_path in (recall_development / "images").glob("*.png"):
        (recall / "images" / image_path.name).write_bytes(image_path.read_bytes())
    (recall / "development.jsonl").write_bytes(
        (recall_development / "development.jsonl").read_bytes()
    )
    recall_manifest["splits"]["development"] = (
        recall_development_manifest["splits"]["development"]
    )
    recall_manifest.pop("dataset_sha256")
    recall_manifest["dataset_sha256"] = _sha256(module._canonical(recall_manifest))
    recall_manifest_path.write_bytes(module._canonical(recall_manifest) + b"\n")

    recall_first = module.train_occlusion_recall_candidate(
        recall, candidate_dir, tmp_path / "recall-first",
    )
    recall_second = module.train_occlusion_recall_candidate(
        recall, candidate_dir, tmp_path / "recall-second",
    )
    recall_checkpoint = json.loads(
        (tmp_path / "recall-first" / "model.json").read_text()
    )

    assert recall_first == recall_second
    assert (tmp_path / "recall-first" / "model.json").read_bytes() == (
        tmp_path / "recall-second" / "model.json"
    ).read_bytes()
    assert recall_checkpoint["schema"] \
        == "rocell.ai_target_conditioned_occlusion_recall.v1"
    assert recall_checkpoint["training"]["positive_abstention_weight"] == 1.5
    assert recall_checkpoint["training"]["trained_parameters"] == "conditioner_only"
    assert recall_checkpoint["state_dict"]["conv1.weight"] \
        == checkpoint["state_dict"]["conv1.weight"]
    assert recall_checkpoint["state_dict"]["conv2.weight"] \
        == checkpoint["state_dict"]["conv2.weight"]
    assert recall_checkpoint["state_dict"]["classifier.weight"] \
        == checkpoint["state_dict"]["classifier.weight"]
    assert recall_checkpoint["consumed_evaluation_dataset_sha256"] is None
    assert recall_checkpoint["evaluation_opened"] is False
    assert recall_first["evaluation_group_present"] is False
    assert recall_first["hardware_writes"] == 0
    assert recall_first["physical_movements"] == 0
    assert recall_first["physical_authority"] is False

    recall_evaluation = make_dataset(
        "recall-evaluation", "rocell.ai_official_mesh_occlusion_data.v12",
        "evaluation",
    )
    recall_checkpoint["localization_uncertainty_policy"].update({
        "maximum_supported_planar_error_mm": 0.0,
        "development_gate_met": True,
        "above_bound_decision": "abstain_localization_uncertain",
    })
    recall_model_path = tmp_path / "recall-first" / "model.json"
    recall_model_path.write_bytes(module._canonical(recall_checkpoint) + b"\n")
    recall_scorecard_path = tmp_path / "recall-first" / "scorecard.json"
    recall_scorecard = json.loads(recall_scorecard_path.read_text())
    recall_scorecard.pop("scorecard_sha256")
    recall_scorecard.update({
        "model_sha256": _sha256(recall_model_path.read_bytes()),
        "maximum_supported_planar_error_mm": 0.0,
        "development_gate_met": True,
        "evaluation_group_present": False,
    })
    recall_scorecard["scorecard_sha256"] = _sha256(
        module._canonical(recall_scorecard)
    )
    recall_scorecard_path.write_bytes(module._canonical(recall_scorecard) + b"\n")
    monkeypatch.setattr(
        module, "EXPECTED_OCCLUSION_RECALL_MODEL_SHA256",
        _sha256(recall_model_path.read_bytes()),
    )
    monkeypatch.setattr(
        module, "EXPECTED_OCCLUSION_RECALL_SCORECARD_SHA256",
        recall_scorecard["scorecard_sha256"],
    )
    rebalance = make_dataset(
        "specificity-rebalance", "rocell.ai_official_mesh_occlusion_data.v13",
        "train",
    )
    rebalance_development = make_dataset(
        "specificity-rebalance-development",
        "rocell.ai_official_mesh_occlusion_data.v13", "development",
    )
    rebalance_manifest_path = rebalance / "manifest.json"
    rebalance_manifest = json.loads(rebalance_manifest_path.read_text())
    rebalance_development_manifest = json.loads(
        (rebalance_development / "manifest.json").read_text()
    )
    for image_path in (rebalance_development / "images").glob("*.png"):
        (rebalance / "images" / image_path.name).write_bytes(image_path.read_bytes())
    (rebalance / "development.jsonl").write_bytes(
        (rebalance_development / "development.jsonl").read_bytes()
    )
    rebalance_manifest["splits"]["development"] = (
        rebalance_development_manifest["splits"]["development"]
    )
    rebalance_manifest.pop("dataset_sha256")
    rebalance_manifest["dataset_sha256"] = _sha256(
        module._canonical(rebalance_manifest)
    )
    rebalance_manifest_path.write_bytes(
        module._canonical(rebalance_manifest) + b"\n"
    )

    rebalance_first = module.train_specificity_rebalance_candidate(
        rebalance, tmp_path / "recall-first", tmp_path / "rebalance-first",
    )
    rebalance_second = module.train_specificity_rebalance_candidate(
        rebalance, tmp_path / "recall-first", tmp_path / "rebalance-second",
    )
    rebalance_checkpoint = json.loads(
        (tmp_path / "rebalance-first" / "model.json").read_text()
    )

    assert rebalance_first == rebalance_second
    assert (tmp_path / "rebalance-first" / "model.json").read_bytes() == (
        tmp_path / "rebalance-second" / "model.json"
    ).read_bytes()
    assert rebalance_checkpoint["schema"] \
        == "rocell.ai_target_conditioned_specificity_rebalance.v1"
    assert rebalance_checkpoint["training"]["loss"] == "binary_cross_entropy"
    assert rebalance_checkpoint["training"]["positive_abstention_weight"] == 1.0
    assert rebalance_checkpoint["training"]["trained_parameters"] \
        == "conditioner_only"
    assert rebalance_checkpoint["state_dict"]["conv1.weight"] \
        == recall_checkpoint["state_dict"]["conv1.weight"]
    assert rebalance_checkpoint["state_dict"]["conv2.weight"] \
        == recall_checkpoint["state_dict"]["conv2.weight"]
    assert rebalance_checkpoint["state_dict"]["classifier.weight"] \
        == recall_checkpoint["state_dict"]["classifier.weight"]
    assert rebalance_checkpoint["consumed_evaluation_dataset_sha256"] is None
    assert rebalance_checkpoint["evaluation_opened"] is False
    assert rebalance_first["evaluation_group_present"] is False
    assert rebalance_first["hardware_writes"] == 0
    assert rebalance_first["physical_movements"] == 0
    assert rebalance_first["physical_authority"] is False

    rebalance_checkpoint["localization_uncertainty_policy"].update({
        "maximum_supported_planar_error_mm": 2.0,
        "development_gate_met": True,
        "above_bound_decision": "abstain_localization_uncertain",
    })
    rebalance_model_path = tmp_path / "rebalance-first" / "model.json"
    rebalance_model_path.write_bytes(module._canonical(rebalance_checkpoint) + b"\n")
    rebalance_scorecard_path = tmp_path / "rebalance-first" / "scorecard.json"
    rebalance_scorecard = json.loads(rebalance_scorecard_path.read_text())
    rebalance_scorecard.pop("scorecard_sha256")
    rebalance_scorecard.update({
        "model_sha256": _sha256(rebalance_model_path.read_bytes()),
        "maximum_supported_planar_error_mm": 2.0,
        "development_gate_met": True,
        "evaluation_group_present": False,
    })
    rebalance_scorecard["scorecard_sha256"] = _sha256(
        module._canonical(rebalance_scorecard)
    )
    rebalance_scorecard_path.write_bytes(
        module._canonical(rebalance_scorecard) + b"\n"
    )
    monkeypatch.setattr(
        module, "EXPECTED_SPECIFICITY_REBALANCE_MODEL_SHA256",
        _sha256(rebalance_model_path.read_bytes()),
    )
    monkeypatch.setattr(
        module, "EXPECTED_SPECIFICITY_REBALANCE_SCORECARD_SHA256",
        rebalance_scorecard["scorecard_sha256"],
    )
    rebalance_evaluation = make_dataset(
        "rebalance-evaluation", "rocell.ai_official_mesh_occlusion_data.v14",
        "evaluation",
    )
    rebalance_eval_first = module.evaluate_specificity_rebalance_candidate(
        rebalance_evaluation, tmp_path / "rebalance-first",
        tmp_path / "rebalance-evaluation-first",
    )
    rebalance_eval_second = module.evaluate_specificity_rebalance_candidate(
        rebalance_evaluation, tmp_path / "rebalance-first",
        tmp_path / "rebalance-evaluation-second",
    )
    assert rebalance_eval_first == rebalance_eval_second
    assert (tmp_path / "rebalance-evaluation-first" / "report.json").read_bytes() \
        == (tmp_path / "rebalance-evaluation-second" / "report.json").read_bytes()
    assert rebalance_eval_first["schema"] \
        == "rocell.ai_specificity_rebalance_evaluation.v1"
    assert rebalance_eval_first["evaluated_planar_error_bound_mm"] == 2.0
    assert rebalance_eval_first["stress_tested_planar_error_mm"] == 4.0
    assert rebalance_eval_first["hardware_writes"] == 0
    assert rebalance_eval_first["physical_movements"] == 0
    assert rebalance_eval_first["physical_authority"] is False

    rebalance_evaluation_manifest_path = rebalance_evaluation / "manifest.json"
    rebalance_evaluation_manifest = json.loads(
        rebalance_evaluation_manifest_path.read_text()
    )
    rebalance_evaluation_manifest["dataset_sha256"] = "0" * 64
    rebalance_evaluation_manifest_path.write_bytes(
        module._canonical(rebalance_evaluation_manifest) + b"\n"
    )
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        module.evaluate_specificity_rebalance_candidate(
            rebalance_evaluation, tmp_path / "rebalance-first",
            tmp_path / "rebalance-evaluation-tampered",
        )

    altered_seed = tmp_path / "altered-recall-seed"
    altered_seed.mkdir()
    (altered_seed / "model.json").write_bytes(recall_model_path.read_bytes())
    altered_scorecard = dict(recall_scorecard)
    altered_scorecard["scorecard_sha256"] = "0" * 64
    (altered_seed / "scorecard.json").write_bytes(
        module._canonical(altered_scorecard) + b"\n"
    )
    with pytest.raises(ValueError, match="seed scorecard hash mismatch"):
        module.train_specificity_rebalance_candidate(
            rebalance, altered_seed, tmp_path / "rebalance-altered-seed",
        )

    recall_evaluation_first = module.evaluate_occlusion_recall_candidate(
        recall_evaluation, tmp_path / "recall-first",
        tmp_path / "recall-evaluation-first",
    )
    recall_evaluation_second = module.evaluate_occlusion_recall_candidate(
        recall_evaluation, tmp_path / "recall-first",
        tmp_path / "recall-evaluation-second",
    )

    assert recall_evaluation_first == recall_evaluation_second
    assert (tmp_path / "recall-evaluation-first" / "report.json").read_bytes() \
        == (tmp_path / "recall-evaluation-second" / "report.json").read_bytes()
    assert recall_evaluation_first["schema"] \
        == "rocell.ai_occlusion_recall_evaluation.v1"
    assert recall_evaluation_first["evaluated_planar_error_bound_mm"] == 0.0
    assert recall_evaluation_first["stress_tested_planar_error_mm"] == 1.0
    assert recall_evaluation_first["evaluation_opened"] is True
    assert recall_evaluation_first["evaluation_row_count"] == 12
    assert recall_evaluation_first["hardware_writes"] == 0
    assert recall_evaluation_first["physical_movements"] == 0
    assert recall_evaluation_first["physical_authority"] is False
    recall_evaluation_manifest_path = recall_evaluation / "manifest.json"
    recall_evaluation_manifest = json.loads(
        recall_evaluation_manifest_path.read_text()
    )
    recall_evaluation_manifest["dataset_sha256"] = "0" * 64
    recall_evaluation_manifest_path.write_bytes(
        module._canonical(recall_evaluation_manifest) + b"\n"
    )
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        module.evaluate_occlusion_recall_candidate(
            recall_evaluation, tmp_path / "recall-first",
            tmp_path / "recall-evaluation-tampered",
        )

    evaluation_first = module.evaluate_target_conditioned_fusion(
        evaluation, candidate_dir, tmp_path / "evaluation-first",
    )
    evaluation_second = module.evaluate_target_conditioned_fusion(
        evaluation, candidate_dir, tmp_path / "evaluation-second",
    )

    assert evaluation_first == evaluation_second
    assert (tmp_path / "evaluation-first" / "report.json").read_bytes() == (
        tmp_path / "evaluation-second" / "report.json"
    ).read_bytes()
    assert evaluation_first["schema"] \
        == "rocell.ai_target_conditioned_fusion_evaluation.v1"
    assert evaluation_first["evaluation_opened"] is True
    assert evaluation_first["evaluation_row_count"] == 12
    assert evaluation_first["hardware_writes"] == 0
    assert evaluation_first["physical_movements"] == 0
    assert evaluation_first["physical_authority"] is False

    manifest_path = evaluation / "manifest.json"
    tampered = json.loads(manifest_path.read_text())
    tampered["dataset_sha256"] = "0" * 64
    manifest_path.write_bytes(module._canonical(tampered) + b"\n")
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        module.evaluate_target_conditioned_fusion(
            evaluation, candidate_dir, tmp_path / "tampered-evaluation",
        )
