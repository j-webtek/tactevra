import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "software" / "ai" / "eval" / "build_residual_obstruction_physical_pilot_predeclaration.py"
SPEC = importlib.util.spec_from_file_location("physical_pilot", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
REMEDY = ROOT / "software" / "ai" / "eval" / "residual_obstruction_v4_2_remedy_classification_v1.json"
COMMIT = "579ca70f1fe95bcafd4cd94e447fbbf0c95fecef"


def test_pilot_freezes_boundary_labeling_escrow_and_energy_state():
    result = MODULE.build(REMEDY, COMMIT)
    rows = {row["nominal_fraction"]: row for row in result["coverage_contract"]}
    assert rows[0.10]["expected_decision"] == "VISIBLE"
    assert rows[0.20]["expected_decision"] == "EITHER_REPORTED"
    assert rows[0.20]["primary_metric_included"] is False
    assert rows[0.30]["expected_decision"] == rows[0.60]["expected_decision"] == "ABSTAIN"
    assert result["boundary_scoring"]["silent_exclusion_prohibited"] is True
    assert result["coverage_measurement"]["methods_required"] == [
        "MEASURED_PLACEMENT_TEMPLATE", "INDEPENDENT_HAND_ANNOTATED_MASK",
    ]
    assert result["data_use"]["measurement_rows_may_train_model"] is False
    assert result["data_use"]["escrow_pixels_opened"] is False
    assert result["capture_safety"]["arm_deenergized_during_every_capture"] is True
    assert result["capture_safety"]["capture_phase_robot_movement_count"] == 0
    assert result["capture_matrix"]["maximum_relative_lighting_drift"] is None


def test_pilot_rejects_source_that_selected_v5(tmp_path):
    changed = copy.deepcopy(json.loads(REMEDY.read_text(encoding="utf-8")))
    changed["invariants"]["v5_selected"] = True
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="before v5 selection"):
        MODULE.build(path, COMMIT)


def test_pilot_rejects_source_without_cable_backstop(tmp_path):
    changed = copy.deepcopy(json.loads(REMEDY.read_text(encoding="utf-8")))
    changed["invariants"]["cable_detector_backstop_required"] = False
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="required backstop"):
        MODULE.build(path, COMMIT)
