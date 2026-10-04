from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))
sys.path.insert(0, str(AI_ROOT / "train"))

from train.paired_height_corpus_contract import (  # noqa: E402
    SHARD_SCHEMA,
    admit_shard_manifest,
    apply_camera_model_native,
    apply_feature_standardization,
    canonical,
    construct_paired_height_features,
    construct_paired_height_features_from_delivered,
    decide_resolution,
    derive_model_input,
    expected_counts,
    finalize_feature_statistics,
    iter_row_identities,
    load_fixture,
    load_resolution_noise_experiment,
    new_feature_statistics_accumulator,
    noise_stddev_for_linear_brightness,
    spatially_correlate_noise,
    select_memorization_rows,
    training_free_difference_score,
    update_feature_statistics,
    sha256_bytes,
)
from train.run_residual_obstruction_v4_2_memorization import (  # noqa: E402
    paired_height_features_from_normalized_torch,
    paired_height_resolution_spatial_model,
)
from train import paired_height_corpus_contract as paired_height_contract  # noqa: E402


ROOT = AI_ROOT
FIXTURE = ROOT / "sim/evidence/residual_obstruction_paired_height_v1_4.json"
RESOLUTION_EXPERIMENT = ROOT / "sim/evidence/paired_height_resolution_noise_experiment_v1.json"


def test_frozen_resolution_noise_experiment_and_decision_rules() -> None:
    value, _ = load_resolution_noise_experiment(RESOLUTION_EXPERIMENT)
    assert [row["profile_id"] for row in value["noise_profiles"]] == [
        "ASSUMED_LOW", "ASSUMED_MODERATE", "ASSUMED_HIGH"
    ]
    assert [row["input_resolution_px"] for row in value["candidates"]] == [96, 192]
    assert {row["input_channel_count"] for row in value["candidates"]} == {12}
    assert {row["parameter_count"] for row in value["candidates"]} == {43_321}
    assert {row["final_pooling"] for row in value["candidates"]} == {
        "ADAPTIVE_AVERAGE_6X6"
    }
    assert len(value["run_matrix"]) == 6
    assert value["input_standardization"]["fit_split"] == "training"
    assert value["input_standardization"]["cross_resolution_statistic_reuse_forbidden"]
    assert value["pre_training_gates"]["memorization_selection"]["scope"] == (
        "TRAINING_ONLY"
    )
    assert value["training_free_baseline"]["selection_effect"] == (
        "DIAGNOSTIC_BENCHMARK_ONLY"
    )

    def profile(winner: str) -> dict:
        eligible = {"memorization_pass": True, "all_development_gates_pass": True}
        if winner == "192":
            delta = {
                "q05_target_auc_point_192_minus_96": 0.02,
                "q05_target_auc_lower_95": 0.01,
                "dark_cable_auc_point_192_minus_96": 0.01,
            }
        else:
            delta = {
                "q05_target_auc_point_192_minus_96": 0.003,
                "q05_target_auc_lower_95": -0.002,
                "dark_cable_auc_point_192_minus_96": 0.002,
            }
        return {"96": copy.deepcopy(eligible), "192": eligible, "paired_delta": delta}

    all_192 = {key: profile("192") for key in (
        "ASSUMED_LOW", "ASSUMED_MODERATE", "ASSUMED_HIGH"
    )}
    assert decide_resolution(all_192)["global_decision"] == "SELECT_192_EXPLORATORY"
    mixed = {
        "ASSUMED_LOW": profile("96"),
        "ASSUMED_MODERATE": profile("192"),
        "ASSUMED_HIGH": profile("96"),
    }
    assert decide_resolution(mixed)["global_decision"] == (
        "NOISE_DEPENDENT_DEFER_TO_MEASURED_CAMERA_PROFILE"
    )


def test_resolution_noise_experiment_rejects_qualifying_claim(tmp_path: Path) -> None:
    value = json.loads(RESOLUTION_EXPERIMENT.read_text(encoding="utf-8"))
    value["loader_mode"] = "QUALIFYING"
    core = {key: item for key, item in value.items() if key != "bundle_sha256"}
    value["bundle_sha256"] = sha256_bytes(canonical(core))
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="qualifying mode is forbidden"):
        load_resolution_noise_experiment(path)


