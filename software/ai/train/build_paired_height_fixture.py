"""Build the frozen synthetic paired-height train/development fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from paired_height_corpus_contract import FIXTURE_SCHEMA, canonical, expected_counts, sha256_bytes


def _target_ids(profile: dict[str, Any], device: str) -> list[str]:
    block = profile[device]
    ids: list[str] = []
    row_key = "key_ids" if device == "keyboard" else "target_ids"
    for row in block["rows"]:
        ids.extend(row[row_key])
    ids.extend(block.get("explicit_targets", {}).keys())
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate {device} target IDs")
    return ids


def build(v5_path: Path, candidate_path: Path, output: Path, source_commit: str) -> dict[str, Any]:
    v5_raw = v5_path.resolve(strict=True).read_bytes()
    candidate_raw = candidate_path.resolve(strict=True).read_bytes()
    v5 = json.loads(v5_raw)
    candidate = json.loads(candidate_raw)
    training_scenes = list(v5["split_identities"]["scenes"]["training"])
    development_scenes = list(v5["split_identities"]["scenes"]["development"])
    heights = (700, 850, 1000)
    targets = [
        {"device": device, "target_id": target_id}
        for device in ("keyboard", "phone")
        for target_id in _target_ids(candidate, device)
    ]
    if len(targets) != 80:
        raise ValueError("the measured candidate must contain exactly 80 targets")
    core: dict[str, Any] = {
        "schema": FIXTURE_SCHEMA,
        "scope": "SYNTHETIC_EXPLORATORY_TRAIN_DEVELOPMENT_ONLY_NO_PHYSICAL_QUALIFICATION",
        "status": "FROZEN_BEFORE_RENDER",
        "source_commit": source_commit,
        "bindings": {
            "superseded_v1_2_fixture_file_sha256": "2ab9382feb524c9787653f06eedb38684caae37ef57ef541e6582bf9a6241b3a",
            "superseded_v1_1_fixture_file_sha256": "2376dd8f1e38c5f479311f1054837ca3d1f76e133d80329d9242424a968b6476",
            "superseded_pre_render_fixture_file_sha256": "c90f8cdbc6835e01a099265da6c238d01d982b343d667f0e57484d2c5a49fbe9",
            "v5_source_file_sha256": sha256_bytes(v5_raw),
            "measured_80_target_candidate_file_sha256": sha256_bytes(candidate_raw),
            "candidate_installed": False,
            "height_admission_result_sha256": "82f04415dace8e22fd8a46078fed01a0d2e9288752e66ee5255c2e0b53aa5fad",
            "official_mesh_result_sha256": "9664f973e145224309615b8e60e868a83cc1033547386ed5833aa55113f3c61a",
            "paired_smoke_result_sha256": "4d54aad0e78d39d1242e13aee967e16619d5c1c2cec13c943e961878420cbae1",
        },
        "camera": {
            "orientation": "EXACT_NADIR_FIXED",
            "center_board_xy_mm": [305.0, 228.5],
            "heights_board_mm": list(heights),
            "focal_length_mm": 16.0,
            "native_mode_px": [5472, 3648],
            "image_axis_contract": {"board_x_to_image_u_sign": 1, "board_y_to_image_v_sign": -1},
            "measured_b0477_noise_profile": None,
            "camera_model_role": "EXPLORATORY_ZERO_NOISE_UNTIL_MEASURED_PROFILE_EXISTS",
        },
        "output_contract": {
            "stored_artifact": "SENSOR_ALIGNED_NATIVE_RGB8_PNG",
            "lossless_source_format": "PNG_RGB8",
            "stored_encoding": "UINT8_SRGB_GAMMA_ENCODED_RGB",
            "local_physical_extent_xy_mm": [48.0, 48.0],
            "context_physical_extent_xy_mm": [72.0, 72.0],
            "stored_native_crop_support_range_px": [320, 480],
            "stored_left_and_right_bounds_must_be_even": True,
            "derived_local_tensor_sizes_px": [[96, 96], [192, 192]],
            "same_stored_native_pixels_for_both_candidates": True,
            "resampler": "PIL_BICUBIC_FLOATING_EXTENT",
            "jpeg_forbidden": True,
            "camera_model_order": [
                "DECODE_STORED_SRGB_TO_LINEAR",
                "LINEAR_EXPOSURE_GAIN",
                "LINEAR_BRIGHTNESS_DEPENDENT_SENSOR_NOISE",
                "LINEAR_SENSOR_QUANTIZATION",
                "WHITE_BALANCE",
                "MEASURED_B0477_TONE_ENCODING",
                "BT601_FULL_RANGE_YUY2_422_COSITED_LEFT",
                "FLOATING_CROP_ALIGNMENT",
                "RESAMPLE_MODEL_INPUT"
            ],
        },
        "measured_camera_profile_contract": {
            "required_for_qualifying_loader": True,
            "brightness_domain": "LINEAR_0_1",
            "noise_model": "PIECEWISE_LINEAR_STDDEV_VERSUS_MEAN_BRIGHTNESS",
            "measurement_method": "LOCKED_SETTINGS_EXPOSURE_SWEEP_FOR_RESPONSE_CURVE_THEN_STATIC_YUY2_BURSTS_INVERSE_MEASURED_TONE_AND_VARIANCE_CORRELATION_AGAINST_PER_PIXEL_MEAN",
            "required_fields": [
                "profile_id",
                "measurement_scope",
                "source_burst_sha256",
                "source_tone_sweep_sha256",
                "brightness_domain",
                "brightness_knots_linear",
                "noise_stddev_knots_linear",
                "channel_noise_scale_rgb",
                "sensor_quantization_bits",
                "white_balance_rgb",
                "tone_curve_linear_knots",
                "tone_curve_output_knots",
                "spatial_noise_kernel",
                "processing_controls"
            ],
            "installed_profile": None,
        },
        "seed_contract": {
            "algorithm": "SHA256_FIRST_64_BITS_BIG_ENDIAN",
            "salt": "TACTEVRA_PAIRED_HEIGHT_CORPUS_V1",
            "training_noise_varies_by_epoch": False,
            "development_noise_is_fixed": True,
        },
        "split_identities": {
            "training_scene_ids": training_scenes,
            "development_scene_ids": development_scenes,
            "training_appearance_ids": list(v5["split_identities"]["lighting"]["training"]),
            "development_appearance_ids": list(v5["split_identities"]["lighting"]["development"]),
            "training_scene_height_mm": {
                scene_id: heights[index % len(heights)]
                for index, scene_id in enumerate(training_scenes)
            },
            "development_height_rule": "EVERY_IDENTITY_AT_ALL_THREE_HEIGHTS",
            "training_obstruction_asset_ids": list(v5["split_identities"]["obstruction_assets"]["training"]),
            "development_obstruction_asset_ids": list(v5["split_identities"]["obstruction_assets"]["development"]),
            "train_development_assets_disjoint": True,
        },
        "targets": targets,
        "variants": list(v5["variants"]),
        "selection_contract": {
            "paired_rows_required": True,
            "identical_optimizer_required": True,
            "compare_safety_diagnostics": True,
            "compare_development_height_stability": True,
            "compare_latency_and_peak_memory": True,
            "evaluation_must_remain_unopened": True,
            "no_winner_from_smoke_or_fixture": True,
            "development_uncertainty_cluster_key": "SCENE_APPEARANCE_TARGET_VARIANT_WITH_HEIGHT_REPEATED",
            "height_rows_are_not_independent": True,
        },
        "future_evaluation_contract": {
            "identities_present": False,
            "pixels_present": False,
            "intermediate_height_probes_required_before_continuous_range_claim": [775, 925],
            "three_training_heights_only_support_discrete_height_claims": True,
        },
        "evaluation_identities_present": False,
        "images_generated": False,
        "training_started": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "The corpus is synthetic and cannot qualify the B0477 camera or hardware deployment.",
            "Stored RGB8 sRGB cannot recover information discarded before storage; linear decoding is an approximation until high-bit-depth linear rendering is available.",
            "The loader remains exploratory until a hash-bound measured B0477 noise profile exists.",
            "The 80-target measured candidate is external and uninstalled.",
            "Training distributes heights across scenes; development repeats every identity at all heights and must cluster statistics by identity.",
            "Only 700, 850, and 1000 mm are represented; intermediate heights are reserved for a future unopened evaluation fixture.",
            "Evaluation identities and pixels are absent and no integration gate is changed.",
        ],
    }
    provisional = {**core, "bundle_sha256": sha256_bytes(canonical(core))}
    provisional["planned_counts"] = expected_counts(provisional)
    core = {key: value for key, value in provisional.items() if key != "bundle_sha256"}
    result = {**core, "bundle_sha256": sha256_bytes(canonical(core))}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical(result) + b"\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v5", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    result = build(args.v5, args.candidate, args.output, args.source_commit)
    print(json.dumps({"bundle_sha256": result["bundle_sha256"], **result["planned_counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
