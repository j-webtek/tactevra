"""Frozen row scheduling and exact admission for paired height corpora.

This module does not render, train, score, or open evaluation data.  It turns a
small frozen fixture into an exact train/development allowlist and verifies that
renderer manifests preserve the same source pixels for the 96 and 192 model
inputs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterator


FIXTURE_SCHEMA = "tactevra.ai_residual_obstruction_paired_height_fixture.v1_4"
SHARD_SCHEMA = "tactevra.ai_residual_obstruction_paired_height_shard.v1_4"
RESOLUTION_NOISE_SCHEMA = "tactevra.ai_paired_height_resolution_noise_experiment.v1"
ASSUMED_NOISE_PROFILE_IDS = ("ASSUMED_LOW", "ASSUMED_MODERATE", "ASSUMED_HIGH")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_resolution_noise_experiment(path: Path) -> tuple[dict[str, Any], bytes]:
    """Load the frozen, explicitly exploratory 96-versus-192 experiment."""
    raw = path.resolve(strict=True).read_bytes()
    value = json.loads(raw)
    if value.get("schema") != RESOLUTION_NOISE_SCHEMA:
        raise ValueError("unsupported resolution/noise experiment")
    core = {key: item for key, item in value.items() if key != "bundle_sha256"}
    if value.get("bundle_sha256") != sha256_bytes(canonical(core)):
        raise ValueError("experiment canonical hash mismatch")
    if value.get("scope") != "EXPLORATORY_SYNTHETIC_ASSUMED_NOISE_NO_QUALIFICATION":
        raise ValueError("experiment scope must remain exploratory")
    if value.get("loader_mode") != "EXPLORATORY":
        raise ValueError("measured qualifying mode is forbidden")
    profiles = value.get("noise_profiles")
    if not isinstance(profiles, list) or tuple(
        row.get("profile_id") for row in profiles
    ) != ASSUMED_NOISE_PROFILE_IDS:
        raise ValueError("noise profiles must be frozen low, moderate, and high")
    for profile in profiles:
        camera = profile.get("camera_profile")
        if camera.get("measurement_scope") != "ASSUMED_EXPLORATORY_NOT_MEASURED":
            raise ValueError("assumed noise may not claim camera measurement")
        if camera.get("spatial_noise_kernel") != [[1.0]]:
            raise ValueError("assumed profiles freeze independent noise only")
    candidates = value.get("candidates")
    if not isinstance(candidates, list) or tuple(
        row.get("input_resolution_px") for row in candidates
    ) != (96, 192):
        raise ValueError("candidate resolutions must be exactly 96 and 192")
    parity_fields = (
        "model_family", "physical_footprint_mm", "feature_channels", "conv_channels",
        "normalization", "spatial_feature_map", "optimizer", "maximum_epochs",
        "batch_size", "learning_rate", "weight_decay", "training_seed",
    )
    if any(candidates[0][field] != candidates[1][field] for field in parity_fields):
        raise ValueError("resolution must be the only candidate difference")
    if value.get("evaluation_opened") is not False:
        raise ValueError("evaluation must remain unopened")
    if value.get("physical_authority") is not False:
        raise ValueError("experiment may not create physical authority")
    return value, raw


def decide_resolution(profile_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Apply the frozen per-profile and cross-noise resolution rules."""
    if tuple(profile_results) != ASSUMED_NOISE_PROFILE_IDS:
        raise ValueError("profile results must preserve frozen profile order")
    winners: dict[str, str] = {}
    for profile_id, results in profile_results.items():
        if set(results) != {"96", "192", "paired_delta"}:
            raise ValueError(f"malformed profile result: {profile_id}")
        low, high = results["96"], results["192"]
        eligible_low = bool(low["memorization_pass"] and low["all_development_gates_pass"])
        eligible_high = bool(high["memorization_pass"] and high["all_development_gates_pass"])
        if eligible_high and not eligible_low:
            winner = "192"
        elif eligible_low and not eligible_high:
            winner = "96"
        elif not eligible_low and not eligible_high:
            winner = "UNRESOLVED"
        else:
            delta = results["paired_delta"]
            if (
                float(delta["q05_target_auc_point_192_minus_96"]) >= 0.01
                and float(delta["q05_target_auc_lower_95"]) > 0.0
                and float(delta["dark_cable_auc_point_192_minus_96"]) >= 0.0
            ):
                winner = "192"
            elif (
                float(delta["q05_target_auc_point_192_minus_96"]) <= 0.005
                and float(delta["dark_cable_auc_point_192_minus_96"]) <= 0.005
            ):
                winner = "96"
            else:
                winner = "UNRESOLVED"
        winners[profile_id] = winner
    unique = set(winners.values())
    if unique == {"192"}:
        decision = "SELECT_192_EXPLORATORY"
    elif unique == {"96"}:
        decision = "SELECT_96_EXPLORATORY"
    elif "UNRESOLVED" in unique:
        decision = "UNRESOLVED_WAIT_FOR_MEASURED_CAMERA_PROFILE"
    else:
        decision = "NOISE_DEPENDENT_DEFER_TO_MEASURED_CAMERA_PROFILE"
    return {"per_profile_winner": winners, "global_decision": decision}