def test_paired_height_model_retains_192_detail_until_final_pool() -> None:
    torch = pytest.importorskip("torch")
    pre_adaptive_shapes = {}
    for size in (96, 192):
        model = paired_height_resolution_spatial_model(torch, size)
        assert sum(parameter.numel() for parameter in model.parameters()) == 43_321
        pool = list(model.children())[11]
        assert isinstance(pool, torch.nn.AvgPool2d)
        assert pool.kernel_size == size // 24
        value = torch.zeros((1, 12, size, size), dtype=torch.float32)
        for layer in list(model.children())[:11]:
            value = layer(value)
        pre_adaptive_shapes[size] = tuple(value.shape)
        value = list(model.children())[11](value)
        assert tuple(value.shape) == (1, 64, 6, 6)
    assert pre_adaptive_shapes == {
        96: (1, 64, 24, 24),
        192: (1, 64, 48, 48),
    }


def test_torch_feature_expansion_matches_frozen_numpy_contract() -> None:
    np = pytest.importorskip("numpy")
    torch = pytest.importorskip("torch")
    rng = np.random.default_rng(55001)
    reference = rng.integers(0, 256, size=(96, 96, 3), dtype=np.uint8)
    observation = rng.integers(0, 256, size=(96, 96, 3), dtype=np.uint8)
    expected = paired_height_contract._construct_features_from_model_inputs(
        reference,
        observation,
        output_size_px=96,
        safe_half_extent_mm=[6.0, 6.0],
        physical_footprint_mm=48.0,
    )
    actual = paired_height_features_from_normalized_torch(
        torch.from_numpy(expected[0:3][None]),
        torch.from_numpy(expected[3:6][None]),
        torch.from_numpy(expected[11:12][None]),
        torch.zeros(11),
        torch.ones(11),
    )[0].numpy()
    np.testing.assert_allclose(actual, expected, rtol=2.0e-5, atol=2.0e-5)


def test_twelve_channel_features_are_deterministic_and_preserve_thin_line() -> None:
    import numpy as np

    profile, _ = load_resolution_noise_experiment(RESOLUTION_EXPERIMENT)
    camera = profile["noise_profiles"][1]["camera_profile"]
    reference = np.full((400, 400, 3), 150, dtype=np.uint8)
    observation = reference.copy()
    observation[:, 197:203] = 35
    outputs = {}
    for size in (96, 192):
        first = construct_paired_height_features(
            reference,
            observation,
            reference_aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
            observation_aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
            output_size_px=size,
            reference_seed=101,
            observation_seed=202,
            camera_profile=camera,
            safe_half_extent_mm=[7.0, 7.0],
        )
        second = construct_paired_height_features(
            reference,
            observation,
            reference_aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
            observation_aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
            output_size_px=size,
            reference_seed=101,
            observation_seed=202,
            camera_profile=camera,
            safe_half_extent_mm=[7.0, 7.0],
        )
        assert first.shape == (12, size, size)
        assert first.dtype == np.float32
        assert np.array_equal(first, second)
        assert float(first[9].max()) > 0.0
        assert float(first[10].max()) > 0.0
        assert set(np.unique(first[11])) == {0.0, 1.0}
        delivered_reference = apply_camera_model_native(
            reference, seed=101, camera_profile=camera, qualifying=False
        )
        delivered_observation = apply_camera_model_native(
            observation, seed=202, camera_profile=camera, qualifying=False
        )
        shared_native = construct_paired_height_features_from_delivered(
            delivered_reference,
            delivered_observation,
            reference_aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
            observation_aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
            output_size_px=size,
            safe_half_extent_mm=[7.0, 7.0],
        )
        assert np.array_equal(first, shared_native)
        outputs[size] = first
    assert outputs[192][11].sum() > outputs[96][11].sum() * 3.5


