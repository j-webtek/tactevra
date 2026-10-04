import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "software" / "ai" / "eval" / "probe_physical_charuco_readiness.py"
SPEC = importlib.util.spec_from_file_location("charuco_probe", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
DEFINITION = ROOT / "active-project" / "RoCell_v0_3" / "fiducials" / "charuco_board_definition.json"
PDF = ROOT / "active-project" / "RoCell_v0_3" / "fiducials" / "charuco_5x7_square25_marker17_5_1to1.pdf"


def test_no_camera_emits_blocked_zero_effect_receipt():
    result = MODULE.build_receipt(
        source_commit="b13e492636178e54ad502dfb7bfa9c8df1084c79",
        camera_output=b"No devices were found on the system.\r\n",
        image_output=b"No devices were found on the system.\r\n",
        opencv={"opencv_version": "5.0.0", "numpy_version": "2.5.3", "aruco_available": True, "generated_asset_charuco_corners": 24},
        board_definition_path=DEFINITION,
        board_pdf_path=PDF,
    )
    assert result["status"] == "BLOCKED"
    assert result["camera_class_device_count"] == result["image_class_device_count"] == 0
    assert "no_connected_windows_camera_or_image_device" in result["blocked_reasons"]
    assert "production_charuco_target_not_retained_or_print_verified" in result["blocked_reasons"]
    assert result["tooling_smoke_board_definition"]["squares_x"] == 5
    assert result["production_board_contract"]["squares_x"] == 12
    assert result["production_board_contract"]["dictionary"] == "DICT_5X5_1000"
    assert result["production_board_asset_retained"] is False
    assert result["capture_count"] == 0
    assert result["calibration_solved"] is False
    assert result["reprojection_error_px"] is None
    assert result["diagnostic_target_is_qualification_threshold"] is False
    assert result["hardware_writes"] == result["physical_movements"] == 0
    assert result["physical_authority"] is False
