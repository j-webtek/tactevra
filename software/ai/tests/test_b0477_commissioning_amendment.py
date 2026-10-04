import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "software/ai/eval/build_b0477_commissioning_amendment.py"
SPEC = importlib.util.spec_from_file_location("b0477_amendment", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
PROBE = ROOT / "software/ai/eval/physical_charuco_probe_blocked_v1.json"


def test_amendment_corrects_mode_and_freezes_precapture_gates():
    result = MODULE.build_amendment(
        source_commit="d5e26be9ca2a3e03cd10d49460d32db367da73be",
        probe_path=PROBE,
    )
    assert result["mode_correction"]["incorrect_fps_in_preserved_probe"] == 4
    assert result["calibration_runtime_mode"] == {
        "width_px": 5472,
        "height_px": 3648,
        "fps": 9.0,
        "pixel_format": "YUY2",
        "sensor_transform": "FULL_NATIVE_MODE",
    }
    assert result["optics_and_controls_gate"]["autofocus_disabled"] is True
    assert result["optics_and_controls_gate"]["auto_exposure_disabled"] is True
    assert result["optics_and_controls_gate"]["auto_white_balance_disabled"] is True
    scale = result["print_scale_measurement_gate"]
    assert scale["minimum_horizontal_measurements"] == 4
    assert scale["minimum_vertical_measurements"] == 4
    assert scale["maximum_axis_scale_error_fraction"] is None
    assert result["ready_for_capture"] is False
    assert result["camera_frames_requested"] == result["hardware_writes"] == 0
    assert result["physical_movements"] == 0
    assert result["physical_authority"] is False