def test_training_statistics_scale_each_resolution_and_preserve_mask() -> None:
    import numpy as np

    rng = np.random.default_rng(771)
    base = rng.normal(0.5, 0.2, (12, 24, 24)).astype(np.float32)
    base[11] = 0.0
    base[11, 6:18, 6:18] = 1.0
    low_resolution = base.copy()
    high_resolution = np.repeat(np.repeat(base, 2, axis=1), 2, axis=2)
    high_resolution[:11] *= 0.5
    standardized = {}
    for name, value in (("96", low_resolution), ("192", high_resolution)):
        accumulator = new_feature_statistics_accumulator()
        update_feature_statistics(accumulator, value)
        statistics = finalize_feature_statistics(accumulator)
        result = apply_feature_standardization(value, statistics)
        assert np.allclose(result[:11].mean(axis=(1, 2)), 0.0, atol=2e-5)
        assert np.allclose(result[:11].std(axis=(1, 2)), 1.0, atol=2e-5)
        assert np.array_equal(result[11], value[11])
        standardized[name] = result
    assert np.allclose(
        standardized["96"][:11], standardized["192"][:11, ::2, ::2], atol=2e-5
    )


def test_memorization_selection_is_training_only_balanced_and_deterministic() -> None:
    rows = []
    decisions = {"clear": "VISIBLE", "cable": "ABSTAIN"}
    for target in ("A", "B", "C"):
        for variant in decisions:
            for index in range(8):
                rows.append({
                    "row_id": f"training:scene-{index}:{target}:{variant}",
                    "split": "training",
                    "device": "keyboard",
                    "target_id": target,
                    "variant_id": variant,
                })
    first = select_memorization_rows(rows, decisions, count=24)
    second = select_memorization_rows(list(reversed(rows)), decisions, count=24)
    assert [row["row_id"] for row in first] == [row["row_id"] for row in second]
    strata = {(row["target_id"], decisions[row["variant_id"]]) for row in first}
    assert len(strata) == 6
    altered = [dict(row) for row in rows]
    altered[0]["split"] = "development"
    with pytest.raises(ValueError, match="training rows only"):
        select_memorization_rows(altered, decisions, count=24)


def test_training_free_score_uses_only_safe_region_rgb_difference() -> None:
    import numpy as np

    features = np.zeros((12, 8, 8), dtype=np.float32)
    features[11, 2:6, 2:6] = 1.0
    features[6:9, 2:6, 2:6] = 0.25
    features[6:9, :2, :] = 1.0
    features[9:11] = 10.0
    assert training_free_difference_score(features) == pytest.approx(0.25)


def test_wide_safe_region_is_intersected_with_visible_physical_crop() -> None:
    import numpy as np

    profile, _ = load_resolution_noise_experiment(RESOLUTION_EXPERIMENT)
    camera = profile["noise_profiles"][0]["camera_profile"]
    native = np.full((400, 400, 3), 120, dtype=np.uint8)
    features = construct_paired_height_features(
        native,
        native,
        reference_aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
        observation_aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
        output_size_px=96,
        reference_seed=1,
        observation_seed=1,
        camera_profile=camera,
        safe_half_extent_mm=[48.0, 7.0],
    )
    assert np.all(features[11].sum(axis=1) % 96 == 0)
    assert features[11].sum() == 96 * 28


def test_frozen_fixture_counts_and_balances_heights() -> None:
    fixture, _ = load_fixture(FIXTURE)
    assert len(fixture["targets"]) == 80
    assert expected_counts(fixture) == fixture["planned_counts"] == {
        "training_source_rows": 46080,
        "development_source_rows": 69120,
        "total_source_rows": 115200,
        "stored_native_crop_pngs": 115200,
        "derived_model_tensors_per_loader_epoch": 230400,
    }
    training_heights = list(fixture["split_identities"]["training_scene_height_mm"].values())
    assert {height: training_heights.count(height) for height in set(training_heights)} == {
        700: 6,
        850: 5,
        1000: 5,
    }
    assert fixture["camera"]["center_board_xy_mm"] == [333.5044034818228, 228.5]
    assert "context_physical_extent_xy_mm" not in fixture["output_contract"]
    assert fixture["rerender_contract"]["rejected_v1_3_row_reuse_forbidden"] is True


def test_rows_are_deterministic_and_development_is_height_paired() -> None:
    fixture, _ = load_fixture(FIXTURE)
    first = list(iter_row_identities(fixture, "training"))[:20]
    assert first == list(iter_row_identities(fixture, "training"))[:20]
    assert len({row["camera_sample_seed"] for row in first}) == len(first)
    selected = [
        row
        for row in iter_row_identities(fixture, "development")
        if row["scene_id"] == "v5_development_scene_01"
        and row["appearance_id"] == "v5_development_light_01"
        and row["device"] == "keyboard"
        and row["target_id"] == "A"
        and row["variant_id"] == "clear"
    ]
    assert [row["height_board_mm"] for row in selected] == [700, 850, 1000]