def load_fixture(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.resolve(strict=True).read_bytes()
    fixture = json.loads(raw)
    if fixture.get("schema") != FIXTURE_SCHEMA:
        raise ValueError("unsupported paired-height fixture")
    core = {key: value for key, value in fixture.items() if key != "bundle_sha256"}
    if fixture.get("bundle_sha256") != sha256_bytes(canonical(core)):
        raise ValueError("fixture canonical hash mismatch")
    if fixture.get("evaluation_identities_present") is not False:
        raise ValueError("evaluation identities must be absent")
    if fixture.get("images_generated") is not False or fixture.get("training_started") is not False:
        raise ValueError("fixture must be frozen before rendering and training")
    if fixture["camera"]["orientation"] != "EXACT_NADIR_FIXED":
        raise ValueError("paired height corpus only admits the fixed nadir family")
    output = fixture["output_contract"]
    sizes = output["derived_local_tensor_sizes_px"]
    if sizes != [[96, 96], [192, 192]]:
        raise ValueError("paired output sizes must be exactly 96 and 192")
    if output.get("stored_artifact") != "SENSOR_ALIGNED_NATIVE_RGB8_PNG":
        raise ValueError("fixture must store native sensor-aligned crops")
    if output.get("local_physical_extent_xy_mm") != [48.0, 48.0]:
        raise ValueError("paired candidates must share the frozen 48 mm source footprint")
    if "context_physical_extent_xy_mm" in output:
        raise ValueError("unused context footprint declarations are forbidden")
    if output.get("same_stored_native_pixels_for_both_candidates") is not True:
        raise ValueError("paired candidates must derive from identical native pixels")
    if output.get("camera_model_order") != [
        "DECODE_STORED_SRGB_TO_LINEAR",
        "LINEAR_EXPOSURE_GAIN",
        "LINEAR_BRIGHTNESS_DEPENDENT_SENSOR_NOISE",
        "LINEAR_SENSOR_QUANTIZATION",
        "WHITE_BALANCE",
        "MEASURED_B0477_TONE_ENCODING",
        "BT601_FULL_RANGE_YUY2_422_COSITED_LEFT",
        "FLOATING_CROP_ALIGNMENT",
        "RESAMPLE_MODEL_INPUT",
    ]:
        raise ValueError("camera model order differs from the sensor pipeline")
    return fixture, raw


def _split_heights(fixture: dict[str, Any], split: str, scene_id: str) -> list[int]:
    if split == "training":
        return [int(fixture["split_identities"]["training_scene_height_mm"][scene_id])]
    if split == "development":
        return [int(value) for value in fixture["camera"]["heights_board_mm"]]
    raise ValueError("only training and development are admitted")


def iter_row_identities(
    fixture: dict[str, Any],
    split: str,
    *,
    scene_ids: set[str] | None = None,
    target_keys: set[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield the exact deterministic identity schedule without image paths."""
    scenes = fixture["split_identities"][f"{split}_scene_ids"]
    appearances = fixture["split_identities"][f"{split}_appearance_ids"]
    for scene_id in scenes:
        if scene_ids is not None and scene_id not in scene_ids:
            continue
        for height_mm in _split_heights(fixture, split, scene_id):
            for appearance_id in appearances:
                for target in fixture["targets"]:
                    target_key = f"{target['device']}:{target['target_id']}"
                    if target_keys is not None and target_key not in target_keys:
                        continue
                    for variant in fixture["variants"]:
                        row_id = ":".join(
                            (
                                split,
                                scene_id,
                                str(height_mm),
                                appearance_id,
                                target["device"],
                                target["target_id"],
                                variant["variant_id"],
                            )
                        )
                        seed_material = f"{fixture['seed_contract']['salt']}|{row_id}".encode()
                        yield {
                            "row_id": row_id,
                            "split": split,
                            "scene_id": scene_id,
                            "height_board_mm": height_mm,
                            "appearance_id": appearance_id,
                            "device": target["device"],
                            "target_id": target["target_id"],
                            "variant_id": variant["variant_id"],
                            "camera_sample_seed": int(sha256_bytes(seed_material)[:16], 16),
                        }


def expected_counts(fixture: dict[str, Any]) -> dict[str, int]:
    training = sum(1 for _ in iter_row_identities(fixture, "training"))
    development = sum(1 for _ in iter_row_identities(fixture, "development"))
    return {
        "training_source_rows": training,
        "development_source_rows": development,
        "total_source_rows": training + development,
        "stored_native_crop_pngs": training + development,
        "derived_model_tensors_per_loader_epoch": 2 * (training + development),
    }


def _yuy2_roundtrip(rgb: Any, np: Any) -> Any:
    value = rgb.astype(np.float32)
    red, green, blue = value[..., 0], value[..., 1], value[..., 2]
    luminance = 0.299 * red + 0.587 * green + 0.114 * blue
    chroma_u = -0.168736 * red - 0.331264 * green + 0.5 * blue + 128.0
    chroma_v = 0.5 * red - 0.418688 * green - 0.081312 * blue + 128.0
    if rgb.shape[1] % 2:
        raise ValueError("sensor-aligned native crop width must be even")
    chroma_u = np.repeat(np.rint(chroma_u[:, ::2]), 2, axis=1)
    chroma_v = np.repeat(np.rint(chroma_v[:, ::2]), 2, axis=1)
    luminance = np.rint(luminance)
    restored = np.stack(
        (
            luminance + 1.402 * (chroma_v - 128.0),
            luminance - 0.344136 * (chroma_u - 128.0) - 0.714136 * (chroma_v - 128.0),
            luminance + 1.772 * (chroma_u - 128.0),
        ),
        axis=-1,
    )
    return np.clip(restored, 0, 255).astype(np.uint8)


def _srgb_to_linear(value: Any, np: Any) -> Any:
    value = np.clip(value, 0.0, 1.0)
    return np.where(
        value <= 0.04045,
        value / 12.92,
        np.power((value + 0.055) / 1.055, 2.4),
    )


def _linear_to_srgb(value: Any, np: Any) -> Any:
    value = np.clip(value, 0.0, 1.0)
    return np.where(
        value <= 0.0031308,
        12.92 * value,
        1.055 * np.power(value, 1.0 / 2.4) - 0.055,
    )


def _validate_camera_profile(profile: dict[str, Any], *, qualifying: bool) -> None:
    required = {
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
        "processing_controls",
    }
    if set(profile) != required:
        raise ValueError("camera profile fields differ from the frozen schema")
    knots = profile["brightness_knots_linear"]
    noise = profile["noise_stddev_knots_linear"]
    if (
        not isinstance(knots, list)
        or not isinstance(noise, list)
        or len(knots) < 2
        or len(knots) != len(noise)
        or knots[0] != 0.0
        or knots[-1] != 1.0
        or any(not 0.0 <= float(item) <= 1.0 for item in knots)
        or any(float(right) <= float(left) for left, right in zip(knots, knots[1:]))
        or any(float(item) < 0.0 for item in noise)
    ):
        raise ValueError("camera noise curve is malformed")
    if profile["brightness_domain"] != "LINEAR_0_1":
        raise ValueError("camera profile brightness domain is unsupported")
    tone_linear = profile["tone_curve_linear_knots"]
    tone_output = profile["tone_curve_output_knots"]
    if (
        not isinstance(tone_linear, list)
        or not isinstance(tone_output, list)
        or len(tone_linear) < 2
        or len(tone_linear) != len(tone_output)
        or tone_linear[0] != 0.0
        or tone_linear[-1] != 1.0
        or tone_output[0] != 0.0
        or tone_output[-1] != 1.0
        or any(float(right) <= float(left) for left, right in zip(tone_linear, tone_linear[1:]))
        or any(float(right) <= float(left) for left, right in zip(tone_output, tone_output[1:]))
    ):
        raise ValueError("camera tone curve is malformed")
    for field in ("channel_noise_scale_rgb", "white_balance_rgb"):
        values = profile[field]
        if not isinstance(values, list) or len(values) != 3 or any(float(item) <= 0 for item in values):
            raise ValueError(f"camera profile {field} is malformed")
    bits = profile["sensor_quantization_bits"]
    if isinstance(bits, bool) or not isinstance(bits, int) or not 8 <= bits <= 16:
        raise ValueError("sensor quantization bits must be an integer from 8 through 16")
    for field in ("source_burst_sha256", "source_tone_sweep_sha256"):
        digest = profile[field]
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"camera profile {field} is malformed")
    kernel = profile["spatial_noise_kernel"]
    if (
        not isinstance(kernel, list)
        or not kernel
        or len(kernel) % 2 != 1
        or len(kernel) > 7
        or any(not isinstance(row, list) or len(row) != len(kernel) for row in kernel)
        or sum(float(item) ** 2 for row in kernel for item in row) <= 0.0
    ):
        raise ValueError("camera spatial noise kernel is malformed")
    controls = profile["processing_controls"]
    if not isinstance(controls, dict) or set(controls) != {
        "denoise_disabled",
        "sharpening_disabled",
        "disable_attempted",
        "settings_receipt_sha256",
    }:
        raise ValueError("camera processing controls are malformed")
    if any(not isinstance(controls[field], bool) for field in (
        "denoise_disabled", "sharpening_disabled", "disable_attempted"
    )):
        raise ValueError("camera processing control flags must be boolean")
    if not isinstance(controls["settings_receipt_sha256"], str) or len(
        controls["settings_receipt_sha256"]
    ) != 64:
        raise ValueError("camera processing settings receipt hash is malformed")
    if qualifying and profile["measurement_scope"] != "MEASURED_B0477_LOCKED_SETTINGS":
        raise ValueError("qualifying load requires a measured B0477 profile")


def noise_stddev_for_linear_brightness(
    profile: dict[str, Any], brightness: float
) -> float:
    """Interpolate the measured linear-light noise curve at one brightness."""
    import numpy as np

    _validate_camera_profile(profile, qualifying=False)
    if not 0.0 <= float(brightness) <= 1.0:
        raise ValueError("linear brightness must be in [0, 1]")
    return float(
        np.interp(
            float(brightness),
            np.asarray(profile["brightness_knots_linear"], dtype=np.float32),
            np.asarray(profile["noise_stddev_knots_linear"], dtype=np.float32),
        )
    )


def spatially_correlate_noise(noise: Any, kernel: list[list[float]]) -> Any:
    """Apply a small measured spatial kernel while preserving noise RMS."""
    import numpy as np

    value = np.asarray(noise, dtype=np.float32)
    weights = np.asarray(kernel, dtype=np.float32)
    if value.ndim != 3:
        raise ValueError("noise must be HxWxC")
    if (
        weights.ndim != 2
        or weights.shape[0] != weights.shape[1]
        or weights.shape[0] % 2 != 1
        or weights.shape[0] > 7
    ):
        raise ValueError("spatial noise kernel must be odd, square, and at most 7x7")
    norm = float(np.sqrt(np.sum(weights * weights)))
    if norm <= 0.0:
        raise ValueError("spatial noise kernel must have positive energy")
    weights = weights / norm
    radius = weights.shape[0] // 2
    padded = np.pad(value, ((radius, radius), (radius, radius), (0, 0)), mode="reflect")
    result = np.zeros_like(value)
    for row in range(weights.shape[0]):
        for column in range(weights.shape[1]):
            result += weights[row, column] * padded[
                row : row + value.shape[0], column : column + value.shape[1]
            ]
    return result


def _measured_tone_encode(value: Any, profile: dict[str, Any], np: Any) -> Any:
    return np.interp(
        np.clip(value, 0.0, 1.0),
        np.asarray(profile["tone_curve_linear_knots"], dtype=np.float32),
        np.asarray(profile["tone_curve_output_knots"], dtype=np.float32),
    )


def derive_model_input(
    native_rgb: Any,
    *,
    aligned_crop_box_px: list[float],
    output_size_px: int,
    seed: int,
    camera_profile: dict[str, Any] | None,
    qualifying: bool,
    exposure_gain: float = 1.0,
) -> Any:
    """Apply the camera model at native pixels, then align and resize.

    Stored RGB8 is decoded to linear light first.  Brightness-dependent noise
    is then sampled before sensor quantization, tone encoding, YUY2, and resize.
    """
    import numpy as np
    from PIL import Image

    if output_size_px not in {96, 192}:
        raise ValueError("output_size_px must be 96 or 192")
    value = np.asarray(native_rgb)
    if value.ndim != 3 or value.shape[2] != 3 or value.dtype != np.uint8:
        raise ValueError("native_rgb must be uint8 HxWx3")
    if value.shape[1] % 2:
        raise ValueError("native crop must start and end on YUY2 pair boundaries")
    if not 0.0 < float(exposure_gain) <= 16.0:
        raise ValueError("exposure_gain must be in (0, 16]")
    linear = _srgb_to_linear(value.astype(np.float32) / 255.0, np)
    exposed = np.clip(linear * float(exposure_gain), 0.0, 1.0)
    if camera_profile is None:
        if qualifying:
            raise ValueError("qualifying load requires measured B0477 noise curve")
        profile = {
            "sensor_quantization_bits": 12,
            "white_balance_rgb": [1.0, 1.0, 1.0],
        }
        noisy = exposed
    else:
        _validate_camera_profile(camera_profile, qualifying=qualifying)
        profile = camera_profile
        luminance = (
            0.2126 * exposed[..., 0]
            + 0.7152 * exposed[..., 1]
            + 0.0722 * exposed[..., 2]
        )
        base_std = np.interp(
            luminance,
            np.asarray(profile["brightness_knots_linear"], dtype=np.float32),
            np.asarray(profile["noise_stddev_knots_linear"], dtype=np.float32),
        )
        channel_std = base_std[..., None] * np.asarray(
            profile["channel_noise_scale_rgb"], dtype=np.float32
        )
        white_noise = np.random.default_rng(seed).normal(0.0, 1.0, value.shape)
        correlated_noise = spatially_correlate_noise(
            white_noise, profile["spatial_noise_kernel"]
        )
        noise = correlated_noise * channel_std
        noisy = np.clip(exposed + noise, 0.0, 1.0)
    levels = float((1 << int(profile["sensor_quantization_bits"])) - 1)
    quantized = np.rint(noisy * levels) / levels
    balanced = np.clip(
        quantized * np.asarray(profile["white_balance_rgb"], dtype=np.float32),
        0.0,
        1.0,
    )
    tone_encoded = (
        _linear_to_srgb(balanced, np)
        if camera_profile is None
        else _measured_tone_encode(balanced, profile, np)
    )
    delivered_rgb8 = np.rint(tone_encoded * 255.0).astype(np.uint8)
    delivered = _yuy2_roundtrip(delivered_rgb8, np)
    left, top, right, bottom = (float(item) for item in aligned_crop_box_px)
    if not (0 <= left < right <= value.shape[1] and 0 <= top < bottom <= value.shape[0]):
        raise ValueError("aligned crop box is outside the stored native crop")
    image = Image.fromarray(delivered, mode="RGB")
    return np.asarray(
        image.transform(
            (output_size_px, output_size_px),
            Image.Transform.EXTENT,
            (left, top, right, bottom),
            resample=Image.Resampling.BICUBIC,
        ),
        dtype=np.uint8,
    )


def admit_shard_manifest(
    fixture_path: Path,
    manifest_path: Path,
    *,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    """Admit one exact shard and optionally verify every referenced PNG."""
    fixture, fixture_raw = load_fixture(fixture_path)
    manifest_raw = manifest_path.resolve(strict=True).read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest.get("schema") != SHARD_SCHEMA:
        raise ValueError("unsupported paired-height shard")
    if manifest.get("fixture_file_sha256") != sha256_bytes(fixture_raw):
        raise ValueError("fixture file hash mismatch")
    if manifest.get("fixture_bundle_sha256") != fixture["bundle_sha256"]:
        raise ValueError("fixture bundle hash mismatch")
    split = manifest.get("split")
    if split not in {"training", "development"}:
        raise ValueError("evaluation or unknown split is forbidden")
    shard = manifest.get("shard", {})
    scene_ids = set(shard.get("scene_ids", []))
    target_keys = set(shard.get("target_keys", []))
    if not scene_ids or not target_keys:
        raise ValueError("shard scene and target allowlists must be nonempty")
    expected = {
        row["row_id"]: row
        for row in iter_row_identities(
            fixture, split, scene_ids=scene_ids, target_keys=target_keys
        )
    }
    rows = manifest.get("observations")
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError("shard observation inventory mismatch")
    seen: set[str] = set()
    allowed_paths: set[str] = set()
    for row in rows:
        row_id = row.get("row_id")
        if row_id in seen or row_id not in expected:
            raise ValueError("duplicate or unexpected row identity")
        seen.add(row_id)
        identity = expected[row_id]
        if any(row.get(key) != value for key, value in identity.items()):
            raise ValueError(f"row identity fields differ for {row_id}")
        native = row.get("native_crop")
        if not isinstance(native, dict):
            raise ValueError("missing stored native crop")
        relative = native.get("path")
        if not isinstance(relative, str) or not relative.endswith(".png"):
            raise ValueError("stored native crop must be a lossless PNG path")
        if relative in allowed_paths:
            raise ValueError("duplicate native crop path")
        allowed_paths.add(relative)
        digest = native.get("sha256")
        size = native.get("size_px")
        bounds = native.get("full_frame_integer_bounds_px")
        aligned = native.get("aligned_model_crop_box_px")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("missing native crop hash")
        if not (
            isinstance(size, list)
            and len(size) == 2
            and all(isinstance(item, int) for item in size)
            and 320 <= min(size) <= max(size) <= 480
            and size[0] % 2 == 0
        ):
            raise ValueError("native crop dimensions are outside the frozen support range")
        if not (
            isinstance(bounds, list)
            and len(bounds) == 4
            and all(isinstance(item, int) for item in bounds)
            and 0 <= bounds[0] < bounds[2] <= fixture["camera"]["native_mode_px"][0]
            and 0 <= bounds[1] < bounds[3] <= fixture["camera"]["native_mode_px"][1]
            and bounds[0] % 2 == 0
            and bounds[2] % 2 == 0
            and bounds[2] - bounds[0] == size[0]
            and bounds[3] - bounds[1] == size[1]
        ):
            raise ValueError("native crop is outside the full frame or not aligned to YUY2 pairs")
        if not (
            isinstance(aligned, list)
            and len(aligned) == 4
            and 0 <= aligned[0] < aligned[2] <= size[0]
            and 0 <= aligned[1] < aligned[3] <= size[1]
        ):
            raise ValueError("model crop alignment is outside the native crop")
        if artifact_root is not None:
            payload = (artifact_root / relative).resolve(strict=True).read_bytes()
            if not payload.startswith(PNG_SIGNATURE):
                raise ValueError(f"non-PNG payload: {relative}")
            if sha256_bytes(payload) != digest:
                raise ValueError(f"native crop hash mismatch: {relative}")
            from PIL import Image

            with Image.open(artifact_root / relative) as image:
                if list(image.size) != size:
                    raise ValueError(f"native crop pixel dimensions differ: {relative}")
    if seen != set(expected):
        raise ValueError("shard is missing frozen row identities")
    if set(manifest.get("file_allowlist", [])) != allowed_paths:
        raise ValueError("file allowlist does not exactly match model inputs")
    return {
        "status": "PASS_EXACT_PAIRED_SHARD_ADMISSION",
        "split": split,
        "source_row_count": len(rows),
        "stored_native_crop_png_count": len(allowed_paths),
        "manifest_file_sha256": sha256_bytes(manifest_raw),
    }

