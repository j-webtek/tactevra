from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import cv2


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "software/scripts/live_charuco_dataset_capture.py"
SPEC = importlib.util.spec_from_file_location("live_charuco_dataset_capture", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source_session = ROOT / "software/config/live_camera_feedback_session_20261015.json"
    source_target = ROOT / "software/config/charuco_b0477_10x7_25mm_17_5mm.json"
    source_pdf = ROOT / "output/pdf/b0477_charuco_10x7_25mm_17_5mm_a4.pdf"
    session, target, pdf = tmp_path / "session.json", tmp_path / "target.json", tmp_path / "target.pdf"
    session.write_bytes(source_session.read_bytes())
    target.write_bytes(source_target.read_bytes())
    pdf.write_bytes(source_pdf.read_bytes())
    evidence = tmp_path / "evidence.json"
    _write_json(evidence, {
        "schema": "rocell.charuco_print_scale_evidence.v1",
        "target_id": "b0477-charuco-10x7-25mm-17_5mm-v2",
        "target_definition_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "printed_pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "instrument_id": "CALIPER-001",
        "rigid_backing_confirmed": True,
        "opposite_extents_measured": True,
        "distributed_across_board": True,
        "horizontal_board_width_mm": [250.0, 250.1, 249.9, 250.2],
        "vertical_board_height_mm": [175.0, 174.9, 175.1, 175.2],
        "reviewed_by": "operator",
        "reviewed_utc": "2026-10-16T12:00:00Z",
    })
    return session, target, evidence, pdf


def test_preflight_accepts_exact_profile_split_and_eight_scale_checks(tmp_path: Path) -> None:
    session, target, evidence, pdf = _inputs(tmp_path)
    loaded_session, loaded_target, summary = MODULE.preflight(session, target, evidence, pdf)
    sequence = loaded_session["camera_baseline"]["intrinsics_dataset_precommit"]["capture_sequence"]
    assert len(sequence) == 26
    assert loaded_target["profile_scope"]["cross_mode_reuse"].startswith("FORBIDDEN")
    assert summary["horizontal_board_width_mm_mean"] == pytest.approx(250.05)
    assert summary["vertical_board_height_mm_mean"] == pytest.approx(175.05)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("rigid_backing_confirmed", False, "rigid_backing_confirmed"),
        ("horizontal_board_width_mm", [250.0] * 3, "at least 4"),
        ("vertical_board_height_mm", [175.0, 175.0, 175.0, 177.0], "scale tolerance"),
        ("printed_pdf_sha256", "0" * 64, "printable PDF"),
    ],
)
def test_preflight_fails_closed_before_camera_access(
    tmp_path: Path, field: str, value: object, message: str,
) -> None:
    session, target, evidence, pdf = _inputs(tmp_path)
    record = json.loads(evidence.read_text(encoding="utf-8"))
    record[field] = value
    _write_json(evidence, record)
    with pytest.raises(MODULE.CaptureGateError, match=message):
        MODULE.preflight(session, target, evidence, pdf)


def test_template_is_intentionally_not_capture_ready(tmp_path: Path) -> None:
    session, target, _evidence, pdf = _inputs(tmp_path)
    template = ROOT / "software/config/charuco_print_scale_evidence.template.json"
    with pytest.raises(MODULE.CaptureGateError):
        MODULE.preflight(session, target, template, pdf)


def test_generated_board_contract_exceeds_capture_corner_gate() -> None:
    target = json.loads(
        (ROOT / "software/config/charuco_b0477_10x7_25mm_17_5mm.json").read_text(
            encoding="utf-8"
        )
    )
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_1000)
    board = cv2.aruco.CharucoBoard((10, 7), 0.025, 0.0175, dictionary)
    image = board.generateImage((1200, 900), marginSize=0, borderBits=1)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    assessment = MODULE.assess_frame(encoded.tobytes(), target)
    assert assessment["accepted"] is True
    assert assessment["detected_charuco_corner_count"] >= 30
    assert assessment["registration_authority"] is False


def test_selected_target_matches_workcell_sizing_decision() -> None:
    target = json.loads(
        (ROOT / "software/config/charuco_b0477_10x7_25mm_17_5mm.json").read_text(
            encoding="utf-8"
        )
    )
    sizing = target["sizing_basis"]
    selected = next(row for row in sizing["alternatives"] if row["result"] == "SELECTED")
    assert [target["board_width_mm"], target["board_height_mm"]] == selected["geometry_mm"]
    assert (target["squares_x"] - 1) * (target["squares_y"] - 1) == 54
    assert sizing["workcell_inputs"]["board_size_xy_mm"] == [610.0, 457.0]
    assert target["board_width_mm"] < target["print_contract"]["page_width_mm"]
    assert target["board_height_mm"] < target["print_contract"]["page_height_mm"]
