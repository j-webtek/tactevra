"""Build synthetic-only target-occlusion data from retained Isaac mesh evidence."""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


SCHEMA_V1 = "rocell.ai_official_mesh_occlusion_data.v1"
SCHEMA_V2 = "rocell.ai_official_mesh_occlusion_data.v2"
SCHEMA_V3 = "rocell.ai_official_mesh_occlusion_data.v3"
SCHEMA_V4 = "rocell.ai_official_mesh_occlusion_data.v4"
SCHEMA_V5 = "rocell.ai_official_mesh_occlusion_data.v5"
SCHEMA_V6 = "rocell.ai_official_mesh_occlusion_data.v6"
SCHEMA_V7 = "rocell.ai_official_mesh_occlusion_data.v7"
SCHEMA_V8 = "rocell.ai_official_mesh_occlusion_data.v8"
SCHEMA_V9 = "rocell.ai_official_mesh_occlusion_data.v9"
SCHEMA_V10 = "rocell.ai_official_mesh_occlusion_data.v10"
SCHEMA_V11 = "rocell.ai_official_mesh_occlusion_data.v11"
SCHEMA_V12 = "rocell.ai_official_mesh_occlusion_data.v12"
SCHEMA_V13 = "rocell.ai_official_mesh_occlusion_data.v13"
SCHEMA_V14 = "rocell.ai_official_mesh_occlusion_data.v14"
SCHEMA_V15 = "rocell.ai_official_mesh_occlusion_data.v15"
SCHEMA_V16 = "rocell.ai_official_mesh_occlusion_data.v16"
SOURCE_SCHEMA_V1 = "tactevra.isaac_fixed_overview_mesh_render.v1"
SOURCE_SCHEMA_V2 = "tactevra.isaac_fixed_overview_mesh_render.v2"
SOURCE_SCHEMA_V3 = "tactevra.isaac_fixed_overview_mesh_render.v3"
SOURCE_SCHEMA_V4 = "tactevra.isaac_fixed_overview_mesh_render.v4"
SOURCE_SCHEMA_V5 = "tactevra.isaac_fixed_overview_mesh_render.v5"
SOURCE_SCHEMA_V6 = "tactevra.isaac_fixed_overview_mesh_render.v6"
SOURCE_SCHEMA_V7 = "tactevra.isaac_fixed_overview_mesh_render.v7"
SOURCE_SCHEMA_V8 = "tactevra.isaac_fixed_overview_mesh_render.v8"
SOURCE_SCHEMA_V9 = "tactevra.isaac_fixed_overview_mesh_render.v9"
SOURCE_SCHEMA_V10 = "tactevra.isaac_fixed_overview_mesh_render.v10"
SOURCE_SCHEMA_V11 = "tactevra.isaac_fixed_overview_mesh_render.v11"
SOURCE_SCHEMA_V12 = "tactevra.isaac_fixed_overview_mesh_render.v12"
SOURCE_SCHEMA_V13 = "tactevra.isaac_fixed_overview_mesh_render.v13"
SOURCE_SCHEMA_V14 = "tactevra.isaac_fixed_overview_mesh_render.v14"
SOURCE_SCHEMA_V15 = "tactevra.isaac_fixed_overview_mesh_render.v15"
SOURCE_SCHEMA_V16 = "tactevra.isaac_fixed_overview_mesh_render.v16"
MAXIMUM_SAFE_REGION_OVERLAP = 0.20
BASELINE_SEED = 190
BASELINE_CROP_SIZE = 16
BASELINE_ITERATIONS = 800
BASELINE_LEARNING_RATE = 0.08
BASELINE_L2 = 0.001
SPATIAL_CROP_SIZE = 32
SPATIAL_PADDING = 24
SPATIAL_EPOCHS = 8
TARGET_IDENTITY_EPOCHS = 12
TARGET_CONDITIONED_EPOCHS = 20
TARGET_CONDITIONED_LEARNING_RATE = 0.001
TARGET_CONDITIONED_MODULATION_SCALE = 0.25
OCCLUSION_RECALL_EPOCHS = 12
OCCLUSION_RECALL_LEARNING_RATE = 0.0005
OCCLUSION_RECALL_POSITIVE_WEIGHT = 1.5
SPECIFICITY_REBALANCE_EPOCHS = 12
SPECIFICITY_REBALANCE_LEARNING_RATE = 0.00025
SPECIFICITY_REBALANCE_POSITIVE_WEIGHT = 1.0
POSE_DIVERSE_EPOCHS = 16
POSE_DIVERSE_LEARNING_RATE = 0.00035
POSE_DIVERSE_POSITIVE_WEIGHT = 1.5
GROUPED_NEIGHBORHOOD_EPOCHS = 12
GROUPED_NEIGHBORHOOD_LEARNING_RATE = 0.00015
GROUPED_NEIGHBORHOOD_POSITIVE_WEIGHT = 1.75
GROUPED_NEIGHBORHOOD_TARGET_EMPHASIS = 2.0
GROUPED_NEIGHBORHOOD_EMPHASIZED_TARGETS = (
    "MINUS", "U", "7", "1", "0", "PERIOD", "6",
)
GROUPED_NEIGHBORHOOD_BOOTSTRAP_SEED = 19016
POSE_CLUSTER_BOOTSTRAP_SEED = 19015
POSE_CLUSTER_BOOTSTRAP_SAMPLES = 2000
EXPECTED_OCCLUSION_RECALL_MODEL_SHA256 = (
    "27c7be58e11f8bf3341cb4eb56abdf7786d984e2664b6eb07d6349243730e09c"
)
EXPECTED_OCCLUSION_RECALL_SCORECARD_SHA256 = (
    "807928f2559d14fa8b0b9da1781d379650deeadb40ec8690e41484be16eaa0d4"
)
EXPECTED_SPECIFICITY_REBALANCE_MODEL_SHA256 = (
    "b20a02990d47ee87d97383d130052c4517391442d517ea94b5b5e78749a7525d"
)
EXPECTED_SPECIFICITY_REBALANCE_SCORECARD_SHA256 = (
    "d11a71c67e2f7072e52a4a28d9c2bdbf5f6da308c5704bfe47a379c79cad9f00"
)
EXPECTED_POSE_DIVERSE_MODEL_SHA256 = (
    "9e09a13fae22cbbc75d2b15d9fe2e9cfbf76638d61220d635dd31272e298cfbb"
)
EXPECTED_POSE_DIVERSE_SCORECARD_SHA256 = (
    "0079e0d7f3b7b4f77d191b7258cafbbe8a53e88441767059f6d4a63858edf490"
)
SPATIAL_BATCH_SIZE = 128
SPATIAL_LEARNING_RATE = 0.002
LEGACY_SPLITS = {
    "train": {
        "poses": ("ready", "hover_t"),
        "lighting": ("nominal", "dim", "bright"),
    },
    "evaluation": {
        "poses": ("hover_e",),
        "lighting": ("warm", "glare", "blur"),
    },
}
EXPANDED_LIGHTING = {
    "train": ("nominal", "dim", "bright"),
    "development": ("warm", "glare", "blur"),
    "evaluation": ("cool", "side_shadow", "defocus"),
}
TRANSIT_LIGHTING = {
    "train": (
        "nominal", "dim", "bright", "warm", "glare", "blur",
        "cool", "side_shadow", "defocus",
    ),
    "development": ("desaturated", "gamma_dark", "vignette"),
    "evaluation": ("low_contrast", "right_shadow", "motion_blur"),
}
SPECIFICITY_LIGHTING = {
    "train": (
        "nominal", "dim", "bright", "warm", "glare", "blur", "cool",
        "side_shadow", "defocus", "desaturated", "gamma_dark", "vignette",
        "low_contrast", "right_shadow", "motion_blur",
    ),
    "development": ("soft_neutral", "gamma_mid", "left_shadow"),
    "evaluation": ("cool_flat", "top_shadow", "vertical_motion_blur"),
}
TARGET_AWARE_LIGHTING = {
    "train": tuple(
        dict.fromkeys(
            (*SPECIFICITY_LIGHTING["train"], *SPECIFICITY_LIGHTING["development"],
             *SPECIFICITY_LIGHTING["evaluation"])
        )
    ),
    "development": ("neutral_low", "bottom_shadow", "diagonal_motion_blur"),
    "evaluation": ("green_cast", "corner_glare", "horizontal_motion_blur"),
}
PERTURBATION_LIGHTING = {
    "train": (),
    "development": TARGET_AWARE_LIGHTING["development"],
    "evaluation": (),
}
POLICY_EVALUATION_LIGHTING = {
    "train": (),
    "development": (),
    "evaluation": ("amber_cast", "center_glare", "anti_diagonal_motion_blur"),
}
HARD_NEGATIVE_LIGHTING = {
    "train": (),
    "development": (
        "amber_low_contrast", "right_center_glare", "offset_anti_diagonal_blur",
    ),
    "evaluation": (),
}
TARGET_IDENTITY_TRAINING_LIGHTING = {
    "train": (
        "amber_edge_boost", "right_glare_dim", "anti_diagonal_blur_contrast",
    ),
    "development": (),
    "evaluation": (),
}
FUSION_EVALUATION_LIGHTING = {
    "train": (),
    "development": (),
    "evaluation": (
        "blue_edge_shadow", "lower_left_glare", "vertical_blur_dim",
    ),
}
OCCLUSION_RECALL_LIGHTING = {
    "train": (
        "neutral_sharp_dim", "upper_right_soft_shadow",
        "horizontal_smear_contrast",
    ),
    "development": (
        "cool_low_contrast", "lower_right_soft_glare",
        "vertical_smear_bright",
    ),
    "evaluation": (),
}
RECALL_EVALUATION_LIGHTING = {
    "train": (),
    "development": (),
    "evaluation": (
        "upper_left_soft_vignette",
        "warm_center_bloom",
        "diagonal_smear_cool",
    ),
}
SPECIFICITY_REBALANCE_LIGHTING = {
    "train": (
        "neutral_microcontrast", "left_soft_falloff", "short_diagonal_smear",
    ),
    "development": (
        "cool_microcontrast", "right_soft_falloff", "short_vertical_smear",
    ),
    "evaluation": (),
}
REBALANCE_EVALUATION_LIGHTING = {
    "train": (),
    "development": (),
    "evaluation": (
        "neutral_edge_soft", "amber_lower_falloff", "cross_smear_cool",
    ),
}
POSE_DIVERSE_LIGHTING = {
    "train": (
        "pose_neutral_range", "pose_warm_side_falloff", "pose_diagonal_soft_blur",
    ),
    "development": (
        "pose_cool_range", "pose_lower_center_glare", "pose_vertical_soft_blur",
    ),
    "evaluation": (),
}
GROUPED_NEIGHBORHOOD_LIGHTING = {
    "train": (
        "grouped_neutral_drift", "grouped_left_warm_falloff",
        "grouped_right_cool_occluder",
    ),
    "development": (
        "grouped_overhead_low", "grouped_side_glare", "grouped_soft_focus",
    ),
    "evaluation": (),
}
NOMINAL_PIXELS_PER_MM = 2.0
MASK_OFFSET_RADII_MM = (1.0, 2.0, 4.0, 8.0)
MASK_OFFSET_DIRECTIONS = (
    (-1, -1), (0, -1), (1, -1),
    (-1, 0), (1, 0),
    (-1, 1), (0, 1), (1, 1),
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _verify_source(path: Path) -> dict[str, Any]:
    source = json.loads(path.read_text(encoding="utf-8"))
    if source.get("schema") not in {
        SOURCE_SCHEMA_V1, SOURCE_SCHEMA_V2, SOURCE_SCHEMA_V3, SOURCE_SCHEMA_V4,
        SOURCE_SCHEMA_V5, SOURCE_SCHEMA_V6,
        SOURCE_SCHEMA_V7,
        SOURCE_SCHEMA_V8,
        SOURCE_SCHEMA_V9,
        SOURCE_SCHEMA_V10,
        SOURCE_SCHEMA_V11,
        SOURCE_SCHEMA_V12,
        SOURCE_SCHEMA_V13,
        SOURCE_SCHEMA_V14,
        SOURCE_SCHEMA_V15,
        SOURCE_SCHEMA_V16,
    }:
        raise ValueError("official-mesh manifest schema mismatch")
    claimed = source.pop("receipt_sha256", None)
    if not isinstance(claimed, str) or _sha256(_canonical(source)) != claimed:
        raise ValueError("official-mesh receipt hash mismatch")
    source["receipt_sha256"] = claimed
    if source.get("result_status") != "PASS_WITH_BLOCKERS":
        raise ValueError("official-mesh source status is not admissible")
    if source.get("physical_authority") is not False or source.get("hardware_writes") != 0:
        raise ValueError("official-mesh source claims authority")
    evidence_dir = path.parent
    for artifact in source["artifact_atlases"].values():
        artifact_path = evidence_dir / artifact["path"]
        if _sha256(artifact_path.read_bytes()) != artifact["sha256"]:
            raise ValueError(f"artifact hash mismatch: {artifact_path.name}")
    return source


def _split_policy(source: dict[str, Any]) -> tuple[str, dict[str, dict[str, tuple[str, ...]]]]:
    if source["schema"] == SOURCE_SCHEMA_V1:
        return SCHEMA_V1, LEGACY_SPLITS
    pose_groups = source.get("pose_groups")
    if not isinstance(pose_groups, dict) or set(pose_groups) != {
        "training", "development", "evaluation"
    }:
        raise ValueError("expanded source must declare training/development/evaluation poses")
    normalized = {
        name: tuple(pose_groups[name])
        for name in ("training", "development", "evaluation")
    }
    flattened = [pose_id for pose_ids in normalized.values() for pose_id in pose_ids]
    rendered = [row["pose_id"] for row in source["pose_results"]]
    if len(set(flattened)) != len(flattened) or set(flattened) != set(rendered):
        raise ValueError("expanded pose groups must partition rendered poses")
    for row in source["pose_results"]:
        expected = next(name for name, poses in normalized.items() if row["pose_id"] in poses)
        if row.get("pose_group") != expected:
            raise ValueError(f"pose group mismatch: {row['pose_id']}")
    if source["schema"] == SOURCE_SCHEMA_V16:
        lighting = GROUPED_NEIGHBORHOOD_LIGHTING
        schema = SCHEMA_V16
    elif source["schema"] == SOURCE_SCHEMA_V15:
        lighting = POSE_DIVERSE_LIGHTING
        schema = SCHEMA_V15
    elif source["schema"] == SOURCE_SCHEMA_V14:
        lighting = REBALANCE_EVALUATION_LIGHTING
        schema = SCHEMA_V14
    elif source["schema"] == SOURCE_SCHEMA_V13:
        lighting = SPECIFICITY_REBALANCE_LIGHTING
        schema = SCHEMA_V13
    elif source["schema"] == SOURCE_SCHEMA_V12:
        lighting = RECALL_EVALUATION_LIGHTING
        schema = SCHEMA_V12
    elif source["schema"] == SOURCE_SCHEMA_V11:
        lighting = OCCLUSION_RECALL_LIGHTING
        schema = SCHEMA_V11
    elif source["schema"] == SOURCE_SCHEMA_V10:
        lighting = FUSION_EVALUATION_LIGHTING
        schema = SCHEMA_V10
    elif source["schema"] == SOURCE_SCHEMA_V9:
        lighting = TARGET_IDENTITY_TRAINING_LIGHTING
        schema = SCHEMA_V9
    elif source["schema"] == SOURCE_SCHEMA_V8:
        lighting = HARD_NEGATIVE_LIGHTING
        schema = SCHEMA_V8
    elif source["schema"] == SOURCE_SCHEMA_V7:
        lighting = POLICY_EVALUATION_LIGHTING
        schema = SCHEMA_V7
    elif source["schema"] == SOURCE_SCHEMA_V6:
        lighting = PERTURBATION_LIGHTING
        schema = SCHEMA_V6
    elif source["schema"] == SOURCE_SCHEMA_V5:
        lighting = TARGET_AWARE_LIGHTING
        schema = SCHEMA_V5
    elif source["schema"] == SOURCE_SCHEMA_V4:
        lighting = SPECIFICITY_LIGHTING
        schema = SCHEMA_V4
    elif source["schema"] == SOURCE_SCHEMA_V3:
        lighting = TRANSIT_LIGHTING
        schema = SCHEMA_V3
    else:
        lighting = EXPANDED_LIGHTING
        schema = SCHEMA_V2
    return schema, {
        "train": {"poses": normalized["training"], "lighting": lighting["train"]},
        "development": {
            "poses": normalized["development"],
            "lighting": lighting["development"],
        },
        "evaluation": {
            "poses": normalized["evaluation"],
            "lighting": lighting["evaluation"],
        },
    }


def _lighting(image: Image.Image, variant: str) -> Image.Image:
    rgb = image.convert("RGB")
    if variant == "nominal":
        return rgb
    if variant == "dim":
        return ImageEnhance.Brightness(rgb).enhance(0.62)
    if variant == "bright":
        return ImageEnhance.Brightness(rgb).enhance(1.28)
    if variant == "warm":
        red, green, blue = rgb.split()
        return Image.merge("RGB", (
            red.point(lambda value: min(255, round(value * 1.10))),
            green.point(lambda value: min(255, round(value * 1.02))),
            blue.point(lambda value: round(value * 0.86)),
        ))
    if variant == "glare":
        overlay = Image.new("RGB", rgb.size, "white")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).ellipse((1080, 80, 1780, 760), fill=145)
        return Image.composite(overlay, rgb, alpha)
    if variant == "blur":
        return rgb.filter(ImageFilter.GaussianBlur(radius=1.4))
    if variant == "cool":
        red, green, blue = rgb.split()
        return Image.merge("RGB", (
            red.point(lambda value: round(value * 0.84)),
            green.point(lambda value: min(255, round(value * 1.01))),
            blue.point(lambda value: min(255, round(value * 1.12))),
        ))
    if variant == "side_shadow":
        overlay = Image.new("RGB", rgb.size, "black")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((0, 0), (round(rgb.width * 0.58), 0),
             (round(rgb.width * 0.38), rgb.height), (0, rgb.height)),
            fill=105,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "defocus":
        return rgb.filter(ImageFilter.GaussianBlur(radius=2.6))
    if variant == "desaturated":
        return ImageEnhance.Color(rgb).enhance(0.22)
    if variant == "gamma_dark":
        return rgb.point(lambda value: round(255 * (value / 255) ** 1.45))
    if variant == "vignette":
        y, x = np.ogrid[:rgb.height, :rgb.width]
        dx = (x - (rgb.width - 1) / 2) / (rgb.width / 2)
        dy = (y - (rgb.height - 1) / 2) / (rgb.height / 2)
        alpha = np.clip((dx * dx + dy * dy) * 105, 0, 105).astype(np.uint8)
        return Image.composite(Image.new("RGB", rgb.size, "black"), rgb, Image.fromarray(alpha))
    if variant == "low_contrast":
        return ImageEnhance.Contrast(rgb).enhance(0.48)
    if variant == "right_shadow":
        overlay = Image.new("RGB", rgb.size, "black")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((round(rgb.width * 0.44), 0), (rgb.width, 0),
             (rgb.width, rgb.height), (round(rgb.width * 0.62), rgb.height)),
            fill=115,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "motion_blur":
        weights = [0.0] * 25
        weights[10:15] = [1.0] * 5
        return rgb.filter(ImageFilter.Kernel((5, 5), weights, scale=5.0))
    if variant == "soft_neutral":
        return ImageEnhance.Contrast(ImageEnhance.Brightness(rgb).enhance(0.96)).enhance(0.84)
    if variant == "gamma_mid":
        return rgb.point(lambda value: round(255 * (value / 255) ** 0.82))
    if variant == "left_shadow":
        overlay = Image.new("RGB", rgb.size, "black")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((0, 0), (round(rgb.width * 0.50), 0),
             (round(rgb.width * 0.34), rgb.height), (0, rgb.height)),
            fill=82,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "cool_flat":
        red, green, blue = rgb.split()
        cooled = Image.merge("RGB", (
            red.point(lambda value: round(value * 0.91)),
            green,
            blue.point(lambda value: min(255, round(value * 1.07))),
        ))
        return ImageEnhance.Contrast(cooled).enhance(0.72)
    if variant == "top_shadow":
        overlay = Image.new("RGB", rgb.size, "black")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((0, 0), (rgb.width, 0), (rgb.width, round(rgb.height * 0.42)),
             (0, round(rgb.height * 0.58))),
            fill=92,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "vertical_motion_blur":
        weights = [0.0] * 25
        for index in (2, 7, 12, 17, 22):
            weights[index] = 1.0
        return rgb.filter(ImageFilter.Kernel((5, 5), weights, scale=5.0))
    if variant == "neutral_low":
        return ImageEnhance.Contrast(ImageEnhance.Brightness(rgb).enhance(0.90)).enhance(0.66)
    if variant == "bottom_shadow":
        overlay = Image.new("RGB", rgb.size, "black")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((0, round(rgb.height * 0.56)), (rgb.width, round(rgb.height * 0.42)),
             (rgb.width, rgb.height), (0, rgb.height)),
            fill=96,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "diagonal_motion_blur":
        weights = [0.0] * 25
        for index in (0, 6, 12, 18, 24):
            weights[index] = 1.0
        return rgb.filter(ImageFilter.Kernel((5, 5), weights, scale=5.0))
    if variant == "green_cast":
        red, green, blue = rgb.split()
        return Image.merge("RGB", (
            red.point(lambda value: round(value * 0.92)),
            green.point(lambda value: min(255, round(value * 1.08))),
            blue.point(lambda value: round(value * 0.94)),
        ))
    if variant == "corner_glare":
        overlay = Image.new("RGB", rgb.size, "white")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).ellipse((-180, -120, 760, 680), fill=118)
        return Image.composite(overlay, rgb, alpha)
    if variant == "horizontal_motion_blur":
        weights = [0.0] * 25
        weights[10:15] = [1.0] * 5
        return rgb.filter(ImageFilter.Kernel((5, 5), weights, scale=5.0))
    if variant == "amber_cast":
        red, green, blue = rgb.split()
        return Image.merge("RGB", (
            red.point(lambda value: min(255, round(value * 1.09))),
            green.point(lambda value: min(255, round(value * 1.03))),
            blue.point(lambda value: round(value * 0.82)),
        ))
    if variant == "center_glare":
        overlay = Image.new("RGB", rgb.size, "white")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).ellipse(
            (round(rgb.width * 0.28), round(rgb.height * 0.18),
             round(rgb.width * 0.78), round(rgb.height * 0.82)),
            fill=102,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "anti_diagonal_motion_blur":
        weights = [0.0] * 25
        for index in (4, 8, 12, 16, 20):
            weights[index] = 1.0
        return rgb.filter(ImageFilter.Kernel((5, 5), weights, scale=5.0))
    if variant == "amber_low_contrast":
        red, green, blue = rgb.split()
        amber = Image.merge("RGB", (
            red.point(lambda value: min(255, round(value * 1.06))),
            green.point(lambda value: min(255, round(value * 1.01))),
            blue.point(lambda value: round(value * 0.86)),
        ))
        return ImageEnhance.Contrast(amber).enhance(0.74)
    if variant == "right_center_glare":
        overlay = Image.new("RGB", rgb.size, "white")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).ellipse(
            (round(rgb.width * 0.43), round(rgb.height * 0.12),
             round(rgb.width * 0.92), round(rgb.height * 0.78)),
            fill=96,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "offset_anti_diagonal_blur":
        weights = [0.0] * 25
        for index in (3, 7, 11, 15, 19):
            weights[index] = 1.0
        return rgb.filter(ImageFilter.Kernel((5, 5), weights, scale=5.0))
    if variant == "amber_edge_boost":
        red, green, blue = rgb.split()
        amber = Image.merge("RGB", (
            red.point(lambda value: min(255, round(value * 1.08))),
            green.point(lambda value: min(255, round(value * 1.02))),
            blue.point(lambda value: round(value * 0.84)),
        ))
        return ImageEnhance.Sharpness(ImageEnhance.Contrast(amber).enhance(0.80)).enhance(1.35)
    if variant == "right_glare_dim":
        dimmed = ImageEnhance.Brightness(rgb).enhance(0.88)
        overlay = Image.new("RGB", rgb.size, "white")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).ellipse(
            (round(rgb.width * 0.48), round(rgb.height * 0.16),
             round(rgb.width * 0.96), round(rgb.height * 0.80)),
            fill=86,
        )
        return Image.composite(overlay, dimmed, alpha)
    if variant == "anti_diagonal_blur_contrast":
        weights = [0.0] * 25
        for index in (4, 8, 12, 16, 20):
            weights[index] = 1.0
        blurred = rgb.filter(ImageFilter.Kernel((5, 5), weights, scale=5.0))
        return ImageEnhance.Contrast(blurred).enhance(0.82)
    if variant == "blue_edge_shadow":
        red, green, blue = rgb.split()
        cooled = Image.merge("RGB", (
            red.point(lambda value: round(value * 0.88)),
            green.point(lambda value: round(value * 0.97)),
            blue.point(lambda value: min(255, round(value * 1.10))),
        ))
        overlay = Image.new("RGB", rgb.size, "black")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((0, 0), (round(rgb.width * 0.36), 0),
             (round(rgb.width * 0.20), rgb.height), (0, rgb.height)),
            fill=74,
        )
        return Image.composite(overlay, cooled, alpha)
    if variant == "lower_left_glare":
        overlay = Image.new("RGB", rgb.size, "white")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).ellipse(
            (-round(rgb.width * 0.08), round(rgb.height * 0.38),
             round(rgb.width * 0.52), round(rgb.height * 1.08)),
            fill=91,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "vertical_blur_dim":
        weights = [0.0] * 25
        for index in (2, 7, 12, 17, 22):
            weights[index] = 1.0
        blurred = rgb.filter(ImageFilter.Kernel((5, 5), weights, scale=5.0))
        return ImageEnhance.Brightness(blurred).enhance(0.91)
    if variant == "neutral_sharp_dim":
        dimmed = ImageEnhance.Brightness(rgb).enhance(0.86)
        return ImageEnhance.Sharpness(dimmed).enhance(1.28)
    if variant == "upper_right_soft_shadow":
        overlay = Image.new("RGB", rgb.size, "black")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((round(rgb.width * 0.56), 0), (rgb.width, 0),
             (rgb.width, round(rgb.height * 0.62)),
             (round(rgb.width * 0.72), round(rgb.height * 0.48))),
            fill=68,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "horizontal_smear_contrast":
        weights = [0.0] * 25
        weights[10:15] = [1.0] * 5
        blurred = rgb.filter(ImageFilter.Kernel((5, 5), weights, scale=5.0))
        return ImageEnhance.Contrast(blurred).enhance(0.88)
    if variant == "cool_low_contrast":
        red, green, blue = rgb.split()
        cooled = Image.merge("RGB", (
            red.point(lambda value: round(value * 0.90)),
            green.point(lambda value: round(value * 0.98)),
            blue.point(lambda value: min(255, round(value * 1.08))),
        ))
        return ImageEnhance.Contrast(cooled).enhance(0.78)
    if variant == "lower_right_soft_glare":
        overlay = Image.new("RGB", rgb.size, "white")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).ellipse(
            (round(rgb.width * 0.48), round(rgb.height * 0.44),
             round(rgb.width * 1.08), round(rgb.height * 1.12)),
            fill=82,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "vertical_smear_bright":
        weights = [0.0] * 25
        for index in (2, 7, 12, 17, 22):
            weights[index] = 1.0
        blurred = rgb.filter(ImageFilter.Kernel((5, 5), weights, scale=5.0))
        return ImageEnhance.Brightness(blurred).enhance(1.08)
    if variant == "upper_left_soft_vignette":
        overlay = Image.new("RGB", rgb.size, "black")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).ellipse(
            (round(rgb.width * -0.18), round(rgb.height * -0.22),
             round(rgb.width * 0.58), round(rgb.height * 0.64)),
            fill=58,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "warm_center_bloom":
        overlay = Image.new("RGB", rgb.size, (255, 236, 210))
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).ellipse(
            (round(rgb.width * 0.22), round(rgb.height * 0.18),
             round(rgb.width * 0.82), round(rgb.height * 0.84)),
            fill=66,
        )
        bloomed = Image.composite(overlay, rgb, alpha)
        return ImageEnhance.Contrast(bloomed).enhance(0.91)
    if variant == "diagonal_smear_cool":
        weights = [0.0] * 25
        for index in (0, 6, 12, 18, 24):
            weights[index] = 1.0
        blurred = rgb.filter(ImageFilter.Kernel((5, 5), weights, scale=5.0))
        red, green, blue = blurred.split()
        return Image.merge("RGB", (
            red.point(lambda value: round(value * 0.92)),
            green.point(lambda value: round(value * 0.98)),
            blue.point(lambda value: min(255, round(value * 1.06))),
        ))
    if variant == "neutral_microcontrast":
        adjusted = ImageEnhance.Brightness(rgb).enhance(0.96)
        return ImageEnhance.Contrast(adjusted).enhance(1.08)
    if variant == "left_soft_falloff":
        overlay = Image.new("RGB", rgb.size, "black")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((0, 0), (round(rgb.width * 0.34), 0),
             (round(rgb.width * 0.22), rgb.height), (0, rgb.height)),
            fill=52,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "short_diagonal_smear":
        weights = [0.0] * 9
        for index in (0, 4, 8):
            weights[index] = 1.0
        return rgb.filter(ImageFilter.Kernel((3, 3), weights, scale=3.0))
    if variant == "cool_microcontrast":
        red, green, blue = rgb.split()
        cooled = Image.merge("RGB", (
            red.point(lambda value: round(value * 0.95)),
            green,
            blue.point(lambda value: min(255, round(value * 1.04))),
        ))
        return ImageEnhance.Contrast(cooled).enhance(1.05)
    if variant == "right_soft_falloff":
        overlay = Image.new("RGB", rgb.size, "black")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((round(rgb.width * 0.66), 0), (rgb.width, 0),
             (rgb.width, rgb.height), (round(rgb.width * 0.78), rgb.height)),
            fill=52,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "short_vertical_smear":
        weights = [0.0] * 9
        for index in (1, 4, 7):
            weights[index] = 1.0
        return rgb.filter(ImageFilter.Kernel((3, 3), weights, scale=3.0))
    if variant == "neutral_edge_soft":
        return ImageEnhance.Sharpness(
            ImageEnhance.Contrast(rgb).enhance(0.92)
        ).enhance(0.82)
    if variant == "amber_lower_falloff":
        red, green, blue = rgb.split()
        amber = Image.merge("RGB", (
            red.point(lambda value: min(255, round(value * 1.05))),
            green.point(lambda value: min(255, round(value * 1.01))),
            blue.point(lambda value: round(value * 0.90)),
        ))
        overlay = Image.new("RGB", rgb.size, "black")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((0, round(rgb.height * 0.68)),
             (rgb.width, round(rgb.height * 0.54)),
             (rgb.width, rgb.height), (0, rgb.height)),
            fill=48,
        )
        return Image.composite(overlay, amber, alpha)
    if variant == "cross_smear_cool":
        weights = [0.0] * 9
        for index in (1, 3, 4, 5, 7):
            weights[index] = 1.0
        blurred = rgb.filter(ImageFilter.Kernel((3, 3), weights, scale=5.0))
        red, green, blue = blurred.split()
        return Image.merge("RGB", (
            red.point(lambda value: round(value * 0.96)),
            green,
            blue.point(lambda value: min(255, round(value * 1.03))),
        ))
    if variant == "pose_neutral_range":
        adjusted = ImageEnhance.Brightness(rgb).enhance(0.93)
        return ImageEnhance.Contrast(adjusted).enhance(1.04)
    if variant == "pose_warm_side_falloff":
        red, green, blue = rgb.split()
        warmed = Image.merge("RGB", (
            red.point(lambda value: min(255, round(value * 1.04))),
            green,
            blue.point(lambda value: round(value * 0.93)),
        ))
        overlay = Image.new("RGB", rgb.size, "black")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((0, 0), (round(rgb.width * 0.25), 0),
             (round(rgb.width * 0.38), rgb.height), (0, rgb.height)),
            fill=44,
        )
        return Image.composite(overlay, warmed, alpha)
    if variant == "pose_diagonal_soft_blur":
        weights = [0.0] * 9
        for index in (0, 4, 8):
            weights[index] = 1.0
        blurred = rgb.filter(ImageFilter.Kernel((3, 3), weights, scale=3.0))
        return ImageEnhance.Contrast(blurred).enhance(0.94)
    if variant == "pose_cool_range":
        red, green, blue = rgb.split()
        cooled = Image.merge("RGB", (
            red.point(lambda value: round(value * 0.94)),
            green.point(lambda value: round(value * 0.99)),
            blue.point(lambda value: min(255, round(value * 1.05))),
        ))
        return ImageEnhance.Brightness(cooled).enhance(0.97)
    if variant == "pose_lower_center_glare":
        overlay = Image.new("RGB", rgb.size, "white")
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).ellipse(
            (round(rgb.width * 0.24), round(rgb.height * 0.48),
             round(rgb.width * 0.76), round(rgb.height * 1.02)),
            fill=74,
        )
        return Image.composite(overlay, rgb, alpha)
    if variant == "pose_vertical_soft_blur":
        weights = [0.0] * 9
        for index in (1, 4, 7):
            weights[index] = 1.0
        blurred = rgb.filter(ImageFilter.Kernel((3, 3), weights, scale=3.0))
        return ImageEnhance.Brightness(blurred).enhance(1.03)
    if variant == "grouped_neutral_drift":
        return ImageEnhance.Contrast(
            ImageEnhance.Brightness(rgb).enhance(0.95)
        ).enhance(1.06)
    if variant == "grouped_left_warm_falloff":
        red, green, blue = rgb.split()
        warmed = Image.merge("RGB", (
            red.point(lambda value: min(255, round(value * 1.05))),
            green,
            blue.point(lambda value: round(value * 0.92)),
        ))
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((0, 0), (round(rgb.width * 0.32), 0),
             (round(rgb.width * 0.45), rgb.height), (0, rgb.height)), fill=48,
        )
        return Image.composite(Image.new("RGB", rgb.size, "black"), warmed, alpha)
    if variant == "grouped_right_cool_occluder":
        red, green, blue = rgb.split()
        cooled = Image.merge("RGB", (
            red.point(lambda value: round(value * 0.93)), green,
            blue.point(lambda value: min(255, round(value * 1.05))),
        ))
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((round(rgb.width * 0.72), 0), (rgb.width, 0),
             (rgb.width, rgb.height), (round(rgb.width * 0.82), rgb.height)), fill=56,
        )
        return Image.composite(Image.new("RGB", rgb.size, "black"), cooled, alpha)
    if variant == "grouped_overhead_low":
        dimmed = ImageEnhance.Brightness(rgb).enhance(0.84)
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).polygon(
            ((0, 0), (rgb.width, 0), (rgb.width, round(rgb.height * 0.34)),
             (0, round(rgb.height * 0.48))), fill=50,
        )
        return Image.composite(Image.new("RGB", rgb.size, "black"), dimmed, alpha)
    if variant == "grouped_side_glare":
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).ellipse(
            (round(rgb.width * 0.52), round(rgb.height * 0.08),
             round(rgb.width * 1.02), round(rgb.height * 0.92)), fill=70,
        )
        return Image.composite(Image.new("RGB", rgb.size, "white"), rgb, alpha)
    if variant == "grouped_soft_focus":
        return ImageEnhance.Contrast(
            rgb.filter(ImageFilter.GaussianBlur(radius=1.1))
        ).enhance(0.92)
    raise ValueError(f"unknown lighting variant: {variant}")


