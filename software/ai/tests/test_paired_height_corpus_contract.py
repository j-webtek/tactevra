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
    canonical,
    decide_resolution,
    derive_model_input,
    expected_counts,
    iter_row_identities,
    load_fixture,
    load_resolution_noise_experiment,
    noise_stddev_for_linear_brightness,
    spatially_correlate_noise,
    sha256_bytes,
)
from train.run_residual_obstruction_v4_2_memorization import (  # noqa: E402
    paired_height_resolution_spatial_model,
)


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
    assert len(value["run_matrix"]) == 6

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