def _write_manifest(tmp_path: Path, fixture: dict, fixture_raw: bytes) -> Path:
    identity = next(
        iter_row_identities(
            fixture,
            "training",
            scene_ids={"v5_training_scene_01"},
            target_keys={"keyboard:A"},
        )
    )
    # The selected shard has all appearances and variants for one target/scene.
    identities = list(
        iter_row_identities(
            fixture,
            "training",
            scene_ids={"v5_training_scene_01"},
            target_keys={"keyboard:A"},
        )
    )
    rows = []
    allowlist = []
    for row in identities:
        path = f"{row['row_id'].replace(':', '_')}_native.png"
        allowlist.append(path)
        rows.append(
            {
                **row,
                "native_crop": {
                    "path": path,
                    "sha256": hashlib.sha256(path.encode()).hexdigest(),
                    "size_px": [400, 400],
                    "full_frame_integer_bounds_px": [100, 200, 500, 600],
                    "aligned_model_crop_box_px": [0.25, 0.5, 399.25, 399.5],
                },
            }
        )
    assert identity in identities
    payload = {
        "schema": SHARD_SCHEMA,
        "fixture_file_sha256": sha256_bytes(fixture_raw),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "split": "training",
        "shard": {"scene_ids": ["v5_training_scene_01"], "target_keys": ["keyboard:A"]},
        "observations": rows,
        "file_allowlist": allowlist,
    }
    path = tmp_path / "manifest.json"
    path.write_bytes(canonical(payload) + b"\n")
    return path


def test_exact_shard_admission_and_tampering_rejection(tmp_path: Path) -> None:
    fixture, fixture_raw = load_fixture(FIXTURE)
    manifest = _write_manifest(tmp_path, fixture, fixture_raw)
    receipt = admit_shard_manifest(FIXTURE, manifest)
    assert receipt["source_row_count"] == 36
    assert receipt["stored_native_crop_png_count"] == 36

    payload = json.loads(manifest.read_text())
    payload["observations"][0]["native_crop"]["full_frame_integer_bounds_px"][0] = 101
    manifest.write_bytes(canonical(payload) + b"\n")
    with pytest.raises(ValueError, match="YUY2 pairs"):
        admit_shard_manifest(FIXTURE, manifest)


def test_exact_admission_rejects_out_of_frame_crop_before_pixel_read(tmp_path: Path) -> None:
    fixture, fixture_raw = load_fixture(FIXTURE)
    manifest = _write_manifest(tmp_path, fixture, fixture_raw)
    payload = json.loads(manifest.read_text())
    native = payload["observations"][0]["native_crop"]
    native["full_frame_integer_bounds_px"] = [5200, 200, 5600, 600]
    manifest.write_bytes(canonical(payload) + b"\n")
    with pytest.raises(ValueError, match="outside the full frame"):
        admit_shard_manifest(FIXTURE, manifest)


def test_evaluation_split_is_rejected(tmp_path: Path) -> None:
    fixture, fixture_raw = load_fixture(FIXTURE)
    manifest = _write_manifest(tmp_path, fixture, fixture_raw)
    payload = json.loads(manifest.read_text())
    payload["split"] = "evaluation"
    manifest.write_bytes(canonical(payload) + b"\n")
    with pytest.raises(ValueError, match="evaluation or unknown split"):
        admit_shard_manifest(FIXTURE, manifest)