def build(source_manifest: Path, output_dir: Path) -> dict[str, Any]:
    source_manifest = source_manifest.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / "images"
    image_dir.mkdir()
    source = _verify_source(source_manifest)
    schema, split_policy = _split_policy(source)
    rgb_atlases: dict[str, Any] = {}
    pose_by_id = {row["pose_id"]: row for row in source["pose_results"]}

    image_records = []
    split_rows: dict[str, list[dict[str, Any]]] = {}
    for split, policy in split_policy.items():
        rows = []
        for pose_id in policy["poses"]:
            pose = pose_by_id[pose_id]
            atlas_key = pose.get("rgb_atlas_key", "rgb")
            if atlas_key not in rgb_atlases:
                rgb_path = (
                    source_manifest.parent
                    / source["artifact_atlases"][atlas_key]["path"]
                )
                rgb_atlases[atlas_key] = Image.open(rgb_path).convert("RGB")
            crop = rgb_atlases[atlas_key].crop(tuple(pose["atlas_crop_px"]))
            for variant in policy["lighting"]:
                transformed = _lighting(crop, variant)
                image_name = f"{split}__{pose_id}__{variant}.jpg"
                image_path = image_dir / image_name
                transformed.save(
                    image_path, "JPEG", quality=92, optimize=False,
                    progressive=False, subsampling=0,
                )
                image_sha = _sha256(image_path.read_bytes())
                image_records.append({
                    "split": split,
                    "pose_id": pose_id,
                    "lighting_variant": variant,
                    "path": f"images/{image_name}",
                    "sha256": image_sha,
                })
                for target in pose["targets"]:
                    overlap = target["safe_region_official_mesh_overlap_fraction"]
                    center_occluded = target["center_occluded_by_official_mesh"]
                    abstain = center_occluded or overlap > MAXIMUM_SAFE_REGION_OVERLAP
                    rows.append({
                        "id": f"{split}-{pose_id}-{variant}-{target['device']}-{target['target_id']}",
                        "image_path": f"images/{image_name}",
                        "image_sha256": image_sha,
                        "pose_id": pose_id,
                        "lighting_variant": variant,
                        "device": target["device"],
                        "target_id": target["target_id"],
                        "center_px": target["center_px"],
                        "safe_polygon_px": target["safe_polygon_px"],
                        "center_occluded": center_occluded,
                        "safe_region_overlap_fraction": overlap,
                        "decision": "abstain" if abstain else "target_visible",
                        "reason": "robot_occlusion" if abstain else None,
                        "synthetic_only": True,
                    })
        raw = b"".join(_canonical(row) + b"\n" for row in rows)
        (output_dir / f"{split}.jsonl").write_bytes(raw)
        split_rows[split] = rows

    pose_groups = [set(policy["poses"]) for policy in split_policy.values()]
    lighting_groups = [set(policy["lighting"]) for policy in split_policy.values()]
    if any(
        left & right
        for index, left in enumerate(pose_groups)
        for right in pose_groups[index + 1:]
    ) or any(
        left & right
        for index, left in enumerate(lighting_groups)
        for right in lighting_groups[index + 1:]
    ):
        raise RuntimeError("pose or lighting group leakage")

    manifest: dict[str, Any] = {
        "schema": schema,
        "scope": "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION",
        "source_manifest_sha256": _sha256(source_manifest.read_bytes()),
        "source_receipt_sha256": source["receipt_sha256"],
        "target_catalog_sha256": source["target_catalog_sha256"],
        "maximum_safe_region_overlap": MAXIMUM_SAFE_REGION_OVERLAP,
        "split_policy": split_policy,
        "pose_groups_disjoint": True,
        "lighting_groups_disjoint": True,
        "images": image_records,
        "splits": {},
        "authority": {
            "hardware_accessed": False,
            "hardware_write_count": 0,
            "physical_movement_count": 0,
            "can_release_physical_gates": False,
        },
        "limitations": [
            "images, geometry, lighting transformations, and occlusion labels are synthetic",
            "camera and robot placement are nominal and unmeasured",
            "tool and camera-support geometry are absent",
            "evaluation split is a synthetic development fixture, not deployment qualification",
        ],
    }
    for split, rows in split_rows.items():
        payload = (output_dir / f"{split}.jsonl").read_bytes()
        manifest["splits"][split] = {
            "path": f"{split}.jsonl",
            "sha256": _sha256(payload),
            "count": len(rows),
            "abstain_count": sum(row["decision"] == "abstain" for row in rows),
            "visible_count": sum(row["decision"] == "target_visible" for row in rows),
        }
    manifest["dataset_sha256"] = _sha256(_canonical(manifest))
    (output_dir / "manifest.json").write_bytes(_canonical(manifest) + b"\n")
    return manifest