def _camera_profile(*, measured: bool = False) -> dict:
    return {
        "profile_id": "brightness-curve",
        "measurement_scope": (
            "MEASURED_B0477_LOCKED_SETTINGS" if measured else "EXPLORATORY_ASSUMED"
        ),
        "source_burst_sha256": "1" * 64,
        "source_tone_sweep_sha256": "2" * 64,
        "brightness_domain": "LINEAR_0_1",
        "brightness_knots_linear": [0.0, 0.25, 0.5, 0.75, 1.0],
        "noise_stddev_knots_linear": [0.002, 0.004, 0.006, 0.008, 0.01],
        "channel_noise_scale_rgb": [1.0, 1.0, 1.0],
        "sensor_quantization_bits": 12,
        "white_balance_rgb": [1.0, 1.0, 1.0],
        "tone_curve_linear_knots": [0.0, 0.1, 0.25, 0.5, 0.75, 1.0],
        "tone_curve_output_knots": [0.0, 0.32, 0.53, 0.74, 0.9, 1.0],
        "spatial_noise_kernel": [[0.15, 0.35, 0.15], [0.35, 1.0, 0.35], [0.15, 0.35, 0.15]],
        "processing_controls": {
            "denoise_disabled": False,
            "sharpening_disabled": False,
            "disable_attempted": True,
            "settings_receipt_sha256": "3" * 64,
        },
    }


def test_camera_model_runs_before_resampling_and_requires_noise_for_qualification() -> None:
    import numpy as np

    native = np.full((400, 400, 3), 80, dtype=np.uint8)
    native[:, 198:202] = [12, 12, 12]
    with pytest.raises(ValueError, match="requires measured B0477 noise"):
        derive_model_input(
            native,
            aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
            output_size_px=96,
            seed=7,
            camera_profile=None,
            qualifying=True,
        )
    output_96 = derive_model_input(
        native,
        aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
        output_size_px=96,
        seed=7,
        camera_profile=_camera_profile(),
        qualifying=False,
    )
    output_192 = derive_model_input(
        native,
        aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
        output_size_px=192,
        seed=7,
        camera_profile=_camera_profile(),
        qualifying=False,
    )
    assert output_96.shape == (96, 96, 3)
    assert output_192.shape == (192, 192, 3)
    clear_96 = np.concatenate((output_96[:, :40], output_96[:, 56:]), axis=1)
    clear_192 = np.concatenate((output_192[:, :80], output_192[:, 112:]), axis=1)
    assert float(clear_96.std()) < float(clear_192.std())


def test_qualifying_profile_requires_measured_brightness_curve() -> None:
    import numpy as np

    with pytest.raises(ValueError, match="measured B0477 profile"):
        derive_model_input(
            np.full((400, 400, 3), 128, dtype=np.uint8),
            aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
            output_size_px=192,
            seed=9,
            camera_profile=_camera_profile(),
            qualifying=True,
        )
    output = derive_model_input(
        np.full((400, 400, 3), 128, dtype=np.uint8),
        aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
        output_size_px=192,
        seed=9,
        camera_profile=_camera_profile(measured=True),
        qualifying=True,
    )
    assert output.shape == (192, 192, 3)
    linear_tone = _camera_profile(measured=True)
    linear_tone["tone_curve_output_knots"] = list(linear_tone["tone_curve_linear_knots"])
    linear_output = derive_model_input(
        np.full((400, 400, 3), 128, dtype=np.uint8),
        aligned_crop_box_px=[0.0, 0.0, 400.0, 400.0],
        output_size_px=192,
        seed=9,
        camera_profile=linear_tone,
        qualifying=True,
    )
    assert not np.array_equal(output, linear_output)
    assert noise_stddev_for_linear_brightness(_camera_profile(), 0.8) > (
        noise_stddev_for_linear_brightness(_camera_profile(), 0.1)
    )
    malformed = _camera_profile(measured=True)
    malformed["brightness_knots_linear"] = [0.0, 0.5, 0.5, 0.75, 1.0]
    with pytest.raises(ValueError, match="noise curve is malformed"):
        noise_stddev_for_linear_brightness(malformed, 0.5)


def test_spatial_noise_kernel_creates_neighbor_correlation() -> None:
    import numpy as np

    impulse = np.zeros((9, 9, 1), dtype=np.float32)
    impulse[4, 4, 0] = 1.0
    independent = spatially_correlate_noise(impulse, [[1.0]])
    correlated = spatially_correlate_noise(
        impulse, [[0.0, 0.25, 0.0], [0.25, 1.0, 0.25], [0.0, 0.25, 0.0]]
    )
    assert independent[4, 5, 0] == 0.0
    assert correlated[4, 5, 0] > 0.0
    assert np.isclose(float(np.sqrt(np.sum(correlated**2))), 1.0)