def _load_rows(dataset_dir: Path, split: str, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    path = dataset_dir / manifest["splits"][split]["path"]
    payload = path.read_bytes()
    if _sha256(payload) != manifest["splits"][split]["sha256"]:
        raise ValueError(f"{split} data hash mismatch")
    return [json.loads(line) for line in payload.decode("utf-8").splitlines() if line]


def _features(
    dataset_dir: Path, rows: list[dict[str, Any]], family: str = "rgb_raw"
) -> tuple[np.ndarray, np.ndarray]:
    cache: dict[str, Image.Image] = {}
    vectors = []
    labels = []
    for row in rows:
        image_path = dataset_dir / row["image_path"]
        image = cache.setdefault(row["image_path"], Image.open(image_path).convert("RGB"))
        if _sha256(image_path.read_bytes()) != row["image_sha256"]:
            raise ValueError(f"image hash mismatch: {row['image_path']}")
        polygon = row["safe_polygon_px"]
        x_values = [point[0] for point in polygon]
        y_values = [point[1] for point in polygon]
        padding = 12
        box = (
            max(0, int(min(x_values)) - padding),
            max(0, int(min(y_values)) - padding),
            min(image.width, int(max(x_values)) + padding + 1),
            min(image.height, int(max(y_values)) + padding + 1),
        )
        crop = image.crop(box).resize(
            (BASELINE_CROP_SIZE, BASELINE_CROP_SIZE), Image.Resampling.BILINEAR
        )
        array = np.asarray(crop, dtype=np.float64) / 255.0
        if family == "rgb_raw":
            vector = array.reshape(-1)
        elif family == "chromatic_gray_edges":
            chromatic = array / np.maximum(array.sum(axis=2, keepdims=True), 1e-8)
            gray = array @ np.asarray((0.299, 0.587, 0.114))
            normalized = (gray - gray.mean()) / max(float(gray.std()), 1e-6)
            horizontal = np.diff(normalized, axis=1, prepend=normalized[:, :1])
            vertical = np.diff(normalized, axis=0, prepend=normalized[:1, :])
            vector = np.concatenate((
                chromatic.reshape(-1), normalized.reshape(-1),
                horizontal.reshape(-1), vertical.reshape(-1),
            ))
        else:
            raise ValueError(f"unknown feature family: {family}")
        vectors.append(vector)
        labels.append(row["decision"] == "abstain")
    return np.stack(vectors), np.asarray(labels, dtype=np.float64)


def _spatial_crops(
    dataset_dir: Path, rows: list[dict[str, Any]]
) -> tuple[np.ndarray, np.ndarray]:
    cache: dict[str, Image.Image] = {}
    verified: set[str] = set()
    crops = []
    labels = []
    for row in rows:
        image_path = dataset_dir / row["image_path"]
        if row["image_path"] not in verified:
            if _sha256(image_path.read_bytes()) != row["image_sha256"]:
                raise ValueError(f"image hash mismatch: {row['image_path']}")
            verified.add(row["image_path"])
        image = cache.setdefault(row["image_path"], Image.open(image_path).convert("RGB"))
        polygon = row["safe_polygon_px"]
        x_values = [point[0] for point in polygon]
        y_values = [point[1] for point in polygon]
        box = (
            max(0, int(min(x_values)) - SPATIAL_PADDING),
            max(0, int(min(y_values)) - SPATIAL_PADDING),
            min(image.width, int(max(x_values)) + SPATIAL_PADDING + 1),
            min(image.height, int(max(y_values)) + SPATIAL_PADDING + 1),
        )
        crop = image.crop(box).resize(
            (SPATIAL_CROP_SIZE, SPATIAL_CROP_SIZE), Image.Resampling.BILINEAR
        )
        crops.append(np.asarray(crop, dtype=np.float32).transpose(2, 0, 1) / 255.0)
        labels.append(row["decision"] == "abstain")
    return np.stack(crops), np.asarray(labels, dtype=np.float32)


def _target_aware_crops(
    dataset_dir: Path,
    rows: list[dict[str, Any]],
    localization_offset_px: tuple[float, float] = (0.0, 0.0),
    *,
    row_offsets_px: list[tuple[float, float]] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return RGB crops plus a possibly displaced catalog safe-region channel."""
    offsets = row_offsets_px or [localization_offset_px] * len(rows)
    if len(offsets) != len(rows):
        raise ValueError("row offset count must match crop row count")
    displaced_rows = []
    for row, (offset_x, offset_y) in zip(rows, offsets, strict=True):
        displaced = dict(row)
        displaced["safe_polygon_px"] = [
            [point[0] + offset_x, point[1] + offset_y]
            for point in row["safe_polygon_px"]
        ]
        displaced_rows.append(displaced)
    rgb, labels = _spatial_crops(dataset_dir, displaced_rows)
    masks = []
    image_sizes: dict[str, tuple[int, int]] = {}
    for row in displaced_rows:
        polygon = row["safe_polygon_px"]
        x_values = [point[0] for point in polygon]
        y_values = [point[1] for point in polygon]
        image_path = dataset_dir / row["image_path"]
        if row["image_path"] not in image_sizes:
            with Image.open(image_path) as image:
                image_sizes[row["image_path"]] = image.size
        width, height = image_sizes[row["image_path"]]
        box = (
            max(0, int(min(x_values)) - SPATIAL_PADDING),
            max(0, int(min(y_values)) - SPATIAL_PADDING),
            min(width, int(max(x_values)) + SPATIAL_PADDING + 1),
            min(height, int(max(y_values)) + SPATIAL_PADDING + 1),
        )
        mask = Image.new("L", (box[2] - box[0], box[3] - box[1]), 0)
        ImageDraw.Draw(mask).polygon(
            [(point[0] - box[0], point[1] - box[1]) for point in polygon],
            fill=255,
        )
        resized = mask.resize(
            (SPATIAL_CROP_SIZE, SPATIAL_CROP_SIZE), Image.Resampling.NEAREST
        )
        masks.append(np.asarray(resized, dtype=np.float32)[None, :, :] / 255.0)
    return np.concatenate((rgb, np.stack(masks)), axis=1), labels


def _target_identity_catalog(*row_groups: list[dict[str, Any]]) -> tuple[str, ...]:
    """Return the stable device-qualified target vocabulary used by the descriptor."""
    return tuple(sorted({
        f"{row['device']}:{row['target_id']}"
        for rows in row_groups
        for row in rows
    }))


def _target_identity_descriptors(
    dataset_dir: Path,
    rows: list[dict[str, Any]],
    catalog: tuple[str, ...],
) -> np.ndarray:
    """Encode exact target identity and nominal full-frame target geometry."""
    index_by_target = {target: index for index, target in enumerate(catalog)}
    if len(index_by_target) != len(catalog):
        raise ValueError("target identity catalog contains duplicates")
    image_sizes: dict[str, tuple[int, int]] = {}
    descriptors = np.zeros((len(rows), len(catalog) + 4), dtype=np.float32)
    for row_index, row in enumerate(rows):
        target = f"{row['device']}:{row['target_id']}"
        target_index = index_by_target.get(target)
        if target_index is None:
            raise ValueError(f"target identity missing from catalog: {target}")
        descriptors[row_index, target_index] = 1.0
        if row["image_path"] not in image_sizes:
            with Image.open(dataset_dir / row["image_path"]) as image:
                image_sizes[row["image_path"]] = image.size
        image_width, image_height = image_sizes[row["image_path"]]
        x_values = [float(point[0]) for point in row["safe_polygon_px"]]
        y_values = [float(point[1]) for point in row["safe_polygon_px"]]
        center_x, center_y = (float(value) for value in row["center_px"])
        descriptors[row_index, len(catalog):] = (
            center_x / image_width,
            center_y / image_height,
            (max(x_values) - min(x_values)) / image_width,
            (max(y_values) - min(y_values)) / image_height,
        )
    return descriptors


def _declared_mask_offsets() -> list[dict[str, float]]:
    offsets = [{"x_mm": 0.0, "y_mm": 0.0, "x_px": 0.0, "y_px": 0.0}]
    for radius in MASK_OFFSET_RADII_MM:
        for direction_x, direction_y in MASK_OFFSET_DIRECTIONS:
            x_mm = radius * direction_x
            y_mm = radius * direction_y
            offsets.append({
                "x_mm": x_mm,
                "y_mm": y_mm,
                "x_px": x_mm * NOMINAL_PIXELS_PER_MM,
                "y_px": y_mm * NOMINAL_PIXELS_PER_MM,
            })
    return offsets


def _metrics(rows: list[dict[str, Any]], labels: np.ndarray,
             probabilities: np.ndarray, threshold: float = 0.5) -> dict[str, Any]:
    predicted = probabilities >= threshold
    expected = labels.astype(bool)
    tp = int(np.count_nonzero(predicted & expected))
    tn = int(np.count_nonzero(~predicted & ~expected))
    fp = int(np.count_nonzero(predicted & ~expected))
    fn = int(np.count_nonzero(~predicted & expected))
    bins = []
    ece = 0.0
    for lower in np.linspace(0.0, 0.9, 10):
        upper = lower + 0.1
        selected = (probabilities >= lower) & (
            probabilities <= upper if upper >= 1.0 else probabilities < upper
        )
        count = int(np.count_nonzero(selected))
        if not count:
            continue
        confidence = float(probabilities[selected].mean())
        rate = float(labels[selected].mean())
        ece += count / len(labels) * abs(confidence - rate)
        bins.append({
            "lower": float(lower), "upper": float(min(1.0, upper)),
            "count": count, "mean_probability": confidence,
            "abstain_rate": rate,
        })
    failures = [
        {
            "id": row["id"],
            "expected": "abstain" if bool(label) else "target_visible",
            "predicted": "abstain" if bool(prediction) else "target_visible",
            "abstain_probability": float(probability),
        }
        for row, label, prediction, probability in zip(
            rows, expected, predicted, probabilities, strict=True
        )
        if prediction != label
    ]
    return {
        "count": len(rows),
        "confusion": {
            "true_abstain": tp, "true_visible": tn,
            "false_abstain": fp, "missed_abstain": fn,
        },
        "accuracy": (tp + tn) / len(rows),
        "balanced_accuracy": 0.5 * (tp / (tp + fn) + tn / (tn + fp)),
        "brier_score": float(np.mean((probabilities - labels) ** 2)),
        "expected_calibration_error_10_bin": ece,
        "calibration_bins": bins,
        "failures": failures,
    }


def _fit_logistic(features: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = features.mean(axis=0)
    scale = features.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (features - mean) / scale
    design = np.column_stack((np.ones(len(standardized)), standardized))
    weights = np.zeros(design.shape[1], dtype=np.float64)
    positives = int(labels.sum())
    negatives = len(labels) - positives
    sample_weights = np.where(
        labels == 1.0, len(labels) / (2 * positives), len(labels) / (2 * negatives)
    )
    for _ in range(BASELINE_ITERATIONS):
        logits = np.clip(design @ weights, -30.0, 30.0)
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        gradient = design.T @ ((probabilities - labels) * sample_weights) / len(labels)
        gradient[1:] += BASELINE_L2 * weights[1:]
        weights -= BASELINE_LEARNING_RATE * gradient
    return weights, mean, scale


def _probabilities(
    features: np.ndarray, weights: np.ndarray, mean: np.ndarray, scale: np.ndarray
) -> np.ndarray:
    design = np.column_stack((np.ones(len(features)), (features - mean) / scale))
    return 1.0 / (1.0 + np.exp(-np.clip(design @ weights, -30.0, 30.0)))


def _select_threshold(labels: np.ndarray, probabilities: np.ndarray) -> float:
    candidates = []
    expected = labels.astype(bool)
    positives = int(expected.sum())
    for threshold in (round(value, 2) for value in np.linspace(0.05, 0.95, 19)):
        predicted = probabilities >= threshold
        tp = int(np.count_nonzero(predicted & expected))
        tn = int(np.count_nonzero(~predicted & ~expected))
        fp = int(np.count_nonzero(predicted & ~expected))
        fn = int(np.count_nonzero(~predicted & expected))
        missed_rate = fn / positives
        balanced = 0.5 * (tp / (tp + fn) + tn / (tn + fp))
        candidates.append(((missed_rate <= 0.05, balanced, -fp, -fn), float(threshold)))
    return max(candidates)[1]


def train_baseline(dataset_dir: Path, output_dir: Path) -> dict[str, Any]:
    dataset_dir = dataset_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("baseline output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_manifest_path = dataset_dir / "manifest.json"
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = dataset_manifest.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) or _sha256(_canonical(dataset_manifest)) != claimed_dataset_sha:
        raise ValueError("dataset manifest hash mismatch")
    dataset_manifest["dataset_sha256"] = claimed_dataset_sha
    if dataset_manifest.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("dataset scope mismatch")
    train_rows = _load_rows(dataset_dir, "train", dataset_manifest)
    evaluation_rows = _load_rows(dataset_dir, "evaluation", dataset_manifest)
    train_x, train_y = _features(dataset_dir, train_rows)
    evaluation_x, evaluation_y = _features(dataset_dir, evaluation_rows)
    mean = train_x.mean(axis=0)
    scale = train_x.std(axis=0)
    scale[scale < 1e-8] = 1.0
    train_x = (train_x - mean) / scale
    evaluation_x = (evaluation_x - mean) / scale
    train_x = np.column_stack((np.ones(len(train_x)), train_x))
    evaluation_x = np.column_stack((np.ones(len(evaluation_x)), evaluation_x))

    weights = np.zeros(train_x.shape[1], dtype=np.float64)
    positives = int(train_y.sum())
    negatives = len(train_y) - positives
    sample_weights = np.where(
        train_y == 1.0, len(train_y) / (2 * positives), len(train_y) / (2 * negatives)
    )
    for _ in range(BASELINE_ITERATIONS):
        logits = np.clip(train_x @ weights, -30.0, 30.0)
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        gradient = train_x.T @ ((probabilities - train_y) * sample_weights) / len(train_y)
        gradient[1:] += BASELINE_L2 * weights[1:]
        weights -= BASELINE_LEARNING_RATE * gradient

    train_probabilities = 1.0 / (1.0 + np.exp(-np.clip(train_x @ weights, -30.0, 30.0)))
    evaluation_probabilities = 1.0 / (
        1.0 + np.exp(-np.clip(evaluation_x @ weights, -30.0, 30.0))
    )
    checkpoint = {
        "schema": "rocell.ai_target_crop_logistic.v1",
        "feature": {"crop_size": BASELINE_CROP_SIZE, "channels": "RGB", "padding_px": 12},
        "threshold": 0.5,
        "weights": weights.tolist(),
        "standardization_mean": mean.tolist(),
        "standardization_scale": scale.tolist(),
    }
    checkpoint_path = output_dir / "model.json"
    checkpoint_path.write_bytes(_canonical(checkpoint) + b"\n")
    scorecard: dict[str, Any] = {
        "schema": "rocell.ai_official_mesh_occlusion_baseline.v1",
        "seed": BASELINE_SEED,
        "algorithm": "deterministic_class_weighted_logistic_regression",
        "iterations": BASELINE_ITERATIONS,
        "learning_rate": BASELINE_LEARNING_RATE,
        "l2": BASELINE_L2,
        "dataset_manifest_sha256": _sha256(dataset_manifest_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "model_sha256": _sha256(checkpoint_path.read_bytes()),
        "train": _metrics(train_rows, train_y, train_probabilities),
        "evaluation": _metrics(evaluation_rows, evaluation_y, evaluation_probabilities),
        "promotion_status": "BLOCKED_SYNTHETIC_ONLY",
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": dataset_manifest["limitations"],
    }
    scorecard["scorecard_sha256"] = _sha256(_canonical(scorecard))
    (output_dir / "scorecard.json").write_bytes(_canonical(scorecard) + b"\n")
    return scorecard


def train_selected_candidate(dataset_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Select on development only, freeze, then score reserved evaluation once."""
    dataset_dir = dataset_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("candidate output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = manifest.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) or _sha256(_canonical(manifest)) != claimed_dataset_sha:
        raise ValueError("dataset manifest hash mismatch")
    manifest["dataset_sha256"] = claimed_dataset_sha
    if manifest.get("schema") != SCHEMA_V2:
        raise ValueError("candidate selection requires three-way v2 dataset")
    if manifest.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("dataset scope mismatch")

    train_rows = _load_rows(dataset_dir, "train", manifest)
    development_rows = _load_rows(dataset_dir, "development", manifest)
    candidates: list[dict[str, Any]] = []
    fitted: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for family in ("rgb_raw", "chromatic_gray_edges"):
        train_x, train_y = _features(dataset_dir, train_rows, family)
        development_x, development_y = _features(dataset_dir, development_rows, family)
        weights, mean, scale = _fit_logistic(train_x, train_y)
        probabilities = _probabilities(development_x, weights, mean, scale)
        threshold = _select_threshold(development_y, probabilities)
        metrics = _metrics(development_rows, development_y, probabilities, threshold)
        missed = metrics["confusion"]["missed_abstain"]
        candidates.append({
            "feature_family": family,
            "threshold": threshold,
            "development": metrics,
            "development_missed_abstain_rate": missed / int(development_y.sum()),
        })
        fitted[family] = (weights, mean, scale)

    def rank(row: dict[str, Any]) -> tuple[bool, float, int, int]:
        confusion = row["development"]["confusion"]
        return (
            row["development_missed_abstain_rate"] <= 0.05,
            row["development"]["balanced_accuracy"],
            -confusion["false_abstain"],
            -confusion["missed_abstain"],
        )

    selected = max(candidates, key=rank)
    family = selected["feature_family"]
    threshold = selected["threshold"]
    weights, mean, scale = fitted[family]
    checkpoint = {
        "schema": "rocell.ai_target_crop_logistic.v2",
        "feature": {
            "family": family,
            "crop_size": BASELINE_CROP_SIZE,
            "padding_px": 12,
        },
        "threshold": threshold,
        "weights": weights.tolist(),
        "standardization_mean": mean.tolist(),
        "standardization_scale": scale.tolist(),
        "selection_dataset_sha256": claimed_dataset_sha,
        "selection_split": "development",
    }
    checkpoint_path = output_dir / "model.json"
    checkpoint_path.write_bytes(_canonical(checkpoint) + b"\n")

    # Evaluation is loaded only after the family, threshold, and checkpoint are frozen.
    evaluation_rows = _load_rows(dataset_dir, "evaluation", manifest)
    evaluation_x, evaluation_y = _features(dataset_dir, evaluation_rows, family)
    evaluation_probabilities = _probabilities(evaluation_x, weights, mean, scale)
    scorecard: dict[str, Any] = {
        "schema": "rocell.ai_official_mesh_occlusion_candidate.v2",
        "seed": BASELINE_SEED,
        "algorithm": "deterministic_class_weighted_logistic_regression",
        "selection_policy": {
            "fit_split": "train",
            "selection_split": "development",
            "evaluation_split": "evaluation_loaded_after_checkpoint_freeze",
            "maximum_development_missed_abstain_rate": 0.05,
            "ranking": [
                "meets_missed_abstain_rate", "balanced_accuracy",
                "fewest_false_abstentions", "fewest_missed_abstentions",
            ],
        },
        "dataset_manifest_sha256": _sha256(manifest_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "candidate_development_results": candidates,
        "selected_feature_family": family,
        "selected_threshold": threshold,
        "model_sha256": _sha256(checkpoint_path.read_bytes()),
        "evaluation": _metrics(
            evaluation_rows, evaluation_y, evaluation_probabilities, threshold
        ),
        "promotion_status": "BLOCKED_SYNTHETIC_ONLY",
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": manifest["limitations"],
    }
    scorecard["scorecard_sha256"] = _sha256(_canonical(scorecard))
    (output_dir / "scorecard.json").write_bytes(_canonical(scorecard) + b"\n")
    return scorecard


def train_spatial_candidate(dataset_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Fit a tiny CNN, freeze on development, then score evaluation once."""
    import torch

    dataset_dir = dataset_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("spatial output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = manifest.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) or _sha256(_canonical(manifest)) != claimed_dataset_sha:
        raise ValueError("dataset manifest hash mismatch")
    manifest["dataset_sha256"] = claimed_dataset_sha
    if manifest.get("schema") not in {SCHEMA_V3, SCHEMA_V4}:
        raise ValueError("spatial selection requires a three-way v3 or v4 dataset")
    if manifest.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("dataset scope mismatch")

    torch.manual_seed(BASELINE_SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)

    class TinySpatial(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.features = torch.nn.Sequential(
                torch.nn.Conv2d(3, 8, 3, padding=1),
                torch.nn.ReLU(),
                torch.nn.MaxPool2d(2),
                torch.nn.Conv2d(8, 16, 3, padding=1),
                torch.nn.ReLU(),
                torch.nn.AdaptiveAvgPool2d((4, 4)),
            )
            self.classifier = torch.nn.Linear(16 * 4 * 4, 1)

        def forward(self, values):  # type: ignore[no-untyped-def]
            return self.classifier(self.features(values).flatten(1)).squeeze(1)

    train_rows = _load_rows(dataset_dir, "train", manifest)
    development_rows = _load_rows(dataset_dir, "development", manifest)
    train_x, train_y = _spatial_crops(dataset_dir, train_rows)
    development_x, development_y = _spatial_crops(dataset_dir, development_rows)
    train_tensor = torch.from_numpy(train_x)
    train_labels = torch.from_numpy(train_y)
    development_tensor = torch.from_numpy(development_x)
    model = TinySpatial().cpu()
    positives = float(train_y.sum())
    negatives = float(len(train_y) - positives)
    loss_fn = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(negatives / positives, dtype=torch.float32)
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=SPATIAL_LEARNING_RATE)
    epoch_losses = []
    for epoch in range(SPATIAL_EPOCHS):
        generator = torch.Generator().manual_seed(BASELINE_SEED + epoch)
        order = torch.randperm(len(train_tensor), generator=generator)
        total_loss = 0.0
        for start in range(0, len(order), SPATIAL_BATCH_SIZE):
            indices = order[start:start + SPATIAL_BATCH_SIZE]
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(train_tensor[indices]), train_labels[indices])
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
        epoch_losses.append(total_loss / len(order))

    model.eval()
    with torch.no_grad():
        development_probabilities = torch.sigmoid(model(development_tensor)).numpy()
    threshold = _select_threshold(development_y.astype(np.float64), development_probabilities)
    development_metrics = _metrics(
        development_rows, development_y.astype(np.float64),
        development_probabilities, threshold,
    )
    development_missed_rate = (
        development_metrics["confusion"]["missed_abstain"] / int(development_y.sum())
    )
    state = {
        name: {
            "shape": list(value.shape),
            "values": value.detach().cpu().numpy().astype(np.float64).reshape(-1).tolist(),
        }
        for name, value in sorted(model.state_dict().items())
    }
    checkpoint = {
        "schema": "rocell.ai_target_crop_tiny_spatial.v1",
        "architecture": {
            "input": [3, SPATIAL_CROP_SIZE, SPATIAL_CROP_SIZE],
            "layers": [
                "conv_3_8_k3_pad1", "relu", "maxpool_2",
                "conv_8_16_k3_pad1", "relu", "adaptive_avgpool_4x4",
                "linear_256_1",
            ],
            "parameter_count": sum(value.numel() for value in model.parameters()),
        },
        "training": {
            "seed": BASELINE_SEED,
            "device": "cpu",
            "epochs": SPATIAL_EPOCHS,
            "batch_size": SPATIAL_BATCH_SIZE,
            "learning_rate": SPATIAL_LEARNING_RATE,
            "optimizer": "adam",
            "class_weighting": "negative_to_positive_ratio",
            "epoch_losses": epoch_losses,
        },
        "crop": {"size": SPATIAL_CROP_SIZE, "padding_px": SPATIAL_PADDING},
        "threshold": threshold,
        "selection_dataset_sha256": claimed_dataset_sha,
        "selection_split": "development",
        "development_missed_abstain_rate": development_missed_rate,
        "state_dict": state,
    }
    checkpoint_path = output_dir / "model.json"
    checkpoint_path.write_bytes(_canonical(checkpoint) + b"\n")

    # Evaluation bytes are loaded only after architecture, state, and threshold freeze.
    evaluation_rows = _load_rows(dataset_dir, "evaluation", manifest)
    evaluation_x, evaluation_y = _spatial_crops(dataset_dir, evaluation_rows)
    with torch.no_grad():
        evaluation_probabilities = torch.sigmoid(
            model(torch.from_numpy(evaluation_x))
        ).numpy()
    scorecard: dict[str, Any] = {
        "schema": "rocell.ai_official_mesh_occlusion_spatial_candidate.v1",
        "algorithm": "tiny_deterministic_cpu_cnn",
        "selection_policy": {
            "fit_split": "train",
            "selection_split": "development",
            "evaluation_split": "evaluation_loaded_after_checkpoint_freeze",
            "maximum_development_missed_abstain_rate": 0.05,
        },
        "dataset_manifest_sha256": _sha256(manifest_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "model_sha256": _sha256(checkpoint_path.read_bytes()),
        "selected_threshold": threshold,
        "development_missed_abstain_rate": development_missed_rate,
        "development_gate_met": development_missed_rate <= 0.05,
        "development": development_metrics,
        "evaluation": _metrics(
            evaluation_rows, evaluation_y.astype(np.float64),
            evaluation_probabilities, threshold,
        ),
        "promotion_status": "BLOCKED_SYNTHETIC_ONLY",
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": manifest["limitations"],
    }
    scorecard["scorecard_sha256"] = _sha256(_canonical(scorecard))
    (output_dir / "scorecard.json").write_bytes(_canonical(scorecard) + b"\n")
    return scorecard


def train_target_aware_candidate(dataset_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Fit an RGB plus known-safe-region CNN, then score held-out data once."""
    import torch

    dataset_dir = dataset_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("target-aware output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = manifest.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) \
            or _sha256(_canonical(manifest)) != claimed_dataset_sha:
        raise ValueError("dataset manifest hash mismatch")
    manifest["dataset_sha256"] = claimed_dataset_sha
    if manifest.get("schema") != SCHEMA_V5:
        raise ValueError("target-aware selection requires a fresh v5 dataset")
    if manifest.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("dataset scope mismatch")

    torch.manual_seed(BASELINE_SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)

    class TinyTargetAware(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.features = torch.nn.Sequential(
                torch.nn.Conv2d(4, 8, 3, padding=1),
                torch.nn.ReLU(),
                torch.nn.MaxPool2d(2),
                torch.nn.Conv2d(8, 16, 3, padding=1),
                torch.nn.ReLU(),
                torch.nn.AdaptiveAvgPool2d((4, 4)),
            )
            self.classifier = torch.nn.Linear(16 * 4 * 4, 1)

        def forward(self, values):  # type: ignore[no-untyped-def]
            return self.classifier(self.features(values).flatten(1)).squeeze(1)

    train_rows = _load_rows(dataset_dir, "train", manifest)
    development_rows = _load_rows(dataset_dir, "development", manifest)
    train_x, train_y = _target_aware_crops(dataset_dir, train_rows)
    development_x, development_y = _target_aware_crops(dataset_dir, development_rows)
    train_tensor = torch.from_numpy(train_x)
    train_labels = torch.from_numpy(train_y)
    development_tensor = torch.from_numpy(development_x)
    model = TinyTargetAware().cpu()
    positives = float(train_y.sum())
    negatives = float(len(train_y) - positives)
    loss_fn = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(negatives / positives, dtype=torch.float32)
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=SPATIAL_LEARNING_RATE)
    epoch_losses = []
    for epoch in range(SPATIAL_EPOCHS):
        generator = torch.Generator().manual_seed(BASELINE_SEED + epoch)
        order = torch.randperm(len(train_tensor), generator=generator)
        total_loss = 0.0
        for start in range(0, len(order), SPATIAL_BATCH_SIZE):
            indices = order[start:start + SPATIAL_BATCH_SIZE]
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(train_tensor[indices]), train_labels[indices])
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
        epoch_losses.append(total_loss / len(order))

    model.eval()
    with torch.no_grad():
        development_probabilities = torch.sigmoid(model(development_tensor)).numpy()
    threshold = _select_threshold(
        development_y.astype(np.float64), development_probabilities
    )
    development_metrics = _metrics(
        development_rows, development_y.astype(np.float64),
        development_probabilities, threshold,
    )
    development_missed_rate = (
        development_metrics["confusion"]["missed_abstain"] / int(development_y.sum())
    )
    state = {
        name: {
            "shape": list(value.shape),
            "values": value.detach().cpu().numpy().astype(np.float64).reshape(-1).tolist(),
        }
        for name, value in sorted(model.state_dict().items())
    }
    checkpoint = {
        "schema": "rocell.ai_target_crop_safe_region_spatial.v1",
        "architecture": {
            "input": [4, SPATIAL_CROP_SIZE, SPATIAL_CROP_SIZE],
            "input_channels": [
                "red", "green", "blue", "known_target_safe_region_mask",
            ],
            "simulator_robot_mask_input": False,
            "layers": [
                "conv_4_8_k3_pad1", "relu", "maxpool_2",
                "conv_8_16_k3_pad1", "relu", "adaptive_avgpool_4x4",
                "linear_256_1",
            ],
            "parameter_count": sum(value.numel() for value in model.parameters()),
        },
        "training": {
            "seed": BASELINE_SEED,
            "device": "cpu",
            "epochs": SPATIAL_EPOCHS,
            "batch_size": SPATIAL_BATCH_SIZE,
            "learning_rate": SPATIAL_LEARNING_RATE,
            "optimizer": "adam",
            "class_weighting": "negative_to_positive_ratio",
            "epoch_losses": epoch_losses,
        },
        "crop": {"size": SPATIAL_CROP_SIZE, "padding_px": SPATIAL_PADDING},
        "threshold": threshold,
        "selection_dataset_sha256": claimed_dataset_sha,
        "selection_split": "development",
        "development_missed_abstain_rate": development_missed_rate,
        "state_dict": state,
    }
    checkpoint_path = output_dir / "model.json"
    checkpoint_path.write_bytes(_canonical(checkpoint) + b"\n")

    # Evaluation is loaded only after architecture, state, and threshold freeze.
    evaluation_rows = _load_rows(dataset_dir, "evaluation", manifest)
    evaluation_x, evaluation_y = _target_aware_crops(dataset_dir, evaluation_rows)
    with torch.no_grad():
        evaluation_probabilities = torch.sigmoid(
            model(torch.from_numpy(evaluation_x))
        ).numpy()
    scorecard: dict[str, Any] = {
        "schema": "rocell.ai_official_mesh_occlusion_target_aware_candidate.v1",
        "algorithm": "tiny_target_safe_region_deterministic_cpu_cnn",
        "selection_policy": {
            "fit_split": "train",
            "selection_split": "development",
            "evaluation_split": "evaluation_loaded_after_checkpoint_freeze",
            "maximum_development_missed_abstain_rate": 0.05,
        },
        "dataset_manifest_sha256": _sha256(manifest_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "model_sha256": _sha256(checkpoint_path.read_bytes()),
        "selected_threshold": threshold,
        "development_missed_abstain_rate": development_missed_rate,
        "development_gate_met": development_missed_rate <= 0.05,
        "development": development_metrics,
        "evaluation": _metrics(
            evaluation_rows, evaluation_y.astype(np.float64),
            evaluation_probabilities, threshold,
        ),
        "promotion_status": "BLOCKED_SYNTHETIC_ONLY",
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": manifest["limitations"],
    }
    scorecard["scorecard_sha256"] = _sha256(_canonical(scorecard))
    (output_dir / "scorecard.json").write_bytes(_canonical(scorecard) + b"\n")
    return scorecard


def _training_augmentation_offsets() -> list[dict[str, float]]:
    return [
        offset for offset in _declared_mask_offsets()
        if max(abs(offset["x_mm"]), abs(offset["y_mm"])) <= 2.0
    ]


def _select_localization_policy(
    rows: list[dict[str, Any]],
    labels: np.ndarray,
    probabilities_by_offset: list[tuple[dict[str, float], np.ndarray]],
    maximum_missed_rate: float = 0.05,
    maximum_false_rate: float = 0.05,
) -> tuple[float, float, bool, list[dict[str, Any]]]:
    if [item[0] for item in probabilities_by_offset] != _declared_mask_offsets():
        raise ValueError("localization policy requires every predeclared offset in order")
    admissible = []
    # Millithreshold resolution is predeclared rather than derived from the
    # development predictions.  This keeps selection deterministic while
    # avoiding the 0.05-wide blind spots of the original research grid.
    thresholds = [value / 1000.0 for value in range(50, 951)]
    positive_count = int(labels.sum())
    visible_count = len(labels) - positive_count
    if positive_count == 0 or visible_count == 0:
        raise ValueError("localization policy requires both abstain and visible rows")
    for threshold in thresholds:
        summaries = []
        for offset, probabilities in probabilities_by_offset:
            predicted = probabilities >= threshold
            true_abstain = int(np.logical_and(labels == 1, predicted).sum())
            true_visible = int(np.logical_and(labels == 0, ~predicted).sum())
            missed_abstain = positive_count - true_abstain
            false_abstain = visible_count - true_visible
            summaries.append({
                "offset": offset,
                "missed_rate": missed_abstain / positive_count,
                "false_rate": false_abstain / visible_count,
                "balanced_accuracy": 0.5 * (
                    true_abstain / positive_count + true_visible / visible_count
                ),
            })
        for bound in (0.0, 1.0, 2.0, 4.0):
            covered = [
                item for item in summaries
                if max(abs(item["offset"]["x_mm"]), abs(item["offset"]["y_mm"])) <= bound
            ]
            missed_rates = [item["missed_rate"] for item in covered]
            false_rates = [item["false_rate"] for item in covered]
            if max(missed_rates) <= maximum_missed_rate \
                    and max(false_rates) <= maximum_false_rate:
                admissible.append((
                    bound,
                    min(item["balanced_accuracy"] for item in covered),
                    -max(false_rates),
                    -max(missed_rates),
                    -threshold,
                    threshold,
                ))
    if admissible:
        selected = max(admissible)
        threshold = selected[5]
        measurements = [
            {"offset": offset, "metrics": _metrics(rows, labels, probabilities, threshold)}
            for offset, probabilities in probabilities_by_offset
        ]
        return threshold, selected[0], True, measurements
    nominal_offset, nominal_probabilities = probabilities_by_offset[0]
    if nominal_offset != {"x_mm": 0.0, "y_mm": 0.0, "x_px": 0.0, "y_px": 0.0}:
        raise ValueError("nominal offset must be first")
    threshold = _select_threshold(labels, nominal_probabilities)
    measurements = [
        {"offset": offset, "metrics": _metrics(rows, labels, probabilities, threshold)}
        for offset, probabilities in probabilities_by_offset
    ]
    return threshold, 0.0, False, measurements


def train_localization_robust_candidate(
    training_dataset_dir: Path,
    development_dataset_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Train with bounded offsets and freeze an uncertainty abstention policy."""
    import torch

    training_dataset_dir = training_dataset_dir.resolve(strict=True)
    development_dataset_dir = development_dataset_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("localization-robust output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    def verified_manifest(directory: Path, expected_schema: str) -> tuple[dict[str, Any], str]:
        path = directory / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        claimed = manifest.pop("dataset_sha256", None)
        if not isinstance(claimed, str) or _sha256(_canonical(manifest)) != claimed:
            raise ValueError("localization-robust dataset manifest hash mismatch")
        manifest["dataset_sha256"] = claimed
        if manifest.get("schema") != expected_schema \
                or manifest.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
            raise ValueError("localization-robust dataset scope or schema mismatch")
        return manifest, claimed

    training_manifest, training_sha = verified_manifest(training_dataset_dir, SCHEMA_V5)
    development_manifest, development_sha = verified_manifest(
        development_dataset_dir, SCHEMA_V6,
    )
    if development_manifest["splits"]["train"]["count"] != 0 \
            or development_manifest["splits"]["evaluation"]["count"] != 0:
        raise ValueError("localization policy dataset must be development-only")

    torch.manual_seed(BASELINE_SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)

    class TinyLocalizationRobust(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.features = torch.nn.Sequential(
                torch.nn.Conv2d(4, 8, 3, padding=1),
                torch.nn.ReLU(),
                torch.nn.MaxPool2d(2),
                torch.nn.Conv2d(8, 16, 3, padding=1),
                torch.nn.ReLU(),
                torch.nn.AdaptiveAvgPool2d((4, 4)),
            )
            self.classifier = torch.nn.Linear(16 * 4 * 4, 1)

        def forward(self, values):  # type: ignore[no-untyped-def]
            return self.classifier(self.features(values).flatten(1)).squeeze(1)

    train_rows = _load_rows(training_dataset_dir, "train", training_manifest)
    augmentation = _training_augmentation_offsets()
    row_offsets = []
    augmentation_counts: dict[str, int] = {}
    for row in train_rows:
        index = int(_sha256(row["id"].encode("utf-8"))[:8], 16) % len(augmentation)
        offset = augmentation[index]
        row_offsets.append((offset["x_px"], offset["y_px"]))
        key = f"{offset['x_mm']:g},{offset['y_mm']:g}"
        augmentation_counts[key] = augmentation_counts.get(key, 0) + 1
    train_x, train_y = _target_aware_crops(
        training_dataset_dir, train_rows, row_offsets_px=row_offsets,
    )
    train_tensor = torch.from_numpy(train_x)
    train_labels = torch.from_numpy(train_y)
    model = TinyLocalizationRobust().cpu()
    positives = float(train_y.sum())
    negatives = float(len(train_y) - positives)
    loss_fn = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(negatives / positives, dtype=torch.float32)
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=SPATIAL_LEARNING_RATE)
    epoch_losses = []
    for epoch in range(SPATIAL_EPOCHS):
        generator = torch.Generator().manual_seed(BASELINE_SEED + epoch)
        order = torch.randperm(len(train_tensor), generator=generator)
        total_loss = 0.0
        for start in range(0, len(order), SPATIAL_BATCH_SIZE):
            indices = order[start:start + SPATIAL_BATCH_SIZE]
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(train_tensor[indices]), train_labels[indices])
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
        epoch_losses.append(total_loss / len(order))

    model.eval()
    development_rows = _load_rows(
        development_dataset_dir, "development", development_manifest,
    )
    development_labels: np.ndarray | None = None
    probabilities_by_offset = []
    for offset in _declared_mask_offsets():
        crops, labels = _target_aware_crops(
            development_dataset_dir,
            development_rows,
            (offset["x_px"], offset["y_px"]),
        )
        if development_labels is None:
            development_labels = labels.astype(np.float64)
        elif not np.array_equal(development_labels, labels):
            raise RuntimeError("development labels changed across offsets")
        with torch.no_grad():
            probabilities = torch.sigmoid(model(torch.from_numpy(crops))).numpy()
        probabilities_by_offset.append((offset, probabilities))
    assert development_labels is not None
    threshold, uncertainty_bound, gate_met, measurements = _select_localization_policy(
        development_rows, development_labels, probabilities_by_offset,
    )

    state = {
        name: {
            "shape": list(value.shape),
            "values": value.detach().cpu().numpy().astype(np.float64).reshape(-1).tolist(),
        }
        for name, value in sorted(model.state_dict().items())
    }
    checkpoint = {
        "schema": "rocell.ai_target_crop_localization_robust_spatial.v1",
        "architecture": {
            "input": [4, SPATIAL_CROP_SIZE, SPATIAL_CROP_SIZE],
            "input_channels": [
                "red", "green", "blue", "known_target_safe_region_mask",
            ],
            "simulator_robot_mask_input": False,
            "parameter_count": sum(value.numel() for value in model.parameters()),
        },
        "training": {
            "seed": BASELINE_SEED,
            "device": "cpu",
            "epochs": SPATIAL_EPOCHS,
            "batch_size": SPATIAL_BATCH_SIZE,
            "learning_rate": SPATIAL_LEARNING_RATE,
            "optimizer": "adam",
            "class_weighting": "negative_to_positive_ratio",
            "augmentation": "one_deterministic_offset_per_training_row",
            "augmentation_offsets_mm": augmentation,
            "augmentation_counts": augmentation_counts,
            "epoch_losses": epoch_losses,
        },
        "crop": {"size": SPATIAL_CROP_SIZE, "padding_px": SPATIAL_PADDING},
        "threshold": threshold,
        "localization_uncertainty_policy": {
            "maximum_supported_planar_error_mm": uncertainty_bound,
            "above_bound_decision": "abstain_localization_uncertain",
            "development_gate_met": gate_met,
            "maximum_missed_abstain_rate": 0.05,
            "maximum_visible_false_abstain_rate": 0.05,
        },
        "training_dataset_sha256": training_sha,
        "selection_dataset_sha256": development_sha,
        "selection_split": "development_only",
        "evaluation_opened": False,
        "state_dict": state,
    }
    checkpoint_path = output_dir / "model.json"
    checkpoint_path.write_bytes(_canonical(checkpoint) + b"\n")
    scorecard: dict[str, Any] = {
        "schema": "rocell.ai_localization_robust_candidate.v1",
        "algorithm": "tiny_target_safe_region_offset_augmented_deterministic_cpu_cnn",
        "training_dataset_manifest_sha256": _sha256(
            (training_dataset_dir / "manifest.json").read_bytes()
        ),
        "training_dataset_sha256": training_sha,
        "development_dataset_manifest_sha256": _sha256(
            (development_dataset_dir / "manifest.json").read_bytes()
        ),
        "development_dataset_sha256": development_sha,
        "model_sha256": _sha256(checkpoint_path.read_bytes()),
        "selected_threshold": threshold,
        "maximum_supported_planar_error_mm": uncertainty_bound,
        "development_gate_met": gate_met,
        "development_measurements": measurements,
        "evaluation_group_present": False,
        "promotion_status": "BLOCKED_AWAITING_FRESH_EVALUATION",
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "training and policy selection use synthetic data only",
            "the uncertainty bound is synthetic and not a physical calibration",
            "no evaluation group was created or opened",
            "tool and camera-support geometry remain absent",
        ],
    }
    scorecard["scorecard_sha256"] = _sha256(_canonical(scorecard))
    (output_dir / "scorecard.json").write_bytes(_canonical(scorecard) + b"\n")
    return scorecard


def train_target_identity_candidate(
    training_dataset_dir: Path,
    development_dataset_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Fit a target-identity-aware model and select only on v8 development data."""
    import torch

    training_dataset_dir = training_dataset_dir.resolve(strict=True)
    development_dataset_dir = development_dataset_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("target-identity output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    def verified_manifest(
        directory: Path, expected_schema: str, expected_nonempty_split: str,
    ) -> tuple[dict[str, Any], str]:
        path = directory / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        claimed = manifest.pop("dataset_sha256", None)
        if not isinstance(claimed, str) or _sha256(_canonical(manifest)) != claimed:
            raise ValueError("target-identity dataset manifest hash mismatch")
        manifest["dataset_sha256"] = claimed
        if manifest.get("schema") != expected_schema \
                or manifest.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
            raise ValueError("target-identity dataset scope or schema mismatch")
        for split in ("train", "development", "evaluation"):
            count = manifest["splits"][split]["count"]
            if (split == expected_nonempty_split) != (count > 0):
                raise ValueError(
                    f"target-identity dataset must be {expected_nonempty_split}-only"
                )
        return manifest, claimed

    training_manifest, training_sha = verified_manifest(
        training_dataset_dir, SCHEMA_V9, "train",
    )
    development_manifest, development_sha = verified_manifest(
        development_dataset_dir, SCHEMA_V8, "development",
    )
    if training_manifest.get("target_catalog_sha256") \
            != development_manifest.get("target_catalog_sha256"):
        raise ValueError("target-identity datasets bind different target catalogs")

    torch.manual_seed(BASELINE_SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)

    training_rows = _load_rows(training_dataset_dir, "train", training_manifest)
    development_rows = _load_rows(
        development_dataset_dir, "development", development_manifest,
    )
    catalog = _target_identity_catalog(training_rows)
    if set(catalog) != set(_target_identity_catalog(development_rows)):
        raise ValueError("target-identity training and development vocabularies differ")
    descriptor_size = len(catalog) + 4

    class TinyTargetIdentity(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.features = torch.nn.Sequential(
                torch.nn.Conv2d(4, 8, 3, padding=1),
                torch.nn.ReLU(),
                torch.nn.MaxPool2d(2),
                torch.nn.Conv2d(8, 16, 3, padding=1),
                torch.nn.ReLU(),
                torch.nn.AdaptiveAvgPool2d((4, 4)),
            )
            self.classifier = torch.nn.Linear(16 * 4 * 4 + descriptor_size, 1)

        def forward(self, values, descriptors):  # type: ignore[no-untyped-def]
            visual = self.features(values).flatten(1)
            return self.classifier(torch.cat((visual, descriptors), dim=1)).squeeze(1)

    augmentation = _training_augmentation_offsets()
    row_offsets = []
    augmentation_counts: dict[str, int] = {}
    for row in training_rows:
        index = int(_sha256(row["id"].encode("utf-8"))[:8], 16) % len(augmentation)
        offset = augmentation[index]
        row_offsets.append((offset["x_px"], offset["y_px"]))
        key = f"{offset['x_mm']:g},{offset['y_mm']:g}"
        augmentation_counts[key] = augmentation_counts.get(key, 0) + 1
    training_crops, training_labels = _target_aware_crops(
        training_dataset_dir, training_rows, row_offsets_px=row_offsets,
    )
    training_descriptors = _target_identity_descriptors(
        training_dataset_dir, training_rows, catalog,
    )
    crop_tensor = torch.from_numpy(training_crops)
    descriptor_tensor = torch.from_numpy(training_descriptors)
    label_tensor = torch.from_numpy(training_labels)
    model = TinyTargetIdentity().cpu()
    positives = float(training_labels.sum())
    negatives = float(len(training_labels) - positives)
    if positives == 0.0 or negatives == 0.0:
        raise ValueError("target-identity training requires both decision classes")
    loss_fn = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(negatives / positives, dtype=torch.float32)
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=SPATIAL_LEARNING_RATE)
    epoch_losses = []
    for epoch in range(TARGET_IDENTITY_EPOCHS):
        generator = torch.Generator().manual_seed(BASELINE_SEED + epoch)
        order = torch.randperm(len(crop_tensor), generator=generator)
        total_loss = 0.0
        for start in range(0, len(order), SPATIAL_BATCH_SIZE):
            indices = order[start:start + SPATIAL_BATCH_SIZE]
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(
                crop_tensor[indices], descriptor_tensor[indices],
            ), label_tensor[indices])
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
        epoch_losses.append(total_loss / len(order))

    model.eval()
    development_descriptors = torch.from_numpy(_target_identity_descriptors(
        development_dataset_dir, development_rows, catalog,
    ))
    development_labels: np.ndarray | None = None
    probabilities_by_offset = []
    for offset in _declared_mask_offsets():
        crops, labels = _target_aware_crops(
            development_dataset_dir,
            development_rows,
            (offset["x_px"], offset["y_px"]),
        )
        if development_labels is None:
            development_labels = labels.astype(np.float64)
        elif not np.array_equal(development_labels, labels):
            raise RuntimeError("target-identity labels changed across offsets")
        with torch.no_grad():
            probabilities = torch.sigmoid(model(
                torch.from_numpy(crops), development_descriptors,
            )).numpy()
        probabilities_by_offset.append((offset, probabilities))
    assert development_labels is not None
    threshold, uncertainty_bound, gate_met, measurements = _select_localization_policy(
        development_rows, development_labels, probabilities_by_offset,
    )

    state = {
        name: {
            "shape": list(value.shape),
            "values": value.detach().cpu().numpy().astype(np.float64).reshape(-1).tolist(),
        }
        for name, value in sorted(model.state_dict().items())
    }
    checkpoint = {
        "schema": "rocell.ai_target_identity_geometry_spatial.v1",
        "architecture": {
            "image_input": [4, SPATIAL_CROP_SIZE, SPATIAL_CROP_SIZE],
            "image_channels": [
                "red", "green", "blue", "known_target_safe_region_mask",
            ],
            "descriptor_size": descriptor_size,
            "descriptor_fields": [
                f"one_hot:{target}" for target in catalog
            ] + [
                "center_x_fraction", "center_y_fraction",
                "safe_width_fraction", "safe_height_fraction",
            ],
            "target_catalog": list(catalog),
            "simulator_robot_mask_input": False,
            "parameter_count": sum(value.numel() for value in model.parameters()),
        },
        "training": {
            "seed": BASELINE_SEED,
            "device": "cpu",
            "epochs": TARGET_IDENTITY_EPOCHS,
            "batch_size": SPATIAL_BATCH_SIZE,
            "learning_rate": SPATIAL_LEARNING_RATE,
            "optimizer": "adam",
            "class_weighting": "negative_to_positive_ratio",
            "augmentation": "one_deterministic_offset_per_training_row",
            "augmentation_offsets_mm": augmentation,
            "augmentation_counts": augmentation_counts,
            "epoch_losses": epoch_losses,
        },
        "crop": {"size": SPATIAL_CROP_SIZE, "padding_px": SPATIAL_PADDING},
        "threshold": threshold,
        "localization_uncertainty_policy": {
            "maximum_supported_planar_error_mm": uncertainty_bound,
            "above_bound_decision": "abstain_localization_uncertain",
            "development_gate_met": gate_met,
            "maximum_missed_abstain_rate": 0.05,
            "maximum_visible_false_abstain_rate": 0.05,
        },
        "target_catalog_sha256": training_manifest["target_catalog_sha256"],
        "training_dataset_sha256": training_sha,
        "selection_dataset_sha256": development_sha,
        "selection_split": "development_only",
        "evaluation_opened": False,
        "state_dict": state,
    }
    checkpoint_path = output_dir / "model.json"
    checkpoint_path.write_bytes(_canonical(checkpoint) + b"\n")
    scorecard: dict[str, Any] = {
        "schema": "rocell.ai_target_identity_candidate.v1",
        "algorithm": "tiny_target_identity_geometry_offset_augmented_cpu_cnn",
        "training_dataset_manifest_sha256": _sha256(
            (training_dataset_dir / "manifest.json").read_bytes()
        ),
        "training_dataset_sha256": training_sha,
        "development_dataset_manifest_sha256": _sha256(
            (development_dataset_dir / "manifest.json").read_bytes()
        ),
        "development_dataset_sha256": development_sha,
        "target_catalog_sha256": training_manifest["target_catalog_sha256"],
        "model_sha256": _sha256(checkpoint_path.read_bytes()),
        "selected_threshold": threshold,
        "maximum_supported_planar_error_mm": uncertainty_bound,
        "development_gate_met": gate_met,
        "development_measurements": measurements,
        "evaluation_group_present": False,
        "promotion_status": "BLOCKED_AWAITING_FRESH_EVALUATION",
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "training and policy selection use synthetic data only",
            "target identity and geometry assume the exact frozen target catalog",
            "the uncertainty bound is synthetic and not a physical calibration",
            "no evaluation group was created or opened",
            "tool and camera-support geometry remain absent",
        ],
    }
    scorecard["scorecard_sha256"] = _sha256(_canonical(scorecard))
    (output_dir / "scorecard.json").write_bytes(_canonical(scorecard) + b"\n")
    return scorecard


def train_target_conditioned_fusion_candidate(
    training_dataset_dir: Path,
    development_dataset_dir: Path,
    seed_candidate_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Learn target-conditioned feature modulation over a frozen safe baseline."""
    import torch

    training_dataset_dir = training_dataset_dir.resolve(strict=True)
    development_dataset_dir = development_dataset_dir.resolve(strict=True)
    seed_candidate_dir = seed_candidate_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("target-conditioned output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    def verified_manifest(
        directory: Path, expected_schema: str, expected_nonempty_split: str,
    ) -> tuple[dict[str, Any], str]:
        path = directory / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        claimed = manifest.pop("dataset_sha256", None)
        if not isinstance(claimed, str) or _sha256(_canonical(manifest)) != claimed:
            raise ValueError("target-conditioned dataset manifest hash mismatch")
        manifest["dataset_sha256"] = claimed
        if manifest.get("schema") != expected_schema \
                or manifest.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
            raise ValueError("target-conditioned dataset scope or schema mismatch")
        for split in ("train", "development", "evaluation"):
            count = manifest["splits"][split]["count"]
            if (split == expected_nonempty_split) != (count > 0):
                raise ValueError(
                    f"target-conditioned dataset must be {expected_nonempty_split}-only"
                )
        return manifest, claimed

    training_manifest, training_sha = verified_manifest(
        training_dataset_dir, SCHEMA_V9, "train",
    )
    development_manifest, development_sha = verified_manifest(
        development_dataset_dir, SCHEMA_V8, "development",
    )
    if training_manifest.get("target_catalog_sha256") \
            != development_manifest.get("target_catalog_sha256"):
        raise ValueError("target-conditioned datasets bind different target catalogs")

    seed_model_path = seed_candidate_dir / "model.json"
    seed_scorecard_path = seed_candidate_dir / "scorecard.json"
    seed_checkpoint, seed_model = _load_spatial_checkpoint(seed_candidate_dir)
    seed_policy = seed_checkpoint.get("localization_uncertainty_policy", {})
    if seed_checkpoint.get("schema") \
            != "rocell.ai_target_crop_localization_robust_spatial.v1" \
            or seed_checkpoint.get("evaluation_opened") is not False \
            or seed_policy.get("maximum_supported_planar_error_mm") != 1.0 \
            or seed_policy.get("development_gate_met") is not True:
        raise ValueError("target-conditioned seed must be the frozen 1 mm baseline")
    seed_scorecard = json.loads(seed_scorecard_path.read_text(encoding="utf-8"))
    claimed_seed_scorecard_sha = seed_scorecard.pop("scorecard_sha256", None)
    if not isinstance(claimed_seed_scorecard_sha, str) \
            or _sha256(_canonical(seed_scorecard)) != claimed_seed_scorecard_sha:
        raise ValueError("target-conditioned seed scorecard hash mismatch")
    seed_scorecard["scorecard_sha256"] = claimed_seed_scorecard_sha
    seed_model_sha = _sha256(seed_model_path.read_bytes())
    if seed_scorecard.get("schema") != "rocell.ai_localization_policy_refreeze.v1" \
            or seed_scorecard.get("model_sha256") != seed_model_sha \
            or seed_scorecard.get("maximum_supported_planar_error_mm") != 1.0 \
            or seed_scorecard.get("development_gate_met") is not True \
            or seed_scorecard.get("hardware_writes") != 0 \
            or seed_scorecard.get("physical_movements") != 0:
        raise ValueError("target-conditioned seed identity or authority mismatch")

    torch.manual_seed(BASELINE_SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    training_rows = _load_rows(training_dataset_dir, "train", training_manifest)
    development_rows = _load_rows(
        development_dataset_dir, "development", development_manifest,
    )
    catalog = _target_identity_catalog(training_rows)
    if set(catalog) != set(_target_identity_catalog(development_rows)):
        raise ValueError("target-conditioned training and development vocabularies differ")
    descriptor_size = len(catalog) + 4

    class TinyTargetConditionedFusion(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.conv1 = seed_model.features[0]
            self.pool1 = seed_model.features[2]
            self.conv2 = seed_model.features[3]
            self.pool2 = seed_model.features[5]
            self.classifier = seed_model.classifier
            self.conditioner = torch.nn.Linear(descriptor_size, 32)
            torch.nn.init.zeros_(self.conditioner.weight)
            torch.nn.init.zeros_(self.conditioner.bias)
            for component in (self.conv1, self.conv2, self.classifier):
                for parameter in component.parameters():
                    parameter.requires_grad_(False)

        def forward(self, values, descriptors):  # type: ignore[no-untyped-def]
            features = torch.relu(self.conv1(values))
            features = self.pool1(features)
            features = torch.relu(self.conv2(features))
            gamma, beta = self.conditioner(descriptors).chunk(2, dim=1)
            scale = TARGET_CONDITIONED_MODULATION_SCALE
            features = torch.relu(
                features * (1.0 + scale * torch.tanh(gamma)[:, :, None, None])
                + scale * beta[:, :, None, None]
            )
            return self.classifier(self.pool2(features).flatten(1)).squeeze(1)

    augmentation = _training_augmentation_offsets()
    row_offsets = []
    augmentation_counts: dict[str, int] = {}
    for row in training_rows:
        index = int(_sha256(row["id"].encode("utf-8"))[:8], 16) % len(augmentation)
        offset = augmentation[index]
        row_offsets.append((offset["x_px"], offset["y_px"]))
        key = f"{offset['x_mm']:g},{offset['y_mm']:g}"
        augmentation_counts[key] = augmentation_counts.get(key, 0) + 1
    training_crops, training_labels = _target_aware_crops(
        training_dataset_dir, training_rows, row_offsets_px=row_offsets,
    )
    training_descriptors = _target_identity_descriptors(
        training_dataset_dir, training_rows, catalog,
    )
    crop_tensor = torch.from_numpy(training_crops)
    descriptor_tensor = torch.from_numpy(training_descriptors)
    label_tensor = torch.from_numpy(training_labels)
    model = TinyTargetConditionedFusion().cpu()
    loss_fn = torch.nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(
        model.conditioner.parameters(),
        lr=TARGET_CONDITIONED_LEARNING_RATE,
        weight_decay=0.0001,
    )
    epoch_losses = []
    for epoch in range(TARGET_CONDITIONED_EPOCHS):
        generator = torch.Generator().manual_seed(BASELINE_SEED + epoch)
        order = torch.randperm(len(crop_tensor), generator=generator)
        total_loss = 0.0
        for start in range(0, len(order), SPATIAL_BATCH_SIZE):
            indices = order[start:start + SPATIAL_BATCH_SIZE]
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(
                crop_tensor[indices], descriptor_tensor[indices],
            ), label_tensor[indices])
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
        epoch_losses.append(total_loss / len(order))

    model.eval()
    development_descriptors = torch.from_numpy(_target_identity_descriptors(
        development_dataset_dir, development_rows, catalog,
    ))
    development_labels: np.ndarray | None = None
    probabilities_by_offset = []
    for offset in _declared_mask_offsets():
        crops, labels = _target_aware_crops(
            development_dataset_dir,
            development_rows,
            (offset["x_px"], offset["y_px"]),
        )
        if development_labels is None:
            development_labels = labels.astype(np.float64)
        elif not np.array_equal(development_labels, labels):
            raise RuntimeError("target-conditioned labels changed across offsets")
        with torch.no_grad():
            probabilities = torch.sigmoid(model(
                torch.from_numpy(crops), development_descriptors,
            )).numpy()
        probabilities_by_offset.append((offset, probabilities))
    assert development_labels is not None
    threshold, uncertainty_bound, gate_met, measurements = _select_localization_policy(
        development_rows, development_labels, probabilities_by_offset,
    )

    state = {
        name: {
            "shape": list(value.shape),
            "values": value.detach().cpu().numpy().astype(np.float64).reshape(-1).tolist(),
        }
        for name, value in sorted(model.state_dict().items())
    }
    checkpoint = {
        "schema": "rocell.ai_target_conditioned_spatial_fusion.v1",
        "architecture": {
            "image_input": [4, SPATIAL_CROP_SIZE, SPATIAL_CROP_SIZE],
            "image_channels": [
                "red", "green", "blue", "known_target_safe_region_mask",
            ],
            "descriptor_size": descriptor_size,
            "descriptor_fields": [
                f"one_hot:{target}" for target in catalog
            ] + [
                "center_x_fraction", "center_y_fraction",
                "safe_width_fraction", "safe_height_fraction",
            ],
            "target_catalog": list(catalog),
            "fusion": "descriptor_film_after_second_convolution_before_spatial_pooling",
            "modulation_scale": TARGET_CONDITIONED_MODULATION_SCALE,
            "frozen_visual_backbone": True,
            "frozen_classifier": True,
            "simulator_robot_mask_input": False,
            "parameter_count": sum(value.numel() for value in model.parameters()),
            "trainable_parameter_count": sum(
                value.numel() for value in model.parameters() if value.requires_grad
            ),
        },
        "seed": {
            "model_sha256": seed_model_sha,
            "scorecard_sha256": claimed_seed_scorecard_sha,
            "maximum_supported_planar_error_mm": 1.0,
        },
        "training": {
            "seed": BASELINE_SEED,
            "device": "cpu",
            "epochs": TARGET_CONDITIONED_EPOCHS,
            "batch_size": SPATIAL_BATCH_SIZE,
            "learning_rate": TARGET_CONDITIONED_LEARNING_RATE,
            "optimizer": "adam",
            "weight_decay": 0.0001,
            "loss": "unweighted_binary_cross_entropy",
            "augmentation": "one_deterministic_offset_per_training_row",
            "augmentation_offsets_mm": augmentation,
            "augmentation_counts": augmentation_counts,
            "epoch_losses": epoch_losses,
        },
        "crop": {"size": SPATIAL_CROP_SIZE, "padding_px": SPATIAL_PADDING},
        "threshold": threshold,
        "localization_uncertainty_policy": {
            "maximum_supported_planar_error_mm": uncertainty_bound,
            "above_bound_decision": "abstain_localization_uncertain",
            "development_gate_met": gate_met,
            "maximum_missed_abstain_rate": 0.05,
            "maximum_visible_false_abstain_rate": 0.05,
        },
        "target_catalog_sha256": training_manifest["target_catalog_sha256"],
        "training_dataset_sha256": training_sha,
        "selection_dataset_sha256": development_sha,
        "selection_split": "development_only",
        "evaluation_opened": False,
        "state_dict": state,
    }
    checkpoint_path = output_dir / "model.json"
    checkpoint_path.write_bytes(_canonical(checkpoint) + b"\n")
    scorecard: dict[str, Any] = {
        "schema": "rocell.ai_target_conditioned_fusion_candidate.v1",
        "algorithm": "frozen_backbone_target_conditioned_prepool_film_v1",
        "seed_model_sha256": seed_model_sha,
        "seed_scorecard_sha256": claimed_seed_scorecard_sha,
        "training_dataset_manifest_sha256": _sha256(
            (training_dataset_dir / "manifest.json").read_bytes()
        ),
        "training_dataset_sha256": training_sha,
        "development_dataset_manifest_sha256": _sha256(
            (development_dataset_dir / "manifest.json").read_bytes()
        ),
        "development_dataset_sha256": development_sha,
        "target_catalog_sha256": training_manifest["target_catalog_sha256"],
        "model_sha256": _sha256(checkpoint_path.read_bytes()),
        "selected_threshold": threshold,
        "maximum_supported_planar_error_mm": uncertainty_bound,
        "development_gate_met": gate_met,
        "development_measurements": measurements,
        "evaluation_group_present": False,
        "promotion_status": "BLOCKED_AWAITING_FRESH_EVALUATION",
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "training and policy selection use synthetic data only",
            "target conditioning assumes the exact frozen target catalog",
            "the visual backbone and classifier are frozen from synthetic development evidence",
            "the uncertainty bound is synthetic and not a physical calibration",
            "no evaluation group was created or opened",
            "tool and camera-support geometry remain absent",
        ],
    }
    scorecard["scorecard_sha256"] = _sha256(_canonical(scorecard))
    (output_dir / "scorecard.json").write_bytes(_canonical(scorecard) + b"\n")
    return scorecard


def _load_target_conditioned_checkpoint(candidate_dir: Path):  # type: ignore[no-untyped-def]
    import torch

    checkpoint_path = candidate_dir / "model.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if checkpoint.get("schema") not in {
        "rocell.ai_target_conditioned_spatial_fusion.v1",
        "rocell.ai_target_conditioned_occlusion_recall.v1",
        "rocell.ai_target_conditioned_specificity_rebalance.v1",
        "rocell.ai_target_conditioned_pose_diverse.v1",
    }:
        raise ValueError("target-conditioned checkpoint schema mismatch")
    architecture = checkpoint.get("architecture", {})
    descriptor_size = architecture.get("descriptor_size")
    catalog = architecture.get("target_catalog")
    if not isinstance(descriptor_size, int) or descriptor_size < 5 \
            or not isinstance(catalog, list) or len(catalog) + 4 != descriptor_size:
        raise ValueError("target-conditioned checkpoint descriptor mismatch")

    class TinyTargetConditionedFusion(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.conv1 = torch.nn.Conv2d(4, 8, 3, padding=1)
            self.pool1 = torch.nn.MaxPool2d(2)
            self.conv2 = torch.nn.Conv2d(8, 16, 3, padding=1)
            self.pool2 = torch.nn.AdaptiveAvgPool2d((4, 4))
            self.classifier = torch.nn.Linear(16 * 4 * 4, 1)
            self.conditioner = torch.nn.Linear(descriptor_size, 32)

        def forward(self, values, descriptors):  # type: ignore[no-untyped-def]
            features = torch.relu(self.conv1(values))
            features = self.pool1(features)
            features = torch.relu(self.conv2(features))
            gamma, beta = self.conditioner(descriptors).chunk(2, dim=1)
            scale = float(architecture["modulation_scale"])
            features = torch.relu(
                features * (1.0 + scale * torch.tanh(gamma)[:, :, None, None])
                + scale * beta[:, :, None, None]
            )
            return self.classifier(self.pool2(features).flatten(1)).squeeze(1)

    model = TinyTargetConditionedFusion().cpu()
    state = {
        name: torch.tensor(item["values"], dtype=torch.float32).reshape(item["shape"])
        for name, item in checkpoint["state_dict"].items()
    }
    model.load_state_dict(state, strict=True)
    model.eval()
    return checkpoint, model


def _load_spatial_checkpoint(candidate_dir: Path):  # type: ignore[no-untyped-def]
    import torch

    checkpoint_path = candidate_dir / "model.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    schemas = {
        "rocell.ai_target_crop_tiny_spatial.v1": 3,
        "rocell.ai_target_crop_safe_region_spatial.v1": 4,
        "rocell.ai_target_crop_localization_robust_spatial.v1": 4,
    }
    input_channels = schemas.get(checkpoint.get("schema"))
    if input_channels is None:
        raise ValueError("spatial checkpoint schema mismatch")

    class TinySpatial(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.features = torch.nn.Sequential(
                torch.nn.Conv2d(input_channels, 8, 3, padding=1),
                torch.nn.ReLU(),
                torch.nn.MaxPool2d(2),
                torch.nn.Conv2d(8, 16, 3, padding=1),
                torch.nn.ReLU(),
                torch.nn.AdaptiveAvgPool2d((4, 4)),
            )
            self.classifier = torch.nn.Linear(16 * 4 * 4, 1)

        def forward(self, values):  # type: ignore[no-untyped-def]
            return self.classifier(self.features(values).flatten(1)).squeeze(1)

    model = TinySpatial().cpu()
    state = {
        name: torch.tensor(item["values"], dtype=torch.float32).reshape(item["shape"])
        for name, item in checkpoint["state_dict"].items()
    }
    model.load_state_dict(state, strict=True)
    model.eval()
    return checkpoint, model


def train_occlusion_recall_candidate(
    dataset_dir: Path,
    seed_candidate_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Update only the fusion conditioner with fixed abstention class weight."""
    import torch

    dataset_dir = dataset_dir.resolve(strict=True)
    seed_candidate_dir = seed_candidate_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("occlusion-recall output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = dataset_dir / "manifest.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = dataset.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) \
            or _sha256(_canonical(dataset)) != claimed_dataset_sha:
        raise ValueError("occlusion-recall dataset manifest hash mismatch")
    dataset["dataset_sha256"] = claimed_dataset_sha
    if dataset.get("schema") != SCHEMA_V11 \
            or dataset.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("occlusion-recall dataset scope or schema mismatch")
    if dataset["splits"]["train"]["count"] == 0 \
            or dataset["splits"]["development"]["count"] == 0 \
            or dataset["splits"]["evaluation"]["count"] != 0:
        raise ValueError("occlusion-recall dataset must contain train and development only")

    seed_model_path = seed_candidate_dir / "model.json"
    seed_scorecard_path = seed_candidate_dir / "scorecard.json"
    seed_checkpoint, model = _load_target_conditioned_checkpoint(seed_candidate_dir)
    seed_policy = seed_checkpoint.get("localization_uncertainty_policy", {})
    if seed_checkpoint.get("evaluation_opened") is not False \
            or seed_policy.get("development_gate_met") is not True \
            or seed_policy.get("maximum_supported_planar_error_mm") != 1.0 \
            or dataset.get("target_catalog_sha256") \
            != seed_checkpoint.get("target_catalog_sha256"):
        raise ValueError("occlusion-recall seed identity or policy mismatch")
    seed_scorecard = json.loads(seed_scorecard_path.read_text(encoding="utf-8"))
    claimed_seed_scorecard_sha = seed_scorecard.pop("scorecard_sha256", None)
    if not isinstance(claimed_seed_scorecard_sha, str) \
            or _sha256(_canonical(seed_scorecard)) != claimed_seed_scorecard_sha:
        raise ValueError("occlusion-recall seed scorecard hash mismatch")
    seed_scorecard["scorecard_sha256"] = claimed_seed_scorecard_sha
    seed_model_sha = _sha256(seed_model_path.read_bytes())
    if seed_scorecard.get("schema") \
            != "rocell.ai_target_conditioned_fusion_candidate.v1" \
            or seed_scorecard.get("model_sha256") != seed_model_sha \
            or seed_scorecard.get("development_gate_met") is not True \
            or seed_scorecard.get("maximum_supported_planar_error_mm") != 1.0 \
            or seed_scorecard.get("hardware_writes") != 0 \
            or seed_scorecard.get("physical_movements") != 0 \
            or seed_scorecard.get("physical_authority") is not False:
        raise ValueError("occlusion-recall seed scorecard identity or authority mismatch")

    torch.manual_seed(BASELINE_SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    training_rows = _load_rows(dataset_dir, "train", dataset)
    development_rows = _load_rows(dataset_dir, "development", dataset)
    catalog = tuple(seed_checkpoint["architecture"]["target_catalog"])
    if set(_target_identity_catalog(training_rows)) != set(catalog) \
            or set(_target_identity_catalog(development_rows)) != set(catalog):
        raise ValueError("occlusion-recall target vocabulary mismatch")
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(name.startswith("conditioner."))

    augmentation = _training_augmentation_offsets()
    row_offsets = []
    augmentation_counts: dict[str, int] = {}
    for row in training_rows:
        index = int(_sha256(row["id"].encode("utf-8"))[:8], 16) % len(augmentation)
        offset = augmentation[index]
        row_offsets.append((offset["x_px"], offset["y_px"]))
        key = f"{offset['x_mm']:g},{offset['y_mm']:g}"
        augmentation_counts[key] = augmentation_counts.get(key, 0) + 1
    training_crops, training_labels = _target_aware_crops(
        dataset_dir, training_rows, row_offsets_px=row_offsets,
    )
    training_descriptors = _target_identity_descriptors(
        dataset_dir, training_rows, catalog,
    )
    crop_tensor = torch.from_numpy(training_crops)
    descriptor_tensor = torch.from_numpy(training_descriptors)
    label_tensor = torch.from_numpy(training_labels)
    loss_fn = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([OCCLUSION_RECALL_POSITIVE_WEIGHT]),
    )
    optimizer = torch.optim.Adam(
        model.conditioner.parameters(),
        lr=OCCLUSION_RECALL_LEARNING_RATE,
        weight_decay=0.0001,
    )
    epoch_losses = []
    model.train()
    for epoch in range(OCCLUSION_RECALL_EPOCHS):
        generator = torch.Generator().manual_seed(BASELINE_SEED + epoch)
        order = torch.randperm(len(crop_tensor), generator=generator)
        total_loss = 0.0
        for start in range(0, len(order), SPATIAL_BATCH_SIZE):
            indices = order[start:start + SPATIAL_BATCH_SIZE]
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(
                crop_tensor[indices], descriptor_tensor[indices],
            ), label_tensor[indices])
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
        epoch_losses.append(total_loss / len(order))

    model.eval()
    development_descriptors = torch.from_numpy(_target_identity_descriptors(
        dataset_dir, development_rows, catalog,
    ))
    development_labels: np.ndarray | None = None
    probabilities_by_offset = []
    for offset in _declared_mask_offsets():
        crops, labels = _target_aware_crops(
            dataset_dir, development_rows, (offset["x_px"], offset["y_px"]),
        )
        if development_labels is None:
            development_labels = labels.astype(np.float64)
        elif not np.array_equal(development_labels, labels):
            raise RuntimeError("occlusion-recall labels changed across offsets")
        with torch.no_grad():
            probabilities = torch.sigmoid(model(
                torch.from_numpy(crops), development_descriptors,
            )).numpy()
        probabilities_by_offset.append((offset, probabilities))
    assert development_labels is not None
    threshold, uncertainty_bound, gate_met, measurements = _select_localization_policy(
        development_rows, development_labels, probabilities_by_offset,
    )

    state = {
        name: {
            "shape": list(value.shape),
            "values": value.detach().cpu().numpy().astype(np.float64).reshape(-1).tolist(),
        }
        for name, value in sorted(model.state_dict().items())
    }
    checkpoint = {
        "schema": "rocell.ai_target_conditioned_occlusion_recall.v1",
        "architecture": dict(seed_checkpoint["architecture"]),
        "seed": {
            "model_sha256": seed_model_sha,
            "scorecard_sha256": claimed_seed_scorecard_sha,
        },
        "training": {
            "seed": BASELINE_SEED,
            "device": "cpu",
            "epochs": OCCLUSION_RECALL_EPOCHS,
            "batch_size": SPATIAL_BATCH_SIZE,
            "learning_rate": OCCLUSION_RECALL_LEARNING_RATE,
            "optimizer": "adam",
            "weight_decay": 0.0001,
            "loss": "positive_weighted_binary_cross_entropy",
            "positive_abstention_weight": OCCLUSION_RECALL_POSITIVE_WEIGHT,
            "trained_parameters": "conditioner_only",
            "augmentation": "one_deterministic_offset_per_training_row",
            "augmentation_offsets_mm": augmentation,
            "augmentation_counts": augmentation_counts,
            "epoch_losses": epoch_losses,
        },
        "crop": dict(seed_checkpoint["crop"]),
        "threshold": threshold,
        "localization_uncertainty_policy": {
            "maximum_supported_planar_error_mm": uncertainty_bound,
            "above_bound_decision": "abstain_localization_uncertain",
            "development_gate_met": gate_met,
            "maximum_missed_abstain_rate": 0.05,
            "maximum_visible_false_abstain_rate": 0.05,
        },
        "target_catalog_sha256": dataset["target_catalog_sha256"],
        "training_dataset_sha256": claimed_dataset_sha,
        "selection_dataset_sha256": claimed_dataset_sha,
        "selection_split": "development_only",
        "consumed_evaluation_dataset_sha256": None,
        "evaluation_opened": False,
        "state_dict": state,
    }
    checkpoint_path = output_dir / "model.json"
    checkpoint_path.write_bytes(_canonical(checkpoint) + b"\n")
    scorecard: dict[str, Any] = {
        "schema": "rocell.ai_occlusion_recall_candidate.v1",
        "algorithm": "seeded_target_conditioned_prepool_film_weighted_recall_v1",
        "seed_model_sha256": seed_model_sha,
        "seed_scorecard_sha256": claimed_seed_scorecard_sha,
        "dataset_manifest_sha256": _sha256(dataset_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "target_catalog_sha256": dataset["target_catalog_sha256"],
        "model_sha256": _sha256(checkpoint_path.read_bytes()),
        "selected_threshold": threshold,
        "maximum_supported_planar_error_mm": uncertainty_bound,
        "development_gate_met": gate_met,
        "development_measurements": measurements,
        "evaluation_group_present": False,
        "promotion_status": "BLOCKED_AWAITING_FRESH_EVALUATION"
        if gate_met else "FAILED_DEVELOPMENT_GATE",
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "training and policy selection use new synthetic v11 data only",
            "consumed v10 evaluation bytes are excluded from training and selection",
            "the uncertainty bound is synthetic and not a physical calibration",
            "no new evaluation group was created or opened",
            "tool and camera-support geometry remain absent",
        ],
    }
    scorecard["scorecard_sha256"] = _sha256(_canonical(scorecard))
    (output_dir / "scorecard.json").write_bytes(_canonical(scorecard) + b"\n")
    return scorecard

def train_specificity_rebalance_candidate(
    dataset_dir: Path,
    seed_candidate_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Rebalance only the frozen E-478 conditioner's synthetic specificity."""
    import torch

    dataset_dir = dataset_dir.resolve(strict=True)
    seed_candidate_dir = seed_candidate_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("specificity-rebalance output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = dataset_dir / "manifest.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = dataset.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) \
            or _sha256(_canonical(dataset)) != claimed_dataset_sha:
        raise ValueError("specificity-rebalance dataset manifest hash mismatch")
    dataset["dataset_sha256"] = claimed_dataset_sha
    if dataset.get("schema") != SCHEMA_V13 \
            or dataset.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("specificity-rebalance dataset scope or schema mismatch")
    if dataset["splits"]["train"]["count"] == 0 \
            or dataset["splits"]["development"]["count"] == 0 \
            or dataset["splits"]["evaluation"]["count"] != 0:
        raise ValueError("specificity-rebalance dataset must contain train and development only")

    seed_model_path = seed_candidate_dir / "model.json"
    seed_scorecard_path = seed_candidate_dir / "scorecard.json"
    seed_checkpoint, model = _load_target_conditioned_checkpoint(seed_candidate_dir)
    seed_policy = seed_checkpoint.get("localization_uncertainty_policy", {})
    seed_model_sha = _sha256(seed_model_path.read_bytes())
    if seed_checkpoint.get("schema") \
            != "rocell.ai_target_conditioned_occlusion_recall.v1" \
            or seed_model_sha != EXPECTED_OCCLUSION_RECALL_MODEL_SHA256 \
            or seed_checkpoint.get("evaluation_opened") is not False \
            or seed_policy.get("development_gate_met") is not True \
            or seed_policy.get("maximum_supported_planar_error_mm") != 0.0 \
            or dataset.get("target_catalog_sha256") \
            != seed_checkpoint.get("target_catalog_sha256"):
        raise ValueError("specificity-rebalance seed identity or policy mismatch")
    seed_scorecard = json.loads(seed_scorecard_path.read_text(encoding="utf-8"))
    claimed_seed_scorecard_sha = seed_scorecard.pop("scorecard_sha256", None)
    if not isinstance(claimed_seed_scorecard_sha, str) \
            or _sha256(_canonical(seed_scorecard)) != claimed_seed_scorecard_sha:
        raise ValueError("specificity-rebalance seed scorecard hash mismatch")
    seed_scorecard["scorecard_sha256"] = claimed_seed_scorecard_sha
    if claimed_seed_scorecard_sha != EXPECTED_OCCLUSION_RECALL_SCORECARD_SHA256 \
            or seed_scorecard.get("schema") \
            != "rocell.ai_occlusion_recall_candidate.v1" \
            or seed_scorecard.get("model_sha256") != seed_model_sha \
            or seed_scorecard.get("development_gate_met") is not True \
            or seed_scorecard.get("maximum_supported_planar_error_mm") != 0.0 \
            or seed_scorecard.get("hardware_writes") != 0 \
            or seed_scorecard.get("physical_movements") != 0 \
            or seed_scorecard.get("physical_authority") is not False:
        raise ValueError("specificity-rebalance seed scorecard identity or authority mismatch")

    torch.manual_seed(BASELINE_SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    training_rows = _load_rows(dataset_dir, "train", dataset)
    development_rows = _load_rows(dataset_dir, "development", dataset)
    catalog = tuple(seed_checkpoint["architecture"]["target_catalog"])
    if set(_target_identity_catalog(training_rows)) != set(catalog) \
            or set(_target_identity_catalog(development_rows)) != set(catalog):
        raise ValueError("specificity-rebalance target vocabulary mismatch")
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(name.startswith("conditioner."))

    augmentation = _training_augmentation_offsets()
    row_offsets = []
    augmentation_counts: dict[str, int] = {}
    for row in training_rows:
        index = int(_sha256(row["id"].encode("utf-8"))[:8], 16) % len(augmentation)
        offset = augmentation[index]
        row_offsets.append((offset["x_px"], offset["y_px"]))
        key = f"{offset['x_mm']:g},{offset['y_mm']:g}"
        augmentation_counts[key] = augmentation_counts.get(key, 0) + 1
    training_crops, training_labels = _target_aware_crops(
        dataset_dir, training_rows, row_offsets_px=row_offsets,
    )
    training_descriptors = _target_identity_descriptors(
        dataset_dir, training_rows, catalog,
    )
    crop_tensor = torch.from_numpy(training_crops)
    descriptor_tensor = torch.from_numpy(training_descriptors)
    label_tensor = torch.from_numpy(training_labels)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(
        model.conditioner.parameters(),
        lr=SPECIFICITY_REBALANCE_LEARNING_RATE,
        weight_decay=0.0001,
    )
    epoch_losses = []
    model.train()
    for epoch in range(SPECIFICITY_REBALANCE_EPOCHS):
        generator = torch.Generator().manual_seed(BASELINE_SEED + epoch)
        order = torch.randperm(len(crop_tensor), generator=generator)
        total_loss = 0.0
        for start in range(0, len(order), SPATIAL_BATCH_SIZE):
            indices = order[start:start + SPATIAL_BATCH_SIZE]
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(
                crop_tensor[indices], descriptor_tensor[indices],
            ), label_tensor[indices])
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
        epoch_losses.append(total_loss / len(order))

    model.eval()
    development_descriptors = torch.from_numpy(_target_identity_descriptors(
        dataset_dir, development_rows, catalog,
    ))
    development_labels: np.ndarray | None = None
    probabilities_by_offset = []
    for offset in _declared_mask_offsets():
        crops, labels = _target_aware_crops(
            dataset_dir, development_rows, (offset["x_px"], offset["y_px"]),
        )
        if development_labels is None:
            development_labels = labels.astype(np.float64)
        elif not np.array_equal(development_labels, labels):
            raise RuntimeError("specificity-rebalance labels changed across offsets")
        with torch.no_grad():
            probabilities = torch.sigmoid(model(
                torch.from_numpy(crops), development_descriptors,
            )).numpy()
        probabilities_by_offset.append((offset, probabilities))
    assert development_labels is not None
    threshold, uncertainty_bound, gate_met, measurements = _select_localization_policy(
        development_rows, development_labels, probabilities_by_offset,
    )

    state = {
        name: {
            "shape": list(value.shape),
            "values": value.detach().cpu().numpy().astype(np.float64).reshape(-1).tolist(),
        }
        for name, value in sorted(model.state_dict().items())
    }
    checkpoint = {
        "schema": "rocell.ai_target_conditioned_specificity_rebalance.v1",
        "architecture": dict(seed_checkpoint["architecture"]),
        "seed": {
            "model_sha256": seed_model_sha,
            "scorecard_sha256": claimed_seed_scorecard_sha,
        },
        "training": {
            "seed": BASELINE_SEED,
            "device": "cpu",
            "epochs": SPECIFICITY_REBALANCE_EPOCHS,
            "batch_size": SPATIAL_BATCH_SIZE,
            "learning_rate": SPECIFICITY_REBALANCE_LEARNING_RATE,
            "optimizer": "adam",
            "weight_decay": 0.0001,
            "loss": "binary_cross_entropy",
            "positive_abstention_weight": SPECIFICITY_REBALANCE_POSITIVE_WEIGHT,
            "trained_parameters": "conditioner_only",
            "augmentation": "one_deterministic_offset_per_training_row",
            "augmentation_offsets_mm": augmentation,
            "augmentation_counts": augmentation_counts,
            "epoch_losses": epoch_losses,
        },
        "crop": dict(seed_checkpoint["crop"]),
        "threshold": threshold,
        "localization_uncertainty_policy": {
            "maximum_supported_planar_error_mm": uncertainty_bound,
            "above_bound_decision": "abstain_localization_uncertain",
            "development_gate_met": gate_met,
            "maximum_missed_abstain_rate": 0.05,
            "maximum_visible_false_abstain_rate": 0.05,
        },
        "target_catalog_sha256": dataset["target_catalog_sha256"],
        "training_dataset_sha256": claimed_dataset_sha,
        "selection_dataset_sha256": claimed_dataset_sha,
        "selection_split": "development_only",
        "consumed_evaluation_dataset_sha256": None,
        "evaluation_opened": False,
        "state_dict": state,
    }
    checkpoint_path = output_dir / "model.json"
    checkpoint_path.write_bytes(_canonical(checkpoint) + b"\n")
    scorecard: dict[str, Any] = {
        "schema": "rocell.ai_specificity_rebalance_candidate.v1",
        "algorithm": "seeded_target_conditioned_prepool_film_specificity_rebalance_v1",
        "seed_model_sha256": seed_model_sha,
        "seed_scorecard_sha256": claimed_seed_scorecard_sha,
        "dataset_manifest_sha256": _sha256(dataset_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "target_catalog_sha256": dataset["target_catalog_sha256"],
        "model_sha256": _sha256(checkpoint_path.read_bytes()),
        "selected_threshold": threshold,
        "maximum_supported_planar_error_mm": uncertainty_bound,
        "development_gate_met": gate_met,
        "development_measurements": measurements,
        "evaluation_group_present": False,
        "promotion_status": "BLOCKED_AWAITING_FRESH_EVALUATION"
        if gate_met else "FAILED_DEVELOPMENT_GATE",
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "training and policy selection use new synthetic v13 data only",
            "consumed v12 evaluation bytes and identities are excluded from training and selection",
            "the uncertainty bound is synthetic and not a physical calibration",
            "no new evaluation group was created or opened",
            "tool and camera-support geometry remain absent",
        ],
    }
    scorecard["scorecard_sha256"] = _sha256(_canonical(scorecard))
    (output_dir / "scorecard.json").write_bytes(_canonical(scorecard) + b"\n")
    return scorecard


def _pose_cluster_bootstrap_bounds(
    rows: list[dict[str, Any]],
    labels: np.ndarray,
    probabilities_by_offset: list[tuple[dict[str, float], np.ndarray]],
    threshold: float,
    bound_mm: float,
    *,
    seed: int = POSE_CLUSTER_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Return one-sided 95% whole-pose bootstrap bounds for a frozen policy."""
    pose_ids = tuple(sorted({str(row["pose_id"]) for row in rows}))
    if len(pose_ids) < 2:
        raise ValueError("pose-cluster bootstrap requires at least two poses")
    pose_lookup = {pose_id: index for index, pose_id in enumerate(pose_ids)}
    row_pose = np.asarray([pose_lookup[str(row["pose_id"])] for row in rows])
    generator = np.random.default_rng(seed)
    sampled = generator.integers(
        0, len(pose_ids), size=(POSE_CLUSTER_BOOTSTRAP_SAMPLES, len(pose_ids)),
    )
    offset_results = []
    for offset, probabilities in probabilities_by_offset:
        if max(abs(offset["x_mm"]), abs(offset["y_mm"])) > bound_mm:
            continue
        predicted = probabilities >= threshold
        pose_counts = np.zeros((len(pose_ids), 4), dtype=np.int64)
        for pose_index in range(len(pose_ids)):
            selected = row_pose == pose_index
            pose_labels = labels[selected]
            pose_predicted = predicted[selected]
            pose_counts[pose_index] = (
                int(np.logical_and(pose_labels == 1, ~pose_predicted).sum()),
                int((pose_labels == 1).sum()),
                int(np.logical_and(pose_labels == 0, pose_predicted).sum()),
                int((pose_labels == 0).sum()),
            )
        totals = pose_counts[sampled].sum(axis=1)
        if np.any(totals[:, 1] == 0) or np.any(totals[:, 3] == 0):
            raise ValueError("pose bootstrap resample lacks one decision class")
        missed_rates = totals[:, 0] / totals[:, 1]
        false_rates = totals[:, 2] / totals[:, 3]
        offset_results.append({
            "offset": offset,
            "missed_abstain_upper_95": float(
                np.quantile(missed_rates, 0.95, method="higher")
            ),
            "visible_false_abstain_upper_95": float(
                np.quantile(false_rates, 0.95, method="higher")
            ),
        })
    if not offset_results:
        raise ValueError("pose bootstrap bound contains no offsets")
    return {
        "method": "seeded_whole_pose_nonparametric_bootstrap_one_sided_95",
        "seed": seed,
        "resamples": POSE_CLUSTER_BOOTSTRAP_SAMPLES,
        "pose_count": len(pose_ids),
        "bound_mm": bound_mm,
        "maximum_missed_abstain_upper_95": max(
            item["missed_abstain_upper_95"] for item in offset_results
        ),
        "maximum_visible_false_abstain_upper_95": max(
            item["visible_false_abstain_upper_95"] for item in offset_results
        ),
        "offsets": offset_results,
    }


def train_pose_diverse_successor_candidate(
    dataset_dir: Path,
    seed_candidate_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Train a pose-diverse successor without opening any evaluation group."""
    import torch

    dataset_dir = dataset_dir.resolve(strict=True)
    seed_candidate_dir = seed_candidate_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("pose-diverse output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = dataset_dir / "manifest.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = dataset.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) \
            or _sha256(_canonical(dataset)) != claimed_dataset_sha:
        raise ValueError("pose-diverse dataset manifest hash mismatch")
    dataset["dataset_sha256"] = claimed_dataset_sha
    if dataset.get("schema") != SCHEMA_V15 \
            or dataset.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("pose-diverse dataset scope or schema mismatch")
    if dataset["splits"]["train"]["count"] == 0 \
            or dataset["splits"]["development"]["count"] == 0 \
            or dataset["splits"]["evaluation"]["count"] != 0:
        raise ValueError("pose-diverse dataset must contain train and development only")
    seed_model_path = seed_candidate_dir / "model.json"
    seed_scorecard_path = seed_candidate_dir / "scorecard.json"
    seed_checkpoint, model = _load_target_conditioned_checkpoint(seed_candidate_dir)
    seed_model_sha = _sha256(seed_model_path.read_bytes())
    seed_policy = seed_checkpoint.get("localization_uncertainty_policy", {})
    if seed_checkpoint.get("schema") \
            != "rocell.ai_target_conditioned_specificity_rebalance.v1" \
            or seed_model_sha != EXPECTED_SPECIFICITY_REBALANCE_MODEL_SHA256 \
            or seed_checkpoint.get("evaluation_opened") is not False \
            or seed_policy.get("development_gate_met") is not True \
            or seed_policy.get("maximum_supported_planar_error_mm") != 2.0 \
            or dataset.get("target_catalog_sha256") \
            != seed_checkpoint.get("target_catalog_sha256"):
        raise ValueError("pose-diverse seed identity or policy mismatch")
    seed_scorecard = json.loads(seed_scorecard_path.read_text(encoding="utf-8"))
    claimed_seed_scorecard_sha = seed_scorecard.pop("scorecard_sha256", None)
    if not isinstance(claimed_seed_scorecard_sha, str) \
            or _sha256(_canonical(seed_scorecard)) != claimed_seed_scorecard_sha:
        raise ValueError("pose-diverse seed scorecard hash mismatch")
    seed_scorecard["scorecard_sha256"] = claimed_seed_scorecard_sha
    if claimed_seed_scorecard_sha != EXPECTED_SPECIFICITY_REBALANCE_SCORECARD_SHA256 \
            or seed_scorecard.get("schema") \
            != "rocell.ai_specificity_rebalance_candidate.v1" \
            or seed_scorecard.get("model_sha256") != seed_model_sha \
            or seed_scorecard.get("evaluation_group_present") is not False \
            or seed_scorecard.get("development_gate_met") is not True \
            or seed_scorecard.get("maximum_supported_planar_error_mm") != 2.0 \
            or seed_scorecard.get("hardware_writes") != 0 \
            or seed_scorecard.get("physical_movements") != 0 \
            or seed_scorecard.get("physical_authority") is not False:
        raise ValueError("pose-diverse seed scorecard identity or authority mismatch")

    torch.manual_seed(BASELINE_SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    training_rows = _load_rows(dataset_dir, "train", dataset)
    development_rows = _load_rows(dataset_dir, "development", dataset)
    if len({row["pose_id"] for row in training_rows}) != 72 \
            or len({row["pose_id"] for row in development_rows}) != 24:
        raise ValueError("pose-diverse dataset has wrong pose partition")
    catalog = tuple(seed_checkpoint["architecture"]["target_catalog"])
    if set(_target_identity_catalog(training_rows)) != set(catalog) \
            or set(_target_identity_catalog(development_rows)) != set(catalog):
        raise ValueError("pose-diverse target vocabulary mismatch")
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(name.startswith("conditioner."))

    augmentation = _training_augmentation_offsets()
    row_offsets = []
    augmentation_counts: dict[str, int] = {}
    for row in training_rows:
        index = int(_sha256(row["id"].encode("utf-8"))[:8], 16) % len(augmentation)
        offset = augmentation[index]
        row_offsets.append((offset["x_px"], offset["y_px"]))
        key = f"{offset['x_mm']:g},{offset['y_mm']:g}"
        augmentation_counts[key] = augmentation_counts.get(key, 0) + 1
    training_crops, training_labels = _target_aware_crops(
        dataset_dir, training_rows, row_offsets_px=row_offsets,
    )
    training_descriptors = _target_identity_descriptors(
        dataset_dir, training_rows, catalog,
    )
    crop_tensor = torch.from_numpy(training_crops)
    descriptor_tensor = torch.from_numpy(training_descriptors)
    label_tensor = torch.from_numpy(training_labels)
    loss_fn = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([POSE_DIVERSE_POSITIVE_WEIGHT]),
    )
    optimizer = torch.optim.Adam(
        model.conditioner.parameters(),
        lr=POSE_DIVERSE_LEARNING_RATE,
        weight_decay=0.0001,
    )
    epoch_losses = []
    model.train()
    for epoch in range(POSE_DIVERSE_EPOCHS):
        generator = torch.Generator().manual_seed(BASELINE_SEED + epoch)
        order = torch.randperm(len(crop_tensor), generator=generator)
        total_loss = 0.0
        for start in range(0, len(order), SPATIAL_BATCH_SIZE):
            indices = order[start:start + SPATIAL_BATCH_SIZE]
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(
                model(crop_tensor[indices], descriptor_tensor[indices]),
                label_tensor[indices],
            )
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
        epoch_losses.append(total_loss / len(order))

    model.eval()
    development_descriptors = torch.from_numpy(_target_identity_descriptors(
        dataset_dir, development_rows, catalog,
    ))
    development_labels: np.ndarray | None = None
    probabilities_by_offset = []
    for offset in _declared_mask_offsets():
        crops, labels = _target_aware_crops(
            dataset_dir, development_rows, (offset["x_px"], offset["y_px"]),
        )
        if development_labels is None:
            development_labels = labels.astype(np.float64)
        elif not np.array_equal(development_labels, labels):
            raise RuntimeError("pose-diverse labels changed across offsets")
        with torch.no_grad():
            probabilities = torch.sigmoid(model(
                torch.from_numpy(crops), development_descriptors,
            )).numpy()
        probabilities_by_offset.append((offset, probabilities))
    assert development_labels is not None
    threshold, uncertainty_bound, point_gate_met, measurements = (
        _select_localization_policy(
            development_rows,
            development_labels,
            probabilities_by_offset,
            maximum_missed_rate=0.02,
            maximum_false_rate=0.10,
        )
    )
    bootstrap = _pose_cluster_bootstrap_bounds(
        development_rows,
        development_labels,
        probabilities_by_offset,
        threshold,
        uncertainty_bound,
    )
    clustered_gate_met = (
        bootstrap["maximum_missed_abstain_upper_95"] <= 0.02
        and bootstrap["maximum_visible_false_abstain_upper_95"] <= 0.10
    )
    gate_met = point_gate_met and clustered_gate_met

    state = {
        name: {
            "shape": list(value.shape),
            "values": value.detach().cpu().numpy().astype(np.float64).reshape(-1).tolist(),
        }
        for name, value in sorted(model.state_dict().items())
    }
    checkpoint = {
        "schema": "rocell.ai_target_conditioned_pose_diverse.v1",
        "architecture": dict(seed_checkpoint["architecture"]),
        "seed": {
            "model_sha256": seed_model_sha,
            "scorecard_sha256": claimed_seed_scorecard_sha,
        },
        "training": {
            "seed": BASELINE_SEED,
            "device": "cpu",
            "epochs": POSE_DIVERSE_EPOCHS,
            "batch_size": SPATIAL_BATCH_SIZE,
            "learning_rate": POSE_DIVERSE_LEARNING_RATE,
            "optimizer": "adam",
            "weight_decay": 0.0001,
            "loss": "positive_weighted_binary_cross_entropy",
            "positive_abstention_weight": POSE_DIVERSE_POSITIVE_WEIGHT,
            "trained_parameters": "conditioner_only",
            "augmentation": "one_deterministic_offset_per_training_row",
            "augmentation_offsets_mm": augmentation,
            "augmentation_counts": augmentation_counts,
            "epoch_losses": epoch_losses,
        },
        "crop": dict(seed_checkpoint["crop"]),
        "threshold": threshold,
        "localization_uncertainty_policy": {
            "maximum_supported_planar_error_mm": uncertainty_bound,
            "above_bound_decision": "abstain_localization_uncertain",
            "point_gate_met": point_gate_met,
            "pose_cluster_upper_bound_gate_met": clustered_gate_met,
            "development_gate_met": gate_met,
            "maximum_missed_abstain_rate": 0.02,
            "maximum_visible_false_abstain_rate": 0.10,
        },
        "target_catalog_sha256": dataset["target_catalog_sha256"],
        "training_dataset_sha256": claimed_dataset_sha,
        "selection_dataset_sha256": claimed_dataset_sha,
        "selection_split": "development_only",
        "consumed_evaluation_dataset_sha256": None,
        "evaluation_opened": False,
        "state_dict": state,
    }
    checkpoint_path = output_dir / "model.json"
    checkpoint_path.write_bytes(_canonical(checkpoint) + b"\n")
    scorecard: dict[str, Any] = {
        "schema": "rocell.ai_pose_diverse_candidate.v1",
        "algorithm": "seeded_target_conditioned_pose_diverse_film_v1",
        "seed_model_sha256": seed_model_sha,
        "seed_scorecard_sha256": claimed_seed_scorecard_sha,
        "dataset_manifest_sha256": _sha256(dataset_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "target_catalog_sha256": dataset["target_catalog_sha256"],
        "model_sha256": _sha256(checkpoint_path.read_bytes()),
        "selected_threshold": threshold,
        "maximum_supported_planar_error_mm": uncertainty_bound,
        "point_gate_met": point_gate_met,
        "pose_cluster_upper_bound_gate_met": clustered_gate_met,
        "development_gate_met": gate_met,
        "development_measurements": measurements,
        "pose_cluster_bootstrap": bootstrap,
        "evaluation_group_present": False,
        "promotion_status": (
            "BLOCKED_AWAITING_FRESH_EVALUATION"
            if gate_met else "FAILED_DEVELOPMENT_GATE"
        ),
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "training and policy selection use new synthetic v15 data only",
            "consumed v14 images, labels, probabilities, failures, poses, lighting, and threshold outcomes are excluded",
            "whole-pose bootstrap bounds describe this synthetic development corpus only",
            "dense samples cover one governed path rather than arbitrary arm configurations",
            "the uncertainty bound is synthetic and not physical calibration",
            "no new evaluation group was created or opened",
            "tool and camera-support geometry remain absent",
        ],
    }
    scorecard["scorecard_sha256"] = _sha256(_canonical(scorecard))
    (output_dir / "scorecard.json").write_bytes(_canonical(scorecard) + b"\n")
    return scorecard

def train_grouped_neighborhood_successor_candidate(
    dataset_dir: Path,
    seed_candidate_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Train a grouped-neighborhood successor without opening any evaluation group."""
    import torch

    dataset_dir = dataset_dir.resolve(strict=True)
    seed_candidate_dir = seed_candidate_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("grouped-neighborhood output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = dataset_dir / "manifest.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = dataset.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) \
            or _sha256(_canonical(dataset)) != claimed_dataset_sha:
        raise ValueError("grouped-neighborhood dataset manifest hash mismatch")
    dataset["dataset_sha256"] = claimed_dataset_sha
    if dataset.get("schema") != SCHEMA_V16 \
            or dataset.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("grouped-neighborhood dataset scope or schema mismatch")
    if dataset["splits"]["train"]["count"] == 0 \
            or dataset["splits"]["development"]["count"] == 0 \
            or dataset["splits"]["evaluation"]["count"] != 0:
        raise ValueError("grouped-neighborhood dataset must contain train and development only")
    seed_model_path = seed_candidate_dir / "model.json"
    seed_scorecard_path = seed_candidate_dir / "scorecard.json"
    seed_checkpoint, model = _load_target_conditioned_checkpoint(seed_candidate_dir)
    seed_model_sha = _sha256(seed_model_path.read_bytes())
    seed_policy = seed_checkpoint.get("localization_uncertainty_policy", {})
    if seed_checkpoint.get("schema") \
            != "rocell.ai_target_conditioned_pose_diverse.v1" \
            or seed_model_sha != EXPECTED_POSE_DIVERSE_MODEL_SHA256 \
            or seed_checkpoint.get("evaluation_opened") is not False \
            or seed_policy.get("development_gate_met") is not False \
            or seed_policy.get("maximum_supported_planar_error_mm") != 1.0 \
            or dataset.get("target_catalog_sha256") \
            != seed_checkpoint.get("target_catalog_sha256"):
        raise ValueError("grouped-neighborhood seed identity or policy mismatch")
    seed_scorecard = json.loads(seed_scorecard_path.read_text(encoding="utf-8"))
    claimed_seed_scorecard_sha = seed_scorecard.pop("scorecard_sha256", None)
    if not isinstance(claimed_seed_scorecard_sha, str) \
            or _sha256(_canonical(seed_scorecard)) != claimed_seed_scorecard_sha:
        raise ValueError("grouped-neighborhood seed scorecard hash mismatch")
    seed_scorecard["scorecard_sha256"] = claimed_seed_scorecard_sha
    if claimed_seed_scorecard_sha != EXPECTED_POSE_DIVERSE_SCORECARD_SHA256 \
            or seed_scorecard.get("schema") \
            != "rocell.ai_pose_diverse_candidate.v1" \
            or seed_scorecard.get("model_sha256") != seed_model_sha \
            or seed_scorecard.get("evaluation_group_present") is not False \
            or seed_scorecard.get("development_gate_met") is not False \
            or seed_scorecard.get("maximum_supported_planar_error_mm") != 1.0 \
            or seed_scorecard.get("hardware_writes") != 0 \
            or seed_scorecard.get("physical_movements") != 0 \
            or seed_scorecard.get("physical_authority") is not False:
        raise ValueError("grouped-neighborhood seed scorecard identity or authority mismatch")

    torch.manual_seed(BASELINE_SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    training_rows = _load_rows(dataset_dir, "train", dataset)
    development_rows = _load_rows(dataset_dir, "development", dataset)
    if len({row["pose_id"] for row in training_rows}) != 256 \
            or len({row["pose_id"] for row in development_rows}) != 64:
        raise ValueError("grouped-neighborhood dataset has wrong pose partition")
    catalog = tuple(seed_checkpoint["architecture"]["target_catalog"])
    if set(_target_identity_catalog(training_rows)) != set(catalog) \
            or set(_target_identity_catalog(development_rows)) != set(catalog):
        raise ValueError("grouped-neighborhood target vocabulary mismatch")
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(
            name.startswith(("conv2.", "conditioner.", "classifier."))
        )

    augmentation = _training_augmentation_offsets()
    row_offsets = []
    augmentation_counts: dict[str, int] = {}
    for row in training_rows:
        index = int(_sha256(row["id"].encode("utf-8"))[:8], 16) % len(augmentation)
        offset = augmentation[index]
        row_offsets.append((offset["x_px"], offset["y_px"]))
        key = f"{offset['x_mm']:g},{offset['y_mm']:g}"
        augmentation_counts[key] = augmentation_counts.get(key, 0) + 1
    training_crops, training_labels = _target_aware_crops(
        dataset_dir, training_rows, row_offsets_px=row_offsets,
    )
    training_descriptors = _target_identity_descriptors(
        dataset_dir, training_rows, catalog,
    )
    crop_tensor = torch.from_numpy(training_crops)
    descriptor_tensor = torch.from_numpy(training_descriptors)
    label_tensor = torch.from_numpy(training_labels)
    emphasis_tensor = torch.tensor([
        GROUPED_NEIGHBORHOOD_TARGET_EMPHASIS
        if row["target_id"] in GROUPED_NEIGHBORHOOD_EMPHASIZED_TARGETS else 1.0
        for row in training_rows
    ], dtype=torch.float32)
    loss_fn = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([GROUPED_NEIGHBORHOOD_POSITIVE_WEIGHT]),
        reduction="none",
    )
    optimizer = torch.optim.Adam(
        (parameter for parameter in model.parameters() if parameter.requires_grad),
        lr=GROUPED_NEIGHBORHOOD_LEARNING_RATE,
        weight_decay=0.0001,
    )
    epoch_losses = []
    model.train()
    for epoch in range(GROUPED_NEIGHBORHOOD_EPOCHS):
        generator = torch.Generator().manual_seed(BASELINE_SEED + epoch)
        order = torch.randperm(len(crop_tensor), generator=generator)
        total_loss = 0.0
        for start in range(0, len(order), SPATIAL_BATCH_SIZE):
            indices = order[start:start + SPATIAL_BATCH_SIZE]
            optimizer.zero_grad(set_to_none=True)
            row_loss = loss_fn(
                model(crop_tensor[indices], descriptor_tensor[indices]),
                label_tensor[indices],
            )
            loss = (row_loss * emphasis_tensor[indices]).sum() \
                / emphasis_tensor[indices].sum()
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
        epoch_losses.append(total_loss / len(order))

    model.eval()
    development_descriptors = torch.from_numpy(_target_identity_descriptors(
        dataset_dir, development_rows, catalog,
    ))
    development_labels: np.ndarray | None = None
    probabilities_by_offset = []
    for offset in _declared_mask_offsets():
        crops, labels = _target_aware_crops(
            dataset_dir, development_rows, (offset["x_px"], offset["y_px"]),
        )
        if development_labels is None:
            development_labels = labels.astype(np.float64)
        elif not np.array_equal(development_labels, labels):
            raise RuntimeError("grouped-neighborhood labels changed across offsets")
        with torch.no_grad():
            probabilities = torch.sigmoid(model(
                torch.from_numpy(crops), development_descriptors,
            )).numpy()
        probabilities_by_offset.append((offset, probabilities))
    assert development_labels is not None
    threshold, uncertainty_bound, point_gate_met, measurements = (
        _select_localization_policy(
            development_rows,
            development_labels,
            probabilities_by_offset,
            maximum_missed_rate=0.02,
            maximum_false_rate=0.10,
        )
    )
    bootstrap = _pose_cluster_bootstrap_bounds(
        development_rows,
        development_labels,
        probabilities_by_offset,
        threshold,
        uncertainty_bound, seed=GROUPED_NEIGHBORHOOD_BOOTSTRAP_SEED,
    )
    clustered_gate_met = (
        bootstrap["maximum_missed_abstain_upper_95"] <= 0.02
        and bootstrap["maximum_visible_false_abstain_upper_95"] <= 0.10
    )
    gate_met = point_gate_met and clustered_gate_met

    state = {
        name: {
            "shape": list(value.shape),
            "values": value.detach().cpu().numpy().astype(np.float64).reshape(-1).tolist(),
        }
        for name, value in sorted(model.state_dict().items())
    }
    checkpoint = {
        "schema": "rocell.ai_target_conditioned_grouped_neighborhood.v1",
        "architecture": dict(seed_checkpoint["architecture"]),
        "seed": {
            "model_sha256": seed_model_sha,
            "scorecard_sha256": claimed_seed_scorecard_sha,
        },
        "training": {
            "seed": BASELINE_SEED,
            "device": "cpu",
            "epochs": GROUPED_NEIGHBORHOOD_EPOCHS,
            "batch_size": SPATIAL_BATCH_SIZE,
            "learning_rate": GROUPED_NEIGHBORHOOD_LEARNING_RATE,
            "optimizer": "adam",
            "weight_decay": 0.0001,
            "loss": "positive_weighted_binary_cross_entropy",
            "positive_abstention_weight": GROUPED_NEIGHBORHOOD_POSITIVE_WEIGHT,
            "trained_parameters": "conv2_conditioner_classifier",
            "target_emphasis": {
                "weight": GROUPED_NEIGHBORHOOD_TARGET_EMPHASIS,
                "target_ids": list(GROUPED_NEIGHBORHOOD_EMPHASIZED_TARGETS),
            },
            "augmentation": "one_deterministic_offset_per_training_row",
            "augmentation_offsets_mm": augmentation,
            "augmentation_counts": augmentation_counts,
            "epoch_losses": epoch_losses,
        },
        "crop": dict(seed_checkpoint["crop"]),
        "threshold": threshold,
        "localization_uncertainty_policy": {
            "maximum_supported_planar_error_mm": uncertainty_bound,
            "above_bound_decision": "abstain_localization_uncertain",
            "point_gate_met": point_gate_met,
            "pose_cluster_upper_bound_gate_met": clustered_gate_met,
            "development_gate_met": gate_met,
            "maximum_missed_abstain_rate": 0.02,
            "maximum_visible_false_abstain_rate": 0.10,
        },
        "target_catalog_sha256": dataset["target_catalog_sha256"],
        "training_dataset_sha256": claimed_dataset_sha,
        "selection_dataset_sha256": claimed_dataset_sha,
        "selection_split": "development_only",
        "consumed_evaluation_dataset_sha256": None,
        "evaluation_opened": False,
        "state_dict": state,
    }
    checkpoint_path = output_dir / "model.json"
    checkpoint_path.write_bytes(_canonical(checkpoint) + b"\n")
    scorecard: dict[str, Any] = {
        "schema": "rocell.ai_grouped_neighborhood_candidate.v1",
        "algorithm": "seeded_target_conditioned_grouped_neighborhood_v1",
        "seed_model_sha256": seed_model_sha,
        "seed_scorecard_sha256": claimed_seed_scorecard_sha,
        "dataset_manifest_sha256": _sha256(dataset_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "target_catalog_sha256": dataset["target_catalog_sha256"],
        "model_sha256": _sha256(checkpoint_path.read_bytes()),
        "selected_threshold": threshold,
        "maximum_supported_planar_error_mm": uncertainty_bound,
        "point_gate_met": point_gate_met,
        "pose_cluster_upper_bound_gate_met": clustered_gate_met,
        "development_gate_met": gate_met,
        "development_measurements": measurements,
        "pose_cluster_bootstrap": bootstrap,
        "evaluation_group_present": False,
        "promotion_status": (
            "BLOCKED_AWAITING_FRESH_EVALUATION"
            if gate_met else "FAILED_DEVELOPMENT_GATE"
        ),
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "training and policy selection use new synthetic v16 data only",
            "consumed v14 evaluation and v15 development evidence are excluded from selection and evaluation",
            "whole-pose bootstrap bounds describe this synthetic development corpus only",
            "dense samples cover one governed path rather than arbitrary arm configurations",
            "the uncertainty bound is synthetic and not physical calibration",
            "no new evaluation group was created or opened",
            "tool and camera-support geometry remain absent",
        ],
    }
    scorecard["scorecard_sha256"] = _sha256(_canonical(scorecard))
    (output_dir / "scorecard.json").write_bytes(_canonical(scorecard) + b"\n")
    return scorecard


def refreeze_localization_policy(
    development_dataset_dir: Path,
    candidate_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Refreeze only the threshold and uncertainty bound of a frozen candidate."""
    import torch

    development_dataset_dir = development_dataset_dir.resolve(strict=True)
    candidate_dir = candidate_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("localization policy refreeze output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = development_dataset_dir / "manifest.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = dataset.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) \
            or _sha256(_canonical(dataset)) != claimed_dataset_sha:
        raise ValueError("localization policy dataset manifest hash mismatch")
    dataset["dataset_sha256"] = claimed_dataset_sha
    if dataset.get("schema") != SCHEMA_V6 \
            or dataset.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("localization policy dataset scope or schema mismatch")
    if dataset["splits"]["train"]["count"] != 0 \
            or dataset["splits"]["evaluation"]["count"] != 0:
        raise ValueError("localization policy dataset must be development-only")

    model_path = candidate_dir / "model.json"
    scorecard_path = candidate_dir / "scorecard.json"
    checkpoint, model = _load_spatial_checkpoint(candidate_dir)
    if checkpoint.get("schema") \
            != "rocell.ai_target_crop_localization_robust_spatial.v1":
        raise ValueError("policy refreeze requires localization-robust checkpoint")
    if checkpoint.get("evaluation_opened") is not False \
            or checkpoint.get("selection_dataset_sha256") != claimed_dataset_sha:
        raise ValueError("policy refreeze checkpoint opened evaluation or changed selection data")
    source_scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    claimed_scorecard_sha = source_scorecard.pop("scorecard_sha256", None)
    if not isinstance(claimed_scorecard_sha, str) \
            or _sha256(_canonical(source_scorecard)) != claimed_scorecard_sha:
        raise ValueError("localization policy source scorecard hash mismatch")
    source_scorecard["scorecard_sha256"] = claimed_scorecard_sha
    source_model_sha = _sha256(model_path.read_bytes())
    if source_scorecard.get("model_sha256") != source_model_sha \
            or source_scorecard.get("development_dataset_sha256") != claimed_dataset_sha \
            or source_scorecard.get("hardware_writes") != 0 \
            or source_scorecard.get("physical_movements") != 0:
        raise ValueError("localization policy source identity or authority mismatch")

    rows = _load_rows(development_dataset_dir, "development", dataset)
    labels_ref: np.ndarray | None = None
    probabilities_by_offset = []
    for offset in _declared_mask_offsets():
        crops, labels = _target_aware_crops(
            development_dataset_dir, rows, (offset["x_px"], offset["y_px"]),
        )
        labels = labels.astype(np.float64)
        if labels_ref is None:
            labels_ref = labels
        elif not np.array_equal(labels_ref, labels):
            raise RuntimeError("development labels changed across offsets")
        with torch.no_grad():
            probabilities = torch.sigmoid(model(torch.from_numpy(crops))).numpy()
        probabilities_by_offset.append((offset, probabilities))
    assert labels_ref is not None
    threshold, uncertainty_bound, gate_met, measurements = _select_localization_policy(
        rows, labels_ref, probabilities_by_offset,
    )

    refrozen_checkpoint = json.loads(json.dumps(checkpoint))
    refrozen_checkpoint["threshold"] = threshold
    refrozen_checkpoint["localization_uncertainty_policy"] = {
        "maximum_supported_planar_error_mm": uncertainty_bound,
        "above_bound_decision": "abstain_localization_uncertain",
        "development_gate_met": gate_met,
        "maximum_missed_abstain_rate": 0.05,
        "maximum_visible_false_abstain_rate": 0.05,
    }
    refrozen_checkpoint["policy_selection"] = {
        "method": "fixed_millithreshold_grid_v1",
        "threshold_minimum": 0.05,
        "threshold_maximum": 0.95,
        "threshold_step": 0.001,
        "source_model_sha256": source_model_sha,
        "source_scorecard_sha256": claimed_scorecard_sha,
        "weights_changed": False,
    }
    checkpoint_path = output_dir / "model.json"
    checkpoint_path.write_bytes(_canonical(refrozen_checkpoint) + b"\n")
    scorecard: dict[str, Any] = {
        "schema": "rocell.ai_localization_policy_refreeze.v1",
        "algorithm": "frozen_weights_fixed_millithreshold_grid_v1",
        "source_model_sha256": source_model_sha,
        "source_scorecard_sha256": claimed_scorecard_sha,
        "development_dataset_manifest_sha256": _sha256(dataset_path.read_bytes()),
        "development_dataset_sha256": claimed_dataset_sha,
        "model_sha256": _sha256(checkpoint_path.read_bytes()),
        "weights_changed": False,
        "selected_threshold": threshold,
        "maximum_supported_planar_error_mm": uncertainty_bound,
        "development_gate_met": gate_met,
        "development_measurements": measurements,
        "evaluation_group_present": False,
        "evaluation_opened": False,
        "promotion_status": "BLOCKED_AWAITING_FRESH_EVALUATION",
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "policy selection uses synthetic development data only",
            "the uncertainty bound is synthetic and not a physical calibration",
            "model weights are unchanged from the source checkpoint",
            "no evaluation group was created or opened",
            "tool and camera-support geometry remain absent",
        ],
    }
    scorecard["scorecard_sha256"] = _sha256(_canonical(scorecard))
    (output_dir / "scorecard.json").write_bytes(_canonical(scorecard) + b"\n")
    return scorecard


def evaluate_localization_policy(
    evaluation_dataset_dir: Path,
    candidate_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Open one synthetic evaluation group for a previously frozen policy."""
    import torch

    evaluation_dataset_dir = evaluation_dataset_dir.resolve(strict=True)
    candidate_dir = candidate_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("localization policy evaluation output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = evaluation_dataset_dir / "manifest.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = dataset.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) \
            or _sha256(_canonical(dataset)) != claimed_dataset_sha:
        raise ValueError("localization evaluation dataset manifest hash mismatch")
    dataset["dataset_sha256"] = claimed_dataset_sha
    if dataset.get("schema") != SCHEMA_V7 \
            or dataset.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("localization evaluation dataset scope or schema mismatch")
    if dataset["splits"]["train"]["count"] != 0 \
            or dataset["splits"]["development"]["count"] != 0 \
            or dataset["splits"]["evaluation"]["count"] == 0:
        raise ValueError("localization evaluation dataset must be evaluation-only")

    model_path = candidate_dir / "model.json"
    scorecard_path = candidate_dir / "scorecard.json"
    checkpoint, model = _load_spatial_checkpoint(candidate_dir)
    if checkpoint.get("schema") \
            != "rocell.ai_target_crop_localization_robust_spatial.v1":
        raise ValueError("evaluation requires localization-robust checkpoint")
    policy = checkpoint.get("localization_uncertainty_policy", {})
    if checkpoint.get("evaluation_opened") is not False \
            or policy.get("development_gate_met") is not True \
            or policy.get("maximum_supported_planar_error_mm") != 1.0 \
            or policy.get("above_bound_decision") != "abstain_localization_uncertain":
        raise ValueError("evaluation candidate policy is not the frozen 1 mm policy")
    source_scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    claimed_scorecard_sha = source_scorecard.pop("scorecard_sha256", None)
    if not isinstance(claimed_scorecard_sha, str) \
            or _sha256(_canonical(source_scorecard)) != claimed_scorecard_sha:
        raise ValueError("localization evaluation scorecard hash mismatch")
    source_scorecard["scorecard_sha256"] = claimed_scorecard_sha
    model_sha = _sha256(model_path.read_bytes())
    if source_scorecard.get("schema") != "rocell.ai_localization_policy_refreeze.v1" \
            or source_scorecard.get("model_sha256") != model_sha \
            or source_scorecard.get("evaluation_opened") is not False \
            or source_scorecard.get("weights_changed") is not False \
            or source_scorecard.get("hardware_writes") != 0 \
            or source_scorecard.get("physical_movements") != 0:
        raise ValueError("localization evaluation candidate identity or authority mismatch")

    rows = _load_rows(evaluation_dataset_dir, "evaluation", dataset)
    offsets = [
        offset for offset in _declared_mask_offsets()
        if max(abs(offset["x_mm"]), abs(offset["y_mm"])) <= 1.0
    ]
    labels_ref: np.ndarray | None = None
    measurements = []
    target_failures: dict[str, dict[str, int]] = {}
    rows_by_id = {row["id"]: row for row in rows}
    threshold = float(checkpoint["threshold"])
    for offset in offsets:
        crops, labels = _target_aware_crops(
            evaluation_dataset_dir, rows, (offset["x_px"], offset["y_px"]),
        )
        labels = labels.astype(np.float64)
        if labels_ref is None:
            labels_ref = labels
        elif not np.array_equal(labels_ref, labels):
            raise RuntimeError("evaluation labels changed across offsets")
        with torch.no_grad():
            probabilities = torch.sigmoid(model(torch.from_numpy(crops))).numpy()
        metrics = _metrics(rows, labels, probabilities, threshold)
        for failure in metrics["failures"]:
            row = rows_by_id[failure["id"]]
            key = f"{row['device']}:{row['target_id']}"
            counts = target_failures.setdefault(
                key, {"false_abstain": 0, "missed_abstain": 0},
            )
            counts[
                "missed_abstain"
                if failure["expected"] == "abstain" else "false_abstain"
            ] += 1
        measurements.append({"offset": offset, "metrics": metrics})
    assert labels_ref is not None
    abstain_count = int(labels_ref.sum())
    visible_count = len(labels_ref) - abstain_count
    if abstain_count == 0 or visible_count == 0:
        raise ValueError("localization evaluation requires abstain and visible rows")
    missed_rates = [
        item["metrics"]["confusion"]["missed_abstain"] / abstain_count
        for item in measurements
    ]
    false_rates = [
        item["metrics"]["confusion"]["false_abstain"] / visible_count
        for item in measurements
    ]
    gate_met = max(missed_rates) <= 0.05 and max(false_rates) <= 0.05
    report: dict[str, Any] = {
        "schema": "rocell.ai_localization_policy_evaluation.v1",
        "scope": "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION",
        "dataset_manifest_sha256": _sha256(dataset_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "model_sha256": model_sha,
        "source_scorecard_sha256": claimed_scorecard_sha,
        "threshold": threshold,
        "evaluated_planar_error_bound_mm": 1.0,
        "evaluation_opened": True,
        "evaluation_row_count": len(rows),
        "abstain_row_count": abstain_count,
        "visible_row_count": visible_count,
        "maximum_missed_abstain_rate": max(missed_rates),
        "maximum_visible_false_abstain_rate": max(false_rates),
        "synthetic_gate_met": gate_met,
        "measurements": measurements,
        "per_target_failure_counts_across_offsets": target_failures,
        "promotion_status": "BLOCKED_SYNTHETIC_ONLY",
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "the evaluation camera, geometry, images, labels, and offsets are synthetic",
            "the 1 mm offset uses nominal camera geometry, not physical calibration",
            "this evaluation group is consumed and cannot tune a successor",
            "tool and camera-support geometry remain absent",
            "a passing synthetic gate cannot qualify deployment",
        ],
    }
    report["report_sha256"] = _sha256(_canonical(report))
    (output_dir / "report.json").write_bytes(_canonical(report) + b"\n")
    return report


def evaluate_target_conditioned_fusion(
    evaluation_dataset_dir: Path,
    candidate_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Evaluate one frozen fusion checkpoint on one fresh synthetic group."""
    import torch

    evaluation_dataset_dir = evaluation_dataset_dir.resolve(strict=True)
    candidate_dir = candidate_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("target-conditioned evaluation output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = evaluation_dataset_dir / "manifest.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = dataset.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) \
            or _sha256(_canonical(dataset)) != claimed_dataset_sha:
        raise ValueError("target-conditioned evaluation dataset manifest hash mismatch")
    dataset["dataset_sha256"] = claimed_dataset_sha
    if dataset.get("schema") != SCHEMA_V10 \
            or dataset.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("target-conditioned evaluation dataset scope or schema mismatch")
    if dataset["splits"]["train"]["count"] != 0 \
            or dataset["splits"]["development"]["count"] != 0 \
            or dataset["splits"]["evaluation"]["count"] == 0:
        raise ValueError("target-conditioned evaluation dataset must be evaluation-only")

    model_path = candidate_dir / "model.json"
    scorecard_path = candidate_dir / "scorecard.json"
    checkpoint, model = _load_target_conditioned_checkpoint(candidate_dir)
    policy = checkpoint.get("localization_uncertainty_policy", {})
    if checkpoint.get("evaluation_opened") is not False \
            or policy.get("development_gate_met") is not True \
            or policy.get("maximum_supported_planar_error_mm") != 1.0 \
            or policy.get("above_bound_decision") != "abstain_localization_uncertain":
        raise ValueError("target-conditioned candidate is not the frozen 1 mm policy")
    if dataset.get("target_catalog_sha256") != checkpoint.get("target_catalog_sha256"):
        raise ValueError("target-conditioned evaluation target catalog mismatch")

    source_scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    claimed_scorecard_sha = source_scorecard.pop("scorecard_sha256", None)
    if not isinstance(claimed_scorecard_sha, str) \
            or _sha256(_canonical(source_scorecard)) != claimed_scorecard_sha:
        raise ValueError("target-conditioned candidate scorecard hash mismatch")
    source_scorecard["scorecard_sha256"] = claimed_scorecard_sha
    model_sha = _sha256(model_path.read_bytes())
    if source_scorecard.get("schema") \
            != "rocell.ai_target_conditioned_fusion_candidate.v1" \
            or source_scorecard.get("model_sha256") != model_sha \
            or source_scorecard.get("evaluation_group_present") is not False \
            or source_scorecard.get("development_gate_met") is not True \
            or source_scorecard.get("maximum_supported_planar_error_mm") != 1.0 \
            or source_scorecard.get("hardware_writes") != 0 \
            or source_scorecard.get("physical_movements") != 0 \
            or source_scorecard.get("physical_authority") is not False:
        raise ValueError("target-conditioned candidate identity or authority mismatch")

    rows = _load_rows(evaluation_dataset_dir, "evaluation", dataset)
    catalog = tuple(checkpoint["architecture"]["target_catalog"])
    descriptors = torch.from_numpy(_target_identity_descriptors(
        evaluation_dataset_dir, rows, catalog,
    ))
    offsets = [
        offset for offset in _declared_mask_offsets()
        if max(abs(offset["x_mm"]), abs(offset["y_mm"])) <= 1.0
    ]
    labels_ref: np.ndarray | None = None
    measurements = []
    target_failures: dict[str, dict[str, int]] = {}
    rows_by_id = {row["id"]: row for row in rows}
    threshold = float(checkpoint["threshold"])
    for offset in offsets:
        crops, labels = _target_aware_crops(
            evaluation_dataset_dir, rows, (offset["x_px"], offset["y_px"]),
        )
        labels = labels.astype(np.float64)
        if labels_ref is None:
            labels_ref = labels
        elif not np.array_equal(labels_ref, labels):
            raise RuntimeError("target-conditioned evaluation labels changed across offsets")
        with torch.no_grad():
            probabilities = torch.sigmoid(model(
                torch.from_numpy(crops), descriptors,
            )).numpy()
        metrics = _metrics(rows, labels, probabilities, threshold)
        for failure in metrics["failures"]:
            row = rows_by_id[failure["id"]]
            key = f"{row['device']}:{row['target_id']}"
            counts = target_failures.setdefault(
                key, {"false_abstain": 0, "missed_abstain": 0},
            )
            counts[
                "missed_abstain"
                if failure["expected"] == "abstain" else "false_abstain"
            ] += 1
        measurements.append({"offset": offset, "metrics": metrics})
    assert labels_ref is not None
    abstain_count = int(labels_ref.sum())
    visible_count = len(labels_ref) - abstain_count
    if abstain_count == 0 or visible_count == 0:
        raise ValueError("target-conditioned evaluation requires abstain and visible rows")
    missed_rates = [
        item["metrics"]["confusion"]["missed_abstain"] / abstain_count
        for item in measurements
    ]
    false_rates = [
        item["metrics"]["confusion"]["false_abstain"] / visible_count
        for item in measurements
    ]
    gate_met = max(missed_rates) <= 0.05 and max(false_rates) <= 0.05
    report: dict[str, Any] = {
        "schema": "rocell.ai_target_conditioned_fusion_evaluation.v1",
        "scope": "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION",
        "algorithm": "frozen_target_conditioned_prepool_film_evaluation_v1",
        "dataset_manifest_sha256": _sha256(dataset_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "model_sha256": model_sha,
        "source_scorecard_sha256": claimed_scorecard_sha,
        "target_catalog_sha256": checkpoint["target_catalog_sha256"],
        "threshold": threshold,
        "evaluated_planar_error_bound_mm": 1.0,
        "evaluation_opened": True,
        "evaluation_row_count": len(rows),
        "abstain_row_count": abstain_count,
        "visible_row_count": visible_count,
        "maximum_missed_abstain_rate": max(missed_rates),
        "maximum_visible_false_abstain_rate": max(false_rates),
        "synthetic_gate_met": gate_met,
        "measurements": measurements,
        "per_target_failure_counts_across_offsets": target_failures,
        "promotion_status": "BLOCKED_SYNTHETIC_ONLY",
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "the evaluation camera, geometry, images, labels, and offsets are synthetic",
            "the 1 mm offset uses nominal camera geometry, not physical calibration",
            "this evaluation group is consumed and cannot tune a successor",
            "tool and camera-support geometry remain absent",
            "a passing synthetic gate cannot qualify deployment",
        ],
    }
    report["report_sha256"] = _sha256(_canonical(report))
    (output_dir / "report.json").write_bytes(_canonical(report) + b"\n")
    return report


def evaluate_occlusion_recall_candidate(
    evaluation_dataset_dir: Path,
    candidate_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Evaluate the exact frozen recall checkpoint once on fresh synthetic data."""
    import torch

    evaluation_dataset_dir = evaluation_dataset_dir.resolve(strict=True)
    candidate_dir = candidate_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("recall evaluation output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = evaluation_dataset_dir / "manifest.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = dataset.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) \
            or _sha256(_canonical(dataset)) != claimed_dataset_sha:
        raise ValueError("recall evaluation dataset manifest hash mismatch")
    dataset["dataset_sha256"] = claimed_dataset_sha
    if dataset.get("schema") != SCHEMA_V12 \
            or dataset.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("recall evaluation dataset scope or schema mismatch")
    if dataset["splits"]["train"]["count"] != 0 \
            or dataset["splits"]["development"]["count"] != 0 \
            or dataset["splits"]["evaluation"]["count"] == 0:
        raise ValueError("recall evaluation dataset must be evaluation-only")

    model_path = candidate_dir / "model.json"
    scorecard_path = candidate_dir / "scorecard.json"
    checkpoint, model = _load_target_conditioned_checkpoint(candidate_dir)
    model_sha = _sha256(model_path.read_bytes())
    policy = checkpoint.get("localization_uncertainty_policy", {})
    if checkpoint.get("schema") \
            != "rocell.ai_target_conditioned_occlusion_recall.v1" \
            or model_sha != EXPECTED_OCCLUSION_RECALL_MODEL_SHA256 \
            or checkpoint.get("evaluation_opened") is not False \
            or checkpoint.get("consumed_evaluation_dataset_sha256") is not None \
            or policy.get("development_gate_met") is not True \
            or policy.get("maximum_supported_planar_error_mm") != 0.0 \
            or policy.get("above_bound_decision") != "abstain_localization_uncertain":
        raise ValueError("recall candidate is not the exact frozen 0 mm policy")
    if dataset.get("target_catalog_sha256") != checkpoint.get("target_catalog_sha256"):
        raise ValueError("recall evaluation target catalog mismatch")
    if claimed_dataset_sha in {
        checkpoint.get("training_dataset_sha256"),
        checkpoint.get("selection_dataset_sha256"),
    }:
        raise ValueError("recall evaluation dataset reuses selection bytes")

    source_scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    claimed_scorecard_sha = source_scorecard.pop("scorecard_sha256", None)
    if not isinstance(claimed_scorecard_sha, str) \
            or _sha256(_canonical(source_scorecard)) != claimed_scorecard_sha:
        raise ValueError("recall candidate scorecard hash mismatch")
    source_scorecard["scorecard_sha256"] = claimed_scorecard_sha
    if claimed_scorecard_sha != EXPECTED_OCCLUSION_RECALL_SCORECARD_SHA256 \
            or source_scorecard.get("schema") \
            != "rocell.ai_occlusion_recall_candidate.v1" \
            or source_scorecard.get("model_sha256") != model_sha \
            or source_scorecard.get("evaluation_group_present") is not False \
            or source_scorecard.get("development_gate_met") is not True \
            or source_scorecard.get("maximum_supported_planar_error_mm") != 0.0 \
            or source_scorecard.get("hardware_writes") != 0 \
            or source_scorecard.get("physical_movements") != 0 \
            or source_scorecard.get("physical_authority") is not False:
        raise ValueError("recall candidate identity or authority mismatch")

    rows = _load_rows(evaluation_dataset_dir, "evaluation", dataset)
    catalog = tuple(checkpoint["architecture"]["target_catalog"])
    descriptors = torch.from_numpy(_target_identity_descriptors(
        evaluation_dataset_dir, rows, catalog,
    ))
    offsets = [
        offset for offset in _declared_mask_offsets()
        if max(abs(offset["x_mm"]), abs(offset["y_mm"])) <= 1.0
    ]
    labels_ref: np.ndarray | None = None
    measurements = []
    target_failures: dict[str, dict[str, int]] = {}
    rows_by_id = {row["id"]: row for row in rows}
    threshold = float(checkpoint["threshold"])
    for offset in offsets:
        crops, labels = _target_aware_crops(
            evaluation_dataset_dir, rows, (offset["x_px"], offset["y_px"]),
        )
        labels = labels.astype(np.float64)
        if labels_ref is None:
            labels_ref = labels
        elif not np.array_equal(labels_ref, labels):
            raise RuntimeError("recall evaluation labels changed across offsets")
        with torch.no_grad():
            probabilities = torch.sigmoid(model(
                torch.from_numpy(crops), descriptors,
            )).numpy()
        metrics = _metrics(rows, labels, probabilities, threshold)
        for failure in metrics["failures"]:
            row = rows_by_id[failure["id"]]
            key = f"{row['device']}:{row['target_id']}"
            counts = target_failures.setdefault(
                key, {"false_abstain": 0, "missed_abstain": 0},
            )
            counts[
                "missed_abstain"
                if failure["expected"] == "abstain" else "false_abstain"
            ] += 1
        measurements.append({"offset": offset, "metrics": metrics})
    assert labels_ref is not None
    abstain_count = int(labels_ref.sum())
    visible_count = len(labels_ref) - abstain_count
    if abstain_count == 0 or visible_count == 0:
        raise ValueError("recall evaluation requires abstain and visible rows")
    nominal = next(
        item for item in measurements
        if item["offset"]["x_mm"] == 0.0 and item["offset"]["y_mm"] == 0.0
    )
    nominal_confusion = nominal["metrics"]["confusion"]
    nominal_missed_rate = nominal_confusion["missed_abstain"] / abstain_count
    nominal_false_rate = nominal_confusion["false_abstain"] / visible_count
    stress = [
        item for item in measurements
        if item["offset"]["x_mm"] != 0.0 or item["offset"]["y_mm"] != 0.0
    ]
    stress_missed_rates = [
        item["metrics"]["confusion"]["missed_abstain"] / abstain_count
        for item in stress
    ]
    stress_false_rates = [
        item["metrics"]["confusion"]["false_abstain"] / visible_count
        for item in stress
    ]
    gate_met = nominal_missed_rate <= 0.05 and nominal_false_rate <= 0.05
    stress_gate_met = max(stress_missed_rates) <= 0.05 \
        and max(stress_false_rates) <= 0.05
    report: dict[str, Any] = {
        "schema": "rocell.ai_occlusion_recall_evaluation.v1",
        "scope": "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION",
        "algorithm": "exact_frozen_occlusion_recall_evaluation_v1",
        "dataset_manifest_sha256": _sha256(dataset_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "model_sha256": model_sha,
        "source_scorecard_sha256": claimed_scorecard_sha,
        "target_catalog_sha256": checkpoint["target_catalog_sha256"],
        "threshold": threshold,
        "evaluated_planar_error_bound_mm": 0.0,
        "stress_tested_planar_error_mm": 1.0,
        "evaluation_opened": True,
        "evaluation_row_count": len(rows),
        "abstain_row_count": abstain_count,
        "visible_row_count": visible_count,
        "nominal_missed_abstain_rate": nominal_missed_rate,
        "nominal_visible_false_abstain_rate": nominal_false_rate,
        "maximum_one_mm_missed_abstain_rate": max(stress_missed_rates),
        "maximum_one_mm_visible_false_abstain_rate": max(stress_false_rates),
        "synthetic_gate_met": gate_met,
        "one_mm_stress_gate_met": stress_gate_met,
        "measurements": measurements,
        "per_target_failure_counts_across_offsets": target_failures,
        "promotion_status": "BLOCKED_SYNTHETIC_ONLY"
        if gate_met else "FAILED_SYNTHETIC_GATE",
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "the evaluation camera, geometry, images, labels, and offsets are synthetic",
            "the frozen checkpoint supports only nominal zero-error localization",
            "the 1 mm ring is reported as stress evidence and cannot alter the policy",
            "this evaluation group is consumed and cannot tune a successor",
            "tool and camera-support geometry remain absent",
            "a passing synthetic gate cannot qualify deployment",
        ],
    }
    report["report_sha256"] = _sha256(_canonical(report))
    (output_dir / "report.json").write_bytes(_canonical(report) + b"\n")
    return report

def evaluate_specificity_rebalance_candidate(
    evaluation_dataset_dir: Path,
    candidate_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Evaluate the exact frozen specificity checkpoint on fresh synthetic data."""
    import torch

    evaluation_dataset_dir = evaluation_dataset_dir.resolve(strict=True)
    candidate_dir = candidate_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("rebalance evaluation output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = evaluation_dataset_dir / "manifest.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = dataset.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) \
            or _sha256(_canonical(dataset)) != claimed_dataset_sha:
        raise ValueError("rebalance evaluation dataset manifest hash mismatch")
    dataset["dataset_sha256"] = claimed_dataset_sha
    if dataset.get("schema") != SCHEMA_V14 \
            or dataset.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("rebalance evaluation dataset scope or schema mismatch")
    if dataset["splits"]["train"]["count"] != 0 \
            or dataset["splits"]["development"]["count"] != 0 \
            or dataset["splits"]["evaluation"]["count"] == 0:
        raise ValueError("rebalance evaluation dataset must be evaluation-only")

    model_path = candidate_dir / "model.json"
    scorecard_path = candidate_dir / "scorecard.json"
    checkpoint, model = _load_target_conditioned_checkpoint(candidate_dir)
    model_sha = _sha256(model_path.read_bytes())
    policy = checkpoint.get("localization_uncertainty_policy", {})
    if checkpoint.get("schema") \
            != "rocell.ai_target_conditioned_specificity_rebalance.v1" \
            or model_sha != EXPECTED_SPECIFICITY_REBALANCE_MODEL_SHA256 \
            or checkpoint.get("evaluation_opened") is not False \
            or checkpoint.get("consumed_evaluation_dataset_sha256") is not None \
            or policy.get("development_gate_met") is not True \
            or policy.get("maximum_supported_planar_error_mm") != 2.0 \
            or policy.get("above_bound_decision") != "abstain_localization_uncertain":
        raise ValueError("rebalance candidate is not the exact frozen 2 mm policy")
    if dataset.get("target_catalog_sha256") != checkpoint.get("target_catalog_sha256"):
        raise ValueError("rebalance evaluation target catalog mismatch")
    if claimed_dataset_sha in {
        checkpoint.get("training_dataset_sha256"),
        checkpoint.get("selection_dataset_sha256"),
    }:
        raise ValueError("rebalance evaluation dataset reuses selection bytes")

    source_scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    claimed_scorecard_sha = source_scorecard.pop("scorecard_sha256", None)
    if not isinstance(claimed_scorecard_sha, str) \
            or _sha256(_canonical(source_scorecard)) != claimed_scorecard_sha:
        raise ValueError("rebalance candidate scorecard hash mismatch")
    source_scorecard["scorecard_sha256"] = claimed_scorecard_sha
    if claimed_scorecard_sha != EXPECTED_SPECIFICITY_REBALANCE_SCORECARD_SHA256 \
            or source_scorecard.get("schema") \
            != "rocell.ai_specificity_rebalance_candidate.v1" \
            or source_scorecard.get("model_sha256") != model_sha \
            or source_scorecard.get("evaluation_group_present") is not False \
            or source_scorecard.get("development_gate_met") is not True \
            or source_scorecard.get("maximum_supported_planar_error_mm") != 2.0 \
            or source_scorecard.get("hardware_writes") != 0 \
            or source_scorecard.get("physical_movements") != 0 \
            or source_scorecard.get("physical_authority") is not False:
        raise ValueError("rebalance candidate identity or authority mismatch")

    rows = _load_rows(evaluation_dataset_dir, "evaluation", dataset)
    catalog = tuple(checkpoint["architecture"]["target_catalog"])
    descriptors = torch.from_numpy(_target_identity_descriptors(
        evaluation_dataset_dir, rows, catalog,
    ))
    offsets = [
        offset for offset in _declared_mask_offsets()
        if max(abs(offset["x_mm"]), abs(offset["y_mm"])) <= 4.0
    ]
    labels_ref: np.ndarray | None = None
    measurements = []
    target_failures: dict[str, dict[str, int]] = {}
    rows_by_id = {row["id"]: row for row in rows}
    threshold = float(checkpoint["threshold"])
    for offset in offsets:
        crops, labels = _target_aware_crops(
            evaluation_dataset_dir, rows, (offset["x_px"], offset["y_px"]),
        )
        labels = labels.astype(np.float64)
        if labels_ref is None:
            labels_ref = labels
        elif not np.array_equal(labels_ref, labels):
            raise RuntimeError("rebalance evaluation labels changed across offsets")
        with torch.no_grad():
            probabilities = torch.sigmoid(model(
                torch.from_numpy(crops), descriptors,
            )).numpy()
        metrics = _metrics(rows, labels, probabilities, threshold)
        for failure in metrics["failures"]:
            row = rows_by_id[failure["id"]]
            key = f"{row['device']}:{row['target_id']}"
            counts = target_failures.setdefault(
                key, {"false_abstain": 0, "missed_abstain": 0},
            )
            counts[
                "missed_abstain"
                if failure["expected"] == "abstain" else "false_abstain"
            ] += 1
        measurements.append({"offset": offset, "metrics": metrics})
    assert labels_ref is not None
    abstain_count = int(labels_ref.sum())
    visible_count = len(labels_ref) - abstain_count
    if abstain_count == 0 or visible_count == 0:
        raise ValueError("rebalance evaluation requires abstain and visible rows")
    nominal = next(
        item for item in measurements
        if item["offset"]["x_mm"] == 0.0 and item["offset"]["y_mm"] == 0.0
    )
    nominal_confusion = nominal["metrics"]["confusion"]
    nominal_missed_rate = nominal_confusion["missed_abstain"] / abstain_count
    nominal_false_rate = nominal_confusion["false_abstain"] / visible_count
    declared_bound = 2.0
    declared_bound_measurements = [
        item for item in measurements
        if max(abs(item["offset"]["x_mm"]), abs(item["offset"]["y_mm"]))
        <= declared_bound
    ]
    four_mm_measurements = [
        item for item in measurements
        if max(abs(item["offset"]["x_mm"]), abs(item["offset"]["y_mm"])) == 4.0
    ]
    declared_bound_missed_rates = [
        item["metrics"]["confusion"]["missed_abstain"] / abstain_count
        for item in declared_bound_measurements
    ]
    declared_bound_false_rates = [
        item["metrics"]["confusion"]["false_abstain"] / visible_count
        for item in declared_bound_measurements
    ]
    four_mm_missed_rates = [
        item["metrics"]["confusion"]["missed_abstain"] / abstain_count
        for item in four_mm_measurements
    ]
    four_mm_false_rates = [
        item["metrics"]["confusion"]["false_abstain"] / visible_count
        for item in four_mm_measurements
    ]
    gate_met = max(declared_bound_missed_rates) <= 0.05 \
        and max(declared_bound_false_rates) <= 0.05
    four_mm_stress_gate_met = max(four_mm_missed_rates) <= 0.05 \
        and max(four_mm_false_rates) <= 0.05
    report: dict[str, Any] = {
        "schema": "rocell.ai_specificity_rebalance_evaluation.v1",
        "scope": "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION",
        "algorithm": "exact_frozen_specificity_rebalance_evaluation_v1",
        "dataset_manifest_sha256": _sha256(dataset_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "model_sha256": model_sha,
        "source_scorecard_sha256": claimed_scorecard_sha,
        "target_catalog_sha256": checkpoint["target_catalog_sha256"],
        "threshold": threshold,
        "evaluated_planar_error_bound_mm": declared_bound,
        "stress_tested_planar_error_mm": 4.0,
        "evaluation_opened": True,
        "evaluation_row_count": len(rows),
        "abstain_row_count": abstain_count,
        "visible_row_count": visible_count,
        "nominal_missed_abstain_rate": nominal_missed_rate,
        "nominal_visible_false_abstain_rate": nominal_false_rate,
        "maximum_declared_bound_missed_abstain_rate": max(
            declared_bound_missed_rates
        ),
        "maximum_declared_bound_visible_false_abstain_rate": max(
            declared_bound_false_rates
        ),
        "maximum_four_mm_missed_abstain_rate": max(four_mm_missed_rates),
        "maximum_four_mm_visible_false_abstain_rate": max(four_mm_false_rates),
        "synthetic_gate_met": gate_met,
        "four_mm_stress_gate_met": four_mm_stress_gate_met,
        "measurements": measurements,
        "per_target_failure_counts_across_offsets": target_failures,
        "promotion_status": "BLOCKED_SYNTHETIC_ONLY"
        if gate_met else "FAILED_SYNTHETIC_GATE",
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "the evaluation camera, geometry, images, labels, and offsets are synthetic",
            "the declared 2 mm bound is synthetic and cannot establish calibration",
            "the 4 mm ring is stress evidence and cannot expand the frozen policy",
            "static interpolated poses are visual fixtures, not motion evidence",
            "this evaluation group is consumed and cannot tune a successor",
            "tool and camera-support geometry remain absent",
            "a passing synthetic gate cannot qualify deployment",
        ],
    }
    report["report_sha256"] = _sha256(_canonical(report))
    (output_dir / "report.json").write_bytes(_canonical(report) + b"\n")
    return report


def diagnose_localization_hard_negatives(
    development_dataset_dir: Path,
    candidate_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Measure a frozen policy on fresh development hard negatives without selection."""
    import torch

    development_dataset_dir = development_dataset_dir.resolve(strict=True)
    candidate_dir = candidate_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("hard-negative diagnostic output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = development_dataset_dir / "manifest.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = dataset.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) \
            or _sha256(_canonical(dataset)) != claimed_dataset_sha:
        raise ValueError("hard-negative dataset manifest hash mismatch")
    dataset["dataset_sha256"] = claimed_dataset_sha
    if dataset.get("schema") != SCHEMA_V8 \
            or dataset.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("hard-negative dataset scope or schema mismatch")
    if dataset["splits"]["train"]["count"] != 0 \
            or dataset["splits"]["evaluation"]["count"] != 0 \
            or dataset["splits"]["development"]["count"] == 0:
        raise ValueError("hard-negative dataset must be development-only")

    model_path = candidate_dir / "model.json"
    scorecard_path = candidate_dir / "scorecard.json"
    checkpoint, model = _load_spatial_checkpoint(candidate_dir)
    policy = checkpoint.get("localization_uncertainty_policy", {})
    if checkpoint.get("schema") \
            != "rocell.ai_target_crop_localization_robust_spatial.v1" \
            or checkpoint.get("evaluation_opened") is not False \
            or policy.get("maximum_supported_planar_error_mm") != 1.0:
        raise ValueError("hard-negative diagnostic requires frozen 1 mm checkpoint")
    source_scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    claimed_scorecard_sha = source_scorecard.pop("scorecard_sha256", None)
    if not isinstance(claimed_scorecard_sha, str) \
            or _sha256(_canonical(source_scorecard)) != claimed_scorecard_sha:
        raise ValueError("hard-negative candidate scorecard hash mismatch")
    source_scorecard["scorecard_sha256"] = claimed_scorecard_sha
    model_sha = _sha256(model_path.read_bytes())
    if source_scorecard.get("schema") != "rocell.ai_localization_policy_refreeze.v1" \
            or source_scorecard.get("model_sha256") != model_sha \
            or source_scorecard.get("hardware_writes") != 0 \
            or source_scorecard.get("physical_movements") != 0:
        raise ValueError("hard-negative candidate identity or authority mismatch")

    rows = _load_rows(development_dataset_dir, "development", dataset)
    offsets = [
        offset for offset in _declared_mask_offsets()
        if max(abs(offset["x_mm"]), abs(offset["y_mm"])) <= 1.0
    ]
    labels_ref: np.ndarray | None = None
    measurements = []
    target_failures: dict[str, dict[str, int]] = {}
    rows_by_id = {row["id"]: row for row in rows}
    threshold = float(checkpoint["threshold"])
    for offset in offsets:
        crops, labels = _target_aware_crops(
            development_dataset_dir, rows, (offset["x_px"], offset["y_px"]),
        )
        labels = labels.astype(np.float64)
        if labels_ref is None:
            labels_ref = labels
        elif not np.array_equal(labels_ref, labels):
            raise RuntimeError("hard-negative labels changed across offsets")
        with torch.no_grad():
            probabilities = torch.sigmoid(model(torch.from_numpy(crops))).numpy()
        metrics = _metrics(rows, labels, probabilities, threshold)
        for failure in metrics["failures"]:
            row = rows_by_id[failure["id"]]
            key = f"{row['device']}:{row['target_id']}"
            counts = target_failures.setdefault(
                key, {"false_abstain": 0, "missed_abstain": 0},
            )
            counts[
                "missed_abstain"
                if failure["expected"] == "abstain" else "false_abstain"
            ] += 1
        measurements.append({"offset": offset, "metrics": metrics})
    assert labels_ref is not None
    abstain_count = int(labels_ref.sum())
    visible_count = len(labels_ref) - abstain_count
    if abstain_count == 0 or visible_count == 0:
        raise ValueError("hard-negative diagnostic requires abstain and visible rows")
    missed_rates = [
        item["metrics"]["confusion"]["missed_abstain"] / abstain_count
        for item in measurements
    ]
    false_rates = [
        item["metrics"]["confusion"]["false_abstain"] / visible_count
        for item in measurements
    ]
    report: dict[str, Any] = {
        "schema": "rocell.ai_localization_hard_negative_diagnostic.v1",
        "scope": "SYNTHETIC_DEVELOPMENT_ONLY_NO_DEPLOYMENT_QUALIFICATION",
        "dataset_manifest_sha256": _sha256(dataset_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "model_sha256": model_sha,
        "source_scorecard_sha256": claimed_scorecard_sha,
        "threshold": threshold,
        "measured_planar_error_bound_mm": 1.0,
        "selection_performed": False,
        "training_performed": False,
        "evaluation_group_present": False,
        "development_row_count": len(rows),
        "abstain_row_count": abstain_count,
        "visible_row_count": visible_count,
        "maximum_missed_abstain_rate": max(missed_rates),
        "maximum_visible_false_abstain_rate": max(false_rates),
        "measurements": measurements,
        "per_target_failure_counts_across_offsets": target_failures,
        "promotion_status": "BLOCKED_DEVELOPMENT_ONLY",
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "all diagnostic images, labels, geometry, and offsets are synthetic",
            "the consumed v7 evaluation informed this separate development campaign",
            "this report performs no threshold selection or training",
            "no evaluation group was created or opened",
            "tool and camera-support geometry remain absent",
        ],
    }
    report["report_sha256"] = _sha256(_canonical(report))
    (output_dir / "report.json").write_bytes(_canonical(report) + b"\n")
    return report


def evaluate_target_mask_perturbations(
    source_manifest: Path,
    dataset_dir: Path,
    candidate_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Measure frozen target-aware inference under predeclared mask offsets."""
    import torch

    source_manifest = source_manifest.resolve(strict=True)
    dataset_dir = dataset_dir.resolve(strict=True)
    candidate_dir = candidate_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("perturbation output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    source = _verify_source(source_manifest)
    if source.get("schema") != SOURCE_SCHEMA_V6:
        raise ValueError("perturbation source must use v6 development-only schema")
    dataset_path = dataset_dir / "manifest.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = dataset.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) \
            or _sha256(_canonical(dataset)) != claimed_dataset_sha:
        raise ValueError("perturbation dataset manifest hash mismatch")
    dataset["dataset_sha256"] = claimed_dataset_sha
    if dataset.get("schema") != SCHEMA_V6 \
            or dataset.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("perturbation dataset scope or schema mismatch")
    if dataset.get("source_manifest_sha256") != _sha256(source_manifest.read_bytes()) \
            or dataset.get("source_receipt_sha256") != source["receipt_sha256"]:
        raise ValueError("perturbation dataset differs from source render")
    if dataset["splits"]["train"]["count"] != 0 \
            or dataset["splits"]["evaluation"]["count"] != 0:
        raise ValueError("perturbation study must not contain train or evaluation rows")

    checkpoint, model = _load_spatial_checkpoint(candidate_dir)
    if checkpoint.get("schema") != "rocell.ai_target_crop_safe_region_spatial.v1":
        raise ValueError("perturbation study requires target-aware checkpoint")
    model_path = candidate_dir / "model.json"
    scorecard_path = candidate_dir / "scorecard.json"
    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    claimed_scorecard_sha = scorecard.pop("scorecard_sha256", None)
    if not isinstance(claimed_scorecard_sha, str) \
            or _sha256(_canonical(scorecard)) != claimed_scorecard_sha:
        raise ValueError("perturbation candidate scorecard hash mismatch")
    scorecard["scorecard_sha256"] = claimed_scorecard_sha
    if scorecard.get("model_sha256") != _sha256(model_path.read_bytes()) \
            or scorecard.get("hardware_writes") != 0 \
            or scorecard.get("physical_movements") != 0:
        raise ValueError("perturbation candidate identity or authority mismatch")

    rows = _load_rows(dataset_dir, "development", dataset)
    threshold = float(checkpoint["threshold"])
    measurements = []
    target_failures: dict[str, dict[str, int]] = {}
    rows_by_id = {row["id"]: row for row in rows}
    for offset in _declared_mask_offsets():
        crops, labels = _target_aware_crops(
            dataset_dir, rows, (offset["x_px"], offset["y_px"]),
        )
        with torch.no_grad():
            probabilities = torch.sigmoid(model(torch.from_numpy(crops))).numpy()
        metrics = _metrics(rows, labels.astype(np.float64), probabilities, threshold)
        for failure in metrics["failures"]:
            row = rows_by_id[failure["id"]]
            key = f"{row['device']}:{row['target_id']}"
            counts = target_failures.setdefault(
                key, {"false_abstain": 0, "missed_abstain": 0},
            )
            counts[
                "missed_abstain"
                if failure["expected"] == "abstain" else "false_abstain"
            ] += 1
        measurements.append({"offset": offset, "metrics": metrics})

    report: dict[str, Any] = {
        "schema": "rocell.ai_target_mask_perturbation_study.v1",
        "scope": "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION",
        "source_manifest_sha256": _sha256(source_manifest.read_bytes()),
        "source_receipt_sha256": source["receipt_sha256"],
        "dataset_manifest_sha256": _sha256(dataset_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "model_sha256": _sha256(model_path.read_bytes()),
        "scorecard_sha256": claimed_scorecard_sha,
        "selection_split": "development_only",
        "evaluation_group_present": False,
        "threshold": threshold,
        "offset_model": {
            "kind": "joint_rgb_crop_and_known_target_safe_region_translation",
            "nominal_pixels_per_mm": NOMINAL_PIXELS_PER_MM,
            "derivation": "nominal_fx_1000_px / nominal_target_depth_500_mm",
            "radii_mm": list(MASK_OFFSET_RADII_MM),
            "direction_count_per_radius": len(MASK_OFFSET_DIRECTIONS),
        },
        "measurements": measurements,
        "per_target_failure_counts_across_offsets": target_failures,
        "promotion_status": "BLOCKED_SYNTHETIC_ONLY",
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "all images, labels, target geometry, and offsets are synthetic",
            "pixel-to-millimetre conversion uses nominal camera geometry",
            "offsets translate the RGB crop and known-target mask together",
            "development-only results are diagnostic and cannot qualify deployment",
            "no evaluation group was created or opened",
        ],
    }
    report["report_sha256"] = _sha256(_canonical(report))
    (output_dir / "report.json").write_bytes(_canonical(report) + b"\n")
    return report


def _video_frame(image: Image.Image, title: str, subtitle: str) -> Image.Image:
    frame = image.convert("RGB").resize((960, 540), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(frame)
    draw.rectangle((0, 0, 960, 58), fill=(8, 12, 18))
    font = ImageFont.load_default()
    draw.text((14, 10), title, fill=(245, 248, 252), font=font)
    draw.text((14, 32), subtitle, fill=(188, 205, 222), font=font)
    return frame


def _scaled_polygon(points: list[list[float]]) -> list[tuple[int, int]]:
    return [(round(point[0] * 0.5), round(point[1] * 0.5)) for point in points]


def _encode_mp4(path: Path, frames: list[Image.Image], fps: int = 2) -> None:
    try:
        import av
    except ImportError as exc:
        raise RuntimeError("PyAV is required to encode progression MP4 files") from exc
    if not frames:
        raise ValueError("progression video requires at least one frame")
    container = av.open(str(path), mode="w")
    container.metadata.clear()
    stream = container.add_stream("libx264", rate=fps)
    stream.width = 960
    stream.height = 540
    stream.pix_fmt = "yuv420p"
    stream.options = {"crf": "20", "preset": "medium", "threads": "1"}
    for index, image in enumerate(frames):
        frame = av.VideoFrame.from_ndarray(np.asarray(image, dtype=np.uint8), format="rgb24")
        frame.pts = index
        frame.time_base = Fraction(1, fps)
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def export_progression_videos(
    source_manifest: Path, dataset_dir: Path, candidate_dir: Path, output_dir: Path,
) -> dict[str, Any]:
    """Export deterministic synthetic progression videos with zero authority."""
    import torch

    source_manifest = source_manifest.resolve(strict=True)
    dataset_dir = dataset_dir.resolve(strict=True)
    candidate_dir = candidate_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("video output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    source = _verify_source(source_manifest)
    dataset_manifest_path = dataset_dir / "manifest.json"
    dataset = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    claimed_dataset_sha = dataset.pop("dataset_sha256", None)
    if not isinstance(claimed_dataset_sha, str) or _sha256(_canonical(dataset)) != claimed_dataset_sha:
        raise ValueError("video dataset manifest hash mismatch")
    dataset["dataset_sha256"] = claimed_dataset_sha
    if dataset.get("source_manifest_sha256") != _sha256(source_manifest.read_bytes()) \
            or dataset.get("source_receipt_sha256") != source["receipt_sha256"]:
        raise ValueError("video dataset differs from source render")
    if dataset.get("scope") != "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION":
        raise ValueError("video dataset scope mismatch")

    scorecard_path = candidate_dir / "scorecard.json"
    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    claimed_scorecard_sha = scorecard.pop("scorecard_sha256", None)
    if not isinstance(claimed_scorecard_sha, str) \
            or _sha256(_canonical(scorecard)) != claimed_scorecard_sha:
        raise ValueError("video scorecard hash mismatch")
    scorecard["scorecard_sha256"] = claimed_scorecard_sha
    checkpoint, model = _load_spatial_checkpoint(candidate_dir)
    model_path = candidate_dir / "model.json"
    if scorecard.get("model_sha256") != _sha256(model_path.read_bytes()) \
            or scorecard.get("dataset_sha256") != claimed_dataset_sha \
            or checkpoint.get("selection_dataset_sha256") != claimed_dataset_sha:
        raise ValueError("video candidate differs from dataset")
    if scorecard.get("hardware_writes") != 0 or scorecard.get("physical_movements") != 0:
        raise ValueError("video candidate claims authority")

    atlas_path = source_manifest.parent / source["artifact_atlases"]["rgb"]["path"]
    atlas = Image.open(atlas_path).convert("RGB")
    geometry_frames = []
    for index, pose in enumerate(source["pose_results"]):
        image = atlas.crop(tuple(pose["atlas_crop_px"]))
        frame = _video_frame(
            image,
            f"Synthetic official-mesh pose {index + 1}/{len(source['pose_results'])}",
            f"{pose['pose_group']} | {pose['pose_id']} | ground-truth occlusion overlay",
        )
        draw = ImageDraw.Draw(frame)
        for target in pose["targets"]:
            blocked = target["center_occluded_by_official_mesh"] or (
                target["safe_region_official_mesh_overlap_fraction"]
                > MAXIMUM_SAFE_REGION_OVERLAP
            )
            color = (240, 72, 72) if blocked else (55, 205, 115)
            draw.line(_scaled_polygon(target["safe_polygon_px"] + [target["safe_polygon_px"][0]]),
                      fill=color, width=2)
        geometry_frames.append(frame)

    evaluation_rows = _load_rows(dataset_dir, "evaluation", dataset)
    crop_loader = (
        _target_aware_crops
        if checkpoint["schema"] == "rocell.ai_target_crop_safe_region_spatial.v1"
        else _spatial_crops
    )
    evaluation_x, _ = crop_loader(dataset_dir, evaluation_rows)
    with torch.no_grad():
        probabilities = torch.sigmoid(model(torch.from_numpy(evaluation_x))).numpy()
    rows_by_image: dict[str, list[tuple[dict[str, Any], float]]] = {}
    for row, probability in zip(evaluation_rows, probabilities, strict=True):
        rows_by_image.setdefault(row["image_path"], []).append((row, float(probability)))
    evaluation_images = [item for item in dataset["images"] if item["split"] == "evaluation"]
    diagnostic_frames = []
    threshold = float(checkpoint["threshold"])
    aggregate = {"true_visible": 0, "true_abstain": 0, "false_abstain": 0, "missed_abstain": 0}
    category_colors = {
        "true_visible": (55, 205, 115),
        "true_abstain": (75, 155, 245),
        "false_abstain": (255, 170, 45),
        "missed_abstain": (245, 55, 190),
    }
    for index, image_record in enumerate(evaluation_images):
        image_path = dataset_dir / image_record["path"]
        if _sha256(image_path.read_bytes()) != image_record["sha256"]:
            raise ValueError("video image hash mismatch")
        rows = rows_by_image[image_record["path"]]
        counts = {key: 0 for key in aggregate}
        categorized = []
        for row, probability in rows:
            expected = row["decision"] == "abstain"
            predicted = probability >= threshold
            category = (
                "true_abstain" if expected and predicted else
                "missed_abstain" if expected else
                "false_abstain" if predicted else "true_visible"
            )
            counts[category] += 1
            aggregate[category] += 1
            categorized.append((row, probability, category))
        frame = _video_frame(
            Image.open(image_path),
            f"Frozen evaluation {index + 1}/{len(evaluation_images)}",
            (f"{image_record['pose_id']} | {image_record['lighting_variant']} | "
             f"missed={counts['missed_abstain']} false-stop={counts['false_abstain']} "
             f"threshold={threshold:.2f}"),
        )
        draw = ImageDraw.Draw(frame)
        for row, probability, category in categorized:
            center = (round(row["center_px"][0] * 0.5), round(row["center_px"][1] * 0.5))
            radius = 5 if category in {"false_abstain", "missed_abstain"} else 2
            color = category_colors[category]
            draw.ellipse((center[0] - radius, center[1] - radius,
                          center[0] + radius, center[1] + radius),
                         outline=color, width=2)
            if category in {"false_abstain", "missed_abstain"}:
                draw.line(_scaled_polygon(row["safe_polygon_px"] + [row["safe_polygon_px"][0]]),
                          fill=color, width=3)
                draw.text((center[0] + 7, center[1] - 6),
                          f"{row['target_id']} {probability:.2f}", fill=color,
                          font=ImageFont.load_default())
        diagnostic_frames.append(frame)

    geometry_path = output_dir / "official_mesh_pose_progression.mp4"
    diagnostic_path = output_dir / "occlusion_candidate_evaluation.mp4"
    _encode_mp4(geometry_path, geometry_frames)
    _encode_mp4(diagnostic_path, diagnostic_frames)
    target_aware = checkpoint["schema"] == "rocell.ai_target_crop_safe_region_spatial.v1"
    manifest: dict[str, Any] = {
        "schema": (
            "rocell.ai_sim_progression_video_bundle.v2"
            if target_aware else "rocell.ai_sim_progression_video_bundle.v1"
        ),
        "scope": "SYNTHETIC_ONLY_NO_DEPLOYMENT_QUALIFICATION",
        "source_manifest_sha256": _sha256(source_manifest.read_bytes()),
        "source_receipt_sha256": source["receipt_sha256"],
        "dataset_manifest_sha256": _sha256(dataset_manifest_path.read_bytes()),
        "dataset_sha256": claimed_dataset_sha,
        "model_sha256": _sha256(model_path.read_bytes()),
        "scorecard_sha256": claimed_scorecard_sha,
        "threshold": threshold,
        "evaluation_confusion": aggregate,
        "videos": {
            "pose_progression": {
                "path": geometry_path.name,
                "sha256": _sha256(geometry_path.read_bytes()),
                "frame_count": len(geometry_frames),
                "fps": 2,
                "resolution_px": [960, 540],
            },
            "candidate_evaluation": {
                "path": diagnostic_path.name,
                "sha256": _sha256(diagnostic_path.read_bytes()),
                "frame_count": len(diagnostic_frames),
                "fps": 2,
                "resolution_px": [960, 540],
            },
        },
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    if target_aware:
        manifest["model_input"] = {
            "checkpoint_schema": checkpoint["schema"],
            "channels": checkpoint["architecture"]["input_channels"],
            "simulator_robot_mask_input": False,
        }
    manifest["bundle_sha256"] = _sha256(_canonical(manifest))
    (output_dir / "manifest.json").write_bytes(_canonical(manifest) + b"\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--baseline-output", type=Path)
    parser.add_argument("--candidate-output", type=Path)
    parser.add_argument("--spatial-output", type=Path)
    parser.add_argument("--target-aware-output", type=Path)
    parser.add_argument(
        "--record-existing", type=Path, nargs=3,
        metavar=("DATASET_DIR", "CANDIDATE_DIR", "VIDEO_OUTPUT_DIR"),
    )
    parser.add_argument(
        "--perturb-existing", type=Path, nargs=3,
        metavar=("DATASET_DIR", "CANDIDATE_DIR", "STUDY_OUTPUT_DIR"),
    )
    parser.add_argument(
        "--train-localization-robust", type=Path, nargs=3,
        metavar=("TRAINING_DATASET_DIR", "DEVELOPMENT_DATASET_DIR", "OUTPUT_DIR"),
    )
    parser.add_argument(
        "--train-target-identity", type=Path, nargs=3,
        metavar=("TRAINING_DATASET_DIR", "DEVELOPMENT_DATASET_DIR", "OUTPUT_DIR"),
    )
    parser.add_argument(
        "--train-target-conditioned-fusion", type=Path, nargs=4,
        metavar=(
            "TRAINING_DATASET_DIR", "DEVELOPMENT_DATASET_DIR",
            "SEED_CANDIDATE_DIR", "OUTPUT_DIR",
        ),
    )
    parser.add_argument(
        "--train-occlusion-recall", type=Path, nargs=3,
        metavar=("DATASET_DIR", "SEED_CANDIDATE_DIR", "OUTPUT_DIR"),
    )
    parser.add_argument(
        "--train-specificity-rebalance", type=Path, nargs=3,
        metavar=("DATASET_DIR", "SEED_CANDIDATE_DIR", "OUTPUT_DIR"),
    )
    parser.add_argument(
        "--train-pose-diverse-successor", type=Path, nargs=3,
        metavar=("DATASET_DIR", "SEED_CANDIDATE_DIR", "OUTPUT_DIR"),
    )
    parser.add_argument(
        "--train-grouped-neighborhood-successor", type=Path, nargs=3,
        metavar=("DATASET_DIR", "SEED_CANDIDATE_DIR", "OUTPUT_DIR"),
    )
    parser.add_argument(
        "--refreeze-localization-policy", type=Path, nargs=3,
        metavar=("DEVELOPMENT_DATASET_DIR", "CANDIDATE_DIR", "OUTPUT_DIR"),
    )
    parser.add_argument(
        "--evaluate-localization-policy", type=Path, nargs=3,
        metavar=("EVALUATION_DATASET_DIR", "CANDIDATE_DIR", "OUTPUT_DIR"),
    )
    parser.add_argument(
        "--evaluate-target-conditioned-fusion", type=Path, nargs=3,
        metavar=("EVALUATION_DATASET_DIR", "CANDIDATE_DIR", "OUTPUT_DIR"),
    )
    parser.add_argument(
        "--evaluate-occlusion-recall", type=Path, nargs=3,
        metavar=("EVALUATION_DATASET_DIR", "CANDIDATE_DIR", "OUTPUT_DIR"),
    )
    parser.add_argument(
        "--evaluate-specificity-rebalance", type=Path, nargs=3,
        metavar=("EVALUATION_DATASET_DIR", "CANDIDATE_DIR", "OUTPUT_DIR"),
    )
    parser.add_argument(
        "--diagnose-localization-hard-negatives", type=Path, nargs=3,
        metavar=("DEVELOPMENT_DATASET_DIR", "CANDIDATE_DIR", "OUTPUT_DIR"),
    )
    args = parser.parse_args()
    if args.train_grouped_neighborhood_successor is not None:
        incompatible = (
            args.train_pose_diverse_successor, args.record_existing,
            args.perturb_existing, args.train_localization_robust,
            args.train_target_identity, args.train_target_conditioned_fusion,
            args.train_occlusion_recall, args.train_specificity_rebalance,
            args.refreeze_localization_policy, args.evaluate_localization_policy,
            args.evaluate_target_conditioned_fusion, args.evaluate_occlusion_recall,
            args.evaluate_specificity_rebalance, args.diagnose_localization_hard_negatives,
            args.output_dir, args.baseline_output, args.candidate_output,
            args.spatial_output, args.target_aware_output,
        )
        if any(value is not None for value in incompatible):
            parser.error(
                "--train-grouped-neighborhood-successor cannot be combined with other outputs"
            )
        scorecard = train_grouped_neighborhood_successor_candidate(
            *args.train_grouped_neighborhood_successor,
        )
        print(json.dumps(scorecard, sort_keys=True))
        return 0
    if args.train_pose_diverse_successor is not None:
        incompatible = (
            args.record_existing, args.perturb_existing,
            args.train_localization_robust, args.train_target_identity,
            args.train_target_conditioned_fusion, args.train_occlusion_recall,
            args.train_specificity_rebalance, args.refreeze_localization_policy,
            args.evaluate_localization_policy,
            args.evaluate_target_conditioned_fusion,
            args.evaluate_occlusion_recall, args.evaluate_specificity_rebalance,
            args.diagnose_localization_hard_negatives, args.output_dir,
            args.baseline_output, args.candidate_output, args.spatial_output,
            args.target_aware_output,
            args.train_grouped_neighborhood_successor,
        )
        if any(value is not None for value in incompatible):
            parser.error(
                "--train-pose-diverse-successor cannot be combined with other outputs"
            )
        scorecard = train_pose_diverse_successor_candidate(
            *args.train_pose_diverse_successor,
        )
        print(json.dumps(scorecard, sort_keys=True))
        return 0
    if args.evaluate_specificity_rebalance is not None:
        incompatible = (
            args.record_existing, args.perturb_existing,
            args.train_localization_robust, args.train_target_identity,
            args.train_target_conditioned_fusion, args.train_occlusion_recall,
            args.train_specificity_rebalance, args.refreeze_localization_policy,
            args.evaluate_localization_policy,
            args.evaluate_target_conditioned_fusion,
            args.evaluate_occlusion_recall,
            args.diagnose_localization_hard_negatives, args.output_dir,
            args.baseline_output, args.candidate_output, args.spatial_output,
            args.target_aware_output,
        )
        if any(value is not None for value in incompatible):
            parser.error(
                "--evaluate-specificity-rebalance cannot be combined with other outputs"
            )
        report = evaluate_specificity_rebalance_candidate(
            *args.evaluate_specificity_rebalance,
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    if args.record_existing is not None:
        if args.perturb_existing is not None \
                or args.train_localization_robust is not None \
                or args.train_target_identity is not None \
                or args.train_target_conditioned_fusion is not None \
                or args.train_occlusion_recall is not None \
                or args.train_specificity_rebalance is not None \
                or args.refreeze_localization_policy is not None \
                or args.evaluate_localization_policy is not None \
                or args.evaluate_target_conditioned_fusion is not None \
                or args.evaluate_occlusion_recall is not None \
                or args.diagnose_localization_hard_negatives is not None \
                or args.output_dir is not None or any(
            value is not None
            for value in (
                args.baseline_output, args.candidate_output, args.spatial_output,
                args.target_aware_output,
            )
        ):
            parser.error("--record-existing cannot be combined with build or training outputs")
        manifest = export_progression_videos(
            args.source_manifest, *args.record_existing,
        )
        print(json.dumps(manifest, sort_keys=True))
        return 0
    if args.perturb_existing is not None:
        if args.train_localization_robust is not None \
                or args.train_target_identity is not None \
                or args.train_target_conditioned_fusion is not None \
                or args.train_occlusion_recall is not None \
                or args.train_specificity_rebalance is not None \
                or args.refreeze_localization_policy is not None \
                or args.evaluate_localization_policy is not None \
                or args.evaluate_target_conditioned_fusion is not None \
                or args.evaluate_occlusion_recall is not None \
                or args.diagnose_localization_hard_negatives is not None \
                or args.output_dir is not None or any(
            value is not None
            for value in (
                args.baseline_output, args.candidate_output, args.spatial_output,
                args.target_aware_output,
            )
        ):
            parser.error("--perturb-existing cannot be combined with build or training outputs")
        report = evaluate_target_mask_perturbations(
            args.source_manifest, *args.perturb_existing,
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    if args.train_localization_robust is not None:
        if args.train_target_identity is not None \
                or args.train_target_conditioned_fusion is not None \
                or args.train_occlusion_recall is not None \
                or args.train_specificity_rebalance is not None \
                or args.refreeze_localization_policy is not None \
                or args.evaluate_localization_policy is not None \
                or args.evaluate_target_conditioned_fusion is not None \
                or args.evaluate_occlusion_recall is not None \
                or args.diagnose_localization_hard_negatives is not None \
                or args.output_dir is not None or any(
            value is not None
            for value in (
                args.baseline_output, args.candidate_output, args.spatial_output,
                args.target_aware_output,
            )
        ):
            parser.error(
                "--train-localization-robust cannot be combined with other outputs"
            )
        scorecard = train_localization_robust_candidate(
            *args.train_localization_robust,
        )
        print(json.dumps(scorecard, sort_keys=True))
        return 0
    if args.train_target_identity is not None:
        if args.train_target_conditioned_fusion is not None \
                or args.train_occlusion_recall is not None \
                or args.train_specificity_rebalance is not None \
                or args.refreeze_localization_policy is not None \
                or args.evaluate_localization_policy is not None \
                or args.evaluate_target_conditioned_fusion is not None \
                or args.evaluate_occlusion_recall is not None \
                or args.diagnose_localization_hard_negatives is not None \
                or args.output_dir is not None or any(
            value is not None
            for value in (
                args.baseline_output, args.candidate_output, args.spatial_output,
                args.target_aware_output,
            )
        ):
            parser.error(
                "--train-target-identity cannot be combined with other outputs"
            )
        scorecard = train_target_identity_candidate(*args.train_target_identity)
        print(json.dumps(scorecard, sort_keys=True))
        return 0
    if args.train_target_conditioned_fusion is not None:
        if args.train_occlusion_recall is not None \
                or args.train_specificity_rebalance is not None \
                or args.refreeze_localization_policy is not None \
                or args.evaluate_localization_policy is not None \
                or args.evaluate_target_conditioned_fusion is not None \
                or args.evaluate_occlusion_recall is not None \
                or args.diagnose_localization_hard_negatives is not None \
                or args.output_dir is not None or any(
            value is not None
            for value in (
                args.baseline_output, args.candidate_output, args.spatial_output,
                args.target_aware_output,
            )
        ):
            parser.error(
                "--train-target-conditioned-fusion cannot be combined with other outputs"
            )
        scorecard = train_target_conditioned_fusion_candidate(
            *args.train_target_conditioned_fusion,
        )
        print(json.dumps(scorecard, sort_keys=True))
        return 0
    if args.train_occlusion_recall is not None:
        if args.train_specificity_rebalance is not None \
                or args.refreeze_localization_policy is not None \
                or args.evaluate_localization_policy is not None \
                or args.evaluate_target_conditioned_fusion is not None \
                or args.evaluate_occlusion_recall is not None \
                or args.diagnose_localization_hard_negatives is not None \
                or args.output_dir is not None or any(
            value is not None
            for value in (
                args.baseline_output, args.candidate_output, args.spatial_output,
                args.target_aware_output,
            )
        ):
            parser.error("--train-occlusion-recall cannot be combined with other outputs")
        scorecard = train_occlusion_recall_candidate(*args.train_occlusion_recall)
        print(json.dumps(scorecard, sort_keys=True))
        return 0
    if args.train_specificity_rebalance is not None:
        if args.refreeze_localization_policy is not None \
                or args.evaluate_localization_policy is not None \
                or args.evaluate_target_conditioned_fusion is not None \
                or args.evaluate_occlusion_recall is not None \
                or args.diagnose_localization_hard_negatives is not None \
                or args.output_dir is not None or any(
            value is not None
            for value in (
                args.baseline_output, args.candidate_output, args.spatial_output,
                args.target_aware_output,
            )
        ):
            parser.error(
                "--train-specificity-rebalance cannot be combined with other outputs"
            )
        scorecard = train_specificity_rebalance_candidate(
            *args.train_specificity_rebalance,
        )
        print(json.dumps(scorecard, sort_keys=True))
        return 0
    if args.refreeze_localization_policy is not None:
        if args.evaluate_localization_policy is not None \
                or args.evaluate_target_conditioned_fusion is not None \
                or args.evaluate_occlusion_recall is not None \
                or args.diagnose_localization_hard_negatives is not None \
                or args.output_dir is not None or any(
            value is not None
            for value in (
                args.baseline_output, args.candidate_output, args.spatial_output,
                args.target_aware_output,
            )
        ):
            parser.error(
                "--refreeze-localization-policy cannot be combined with other outputs"
            )
        scorecard = refreeze_localization_policy(
            *args.refreeze_localization_policy,
        )
        print(json.dumps(scorecard, sort_keys=True))
        return 0
    if args.evaluate_localization_policy is not None:
        if args.evaluate_target_conditioned_fusion is not None \
                or args.evaluate_occlusion_recall is not None \
                or args.diagnose_localization_hard_negatives is not None \
                or args.output_dir is not None or any(
            value is not None
            for value in (
                args.baseline_output, args.candidate_output, args.spatial_output,
                args.target_aware_output,
            )
        ):
            parser.error(
                "--evaluate-localization-policy cannot be combined with other outputs"
            )
        report = evaluate_localization_policy(
            *args.evaluate_localization_policy,
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    if args.evaluate_target_conditioned_fusion is not None:
        if args.evaluate_occlusion_recall is not None \
                or args.diagnose_localization_hard_negatives is not None \
                or args.output_dir is not None or any(
            value is not None
            for value in (
                args.baseline_output, args.candidate_output, args.spatial_output,
                args.target_aware_output,
            )
        ):
            parser.error(
                "--evaluate-target-conditioned-fusion cannot be combined "
                "with other outputs"
            )
        report = evaluate_target_conditioned_fusion(
            *args.evaluate_target_conditioned_fusion,
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    if args.evaluate_occlusion_recall is not None:
        if args.diagnose_localization_hard_negatives is not None \
                or args.output_dir is not None or any(
            value is not None
            for value in (
                args.baseline_output, args.candidate_output, args.spatial_output,
                args.target_aware_output,
            )
        ):
            parser.error(
                "--evaluate-occlusion-recall cannot be combined with other outputs"
            )
        report = evaluate_occlusion_recall_candidate(
            *args.evaluate_occlusion_recall,
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    if args.diagnose_localization_hard_negatives is not None:
        if args.output_dir is not None or any(
            value is not None
            for value in (
                args.baseline_output, args.candidate_output, args.spatial_output,
                args.target_aware_output,
            )
        ):
            parser.error(
                "--diagnose-localization-hard-negatives cannot be combined "
                "with other outputs"
            )
        report = diagnose_localization_hard_negatives(
            *args.diagnose_localization_hard_negatives,
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    if args.output_dir is None:
        parser.error(
            "--output-dir is required unless an existing-artifact mode is used"
        )
    try:
        manifest = build(args.source_manifest, args.output_dir)
        scorecard = (
            train_baseline(args.output_dir, args.baseline_output)
            if args.baseline_output is not None else None
        )
        candidate_scorecard = (
            train_selected_candidate(args.output_dir, args.candidate_output)
            if args.candidate_output is not None else None
        )
        spatial_scorecard = (
            train_spatial_candidate(args.output_dir, args.spatial_output)
            if args.spatial_output is not None else None
        )
        target_aware_scorecard = (
            train_target_aware_candidate(args.output_dir, args.target_aware_output)
            if args.target_aware_output is not None else None
        )
    except BaseException:
        if args.output_dir.exists():
            shutil.rmtree(args.output_dir)
        raise
    result = {
        "schema": manifest["schema"],
        "dataset_sha256": manifest["dataset_sha256"],
        "splits": manifest["splits"],
    }
    if scorecard is not None:
        evaluation = scorecard["evaluation"]
        result["baseline"] = {
            "scorecard_sha256": scorecard["scorecard_sha256"],
            "promotion_status": scorecard["promotion_status"],
            "evaluation": {
                key: evaluation[key]
                for key in (
                    "count", "confusion", "accuracy", "balanced_accuracy",
                    "brier_score", "expected_calibration_error_10_bin",
                )
            },
        }
    if candidate_scorecard is not None:
        evaluation = candidate_scorecard["evaluation"]
        result["candidate"] = {
            "scorecard_sha256": candidate_scorecard["scorecard_sha256"],
            "promotion_status": candidate_scorecard["promotion_status"],
            "selected_feature_family": candidate_scorecard["selected_feature_family"],
            "selected_threshold": candidate_scorecard["selected_threshold"],
            "evaluation": {
                key: evaluation[key]
                for key in (
                    "count", "confusion", "accuracy", "balanced_accuracy",
                    "brier_score", "expected_calibration_error_10_bin",
                )
            },
        }
    if spatial_scorecard is not None:
        evaluation = spatial_scorecard["evaluation"]
        result["spatial_candidate"] = {
            "scorecard_sha256": spatial_scorecard["scorecard_sha256"],
            "promotion_status": spatial_scorecard["promotion_status"],
            "selected_threshold": spatial_scorecard["selected_threshold"],
            "development_gate_met": spatial_scorecard["development_gate_met"],
            "evaluation": {
                key: evaluation[key]
                for key in (
                    "count", "confusion", "accuracy", "balanced_accuracy",
                    "brier_score", "expected_calibration_error_10_bin",
                )
            },
        }
    if target_aware_scorecard is not None:
        evaluation = target_aware_scorecard["evaluation"]
        result["target_aware_candidate"] = {
            "scorecard_sha256": target_aware_scorecard["scorecard_sha256"],
            "promotion_status": target_aware_scorecard["promotion_status"],
            "selected_threshold": target_aware_scorecard["selected_threshold"],
            "development_gate_met": target_aware_scorecard["development_gate_met"],
            "evaluation": {
                key: evaluation[key]
                for key in (
                    "count", "confusion", "accuracy", "balanced_accuracy",
                    "brier_score", "expected_calibration_error_10_bin",
                )
            },
        }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
